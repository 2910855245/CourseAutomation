//! 刷课核心循环 — 反检测参数与 study_worker.py LightStudyReporter 1:1 对齐

use std::collections::HashMap;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use rand::RngExt;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;
use tokio::task::JoinSet;

use crate::speed::{SpeedMode, SpeedProfile};

/// 全局请求间隔：跨所有任务共享，任意两个 HTTP 请求间隔 ≥ 0.5s
/// （实现集中在 platform_client::wait_rate_limit，与登录/扫描链路共用同一道闸）

/// 墙钟/时长比率已下沉为档位参数（[`SpeedProfile::wall_ratio`]）：
/// 急速/均衡档保留 2.1× 安全余量；保守档（纯串行）为 1.0 —— studyTime 报满
/// 立即收工、直接衔接下一节，不再把每节硬撑到 2.1×（用户 2026-09-30 拍板）。

/// studyTime 报满后的续报间隔（秒）。见 [`next_tick_secs`]。
const TAIL_TICK_SECS: f64 = 30.0;

/// 一次循环该睡多久（秒）。
///
/// 视频的时间轴分两段：
/// - `0 → actual_target`：studyTime 需要逐秒逼近目标，维持 1s 粒度；
/// - `actual_target → wall_ratio×时长`：studyTime 已报满，这段只是把墙钟撑满
///   （保守档 wall_ratio=1.0，该段为零：报满即收工）。
///
/// 原实现第二段仍按 1s 粒度空转并重复上报同一个 studyTime —— 一个 45 分钟的
/// 视频要多发约 3000 次内容完全相同的请求，且"1 秒不差"的节奏本身就是机器特征。
/// 改成 30s 一续报、最后一段按剩余时间精确睡到终点：请求数降两个数量级，
/// 末次上报仍落在墙钟终点（平台按首末上报的时间跨度判完成）。
fn next_tick_secs(past_target: bool, wall_left: f64) -> f64 {
    if !past_target {
        1.0
    } else {
        wall_left.clamp(0.0, TAIL_TICK_SECS)
    }
}

/// 平台连续拒收多少份上报，就判这一节失败。
///
/// 为什么要有上限：平台会明确回 `status=0` 拒收（实测是 MySQL 1062 唯一键冲突
/// `Duplicate entry 'studyId-时间' for key 'classDate'`）。此前不看 status，
/// 被拒了照样推进、墙钟走满就宣布完成 —— 于是订单显示 100%、平台上这一节一秒
/// 都没记上（真实案例：ORD-B2270270 的《12.3 压力应对》报了 43 次全被拒，
/// 平台进度 0%，我们却记了"127/127 完成"）。宁可显式失败，也不谎报完成。
const MAX_REJECTS: u32 = 6;

/// 撞上记账时间片时最多退避几个片（每片最长 20 分钟）
const MAX_SLOT_WAITS: u32 = 1;

/// 平台的记账时间片长度：唯一键 `classDate` 的分钟位只有 :00/:20/:40，
/// 即 **20 分钟一片**，同一节视频在同一片内只允许有一行。
const SLOT_SECS: i64 = 20 * 60;

/// 距离下一个记账时间片边界的秒数。
///
/// 实测：同一节在同一个片内第二次写入会被平台整条拒绝（1062），
/// 同片内怎么重试都写不进去 —— **只有换片才能落账**。
fn secs_to_next_slot() -> u64 {
    secs_to_next_slot_from(crate::queue::local_secs() as i64)
}

/// 同上，但时间自己给（便于单测，不依赖时钟）
fn secs_to_next_slot_from(now_secs: i64) -> u64 {
    (SLOT_SECS - now_secs.rem_euclid(SLOT_SECS)) as u64
}

/// 拒收阈值 / 退避时长 / 撞片退避开关都可用环境变量覆盖：
/// E2E 测试要把等待压到毫秒级，否则一次拒收用例要等半分钟。
fn max_rejects() -> u32 {
    std::env::var("STUDY_MAX_REJECTS").ok().and_then(|v| v.parse().ok()).unwrap_or(MAX_REJECTS)
}

fn reject_backoff() -> f64 {
    std::env::var("STUDY_REJECT_BACKOFF_SECS").ok().and_then(|v| v.parse().ok())
        .unwrap_or(1.5)
}

fn slot_wait_enabled() -> bool {
    std::env::var("STUDY_SLOT_WAIT").map(|v| v.trim() != "0").unwrap_or(true)
}

/// 进度百分比，收敛到 1 位小数：原始浮点（如 1/61 → 1.639344262295082）
/// 落库后会在订单页整串显示出来。
fn pct_of(done: u64, total: u64) -> f64 {
    if total > 0 { (done as f64 * 1000.0 / total as f64).round() / 10.0 } else { 0.0 }
}

/// 进程级同时在刷的视频会话上限（跨订单共享）。
///
/// 队列 worker 数可以调到几十，但每个订单内部还有自己的课程并发（急速档 8），
/// 两者相乘就是进程内的并发会话总数：64 worker × 8 = 512 路会话同时抢
/// [`crate::platform_client::wait_rate_limit`] 那道 0.5s 的全局闸门。闸门容量
/// 约 2 req/s，而单个会话上报密度约 4 次/分钟 —— 512 路会话意味着每路的上报
/// 被推迟十几倍，视频墙钟被拉长到不可用，还会让平台的会话超时。
///
/// 因此这里加一道闸把总会话数压住：worker 并发决定"同时处理多少个订单"，
/// 本上限决定"同时有多少路视频在跑"，后者才是真正贴着平台风险的旋钮。
/// 默认 32（约为闸门容量的 1.3 倍，留有余量），可用 `GLOBAL_STUDY_SESSIONS` 调整。
const DEFAULT_GLOBAL_SESSIONS: usize = 32;

fn global_session_limit() -> usize {
    std::env::var("GLOBAL_STUDY_SESSIONS")
        .ok()
        .and_then(|v| v.trim().parse::<usize>().ok())
        .filter(|n| *n > 0)
        .unwrap_or(DEFAULT_GLOBAL_SESSIONS)
}

/// 供管理端读取当前生效的全局会话上限
pub fn global_session_limit_public() -> usize {
    global_session_limit()
}

/// 全局会话信号量（进程内唯一，首个调用点初始化）
static GLOBAL_SESSIONS: tokio::sync::OnceCell<Arc<tokio::sync::Semaphore>> =
    tokio::sync::OnceCell::const_new();

async fn global_session_sem() -> &'static Arc<tokio::sync::Semaphore> {
    GLOBAL_SESSIONS
        .get_or_init(|| async { Arc::new(tokio::sync::Semaphore::new(global_session_limit())) })
        .await
}

fn make_client() -> Client {
    crate::platform_client::build_client_with_ua(
        crate::platform_client::SHORT_UA, true, None)
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Video {
    #[serde(default)]
    pub node_id: String,
    /// 视频总时长（秒）。`None` = 平台没给出可用时长（字段缺失/非数值/为 0）。
    ///
    /// 必须是 Option 而不是"0 兜底"：0 会让 `duration - viewed` 算出 0，
    /// 于是这一节被当成"已看完"瞬间跳过 —— 而扫描侧用的是另一套判据，
    /// 会把同一节算成"待刷"并据此收钱。两边结论相反的结果是：客户付了钱、
    /// 进度条爬到 100%、平台上一节都没动。拿不到时长就必须能表达"不知道"。
    #[serde(default)]
    pub duration: Option<u64>,
    /// 平台自报的时长（`videoDuration` 原值，未经媒体探测校准）。
    ///
    /// **判"是否已学"用它，判"还要刷多久"用 `duration`**：平台按它自己的
    /// 元数据算已学时长，所以"平台显示已学"的节必须按它的口径跳过、计入进度基数，
    /// 否则我们的进度永远比平台少几节（平台的元数据偶尔偏短，真实文件更长）。
    /// 真刷时仍以校准后的 `duration` 为准 —— 报满文件真长度平台才一定认账。
    #[serde(default)]
    pub platform_duration: Option<u64>,
    /// 平台**自己**的"已学"判定（节点 `state` 字段带"已学"）。
    ///
    /// 这是与平台页面 100% 对齐的唯一可靠依据：平台的判定比"看满总时长"宽
    /// （线上实测 `progress=0.98`、比 videoDuration 少 19 秒也照样标"已学"），
    /// 而校准后的文件真值又比平台元数据长 —— 拿数值比较必然少算几节。
    #[serde(default)]
    pub platform_done: bool,
    #[serde(default)]
    pub viewed_duration: u64,
    /// 视频文件地址。平台列表接口不返回时长，补时长要从文件本身读（见 scan 的媒体探测）。
    #[serde(default)]
    pub local_file: Option<String>,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub course_id: String,
}

/// 视频是否已在平台上刷满。
///
/// **扫描侧（计费/待刷统计）与刷课侧（是否跳过）必须共用这一个判据**。
/// 此前两边各写一套等价但不一致的判断，`duration` 一旦解析失败就会分叉：
/// 扫描判"要刷"（计费、入队），刷课判"已完成"（秒过、报 100%）。
/// 时长未知一律**不算已完成** —— 不知道就不许替客户宣布成功。
///
/// 口径以**平台自己的判定**为准（2026-10-01 用户拍板）：平台标"已学"的节，
/// 我们直接跳过并计入进度基数，后台进度才与平台页面一致；平台没给判定时，
/// 退回"看满平台自报时长"的数值比较，最后才用校准值兜底（仍保证
/// "不知道就不算完成"）。
pub fn video_is_done(v: &Video) -> bool {
    if v.platform_done {
        return true;
    }
    match v.platform_duration.or(v.duration) {
        Some(d) => v.viewed_duration >= d,
        None => false,
    }
}

#[derive(Debug, Deserialize)]
pub struct TaskInput {
    pub order_id: String,
    pub username: String,
    pub password: String,
    pub base_url: String,
    pub cookies: Vec<CookieKV>,
    pub videos: Vec<Video>,
    #[serde(default)]
    pub concurrency: usize,
    #[serde(default)]
    pub push_ws: bool,
    /// 刷课节奏档位（turbo/balanced/gentle；缺省/未知 → 均衡）
    #[serde(default)]
    pub speed_mode: String,
    /// 本轮开始前平台侧**已完成**的节数（扫描时判定已刷满、被跳过的那些）。
    ///
    /// 进度条的分母必须是"整单总节数"、分子起点必须是这个基数 —— 否则每次
    /// 重启/重扫都会从 1/剩余数 重爬：平台侧的成果一节没丢，界面上却表现为
    /// "进度被重置"（用户看到的百分比突然掉回 1%，其实只是把已完成的从分子里漏掉了）。
    #[serde(default)]
    pub already_done: u64,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct CookieKV {
    pub name: String,
    pub value: String,
}

/// cookie 过期（平台回 `offline=1`「登录超时,请重新登录」）后，允许的连续重登
/// 失败次数。超过即熔断、本单不再尝试登录：平台对错误尝试超 5 次即锁号，
/// 而视频是逐个跑的 —— 不加熔断会把登录尝试按视频数成倍放大。
const MAX_RELOGIN_FAILS: usize = 3;

struct Shared {
    client: Client,
    base_url: String,
    cookie_str: Mutex<String>,
    username: String,
    password: String,
    push_ws: bool,
    /// 随推送一起上报：服务端据此把消息投到 order:{id} topic
    order_id: String,
    /// 本任务的节奏档位参数（并发/错峰/请求间隔）
    profile: SpeedProfile,
    /// 本单连续重登失败次数（成功清零），见 [`MAX_RELOGIN_FAILS`]
    relogin_fails: AtomicUsize,
}

#[derive(Debug, Serialize)]
struct ReportForm<'a> {
    nodeId: &'a str,
    studyId: i64,
    studyTime: i64,
}

/// 平台对同一字段的类型并不稳定 —— 已实测到字符串 / 数字 / 布尔三种形态。
/// 数字字段一旦收到 `true`，整个响应反序列化就失败，一节视频会被判成失败，
/// 而这种"类型随意"并不是真的执行错误。这里统一做宽松转换。
fn lenient_i64<'de, D>(d: D) -> Result<i64, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let v = Option::<serde_json::Value>::deserialize(d)?;
    Ok(match v {
        Some(serde_json::Value::Number(n)) => n
            .as_i64()
            .or_else(|| n.as_f64().map(|f| f as i64))
            .unwrap_or(0),
        Some(serde_json::Value::String(s)) => s.trim().parse::<i64>().unwrap_or(0),
        // 布尔当真值用：true=1。平台把标志位塞进数字字段时就是这个形态
        Some(serde_json::Value::Bool(b)) => i64::from(b),
        _ => 0,
    })
}

fn lenient_bool<'de, D>(d: D) -> Result<bool, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let v = Option::<serde_json::Value>::deserialize(d)?;
    Ok(match v {
        Some(serde_json::Value::Bool(b)) => b,
        Some(serde_json::Value::Number(n)) => n.as_i64().unwrap_or(0) != 0,
        Some(serde_json::Value::String(s)) => {
            !matches!(s.trim().to_ascii_lowercase().as_str(), "" | "0" | "false" | "no")
        }
        _ => false,
    })
}

/// 字符串字段同样存在类型随意：实测平台会把 `msg`/`verifyToken` 写成 `null`。
/// `#[serde(default)]` 只兜"字段缺失"，字段存在但为 null 时仍整体解析失败 ——
/// 而带 null 的恰好是「需要验证码」这类响应，一失败整个 OCR 验证码流程
/// 就走不到，视频被直接计入失败。
fn lenient_string<'de, D>(d: D) -> Result<String, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let v = Option::<serde_json::Value>::deserialize(d)?;
    Ok(match v {
        Some(serde_json::Value::String(s)) => s,
        Some(serde_json::Value::Number(n)) => n.to_string(),
        Some(serde_json::Value::Bool(b)) => b.to_string(),
        _ => String::new(),
    })
}

#[derive(Debug, Deserialize)]
struct ReportResp {
    #[serde(default, deserialize_with = "lenient_i64")]
    status: i64,
    #[serde(default, deserialize_with = "lenient_i64")]
    state: i64,
    #[serde(default, deserialize_with = "lenient_i64")]
    studyId: i64,
    #[serde(default, deserialize_with = "lenient_i64")]
    need_code: i64,
    #[serde(default, deserialize_with = "lenient_string")]
    verifyToken: String,
    #[serde(default, deserialize_with = "lenient_bool")]
    offline: bool,
    #[serde(default, deserialize_with = "lenient_string")]
    msg: String,
}

async fn report_once(
    shared: &Shared,
    node_id: &str,
    study_id: i64,
    study_time: i64,
    force: bool,
) -> Result<ReportResp> {
    crate::speed::pace(&shared.profile).await;
    let mut params: HashMap<String, String> = HashMap::new();
    params.insert("nodeId".to_string(), node_id.to_string());
    params.insert("studyId".to_string(), study_id.to_string());
    params.insert("studyTime".to_string(), study_time.to_string());
    if force {
        params.insert("force".to_string(), "1".to_string());
    }
    let url = format!("{}/user/node/study", shared.base_url);
    let cookie = shared.cookie_str.lock().await.clone();
    let sent = shared
        .client
        .post(&url)
        .header("Cookie", cookie)
        .header("X-Requested-With", "XMLHttpRequest")
        .header("Accept-Language", "zh-CN,zh;q=0.9")
        .form(&params)
        .send()
        .await;
    let resp = match sent {
        Ok(r) => r,
        Err(e) => {
            crate::logs::error(crate::logs::CAT_REPORT, &shared.order_id, node_id,
                format!("上报失败 node={node_id} studyTime={study_time}: {e}"));
            return Err(e).with_context(|| format!("上报请求失败 node={node_id}"));
        }
    };
    let status_code = resp.status().as_u16();
    if status_code == 302 {
        let loc = resp.headers().get("location").and_then(|v| v.to_str().ok()).unwrap_or("");
        crate::logs::warn(crate::logs::CAT_REPORT, &shared.order_id, node_id,
            format!("上报被重定向，会话失效: {loc}"));
        return Err(anyhow::anyhow!("会话失效重定向: {loc}"));
    }
    let body: ReportResp = match resp.json().await {
        Ok(b) => b,
        Err(e) => {
            crate::logs::warn(crate::logs::CAT_REPORT, &shared.order_id, node_id,
                format!("上报响应解析失败 node={node_id}: {e}"));
            return Err(e).with_context(|| "上报响应解析失败");
        }
    };
    // 上报记录（面板「上报」分类的数据源）：请求参数与平台应答各留一份，
    // 复盘"这节为什么没刷动"时能直接看到平台当时的判断，不必再翻平台日志。
    crate::logs::info_detail(
        crate::logs::CAT_REPORT,
        &shared.order_id,
        node_id,
        format!("上报 studyTime={study_time} → status={} state={} need_code={}",
                body.status, body.state, body.need_code),
        serde_json::json!({
            "studyId": study_id,
            "studyTime": study_time,
            "force": force,
            "http": status_code,
            "status": body.status,
            "state": body.state,
            "need_code": body.need_code,
            "offline": body.offline,
            "msg": crate::logs::clip(&body.msg, 120),
        }),
    );
    Ok(body)
}

/// need_code 验证码处理：need_code=1 图形码走本地 OCR 引擎；
/// need_code=2 点选码不支持（原由 Python 后端 sidecar 处理，已随 Python 移除）
async fn handle_captcha(shared: &Shared, need_code: i64) -> Result<String> {
    if need_code == 2 {
        return Err(anyhow::anyhow!(
            "点选验证码(need_code=2)不支持，已随 Python 后端移除"
        ));
    }
    let engine = crate::ocr::engine().context("本地 OCR 引擎不可用")?;
    // 取图 → OCR → 本地预校验；结果不合格（长度不符/含噪声）就重新取图。
    // 无效结果提交给平台只会白送一次风控计数，重取的代价低得多。
    for attempt in 1..=3 {
        let r: u8 = rand::rng().random();
        let cap_url = format!("{}/service/code?r={}", shared.base_url, r);
        crate::speed::pace(&shared.profile).await;
        let img = shared.client.get(&cap_url)
            .header("Cookie", shared.cookie_str.lock().await.clone())
            .send().await.context("验证码图片获取失败")?
            .bytes().await.context("验证码图片读取失败")?;
        // 本地 OCR 识别（CPU 密集，放阻塞线程池）
        let bytes = img.to_vec();
        let code = tokio::task::spawn_blocking(move || engine.recognize(&bytes))
            .await.context("OCR 任务执行失败")?
            .context("验证码识别失败")?;
        let code = code.trim().to_string();
        if crate::ocr::plausible(&code) {
            eprintln!("[rust_worker] 验证码 OCR 识别成功: {code}（第 {attempt} 次取图）");
            return Ok(code);
        }
        eprintln!("[rust_worker] 验证码 OCR 结果不合格: {code:?}（第 {attempt} 次取图，重新取图）");
        tokio::time::sleep(Duration::from_secs_f64(0.3 * attempt as f64)).await;
    }
    anyhow::bail!("验证码 OCR 连续 3 次未识别出合法结果")
}

/// 刷单个视频：墙钟推进 + 自适应上报 + 验证码重试 + 档位墙钟比率
async fn study_video(shared: &Shared, video: &Video) -> Result<bool> {
    // 时长拿不到时绝不能当成"已完成"：那是假成功 —— 客户付了钱、进度条爬到
    // 100%、平台上一节都没动，而且不会有任何报错。宁可让这一单失败被看见。
    let Some(duration) = video.duration else {
        anyhow::bail!("视频时长无法获取，无法刷课（node={} 《{}》）", video.node_id, video.name);
    };
    let actual_target = duration.saturating_sub(video.viewed_duration);
    if actual_target == 0 {
        // 时长已知且已看满 → 真的不需要再刷
        return Ok(true);
    }
    // 全局会话闸：许可在整个视频生命周期内持有，把进程内并发会话总数压在上限内。
    // 等待期间不发任何请求，只是排队（因此不会对平台产生额外流量）。
    let _session_permit = match global_session_sem().await.clone().acquire_owned().await {
        Ok(p) => p,
        Err(_) => return Err(anyhow::anyhow!("全局会话闸已关闭")),
    };
    let start = Instant::now();
    let mut total_time: u64 = 0;
    let mut study_id: i64 = 0;
    let mut last_report: u64 = 0;
    // 平台**真正记上**的秒数：只有 status=1 的上报才算。完成判据用它，
    // 不用 total_time —— 后者只是"我们发了多少"，被拒的份一秒都没落账。
    let mut credited: u64 = 0;
    let mut rejections: u32 = 0;
    let mut slot_waits: u32 = 0;

    loop {
        // 报满 studyTime 后一次睡到下一续报点，不再每秒空转（见 next_tick_secs）
        let past_target = total_time >= actual_target;
        let wall_left = duration as f64 * shared.profile.wall_ratio
            - start.elapsed().as_secs_f64();
        let tick = next_tick_secs(past_target, wall_left);
        if tick > 0.0 {
            tokio::time::sleep(Duration::from_secs_f64(tick)).await;
        }
        // 本轮的推进量（秒）：未报满时恒为 1，报满后为一整个续报间隔
        let step = tick.max(1.0) as u64;
        total_time += step;

        // 自适应上报间隔（与原实现一致）
        let remaining = actual_target.saturating_sub(total_time.min(actual_target));
        let interval = match remaining {
            0..=5 => 1,
            6..=15 => 3,
            16..=30 => 5,
            31..=60 => 10,
            61..=180 => 15,
            181..=300 => 20,
            _ => 30,
        };
        let study_time = total_time.min(actual_target);
        let force = total_time == 1;
        // 首报必须立刻发：平台的"本次学习时长"从**第一份上报到达**时开始计时，
        // 而自适应间隔会把首报压到 interval 之后（大视频 30s）——会话起点随之晚 30s，
        // 收尾时平台只认到"墙钟 − 30"，于是每节都停在总长−20 秒、永远差一口气不判完成。
        if force || total_time >= actual_target || total_time - last_report >= interval {
            last_report = total_time;
            let mut retries = 0;
            loop {
                match report_once(shared, &video.node_id, study_id, study_time as i64, force).await {
                    Ok(resp) => {
                        if resp.state == 1 {
                            // 课程异常重置 studyId
                            study_id = 0;
                        } else if resp.studyId > 0 {
                            study_id = resp.studyId;
                        }
                        if resp.offline {
                            // cookie 失效（平台 `offline=1`「登录超时,请重新登录」）——
                            // 这是重登指令，不是"被踢"。此前直接 Err 判失败，
                            // 后面按 msg 含"会话失效"才重登的分支永远走不到，
                            // 过期账号因此循环空转不干活。
                            recover_offline(shared).await?;
                            // 旧会话的 studyId 作废，下一轮上报自动领新的
                            study_id = 0;
                            continue;
                        }
                        if resp.need_code == 1 || resp.need_code == 2 {
                            retries += 1;
                            if retries > 7 {
                                return Err(anyhow::anyhow!("验证码重试次数过多"));
                            }
                            // 识别失败（内部已重取 3 次）直接报错，继续硬试只会堆风控计数
                            let code = handle_captcha(shared, resp.need_code).await?;
                            // 带验证码重报
                            crate::speed::pace(&shared.profile).await;
                            let mut params: HashMap<String, String> = HashMap::new();
                            params.insert("nodeId".to_string(), video.node_id.clone());
                            params.insert("studyId".to_string(), study_id.to_string());
                            params.insert("studyTime".to_string(), study_time.to_string());
                            if resp.need_code == 1 && !code.is_empty() {
                                params.insert("code".to_string(), code);
                            }
                            let r2 = shared.client
                                .post(format!("{}/user/node/study", shared.base_url))
                                // 漏 Cookie = 匿名重报：平台只看登录态，不带会话
                                // 的重报验证码再对也过不了
                                .header("Cookie", shared.cookie_str.lock().await.clone())
                                .header("X-Requested-With", "XMLHttpRequest")
                                .form(&params)
                                .send()
                                .await
                                .context("验证码重报请求失败")?;
                            let body: ReportResp = r2.json().await.context("验证码重报响应解析失败")?;
                            if body.offline {
                                // 重报途中会话过期：走统一恢复路径（失败即熔断）
                                recover_offline(shared).await?;
                                study_id = 0;
                                continue;
                            }
                            if body.need_code == 0 {
                                // 验证码过了但平台仍拒收（如时间片冲突）：同样不算记上
                                if body.status != 1 {
                                    rejections += 1;
                                    crate::logs::warn(crate::logs::CAT_REPORT, &shared.order_id, &video.node_id,
                                        format!("验证码重报仍被平台拒收（第 {rejections} 次）: {}",
                                                crate::logs::clip(&body.msg, 90)));
                                    if rejections > max_rejects() {
                                        anyhow::bail!("平台连续拒收上报 {} 次（{}），这一节平台没记上",
                                                      max_rejects(), crate::logs::clip(&body.msg, 60));
                                    }
                                    tokio::time::sleep(Duration::from_secs_f64(
                                        reject_backoff() * rejections as f64)).await;
                                    continue;
                                }
                                if body.state == 1 { study_id = 0; }
                                else if body.studyId > 0 { study_id = body.studyId; }
                                credited = credited.max(study_time);
                                break;
                            }
                            // 验证码未被平台接受 → 退避后重新取图识别
                            tokio::time::sleep(Duration::from_secs_f64(0.3 * retries as f64)).await;
                            continue;
                        }
                        // 平台明确拒收（status=0，且不是掉线/验证码）：这一份一秒没记上。
                        // 必须挡在这里 —— 放过它就等于允许"被拒也照推进度"，最后墙钟走满
                        // 报 100%，平台上却还是未学。
                        if resp.status != 1 {
                            rejections += 1;
                            let slot_conflict = resp.msg.contains("Duplicate entry")
                                || resp.msg.contains("数据出现异常");
                            crate::logs::warn(crate::logs::CAT_REPORT, &shared.order_id, &video.node_id,
                                format!("上报被平台拒收（第 {rejections}/{} 次）: {}",
                                        max_rejects(), crate::logs::clip(&resp.msg, 90)));
                            if rejections > max_rejects() {
                                anyhow::bail!("平台连续拒收上报 {} 次（{}），这一节平台没记上",
                                              max_rejects(), crate::logs::clip(&resp.msg, 60));
                            }
                            if slot_conflict && slot_wait_enabled() && slot_waits < MAX_SLOT_WAITS {
                                // 同片内重试是纯浪费（实测 43 次全撞在同一个片上），
                                // 只有跨过片边界才能写进去
                                slot_waits += 1;
                                let wait = secs_to_next_slot() + 3;
                                crate::logs::warn(crate::logs::CAT_REPORT, &shared.order_id, &video.node_id,
                                    format!("撞上平台 20 分钟记账片（同一节同片只能写一行），退避 {wait}s 到下一片再报"));
                                tokio::time::sleep(Duration::from_secs(wait)).await;
                            } else {
                                tokio::time::sleep(Duration::from_secs_f64(
                                    reject_backoff() * rejections as f64)).await;
                            }
                            continue;
                        }
                        credited = credited.max(study_time);
                        break;
                    }
                    Err(e) => {
                        let msg = e.to_string();
                        if msg.contains("会话失效") {
                            // 掉线 → 尝试 relogin sidecar
                            if let Ok(true) = relogin(shared).await {
                                continue;
                            }
                        }
                        return Err(e);
                    }
                }
            }
        }

        // 完成条件：**平台已记账的** studyTime 报满 + 墙钟 ≥ 比率×时长
        // （保守档比率=1.0，报满即收工）。
        // 判据必须是 credited 而不是 total_time：total_time 只代表"我们发了多少"，
        // 被平台拒收的份一秒都没落账，拿它判完成就是假成功。
        if credited >= actual_target
            && start.elapsed().as_secs_f64() >= duration as f64 * shared.profile.wall_ratio
        {
            return Ok(true);
        }
    }
}

/// 掉线重登：本地登录（验证码由内置 OCR 识别），更新共享 cookie。
/// 计数统一在这里维护：成功清零、失败递增（调用方据 [`MAX_RELOGIN_FAILS`] 熔断）。
async fn relogin(shared: &Shared) -> Result<bool> {
    if shared.username.is_empty() {
        return Ok(false);
    }
    match crate::login::login_school(&shared.base_url, &shared.username, &shared.password).await {
        Ok(session) => {
            let mut guard = shared.cookie_str.lock().await;
            *guard = session.cookie_str;
            shared.relogin_fails.store(0, Ordering::Relaxed);
            eprintln!("[rust_worker] 重新登录成功（{}）", shared.username);
            Ok(true)
        }
        Err(e) => {
            let n = shared.relogin_fails.fetch_add(1, Ordering::Relaxed) + 1;
            eprintln!("[rust_worker] 重新登录失败（连续 {n}/{MAX_RELOGIN_FAILS}）: {e:#}");
            Ok(false)
        }
    }
}

/// 平台回 `offline=1`（cookie 过期）时的统一恢复路径：
/// 熔断检查 → 重登 → 成功返回 Ok（调用方 `continue` 续刷），否则返回错误。
async fn recover_offline(shared: &Shared) -> Result<()> {
    if shared.relogin_fails.load(Ordering::Relaxed) >= MAX_RELOGIN_FAILS {
        anyhow::bail!("账号被强制下线（重登连续失败 {MAX_RELOGIN_FAILS} 次，已熔断防锁号）");
    }
    eprintln!("[rust_worker] cookie 过期（{}），尝试重新登录", shared.username);
    if matches!(relogin(shared).await, Ok(true)) {
        return Ok(());
    }
    anyhow::bail!("账号被强制下线且重新登录失败");
}

/// 心跳：随机 90-150s 一次 POST /user/online
async fn heartbeat_loop(shared: Arc<Shared>) {
    loop {
        let secs = rand::rng().random_range(90..=150);
        tokio::time::sleep(Duration::from_secs(secs)).await;
        crate::speed::pace(&shared.profile).await;
        // 心跳同样要带 cookie，否则平台侧看到的是一次匿名访问，等于没心跳
        let cookie = shared.cookie_str.lock().await.clone();
        let _ = shared.client
            .post(format!("{}/user/online", shared.base_url))
            .header("Cookie", cookie)
            .header("X-Requested-With", "XMLHttpRequest")
            .send().await;
    }
}

/// cookie 续期：每 30 分钟检查 /user/index，302/401/403 → relogin
async fn cookie_refresh_loop(shared: Arc<Shared>) {
    loop {
        tokio::time::sleep(Duration::from_secs(30 * 60)).await;
        if shared.username.is_empty() {
            continue;
        }
        crate::speed::pace(&shared.profile).await;
        // 与启动检查同一个坑：不带 cookie 的 /user/index 一定 302，
        // 结果是每 30 分钟白白触发一次重新登录（每单一轮 10 次登录尝试）
        let cookie = shared.cookie_str.lock().await.clone();
        let resp = shared.client
            .get(format!("{}/user/index", shared.base_url))
            .header("Cookie", cookie)
            .send().await;
        match resp {
            Ok(r) if matches!(r.status().as_u16(), 302 | 401 | 403) => {
                eprintln!("[rust_worker] cookie 过期，尝试重新登录");
                match relogin(&shared).await {
                    Ok(true) => eprintln!("[rust_worker] 重新登录成功"),
                    Ok(false) => eprintln!("[rust_worker] 重新登录失败"),
                    Err(e) => eprintln!("[rust_worker] 重新登录异常: {e}"),
                }
            }
            _ => {}
        }
    }
}

async fn push_ws(shared: &Shared, mut data: serde_json::Value, push_url: &str, push_token: &str) {
    if !shared.push_ws {
        return;
    }
    // 载荷必须带 order_id：服务端据此确定广播 topic，前端据此路由到具体订单
    if let Some(obj) = data.as_object_mut() {
        obj.insert("order_id".to_string(), serde_json::Value::from(shared.order_id.clone()));
    }
    let _ = shared.client
        .post(push_url)
        .header("Content-Type", "application/json")
        .header("X-Worker-Token", push_token)
        .json(&data)
        .timeout(Duration::from_secs(2))
        .send().await;
}

/// 后台协程守卫：把心跳/续期任务的 JoinHandle 绑定到 run_study 的函数帧上。
///
/// 管理端「取消」掐的是外层任务（AbortHandle::abort），外层 future 被 drop 后
/// 函数末尾的显式 abort() 根本不会执行，两个 loop 会被分离并带 Arc<Shared>
/// 一直活着 —— 用已取消账号的 cookie 持续打平台。Drop 里统一收尾，取消也干净。
struct BackgroundTasks(Vec<tokio::task::JoinHandle<()>>);

impl Drop for BackgroundTasks {
    fn drop(&mut self) {
        for h in &self.0 {
            h.abort();
        }
    }
}

pub async fn run_study(task: &TaskInput, push_url: &str, push_token: &str) -> Result<()> {
    let base_url = task.base_url.trim_end_matches('/').to_string();
    let profile = SpeedMode::parse(&task.speed_mode).profile();
    let client = make_client();
    let cookie_str = task.cookies.iter()
        .map(|c| format!("{}={}", c.name, c.value))
        .collect::<Vec<_>>().join(";");

    let shared = Arc::new(Shared {
        client,
        base_url,
        cookie_str: Mutex::new(cookie_str),
        username: task.username.clone(),
        password: task.password.clone(),
        push_ws: task.push_ws,
        order_id: task.order_id.clone(),
        profile,
        relogin_fails: AtomicUsize::new(0),
    });

    // 启动时 cookie 有效性检查。
    // 必须显式带上会话 cookie：不带就是匿名请求，平台对 /user/index 一律 302 到
    // 登录页 → 每次启动都误判「cookie 已过期」并触发一次毫无必要的重新登录。
    if !task.username.is_empty() {
        let cookie = shared.cookie_str.lock().await.clone();
        let r = shared.client.get(format!("{}/user/index", shared.base_url))
            .header("Cookie", cookie)
            .send().await;
        if let Ok(resp) = r {
            if matches!(resp.status().as_u16(), 302 | 401 | 403) {
                eprintln!("[rust_worker] 启动时 cookie 已过期，尝试重新登录");
                let _ = relogin(&shared).await;
            }
        }
    }

    push_ws(&shared, serde_json::json!({"type": "progress", "phase": "video"}), push_url, push_token).await;

    // 心跳 + cookie 续期后台任务（生命周期由守卫绑定到本函数帧，见 BackgroundTasks）
    let _bg = BackgroundTasks(vec![
        tokio::spawn(heartbeat_loop(shared.clone())),
        tokio::spawn(cookie_refresh_loop(shared.clone())),
    ]);

    // 视频级调度：把整单的视频放进一个有 N 个槽位的池子里，而不是"每课程一个任务、
    // 课程内部串行"。
    //
    // 为什么按视频而不是按课程切：课程长度天然极不均 —— 真实账号里同一批课程是
    // 1 / 22 / 38 / 41 节。按课程切分时，最长那门会独占一个槽位直到最后，
    // 整单时长被它拖成 ≈ 2.1 × 最长课程的工作量；视频级调度让所有槽位一起排空，
    // 时长趋近 总工作量 / 并发数（同一批课实测可差 2~3 倍）。
    //
    // 平台可见的"beginTime/finalTime 重叠数"仍然是 ≤ 档位并发（急速 8，与旧版
    // 课程并发同值），没有多开会话；队列按课程轮转取视频，避免整段时间集中在一门课上。
    let mut buckets: HashMap<String, Vec<Video>> = HashMap::new();
    for v in &task.videos {
        buckets.entry(if v.course_id.is_empty() { "unknown".into() } else { v.course_id.clone() })
            .or_default().push(v.clone());
    }
    // 顺序确定（便于日志与测试复现），然后按课程轮转排队：A1 B1 C1 A2 B2 …
    let mut groups: Vec<(String, Vec<Video>)> = buckets.into_iter().collect();
    groups.sort_by(|a, b| a.0.cmp(&b.0));
    let max_len = groups.iter().map(|(_, vids)| vids.len()).max().unwrap_or(0);
    let mut queue: Vec<Video> = Vec::with_capacity(task.videos.len());
    for i in 0..max_len {
        for (_, vids) in &groups {
            if let Some(v) = vids.get(i) {
                queue.push(v.clone());
            }
        }
    }
    eprintln!("[rust_worker] 视频队列: {} 个课程 / {} 节（按课程轮转排队）",
              groups.len(), queue.len());
    crate::logs::info(crate::logs::CAT_REPORT, &task.order_id, "",
        format!("开始刷课：{} 个课程 / {} 节，档位 {}（并发 {} 路会话）",
                groups.len(), queue.len(), profile.mode.label(), profile.video_concurrency));

    // 分子起点 = 平台侧已完成的节数（见 TaskInput::already_done）：
    // done_counter 从基数递增，进度条才是"整单视角"的累计值，重启后不会归零。
    let done_counter = Arc::new(std::sync::atomic::AtomicU64::new(task.already_done));
    let failed_counter = Arc::new(std::sync::atomic::AtomicU64::new(0));
    // 本地判定"这一节完成了"的节点集合，收尾时拿去和平台的 state 对账
    let done_nodes: Arc<std::sync::Mutex<std::collections::HashSet<String>>> =
        Arc::new(std::sync::Mutex::new(std::collections::HashSet::new()));

    // 进度回报参数：闭包要 move 进去，先转成 owned；总节数在这里定死
    let push_url = push_url.to_string();
    let push_token = push_token.to_string();
    // 分母 = 已完成的 + 本轮待刷的 = 整单总节数
    let total_videos = task.already_done + queue.len() as u64;

    // 扫描后的第一帧立刻把基数报上去：不清这一下，重扫/重启后进度条会一直停在
    // 上一轮的旧值，直到下一节刷完才跳变 —— 后台看起来就像"进度比平台少几节"。
    push_ws(&shared, serde_json::json!({
        "type": "progress", "phase": "video",
        "progress": pct_of(task.already_done, total_videos),
        "done": task.already_done, "failed": 0, "total": total_videos,
        "step": format!("已刷 {}/{} 节", task.already_done, total_videos),
    }), &push_url, &push_token).await;

    // 视频并发闸：档位决定同时在跑几路会话（急速 8 / 均衡 4 / 温柔 1）。
    // 槽位满时后面的视频在此排队（不产生任何请求）。
    let video_sem = Arc::new(tokio::sync::Semaphore::new(profile.video_concurrency.max(1)));
    eprintln!("[rust_worker] 刷课档位 {}：并发 {} 路会话 / 启动错峰 {}ms",
              profile.mode.label(), profile.video_concurrency, profile.course_stagger_ms);

    let mut set = JoinSet::new();
    let mut first = true;
    for v in queue {
        let permit = match video_sem.clone().acquire_owned().await {
            Ok(p) => p,
            Err(_) => break,
        };
        // 拿到槽位后再错峰：保守档因此是"上一节结束 → 微停顿 → 下一节"，
        // 而不是把间隔藏在排队里（第一节不等待，保持原行为）
        if !first {
            profile.sleep_course_stagger().await;
        }
        first = false;
        let shared = shared.clone();
        let done_counter = done_counter.clone();
        let failed_counter = failed_counter.clone();
        let done_nodes = done_nodes.clone();
        let push_url = push_url.clone();
        let push_token = push_token.clone();
        set.spawn(async move {
            let _permit = permit;
            let t0 = Instant::now();
            let r = study_video(&shared, &v).await;
            let wall = t0.elapsed().as_secs();
            let order = std::sync::atomic::Ordering::Relaxed;
            let (done, failed) = match r {
                Ok(true) => {
                    let d = done_counter.fetch_add(1, order) + 1;
                    let f = failed_counter.load(order);
                    if let Ok(mut g) = done_nodes.lock() {
                        g.insert(v.node_id.clone());
                    }
                    eprintln!("[rust_worker] 视频完成 {}/{} 《{}》时长 {}s 墙钟 {}s",
                              d + f, total_videos, v.name, v.duration.unwrap_or(0), wall);
                    crate::logs::info(crate::logs::CAT_REPORT, &shared.order_id, &v.node_id,
                        format!("视频完成 {}/{}（{}%）《{}》时长 {}s 墙钟 {}s",
                                d + f, total_videos, pct_of(d, total_videos),
                                v.name, v.duration.unwrap_or(0), wall));
                    (d, f)
                }
                Ok(false) => {
                    let f = failed_counter.fetch_add(1, order) + 1;
                    eprintln!("[rust_worker] 视频未完成 {}/{} 《{}》墙钟 {}s",
                              f, total_videos, v.name, wall);
                    crate::logs::warn(crate::logs::CAT_REPORT, &shared.order_id, &v.node_id,
                        format!("视频未完成 {}/{} 《{}》墙钟 {}s（studyTime 未报满）",
                                f, total_videos, v.name, wall));
                    (done_counter.load(order), f)
                }
                Err(e) => {
                    let f = failed_counter.fetch_add(1, order) + 1;
                    eprintln!("[rust_worker] 视频失败 {}/{} 《{}》err={e:#}",
                              f, total_videos, v.name);
                    crate::logs::error(crate::logs::CAT_REPORT, &shared.order_id, &v.node_id,
                        format!("视频失败 {}/{} 《{}》err={e:#}", f, total_videos, v.name));
                    (done_counter.load(order), f)
                }
            };
            // 每节结束回报一次进度：进度条按**成功**节数走，
            // 失败的单独写在步骤文案里 —— 不能拿"尝试过的节数"冒充"刷成功的节数"。
            // 收敛到 1 位小数：原始浮点（如 1/61 → 1.639344262295082）落库后
            // 会在订单页整串显示出来
            let pct = pct_of(done, total_videos);
            let step = if failed > 0 {
                format!("已完成 {done}/{total_videos} 节（失败 {failed}）")
            } else {
                format!("已刷 {done}/{total_videos} 节")
            };
            push_ws(&shared, serde_json::json!({
                "type": "progress", "phase": "video",
                "progress": pct, "done": done, "failed": failed, "total": total_videos,
                "step": step,
            }), &push_url, &push_token).await;
        });
    }
    while set.join_next().await.is_some() {}

    drop(_bg);

    // ── 平台复核：唯一能戳穿"我们记了完成、平台其实没记上"的手段 ──
    //
    // 逐课程重拉一次平台的节列表（`/user/study_record/video`，与扫描同源），
    // 看平台自己的 state 里是不是「已学」。实测平台会因
    // (studyId, 20 分钟记账片) 唯一键冲突整条拒收上报 —— 只信本地"墙钟走满"
    // 就会出现订单 100%、平台一节没动（真实案例 ORD-B2270270）。
    //
    // 代价：每门课一次列表请求（多页），时长探测命中进程内缓存不再重复下载。
    // 值这个价 —— 谎报完成是客户投诉与退款的第一来源。
    let mut false_done = 0usize;
    {
        let cookie = shared.cookie_str.lock().await.clone();
        for (course_id, vids) in &groups {
            let mine: Vec<&Video> = match done_nodes.lock() {
                Ok(g) => vids.iter().filter(|v| g.contains(&v.node_id)).collect(),
                Err(p) => {
                    let g = p.into_inner();
                    vids.iter().filter(|v| g.contains(&v.node_id)).collect()
                }
            };
            if mine.is_empty() {
                continue;
            }
            match crate::scan::fetch_course_videos(&shared.client, &cookie, &shared.base_url,
                                                   course_id, "").await {
                // 列表为空说明这次复核没拿到有效数据（接口异常/课程已下架），
                // 不能据此判定"所有节都没完成" —— 那会把正常订单误判成失败。
                Ok(plat) if plat.is_empty() => {
                    crate::logs::warn(crate::logs::CAT_REPORT, &task.order_id, "",
                        format!("平台复核跳过（课程 {course_id} 的节列表为空）"));
                }
                Ok(plat) => {
                    let plat_done: std::collections::HashSet<&str> = plat.iter()
                        .filter(|v| v.platform_done)
                        .map(|v| v.node_id.as_str())
                        .collect();
                    let known: std::collections::HashSet<&str> =
                        plat.iter().map(|v| v.node_id.as_str()).collect();
                    for v in mine {
                        if plat_done.contains(v.node_id.as_str()) {
                            continue;
                        }
                        // 只在"平台列表里确实有这一节、且没标已学"时才判假完成；
                        // 节点不在列表里（被平台下架/换版本）只告警不扣分。
                        if known.contains(v.node_id.as_str()) {
                            false_done += 1;
                            crate::logs::warn(crate::logs::CAT_REPORT, &task.order_id, &v.node_id,
                                format!("平台未记账：本地判定完成，但平台 state 不是「已学」《{}》", v.name));
                        } else {
                            crate::logs::warn(crate::logs::CAT_REPORT, &task.order_id, &v.node_id,
                                format!("平台列表里找不到这一节，无法复核《{}》", v.name));
                        }
                    }
                }
                Err(e) => crate::logs::warn(crate::logs::CAT_REPORT, &task.order_id, "",
                    format!("平台复核跳过（读取课程 {course_id} 的节列表失败）：{e}")),
            }
        }
    }
    if false_done > 0 {
        // 从成功数里扣掉并计入失败：宁可让订单显式失败，也不报假 100%
        let order = std::sync::atomic::Ordering::Relaxed;
        done_counter.fetch_sub(false_done as u64, order);
        failed_counter.fetch_add(false_done as u64, order);
        crate::logs::warn(crate::logs::CAT_REPORT, &task.order_id, "",
            format!("平台复核发现 {false_done} 节本地记了完成、平台却是未学，已改为失败"));
    }

    let done = done_counter.load(std::sync::atomic::Ordering::Relaxed);
    let failed = failed_counter.load(std::sync::atomic::Ordering::Relaxed);
    // 与进度条同一口径：done 是从 already_done 起的累计值，分母也用整单总节数
    let total = total_videos;

    if failed > 0 {
        crate::logs::warn(crate::logs::CAT_REPORT, &task.order_id, "",
            format!("刷课结束（有失败）{done}/{total}，失败 {failed} 节"));
        anyhow::bail!("部分视频未完成 {done}/{total}");
    }
    eprintln!("[rust_worker] 任务完成 {done}/{total}");
    crate::logs::info(crate::logs::CAT_REPORT, &task.order_id, "",
        format!("刷课完成 {done}/{total} 节（100%）"));
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex as StdMutex;

    /// 退避必须正好落在平台的 20 分钟记账片边界上（:00/:20/:40），
    /// 否则退避完了还是同一个片，白白再撞一次唯一键。
    #[test]
    fn test_secs_to_next_slot_lands_on_boundary() {
        // 取几个代表性时刻：正落在边界、片开头、片末尾
        for now in [0i64, 1, 1_199, 1_200, 1_201, 1_792_000_000, 1_792_000_137] {
            let w = secs_to_next_slot_from(now) as i64;
            assert!((1..=SLOT_SECS).contains(&w), "now={now} 退避 {w}s 超出范围");
            assert_eq!((now + w).rem_euclid(SLOT_SECS), 0, "now={now} 退避后不在片边界");
        }
        // 片末尾（差 1 秒到边界）只需等 1 秒，不该等满一片
        assert_eq!(secs_to_next_slot_from(1_199), 1);
        // 刚好在边界上 → 当前片刚刚开始，只能等满一片
        assert_eq!(secs_to_next_slot_from(1_200), SLOT_SECS as u64);
    }

    /// 回归：报满 studyTime 后的"撑墙钟"阶段必须按 30s 粒度推进，
    /// 而不是 1s 空转（否则一个 45 分钟视频要多发上千次重复上报）
    #[test]
    fn test_tail_tick_avoids_per_second_spin() {
        // 未报满：维持 1s 粒度（studyTime 要逐秒逼近目标）
        assert_eq!(next_tick_secs(false, 9999.0), 1.0);
        assert_eq!(next_tick_secs(false, 0.2), 1.0);
        // 报满后：按 30s 续报
        assert_eq!(next_tick_secs(true, 300.0), TAIL_TICK_SECS);
        assert_eq!(next_tick_secs(true, 30.0), TAIL_TICK_SECS);
        // 尾段：按剩余时间精确睡到终点，不多睡
        assert!((next_tick_secs(true, 5.5) - 5.5).abs() < 1e-9);
        // 已到终点：不再睡（由完成判据收尾）
        assert_eq!(next_tick_secs(true, -3.0), 0.0);
    }

    // ── mock 平台 E2E：验证视频级调度的三条契约 ──────────────────────────
    //
    // mock 只实现 run_study 真正会打的端点，并记录每次上报的 (nodeId, 时刻)。
    // 不碰真实平台，也不依赖任何外部服务。

    /// 极简 HTTP/1.1 mock：POST /user/node/study → 记录上报并回成功 JSON，
    /// 其余路径一律 200（run_study 里只有启动 cookie 检查与心跳会走到）
    async fn spawn_mock_platform() -> (String, Arc<StdMutex<Vec<(String, f64)>>>) {
        spawn_mock_platform_with(false).await
    }

    /// `reject = true` 时上报一律回 `status=0`（模拟线上实测的
    /// `Duplicate entry ... for key 'classDate'` 拒收）
    async fn spawn_mock_platform_with(reject: bool) -> (String, Arc<StdMutex<Vec<(String, f64)>>>) {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let log: Arc<StdMutex<Vec<(String, f64)>>> = Arc::new(StdMutex::new(Vec::new()));
        let log2 = log.clone();
        let t0 = Instant::now();

        tokio::spawn(async move {
            loop {
                let Ok((mut sock, _)) = listener.accept().await else { continue };
                let log = log2.clone();
                tokio::spawn(async move {
                    use tokio::io::{AsyncReadExt, AsyncWriteExt};
                    let mut buf = Vec::new();
                    let mut tmp = [0u8; 4096];
                    // 读到 header 结束，再按 Content-Length 读 body
                    let (head_end, mut body) = loop {
                        let n = match sock.read(&mut tmp).await { Ok(0) | Err(_) => return, Ok(n) => n };
                        buf.extend_from_slice(&tmp[..n]);
                        if let Some(pos) = buf.windows(4).position(|w| w == b"\r\n\r\n") {
                            let head = String::from_utf8_lossy(&buf[..pos]).to_string();
                            let len: usize = head.lines()
                                .find_map(|l| l.to_ascii_lowercase().strip_prefix("content-length:")
                                    .map(|v| v.trim().parse().unwrap_or(0)))
                                .unwrap_or(0);
                            let rest = buf[pos + 4..].to_vec();
                            let body = if rest.len() >= len {
                                rest[..len].to_vec()
                            } else {
                                let mut b = rest;
                                while b.len() < len {
                                    let n = match sock.read(&mut tmp).await { Ok(0) | Err(_) => return, Ok(n) => n };
                                    b.extend_from_slice(&tmp[..n]);
                                }
                                b[..len].to_vec()
                            };
                            break (head, body);
                        }
                    };
                    // 收尾复核会 GET /user/study_record/video：回一份"平台已学"的列表。
                    // 不实现它，复核就会把 8 节全判成"平台未记账"，测试反而测不到正路。
                    if head_end.starts_with("GET") && head_end.contains("/user/study_record/video") {
                        let cid = head_end.split("courseId=").nth(1)
                            .map(|s| s.split(|c: char| !c.is_ascii_alphanumeric())
                                .next().unwrap_or("").to_string())
                            .unwrap_or_default();
                        let n = if cid == "A" { 1 } else { 7 };
                        let items: Vec<String> = (0..n).map(|i| format!(
                            r#"{{"id":"{cid}-n{i}","name":"{cid} 第{i}节","state":"<span style=\"color: #2bbc66\">已学</span>","videoDuration":"00:00:02","viewedDuration":"00:00:02","duration":"2","localFile":null}}"#
                        )).collect();
                        let payload = format!(
                            r#"{{"status":true,"list":[{}],"pageInfo":{{"pageCount":1}}}}"#,
                            items.join(","));
                        let resp = format!(
                            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                            payload.len(), payload);
                        let _ = sock.write_all(resp.as_bytes()).await;
                        let _ = sock.shutdown().await;
                        return;
                    }
                    let body = String::from_utf8_lossy(&body).to_string();
                    if body.contains("nodeId=") {
                        let node = body.split('&').find_map(|kv| kv.strip_prefix("nodeId="))
                            .unwrap_or("?").to_string();
                        log.lock().unwrap().push((node, t0.elapsed().as_secs_f64()));
                    }
                    let payload = if reject {
                        r#"{"status":0,"state":0,"studyId":0,"need_code":0,"offline":false,"msg":"提交失败"}"#
                    } else {
                        r#"{"status":1,"state":0,"studyId":1,"need_code":0,"offline":false,"msg":""}"#
                    };
                    let resp = format!(
                        "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                        payload.len(), payload);
                    let _ = sock.write_all(resp.as_bytes()).await;
                    let _ = sock.shutdown().await;
                });
            }
        });
        (format!("http://{addr}"), log)
    }

    fn mock_videos(course: &str, count: usize, duration: u64) -> Vec<Video> {
        (0..count).map(|i| Video {
            node_id: format!("{course}-n{i}"),
            duration: Some(duration),
            platform_duration: Some(duration),
            platform_done: false,
            viewed_duration: 0,
            local_file: None,
            name: format!("{course} 第{i}节"),
            course_id: course.to_string(),
        }).collect()
    }

    /// 核心回归：平台明确拒收（status=0）时**必须判失败**，不能照样报完成。
    ///
    /// 线上事故背景：平台因 (studyId, 20 分钟记账片) 唯一键冲突整条拒收上报，
    /// 而我们此前不看 status —— 墙钟走满就宣布"127/127 完成"，平台上那一节
    /// 一秒都没记上（客户看到 100%，后台一对账才发现差 2 节）。
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn test_rejected_reports_must_not_report_completion() {
        // 把拒收阈值与退避压到毫秒级，否则本用例要等半分钟
        std::env::set_var("PLATFORM_REQUEST_SPACING_SECS", "0");
        std::env::set_var("STUDY_MAX_REJECTS", "2");
        std::env::set_var("STUDY_REJECT_BACKOFF_SECS", "0.01");
        std::env::set_var("STUDY_SLOT_WAIT", "0");   // 关掉 20 分钟撞片退避
        let (base_url, _log) = spawn_mock_platform_with(true).await;

        let task = TaskInput {
            order_id: "TEST-REJECT".into(),
            username: String::new(),
            password: String::new(),
            base_url,
            cookies: vec![],
            videos: mock_videos("A", 1, 2),
            concurrency: 0,
            push_ws: false,
            speed_mode: "gentle".into(),
            already_done: 0,
        };

        let res = run_study(&task, "", "").await;
        std::env::remove_var("PLATFORM_REQUEST_SPACING_SECS");
        std::env::remove_var("STUDY_MAX_REJECTS");
        std::env::remove_var("STUDY_REJECT_BACKOFF_SECS");
        std::env::remove_var("STUDY_SLOT_WAIT");

        // 关键断言：全被拒 → 必须报失败（Err），绝不能在平台上没记账时说成功
        assert!(res.is_err(), "平台全程拒收上报，却报告了完成 —— 假成功回归");
        let msg = res.unwrap_err().to_string();
        assert!(msg.contains("未完成") || msg.contains("拒收"),
                "失败原因应指向「没刷成」，实际: {msg}");
    }

    /// 端到端：课程长度极不均（1 节 vs 7 节）时，
    /// ① 每个视频自己的 begin→final 跨度仍满足均衡档 2.1× 安全比率
    /// ② 任意时刻的重叠会话数不超过档位并发（平台重叠检测口径）
    /// ③ 整单时长显著短于"每课程串行"（旧调度：7 节 × 2.1×2s ≈ 29s）
    #[tokio::test(flavor = "multi_thread", worker_threads = 4)]
    async fn test_video_pool_keeps_span_and_caps_overlap() {
        std::env::set_var("PLATFORM_REQUEST_SPACING_SECS", "0");
        let (base_url, log) = spawn_mock_platform().await;

        let mut videos = mock_videos("A", 1, 2);   // 短课程
        videos.extend(mock_videos("B", 7, 2));     // 长课程

        let task = TaskInput {
            order_id: "TEST-ORD".into(),
            username: String::new(),   // 空用户名 → 跳过启动 cookie 检查
            password: String::new(),
            base_url,
            cookies: vec![],
            videos,
            concurrency: 0,
            push_ws: false,            // 不打推送端点
            speed_mode: "balanced".into(),   // 4 路会话 + 0.5s 启动错峰
            already_done: 0,
        };

        let started = Instant::now();
        run_study(&task, "", "").await.expect("mock 平台下应全部完成");
        let makespan = started.elapsed().as_secs_f64();

        let events = log.lock().unwrap().clone();
        std::env::remove_var("PLATFORM_REQUEST_SPACING_SECS");

        // 每个视频的首末上报即平台看到的 begin/final
        let mut spans: Vec<(f64, f64)> = Vec::new();
        for i in 0..8 {
            let node = if i == 0 { "A-n0".to_string() } else { format!("B-n{}", i - 1) };
            let ts: Vec<f64> = events.iter().filter(|(n, _)| *n == node).map(|(_, t)| *t).collect();
            assert!(ts.len() >= 2, "{node} 至少应有 起/末 两次上报，实际 {:?}", ts);
            let begin = ts[0];
            let end = *ts.last().unwrap();
            // 跨度从"首次上报"算起（首个上报发生在第 1 秒），所以下界要减掉这 1s
            let need = 2.0 * SpeedMode::Balanced.profile().wall_ratio - 1.5;
            assert!(end - begin >= need,
                    "{node} 跨度 {:.2}s 低于安全比率下界 {:.2}s", end - begin, need);
            spans.push((begin, end));
        }

        // 重叠数扫描：任意时刻"未闭合会话"的最大值
        let mut max_overlap = 0usize;
        for (begin, _) in &spans {
            let n = spans.iter().filter(|(b, e)| b <= begin && begin <= e).count();
            max_overlap = max_overlap.max(n);
        }
        assert!(max_overlap <= 4, "重叠会话数 {max_overlap} 超过均衡档并发 4");
        assert!(max_overlap >= 2, "应当真的并行推进（实际 {max_overlap}）");

        // 旧调度（课程内串行）下这一单至少要 7 × 4.2s ≈ 29s
        assert!(makespan < 22.0, "整单耗时 {makespan:.1}s，视频级调度没有生效");
        assert!(makespan > 5.0, "整单耗时 {makespan:.1}s，疑似调度没真正等待墙钟");
        eprintln!(
            "[E2E] 8 节视频（课程 1 节 vs 7 节）：整单 {makespan:.1}s / 最大重叠 {max_overlap} 路；\
             旧调度（课程内串行）下界 ≈29s"
        );
    }
}

//! 刷课核心循环 — 反检测参数与 study_worker.py LightStudyReporter 1:1 对齐

use std::collections::HashMap;
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

/// 墙钟/时长安全比率：studyTime 报满后仍须等 2.1×时长（防 beginTime/finalTime 重叠检测）。
/// 三档均不改动该比率 —— 提速来自并发与错峰，而不是压缩单个视频的安全等待。
const MIN_RATIO: f64 = 2.1;

/// studyTime 报满后的续报间隔（秒）。见 [`next_tick_secs`]。
const TAIL_TICK_SECS: f64 = 30.0;

/// 一次循环该睡多久（秒）。
///
/// 视频的时间轴分两段：
/// - `0 → actual_target`：studyTime 需要逐秒逼近目标，维持 1s 粒度；
/// - `actual_target → 2.1×时长`：studyTime 已报满，这段只是把墙钟撑满。
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
    #[serde(default)]
    pub duration: u64,
    #[serde(default)]
    pub viewed_duration: u64,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub course_id: String,
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
}

#[derive(Debug, Deserialize, Serialize)]
pub struct CookieKV {
    pub name: String,
    pub value: String,
}

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
}

#[derive(Debug, Serialize)]
struct ReportForm<'a> {
    nodeId: &'a str,
    studyId: i64,
    studyTime: i64,
}

#[derive(Debug, Deserialize)]
struct ReportResp {
    #[serde(default)]
    status: i64,
    #[serde(default)]
    state: i64,
    #[serde(default)]
    studyId: i64,
    #[serde(default)]
    need_code: i64,
    #[serde(default)]
    verifyToken: String,
    #[serde(default)]
    offline: bool,
    #[serde(default)]
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
    let resp = shared
        .client
        .post(&url)
        .header("Cookie", cookie)
        .header("X-Requested-With", "XMLHttpRequest")
        .header("Accept-Language", "zh-CN,zh;q=0.9")
        .form(&params)
        .send()
        .await
        .with_context(|| format!("上报请求失败 node={node_id}"))?;
    let status_code = resp.status().as_u16();
    if status_code == 302 {
        let loc = resp.headers().get("location").and_then(|v| v.to_str().ok()).unwrap_or("");
        return Err(anyhow::anyhow!("会话失效重定向: {loc}"));
    }
    let body: ReportResp = resp.json().await.with_context(|| "上报响应解析失败")?;
    Ok(body)
}

/// need_code 验证码处理：need_code=1 图形码走本地 OCR 引擎；
/// need_code=2 点选码不支持（原由 Python 后端 sidecar 处理，已随 Python 移除）
async fn handle_captcha(shared: &Shared, node_id: &str, need_code: i64, verify_token: &str) -> Result<(String, String)> {
    let _ = (node_id, verify_token); // 点选码所需参数，本地 OCR 用不到
    if need_code == 2 {
        return Err(anyhow::anyhow!(
            "点选验证码(need_code=2)不支持，已随 Python 后端移除"
        ));
    }
    // 获取验证码图片
    let r: u8 = rand::rng().random();
    let cap_url = format!("{}/service/code?r={}", shared.base_url, r);
    crate::speed::pace(&shared.profile).await;
    let img = shared.client.get(&cap_url)
        .header("Cookie", shared.cookie_str.lock().await.clone())
        .send().await?.bytes().await?;
    // 本地 OCR 识别（CPU 密集，放阻塞线程池）
    let engine = crate::ocr::engine().context("本地 OCR 引擎不可用")?;
    let bytes = img.to_vec();
    let code = tokio::task::spawn_blocking(move || engine.recognize(&bytes))
        .await.context("OCR 任务执行失败")?
        .context("验证码识别失败")?;
    Ok((code, String::new()))
}

/// 刷单个视频：墙钟推进 + 自适应上报 + 验证码重试 + 2.1 比率
async fn study_video(shared: &Shared, video: &Video) -> Result<bool> {
    let actual_target = video.duration.saturating_sub(video.viewed_duration);
    if actual_target == 0 {
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

    loop {
        // 报满 studyTime 后一次睡到下一续报点，不再每秒空转（见 next_tick_secs）
        let past_target = total_time >= actual_target;
        let wall_left = video.duration as f64 * MIN_RATIO - start.elapsed().as_secs_f64();
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
        if total_time >= actual_target || total_time - last_report >= interval {
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
                            return Err(anyhow::anyhow!("账号被强制下线"));
                        }
                        if resp.need_code == 1 || resp.need_code == 2 {
                            retries += 1;
                            if retries > 7 {
                                return Err(anyhow::anyhow!("验证码重试次数过多"));
                            }
                            match handle_captcha(shared, &video.node_id, resp.need_code, &resp.verifyToken).await {
                                Ok((code, verify)) => {
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
                                        .header("X-Requested-With", "XMLHttpRequest")
                                        .form(&params).send().await?;
                                    let body: ReportResp = r2.json().await?;
                                    if body.need_code == 0 {
                                        if body.state == 1 { study_id = 0; }
                                        else if body.studyId > 0 { study_id = body.studyId; }
                                        break;
                                    }
                                }
                                Err(e) => return Err(e),
                            }
                            // 验证码退避
                            tokio::time::sleep(Duration::from_secs_f64(0.3 * retries as f64)).await;
                            continue;
                        }
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

        // 完成条件：studyTime 报满 + 墙钟 ≥ 2.1×时长
        if total_time >= actual_target && start.elapsed().as_secs_f64() >= video.duration as f64 * MIN_RATIO {
            return Ok(true);
        }
    }
}

/// 掉线重登：本地登录（验证码由内置 OCR 识别），更新共享 cookie
async fn relogin(shared: &Shared) -> Result<bool> {
    if shared.username.is_empty() {
        return Ok(false);
    }
    match crate::login::login_school(&shared.base_url, &shared.username, &shared.password).await {
        Ok(session) => {
            let mut guard = shared.cookie_str.lock().await;
            *guard = session.cookie_str;
            Ok(true)
        }
        Err(e) => {
            eprintln!("[rust_worker] 重新登录失败: {e:#}");
            Ok(false)
        }
    }
}

/// 心跳：随机 90-150s 一次 POST /user/online
async fn heartbeat_loop(shared: Arc<Shared>) {
    loop {
        let secs = rand::rng().random_range(90..=150);
        tokio::time::sleep(Duration::from_secs(secs)).await;
        crate::speed::pace(&shared.profile).await;
        let _ = shared.client
            .post(format!("{}/user/online", shared.base_url))
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
        let resp = shared.client
            .get(format!("{}/user/index", shared.base_url))
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
    });

    // 启动时 cookie 有效性检查
    if !task.username.is_empty() {
        let r = shared.client.get(format!("{}/user/index", shared.base_url)).send().await;
        if let Ok(resp) = r {
            if matches!(resp.status().as_u16(), 302 | 401 | 403) {
                eprintln!("[rust_worker] 启动时 cookie 已过期，尝试重新登录");
                let _ = relogin(&shared).await;
            }
        }
    }

    push_ws(&shared, serde_json::json!({"type": "progress", "phase": "video"}), push_url, push_token).await;

    // 心跳 + cookie 续期后台任务
    let hb = tokio::spawn(heartbeat_loop(shared.clone()));
    let cr = tokio::spawn(cookie_refresh_loop(shared.clone()));

    // 按课程分组：课程内串行，课程间并发
    let mut groups: HashMap<String, Vec<Video>> = HashMap::new();
    for v in &task.videos {
        groups.entry(if v.course_id.is_empty() { "unknown".into() } else { v.course_id.clone() })
            .or_default().push(v.clone());
    }
    eprintln!("[rust_worker] 视频分组: {} 个课程, 共 {} 个视频", groups.len(), task.videos.len());

    let done_counter = Arc::new(std::sync::atomic::AtomicU64::new(0));
    let failed_counter = Arc::new(std::sync::atomic::AtomicU64::new(0));

    // 课程并发闸：档位决定同时在刷的课程数（急速 8 / 均衡 4 / 温柔 1），
    // 课程内部仍是逐节串行 —— 与平台「并发重叠数」检测口径一致。
    let course_sem = Arc::new(tokio::sync::Semaphore::new(profile.course_concurrency.max(1)));
    eprintln!("[rust_worker] 刷课档位 {}：课程并发 {} / 错峰 {}ms",
              profile.mode.label(), profile.course_concurrency, profile.course_stagger_ms);

    let mut set = JoinSet::new();
    for (cid, videos) in groups {
        let shared = shared.clone();
        let done_counter = done_counter.clone();
        let failed_counter = failed_counter.clone();
        let course_sem = course_sem.clone();
        set.spawn(async move {
            // 超出并发的课程在此排队等待（不额外打请求）
            let _permit = match course_sem.acquire_owned().await {
                Ok(p) => p,
                Err(_) => return,
            };
            eprintln!("[rust_worker] [course-{cid}] 开始处理 {} 个视频", videos.len());
            for v in &videos {
                match study_video(&shared, v).await {
                    Ok(true) => {
                        done_counter.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                    }
                    Ok(false) | Err(_) => {
                        failed_counter.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                    }
                }
            }
            eprintln!("[rust_worker] [course-{cid}] 课程处理完毕");
        });
        // 课程间启动错峰：急速档零等待，温柔档拉长到几十秒（含随机抖动）
        profile.sleep_course_stagger().await;
    }
    while set.join_next().await.is_some() {}

    hb.abort();
    cr.abort();

    let done = done_counter.load(std::sync::atomic::Ordering::Relaxed);
    let failed = failed_counter.load(std::sync::atomic::Ordering::Relaxed);
    let total = task.videos.len() as u64;
    let pct = if total > 0 { done * 100 / total } else { 100 };

    // 平台进度复核：拉 study_record/video 算一次账号维度的完成率。
    //
    // 它是**参考信号，不是失败判据**。原因：该接口不带 courseId，返回的是账号下
    // 全部课程的汇总，而本单通常只包含其中一部分（学员自己先刷掉几门很常见）。
    // 拿账号全量完成率当门槛，会把「只下单 3 门、其他 7 门没动」的订单判成失败 ——
    // 任务实际做完了却告诉用户失败，还会触发无谓的重试登录（平台风控）。
    // 单视频是否真的刷完，由 study_video 自己的判定（studyTime 报满 + 墙钟 ≥ 2.1×时长）
    // 保证，本地的 failed/dead 计数才是硬判据。
    let actual_pct = verify_platform_progress(&shared).await;
    match actual_pct {
        Some(p) if p < 95 => tracing::warn!(
            done, total, platform_pct = p,
            "账号整体完成率低于 95%（可能包含本单未选中的课程），不计为失败"
        ),
        None => tracing::warn!(done, total, "平台进度复核失败（响应异常），跳过该项检查"),
        _ => {}
    }
    if failed > 0 {
        anyhow::bail!("部分视频未完成 {done}/{total}");
    }
    eprintln!("[rust_worker] 任务完成 {done}/{total}");
    Ok(())
}

async fn verify_platform_progress(shared: &Shared) -> Option<u64> {
    crate::speed::pace(&shared.profile).await;
    // Cookie 头不能漏：run_study 用的 client 是 jar=None 的（不自动带 cookie），
    // 本模块其它请求都是手动带上。漏了它就等于发了个未登录请求 —— 平台回登录页，
    // JSON 解析失败 → 返回 None → 调用方 unwrap_or(0) 得到 0%，
    // 于是**每个任务收尾都被判定「部分视频未完成」而失败**（哪怕课真的刷完了）。
    let cookie = shared.cookie_str.lock().await.clone();
    let resp = shared.client
        .get(format!("{}/user/study_record/video.json", shared.base_url))
        .header("Cookie", cookie)
        .header("X-Requested-With", "XMLHttpRequest")
        .send().await.ok()?;
    let data: serde_json::Value = resp.json().await.ok()?;
    let list = data["list"].as_array()?;
    let mut total: u64 = 0;
    let mut viewed: u64 = 0;
    for item in list {
        // 时长格式为 "HH:MM:SS"/"MM:SS"/秒数（与 Python _parse_duration_str 一致）
        total += crate::scan::parse_duration_secs(item["duration"].as_str().unwrap_or("0"));
        viewed += crate::scan::parse_duration_secs(item["viewedDuration"].as_str().unwrap_or("0"));
    }
    if total == 0 { return Some(0); }
    Some(viewed * 100 / total)
}

#[cfg(test)]
mod tests {
    use super::*;

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
}

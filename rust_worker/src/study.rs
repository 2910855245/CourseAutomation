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
    pub status_file: String,
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
    status_file: String,
    push_ws: bool,
    /// 随推送一起上报：服务端据此把消息投到 order:{id} topic
    order_id: String,
    /// 本任务的节奏档位参数（并发/错峰/请求间隔）
    profile: SpeedProfile,
    progress: Mutex<Progress>,
}

#[derive(Default)]
struct Progress {
    done: u64,
    total: u64,
    total_study: u64,
    total_duration: u64,
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
        tokio::time::sleep(Duration::from_secs(1)).await;
        total_time += 1;

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

        // 更新进度
        {
            let mut p = shared.progress.lock().await;
            p.total_study += 1;
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

/// status.json 原子写（tmp + rename；Windows 上无 fsync 保证但 rename 原子）
async fn write_status(shared: &Shared, extra: &[(&str, &str)]) {
    let p = shared.progress.lock().await;
    let mut map = serde_json::Map::new();
    map.insert("video_done".into(), p.done.into());
    map.insert("video_total".into(), p.total.into());
    map.insert("video_pct".into(), if p.total > 0 { (p.done * 100 / p.total) as u64 } else { 0 }.into());
    map.insert("total_study_time".into(), p.total_study.into());
    map.insert("total_duration".into(), p.total_duration.into());
    map.insert("updated_at".into(), serde_json::Value::from(
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs_f64()).unwrap_or(0.0)));
    for (k, v) in extra {
        map.insert(k.to_string(), serde_json::Value::from(v.clone()));
    }
    let body = serde_json::Value::Object(map).to_string();
    let tmp = format!("{}.tmp", shared.status_file);
    if tokio::fs::write(&tmp, body).await.is_ok() {
        let _ = tokio::fs::rename(&tmp, &shared.status_file).await;
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

    let total_duration: u64 = task.videos.iter().map(|v| v.duration).sum();
    let shared = Arc::new(Shared {
        client,
        base_url,
        cookie_str: Mutex::new(cookie_str),
        username: task.username.clone(),
        password: task.password.clone(),
        status_file: task.status_file.clone(),
        push_ws: task.push_ws,
        order_id: task.order_id.clone(),
        profile,
        progress: Mutex::new(Progress { total: task.videos.len() as u64, total_duration, ..Default::default() }),
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

    write_status(&shared, &[
        ("phase", "video"),
        ("message", &format!("开始刷视频 (共{}个)", task.videos.len())),
    ]).await;
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
                        let mut p = shared.progress.lock().await;
                        p.done = done_counter.load(std::sync::atomic::Ordering::Relaxed);
                        drop(p);
                        write_status(&shared, &[
                            ("phase", "video"),
                            ("message", ""),
                        ]).await;
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

    // 平台进度验证：拉 study_record/video 重算真实进度
    let actual_pct = verify_platform_progress(&shared).await.unwrap_or(0);

    if failed > 0 || actual_pct < 95 {
        write_status(&shared, &[
            ("phase", "done"),
            ("done", "true"),
            ("success", "false"),
            ("video_pct", &actual_pct.to_string()),
            ("message", &format!("部分视频未完成 {done}/{total} 平台进度{actual_pct}%")),
        ]).await;
        anyhow::bail!("部分视频未完成 {done}/{total} 平台进度{actual_pct}%");
    }
    write_status(&shared, &[
        ("phase", "done"),
        ("done", "true"),
        ("success", "true"),
        ("video_pct", "100"),
        ("message", "任务完成"),
    ]).await;
    eprintln!("[rust_worker] 任务完成 {done}/{total}");
    Ok(())
}

async fn verify_platform_progress(shared: &Shared) -> Option<u64> {
    crate::speed::pace(&shared.profile).await;
    let resp = shared.client
        .get(format!("{}/user/study_record/video.json", shared.base_url))
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

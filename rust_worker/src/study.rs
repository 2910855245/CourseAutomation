//! 刷课核心循环 — 反检测参数与 study_worker.py LightStudyReporter 1:1 对齐

use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use rand::Rng;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;
use tokio::task::JoinSet;

/// 全局请求间隔：跨所有任务共享，任意两个 HTTP 请求间隔 ≥ 0.5s
static SPACING: Mutex<Option<Instant>> = Mutex::const_new(None);
const REQUEST_SPACING_SECS: f64 = 0.5;

/// 墙钟/时长安全比率：studyTime 报满后仍须等 2.1×时长（防 beginTime/finalTime 重叠检测）
const MIN_RATIO: f64 = 2.1;

const UA: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36";

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
    #[serde(default)]
    pub ocr_url: String,
    #[serde(default)]
    pub relogin_url: String,
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
    ocr_url: String,
    relogin_url: String,
    progress: Mutex<Progress>,
}

#[derive(Default)]
struct Progress {
    done: u64,
    total: u64,
    total_study: u64,
    total_duration: u64,
}

/// 全局请求间隔门（模拟原 _wait_rate_limit：所有线程共享 _next_request_time）
async fn wait_spacing() {
    let mut guard = SPACING.lock().await;
    let now = Instant::now();
    if let Some(next) = *guard {
        if now < next {
            tokio::time::sleep(next - now).await;
        }
    }
    *guard = Some(Instant::now() + Duration::from_secs_f64(REQUEST_SPACING_SECS));
}

fn make_client() -> Client {
    Client::builder()
        .danger_accept_invalid_certs(true)
        .user_agent(UA)
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .expect("构建 HTTP client 失败")
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
    wait_spacing().await;
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

/// need_code 验证码处理：图形码走 OCR sidecar，点选码走 sidecar 的 dunclick 流程
async fn handle_captcha(shared: &Shared, node_id: &str, need_code: i64, verify_token: &str) -> Result<(String, String)> {
    if shared.ocr_url.is_empty() {
        return Err(anyhow::anyhow!("触发验证码 need_code={need_code} 且无 OCR sidecar"));
    }
    // 获取验证码图片
    let r: u8 = rand::thread_rng().gen();
    let cap_url = format!("{}/service/code?r={}", shared.base_url, r);
    wait_spacing().await;
    let img = shared.client.get(&cap_url).send().await?.bytes().await?;
    use base64::Engine;
    let b64 = base64::engine::general_purpose::STANDARD.encode(&img);
    let payload = serde_json::json!({
        "image_base64": b64,
        "need_code": need_code,
        "verify_token": verify_token,
        "base_url": shared.base_url,
        "node_id": node_id,
    });
    let resp: serde_json::Value = shared.client.post(&shared.ocr_url).json(&payload).send().await?.json().await?;
    if resp["data"]["solved"].as_bool().unwrap_or(false) || resp["success"].as_bool().unwrap_or(false) {
        let code = resp["data"]["code"].as_str().unwrap_or("").to_string();
        Ok((code, String::new()))
    } else {
        Err(anyhow::anyhow!("OCR sidecar 处理失败: {}", resp["message"].as_str().unwrap_or("未知错误")))
    }
}

/// 刷单个视频：墙钟推进 + 自适应上报 + 验证码重试 + 2.1 比率
async fn study_video(shared: &Shared, video: &Video) -> Result<bool> {
    let actual_target = video.duration.saturating_sub(video.viewed_duration);
    if actual_target == 0 {
        return Ok(true);
    }
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
                                    wait_spacing().await;
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

/// 掉线重登：调用 Python sidecar（复用 login_single_platform + 验证码 OCR），更新共享 cookie
async fn relogin(shared: &Shared) -> Result<bool> {
    if shared.relogin_url.is_empty() {
        return Ok(false);
    }
    let payload = serde_json::json!({
        "base_url": shared.base_url,
        "username": shared.username,
        "password": shared.password,
    });
    let resp: serde_json::Value = shared.client.post(&shared.relogin_url).json(&payload).send().await?.json().await?;
    if resp["ok"].as_bool().unwrap_or(false) {
        if let Some(cookies) = resp["cookies"].as_array() {
            let mut new_str = String::new();
            for c in cookies {
                let name = c["name"].as_str().unwrap_or("");
                let value = c["value"].as_str().unwrap_or("");
                if !name.is_empty() {
                    if !new_str.is_empty() { new_str.push(';'); }
                    new_str.push_str(&format!("{name}={value}"));
                }
            }
            let mut guard = shared.cookie_str.lock().await;
            *guard = new_str;
        }
        return Ok(true);
    }
    Ok(false)
}

/// 心跳：随机 90-150s 一次 POST /user/online
async fn heartbeat_loop(shared: Arc<Shared>) {
    loop {
        let secs = rand::thread_rng().gen_range(90..=150);
        tokio::time::sleep(Duration::from_secs(secs)).await;
        wait_spacing().await;
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
        wait_spacing().await;
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

async fn push_ws(shared: &Shared, data: serde_json::Value, push_url: &str, push_token: &str) {
    if !shared.push_ws {
        return;
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
        ocr_url: task.ocr_url.clone(),
        relogin_url: task.relogin_url.clone(),
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

    let mut set = JoinSet::new();
    for (cid, videos) in groups {
        let shared = shared.clone();
        let done_counter = done_counter.clone();
        let failed_counter = failed_counter.clone();
        set.spawn(async move {
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
        // 课程间启动间隔 0.5s
        tokio::time::sleep(Duration::from_millis(500)).await;
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
    wait_spacing().await;
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

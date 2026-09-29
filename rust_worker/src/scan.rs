//! 学校平台课程扫描 — 协议对齐 worker.py crawl 阶段
//!
//! 覆盖 Python 侧 get_courses_with_diag（课程列表 HTML 解析）与
//! get_course_nodes_from_api 的视频分页拉取。扫描完成后直接链式进入
//! study::run_study（视频列表无缝衔接），Python 只需登录后提交一次任务。
//!
//! 注意：考试/作业的清洗与验证留在 Python（考试阶段会重新扫描，
//! 且含大量平台特判逻辑）；本模块只产出刷课所需的视频列表。

use anyhow::{Context, Result};
use rand::RngExt;
use reqwest::Client;
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::HashSet;
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use crate::study::{run_study, TaskInput, Video};

// ── 扫描并发控制（全模块共享） ────────────────────────────────────────────

/// 单平台在飞 HTTP 请求上限：对服务器压力抹平，并发但不猛打
pub const SCAN_CONCURRENCY: usize = 8;

static SCAN_SEM: tokio::sync::OnceCell<Arc<tokio::sync::Semaphore>> =
    tokio::sync::OnceCell::const_new();

/// 全局扫描信号量（所有分页/记录请求都需先 acquire）
pub async fn scan_sem() -> &'static Arc<tokio::sync::Semaphore> {
    SCAN_SEM.get_or_init(|| async { Arc::new(tokio::sync::Semaphore::new(SCAN_CONCURRENCY)) }).await
}

#[derive(Debug, Deserialize)]
pub struct ScanTaskInput {
    pub order_id: String,
    #[serde(default)]
    pub username: String,
    #[serde(default)]
    pub password: String,
    pub base_url: String,
    pub cookie_str: String,
    #[serde(default)]
    pub course_ids: Vec<String>, // "courseId" 或 "courseId:classId"
    pub status_file: String,
    #[serde(default)]
    pub push_ws: bool,
    /// 刷课节奏档位（turbo/balanced/gentle；缺省/未知 → 均衡）
    #[serde(default)]
    pub speed_mode: String,
}

/// 课程条目（从 /user/index HTML 解析）
pub struct CourseItem {
    pub name: String,
    pub course_id: String,
    pub study_record_url: String,
    /// .name a 的 href（detail_link，对齐 get_courses）
    #[allow(dead_code)]
    pub detail_link: String,
}

fn now_ms() -> u128 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0)
}

/// 学校平台 base_url 映射（对齐 config/platforms.py WEBSITES）
/// 测试钩子：RUST_TEST_BASE_URL 环境变量覆盖（mock 平台 E2E 用）
pub fn platform_base_url(website_id: i64) -> String {
    if let Ok(url) = std::env::var("RUST_TEST_BASE_URL") {
        if !url.is_empty() {
            return url;
        }
    }
    // 注意：这里是**静默兜底**——未列出的 website_id 会被当成学校平台 1 去登录。
    // 学习通（id=4）绝不能落到这条兜底上：那会拿用户的手机号+密码去登录
    // 在线课程测评考试平台，若该手机号在那边也存在，就会刷错人的课。
    // （id 4/5 的来源见 DB system_config.domain_monitor_website_map。）
    match website_id {
        2 => "https://cdcas.duxingkej.com".to_string(),
        3 => "https://cdcas.chaoxiankeji.com".to_string(),
        // 学习通站点本身；登录另需 TLS 指纹伪装（见 school_exam::scan_chaoxing 注释）
        4 => "https://mooc1.chaoxing.com".to_string(),
        // 同一学校体系的镜像域名（DB 的 domain_monitor 自动发现）
        5 => "https://cdcas.suwankj.com".to_string(),
        _ => "https://cdcass.taiskeji.com".to_string(),
    }
}

/// 解析 "HH:MM:SS" / "MM:SS" / 秒数 为秒
pub fn parse_duration_secs(s: &str) -> u64 {
    let s = s.trim();
    if s.is_empty() {
        return 0;
    }
    if let Ok(n) = s.parse::<u64>() {
        return n;
    }
    if let Ok(n) = s.parse::<f64>() {
        return n.round() as u64;
    }
    let parts: Vec<&str> = s.split(':').collect();
    if parts.len() == 2 {
        if let (Ok(m), Ok(sec)) = (parts[0].parse::<u64>(), parts[1].parse::<u64>()) {
            return m * 60 + sec;
        }
    }
    if parts.len() == 3 {
        if let (Ok(h), Ok(m), Ok(sec)) = (
            parts[0].parse::<u64>(),
            parts[1].parse::<u64>(),
            parts[2].parse::<u64>(),
        ) {
            return h * 3600 + m * 60 + sec;
        }
    }
    0
}

/// 从 URL 中提取 courseId=（与 Python 一致）
fn extract_course_id(url: &str) -> String {
    let mut out = String::new();
    for part in url.split(['&', '?']) {
        if let Some(v) = part.strip_prefix("courseId=") {
            out = v.to_string();
        }
    }
    out
}

/// 解析课程列表（对齐 get_courses_with_diag 的 xpath 提取）
pub async fn fetch_course_list(client: &Client, cookie: &str, base_url: &str) -> Result<Vec<CourseItem>> {
    let html = fetch_course_list_html(client, cookie, base_url).await?;
    Ok(parse_course_list(&html))
}

/// 抓取课程列表页原始 HTML（降负载：调用方可复用同一响应做二次解析，
/// 避免对 /user/index 发第二次 17KB 请求）
pub async fn fetch_course_list_html(client: &Client, cookie: &str, base_url: &str) -> Result<String> {
    let url = format!("{}/user/index", base_url.trim_end_matches('/'));
    // 整页导航请求，不能带 X-Requested-With（否则平台走 AJAX 分支渲染 500「数据出现异常」）
    let resp = client.get(&url)
        .header("Cookie", cookie)
        .send().await
        .context("获取课程列表失败")?;
    let html = resp.text().await.context("课程列表读取失败")?;

    // 登录失效诊断（对齐 Python 的 302/登录页特征）
    if html.contains("SQLSTATE") || html.contains("数据出现异常") {
        anyhow::bail!("平台数据库异常");
    }
    Ok(html)
}

/// 解析课程列表 HTML（对齐 get_courses_with_diag 的 xpath 提取）：
/// //div[contains(@class,"user-course")]//div[@class="item"]，
/// 名称取 .name a 文本，course_id 从 .status a 的 courseId= 参数提取
pub fn parse_course_list(html: &str) -> Vec<CourseItem> {
    use scraper::{Html, Selector};

    let doc = Html::parse_document(html);
    let item_sel = Selector::parse(".user-course .item").unwrap();
    let name_sel = Selector::parse(".name a").unwrap();
    let status_sel = Selector::parse(".status a").unwrap();

    let mut courses = Vec::new();
    let mut seen = HashSet::new();
    for item in doc.select(&item_sel) {
        let name = item.select(&name_sel).next()
            .map(|a| a.text().collect::<String>().trim().to_string())
            .unwrap_or_default();
        if name.is_empty() {
            continue;
        }
        let detail_link = item.select(&name_sel).next()
            .and_then(|a| a.value().attr("href"))
            .unwrap_or("")
            .to_string();
        let study_record_url = item.select(&status_sel).next()
            .and_then(|a| a.value().attr("href"))
            .unwrap_or("")
            .to_string();
        let course_id = extract_course_id(&study_record_url);
        if course_id.is_empty() || !seen.insert(course_id.clone()) {
            continue;
        }
        courses.push(CourseItem { name, course_id, study_record_url, detail_link });
    }
    courses
}

/// 拉取单门课程的视频（分页 study_record/video.json，对齐 get_course_nodes_from_api）
/// 优化：第 1 页拿到 pageCount 后剩余页并发预取（推测分页），不再逐页串行
pub async fn fetch_course_videos(client: &Client, cookie: &str, base_url: &str,
                             course_id: &str, course_name: &str) -> Result<Vec<Video>> {
    let base = format!("{}/user/study_record/video", base_url.trim_end_matches('/'));

    let parse_items = |items: &[Value]| -> Vec<Video> {
        let mut out = Vec::new();
        for item in items {
            let node_id = item["id"].as_str().unwrap_or("").to_string();
            if node_id.is_empty() {
                continue;
            }
            out.push(Video {
                node_id,
                duration: parse_duration_secs(item["duration"].as_str().unwrap_or("0")),
                viewed_duration: parse_duration_secs(
                    item["viewedDuration"].as_str().or(item["viewed_duration"].as_str()).unwrap_or("0")),
                name: item["name"].as_str().unwrap_or(course_name).to_string(),
                course_id: course_id.to_string(),
            });
        }
        out
    };

    // 单页拉取（带并发信号量 + 抖动，对齐 exam/work 的取页策略）
    // 独立 async fn 而非闭包：可被多次调用做并发预取
    async fn fetch_video_page(client: &Client, cookie: &str, base: &str,
                              course_id: &str, page: u32) -> Option<Value> {
        let jitter = rand::random::<u64>() % 100;
        tokio::time::sleep(std::time::Duration::from_millis(jitter)).await;
        let _permit = scan_sem().await.acquire().await.ok()?;
        let url = format!("{}?courseId={}&page={}", base, course_id, page);
        let resp = client.get(&url)
            .header("Cookie", cookie)
            .header("X-Requested-With", "XMLHttpRequest")
            .send().await.ok()?;
        if resp.status().as_u16() != 200 {
            return None;
        }
        resp.json::<Value>().await.ok()
    }

    // 第 1 页：探测 pageCount + 拿首批数据
    let first = match fetch_video_page(client, cookie, &base, course_id, 1).await {
        Some(d) if d["status"].as_bool() == Some(true) => d,
        _ => return Ok(Vec::new()),
    };
    let mut videos = parse_items(first["list"].as_array().map(|a| a.as_slice()).unwrap_or(&[]));
    let page_count = first["pageInfo"]["pageCount"].as_u64().unwrap_or(1) as u32;
    if page_count <= 1 {
        return Ok(videos);
    }
    // 推测预取：剩余页并发全发
    let mut futs = Vec::new();
    for page in 2..=page_count {
        futs.push(fetch_video_page(client, cookie, &base, course_id, page));
    }
    for d in futures_util::future::join_all(futs).await.into_iter().flatten() {
        if d["status"].as_bool() == Some(true) {
            if let Some(list) = d["list"].as_array() {
                videos.extend(parse_items(list));
            }
        }
    }
    Ok(videos)
}

async fn write_scan_status(status_file: &str, phase: &str, message: &str,
                           done_flag: Option<bool>, success: Option<bool>,
                           extra: &[(&str, Value)]) {
    let mut map = serde_json::Map::new();
    map.insert("phase".into(), phase.into());
    map.insert("message".into(), message.into());
    map.insert("updated_at".into(), json!(now_ms() as f64 / 1000.0));
    for (k, v) in extra {
        map.insert(k.to_string(), v.clone());
    }
    if let Some(d) = done_flag {
        map.insert("done".into(), d.into());
    }
    if let Some(s) = success {
        map.insert("success".into(), s.into());
    }
    let body = Value::Object(map).to_string();
    let tmp = format!("{}.tmp", status_file);
    if tokio::fs::write(&tmp, body).await.is_ok() {
        let _ = tokio::fs::rename(&tmp, status_file).await;
    }
}

/// 完整任务：扫描全部课程视频 → 链式进入刷课
pub async fn run_scan_and_study(task: &ScanTaskInput, push_url: &str,
                                push_token: &str) -> Result<()> {
    let base_url = task.base_url.trim_end_matches('/').to_string();
    let client = crate::platform_client::build_client_with_ua(
        crate::platform_client::SHORT_UA, false, None);

    // course_ids 过滤集（兼容 "courseId" 与 "courseId:classId" 两种格式）
    let filter: HashSet<String> = task.course_ids.iter()
        .map(|c| c.split(':').next().unwrap_or("").to_string())
        .filter(|c| !c.is_empty())
        .collect();

    write_scan_status(&task.status_file, "crawl", "正在获取课程...", None, None,
                      &[]).await;
    let courses = fetch_course_list(&client, &task.cookie_str, &base_url).await?;
    let selected: Vec<&CourseItem> = courses.iter()
        .filter(|c| filter.is_empty() || filter.contains(&c.course_id))
        .collect();
    if selected.is_empty() {
        write_scan_status(&task.status_file, "error", "未找到课程", Some(true), Some(false),
                          &[]).await;
        anyhow::bail!("未找到课程");
    }
    write_scan_status(&task.status_file, "crawl",
                      &format!("获取到 {} 门课程", selected.len()), None, None,
                      &[]).await;

    // 并发扫描各课程视频（每课程一个 tokio task）。
    // 并发度与错峰由档位决定：急速档全量并行，温柔档一次只扫 1~2 门并长间隔错开。
    let profile = crate::speed::SpeedMode::parse(&task.speed_mode).profile();
    let shared_client = Arc::new(client);
    let cookie = Arc::new(task.cookie_str.clone());
    let scan_sem = Arc::new(tokio::sync::Semaphore::new(profile.scan_concurrency.max(1)));
    let mut handles = Vec::new();
    for course in selected {
        // 先取扫描许可再派发：超出并发的课程会在此等待，天然形成分批扫描
        let permit = match scan_sem.clone().acquire_owned().await {
            Ok(p) => p,
            Err(_) => break,
        };
        let c = shared_client.clone();
        let ck = cookie.clone();
        let b = base_url.clone();
        let cid = course.course_id.clone();
        let cname = course.name.clone();
        let jitter = profile.scan_jitter();
        handles.push(tokio::spawn(async move {
            let _permit = permit;
            // 启动抖动：把同批课程的首请求错开，避免瞬间并发突发打到平台
            if !jitter.is_zero() {
                tokio::time::sleep(jitter).await;
            }
            let videos = fetch_course_videos(&c, &ck, &b, &cid, &cname).await;
            (cname, cid, videos)
        }));
        // 课程之间错峰：温柔档拉长到几十秒，急速档为零
        profile.sleep_course_stagger().await;
    }
    let mut all_videos: Vec<Video> = Vec::new();
    let mut scan_failed = 0u64;
    for h in handles {
        match h.await {
            Ok((cname, cid, Ok(vids))) => {
                if vids.is_empty() {
                    eprintln!("[scan] 课程无视频: {cname} (id={cid})");
                }
                all_videos.extend(vids);
            }
            Ok((cname, cid, Err(e))) => {
                scan_failed += 1;
                eprintln!("[scan] 课程扫描失败: {cname} (id={cid}) err={e}");
            }
            Err(e) => {
                scan_failed += 1;
                eprintln!("[scan] 课程扫描任务失败: {e}");
            }
        }
    }
    write_scan_status(&task.status_file, "crawl",
                      &format!("扫描完成 视频={} 失败课程={}", all_videos.len(), scan_failed),
                      None, None, &[]).await;

    if all_videos.is_empty() {
        write_scan_status(&task.status_file, "error", "未找到任何视频",
                          Some(true), Some(false), &[]).await;
        anyhow::bail!("未找到任何视频");
    }

    // 链式进入刷课（复用 study::run_study；cookies/状态文件原样传递）
    let study_task = TaskInput {
        order_id: task.order_id.clone(),
        username: task.username.clone(),
        password: task.password.clone(),
        base_url: base_url.clone(),
        cookies: task.cookie_str.split(';').filter_map(|pair| {
            let (k, v) = pair.split_once('=')?;
            Some(crate::study::CookieKV {
                name: k.trim().to_string(),
                value: v.trim().to_string(),
            })
        }).collect(),
        videos: all_videos,
        status_file: task.status_file.clone(),
        concurrency: 0,
        push_ws: task.push_ws,
        speed_mode: task.speed_mode.clone(),
    };
    run_study(&study_task, push_url, push_token).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_duration() {
        assert_eq!(parse_duration_secs("00:00:02"), 2);
        assert_eq!(parse_duration_secs("01:05:30"), 3930);
        assert_eq!(parse_duration_secs("03:45"), 225);
        assert_eq!(parse_duration_secs("120"), 120);
        assert_eq!(parse_duration_secs(""), 0);
        assert_eq!(parse_duration_secs("abc"), 0);
    }

    #[test]
    fn test_course_list_parse() {
        let html = r#"<html><body>
<div class="user-course">
  <div class="item">
    <div class="name"><a href="/user/node?courseId=101">高等数学</a></div>
    <div class="note"><div class="status"><a href="/user/study_record?courseId=101">学习记录</a></div></div>
  </div>
  <div class="item">
    <div class="name"><a href="/user/node?courseId=102">大学英语</a></div>
    <div class="note"><div class="status"><a href="/user/study_record?courseId=102">学习记录</a></div></div>
  </div>
</div>
<div class="other"><div class="item"><div class="name"><a href="/x?courseId=999">干扰项</a></div></div></div>
</body></html>"#;
        let courses = parse_course_list(html);
        assert_eq!(courses.len(), 2, "应解析出 2 门课程且过滤 user-course 外的干扰项: {:?}",
                   courses.iter().map(|c| (&c.name, &c.course_id)).collect::<Vec<_>>());
        assert_eq!(courses[0].name, "高等数学");
        assert_eq!(courses[0].course_id, "101");
        assert_eq!(courses[1].name, "大学英语");
        assert_eq!(courses[1].course_id, "102");
    }
}
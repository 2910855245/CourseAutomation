//! 学校平台课程扫描 + 考试答题 API（Rust 版）
//! — 协议对齐 api/routers/scan.py + services/scan_service.py
//!   + infrastructure/school/course_crawler.py / data_cleaner.py / task_filter.py
//!   + api/routers/config_admin.py test-deepseek
//!
//! 与 Python 的已知取舍（刻意不迁移）：
//! - 扫描结果不落盘缓存（Python 存 data/accounts/，Rust 内存会话每次重新登录）
//! - 域名发现走静态表 scan::platform_base_url（Python 走 domain_monitor 动态域名）
//! - _verify_exam_exists（考试存在性二次验证）未迁移：需多一次页面请求，主流程可后续补
//!
//! 鉴权说明：scan/relogin 对齐 Python get_optional_user（可选登录），本 router 不加 auth；
//! test-deepseek 对齐 get_current_admin，需由主 agent 注册时加 auth layer（见模块总结）。

use anyhow::Result;
use axum::extract::State;
use axum::routing::{get, post};
use axum::{Json, Router};
use futures_util::stream::{self, StreamExt};
use regex::Regex;
use reqwest::Client;
use serde_json::{json, Value};
use std::time::{SystemTime, UNIX_EPOCH};
use tracing::{info, warn};

use crate::exam;
use crate::llm::{cached_config, configured_model, configured_thinking, effective_api_key};
use crate::scan;
use crate::AppState;

/// 学校平台静态表（对齐 platforms.py WEBSITES，学习通 4 由 cx 侧处理）
const PLATFORMS: &[(i64, &str)] = &[
    (1, "在线课程测评考试平台"),
    (2, "劳动课程测评考试平台"),
    (3, "公益课程平台"),
];

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/courses/platforms", get(list_platforms))
        .route("/api/courses/scan", post(scan_courses))
        .route("/api/courses/scan/chaoxing", post(scan_chaoxing))
        .route("/api/courses/relogin", post(relogin_platform))
        .route("/api/exam/solve", post(solve_exam_api))
        .route("/api/admin/config/test-deepseek", post(test_deepseek))
}

// ── /api/courses/platforms ──────────────────────────────────────────────

async fn list_platforms() -> Json<Value> {
    let items: Vec<Value> = PLATFORMS.iter()
        .map(|(id, name)| json!({
            "id": id, "name": name, "base_url": scan::platform_base_url(*id),
        }))
        .collect();
    Json(json!({"success": true, "message": "ok", "data": items}))
}

// ── /api/courses/scan/chaoxing ───────────────────────────────────────────
//
// 学习通站点启用 TLS 指纹校验（JA3），reqwest/native-tls 会被直接拒绝，
// 需 wreq（TLS 指纹伪装）才能登录。当前依赖尚未落地，故本端点返回明确的
// 业务失败（而非 404/SPA HTML），前端据此提示用户，不影响学校平台链路。

#[derive(serde::Deserialize)]
struct ScanChaoxingRequest {
    #[serde(default)]
    username: String,
    #[serde(default)]
    password: String,
}

async fn scan_chaoxing(Json(req): Json<ScanChaoxingRequest>) -> Json<Value> {
    let _ = (req.username, req.password);
    Json(json!({
        "success": false,
        "message": "学习通扫描暂不可用：该站点需 TLS 指纹伪装客户端（wreq）支持",
        "data": {"platform": {
            "website_id": 4,
            "name": "超星学习通",
            "status": "unsupported",
            "error": "后端尚未接入 wreq，学习通链路暂不可用",
            "courses": [],
            "tasks": [],
        }},
    }))
}

// ── 登录：统一走 session 模块（缓存/落盘复用 + 失效才登录）────────────
//
// 历史实现（login_with_local_ocr / do_login_with_code）每次扫描都重新登录，
// 频繁触发平台风控；且密码错误判定不全（缺「账号密码不正确 / 已被锁定」），
// 会一路重试到锁号。现已收敛到 login::login_school + session::get_session。


// ── 考试/作业分页拉取 + 清洗（对齐 course_crawler + data_cleaner + task_filter）──

/// 分页拉取（对齐 _fetch_all_pages：status 真 + list 非空 + page < pageInfo.pageCount）
/// 全局扫描并发上限（单平台在飞请求数），防止瞬时打满对方服务器
/// 单平台在飞请求上限（对服务器友好的并发度）——信号量定义在 scan 模块，全局共享
const SCAN_CONCURRENCY: usize = scan::SCAN_CONCURRENCY;

/// 拉取单页 JSON（带并发信号量 + 随机抖动，对服务器压力抹平）。
/// 返回 None 表示该页失败/无效，调用方据此终止分页。
async fn fetch_page_json(client: &Client, cookie: &str, url: &str,
                         course_id: &str, page: u64) -> Option<Value> {
    // 0~100ms 随机抖动：并发请求在时间上错开，削峰
    let jitter = rand::random::<u64>() % 100;
    tokio::time::sleep(std::time::Duration::from_millis(jitter)).await;
    // 占用一个并发槽位（全局共享，含 video 分页）
    let _permit = scan::scan_sem().await.acquire().await.ok()?;
    let resp = client.get(format!("{url}?courseId={course_id}&page={page}"))
        .header("Cookie", cookie)
        .header("X-Requested-With", "XMLHttpRequest")
        .send().await.ok()?;
    if resp.status().as_u16() != 200 {
        return None;
    }
    resp.json::<Value>().await.ok()
}

/// 分页拉取（推测分页预取算法）：
/// 第 1 页先拿到 pageCount，随后第 2..=pageCount 页一次性并发发出，
/// 而非逐页串行等待。pageCount=1（绝大多数 exam/work）时只发 1 个请求。
async fn fetch_all_pages(client: &Client, cookie: &str, url: &str,
                         course_id: &str) -> Vec<Value> {
    // 第 1 页：探测 pageCount + 拿到首批数据
    let first = match fetch_page_json(client, cookie, url, course_id, 1).await {
        Some(d) if d["status"].as_bool() == Some(true) => d,
        _ => return Vec::new(),
    };
    let mut items: Vec<Value> = first["list"].as_array().cloned().unwrap_or_default();
    let page_count = first["pageInfo"]["pageCount"].as_u64().unwrap_or(1);
    if page_count <= 1 {
        return items;
    }
    // 推测预取：剩余页并发全发（pageCount 已由第 1 页给出，无需串行探测）
    let mut futs = Vec::new();
    for page in 2..=page_count {
        futs.push(fetch_page_json(client, cookie, url, course_id, page));
    }
    let rest = futures_util::future::join_all(futs).await;
    for d in rest.into_iter().flatten() {
        if d["status"].as_bool() == Some(true) {
            if let Some(list) = d["list"].as_array() {
                items.extend(list.iter().cloned());
            }
        }
    }
    items
}

/// 时间状态（对齐 _parse_time_status：startTime/endTime 为秒级时间戳）
fn parse_time_status(raw: &Value, now: i64) -> &'static str {
    let start = raw["startTime"].as_str().unwrap_or("").parse::<i64>().unwrap_or(0);
    let end = raw["endTime"].as_str().unwrap_or("").parse::<i64>().unwrap_or(0);
    if start > 0 && now < start {
        return "未开始";
    }
    if end > 0 && now > end {
        return "已结束";
    }
    "进行中"
}

const EXAM_DONE_KEYWORDS: &[&str] = &["已交", "已阅", "已批阅", "已完成", "已通过", "已批改"];

/// 清洗考试/作业（对齐 classify_exam；输出即扫描响应里的 exam 条目）
fn classify_exam(raw: &Value, course_name: &str, course_id: &str, now: i64) -> Value {
    let clean = |v: &Value| -> String {
        let s = v.as_str().unwrap_or("");
        Regex::new(r"<[^>]+>").unwrap().replace_all(s, "").trim().to_string()
    };
    let submit_status = {
        let s = clean(&raw["state"]);
        if s.is_empty() { "未交".to_string() } else { s }
    };
    let time_status = parse_time_status(raw, now);
    let not_started = time_status == "未开始";
    let actionable_states = ["未交", "继续做题", "在做"];
    let is_actionable = !not_started
        && actionable_states.contains(&submit_status.as_str())
        && time_status == "进行中";

    let final_score = clean(&raw["finalScore"]);
    let final_score = if final_score.is_empty() { "-".to_string() } else { final_score };
    let has_valid_score = {
        let s = final_score.trim();
        !s.is_empty()
            && !["-", "--", "null", "None"].contains(&s)
            && s.parse::<f64>().map(|f| f > 0.0).unwrap_or(false)
    };
    let is_expired = submit_status == "未交" && time_status == "已结束";
    let is_done = not_started
        || EXAM_DONE_KEYWORDS.contains(&submit_status.as_str())
        || has_valid_score
        || is_expired;

    json!({
        "course_name": course_name,
        "course_id": course_id,
        "name": raw["title"].as_str().or(raw["name"].as_str()).unwrap_or(""),
        "work_id": raw["id"].as_str().unwrap_or(""),
        "node_id": raw["nodeId"].as_str().unwrap_or(""),
        "chapter_id": raw["chapterId"].as_str().unwrap_or(""),
        "exam_url": raw["url"].as_str().unwrap_or(""),
        "submit_status": submit_status,
        "time_status": time_status,
        "is_actionable": is_actionable,
        "is_done": is_done,
        "is_deleted": false,
        "is_pending": not_started,
        "final_score": final_score,
        "start_time": raw["startTime"].as_str().unwrap_or(""),
        "end_time": raw["endTime"].as_str().unwrap_or(""),
        "submit_time": raw["submitTime"].as_str().or(raw["finishTime"].as_str()).unwrap_or(""),
        "frequency": raw["frequency"].as_str().unwrap_or(""),
        "topic_number": raw["topicNumber"].as_str().unwrap_or(""),
    })
}

/// 拉取某门课程"还需处理"的考试清单（供刷课主流程在视频刷完后接着做题）。
///
/// 返回 [{work_id, node_id, name, course_id}]，只含 is_actionable（未交/继续做题/在做）
/// 且未做过的考试 —— 已交卷、已过期、未开始的都不动。
pub(crate) async fn list_actionable_exams(client: &Client, cookie: &str,
                                          base_url: &str, course_id: &str) -> Vec<Value> {
    let base = base_url.trim_end_matches('/');
    let now = SystemTime::now().duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64).unwrap_or(0);
    let raw = fetch_all_pages(client, cookie,
        &format!("{base}/user/study_record/exam"), course_id).await;
    raw.iter()
        .map(|e| classify_exam(e, "", course_id, now))
        .filter(|e| e["is_actionable"].as_bool() == Some(true))
        .map(|e| json!({
            "work_id": e["work_id"],
            "node_id": e["node_id"],
            "name": e["name"],
            "course_id": e["course_id"],
        }))
        .collect()
}

/// 扫描单门课程（对齐 scan_course：拉取+清洗+分类；跳过 _verify_exam_exists）
async fn scan_course(client: &Client, cookie: &str, base_url: &str,
                     course_id: &str, course_name: &str) -> Result<Value> {
    let base = base_url.trim_end_matches('/');
    let now = SystemTime::now().duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64).unwrap_or(0);

    let videos_raw = scan::fetch_course_videos(client, cookie, base, course_id, course_name)
        .await.unwrap_or_default();
    let exams_raw = fetch_all_pages(client, cookie,
        &format!("{base}/user/study_record/exam"), course_id).await;
    let works_raw = fetch_all_pages(client, cookie,
        &format!("{base}/user/study_record/work"), course_id).await;

    let videos: Vec<Value> = videos_raw.iter().map(|v| {
        // 已学判定必须与刷课侧共用同一个函数：以前两处各写一套，
        // duration 解析异常时会出现"扫描说待刷、刷课说已完成"
        // （收钱不干活还报 100%）。时长未知一律不算已学。
        let status = if crate::study::video_is_done(v) {
            "已学"
        } else if v.viewed_duration > 0 {
            "未学完"
        } else {
            "未学"
        };
        json!({
            "course_name": course_name,
            "course_id": course_id,
            "name": v.name,
            "node_id": v.node_id,
            "duration": v.duration,
            "viewed_duration": v.viewed_duration,
            "status": status,
        })
    }).collect();
    let exams: Vec<Value> = exams_raw.iter()
        .map(|e| classify_exam(e, course_name, course_id, now)).collect();
    let works: Vec<Value> = works_raw.iter()
        .map(|w| classify_exam(w, course_name, course_id, now)).collect();

    // 分类（对齐 task_filter.get_all_actionable）
    let mut tasks = Vec::new();
    for v in &videos {
        if v["status"].as_str() != Some("已学") {
            let mut t = v.clone();
            t["task_type"] = json!("video");
            tasks.push(t);
        }
    }
    let mut actionable_exams = Vec::new();
    let mut missed = Vec::new();
    let mut pending = Vec::new();
    for e in exams.iter().chain(works.iter()) {
        if e["is_actionable"].as_bool() == Some(true) && e["is_pending"].as_bool() != Some(true) {
            actionable_exams.push(e.clone());
            let mut t = e.clone();
            t["task_type"] = json!("exam");
            tasks.push(t);
        }
        if e["submit_status"].as_str() == Some("未交") && e["time_status"].as_str() == Some("已结束") {
            missed.push(e.clone());
        }
        if e["is_pending"].as_bool() == Some(true) {
            pending.push(e.clone());
        }
    }
    let actionable_videos: Vec<Value> = videos.iter()
        .filter(|v| v["status"].as_str() != Some("已学")).cloned().collect();

    Ok(json!({
        "videos": videos,
        "exams": exams,
        "works": works,
        "tasks": tasks,
        "actionable_videos": actionable_videos,
        "actionable_exams": actionable_exams,
        "missed": missed,
        "pending": pending,
    }))
}

// ── /api/courses/scan ────────────────────────────────────────────────────

#[derive(serde::Deserialize)]
struct ScanRequest {
    username: String,
    password: String,
    #[serde(default = "default_true")]
    include_records: bool,
    #[serde(default)]
    force_refresh: bool,
}

fn default_true() -> bool { true }

async fn scan_courses(Json(req): Json<ScanRequest>) -> Json<Value> {
    if req.username.is_empty() || req.password.is_empty() {
        return Json(json!({"success": false, "message": "username/password 不能为空",
                           "data": {"platforms": []}}));
    }
    let _ = req.force_refresh; // 扫描结果不落盘缓存（见模块头注）
    let mut handles = Vec::new();
    for (wid, name) in PLATFORMS {
        let (u, p, n) = (req.username.clone(), req.password.clone(), name.to_string());
        let (wid, include) = (*wid, req.include_records);
        handles.push(tokio::spawn(async move {
            scan_one_platform(&u, &p, wid, &n, include, false).await
        }));
    }
    let mut results = Vec::new();
    for h in handles {
        match h.await {
            Ok(r) => {
                info!(website_id = r["website_id"].as_i64().unwrap_or(0),
                      status = r["status"].as_str().unwrap_or("?"),
                      error = r["error"].as_str().unwrap_or(""),
                      "scan_one_platform 返回");
                results.push(r);
            }
            Err(e) => warn!("scan_one_platform task panic/err: {e}"),
        }
    }
    results.sort_by_key(|r| r["website_id"].as_i64().unwrap_or(0));

    let total_courses: usize = results.iter()
        .map(|r| r["courses"].as_array().map(|a| a.len()).unwrap_or(0)).sum();
    let ok_platforms = results.iter()
        .filter(|r| r["status"].as_str() == Some("ok")).count();
    Json(json!({
        "success": true,
        "message": format!("扫描完成: {ok_platforms}/{} 个平台登录成功, 共 {total_courses} 门课程", results.len()),
        "data": {"platforms": results},
    }))
}

/// 扫描单个平台（对齐 scan_platform：取会话 → 课程列表 → 逐课程扫描）
/// `force_login = true` 时跳过会话复用（/api/courses/relogin 语义：用户主动重新登录）
async fn scan_one_platform(username: &str, password: &str, website_id: i64,
                           platform_name: &str, include_records: bool,
                           force_login: bool) -> Value {
    let base_url = scan::platform_base_url(website_id);
    let fail = |status: &str, error: String| json!({
        "website_id": website_id,
        "name": platform_name,
        "status": status,
        "error": error,
        "courses": [],
        "tasks": [],
    });

    // 会话复用（缓存/落盘 cookie 有效则跳过登录，避免频繁登录被风控）
    if force_login {
        crate::session::invalidate(username, &base_url);
    }
    let session = match crate::session::get_session(&base_url, username, password).await {
        Ok(s) => {
            info!(website_id, cookie = %s.cookie_str, "会话就绪");
            s
        }
        Err(e) => {
            let detail = format!("{e:#}");
            let error_msg = if detail.contains("锁定") {
                "账号已被锁定，请稍后再试"
            } else if detail.contains("验证码") {
                "验证码识别失败，请重试"
            } else if detail.contains("密码") || detail.to_lowercase().contains("password") {
                "密码错误"
            } else if detail.contains("不存在") || detail.to_lowercase().contains("not found") {
                "账号不存在"
            } else if detail.contains("超时") || detail.to_lowercase().contains("timeout") {
                "连接超时，请重试"
            } else {
                "登录失败，请检查账号密码"
            };
            return fail("login_failed", error_msg.to_string());
        }
    };

    let client = crate::platform_client::build_client(false, None);

    // 课程列表页只抓一次：解析课程 + 提取学生姓名（降负载：省一次 17KB 整页请求）
    let index_html = match scan::fetch_course_list_html(&client, &session.cookie_str, &base_url).await {
        Ok(h) => h,
        Err(e) => return fail("error", format!("获取课程列表失败: {e:#}")),
    };
    let courses_raw = scan::parse_course_list(&index_html);
    let student_name = parse_student_name(&index_html);
    info!(website_id, html_len = index_html.len(), courses = courses_raw.len(),
          student = %student_name, html_head = %index_html.chars().take(100).collect::<String>(),
          "课程列表页抓取结果");

    // 课程级并发：N 门课之间并发扫描（buffer_unordered 限流 + 全局信号量兜底），
    // 而非逐门串行等待。总请求数不变（不多发一个），只压缩墙钟时间。
    // 每门课内部 video/exam/work 也已并发，且分页做推测预取。
    let mut results: Vec<(usize, Value, Vec<Value>)> = stream::iter(
        courses_raw.into_iter().enumerate().map(|(idx, c)| {
            let client = client.clone();
            let cookie = session.cookie_str.clone();
            let base = base_url.clone();
            let platform_name = platform_name.to_string();
            async move {
                let mut entry = json!({
                    "course_id": c.course_id,
                    "course_name": c.name,
                    "detail_link": c.detail_link,
                    "study_record_url": c.study_record_url,
                    "video_total": 0, "video_completed": 0, "video_pending": 0, "video_actionable": 0,
                    "exam_total": 0, "exam_done": 0, "exam_deleted": 0,
                    "exam_missed": 0, "exam_pending": 0, "exam_actionable": 0,
                    "records_loaded": false,
                });
                let mut course_tasks = Vec::new();
                if include_records && !c.course_id.is_empty() {
                    match scan_course(&client, &cookie, &base, &c.course_id, &c.name).await {
                        Ok(r) => {
                            let videos = r["videos"].as_array().cloned().unwrap_or_default();
                            let exams = r["exams"].as_array().cloned().unwrap_or_default();
                            let works = r["works"].as_array().cloned().unwrap_or_default();
                            let tasks = r["tasks"].as_array().cloned().unwrap_or_default();
                            let actionable_videos = r["actionable_videos"].as_array()
                                .map(|a| a.len()).unwrap_or(0);
                            let missed = r["missed"].as_array().map(|a| a.len()).unwrap_or(0);
                            let pending = r["pending"].as_array().map(|a| a.len()).unwrap_or(0);

                            let video_total = videos.len();
                            let exam_total = exams.len() + works.len();
                            let exam_done = exams.iter().chain(works.iter())
                                .filter(|e| e["is_done"].as_bool() == Some(true)).count();
                            let exam_deleted = exams.iter().chain(works.iter())
                                .filter(|e| e["is_deleted"].as_bool() == Some(true)).count();
                            let exam_actionable = tasks.iter()
                                .filter(|t| t["task_type"].as_str() == Some("exam")).count();

                            entry["video_total"] = json!(video_total);
                            entry["video_completed"] = json!(video_total - actionable_videos);
                            entry["video_pending"] = json!(actionable_videos);
                            entry["video_actionable"] = json!(actionable_videos);
                            entry["exam_total"] = json!(exam_total - exam_deleted);
                            entry["exam_done"] = json!(exam_done);
                            entry["exam_deleted"] = json!(exam_deleted);
                            entry["exam_missed"] = json!(missed);
                            entry["exam_pending"] = json!(pending);
                            entry["exam_actionable"] = json!(exam_actionable);
                            entry["records_loaded"] = json!(true);

                            for mut t in tasks {
                                t["website_id"] = json!(website_id);
                                t["platform_name"] = json!(platform_name);
                                t["course_name"] = json!(c.name);
                                t["course_id"] = json!(c.course_id);
                                course_tasks.push(t);
                            }
                        }
                        Err(e) => tracing::warn!(course = %c.name, error = %e, "扫描课程失败"),
                    }
                }
                (idx, entry, course_tasks)
            }
        })
    )
    .buffer_unordered(SCAN_CONCURRENCY)
    .collect()
    .await;

    // 保持与课程列表一致的稳定顺序（并发完成顺序是乱的）
    results.sort_by_key(|(idx, _, _)| *idx);
    let mut courses = Vec::new();
    let mut all_tasks = Vec::new();
    for (_, entry, tasks) in results {
        courses.push(entry);
        all_tasks.extend(tasks);
    }

    json!({
        "website_id": website_id,
        "name": platform_name,
        "status": "ok",
        "student_name": student_name,
        "courses": courses,
        "tasks": all_tasks,
    })
}

/// 从个人中心页 HTML 提取学生姓名（对齐 extract_student_name 的简化版）
/// 入参为已抓取的 /user/index HTML，不再单独发请求（降负载）
fn parse_student_name(html: &str) -> String {
    // 欢迎语特征（对齐 Python re：欢迎[你您]，xxx）
    let re = Regex::new(r"欢迎[你您][，,]?\s*([^\s<]{2,6})").unwrap();
    if let Some(m) = re.captures(html).and_then(|c| c.get(1)) {
        return m.as_str().trim().to_string();
    }
    let re2 = Regex::new(r#"<div[^>]*class="name"[^>]*>\s*([^\s<]{2,10})\s*</div>"#).unwrap();
    if let Some(m) = re2.captures(html).and_then(|c| c.get(1)) {
        return m.as_str().trim().to_string();
    }
    String::new()
}

// ── /api/courses/relogin ─────────────────────────────────────────────────

#[derive(serde::Deserialize)]
struct ReloginRequest {
    username: String,
    password: String,
    website_id: i64,
    #[serde(default = "default_true")]
    include_records: bool,
}

async fn relogin_platform(Json(req): Json<ReloginRequest>) -> Json<Value> {
    let name = PLATFORMS.iter().find(|(id, _)| *id == req.website_id)
        .map(|(_, n)| *n).unwrap_or("未知平台");
    let result = scan_one_platform(&req.username, &req.password,
                                   req.website_id, name, req.include_records, true).await;
    let ok = result["status"].as_str() == Some("ok");
    Json(json!({
        "success": true,
        "message": if ok { "平台登录成功" } else { "平台登录失败" },
        "data": {"platform": result},
    }))
}

// ── /api/exam/solve ──────────────────────────────────────────────────────

#[derive(serde::Deserialize)]
struct SolveRequest {
    base_url: String,
    cookie_str: String,
    work_id: String,
    #[serde(default)]
    course_id: String,
    #[serde(default)]
    node_id: String,
    api_key: String,
    #[serde(default)]
    model: String,
    #[serde(default)]
    item_type: String,
}

async fn solve_exam_api(State(state): State<AppState>, Json(req): Json<SolveRequest>) -> Json<Value> {
    if req.base_url.is_empty() || req.cookie_str.is_empty() || req.work_id.is_empty() {
        return Json(json!({"success": false, "message": "base_url/cookie_str/work_id 不能为空"}));
    }
    // API Key / 模型未显式传入时回退管理端配置（此前"考试模型"配置项后端从不读取）
    let api_key = if req.api_key.is_empty() {
        effective_api_key(&state.db).await
    } else {
        req.api_key.clone()
    };
    if api_key.is_empty() {
        return Json(json!({"success": false, "message": "DEEPSEEK_API_KEY 未配置"}));
    }
    let model = if req.model.is_empty() {
        configured_model(&state.db, "deepseek_model", crate::llm::MODEL_FLASH).await
    } else {
        req.model.clone()
    };
    let thinking = configured_thinking(&state.db).await;
    let item_type = if req.item_type.is_empty() { "work" } else { &req.item_type };
    match exam::solve_exam(&req.base_url, &req.cookie_str, &req.work_id,
                           &req.course_id, &req.node_id, &api_key,
                           &model, item_type, thinking).await {
        Ok(r) => Json(r),
        Err(e) => Json(json!({"success": false, "error": format!("{e:#}")})),
    }
}

// ── /api/admin/config/test-deepseek（对齐 config_admin.py）────────────────

#[derive(serde::Deserialize)]
struct TestModelInput {
    #[serde(default)]
    model: Option<String>,
}

async fn test_deepseek(State(state): State<AppState>,
                       body: Option<Json<TestModelInput>>) -> Json<Value> {
    // 默认用当前在售的 flash（deepseek-chat 已于 2026-07-24 弃用，
    // 拿它做默认值会让"测试"永远返回 401）
    let test_model = body.and_then(|b| b.0.model)
        .unwrap_or_else(|| crate::llm::MODEL_FLASH.to_string());
    let mut result = json!({
        "openai_module": true, // Rust 直连 HTTP，恒 true（对齐 Python 的 openai 模块检查位）
        "api_key": "", "key_source": "", "api_ok": false,
        "error": "", "model": "", "latency_ms": 0,
    });

    // API key：先数据库 system_config，后环境变量（对齐 Python）
    let db_key = cached_config(&state.db, "deepseek_api_key", "").await;
    let (api_key, key_source) = if !db_key.is_empty() {
        (db_key, "数据库配置")
    } else {
        (std::env::var("DEEPSEEK_API_KEY").unwrap_or_default(), "环境变量")
    };
    if api_key.is_empty() {
        result["error"] = json!("DeepSeek API Key 未配置");
        return Json(json!({"code": -1, "data": result}));
    }
    result["key_source"] = json!(key_source);
    // 按字符切（api_key 来自 DB/env，含多字节字符时字节切片会 panic）
    let key_chars: Vec<char> = api_key.chars().collect();
    result["api_key"] = json!(if key_chars.len() > 10 {
        format!("{}****{}",
                key_chars[..6].iter().collect::<String>(),
                key_chars[key_chars.len() - 4..].iter().collect::<String>())
    } else {
        "****".to_string()
    });

    // 走统一 LlmClient，让"测试通过"与"答题能跑通"是同一条件
    // （此前测试用裸 reqwest，两边参数不一致时可能测试通过而线上失败）
    let thinking = configured_thinking(&state.db).await;
    let client = crate::llm::LlmClient::new(&api_key, "");
    let t0 = std::time::Instant::now();
    let req = crate::llm::ChatRequest::new("selftest", &test_model, "回复OK")
        .max_tokens(16);
    let req = match thinking {
        Some(t) => req.thinking(t),
        None => req,
    };
    let resp = client.chat(req).await;
    let latency = t0.elapsed().as_millis() as u64;
    result["latency_ms"] = json!(latency);
    match resp {
        Ok(reply) => {
            result["api_ok"] = json!(true);
            let (actual, _) = crate::llm::resolve_model(&test_model);
            result["model"] = json!(actual);
            result["reply"] = json!(reply.content.chars().take(40).collect::<String>());
            if let Some(u) = &reply.usage {
                result["usage"] = json!(u);
            }
        }
        Err(e) => {
            result["error"] = json!(classify_deepseek_error(&format!("{e:#}")));
        }
    }
    Json(json!({"code": 0, "data": result}))
}

/// 错误分类（对齐 config_admin.py 的文案）
fn classify_deepseek_error(err: &str) -> String {
    if err.contains("401") || err.contains("Unauthorized") {
        "API Key 无效或已过期".to_string()
    } else if err.contains("429") || err.to_lowercase().contains("rate") {
        "请求频率过高，请稍后再试".to_string()
    } else if err.to_lowercase().contains("timeout") || err.to_lowercase().contains("connect") {
        "网络连接超时，无法访问 DeepSeek API".to_string()
    } else {
        let truncated: String = err.chars().take(200).collect();
        format!("API 调用失败: {truncated}")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_classify_exam() {
        let now = 1_700_000_000i64; // 2023-11-14
        // 未交 + 进行中 → actionable
        let e = classify_exam(&json!({
            "id": "11", "nodeId": "22", "chapterId": "33",
            "title": "期中考试", "state": "<b>未交</b>",
            "startTime": "1699900000", "endTime": "1700100000",
        }), "高数", "101", now);
        assert_eq!(e["submit_status"], "未交");
        assert_eq!(e["time_status"], "进行中");
        assert_eq!(e["is_actionable"], true);
        assert_eq!(e["is_done"], false);
        assert_eq!(e["name"], "期中考试");
        assert_eq!(e["work_id"], "11");
        assert_eq!(e["node_id"], "22");

        // 未交 + 已结束 → missed + done（不可操作）
        let e = classify_exam(&json!({
            "id": "12", "state": "未交",
            "startTime": "1699000000", "endTime": "1699100000",
        }), "高数", "101", now);
        assert_eq!(e["time_status"], "已结束");
        assert_eq!(e["is_actionable"], false);
        assert_eq!(e["is_done"], true);

        // 未开始 → pending + done，不计入可操作
        let e = classify_exam(&json!({
            "id": "13", "state": "未交",
            "startTime": "1701000000", "endTime": "1702000000",
        }), "高数", "101", now);
        assert_eq!(e["time_status"], "未开始");
        assert_eq!(e["is_pending"], true);
        assert_eq!(e["is_done"], true);
        assert_eq!(e["is_actionable"], false);

        // 已交 → done
        let e = classify_exam(&json!({"id": "14", "state": "已交"}), "高数", "101", now);
        assert_eq!(e["is_done"], true);
        assert_eq!(e["is_actionable"], false);

        // 继续做题 + 进行中 → actionable
        let e = classify_exam(&json!({
            "id": "15", "state": "继续做题",
            "startTime": "1699900000", "endTime": "1700100000",
        }), "高数", "101", now);
        assert_eq!(e["is_actionable"], true);

        // 有效分数 > 0 → done（即使 state 是未交且进行中）
        let e = classify_exam(&json!({
            "id": "16", "state": "未交", "finalScore": "88",
            "startTime": "1699900000", "endTime": "1700100000",
        }), "高数", "101", now);
        assert_eq!(e["is_done"], true);
    }

    #[test]
    fn test_parse_time_status() {
        let now = 1_700_000_000i64;
        assert_eq!(parse_time_status(&json!({"startTime": "1701000000"}), now), "未开始");
        assert_eq!(parse_time_status(&json!({"endTime": "1699000000"}), now), "已结束");
        assert_eq!(parse_time_status(&json!({"startTime": "1699000000", "endTime": "1701000000"}), now), "进行中");
        // 无时间戳 → 进行中
        assert_eq!(parse_time_status(&json!({}), now), "进行中");
    }

    #[test]
    fn test_classify_deepseek_error() {
        assert_eq!(classify_deepseek_error("HTTP 401: Unauthorized"), "API Key 无效或已过期");
        assert_eq!(classify_deepseek_error("HTTP 429: rate limit"), "请求频率过高，请稍后再试");
        assert_eq!(classify_deepseek_error("connection timeout"), "网络连接超时，无法访问 DeepSeek API");
        assert!(classify_deepseek_error("HTTP 500: boom").starts_with("API 调用失败: "));
    }
}

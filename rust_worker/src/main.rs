//! rust-backend — 刷课系统后端（纯 Rust 化，单二进制）
//!
//! 单进程承载：
//! - 刷课 daemon（/submit /submit_cx /submit_full /cancel，tokio task 调度）
//! - HTTP API（/api/*，逐步对齐 Python 版本）
//! - 静态资源 + SPA（gzip/brotli 压缩 + immutable 缓存）
//! - SQLite 访问层（rusqlite 直连，与 Python 迁移期共享 data/*.db）

mod api;
mod auth;
mod cx_scan;
mod cx_study;
mod db;
mod exam;
mod login;
mod order;
mod pay;
mod progress;
mod queue;
mod scan;
mod study;

use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::Context;
use axum::body::Body;
use axum::extract::{Path, Request, State};
use axum::http::{header, HeaderValue, StatusCode};
use axum::middleware::{self, Next};
use axum::response::Response;
use axum::routing::{get, post};
use axum::{Json, Router};
use dashmap::DashMap;
use serde_json::json;
use tower_http::compression::CompressionLayer;
use tower_http::services::ServeDir;
use tracing_subscriber::EnvFilter;

type TaskMap = Arc<DashMap<String, tokio::task::JoinHandle<()>>>;

#[derive(Clone)]
pub struct AppState {
    pub tasks: TaskMap,
    pub push_url: String,
    pub push_token: String,
    pub db: db::Db,
    pub progress_tx: tokio::sync::broadcast::Sender<String>,
}

type SubmitTask = study::TaskInput;

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.to_string())
}

pub(crate) fn rss_mb() -> u64 {
    #[cfg(target_os = "linux")]
    {
        let s = std::fs::read_to_string("/proc/self/status").unwrap_or_default();
        s.lines().find(|l| l.starts_with("VmRSS:"))
            .and_then(|l| l.split_whitespace().nth(1))
            .and_then(|v| v.parse::<u64>().ok())
            .map(|kb| kb / 1024)
            .unwrap_or(0)
    }
    #[cfg(not(target_os = "linux"))]
    { 0 }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let _ = dotenvy::dotenv();
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()))
        .init();

    let port: u16 = env_or("RUST_DAEMON_PORT", "17017").parse().unwrap_or(17017);
    let push_url = env_or("RUST_DAEMON_PUSH_URL", "http://127.0.0.1:17017/api/progress/live/push");
    let push_token = env_or("RUST_DAEMON_PUSH_TOKEN", "");
    let db_path = env_or("DB_PATH", "data/orders.db");

    let database = db::Db::open(&db_path)
        .with_context(|| format!("打开数据库失败: {db_path}"))?;
    tracing::info!(db_path, "SQLite 就绪");

    let (progress_tx, _) = tokio::sync::broadcast::channel::<String>(256);
    let state = AppState {
        tasks: Arc::new(DashMap::new()),
        push_url,
        push_token,
        db: database,
        progress_tx,
    };

    // Rust 队列调度器（RUST_QUEUE_ENABLED=true 时接管学校任务）
    tokio::spawn(queue::dispatcher_loop(std::sync::Arc::new(state.clone())));

    let app = Router::new()
        .route("/status", get(status))
        .route("/submit", post(submit))
        .route("/submit_cx", post(submit_cx))
        .route("/submit_cx_full", post(submit_cx_full))
        .route("/submit_full", post(submit_full))
        .route("/submit_exam", post(submit_exam))
        .route("/api/progress/live/push", post(progress::push_progress))
        .route("/api/progress/ws/live", get(progress::ws_live))
        .route("/cancel/{order_id}", post(cancel))
        .merge(api::router(state.clone()))
        .nest_service("/static", ServeDir::new("static").append_index_html_on_directories(true))
        .fallback(spa_fallback)
        .layer(middleware::from_fn(cache_headers))
        .layer(CompressionLayer::new())
        .layer(middleware::from_fn(trace_request))
        .with_state(state);

    let addr = format!("127.0.0.1:{port}");
    tracing::info!(addr, "rust-backend 就绪（API + daemon + 静态服务）");

    let listener = tokio::net::TcpListener::bind(&addr).await
        .with_context(|| format!("绑定 {addr} 失败"))?;
    axum::serve(listener, app).await?;
    Ok(())
}

/// 请求日志
async fn trace_request(req: Request, next: Next) -> Response {
    let method = req.method().clone();
    let path = req.uri().path().to_string();
    let start = std::time::Instant::now();
    let resp = next.run(req).await;
    let status = resp.status().as_u16();
    if path.starts_with("/api/") || path == "/submit" || path == "/submit_cx" || path == "/submit_full" {
        tracing::debug!(method = %method, path = %path, status, elapsed_ms = start.elapsed().as_millis(), "request");
    }
    resp
}

/// 构建产物文件名带内容 hash：永久缓存；HTML 保持 no-cache
async fn cache_headers(req: Request, next: Next) -> Response {
    let is_asset = req.uri().path().starts_with("/static/assets/");
    let mut resp = next.run(req).await;
    if is_asset {
        resp.headers_mut().insert(
            header::CACHE_CONTROL,
            HeaderValue::from_static("public, max-age=31536000, immutable"),
        );
    }
    resp
}

/// SPA 回退：非 API/静态路径返回 index.html（no-cache）
async fn spa_fallback() -> Response {
    match tokio::fs::read("static/index.html").await {
        Ok(body) => {
            let mut resp = Response::new(Body::from(body));
            *resp.status_mut() = StatusCode::OK;
            resp.headers_mut().insert(
                header::CONTENT_TYPE,
                HeaderValue::from_static("text/html; charset=utf-8"),
            );
            resp.headers_mut().insert(
                header::CACHE_CONTROL,
                HeaderValue::from_static("no-store, no-cache, must-revalidate, max-age=0"),
            );
            resp
        }
        Err(_) => {
            let mut resp = Response::new(Body::from("index.html 未找到（请先 npm run build）"));
            *resp.status_mut() = StatusCode::NOT_FOUND;
            resp
        }
    }
}

async fn status(State(state): State<AppState>) -> Json<serde_json::Value> {
    let ids: Vec<String> = state.tasks.iter().map(|e| e.key().clone()).collect();
    Json(json!({"tasks": ids}))
}

async fn cancel(
    State(state): State<AppState>,
    Path(order_id): Path<String>,
) -> Json<serde_json::Value> {
    if let Some((_, handle)) = state.tasks.remove(&order_id) {
        handle.abort();
        Json(json!({"ok": true}))
    } else {
        Json(json!({"ok": false, "message": "任务不存在"}))
    }
}

async fn submit(
    State(state): State<AppState>,
    Json(task): Json<SubmitTask>,
) -> Json<serde_json::Value> {
    if task.order_id.is_empty() || task.videos.is_empty() {
        return Json(json!({"ok": false, "message": "order_id/videos 不能为空"}));
    }
    if state.tasks.contains_key(&task.order_id) {
        return Json(json!({"ok": false, "message": "任务已存在"}));
    }

    let push_url = state.push_url.clone();
    let push_token = state.push_token.clone();
    let tasks = state.tasks.clone();
    let order_id = task.order_id.clone();

    let oid_for_task = task.order_id.clone();
    let oid_resp = task.order_id.clone();
    let handle = tokio::spawn(async move {
        let result = study::run_study(&task, &push_url, &push_token).await;
        if let Err(e) = result {
            tracing::warn!(order_id = %oid_for_task, error = %e, "school study task failed");
        }
        tasks.remove(&oid_for_task);
    });

    state.tasks.insert(oid_resp.clone(), handle);
    Json(json!({"ok": true, "order_id": oid_resp}))
}

async fn submit_full(
    State(state): State<AppState>,
    Json(task): Json<scan::ScanTaskInput>,
) -> Json<serde_json::Value> {
    if task.order_id.is_empty() || task.cookie_str.is_empty() || task.base_url.is_empty() {
        return Json(json!({"ok": false, "message": "order_id/cookie_str/base_url 不能为空"}));
    }
    if state.tasks.contains_key(&task.order_id) {
        return Json(json!({"ok": false, "message": "任务已存在"}));
    }

    let push_url = state.push_url.clone();
    let push_token = state.push_token.clone();
    let tasks = state.tasks.clone();
    let order_id = task.order_id.clone();
    let oid_resp = task.order_id.clone();

    let handle = tokio::spawn(async move {
        let result = scan::run_scan_and_study(&task, &push_url, &push_token).await;
        if let Err(e) = result {
            tracing::warn!(order_id = %order_id, error = %e, "full task failed");
        }
        tasks.remove(&order_id);
    });

    state.tasks.insert(oid_resp.clone(), handle);
    Json(json!({"ok": true, "order_id": oid_resp}))
}

async fn submit_cx_full(
    State(state): State<AppState>,
    Json(task): Json<cx_scan::ScanCxTaskInput>,
) -> Json<serde_json::Value> {
    if task.order_id.is_empty() || task.cookie_str.is_empty() || task.uid.is_empty() {
        return Json(json!({"ok": false, "message": "order_id/cookie_str/uid 不能为空"}));
    }
    if state.tasks.contains_key(&task.order_id) {
        return Json(json!({"ok": false, "message": "任务已存在"}));
    }

    let push_url = state.push_url.clone();
    let push_token = state.push_token.clone();
    let tasks = state.tasks.clone();
    let order_id = task.order_id.clone();
    let oid_resp = task.order_id.clone();

    let handle = tokio::spawn(async move {
        let result = cx_scan::run_cx_scan_and_study(&task, &push_url, &push_token).await;
        if let Err(e) = result {
            tracing::warn!(order_id = %order_id, error = %e, "cx full task failed");
        }
        tasks.remove(&order_id);
    });

    state.tasks.insert(oid_resp.clone(), handle);
    Json(json!({"ok": true, "order_id": oid_resp}))
}

#[derive(serde::Deserialize)]
struct ExamTask {
    order_id: String,
    base_url: String,
    cookie_str: String,
    work_id: String,
    #[serde(default)]
    course_id: String,
    #[serde(default)]
    node_id: String,
    api_key: String,
    #[serde(default = "default_model")]
    model: String,
    #[serde(default)]
    item_type: String,
    status_file: String,
}

fn default_model() -> String {
    "deepseek-v4-flash".to_string()
}

async fn submit_exam(
    State(state): State<AppState>,
    Json(task): Json<ExamTask>,
) -> Json<serde_json::Value> {
    if task.order_id.is_empty() || task.api_key.is_empty() || task.work_id.is_empty() {
        return Json(json!({"ok": false, "message": "order_id/api_key/work_id 不能为空"}));
    }
    let resp_id = task.order_id.clone();
    let resp_id2 = task.order_id.clone();
    tokio::spawn(async move {
        let result = exam::solve_exam(
            &task.base_url, &task.cookie_str, &task.work_id,
            &task.course_id, &task.node_id, &task.api_key, &task.model,
            if task.item_type.is_empty() { "work" } else { &task.item_type },
        ).await;
        match result {
            Ok(r) => {
                tracing::info!(order_id = %resp_id, result = %r, "考试完成");
                let done = r["success"].as_bool().unwrap_or(false);
                let _ = tokio::fs::write(&task.status_file, json!({
                    "phase": "exam", "done": true, "success": done,
                    "message": format!("考试完成 提交{}/{}", r["submitted"], r["total"]),
                }).to_string()).await;
            }
            Err(e) => {
                tracing::warn!(order_id = %resp_id, error = %e, "考试失败");
                let _ = tokio::fs::write(&task.status_file, json!({
                    "phase": "exam", "done": true, "success": false,
                    "message": format!("考试失败: {e}"),
                }).to_string()).await;
            }
        }
    });
    Json(json!({"ok": true, "order_id": resp_id2}))
}

async fn submit_cx(
    State(state): State<AppState>,
    Json(task): Json<cx_study::CxTaskInput>,
) -> Json<serde_json::Value> {
    if task.order_id.is_empty() || task.points.is_empty() {
        return Json(json!({"ok": false, "message": "order_id/points 不能为空"}));
    }
    if state.tasks.contains_key(&task.order_id) {
        return Json(json!({"ok": false, "message": "任务已存在"}));
    }

    let push_url = state.push_url.clone();
    let push_token = state.push_token.clone();
    let tasks = state.tasks.clone();
    let order_id = task.order_id.clone();
    let oid_resp = task.order_id.clone();

    let handle = tokio::spawn(async move {
        let result = cx_study::run_cx_study(&task, &push_url, &push_token).await;
        if let Err(e) = result {
            tracing::warn!(order_id = %order_id, error = %e, "cx task failed");
        }
        tasks.remove(&order_id);
    });

    state.tasks.insert(oid_resp.clone(), handle);
    Json(json!({"ok": true, "order_id": oid_resp}))
}

// 供状态写入使用的时间戳
#[allow(dead_code)]
pub(crate) fn now_ms() -> u128 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0)
}

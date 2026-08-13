//! rust_worker — 刷课守护进程
//!
//! Python（编织层）完成登录/爬取/考试后，把刷课任务 JSON 交给本进程；
//! 每任务一个 tokio task，反检测参数与 study_worker.py 的 LightStudyReporter 1:1 对齐。
//! 单进程 N 并发任务内存 ~50MB（对比 Python 每任务 ~100MB 子进程）。

mod cx_study;
mod study;

use std::env;
use std::sync::Arc;

use anyhow::Context;
use axum::{
    Json, Router,
    extract::Path, extract::State,
    routing::{get, post},
};
use dashmap::DashMap;
use serde_json::json;

type TaskMap = Arc<DashMap<String, tokio::task::JoinHandle<()>>>;

#[derive(Clone)]
struct DaemonState {
    tasks: TaskMap,
    push_url: String,
    push_token: String,
}

type SubmitTask = study::TaskInput;

fn env_or(key: &str, default: &str) -> String {
    env::var(key).unwrap_or_else(|_| default.to_string())
}

fn rss_mb() -> u64 {
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
    let port: u16 = env_or("RUST_DAEMON_PORT", "17017").parse().unwrap_or(17017);
    let push_url = env_or("RUST_DAEMON_PUSH_URL", "http://127.0.0.1:8000/api/progress/live/push");
    let push_token = env_or("RUST_DAEMON_PUSH_TOKEN", "");

    let state = DaemonState {
        tasks: Arc::new(DashMap::new()),
        push_url,
        push_token,
    };

    let app = Router::new()
        .route("/health", get(health))
        .route("/status", get(status))
        .route("/submit", post(submit))
        .route("/submit_cx", post(submit_cx))
        .route("/cancel/{order_id}", post(cancel))
        .with_state(state);

    let addr = format!("127.0.0.1:{port}");
    println!("[rust_worker] listening on {addr}");
    let listener = tokio::net::TcpListener::bind(&addr).await
        .with_context(|| format!("绑定 {addr} 失败"))?;
    axum::serve(listener, app).await?;
    Ok(())
}

async fn health(State(state): State<DaemonState>) -> Json<serde_json::Value> {
    Json(json!({
        "tasks": state.tasks.len(),
        "memory_mb": rss_mb(),
    }))
}

async fn status(State(state): State<DaemonState>) -> Json<serde_json::Value> {
    let ids: Vec<String> = state.tasks.iter().map(|e| e.key().clone()).collect();
    Json(json!({"tasks": ids}))
}

async fn cancel(
    State(state): State<DaemonState>,
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
    State(state): State<DaemonState>,
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
            eprintln!("[rust_worker] task {} failed: {e}", oid_for_task);
        }
        tasks.remove(&oid_for_task);
    });

    state.tasks.insert(oid_resp.clone(), handle);
    Json(json!({"ok": true, "order_id": oid_resp}))
}

async fn submit_cx(
    State(state): State<DaemonState>,
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
            eprintln!("[rust_worker] cx task {} failed: {e}", order_id);
        }
        tasks.remove(&order_id);
    });

    state.tasks.insert(oid_resp.clone(), handle);
    Json(json!({"ok": true, "order_id": oid_resp}))
}

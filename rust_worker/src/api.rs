//! HTTP API 路由（纯 Rust 化阶段 0：骨架）
//!
//! 前端兼容：路由路径与响应格式逐步对齐 Python api/ 模块。
//! Phase 3 起逐路由迁移（读路径 → 写路径），迁移期与 Python 双跑对照。

use axum::extract::State;
use axum::routing::{get, post};
use axum::{Json, Router};
use serde_json::{json, Value};

use crate::AppState;

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/info", get(api_info))
        .route("/api/system/status", get(system_status))
        .route("/api/jobs/submit", post(submit_job))
        .route("/health", get(health))
}

/// 提交学校任务到队列（对齐 Python queue.submit_job 核心字段）
async fn submit_job(State(state): State<AppState>, Json(body): Json<Value>) -> Json<Value> {
    match crate::queue::submit_job(&state.db, body).await {
        Ok(v) => Json(v),
        Err(e) => Json(json!({"ok": false, "message": e.to_string()})),
    }
}

async fn api_info() -> Json<Value> {
    Json(json!({"name": "网课代刷平台 API", "version": "7.0.0-rust"}))
}

async fn health(State(state): State<AppState>) -> Json<Value> {
    Json(json!({
        "ok": true,
        "tasks": state.tasks.len(),
        "memory_mb": crate::rss_mb(),
    }))
}

/// 系统状态（对齐 Python /api/system/status 的骨架版本）
async fn system_status(State(state): State<AppState>) -> Json<Value> {
    let orders = match state.db.order_stats().await {
        Ok(v) => v,
        Err(e) => {
            tracing::warn!("order_stats 失败: {e}");
            json!({"total_orders": 0, "total_revenue": 0.0, "by_status": {}})
        }
    };
    Json(json!({
        "queue": {
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "total": 0,
            "active_workers": state.tasks.len(),
        },
        "orders": orders,
    }))
}

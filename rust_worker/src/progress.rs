//! 实时进度：WebSocket 中枢（Rust 版）— 对齐 api/routers/progress.py
//!
//! - POST /api/progress/live/push：worker 推送 → tokio broadcast 广播
//! - GET  /api/progress/ws/live：前端 WS 订阅（ping/pong + 30s 心跳）
//! - 推送鉴权：X-Worker-Token（localhost 豁免，对齐 Python 语义）

use axum::extract::{Request, State, WebSocketUpgrade};
use axum::response::{IntoResponse, Response};
use axum::Json;
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use tokio::sync::broadcast;

use crate::AppState;

/// 进度推送（对齐 push_progress_update：token 鉴权 → 广播）
pub async fn push_progress(
    State(state): State<AppState>,
    headers: axum::http::HeaderMap,
    Json(data): Json<Value>,
) -> Response {
    // 鉴权：配置 WORKER_TOKEN 后校验 X-Worker-Token
    // （Rust 化后 worker 全部同进程/内网，取消 Python 的 localhost 豁免）
    if let Ok(token) = std::env::var("WORKER_TOKEN") {
        if !token.is_empty() {
            let provided = headers
                .get("x-worker-token")
                .and_then(|v| v.to_str().ok())
                .unwrap_or("");
            if provided != token {
                return (axum::http::StatusCode::UNAUTHORIZED,
                        Json(json!({"detail": "无效的 Worker 凭证"}))).into_response();
            }
        }
    }
    let message = data.to_string();
    let _ = state.progress_tx.send(message);
    Json(json!({"success": true, "message": "已推送"})).into_response()
}

/// WebSocket 订阅（对齐 websocket_progress：ping→pong，30s 心跳）
pub async fn ws_live(
    State(state): State<AppState>,
    ws: WebSocketUpgrade,
) -> Response {
    ws.on_upgrade(move |mut socket| async move {
        use axum::extract::ws::Message;
        let mut rx = state.progress_tx.subscribe();
        let mut heartbeat = tokio::time::interval(std::time::Duration::from_secs(30));
        loop {
            tokio::select! {
                _ = heartbeat.tick() => {
                    if socket.send(Message::Text("{\"type\":\"heartbeat\"}".into())).await.is_err() {
                        break;
                    }
                }
                result = rx.recv() => {
                    match result {
                        Ok(msg) => {
                            if socket.send(Message::Text(msg.into())).await.is_err() {
                                break;
                            }
                        }
                        Err(broadcast::error::RecvError::Lagged(_)) => continue,
                        Err(broadcast::error::RecvError::Closed) => break,
                    }
                }
                incoming = socket.recv() => {
                    match incoming {
                        Some(Ok(Message::Text(t))) if t == "ping" => {
                            if socket.send(Message::Text("pong".into())).await.is_err() {
                                break;
                            }
                        }
                        Some(Ok(Message::Close(_))) | None => break,
                        _ => {}
                    }
                }
            }
        }
    })
    .into_response()
}

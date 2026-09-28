//! 实时进度：WebSocket 中枢（Rust 版）
//!
//! - POST /api/progress/live/push：worker 推送 → 统一封装后广播
//! - GET  /api/progress/ws/live：前端 WS 订阅
//! - 推送鉴权：X-Worker-Token
//!
//! ## 消息封装（envelope，v=1）
//!
//! ```json
//! {"v":1,"topic":"order:ORD-x","type":"order.update",
//!  "data":{"order_id":"ORD-x","status":"running","progress":42},
//!  "ts":1759132800123,"seq":12871}
//! ```
//!
//! topic：`order:{order_id}` / `payment:{trade_no}` / `queue` / `dashboard`
//! 控制帧：`auth` / `authenticated` / `sub` / `subscribed` / `error` / `heartbeat` / `pong`
//!
//! ## 鉴权（灰度开关 AUTH_WS_REQUIRED，默认关闭）
//!
//! - 首帧 `{"type":"auth","token":"<admin JWT>"}` → `allowed=["*"]`
//! - 首帧 `{"type":"sub","orders":[{"order_id":..,"view_token":..}]}` → 逐条与
//!   [`crate::order::view_token`] 比对 → 只放行校验通过的 topic；失败只回 `error`
//!   帧不关连接（游客页可能同时持有效+失效订单）；5s 未表态则关闭（4401）。
//! - **topic 过滤在服务端做**：不是性能考虑而是隐私 —— 载荷里含 `message` 文本，
//!   若在客户端过滤，任何人开 DevTools 就能看到别人订单的进度与 order_id。
//! - 开关关闭时等价于全量广播，保证新旧前端共存期不出现「收不到消息」。

use std::collections::HashSet;
use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use axum::extract::ws::{CloseFrame, Message, WebSocket, WebSocketUpgrade};
use axum::extract::State;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::{json, Value};
use tokio::sync::broadcast;

use crate::AppState;

/// 广播单元：topic 单独放在结构体里，订阅端过滤时无需解析 JSON。
/// 载荷用 Arc<str>，一次广播 N 个订阅者只是 N 次 Arc 克隆（O(1) fan-out）。
#[derive(Clone, Debug)]
pub struct Envelope {
    pub topic: Arc<str>,
    pub body: Arc<str>,
}

/// 统一广播入口 —— 各模块一律走这里，不要各自手搓 JSON，
/// 否则 topic / ts / seq 迟早对不上，前端就无法做稳定路由。
pub fn broadcast(state: &AppState, topic: &str, kind: &str, data: Value) {
    let envelope = json!({
        "v": 1,
        "topic": topic,
        "type": kind,
        "data": data,
        "ts": now_ms(),
        "seq": state.ws_seq.fetch_add(1, Ordering::Relaxed),
    });
    send_envelope(state, topic, envelope);
}

/// 广播一个已经封装好的信封（仅本模块内部使用）
fn send_envelope(state: &AppState, topic: &str, envelope: Value) {
    let _ = state.progress_tx.send(Envelope {
        topic: Arc::from(topic),
        body: Arc::from(envelope.to_string().as_str()),
    });
}

fn now_ms() -> u128 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0)
}

fn auth_required() -> bool {
    std::env::var("AUTH_WS_REQUIRED").map(|v| v == "true").unwrap_or(false)
}

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

    // 已是信封 → 原样转发；裸载荷（study.rs / cx_study.rs 现有格式）→ 补封装。
    // 这样两处既有推送调用点零改动即可产出合规范消息。
    if data.get("topic").is_some() && data.get("v").is_some() {
        let topic = data["topic"].as_str().unwrap_or("dashboard").to_string();
        send_envelope(&state, &topic, data);
        return Json(json!({"success": true, "message": "已推送"})).into_response();
    }

    let order_id = data.get("order_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let kind = data.get("type").and_then(|v| v.as_str()).unwrap_or("progress").to_string();
    let (topic, payload) = if order_id.is_empty() {
        ("dashboard".to_string(), data)
    } else {
        // 载荷里回填 order_id：前端按 order_id 局部 patch 时不必再读外层 topic
        let mut payload = data;
        if let Some(obj) = payload.as_object_mut() {
            obj.insert("order_id".to_string(), json!(order_id));
        }
        (format!("order:{order_id}"), payload)
    };
    broadcast(&state, &topic, &kind, payload);
    Json(json!({"success": true, "message": "已推送"})).into_response()
}

/// 订阅范围。`allowed = None` 表示尚未表态（鉴权模式下的初始态，不放行任何消息）。
struct Scope {
    allowed: Option<HashSet<String>>,
    authed: bool,
}

impl Scope {
    fn allows(&self, topic: &str) -> bool {
        match &self.allowed {
            None => false,
            Some(set) => set.contains("*") || set.contains(topic),
        }
    }
}

/// WebSocket 订阅
pub async fn ws_live(
    State(state): State<AppState>,
    ws: WebSocketUpgrade,
) -> Response {
    ws.on_upgrade(move |socket| handle_socket(state, socket)).into_response()
}

async fn handle_socket(state: AppState, mut socket: WebSocket) {
    let required = auth_required();
    let mut scope = Scope {
        allowed: if required { None } else { Some(HashSet::from(["*".to_string()])) },
        authed: !required,
    };

    let mut rx = state.progress_tx.subscribe();
    let mut heartbeat = tokio::time::interval(Duration::from_secs(30));
    let auth_timer = tokio::time::sleep(Duration::from_secs(5));
    tokio::pin!(auth_timer);

    loop {
        tokio::select! {
            // 鉴权模式下的表态期限
            _ = &mut auth_timer, if required && !scope.authed => {
                let _ = send_json(&mut socket, json!({
                    "type": "error", "scope": "auth", "message": "鉴权超时",
                })).await;
                let _ = socket.send(Message::Close(Some(CloseFrame {
                    code: 4401,
                    reason: "未完成鉴权".into(),
                }))).await;
                break;
            }
            _ = heartbeat.tick() => {
                if send_json(&mut socket, json!({"type": "heartbeat"})).await.is_err() {
                    break;
                }
            }
            result = rx.recv() => {
                match result {
                    Ok(env) => {
                        if !scope.allows(&env.topic) { continue; }
                        if socket.send(Message::Text(String::from(&*env.body).into())).await.is_err() {
                            break;
                        }
                    }
                    Err(broadcast::error::RecvError::Lagged(_)) => continue,
                    Err(broadcast::error::RecvError::Closed) => break,
                }
            }
            incoming = socket.recv() => {
                match incoming {
                    Some(Ok(Message::Text(t))) => {
                        // 兼容裸 "ping"（改动窗口期新旧前端共存）
                        if t == "ping" {
                            if send_json(&mut socket, json!({"type": "pong"})).await.is_err() {
                                break;
                            }
                            continue;
                        }
                        let Ok(msg) = serde_json::from_str::<Value>(&t) else { continue };
                        if matches!(handle_control(&mut scope, &msg, &mut socket).await, ControlFlow::Close) {
                            break;
                        }
                    }
                    Some(Ok(Message::Close(_))) | None => break,
                    _ => {}
                }
            }
        }
    }
}

enum ControlFlow {
    Continue,
    Close,
}

/// 处理客户端控制帧（auth / sub / ping）
async fn handle_control(
    scope: &mut Scope,
    msg: &Value,
    socket: &mut WebSocket,
) -> ControlFlow {
    match msg["type"].as_str().unwrap_or("") {
        "ping" => {
            if send_json(socket, json!({"type": "pong"})).await.is_err() {
                return ControlFlow::Close;
            }
        }
        "auth" => {
            let token = msg["token"].as_str().unwrap_or("");
            match crate::auth::verify_token(token) {
                Some(claims) if claims.role == "admin" => {
                    scope.allowed = Some(HashSet::from(["*".to_string()]));
                    scope.authed = true;
                    if send_json(socket, json!({
                        "type": "authenticated", "role": "admin", "topics": ["*"],
                    })).await.is_err() {
                        return ControlFlow::Close;
                    }
                }
                _ => {
                    if send_json(socket, json!({
                        "type": "error", "scope": "auth", "message": "管理员令牌无效",
                    })).await.is_err() {
                        return ControlFlow::Close;
                    }
                }
            }
        }
        "sub" => {
            let mut topics: Vec<String> = Vec::new();
            let mut invalid: Vec<String> = Vec::new();
            for item in msg["orders"].as_array().cloned().unwrap_or_default() {
                let order_id = item["order_id"].as_str().unwrap_or("");
                let token = item["view_token"].as_str().unwrap_or("");
                if order_id.is_empty() {
                    continue;
                }
                if token == crate::order::view_token(order_id) {
                    topics.push(format!("order:{order_id}"));
                } else {
                    invalid.push(order_id.to_string());
                }
            }
            scope.allowed = Some(topics.iter().cloned().collect());
            // 即使一条都没通过也算已表态，不再等 5s 超时（游客可能确实没有有效订单）
            scope.authed = true;
            if send_json(socket, json!({"type": "subscribed", "topics": topics})).await.is_err() {
                return ControlFlow::Close;
            }
            if !invalid.is_empty()
                && send_json(socket, json!({
                    "type": "error", "scope": "sub", "message": "以下订单凭证无效",
                    "order_ids": invalid,
                })).await.is_err()
            {
                return ControlFlow::Close;
            }
        }
        _ => {}
    }
    ControlFlow::Continue
}

async fn send_json(socket: &mut WebSocket, value: Value) -> Result<(), axum::Error> {
    socket.send(Message::Text(value.to_string().into())).await
}

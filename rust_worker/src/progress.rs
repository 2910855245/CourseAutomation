//! 实时进度：推送中枢（Rust 版）
//!
//! - POST /api/progress/live/push：worker 推送 → 统一封装后广播
//! - GET  /api/progress/ws/live：管理后台 WS 订阅（需要首帧 auth/sub 控制帧）
//! - GET  /api/progress/sse/live：客户端 SSE 长连接订阅（订单进度，见下）
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
//! ## 双通道分工
//!
//! - **管理后台走 WS**：需要 `auth`（管理员令牌）与 `sub`（多订单凭证）两种表态，
//!   且后台在桌面端，WS 的双向帧能力用来传控制帧最直接。
//! - **客户端（手机端订单页）走 SSE**：只需单向推送，用原生 `EventSource` 即可，
//!   浏览器自带重连（含退避），前端不必实现 ping / 半开检测 / 指数退避；
//!   鉴权放在查询串里（订单凭证本来就以查询串传递，未新增暴露面），
//!   服务端仍逐条比对 `view_token`，只放行校验通过的 topic。
//! - SSE 关闭时机由前端掌握：页面不可见或订单全部终态即断开，避免手机端
//!   在后台维持长连接空耗电。
//!
//! ## 鉴权
//!
//! WS 通道（管理后台，开关 `AUTH_WS_REQUIRED`，**默认开启**）：
//!
//! - 首帧 `{"type":"auth","token":"<admin JWT>"}` → `allowed=["*"]`
//! - 首帧 `{"type":"sub","orders":[{"order_id":..,"view_token":..}]}` → 逐条与
//!   [`crate::order::view_token`] 比对 → 只放行校验通过的 topic；失败只回 `error`
//!   帧不关连接（游客页可能同时持有效+失效订单）；5s 未表态则关闭（4401）。
//! - 设 `AUTH_WS_REQUIRED=false` 可退回全量广播（仅用于排查问题）。
//!
//! SSE 通道：凭证只能走查询串，因此**不提供**关闭过滤的开关 —— 没有有效
//! view_token 直接 401，不会因为环境变量配错而把全站广播暴露给任何人。
//!
//! - **topic 过滤在服务端做**：不是性能考虑而是隐私 —— 载荷里含 `message` 文本，
//!   若在客户端过滤，任何人开 DevTools 就能看到别人订单的进度与 order_id。

use std::collections::HashSet;
use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use axum::extract::ws::{CloseFrame, Message, WebSocket, WebSocketUpgrade};
use axum::extract::{Query, State};
use axum::response::sse::{Event, KeepAlive, Sse};
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

/// 默认**开启**鉴权。此前默认关闭，等于把所有人的订单进度（含 order_id 与
/// message 文本）挂在公网上，任何人开 DevTools 就能看到别人的订单。
/// 需要临时关闭（例如排查前端问题）时设 `AUTH_WS_REQUIRED=false`。
fn auth_required() -> bool {
    std::env::var("AUTH_WS_REQUIRED").map(|v| v.trim() != "false").unwrap_or(true)
}

/// 进度推送（对齐 push_progress_update：token 鉴权 → 广播）
pub async fn push_progress(
    State(state): State<AppState>,
    headers: axum::http::HeaderMap,
    Json(data): Json<Value>,
) -> Response {
    // 鉴权：X-Worker-Token 必须等于 main::worker_token()。
    // 令牌与出站推送同源：未配置环境变量时是启动时随机生成的进程内令牌，
    // 因此零配置部署下自推送照常，而外部无法伪造广播帧（此前令牌名对不上，
    // 结果是「要么推送全被 401、要么完全不校验」二选一）。
    let provided = headers
        .get("x-worker-token")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    if !crate::crypto::ct_eq(provided.as_bytes(), crate::worker_token().as_bytes()) {
        return (axum::http::StatusCode::UNAUTHORIZED,
                Json(json!({"detail": "无效的 Worker 凭证"}))).into_response();
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
    persist_job_progress(&state, &payload).await;
    broadcast(&state, &topic, &kind, payload);
    Json(json!({"success": true, "message": "已推送"})).into_response()
}

/// 带进度数值的推送帧顺手落库。
///
/// 订单页与后台队列监控读的是 `queue_jobs_*` 的 progress 列；引擎只广播不落库的话，
/// 刷新页面进度条又回到 0%（此前正是如此：整单跑完前永远是 0，末尾直接跳 100）。
/// 让引擎继续不感知数据库，落库收敛在这一个入口，两条推送链路都受益。
async fn persist_job_progress(state: &AppState, payload: &Value) {
    let order_id = payload.get("order_id").and_then(Value::as_str).unwrap_or("");
    let Some(pct) = payload.get("progress").and_then(Value::as_f64) else { return };
    if order_id.is_empty() {
        return;
    }
    let order_id = order_id.to_string();
    let step = payload.get("step").and_then(Value::as_str).unwrap_or("").to_string();
    let done = payload.get("done").and_then(Value::as_i64).unwrap_or(0);
    let total = payload.get("total").and_then(Value::as_i64).unwrap_or(0);
    let pool = state.db.clone_pool();
    let _ = tokio::task::spawn_blocking(move || -> anyhow::Result<()> {
        let conn = pool.get()?;
        for table in ["queue_jobs_school", "queue_jobs_chaoxing"] {
            // 只推进运行中的行：终态任务不允许被迟到的帧改回去
            let _ = conn.execute(
                &format!(
                    "UPDATE {table} SET progress=?1, completed_steps=?2, total_steps=?3,
                            current_step_name=?4
                     WHERE order_id=?5 AND status='running' AND deleted_at IS NULL"
                ),
                rusqlite::params![pct, done, total, step, order_id],
            );
        }
        Ok(())
    })
    .await;
}

/// 解析 `orders=OID:token,OID:token` → 允许的 topic 集合。
/// 与 WS 的 `sub` 帧同一套规则：逐条比对 `view_token`，无效条目直接忽略。
fn orders_scope(spec: &str) -> HashSet<String> {
    let mut allowed = HashSet::new();
    for pair in spec.split(',') {
        let Some((order_id, token)) = pair.split_once(':') else { continue };
        let order_id = order_id.trim();
        if order_id.is_empty() {
            continue;
        }
        if crate::crypto::ct_eq(token.trim().as_bytes(),
                               crate::order::view_token(order_id).as_bytes()) {
            allowed.insert(format!("order:{order_id}"));
        }
    }
    allowed
}

/// SSE 订阅：`GET /api/progress/sse/live?orders=OID:token,OID:token`
///
/// 客户端（手机端订单页）专用长连接：只推 `order:{order_id}` 帧，
/// 没有有效凭证直接 401。连接的生命周期由前端掌握（不可见/全部终态就断开）。
pub async fn sse_live(
    State(state): State<AppState>,
    Query(params): Query<std::collections::HashMap<String, String>>,
) -> Response {
    let allowed = orders_scope(params.get("orders").map(String::as_str).unwrap_or(""));
    if allowed.is_empty() {
        return (
            axum::http::StatusCode::UNAUTHORIZED,
            Json(json!({"success": false, "message": "缺少有效的订单凭证"})),
        )
            .into_response();
    }

    let rx = state.progress_tx.subscribe();
    let allowed = Arc::new(allowed);
    // 用 unfold 手写流而不是引入 tokio-stream：这里只需要「按 topic 过滤 +
    // 掉帧时提示重同步」两件事，不值得为它多一个依赖
    let stream = futures_util::stream::unfold(rx, move |mut rx| {
        let allowed = allowed.clone();
        async move {
            loop {
                match rx.recv().await {
                    Ok(env) => {
                        if !allowed.contains(env.topic.as_ref()) {
                            continue;
                        }
                        return Some((Ok::<_, std::convert::Infallible>(
                            Event::default().data(&*env.body)), rx));
                    }
                    // 广播缓冲被冲掉：静默丢帧会让界面停在旧状态，让前端重拉一次
                    Err(broadcast::error::RecvError::Lagged(_)) => {
                        return Some((Ok(Event::default().event("resync").data("{}")), rx));
                    }
                    Err(broadcast::error::RecvError::Closed) => return None,
                }
            }
        }
    });
    // 心跳 40s：既压住反代的 60s 空闲超时，又不至于让手机基带频繁醒来
    let mut resp = Sse::new(stream)
        .keep_alive(KeepAlive::new().interval(Duration::from_secs(40)).text("ka"))
        .into_response();
    // 反代（nginx/Caddy）默认会缓冲响应体，那会把 SSE 帧憋在缓冲区里，
    // 表现为"连上了但永远收不到消息"。这两个头是给反代和缓存看的通行做法。
    resp.headers_mut().insert(
        axum::http::header::CACHE_CONTROL,
        axum::http::HeaderValue::from_static("no-cache"),
    );
    resp.headers_mut().insert(
        axum::http::HeaderName::from_static("x-accel-buffering"),
        axum::http::HeaderValue::from_static("no"),
    );
    resp
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
                if crate::crypto::ct_eq(token.as_bytes(),
                                        crate::order::view_token(order_id).as_bytes()) {
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_orders_scope_accepts_only_valid_tokens() {
        let oid = "ORD-ABC123";
        let good = crate::order::view_token(oid);
        let spec = format!("{oid}:{good},ORD-BAD:wrongtoken,broken");
        let allowed = orders_scope(&spec);
        assert_eq!(allowed.len(), 1, "只应放行凭证正确的那一条：{allowed:?}");
        assert!(allowed.contains(&format!("order:{oid}")));
    }

    #[test]
    fn test_orders_scope_empty_is_unauthorized_basis() {
        // 空串/缺参数/只有无效条目 → 集合为空 → handler 直接 401
        assert!(orders_scope("").is_empty());
        assert!(orders_scope("ORD-1:").is_empty());
        assert!(orders_scope(":token").is_empty());
    }
}

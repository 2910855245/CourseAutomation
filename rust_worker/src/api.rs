//! HTTP API 路由（纯 Rust 化阶段 3：读路径）
//!
//! 响应格式与 Python 逐字段对齐（对照测试基准见 py_refs.json）。
//! 受保护路由经 auth_middleware 校验 Bearer token。

use axum::extract::{Path, Query, State};
use axum::http::header::AUTHORIZATION;
use axum::http::HeaderMap;
use axum::middleware;
use axum::routing::{delete, get, post};
use axum::{Extension, Json, Router};
use serde_json::{json, Map, Value};

use crate::auth::Claims;
use crate::AppState;

pub fn router(state: AppState) -> Router<AppState> {
    // 受保护读/写路径（Bearer 鉴权）
    let protected = Router::new()
        .route("/api/orders/", get(orders_list))
        .route("/api/admin/dashboard", get(admin_dashboard))
        .route("/api/queue/stats", get(queue_stats))
        .route("/api/pricing", get(pricing))
        .route("/api/pricing/apply-package", post(apply_package))
        .route("/api/admin/orders", get(admin_orders_list))
        .route("/api/admin/orders/{order_id}/accept", post(admin_order_accept))
        .route("/api/admin/orders/{order_id}/enqueue", post(admin_order_enqueue))
        .route("/api/admin/orders/{order_id}/execute", post(admin_order_execute))
        .route("/api/admin/orders/{order_id}/fail", post(admin_order_fail))
        .route("/api/admin/orders/{order_id}/complete", post(admin_order_complete))
        .route("/api/admin/change-password", post(admin_change_password))
        .route("/api/admin/config", get(admin_config_get).post(admin_config_set))
        .route("/api/queue/jobs", get(queue_jobs))
        .route("/api/queue/jobs/{job_id}/cancel", post(queue_job_cancel))
        .route("/api/queue/jobs/{job_id}/retry", post(queue_job_retry))
        .route("/api/queue/jobs/{job_id}", delete(queue_job_delete))
        .route("/api/queue/clear", post(queue_clear))
        .route("/api/queue/pause", post(queue_pause_all))
        .route("/api/queue/pause/{queue}", post(queue_pause_one))
        .route("/api/queue/resume", post(queue_resume_all))
        .route("/api/queue/resume/{queue}", post(queue_resume_one))
        .route("/api/queue/config", post(queue_config))
        .route("/api/queue/detect", get(queue_detect))
        // 聚合经营数据（订单/营收/在跑任务），属后台信息，移到鉴权组
        .route("/api/system/status", get(system_status))
        // 支付配置：前端「支付收款 → 基本配置」依赖（此前后端整段缺失，
        // 导致通讯密钥只能建库时写死、无法在后台读取或轮换）
        .route("/api/ypay/config/get", get(ypay_config_get))
        .route("/api/ypay/config/save", post(ypay_config_save))
        .route("/api/ypay/status", get(ypay_status))
        // 公告发布：前端「系统通告」页 + 首页弹窗依赖
        .route("/api/admin/announcement", post(announcement_publish))
        .route("/api/admin/announcement/disable", post(announcement_disable))
        .route_layer(middleware::from_fn_with_state(state.clone(), crate::auth::auth_middleware));

    Router::new()
        .route("/api/info", get(api_info))
        .route("/api/orders/batch", post(batch_orders))
        // 公告读取（公开：首页弹窗）
        .route("/api/announcement", get(announcement_get))
        // 游客可达：Bearer 或 view_token 二选一（handler 内校验）
        .route("/api/orders/{order_id}", get(order_get).delete(order_delete))
        .route("/api/orders/audit-log/{order_id}", get(order_audit_log))
        .route("/api/orders/active-courses", get(orders_active_courses))
        .route("/api/orders/clear-history", post(orders_clear_history))
        .route("/api/pricing/calculate", post(pricing_calculate))
        .route("/api/ypay/vmq/heart", post(vmq_heart))
        .route("/api/ypay/vmq/push", post(vmq_push))
        .route("/api/admin/login", post(crate::auth::admin_login))
        .route("/health", get(health))
        .merge(protected)
}

/// Bearer 是否有效（可选鉴权路由用）
fn bearer_ok(headers: &HeaderMap) -> bool {
    headers
        .get(AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .map(|t| crate::auth::verify_token(t).is_some())
        .unwrap_or(false)
}

/// 订单访问鉴权：管理员 Bearer，或游客 view_token（sha256(order_id:secret)[:24]）
fn order_access_ok(headers: &HeaderMap, order_id: &str, token: &str) -> bool {
    // view_token 是 24 位 hex（96 bit），本就不易枚举；这里再用常数时间比较，
    // 避免响应耗时泄露「前缀猜对了多少位」
    bearer_ok(headers)
        || (!token.is_empty()
            && crate::crypto::ct_eq(token.as_bytes(),
                                    crate::order::view_token(order_id).as_bytes()))
}


/// VMQ 心跳（签名验证，对齐 ypay_vmq.vmq_heart 的 success/fail 纯文本协议）
async fn vmq_heart(
    State(state): State<AppState>,
    Query(q): Query<std::collections::HashMap<String, String>>,
    body: axum::body::Bytes,
) -> axum::response::Response {
    let mut params = q;
    if let Ok(text) = String::from_utf8(body.to_vec()) {
        for pair in text.split('&') {
            if let Some((k, v)) = pair.split_once('=') {
                params.entry(k.to_string()).or_insert_with(|| v.to_string());
            }
        }
    }
    let t = params.get("t").cloned().unwrap_or_default();
    let sign = params.get("sign").cloned().unwrap_or_default();
    let ok = crate::pay::verify_heart_sign(&state.db, &t, &sign).await;
    axum::response::Response::new(if ok { "success" } else { "fail" }.into())
}

/// VMQ 支付推送（签名验证，对齐 ypay_vmq.vmq_push）
async fn vmq_push(
    State(state): State<AppState>,
    Query(q): Query<std::collections::HashMap<String, String>>,
    body: axum::body::Bytes,
) -> axum::response::Response {
    let mut params = q;
    if let Ok(text) = String::from_utf8(body.to_vec()) {
        for pair in text.split('&') {
            if let Some((k, v)) = pair.split_once('=') {
                params.entry(k.to_string()).or_insert_with(|| v.to_string());
            }
        }
    }
    let ptype = params.get("type").cloned().unwrap_or_default();
    let price = params.get("price").cloned().unwrap_or_default();
    let t = params.get("t").cloned().unwrap_or_default();
    let sign = params.get("sign").cloned().unwrap_or_default();
    let resp = crate::pay::vmq_push_response(&state.db, &ptype, &price, &t, &sign).await;
    axum::response::Response::new(resp.into())
}

/// 批量下单（写路径，与 Python 双跑对照验收）
async fn batch_orders(State(state): State<AppState>, Json(body): Json<Value>) -> Json<Value> {
    match crate::order::create_batch_orders(&state.db, &body).await {
        Ok(v) => Json(v),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
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
            "pending": 0, "running": 0, "completed": 0, "failed": 0, "total": 0,
            "active_workers": state.tasks.len(),
        },
        "orders": orders,
    }))
}

// ── 系统公告（system_config 存储）───────────────────────────────────────
//
// 前端「系统通告」页与首页弹窗都依赖这三个键。此前后端没有对应路由，
// 公告功能整条链路是断的（首页弹窗永远不出现、后台发布必然失败）。
// id 用发布时间戳，且保证严格递增：前端用「服务端 id > 本地已读 id」判断
// 是否弹出，递增才能让每条新公告都能到达已关闭过旧公告的用户。

const ANN_CONTENT: &str = "announcement_content";
const ANN_ID: &str = "announcement_id";
const ANN_ACTIVE: &str = "announcement_active";

async fn announcement_get(State(state): State<AppState>) -> Json<Value> {
    let content = crate::queue::config_get(&state.db, ANN_CONTENT).await.unwrap_or_default();
    let id: i64 = crate::queue::config_get(&state.db, ANN_ID).await
        .and_then(|v| v.parse().ok()).unwrap_or(0);
    let active = crate::queue::config_get(&state.db, ANN_ACTIVE).await
        .map(|v| v == "1").unwrap_or(false) && !content.trim().is_empty();
    Json(json!({
        "success": true,
        "message": "ok",
        "data": { "id": id, "content": if active { content } else { String::new() }, "active": active },
    }))
}

async fn announcement_publish(State(state): State<AppState>, Json(body): Json<Value>) -> Json<Value> {
    let content = body["content"].as_str().unwrap_or("").trim().to_string();
    if content.is_empty() {
        return Json(json!({"success": false, "message": "公告内容不能为空"}));
    }
    // 严格递增的 id（同一秒内连续发布也不会撞号）
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs() as i64).unwrap_or(0);
    let prev: i64 = crate::queue::config_get(&state.db, ANN_ID).await
        .and_then(|v| v.parse().ok()).unwrap_or(0);
    let id = now.max(prev + 1);
    for (k, v) in [(ANN_CONTENT, content.as_str()), (ANN_ACTIVE, "1")] {
        if let Err(e) = crate::queue::config_set(&state.db, k, v).await {
            return Json(json!({"success": false, "message": e.to_string()}));
        }
    }
    if let Err(e) = crate::queue::config_set(&state.db, ANN_ID, &id.to_string()).await {
        return Json(json!({"success": false, "message": e.to_string()}));
    }
    Json(json!({"success": true, "message": "公告已发布", "data": {"id": id}}))
}

async fn announcement_disable(State(state): State<AppState>) -> Json<Value> {
    match crate::queue::config_set(&state.db, ANN_ACTIVE, "0").await {
        Ok(()) => Json(json!({"success": true, "message": "公告已下线"})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

// ── 支付配置（ypay_settings）────────────────────────────────────────────
//
// 这一组是「支付收款 → 基本配置」页面的数据源。此前后端完全没有对应路由，
// 页面请求全部 404，等于支付通讯密钥只能建库时写死、出问题无法在后台轮换。

/// 允许在后台读写的支付配置键（与前端 ypayForm 字段一一对应）
const YPAY_CONFIG_KEYS: [(&str, &str); 3] = [
    ("key", ""),          // 通讯密钥（回调签名用，空表示未配置）
    ("close_time", "5"),  // 未支付订单关闭时间（分钟）
    ("pay_timeout", "300"), // 支付超时（秒）
];

async fn ypay_config_get(State(state): State<AppState>) -> Json<Value> {
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Map<String, Value>> {
        let conn = db.get()?;
        let mut out = Map::new();
        for (k, default) in YPAY_CONFIG_KEYS {
            let v: Option<String> = conn
                .query_row(
                    "SELECT value FROM ypay_settings WHERE key=?1",
                    rusqlite::params![k],
                    |r| r.get(0),
                )
                .ok();
            out.insert(k.to_string(), json!(v.unwrap_or_else(|| default.to_string())));
        }
        Ok(out)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(mut data) => {
            let key_set = data.get("key").and_then(|v| v.as_str()).map(|s| !s.is_empty()).unwrap_or(false);
            data.insert("key_set".into(), json!(key_set));
            Json(json!({"success": true, "message": "ok", "data": data}))
        }
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

async fn ypay_config_save(State(state): State<AppState>, Json(body): Json<Value>) -> Json<Value> {
    let mut pairs: Vec<(String, String)> = Vec::new();
    for (k, _) in YPAY_CONFIG_KEYS {
        if let Some(v) = body.get(k) {
            let s = v.as_str().map(|s| s.to_string()).unwrap_or_else(|| v.to_string());
            pairs.push((k.to_string(), s));
        }
    }
    if pairs.is_empty() {
        return Json(json!({"success": false, "message": "没有可保存的字段"}));
    }
    // 密钥写成空串会让回调签名永久校验失败（pay.rs::ypay_key 取到空值），
    // 这类「静默毁掉支付」的操作直接拒绝。
    if let Some((_, v)) = pairs.iter().find(|(k, _)| k == "key") {
        if v.trim().is_empty() {
            return Json(json!({"success": false, "message": "通讯密钥不能为空"}));
        }
    }
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<()> {
        let mut conn = db.get()?;
        let tx = conn.transaction()?;
        for (k, v) in &pairs {
            tx.execute(
                "INSERT INTO ypay_settings (key, value) VALUES (?1, ?2)
                 ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                rusqlite::params![k, v],
            )?;
        }
        tx.commit()?;
        Ok(())
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(()) => Json(json!({"success": true, "message": "支付配置已保存"})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 支付通道概况：密钥是否就绪 + 支付单数量（供后台「支付收款」页展示）
async fn ypay_status(State(state): State<AppState>) -> Json<Value> {
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Value> {
        let conn = db.get()?;
        let key_set: bool = conn
            .query_row(
                "SELECT COALESCE(NULLIF(value,''),'') <> '' FROM ypay_settings WHERE key='key'",
                [],
                |r| r.get(0),
            )
            .unwrap_or(false);
        let count = |sql: &str| -> i64 { conn.query_row(sql, [], |r| r.get(0)).unwrap_or(0) };
        Ok(json!({
            "key_set": key_set,
            "orders_total": count("SELECT COUNT(*) FROM ypay_order WHERE deleted_at IS NULL"),
            "orders_paid": count("SELECT COUNT(*) FROM ypay_order WHERE deleted_at IS NULL AND status=1"),
            "last_order_at": conn
                .query_row("SELECT COALESCE(MAX(create_time),'') FROM ypay_order", [], |r| r.get::<_, String>(0))
                .unwrap_or_default(),
        }))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => Json(json!({"success": true, "message": "ok", "data": data})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

// 说明：Python 时代的 /api/jobs/submit 已删除 —— 没有任何调用方
// （前端下单走 /api/orders/batch，后台入队走 /api/admin/orders/{id}/enqueue），
// 而它是个无鉴权、可直接往队列表写任意行的入口。

// ── 读路径（与 Python 逐字段对齐）──────────────────────────

fn order_row_to_json(r: &rusqlite::Row, course_ids: &str) -> rusqlite::Result<Value> {
    Ok(json!({
        "order_id": r.get::<_, String>(0)?,
        "out_trade_no": r.get::<_, Option<String>>(1)?.unwrap_or_default(),
        "payment_trade_no": r.get::<_, Option<String>>(2)?.unwrap_or_default(),
        "payment_channel": r.get::<_, Option<String>>(3)?.unwrap_or_default(),
        "payment_time": r.get::<_, Option<String>>(4)?,
        "paid_processed": r.get::<_, Option<String>>(5)?.unwrap_or_default(),
        "user_id": r.get::<_, Option<String>>(6)?.unwrap_or_default(),
        "customer_name": r.get::<_, Option<String>>(7)?.unwrap_or_default(),
        "customer_contact": r.get::<_, Option<String>>(8)?.unwrap_or_default(),
        "username": r.get::<_, Option<String>>(9)?.unwrap_or_default(),
        "password": "***",
        "website_id": r.get::<_, i64>(10)?,
        "task_type": r.get::<_, Option<String>>(11)?.unwrap_or_default(),
        "course_ids": serde_json::from_str::<Value>(course_ids).unwrap_or(json!([])),
        "video_count": r.get::<_, i64>(13)?,
        "exam_count": r.get::<_, i64>(14)?,
        "price": r.get::<_, f64>(15)?,
        "notes": r.get::<_, Option<String>>(16)?.unwrap_or_default(),
        "status": r.get::<_, Option<String>>(17)?.unwrap_or_default(),
        "paid": r.get::<_, i64>(18)?,
        "task_id": r.get::<_, Option<String>>(19)?,
        "admin_note": r.get::<_, Option<String>>(20)?.unwrap_or_default(),
        "created_at": r.get::<_, Option<String>>(21)?.unwrap_or_default(),
        "updated_at": r.get::<_, Option<String>>(22)?.unwrap_or_default(),
        "accepted_at": r.get::<_, Option<String>>(23)?,
        "started_at": r.get::<_, Option<String>>(24)?,
        "finished_at": r.get::<_, Option<String>>(25)?,
        // 刷课节奏档位：历史订单该列为空 → 显示回退均衡
        "speed_mode": r.get::<_, Option<String>>(26)?.unwrap_or_else(|| "balanced".into()),
    }))
}


/// 对齐 Python _inject_task_progress：队列任务进度注入（completed→100，默认 0）
///
/// 原实现是每个订单 2 次 `query_row`（school + chaoxing），列表 50 条就是 100
/// 次往返 —— 一次列表请求把连接池占满，是压测里最先暴露的瓶颈。改成两张表
/// 各一条 `IN (...)` 批量查询后在内存里归并：往返次数 2N → 2，且不再随列表
/// 长度增长。
///
/// 语义保持与原先一致：同一订单 school 表优先于 chaoxing 表；同表内取
/// `created_at` 最新的一条。
///
/// 失败时**不**让整个列表请求失败（与旧行为一致：旧代码对查询错误取 `.ok()`），
/// 只记一条 warn 并保留 progress=0。
fn inject_progress(conn: &rusqlite::Connection, items: &mut [Value]) {
    if items.is_empty() {
        return;
    }
    let ids: Vec<String> = items.iter()
        .filter_map(|i| i["order_id"].as_str().map(String::from))
        .collect();
    if ids.is_empty() {
        return;
    }
    if let Err(e) = inject_progress_inner(conn, items, &ids) {
        tracing::warn!(error = %e, "队列进度注入失败，本次列表进度显示为 0");
    }
}

fn inject_progress_inner(
    conn: &rusqlite::Connection,
    items: &mut [Value],
    ids: &[String],
) -> rusqlite::Result<()> {
    // SQLite 变量数上限（默认 999）：分批绑定，避免长列表直接报错
    const CHUNK: usize = 500;
    let mut latest: std::collections::HashMap<String, f64> = std::collections::HashMap::new();
    // school 先查：or_insert 保证 school 的记录不被 chaoxing 覆盖（学校优先）
    for table in ["queue_jobs_school", "queue_jobs_chaoxing"] {
        for chunk in ids.chunks(CHUNK) {
            let placeholders = std::iter::repeat_n("?", chunk.len())
                .collect::<Vec<_>>()
                .join(",");
            let sql = format!(
                "SELECT order_id, status, progress FROM {table}
                 WHERE order_id IN ({placeholders})
                 ORDER BY created_at DESC"
            );
            let mut stmt = conn.prepare(&sql)?;
            let rows = stmt.query_map(
                rusqlite::params_from_iter(chunk.iter().map(|s| s.as_str())),
                |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?, r.get::<_, f64>(2)?)),
            )?;
            for row in rows {
                let (order_id, status, progress) = row?;
                // 已按 created_at DESC 排序：首次出现即该表最新一条
                latest.entry(order_id)
                    .or_insert(if status == "completed" { 100.0 } else { progress });
            }
        }
    }
    for item in items.iter_mut() {
        let order_id = item["order_id"].as_str().unwrap_or("");
        item["progress"] = json!(latest.get(order_id).copied().unwrap_or(0.0));
    }
    Ok(())
}


async fn orders_list(
    State(state): State<AppState>,
    Query(params): Query<std::collections::HashMap<String, String>>,
) -> Json<Value> {
    let limit = params.get("limit").and_then(|v| v.parse::<i64>().ok()).unwrap_or(50);
    let status_filter = params.get("status").cloned();
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Value> {
        let conn = db.get()?;
        // 先取总数（与 Python 同口径：状态过滤 + 非删除）
        let (total, items) = match &status_filter {
            Some(st) => {
                let total: i64 = conn.query_row(
                    "SELECT COUNT(*) FROM orders WHERE status=?1 AND deleted_at IS NULL",
                    rusqlite::params![st], |r| r.get(0))?;
                let mut stmt = conn.prepare(
                    "SELECT order_id, out_trade_no, ezfpy_trade_no, payment_channel, payment_time,
                            paid_processed, user_id, customer_name, customer_contact, username,
                            website_id, task_type, course_ids, video_count, exam_count, price,
                            notes, status, paid, task_id, admin_note, created_at, updated_at,
                            accepted_at, started_at, finished_at, speed_mode
                     FROM orders WHERE status=?1 AND deleted_at IS NULL
                     ORDER BY created_at DESC LIMIT ?2")?;
                let mut rows: Vec<Value> = stmt.query_map(rusqlite::params![st, limit], |r| {
                    let cids: String = r.get(12)?;
                    order_row_to_json(r, &cids)
                })?.collect::<Result<Vec<_>, _>>()?;
                inject_progress(&conn, &mut rows);
                (total, rows)
            }
            None => {
                let total: i64 = conn.query_row(
                    "SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL", [], |r| r.get(0))?;
                let mut stmt = conn.prepare(
                    "SELECT order_id, out_trade_no, ezfpy_trade_no, payment_channel, payment_time,
                            paid_processed, user_id, customer_name, customer_contact, username,
                            website_id, task_type, course_ids, video_count, exam_count, price,
                            notes, status, paid, task_id, admin_note, created_at, updated_at,
                            accepted_at, started_at, finished_at, speed_mode
                     FROM orders WHERE deleted_at IS NULL
                     ORDER BY created_at DESC LIMIT ?1")?;
                let mut rows: Vec<Value> = stmt.query_map(rusqlite::params![limit], |r| {
                    let cids: String = r.get(12)?;
                    order_row_to_json(r, &cids)
                })?.collect::<Result<Vec<_>, _>>()?;
                inject_progress(&conn, &mut rows);
                (total, rows)
            }
        };
        Ok(json!({
            "total": total,
            "page": 1,
            "page_size": limit,
            "total_pages": ((total + limit - 1) / limit).max(1),
            "items": items,
        }))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => Json(json!({"success": true, "message": "ok", "data": data})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

async fn order_get(
    State(state): State<AppState>,
    Path(order_id): Path<String>,
    Query(params): Query<std::collections::HashMap<String, String>>,
    headers: HeaderMap,
) -> Json<Value> {
    let token = params.get("token").cloned().unwrap_or_default();
    if !order_access_ok(&headers, &order_id, &token) {
        return Json(json!({"success": false, "message": "无权查看该订单"}));
    }
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Option<Value>> {
        let conn = db.get()?;
        let row = conn.query_row(
            "SELECT order_id, out_trade_no, ezfpy_trade_no, payment_channel, payment_time,
                    paid_processed, user_id, customer_name, customer_contact, username,
                    website_id, task_type, course_ids, video_count, exam_count, price,
                    notes, status, paid, task_id, admin_note, created_at, updated_at,
                    accepted_at, started_at, finished_at, speed_mode
             FROM orders WHERE order_id=?1 AND deleted_at IS NULL",
            rusqlite::params![order_id],
            |r| {
                let cids: String = r.get(12)?;
                order_row_to_json(r, &cids)
            },
        );
        match row {
            Ok(v) => Ok(Some(v)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e.into()),
        }
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(Some(data)) => Json(json!({"success": true, "message": "ok", "data": data})),
        Ok(None) => Json(json!({"success": false, "message": "订单不存在"})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 后台数据看板。
///
/// 口径说明（与订单列表/队列监控保持一致，避免同一屏上两个数字对不上）：
///   - 「今日/昨日/近 7 天」按本地时间（北京时间）日期前缀；时间戳统一由
///     queue::now_str() 写入，见 queue::LOCAL_OFFSET_SECS。
///   - 收入 = 已收款（paid=1 或已记 payment_time）且未取消的订单金额；
///     未收款金额单列 `receivable`，两者相加才等于订单总额。此前收入把
///     未付款、已取消的单全部计入，财务报表数字虚高。
///   - 完成率分母为已进入终态的订单（完成 + 失败 + 取消），不含仍在流转的单，
///     否则"刚下单还没跑"会稀释完成率，看着像系统在变差。
///
/// 聚合次数：订单 1 次全表条件聚合 + 7 天分组 1 次 + 队列 2 次 + AI 用量 3 次，
/// 替代此前「7 次 COUNT + 3 次 SUM + 每日 2 次 ×7 天」的 24 次扫描。
async fn admin_dashboard(State(state): State<AppState>) -> Json<Value> {
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Value> {
        let conn = db.get()?;
        let now = crate::queue::local_secs();
        let today_prefix = day_label(now).1;               // YYYY-MM-DD
        let today_like = format!("{today_prefix}%");
        let yest_like = format!("{}%", day_label(now - 86400).1);
        let week_from = day_label(now - 6 * 86400).1;       // 近 7 天（含今日）
        // 卡单判定阈值：排队/待处理超 2 小时、执行中超 6 小时
        let stuck_before = crate::queue::iso_from_secs(now - 2 * 3600);
        let running_before = crate::queue::iso_from_secs(now - 6 * 3600);
        // 已收款的统一定义，多处复用
        const PAID: &str = "(paid=1 OR payment_time IS NOT NULL) AND status<>'cancelled'";

        let (total, paid_count, today_c, yest_c, week_c, completed, pending, running, failed, cancelled,
             rev_total, rev_today, rev_yest, rev_week, receivable, refund_due,
             stuck, long_running, avg_hours): (i64, i64, i64, i64, i64, i64, i64, i64, i64, i64,
                                               f64, f64, f64, f64, f64, f64, i64, i64, f64) =
            conn.query_row(
                &format!(
                    "SELECT
                        COUNT(*),
                        COALESCE(SUM(CASE WHEN {PAID} THEN 1 ELSE 0 END), 0),
                        COALESCE(SUM(created_at LIKE ?1), 0),
                        COALESCE(SUM(created_at LIKE ?2), 0),
                        COALESCE(SUM(created_at >= ?3), 0),
                        COALESCE(SUM(status='completed'), 0),
                        COALESCE(SUM(status='pending'), 0),
                        COALESCE(SUM(status='running'), 0),
                        COALESCE(SUM(status='failed'), 0),
                        COALESCE(SUM(status='cancelled'), 0),
                        COALESCE(SUM(CASE WHEN {PAID} THEN price ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN {PAID} AND created_at LIKE ?1 THEN price ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN {PAID} AND created_at LIKE ?2 THEN price ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN {PAID} AND created_at >= ?3 THEN price ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN NOT {PAID} AND status<>'cancelled' THEN price ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN (paid=1 OR payment_time IS NOT NULL) AND status='cancelled'
                                          THEN price ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN status IN ('pending','accepted','paid','queued','waiting')
                                           AND created_at < ?4 THEN 1 ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN status='running' AND created_at < ?5 THEN 1 ELSE 0 END), 0),
                        COALESCE(AVG(CASE WHEN status='completed' AND finished_at IS NOT NULL
                                          THEN (julianday(finished_at)-julianday(created_at))*24 END), 0)
                     FROM orders WHERE deleted_at IS NULL"
                ),
                rusqlite::params![today_like, yest_like, week_from, stuck_before, running_before],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?, r.get(5)?,
                        r.get(6)?, r.get(7)?, r.get(8)?, r.get(9)?, r.get(10)?, r.get(11)?,
                        r.get(12)?, r.get(13)?, r.get(14)?, r.get(15)?, r.get(16)?, r.get(17)?,
                        r.get(18)?)),
            // 元组超过 12 项不实现 Default，失败时手写全零兜底（与成功路径同形状）
            ).unwrap_or((0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 0.0));

        // 近 7 天趋势：一次分组查询取回订单/收入/失败，避免每天 2 次 COUNT
        let mut day_rows: std::collections::HashMap<String, (i64, f64, i64)> =
            std::collections::HashMap::new();
        {
            let mut stmt = conn.prepare(
                &format!(
                    "SELECT substr(created_at,1,10) AS d, COUNT(*),
                            COALESCE(SUM(CASE WHEN {PAID} THEN price ELSE 0 END), 0),
                            COALESCE(SUM(status='failed'), 0)
                     FROM orders WHERE deleted_at IS NULL AND created_at >= ?1
                     GROUP BY d"
                ))?;
            for r in stmt.query_map(rusqlite::params![week_from], |r| {
                Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?,
                    r.get::<_, f64>(2)?, r.get::<_, i64>(3)?))
            })? {
                let (d, c, v, f) = r?;
                day_rows.insert(d, (c, v, f));
            }
        }

        // AI 用量（近 7 天按天分组；今日单独一条汇总）
        let mut ai_days: std::collections::HashMap<String, (i64, f64)> =
            std::collections::HashMap::new();
        {
            let mut stmt = conn.prepare(
                "SELECT substr(created_at,1,10) AS d, COUNT(*), COALESCE(SUM(cost_yuan),0)
                 FROM ai_usage WHERE created_at >= ?1 GROUP BY d")?;
            for r in stmt.query_map(rusqlite::params![week_from], |r| {
                Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?, r.get::<_, f64>(2)?))
            })? {
                let (d, c, v) = r?;
                ai_days.insert(d, (c, v));
            }
        }

        let mut recent_7_days = Vec::new();
        for i in (0..7).rev() {
            let (label, prefix) = day_label(now - i * 86400);
            let (o, rev, fail) = day_rows.get(&prefix).copied().unwrap_or((0, 0.0, 0));
            let (ai_calls, ai_cost) = ai_days.get(&prefix).copied().unwrap_or((0, 0.0));
            recent_7_days.push(json!({
                "date": label, "orders": o, "revenue": rev, "failed": fail,
                "ai_calls": ai_calls, "ai_cost": ai_cost,
            }));
        }

        // AI 用量汇总：今日 / 近 7 天 / 累计，含缓存命中率与成功率
        let ai_agg = |range_sql: &str, param: Option<&str>| -> (i64, i64, i64, i64, i64, f64) {
            let sql = format!(
                "SELECT COUNT(*), COALESCE(SUM(ok),0), COALESCE(SUM(prompt_tokens),0),
                        COALESCE(SUM(completion_tokens),0),
                        COALESCE(SUM(cache_hit_tokens),0), COALESCE(SUM(cost_yuan),0)
                 FROM ai_usage {range_sql}");
            let map = |r: &rusqlite::Row<'_>| -> rusqlite::Result<(i64, i64, i64, i64, i64, f64)> {
                Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?, r.get(5)?))
            };
            match param {
                Some(p) => conn.query_row(&sql, rusqlite::params![p], map),
                None => conn.query_row(&sql, [], map),
            }
            .unwrap_or_default()
        };
        let ai_today = ai_agg("WHERE created_at LIKE ?1", Some(&today_like));
        let ai_total = ai_agg("", None);
        // by_scene 近 7 天：哪类调用在烧钱（答题/测验/复核/验证码）
        let mut ai_scenes: Vec<(String, i64, f64)> = Vec::new();
        {
            let mut stmt = conn.prepare(
                "SELECT scene, COUNT(*), COALESCE(SUM(cost_yuan),0) FROM ai_usage
                 WHERE created_at >= ?1 GROUP BY scene ORDER BY 3 DESC LIMIT 8")?;
            for r in stmt.query_map(rusqlite::params![week_from], |r| {
                Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?, r.get::<_, f64>(2)?))
            })? {
                ai_scenes.push(r?);
            }
        }
        let hit_rate = |hit: i64, miss: i64| -> f64 {
            let d = hit + miss;
            if d > 0 { hit as f64 / d as f64 } else { 0.0 }
        };

        // 队列快照（看板要能一眼看出"任务有没有在动"）
        let (q_pending, q_running, q_retrying, q_failed, q_completed, q_waiting):
            (i64, i64, i64, i64, i64, i64) = conn.query_row(
            "SELECT COALESCE(SUM(status='pending'),0), COALESCE(SUM(status='running'),0),
                    COALESCE(SUM(status='retrying'),0), COALESCE(SUM(status='failed'),0),
                    COALESCE(SUM(status='completed'),0), COALESCE(SUM(status='waiting'),0)
             FROM queue_jobs_school WHERE deleted_at IS NULL",
            [], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?, r.get(5)?)),
        ).unwrap_or_default();
        let oldest_pending: Option<String> = conn.query_row(
            "SELECT MIN(created_at) FROM queue_jobs_school
             WHERE deleted_at IS NULL AND status IN ('pending','retrying')",
            [], |r| r.get(0)).ok().flatten();
        let max_workers = crate::queue::config_get_blocking(&conn, "queue_max_workers")
            .and_then(|v| v.parse::<i64>().ok()).unwrap_or(0);
        let paused = crate::queue::config_get_blocking(&conn, "queue_paused")
            .map(|v| v == "1").unwrap_or(false);
        let backlog_minutes = oldest_pending.as_deref()
            .and_then(crate::pay::parse_iso_secs)
            .map(|t| ((now as i64 - t) / 60).max(0))
            .unwrap_or(0);

        // 平台 / 任务类型 / 状态分布
        let mut stmt = conn.prepare(
            &format!(
                "SELECT website_id, COUNT(*), COALESCE(SUM(CASE WHEN {PAID} THEN price ELSE 0 END),0)
                 FROM orders WHERE deleted_at IS NULL GROUP BY website_id"))?;
        let mut dist = std::collections::HashMap::new();
        for r in stmt.query_map([], |r| Ok((r.get::<_, i64>(0)?, r.get::<_, i64>(1)?, r.get::<_, f64>(2)?)))? {
            let (w, c, v) = r?;
            dist.insert(w, (c, v));
        }
        let platform_distribution: Vec<Value> = (1..=4).map(|w| {
            let (c, v) = dist.get(&w).copied().unwrap_or((0, 0.0));
            json!({"website_id": w, "count": c, "revenue": v})
        }).collect();

        let mut stmt = conn.prepare(
            &format!(
                "SELECT task_type, COUNT(*), COALESCE(SUM(CASE WHEN {PAID} THEN price ELSE 0 END),0)
                 FROM orders WHERE deleted_at IS NULL GROUP BY task_type"))?;
        let task_type_distribution: Vec<Value> = stmt.query_map([], |r| {
            Ok(json!({"task_type": r.get::<_, String>(0)?, "count": r.get::<_, i64>(1)?, "revenue": r.get::<_, f64>(2)?}))
        })?.collect::<Result<Vec<_>, _>>()?;

        let mut stmt = conn.prepare(
            "SELECT status, COUNT(*) FROM orders WHERE deleted_at IS NULL GROUP BY status")?;
        let status_distribution: Vec<Value> = stmt.query_map([], |r| {
            Ok(json!({"status": r.get::<_, String>(0)?, "count": r.get::<_, i64>(1)?}))
        })?.collect::<Result<Vec<_>, _>>()?;

        let mut stmt = conn.prepare(
            "SELECT order_id, username, website_id, task_type, price, status, created_at, paid
             FROM orders WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 10")?;
        let recent_orders: Vec<Value> = stmt.query_map([], |r| {
            Ok(json!({
                "order_id": r.get::<_, String>(0)?,
                "username": r.get::<_, Option<String>>(1)?.unwrap_or_default(),
                "website_id": r.get::<_, i64>(2)?,
                "task_type": r.get::<_, Option<String>>(3)?.unwrap_or_default(),
                "price": r.get::<_, f64>(4)?,
                "status": r.get::<_, Option<String>>(5)?.unwrap_or_default(),
                "created_at": r.get::<_, Option<String>>(6)?.unwrap_or_default(),
                "paid": r.get::<_, Option<i64>>(7)?.unwrap_or(0) != 0,
            }))
        })?.collect::<Result<Vec<_>, _>>()?;

        // ── 异常信号：看板第一眼要看的就是"现在有没有事" ──
        let mut alerts: Vec<Value> = Vec::new();
        let mut push_alert = |level: &str, title: &str, detail: String| {
            alerts.push(json!({"level": level, "title": title, "detail": detail}));
        };
        if !crate::queue::dispatcher_enabled_public() && (q_pending + q_retrying) > 0 {
            push_alert("danger", "调度器已停用",
                       format!("有 {} 个任务在排队但调度器处于停用状态，任务不会被执行",
                               q_pending + q_retrying));
        }
        if paused && (q_pending + q_retrying) > 0 {
            push_alert("danger", "队列处于暂停",
                       format!("队列已暂停，{} 个任务等待放行", q_pending + q_retrying));
        }
        if q_failed > 0 {
            push_alert("warn", "有失败任务待处理",
                       format!("队列中有 {q_failed} 个失败任务，可在队列监控里重试或删除"));
        }
        if backlog_minutes >= 60 {
            push_alert("warn", "排队积压",
                       format!("最早的排队任务已等待 {} 分钟", backlog_minutes));
        }
        if stuck > 0 {
            push_alert("warn", "订单长时间未推进",
                       format!("{stuck} 个待处理/排队订单超过 2 小时没有状态变化"));
        }
        if long_running > 0 {
            push_alert("danger", "执行中订单超时",
                       format!("{long_running} 个订单执行超过 6 小时，可能已卡死"));
        }
        if failed > 0 {
            push_alert("warn", "存在失败订单",
                       format!("累计 {failed} 个失败订单，需人工确认是否重跑"));
        }
        if refund_due > 0.0 {
            push_alert("warn", "已收款订单被取消",
                       format!("共 {refund_due:.2} 元已收款但订单已取消，请确认是否已完成退款"));
        }
        let ai_calls_today = ai_today.0;
        let ai_fail_today = ai_calls_today - ai_today.1;
        if ai_calls_today >= 5 && ai_fail_today * 5 > ai_calls_today {
            push_alert("warn", "AI 调用失败率偏高",
                       format!("今日 {ai_calls_today} 次调用中 {ai_fail_today} 次失败，检查 API Key 与额度"));
        }
        if total == 0 {
            push_alert("info", "暂无经营数据", "还没有订单记录，跑通一单后这里会出现趋势与分布".into());
        }

        let terminal = completed + failed + cancelled;
        Ok(json!({
            "orders": {
                "total": total, "today": today_c, "yesterday": yest_c, "week": week_c,
                "completed": completed, "pending": pending, "running": running,
                "failed": failed, "cancelled": cancelled, "paid": paid_count,
                // 完成率分母为终态订单（见函数注释）
                "completion_rate": if terminal > 0 { completed as f64 / terminal as f64 } else { 0.0 },
                "avg_delivery_hours": (avg_hours * 10.0).round() / 10.0,
                "stuck": stuck,
                "long_running": long_running,
                // 环比：今日 vs 昨日（昨日为 0 时不返回倍数，避免除零得到 Infinity）
                "today_change": if yest_c > 0 { Some((today_c - yest_c) as f64 / yest_c as f64) } else { None },
                "today_diff": (today_c - yest_c),
            },
            "revenue": {
                "total": rev_total, "today": rev_today, "yesterday": rev_yest,
                "week": rev_week, "receivable": receivable, "refund_due": refund_due,
                // 客单价 = 实收 / 已收款订单数（用全部订单数是把未付款单也算进分母）
                "avg_order": if paid_count > 0 { (rev_total / paid_count as f64 * 100.0).round() / 100.0 } else { 0.0 },
                "today_change": if rev_yest > 0.0 { Some((rev_today - rev_yest) / rev_yest) } else { None },
                "today_diff": (rev_today - rev_yest * 100.0).round() / 100.0,
            },
            "queue": {
                "enabled": crate::queue::dispatcher_enabled_public(),
                "paused": paused,
                "active_workers": crate::queue::active_workers(),
                "max_workers": max_workers,
                "pending": q_pending, "retrying": q_retrying, "running": q_running,
                "waiting": q_waiting, "failed": q_failed, "completed": q_completed,
                "backlog_minutes": backlog_minutes,
            },
            "ai": {
                "today": {
                    "calls": ai_today.0, "ok": ai_today.1,
                    "prompt_tokens": ai_today.2, "completion_tokens": ai_today.3,
                    "cache_hit_tokens": ai_today.4, "cost": ai_today.5,
                    "cache_hit_rate": hit_rate(ai_today.4, (ai_today.2 - ai_today.4).max(0)),
                    "success_rate": if ai_today.0 > 0 { ai_today.1 as f64 / ai_today.0 as f64 } else { 0.0 },
                },
                "total": {
                    "calls": ai_total.0, "ok": ai_total.1,
                    "prompt_tokens": ai_total.2, "completion_tokens": ai_total.3,
                    "cache_hit_tokens": ai_total.4, "cost": ai_total.5,
                },
                "by_scene": ai_scenes.iter().map(|(s, c, v)| json!({
                    "scene": s, "calls": c, "cost": v,
                })).collect::<Vec<_>>(),
            },
            "alerts": alerts,
            "platform_distribution": platform_distribution,
            "task_type_distribution": task_type_distribution,
            "status_distribution": status_distribution,
            "recent_7_days": recent_7_days,
            "recent_orders": recent_orders,
        }))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => Json(json!({"success": true, "message": "ok", "data": data})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 秒时间戳 → (MM/DD 标签, YYYY-MM-DD 前缀)
fn day_label(secs: u64) -> (String, String) {
    let days = secs / 86400;
    let mut y = 1970u64;
    let mut rem = days;
    loop {
        let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
        let ydays = if leap { 366 } else { 365 };
        if rem < ydays { break; }
        rem -= ydays;
        y += 1;
    }
    let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
    let mdays = [31, if leap { 29 } else { 28 }, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let mut m = 0usize;
    while rem >= mdays[m] {
        rem -= mdays[m];
        m += 1;
    }
    (format!("{:02}/{:02}", m + 1, rem + 1), format!("{:04}-{:02}-{:02}", y, m + 1, rem + 1))
}

async fn queue_stats(State(state): State<AppState>) -> Json<Value> {
    // 运行期配置（管理端可热更新，调度器每 5s 同步一次）
    let max_workers = crate::queue::config_get(&state.db, "queue_max_workers").await
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or_else(|| default_max_workers() as i64);
    let paused_all = crate::queue::config_get(&state.db, "queue_paused").await
        .map(|v| v == "1").unwrap_or(false);
    let paused_school = paused_all || crate::queue::config_get(&state.db, "queue_paused_school").await
        .map(|v| v == "1").unwrap_or(false);
    let paused_cx = paused_all || crate::queue::config_get(&state.db, "queue_paused_chaoxing").await
        .map(|v| v == "1").unwrap_or(false);
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Value> {
        let conn = db.get()?;
        // 统计口径与任务列表保持一致：都被软删的任务不该继续出现在 KPI 里
        // （此前列表过滤了 deleted_at、KPI 没过滤，两个数字对不上）
        let table_stats = |table: &str| -> rusqlite::Result<Map<String, Value>> {
            let mut m = Map::new();
            for st in ["pending", "running", "waiting", "completed", "failed"] {
                let c: i64 = conn.query_row(
                    &format!("SELECT COUNT(*) FROM {table} WHERE status=?1 AND deleted_at IS NULL"),
                    rusqlite::params![st], |r| r.get(0))?;
                m.insert(st.to_string(), json!(c));
            }
            let total: i64 = conn.query_row(
                &format!("SELECT COUNT(*) FROM {table} WHERE deleted_at IS NULL"),
                [], |r| r.get(0))?;
            m.insert("total".into(), json!(total));
            Ok(m)
        };
        let active = crate::queue::active_workers() as i64;
        let mut school = table_stats("queue_jobs_school")?;
        let mut chaoxing = table_stats("queue_jobs_chaoxing")?;
        // 学校队列是唯一被调度器消费的队列（学习通链路未落地），
        // 所以进程级在跑数全部归到 school；chaoxing 恒为 0 是事实而非占位。
        school.insert("active_workers".into(), json!(active));
        school.insert("max_workers".into(), json!(max_workers));
        school.insert("active_study_workers".into(), json!(active));
        school.insert("max_study_workers".into(), json!(max_workers));
        school.insert("paused".into(), json!(paused_school));
        school.insert("queue_name".into(), json!("school"));
        chaoxing.insert("active_workers".into(), json!(0));
        chaoxing.insert("max_workers".into(), json!(max_workers));
        chaoxing.insert("active_study_workers".into(), json!(0));
        chaoxing.insert("max_study_workers".into(), json!(max_workers));
        chaoxing.insert("paused".into(), json!(paused_cx));
        chaoxing.insert("queue_name".into(), json!("chaoxing"));

        let sum = |k: &str| -> i64 {
            school.get(k).and_then(|v| v.as_i64()).unwrap_or(0)
                + chaoxing.get(k).and_then(|v| v.as_i64()).unwrap_or(0)
        };
        Ok(json!({
            "pending": sum("pending"), "running": sum("running"), "waiting": sum("waiting"),
            "completed": sum("completed"), "failed": sum("failed"), "total": sum("total"),
            "active_workers": active, "max_workers": max_workers, "paused": paused_all,
            // 调度器是否真的在消费（此前监控只显示"暂停/运行中"，开关没开会假装运行中）
            "scheduler_enabled": crate::queue::dispatcher_enabled_public(),
            "global_study_sessions": crate::study::global_session_limit_public(),
            "school": school, "chaoxing": chaoxing,
        }))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => Json(json!({"success": true, "message": "ok", "data": data})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 定价配置键：前端 camelCase ↔ 库内 snake_case（对齐 useSystemConfig.loadPricing）
const PRICING_KEYS: &[(&str, &str, f64)] = &[
    ("priceSmall", "price_small", 3.0),
    ("priceMedium", "price_medium", 5.0),
    ("priceLarge", "price_large", 6.0),
    ("discount25", "discount_25", 0.7),
    ("discount50", "discount_50", 0.5),
    ("discount75", "discount_75", 0.3),
    ("priceMinimum", "price_minimum", 2.0),
    ("priceExamOnly", "price_exam_only", 5.0),
    ("priceHomeworkOnly", "price_homework_only", 3.0),
    ("priceChaoxing", "price_chaoxing", 8.0),
];

async fn pricing(State(state): State<AppState>) -> Json<Value> {
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Value> {
        let conn = db.get()?;
        let mut data = Map::new();
        for (camel, snake, default) in PRICING_KEYS {
            let v: Option<String> = conn.query_row(
                "SELECT config_value FROM system_config WHERE config_key=?1",
                rusqlite::params![snake], |r| r.get(0),
            ).ok().flatten();
            data.insert(camel.to_string(), json!(v.and_then(|s| s.parse::<f64>().ok()).unwrap_or(*default)));
        }
        // 前端类型里声明的单价/模式字段（当前按打包定价，单价位占位）
        data.insert("videoUnitPrice".into(), json!(0));
        data.insert("examUnitPrice".into(), json!(0));
        data.insert("homeworkUnitPrice".into(), json!(0));
        data.insert("pricingMode".into(), json!("package"));
        Ok(Value::Object(data))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => Json(json!({"code": 0, "data": data})),
        Err(e) => Json(json!({"code": -1, "data": {}, "message": e.to_string()})),
    }
}

/// 保存打包定价（前端传 camelCase，落库 snake_case）
async fn apply_package(State(state): State<AppState>, Json(body): Json<Value>) -> Json<Value> {
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<usize> {
        let conn = db.get()?;
        let now = crate::queue::now_str();
        let mut n = 0usize;
        for (camel, snake, _) in PRICING_KEYS {
            if let Some(v) = body.get(*camel).and_then(|v| v.as_f64()) {
                conn.execute(
                    "INSERT INTO system_config (config_key, config_value, updated_at)
                     VALUES (?1, ?2, ?3)
                     ON CONFLICT(config_key) DO UPDATE SET config_value=excluded.config_value,
                                                          updated_at=excluded.updated_at",
                    rusqlite::params![snake, v.to_string(), now],
                )?;
                n += 1;
            }
        }
        Ok(n)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(n) => Json(json!({"success": true, "message": format!("已保存 {n} 项定价配置")})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 试算价格（对齐 /api/pricing/calculate：逐课 type/price/label + 总价）
async fn pricing_calculate(State(state): State<AppState>, Json(body): Json<Value>) -> Json<Value> {
    let courses = body["courses"].as_array().cloned().unwrap_or_default();
    let cfg = match crate::order::pricing_config(&state.db).await {
        Ok(c) => c,
        Err(e) => return Json(json!({"success": false, "message": e.to_string()})),
    };
    let (entries, total) = crate::order::price_courses(&cfg, &courses);
    Json(json!({
        "success": true,
        "message": "ok",
        "data": {"courses": entries, "total": total, "pricing_mode": "package"},
    }))
}

// ── 订单：游客可写/可读（token 或 Bearer）────────────────────────────────

/// 取消订单（前端走 DELETE /api/orders/{id}）
async fn order_delete(
    State(state): State<AppState>,
    Path(order_id): Path<String>,
    Query(params): Query<std::collections::HashMap<String, String>>,
    headers: HeaderMap,
) -> Json<Value> {
    let token = params.get("token").cloned().unwrap_or_default();
    if !order_access_ok(&headers, &order_id, &token) {
        return Json(json!({"success": false, "message": "无权操作该订单"}));
    }
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<i64> {
        let conn = db.get()?;
        // 终态订单不可取消（已跑完/已失败）
        let n = conn.execute(
            "UPDATE orders SET status='cancelled', updated_at=?2
             WHERE order_id=?1 AND status NOT IN ('completed','failed','running')",
            rusqlite::params![order_id, crate::queue::now_str()],
        )?;
        if n > 0 {
            log_event(&conn, "order_cancelled", "user", "用户取消订单", &order_id)?;
        }
        Ok(n as i64)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(n) if n > 0 => Json(json!({"success": true, "message": "订单已取消"})),
        Ok(_) => Json(json!({"success": false, "message": "订单当前状态不可取消"})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 订单操作日志（audit_logs.event_type → event，对齐前端字段名）
async fn order_audit_log(
    State(state): State<AppState>,
    Path(order_id): Path<String>,
    headers: HeaderMap,
    Query(params): Query<std::collections::HashMap<String, String>>,
) -> Json<Value> {
    // 与查单同一套鉴权（管理员 Bearer 或该订单的 view_token）。
    // 此前完全没有校验：只要猜到 ORD-xxxxxxxx 就能读到任意订单的操作日志。
    let token = params.get("token").cloned().unwrap_or_default();
    if !order_access_ok(&headers, &order_id, &token) {
        return Json(json!({"success": false, "message": "无权访问该订单"}));
    }
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Vec<Value>> {
        let conn = db.get()?;
        let mut stmt = conn.prepare(
            "SELECT event_type, detail, created_at FROM audit_logs
             WHERE order_id=?1 ORDER BY created_at DESC LIMIT 50",
        )?;
        let rows = stmt
            .query_map(rusqlite::params![order_id], |r| {
                Ok(json!({
                    "event": r.get::<_, String>(0)?,
                    "detail": r.get::<_, Option<String>>(1)?.unwrap_or_default(),
                    "created_at": r.get::<_, Option<String>>(2)?.unwrap_or_default(),
                }))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        Ok(rows)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => Json(json!({"success": true, "message": "ok", "data": data})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 进行中订单的课程 ID 列表（前端据此禁止重复下单）
async fn orders_active_courses(
    State(state): State<AppState>,
    Query(params): Query<std::collections::HashMap<String, String>>,
) -> Json<Value> {
    let username = params.get("username").cloned().unwrap_or_default();
    if username.is_empty() {
        return Json(json!({"success": true, "message": "ok", "data": []}));
    }
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Vec<String>> {
        let conn = db.get()?;
        let mut stmt = conn.prepare(
            "SELECT course_ids FROM orders
             WHERE username=?1 AND deleted_at IS NULL
               AND status IN ('pending','accepted','queued','running','retrying','paid','waiting')",
        )?;
        let rows = stmt.query_map(rusqlite::params![username], |r| r.get::<_, String>(0))?;
        let mut ids = Vec::new();
        for r in rows {
            let raw = r?;
            if let Ok(arr) = serde_json::from_str::<Value>(&raw) {
                if let Some(list) = arr.as_array() {
                    for v in list {
                        if let Some(s) = v.as_str() {
                            // "courseId:classId" 只取课程 ID（与扫描结果对齐）
                            ids.push(s.split(':').next().unwrap_or(s).to_string());
                        }
                    }
                }
            }
        }
        ids.sort();
        ids.dedup();
        Ok(ids)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => Json(json!({"success": true, "message": "ok", "data": data})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 清空历史订单：管理员软删除全部终态订单；游客仅返回成功（前端据此清本地缓存）
async fn orders_clear_history(State(state): State<AppState>, headers: HeaderMap) -> Json<Value> {
    if !bearer_ok(&headers) {
        return Json(json!({"success": true, "message": "已清空本地历史"}));
    }
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<usize> {
        let conn = db.get()?;
        let n = conn.execute(
            "UPDATE orders SET deleted_at=?1
             WHERE deleted_at IS NULL AND status IN ('completed','failed','cancelled')",
            rusqlite::params![crate::queue::now_str()],
        )?;
        Ok(n)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(n) => Json(json!({"success": true, "message": format!("已清空 {n} 条历史订单")})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

// ── 管理端：订单 ────────────────────────────────────────────────────────

/// 审计日志写入（统一入口，避免各处手拼 INSERT）
fn log_event(conn: &rusqlite::Connection, event_type: &str, operator: &str,
             detail: &str, order_id: &str) -> rusqlite::Result<()> {
    let log_id = format!("LOG-{:08X}", rand::random::<u32>());
    conn.execute(
        "INSERT INTO audit_logs (log_id, event_type, operator, detail, order_id, user_id, created_at)
         VALUES (?1, ?2, ?3, ?4, ?5, '', ?6)",
        rusqlite::params![log_id, event_type, operator, detail, order_id, crate::queue::now_str()],
    )?;
    Ok(())
}

/// 单条订单（含 course_ids 解析），供管理端动作复用
fn fetch_order(conn: &rusqlite::Connection, order_id: &str) -> rusqlite::Result<Option<Value>> {
    conn.query_row(
        "SELECT order_id, out_trade_no, ezfpy_trade_no, payment_channel, payment_time,
                paid_processed, user_id, customer_name, customer_contact, username,
                website_id, task_type, course_ids, video_count, exam_count, price,
                notes, status, paid, task_id, admin_note, created_at, updated_at,
                accepted_at, started_at, finished_at, speed_mode
         FROM orders WHERE order_id=?1 AND deleted_at IS NULL",
        rusqlite::params![order_id],
        |r| {
            let cids: String = r.get(12)?;
            order_row_to_json(r, &cids)
        },
    )
    .map(Some)
    .or_else(|e| match e {
        rusqlite::Error::QueryReturnedNoRows => Ok(None),
        other => Err(other),
    })
}

/// 管理端订单列表（limit/offset + status/user_id 过滤）
async fn admin_orders_list(
    State(state): State<AppState>,
    Query(params): Query<std::collections::HashMap<String, String>>,
) -> Json<Value> {
    let limit = params.get("limit").and_then(|v| v.parse::<i64>().ok()).unwrap_or(50);
    let offset = params.get("offset").and_then(|v| v.parse::<i64>().ok()).unwrap_or(0);
    let status_filter = params.get("status").cloned().unwrap_or_default();
    let user_id = params.get("user_id").cloned().unwrap_or_default();
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Value> {
        let conn = db.get()?;
        let mut where_sql = String::from("deleted_at IS NULL");
        let mut args: Vec<String> = Vec::new();
        if !status_filter.is_empty() {
            where_sql.push_str(" AND status=?");
            args.push(status_filter);
        }
        if !user_id.is_empty() {
            where_sql.push_str(" AND user_id=?");
            args.push(user_id);
        }
        let total: i64 = conn.query_row(
            &format!("SELECT COUNT(*) FROM orders WHERE {where_sql}"),
            rusqlite::params_from_iter(args.iter()),
            |r| r.get(0),
        )?;
        let mut stmt = conn.prepare(&format!(
            "SELECT order_id, out_trade_no, ezfpy_trade_no, payment_channel, payment_time,
                    paid_processed, user_id, customer_name, customer_contact, username,
                    website_id, task_type, course_ids, video_count, exam_count, price,
                    notes, status, paid, task_id, admin_note, created_at, updated_at,
                    accepted_at, started_at, finished_at, speed_mode
             FROM orders WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        ))?;
        let page_args: Vec<String> = args.iter().cloned()
            .chain([limit.to_string(), offset.to_string()])
            .collect();
        let mut rows: Vec<Value> = stmt
            .query_map(rusqlite::params_from_iter(page_args.iter()), |r| {
                let cids: String = r.get(12)?;
                order_row_to_json(r, &cids)
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        inject_progress(&conn, &mut rows);
        Ok(json!({"total": total, "items": rows}))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => Json(json!({"success": true, "message": "ok", "data": data})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 管理端订单状态迁移（accept/fail/complete 共用）
async fn transition_order(state: &AppState, order_id: &str, set_sql: &str,
                          event: &str, detail: &str) -> Json<Value> {
    let db = state.db.clone_pool();
    let sql = set_sql.to_string();
    let order_id = order_id.to_string();
    let event = event.to_string();
    let detail = detail.to_string();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<usize> {
        let conn = db.get()?;
        let n = conn.execute(&sql, rusqlite::params![crate::queue::now_str(), order_id])?;
        if n > 0 {
            log_event(&conn, &event, "admin", &detail, &order_id)?;
        }
        Ok(n)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(_) => Json(json!({"success": true, "message": "ok"})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

async fn admin_order_accept(State(state): State<AppState>, Path(order_id): Path<String>) -> Json<Value> {
    transition_order(
        &state, &order_id,
        "UPDATE orders SET status='accepted', accepted_at=?1, updated_at=?1
         WHERE order_id=?2 AND status IN ('pending','cancelled')",
        "order_accepted", "管理员接单",
    ).await
}

async fn admin_order_complete(State(state): State<AppState>, Path(order_id): Path<String>) -> Json<Value> {
    transition_order(
        &state, &order_id,
        "UPDATE orders SET status='completed', finished_at=?1, updated_at=?1
         WHERE order_id=?2 AND status <> 'completed'",
        "order_completed", "管理员标记完成",
    ).await
}

#[derive(serde::Deserialize)]
struct FailBody {
    #[serde(default)]
    admin_note: String,
}

async fn admin_order_fail(
    State(state): State<AppState>,
    Path(order_id): Path<String>,
    body: Option<Json<FailBody>>,
) -> Json<Value> {
    let note = body.map(|b| b.0.admin_note).unwrap_or_default();
    let note = if note.is_empty() { "管理员手动标记失败".to_string() } else { note };
    let db = state.db.clone_pool();
    let oid = order_id.clone();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<usize> {
        let conn = db.get()?;
        let now = crate::queue::now_str();
        let n = conn.execute(
            "UPDATE orders SET status='failed', admin_note=?2, finished_at=?1, updated_at=?1
             WHERE order_id=?3 AND status <> 'failed'",
            rusqlite::params![now, note, oid],
        )?;
        if n > 0 {
            log_event(&conn, "order_failed", "admin", &note, &oid)?;
        }
        Ok(n)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(_) => Json(json!({"success": true, "message": "订单已标记失败"})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 入队：把订单转成 queue_jobs_school 行（密码从加密凭据表解密）
async fn admin_order_enqueue(State(state): State<AppState>, Path(order_id): Path<String>) -> Json<Value> {
    match enqueue_order_impl(&state, &order_id).await {
        Ok(job_id) => Json(json!({"success": true, "message": "订单已入队", "data": {"job_id": job_id}})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

async fn enqueue_order_impl(state: &AppState, order_id: &str) -> anyhow::Result<String> {
    let db = state.db.clone_pool();
    let oid = order_id.to_string();
    let job_id = format!("JOB-{:08X}", rand::random::<u32>());
    let job_id_out = job_id.clone();
    tokio::task::spawn_blocking(move || -> anyhow::Result<()> {
        let conn = db.get()?;
        let order = fetch_order(&conn, &oid)?
            .ok_or_else(|| anyhow::anyhow!("订单不存在"))?;
        let username = order["username"].as_str().unwrap_or("").to_string();
        let password = crate::crypto::load_password(&conn, &oid)
            .ok_or_else(|| anyhow::anyhow!("订单凭据缺失（加密记录与明文列均无）"))?;
        conn.execute(
            "INSERT INTO queue_jobs_school
             (job_id, username, password, website_id, job_type, course_ids, status, priority,
              progress, total_steps, completed_steps, current_step_name, error_message,
              retry_count, max_retries, task_id, order_id, result_data, verified,
              created_at, started_at, finished_at, deleted_at, speed_mode)
             VALUES (?1,?2,?3,?4,?5,?6,'pending',0,0,0,0,'','',0,3,NULL,?7,'{}',0,?8,NULL,NULL,NULL,?9)",
            rusqlite::params![
                job_id, username, password,
                order["website_id"].as_i64().unwrap_or(1),
                order["task_type"].as_str().unwrap_or("video"),
                serde_json::to_string(&order["course_ids"])?,
                oid, crate::queue::now_str(),
                crate::speed::SpeedMode::parse(
                    order["speed_mode"].as_str().unwrap_or("")).as_str(),
            ],
        )?;
        conn.execute(
            "UPDATE orders SET status='queued', updated_at=?1 WHERE order_id=?2",
            rusqlite::params![crate::queue::now_str(), oid],
        )?;
        log_event(&conn, "order_enqueued", "admin", "订单已入队", &oid)?;
        Ok(())
    })
    .await??;
    Ok(job_id_out)
}

/// 立即执行：直接派发刷课任务（不等待队列调度器）
async fn admin_order_execute(State(state): State<AppState>, Path(order_id): Path<String>) -> Json<Value> {
    if state.tasks.contains_key(&order_id) {
        return Json(json!({"success": false, "message": "该订单任务已在执行中"}));
    }
    // 取订单 + 解密凭据
    let db = state.db.clone_pool();
    let oid = order_id.clone();
    let loaded = tokio::task::spawn_blocking(move || -> anyhow::Result<Option<(Value, String)>> {
        let conn = db.get()?;
        match fetch_order(&conn, &oid)? {
            Some(order) => {
                let pwd = crate::crypto::load_password(&conn, &oid).unwrap_or_default();
                conn.execute(
                    "UPDATE orders SET status='running', started_at=?1, updated_at=?1 WHERE order_id=?2",
                    rusqlite::params![crate::queue::now_str(), oid],
                )?;
                log_event(&conn, "order_executing", "admin", "管理员手动执行", &oid)?;
                Ok(Some((order, pwd)))
            }
            None => Ok(None),
        }
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);

    let (order, password) = match loaded {
        Ok(Some(v)) => v,
        Ok(None) => return Json(json!({"success": false, "message": "订单不存在"})),
        Err(e) => return Json(json!({"success": false, "message": e.to_string()})),
    };
    let username = order["username"].as_str().unwrap_or("").to_string();
    if username.is_empty() || password.is_empty() {
        return Json(json!({"success": false, "message": "订单账号或凭据缺失，无法执行"}));
    }
    let website_id = order["website_id"].as_i64().unwrap_or(1);
    let course_ids: Vec<String> = order["course_ids"].as_array()
        .map(|a| a.iter().filter_map(|v| v.as_str().map(String::from)).collect())
        .unwrap_or_default();

    // 手动执行同样遵循订单所选档位
    let speed_mode = crate::speed::SpeedMode::parse(
        order["speed_mode"].as_str().unwrap_or("")).as_str().to_string();

    let push_url = state.push_url.clone();
    let push_token = state.push_token.clone();
    let tasks = state.tasks.clone();
    let oid_task = order_id.clone();
    let oid_resp = order_id.clone();
    let handle = tokio::spawn(async move {
        let base_url = crate::scan::platform_base_url(website_id);
        let session = match crate::session::get_session(&base_url, &username, &password).await {
            Ok(s) => s,
            Err(e) => {
                tracing::warn!(order_id = %oid_task, error = %e, "手动执行：登录失败");
                tasks.remove(&oid_task);
                return;
            }
        };
        let tmpdir = std::env::temp_dir().join(format!("task_{oid_task}"));
        let _ = tokio::fs::create_dir_all(&tmpdir).await;
        let task = crate::scan::ScanTaskInput {
            order_id: oid_task.clone(),
            username,
            password,
            base_url,
            cookie_str: session.cookie_str,
            course_ids,
            status_file: tmpdir.join("status.json").to_string_lossy().to_string(),
            push_ws: true,
            speed_mode,
        };
        if let Err(e) = crate::scan::run_scan_and_study(&task, &push_url, &push_token).await {
            tracing::warn!(order_id = %oid_task, error = %e, "手动执行任务失败");
        }
        let _ = tokio::fs::remove_dir_all(&tmpdir).await;
        tasks.remove(&oid_task);
    });
    state.tasks.insert(oid_resp.clone(), handle);
    Json(json!({"success": true, "message": "订单执行中", "data": {"order_id": oid_resp}}))
}

// ── 管理端：改密 / 配置 ─────────────────────────────────────────────────

async fn admin_change_password(
    State(state): State<AppState>,
    Extension(claims): Extension<Claims>,
    Json(body): Json<Value>,
) -> Json<Value> {
    let old = body["old_password"].as_str().unwrap_or("");
    let new = body["new_password"].as_str().unwrap_or("");
    if new.len() < 6 {
        return Json(json!({"success": false, "message": "新密码至少 6 位"}));
    }
    // 用当前登录身份校验旧密码
    if crate::auth::check_user(&state, &claims.sub, old).await.is_none() {
        return Json(json!({"success": false, "message": "原密码错误"}));
    }
    let hash = match bcrypt::hash(new, 10) {
        Ok(h) => h,
        Err(e) => return Json(json!({"success": false, "message": format!("哈希失败: {e}")})),
    };
    let db = state.db.clone_pool();
    let username = claims.sub.clone();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<usize> {
        let conn = db.get()?;
        Ok(conn.execute(
            "UPDATE users SET password_hash=?1 WHERE username=?2 AND deleted_at IS NULL",
            rusqlite::params![hash, username],
        )?)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(n) if n > 0 => Json(json!({"success": true, "message": "密码已修改"})),
        Ok(_) => Json(json!({"success": false, "message": "用户不存在"})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 系统配置读取：全部非敏感配置键值对（前端 ConfigTab 用）
async fn admin_config_get(State(state): State<AppState>) -> Json<Value> {
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Map<String, Value>> {
        let conn = db.get()?;
        let mut stmt = conn.prepare("SELECT config_key, config_value FROM system_config")?;
        let mut out = Map::new();
        for r in stmt.query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?)))? {
            let (k, v) = r?;
            // 密钥类配置脱敏返回
            if k.contains("api_key") || k.contains("secret") {
                out.insert(k, json!("***"));
            } else {
                out.insert(k, json!(v));
            }
        }
        Ok(out)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => Json(json!({"success": true, "message": "ok", "data": data})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

async fn admin_config_set(State(state): State<AppState>, Json(body): Json<Value>) -> Json<Value> {
    let key = body["key"].as_str().unwrap_or("").to_string();
    if key.is_empty() {
        return Json(json!({"success": false, "message": "key 不能为空"}));
    }
    let value = match body.get("value") {
        Some(Value::String(s)) => s.clone(),
        Some(v) => v.to_string(),
        None => String::new(),
    };
    match crate::queue::config_set(&state.db, &key, &value).await {
        Ok(()) => Json(json!({"success": true, "message": "配置已保存"})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

// ── 队列管理 ────────────────────────────────────────────────────────────

const QUEUE_TABLES: &[&str] = &["queue_jobs_school", "queue_jobs_chaoxing"];

/// 队列任务列表（两表合并，附 queue 标识）
async fn queue_jobs(
    State(state): State<AppState>,
    Query(params): Query<std::collections::HashMap<String, String>>,
) -> Json<Value> {
    let queue_filter = params.get("queue").cloned().unwrap_or_default();
    let status_filter = params.get("status").cloned().unwrap_or_default();
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Vec<Value>> {
        let conn = db.get()?;
        let mut out = Vec::new();
        for table in QUEUE_TABLES {
            let queue_tag = if *table == "queue_jobs_chaoxing" { "chaoxing" } else { "school" };
            if !queue_filter.is_empty() && queue_filter != queue_tag {
                continue;
            }
            let mut sql = format!(
                "SELECT job_id, username, order_id, status, progress, current_step_name,
                        error_message, retry_count, verified, job_type, created_at,
                        started_at, finished_at
                 FROM {table} WHERE deleted_at IS NULL"
            );
            let mut args: Vec<String> = Vec::new();
            if !status_filter.is_empty() {
                sql.push_str(" AND status=?");
                args.push(status_filter.clone());
            }
            sql.push_str(" ORDER BY created_at DESC LIMIT 200");
            let mut stmt = conn.prepare(&sql)?;
            let rows = stmt.query_map(rusqlite::params_from_iter(args.iter()), |r| {
                Ok(json!({
                    "job_id": r.get::<_, String>(0)?,
                    "username": r.get::<_, Option<String>>(1)?.unwrap_or_default(),
                    "order_id": r.get::<_, Option<String>>(2)?.unwrap_or_default(),
                    "status": r.get::<_, Option<String>>(3)?.unwrap_or_default(),
                    "progress": r.get::<_, f64>(4)?,
                    "current_step_name": r.get::<_, Option<String>>(5)?.unwrap_or_default(),
                    "error_message": r.get::<_, Option<String>>(6)?.unwrap_or_default(),
                    "retry_count": r.get::<_, i64>(7)?,
                    "verified": r.get::<_, i64>(8)?,
                    "job_type": r.get::<_, Option<String>>(9)?.unwrap_or_default(),
                    "created_at": r.get::<_, Option<String>>(10)?.unwrap_or_default(),
                    "started_at": r.get::<_, Option<String>>(11)?,
                    "finished_at": r.get::<_, Option<String>>(12)?,
                    "queue": queue_tag,
                }))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?;
            out.extend(rows);
        }
        out.sort_by(|a, b| b["created_at"].as_str().cmp(&a["created_at"].as_str()));
        Ok(out)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => Json(json!({"success": true, "message": "ok", "data": data})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 在两张队列表中定位 job_id 所属表
fn find_job_table(conn: &rusqlite::Connection, job_id: &str) -> Option<&'static str> {
    for t in QUEUE_TABLES {
        let exists: i64 = conn
            .query_row(&format!("SELECT COUNT(*) FROM {t} WHERE job_id=?1"), rusqlite::params![job_id], |r| r.get(0))
            .unwrap_or(0);
        if exists > 0 {
            return Some(t);
        }
    }
    None
}

async fn queue_job_cancel(State(state): State<AppState>, Path(job_id): Path<String>) -> Json<Value> {
    queue_job_action(&state, &job_id,
        "UPDATE {t} SET status='cancelled', finished_at=?1 WHERE job_id=?2 AND status IN ('pending','running','retrying','waiting')",
        "任务已取消").await
}

async fn queue_job_retry(State(state): State<AppState>, Path(job_id): Path<String>) -> Json<Value> {
    queue_job_action(&state, &job_id,
        "UPDATE {t} SET status='retrying', retry_count=retry_count+1, error_message='', finished_at=NULL WHERE job_id=?2 AND status IN ('failed','cancelled')",
        "任务已重新入队").await
}

async fn queue_job_delete(State(state): State<AppState>, Path(job_id): Path<String>) -> Json<Value> {
    queue_job_action(&state, &job_id,
        "UPDATE {t} SET deleted_at=?1 WHERE job_id=?2", "任务已删除").await
}

/// 队列 job 通用动作：定位表 → 执行 UPDATE（?1=now, ?2=job_id）
async fn queue_job_action(state: &AppState, job_id: &str, sql_tpl: &str, ok_msg: &str) -> Json<Value> {
    let db = state.db.clone_pool();
    let jid = job_id.to_string();
    let tpl = sql_tpl.to_string();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<usize> {
        let conn = db.get()?;
        let table = find_job_table(&conn, &jid).ok_or_else(|| anyhow::anyhow!("任务不存在"))?;
        let sql = tpl.replace("{t}", table);
        Ok(conn.execute(&sql, rusqlite::params![crate::queue::now_str(), jid])?)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(_) => Json(json!({"success": true, "message": ok_msg})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 清空历史任务（软删除全部终态）
async fn queue_clear(State(state): State<AppState>) -> Json<Value> {
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<usize> {
        let conn = db.get()?;
        let now = crate::queue::now_str();
        let mut n = 0usize;
        for t in QUEUE_TABLES {
            n += conn.execute(
                &format!(
                    "UPDATE {t} SET deleted_at=?1
                     WHERE deleted_at IS NULL AND status IN ('completed','failed','cancelled')"
                ),
                rusqlite::params![now],
            )?;
        }
        Ok(n)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(n) => Json(json!({"success": true, "message": format!("已清除 {n} 条历史任务")})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

async fn queue_pause_all(State(state): State<AppState>) -> Json<Value> {
    set_pause(&state, &["queue_paused"], "1", "全部队列已暂停").await
}

async fn queue_resume_all(State(state): State<AppState>) -> Json<Value> {
    set_pause(&state, &["queue_paused"], "0", "全部队列已恢复").await
}

async fn queue_pause_one(State(state): State<AppState>, Path(queue): Path<String>) -> Json<Value> {
    let key = pause_key(&queue);
    set_pause(&state, &[key.as_str()], "1", "队列已暂停").await
}

async fn queue_resume_one(State(state): State<AppState>, Path(queue): Path<String>) -> Json<Value> {
    let key = pause_key(&queue);
    set_pause(&state, &[key.as_str()], "0", "队列已恢复").await
}

fn pause_key(queue: &str) -> String {
    format!("queue_paused_{queue}")
}

async fn set_pause(state: &AppState, keys: &[&str], value: &str, msg: &str) -> Json<Value> {
    for k in keys {
        if let Err(e) = crate::queue::config_set(&state.db, k, value).await {
            return Json(json!({"success": false, "message": e.to_string()}));
        }
    }
    Json(json!({"success": true, "message": msg}))
}

/// 并发数配置：?max_workers=N 或 ?auto=true（按机器规格推荐）
async fn queue_config(
    State(state): State<AppState>,
    Query(params): Query<std::collections::HashMap<String, String>>,
) -> Json<Value> {
    let specs = tokio::task::spawn_blocking(|| server_specs().clone())
        .await
        .unwrap_or(Value::Null);
    let current = crate::queue::config_get(&state.db, "queue_max_workers").await
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(default_max_workers());
    let auto = params.get("auto").map(|v| v == "true").unwrap_or(false);
    let value = if auto {
        specs["recommended_workers"].as_u64().unwrap_or(current as u64) as usize
    } else {
        match params.get("max_workers").and_then(|v| v.parse::<usize>().ok()) {
            Some(n) if n > 0 => n,
            _ => {
                return Json(json!({"success": false, "message": "max_workers 非法"}));
            }
        }
    };
    match crate::queue::config_set(&state.db, "queue_max_workers", &value.to_string()).await {
        Ok(()) => Json(json!({"success": true, "message": "并发数已更新", "data": {"max_workers": value}})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 机器规格检测（CPU/内存/推荐并发），结果进程内缓存（探测较重）
fn server_specs() -> &'static Value {
    static SPECS: std::sync::OnceLock<Value> = std::sync::OnceLock::new();
    SPECS.get_or_init(|| {
        let cpu = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4);
        let mem_gb = detect_memory_gb();
        // 推荐并发：任务全程是 I/O 等待（视频墙钟 + 平台请求），不占 CPU 时间片，
        // 所以不按核数 1:1 推，而是按核数的 4 倍（每个任务实际只在"醒来上报"的
        // 瞬间用一点 CPU）。内存仍按每 GB 允许 2 个任务兜底，取小值，夹在 1..=64。
        let by_cpu = cpu.max(1) * 4;
        let by_mem = if mem_gb > 0.0 { (mem_gb * 2.0) as usize } else { by_cpu };
        let recommended = by_cpu.min(by_mem).clamp(1, MAX_WORKERS_CEILING);
        json!({
            "cpu_count": cpu,
            "total_mem_gb": (mem_gb * 10.0).round() / 10.0,
            "recommended_workers": recommended,
        })
    })
}

/// 并发上限硬边界，与 queue::MAX_WORKERS_CEILING 保持一致
const MAX_WORKERS_CEILING: usize = 64;

/// 默认并发：CPU 核数 - 1（夹在 1..=64），与队列调度器启动默认一致。
/// Rust 任务全是 I/O 等待，上限远高于 Python 时代的 8 —— 提高的是"同时等
/// 多少个视频的墙钟"，不是"每秒打多少请求"（后者由全局闸门固定在 ≈2 req/s）。
fn default_max_workers() -> usize {
    std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4)
        .saturating_sub(1).max(1).clamp(1, MAX_WORKERS_CEILING)
}

#[cfg(target_os = "linux")]
fn detect_memory_gb() -> f64 {
    std::fs::read_to_string("/proc/meminfo")
        .ok()
        .and_then(|s| {
            s.lines().find(|l| l.starts_with("MemTotal:"))
                .and_then(|l| l.split_whitespace().nth(1))
                .and_then(|v| v.parse::<f64>().ok())
        })
        .map(|kb| kb / 1024.0 / 1024.0)
        .unwrap_or(0.0)
}

#[cfg(not(target_os = "linux"))]
fn detect_memory_gb() -> f64 {
    // Windows：CIM 查询物理内存（按需调用，结果已被 OnceLock 缓存）
    let out = std::process::Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command",
               "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"])
        .output();
    out.ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .and_then(|s| s.trim().parse::<f64>().ok())
        .map(|bytes| bytes / 1024.0 / 1024.0 / 1024.0)
        .unwrap_or(0.0)
}

async fn queue_detect(State(state): State<AppState>) -> Json<Value> {
    let mut data = tokio::task::spawn_blocking(|| server_specs().clone())
        .await
        .unwrap_or(Value::Null);
    let current = crate::queue::config_get(&state.db, "queue_max_workers").await
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(default_max_workers());
    data["current_workers"] = json!(current);
    Json(json!({"success": true, "message": "ok", "data": data}))
}



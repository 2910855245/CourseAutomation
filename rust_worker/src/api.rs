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
        // DeepSeek 连通性自检：会回吐 Key 前后各几位、且真实计费调用。
        // 它原先挂在 school_exam::router() 并随顶层 merge 出去，越过了本层的
        // 鉴权中间件 —— 匿名可打，等于把 API Key 与额度白送。必须留在鉴权组。
        .route("/api/admin/config/test-deepseek", post(crate::school_exam::test_deepseek))
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
        // 支付收款页其余管理接口（渠道账号 CRUD / 通道自检 / 配对二维码 /
        // 支付订单 / 测试支付 / 诊断 / 连接重置）——见 ypay_admin.rs。
        // 合并进 protected 分组，随附管理员 Bearer 鉴权。
        .merge(crate::ypay_admin::router())
        // 运行日志面板：列表 / 统计 / 清空（内存环形缓冲 + DB 持久层）
        .merge(crate::logs::router())
        // 域名监控：平台域名/名称的查看、立即检测、检测间隔（管理员可见）
        .merge(crate::domain::router())
        // 营销推广统计：必须带管理员鉴权（访客量/转化率/邀请码列表属经营数据）
        .route("/api/admin/promo/stats", get(crate::promo_routes::admin_promo_stats))
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
    if ok {
        // 记下最后一次心跳：后台「监控在线/离线」徽标与心跳时间读的就是它。
        // 不记的话徽标只能靠猜（此前恒显"监控离线"，等于骗操作者）。
        let _ = crate::queue::config_set(&state.db, "ypay_last_heart", &crate::queue::now_str()).await;
    }
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
async fn batch_orders(
    State(state): State<AppState>,
    ext: Option<Extension<crate::promo_routes::VisitorId>>,
    Json(body): Json<Value>,
) -> Json<Value> {
    let vid = ext.map(|e| e.0.as_str().to_string()).unwrap_or_default();
    // 免费待遇（全局免费开关或本人持有效刷课卡）：命中时订单 0 元并直接进队列
    let benefit = crate::promo::check_benefit(&state.db, &vid).await;
    match crate::order::create_batch_orders(&state.db, &body, &vid, benefit).await {
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
/// 公告附加项：标题 / 图片（URL 或 data URL）/ 联系方式（类型 + 值）
const ANN_TITLE: &str = "announcement_title";
const ANN_IMAGE: &str = "announcement_image";
const ANN_CONTACT_TYPE: &str = "announcement_contact_type";
const ANN_CONTACT_VALUE: &str = "announcement_contact_value";
/// 图片体积上限（data URL 直接存库，超过就会把库撑大）
const ANN_IMAGE_MAX: usize = 700 * 1024;

async fn announcement_get(State(state): State<AppState>) -> Json<Value> {
    let content = crate::queue::config_get(&state.db, ANN_CONTENT).await.unwrap_or_default();
    let id: i64 = crate::queue::config_get(&state.db, ANN_ID).await
        .and_then(|v| v.parse().ok()).unwrap_or(0);
    let active = crate::queue::config_get(&state.db, ANN_ACTIVE).await
        .map(|v| v == "1").unwrap_or(false) && !content.trim().is_empty();
    let title = crate::queue::config_get(&state.db, ANN_TITLE).await.unwrap_or_default();
    let image = crate::queue::config_get(&state.db, ANN_IMAGE).await.unwrap_or_default();
    let contact_type = crate::queue::config_get(&state.db, ANN_CONTACT_TYPE).await.unwrap_or_default();
    let contact_value = crate::queue::config_get(&state.db, ANN_CONTACT_VALUE).await.unwrap_or_default();
    let visible = |v: String| if active { v } else { String::new() };
    Json(json!({
        "success": true,
        "message": "ok",
        "data": {
            "id": id,
            "content": visible(content),
            "active": active,
            "title": visible(title),
            "image": visible(image),
            "contact_type": visible(contact_type),
            "contact_value": visible(contact_value),
        },
    }))
}

async fn announcement_publish(State(state): State<AppState>, Json(body): Json<Value>) -> Json<Value> {
    let content = body["content"].as_str().unwrap_or("").trim().to_string();
    if content.is_empty() {
        return Json(json!({"success": false, "message": "公告内容不能为空"}));
    }
    let title = body["title"].as_str().unwrap_or("").trim().chars().take(60).collect::<String>();
    let image = body["image"].as_str().unwrap_or("").trim().to_string();
    if image.len() > ANN_IMAGE_MAX {
        return Json(json!({"success": false, "message": "图片过大（请压缩到 700KB 以内）"}));
    }
    // 只接受 http(s) 图片或 data:image，避免把 javascript:/file: 之类写进前端 <img>
    if !image.is_empty()
        && !(image.starts_with("http://") || image.starts_with("https://")
             || image.starts_with("data:image/"))
    {
        return Json(json!({"success": false, "message": "图片地址不合法（需 http(s) 或上传图片）"}));
    }
    let contact_type = body["contact_type"].as_str().unwrap_or("").trim()
        .chars().take(16).collect::<String>();
    let contact_value = body["contact_value"].as_str().unwrap_or("").trim()
        .chars().take(120).collect::<String>();
    // 严格递增的 id（同一秒内连续发布也不会撞号）
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs() as i64).unwrap_or(0);
    let prev: i64 = crate::queue::config_get(&state.db, ANN_ID).await
        .and_then(|v| v.parse().ok()).unwrap_or(0);
    let id = now.max(prev + 1);
    let fields = [
        (ANN_CONTENT, content.as_str()),
        (ANN_TITLE, title.as_str()),
        (ANN_IMAGE, image.as_str()),
        (ANN_CONTACT_TYPE, contact_type.as_str()),
        (ANN_CONTACT_VALUE, contact_value.as_str()),
        (ANN_ACTIVE, "1"),
    ];
    for (k, v) in fields {
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
        // 心跳：vmq_heart 成功时写入 ypay_last_heart（超过 120s 视为离线）
        let last_heart: String = conn
            .query_row("SELECT COALESCE(config_value,'') FROM system_config WHERE config_key='ypay_last_heart'",
                       [], |r| r.get(0)).unwrap_or_default();
        let seconds_ago: i64 = crate::pay::parse_iso_secs(&last_heart)
            .map(|t| (crate::queue::local_secs() as i64 - t).max(0))
            .unwrap_or(-1);
        Ok(json!({
            "key_set": key_set,
            "orders_total": count("SELECT COUNT(*) FROM ypay_order WHERE deleted_at IS NULL"),
            "orders_paid": count("SELECT COUNT(*) FROM ypay_order WHERE deleted_at IS NULL AND status=1"),
            "last_order_at": conn
                .query_row("SELECT COALESCE(MAX(create_time),'') FROM ypay_order", [], |r| r.get::<_, String>(0))
                .unwrap_or_default(),
            "monitor_last_heart": last_heart,
            "seconds_ago": seconds_ago,
            "is_online": seconds_ago >= 0 && seconds_ago < 120,
            "monitor_status": if !key_set { "key_missing" } else if seconds_ago >= 0 && seconds_ago < 120 { "online" } else { "offline" },
            "online_accounts": count("SELECT COUNT(*) FROM ypay_account WHERE deleted_at IS NULL AND status=1"),
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

/// orders 表在 API 层的列清单。**顺序即 [`order_row_to_json`] 的位置索引**。
///
/// 此前这段列清单在 5 处各拷一份（列表/单条/管理端分页…），加一列时漏改任何一处，
/// 该接口的字段就会静默错位（上一轮 `vid` 漏选就是这么来的）。收敛成唯一真源。
const ORDER_SELECT: &str = "order_id, out_trade_no, ezfpy_trade_no, payment_channel, payment_time,
        paid_processed, user_id, customer_name, customer_contact, username,
        website_id, task_type, course_ids, video_count, exam_count, price,
        notes, status, paid, task_id, admin_note, created_at, updated_at,
        accepted_at, started_at, finished_at, speed_mode";

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
    let mut latest: std::collections::HashMap<String, (f64, String)> = std::collections::HashMap::new();
    // school 先查：or_insert 保证 school 的记录不被 chaoxing 覆盖（学校优先）
    for table in ["queue_jobs_school", "queue_jobs_chaoxing"] {
        for chunk in ids.chunks(CHUNK) {
            let placeholders = std::iter::repeat_n("?", chunk.len())
                .collect::<Vec<_>>()
                .join(",");
            let sql = format!(
                "SELECT order_id, status, progress, current_step_name FROM {table}
                 WHERE order_id IN ({placeholders})
                 ORDER BY created_at DESC"
            );
            let mut stmt = conn.prepare(&sql)?;
            let rows = stmt.query_map(
                rusqlite::params_from_iter(chunk.iter().map(|s| s.as_str())),
                |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?, r.get::<_, f64>(2)?,
                        r.get::<_, Option<String>>(3)?.unwrap_or_default())),
            )?;
            for row in rows {
                let (order_id, status, progress, step) = row?;
                // 已按 created_at DESC 排序：首次出现即该表最新一条
                latest.entry(order_id)
                    .or_insert((if status == "completed" { 100.0 } else { progress }, step));
            }
        }
    }
    for item in items.iter_mut() {
        let order_id = item["order_id"].as_str().unwrap_or("");
        let (progress, step) = latest.get(order_id).cloned().unwrap_or((0.0, String::new()));
        item["progress"] = json!(progress);
        // 当前步骤：订单页用它显示"正在做什么"（此前只回进度数字，用户看不到进展细节）
        item["current_step_name"] = json!(step);
    }
    Ok(())
}


async fn orders_list(
    State(state): State<AppState>,
    Query(params): Query<std::collections::HashMap<String, String>>,
) -> Json<Value> {
    // 钳到 1..=200：limit=0 会让下面的 total_pages 整除零 panic，
    // 负数在 SQLite 里是 LIMIT -1（返回全表），都不该由调用方决定
    let limit = params.get("limit").and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(50).clamp(1, 200);
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
                let mut stmt = conn.prepare(&format!(
                    "SELECT {ORDER_SELECT}
                     FROM orders WHERE status=?1 AND deleted_at IS NULL
                     ORDER BY created_at DESC LIMIT ?2"))?;
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
                let mut stmt = conn.prepare(&format!(
                    "SELECT {ORDER_SELECT}
                     FROM orders WHERE deleted_at IS NULL
                     ORDER BY created_at DESC LIMIT ?1"))?;
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
            &format!("SELECT {ORDER_SELECT}
             FROM orders WHERE order_id=?1 AND deleted_at IS NULL"),
            rusqlite::params![order_id],
            |r| {
                let cids: String = r.get(12)?;
                order_row_to_json(r, &cids)
            },
        );
        match row {
            // 单条查单同样注入队列进度：订单页是按订单号单查的（没有按用户列单的接口），
            // 不注入的话客户永远看不到进度百分比，进度条恒为 0。
            Ok(mut v) => {
                let mut one = [v];
                inject_progress(&conn, &mut one);
                v = one.into_iter().next().unwrap_or(json!({}));
                Ok(Some(v))
            }
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
/// 口径（与订单列表、队列监控保持一致，同屏数字必须能互相对上）：
///   - 时间按本地（北京时间）日期前缀；收入只算已收款且未取消的订单，
///     未收款与"已收款但已取消（待退款）"各自单列。
///   - 完成率分母为终态订单，避免被刚下单还没跑的单稀释。
async fn admin_dashboard(State(state): State<AppState>) -> Json<Value> {
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Value> {
        let conn = db.get()?;
        let now = crate::queue::local_secs();
        let today_prefix = day_label(now).1;               // YYYY-MM-DD
        let today_like = format!("{today_prefix}%");
        let yest_like = format!("{}%", day_label(now - 86400).1);
        let week_from = day_label(now - 6 * 86400).1;       // 近 7 天（含今日）
        // 卡单判定阈值：排队/待处理超 2 小时、执行中超 6 小时。
        // 用 updated_at（最后一次状态变化）而非 created_at：老订单重新入队后
        // created_at 仍是很多天前，会把刚排上的单误报成"长时间未推进"。
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
                                           AND COALESCE(updated_at, created_at) < ?4 THEN 1 ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN status='running'
                                           AND COALESCE(updated_at, created_at) < ?5 THEN 1 ELSE 0 END), 0),
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

        // 近 7 天趋势：一次分组查询取回订单/收入/失败
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
        let free_max_workers = crate::queue::config_get_blocking(&conn, crate::queue::CFG_FREE_MAX_WORKERS)
            .and_then(|v| v.parse::<i64>().ok())
            .unwrap_or_else(|| default_free_max_workers() as i64);
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
                // 双通道分开报：分子必须配本通道的分母，免费在跑数算进付费额度会虚高
                "paid": {
                    "active_workers": crate::queue::active_workers_in(crate::queue::Lane::Paid),
                    "max_workers": max_workers,
                },
                "free": {
                    "active_workers": crate::queue::active_workers_in(crate::queue::Lane::Free),
                    "max_workers": free_max_workers,
                },
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
    // 免费通道额度（与调度器读同一个键，监控显示的才是真实生效值）
    let free_max_workers = crate::queue::config_get(&state.db, crate::queue::CFG_FREE_MAX_WORKERS).await
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or_else(|| default_free_max_workers() as i64);
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
        let table_stats = |table: &str, lane: Option<&str>| -> rusqlite::Result<Map<String, Value>> {
            let mut m = Map::new();
            for st in ["pending", "running", "waiting", "completed", "failed"] {
                let c: i64 = match lane {
                    Some(l) => conn.query_row(
                        &format!("SELECT COUNT(*) FROM {table} WHERE status=?1 AND deleted_at IS NULL AND lane=?2"),
                        rusqlite::params![st, l], |r| r.get(0))?,
                    None => conn.query_row(
                        &format!("SELECT COUNT(*) FROM {table} WHERE status=?1 AND deleted_at IS NULL"),
                        rusqlite::params![st], |r| r.get(0))?,
                };
                m.insert(st.to_string(), json!(c));
            }
            let total: i64 = match lane {
                Some(l) => conn.query_row(
                    &format!("SELECT COUNT(*) FROM {table} WHERE deleted_at IS NULL AND lane=?1"),
                    rusqlite::params![l], |r| r.get(0))?,
                None => conn.query_row(
                    &format!("SELECT COUNT(*) FROM {table} WHERE deleted_at IS NULL"),
                    [], |r| r.get(0))?,
            };
            m.insert("total".into(), json!(total));
            Ok(m)
        };
        let active_paid = crate::queue::active_workers_in(crate::queue::Lane::Paid) as i64;
        let active_free = crate::queue::active_workers_in(crate::queue::Lane::Free) as i64;
        let active = active_paid + active_free;
        // 学习通队列有自己的调度循环，在跑数必须分队列读 —— 此前全部记在学校头上
        let cx_paid = crate::queue::active_workers_in_kind(
            crate::queue::QueueKind::Chaoxing, crate::queue::Lane::Paid) as i64;
        let cx_free = crate::queue::active_workers_in_kind(
            crate::queue::QueueKind::Chaoxing, crate::queue::Lane::Free) as i64;
        let cx_active = cx_paid + cx_free;
        let mut school = table_stats("queue_jobs_school", None)?;
        let mut chaoxing = table_stats("queue_jobs_chaoxing", None)?;
        school.insert("active_workers".into(), json!(active));
        school.insert("max_workers".into(), json!(max_workers));
        school.insert("active_study_workers".into(), json!(active));
        school.insert("max_study_workers".into(), json!(max_workers));
        school.insert("paused".into(), json!(paused_school));
        school.insert("queue_name".into(), json!("school"));
        // 两条通道各自的积压/在跑/额度：付费单会不会被免费积压拖住，看这里
        let mut paid_lane = table_stats("queue_jobs_school", Some("paid"))?;
        paid_lane.insert("active_workers".into(), json!(active_paid));
        paid_lane.insert("max_workers".into(), json!(max_workers));
        let mut free_lane = table_stats("queue_jobs_school", Some("free"))?;
        free_lane.insert("active_workers".into(), json!(active_free));
        free_lane.insert("max_workers".into(), json!(free_max_workers));
        school.insert("paid".into(), json!(paid_lane));
        school.insert("free".into(), json!(free_lane));
        chaoxing.insert("active_workers".into(), json!(cx_active));
        chaoxing.insert("max_workers".into(), json!(max_workers));
        chaoxing.insert("active_study_workers".into(), json!(cx_active));
        chaoxing.insert("max_study_workers".into(), json!(max_workers));
        chaoxing.insert("paused".into(), json!(paused_cx));
        chaoxing.insert("queue_name".into(), json!("chaoxing"));
        // 学习通也分付费/免费两条通道（与学校同一套额度键、独立计数）
        let mut cx_paid_lane = table_stats("queue_jobs_chaoxing", Some("paid"))?;
        cx_paid_lane.insert("active_workers".into(), json!(cx_paid));
        cx_paid_lane.insert("max_workers".into(), json!(max_workers));
        let mut cx_free_lane = table_stats("queue_jobs_chaoxing", Some("free"))?;
        cx_free_lane.insert("active_workers".into(), json!(cx_free));
        cx_free_lane.insert("max_workers".into(), json!(free_max_workers));
        chaoxing.insert("paid".into(), json!(cx_paid_lane));
        chaoxing.insert("free".into(), json!(cx_free_lane));

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

/// 收费标准键：前端 camelCase ↔ 库内 snake_case（对齐 useSystemConfig.loadPricing）。
/// 视频打包价（小/中/大课）与进度折扣已随"刷视频免费"下线，只剩真正在收钱的三档。
const PRICING_KEYS: &[(&str, &str, f64)] = &[
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
    // 试算与下单必须同源：只要带了 username，就一律用服务端扫描快照里的事实，
    // 覆盖客户端回传的明细。否则试算按客户端数据、下单按服务端数据，两边价不一致，
    // 更糟的是给"伪造明细"的客户端显示 0 元（虽然下单会被拒，但界面在骗人）。
    let username = body["username"].as_str().unwrap_or("").trim().to_string();
    let courses = if username.is_empty() || courses.is_empty() {
        courses // 老调用方没带身份：退回客户端数据（仅试算展示，不参与下单）
    } else {
        let mut resolved: Vec<Value> = Vec::with_capacity(courses.len());
        for c in &courses {
            let cid = c["course_id"].as_str().unwrap_or("").trim().to_string();
            if cid.is_empty() {
                continue;
            }
            let wid = c["website_id"].as_i64().unwrap_or(0);
            // 学习通一口价，不需要课程明细事实（也没有对应快照）→ 原样透传
            if wid == 4 {
                resolved.push(c.clone());
                continue;
            }
            let facts = if wid > 0 {
                crate::scan_snapshot::resolve(&username, wid, &[cid.clone()])
            } else {
                crate::scan_snapshot::resolve_any_school_platform(&username, &[cid.clone()])
            };
            match facts {
                Ok(f) if !f.is_empty() => resolved.push(f[0].clone()),
                // 快照缺失：与下单同一口径做**保守试算**（按一门课收考试费），
                // 而不是报错或按客户端明细显示 0 元 —— 试算价必须与实收价一致
                _ => resolved.push(json!({
                    "course_id": cid,
                    "video_total": 0, "video_completed": 0,
                    "exam_total": 1, "exam_done": 0,
                    "homework_total": 0, "homework_done": 0,
                })),
            }
        }
        resolved
    };
    let (entries, total) = crate::order::price_courses(&cfg, &courses);
    Json(json!({
        "success": true,
        "message": "ok",
        // chaoxing_price 一并回给前端：学习通是整批一口价、不跟着课程明细算，
        // 而 /api/pricing（配置读取）是管理员接口、客户页拿不到 ——
        // 不在这里带上，客户页就只能显示硬编码的默认价，后台改价永远不生效。
        "data": {"courses": entries, "total": total, "pricing_mode": "package",
                 "chaoxing_price": cfg["price_chaoxing"].as_f64().unwrap_or(8.0)},
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
        &format!("SELECT {ORDER_SELECT}
         FROM orders WHERE order_id=?1 AND deleted_at IS NULL"),
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
            "SELECT {ORDER_SELECT}
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
        // 通道/优先级与支付入队走同一张判定表：管理员手动补入队时若写死 0，
        // 免费单会落进付费池抢额度，两条通道的隔离就形同虚设
        let (lane, priority) =
            crate::queue::lane_and_priority(order["paid_processed"].as_str().unwrap_or(""));
        // 路由与支付入队同一条规则：学习通（website_id=4）进学习通队列
        let website_id = order["website_id"].as_i64().unwrap_or(1);
        let table = if website_id == 4 { "queue_jobs_chaoxing" } else { "queue_jobs_school" };
        // 去重：已有活跃任务（pending/running/retrying）就不再投一份。
        // 此前这里是无条件 INSERT，后台「入队」连点两下就造出两条同订单任务
        // （线上实测 ORD-874EAB18 / ORD-4CA1A735 各有一份多余任务，均来自
        // 2026-10-01 12:59 的手动入队），同账号两个任务并行会让平台重叠检测
        // 越线（安全线 ≤8）并互踢会话。已终态（完成/失败）的单不受影响 ——
        // 故意补刷仍然可以入队。
        let active: Option<String> = conn
            .query_row(
                &format!(
                    "SELECT job_id FROM {table}
                     WHERE order_id=?1 AND deleted_at IS NULL
                       AND status IN ('pending','running','retrying') LIMIT 1"
                ),
                rusqlite::params![oid],
                |r| r.get(0),
            )
            .ok();
        if active.is_some() {
            anyhow::bail!("该订单已有进行中的任务，无需重复入队");
        }
        conn.execute(
            &format!(
            "INSERT INTO {table}
             (job_id, username, password, website_id, job_type, course_ids, status, priority, lane,
              progress, total_steps, completed_steps, current_step_name, error_message,
              retry_count, max_retries, task_id, order_id, result_data, verified,
              created_at, started_at, finished_at, deleted_at, speed_mode)
             VALUES (?1,?2,?3,?4,?5,?6,'pending',?7,?8,0,0,0,'','',0,3,NULL,?9,'{{}}',0,?10,NULL,NULL,NULL,?11)"
            ),
            rusqlite::params![
                job_id, username, password,
                order["website_id"].as_i64().unwrap_or(1),
                order["task_type"].as_str().unwrap_or("video"),
                serde_json::to_string(&order["course_ids"])?,
                priority, lane.as_str(), oid, crate::queue::now_str(),
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
    let task_type = order["task_type"].as_str().unwrap_or("video").to_string();
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
    // 手动执行必须自己回写订单终态：这条路径不经过队列（queue::sync_order_state），
    // 此前只在 tracing 里记一笔，订单会永久停在 running，顾客看到"永远执行中"。
    let state2 = state.clone();
    let handle = tokio::spawn(async move {
        // 学习通订单走学习通链路：登录协议（AES 表单）与上报协议都与学校完全不同，
        // 用学校路径去打 mooc1 只会失败并白刷平台错误次数
        if website_id == 4 {
            let session = match crate::cx_login::login(&username, &password).await {
                Ok(s) => s,
                Err(e) => {
                    tracing::warn!(order_id = %oid_task, error = %e, "手动执行：学习通登录失败");
                    finish_manual_run(&state2, &oid_task, false, &format!("学习通登录失败: {e}")).await;
                    tasks.remove(&oid_task);
                    return;
                }
            };
            let task = crate::cx_scan::ScanCxTaskInput {
                order_id: oid_task.clone(),
                cookie_str: session.cookie_str.clone(),
                uid: session.uid.clone(),
                fid: session.fid.clone(),
                ua: String::new(),
                course_ids,
                status_file: None,
                push_ws: true,
            };
            let result = crate::cx_scan::run_cx_scan_and_study(&task, &push_url, &push_token).await;
            match &result {
                Ok(()) => finish_manual_run(&state2, &oid_task, true, "").await,
                Err(e) => finish_manual_run(&state2, &oid_task, false, &e.to_string()).await,
            }
            if let Err(e) = result {
                tracing::warn!(order_id = %oid_task, error = %e, "手动执行：学习通任务失败");
            }
            tasks.remove(&oid_task);
            return;
        }
        let base_url = crate::scan::platform_base_url(website_id);
        let session = match crate::session::get_session(&base_url, &username, &password).await {
            Ok(s) => s,
            Err(e) => {
                tracing::warn!(order_id = %oid_task, error = %e, "手动执行：登录失败");
                finish_manual_run(&state2, &oid_task, false, &format!("登录失败: {e}")).await;
                tasks.remove(&oid_task);
                return;
            }
        };
        // 手动执行也要能跑考试环节：与队列路径同一套取配置方式
        let api_key = crate::llm::effective_api_key(&state2.db).await;
        let ai_model = crate::llm::configured_model(&state2.db, "deepseek_model",
                                                    crate::llm::MODEL_FLASH).await;
        let exam_enabled = crate::queue::config_get(&state2.db, "exam_solve_enabled").await
            .map(|v| v != "0").unwrap_or(true);
        let task = crate::scan::ScanTaskInput {
            order_id: oid_task.clone(),
            username,
            password,
            base_url,
            cookie_str: session.cookie_str,
            course_ids,
            push_ws: true,
            speed_mode,
            task_type,
            api_key,
            ai_model,
            exam_enabled,
        };
        let result = crate::scan::run_scan_and_study(&task, &push_url, &push_token).await;
        match &result {
            Ok(()) => finish_manual_run(&state2, &oid_task, true, "").await,
            Err(e) => finish_manual_run(&state2, &oid_task, false, &e.to_string()).await,
        }
        if let Err(e) = result {
            tracing::warn!(order_id = %oid_task, error = %e, "手动执行任务失败");
        }
        tasks.remove(&oid_task);
    });
    // 只登记仍在跑的任务：任务若在 insert 前就结束（如登录秒失败），任务内
    // tasks.remove 先跑成空操作，随后无条件 insert 会塞进一条僵尸句柄，
    // 该订单从此每次手动执行都被判「已在执行中」。与队列路径同护栏。
    if !handle.is_finished() {
        state.tasks.insert(oid_resp.clone(), handle.abort_handle());
    }
    Json(json!({"success": true, "message": "订单执行中", "data": {"order_id": oid_resp}}))
}

/// 手动执行的收尾：写订单终态 + 广播（与队列路径同一套语义，避免两处口径漂移）。
/// 只在订单仍处于流转中状态时改写，管理员已人工推进的单不覆盖。
async fn finish_manual_run(state: &AppState, order_id: &str, ok: bool, note: &str) {
    let pool = state.db.clone_pool();
    let oid = order_id.to_string();
    let note = note.to_string();
    let status = if ok { "completed" } else { "failed" };
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<usize> {
        let conn = pool.get()?;
        let now = crate::queue::now_str();
        let n = conn.execute(
            "UPDATE orders SET status=?1, admin_note=?2, finished_at=?3, updated_at=?3
             WHERE order_id=?4 AND deleted_at IS NULL
               AND status IN ('pending','accepted','queued','running','paid','waiting')",
            rusqlite::params![status, note, now, oid],
        )?;
        Ok(n)
    })
    .await;
    match result {
        Ok(Ok(0)) => {}
        Ok(Ok(_)) => {
            crate::progress::broadcast(state, &format!("order:{order_id}"), "order.update",
                                      json!({"order_id": order_id, "status": status}));
        }
        Ok(Err(e)) => tracing::warn!(order_id, error = %e, "手动执行回写订单状态失败"),
        Err(e) => tracing::warn!(order_id, error = %e, "手动执行回写订单状态失败（spawn_blocking 异常）"),
    }
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
                        started_at, finished_at, lane, priority
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
                    "lane": r.get::<_, Option<String>>(13)?.unwrap_or_else(|| "paid".into()),
                    "priority": r.get::<_, i64>(14).unwrap_or(0),
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

/// 真正停掉在跑的任务，返回它的 order_id。
///
/// 只改库状态是不够的：任务协程会照旧跑完，并在完成时把状态覆盖回 completed
/// —— 管理员看到的是"取消成功但任务又跑起来了"。
async fn abort_running_job(state: &AppState, job_id: &str) -> String {
    let db = state.db.clone_pool();
    let jid = job_id.to_string();
    let order_id = tokio::task::spawn_blocking(move || -> Option<String> {
        let conn = db.get().ok()?;
        let table = find_job_table(&conn, &jid)?;
        conn.query_row(
            &format!("SELECT order_id FROM {table} WHERE job_id=?1"),
            rusqlite::params![jid], |r| r.get::<_, Option<String>>(0),
        ).ok().flatten()
    })
    .await
    .ok()
    .flatten()
    .unwrap_or_default();
    if !order_id.is_empty() {
        if let Some((_, abort)) = state.tasks.remove(&order_id) {
            abort.abort();
            tracing::info!(job_id = %job_id, order_id = %order_id, "已中止运行中的刷课任务");
        }
    }
    order_id
}

async fn queue_job_cancel(State(state): State<AppState>, Path(job_id): Path<String>) -> Json<Value> {
    abort_running_job(&state, &job_id).await;
    queue_job_action(&state, &job_id,
        "UPDATE {t} SET status='cancelled', finished_at=?1 WHERE job_id=?2 AND status IN ('pending','running','retrying','waiting')",
        "任务已取消", true).await
}

async fn queue_job_retry(State(state): State<AppState>, Path(job_id): Path<String>) -> Json<Value> {
    queue_job_action(&state, &job_id,
        "UPDATE {t} SET status='retrying', retry_count=retry_count+1, error_message='', finished_at=NULL WHERE job_id=?2 AND status IN ('failed','cancelled')",
        "任务已重新入队", false).await
}

async fn queue_job_delete(State(state): State<AppState>, Path(job_id): Path<String>) -> Json<Value> {
    // 删除也必须真的停掉在跑的协程：否则它跑完会把状态覆盖回 completed，
    // 于是"删掉的任务"又出现在列表里（line 上实测过这种反复）。
    abort_running_job(&state, &job_id).await;
    queue_job_action(&state, &job_id,
        "UPDATE {t} SET deleted_at=?1 WHERE job_id=?2", "任务已删除", true).await
}

/// 队列 job 通用动作：定位表 → 执行 UPDATE（?1=now, ?2=job_id）
///
/// `close_order`：任务从"进行中"被停掉时，把订单也收尾（置 cancelled）。
/// 为什么必须有：订单只要停在 running 就永远出不来 ——
///   - 订单页一直显示"处理中"、进度不动；
///   - `/api/orders/active-courses` 把它算作进行中，客户再扫也选不了这批课；
///   - 补投扫描 `find_orders_paid_without_job_sync` 的 NOT EXISTS 不滤 deleted_at，
///     有任务行（哪怕已删）就不再补投 → 既不会跑，也不会自愈。
/// 于是"删了任务"反而把客户卡死。这里让删除/取消的语义变成"这单不要了"。
async fn queue_job_action(state: &AppState, job_id: &str, sql_tpl: &str, ok_msg: &str,
                          close_order: bool) -> Json<Value> {
    let db = state.db.clone_pool();
    let jid = job_id.to_string();
    let tpl = sql_tpl.to_string();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<usize> {
        let conn = db.get()?;
        let table = find_job_table(&conn, &jid).ok_or_else(|| anyhow::anyhow!("任务不存在"))?;
        // 先读动作前的状态：取消会把状态改成 cancelled，改完就分不清"本来是不是在跑"
        let (order_id, prev): (String, String) = conn
            .query_row(
                &format!("SELECT COALESCE(order_id,''), COALESCE(status,'') FROM {table} WHERE job_id=?1"),
                rusqlite::params![jid],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .unwrap_or_default();
        let sql = tpl.replace("{t}", table);
        let now = crate::queue::now_str();
        let n = conn.execute(&sql, rusqlite::params![now, jid])?;
        let was_active = matches!(prev.as_str(), "pending" | "running" | "retrying" | "waiting");
        if n > 0 && close_order && was_active && !order_id.is_empty() {
            conn.execute(
                "UPDATE orders SET status='cancelled', finished_at=?1, updated_at=?1,
                        admin_note=CASE WHEN COALESCE(admin_note,'')=''
                                        THEN '任务被后台取消/删除，订单一并收尾'
                                        ELSE admin_note END
                 WHERE order_id=?2 AND deleted_at IS NULL
                   AND status NOT IN ('completed','failed','cancelled')",
                rusqlite::params![now, order_id],
            )?;
            log_event(&conn, "order_cancelled", "admin", "任务取消/删除，订单已一并收尾", &order_id)?;
        }
        Ok(n)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        // 影响 0 行说明状态不匹配（如已完成的单不能再取消）：
        // 以前这种情况也返回 success，等于把"什么都没做"报成成功
        Ok(0) => Json(json!({"success": false, "message": "任务当前状态不允许该操作，请刷新后重试"})),
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

/// 并发数配置：?max_workers=N（付费通道）/ ?free_max_workers=N（免费通道）/ ?auto=true
///
/// 两条通道额度独立配置，写进同一个配置表，调度器 5s 内热加载生效
/// （见 queue::read_runtime_config）。auto 会把两条通道**一起**写成推荐值
/// （算法见 [`recommend_workers`]）—— 旧版 auto 只写付费通道，免费通道
/// 永远停在默认值，"智能检测"点完只动了一半。
async fn queue_config(
    State(state): State<AppState>,
    Query(params): Query<std::collections::HashMap<String, String>>,
) -> Json<Value> {
    if let Some(raw) = params.get("free_max_workers") {
        let n = match raw.parse::<usize>() {
            Ok(n) if n > 0 => n.clamp(1, MAX_FREE_WORKERS_CEILING),
            _ => return Json(json!({"success": false, "message": "free_max_workers 非法"})),
        };
        return match crate::queue::config_set(&state.db, crate::queue::CFG_FREE_MAX_WORKERS, &n.to_string()).await {
            Ok(()) => Json(json!({"success": true, "message": "免费通道并发已更新", "data": {"free_max_workers": n}})),
            Err(e) => Json(json!({"success": false, "message": e.to_string()})),
        };
    }
    if params.get("auto").map(|v| v == "true").unwrap_or(false) {
        let specs = tokio::task::spawn_blocking(server_specs).await.unwrap_or(Value::Null);
        // 探测失败（极不可能）时退回当前值，绝不把配置写坏
        let current = crate::queue::config_get(&state.db, "queue_max_workers").await
            .and_then(|v| v.parse::<usize>().ok())
            .unwrap_or_else(default_max_workers);
        let current_free = crate::queue::config_get(&state.db, crate::queue::CFG_FREE_MAX_WORKERS).await
            .and_then(|v| v.parse::<usize>().ok())
            .unwrap_or_else(default_free_max_workers);
        let paid = specs["recommended_workers"].as_u64().map(|v| v as usize).unwrap_or(current);
        let free = specs["recommended_free_workers"].as_u64().map(|v| v as usize).unwrap_or(current_free);
        for (key, val) in [("queue_max_workers", paid), (crate::queue::CFG_FREE_MAX_WORKERS, free)] {
            if let Err(e) = crate::queue::config_set(&state.db, key, &val.to_string()).await {
                return Json(json!({"success": false, "message": e.to_string()}));
            }
        }
        return Json(json!({
            "success": true,
            "message": format!("已应用推荐并发：付费 {paid} / 免费 {free}"),
            "data": {"max_workers": paid, "free_max_workers": free},
        }));
    }
    let value = match params.get("max_workers").and_then(|v| v.parse::<usize>().ok()) {
        Some(n) if n > 0 => n,
        _ => {
            return Json(json!({"success": false, "message": "max_workers 非法"}));
        }
    };
    match crate::queue::config_set(&state.db, "queue_max_workers", &value.to_string()).await {
        Ok(()) => Json(json!({"success": true, "message": "并发数已更新", "data": {"max_workers": value}})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 每任务内存预算（MB）。实测：rust_worker 整进程含 5 个在跑任务仅约 105MB
/// （≈21MB/任务），这里按 2 倍余量取 48MB —— 刷课任务全程是 I/O 等待，
/// 内存大头（HTML 解析缓冲、cookie jar、会话状态）都是短生命周期的小对象。
const PER_TASK_MEM_MB: usize = 48;

/// 为同机其他项目（faceswap / MySQL / RabbitMQ / nginx）与系统预留的内存（MB）。
/// 这台机器不是独占跑本服务：并发预算必须按"可用内存 − 预留"计算，
/// 否则会把邻居的余量也算进自己的额度，负载一上来大家互相 OOM。
const OTHER_SERVICES_RESERVE_MB: usize = 1024;

/// 由（CPU 核数、内存预算 MB、平台会话闸）推导推荐并发。纯函数便于单测。
///
/// 三个上界取小，谁最小谁说了算：
///   - CPU 上界 = 核数 × 4：任务全程 I/O 等待（视频墙钟 + 平台请求都在 0.5s
///     全局闸门后面排队），真正烧 CPU 的只有"醒来上报"的瞬间。
///   - 内存上界 = 预算 / 每任务预算：Rust 侧任务开销极小，8 核机器上它根本
///     不是瓶颈（可用 6GB → 100+ 任务），只在内存紧的小机器上生效。
///   - 会话闸 = study::GLOBAL_STUDY_SESSIONS（默认 32）：进程内同时视频会话数。
///     池里的任务都可能进入视频阶段（免费单 1 会话/任务，付费 turbo 单最多 8），
///     池 > 闸只会产出"做完登录+扫描后排队等会话"的空转任务，两条通道都不越过它。
///
/// `budget_mb` 是调用方算好的**有效内存预算**（主机可用 − 邻居预留，再与
/// cgroup 硬顶余量取 min），本函数不做环境探测。
fn recommend_workers(cpu: usize, budget_mb: usize, gate: usize) -> usize {
    let by_cpu = cpu.max(1) * 4;
    let by_mem = (budget_mb / PER_TASK_MEM_MB).max(1);
    by_cpu.min(by_mem).min(gate.max(1)).clamp(1, MAX_WORKERS_CEILING)
}

/// 服务自身 cgroup 的内存硬顶余量（MB）。
///
/// 本服务被 systemd cgroup 管着（线上 drop-in：MemoryMax=3G / MemoryHigh=1G）：
/// 主机 MemAvailable 再充裕，进程越过 cgroup 硬顶照样被 OOM-kill —— 它是比
/// "主机可用"更小的盘子，推荐并发必须服从。路径从 /proc/self/cgroup 动态解析
/// （v1/v2 都兼容）：硬编码服务名换个部署就静默失效。
/// 读不到（无 cgroup / 无限制）返回 None → 退化为纯主机口径。
#[cfg(target_os = "linux")]
fn cgroup_mem_headroom_mb() -> Option<usize> {
    // /proc/self/cgroup 行格式 "id:controllers:path"（v2 的 controllers 为空）
    let rel = std::fs::read_to_string("/proc/self/cgroup").ok()?
        .lines()
        .find_map(|l| {
            let mut it = l.split(':');
            let _id = it.next()?;
            let ctrl = it.next()?;
            let path = it.next()?.trim().to_string();
            if ctrl.is_empty() || ctrl.split(',').any(|c| c == "memory") { Some(path) } else { None }
        })?;
    // v2：memory.max / memory.current；v1：memory.limit_in_bytes / memory.usage_in_bytes
    let (limit_raw, usage_raw) =
        if let Ok(l) = std::fs::read_to_string(format!("/sys/fs/cgroup{rel}/memory.max")) {
            (l, std::fs::read_to_string(format!("/sys/fs/cgroup{rel}/memory.current")).unwrap_or_default())
        } else {
            (std::fs::read_to_string(format!("/sys/fs/cgroup/memory{rel}/memory.limit_in_bytes")).ok()?,
             std::fs::read_to_string(format!("/sys/fs/cgroup/memory{rel}/memory.usage_in_bytes")).unwrap_or_default())
        };
    let limit: u64 = limit_raw.trim().parse().ok()?;
    // v2 写 "max"、v1 写超大哨兵值（≈u64::MAX 页对齐）都表示"无限制"
    if limit > (1u64 << 50) { return None; }
    let used: u64 = usage_raw.trim().parse().unwrap_or(0);
    Some((limit.saturating_sub(used) / 1024 / 1024) as usize)
}

#[cfg(not(target_os = "linux"))]
fn cgroup_mem_headroom_mb() -> Option<usize> {
    None // 本地开发（非 Linux）没有 cgroup 口径
}

/// 机器规格与推荐并发（每次实时探测）。
///
/// **不再缓存**：旧实现用 OnceLock 把首次探测结果钉死在进程生命周期里，
/// 而"可用内存"是动态值 —— 启动时若内存紧张（邻居项目正在跑），算出的低值
/// 会一直显示到下次重启，这正是"检测不准"的来源之一。读 /proc/meminfo 只有
/// 几微秒，接口又是低频调用，实时算没有成本问题。
fn server_specs() -> Value {
    let cpu = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4);
    let total_gb = detect_memory_gb();
    let avail_gb = detect_available_memory_gb();
    let gate = crate::study::global_session_limit_public();
    // 内存预算 = min(主机可用 − 邻居预留, cgroup 硬顶余量)。
    // 两个口径都要：主机口径防挤爆邻居，cgroup 口径防自己越顶被 OOM-kill。
    let host_budget = ((avail_gb * 1024.0) as usize).saturating_sub(OTHER_SERVICES_RESERVE_MB);
    let budget = match cgroup_mem_headroom_mb() {
        Some(cg) => host_budget.min(cg),
        None => host_budget,
    };
    let recommended = recommend_workers(cpu, budget, gate);
    json!({
        "cpu_count": cpu,
        "total_mem_gb": (total_gb * 10.0).round() / 10.0,
        "available_mem_gb": (avail_gb * 10.0).round() / 10.0,
        "per_task_mem_mb": PER_TASK_MEM_MB,
        "session_gate": gate,
        // 两条通道的推荐值：当前算法下同源（同一组上界）。分开给字段是给未来
        // 留口径 —— 比如按通道加权会话倍率（付费 turbo 单 8 路 vs 免费单 1 路）。
        "recommended_workers": recommended,
        "recommended_free_workers": recommended,
    })
}

/// 并发上限硬边界，与 queue::MAX_WORKERS_CEILING 保持一致
const MAX_WORKERS_CEILING: usize = 64;

/// 免费通道并发上限，与 queue::MAX_FREE_WORKERS_CEILING 保持一致
const MAX_FREE_WORKERS_CEILING: usize = 64;

/// 默认并发：CPU 核数 - 1（夹在 1..=64），与队列调度器启动默认一致。
/// Rust 任务全是 I/O 等待，上限远高于 Python 时代的 8 —— 提高的是"同时等
/// 多少个视频的墙钟"，不是"每秒打多少请求"（后者由全局闸门固定在 ≈2 req/s）。
fn default_max_workers() -> usize {
    std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4)
        .saturating_sub(1).max(1).clamp(1, MAX_WORKERS_CEILING)
}

/// 免费通道默认并发，与 queue::default_free_max_workers 同源（默认 8，管理端可热改）
fn default_free_max_workers() -> usize {
    std::env::var("RUST_FREE_MAX_WORKERS").ok()
        .and_then(|v| v.parse::<usize>().ok())
        .filter(|n| *n > 0)
        .unwrap_or(8)
        .clamp(1, MAX_FREE_WORKERS_CEILING)
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

/// 可用内存（MemAvailable）。与 MemTotal 的关键区别：它已扣除内核认为
/// **不可回收**的页（含邻居项目真实占用的常驻集），是"新任务还能吃多少"的
/// 正确口径。旧代码用 MemTotal 推导并发，等于把 faceswap/MySQL 和页缓存都
/// 当成了自己的余量（7.8GB 总量里实际可用的常常只有 5-6GB）。
///
/// 老内核（<3.14）没有 MemAvailable，退回总量（配合预留常量仍安全）。
#[cfg(target_os = "linux")]
fn detect_available_memory_gb() -> f64 {
    std::fs::read_to_string("/proc/meminfo")
        .ok()
        .and_then(|s| {
            s.lines().find(|l| l.starts_with("MemAvailable:"))
                .and_then(|l| l.split_whitespace().nth(1))
                .and_then(|v| v.parse::<f64>().ok())
        })
        .map(|kb| kb / 1024.0 / 1024.0)
        .unwrap_or_else(detect_memory_gb)
}

#[cfg(not(target_os = "linux"))]
fn detect_memory_gb() -> f64 {
    // Windows：CIM 查询物理内存（仅本地开发预览走这条路径，线上是 Linux）
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

#[cfg(not(target_os = "linux"))]
fn detect_available_memory_gb() -> f64 {
    // 非 Linux 无 MemAvailable 等价物：退回总量（配上预留常量仍安全）
    detect_memory_gb()
}

/// 服务器配置探测接口：返回实时资源与两条通道的推荐值/当前值。
/// `available_mem_gb` / `session_gate` / `recommended_free_workers` /
/// `current_free_workers` 是给前端"服务器配置"卡片解释推荐依据用的。
async fn queue_detect(State(state): State<AppState>) -> Json<Value> {
    let mut data = tokio::task::spawn_blocking(server_specs)
        .await
        .unwrap_or(Value::Null);
    let current = crate::queue::config_get(&state.db, "queue_max_workers").await
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or_else(default_max_workers);
    let current_free = crate::queue::config_get(&state.db, crate::queue::CFG_FREE_MAX_WORKERS).await
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or_else(default_free_max_workers);
    data["current_workers"] = json!(current);
    data["current_free_workers"] = json!(current_free);
    Json(json!({"success": true, "message": "ok", "data": data}))
}

#[cfg(test)]
mod specs_tests {
    use super::*;

    /// 推荐并发的三条上界（CPU / 内存预算 / 会话闸）必须分别能起决定作用：
    /// 这是"智能检测"从拍脑袋公式（内存 GB×2）换成可解释算法的回归护栏。
    /// 第二参数是调用方算好的有效预算（主机可用 − 邻居预留，与 cgroup 余量取 min）。
    #[test]
    fn recommend_workers_three_bounds() {
        // 线上机型：8 核 / 主机可用 6GB − 预留 1GB = 预算 5120MB / 会话闸 32 → 32
        // （旧公式被"每 GB 养 2 个任务"压到 15，这才是"检测不准"的根源）
        assert_eq!(recommend_workers(8, 6 * 1024 - 1024, 32), 32);
        // 闸更小 → 由会话闸决定
        assert_eq!(recommend_workers(8, 6 * 1024 - 1024, 10), 10);
        // 预算被 cgroup/内存压到 1024MB → 1024/48 = 21（旧公式会算出 4，差 5 倍）
        assert_eq!(recommend_workers(8, 1024, 32), 21);
        // 预算极小 → 至少 1，不推荐 0
        assert_eq!(recommend_workers(8, 10, 32), 1);
        // 小核机 → 由 CPU 决定
        assert_eq!(recommend_workers(2, 4096, 32), 8);
        // 上限兜底：核数再多也不超过 64
        assert_eq!(recommend_workers(64, 64 * 1024, 64), 64);
    }

    /// 线上是 Linux：MemAvailable 必须能读到（读到 0 说明解析坏了，
    /// 会导致推荐值被错误地压到 1）
    #[cfg(target_os = "linux")]
    #[test]
    fn available_memory_is_detected() {
        assert!(detect_available_memory_gb() > 0.0, "MemAvailable 解析失败");
    }

    /// cgroup 口径：能解析出限制时余量必须是正数（线上服务跑在 MemoryMax=3G
    /// 的 cgroup 下；解析错误会让预算口径失准）。无 cgroup 限制的环境返回 None，
    /// 属合法降级。
    #[cfg(target_os = "linux")]
    #[test]
    fn cgroup_headroom_is_sane_when_limited() {
        if let Some(mb) = cgroup_mem_headroom_mb() {
            assert!(mb > 0, "cgroup 余量解析异常: {mb}MB");
        }
    }
}



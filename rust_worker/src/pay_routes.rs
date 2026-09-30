//! YPay 支付路由 — 对齐 api/routers/payment.py + api/routers/ypay_routes.py
//!
//! 响应 JSON 字段名与 Python 逐字对齐；路由全部公开（对齐 Python get_optional_user）。
//! 已知缺口（汇报父代理）：
//! - qr_image（二维码 PNG base64）不生成，一律返回 null（Python make_qr_base64 失败也返回 None，形状兼容）。
//! - POST /api/ypay/decode-qr 与 GET /api/ypay/qrcode/{trade_no} 返回 code=-1 说明（不移植 pyzbar/qrcode PNG）。

use std::collections::HashMap;
use std::sync::Arc;

use axum::body::Bytes;
use axum::extract::{Path, Query, State};
use axum::http::{header, HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::db::Db;
use crate::AppState;

pub fn router() -> Router<AppState> {
    Router::new()
        // payment.py
        .route("/api/payment/create", post(payment_create))
        .route("/api/payment/notify", post(payment_notify))
        .route("/api/payment/check/{out_trade_no}", get(payment_check))
        .route("/api/payment/batch-create", post(payment_batch_create))
        .route("/api/payment/batch-check/{batch_id}", get(payment_batch_check))
        // ypay_routes.py
        .route("/api/ypay/create", post(ypay_create))
        .route("/api/ypay/check/{trade_no}", get(ypay_check))
        .route("/api/ypay/order/{trade_no}", get(ypay_order_detail))
        .route("/api/ypay/batch-create", post(ypay_batch_create))
        .route("/api/ypay/decode-qr", post(ypay_decode_qr))
        .route("/api/ypay/qrcode/{trade_no}", get(ypay_qrcode_png))
}

// ── 响应辅助 ────────────────────────────────────────────────

/// no-cache JSON 响应（对齐 _paid_response/_unpaid_response 的头）
fn no_cache_json(v: Value) -> Response {
    let mut resp = Json(v).into_response();
    let h = resp.headers_mut();
    h.insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
    h.insert("x-accel-buffering", HeaderValue::from_static("no"));
    resp
}

fn paid_response(order_id: &str) -> Response {
    no_cache_json(json!({"code": 0, "paid": true, "order_id": order_id, "message": "支付成功"}))
}

fn unpaid_response(message: &str, expired: bool) -> Response {
    let mut v = json!({"code": 0, "paid": false, "message": message});
    if expired {
        v["expired"] = json!(true);
    }
    no_cache_json(v)
}

fn plain_text(s: &'static str) -> Response {
    let mut resp = s.into_response();
    resp.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("text/plain; charset=utf-8"),
    );
    resp
}

/// form 解析失败 → 422 + "fail"（支付通道对接约定的响应形状，改动会影响对端重试语义）
fn form_fail() -> Response {
    let mut resp = plain_text("fail");
    *resp.status_mut() = StatusCode::UNPROCESSABLE_ENTITY;
    resp
}

// ── 入队辅助（对齐 services/order_service.py）────────────────

/// 对齐 enqueue_order：取单 → 状态闸 → 队列去重 → 写队列任务 → start_order
fn enqueue_order_sync(db: &Db, order_id: &str) -> bool {
    let Some(order) = db.get_order_sync(order_id) else { return false };
    if order.get("status").and_then(Value::as_str) != Some("paid") {
        return false;
    }
    // 对齐 q.get_job_by_order_id(order_id)：两表查最新任务
    if db.queue_job_status_by_order_sync(order_id).is_some() {
        return false;
    }
    match db.submit_paid_order_job_sync(&order) {
        Ok(true) => {
            db.start_order_sync(order_id, "");
            // 付款成功即"有效邀请"：这是唯一可信的转化信号（免费单走不到这里）。
            // 放在入队的唯一扼流点上，推送/对账/手动三条收款路径都覆盖到。
            let vid = order.get("vid").and_then(Value::as_str).unwrap_or("");
            if !vid.is_empty() {
                crate::promo::mark_converted_blocking(db, vid, order_id);
            }
            true
        }
        Ok(false) => false,
        Err(e) => {
            tracing::error!(order_id, error = %e, "入队失败");
            false
        }
    }
}

/// 对齐 enqueue_paid_orders：逐单入队，返回成功数
fn enqueue_paid_orders_sync(db: &Db, order_ids: &[String]) -> usize {
    let mut n = 0;
    for oid in order_ids {
        if enqueue_order_sync(db, oid) {
            n += 1;
        }
    }
    n
}

/// 单笔入队（免费/刷课卡订单复用同一条通道，避免两套入队逻辑漂移）
pub async fn enqueue_paid_order(db: &Db, order_id: &str) {
    let db = db.clone();
    let oid = order_id.to_string();
    let _ = tokio::task::spawn_blocking(move || enqueue_order_sync(&db, &oid)).await;
}

// ── 请求体 ──────────────────────────────────────────────────

#[derive(Deserialize)]
struct PaymentCreateReq {
    order_id: String,
    #[serde(default = "default_pay_type")]
    pay_type: i64,
}

#[derive(Deserialize)]
struct BatchCreateReq {
    #[serde(default)]
    order_ids: Vec<String>,
    #[serde(default = "default_pay_type")]
    pay_type: i64,
}

fn default_pay_type() -> i64 {
    1
}

// ── /api/payment/create（对齐 payment_create）────────────────

async fn payment_create(State(state): State<AppState>, Json(body): Json<PaymentCreateReq>) -> Json<Value> {
    let db = state.db.clone();
    let order_id = body.order_id.clone();
    let order = {
        let dbc = db.clone();
        let oid = order_id.clone();
        tokio::task::spawn_blocking(move || dbc.get_order_sync(&oid))
            .await
            .ok()
            .flatten()
    };
    let Some(order) = order else {
        return Json(json!({"code": 404, "message": "订单不存在"}));
    };
    if order.get("paid").and_then(Value::as_bool).unwrap_or(false) {
        return Json(json!({"code": 400, "message": "订单已支付"}));
    }

    let site_url = crate::pay::get_site_url(&db).await;
    let price = order.get("price").and_then(Value::as_f64).unwrap_or(0.0);
    let username = order.get("username").and_then(Value::as_str).unwrap_or("");
    let client = reqwest::Client::new();
    let result = crate::pay::create_order(
        &db,
        &client,
        body.pay_type,
        price,
        &body.order_id,
        &format!("网课代刷-{username}"),
        &format!("{site_url}/api/payment/notify"),
        &format!("{site_url}/#/orders"),
        "",
        true,
    )
    .await;
    let Some(result) = result else {
        return Json(json!({"code": -1, "message": "创建支付订单失败，请检查收款通道是否在线"}));
    };

    let trade_no = result.get("trade_no").and_then(Value::as_str).unwrap_or("").to_string();
    let pay_link = result.get("qrcode").and_then(Value::as_str).unwrap_or("").to_string();
    let pay_url = crate::pay::build_pay_url(&db, &trade_no).await;
    // 前端只渲染 qr_image，必须真的出图，否则收银台卡在「生成二维码中…」
    let qr_image = crate::ypay_qr::render_qr_image_value(&pay_link);

    {
        let oid = order_id.clone();
        let tn = trade_no.clone();
        let detail = format!("YPay支付订单:{trade_no} 金额:{price}");
        tokio::task::spawn_blocking(move || {
            db.update_order_out_trade_no_sync(&oid, &tn);
            db.audit_log_sync("payment_created", &oid, &detail);
        })
        .await
        .ok();
    }

    Json(json!({
        "code": 0,
        "data": {
            "mode": "ypay",
            "trade_no": trade_no,
            "out_trade_no": order_id,
            "order_id": body.order_id,
            "pay_url": pay_url,
            "pay_link": pay_link,
            "price": price,
            "really_price": result.get("truemoney").cloned().unwrap_or(json!(0.0)),
            "pay_type": body.pay_type,
            "qr_image": qr_image,
            "h5_qrurl": result.get("h5_qrurl").and_then(Value::as_str).unwrap_or(""),
        },
    }))
}

// ── /api/payment/notify（对齐 _payment_notify_sync）──────────

async fn payment_notify(State(state): State<AppState>, body: Bytes) -> Response {
    // 只在表单 Content-Type 下解析，其它一律抛错 → "fail"（对接约定）
    let text = match String::from_utf8(body.to_vec()) {
        Ok(t) => t,
        Err(_) => return form_fail(),
    };
    let mut params: HashMap<String, String> = HashMap::new();
    for pair in text.split('&') {
        if pair.is_empty() {
            continue;
        }
        let (k, v) = pair.split_once('=').unwrap_or((pair, ""));
        params.insert(
            crate::ypay_qr::quote_full(k),
            crate::ypay_qr::quote_full(v),
        );
    }

    let db = state.db.clone();
    let out = tokio::task::spawn_blocking(move || payment_notify_sync(&db, params))
        .await
        .unwrap_or(false);
    plain_text(if out { "success" } else { "fail" })
}

/// 对齐 _payment_notify_sync：返回 true=success / false=fail
fn payment_notify_sync(db: &Db, params: HashMap<String, String>) -> bool {
    let pay_id = params.get("payId").cloned().unwrap_or_default();
    let param = params.get("param").cloned().unwrap_or_default();
    let pay_type = params.get("type").cloned().unwrap_or_default();
    let price = params.get("price").cloned().unwrap_or_default();
    let really_price = params.get("reallyPrice").cloned().unwrap_or_default();
    let sign = params.get("sign").cloned().unwrap_or_default();

    if pay_id.is_empty() || sign.is_empty() {
        return false;
    }

    // 验签（对齐 verify_callback_sign：key 空 → false）
    let key = db.ypay_setting_get_sync("key", "");
    if key.is_empty() {
        return false;
    }
    let expected = crate::pay::hash_md5(&format!("{pay_id}{param}{pay_type}{price}{really_price}{key}"));
    if sign != expected {
        return false;
    }

    let trade_no = if pay_id.starts_with('Y') { pay_id.clone() } else { param.clone() };
    let mut ypay_order = db.ypay_get_order_sync(&trade_no);
    if ypay_order.is_none() {
        ypay_order = db.ypay_get_order_by_out_trade_no_sync(&param);
    }
    let Some(ypay_order) = ypay_order else {
        // 签名已验证但订单不存在，返回 success 防止 YPay 无限重试
        return true;
    };
    let trade_no = ypay_order.get("trade_no").and_then(Value::as_str).unwrap_or("").to_string();

    if ypay_order.get("status").and_then(Value::as_i64) != Some(1) {
        if !db.ypay_mark_paid_sync(&trade_no) {
            tracing::error!(trade_no, "标记支付单失败，继续处理业务订单");
        }
    }

    let out_trade_no = {
        let v = ypay_order.get("out_trade_no").and_then(Value::as_str).unwrap_or("");
        if v.is_empty() { trade_no.clone() } else { v.to_string() }
    };
    let channel_name = match pay_type.as_str() {
        "1" => "wechat",
        "2" => "alipay",
        "3" => "lkl",
        _ => "unknown",
    };

    if out_trade_no.starts_with("BATCH-") {
        // 批量支付：查找所有关联订单
        let mut order_ids: Vec<String> = db
            .get_orders_by_out_trade_no_sync(&out_trade_no)
            .iter()
            .filter_map(|o| o.get("order_id").and_then(Value::as_str).map(str::to_string))
            .collect();

        // 回退：按金额匹配未支付订单
        if order_ids.is_empty() {
            let price_val = price.parse::<f64>().unwrap_or(0.0);
            if price_val > 0.0 {
                let fallback = db.find_unpaid_batch_orders_sync();
                let total: f64 = fallback
                    .iter()
                    .map(|o| o.get("price").and_then(Value::as_f64).unwrap_or(0.0))
                    .sum();
                if !fallback.is_empty() && (total - price_val).abs() < 0.02 {
                    order_ids = fallback
                        .iter()
                        .filter_map(|o| o.get("order_id").and_then(Value::as_str).map(str::to_string))
                        .collect();
                    tracing::warn!(
                        batch = out_trade_no,
                        found = order_ids.len(),
                        price = price_val,
                        "payment_callback_fallback 按金额匹配未支付订单"
                    );
                }
            }
        }

        for oid in &order_ids {
            if !db.claim_payment_processing_sync(oid) {
                continue;
            }
            db.confirm_payment_sync(oid, &trade_no, channel_name);
            db.mark_payment_processed_sync(oid);
            db.audit_log_sync(
                "payment_confirm",
                oid,
                &format!("YPay批量支付成功 batch={out_trade_no} ¥{price} 实付¥{really_price}"),
            );
        }
        enqueue_paid_orders_sync(db, &order_ids);
    } else {
        // 单笔支付
        let order_id = out_trade_no.clone();
        let Some(order) = db.get_order_sync(&order_id) else {
            return true;
        };
        if order.get("paid_processed").and_then(Value::as_str) == Some("processed") {
            return true;
        }
        if !db.claim_payment_processing_sync(&order_id) {
            return true;
        }
        db.confirm_payment_sync(&order_id, &trade_no, channel_name);
        db.mark_payment_processed_sync(&order_id);
        db.audit_log_sync(
            "payment_confirm",
            &order_id,
            &format!("YPay支付成功 ¥{price} 实付¥{really_price}"),
        );
        enqueue_paid_orders_sync(db, &[order_id]);
    }
    true
}


// ── 轮询/批量/YPay 直连接口（对齐 payment.py + ypay_routes.py 其余端点）────

use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Deserialize)]
struct PaymentCheckQuery {
    #[serde(default)]
    order_id: String,
}

#[derive(Deserialize)]
struct BatchCheckQuery {
    #[serde(default)]
    out_trade_no: String,
    // Python 签名里接收 token 但未参与逻辑，保留兼容
    #[serde(default)]
    #[allow(dead_code)]
    token: String,
}

/// Python str(value) 对齐：int → "10"，float → py_float_str，str 原样，缺省 ""
fn py_value_str(v: Option<&Value>) -> String {
    match v {
        Some(Value::Number(n)) => {
            if let Some(i) = n.as_i64() {
                i.to_string()
            } else if let Some(u) = n.as_u64() {
                u.to_string()
            } else {
                crate::pay::py_float_str(n.as_f64().unwrap_or(0.0))
            }
        }
        Some(Value::String(s)) => s.clone(),
        Some(Value::Null) | None => String::new(),
        Some(other) => other.to_string(),
    }
}

fn status_of(v: &Value) -> i64 {
    v.get("status").and_then(Value::as_i64).unwrap_or(0)
}

fn paid_json(order_id: &str) -> Value {
    json!({"code": 0, "paid": true, "order_id": order_id, "message": "支付成功"})
}

fn unpaid_json(message: &str, expired: bool) -> Value {
    let mut v = json!({"code": 0, "paid": false, "message": message});
    if expired {
        v["expired"] = json!(true);
    }
    v
}

// ── /api/payment/check/{out_trade_no}（对齐 check_payment）────────────────

async fn payment_check(
    State(state): State<AppState>,
    Path(out_trade_no): Path<String>,
    Query(q): Query<PaymentCheckQuery>,
) -> Response {
    let db = state.db.clone();
    let v = tokio::task::spawn_blocking(move || payment_check_sync(&db, &out_trade_no, &q.order_id))
        .await
        .unwrap_or_else(|_| unpaid_json("未支付或处理中", false));
    no_cache_json(v)
}

fn payment_check_sync(db: &Db, out_trade_no: &str, order_id_q: &str) -> Value {
    let mut ypay_order = db.ypay_get_order_sync(out_trade_no);
    if ypay_order.is_none() {
        ypay_order = db.ypay_get_order_by_out_trade_no_sync(out_trade_no);
    }
    if ypay_order.is_none() && !order_id_q.is_empty() {
        ypay_order = db.ypay_get_order_by_out_trade_no_sync(order_id_q);
    }
    let Some(ypay_order) = ypay_order else {
        return unpaid_json("支付单不存在", false);
    };

    let trade_no = ypay_order
        .get("trade_no")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let actual_order_id = ypay_order
        .get("out_trade_no")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();

    if status_of(&ypay_order) == 1 {
        // 已支付：检查是否已处理
        if let Some(fresh) = db.get_order_sync(&actual_order_id) {
            if fresh.get("paid_processed").and_then(Value::as_str) == Some("processed") {
                return paid_json(&actual_order_id);
            }
        }

        if !db.claim_payment_processing_sync(&actual_order_id) {
            // claim 失败：并发处理中，或卡在 processing（进程崩溃）。已支付则自愈收尾。
            if let Some(stale) = db.get_order_sync(&actual_order_id) {
                let processing =
                    stale.get("paid_processed").and_then(Value::as_str) == Some("processing");
                let paid = stale.get("paid").and_then(Value::as_bool).unwrap_or(false);
                if processing && paid && db.queue_job_status_by_order_sync(&actual_order_id).is_none()
                {
                    db.confirm_payment_sync(&actual_order_id, &trade_no, "ypay");
                    db.mark_payment_processed_sync(&actual_order_id);
                    enqueue_paid_orders_sync(db, std::slice::from_ref(&actual_order_id));
                }
            }
            return paid_json(&actual_order_id);
        }

        if db.queue_job_status_by_order_sync(&actual_order_id).is_some() {
            return paid_json(&actual_order_id);
        }

        db.confirm_payment_sync(&actual_order_id, &trade_no, "ypay");
        db.mark_payment_processed_sync(&actual_order_id);
        db.audit_log_sync(
            "payment_confirm",
            &actual_order_id,
            &format!("YPay支付成功(轮询) 金额:{}", py_value_str(ypay_order.get("money"))),
        );
        enqueue_paid_orders_sync(db, std::slice::from_ref(&actual_order_id));
        return paid_json(&actual_order_id);
    }

    let end_time = ypay_order.get("end_time").and_then(Value::as_str).unwrap_or("");
    if !end_time.is_empty() && status_of(&ypay_order) == 0 {
        return unpaid_json("订单已过期", true);
    }
    unpaid_json("未支付或处理中", false)
}

// ── /api/payment/batch-create（对齐 batch_payment_create）──────────────────

async fn payment_batch_create(
    State(state): State<AppState>,
    Json(body): Json<BatchCreateReq>,
) -> Json<Value> {
    let db = state.db.clone();
    let dbc = db.clone();
    let ids = body.order_ids.clone();
    let fetched = tokio::task::spawn_blocking(move || -> Result<Vec<Value>, String> {
        let mut orders = Vec::new();
        for oid in &ids {
            let Some(o) = dbc.get_order_sync(oid) else {
                return Err(oid.clone());
            };
            if o.get("paid").and_then(Value::as_bool).unwrap_or(false) {
                continue;
            }
            let st = o.get("status").and_then(Value::as_str).unwrap_or("");
            if st != "pending" && st != "awaiting_payment" {
                continue;
            }
            orders.push(o);
        }
        Ok(orders)
    })
    .await;
    let orders = match fetched {
        Ok(Ok(o)) => o,
        Ok(Err(missing)) => {
            return Json(json!({"code": 404, "message": format!("订单 {missing} 不存在")}));
        }
        Err(_) => return Json(json!({"code": 400, "message": "没有待支付的订单"})),
    };
    if orders.is_empty() {
        return Json(json!({"code": 400, "message": "没有待支付的订单"}));
    }

    let total_price: f64 = orders
        .iter()
        .map(|o| o.get("price").and_then(Value::as_f64).unwrap_or(0.0))
        .sum();
    let batch_id = format!("BATCH-{}", crate::ypay_db::uuid_hex_upper(8));

    let site_url = crate::pay::get_site_url(&db).await;
    let client = reqwest::Client::new();
    let result = crate::pay::create_order(
        &db,
        &client,
        body.pay_type,
        total_price,
        &batch_id,
        &format!("批量支付-{}笔订单", orders.len()),
        &format!("{site_url}/api/payment/notify"),
        &format!("{site_url}/#/orders"),
        "",
        true,
    )
    .await;
    let Some(result) = result else {
        return Json(json!({"code": -1, "message": "创建支付订单失败"}));
    };

    let trade_no = result.get("trade_no").and_then(Value::as_str).unwrap_or("").to_string();
    let pay_link = result.get("qrcode").and_then(Value::as_str).unwrap_or("").to_string();
    let pay_url = crate::pay::build_pay_url(&db, &trade_no).await;
    let order_ids: Vec<String> = orders
        .iter()
        .filter_map(|o| o.get("order_id").and_then(Value::as_str).map(str::to_string))
        .collect();

    {
        let dbc = db.clone();
        let oids = order_ids.clone();
        let bid = batch_id.clone();
        let detail = format!("批量支付 batch={batch_id} 金额:{}", crate::pay::py_float_str(total_price));
        tokio::task::spawn_blocking(move || {
            for oid in &oids {
                dbc.update_order_out_trade_no_sync(oid, &bid);
            }
            for oid in &oids {
                dbc.audit_log_sync("batch_payment_created", oid, &detail);
            }
        })
        .await
        .ok();
    }

    Json(json!({
        "code": 0,
        "data": {
            "mode": "ypay_batch",
            "batch_id": batch_id,
            "trade_no": trade_no,
            "out_trade_no": batch_id,
            "order_ids": order_ids,
            "pay_url": pay_url,
            "pay_link": pay_link,
            "total_price": total_price,
            "really_price": result.get("truemoney").cloned().unwrap_or(json!(0.0)),
            "pay_type": body.pay_type,
            "qr_image": crate::ypay_qr::render_qr_image_value(&pay_link),
            "h5_qrurl": result.get("h5_qrurl").and_then(Value::as_str).unwrap_or(""),
        },
    }))
}

// ── /api/payment/batch-check/{batch_id}（对齐 batch_check_payment）─────────

async fn payment_batch_check(
    State(state): State<AppState>,
    Path(batch_id): Path<String>,
    Query(q): Query<BatchCheckQuery>,
) -> Response {
    let db = state.db.clone();
    let out_trade_no = q.out_trade_no.clone();
    let v = tokio::task::spawn_blocking(move || payment_batch_check_sync(&db, &batch_id, &out_trade_no))
        .await
        .unwrap_or_else(|_| unpaid_json("未支付或处理中", false));
    no_cache_json(v)
}

fn payment_batch_check_sync(db: &Db, batch_id: &str, out_trade_no: &str) -> Value {
    let mut ypay_order = db.ypay_get_order_sync(out_trade_no);
    if ypay_order.is_none() {
        ypay_order = db.ypay_get_order_by_out_trade_no_sync(out_trade_no);
    }
    let Some(ypay_order) = ypay_order else {
        return unpaid_json("支付单不存在", false);
    };

    let end_time = ypay_order.get("end_time").and_then(Value::as_str).unwrap_or("");
    if !end_time.is_empty() && status_of(&ypay_order) == 0 {
        return unpaid_json("订单已过期", true);
    }
    if status_of(&ypay_order) != 1 {
        return unpaid_json("未支付或处理中", false);
    }

    // 对齐 Python：按 query 参数 out_trade_no 查关联订单（而非 ypay_order.out_trade_no）
    let order_ids: Vec<String> = db
        .get_orders_by_out_trade_no_sync(out_trade_no)
        .iter()
        .filter_map(|o| o.get("order_id").and_then(Value::as_str).map(str::to_string))
        .collect();
    if order_ids.is_empty() {
        return unpaid_json("订单关联异常", false);
    }

    let mut paid_count = 0usize;
    for oid in &order_ids {
        let Some(order) = db.get_order_sync(oid) else { continue };
        if order.get("paid").and_then(Value::as_bool).unwrap_or(false)
            && order.get("paid_processed").and_then(Value::as_str) == Some("processed")
        {
            paid_count += 1;
            continue;
        }
        if !db.claim_payment_processing_sync(oid) {
            paid_count += 1;
            continue;
        }
        if db.queue_job_status_by_order_sync(oid).is_some() {
            paid_count += 1;
            continue;
        }
        db.confirm_payment_sync(oid, out_trade_no, "ypay");
        db.mark_payment_processed_sync(oid);
        paid_count += 1;
        db.audit_log_sync("batch_payment_confirm", oid, &format!("批量支付确认 batch={batch_id}"));
    }

    enqueue_paid_orders_sync(db, &order_ids);

    if paid_count >= order_ids.len() {
        // credited ≠ paid：paid 只说明钱到了，credited 说明业务侧真的走完入账
        // （paid_processed='processed'）。前端据此把「支付成功」与「已收款未入账」
        // 分成两种提示，避免钱收了却告诉用户成功、用户关页面后无人补账。
        let credited = order_ids.iter().all(|oid| {
            db.get_order_sync(oid)
                .map(|o| {
                    o.get("paid").and_then(Value::as_bool).unwrap_or(false)
                        && o.get("paid_processed").and_then(Value::as_str) == Some("processed")
                })
                .unwrap_or(false)
        });
        return json!({
            "code": 0,
            "paid": true,
            "credited": credited,
            "paid_count": paid_count,
            "message": if credited { "全部支付成功" } else { "支付已收到，正在入账" },
        });
    }
    unpaid_json("未支付或处理中", false)
}

// ── /api/ypay/create（对齐 pay_create）────────────────────────────────────

async fn ypay_create(State(state): State<AppState>, Json(body): Json<PaymentCreateReq>) -> Json<Value> {
    let db = state.db.clone();
    let order_id = body.order_id.clone();
    let order = {
        let dbc = db.clone();
        let oid = order_id.clone();
        tokio::task::spawn_blocking(move || dbc.get_order_sync(&oid))
            .await
            .ok()
            .flatten()
    };
    let Some(order) = order else {
        return Json(json!({"code": 404, "message": "订单不存在"}));
    };
    if order.get("paid").and_then(Value::as_bool).unwrap_or(false) {
        return Json(json!({"code": 400, "message": "订单已支付"}));
    }

    let site_url = crate::pay::get_site_url(&db).await;
    let price = order.get("price").and_then(Value::as_f64).unwrap_or(0.0);
    let username = order.get("username").and_then(Value::as_str).unwrap_or("");
    let client = reqwest::Client::new();
    let result = crate::pay::create_order(
        &db,
        &client,
        body.pay_type,
        price,
        &body.order_id,
        &format!("网课代刷-{username}"),
        &format!("{site_url}/api/payment/notify"),
        &format!("{site_url}/#/orders"),
        "",
        true,
    )
    .await;
    let Some(result) = result else {
        return Json(json!({"code": -1, "message": "创建支付订单失败，请检查收款通道是否在线"}));
    };

    let trade_no = result.get("trade_no").and_then(Value::as_str).unwrap_or("").to_string();
    let pay_url = crate::pay::build_pay_url(&db, &trade_no).await;
    let qr_content = result.get("qrcode").and_then(Value::as_str).unwrap_or("").to_string();
    // create_order 已写入 qr_content_type；缺省回落 detect（对齐 _detect_type）
    let qr_content_type = result
        .get("qr_content_type")
        .and_then(Value::as_str)
        .unwrap_or_else(|| crate::ypay_qr::detect_qr_content_type(&qr_content))
        .to_string();
    // 前端只渲染 qr_image，必须真的出图
    let qr_image = crate::ypay_qr::render_qr_image_value(&qr_content);

    {
        let oid = order_id.clone();
        let tn = trade_no.clone();
        let detail = format!("YPay订单:{trade_no} 金额:{}", crate::pay::py_float_str(price));
        tokio::task::spawn_blocking(move || {
            db.update_order_out_trade_no_sync(&oid, &tn);
            db.audit_log_sync("ypay_created", &oid, &detail);
        })
        .await
        .ok();
    }

    Json(json!({
        "code": 0,
        "data": {
            "mode": "ypay",
            "trade_no": trade_no,
            "out_trade_no": order_id,
            "order_id": body.order_id,
            "pay_url": pay_url,
            "price": price,
            "really_price": result.get("truemoney").cloned().unwrap_or(json!(0.0)),
            "pay_type": body.pay_type,
            "qr_image": qr_image,
            "qr_content_type": qr_content_type,
            "channel_code": result.get("channel_code").and_then(Value::as_str).unwrap_or(""),
            "channel_name": result.get("channel_name").and_then(Value::as_str).unwrap_or(""),
            "qrcode_content": qr_content,
            "h5_qrurl": result.get("h5_qrurl").and_then(Value::as_str).unwrap_or(""),
        },
    }))
}

// ── /api/ypay/check/{trade_no}（对齐 pay_check）────────────────────────────

/// 对齐 _process_paid_order（不含入队，Python 侧此路径也不入队）
fn process_paid_order_sync(db: &Db, order_id: &str, already_confirmed: bool) {
    let mut fresh = db.get_order_sync(order_id);
    let is_done = |o: &Value| {
        o.get("paid").and_then(Value::as_bool).unwrap_or(false)
            && o.get("paid_processed").and_then(Value::as_str) == Some("processed")
    };
    let Some(f) = &fresh else { return };
    if is_done(f) {
        return;
    }
    let paid = f.get("paid").and_then(Value::as_bool).unwrap_or(false);
    if !already_confirmed && !paid {
        db.confirm_payment_sync(order_id, &format!("YPAY-{order_id}"), "ypay");
        fresh = db.get_order_sync(order_id);
    }
    let processed = fresh
        .as_ref()
        .and_then(|o| o.get("paid_processed"))
        .and_then(Value::as_str)
        == Some("processed");
    if !processed {
        if !db.claim_payment_processing_sync(order_id) {
            return;
        }
        db.mark_payment_processed_sync(order_id);
    }
}

/// 后台对账：把「通道已收款但业务未入账」的订单补齐并发货。
///
/// 为什么必须由后台主动做，而不能靠前端轮询：
/// 发货只有两条有验签的入口（YPay 回调 / VMQ 推送），二者在写业务库时都可能
/// 只完成一半 —— 通道单已 `status=1`，但业务单的 `paid` / `paid_processed`
/// 未落、队列任务未投。此前这个补偿完全依赖用户还开着支付弹窗（轮询 check
/// 接口会顺带修），一旦用户付完就关页面/断网，订单会永久停在「已收款但
/// 未入账」，既没人补账也没有告警 —— 对顾客就是「钱付了，课没刷」。
///
/// 幂等：`enqueue_paid_orders_sync` 内部对同 order_id 的活跃任务去重，
/// 重复扫到同样的订单不会重复投递任务。
pub(crate) fn reconcile_paid_orders_sync(db: &Db) -> usize {
    let ids = db.find_uncredited_paid_order_ids_sync(200);
    if ids.is_empty() {
        return 0;
    }
    for oid in &ids {
        db.confirm_payment_sync(oid, &format!("YPAY-{oid}"), "ypay");
        process_paid_order_sync(db, oid, true);
    }
    // 队列任务单独补投：上面两个只改业务单标志位，不碰队列
    enqueue_paid_orders_sync(db, &ids);
    tracing::warn!(count = ids.len(), "对账：已补齐未入账的已付款订单并补投队列");
    ids.len()
}

/// 顺延补投：把「已付款、但被账号级去重拦下、至今没有队列任务」的订单补投。
///
/// 入队去重对同账号同平台串行（见 ypay_db.submit_paid_order_job_sync，防止
/// 平台按账号统计的重叠检测越线），第二单入队时会静默返回 false。这里周期性
/// 兜底：前一单跑完、账号槽位空出后，下一轮扫描把它送上，顾客无需重新下单。
/// 幂等：enqueue 链路自带 order_id 去重，重复扫到不会重复投递；同账号仍受
/// 去重约束，一单在跑时其余单继续留在原地等下一轮。
pub(crate) fn resume_deferred_orders_sync(db: &Db) -> usize {
    let ids = db.find_orders_paid_without_job_sync(100);
    if ids.is_empty() {
        return 0;
    }
    let n = enqueue_paid_orders_sync(db, &ids);
    if n > 0 {
        tracing::info!(resumed = n, scanned = ids.len(), "顺延：补投被账号去重拦下的已付款订单");
    }
    n
}

/// 对账循环：每 60s 扫一次悬空的已付款订单
pub async fn reconcile_loop(state: Arc<AppState>) {
    loop {
        tokio::time::sleep(std::time::Duration::from_secs(60)).await;
        let db = state.db.clone();
        let r = tokio::task::spawn_blocking(move || {
            let n = reconcile_paid_orders_sync(&db);
            // 顺延：账号串行拦下的已付款单，在前一单跑完后自动补投
            resume_deferred_orders_sync(&db);
            n
        })
        .await;
        if let Ok(n) = r {
            if n > 0 {
                tracing::info!(repaired = n, "对账完成");
            }
        }
    }
}

async fn ypay_check(
    State(state): State<AppState>,
    Path(trade_no): Path<String>,
    Query(q): Query<PaymentCheckQuery>,
) -> Response {
    let db = state.db.clone();
    let v = tokio::task::spawn_blocking(move || ypay_check_sync(&db, &trade_no, &q.order_id))
        .await
        .unwrap_or_else(|_| json!({"code": 0, "paid": false, "message": "等待支付", "remaining": 0}));
    no_cache_json(v)
}

fn ypay_check_sync(db: &Db, trade_no: &str, order_id_q: &str) -> Value {
    let Some(order_data) = db.ypay_get_order_sync(trade_no) else {
        return json!({"code": 0, "paid": false, "message": "未找到支付订单"});
    };

    if status_of(&order_data) == 1 {
        let actual_order_id = {
            let v = order_data.get("out_trade_no").and_then(Value::as_str).unwrap_or("");
            if v.is_empty() {
                order_id_q.to_string()
            } else {
                v.to_string()
            }
        };
        if !actual_order_id.is_empty() {
            if let Some(anti) = db.get_order_sync(&actual_order_id) {
                let paid = anti.get("paid").and_then(Value::as_bool).unwrap_or(false);
                let processed =
                    anti.get("paid_processed").and_then(Value::as_str) == Some("processed");
                if !paid {
                    db.confirm_payment_sync(&actual_order_id, trade_no, "ypay");
                    process_paid_order_sync(db, &actual_order_id, true);
                } else if !processed {
                    process_paid_order_sync(db, &actual_order_id, true);
                }
            }
        }
        // 只回报状态浮标，不在这里决定「业务是否已入账」之外的任何事。
        //
        // credited 是本次新增的关键字段：区分「通道已收款」与「业务已入账」。
        // 二者不是一回事 —— 通道单 status=1 由回调写入，业务单的
        // paid/paid_processed 可能因进程重启等原因滞后。前端据此分出
        // 「支付成功」与「已收款未入账」两种提示，避免钱收了却告诉用户成功、
        // 用户关掉页面后再也没人补账。
        let mut credited = false;
        if !actual_order_id.is_empty() {
            if let Some(anti) = db.get_order_sync(&actual_order_id) {
                let paid = anti.get("paid").and_then(Value::as_bool).unwrap_or(false);
                let processed = anti.get("paid_processed").and_then(Value::as_str) == Some("processed");
                credited = paid && processed;
            }
        }
        return json!({
            "code": 0,
            "paid": true,
            "credited": credited,
            "order_id": actual_order_id,
            "message": if credited { "支付成功" } else { "支付已收到，正在入账" },
            "really_price": order_data.get("truemoney").cloned().unwrap_or(json!(0)),
        });
    }

    // 对齐 datetime.fromisoformat(out_time) - now（两侧同为 naive，差值一致）
    let mut remaining: i64 = 0;
    if let Some(out_time) = order_data.get("out_time").and_then(Value::as_str) {
        if !out_time.is_empty() {
            if let Some(out_secs) = crate::pay::parse_iso_secs(out_time) {
                let now = SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .map(|d| d.as_secs() as i64)
                    .unwrap_or(0);
                remaining = (out_secs - now).max(0);
            }
        }
    }

    if remaining <= 0 && status_of(&order_data) == 0 {
        return json!({"code": 0, "paid": false, "message": "订单已过期", "expired": true});
    }
    json!({"code": 0, "paid": false, "message": "等待支付", "remaining": remaining})
}

// ── /api/ypay/order/{trade_no}（对齐 pay_order_detail）─────────────────────

async fn ypay_order_detail(State(state): State<AppState>, Path(trade_no): Path<String>) -> Json<Value> {
    let db = state.db.clone();
    let tn = trade_no.clone();
    let order_data = tokio::task::spawn_blocking(move || db.ypay_get_order_sync(&tn))
        .await
        .ok()
        .flatten();
    let Some(order_data) = order_data else {
        return Json(json!({"code": -1, "message": "支付订单不存在"}));
    };
    let g = |k: &str| order_data.get(k).cloned().unwrap_or(Value::Null);

    if status_of(&order_data) == 1 {
        return Json(json!({
            "code": 0,
            "data": {
                "trade_no": g("trade_no"),
                "out_trade_no": g("out_trade_no"),
                "type": g("type"),
                "pay_type": g("pay_type"),
                "money": g("money"),
                "truemoney": g("truemoney"),
                "status": 1,
                "paid": true,
                "message": "支付成功",
            },
        }));
    }

    let qr_content = order_data.get("qrcode").and_then(Value::as_str).unwrap_or("").to_string();
    let qr_content_type = crate::ypay_qr::detect_qr_content_type(&qr_content);
    let pay_url = crate::pay::build_pay_url(&state.db, &trade_no).await;
    // qr_image：Rust 端不生成 PNG base64（对齐 Python make_qr_base64 失败时的 None）
    Json(json!({
        "code": 0,
        "data": {
            "trade_no": g("trade_no"),
            "out_trade_no": g("out_trade_no"),
            "type": g("type"),
            "pay_type": g("pay_type"),
            "money": g("money"),
            "truemoney": g("truemoney"),
            "qrcode": qr_content.clone(),
            "qr_content_type": qr_content_type,
            "status": status_of(&order_data),
            "qr_image": crate::ypay_qr::render_qr_image_value(&qr_content),
            "pay_url": pay_url,
        },
    }))
}

// ── /api/ypay/batch-create（对齐 batch_pay_create）─────────────────────────

async fn ypay_batch_create(State(state): State<AppState>, Json(body): Json<BatchCreateReq>) -> Json<Value> {
    let db = state.db.clone();
    let dbc = db.clone();
    let ids = body.order_ids.clone();
    let fetched = tokio::task::spawn_blocking(move || -> Result<(Vec<Value>, Vec<String>), String> {
        let mut orders = Vec::new();
        let mut skipped = Vec::new();
        for oid in &ids {
            let Some(o) = dbc.get_order_sync(oid) else {
                return Err(oid.clone());
            };
            if o.get("paid").and_then(Value::as_bool).unwrap_or(false) {
                skipped.push(oid.clone());
                continue;
            }
            let st = o.get("status").and_then(Value::as_str).unwrap_or("");
            if st != "pending" && st != "awaiting_payment" {
                skipped.push(oid.clone());
                continue;
            }
            orders.push(o);
        }
        Ok((orders, skipped))
    })
    .await;
    let (orders, skipped) = match fetched {
        Ok(Ok(v)) => v,
        Ok(Err(missing)) => {
            return Json(json!({"code": 404, "message": format!("订单 {missing} 不存在")}));
        }
        Err(_) => return Json(json!({"code": 400, "message": "没有待支付的订单"})),
    };
    if orders.is_empty() {
        return Json(json!({"code": 400, "message": "没有待支付的订单"}));
    }

    let total_price: f64 = orders
        .iter()
        .map(|o| o.get("price").and_then(Value::as_f64).unwrap_or(0.0))
        .sum();
    let batch_id = format!("BATCH-{}", crate::ypay_db::uuid_hex_upper(8));

    let site_url = crate::pay::get_site_url(&db).await;
    let client = reqwest::Client::new();
    let result = crate::pay::create_order(
        &db,
        &client,
        body.pay_type,
        total_price,
        &batch_id,
        &format!("批量支付-{}笔订单", orders.len()),
        &format!("{site_url}/api/payment/notify"),
        &format!("{site_url}/#/orders"),
        "",
        true,
    )
    .await;
    let Some(result) = result else {
        return Json(json!({"code": -1, "message": "创建支付订单失败"}));
    };

    let trade_no = result.get("trade_no").and_then(Value::as_str).unwrap_or("").to_string();
    let pay_link = result.get("qrcode").and_then(Value::as_str).unwrap_or("").to_string();
    let pay_url = crate::pay::build_pay_url(&db, &trade_no).await;
    let order_ids: Vec<String> = orders
        .iter()
        .filter_map(|o| o.get("order_id").and_then(Value::as_str).map(str::to_string))
        .collect();

    {
        let dbc = db.clone();
        let oids = order_ids.clone();
        let bid = batch_id.clone();
        tokio::task::spawn_blocking(move || {
            for oid in &oids {
                dbc.update_order_out_trade_no_sync(oid, &bid);
                dbc.audit_log_sync("batch_ypay_created", oid, &format!("批量支付 batch={bid}"));
            }
        })
        .await
        .ok();
    }

    Json(json!({
        "code": 0,
        "data": {
            "mode": "ypay_batch",
            "batch_id": batch_id,
            "trade_no": trade_no,
            "out_trade_no": batch_id,
            "order_ids": order_ids,
            "skipped_ids": skipped,
            "pay_url": pay_url,
            "pay_link": pay_link,
            "total_price": total_price,
            "really_price": result.get("truemoney").cloned().unwrap_or(json!(0.0)),
            "pay_type": body.pay_type,
            "qr_image": crate::ypay_qr::render_qr_image_value(&pay_link),
            "h5_qrurl": result.get("h5_qrurl").and_then(Value::as_str).unwrap_or(""),
        },
    }))
}

// ── /api/ypay/decode-qr（已知缺口：不移植 pyzbar，返回 code=-1 说明）───────

async fn ypay_decode_qr() -> Json<Value> {
    Json(json!({"code": -1, "message": "二维码解码功能未在 Rust worker 实现，请手动输入"}))
}

// ── /api/ypay/qrcode/{trade_no}（已知缺口：不移植 qrcode PNG，返回 code=-1 说明）

async fn ypay_qrcode_png(Path(_trade_no): Path<String>) -> Json<Value> {
    Json(json!({"code": -1, "message": "二维码 PNG 生成未在 Rust worker 实现"}))
}

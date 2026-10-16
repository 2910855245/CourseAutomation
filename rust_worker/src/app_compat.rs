//! APP 端通信协议（对齐 Refine `payment_service/routers/ypay_app.py`，也是手头那台 Vmq 监控 APP 的既定协议）。
//!
//! 背景：本后端此前自造了一套方言 —— 配对二维码是 `{"type":"pair","app":"ypay-monitor",...}`、
//! 心跳/推送挂在 `/api/ypay/vmq/heart|push`、心跳签名 `MD5(t+key)`。而那台 APP 是照
//! Vmq/Refine 契约写死的：配对二维码必须 `t == "vmq-pair"`，接口是
//! `/api/ypay/app-heart|app-push|pair-confirm`（APP 的 ApiUrl.build 还会把 `/api/` 自动补成
//! `/pay/api/`），心跳 `sign = MD5(key)`，推送 `sign = MD5(payId+param+type+price+reallyPrice+key)`。
//! 两边对不上 ⇒ 扫码/配对/心跳全部失败（APP 扫到后直接判定"不是配对码"）。
//! 本模块把 APP 侧契约原样补齐，同时挂在 `/api/ypay/*` 与 `/pay/api/ypay/*` 两处。

use std::collections::HashMap;

use axum::body::Bytes;
use axum::extract::{Query, State};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde_json::{json, Value};

use crate::AppState;

type Params = HashMap<String, String>;

/// APP 侧接口：GET / POST 都注册（不同 APP 版本分别用 GET 与 POST，少一个就是 405）。
pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/ypay/app-heart", get(app_heart).post(app_heart))
        .route("/api/ypay/app-offline", get(app_offline).post(app_offline))
        .route("/api/ypay/app-push", get(app_push).post(app_push))
        .route("/api/ypay/app-info", get(app_info))
        .route("/api/ypay/pair-confirm", get(pair_confirm).post(pair_confirm))
        .route("/api/ypay/pair-status", get(pair_status))
        // Refine 里另有无前缀的兼容路径
        .route("/appHeart", get(app_heart).post(app_heart))
        .route("/appPush", get(app_push).post(app_push))
}

/// 合并 query 与 form body 参数（对齐 Refine `_get_params`：form → query → body）
fn merge_params(q: Params, body: &Bytes) -> Params {
    let mut p = q;
    if let Ok(text) = std::str::from_utf8(body) {
        for pair in text.split('&') {
            if let Some((k, v)) = pair.split_once('=') {
                p.entry(k.to_string()).or_insert_with(|| v.to_string());
            }
        }
    }
    p
}

fn md5_hex(s: &str) -> String {
    format!("{:x}", md5::compute(s.as_bytes()))
}

/// 通讯密钥（ypay_settings.key）
async fn key_of(state: &AppState) -> Option<String> {
    let pool = state.db.clone_pool();
    tokio::task::spawn_blocking(move || -> Option<String> {
        let conn = pool.get().ok()?;
        conn.query_row("SELECT value FROM ypay_settings WHERE key='key'", [], |r| {
            r.get::<_, String>(0)
        })
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
    })
    .await
    .ok()
    .flatten()
}

/// 后台「监控在线/心跳时间」读的就是 system_config.ypay_last_heart（见 api.rs system_status）
async fn last_heart_of(state: &AppState) -> String {
    let pool = state.db.clone_pool();
    tokio::task::spawn_blocking(move || -> String {
        let Ok(conn) = pool.get() else { return String::new() };
        conn.query_row(
            "SELECT COALESCE(config_value,'') FROM system_config WHERE config_key='ypay_last_heart'",
            [], |r| r.get(0),
        )
        .unwrap_or_default()
    })
    .await
    .unwrap_or_default()
}

/// 心跳/离线验签：`sign == MD5(key)`（协议固定，勿把 t 拼进去）。
/// 另要求带 `t`（APP 每 ~15s 一个毫秒时间戳）：不带就拒绝，免得固定语料变成永久可重放。
async fn heart_sign_ok(state: &AppState, p: &Params) -> bool {
    if p.get("t").map(|t| t.trim().is_empty()).unwrap_or(true) {
        return false;
    }
    let sign = p.get("sign").map(|s| s.trim().to_ascii_lowercase()).unwrap_or_default();
    if sign.is_empty() {
        return false;
    }
    match key_of(state).await {
        Some(key) => sign == md5_hex(&key),
        None => false,
    }
}

/// 记一次成功心跳/配对：必须写 ypay_last_heart，否则后台永远显示"监控离线"
async fn mark_online(state: &AppState) {
    let _ = crate::queue::config_set(&state.db, "ypay_last_heart", &crate::queue::now_str()).await;
}

// ── 心跳 / 离线 ──────────────────────────────────────────────────────────

async fn app_heart(State(state): State<AppState>, Query(q): Query<Params>, body: Bytes) -> Json<Value> {
    let p = merge_params(q, &body);
    if !heart_sign_ok(&state, &p).await {
        return Json(json!({"code": -1, "msg": "签名错误"}));
    }
    mark_online(&state).await;
    Json(json!({"code": 0, "msg": "成功"}))
}

async fn app_offline(State(state): State<AppState>, Query(q): Query<Params>, body: Bytes) -> Json<Value> {
    let p = merge_params(q, &body);
    if !heart_sign_ok(&state, &p).await {
        return Json(json!({"code": -1, "msg": "签名错误"}));
    }
    // 置空 = 后台按"超过 120s 视为离线"自然显示离线
    let _ = crate::queue::config_set(&state.db, "ypay_last_heart", "").await;
    Json(json!({"code": 0, "msg": "成功"}))
}

// ── 支付推送（真入账）────────────────────────────────────────────────────

async fn app_push(State(state): State<AppState>, Query(q): Query<Params>, body: Bytes) -> Json<Value> {
    let p = merge_params(q, &body);
    let Some(key) = key_of(&state).await else {
        return Json(json!({"code": -1, "msg": "密钥未配置"}));
    };
    let sign = p.get("sign").map(|s| s.trim().to_ascii_lowercase()).unwrap_or_default();
    let sign_str = format!(
        "{}{}{}{}{}{}",
        p.get("payId").cloned().unwrap_or_default(),
        p.get("param").cloned().unwrap_or_default(),
        p.get("type").cloned().unwrap_or_default(),
        p.get("price").cloned().unwrap_or_default(),
        p.get("reallyPrice").cloned().unwrap_or_default(),
        key,
    );
    if sign.is_empty() || sign != md5_hex(&sign_str) {
        return Json(json!({"code": -1, "msg": "签名错误"}));
    }
    let type_str = p.get("type").cloned().unwrap_or_default();
    let pay_type: i64 = if type_str == "2" || type_str == "alipay" { 2 } else { 1 };
    let price = p.get("price").cloned().unwrap_or_default().parse::<f64>().unwrap_or(0.0);
    match crate::pay::match_payment(&state.db, price, pay_type).await {
        Some(_) => Json(json!({"code": 0, "msg": "成功"})),
        None => Json(json!({"code": -1, "msg": "未找到匹配订单"})),
    }
}

// ── 配对 ────────────────────────────────────────────────────────────────

async fn pair_confirm(State(state): State<AppState>, Query(q): Query<Params>, body: Bytes) -> Json<Value> {
    let p = merge_params(q, &body);
    let sent = p.get("key").map(|s| s.trim().to_string()).unwrap_or_default();
    match key_of(&state).await {
        Some(k) if !sent.is_empty() && sent == k => {
            mark_online(&state).await;
            Json(json!({"code": 0, "msg": "配对成功"}))
        }
        _ => Json(json!({"code": -1, "msg": "密钥不匹配"})),
    }
}

async fn pair_status(State(state): State<AppState>) -> Json<Value> {
    let last = last_heart_of(&state).await;
    Json(json!({"code": 0, "data": {"paired": !last.is_empty(), "last_heart": last}}))
}

async fn app_info(State(state): State<AppState>) -> Json<Value> {
    let last = last_heart_of(&state).await;
    Json(json!({"code": 0, "data": {
        "status": if last.is_empty() { "0" } else { "1" },
        "last_heart": last,
        "version": "",
    }}))
}

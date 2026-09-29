//! 营销推广路由 + 访客身份中间件。
//!
//! 访客身份（[`visitor_middleware`]）：读取 HttpOnly cookie `vid`，没有就新发一个，
//! 并把 vid 塞进 request extensions 供各 handler 取用。同时（若 URL 带 `?ref=<邀请码>`）
//! 顺手记录一次邀请 —— 放在中间件里是为了"分享链接落地即计数"，
//! 不依赖前端是否记得上报。

use axum::extract::{Request, State};
use axum::http::{header, HeaderValue};
use axum::middleware::Next;
use axum::response::Response;
use axum::routing::{get, post};
use axum::{Extension, Json, Router};
use serde_json::{json, Value};

use crate::promo;
use crate::AppState;

/// 访客身份在 request extensions 里的键
#[derive(Clone, Debug)]
pub struct VisitorId(pub String);

impl VisitorId {
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/invite/me", get(invite_me))
        .route("/api/invite/claim", post(invite_claim))
        .route("/api/me/benefit", get(my_benefit))
        .route("/api/admin/promo/stats", get(admin_promo_stats))
}

/// 从 Cookie 头里取 vid
fn cookie_vid(headers: &header::HeaderMap) -> Option<String> {
    let raw = headers.get(header::COOKIE)?.to_str().ok()?;
    for kv in raw.split(';') {
        let (k, v) = kv.trim().split_once('=')?;
        if k == promo::COOKIE_NAME && v.starts_with("VID-") && v.len() <= 64 {
            return Some(v.to_string());
        }
    }
    None
}

/// 访客身份中间件：确保有 vid；URL 带 ?ref= 时顺手记录邀请
pub async fn visitor_middleware(
    State(state): State<AppState>,
    mut req: Request,
    next: Next,
) -> Response {
    let existing = cookie_vid(req.headers());
    let fresh = existing.is_none();
    let vid = existing.unwrap_or_else(promo::new_vid);

    // 只有 API 请求需要建档（静态资源不落库、也不发 cookie）
    let is_api = req.uri().path().starts_with("/api/");
    if is_api {
        let ua = req.headers().get(header::USER_AGENT)
            .and_then(|v| v.to_str().ok())
            .unwrap_or("")
            .to_string();
        // 建档失败不阻断请求：营销是附加功能，不能拖垮下单主链路
        if let Err(e) = promo::ensure_visitor(&state.db, &vid, &ua).await {
            tracing::warn!(error = %e, "访客建档失败");
        }
        if let Some(code) = ref_code_from_query(req.uri().query()) {
            if let Err(e) = promo::track_invite(&state.db, &vid, &code).await {
                tracing::warn!(error = %e, "记录邀请失败");
            }
        }
    }

    req.extensions_mut().insert(VisitorId(vid.clone()));
    let mut resp = next.run(req).await;
    if fresh && is_api {
        let cookie = format!(
            "{}={}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax",
            promo::COOKIE_NAME, vid
        );
        if let Ok(v) = HeaderValue::from_str(&cookie) {
            resp.headers_mut().append(header::SET_COOKIE, v);
        }
    }
    resp
}

/// 从 query 里取 ref（只接受字母数字短码，避免把任意字符串写库）
fn ref_code_from_query(query: Option<&str>) -> Option<String> {
    let q = query?;
    for kv in q.split('&') {
        let (k, v) = kv.split_once('=')?;
        if k == "ref" {
            let code = v.trim();
            if promo::is_valid_code(code) {
                return Some(code.to_uppercase());
            }
        }
    }
    None
}

fn visitor_ext(ext: &Extension<VisitorId>) -> String {
    ext.0.as_str().to_string()
}

async fn invite_me(
    State(state): State<AppState>,
    ext: Option<Extension<VisitorId>>,
) -> Json<Value> {
    let Some(ext) = ext else {
        return Json(json!({"success": false, "message": "访客身份缺失"}));
    };
    match promo::invite_overview(&state.db, &visitor_ext(&ext)).await {
        Ok(data) => Json(json!({"success": true, "message": "ok", "data": data})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

async fn invite_claim(
    State(state): State<AppState>,
    ext: Option<Extension<VisitorId>>,
    Json(body): Json<Value>,
) -> Json<Value> {
    let Some(ext) = ext else {
        return Json(json!({"success": false, "message": "访客身份缺失"}));
    };
    let contact = body["contact"].as_str().unwrap_or("");
    match promo::claim_card(&state.db, &visitor_ext(&ext), contact).await {
        Ok(card) => {
            let overview = promo::invite_overview(&state.db, &visitor_ext(&ext)).await
                .unwrap_or_else(|_| json!({}));
            Json(json!({"success": true, "message": "领取成功", "data": {"card": card, "overview": overview}}))
        }
        Err(e) => Json(json!({"success": false, "message": format!("{e}")})),
    }
}

async fn my_benefit(
    State(state): State<AppState>,
    ext: Option<Extension<VisitorId>>,
) -> Json<Value> {
    let vid = ext.map(|e| visitor_ext(&e)).unwrap_or_default();
    let benefit = promo::check_benefit(&state.db, &vid).await;
    let overview = if vid.is_empty() {
        json!({})
    } else {
        promo::invite_overview(&state.db, &vid).await.unwrap_or_else(|_| json!({}))
    };
    Json(json!({
        "success": true, "message": "ok",
        "data": {
            "benefit": benefit.to_json(),
            "invite": {
                "code": overview["code"],
                "threshold": overview["threshold"],
                "invited_valid": overview["invited_valid"],
                "can_claim": overview["can_claim"],
                "enabled": overview["enabled"],
            },
            "card": overview["cards"].as_array().and_then(|c| {
                c.iter().find(|x| x["valid"].as_bool() == Some(true)).cloned()
            }),
        },
    }))
}

async fn admin_promo_stats(State(state): State<AppState>) -> Json<Value> {
    match promo::admin_stats(&state.db).await {
        Ok(data) => Json(json!({"success": true, "message": "ok", "data": data})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ref_code_from_query() {
        assert_eq!(ref_code_from_query(Some("ref=ab23cd")).as_deref(), Some("AB23CD"));
        assert_eq!(ref_code_from_query(Some("a=1&ref=XY99")).as_deref(), Some("XY99"));
        // 非法邀请码一律忽略（防止把任意串写进库）
        assert!(ref_code_from_query(Some("ref=../etc")).is_none());
        assert!(ref_code_from_query(Some("ref=")).is_none());
        assert!(ref_code_from_query(Some("other=1")).is_none());
        assert!(ref_code_from_query(None).is_none());
    }
}
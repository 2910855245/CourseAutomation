//! 认证：bcrypt 校验 + JWT 签发/验证 + Bearer 中间件
//! 与 Python api/auth.py 对齐（HS256 + JWT_SECRET_KEY，72h 过期）。

use axum::extract::{Request, State};
use axum::http::header;
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use axum::Json;
use bcrypt::verify;
use jsonwebtoken::{decode, encode, Algorithm, DecodingKey, EncodingKey, Header, Validation};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::time::{SystemTime, UNIX_EPOCH};

use crate::AppState;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Claims {
    pub sub: String,
    pub role: String,
    pub exp: usize,
}

/// 全局唯一密钥源：管理员 JWT 签名、游客 view_token 都从这里取。
/// 缺失时 main::check_secret_key 会直接拒绝启动，所以这里不再需要兜底值。
pub(crate) fn secret() -> Vec<u8> {
    std::env::var("JWT_SECRET_KEY")
        .unwrap_or_else(|_| "local-dev-secret-key".into())
        .into_bytes()
}

/// 签发 token（与 Python create_token 等价语义）
pub fn create_token(username: &str, role: &str) -> Result<String, jsonwebtoken::errors::Error> {
    let exp = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() as usize + 72 * 3600;
    encode(
        &Header::default(),
        &Claims { sub: username.to_string(), role: role.to_string(), exp },
        &EncodingKey::from_secret(&secret()),
    )
}

/// 校验 token 并返回 claims
///
/// 显式写出算法与必需声明，不用 `Validation::default()`：
/// 这是鉴权链路，语义不能依赖上游库默认值的后续版本变化
/// （HS256 与签名用的 EncodingKey 必须严格对应，避免算法混淆）。
pub fn verify_token(token: &str) -> Option<Claims> {
    let mut validation = Validation::new(Algorithm::HS256);
    validation.validate_exp = true;
    validation.required_spec_claims = ["exp".to_string()].into_iter().collect();
    decode::<Claims>(token, &DecodingKey::from_secret(&secret()), &validation)
        .ok()
        .map(|d| d.claims)
}

/// 用户存在 + bcrypt 密码校验（users 表）
pub async fn check_user(state: &AppState, username: &str, password: &str) -> Option<String> {
    let pool = state.db.raw_pool().clone();
    let username = username.to_string();
    let password = password.to_string();
    let row = tokio::task::spawn_blocking(move || -> Option<(String, String)> {
        let conn = pool.get().ok()?;
        conn.query_row(
            "SELECT password_hash, role FROM users WHERE username=?1 AND deleted_at IS NULL",
            rusqlite::params![username],
            |r| Ok((r.get(0)?, r.get(1).unwrap_or_default())),
        )
        .ok()
    })
    .await
    .ok()?;
    let (hash, role) = row?;
    if verify(&password, &hash).unwrap_or(false) {
        Some(role)
    } else {
        None
    }
}

/// 登录端点（对齐 Python /api/admin/login 响应格式）
pub async fn admin_login(State(state): State<AppState>, Json(body): Json<serde_json::Value>) -> Json<serde_json::Value> {
    let username = body["username"].as_str().unwrap_or("").to_string();
    let password = body["password"].as_str().unwrap_or("").to_string();
    // 验证码字段在迁移期不做服务端校验（Python 内存验证码库，Phase 5 前实现 Rust 版）
    match check_user(&state, &username, &password).await {
        Some(role) if role == "admin" => {
            match create_token(&username, &role) {
                Ok(token) => Json(json!({"success": true, "message": "ok", "data": {
                    "token": token, "username": username, "role": role,
                }})),
                Err(e) => Json(json!({"success": false, "message": format!("token 签发失败: {e}")})),
            }
        }
        _ => Json(json!({"success": false, "message": "账号或密码错误"})),
    }
}

/// Bearer 鉴权中间件：校验失败返回 401（与 Python 语义一致）
pub async fn auth_middleware(
    State(state): State<AppState>,
    mut req: Request,
    next: Next,
) -> Response {
    let token = req.headers()
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .unwrap_or("");
    if let Some(claims) = verify_token(token) {
        req.extensions_mut().insert(claims);
        next.run(req).await
    } else {
        let _ = state;
        (axum::http::StatusCode::UNAUTHORIZED,
         Json(json!({"detail": "未登录或登录已过期"}))).into_response()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_token_roundtrip() {
        std::env::set_var("JWT_SECRET_KEY", "test-secret");
        let token = create_token("admin1", "admin").unwrap();
        let claims = verify_token(&token).unwrap();
        assert_eq!(claims.sub, "admin1");
        assert_eq!(claims.role, "admin");
        assert!(verify_token("bad-token").is_none());
    }
}

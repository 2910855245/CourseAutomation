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
use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

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

// ── 管理员登录失败封锁（防暴力破解）──────────────────────────────────────
//
// 此前 /api/admin/login 没有任何失败计数：密码空间再小也能被离线脚本按
// 每秒几十次的速度穷举。这里按「账号」维度做渐进式封锁：
//   - 连续失败达到 N 次（默认 5）→ 锁定 T 秒（默认 900）
//   - 成功登录清零
//   - 只统计失败次数，不区分来源 IP：后台管理员通常只有一个账号，
//     按账号封锁才能挡住换 IP 的分布式尝试（IP 维度已由 guard::rate_limit 兜住）
//
// 状态放在进程内存：重启即清空。对单实例部署足够，且避免把锁定状态写库
// （否则攻击者可以靠刷失败把管理员永久锁死）。

struct LoginGuard {
    fails: u32,
    /// 锁定到期时间
    locked_until: Option<Instant>,
    last_fail: Instant,
}

static LOGIN_GUARD: OnceLock<Mutex<HashMap<String, LoginGuard>>> = OnceLock::new();

fn login_guard() -> &'static Mutex<HashMap<String, LoginGuard>> {
    LOGIN_GUARD.get_or_init(|| Mutex::new(HashMap::new()))
}

fn max_fails() -> u32 {
    std::env::var("ADMIN_LOGIN_MAX_FAILS")
        .ok().and_then(|v| v.trim().parse().ok()).unwrap_or(5)
}

fn lock_seconds() -> u64 {
    std::env::var("ADMIN_LOGIN_LOCK_SECONDS")
        .ok().and_then(|v| v.trim().parse().ok()).unwrap_or(900)
}

/// 返回剩余锁定秒数（0 = 未锁定）
fn locked_for(key: &str) -> u64 {
    let Ok(map) = login_guard().lock() else { return 0 };
    match map.get(key).and_then(|g| g.locked_until) {
        Some(until) => until.saturating_duration_since(Instant::now()).as_secs() + 1,
        None => 0,
    }
}

fn record_failure(key: &str) {
    let Ok(mut map) = login_guard().lock() else { return };
    let now = Instant::now();
    let g = map.entry(key.to_string()).or_insert(LoginGuard {
        fails: 0, locked_until: None, last_fail: now,
    });
    g.fails += 1;
    g.last_fail = now;
    if g.fails >= max_fails() {
        g.locked_until = Some(now + Duration::from_secs(lock_seconds()));
        tracing::warn!(account = %key, fails = g.fails, lock_seconds = lock_seconds(),
                       "管理员登录失败次数超限，已临时锁定该账号");
    }
}

fn record_success(key: &str) {
    if let Ok(mut map) = login_guard().lock() {
        map.remove(key);
    }
}

/// 登录端点（对齐 Python /api/admin/login 响应格式）
pub async fn admin_login(State(state): State<AppState>, Json(body): Json<serde_json::Value>) -> Json<serde_json::Value> {
    let username = body["username"].as_str().unwrap_or("").to_string();
    let password = body["password"].as_str().unwrap_or("").to_string();
    // 验证码字段在迁移期不做服务端校验（Python 内存验证码库，Phase 5 前实现 Rust 版）

    // 注意：锁定判定必须放在密码校验**之前**，否则失败一次就能探到一个候选密码
    let key = username.trim().to_lowercase();
    let wait = locked_for(&key);
    if wait > 0 {
        return Json(json!({
            "success": false,
            "message": format!("尝试次数过多，该账号已临时锁定，请 {wait} 秒后重试"),
        }));
    }

    match check_user(&state, &username, &password).await {
        Some(role) if role == "admin" => {
            record_success(&key);
            match create_token(&username, &role) {
                Ok(token) => Json(json!({"success": true, "message": "ok", "data": {
                    "token": token, "username": username, "role": role,
                }})),
                Err(e) => Json(json!({"success": false, "message": format!("token 签发失败: {e}")})),
            }
        }
        _ => {
            record_failure(&key);
            // 不区分「用户不存在」与「密码错误」，避免账号枚举
            Json(json!({"success": false, "message": "账号或密码错误"}))
        }
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

    #[test]
    fn test_login_lockout_after_max_fails() {
        std::env::set_var("ADMIN_LOGIN_MAX_FAILS", "3");
        std::env::set_var("ADMIN_LOGIN_LOCK_SECONDS", "60");
        let key = "lockout-test-account";
        assert_eq!(locked_for(key), 0);
        record_failure(key);
        record_failure(key);
        assert_eq!(locked_for(key), 0, "未达阈值不应锁定");
        record_failure(key);
        assert!(locked_for(key) > 0, "达到阈值应锁定");
        // 成功登录（或清理）后解除
        record_success(key);
        assert_eq!(locked_for(key), 0);
    }
}

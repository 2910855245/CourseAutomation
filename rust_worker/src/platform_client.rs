//! 统一平台 HTTP 客户端 — cookie jar + UA + 全局限速 + 会话失效统一检测
//!
//! 此前 login.rs / scan.rs / study.rs / exam.rs / school_exam.rs 各自构建 client、
//! 各自手拼 `Cookie:` 头、各自判断会话是否失效，规则分散易漂移。本模块收敛：
//!   - `build_client`：统一 TLS/UA/重定向策略（可选持久 cookie jar）
//!   - `get_cookie_header`：从 cookie jar 提取 `Cookie` 头（验证码会话依赖）
//!   - `session_invalid`：统一「登录态失效」判定（302 跳登录 / 登录页特征）

use std::sync::Arc;
use std::time::{Duration, Instant};

use reqwest::cookie::{CookieStore, Jar};
use reqwest::header::{HeaderMap, HeaderValue, COOKIE};
use reqwest::Client;

/// 桌面 Chrome UA（平台按 UA 分流，移动端 UA 会命中不同渲染分支）
pub const DESKTOP_UA: &str =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

/// 短 UA（与原 study.rs / scan.rs 一致，保持行为不变）
pub const SHORT_UA: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36";

/// 全局请求间隔：跨模块共享，任意两个出站请求间隔 ≥ 0.5s
static SPACING: tokio::sync::Mutex<Option<Instant>> = tokio::sync::Mutex::const_new(None);
const REQUEST_SPACING_SECS: f64 = 0.5;

/// 出站超时。原先所有 client 都没设超时：平台无响应或 TCP 半开时
/// `send().await` 会永久挂住，占死队列 worker 槽位（`active` 计数不归零）
/// 与扫描并发许可，最终导致整条队列停摆且无任何日志。
pub const CONNECT_TIMEOUT: Duration = Duration::from_secs(10);
pub const REQUEST_TIMEOUT: Duration = Duration::from_secs(45);

/// 平台级限速门（对同一目标站的请求串行排队）
pub async fn wait_rate_limit() {
    let mut guard = SPACING.lock().await;
    let now = Instant::now();
    if let Some(next) = *guard {
        if now < next {
            tokio::time::sleep(next - now).await;
        }
    }
    *guard = Some(Instant::now() + Duration::from_secs_f64(REQUEST_SPACING_SECS));
}

/// 构建平台 client。
/// - `redirect_none = true`：登录/上报链路需要观察 302（会话失效信号），不自动跟随
/// - `jar = Some`：启用显式 cookie jar（验证码会话与登录 cookie 同源，必须持久化）
/// - `jar = None`：无 cookie 存储（调用方自行携带 `Cookie` 头，避免与 jar 重复发送）
pub fn build_client(redirect_none: bool, jar: Option<Arc<Jar>>) -> Client {
    build_client_with_ua(DESKTOP_UA, redirect_none, jar)
}

/// 同上，但可指定 UA（study 上报链路沿用短 UA，保持与原实现一致）
pub fn build_client_with_ua(ua: &str, redirect_none: bool, jar: Option<Arc<Jar>>) -> Client {
    let mut b = Client::builder()
        .danger_accept_invalid_certs(true)
        .connect_timeout(CONNECT_TIMEOUT)
        .timeout(REQUEST_TIMEOUT)
        .user_agent(ua);
    b = if redirect_none {
        b.redirect(reqwest::redirect::Policy::none())
    } else {
        b.redirect(reqwest::redirect::Policy::limited(10))
    };
    if let Some(j) = jar {
        b = b.cookie_provider(j);
    }
    b.build().expect("构建平台 HTTP client 失败")
}

/// 按**字符**截断，用于日志/错误信息预览。
/// 直接 `&s[..n]` 是字节切片，遇到多字节字符（外部响应里常含中文）
/// 且切点落在字符中段时会 panic。
pub fn preview(s: &str, max_chars: usize) -> String {
    s.chars().take(max_chars).collect()
}

/// 从 cookie jar 提取 `Cookie` 请求头值（平台把会话 token 种在验证码响应里，
/// 登录成功响应本身不带 set-cookie，必须从 jar 反向提取）
pub fn jar_cookie_str(jar: &Jar, url: &str) -> String {
    url.parse::<reqwest::Url>()
        .ok()
        .and_then(|u| jar.cookies(&u))
        .and_then(|v| v.to_str().ok().map(String::from))
        .unwrap_or_default()
}

/// 把 cookie 字符串塞进 `HeaderMap`（统一手拼 `Cookie:` 头的写法）
pub fn cookie_headers(cookie: &str) -> HeaderMap {
    let mut h = HeaderMap::new();
    if let Ok(v) = HeaderValue::from_str(cookie) {
        h.insert(COOKIE, v);
    }
    h
}

/// 登录态失效统一判定：
/// - HTTP 302/303（未跟随重定向）→ 跳转登录页
/// - 200 但响应体是登录页特征（登录表单 / 密码框）
/// - 平台明确的会话异常文案
pub fn session_invalid(status: u16, body: &str) -> bool {
    if status == 302 || status == 303 {
        return true;
    }
    body.contains("name=\"password\"")
        || body.contains("id=\"password\"")
        || body.contains("账号密码不正确")
        || body.contains("<?xml") // 部分网关的裸 XML 错误页
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_session_invalid() {
        assert!(session_invalid(302, ""));
        assert!(session_invalid(200, "<input name=\"password\">"));
        assert!(!session_invalid(200, "<div class=\"user-course\"></div>"));
    }

    #[test]
    fn test_cookie_headers() {
        let h = cookie_headers("token=sid.abc");
        assert_eq!(h.get(COOKIE).unwrap().to_str().unwrap(), "token=sid.abc");
    }
}

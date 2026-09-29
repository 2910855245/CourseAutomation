//! 边界防护：按客户端 IP 限流 + 安全响应头
//!
//! 本模块只做「入口处的粗粒度防线」，不替代业务鉴权：
//!   - [`rate_limit`]：滑动窗口计数，超限 429 + Retry-After。目的是把
//!     暴力破解、批量下单、开放代理式调用（`/api/courses/scan` 会拿用户
//!     凭据去登录第三方平台）这类行为的成本抬起来。
//!   - [`security_headers`]：防点击劫持 / MIME 嗅探 / 外部资源注入。
//!
//! ## 客户端 IP 的来源（重要）
//!
//! 服务默认只监听 127.0.0.1，线上一定在反向代理之后，所以需要读
//! `X-Forwarded-For` 才能拿到真实访客 IP。但 XFF 是**可伪造**的：任何能直连
//! 本服务的人都能改它来轮换身份、绕过限流。
//!
//! 因此这里采取「只信任来自回环地址的 XFF」策略：只有当 TCP 对端就是本机
//! （说明对面是同一台机器上的 nginx/caddy）时才采用 XFF，否则一律用 socket
//! 对端地址。这样直接把端口暴露出去也无法伪造来源。
//! 若反向代理部署在另一台机器上，请设 `RATE_LIMIT_TRUST_PROXY=false`
//! （此时所有访客共用一个桶，限流阈值需相应放大）。

use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use axum::extract::{ConnectInfo, Request, State};
use axum::http::{header, HeaderValue, StatusCode};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::json;

/// 窗口内计数（固定窗口，够用且无需存时间序列）
struct Window {
    start: Instant,
    count: u32,
}

pub struct RateLimiter {
    buckets: Mutex<HashMap<String, Window>>,
    /// 普通接口：每 IP 每窗口允许的请求数
    limit: u32,
    /// 敏感接口：更严的阈值
    sensitive_limit: u32,
    window: Duration,
    enabled: bool,
    trust_proxy: bool,
}

/// 敏感接口前缀：会消耗外部资源 / 触发第三方登录 / 写库 / 涉及金钱
const SENSITIVE_PREFIXES: &[&str] = &[
    "/api/admin/login",
    "/api/courses/scan",
    "/api/courses/relogin",
    "/api/orders/batch",
    "/api/payment/",
    "/api/ypay/create",
    "/api/ypay/batch-create",
    "/api/exam/solve",
];

/// 豁免路径：内部推送（已用 worker token 鉴权，且是进度主干道）、健康检查、
/// 静态资源（不经过本中间件的也会走这里，统一豁免更省心）
const EXEMPT_PREFIXES: &[&str] = &[
    "/api/progress/live/push",
    "/health",
    "/static/",
    "/assets/",
];

fn env_u32(key: &str, default: u32) -> u32 {
    std::env::var(key).ok().and_then(|v| v.trim().parse().ok()).unwrap_or(default)
}

fn env_bool(key: &str, default: bool) -> bool {
    std::env::var(key)
        .map(|v| matches!(v.trim().to_lowercase().as_str(), "1" | "true" | "yes" | "on"))
        .unwrap_or(default)
}

impl RateLimiter {
    pub fn from_env() -> Arc<Self> {
        let window = Duration::from_secs(env_u32("RATE_LIMIT_WINDOW_SECONDS", 60).max(1) as u64);
        let limit = env_u32("RATE_LIMIT_REQUESTS", 600).max(1);
        // 默认取全局阈值的 1/10，且不超过 60：登录/下单这类操作人工不可能高频
        let sensitive = env_u32("RATE_LIMIT_SENSITIVE", (limit / 10).clamp(10, 60));
        Arc::new(Self {
            buckets: Mutex::new(HashMap::new()),
            limit,
            sensitive_limit: sensitive,
            window,
            enabled: env_bool("RATE_LIMIT_ENABLED", true),
            trust_proxy: env_bool("RATE_LIMIT_TRUST_PROXY", true),
        })
    }

    fn limit_for(&self, path: &str) -> u32 {
        if SENSITIVE_PREFIXES.iter().any(|p| path.starts_with(p)) {
            self.sensitive_limit
        } else {
            self.limit
        }
    }

    /// 计数并判断是否放行，返回 (放行, 需等待秒数)
    fn check(&self, key: &str, limit: u32) -> (bool, u64) {
        let now = Instant::now();
        let mut buckets = match self.buckets.lock() {
            Ok(g) => g,
            // 锁中毒：宁可不限流也不要让整个服务 500
            Err(_) => return (true, 0),
        };
        // 低频清理：桶数量超过阈值时回收过期条目，避免被大量伪造来源撑爆内存
        if buckets.len() > 8192 {
            let window = self.window;
            buckets.retain(|_, w| now.duration_since(w.start) < window);
        }
        let entry = buckets.entry(key.to_string()).or_insert(Window { start: now, count: 0 });
        if now.duration_since(entry.start) >= self.window {
            entry.start = now;
            entry.count = 0;
        }
        entry.count += 1;
        if entry.count > limit {
            let elapsed = now.duration_since(entry.start);
            let left = self.window.saturating_sub(elapsed);
            return (false, left.as_secs().max(1));
        }
        (true, 0)
    }
}

/// 从 socket 对端 + （可信时）XFF 推导客户端标识
fn client_key(req: &Request, trust_proxy: bool) -> String {
    let peer = req
        .extensions()
        .get::<ConnectInfo<SocketAddr>>()
        .map(|c| c.0);

    if trust_proxy {
        // 只有对端是本机时才采信 XFF：外部直连无法伪造来源
        if peer.map(|p| p.ip().is_loopback()).unwrap_or(false) {
            if let Some(xff) = req.headers().get("x-forwarded-for").and_then(|v| v.to_str().ok()) {
                if let Some(first) = xff.split(',').next() {
                    let first = first.trim();
                    if !first.is_empty() {
                        return first.to_string();
                    }
                }
            }
            if let Some(real) = req.headers().get("x-real-ip").and_then(|v| v.to_str().ok()) {
                let real = real.trim();
                if !real.is_empty() {
                    return real.to_string();
                }
            }
        }
    }
    peer.map(|p| p.ip().to_string()).unwrap_or_else(|| "unknown".into())
}

/// 限流中间件
pub async fn rate_limit(
    State(limiter): State<Arc<RateLimiter>>,
    req: Request,
    next: Next,
) -> Response {
    if !limiter.enabled {
        return next.run(req).await;
    }
    let path = req.uri().path().to_string();
    if EXEMPT_PREFIXES.iter().any(|p| path.starts_with(p)) {
        return next.run(req).await;
    }

    let ip = client_key(&req, limiter.trust_proxy);
    // 敏感与非敏感分开计数：一次登录风暴不应该把同一 IP 的正常浏览也拖下水
    let limit = limiter.limit_for(&path);
    let bucket = if limit == limiter.limit {
        format!("{ip}|normal")
    } else {
        format!("{ip}|sensitive")
    };
    let (allowed, retry_after) = limiter.check(&bucket, limit);
    if !allowed {
        tracing::warn!(ip = %ip, path = %path, retry_after, "触发限流");
        let mut resp = Json(json!({
            "success": false,
            "message": "请求过于频繁，请稍后再试",
        }))
        .into_response();
        *resp.status_mut() = StatusCode::TOO_MANY_REQUESTS;
        if let Ok(v) = HeaderValue::from_str(&retry_after.to_string()) {
            resp.headers_mut().insert(header::RETRY_AFTER, v);
        }
        return resp;
    }
    next.run(req).await
}

/// 安全响应头。CSP 允许多处 env 覆盖（`CSP_POLICY`），避免过严策略把前端
/// 打死时只能改代码重新编译。
///
/// 说明两点取舍：
///   - `script-src`/`style-src` 必须带 `'unsafe-inline'`：index.html 里有一段
///     必须在样式表之前执行的主题脚本（防暗色白闪），且 Vue 的 `:style`
///     绑定会产生内联样式。去掉它首屏会闪白/样式丢失。CSP 的真正价值在这里
///     转移到 `frame-ancestors`/`object-src`/`base-uri`/外部源收敛上。
///   - `img-src` 需要 `data:`（支付二维码是 data URL）与 `blob:`。
const DEFAULT_CSP: &str = "default-src 'self'; \
     script-src 'self' 'unsafe-inline'; \
     style-src 'self' 'unsafe-inline'; \
     img-src 'self' data: blob:; \
     font-src 'self' data:; \
     connect-src 'self' ws: wss:; \
     frame-ancestors 'none'; \
     object-src 'none'; \
     base-uri 'self'; \
     form-action 'self'";

pub async fn security_headers(req: Request, next: Next) -> Response {
    // 是否经由 HTTPS 代理（HSTS 只在 HTTPS 下有意义，HTTP 下发了也无效）
    let https = req
        .headers()
        .get("x-forwarded-proto")
        .and_then(|v| v.to_str().ok())
        .map(|v| v.eq_ignore_ascii_case("https"))
        .unwrap_or(false);

    let mut resp = next.run(req).await;
    let h = resp.headers_mut();
    let set = |h: &mut axum::http::HeaderMap, k: header::HeaderName, v: &str| {
        if let Ok(val) = HeaderValue::from_str(v) {
            h.insert(k, val);
        }
    };
    set(h, header::X_CONTENT_TYPE_OPTIONS, "nosniff");
    set(h, header::X_FRAME_OPTIONS, "DENY");
    set(h, header::REFERRER_POLICY, "no-referrer");
    set(h, header::HeaderName::from_static("permissions-policy"),
        "geolocation=(), microphone=(), camera=(), payment=()");

    if !h.contains_key(header::CONTENT_SECURITY_POLICY) {
        let csp = std::env::var("CSP_POLICY").unwrap_or_else(|_| DEFAULT_CSP.to_string());
        set(h, header::CONTENT_SECURITY_POLICY, &csp);
    }
    if https {
        set(h, header::STRICT_TRANSPORT_SECURITY, "max-age=31536000; includeSubDomains");
    }
    resp
}

#[cfg(test)]
mod tests {
    use super::*;

    fn limiter(enabled: bool) -> RateLimiter {
        RateLimiter {
            buckets: Mutex::new(HashMap::new()),
            limit: 3,
            sensitive_limit: 2,
            window: Duration::from_secs(60),
            enabled,
            trust_proxy: true,
        }
    }

    #[test]
    fn test_window_blocks_after_limit() {
        let l = limiter(true);
        assert!(l.check("ip|normal", 3).0);
        assert!(l.check("ip|normal", 3).0);
        assert!(l.check("ip|normal", 3).0);
        let (allowed, retry) = l.check("ip|normal", 3);
        assert!(!allowed, "第 4 次应被拦截");
        assert!(retry >= 1, "应给出 Retry-After");
    }

    #[test]
    fn test_buckets_are_isolated_per_ip() {
        let l = limiter(true);
        for _ in 0..3 {
            assert!(l.check("a|normal", 3).0);
        }
        assert!(!l.check("a|normal", 3).0);
        // 另一个 IP 不受影响
        assert!(l.check("b|normal", 3).0);
    }

    #[test]
    fn test_sensitive_threshold_is_stricter() {
        let l = RateLimiter { limit: 10, ..limiter(true) };
        assert_eq!(l.limit_for("/api/orders/batch"), 2);
        assert_eq!(l.limit_for("/api/admin/login"), 2);
        assert_eq!(l.limit_for("/api/orders/ORD-1"), 10);
        assert_eq!(l.limit_for("/api/announcement"), 10);
    }
}

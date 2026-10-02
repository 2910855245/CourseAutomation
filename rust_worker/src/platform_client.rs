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

/// 生效的请求间隔（秒）。默认 0.5；`PLATFORM_REQUEST_SPACING_SECS` 可覆盖
/// （E2E 测试打 mock 平台时置 0，否则几十次上报会被 0.5s 串行拖到十几秒）。
fn spacing_secs() -> f64 {
    std::env::var("PLATFORM_REQUEST_SPACING_SECS")
        .ok()
        .and_then(|v| v.trim().parse::<f64>().ok())
        .filter(|s| (0.0..=10.0).contains(s))
        .unwrap_or(REQUEST_SPACING_SECS)
}

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
    *guard = Some(Instant::now() + Duration::from_secs_f64(spacing_secs()));
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

/// IP 是否属于"不该被服务端主动请求"的网段：
/// 回环（127/::1）、私有（10/172.16/192.168）、链路本地（169.254 —— 云元数据
/// 169.254.169.254 就在这里）、CGNAT（100.64/10）、组播/保留（>=224）、
/// 未指定（0.0.0.0/::）、IPv6 ULA（fc00::/7）与 IPv6 链路本地（fe80::/10）。
pub fn is_blocked_ip(ip: std::net::IpAddr) -> bool {
    use std::net::IpAddr;
    match ip {
        IpAddr::V4(v4) => {
            let o = v4.octets();
            v4.is_loopback()
                || v4.is_private()
                || v4.is_link_local()
                || v4.is_broadcast()
                || v4.is_unspecified()
                || o[0] == 0
                || (o[0] == 100 && (64..128).contains(&o[1]))
                || o[0] >= 224
        }
        IpAddr::V6(v6) => {
            let s = v6.segments();
            v6.is_loopback()
                || v6.is_unspecified()
                || (s[0] & 0xfe00) == 0xfc00
                || (s[0] & 0xffc0) == 0xfe80
                || v6.to_ipv4_mapped().map(|v| is_blocked_ip(IpAddr::V4(v))).unwrap_or(false)
        }
    }
}

/// 出站目标安全阀：阻断 SSRF 打本机/内网/云元数据。
///
/// 为什么需要：域名监控抓的是**平台首页里出现的链接**、媒体探测抓的是
/// **平台响应里的视频地址** —— 都是外部可控输入。没有这层，被抓方（或攻陷了
/// 学校站的一方）就能让我们去请求 `http://127.0.0.1:17017/...`（本服务，
/// 绕过 nginx 的鉴权边界）或 `http://169.254.169.254/`（云厂元数据，可换到
/// 实例凭证）。域名监控的目标还直接由管理员填写，同样属于可控输入。
///
/// 做法两步：字面 IP 直接判；域名先解析，任一结果落在禁网段就拒。
/// 局限：挡不住 DNS rebinding（解析与真正建连是两次查询）—— 但那是要自建
/// 域名+精确时序的高级手法，这里先把"直接写内网地址"这条廉价通道关掉。
pub async fn outbound_allowed(url: &str) -> bool {
    let Ok(u) = url.parse::<reqwest::Url>() else { return false };
    if !matches!(u.scheme(), "http" | "https") {
        return false;
    }
    let Some(host) = u.host_str() else { return false };
    // url crate 的 host_str 对 IPv6 会带方括号（[::1]），解析前先剥掉
    if let Ok(ip) = host.trim_start_matches('[').trim_end_matches(']').parse::<std::net::IpAddr>() {
        return !is_blocked_ip(ip);
    }
    let h = host.to_lowercase();
    // 无点主机名（localhost、容器短名、内网搜索域）一律拒 —— 正常学校域名都带点
    if !h.contains('.') {
        return false;
    }
    let port = u.port_or_known_default().unwrap_or(80);
    // 传 own 的 String：借用 h 会让 lookup_host 的 future 跨 await 持有局部借用，
    // borrow checker 直接拒（临时值活不过 await）
    match tokio::net::lookup_host((h.clone(), port)).await {
        Ok(addrs) => {
            let mut any = false;
            for a in addrs {
                any = true;
                if is_blocked_ip(a.ip()) {
                    tracing::warn!(host = %h, ip = %a.ip(), "出站目标解析到内网网段，已拒绝");
                    return false;
                }
            }
            any
        }
        // 解析不了就交给请求本身去失败：不把"DNS 抽风"当攻击，
        // 否则一次解析超时会把正常的域名监控整轮掐掉。
        Err(_) => true,
    }
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

    /// SSRF 安全阀：内网/元数据网段必须全挡，公网地址必须放行。
    #[test]
    fn test_is_blocked_ip() {
        for s in ["127.0.0.1", "10.0.0.1", "172.16.5.4", "192.168.1.1",
                  "169.254.169.254", "100.64.0.1", "0.0.0.0", "224.0.0.1"] {
            assert!(is_blocked_ip(s.parse().unwrap()), "{s} 应被拒");
        }
        for s in ["::1", "fd00::1", "fe80::1", "::ffff:127.0.0.1"] {
            assert!(is_blocked_ip(s.parse().unwrap()), "{s} 应被拒");
        }
        for s in ["8.8.8.8", "1.1.1.1", "223.5.5.5", "2400:3200::1"] {
            assert!(!is_blocked_ip(s.parse().unwrap()), "{s} 应放行");
        }
    }

    /// 协议与字面 IP 的判断不依赖网络（不测域名解析，避免测试机 DNS 影响结果）。
    #[tokio::test]
    async fn test_outbound_allowed_scheme_and_ip() {
        assert!(!outbound_allowed("file:///etc/passwd").await);
        assert!(!outbound_allowed("gopher://x/").await);
        assert!(!outbound_allowed("不是 URL").await);
        // 本机后端端口与云元数据是最危险的两个目标
        assert!(!outbound_allowed("http://127.0.0.1:17017/api/admin/config").await);
        assert!(!outbound_allowed("http://169.254.169.254/latest/meta-data/").await);
        assert!(!outbound_allowed("http://[::1]:17017/").await);
        // 无点主机名（内网短名）一律拒
        assert!(!outbound_allowed("http://localhost/x").await);
        assert!(outbound_allowed("http://8.8.8.8/").await);
    }
}

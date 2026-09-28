//! 学校平台会话管理 — 内存缓存 + cookie 复用 + 失效才重新登录
//!
//! 问题背景：此前每次扫描/任务都重新走一遍「取验证码 → OCR → 登录」，
//! 频繁登录会触发平台风控（甚至锁号），且浪费大量请求。
//!
//! 本模块提供 `get_session`：先校验缓存/落盘 cookie 是否仍然有效
//! （GET /user/index 返回 200 且非登录页），有效直接复用；无效才登录。
//! 登录成功后同时回写内存缓存与 `data/accounts/<user>/cookies/<平台>.json`。

use std::path::PathBuf;
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use anyhow::Result;
use dashmap::DashMap;

use crate::login::{login_school, SchoolSession};
use crate::platform_client as pc;

/// 内存缓存条目
struct Cached {
    cookie_str: String,
    base_url: String,
    last_used: Instant,
}

/// 缓存有效期：超过则重新校验（校验失败即重新登录）
const CACHE_TTL: Duration = Duration::from_secs(30 * 60);

static CACHE: OnceLock<DashMap<String, Cached>> = OnceLock::new();

fn cache() -> &'static DashMap<String, Cached> {
    CACHE.get_or_init(DashMap::new)
}

fn key_of(username: &str, base_url: &str) -> String {
    format!("{username}|{}", base_url.trim_end_matches('/'))
}

/// base_url → 平台中文名（cookie 落盘文件名，兼容历史 Python 布局）
pub fn platform_name_for_url(base_url: &str) -> String {
    let u = base_url.to_lowercase();
    if u.contains("duxingkej") {
        "劳动课程测评考试平台".to_string()
    } else if u.contains("chaoxiankeji") {
        "公益课程平台".to_string()
    } else {
        "在线课程测评考试平台".to_string()
    }
}

fn cookie_path(username: &str, base_url: &str) -> PathBuf {
    PathBuf::from("data")
        .join("accounts")
        .join(username)
        .join("cookies")
        .join(format!("{}.json", platform_name_for_url(base_url)))
}

/// 落盘 cookie（`[{name,value,domain,path}]`，与历史 Python 文件格式一致）
pub fn save_cookie_file(username: &str, base_url: &str, cookie_str: &str) -> Result<()> {
    let path = cookie_path(username, base_url);
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let pairs: Vec<serde_json::Value> = cookie_str
        .split(';')
        .filter_map(|kv| {
            let (name, value) = kv.trim().split_once('=')?;
            Some(serde_json::json!({"name": name, "value": value, "domain": "", "path": "/"}))
        })
        .collect();
    std::fs::write(&path, serde_json::to_string_pretty(&pairs)?)?;
    Ok(())
}

/// 读回落盘 cookie
pub fn load_cookie_file(username: &str, base_url: &str) -> Option<String> {
    let text = std::fs::read_to_string(cookie_path(username, base_url)).ok()?;
    let arr: Vec<serde_json::Value> = serde_json::from_str(&text).ok()?;
    let cookie = arr
        .iter()
        .filter_map(|v| {
            let n = v["name"].as_str()?;
            let val = v["value"].as_str()?;
            Some(format!("{n}={val}"))
        })
        .collect::<Vec<_>>()
        .join("; ");
    if cookie.is_empty() {
        None
    } else {
        Some(cookie)
    }
}

/// 校验 cookie 是否仍然有效（GET /user/index）
/// 200 且非登录页 → 有效；302/登录页特征 → 失效
pub async fn cookie_valid(base_url: &str, cookie: &str) -> bool {
    if cookie.is_empty() {
        return false;
    }
    let client = pc::build_client(true, None);
    let url = format!("{}/user/index", base_url.trim_end_matches('/'));
    match client.get(&url).headers(pc::cookie_headers(cookie)).send().await {
        Ok(resp) => {
            let status = resp.status().as_u16();
            if status != 200 {
                return false;
            }
            let body = resp.text().await.unwrap_or_default();
            // 课程列表页特征：user-course 容器存在即视为已登录态
            !pc::session_invalid(status, &body) && !body.contains("SQLSTATE")
        }
        Err(_) => false,
    }
}

/// 写入内存缓存
pub fn remember(username: &str, base_url: &str, cookie_str: &str) {
    cache().insert(
        key_of(username, base_url),
        Cached {
            cookie_str: cookie_str.to_string(),
            base_url: base_url.trim_end_matches('/').to_string(),
            last_used: Instant::now(),
        },
    );
}

/// 主动失效（检测到会话过期时调用，下次请求会重新登录）
pub fn invalidate(username: &str, base_url: &str) {
    cache().remove(&key_of(username, base_url));
}

/// 取会话：缓存 → 落盘 → 重新登录（逐级回退，全链路先校验后用）
pub async fn get_session(base_url: &str, username: &str, password: &str) -> Result<SchoolSession> {
    let base = base_url.trim_end_matches('/').to_string();

    // 1) 内存缓存（TTL 内且未失效）
    if let Some(e) = cache().get(&key_of(username, &base)) {
        if e.last_used.elapsed() < CACHE_TTL {
            let cookie = e.cookie_str.clone();
            drop(e);
            if cookie_valid(&base, &cookie).await {
                return Ok(SchoolSession { cookie_str: cookie, base_url: base });
            }
            invalidate(username, &base);
        }
    }

    // 2) 落盘 cookie（进程重启后仍可复用）
    if let Some(cookie) = load_cookie_file(username, &base) {
        if cookie_valid(&base, &cookie).await {
            remember(username, &base, &cookie);
            return Ok(SchoolSession { cookie_str: cookie, base_url: base });
        }
    }

    // 3) 重新登录（本地 OCR）
    let session = login_school(&base, username, password).await?;
    remember(username, &base, &session.cookie_str);
    // 落盘失败不影响主流程
    if let Err(e) = save_cookie_file(username, &base, &session.cookie_str) {
        tracing::warn!(error = %e, "cookie 落盘失败");
    }
    Ok(session)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_platform_name() {
        assert_eq!(platform_name_for_url("https://cdcass.taiskeji.com"), "在线课程测评考试平台");
        assert_eq!(platform_name_for_url("https://cdcas.duxingkej.com"), "劳动课程测评考试平台");
        assert_eq!(platform_name_for_url("https://cdcas.chaoxiankeji.com"), "公益课程平台");
    }

    #[test]
    fn test_key_of_normalizes_trailing_slash() {
        assert_eq!(key_of("u", "https://a.com/"), key_of("u", "https://a.com"));
    }
}

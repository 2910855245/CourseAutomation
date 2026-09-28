//! 学校平台登录（Rust 版）— 协议对齐 services/multi_platform_auth.login_single_platform
//!
//! 验证码识别使用本地 OCR 引擎（crate::ocr），不依赖任何 HTTP sidecar。
//! 登录成功后返回 cookie_str 供后续扫描/刷课使用。重试上限 10 次（与 Python 一致）。

use anyhow::{bail, Context, Result};
use reqwest::cookie::CookieStore;
use reqwest::Client;
use std::sync::Arc;

use crate::ocr;

pub struct SchoolSession {
    pub cookie_str: String,
    pub base_url: String,
}

/// 构建带显式 cookie jar 的 client。平台把会话 cookie（token=sid.xxx）
/// 放在取验证码的响应里，登录成功响应本身不带 set-cookie，
/// 因此必须从 jar 里提取，返回 jar 供调用方读取。
fn make_client() -> (Client, Arc<reqwest::cookie::Jar>) {
    let jar = Arc::new(reqwest::cookie::Jar::default());
    let client = Client::builder()
        .danger_accept_invalid_certs(true)
        .user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        .redirect(reqwest::redirect::Policy::none())
        .cookie_provider(Arc::clone(&jar)) // 验证码与 cookie 中的 session 绑定，必须持久化
        .build()
        .expect("构建登录 client 失败");
    (client, jar)
}

/// 登录学校平台（对齐 login_single_platform 主流程）
/// 验证码由本地 OCR 引擎识别；引擎不可用时验证码留空，
/// 由平台返回"验证码有误"触发重取。
pub async fn login_school(base_url: &str, username: &str, password: &str) -> Result<SchoolSession> {
    let base = base_url.trim_end_matches('/').to_string();
    let login_url = format!("{base}/user/login");
    let captcha_url = format!("{base}/service/code");
    let (client, jar) = make_client();

    // 注：旧逻辑会先 GET /user/login 预检提取 <select id="schoolId">，
    // 现行平台登录页已无该字段（schoolId 为 localStorage 隐藏项），预检纯属
    // 浪费一次整页请求，已移除。school_ids 恒为 None，不会附加 schoolId。
    let school_ids: Option<Vec<String>> = None;
    let mut school_id_index = 0usize;

    for _attempt in 0..10 {
        // 获取验证码图片
        let img = client.get(&captcha_url)
            .header("Referer", &login_url)
            .header("X-Requested-With", "XMLHttpRequest")
            .send().await
            .context("获取验证码失败")?
            .bytes().await
            .context("验证码读取失败")?;

        // 本地 OCR 识别（CPU 密集，放阻塞线程池）
        let code = if let Ok(engine) = ocr::engine() {
            let bytes = img.to_vec();
            tokio::task::spawn_blocking(move || engine.recognize(&bytes))
                .await.ok().and_then(|r| r.ok()).unwrap_or_default()
        } else {
            String::new()
        };

        let mut form = vec![
            ("username", username.to_string()),
            ("password", password.to_string()),
            ("code", code),
            ("redirect", String::new()),
            ("remember", "on".to_string()),
        ];
        if let Some(ids) = &school_ids {
            if school_id_index < ids.len() {
                form.push(("schoolId", ids[school_id_index].clone()));
            }
        }

        let resp = client.post(&login_url)
            .header("Referer", &login_url)
            .header("X-Requested-With", "XMLHttpRequest")
            .form(&form)
            .send().await
            .context("登录请求失败")?;

        let status = resp.status().as_u16();
        let text = resp.text().await.unwrap_or_default();

        if text.contains("验证码有误") || text.contains("验证码错误") {
            continue;
        }
        // 登录成功两种形态：302 跳转（老版）或 200 + {"status":true,...}（yee ajax）
        if status == 302 || (text.contains("\"status\":true") && text.contains("登录成功")) {
            // 会话 cookie 是取验证码时种进 jar 的（token=sid.xxx），
            // 登录响应本身不带 set-cookie，从 jar 提取。
            let url: reqwest::Url = base.parse().context("base_url 解析失败")?;
            let cookie_str = jar.cookies(&url)
                .and_then(|h| h.to_str().ok().map(String::from))
                .unwrap_or_default();
            if cookie_str.is_empty() {
                bail!("登录成功但未获取到 cookie");
            }
            return Ok(SchoolSession { cookie_str, base_url: base });
        }
        // 密码错误/账号锁定类：立即终止，避免重试循环触发平台 5 次锁号
        // （实测平台文案为「账号密码不正确」「尝试密码错误超过5次，账号已被锁定」）
        if text.contains("密码错误") || text.contains("账号或密码") || text.contains("用户名或密码")
            || text.contains("账号密码不正确") || text.contains("已被锁定") || text.contains("账号锁定") {
            bail!("登录失败: {}", {
                let msg = json_try_msg(&text);
                if msg.is_empty() { "账号或密码错误".to_string() } else { msg }
            });
        }
        let _ = school_id_index; // 保留变量避免大改，school_ids 恒 None 不会触达
    }
    bail!("登录失败: 重试10次未成功")
}

/// 从平台 JSON 响应中提取 msg 字段（{"status":false,"msg":"..."}）
fn json_try_msg(text: &str) -> String {
    serde_json::from_str::<serde_json::Value>(text)
        .ok()
        .and_then(|v| v["msg"].as_str().map(String::from))
        .unwrap_or_default()
}

//! 学校平台登录（Rust 版）— 协议对齐 services/multi_platform_auth.login_single_platform
//!
//! 验证码识别调用 OCR sidecar（HTTP），登录成功后返回 cookie_str 供后续
//! 扫描/刷课使用。重试上限 10 次（与 Python 一致）。

use anyhow::{bail, Context, Result};
use base64::Engine;
use regex::Regex;
use reqwest::Client;

pub struct SchoolSession {
    pub cookie_str: String,
    pub base_url: String,
}

fn make_client() -> Client {
    Client::builder()
        .danger_accept_invalid_certs(true)
        .user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .expect("构建登录 client 失败")
}

/// 提取登录页 schoolId 选项（对齐 _extract_school_ids）
fn extract_school_ids(html: &str) -> Option<Vec<String>> {
    let sel = Regex::new(r#"<select[^>]*id="schoolId"[^>]*>(.*?)</select>"#).unwrap();
    let opt = Regex::new(r#"<option[^>]*value="([^"]*)"[^>]*>"#).unwrap();
    let body = sel.captures(html)?.get(1)?.as_str();
    let ids: Vec<String> = opt.captures_iter(body)
        .filter_map(|c| c.get(1))
        .map(|m| m.as_str().to_string())
        .filter(|v| !v.is_empty())
        .collect();
    if ids.is_empty() { None } else { Some(ids) }
}

/// 合并 Set-Cookie 头到 cookie 字典
fn merge_cookies(cookies: &mut std::collections::HashMap<String, String>, set_cookie: &str) {
    for pair in set_cookie.split(';') {
        if let Some((k, v)) = pair.split_once('=') {
            let k = k.trim();
            let v = v.trim();
            if !k.is_empty() && !v.is_empty() && !v.eq_ignore_ascii_case("deleted") {
                cookies.insert(k.to_string(), v.to_string());
            }
        }
    }
}

/// 登录学校平台（对齐 login_single_platform 主流程）
pub async fn login_school(base_url: &str, username: &str, password: &str,
                          ocr_url: &str) -> Result<SchoolSession> {
    let base = base_url.trim_end_matches('/').to_string();
    let login_url = format!("{base}/user/login");
    let captcha_url = format!("{base}/service/code");
    let client = make_client();

    // 预检登录页，提取 schoolId 选项
    let mut school_ids: Option<Vec<String>> = None;
    let mut school_id_index = 0usize;
    if let Ok(resp) = client.get(&login_url).send().await {
        if let Ok(html) = resp.text().await {
            school_ids = extract_school_ids(&html);
        }
    }

    for _attempt in 0..10 {
        // 获取验证码图片
        let img = client.get(&captcha_url)
            .header("Referer", &login_url)
            .send().await
            .context("获取验证码失败")?
            .bytes().await
            .context("验证码读取失败")?;
        let b64 = base64::engine::general_purpose::STANDARD.encode(&img);

        // OCR sidecar 识别（协议与 ocr_sidecar.py /ocr 一致）
        let code = if ocr_url.is_empty() {
            String::new()
        } else {
            let resp: serde_json::Value = client.post(format!("{}/ocr", ocr_url.trim_end_matches('/')))
                .json(&serde_json::json!({"image_base64": b64}))
                .timeout(std::time::Duration::from_secs(15))
                .send().await
                .context("OCR sidecar 不可达")?
                .json().await
                .context("OCR 响应解析失败")?;
            resp["code"].as_str().unwrap_or("").to_string()
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
            .form(&form)
            .send().await
            .context("登录请求失败")?;

        let mut cookies: std::collections::HashMap<String, String> = std::collections::HashMap::new();
        if let Some(header) = resp.headers().get_all("set-cookie").iter().last() {
            if let Ok(v) = header.to_str() {
                merge_cookies(&mut cookies, v);
            }
        }
        let status = resp.status().as_u16();
        let text = resp.text().await.unwrap_or_default();

        if text.contains("验证码有误") || text.contains("验证码错误") {
            continue;
        }
        if status == 302 {
            let cookie_str = cookies.iter()
                .map(|(k, v)| format!("{k}={v}"))
                .collect::<Vec<_>>().join("; ");
            if cookie_str.is_empty() {
                bail!("登录成功但未获取到 cookie");
            }
            return Ok(SchoolSession { cookie_str, base_url: base });
        }
        // 密码错误类
        if text.contains("密码错误") || text.contains("账号或密码") || text.contains("用户名或密码") {
            bail!("登录失败: 账号或密码错误");
        }
        if let Some(ids) = &school_ids {
            school_id_index += 1;
            if school_id_index >= ids.len() {
                school_id_index = 0;
            }
        }
    }
    bail!("登录失败: 重试10次未成功")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_school_ids() {
        let html = r#"<select id="schoolId"><option value="101">A</option><option value="102">B</option></select>"#;
        assert_eq!(extract_school_ids(html), Some(vec!["101".to_string(), "102".to_string()]));
        assert_eq!(extract_school_ids("<div>无</div>"), None);
    }

    #[test]
    fn test_merge_cookies() {
        let mut m = std::collections::HashMap::new();
        merge_cookies(&mut m, "a=1; path=/; b=2");
        assert_eq!(m.get("a").unwrap(), "1");
        assert_eq!(m.get("b").unwrap(), "2");
        // 属性片段（path 等无 '=' 值的键值对被跳过）
        merge_cookies(&mut m, "c=3; path=/; HttpOnly");
        assert_eq!(m.get("c").unwrap(), "3");
        assert!(m.get("HttpOnly").is_none());
    }
}

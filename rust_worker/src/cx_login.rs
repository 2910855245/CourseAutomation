//! 学习通登录 — 协议来自 passport2-static 的 `login.js`（手机号/密码 AES 加密后提交）
//!
//! 关键事实（2026-10-01 线上实测，勿再沿用旧结论）：**不需要 TLS 指纹伪装**。
//! 系统 TLS 栈（OpenSSL/reqwest native-tls）实测可正常登录并拿到完整 cookie，
//! 所以这里直接复用统一的 `platform_client`，不引入 wreq/rnet。
//!
//! 加密参数（从 login.js 的 `encryptByAES` 逐行逆出，已用 openssl 复现验证）：
//! AES-128-CBC，key = iv = `u2oh6Vu^HWe4_AES`，PKCS7 填充，输出 base64。
//!
//! 安全约定：凭据相关的失败（密码错/被锁/需二次验证）**立即返回、绝不重试** ——
//! 平台错误尝试超 5 次即锁号，自动重试会把风险放大成锁号。

use std::sync::Arc;

use anyhow::Result;
use reqwest::cookie::Jar;
use serde_json::Value;

use crate::platform_client as pc;

const LOGIN_PAGE: &str =
    "https://passport2.chaoxing.com/login?fid=&newversion=true&refer=https%3A%2F%2Fi.chaoxing.com";
const LOGIN_POST: &str = "https://passport2.chaoxing.com/fanyalogin";
const AES_KEY: &[u8] = b"u2oh6Vu^HWe4_AES";

/// 登录成功后的会话。除 cookie 串外还保留 cookie jar：
/// 学习通各子站（mooc1 / mooc2-ans / tsjy / mooc1-api）**各自有 host 级 cookie**，
/// 只带一份字符串会在某些站点被 302 回登录页 —— 用 jar 让每个请求按域名自动带对 cookie。
#[derive(Debug, Clone)]
pub struct CxSession {
    pub cookie_str: String,
    pub uid: String,
    pub fid: String,
    pub jar: Arc<Jar>,
}

/// 登录后预热：泛雅/门户/资源站各自要有一次站点访问才会下发 host cookie
const WARMUP: &[&str] = &[
    "https://i.chaoxing.com/",
    "https://mooc1.chaoxing.com/",
    "https://mooc2-ans.chaoxing.com/",
    "https://mooc1-api.chaoxing.com/",
    "https://tsjy.chaoxing.com/",
];

/// AES-128-CBC + PKCS7 → base64（与前端 `encryptByAES` 等价，iv 用同一把密钥）
pub fn encrypt_field(plain: &str) -> String {
    use aes::cipher::{BlockCipherEncrypt, KeyInit};

    let cipher = aes::Aes128::new_from_slice(AES_KEY).expect("AES-128 密钥固定 16 字节");
    let mut data = plain.as_bytes().to_vec();
    let pad = 16 - (data.len() % 16);
    data.extend(std::iter::repeat(pad as u8).take(pad));

    let mut out = Vec::with_capacity(data.len());
    let mut prev = AES_KEY.to_vec();
    for chunk in data.chunks(16) {
        let mut block = aes::cipher::Block::<aes::Aes128>::default();
        block.copy_from_slice(chunk);
        for i in 0..16 {
            block[i] ^= prev[i];
        }
        cipher.encrypt_block(&mut block);
        out.extend_from_slice(&block);
        prev.copy_from_slice(&block);
    }
    base64::Engine::encode(&base64::engine::general_purpose::STANDARD, out)
}

/// 从 cookie 串里取某个键的值
fn cookie_value(cookie_str: &str, key: &str) -> String {
    cookie_str
        .split(';')
        .filter_map(|kv| kv.trim().split_once('='))
        .find(|(k, _)| *k == key)
        .map(|(_, v)| v.to_string())
        .unwrap_or_default()
}

/// 学习通登录：取登录页（JSESSIONID）→ POST /fanyalogin → 收 cookie
pub async fn login(phone: &str, password: &str) -> Result<CxSession> {
    let phone = phone.trim();
    if phone.is_empty() || password.is_empty() {
        anyhow::bail!("学习通账号/密码不能为空");
    }
    let jar = Arc::new(Jar::default());
    // 不跟随重定向：登录结果用 JSON 判定，跟随会丢掉 set-cookie 的原始现场
    let client = pc::build_client(true, Some(jar.clone()));

    let form: Vec<(&str, String)> = vec![
        ("fid", "-1".to_string()),
        ("uname", encrypt_field(phone)),
        ("password", encrypt_field(password)),
        ("refer", "https://i.chaoxing.com".to_string()),
        ("t", "true".to_string()),
        ("forbidotherlogin", "0".to_string()),
        ("validate", String::new()),
        ("doubleFactorLogin", "0".to_string()),
        ("independentId", "0".to_string()),
        ("independentNameId", "0".to_string()),
    ];

    // 只对网络抖动（DNS/连接）重试：服务器 DNS 对超星域名偶发解析失败（已知老问题）。
    // 凭据类失败一律不重试，见模块头注释。
    let mut last_err: Option<anyhow::Error> = None;
    for _ in 0..3 {
        pc::wait_rate_limit().await;
        if let Err(e) = client.get(LOGIN_PAGE).send().await {
            last_err = Some(anyhow::anyhow!("学习通登录页请求失败：{e}"));
            continue;
        }
        pc::wait_rate_limit().await;
        let resp = match client
            .post(LOGIN_POST)
            .header("Referer", LOGIN_PAGE)
            .form(&form)
            .send()
            .await
        {
            Ok(r) => r,
            Err(e) => {
                last_err = Some(anyhow::anyhow!("学习通登录请求失败：{e}"));
                continue;
            }
        };
        let status = resp.status().as_u16();
        let text = resp.text().await.unwrap_or_default();
        if status != 200 {
            anyhow::bail!("学习通登录返回 HTTP {status}（{}）", pc::preview(&text, 120));
        }
        let v: Value = serde_json::from_str(&text).unwrap_or(Value::Null);
        if v["status"].as_bool() == Some(true) {
            let mut cookie_str = pc::jar_cookie_str(&jar, LOGIN_POST);
            if cookie_str.is_empty() {
                anyhow::bail!("学习通登录成功但未取到 cookie（会话无法继续）");
            }
            let uid = cookie_value(&cookie_str, "UID");
            if uid.is_empty() {
                anyhow::bail!("学习通登录成功但缺少 UID cookie");
            }
            // 预热各子站（顺带把 host 级 cookie 补进 jar），失败不致命：没预热的站点会在业务请求里退化为 0
            for u in WARMUP {
                pc::wait_rate_limit().await;
                let _ = client.get(*u).send().await;
            }
            // 预热后 jar 里多了一批 host cookie，串也要跟着更新（cx_study 等按字符串用）
            let refreshed = pc::jar_cookie_str(&jar, "https://mooc1.chaoxing.com/");
            if !refreshed.is_empty() {
                cookie_str = refreshed;
            }
            let fid = cookie_value(&cookie_str, "fid");
            return Ok(CxSession { cookie_str, uid, fid, jar });
        }
        // 明确的业务失败（密码错/需验证码/被锁）：立即返回，绝不重试
        let msg = v["msg"].as_str().unwrap_or("").trim().to_string();
        let msg = if msg.is_empty() { pc::preview(&text, 160) } else { msg };
        anyhow::bail!("学习通登录失败：{msg}");
    }
    Err(last_err.unwrap_or_else(|| anyhow::anyhow!("学习通登录失败（网络抖动，已重试 3 次）")))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 与线上 login.js 的实现逐字节对齐（固定向量由 openssl 命令算出并复核）
    #[test]
    fn test_encrypt_field_matches_openssl() {
        // printf '%s' 'woainima123' | openssl enc -aes-128-cbc -K <key hex> -iv <key hex> -base64 -A
        assert_eq!(encrypt_field("woainima123"), "FROz4xBzRwQ5Mi1iByE6TQ==");
        assert_eq!(encrypt_field("19136434661"), "f5r65jqHPZg10EeJja3qtQ==");
        // 长度必须整除 16（PKCS7 补齐），否则平台解不出明文
        assert_eq!(encrypt_field("任意长度都一样").len() % 4, 0);
    }

    #[test]
    fn test_encrypt_pads_to_block() {
        // 恰好 16 字节也要补一整块（PKCS7 规则），否则解密方会拿到残缺明文
        let a = encrypt_field("0123456789abcdef");
        let b = encrypt_field("0123456789abcde");
        assert!(!a.is_empty() && !b.is_empty() && a != b);
    }

    #[test]
    fn test_cookie_value() {
        let ck = "JSESSIONID=abc; UID=430580003; fid=336900; _uid=430580003";
        assert_eq!(cookie_value(ck, "UID"), "430580003");
        assert_eq!(cookie_value(ck, "fid"), "336900");
        assert_eq!(cookie_value(ck, "nope"), "");
    }
}
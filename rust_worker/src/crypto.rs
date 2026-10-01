//! 凭据存储：明文 —— 用户 2026-09-30 明确立规「密码不要加密，就明文」
//!
//! 规则：学校平台密码一律明文落 `orders.password`，读路径直接读明文列；
//! 禁止再加密、禁止清空明文列。
//!
//! 本模块保留的 `decrypt` 只服务历史数据一次性回迁：老库留下的
//! `credentials` 加密行在启动时解回明文写进 `orders.password` 并删除
//! （见 [`restore_plaintext_credentials`]）。回迁完成后该表为空，加密链路
//! 仅作为「明文意外为空」时的兜底读取残留。

use anyhow::{Context, Result};
use base64::Engine;
use rusqlite::Connection;
use sha2::{Digest, Sha256};

use aes_gcm::aead::{Aead, KeyInit};
use aes_gcm::{Aes256Gcm, Key, Nonce};

const B64: base64::engine::general_purpose::GeneralPurpose =
    base64::engine::general_purpose::STANDARD;

/// 派生 32 字节密钥的候选来源（按优先级）：
///   1. `CREDENTIAL_KEY`（64 位 hex，专用主密钥）
///   2. `PASSWORD_ENCRYPTION_KEY`（项目既有配置项，先 sha256 压成 32 字节）
///   3. `JWT_SECRET_KEY` 派生（兜底，保证零配置也能跑）
///
/// 加密用第一个候选；解密按顺序逐个尝试——这样轮换密钥或补齐
/// `CREDENTIAL_KEY` 时，历史密文仍可解开，不会丢数据。
fn candidate_keys() -> Vec<[u8; 32]> {
    let mut keys: Vec<[u8; 32]> = Vec::new();

    if let Ok(hex_key) = std::env::var("CREDENTIAL_KEY") {
        if let Some(k) = hex_to_key(hex_key.trim()) {
            keys.push(k);
        } else {
            tracing::warn!("CREDENTIAL_KEY 非法（需 64 位 hex），忽略");
        }
    }
    if let Ok(legacy) = std::env::var("PASSWORD_ENCRYPTION_KEY") {
        if !legacy.is_empty() {
            keys.push(sha256_key(&legacy));
        }
    }
    let jwt = std::env::var("JWT_SECRET_KEY").unwrap_or_else(|_| "local-dev-secret-key".into());
    keys.push(sha256_key(&format!("credential-encryption-v1:{jwt}")));

    keys.dedup();
    keys
}

/// 常数时间字节比较：用于比对密钥/令牌，避免 `==` 的短路比较把「前几位
/// 猜对了」这个信息通过响应耗时泄露出去（时间侧信道）。
pub fn ct_eq(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff = 0u8;
    for (x, y) in a.iter().zip(b.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}

fn hex_to_key(hex_key: &str) -> Option<[u8; 32]> {
    if hex_key.len() != 64 {
        return None;
    }
    let mut key = [0u8; 32];
    for i in 0..32 {
        key[i] = u8::from_str_radix(&hex_key[i * 2..i * 2 + 2], 16).ok()?;
    }
    Some(key)
}

fn sha256_key(seed: &str) -> [u8; 32] {
    let digest = Sha256::digest(seed.as_bytes());
    let mut key = [0u8; 32];
    key.copy_from_slice(&digest);
    key
}

/// 解密（按候选密钥顺序尝试，兼容历史密钥）
pub fn decrypt(ct_b64: &str, nonce_b64: &str) -> Result<String> {
    decrypt_with(&candidate_keys(), ct_b64, nonce_b64)
}

/// 指定密钥加密 —— 仅测试用（生产禁止再加密，见模块头规则）
#[cfg(test)]
fn encrypt_with(key: &[u8; 32], plain: &str) -> Result<(String, String)> {
    let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(key));
    let nonce_bytes: [u8; 12] = rand::random();
    let ct = cipher
        .encrypt(Nonce::from_slice(&nonce_bytes), plain.as_bytes())
        .map_err(|_| anyhow::anyhow!("凭据加密失败"))?;
    Ok((B64.encode(ct), B64.encode(nonce_bytes)))
}

/// 按给定候选密钥逐个尝试解密
fn decrypt_with(keys: &[[u8; 32]], ct_b64: &str, nonce_b64: &str) -> Result<String> {
    let ct = B64.decode(ct_b64).context("密文 base64 解码失败")?;
    let nonce = B64.decode(nonce_b64).context("nonce base64 解码失败")?;
    if nonce.len() != 12 {
        anyhow::bail!("nonce 长度非法");
    }
    for key in keys {
        let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(key));
        if let Ok(plain) = cipher.decrypt(Nonce::from_slice(&nonce), ct.as_ref()) {
            return String::from_utf8(plain).context("凭据非 UTF-8");
        }
    }
    anyhow::bail!("凭据解密失败（所有候选密钥均不匹配，可能密钥已变更）")
}

/// 读取订单密码：明文列优先（用户规则）；仅当明文为空时回退解密历史密文行
/// （回迁尚未跑完的过渡窗口，正常情况下走不到）。
pub fn load_password(conn: &Connection, order_id: &str) -> Option<String> {
    if let Ok(p) = conn.query_row(
        "SELECT password FROM orders WHERE order_id=?1",
        rusqlite::params![order_id],
        |r| r.get::<_, String>(0),
    ) {
        if !p.is_empty() && p != "***" {
            return Some(p);
        }
    }
    let row: Option<(String, String)> = conn
        .query_row(
            "SELECT password_enc, nonce FROM credentials WHERE order_id=?1",
            rusqlite::params![order_id],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .ok();
    if let Some((ct, nonce)) = row {
        match decrypt(&ct, &nonce) {
            Ok(p) if !p.is_empty() => return Some(p),
            Ok(_) => {}
            Err(e) => tracing::error!(order_id, error = %e, "历史密文解密失败"),
        }
    }
    None
}

/// 历史加密凭据一次性回迁为明文（用户规则：密码只存明文）。
///
/// 幂等可重跑：明文已在的订单只清掉多余的密文行；明文为空的订单解密后
/// 写回；解密失败的保留密文行（读路径仍能兜底），下次启动重试。
pub fn restore_plaintext_credentials(conn: &Connection) -> Result<usize> {
    let mut stmt = conn.prepare("SELECT order_id, password_enc, nonce FROM credentials")?;
    let rows: Vec<(String, String, String)> = stmt
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)))?
        .collect::<std::result::Result<_, _>>()?;
    drop(stmt);

    let mut restored = 0usize;
    for (order_id, ct, nonce) in rows {
        let plain: Option<String> = conn
            .query_row(
                "SELECT password FROM orders WHERE order_id=?1",
                rusqlite::params![order_id],
                |r| r.get(0),
            )
            .ok();
        match plain {
            // 订单不存在：密文已无意义
            None => {
                conn.execute(
                    "DELETE FROM credentials WHERE order_id=?1",
                    rusqlite::params![order_id],
                )?;
            }
            // 明文已在：密文是历史残留，清掉即完成
            Some(p) if !p.is_empty() && p != "***" => {
                conn.execute(
                    "DELETE FROM credentials WHERE order_id=?1",
                    rusqlite::params![order_id],
                )?;
            }
            // 明文为空 → 解密回填，成功才删密文
            Some(_) => match decrypt(&ct, &nonce) {
                Ok(p) if !p.is_empty() => {
                    conn.execute(
                        "UPDATE orders SET password=?2 WHERE order_id=?1",
                        rusqlite::params![order_id, p],
                    )?;
                    conn.execute(
                        "DELETE FROM credentials WHERE order_id=?1",
                        rusqlite::params![order_id],
                    )?;
                    restored += 1;
                }
                Ok(_) => {}
                Err(e) => tracing::warn!(order_id, error = %e, "历史密文解密失败，保留待下次重试"),
            },
        }
    }
    Ok(restored)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 固定测试密钥（不读写环境变量，避免与其它测试并行时相互干扰）
    fn key_a() -> [u8; 32] {
        [0xA5; 32]
    }
    fn key_b() -> [u8; 32] {
        [0x5A; 32]
    }

    #[test]
    fn test_roundtrip_and_nonce_uniqueness() {
        let (ct, nonce) = encrypt_with(&key_a(), "Axy@321987").unwrap();
        assert_ne!(ct, "Axy@321987");
        assert_eq!(decrypt_with(&[key_a()], &ct, &nonce).unwrap(), "Axy@321987");
        // 同一明文两次加密：nonce 与密文均不同（语义安全）
        let (ct2, nonce2) = encrypt_with(&key_a(), "Axy@321987").unwrap();
        assert_ne!(nonce, nonce2);
        assert_ne!(ct, ct2);
    }

    #[test]
    fn test_wrong_key_or_nonce_fails() {
        let (ct, nonce) = encrypt_with(&key_a(), "hello").unwrap();
        // 错误密钥
        assert!(decrypt_with(&[key_b()], &ct, &nonce).is_err());
        // 错误 nonce
        let (_, other_nonce) = encrypt_with(&key_a(), "hello").unwrap();
        assert!(decrypt_with(&[key_a()], &ct, &other_nonce).is_err());
    }

    #[test]
    fn test_key_rotation_keeps_old_ciphertext_readable() {
        // 旧密钥(key_a)加密的历史密文，在轮换到新密钥(key_b)后仍可解开
        let (old_ct, old_nonce) = encrypt_with(&key_a(), "legacy-pwd").unwrap();
        let (new_ct, new_nonce) = encrypt_with(&key_b(), "new-pwd").unwrap();
        let keys = [key_b(), key_a()]; // 新密钥优先，旧密钥兜底
        assert_eq!(
            decrypt_with(&keys, &old_ct, &old_nonce).unwrap(),
            "legacy-pwd"
        );
        assert_eq!(decrypt_with(&keys, &new_ct, &new_nonce).unwrap(), "new-pwd");
    }

    #[test]
    fn test_hex_key_parsing() {
        assert!(hex_to_key("zz").is_none());
        assert!(hex_to_key(&"ab".repeat(31)).is_none()); // 长度不足
        assert_eq!(hex_to_key(&"0f".repeat(32)).unwrap()[0], 0x0f);
    }
}

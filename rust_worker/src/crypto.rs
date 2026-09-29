//! 凭据加密存储（AES-256-GCM）— orders 表不再落明文学校平台密码
//!
//! 背景：orders.password / queue_jobs_*.password 长期明文入库，一旦 db 泄露即
//! 直接暴露学员账号密码。本模块把密码迁到独立 `credentials` 表并加密：
//!   - 主密钥来源：环境变量 `CREDENTIAL_KEY`（64 位 hex），
//!     缺省时由 `JWT_SECRET_KEY` 派生（sha256("credential-encryption-v1:" + secret)）
//!   - 密文存 TEXT（base64），nonce 单独一列（每条记录随机，绝不复用）
//!   - 老库迁移幂等：orders.password 仍是明文时加密搬入 credentials 并清空原列
//!
//! 兼容性：读取时 credentials 缺失则回退读 orders.password（迁移未跑完/历史行）。

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

/// 加密：返回 (密文 base64, nonce base64)
pub fn encrypt(plain: &str) -> Result<(String, String)> {
    encrypt_with(&candidate_keys()[0], plain)
}

/// 解密（按候选密钥顺序尝试，兼容历史密钥）
pub fn decrypt(ct_b64: &str, nonce_b64: &str) -> Result<String> {
    decrypt_with(&candidate_keys(), ct_b64, nonce_b64)
}

/// 指定密钥加密（测试与密钥轮换用）
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

/// 写入（或覆盖）一条订单凭据
pub fn store(conn: &Connection, order_id: &str, username: &str, password: &str) -> Result<()> {
    let (ct, nonce) = encrypt(password)?;
    conn.execute(
        "INSERT INTO credentials (order_id, username, password_enc, nonce, created_at)
         VALUES (?1, ?2, ?3, ?4, ?5)
         ON CONFLICT(order_id) DO UPDATE SET
             username=excluded.username,
             password_enc=excluded.password_enc,
             nonce=excluded.nonce",
        rusqlite::params![order_id, username, ct, nonce, crate::queue::now_str()],
    )?;
    Ok(())
}

/// 读取订单密码：优先 credentials（解密），回退 orders.password 明文（老数据）
pub fn load_password(conn: &Connection, order_id: &str) -> Option<String> {
    let row: Option<(String, String)> = conn
        .query_row(
            "SELECT password_enc, nonce FROM credentials WHERE order_id=?1",
            rusqlite::params![order_id],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .ok();
    if let Some((ct, nonce)) = row {
        match decrypt(&ct, &nonce) {
            Ok(p) => return Some(p),
            Err(e) => {
                tracing::error!(order_id, error = %e, "凭据解密失败，回退明文列");
            }
        }
    }
    conn.query_row(
        "SELECT password FROM orders WHERE order_id=?1",
        rusqlite::params![order_id],
        |r| r.get::<_, String>(0),
    )
    .ok()
    .filter(|p| !p.is_empty() && p != "***")
}

/// 老库一次性迁移：orders.password 明文的行搬进 credentials 并清空原列。
/// 幂等：已迁移的行 credentials 已有记录，跳过。
pub fn migrate_plaintext_credentials(conn: &Connection) -> Result<usize> {
    let mut stmt = conn.prepare(
        "SELECT o.order_id, o.username, o.password FROM orders o
         WHERE o.password IS NOT NULL AND o.password <> '' AND o.password <> '***'
           AND NOT EXISTS (SELECT 1 FROM credentials c WHERE c.order_id = o.order_id)",
    )?;
    let rows: Vec<(String, String, String)> = stmt
        .query_map([], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, Option<String>>(1)?.unwrap_or_default(),
                r.get::<_, String>(2)?,
            ))
        })?
        .collect::<std::result::Result<_, _>>()?;
    drop(stmt);

    let mut migrated = 0usize;
    for (order_id, username, password) in rows {
        match store(conn, &order_id, &username, &password) {
            Ok(()) => {
                conn.execute(
                    "UPDATE orders SET password='' WHERE order_id=?1",
                    rusqlite::params![order_id],
                )?;
                migrated += 1;
            }
            Err(e) => tracing::warn!(order_id, error = %e, "凭据迁移失败，保留明文"),
        }
    }
    Ok(migrated)
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

//! 支付信任关键件（Rust 版）— 对齐 services/ypay_service.py 的签名验证
//!
//! VMQ 协议（Android 监控 APP）：heart/push 签名验证 + 时间戳窗口。
//! 与 Python 交叉验证：同密钥下两端的判定必须逐字节一致。

use std::time::{SystemTime, UNIX_EPOCH};

use md5::compute;
use serde_json::{json, Value};

use crate::db::Db;

fn hash_md5(s: &str) -> String {
    format!("{:x}", compute(s.as_bytes()))
}

/// ypay 密钥（ypay_settings 表 key=key）
async fn ypay_key(db: &Db) -> Option<String> {
    let pool = db.clone_pool();
    tokio::task::spawn_blocking(move || -> Option<String> {
        let conn = pool.get().ok()?;
        conn.query_row(
            "SELECT value FROM ypay_settings WHERE key='key'",
            [], |r| r.get(0),
        ).ok().flatten()
    })
    .await
    .ok()
    .flatten()
}

/// 时间戳窗口校验（对齐 _validate_timestamp，120 分钟，毫秒自动降秒）
pub fn validate_timestamp(t: &str, max_offset_minutes: i64) -> bool {
    if t.is_empty() || !t.chars().all(|c| c.is_ascii_digit()) {
        return false;
    }
    let Ok(mut ts) = t.parse::<i64>() else { return false };
    if ts > 1_000_000_000_000 {
        ts /= 1000;
    }
    let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() as i64;
    (now - ts).abs() <= max_offset_minutes * 60
}

/// 回调签名（对齐 verify_callback_sign）
pub async fn verify_callback_sign(db: &Db, pay_id: &str, param: &str, pay_type: &str,
                                  price: &str, really_price: &str, sign: &str) -> bool {
    match ypay_key(db).await {
        Some(key) => sign == hash_md5(&format!("{pay_id}{param}{pay_type}{price}{really_price}{key}")),
        None => false,
    }
}

/// 心跳签名（对齐 verify_heart_sign：候选含毫秒降秒变体）
pub async fn verify_heart_sign(db: &Db, t: &str, sign: &str) -> bool {
    let Some(key) = ypay_key(db).await else { return false };
    if !validate_timestamp(t, 120) {
        return false;
    }
    let mut candidates = vec![
        hash_md5(&format!("{t}{key}")),
        hash_md5(&format!("{key}{t}")),
    ];
    if t.chars().all(|c| c.is_ascii_digit()) {
        if let Ok(ts) = t.parse::<u128>() {
            if ts > 1_000_000_000_000 {
                let t_sec = (ts / 1000).to_string();
                candidates.push(hash_md5(&format!("{t_sec}{key}")));
                candidates.push(hash_md5(&format!("{key}{t_sec}")));
            }
        }
    }
    candidates.contains(&sign.to_string())
}

/// 推送签名（对齐 verify_push_sign）
pub async fn verify_push_sign(db: &Db, ptype: &str, price: &str, t: &str, sign: &str) -> bool {
    let Some(key) = ypay_key(db).await else { return false };
    if !validate_timestamp(t, 120) {
        return false;
    }
    let candidates = [
        hash_md5(&format!("{ptype}{price}{t}{key}")),
        hash_md5(&format!("{key}{ptype}{price}{t}")),
        hash_md5(&format!("{t}{key}")),
        hash_md5(&format!("{key}{t}")),
    ];
    candidates.contains(&sign.to_string())
}

/// 交易号（对齐 generate_trade_no）
pub fn generate_trade_no() -> String {
    let secs = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
    // Y + YYYYMMDDHHMMSS 近似（无 chrono，用自算日期）
    let days = secs / 86400;
    let mut y = 1970u64;
    let mut rem = days;
    loop {
        let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
        let ydays = if leap { 366 } else { 365 };
        if rem < ydays { break; }
        rem -= ydays;
        y += 1;
    }
    let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
    let mdays = [31, if leap { 29 } else { 28 }, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let mut m = 0usize;
    while rem >= mdays[m] {
        rem -= mdays[m];
        m += 1;
    }
    let sod = secs % 86400;
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let hex: String = format!("{:06x}", (nanos % 0xffffff) as u32);
    format!(
        "Y{:04}{:02}{:02}{:02}{:02}{:02}{}",
        y, m + 1, rem + 1, sod / 3600, (sod % 3600) / 60, sod % 60, hex
    )
}

/// 浮动价格（对齐 _compute_floating_price：偏移打乱后取首个未被占用的）
pub fn compute_floating_price(base: f64, existing: &[f64]) -> f64 {
    use rand::seq::SliceRandom;
    let mut offsets = [0.01, 0.02, 0.03, 0.04, 0.05, -0.01, -0.02, -0.03];
    offsets.shuffle(&mut rand::thread_rng());
    for off in offsets {
        let candidate = (base + off).round_to_2();
        if candidate > 0.0 && !existing.contains(&candidate) {
            return candidate;
        }
    }
    base
}

trait Round2 {
    fn round_to_2(self) -> f64;
}
impl Round2 for f64 {
    fn round_to_2(self) -> f64 {
        (self * 100.0).round() / 100.0
    }
}

/// 支付匹配（对齐 ypay_service.match_payment：浮动价精确匹配 → 标记已付 → 释放价格锁）
/// 返回 trade_no（无匹配 → None）。
/// 注：回调通知（_send_callback 线程）暂未移植，迁移期由 Python 侧承担。
pub async fn match_payment(db: &Db, price: f64, pay_type: i64) -> Option<String> {
    let base = (price * 100.0).round() / 100.0;
    let pool = db.clone_pool();
    let row = tokio::task::spawn_blocking(move || -> Option<(String, f64)> {
        let conn = pool.get().ok()?;
        let now = crate::queue::now_str();
        conn.query_row(
            "SELECT trade_no, truemoney FROM ypay_order
             WHERE truemoney=?1 AND type=?2 AND status=0 AND out_time > ?3
             ORDER BY create_time ASC LIMIT 1",
            rusqlite::params![base, pay_type, now],
            |r| Ok((r.get(0)?, r.get(1)?)),
        ).ok()
    })
    .await
    .ok()
    .flatten();

    let (trade_no, truemoney) = row?;
    if (truemoney - base).abs() >= 0.01 {
        tracing::warn!(pushed = base, order = truemoney, trade_no, "ypay_amount_mismatch");
        return None;
    }
    // 标记已付（对齐 ypay_mark_paid）
    let pool = db.clone_pool();
    let trade_no2 = trade_no.clone();
    let ok = tokio::task::spawn_blocking(move || -> bool {
        match pool.get() {
            Ok(conn) => conn.execute(
                "UPDATE ypay_order SET status=1, end_time=?1 WHERE trade_no=?2",
                rusqlite::params![crate::queue::now_str(), trade_no2],
            ).is_ok(),
            Err(_) => false,
        }
    })
    .await
    .ok()
    .unwrap_or(false);
    if ok {
        tracing::info!(trade_no, price = base, "ypay_payment_matched");
        Some(trade_no)
    } else {
        None
    }
}

/// VMQ 推送完整判定（对齐 _vmq_push_sync：验签 → 匹配 → notify/success）
pub async fn vmq_push_response(db: &Db, ptype: &str, price: &str, t: &str, sign: &str) -> String {
    if !verify_push_sign(db, ptype, price, t, sign).await {
        return "fail".to_string();
    }
    let (Ok(price_f), Ok(ptype_i)) = (price.parse::<f64>(), ptype.parse::<i64>()) else {
        return "fail".to_string();
    };
    match match_payment(db, price_f, ptype_i).await {
        Some(_) => "success".to_string(),
        None => "notify".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hash_md5() {
        assert_eq!(hash_md5("hello"), "5d41402abc4b2a76b9719d911017c592");
    }

    #[test]
    fn test_validate_timestamp() {
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
        assert!(validate_timestamp(&now.to_string(), 120));
        assert!(validate_timestamp(&(now * 1000).to_string(), 120)); // 毫秒
        assert!(!validate_timestamp(&(now - 10000).to_string(), 120)); // 超窗
        assert!(!validate_timestamp("abc", 120));
        assert!(!validate_timestamp("", 120));
    }

    #[test]
    fn test_floating_price() {
        let p = compute_floating_price(10.0, &[10.0, 10.01]);
        assert_ne!(p, 10.0);
        assert!(!(10.0..10.01).contains(&p) || p != 10.01, "{p}");
        assert!((p - 10.0).abs() <= 0.05);
    }

    #[test]
    fn test_trade_no() {
        let t = generate_trade_no();
        assert!(t.starts_with('Y') && t.len() > 14, "{t}");
        assert!(t[1..15].chars().all(|c| c.is_ascii_digit()), "{t}");
    }
}

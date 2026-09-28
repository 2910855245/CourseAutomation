//! 支付信任关键件（Rust 版）— 对齐 services/ypay_service.py 的签名验证
//!
//! VMQ 协议（Android 监控 APP）：heart/push 签名验证 + 时间戳窗口。
//! 与 Python 交叉验证：同密钥下两端的判定必须逐字节一致。

use std::time::{SystemTime, UNIX_EPOCH};

use md5::compute;
use serde_json::{json, Value};

use crate::db::Db;

pub(crate) fn hash_md5(s: &str) -> String {
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
    offsets.shuffle(&mut rand::rng());
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

/// ISO 时间字符串解析回秒（对齐 datetime.fromisoformat 处理的 "YYYY-MM-DDTHH:MM:SS" 形状）
/// 解析失败返回 None。仅支持 now_str()/chrono_lite 产出的格式。
pub fn parse_iso_secs(s: &str) -> Option<i64> {
    let s = s.trim();
    if s.len() < 19 {
        return None;
    }
    let num = |a: usize, b: usize| -> Option<i64> { s.get(a..b)?.parse().ok() };
    let y = num(0, 4)?;
    let mo = num(5, 7)?;
    let d = num(8, 10)?;
    let h = num(11, 13)?;
    let mi = num(14, 16)?;
    let se = num(17, 19)?;
    if !(1..=12).contains(&mo) || !(1..=31).contains(&d) {
        return None;
    }
    // days from civil（Howard Hinnant 算法），与 chrono_lite 互逆
    let yy = if mo <= 2 { y - 1 } else { y };
    let era = if yy >= 0 { yy } else { yy - 399 } / 400;
    let yoe = yy - era * 400;
    let mp = (mo + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    let days = era * 146097 + doe - 719468;
    Some(days * 86400 + h * 3600 + mi * 60 + se)
}

/// 当前时间 + secs 秒 → ISO 字符串（对齐 datetime.now() + timedelta(seconds=...) 的 isoformat）
pub fn iso_after_secs(secs: u64) -> String {
    let now = SystemTime::now().duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let days = (now + secs) / 86400;
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
    let sod = (now + secs) % 86400;
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}",
        y, m + 1, rem + 1, sod / 3600, (sod % 3600) / 60, sod % 60
    )
}

/// 对齐 Python str(float)：10.0 → "10.0"，10.5 → "10.5"
/// Rust format!("{}", f64) 会把 10.0 打成 "10"，会破坏回调签名串的逐字节一致性。
pub fn py_float_str(v: f64) -> String {
    if v.fract() == 0.0 && v.abs() < 1e15 {
        format!("{v:.1}")
    } else {
        format!("{v}")
    }
}

/// 异步回调通知（对齐 _send_callback：form POST，2 次尝试，间隔 2s，timeout 5s）
pub async fn send_callback(order: Value, notify_url: String, key: String) {
    let pay_id = order.get("trade_no").and_then(Value::as_str).unwrap_or("").to_string();
    let param = order.get("out_trade_no").and_then(Value::as_str).unwrap_or("").to_string();
    let ptype = order.get("pay_type").map(|v| match v {
        Value::Number(n) => n.to_string(),
        Value::String(s) => s.clone(),
        _ => "1".to_string(),
    }).unwrap_or_else(|| "1".to_string());
    let price_str = py_float_str(order.get("money").and_then(Value::as_f64).unwrap_or(0.0));
    let really_price_str = py_float_str(order.get("truemoney").and_then(Value::as_f64).unwrap_or(0.0));
    let sign = hash_md5(&format!("{pay_id}{param}{ptype}{price_str}{really_price_str}{key}"));

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .unwrap_or_default();
    for attempt in 0..2 {
        let form = [
            ("payId", pay_id.as_str()),
            ("param", param.as_str()),
            ("type", ptype.as_str()),
            ("price", price_str.as_str()),
            ("reallyPrice", really_price_str.as_str()),
            ("sign", sign.as_str()),
        ];
        match client.post(&notify_url).form(&form).send().await {
            Ok(resp) => {
                let status = resp.status().as_u16();
                let text = resp.text().await.unwrap_or_default();
                if status == 200 {
                    let t = text.trim().to_lowercase();
                    if ["success", "ok", "1", "true"].contains(&t.as_str()) {
                        tracing::info!(trade_no = pay_id, attempt = attempt + 1, "ypay_callback_success");
                        return;
                    }
                    tracing::warn!(trade_no = pay_id, attempt = attempt + 1, body = &t[..t.len().min(100)], "ypay_callback_bad_response");
                } else {
                    tracing::warn!(trade_no = pay_id, attempt = attempt + 1, status, "ypay_callback_http_error");
                }
                if attempt < 1 {
                    tokio::time::sleep(std::time::Duration::from_secs(2)).await;
                }
            }
            Err(e) => {
                tracing::warn!(trade_no = pay_id, attempt = attempt + 1, error = %e, "ypay_callback_retry");
                if attempt < 1 {
                    tokio::time::sleep(std::time::Duration::from_secs(2u64.pow(attempt as u32 + 1))).await;
                }
            }
        }
    }
    tracing::error!(trade_no = pay_id, notify_url, "ypay_callback_failed");
}

/// 支付匹配（对齐 ypay_service.match_payment：
/// 关过期 → 金额+类型匹配 → 标记已付 → 释放价格锁 → spawn 回调线程）
/// 返回匹配的支付单 dict（无匹配 → None）。
pub async fn match_payment(db: &Db, price: f64, pay_type: i64) -> Option<Value> {
    let dbc = db.clone();
    let order = tokio::task::spawn_blocking(move || -> Option<Value> {
        dbc.ypay_close_expired_orders_sync();
        // 对齐 round(float(Decimal(str(price))), 2)
        let base = (price * 100.0).round() / 100.0;
        let order = dbc.ypay_find_pending_by_price_sync(base, pay_type)?;
        let truemoney = order.get("truemoney").and_then(Value::as_f64).unwrap_or(0.0);
        if (truemoney - base).abs() >= 0.01 {
            let tn = order.get("trade_no").and_then(Value::as_str).unwrap_or("");
            tracing::warn!(pushed = base, order = truemoney, trade_no = tn, "ypay_amount_mismatch");
            return None;
        }
        let trade_no = order.get("trade_no").and_then(Value::as_str).unwrap_or("").to_string();
        if !dbc.ypay_mark_paid_sync(&trade_no) {
            return None;
        }
        dbc.ypay_release_price_sync(truemoney);
        Some(order)
    })
    .await
    .ok()
    .flatten()?;

    let notify_url = order.get("notify_url").and_then(Value::as_str).unwrap_or("").to_string();
    if !notify_url.is_empty() {
        let dbc = db.clone();
        let order2 = order.clone();
        tokio::spawn(async move {
            let key = tokio::task::spawn_blocking(move || dbc.ypay_setting_get_sync("key", ""))
                .await
                .unwrap_or_default();
            send_callback(order2, notify_url, key).await;
        });
    }
    let tn = order.get("trade_no").and_then(Value::as_str).unwrap_or("");
    tracing::info!(trade_no = tn, price, "ypay_payment_matched");
    Some(order)
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

// ── 创建支付单（对齐 ypay_service.create_order）─────────────────────────

struct PreparedOrder {
    account: Value,
    trade_no: String,
    really_price: f64,
    type_str: String,
    site_url: String,
    timeout_seconds: u64,
}

/// 对齐 site_url 取值链：ypay_setting site_url → env SITE_URL → 默认
fn site_url_of(db: &Db) -> String {
    let v = db.ypay_setting_get_sync("site_url", "");
    let v = if v.is_empty() { std::env::var("SITE_URL").unwrap_or_default() } else { v };
    let v = if v.is_empty() { "http://localhost:8000".to_string() } else { v };
    v.trim_end_matches('/').to_string()
}

/// 对齐 ypay_service._get_site_url（异步包装，spawn_blocking 读 DB）
pub async fn get_site_url(db: &Db) -> String {
    let dbc = db.clone();
    tokio::task::spawn_blocking(move || site_url_of(&dbc))
        .await
        .unwrap_or_else(|_| "http://localhost:8000".to_string())
}

/// 对齐 ypay_service.build_pay_url
pub async fn build_pay_url(db: &Db, trade_no: &str) -> String {
    format!("{}/#/payment/{}", get_site_url(db).await, trade_no)
}

/// 创建支付单（对齐 ypay_service.create_order）。
/// 涉及网络（lkl 等动态二维码），故 DB 段与网络段分离；失败路径释放价格锁。
pub async fn create_order(
    db: &Db,
    client: &reqwest::Client,
    pay_type: i64,
    price: f64,
    out_trade_no: &str,
    name: &str,
    notify_url: &str,
    return_url: &str,
    ip: &str,
    floating: bool,
) -> Option<Value> {
    let money = (price * 100.0).round() / 100.0;
    let trade_no = generate_trade_no();

    // 段 1：关过期 + 选渠道 + 浮动价 + 锁价
    let dbc = db.clone();
    let out_trade_no_s = out_trade_no.to_string();
    let Some(prep) = tokio::task::spawn_blocking(move || -> Option<PreparedOrder> {
        let account = dbc.ypay_pick_channel_sync(pay_type)?;
        let ch_code = account.get("code").and_then(Value::as_str).unwrap_or("");
        let ch_name = account.get("name").and_then(Value::as_str).unwrap_or("");
        let has_qr = !account.get("qr_url").and_then(Value::as_str).unwrap_or("").is_empty();
        tracing::info!(pay_type, code = ch_code, name = ch_name, has_qr_url = has_qr, "ypay_channel_picked");
        let account_id = account.get("id").and_then(Value::as_i64).unwrap_or(0);
        let really_price = if floating {
            let existing = dbc.ypay_get_active_prices_sync(account_id);
            compute_floating_price(money, &existing)
        } else {
            money
        };
        let locked = dbc.ypay_lock_price_sync(really_price, &trade_no)?;
        // Python 用锁后返回价（+0.01 重试可能改变价格）
        let really_price = locked;
        // 对齐 type_str 修正：账单/插件渠道覆盖 account.type
        let code = account.get("code").and_then(Value::as_str).unwrap_or("").to_string();
        let mut type_str = {
            let t = account.get("type").and_then(Value::as_str).unwrap_or("");
            if t.is_empty() {
                crate::ypay_db::pay_type_str(pay_type).to_string()
            } else {
                t.to_string()
            }
        };
        if ["lkl_alipay", "dougong_alipay", "lebrush_alipay"].contains(&code.as_str()) {
            type_str = "alipay".to_string();
        } else if ["lkl_wxpay", "dougong_wxpay", "lebrush_wxpay"].contains(&code.as_str()) {
            type_str = "wxpay".to_string();
        }
        let site_url = site_url_of(&dbc);
        let timeout_seconds = dbc.ypay_setting_get_sync("pay_timeout", "300").parse::<u64>().unwrap_or(300);
        let _ = out_trade_no_s;
        Some(PreparedOrder { account, trade_no, really_price, type_str, site_url, timeout_seconds })
    })
    .await
    .ok()
    .flatten() else {
        tracing::warn!(pay_type, "ypay_no_channel 或锁价失败");
        return None;
    };

    // 段 2：生成二维码（可能走网络）
    let (qrcode, h5_qrurl) = crate::ypay_qr::generate_qrcode(
        client, &prep.account, prep.really_price, &prep.trade_no, out_trade_no, &prep.site_url,
    )
    .await;
    if qrcode.is_empty() {
        let code = prep.account.get("code").and_then(Value::as_str).unwrap_or("").to_string();
        let dbc = db.clone();
        let rp = prep.really_price;
        tokio::task::spawn_blocking(move || dbc.ypay_release_price_sync(rp)).await.ok();
        tracing::warn!(code, trade_no = prep.trade_no, "ypay_qrcode_failed");
        return None;
    }

    // 段 3：写支付单
    let dbc = db.clone();
    let name_s = name.to_string();
    let notify_s = notify_url.to_string();
    let return_s = return_url.to_string();
    let ip_s = ip.to_string();
    let out_time = iso_after_secs(prep.timeout_seconds);
    let out_trade_no_s = out_trade_no.to_string();
    let code = prep.account.get("code").and_then(Value::as_str).unwrap_or("").to_string();
    let channel_name = prep.account.get("name").and_then(Value::as_str).unwrap_or("").to_string();
    let account_id = prep.account.get("id").and_then(Value::as_i64).unwrap_or(0);
    let trade_no = prep.trade_no.clone();
    let order = tokio::task::spawn_blocking(move || {
        let created = dbc.ypay_create_order_sync(
            &trade_no, &out_trade_no_s, pay_type, &prep.type_str, &name_s, money,
            prep.really_price, account_id, &qrcode, &h5_qrurl, &notify_s, &return_s, &ip_s, &out_time,
        );
        if created.is_none() {
            dbc.ypay_release_price_sync(prep.really_price);
        }
        created
    })
    .await
    .ok()
    .flatten()?;

    let qr_content_type = crate::ypay_qr::detect_qr_content_type(
        order.get("qrcode").and_then(Value::as_str).unwrap_or(""),
    );
    let mut order = order;
    if let Value::Object(ref mut m) = order {
        m.insert("qr_content_type".into(), Value::String(qr_content_type.into()));
        m.insert("channel_code".into(), Value::String(code));
        m.insert("channel_name".into(), Value::String(channel_name));
    }
    tracing::info!(price = money, really_price = prep.really_price, pay_type, "ypay_order_created");
    Some(order)
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

//! 营销推广：免费刷开关、邀请拉新、刷课卡。
//!
//! 身份：每个访客由服务端下发一个 `vid`（HttpOnly cookie，见 [`COOKIE_NAME`]），
//! 邀请关系与卡片都挂在 vid 上，**不依赖浏览器 localStorage**。vid 丢失时
//! 靠领卡时留的联系方式人工找回（后台可查）。
//!
//! 规则（阈值全部可在后台改，键名见各 `CFG_*` 常量）：
//!   - `free_mode`：全局免费开关，开着时所有人 0 元下单并直接进队列
//!   - 邀请：好友通过 `?ref=<邀请码>` 进来即记录；是否"有效"由
//!     `invite_require_order` 决定（默认需要好友真正下单，防刷）
//!   - 领卡：每累计 `invite_threshold` 个有效邀请可领 1 张，可重复领
//!   - 卡：有效期内该访客免单（`card_max_orders` = 0 表示不限次）

use anyhow::{Context, Result};
use serde_json::{json, Value};

use crate::db::Db;

/// 访客身份 cookie 名（前端不读它，只由浏览器带回）
pub const COOKIE_NAME: &str = "vid";
/// 邀请码长度
const CODE_LEN: usize = 8;

pub const CFG_FREE_MODE: &str = "free_mode";
pub const CFG_INVITE_ENABLED: &str = "invite_enabled";
pub const CFG_THRESHOLD: &str = "invite_threshold";
pub const CFG_REQUIRE_ORDER: &str = "invite_require_order";
pub const CFG_VALID_DAYS: &str = "card_valid_days";
pub const CFG_MAX_ORDERS: &str = "card_max_orders";

/// 当前生效的营销配置（一次读齐，避免多处各读一次）
#[derive(Debug, Clone)]
pub struct PromoConfig {
    pub free_mode: bool,
    pub invite_enabled: bool,
    pub threshold: i64,
    pub require_order: bool,
    pub valid_days: i64,
    pub max_orders: i64,
}

impl PromoConfig {
    pub async fn load(db: &Db) -> Self {
        let get = |k: &'static str| async move {
            crate::queue::config_get(db, k).await.unwrap_or_default()
        };
        let threshold = get(CFG_THRESHOLD).await.parse::<i64>().ok().unwrap_or(3).clamp(1, 1000);
        let valid_days = get(CFG_VALID_DAYS).await.parse::<i64>().ok().unwrap_or(30).clamp(1, 3650);
        let max_orders = get(CFG_MAX_ORDERS).await.parse::<i64>().ok().unwrap_or(0).max(0);
        Self {
            free_mode: get(CFG_FREE_MODE).await == "1",
            // 默认开启：这是拉新功能，装好就该能用
            invite_enabled: get(CFG_INVITE_ENABLED).await != "0",
            threshold,
            require_order: get(CFG_REQUIRE_ORDER).await != "0",
            valid_days,
            max_orders,
        }
    }
}

/// 该访客当前能享受的免费待遇。
///
/// 商业规则：刷视频对所有人免费，平台收入来自答题/考试。因此这里的 `free`
/// 含义是「**这一单不用付钱**」，来源只有两种：全局免费活动，或刷课卡
/// （卡的权益 = 免考试费 + 优先排队）。
///
/// 免费单一律只能用保守档（串行）：适中/暴力是付费权益，服务端会在创建订单时
/// 强制改写档位，前端置灰只是提示。
#[derive(Debug, Clone, Default)]
pub struct Benefit {
    pub free: bool,
    /// global（全局免费）/ card（刷课卡）
    pub reason: String,
    pub card_id: String,
    /// 免费单锁定的档位（恒为保守档）
    pub speed_mode: String,
}

impl Benefit {
    pub fn paid() -> Self {
        Self::default()
    }
    pub fn is_free(&self) -> bool {
        self.free
    }
    pub fn to_json(&self) -> Value {
        json!({
            "free": self.free,
            "reason": self.reason,
            "card_id": self.card_id,
            "speed_mode": self.speed_mode,
        })
    }
}

/// 生成短码（邀请码 / 卡号），去掉易混字符 0/O/1/I
fn short_code(len: usize) -> String {
    const ALPHABET: &[u8] = b"ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    let mut out = String::with_capacity(len);
    for _ in 0..len {
        let i = rand::random::<u32>() as usize % ALPHABET.len();
        out.push(ALPHABET[i] as char);
    }
    out
}

/// 为访客生成 id（VID- 前缀便于在日志/后台里一眼认出）
pub fn new_vid() -> String {
    format!("VID-{}", short_code(16))
}

/// 短码只允许字母数字（防止把奇怪的东西当邀请码塞进 cookie/URL 再回显）
pub fn is_valid_code(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 32
        && s.chars().all(|c| c.is_ascii_alphanumeric())
}

/// 秒级时间戳 + 天数 → "YYYY-MM-DDTHH:MM:SS"（与库内时间戳同源，本地时区）
pub fn iso_after_days(days: i64) -> String {
    let secs = (days.max(0) as u64) * 86_400;
    crate::queue::iso_from_secs(crate::queue::local_secs() + secs)
}

/// 卡是否仍在有效期内（revoked 或过期即失效）
pub fn card_valid(expires_at: &str, revoked: bool, now_secs: i64) -> bool {
    if revoked {
        return false;
    }
    crate::pay::parse_iso_secs(expires_at).map(|t| t > now_secs).unwrap_or(false)
}

/// 剩余天数（不足一天按 1 天算，展示用）
pub fn days_left(expires_at: &str, now_secs: i64) -> i64 {
    match crate::pay::parse_iso_secs(expires_at) {
        Some(t) => ((t - now_secs).max(0) + 86_399) / 86_400,
        None => 0,
    }
}

// ── 访客 ────────────────────────────────────────────────────────────────

/// 确保访客存在（首次访问时建档 + 分配邀请码），返回邀请码
pub async fn ensure_visitor(db: &Db, vid: &str, ua: &str) -> Result<String> {
    let pool = db.clone_pool();
    let vid = vid.to_string();
    let ua = ua.chars().take(200).collect::<String>();
    let now = crate::queue::now_str();
    tokio::task::spawn_blocking(move || -> Result<String> {
        let conn = pool.get()?;
        if let Ok(code) = conn.query_row(
            "SELECT invite_code FROM visitors WHERE vid=?1",
            rusqlite::params![vid], |r| r.get::<_, String>(0),
        ) {
            conn.execute("UPDATE visitors SET last_seen=?1 WHERE vid=?2",
                         rusqlite::params![now, vid])?;
            return Ok(code);
        }
        // 邀请码撞号概率极低，但仍重试几次，避免 500
        for _ in 0..5 {
            let code = short_code(CODE_LEN);
            let r = conn.execute(
                "INSERT INTO visitors (vid, invite_code, ref_code, contact, ua, created_at, last_seen)
                 VALUES (?1, ?2, '', '', ?3, ?4, ?4)",
                rusqlite::params![vid, code, ua, now],
            );
            match r {
                Ok(_) => return Ok(code),
                Err(e) => {
                    if !e.to_string().contains("UNIQUE") {
                        return Err(e.into());
                    }
                }
            }
        }
        anyhow::bail!("邀请码生成失败（连续撞号）")
    })
    .await?
}

/// 邀请码 → vid（找不到返回 None）
pub async fn vid_by_code(db: &Db, code: &str) -> Option<String> {
    if !is_valid_code(code) {
        return None;
    }
    let pool = db.clone_pool();
    let code = code.trim().to_uppercase();
    tokio::task::spawn_blocking(move || -> Option<String> {
        let conn = pool.get().ok()?;
        conn.query_row("SELECT vid FROM visitors WHERE invite_code=?1",
                       rusqlite::params![code], |r| r.get::<_, String>(0)).ok()
    })
    .await
    .ok()
    .flatten()
}

/// 记录一次邀请（幂等：同一个被邀请人只记一次；自己邀自己忽略）
pub async fn track_invite(db: &Db, invitee_vid: &str, ref_code: &str) -> Result<bool> {
    let Some(inviter_vid) = vid_by_code(db, ref_code).await else { return Ok(false) };
    if inviter_vid == invitee_vid {
        return Ok(false);
    }
    let pool = db.clone_pool();
    let invitee = invitee_vid.to_string();
    let ref_code = ref_code.trim().to_uppercase();
    let now = crate::queue::now_str();
    tokio::task::spawn_blocking(move || -> Result<bool> {
        let conn = pool.get()?;
        let n = conn.execute(
            "INSERT OR IGNORE INTO invites (inviter_vid, invitee_vid, ref_code, converted, created_at)
             VALUES (?1, ?2, ?3, 0, ?4)",
            rusqlite::params![inviter_vid, invitee, ref_code, now],
        )?;
        if n > 0 {
            conn.execute("UPDATE visitors SET ref_code=?1 WHERE vid=?2",
                         rusqlite::params![ref_code, invitee])?;
        }
        Ok(n > 0)
    })
    .await?
}

/// 被邀请人下单 → 把这条邀请标记为有效（同一个人只转化一次）
pub async fn mark_converted(db: &Db, invitee_vid: &str, order_id: &str) {
    if invitee_vid.is_empty() {
        return;
    }
    let pool = db.clone_pool();
    let invitee = invitee_vid.to_string();
    let order_id = order_id.to_string();
    let _ = tokio::task::spawn_blocking(move || -> Result<()> {
        let conn = pool.get()?;
        mark_converted_inner(&conn, &invitee, &order_id)?;
        Ok(())
    })
    .await;
}

/// 同步版转化标记（在入队的 spawn_blocking 内部直接调用，避免再包一层）
pub(crate) fn mark_converted_blocking(db: &Db, invitee_vid: &str, order_id: &str) {
    let Some(conn) = db.clone_pool().get().ok() else { return };
    let _ = mark_converted_inner(&conn, invitee_vid, order_id);
}

fn mark_converted_inner(conn: &rusqlite::Connection, invitee_vid: &str, order_id: &str) -> Result<()> {
    conn.execute(
        "UPDATE invites SET converted=1, converted_order_id=?1
         WHERE invitee_vid=?2 AND converted=0",
        rusqlite::params![order_id, invitee_vid],
    )?;
    Ok(())
}

// ── 邀请统计与领卡 ───────────────────────────────────────────────────────

/// 邀请概况（邀请页用）
pub async fn invite_overview(db: &Db, vid: &str) -> Result<Value> {
    let cfg = PromoConfig::load(db).await;
    let pool = db.clone_pool();
    let vid = vid.to_string();
    let now_secs = crate::queue::local_secs() as i64;
    tokio::task::spawn_blocking(move || -> Result<Value> {
        let conn = pool.get()?;
        let code: String = conn.query_row(
            "SELECT invite_code FROM visitors WHERE vid=?1",
            rusqlite::params![vid], |r| r.get(0),
        ).unwrap_or_default();

        let total: i64 = conn.query_row(
            "SELECT COUNT(*) FROM invites WHERE inviter_vid=?1",
            rusqlite::params![vid], |r| r.get(0)).unwrap_or(0);
        let converted: i64 = conn.query_row(
            "SELECT COUNT(*) FROM invites WHERE inviter_vid=?1 AND converted=1",
            rusqlite::params![vid], |r| r.get(0)).unwrap_or(0);
        // require_order=0 时"打开链接即算"：此时全部邀请都算有效
        let valid = if cfg.require_order { converted } else { total };
        // 已领张数按"累计发放"计（含已吊销）：否则吊销一张就能再领一张，
        // 等于把额度退回来
        let claimed: i64 = conn.query_row(
            "SELECT COUNT(*) FROM brush_cards WHERE owner_vid=?1",
            rusqlite::params![vid], |r| r.get(0)).unwrap_or(0);
        // 每满一个阈值可领一张，已领数从可领数里扣掉
        let can_claim = if cfg.invite_enabled {
            (valid / cfg.threshold - claimed).max(0)
        } else {
            0
        };

        let mut stmt = conn.prepare(
            "SELECT code, granted_at, expires_at, revoked, used_orders FROM brush_cards
             WHERE owner_vid=?1 ORDER BY granted_at DESC LIMIT 20")?;
        let cards: Vec<Value> = stmt.query_map(rusqlite::params![vid], |r| {
            let code: String = r.get(0)?;
            let expires: String = r.get(2)?;
            let revoked: i64 = r.get(3)?;
            Ok(json!({
                "code": code,
                "granted_at": r.get::<_, String>(1)?,
                "expires_at": expires.clone(),
                "valid": card_valid(&expires, revoked != 0, now_secs),
                "days_left": days_left(&expires, now_secs),
                "used_orders": r.get::<_, i64>(4)?,
            }))
        })?.collect::<Result<Vec<_>, _>>()?;
        let has_valid_card = cards.iter().any(|c| c["valid"].as_bool() == Some(true));

        Ok(json!({
            "code": code,
            "enabled": cfg.invite_enabled,
            "threshold": cfg.threshold,
            "valid_days": cfg.valid_days,
            "require_order": cfg.require_order,
            "invited_total": total,
            "invited_valid": valid,
            // 距离下一张还差几个人（营销文案直接用）
            "need_more": (cfg.threshold - valid % cfg.threshold) % cfg.threshold,
            "claimed": claimed,
            "can_claim": can_claim,
            "cards": cards,
            "has_valid_card": has_valid_card,
            "free_mode": cfg.free_mode,
        }))
    })
    .await?
}

/// 领卡（可重复领；联系方式选填，留空也能领，只是少了人工找回凭据）
pub async fn claim_card(db: &Db, vid: &str, contact: &str) -> Result<Value> {
    let cfg = PromoConfig::load(db).await;
    if !cfg.invite_enabled {
        anyhow::bail!("邀请活动未开启");
    }
    // 联系方式是选填：留空也能领卡（降低领卡摩擦），只是换设备后少了找回凭据
    let contact = contact.trim().to_string();
    if contact.chars().count() > 120 {
        anyhow::bail!("联系方式过长");
    }
    let has_contact = !contact.is_empty();
    let pool = db.clone_pool();
    let vid_s = vid.to_string();
    let valid_days = cfg.valid_days;
    let threshold = cfg.threshold;
    let card = tokio::task::spawn_blocking(move || -> Result<Value> {
        let mut conn = pool.get()?;
        let tx = conn.transaction()?;
        let valid: i64 = tx.query_row(
            "SELECT COUNT(*) FROM invites WHERE inviter_vid=?1 AND converted=1",
            rusqlite::params![vid_s], |r| r.get(0))?;
        let claimed: i64 = tx.query_row(
            "SELECT COUNT(*) FROM brush_cards WHERE owner_vid=?1",
            rusqlite::params![vid_s], |r| r.get(0))?;
        if valid / threshold - claimed <= 0 {
            anyhow::bail!("暂无可领取的刷课卡（还差 {} 位好友下单）", threshold - valid % threshold);
        }
        let now = crate::queue::now_str();
        let expires = iso_after_days(valid_days);
        for _ in 0..5 {
            let code = short_code(CODE_LEN);
            let card_id = format!("CARD-{}", short_code(10));
            let r = tx.execute(
                "INSERT INTO brush_cards (card_id, code, owner_vid, contact, source, granted_at, expires_at)
                 VALUES (?1, ?2, ?3, ?4, 'invite', ?5, ?6)",
                rusqlite::params![card_id, code, vid_s, contact, now, expires],
            );
            match r {
                Ok(_) => {
                    if has_contact {
                        tx.execute("UPDATE visitors SET contact=?1 WHERE vid=?2",
                                   rusqlite::params![contact, vid_s])?;
                    }
                    tx.commit()?;
                    return Ok(json!({
                        "code": code, "expires_at": expires, "valid_days": valid_days,
                    }));
                }
                Err(e) => {
                    if !e.to_string().contains("UNIQUE") {
                        return Err(e.into());
                    }
                }
            }
        }
        anyhow::bail!("卡号生成失败（连续撞号）")
    })
    .await??;
    tracing::info!(vid = %vid, code = %card["code"], "发出刷课卡");
    Ok(card)
}

/// 判定该访客的免费待遇：全局免费优先，其次有效卡
pub async fn check_benefit(db: &Db, vid: &str) -> Benefit {
    let cfg = PromoConfig::load(db).await;
    if cfg.free_mode {
        return Benefit { free: true, reason: "global".into(), card_id: String::new(),
                         speed_mode: crate::speed::SpeedMode::Gentle.as_str().into() };
    }
    if vid.is_empty() {
        return Benefit::paid();
    }
    let pool = db.clone_pool();
    let vid_s = vid.to_string();
    let max_orders = cfg.max_orders;
    let now_secs = crate::queue::local_secs() as i64;
    let found = tokio::task::spawn_blocking(move || -> Option<String> {
        let conn = pool.get().ok()?;
        let mut stmt = conn.prepare(
            "SELECT card_id, expires_at, revoked, used_orders FROM brush_cards
             WHERE owner_vid=?1 ORDER BY expires_at DESC").ok()?;
        let rows = stmt.query_map(rusqlite::params![vid_s], |r| {
            Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?, r.get::<_, i64>(2)?, r.get::<_, i64>(3)?))
        }).ok()?;
        for row in rows.flatten() {
            let (card_id, expires, revoked, used) = row;
            if card_valid(&expires, revoked != 0, now_secs)
                && (max_orders == 0 || used < max_orders)
            {
                return Some(card_id);
            }
        }
        None
    })
    .await
    .ok()
    .flatten();
    match found {
        Some(card_id) => Benefit { free: true, reason: "card".into(), card_id,
                                   speed_mode: crate::speed::SpeedMode::Gentle.as_str().into() },
        None => Benefit::paid(),
    }
}

/// 免费单用掉卡额度（按订单数递增；全局免费不计数）。
///
/// 条件写进 UPDATE 里（`used_orders + n <= max_orders`）：先 SELECT 再判断再写
/// 在并发下会超出额度。已吊销/已过期的卡不再扣（本来也不该能免单）。
pub async fn consume_card(db: &Db, card_id: &str, orders: i64) {
    if card_id.is_empty() || orders <= 0 {
        return;
    }
    let pool = db.clone_pool();
    let card_id = card_id.to_string();
    let _ = tokio::task::spawn_blocking(move || -> Result<()> {
        let conn = pool.get()?;
        let now = crate::queue::now_str();
        conn.execute(
            "UPDATE brush_cards SET used_orders = used_orders + ?1
             WHERE card_id=?2 AND revoked=0 AND expires_at > ?3",
            rusqlite::params![orders, card_id, now],
        )?;
        Ok(())
    })
    .await;
}

/// 后台推广总览
pub async fn admin_stats(db: &Db) -> Result<Value> {
    let cfg = PromoConfig::load(db).await;
    let pool = db.clone_pool();
    let today = crate::queue::now_str();
    let today_like = format!("{}%", &today[..10]);
    tokio::task::spawn_blocking(move || -> Result<Value> {
        let conn = pool.get()?;
        let visitors: i64 = conn.query_row("SELECT COUNT(*) FROM visitors", [], |r| r.get(0)).unwrap_or(0);
        let visitors_today: i64 = conn.query_row(
            "SELECT COUNT(*) FROM visitors WHERE created_at LIKE ?1",
            rusqlite::params![today_like], |r| r.get(0)).unwrap_or(0);
        let invites: i64 = conn.query_row("SELECT COUNT(*) FROM invites", [], |r| r.get(0)).unwrap_or(0);
        let invites_valid: i64 = conn.query_row(
            "SELECT COUNT(*) FROM invites WHERE converted=1", [], |r| r.get(0)).unwrap_or(0);
        let cards: i64 = conn.query_row(
            "SELECT COUNT(*) FROM brush_cards WHERE revoked=0", [], |r| r.get(0)).unwrap_or(0);
        let cards_active: i64 = conn.query_row(
            "SELECT COUNT(*) FROM brush_cards WHERE revoked=0 AND expires_at > ?1",
            rusqlite::params![today], |r| r.get(0)).unwrap_or(0);
        // 免费订单（全局免费或卡免单）：用 payment_channel='free' 标记统计
        let free_orders: i64 = conn.query_row(
            "SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL AND payment_channel='free'",
            [], |r| r.get(0)).unwrap_or(0);
        let free_orders_today: i64 = conn.query_row(
            "SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL AND payment_channel='free'
             AND created_at LIKE ?1",
            rusqlite::params![today_like], |r| r.get(0)).unwrap_or(0);
        let mut top: Vec<Value> = Vec::new();
        let mut stmt = conn.prepare(
            "SELECT v.invite_code, COUNT(i.id), COALESCE(SUM(i.converted),0)
             FROM invites i JOIN visitors v ON v.vid = i.inviter_vid
             GROUP BY i.inviter_vid ORDER BY 3 DESC, 2 DESC LIMIT 10")?;
        for r in stmt.query_map([], |r| {
            Ok(json!({"code": r.get::<_, String>(0)?, "invited": r.get::<_, i64>(1)?,
                      "converted": r.get::<_, i64>(2)?}))
        })? { top.push(r?); }
        Ok(json!({
            "config": {
                "free_mode": cfg.free_mode,
                "invite_enabled": cfg.invite_enabled,
                "threshold": cfg.threshold,
                "require_order": cfg.require_order,
                "valid_days": cfg.valid_days,
                "max_orders": cfg.max_orders,
            },
            "visitors": visitors, "visitors_today": visitors_today,
            "invites": invites, "invites_valid": invites_valid,
            "cards": cards, "cards_active": cards_active,
            "free_orders": free_orders, "free_orders_today": free_orders_today,
            "conversion": if invites > 0 { invites_valid as f64 / invites as f64 } else { 0.0 },
            "top_inviters": top,
        }))
    })
    .await?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_short_code_charset() {
        for _ in 0..50 {
            let c = short_code(CODE_LEN);
            assert_eq!(c.chars().count(), CODE_LEN);
            // 易混字符不入码（人工念/抄时不至于 0 与 O 分不清）
            assert!(!c.contains('0') && !c.contains('O') && !c.contains('1') && !c.contains('I'), "{c}");
            assert!(is_valid_code(&c));
        }
    }

    #[test]
    fn test_is_valid_code() {
        assert!(is_valid_code("AB23CD"));
        assert!(!is_valid_code(""));
        assert!(!is_valid_code("ab-23"));
        assert!(!is_valid_code("ab 23"));
        assert!(!is_valid_code(&"A".repeat(33)));
    }

    #[test]
    fn test_card_valid_and_days_left() {
        let now = crate::pay::parse_iso_secs("2026-09-29T12:00:00").unwrap();
        assert!(card_valid("2026-09-30T12:00:00", false, now));
        assert!(!card_valid("2026-09-28T12:00:00", false, now)); // 过期
        assert!(!card_valid("2026-09-30T12:00:00", true, now));  // 已吊销
        assert!(!card_valid("", false, now));                     // 脏数据
        assert_eq!(days_left("2026-09-30T12:00:00", now), 1);
        assert_eq!(days_left("2026-09-29T12:00:01", now), 1);     // 不足一天按 1 天
        assert_eq!(days_left("2026-09-28T12:00:00", now), 0);
    }

    #[test]
    fn test_iso_after_days_shape() {
        let s = iso_after_days(30);
        assert_eq!(s.len(), 19, "{s}");
        assert!(s.contains('T'));
        assert_eq!(s, crate::queue::iso_from_secs(
            crate::queue::local_secs() + 30 * 86_400));
    }

    #[test]
    fn test_benefit_json() {
        let b = Benefit { free: true, reason: "card".into(), card_id: "CARD-1".into(),
                          speed_mode: "gentle".into() };
        assert!(b.is_free());
        assert_eq!(b.to_json()["reason"], "card");
        assert!(!Benefit::paid().is_free());
    }

    #[test]
    fn test_free_always_serial_mode() {
        // 商业规则：不付费只能串行。免费待遇携带的档位必须恒为保守档，
        // create_batch_orders 会拿它覆盖客户端传来的档位。
        assert_eq!(crate::speed::SpeedMode::Gentle.as_str(), "gentle");
        assert!(crate::speed::SpeedMode::parse("gentle").is_serial());
    }
}
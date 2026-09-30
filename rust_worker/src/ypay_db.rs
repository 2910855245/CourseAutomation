//! YPay 支付 SQL 层 — 对齐 api/db/payment_db.py + api/db/order_db.py 支付相关方法
//!
//! rusqlite 直写，全部同步函数（调用方用 spawn_blocking 包裹，对齐 db.rs/queue.rs 风格）。
//! 表结构由 Python 侧 create_all 保证（迁移期双跑共享同一 data/*.db）。

use anyhow::{Context, Result};
use rusqlite::{params, Connection};
use serde_json::{json, Value};

use crate::db::Db;

/// Vmq 推送类型 → 渠道字符串（对齐 payment_db.py 的 {1:wxpay, 2:alipay, 3:lkl}）
pub fn pay_type_str(pay_type: i64) -> &'static str {
    match pay_type {
        2 => "alipay",
        3 => "lkl",
        _ => "wxpay",
    }
}

/// 渠道字符串 → Vmq 推送类型（对齐 _ypay_order_to_dict 的反映射）
pub fn type_to_pay_type(type_str: &str) -> i64 {
    match type_str {
        "alipay" => 2,
        "lkl" => 3,
        _ => 1,
    }
}

// ── ypay_order 行 → JSON（对齐 _ypay_order_to_dict）────────────────────────

fn ypay_order_row_to_json(r: &rusqlite::Row) -> rusqlite::Result<Value> {
    let type_str: String = r.get(3)?;
    Ok(json!({
        "id": r.get::<_, i64>(0)?,
        "trade_no": r.get::<_, String>(1)?,
        "out_trade_no": r.get::<_, String>(2)?,
        "type": type_str,
        "pay_type": type_to_pay_type(&type_str),
        "name": r.get::<_, Option<String>>(4)?.unwrap_or_default(),
        "money": r.get::<_, f64>(5)?,
        "truemoney": r.get::<_, f64>(6)?,
        "qrcode": r.get::<_, Option<String>>(7)?.unwrap_or_default(),
        "h5_qrurl": r.get::<_, Option<String>>(8)?.unwrap_or_default(),
        "status": r.get::<_, i64>(9)?,
        "account_id": r.get::<_, i64>(10)?,
        "notify_url": r.get::<_, Option<String>>(11)?.unwrap_or_default(),
        "return_url": r.get::<_, Option<String>>(12)?.unwrap_or_default(),
        "ip": r.get::<_, Option<String>>(13)?.unwrap_or_default(),
        "create_time": r.get::<_, Option<String>>(14)?.unwrap_or_default(),
        "out_time": r.get::<_, Option<String>>(15)?.unwrap_or_default(),
        "end_time": r.get::<_, Option<String>>(16)?,
    }))
}

const YPAY_ORDER_COLS: &str =
    "id, trade_no, out_trade_no, type, name, money, truemoney, qrcode, h5_qrurl,
     status, account_id, notify_url, return_url, ip, create_time, out_time, end_time";

// ── ypay_account 行 → JSON（对齐 ypay_pick_channel/ypay_list_accounts 字段集）

fn ypay_account_row_to_json(r: &rusqlite::Row) -> rusqlite::Result<Value> {
    Ok(json!({
        "id": r.get::<_, i64>(0)?,
        "type": r.get::<_, Option<String>>(1)?.unwrap_or_default(),
        "code": r.get::<_, Option<String>>(2)?.unwrap_or_default(),
        "name": r.get::<_, Option<String>>(3)?.unwrap_or_default(),
        "status": r.get::<_, i64>(4)?,
        "is_status": r.get::<_, i64>(5)?,
        "qr_url": r.get::<_, Option<String>>(6)?.unwrap_or_default(),
        "zfb_pid": r.get::<_, Option<String>>(7)?.unwrap_or_default(),
        "alipay_appid": r.get::<_, Option<String>>(8)?.unwrap_or_default(),
        "alipay_public_key": r.get::<_, Option<String>>(9)?.unwrap_or_default(),
        "alipay_private_key": r.get::<_, Option<String>>(10)?.unwrap_or_default(),
        "cookie": r.get::<_, Option<String>>(11)?.unwrap_or_default(),
        "wx_guid": r.get::<_, Option<String>>(12)?.unwrap_or_default(),
        "qq": r.get::<_, Option<String>>(13)?.unwrap_or_default(),
        "cloud_id": r.get::<_, Option<String>>(14)?.unwrap_or_default(),
        "qr_type": r.get::<_, Option<String>>(15)?.unwrap_or_default(),
        "memo": r.get::<_, Option<String>>(16)?.unwrap_or_default(),
        "remark": r.get::<_, Option<String>>(17)?.unwrap_or_default(),
        "channel_mode": r.get::<_, i64>(18)?,
        "app_public_cert": r.get::<_, Option<String>>(19)?.unwrap_or_default(),
        "alipay_public_cert": r.get::<_, Option<String>>(20)?.unwrap_or_default(),
        "alipay_root_cert": r.get::<_, Option<String>>(21)?.unwrap_or_default(),
        "create_time": r.get::<_, Option<String>>(22)?.unwrap_or_default(),
    }))
}

const YPAY_ACCOUNT_COLS: &str =
    "id, type, code, name, status, is_status, qr_url, zfb_pid, alipay_appid,
     alipay_public_key, alipay_private_key, cookie, wx_guid, qq, cloud_id,
     qr_type, memo, remark, channel_mode, app_public_cert, alipay_public_cert,
     alipay_root_cert, create_time";

// ── orders 行 → JSON（对齐 order_db._order_to_dict，密码不脱敏——内部调用用）

fn order_row_to_json(r: &rusqlite::Row) -> rusqlite::Result<Value> {
    Ok(json!({
        "order_id": r.get::<_, String>(0)?,
        "out_trade_no": r.get::<_, Option<String>>(1)?.unwrap_or_default(),
        "payment_trade_no": r.get::<_, Option<String>>(2)?.unwrap_or_default(),
        "payment_channel": r.get::<_, Option<String>>(3)?.unwrap_or_default(),
        "payment_time": r.get::<_, Option<String>>(4)?,
        "paid_processed": r.get::<_, Option<String>>(5)?.unwrap_or_default(),
        "user_id": r.get::<_, Option<String>>(6)?.unwrap_or_default(),
        "customer_name": r.get::<_, Option<String>>(7)?.unwrap_or_default(),
        "customer_contact": r.get::<_, Option<String>>(8)?.unwrap_or_default(),
        "username": r.get::<_, Option<String>>(9)?.unwrap_or_default(),
        "password": r.get::<_, Option<String>>(10)?.unwrap_or_default(),
        "website_id": r.get::<_, i64>(11)?,
        "task_type": r.get::<_, Option<String>>(12)?.unwrap_or_default(),
        "course_ids": serde_json::from_str::<Value>(
            &r.get::<_, Option<String>>(13)?.unwrap_or_else(|| "[]".into())
        ).unwrap_or(json!([])),
        "video_count": r.get::<_, i64>(14)?,
        "exam_count": r.get::<_, i64>(15)?,
        "price": r.get::<_, f64>(16)?,
        "notes": r.get::<_, Option<String>>(17)?.unwrap_or_default(),
        "status": r.get::<_, Option<String>>(18)?.unwrap_or_default(),
        "paid": r.get::<_, i64>(19)? != 0,
        "task_id": r.get::<_, Option<String>>(20)?,
        "admin_note": r.get::<_, Option<String>>(21)?.unwrap_or_default(),
        "created_at": r.get::<_, Option<String>>(22)?.unwrap_or_default(),
        "updated_at": r.get::<_, Option<String>>(23)?,
        "accepted_at": r.get::<_, Option<String>>(24)?,
        "started_at": r.get::<_, Option<String>>(25)?,
        "finished_at": r.get::<_, Option<String>>(26)?,
        // 刷课节奏档位：历史订单该列为空 → 显示回退均衡
        "speed_mode": r.get::<_, Option<String>>(27)?.unwrap_or_else(|| "balanced".into()),
        // 访客标识：付款成功后据此归因"有效邀请"（必须在 ORDER_COLS 里选出来，
        // 否则 enqueue_order_sync 里取到的永远是空）
        "vid": r.get::<_, Option<String>>(28)?.unwrap_or_default(),
    }))
}

const ORDER_COLS: &str = "order_id, out_trade_no, ezfpy_trade_no, payment_channel, payment_time,
     paid_processed, user_id, customer_name, customer_contact, username, password,
     website_id, task_type, course_ids, video_count, exam_count, price, notes,
     status, paid, task_id, admin_note, created_at, updated_at, accepted_at,
     started_at, finished_at, speed_mode, vid";

impl Db {
    // ── ypay_settings（对齐 ypay_setting_get/set）──────────────────────────

    /// 读 ypay 配置项（对齐 ypay_setting_get，空值回退 default）
    pub fn ypay_setting_get_sync(&self, key: &str, default: &str) -> String {
        let pool = self.clone_pool();
        let key = key.to_string();
        let default = default.to_string();
        let v: Option<Option<String>> = (|| {
            let conn = pool.get().ok()?;
            conn.query_row(
                "SELECT value FROM ypay_settings WHERE key=?1",
                params![key],
                |r| r.get(0),
            )
            .ok()
        })();
        v.flatten()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .unwrap_or(default)
    }

    /// 写 ypay 配置项（对齐 ypay_setting_set：merge 语义）
    pub fn ypay_setting_set_sync(&self, key: &str, value: &str) -> Result<()> {
        let pool = self.clone_pool();
        let key = key.to_string();
        let value = value.trim().to_string();
        let conn = pool.get().context("获取连接失败")?;
        conn.execute(
            "INSERT INTO ypay_settings (key, value) VALUES (?1, ?2)
             ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            params![key, value],
        )?;
        Ok(())
    }

    // ── 浮动价锁（对齐 ypay_lock_price / ypay_release_price）───────────────

    /// 占用浮动价：唯一冲突则 +0.01 重试，最多 10 次（对齐 ypay_lock_price）
    pub fn ypay_lock_price_sync(&self, price: f64, oid: &str) -> Option<f64> {
        let pool = self.clone_pool();
        let oid = oid.to_string();
        let mut price = price;
        let conn = pool.get().ok()?;
        let now = crate::queue::now_str();
        for _ in 0..10 {
            match conn.execute(
                "INSERT INTO ypay_tmp_price (price, oid, create_time) VALUES (?1, ?2, ?3)",
                params![price, oid, now],
            ) {
                Ok(_) => return Some(price),
                Err(rusqlite::Error::SqliteFailure(e, _))
                    if e.code == rusqlite::ErrorCode::ConstraintViolation =>
                {
                    price = ((price + 0.01) * 100.0).round() / 100.0;
                }
                Err(e) => {
                    tracing::warn!(error = %e, "ypay_lock_price 失败");
                    return None;
                }
            }
        }
        None
    }

    /// 释放浮动价（对齐 ypay_release_price：按 price 删）
    pub fn ypay_release_price_sync(&self, price: f64) {
        let pool = self.clone_pool();
        if let Ok(conn) = pool.get() {
            let _ = conn.execute("DELETE FROM ypay_tmp_price WHERE price=?1", params![price]);
        }
    }

    /// 渠道在途未支付金额列表（对齐 ypay_get_active_prices）
    pub fn ypay_get_active_prices_sync(&self, account_id: i64) -> Vec<f64> {
        let pool = self.clone_pool();
        let now = crate::queue::now_str();
        let Ok(conn) = pool.get() else { return vec![] };
        let Ok(mut stmt) = conn.prepare(
            "SELECT truemoney FROM ypay_order
             WHERE account_id=?1 AND status=0 AND out_time > ?2",
        ) else {
            return vec![];
        };
        stmt.query_map(params![account_id, now], |r| r.get(0))
            .map(|rows| rows.flatten().collect())
            .unwrap_or_default()
    }

    // ── 支付单（对齐 ypay_find_pending_by_price / get_order / mark_paid 等）

    /// 按金额+类型找待支付单（对齐 ypay_find_pending_by_price：abs 容差 0.01）
    pub fn ypay_find_pending_by_price_sync(&self, price: f64, pay_type: i64) -> Option<Value> {
        let pool = self.clone_pool();
        let type_str = pay_type_str(pay_type);
        let conn = pool.get().ok()?;
        conn.query_row(
            &format!(
                "SELECT {YPAY_ORDER_COLS} FROM ypay_order
                 WHERE abs(truemoney - ?1) < 0.01 AND type=?2 AND status=0 LIMIT 1"
            ),
            params![price, type_str],
            ypay_order_row_to_json,
        )
        .ok()
    }

    /// 按 trade_no 查支付单（对齐 ypay_get_order）
    pub fn ypay_get_order_sync(&self, trade_no: &str) -> Option<Value> {
        let pool = self.clone_pool();
        let trade_no = trade_no.to_string();
        let conn = pool.get().ok()?;
        conn.query_row(
            &format!("SELECT {YPAY_ORDER_COLS} FROM ypay_order WHERE trade_no=?1"),
            params![trade_no],
            ypay_order_row_to_json,
        )
        .ok()
    }

    /// 按 out_trade_no 查支付单（对齐 ypay_get_order_by_out_trade_no）
    pub fn ypay_get_order_by_out_trade_no_sync(&self, out_trade_no: &str) -> Option<Value> {
        let pool = self.clone_pool();
        let out_trade_no = out_trade_no.to_string();
        let conn = pool.get().ok()?;
        conn.query_row(
            &format!("SELECT {YPAY_ORDER_COLS} FROM ypay_order WHERE out_trade_no=?1"),
            params![out_trade_no],
            ypay_order_row_to_json,
        )
        .ok()
    }

    /// 创建支付单（对齐 ypay_create_order，返回 dict 或 None）
    #[allow(clippy::too_many_arguments)]
    pub fn ypay_create_order_sync(
        &self,
        trade_no: &str,
        out_trade_no: &str,
        pay_type: i64,
        type_str: &str,
        name: &str,
        money: f64,
        truemoney: f64,
        account_id: i64,
        qrcode: &str,
        h5_qrurl: &str,
        notify_url: &str,
        return_url: &str,
        ip: &str,
        out_time: &str,
    ) -> Option<Value> {
        let pool = self.clone_pool();
        let conn = pool.get().ok()?;
        let now = crate::queue::now_str();
        let id = conn
            .execute(
                "INSERT INTO ypay_order
                 (type, account_id, trade_no, out_trade_no, name, money, truemoney,
                  qrcode, h5_qrurl, status, notify_url, return_url, ip, create_time, out_time)
                 VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,0,?10,?11,?12,?13,?14)",
                params![
                    type_str,
                    account_id,
                    trade_no,
                    out_trade_no,
                    name,
                    money,
                    truemoney,
                    qrcode,
                    h5_qrurl,
                    notify_url,
                    return_url,
                    ip,
                    now,
                    out_time
                ],
            )
            .map_err(|e| tracing::warn!(error = %e, "ypay_create_order 失败"))
            .ok()?;
        let _ = id;
        let id: i64 = conn.last_insert_rowid();
        Some(json!({
            "id": id,
            "trade_no": trade_no,
            "out_trade_no": out_trade_no,
            "type": type_str,
            "pay_type": pay_type,
            "name": name,
            "money": money,
            "truemoney": truemoney,
            "qrcode": qrcode,
            "h5_qrurl": h5_qrurl,
            "status": 0,
            "account_id": account_id,
            "notify_url": notify_url,
            "return_url": return_url,
            "ip": ip,
            "create_time": now,
            "out_time": out_time,
            "end_time": Value::Null,
        }))
    }

    /// 标记支付单已付（对齐 ypay_mark_paid：status=1 + end_time + 删价格锁）
    pub fn ypay_mark_paid_sync(&self, trade_no: &str) -> bool {
        let pool = self.clone_pool();
        let Ok(mut conn) = pool.get() else {
            return false;
        };
        let now = crate::queue::now_str();
        let result = (|| -> Result<()> {
            let tx = conn.transaction()?;
            let updated = tx.execute(
                "UPDATE ypay_order SET status=1, end_time=?1 WHERE trade_no=?2",
                params![now, trade_no],
            )?;
            if updated == 0 {
                anyhow::bail!("支付单不存在");
            }
            tx.execute("DELETE FROM ypay_tmp_price WHERE oid=?1", params![trade_no])?;
            tx.commit()?;
            Ok(())
        })();
        if let Err(e) = &result {
            tracing::warn!(error = %e, trade_no, "ypay_mark_paid 失败");
        }
        result.is_ok()
    }

    /// 关闭过期支付单（对齐 ypay_close_expired_orders，返回关闭数）
    pub fn ypay_close_expired_orders_sync(&self) -> usize {
        let pool = self.clone_pool();
        let Ok(mut conn) = pool.get() else { return 0 };
        let now = crate::queue::now_str();
        (|| -> Result<usize> {
            let tx = conn.transaction()?;
            let trade_nos: Vec<String> = {
                let mut stmt =
                    tx.prepare("SELECT trade_no FROM ypay_order WHERE status=0 AND out_time < ?1")?;
                let rows = stmt.query_map(params![now], |r| r.get(0))?;
                let mut v = Vec::new();
                for r in rows {
                    v.push(r?);
                }
                v
            };
            let count = trade_nos.len();
            for tn in &trade_nos {
                tx.execute(
                    "UPDATE ypay_order SET status=-1, end_time=?1 WHERE trade_no=?2",
                    params![now, tn],
                )?;
                tx.execute("DELETE FROM ypay_tmp_price WHERE oid=?1", params![tn])?;
            }
            tx.commit()?;
            Ok(count)
        })()
        .unwrap_or_else(|e| {
            tracing::warn!(error = %e, "ypay_close_expired_orders 失败");
            0
        })
    }

    // ── 收款渠道（对齐 ypay_pick_channel / list_accounts）──────────────────

    /// 随机选一个可用渠道（对齐 ypay_pick_channel：type+status=1+is_status=1，RANDOM()）
    pub fn ypay_pick_channel_sync(&self, pay_type: i64) -> Option<Value> {
        let pool = self.clone_pool();
        let type_str = pay_type_str(pay_type);
        let conn = pool.get().ok()?;
        conn.query_row(
            &format!(
                "SELECT {YPAY_ACCOUNT_COLS} FROM ypay_account
                 WHERE type=?1 AND status=1 AND is_status=1 ORDER BY RANDOM() LIMIT 1"
            ),
            params![type_str],
            ypay_account_row_to_json,
        )
        .ok()
    }

    /// 渠道列表（对齐 ypay_list_accounts，按 create_time 倒序）
    pub fn ypay_list_accounts_sync(&self) -> Vec<Value> {
        let pool = self.clone_pool();
        let Ok(conn) = pool.get() else { return vec![] };
        let Ok(mut stmt) = conn.prepare(&format!(
            "SELECT {YPAY_ACCOUNT_COLS} FROM ypay_account ORDER BY create_time DESC"
        )) else {
            return vec![];
        };
        stmt.query_map([], ypay_account_row_to_json)
            .map(|rows| rows.flatten().collect())
            .unwrap_or_default()
    }

    // ── 业务订单（对齐 order_db 的支付相关方法）────────────────────────────

    /// 查订单（对齐 order_db.get_order）
    pub fn get_order_sync(&self, order_id: &str) -> Option<Value> {
        let pool = self.clone_pool();
        let order_id = order_id.to_string();
        let conn = pool.get().ok()?;
        conn.query_row(
            &format!("SELECT {ORDER_COLS} FROM orders WHERE order_id=?1"),
            params![order_id],
            order_row_to_json,
        )
        .ok()
    }

    /// 按 out_trade_no 查订单列表（对齐 payment.py 批量分支的 OrderModel 查询）
    pub fn get_orders_by_out_trade_no_sync(&self, out_trade_no: &str) -> Vec<Value> {
        let pool = self.clone_pool();
        let out_trade_no = out_trade_no.to_string();
        let Ok(conn) = pool.get() else { return vec![] };
        let Ok(mut stmt) = conn.prepare(&format!(
            "SELECT {ORDER_COLS} FROM orders WHERE out_trade_no=?1"
        )) else {
            return vec![];
        };
        stmt.query_map(params![out_trade_no], order_row_to_json)
            .map(|rows| rows.flatten().collect())
            .unwrap_or_default()
    }

    /// 批量金额回退匹配（对齐 _payment_notify_sync 的 BATCH-% 未支付回退）
    pub fn find_unpaid_batch_orders_sync(&self) -> Vec<Value> {
        let pool = self.clone_pool();
        let Ok(conn) = pool.get() else { return vec![] };
        let Ok(mut stmt) = conn.prepare(&format!(
            "SELECT {ORDER_COLS} FROM orders
             WHERE out_trade_no LIKE 'BATCH-%' AND paid=0
               AND status IN ('pending','awaiting_payment')"
        )) else {
            return vec![];
        };
        stmt.query_map([], order_row_to_json)
            .map(|rows| rows.flatten().collect())
            .unwrap_or_default()
    }

    /// 找出「通道已收款、业务未入账」的订单号（后台对账用）。
    ///
    /// 判据是三个条件同时成立：通道单 `status=1`（钱确实到账，由验签回调写入）、
    /// 业务单未删除、业务单尚未进入 paid_processed='processed'。这类订单正是
    /// 「钱收了但系统没往前走」的悬空态，必须由后台主动发现并补齐 —— 不能依赖
    /// 用户还开着支付弹窗（关页面/断网就永远不会被补）。
    pub fn find_uncredited_paid_order_ids_sync(&self, limit: i64) -> Vec<String> {
        let pool = self.clone_pool();
        let Ok(conn) = pool.get() else { return vec![] };
        let Ok(mut stmt) = conn.prepare(
            "SELECT o.order_id FROM orders o
             JOIN ypay_order y ON y.out_trade_no = o.out_trade_no
             WHERE y.status = 1 AND y.deleted_at IS NULL
               AND o.deleted_at IS NULL
               AND (o.paid = 0 OR o.paid_processed IS NULL OR o.paid_processed != 'processed')
             ORDER BY o.created_at DESC LIMIT ?1",
        ) else {
            return vec![];
        };
        stmt.query_map(params![limit], |r| r.get::<_, String>(0))
            .map(|rows| rows.flatten().collect())
            .unwrap_or_default()
    }

    /// 更新订单 out_trade_no（对齐 update_order 的单字段用法，附 updated_at）
    pub fn update_order_out_trade_no_sync(&self, order_id: &str, out_trade_no: &str) -> bool {
        let pool = self.clone_pool();
        let order_id = order_id.to_string();
        let out_trade_no = out_trade_no.to_string();
        let Ok(conn) = pool.get() else { return false };
        conn.execute(
            "UPDATE orders SET out_trade_no=?1, updated_at=?2 WHERE order_id=?3",
            params![out_trade_no, crate::queue::now_str(), order_id],
        )
        .map(|n| n > 0)
        .unwrap_or(false)
    }

    /// 确认支付（对齐 confirm_payment：pending/awaiting_payment → paid）
    pub fn confirm_payment_sync(
        &self,
        order_id: &str,
        payment_trade_no: &str,
        payment_channel: &str,
    ) -> bool {
        let pool = self.clone_pool();
        let order_id = order_id.to_string();
        let payment_trade_no = payment_trade_no.to_string();
        let payment_channel = payment_channel.to_string();
        let Ok(conn) = pool.get() else { return false };
        let now = crate::queue::now_str();
        // 列名对齐 models.py：payment_trade_no 物理列是 ezfpy_trade_no
        conn.execute(
            "UPDATE orders SET status='paid', paid=1, ezfpy_trade_no=?1,
                    payment_channel=?2, payment_time=?3
             WHERE order_id=?4 AND status IN ('pending','awaiting_payment')",
            params![payment_trade_no, payment_channel, now, order_id],
        )
        .map(|n| n > 0)
        .unwrap_or(false)
    }

    /// 支付处理幂等闸门（对齐 claim_payment_processing：unprocessed → processing）
    pub fn claim_payment_processing_sync(&self, order_id: &str) -> bool {
        let pool = self.clone_pool();
        let order_id = order_id.to_string();
        let Ok(conn) = pool.get() else { return false };
        conn.execute(
            "UPDATE orders SET paid_processed='processing'
             WHERE order_id=?1 AND paid_processed='unprocessed'",
            params![order_id],
        )
        .map(|n| n > 0)
        .unwrap_or(false)
    }

    /// 标记支付处理完成（对齐 mark_payment_processed）
    pub fn mark_payment_processed_sync(&self, order_id: &str) -> bool {
        let pool = self.clone_pool();
        let order_id = order_id.to_string();
        let Ok(conn) = pool.get() else { return false };
        conn.execute(
            "UPDATE orders SET paid_processed='processed', updated_at=?1 WHERE order_id=?2",
            params![crate::queue::now_str(), order_id],
        )
        .map(|n| n > 0)
        .unwrap_or(false)
    }

    /// 订单开跑（对齐 start_order：paid/accepted/queued/retrying → running）
    pub fn start_order_sync(&self, order_id: &str, task_id: &str) -> bool {
        let pool = self.clone_pool();
        let order_id = order_id.to_string();
        let task_id = task_id.to_string();
        let Ok(conn) = pool.get() else { return false };
        let now = crate::queue::now_str();
        conn.execute(
            "UPDATE orders SET status='running', task_id=?1, started_at=?2, updated_at=?3
             WHERE order_id=?4 AND status IN ('paid','accepted','queued','retrying')",
            params![task_id, now, now, order_id],
        )
        .map(|n| n > 0)
        .unwrap_or(false)
    }

    /// 审计日志（对齐 config_db.audit_log：log_id=AL-{12hex大写}）
    pub fn audit_log_sync(&self, event_type: &str, order_id: &str, detail: &str) {
        let pool = self.clone_pool();
        let event_type = event_type.to_string();
        let order_id = order_id.to_string();
        let detail = detail.to_string();
        let Ok(conn) = pool.get() else { return };
        let log_id = format!("AL-{}", uuid_hex_upper(12));
        let _ = conn.execute(
            "INSERT INTO audit_logs (log_id, event_type, operator, detail, order_id, user_id, created_at)
             VALUES (?1, ?2, 'system', ?3, ?4, '', ?5)",
            params![log_id, event_type, detail, order_id, crate::queue::now_str()],
        );
    }

    // ── 队列（对齐 task_queue.submit_job 的去重语义 + get_queue_for_type）──

    /// 按 order_id 查最新队列任务状态（对齐 get_job_by_order_id，两表都查）
    pub fn queue_job_status_by_order_sync(&self, order_id: &str) -> Option<String> {
        let pool = self.clone_pool();
        let order_id = order_id.to_string();
        let conn = pool.get().ok()?;
        for table in ["queue_jobs_school", "queue_jobs_chaoxing"] {
            let status: Option<String> = conn
                .query_row(
                    &format!(
                        "SELECT status FROM {table} WHERE order_id=?1
                         ORDER BY created_at DESC LIMIT 1"
                    ),
                    params![order_id],
                    |r| r.get(0),
                )
                .ok();
            if status.is_some() {
                return status;
            }
        }
        None
    }

    /// 支付成功入队（对齐 order_service.enqueue_order 的队列写入部分）。
    /// task_type=chaoxing_points 进 chaoxing 表，其余进 school 表（对齐 get_queue_for_type）。
    /// 去重：order_id 已有 pending/running/retrying 任务则跳过（对齐 submit_job）。
    /// website_id==4 的 _trigger_full_scan 在 Python 侧本就无定义（运行时 NameError 也不会触发——
    /// 该调用前 enqueue 主流程不依赖其结果），Rust 侧跳过。
    pub fn submit_paid_order_job_sync(&self, order: &Value) -> Result<bool> {
        let order_id = order["order_id"].as_str().unwrap_or("").to_string();
        if order_id.is_empty() {
            return Ok(false);
        }
        let status = order["status"].as_str().unwrap_or("");
        if status != "paid" {
            return Ok(false);
        }
        let task_type_raw = order["task_type"].as_str().unwrap_or("full");
        // 对齐 normalize_task_type：白名单外回退 full
        let task_type = match task_type_raw {
            "video" | "exam" | "full" | "chaoxing_points" => task_type_raw,
            _ => "full",
        };
        let table = if task_type == "chaoxing_points" {
            "queue_jobs_chaoxing"
        } else {
            "queue_jobs_school"
        };
        let username = order["username"].as_str().unwrap_or("").to_string();
        let password = order["password"].as_str().unwrap_or("").to_string();
        let website_id = order["website_id"].as_i64().unwrap_or(1);
        let course_ids = serde_json::to_string(order.get("course_ids").unwrap_or(&json!([])))
            .unwrap_or_else(|_| "[]".into());

        let pool = self.clone_pool();
        let mut conn = pool.get().context("获取连接失败")?;
        let tx = conn.transaction()?;
        // 对齐 submit_job：order_id 已有活跃任务 → 跳过
        let existing: Option<String> = tx
            .query_row(
                &format!(
                    "SELECT job_id FROM {table}
                     WHERE order_id=?1 AND status IN ('pending','running','retrying')
                     ORDER BY created_at DESC LIMIT 1"
                ),
                params![order_id],
                |r| r.get(0),
            )
            .ok();
        if existing.is_some() {
            tx.rollback()?;
            return Ok(false);
        }
        // 对齐 submit_job：同 username+website_id+job_type 活跃任务 → 跳过。
        // job_type 必须参与去重：刷课免费之后，「先领免费刷课、之后再买答题」是
        // 主流程，若只按账号判重，付款后的答题单会被静默丢弃（订单永远停在已付款、
        // 无报错、不重试）。带上 job_type 后同账号的「刷课」与「考试」可并行。
        let dup: Option<String> = tx
            .query_row(
                &format!(
                    "SELECT job_id FROM {table}
                     WHERE username=?1 AND website_id=?2 AND job_type=?3
                       AND status IN ('pending','running','retrying') LIMIT 1"
                ),
                params![username, website_id, task_type],
                |r| r.get(0),
            )
            .ok();
        if dup.is_some() {
            tx.rollback()?;
            return Ok(false);
        }
        let job_id = format!("JOB-{}", uuid_hex_upper(10));
        // 刷课档位随订单带入队列任务（老订单该列为空 → 均衡）
        let speed_mode =
            crate::speed::SpeedMode::parse(order["speed_mode"].as_str().unwrap_or("")).as_str();
        // 通道与池内优先级由订单的免费来源派生（判定表唯一，见 queue::lane_and_priority）
        let paid_processed = order["paid_processed"].as_str().unwrap_or("");
        let (lane, priority) = crate::queue::lane_and_priority(paid_processed);
        tx.execute(
            &format!(
                "INSERT INTO {table}
                 (job_id, username, password, website_id, job_type, course_ids, status,
                  priority, lane, progress, total_steps, completed_steps, current_step_name,
                  error_message, retry_count, max_retries, task_id, order_id, result_data,
                  verified, created_at, started_at, finished_at, deleted_at, speed_mode)
                 VALUES (?1,?2,?3,?4,?5,?6,'pending',?7,?8,0,0,0,'','',0,3,NULL,?9,'{{}}',0,?10,NULL,NULL,NULL,?11)"
            ),
            params![job_id, username, password, website_id, task_type, course_ids,
                    priority, lane.as_str(), order_id,
                    crate::queue::now_str(), speed_mode],
        )?;
        tx.commit()?;
        tracing::info!(
            job_id,
            order_id,
            task_type,
            table,
            lane = lane.as_str(),
            priority,
            "支付订单入队"
        );
        Ok(true)
    }
}

/// 大写 hex 随机串（对齐 uuid.uuid4().hex[:n].upper()）
pub fn uuid_hex_upper(n: usize) -> String {
    use rand::RngExt;
    let mut rng = rand::rng();
    let bytes: Vec<u8> = (0..(n + 1) / 2).map(|_| rng.random::<u8>()).collect();
    bytes.iter().map(|b| format!("{b:02X}")).collect::<String>()[..n].to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 回归：ORDER_COLS 必须带 vid。
    /// 漏选不会报错，但会让「付款成功 → 有效邀请」的归因永远取到空串、
    /// 静默失效（邀请进度永远不涨）。用断言钉住这一列。
    #[test]
    fn test_order_json_carries_vid_and_speed_mode() {
        let dir =
            std::env::temp_dir().join(format!("rust_worker_ypay_db_test_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("order_vid.db");
        let _ = std::fs::remove_file(&path);
        let db = Db::open(path.to_str().unwrap()).unwrap();
        {
            let conn = db.clone_pool().get().unwrap();
            conn.execute(
                "INSERT INTO orders (order_id, username, password, website_id, task_type,
                     course_ids, video_count, exam_count, price, status, paid, created_at,
                     updated_at, speed_mode, vid)
                 VALUES ('ORD-T1','u','p',1,'video','[]',1,0,3.0,'paid',1,
                     '2026-01-01 00:00:00','2026-01-01 00:00:00','turbo','VID-TEST')",
                [],
            )
            .unwrap();
        }
        let order = db.get_order_sync("ORD-T1").expect("订单应能读出");
        assert_eq!(order["vid"], "VID-TEST");
        assert_eq!(order["speed_mode"], "turbo");
        let _ = std::fs::remove_file(&path);
    }

    /// 回归：去重必须带上 job_type。
    ///
    /// "刷课免费、考试付费"之后，「先领免费刷课、之后再买答题」是主流程。
    /// 若去重只看 username+website_id，付款后的答题单会被静默丢弃
    /// （返回 Ok(false)，订单永远停在已付款、无报错、不重试）。
    #[test]
    fn test_dedup_allows_video_and_exam_same_account() {
        let dir = std::env::temp_dir().join(format!(
            "rust_worker_ypay_dedup_test_{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("dedup.db");
        let _ = std::fs::remove_file(&path);
        let db = Db::open(path.to_str().unwrap()).unwrap();

        let order = |oid: &str, task_type: &str, paid_processed: &str| {
            json!({
                "order_id": oid, "status": "paid", "task_type": task_type,
                "username": "SAMEUSER", "password": "p", "website_id": 1,
                "course_ids": [], "speed_mode": "gentle",
                "paid_processed": paid_processed,
            })
        };

        // 同一账号先有一条免费刷课任务在跑
        assert!(db
            .submit_paid_order_job_sync(&order("ORD-V1", "video", "free:video"))
            .unwrap());
        // 再买答题：必须入队成功（这正是旧逻辑会静默吞掉的那一单）
        assert!(db
            .submit_paid_order_job_sync(&order("ORD-E1", "exam", "paid"))
            .unwrap());

        let conn = db.clone_pool().get().unwrap();
        let rows: Vec<(String, String, i64)> = {
            let mut stmt = conn
                .prepare(
                    "SELECT job_type, lane, priority FROM queue_jobs_school
                     WHERE order_id IN ('ORD-V1','ORD-E1') ORDER BY job_type",
                )
                .unwrap();
            stmt.query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)))
                .unwrap()
                .collect::<std::result::Result<Vec<_>, _>>()
                .unwrap()
        };
        assert_eq!(rows.len(), 2, "答题单被去重逻辑吞掉了");
        // exam → 付费池；video 免费单 → 免费池（普通档 priority 2）
        assert_eq!(rows[0], ("exam".to_string(), "paid".to_string(), 0));
        assert_eq!(rows[1], ("video".to_string(), "free".to_string(), 2));

        // 同类型重复入队仍应被拦住（去重本身没有失效）
        assert!(!db
            .submit_paid_order_job_sync(&order("ORD-E2", "exam", "paid"))
            .unwrap());
        drop(conn);
        let _ = std::fs::remove_file(&path);
    }
}

//! 写路径：批量下单（Rust 版）— 对齐 api/routers/orders.py + order_service + pricing_service
//!
//! 价格引擎与 Python 逐行对齐：打包分档 + 进度折扣 + 最低价 + 后端价校正。
//! 双跑对照验收：同一请求发 Python/Rust，total_price 与订单字段必须一致。

use anyhow::Result;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::db::Db;

/// 订单ID生成（对齐 api.utils.gen_id("ORD")）
fn gen_order_id() -> String {
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos() as u64;
    format!("ORD-{:08X}", nanos & 0xffff_ffff)
}

/// 游客查单凭证（对齐 make_view_token：sha256(order_id:secret)[:24]）
pub(crate) fn view_token(order_id: &str) -> String {
    // 与管理员 JWT 共用同一密钥源（auth::secret）。此前这里用 unwrap_or_default()，
    // 密钥缺失时 secret 会是空串，与 auth 的兜底值不一致 —— 那样 view_token 变成
    // 可离线枚举的 sha256(order_id + ":")，能读/取消任意订单。
    // 注意：派生串必须保持与历史完全一致，否则已发出的游客查单链接全部失效。
    let secret = String::from_utf8_lossy(&crate::auth::secret()).into_owned();
    let digest = Sha256::digest(format!("{order_id}:{secret}").as_bytes());
    let hex: String = digest.iter().map(|b| format!("{b:02x}")).collect();
    hex[..24].to_string()
}

/// 定价配置（system_config，对齐 pricing_service.get_pricing_config 默认值）
pub async fn pricing_config(db: &Db) -> Result<Value> {
    let pool = db.clone_pool();
    tokio::task::spawn_blocking(move || -> Result<Value> {
        let conn = pool.get()?;
        let defaults = [
            ("price_small", 3.0), ("price_medium", 5.0), ("price_large", 6.0),
            ("discount_25", 0.7), ("discount_50", 0.5), ("discount_75", 0.3),
            ("price_minimum", 2.0), ("price_exam_only", 5.0), ("price_homework_only", 3.0),
            ("price_chaoxing", 8.0),
        ];
        let mut cfg = serde_json::Map::new();
        for (key, default) in defaults {
            let v: Option<String> = conn.query_row(
                "SELECT config_value FROM system_config WHERE config_key=?1",
                rusqlite::params![key], |r| r.get(0)).ok().flatten();
            cfg.insert(key.to_string(), json!(v.and_then(|s| s.parse::<f64>().ok()).unwrap_or(default)));
        }
        Ok(Value::Object(cfg))
    })
    .await?
}

/// 打包价（对齐 pricing_service.calculate_package_price）
fn calculate_package_price(cfg: &Value, video_total: i64, video_completed: i64) -> f64 {
    if video_total <= 0 {
        return 0.0;
    }
    let base = if video_total <= 30 {
        cfg["price_small"].as_f64().unwrap_or(3.0)
    } else if video_total <= 80 {
        cfg["price_medium"].as_f64().unwrap_or(5.0)
    } else {
        cfg["price_large"].as_f64().unwrap_or(6.0)
    };
    let progress = video_completed as f64 / video_total as f64 * 100.0;
    let coeff = if progress <= 25.0 {
        1.0
    } else if progress <= 50.0 {
        cfg["discount_25"].as_f64().unwrap_or(0.7)
    } else if progress <= 75.0 {
        cfg["discount_50"].as_f64().unwrap_or(0.5)
    } else {
        cfg["discount_75"].as_f64().unwrap_or(0.3)
    };
    (base * coeff).round_to_2().max(cfg["price_minimum"].as_f64().unwrap_or(2.0))
}

trait Round2 {
    fn round_to_2(self) -> f64;
}
impl Round2 for f64 {
    fn round_to_2(self) -> f64 {
        (self * 100.0).round() / 100.0
    }
}

/// 单门课定价 + 档位标签（对齐 order_service 的 course 条目输出）
/// 返回 (course_id, type, price, label)，供 /api/pricing/calculate 逐课回显
pub fn price_course_entry(cd: &Value, cfg: &Value) -> Value {
    let course_id = cd["course_id"].as_str().unwrap_or("").to_string();
    let video_total = cd["video_total"].as_i64().unwrap_or(0);
    let video_completed = cd["video_completed"].as_i64().unwrap_or(0);
    let exam_total = cd["exam_total"].as_i64().unwrap_or(0);
    let exam_done = cd["exam_done"].as_i64().unwrap_or(0);
    let homework_total = cd["homework_total"].as_i64().unwrap_or(0);
    let homework_done = cd["homework_done"].as_i64().unwrap_or(0);

    let video_all_done = video_total > 0 && video_completed >= video_total;
    let has_exam = exam_total > 0 && exam_done < exam_total;
    let has_homework = homework_total > 0 && homework_done < homework_total;
    // 视频尚未刷完 → 走打包价；否则按剩余项定价
    let use_package = video_total > 0 && !video_all_done;

    let (kind, label) = if use_package {
        let base = if video_total <= 30 { "小档" } else if video_total <= 80 { "中档" } else { "大档" };
        ("package", format!("视频打包·{base}"))
    } else {
        match (has_exam, has_homework) {
            (true, true) => ("exam_homework", "考试+作业".to_string()),
            (true, false) => ("exam", "仅考试".to_string()),
            (false, true) => ("homework", "仅作业".to_string()),
            (false, false) => ("done", "已完成".to_string()),
        }
    };
    let price = price_single_course(cd, cfg);
    json!({"course_id": course_id, "type": kind, "price": price, "label": label})
}

/// 批量定价（/api/pricing/calculate）→ (逐课条目, 总价)
pub fn price_courses(cfg: &Value, courses: &[Value]) -> (Vec<Value>, f64) {
    let entries: Vec<Value> = courses.iter().map(|c| price_course_entry(c, cfg)).collect();
    let total = entries.iter().map(|e| e["price"].as_f64().unwrap_or(0.0)).sum::<f64>().round_to_2();
    (entries, total)
}

/// 单门课定价（对齐 order_service._price_single_course）
fn price_single_course(cd: &Value, cfg: &Value) -> f64 {
    let video_total = cd["video_total"].as_i64().unwrap_or(0);
    let video_completed = cd["video_completed"].as_i64().unwrap_or(0);
    let exam_total = cd["exam_total"].as_i64().unwrap_or(0);
    let exam_done = cd["exam_done"].as_i64().unwrap_or(0);
    let homework_total = cd["homework_total"].as_i64().unwrap_or(0);
    let homework_done = cd["homework_done"].as_i64().unwrap_or(0);

    let has_video = video_total > 0;
    let video_all_done = has_video && video_completed >= video_total;
    let has_exam = exam_total > 0 && exam_done < exam_total;
    let has_homework = homework_total > 0 && homework_done < homework_total;
    let price_exam = cfg["price_exam_only"].as_f64().unwrap_or(5.0);
    let price_homework = cfg["price_homework_only"].as_f64().unwrap_or(3.0);

    if video_all_done {
        if has_exam && !has_homework {
            return price_exam;
        }
        if has_homework && !has_exam {
            return price_homework;
        }
        if has_exam && has_homework {
            return price_exam.max(price_homework);
        }
        return calculate_package_price(cfg, video_total, video_completed);
    }
    if has_video {
        return calculate_package_price(cfg, video_total, video_completed);
    }
    if has_exam && !has_homework {
        return price_exam;
    }
    if has_homework && !has_exam {
        return price_homework;
    }
    if has_exam && has_homework {
        return price_exam.max(price_homework);
    }
    0.0
}

/// 后端总价（对齐 order_service.compute_batch_price）
pub async fn compute_batch_price(db: &Db, orders: &[Value]) -> Result<f64> {
    let cfg = pricing_config(db).await?;
    Ok(compute_item_prices(&cfg, orders).iter().sum::<f64>().round_to_2())
}

/// 逐单后端价（唯一真相源）。有明细按课程计价，否则按打包/学习通口径。
///
/// 抽成函数是为了让下单路径能**逐单覆盖**客户端传来的价格：
/// 客户端只要把所有 price 传 0，旧逻辑里 "front_total=0 时不重算" 的分支就会让
/// 0 元订单落库（支付金额取自库里的价格）—— 等于白嫖。现在一律以后端算出的价为准。
fn compute_item_prices(cfg: &Value, orders: &[Value]) -> Vec<f64> {
    orders.iter().map(|item| {
        let website_id = item["website_id"].as_i64().unwrap_or(1);
        let video_count = item["video_count"].as_i64().unwrap_or(0);
        let details = item["course_details"].as_array().cloned().unwrap_or_default();
        if website_id == 4 {
            cfg["price_chaoxing"].as_f64().unwrap_or(8.0)
        } else if !details.is_empty() {
            details.iter().map(|cd| price_single_course(cd, cfg)).sum::<f64>().round_to_2()
        } else {
            calculate_package_price(cfg, video_count, 0)
        }
    }).collect()
}

/// 创建订单（对齐 db.create_order）
async fn create_order(db: &Db, username: &str, password: &str, item: &Value,
                      user_id: &str) -> Result<Value> {
    let order_id = gen_order_id();
    let now = crate::queue::now_str();
    let pool = db.clone_pool();
    let order_id2 = order_id.clone();
    let username = username.to_string();
    let password = password.to_string();
    let website_id = item["website_id"].as_i64().unwrap_or(1);
    let task_type = item["task_type"].as_str().unwrap_or("video").to_string();
    let course_ids = serde_json::to_string(item["course_ids"].as_array().unwrap_or(&vec![]))?;
    let video_count = item["video_count"].as_i64().unwrap_or(0);
    let exam_count = item["exam_count"].as_i64().unwrap_or(0);
    let price = item["price"].as_f64().unwrap_or(0.0);
    // 刷课节奏档位：未知/缺省一律落「均衡」，保证老前端与历史数据行为不变
    let speed_mode = crate::speed::SpeedMode::parse(
        item["speed_mode"].as_str().unwrap_or("")).as_str().to_string();
    let user_id = user_id.to_string();

    // 响应用的副本（闭包 move 后仍可用）
    let r_username = username.clone();
    let r_task_type = task_type.clone();
    let r_now = now.clone();
    let r_speed_mode = speed_mode.clone();

    tokio::task::spawn_blocking(move || -> Result<()> {
        let conn = pool.get()?;
        // 密码不落 orders 明文列，统一进加密凭据表（crypto::store）
        conn.execute(
            "INSERT INTO orders (order_id, out_trade_no, ezfpy_trade_no, payment_channel,
                                 paid_processed, user_id, customer_name, customer_contact,
                                 username, password, website_id, task_type, course_ids,
                                 video_count, exam_count, price, notes, status, paid,
                                 admin_note, created_at, updated_at, speed_mode)
             VALUES (?1,'','','','unprocessed',?2,'','',?3,'',?4,?5,?6,?7,?8,?9,'',
                     'pending',0,'',?10,?10,?11)",
            rusqlite::params![
                order_id2, user_id, username, website_id, task_type,
                course_ids, video_count, exam_count, price, now, speed_mode,
            ],
        )?;
        crate::crypto::store(&conn, &order_id2, &username, &password)?;
        Ok(())
    })
    .await??;
    Ok(json!({
        "order_id": order_id,
        "username": r_username,
        "website_id": website_id,
        "task_type": r_task_type,
        "course_ids": item["course_ids"],
        "video_count": video_count,
        "exam_count": exam_count,
        "price": price,
        "speed_mode": r_speed_mode,
        "status": "pending",
        "paid": 0,
        "created_at": r_now,
    }))
}

/// 批量下单（对齐 create_batch_orders 主流程）
///
/// `vid` / `benefit`：营销推广的免费待遇。命中时所有订单 0 元、标记为已支付并
/// **直接进队列**（免费用户不该走支付流程，也不该等对账），同时把邀请关系标记为
/// 已转化、消耗一次卡额度。
pub async fn create_batch_orders(db: &Db, body: &Value, vid: &str,
                                 benefit: crate::promo::Benefit) -> Result<Value> {
    let username = body["username"].as_str().unwrap_or("").to_string();
    let password = body["password"].as_str().unwrap_or("").to_string();
    let mut orders: Vec<Value> = body["orders"].as_array().cloned().unwrap_or_default();

    // 价格唯一真相源是后端：逐单用后端算出的价覆盖客户端传值。
    // 旧实现只在"客户端总价与后端不一致且客户端总价>0"时才重算，
    // 于是把 price 全传 0 就能让 0 元订单落库（支付金额读库里的价格）→ 白嫖。
    let cfg = pricing_config(db).await?;
    let item_prices = compute_item_prices(&cfg, &orders);
    let total_price = item_prices.iter().sum::<f64>().round_to_2();
    for (item, price) in orders.iter_mut().zip(item_prices.iter()) {
        item["price"] = json!(price);
    }

    let mut created = Vec::new();
    for item in &orders {
        let course_ids = item["course_ids"].as_array().cloned().unwrap_or_default();
        if course_ids.is_empty() && item["video_count"].as_i64().unwrap_or(0) == 0 {
            continue;
        }
        // 免费订单（全局免费 / 刷课卡）：价格清零，并且**强制**保守档。
        // 这是商业规则而不是默认值：不付费只能用串行档，适中/暴力是付费权益。
        // 必须在服务端强制——只靠前端置灰的话，直接调接口传 turbo 就白嫖了加速。
        let mut item = item.clone();
        if benefit.is_free() {
            item["speed_mode"] = json!(crate::speed::SpeedMode::Gentle.as_str());
            item["price"] = json!(0.0);
        }
        let order = create_order(db, &username, &password, &item, "").await?;
        let mut masked = order.clone();
        masked["password"] = json!("***");
        masked["view_token"] = json!(view_token(order["order_id"].as_str().unwrap_or("")));
        masked["free"] = json!(benefit.is_free());
        created.push(masked);
    }

    // 免费单：标记已支付 + 直接入队（复用支付成功那条唯一入队通道）
    if benefit.is_free() {
        for order in &created {
            let oid = order["order_id"].as_str().unwrap_or("").to_string();
            if oid.is_empty() {
                continue;
            }
            let oid2 = oid.clone();
            let reason = benefit.reason.clone();
            let pool = db.clone_pool();
            let _ = tokio::task::spawn_blocking(move || -> Result<()> {
                let conn = pool.get()?;
                let now = crate::queue::now_str();
                // paid_processed 的 'free' 是免费单的标记；payment_channel 便于后台统计
                conn.execute(
                    "UPDATE orders SET status='paid', paid=1, payment_channel='free',
                            payment_time=?1, paid_processed=?2, updated_at=?1
                     WHERE order_id=?3",
                    rusqlite::params![now, format!("free:{reason}"), oid2],
                )?;
                Ok(())
            })
            .await;
            crate::pay_routes::enqueue_paid_order(db, &oid).await;
        }
        // 一卡按张数计额度：一次提交建了 N 单就扣 N 次，
        // 否则把多门课塞进一批就能用 1 次额度刷 N 单
        crate::promo::consume_card(db, &benefit.card_id, created.len() as i64).await;
        tracing::info!(orders = created.len(), reason = %benefit.reason, "免费订单已创建并直接入队");
    }
    // 付费订单：把访客身份写进订单，供"付款成功 → 邀请转化"归因
    // （有效邀请只认已收款订单，免费单不算，避免注册小号白刷卡）
    if !benefit.is_free() && !vid.is_empty() {
        for order in &created {
            let oid = order["order_id"].as_str().unwrap_or("").to_string();
            if oid.is_empty() {
                continue;
            }
            let pool = db.clone_pool();
            let vid2 = vid.to_string();
            let _ = tokio::task::spawn_blocking(move || -> Result<()> {
                let conn = pool.get()?;
                conn.execute("UPDATE orders SET vid=?1 WHERE order_id=?2",
                             rusqlite::params![vid2, oid])?;
                Ok(())
            })
            .await;
        }
    }

    Ok(json!({
        "success": true,
        "message": format!("成功创建 {} 个订单", created.len()),
        "data": {
            "orders": created,
            "total_price": if benefit.is_free() { 0.0 } else { total_price },
            "paid": benefit.is_free(),
            "free": benefit.is_free(),
            "free_reason": benefit.reason,
        },
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_cfg() -> Value {
        json!({"price_small": 3.0, "price_medium": 5.0, "price_large": 6.0,
               "discount_25": 0.7, "discount_50": 0.5, "discount_75": 0.3,
               "price_minimum": 2.0, "price_exam_only": 5.0, "price_homework_only": 3.0,
               "price_chaoxing": 8.0})
    }

    #[test]
    fn test_package_pricing() {
        let cfg = test_cfg();
        assert_eq!(calculate_package_price(&cfg, 20, 0), 3.0);      // 小档全价
        assert_eq!(calculate_package_price(&cfg, 50, 0), 5.0);      // 中档
        assert_eq!(calculate_package_price(&cfg, 100, 0), 6.0);     // 大档
        assert_eq!(calculate_package_price(&cfg, 20, 6), 2.1);      // 30%进度 ×0.7
        assert_eq!(calculate_package_price(&cfg, 20, 12), 2.0);     // 60%×0.5=1.5→最低2.0
        assert_eq!(calculate_package_price(&cfg, 20, 20), 2.0);     // 100%×0.3=0.9→最低2.0
        assert_eq!(calculate_package_price(&cfg, 0, 0), 0.0);
    }

    #[test]
    fn test_view_token() {
        std::env::set_var("JWT_SECRET_KEY", "secret");
        let t = view_token("ORD-TEST");
        assert_eq!(t.len(), 24);
        assert_eq!(t, view_token("ORD-TEST"));
    }
}

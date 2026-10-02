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
pub(crate) fn gen_order_id() -> String {
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



/// 单门课定价。
///
/// 商业规则：**刷视频免费，答题/考试收费**。所以这里只看"还剩多少要付费的活"：
/// 视频进度不再参与计价，一门课只要还有未完成的考试/作业就要付费，两样都没有
/// 就是 0 元（走免费通道，下单即开跑、不进支付流程）。
fn price_single_course(cd: &Value, cfg: &Value) -> f64 {
    let exam_total = cd["exam_total"].as_i64().unwrap_or(0);
    let exam_done = cd["exam_done"].as_i64().unwrap_or(0);
    let homework_total = cd["homework_total"].as_i64().unwrap_or(0);
    let homework_done = cd["homework_done"].as_i64().unwrap_or(0);

    let has_exam = exam_total > 0 && exam_done < exam_total;
    let has_homework = homework_total > 0 && homework_done < homework_total;
    let price_exam = cfg["price_exam_only"].as_f64().unwrap_or(5.0);
    let price_homework = cfg["price_homework_only"].as_f64().unwrap_or(3.0);

    if has_exam && !has_homework {
        return price_exam;
    }
    if has_homework && !has_exam {
        return price_homework;
    }
    if has_exam && has_homework {
        return price_exam.max(price_homework);
    }
    // 只剩视频（或什么都已完成）→ 免费
    0.0
}

/// 逐单后端价（唯一真相源）。
///
/// 事实来源是**服务端扫描快照**（见 [`crate::scan_snapshot`]），而不是客户端回传的
/// `course_details`：定价要知道"这门课还剩几场考试"，此前这个事实由客户端提供 ——
/// 伪造 `exam_total: 0` 就能把付费考试算成 0 元，白做整批考试。现在客户端只能
/// "选择课程"（course_ids），事实一律回查快照；查不到就拒绝整批，宁可让用户
/// 重新扫描一次，也不接受一份无法核实的价格。
///
/// 逐单覆盖客户端传来的 price：客户端把 price 全传 0 也不会让 0 元订单落库。
pub fn compute_item_prices(cfg: &Value, orders: &[Value], username: &str) -> Result<Vec<f64>> {
    let mut prices = Vec::with_capacity(orders.len());
    for item in orders {
        let website_id = item["website_id"].as_i64().unwrap_or(1);
        let price = if website_id == 4 {
            // 学习通一口价（与前端展示一致，不按课程明细计价）
            cfg["price_chaoxing"].as_f64().unwrap_or(8.0)
        } else {
            let course_ids: Vec<String> = item["course_ids"].as_array()
                .map(|a| a.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
                .unwrap_or_default();
            if course_ids.is_empty() {
                // 没选具体课程：只可能是"纯视频"诉求（视频对所有人免费）。
                // 考试必须有明确课程才能执行，调用方会把这类单的任务类型收敛为
                // video，因此这里一律 0 元，不存在"少传课程 = 少付考试费"的空间。
                0.0
            } else {
                match crate::scan_snapshot::resolve(username, website_id, &course_ids) {
                    Ok(facts) => facts.iter()
                        .map(|cd| price_single_course(cd, cfg))
                        .sum::<f64>().round_to_2(),
                    Err(_) => {
                        // 没有可用快照（没扫过 / 扫描失败 / 进程刚重启）：既不信任
                        // 客户端明细（那是白嫖通道），也不拒单（会误伤正常用户）。
                        // 按选中课程数保守计考试费 —— 与"宁可多收，也不让少传明细
                        // 变成少付钱的后门"的既有原则一致。正常流程总是先扫描，
                        // 命中快照时按真实数据精确计价。
                        (cfg["price_exam_only"].as_f64().unwrap_or(5.0)
                            * course_ids.len() as f64).round_to_2()
                    }
                }
            }
        };
        prices.push(price);
    }
    Ok(prices)
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
        // 用户规则（2026-09-30）：密码只存明文，直接落 orders.password
        conn.execute(
            "INSERT INTO orders (order_id, out_trade_no, ezfpy_trade_no, payment_channel,
                                 paid_processed, user_id, customer_name, customer_contact,
                                 username, password, website_id, task_type, course_ids,
                                 video_count, exam_count, price, notes, status, paid,
                                 admin_note, created_at, updated_at, speed_mode)
             VALUES (?1,'','','','unprocessed',?2,'','',?3,?12,?4,?5,?6,?7,?8,?9,'',
                     'pending',0,'',?10,?10,?11)",
            rusqlite::params![
                order_id2, user_id, username, website_id, task_type,
                course_ids, video_count, exam_count, price, now, speed_mode, password,
            ],
        )?;
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

/// 批量下单。
///
/// 商业规则：**刷视频免费、答题/考试收费**。因此不再"整批免费或整批付费"，
/// 而是**逐单分流**：后端算出的价是 0 的（只剩视频）直接标记已支付并入队，
/// 立刻开跑、不进支付流程；价 > 0 的（含未完成的考试/作业）留给支付。
///
/// `vid` / `benefit`：营销推广待遇。命中刷课卡时考试费清零（该单也变 0 元），
/// 并在入队时拿到更高的排队档位（见 `queue::lane_and_priority`）。
pub async fn create_batch_orders(db: &Db, body: &Value, vid: &str,
                                 benefit: crate::promo::Benefit) -> Result<Value> {
    let username = body["username"].as_str().unwrap_or("").to_string();
    let password = body["password"].as_str().unwrap_or("").to_string();
    let mut orders: Vec<Value> = body["orders"].as_array().cloned().unwrap_or_default();

    // 价格唯一真相源是后端：逐单用后端算出的价覆盖客户端传值，且定价事实来自
    // 服务端扫描快照（见 compute_item_prices）。快照缺失/过期会直接拒绝整批。
    let cfg = pricing_config(db).await?;
    let item_prices = compute_item_prices(&cfg, &orders, &username)?;
    for (item, price) in orders.iter_mut().zip(item_prices.iter()) {
        item["price"] = json!(price);
    }

    // 持卡：考试费清零，整单变 0 元走免费通道（卡的权益是"免考试费 + 优先排队"）
    let card_free = benefit.is_free();

    let mut created = Vec::new();
    let mut free_ids: Vec<String> = Vec::new();
    let mut payable_ids: Vec<String> = Vec::new();
    let mut payable_total = 0.0f64;
    // 卡的额度只被"卡真正免掉的钱"消耗：纯视频单本来就免费，不该扣卡额度
    let mut card_charged = 0i64;

    for item in &orders {
        let course_ids = item["course_ids"].as_array().cloned().unwrap_or_default();
        if course_ids.is_empty() && item["video_count"].as_i64().unwrap_or(0) == 0 {
            continue;
        }
        let mut item = item.clone();
        // 'pass' 是学期卡虚拟商品的保留类型，只能由 /api/promo/pass/create 建单。
        // 普通下单接口被传这个值就直接降级成视频单，否则能白嫖一张学期卡。
        if item["task_type"].as_str() == Some(crate::promo::KIND_PASS) {
            item["task_type"] = json!("video");
        }
        let original_price = item["price"].as_f64().unwrap_or(0.0);
        if card_free {
            // 持卡：考试费清零，该单变 0 元
            item["price"] = json!(0.0);
            if original_price > 0.0 {
                card_charged += 1;
            }
        }
        // 免费单一律只能用保守档：适中/暴力是付费权益。必须在服务端强制——
        // 只靠前端置灰的话，直接调接口传 turbo 就白嫖了加速。
        // 注意判据是"这一单要不要付钱"，而不是"有没有卡"：刷视频对所有人免费，
        // 所以没有卡的普通用户下的纯视频单同样是免费单，同样只能串行。
        let is_free_item = item["price"].as_f64().unwrap_or(0.0) <= 0.0;
        if is_free_item {
            // 学期卡把暴力档当权益卖出去（benefit.turbo）；其余免费单（纯视频、
            // 全局免费活动、刷课卡）一律锁保守档 —— 加速只能花钱买。
            if !benefit.turbo {
                item["speed_mode"] = json!(crate::speed::SpeedMode::Gentle.as_str());
            }
            // 免费单不得执行考试/作业：只有"持卡/全局免费"覆盖考试费，"视频免费"
            // 不覆盖。算价已经改用服务端快照（伪造不了），这里再兜一道 ——
            // 即使未来算价再出漏洞，免费单也只会刷视频，不会把付费考试白做掉。
            let task_type = item["task_type"].as_str().unwrap_or("").to_string();
            if !card_free && (task_type == "exam" || task_type == "full") {
                item["task_type"] = json!("video");
            }
        }
        let order = create_order(db, &username, &password, &item, "").await?;
        let oid = order["order_id"].as_str().unwrap_or("").to_string();
        let mut masked = order.clone();
        masked["password"] = json!("***");
        masked["view_token"] = json!(view_token(&oid));
        masked["free"] = json!(is_free_item);
        created.push(masked);

        if is_free_item {
            // 免费来源照抄 benefit.reason（global / card），只有"纯视频免费"才是 video。
            // 千万不要在这里把来源归并成 card：`lane_and_priority` 按 free:card 给插队档，
            // 归并会让全局免费活动的单白拿持卡优先权，后台统计也会误判。
            let reason = if card_free { benefit.reason.clone() } else { "video".to_string() };
            let oid2 = oid.clone();
            let pool = db.clone_pool();
            let _ = tokio::task::spawn_blocking(move || -> Result<()> {
                let conn = pool.get()?;
                let now = crate::queue::now_str();
                // paid_processed 的 'free:*' 前缀是免费单标记，也是队列通道的判定依据
                // （见 queue::lane_and_priority）；payment_channel 便于后台统计
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
            free_ids.push(oid);
        } else {
            payable_total += item["price"].as_f64().unwrap_or(0.0);
            payable_ids.push(oid.clone());
            // 付费单才写访客身份：有效邀请只认已收款订单，免费单带 vid 会刷出假邀请
            if !vid.is_empty() {
                let oid2 = oid.clone();
                let vid2 = vid.to_string();
                let pool = db.clone_pool();
                let _ = tokio::task::spawn_blocking(move || -> Result<()> {
                    let conn = pool.get()?;
                    conn.execute("UPDATE orders SET vid=?1 WHERE order_id=?2",
                                 rusqlite::params![vid2, oid2])?;
                    Ok(())
                })
                .await;
            }
        }
    }

    // 额度按"卡真正免掉的单数"计：纯视频单本来就免费，不该消耗卡的免考试费额度；
    // 全局免费（reason=global）没有卡号，consume_card 会自行跳过。
    if card_free {
        if card_charged > 0 {
            crate::promo::consume_card(db, &benefit.card_id, card_charged).await;
        }
        tracing::info!(orders = created.len(), charged = card_charged, reason = %benefit.reason,
                       "持卡订单已创建并直接入队");
    }
    if !free_ids.is_empty() {
        tracing::info!(free = free_ids.len(), payable = payable_ids.len(),
                       "订单已分流：免费单直接入队，付费单待支付");
    }

    Ok(json!({
        "success": true,
        "message": format!("成功创建 {} 个订单", created.len()),
        "data": {
            "orders": created,
            // 已直接开跑的免费单 / 还需支付才能跑的付费单
            "free_order_ids": free_ids,
            "payable_order_ids": payable_ids,
            "total_price": payable_total.round_to_2(),
            // 是否全部免单（全部走免费通道、无需支付）
            "paid": payable_ids.is_empty(),
            "free": free_ids.len() == created.len() && !created.is_empty(),
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

    /// 核心商业规则：**刷视频不计费，只有未完成的考试/作业才收费**。
    /// 这条规则决定了一单要不要走支付流程，价错一块钱就是白嫖或多收。
    #[test]
    fn test_video_is_free_exam_is_paid() {
        let cfg = test_cfg();

        // 只剩视频（含"视频没刷完"与"视频已刷完"两种）→ 一律 0 元
        assert_eq!(price_single_course(
            &json!({"video_total": 100, "video_completed": 0,
                    "exam_total": 0, "exam_done": 0,
                    "homework_total": 0, "homework_done": 0}), &cfg), 0.0);
        assert_eq!(price_single_course(
            &json!({"video_total": 100, "video_completed": 100,
                    "exam_total": 0, "exam_done": 0,
                    "homework_total": 0, "homework_done": 0}), &cfg), 0.0);
        // 视频没刷完 + 有考试未完成 → 只收考试费（视频那部分免费）
        assert_eq!(price_single_course(
            &json!({"video_total": 100, "video_completed": 0,
                    "exam_total": 2, "exam_done": 0,
                    "homework_total": 0, "homework_done": 0}), &cfg), 5.0);
        // 考试已全部完成 → 没有要付费的活了
        assert_eq!(price_single_course(
            &json!({"video_total": 100, "video_completed": 0,
                    "exam_total": 2, "exam_done": 2,
                    "homework_total": 0, "homework_done": 0}), &cfg), 0.0);
        // 只有作业 → 作业价；考试+作业 → 取较高者
        assert_eq!(price_single_course(
            &json!({"video_total": 10, "video_completed": 0,
                    "exam_total": 0, "exam_done": 0,
                    "homework_total": 3, "homework_done": 0}), &cfg), 3.0);
        assert_eq!(price_single_course(
            &json!({"video_total": 10, "video_completed": 0,
                    "exam_total": 1, "exam_done": 0,
                    "homework_total": 3, "homework_done": 0}), &cfg), 5.0);
    }

    /// 纯视频单整单必须判 0 元 —— 前端据此跳开支付流程直接进订单页。
    #[test]
    fn test_video_only_batch_prices_to_zero() {
        let cfg = test_cfg();
        crate::scan_snapshot::save("u_price_video", 1, &[json!({
            "course_id": "c1", "records_loaded": true,
            "video_total": 60, "video_completed": 0, "exam_total": 0, "exam_done": 0,
        })]);
        let orders = vec![json!({
            "website_id": 1, "video_count": 120, "exam_count": 0, "course_ids": ["c1"],
        })];
        assert_eq!(compute_item_prices(&cfg, &orders, "u_price_video").unwrap(), vec![0.0]);
    }

    /// 定价事实只认服务端快照：客户端把 exam_total 传 0 也没用 ——
    /// 快照里这门课有未完成考试，就必须付考试费（0 元白嫖考试通道已封死）。
    #[test]
    fn test_client_cannot_forge_free_exam() {
        let cfg = test_cfg();
        crate::scan_snapshot::save("u_price_forge", 1, &[json!({
            "course_id": "c1", "records_loaded": true,
            "video_total": 10, "video_completed": 10, "exam_total": 2, "exam_done": 0,
        })]);
        let orders = vec![json!({
            "website_id": 1, "video_count": 0, "exam_count": 0, "course_ids": ["c1"],
            // 客户端伪造：声称这门课没有考试
            "course_details": [{"video_total": 10, "video_completed": 10,
                                "exam_total": 0, "exam_done": 0}],
        })];
        assert_eq!(compute_item_prices(&cfg, &orders, "u_price_forge").unwrap(), vec![5.0]);
    }

    /// 没有扫描快照（没扫过、扫描失败或进程刚重启）→ **保守计价**而不是按客户端
    /// 数据算价：2 门课按 2×考试单价收，既不会 0 元白嫖，也不会因拒单误伤用户。
    #[test]
    fn test_pricing_without_snapshot_charges_conservatively() {
        let cfg = test_cfg();
        let orders = vec![json!({
            "website_id": 1, "video_count": 5, "exam_count": 0, "course_ids": ["c1", "c2"],
            // 客户端声称没有考试 —— 没有快照时这份声明一律不采信
            "course_details": [{"exam_total": 0, "exam_done": 0}],
        })];
        assert_eq!(compute_item_prices(&cfg, &orders, "u_price_nobody").unwrap(), vec![10.0]);
    }

    /// 学习通一口价：不依赖课程明细快照
    #[test]
    fn test_chaoxing_flat_price() {
        let cfg = test_cfg();
        let orders = vec![json!({"website_id": 4, "course_ids": ["c9"]})];
        assert_eq!(compute_item_prices(&cfg, &orders, "anyone").unwrap(), vec![8.0]);
    }
}

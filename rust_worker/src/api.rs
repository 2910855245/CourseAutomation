//! HTTP API 路由（纯 Rust 化阶段 3：读路径）
//!
//! 响应格式与 Python 逐字段对齐（对照测试基准见 py_refs.json）。
//! 受保护路由经 auth_middleware 校验 Bearer token。

use axum::extract::{Path, Query, State};
use axum::middleware;
use axum::routing::{get, post};
use axum::{Json, Router};
use serde_json::{json, Map, Value};

use crate::db::Db;
use crate::AppState;

pub fn router(state: AppState) -> Router<AppState> {
    // 受保护读路径（Bearer 鉴权）
    let protected = Router::new()
        .route("/api/orders/", get(orders_list))
        .route("/api/orders/{order_id}", get(order_get))
        .route("/api/admin/dashboard", get(admin_dashboard))
        .route("/api/queue/stats", get(queue_stats))
        .route("/api/pricing", get(pricing))
        .route_layer(middleware::from_fn_with_state(state.clone(), crate::auth::auth_middleware));

    Router::new()
        .route("/api/info", get(api_info))
        .route("/api/system/status", get(system_status))
        .route("/api/jobs/submit", post(submit_job))
        .route("/api/orders/batch", post(batch_orders))
        .route("/api/admin/login", post(crate::auth::admin_login))
        .route("/health", get(health))
        .merge(protected)
}

/// 批量下单（写路径，与 Python 双跑对照验收）
async fn batch_orders(State(state): State<AppState>, Json(body): Json<Value>) -> Json<Value> {
    match crate::order::create_batch_orders(&state.db, &body).await {
        Ok(v) => Json(v),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

async fn api_info() -> Json<Value> {
    Json(json!({"name": "网课代刷平台 API", "version": "7.0.0-rust"}))
}

async fn health(State(state): State<AppState>) -> Json<Value> {
    Json(json!({
        "ok": true,
        "tasks": state.tasks.len(),
        "memory_mb": crate::rss_mb(),
    }))
}

/// 系统状态（对齐 Python /api/system/status 的骨架版本）
async fn system_status(State(state): State<AppState>) -> Json<Value> {
    let orders = match state.db.order_stats().await {
        Ok(v) => v,
        Err(e) => {
            tracing::warn!("order_stats 失败: {e}");
            json!({"total_orders": 0, "total_revenue": 0.0, "by_status": {}})
        }
    };
    Json(json!({
        "queue": {
            "pending": 0, "running": 0, "completed": 0, "failed": 0, "total": 0,
            "active_workers": state.tasks.len(),
        },
        "orders": orders,
    }))
}

/// 提交学校任务到队列（对齐 Python queue.submit_job 核心字段）
async fn submit_job(State(state): State<AppState>, Json(body): Json<Value>) -> Json<Value> {
    match crate::queue::submit_job(&state.db, body).await {
        Ok(v) => Json(v),
        Err(e) => Json(json!({"ok": false, "message": e.to_string()})),
    }
}

// ── 读路径（与 Python 逐字段对齐）──────────────────────────

fn order_row_to_json(r: &rusqlite::Row, course_ids: &str) -> rusqlite::Result<Value> {
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
        "password": "***",
        "website_id": r.get::<_, i64>(10)?,
        "task_type": r.get::<_, Option<String>>(11)?.unwrap_or_default(),
        "course_ids": serde_json::from_str::<Value>(course_ids).unwrap_or(json!([])),
        "video_count": r.get::<_, i64>(13)?,
        "exam_count": r.get::<_, i64>(14)?,
        "price": r.get::<_, f64>(15)?,
        "notes": r.get::<_, Option<String>>(16)?.unwrap_or_default(),
        "status": r.get::<_, Option<String>>(17)?.unwrap_or_default(),
        "paid": r.get::<_, i64>(18)?,
        "task_id": r.get::<_, Option<String>>(19)?,
        "admin_note": r.get::<_, Option<String>>(20)?.unwrap_or_default(),
        "created_at": r.get::<_, Option<String>>(21)?.unwrap_or_default(),
        "updated_at": r.get::<_, Option<String>>(22)?.unwrap_or_default(),
        "accepted_at": r.get::<_, Option<String>>(23)?,
        "started_at": r.get::<_, Option<String>>(24)?,
        "finished_at": r.get::<_, Option<String>>(25)?,
    }))
}


/// 对齐 Python _inject_task_progress：队列任务进度注入（completed→100，默认 0）
fn inject_progress(conn: &rusqlite::Connection, items: &mut Vec<Value>) -> rusqlite::Result<()> {
    for item in items.iter_mut() {
        let order_id = item["order_id"].as_str().unwrap_or("").to_string();
        let progress: f64 = ["queue_jobs_school", "queue_jobs_chaoxing"].iter()
            .find_map(|t| {
                conn.query_row(
                    &format!(
                        "SELECT status, progress FROM {t} WHERE order_id=?1
                         ORDER BY created_at DESC LIMIT 1"
                    ),
                    rusqlite::params![order_id],
                    |r| Ok((r.get::<_, String>(0)?, r.get::<_, f64>(1)?)),
                ).ok()
            })
            .map(|(status, p)| if status == "completed" { 100.0 } else { p })
            .unwrap_or(0.0);
        item["progress"] = json!(progress);
    }
    Ok(())
}


async fn orders_list(
    State(state): State<AppState>,
    Query(params): Query<std::collections::HashMap<String, String>>,
) -> Json<Value> {
    let limit = params.get("limit").and_then(|v| v.parse::<i64>().ok()).unwrap_or(50);
    let status_filter = params.get("status").cloned();
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Value> {
        let conn = db.get()?;
        // 先取总数（与 Python 同口径：状态过滤 + 非删除）
        let (total, items) = match &status_filter {
            Some(st) => {
                let total: i64 = conn.query_row(
                    "SELECT COUNT(*) FROM orders WHERE status=?1 AND deleted_at IS NULL",
                    rusqlite::params![st], |r| r.get(0))?;
                let mut stmt = conn.prepare(
                    "SELECT order_id, out_trade_no, ezfpy_trade_no, payment_channel, payment_time,
                            paid_processed, user_id, customer_name, customer_contact, username,
                            website_id, task_type, course_ids, video_count, exam_count, price,
                            notes, status, paid, task_id, admin_note, created_at, updated_at,
                            accepted_at, started_at, finished_at
                     FROM orders WHERE status=?1 AND deleted_at IS NULL
                     ORDER BY created_at DESC LIMIT ?2")?;
                let mut rows: Vec<Value> = stmt.query_map(rusqlite::params![st, limit], |r| {
                    let cids: String = r.get(12)?;
                    order_row_to_json(r, &cids)
                })?.collect::<Result<Vec<_>, _>>()?;
                inject_progress(&conn, &mut rows)?;
                (total, rows)
            }
            None => {
                let total: i64 = conn.query_row(
                    "SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL", [], |r| r.get(0))?;
                let mut stmt = conn.prepare(
                    "SELECT order_id, out_trade_no, ezfpy_trade_no, payment_channel, payment_time,
                            paid_processed, user_id, customer_name, customer_contact, username,
                            website_id, task_type, course_ids, video_count, exam_count, price,
                            notes, status, paid, task_id, admin_note, created_at, updated_at,
                            accepted_at, started_at, finished_at
                     FROM orders WHERE deleted_at IS NULL
                     ORDER BY created_at DESC LIMIT ?1")?;
                let mut rows: Vec<Value> = stmt.query_map(rusqlite::params![limit], |r| {
                    let cids: String = r.get(12)?;
                    order_row_to_json(r, &cids)
                })?.collect::<Result<Vec<_>, _>>()?;
                inject_progress(&conn, &mut rows)?;
                (total, rows)
            }
        };
        Ok(json!({
            "total": total,
            "page": 1,
            "page_size": limit,
            "total_pages": ((total + limit - 1) / limit).max(1),
            "items": items,
        }))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => Json(json!({"success": true, "message": "ok", "data": data})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

async fn order_get(State(state): State<AppState>, Path(order_id): Path<String>) -> Json<Value> {
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Option<Value>> {
        let conn = db.get()?;
        let row = conn.query_row(
            "SELECT order_id, out_trade_no, ezfpy_trade_no, payment_channel, payment_time,
                    paid_processed, user_id, customer_name, customer_contact, username,
                    website_id, task_type, course_ids, video_count, exam_count, price,
                    notes, status, paid, task_id, admin_note, created_at, updated_at,
                    accepted_at, started_at, finished_at
             FROM orders WHERE order_id=?1 AND deleted_at IS NULL",
            rusqlite::params![order_id],
            |r| {
                let cids: String = r.get(12)?;
                order_row_to_json(r, &cids)
            },
        );
        match row {
            Ok(v) => Ok(Some(v)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e.into()),
        }
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(Some(data)) => Json(json!({"success": true, "message": "ok", "data": data})),
        Ok(None) => Json(json!({"success": false, "message": "订单不存在"})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

async fn admin_dashboard(State(state): State<AppState>) -> Json<Value> {
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Value> {
        let conn = db.get()?;
        let today_prefix: String = crate::queue::now_str()[..10].into();
        let today = today_prefix.as_str();

        let (total, today_c, week_c, completed, pending, running, failed): (i64, i64, i64, i64, i64, i64, i64) = {
            let count = |sql: &str, params: &[&dyn rusqlite::ToSql]| -> i64 {
                conn.query_row(sql, params, |r| r.get(0)).unwrap_or(0)
            };
            (
                count("SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL", &[]),
                count("SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL AND created_at LIKE ?1", &[&format!("{today}%")]),
                count("SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL AND created_at >= ?1", &[&week_start_prefix()]),
                count("SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL AND status='completed'", &[]),
                count("SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL AND status='pending'", &[]),
                count("SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL AND status='running'", &[]),
                count("SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL AND status='failed'", &[]),
            )
        };
        // 简化：week 按近 7 天日期前缀计算（对齐 Python 的口径近似）
        let week_c = week_c.max(today_c);

        let revenue = |cond: &str, params: Vec<String>| -> f64 {
            conn.query_row(
                &format!("SELECT COALESCE(SUM(price),0) FROM orders WHERE deleted_at IS NULL AND {cond}"),
                rusqlite::params_from_iter(params.iter().map(|s| s.as_str())),
                |r| r.get(0),
            ).unwrap_or(0.0)
        };
        let rev_total: f64 = revenue("1=1", vec![]);
        let rev_today: f64 = revenue("created_at LIKE ?1", vec![format!("{today}%")]);
        let rev_week: f64 = revenue("created_at >= ?1", vec![format!("{}T00:00:00", &today_prefix[..10])]);

        let mut stmt = conn.prepare(
            "SELECT website_id, COUNT(*), COALESCE(SUM(price),0) FROM orders WHERE deleted_at IS NULL GROUP BY website_id")?;
        let mut dist = std::collections::HashMap::new();
        for r in stmt.query_map([], |r| Ok((r.get::<_, i64>(0)?, r.get::<_, i64>(1)?, r.get::<_, f64>(2)?)))? {
            let (w, c, v) = r?;
            dist.insert(w, (c, v));
        }
        let platform_distribution: Vec<Value> = (1..=4).map(|w| {
            let (c, v) = dist.get(&w).copied().unwrap_or((0, 0.0));
            json!({"website_id": w, "count": c, "revenue": v})
        }).collect();

        let mut stmt = conn.prepare(
            "SELECT task_type, COUNT(*), COALESCE(SUM(price),0) FROM orders WHERE deleted_at IS NULL GROUP BY task_type")?;
        let task_type_distribution: Vec<Value> = stmt.query_map([], |r| {
            Ok(json!({"task_type": r.get::<_, String>(0)?, "count": r.get::<_, i64>(1)?, "revenue": r.get::<_, f64>(2)?}))
        })?.collect::<Result<Vec<_>, _>>()?;

        let mut stmt = conn.prepare(
            "SELECT status, COUNT(*) FROM orders WHERE deleted_at IS NULL GROUP BY status")?;
        let status_distribution: Vec<Value> = stmt.query_map([], |r| {
            Ok(json!({"status": r.get::<_, String>(0)?, "count": r.get::<_, i64>(1)?}))
        })?.collect::<Result<Vec<_>, _>>()?;

        // recent_7_days：MM/DD 标签 7 天
        let mut recent_7_days = Vec::new();
        let now_secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs();
        for i in (0..7).rev() {
            let day_secs = now_secs - i * 86400;
            let (date_label, prefix) = day_label(day_secs);
            let orders: i64 = conn.query_row(
                "SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL AND created_at LIKE ?1",
                rusqlite::params![format!("{prefix}%")], |r| r.get(0)).unwrap_or(0);
            let rev: f64 = conn.query_row(
                "SELECT COALESCE(SUM(price),0) FROM orders WHERE deleted_at IS NULL AND created_at LIKE ?1",
                rusqlite::params![format!("{prefix}%")], |r| r.get(0)).unwrap_or(0.0);
            recent_7_days.push(json!({"date": date_label, "orders": orders, "revenue": rev}));
        }

        let mut stmt = conn.prepare(
            "SELECT order_id, username, website_id, task_type, price, status, created_at
             FROM orders WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 10")?;
        let recent_orders: Vec<Value> = stmt.query_map([], |r| {
            Ok(json!({
                "order_id": r.get::<_, String>(0)?,
                "username": r.get::<_, Option<String>>(1)?.unwrap_or_default(),
                "website_id": r.get::<_, i64>(2)?,
                "task_type": r.get::<_, Option<String>>(3)?.unwrap_or_default(),
                "price": r.get::<_, f64>(4)?,
                "status": r.get::<_, Option<String>>(5)?.unwrap_or_default(),
                "created_at": r.get::<_, Option<String>>(6)?.unwrap_or_default(),
            }))
        })?.collect::<Result<Vec<_>, _>>()?;

        Ok(json!({
            "orders": {
                "total": total, "today": today_c, "week": week_c,
                "completed": completed, "pending": pending, "running": running, "failed": failed,
                "completion_rate": if total > 0 { completed as f64 / total as f64 } else { 0.0 },
            },
            "revenue": {"total": rev_total, "today": rev_today, "week": rev_week},
            "platform_distribution": platform_distribution,
            "task_type_distribution": task_type_distribution,
            "status_distribution": status_distribution,
            "recent_7_days": recent_7_days,
            "recent_orders": recent_orders,
        }))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => Json(json!({"success": true, "message": "ok", "data": data})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 近 7 天起始日期前缀（YYYY-MM-DD）
fn week_start_prefix() -> String {
    let now_secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs();
    day_label(now_secs - 6 * 86400).1
}

/// 秒时间戳 → (MM/DD 标签, YYYY-MM-DD 前缀)
fn day_label(secs: u64) -> (String, String) {
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
    (format!("{:02}/{:02}", m + 1, rem + 1), format!("{:04}-{:02}-{:02}", y, m + 1, rem + 1))
}

async fn queue_stats(State(state): State<AppState>) -> Json<Value> {
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Value> {
        let conn = db.get()?;
        let table_stats = |table: &str| -> rusqlite::Result<Map<String, Value>> {
            let mut m = Map::new();
            for st in ["pending", "running", "waiting", "completed", "failed"] {
                let c: i64 = conn.query_row(
                    &format!("SELECT COUNT(*) FROM {table} WHERE status=?1"),
                    rusqlite::params![st], |r| r.get(0))?;
                m.insert(st.to_string(), json!(c));
            }
            let total: i64 = conn.query_row(
                &format!("SELECT COUNT(*) FROM {table}"), [], |r| r.get(0))?;
            m.insert("total".into(), json!(total));
            Ok(m)
        };
        let mut school = table_stats("queue_jobs_school")?;
        let mut chaoxing = table_stats("queue_jobs_chaoxing")?;
        school.insert("active_workers".into(), json!(0));
        school.insert("max_workers".into(), json!(15));
        school.insert("active_study_workers".into(), json!(0));
        school.insert("max_study_workers".into(), json!(15));
        school.insert("paused".into(), json!(false));
        school.insert("queue_name".into(), json!("school"));
        chaoxing.insert("active_workers".into(), json!(0));
        chaoxing.insert("max_workers".into(), json!(15));
        chaoxing.insert("active_study_workers".into(), json!(0));
        chaoxing.insert("max_study_workers".into(), json!(15));
        chaoxing.insert("paused".into(), json!(false));
        chaoxing.insert("queue_name".into(), json!("chaoxing"));

        let sum = |k: &str| -> i64 {
            school.get(k).and_then(|v| v.as_i64()).unwrap_or(0)
                + chaoxing.get(k).and_then(|v| v.as_i64()).unwrap_or(0)
        };
        Ok(json!({
            "pending": sum("pending"), "running": sum("running"), "waiting": sum("waiting"),
            "completed": sum("completed"), "failed": sum("failed"), "total": sum("total"),
            "active_workers": 0, "max_workers": 30, "paused": false,
            "school": school, "chaoxing": chaoxing,
        }))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => Json(json!({"success": true, "message": "ok", "data": data})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

async fn pricing(State(state): State<AppState>) -> Json<Value> {
    let db = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Value> {
        let conn = db.get()?;
        let defaults = [
            ("priceSmall", 3.0), ("priceMedium", 5.0), ("priceLarge", 6.0),
            ("discount25", 0.7), ("discount50", 0.5), ("discount75", 0.3),
            ("priceMinimum", 2.0), ("priceExamOnly", 5.0), ("priceHomeworkOnly", 3.0),
            ("priceChaoxing", 8.0),
        ];
        let mut data = Map::new();
        for (key, default) in defaults {
            let v: Option<String> = conn.query_row(
                "SELECT config_value FROM system_config WHERE config_key=?1",
                rusqlite::params![key], |r| r.get(0),
            ).ok().flatten();
            let val = v.and_then(|s| s.parse::<f64>().ok()).unwrap_or(default);
            data.insert(key.to_string(), json!(val));
        }
        Ok(Value::Object(data))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(data) => Json(json!({"code": 0, "data": data})),
        Err(e) => Json(json!({"code": -1, "data": {}, "message": e.to_string()})),
    }
}

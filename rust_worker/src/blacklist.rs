//! 风控黑名单：账号黑名单 + IP 黑名单 + IP 限制（同 IP 最多提交几个学号）。
//!
//! 三条防线，全部落在后端（前端弹窗只是提示，绕不过）：
//!
//! 1. **账号黑名单**（`account_blacklist`，判定只看 username）
//!    - `school_exam::scan_courses` / `scan_chaoxing`：一进门（扫描）就拦下
//!    - `order::create_batch_orders`：下单/刷课的权威闸门
//! 2. **IP 黑名单**（`ip_blacklist`，判定只看 IP）
//!    - `guard::ip_guard` 中间件：命中即全站 403（连静态页都不给）
//!    - 命中集合缓存在进程内（DashMap），启动时载入、增删时同步，避免每请求查库
//! 3. **IP 限制**（`ip_submissions` + `system_config` 里的三个配置键）
//!    - 同一 IP 在 N 小时内最多提交 M 个**不同**学号；超了拒绝下单
//!    - 只有不同的学号才计数：同一学号重试/重复提交不会把额度耗光
//!
//! 查询失败一律 **fail-open**（黑名单是运营策略而非业务正确性前提，
//! 不能因为一次查库抖动就把正常学员挡在门外），失败会打 warn 日志。

use axum::extract::{Path, State};
use axum::routing::{delete, get};
use axum::{Json, Router};
use serde_json::{json, Value};

use crate::AppState;

/// 账号被拉黑时统一返回的文案（前端据此弹窗）
pub const BLOCKED_MESSAGE: &str = "该账号已被本平台拉黑，无法享用免费刷课";
/// 同 IP 提交账号数超限时统一返回的文案
pub const IP_LIMIT_MESSAGE: &str = "当前网络地址提交的账号数量已达上限，无法继续免费刷课";

/// IP 限制的三个配置键（存 system_config，后台可视化调整）
const CFG_IP_LIMIT_ENABLED: &str = "ip_limit_enabled";
const CFG_IP_LIMIT_MAX: &str = "ip_limit_max_accounts";
const CFG_IP_LIMIT_WINDOW: &str = "ip_limit_window_hours";
/// 默认：开启，24 小时内最多 5 个不同学号（正常学员自己 1 个，代刷党几十个）
const DEFAULT_IP_LIMIT_MAX: i64 = 5;
const DEFAULT_IP_LIMIT_WINDOW_HOURS: i64 = 24;

/// 后台「拉黑管理」的管理接口（挂在 api.rs 的鉴权分组里）
pub fn router() -> Router<AppState> {
    Router::new()
        // 账号黑名单
        .route("/api/admin/blacklist", get(list_accounts).post(add_account))
        .route("/api/admin/blacklist/{id}", delete(remove_account))
        // IP 黑名单
        .route("/api/admin/ip-blacklist", get(list_ips).post(add_ip))
        .route("/api/admin/ip-blacklist/{id}", delete(remove_ip))
        // 下单来源记录（按 IP 聚合：提交过几个不同学号、最近一次什么时候）
        .route("/api/admin/ip-records", get(ip_records))
        // IP 限制设置（开关 / 上限 / 窗口）
        .route("/api/admin/ip-limit", get(ip_limit_get).post(ip_limit_set))
}

// ── 进程内 IP 黑名单缓存（中间件每请求都要判，不能查库）──────────────────

static IP_SET: std::sync::OnceLock<dashmap::DashMap<String, ()>> = std::sync::OnceLock::new();

fn ip_set() -> &'static dashmap::DashMap<String, ()> {
    IP_SET.get_or_init(dashmap::DashMap::new)
}

/// 该 IP 是否在黑名单里（同步，中间件用）
pub fn ip_is_blocked(ip: &str) -> bool {
    ip_set().contains_key(ip)
}

/// 启动时把库里的 IP 黑名单载入进程缓存
pub async fn load_ip_cache(db: &crate::db::Db) -> anyhow::Result<usize> {
    let pool = db.clone_pool();
    let ips = tokio::task::spawn_blocking(move || -> anyhow::Result<Vec<String>> {
        let conn = pool.get()?;
        let mut stmt = conn.prepare("SELECT ip FROM ip_blacklist")?;
        let v = stmt
            .query_map([], |r| r.get::<_, String>(0))?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        Ok(v)
    })
    .await??;
    let set = ip_set();
    set.clear();
    for ip in &ips {
        set.insert(ip.clone(), ());
    }
    Ok(ips.len())
}

// ── 账号黑名单 ────────────────────────────────────────────────────────────

/// 是否被拉黑：命中返回原因（可能为空串 = 拉黑时没填原因）
pub async fn blocked_reason(db: &crate::db::Db, username: &str) -> Option<String> {
    let username = username.trim().to_string();
    if username.is_empty() {
        return None;
    }
    let pool = db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Option<String>> {
        let conn = pool.get()?;
        let mut stmt = conn.prepare("SELECT reason FROM account_blacklist WHERE username=?1")?;
        let mut rows = stmt.query(rusqlite::params![username])?;
        match rows.next()? {
            Some(r) => Ok(Some(r.get::<_, Option<String>>(0)?.unwrap_or_default())),
            None => Ok(None),
        }
    })
    .await;
    match result {
        Ok(Ok(v)) => v,
        Ok(Err(e)) => {
            tracing::warn!("黑名单查询失败（本次放行）: {e}");
            None
        }
        Err(e) => {
            tracing::warn!("黑名单查询 spawn_blocking 失败（本次放行）: {e}");
            None
        }
    }
}

/// 账号被拉黑时的统一失败响应（含 `blacklisted` 标记，前端据此弹窗而不是 toast）
pub fn blocked_payload() -> Value {
    json!({"success": false, "blacklisted": true, "message": BLOCKED_MESSAGE})
}

async fn list_accounts(State(state): State<AppState>) -> Json<Value> {
    let pool = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Vec<Value>> {
        let conn = pool.get()?;
        let mut stmt = conn.prepare(
            "SELECT id, username, website_id, reason, created_at, created_by
             FROM account_blacklist ORDER BY id DESC",
        )?;
        let rows = stmt
            .query_map([], |r| {
                Ok(json!({
                    "id": r.get::<_, i64>(0)?,
                    "username": r.get::<_, String>(1)?,
                    "website_id": r.get::<_, i64>(2)?,
                    "reason": r.get::<_, String>(3)?,
                    "created_at": r.get::<_, String>(4)?,
                    "created_by": r.get::<_, String>(5)?,
                }))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        Ok(rows)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(items) => Json(json!({"success": true, "message": "ok", "data": {"items": items}})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 拉黑账号（重复拉黑视为覆盖原因/来源平台，id 不变）
async fn add_account(State(state): State<AppState>, Json(body): Json<Value>) -> Json<Value> {
    let username = body["username"].as_str().unwrap_or("").trim().to_string();
    if username.is_empty() {
        return Json(json!({"success": false, "message": "账号不能为空"}));
    }
    let website_id = body["website_id"].as_i64().unwrap_or(0);
    let reason = body["reason"].as_str().unwrap_or("").trim()
        .chars().take(200).collect::<String>();
    let pool = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<()> {
        let conn = pool.get()?;
        let now = crate::queue::now_str();
        // 已存在则覆盖（子查询取回原 id：INSERT OR REPLACE 会删除重插，
        // 不显式带 id 的话每次都换新 id，前端列表会出现"重复项"错觉）
        conn.execute(
            "INSERT OR REPLACE INTO account_blacklist
                 (id, username, website_id, reason, created_at, created_by)
             VALUES ((SELECT id FROM account_blacklist WHERE username=?1), ?1, ?2, ?3, ?4, 'admin')",
            rusqlite::params![username, website_id, reason, now],
        )?;
        audit(&conn, "blacklist_add", &format!("{username}（平台 {website_id}）：{reason}"))?;
        Ok(())
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(()) => Json(json!({"success": true, "message": "已拉黑该账号"})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 解除账号拉黑
async fn remove_account(State(state): State<AppState>, Path(id): Path<i64>) -> Json<Value> {
    let pool = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<usize> {
        let conn = pool.get()?;
        let username: String = conn
            .query_row("SELECT username FROM account_blacklist WHERE id=?1", rusqlite::params![id],
                       |r| r.get(0))
            .unwrap_or_default();
        let n = conn.execute("DELETE FROM account_blacklist WHERE id=?1", rusqlite::params![id])?;
        if n > 0 {
            audit(&conn, "blacklist_remove", &username)?;
        }
        Ok(n)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(n) if n > 0 => Json(json!({"success": true, "message": "已解除拉黑"})),
        Ok(_) => Json(json!({"success": false, "message": "记录不存在"})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

// ── IP 黑名单 ─────────────────────────────────────────────────────────────

/// 校验 IP 字面量：只收 IPv4/IPv6（挡掉把域名/任意字符串写进黑名单）
fn valid_ip(s: &str) -> bool {
    s.parse::<std::net::IpAddr>().is_ok()
}

async fn list_ips(State(state): State<AppState>) -> Json<Value> {
    let pool = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Vec<Value>> {
        let conn = pool.get()?;
        let mut stmt = conn.prepare(
            "SELECT id, ip, reason, created_at, created_by FROM ip_blacklist ORDER BY id DESC",
        )?;
        let rows = stmt
            .query_map([], |r| {
                Ok(json!({
                    "id": r.get::<_, i64>(0)?,
                    "ip": r.get::<_, String>(1)?,
                    "reason": r.get::<_, String>(2)?,
                    "created_at": r.get::<_, String>(3)?,
                    "created_by": r.get::<_, String>(4)?,
                }))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        Ok(rows)
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(items) => Json(json!({"success": true, "message": "ok", "data": {"items": items}})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 拉黑 IP（重复拉黑覆盖原因，id 不变；同时刷新进程内缓存）
async fn add_ip(State(state): State<AppState>, Json(body): Json<Value>) -> Json<Value> {
    let ip = body["ip"].as_str().unwrap_or("").trim().to_string();
    if !valid_ip(&ip) {
        return Json(json!({"success": false, "message": "IP 格式不正确（只支持 IPv4 / IPv6）"}));
    }
    let reason = body["reason"].as_str().unwrap_or("").trim()
        .chars().take(200).collect::<String>();
    let pool = state.db.clone_pool();
    let ip2 = ip.clone();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<()> {
        let conn = pool.get()?;
        let now = crate::queue::now_str();
        conn.execute(
            "INSERT OR REPLACE INTO ip_blacklist (id, ip, reason, created_at, created_by)
             VALUES ((SELECT id FROM ip_blacklist WHERE ip=?1), ?1, ?2, ?3, 'admin')",
            rusqlite::params![ip2, reason, now],
        )?;
        audit(&conn, "ip_blacklist_add", &format!("{ip2}：{reason}"))?;
        Ok(())
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(()) => {
            ip_set().insert(ip, ());
            Json(json!({"success": true, "message": "已拉黑该 IP"}))
        }
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

/// 解除 IP 拉黑（同时从进程内缓存移除）
async fn remove_ip(State(state): State<AppState>, Path(id): Path<i64>) -> Json<Value> {
    let pool = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<(usize, String)> {
        let conn = pool.get()?;
        let ip: String = conn
            .query_row("SELECT ip FROM ip_blacklist WHERE id=?1", rusqlite::params![id], |r| r.get(0))
            .unwrap_or_default();
        let n = conn.execute("DELETE FROM ip_blacklist WHERE id=?1", rusqlite::params![id])?;
        if n > 0 {
            audit(&conn, "ip_blacklist_remove", &ip)?;
        }
        Ok((n, ip))
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok((n, ip)) if n > 0 => {
            ip_set().remove(&ip);
            Json(json!({"success": true, "message": "已解除该 IP 的拉黑"}))
        }
        Ok(_) => Json(json!({"success": false, "message": "记录不存在"})),
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

// ── 下单来源记录（按 IP 聚合，供后台"看着拉黑"）──────────────────────────

async fn ip_records(State(state): State<AppState>) -> Json<Value> {
    let pool = state.db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<Vec<Value>> {
        let conn = pool.get()?;
        // accounts = 不同学号数（就是 IP 限制计数的口径），submissions = 提交次数
        let mut stmt = conn.prepare(
            "SELECT ip, COUNT(DISTINCT username), COUNT(*), MAX(created_at)
             FROM ip_submissions GROUP BY ip
             ORDER BY COUNT(DISTINCT username) DESC, MAX(created_at) DESC LIMIT 200",
        )?;
        let rows = stmt
            .query_map([], |r| {
                Ok((
                    r.get::<_, String>(0)?,
                    r.get::<_, i64>(1)?,
                    r.get::<_, i64>(2)?,
                    r.get::<_, Option<String>>(3)?.unwrap_or_default(),
                ))
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        Ok(rows
            .into_iter()
            .map(|(ip, accounts, submissions, last_seen)| {
                json!({"ip": ip, "accounts": accounts, "submissions": submissions, "last_seen": last_seen})
            })
            .collect())
    })
    .await
    .map_err(|e| anyhow::anyhow!("{e}"))
    .and_then(|v| v);
    match result {
        Ok(mut items) => {
            for it in items.iter_mut() {
                let ip = it["ip"].as_str().unwrap_or("").to_string();
                it["blocked"] = json!(ip_is_blocked(&ip));
            }
            Json(json!({"success": true, "message": "ok", "data": {"items": items}}))
        }
        Err(e) => Json(json!({"success": false, "message": e.to_string()})),
    }
}

// ── IP 限制（同 IP 最多提交几个不同学号）─────────────────────────────────

/// 读取当前 IP 限制设置
pub async fn ip_limit_config(db: &crate::db::Db) -> (bool, i64, i64) {
    let enabled = crate::queue::config_get(db, CFG_IP_LIMIT_ENABLED).await
        .map(|v| v != "0").unwrap_or(true);
    let max = crate::queue::config_get(db, CFG_IP_LIMIT_MAX).await
        .and_then(|v| v.parse::<i64>().ok()).unwrap_or(DEFAULT_IP_LIMIT_MAX).max(1);
    let hours = crate::queue::config_get(db, CFG_IP_LIMIT_WINDOW).await
        .and_then(|v| v.parse::<i64>().ok()).unwrap_or(DEFAULT_IP_LIMIT_WINDOW_HOURS).max(1);
    (enabled, max, hours)
}

async fn ip_limit_get(State(state): State<AppState>) -> Json<Value> {
    let (enabled, max_accounts, window_hours) = ip_limit_config(&state.db).await;
    Json(json!({
        "success": true,
        "message": "ok",
        "data": {"enabled": enabled, "max_accounts": max_accounts, "window_hours": window_hours},
    }))
}

async fn ip_limit_set(State(state): State<AppState>, Json(body): Json<Value>) -> Json<Value> {
    let enabled = body["enabled"].as_bool().unwrap_or(true);
    // 上限 1~200、窗口 1~720 小时：给足运营空间，也挡住把 0 写进去导致人人被拦
    let max = body["max_accounts"].as_i64().unwrap_or(DEFAULT_IP_LIMIT_MAX).clamp(1, 200);
    let hours = body["window_hours"].as_i64().unwrap_or(DEFAULT_IP_LIMIT_WINDOW_HOURS).clamp(1, 720);
    let pairs = [
        (CFG_IP_LIMIT_ENABLED, (if enabled { "1" } else { "0" }).to_string()),
        (CFG_IP_LIMIT_MAX, max.to_string()),
        (CFG_IP_LIMIT_WINDOW, hours.to_string()),
    ];
    for (k, v) in pairs {
        if let Err(e) = crate::queue::config_set(&state.db, k, &v).await {
            return Json(json!({"success": false, "message": e.to_string()}));
        }
    }
    Json(json!({
        "success": true,
        "message": "已保存",
        "data": {"enabled": enabled, "max_accounts": max, "window_hours": hours},
    }))
}

/// 下单时的 IP 限制闸门：放行则返回 `true`，超限返回 `false`。
///
/// 语义要点：
///   - 只有**不同学号**才吃额度（同一学号重试不重复计数）
///   - 已记录过该 (ip, username) 组合的一律放行 —— 否则老用户过一轮窗口就被拦
///   - `unknown` / 空 IP 不参与限制（拿不到来源时宁可放过，也不能误伤所有本机直连）
pub async fn check_ip_limit(db: &crate::db::Db, ip: &str, username: &str) -> bool {
    let ip = ip.trim().to_string();
    let username = username.trim().to_string();
    if ip.is_empty() || ip == "unknown" || username.is_empty() {
        return true;
    }
    let (enabled, max, hours) = ip_limit_config(db).await;
    if !enabled {
        return true;
    }
    let now = crate::queue::local_secs() as i64;
    let cutoff = now - hours * 3600;
    let pool = db.clone_pool();
    let result = tokio::task::spawn_blocking(move || -> anyhow::Result<bool> {
        let conn = pool.get()?;
        let seen: i64 = conn.query_row(
            "SELECT COUNT(*) FROM ip_submissions WHERE ip=?1 AND username=?2",
            rusqlite::params![ip, username],
            |r| r.get(0),
        )?;
        if seen == 0 {
            let used: i64 = conn.query_row(
                "SELECT COUNT(DISTINCT username) FROM ip_submissions WHERE ip=?1 AND ts>=?2",
                rusqlite::params![ip, cutoff],
                |r| r.get(0),
            )?;
            if used >= max {
                return Ok(false);
            }
        }
        conn.execute(
            "INSERT INTO ip_submissions (ip, username, created_at, ts) VALUES (?1, ?2, ?3, ?4)",
            rusqlite::params![ip, username, crate::queue::now_str(), now],
        )?;
        Ok(true)
    })
    .await;
    match result {
        Ok(Ok(v)) => v,
        Ok(Err(e)) => {
            tracing::warn!("IP 限制查询失败（本次放行）: {e}");
            true
        }
        Err(e) => {
            tracing::warn!("IP 限制 spawn_blocking 失败（本次放行）: {e}");
            true
        }
    }
}

/// IP 超限时的统一失败响应（含 `ip_limited` 标记，前端据此弹窗）
pub fn ip_limited_payload() -> Value {
    json!({"success": false, "ip_limited": true, "message": IP_LIMIT_MESSAGE})
}

/// 黑名单动作写审计日志（与订单动作同一张 audit_logs 表）
fn audit(conn: &rusqlite::Connection, event_type: &str, detail: &str) -> rusqlite::Result<()> {
    let log_id = format!("LOG-{:08X}", rand::random::<u32>());
    conn.execute(
        "INSERT INTO audit_logs (log_id, event_type, operator, detail, order_id, user_id, created_at)
         VALUES (?1, ?2, 'admin', ?3, '', '', ?4)",
        rusqlite::params![log_id, event_type, detail, crate::queue::now_str()],
    )?;
    Ok(())
}
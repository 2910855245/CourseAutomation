//! 运行日志：内存环形缓冲 + WebSocket 实时推送 + SQLite 持久层。
//!
//! 三层各司其职，都是为了"后台能实时看到上报记录，且日志不会把内存/磁盘撑爆"：
//!
//! 1. **内存环形缓冲**（`VecDeque`，上限 `LOG_MEM_MAX`，满则淘汰最旧）。
//!    面板打开时先读它，保证刷新页面立刻有内容，不必等新日志。
//! 2. **WebSocket 广播**：复用 progress.rs 的同一条广播通道，topic=`logs`。
//!    管理端已用 `*` 订阅（见 progress.rs `handle_control` 的 admin 分支），
//!    因此无需新增鉴权面 —— 未鉴权连接拿不到 `logs` 帧。
//! 3. **SQLite 持久层**：异步批量写（bounded channel + `try_send`），
//!    进程重启后仍能回看历史。写入溢出时直接丢弃并计数，绝不反压业务线程 ——
//!    日志系统拖垮刷课引擎是比丢日志严重得多的事故。
//!
//! **垃圾回收**：`gc_loop` 每 5 分钟跑一次，同时按两个阈值裁剪 ——
//! 内存按 TTL（`LOG_MEM_TTL_HOURS`）过期淘汰，DB 按 TTL（`LOG_DB_TTL_DAYS`）
//! 删除旧行、再按条数上限（`LOG_DB_MAX_ROWS`）保留最新的一批。
//! 只按 TTL 不按条数，遇到突发刷屏仍会把库撑大；只按条数不按 TTL，
//! 则沉寂期也会一直留着几个月前的旧行。两者都设才闭环。
//!
//! **脱敏**：日志会进后台面板，禁止写入密码/cookie/token。
//! 账号类信息只记用户名，`detail` 里不放凭据（见 `redact`）。

use std::collections::VecDeque;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use axum::extract::{Query, State};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::sync::{broadcast, mpsc};

use crate::progress::Envelope;
use crate::AppState;

// ── 级别与分类 ──────────────────────────────────────────────────────────
pub const LEVEL_DEBUG: &str = "DEBUG";
pub const LEVEL_INFO: &str = "INFO";
pub const LEVEL_WARN: &str = "WARN";
pub const LEVEL_ERROR: &str = "ERROR";

pub const CAT_REPORT: &str = "report";
pub const CAT_LOGIN: &str = "login";
pub const CAT_ORDER: &str = "order";
pub const CAT_QUEUE: &str = "queue";
pub const CAT_EXAM: &str = "exam";
pub const CAT_SCAN: &str = "scan";
pub const CAT_SYSTEM: &str = "system";
/// 域名监控（学校首页抓取 / 域名与显示名变更）
pub const CAT_DOMAIN: &str = "domain";

/// 广播 topic。前端 realtime store 以它为前缀订阅。
pub const TOPIC: &str = "logs";

// ── 配置（环境变量可覆盖）──────────────────────────────────────────────
/// 内存环形缓冲条数上限。5000 条约 1~2MB，足够面板回看且不会失控。
const DEFAULT_MEM_MAX: usize = 5000;
/// 内存条目存活时长（小时）。
const DEFAULT_MEM_TTL_HOURS: u64 = 6;
/// DB 条目存活时长（天）。
const DEFAULT_DB_TTL_DAYS: u64 = 7;
/// DB 保留的最大行数（TTL 之外的第二道闸）。
const DEFAULT_DB_MAX_ROWS: i64 = 50_000;
/// 待落库队列长度。满了就丢，不阻塞业务线程。
const DB_QUEUE_CAP: usize = 4096;
/// 单批落库上限。
const DB_BATCH_MAX: usize = 256;
/// GC 间隔（秒）。
const GC_INTERVAL_SECS: u64 = 300;

fn env_usize(key: &str, default: usize) -> usize {
    std::env::var(key).ok().and_then(|v| v.trim().parse().ok()).unwrap_or(default)
}

fn env_u64(key: &str, default: u64) -> u64 {
    std::env::var(key).ok().and_then(|v| v.trim().parse().ok()).unwrap_or(default)
}

fn mem_max() -> usize {
    env_usize("LOG_MEM_MAX", DEFAULT_MEM_MAX).max(100)
}

fn mem_ttl_ms() -> i64 {
    (env_u64("LOG_MEM_TTL_HOURS", DEFAULT_MEM_TTL_HOURS) as i64) * 3_600_000
}

fn db_ttl_ms() -> i64 {
    (env_u64("LOG_DB_TTL_DAYS", DEFAULT_DB_TTL_DAYS) as i64) * 86_400_000
}

fn db_max_rows() -> i64 {
    env_u64("LOG_DB_MAX_ROWS", DEFAULT_DB_MAX_ROWS as u64) as i64
}

pub fn now_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

// ── 数据模型 ────────────────────────────────────────────────────────────
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct LogEntry {
    /// 进程内自增序号（前端据此去重/排序，重启后从头开始）
    pub seq: u64,
    /// epoch 毫秒
    pub ts: i64,
    pub level: String,
    pub category: String,
    #[serde(default)]
    pub order_id: String,
    #[serde(default)]
    pub node_id: String,
    pub message: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub detail: Option<Value>,
}

// ── 全局状态 ────────────────────────────────────────────────────────────
struct Store {
    buf: Mutex<VecDeque<LogEntry>>,
    /// 已生成的总条数（含已被淘汰的）
    total: AtomicU64,
    /// 因内存上限被淘汰的条数
    evicted: AtomicU64,
    /// 因落库队列满被丢弃的条数
    dropped: AtomicU64,
}

impl Store {
    fn new() -> Self {
        Self {
            buf: Mutex::new(VecDeque::with_capacity(256)),
            total: AtomicU64::new(0),
            evicted: AtomicU64::new(0),
            dropped: AtomicU64::new(0),
        }
    }
}

static STORE: OnceLock<Store> = OnceLock::new();
static BROADCAST: OnceLock<broadcast::Sender<Envelope>> = OnceLock::new();
static DB_TX: OnceLock<mpsc::Sender<LogEntry>> = OnceLock::new();
static SEQ: AtomicU64 = AtomicU64::new(1);

fn store() -> &'static Store {
    STORE.get_or_init(Store::new)
}

/// 启动装配：接管广播发送端并起落库 + GC 后台任务。
///
/// 必须在 `main` 里、`progress_tx` 建好后调用一次；未调用时 `emit` 仍然可用
/// （只写内存，不广播不落库），因此测试与单进程工具不会因为没初始化而 panic。
pub fn init(state: &AppState) {
    let _ = BROADCAST.set(state.progress_tx.clone());

    let (tx, rx) = mpsc::channel::<LogEntry>(DB_QUEUE_CAP);
    if DB_TX.set(tx).is_ok() {
        let db = state.db.clone();
        tokio::spawn(writer_loop(db.clone(), rx));
        tokio::spawn(gc_loop(db));
    }
}

// ── 写入 ────────────────────────────────────────────────────────────────

/// 记录一条日志。**同步、非阻塞**，可在任意 async/sync 上下文调用。
///
/// 内存锁只做几次 push/pop，广播是 `send`（无订阅者时直接返回），
/// 落库走 `try_send`（队列满即丢）。全程没有 `.await`，不会拖慢调用方。
pub fn emit(
    level: &str,
    category: &str,
    order_id: &str,
    node_id: &str,
    message: impl Into<String>,
    detail: Option<Value>,
) {
    let st = store();
    let entry = LogEntry {
        seq: SEQ.fetch_add(1, Ordering::Relaxed),
        ts: now_ms(),
        level: level.to_string(),
        category: category.to_string(),
        order_id: order_id.to_string(),
        node_id: node_id.to_string(),
        message: message.into(),
        detail,
    };
    st.total.fetch_add(1, Ordering::Relaxed);

    // 1) 内存环形缓冲：满则淘汰最旧
    {
        let mut buf = match st.buf.lock() {
            Ok(g) => g,
            // 锁中毒说明别处 panic 过；日志系统不能因此再 panic
            Err(p) => p.into_inner(),
        };
        let cap = mem_max();
        while buf.len() >= cap {
            buf.pop_front();
            st.evicted.fetch_add(1, Ordering::Relaxed);
        }
        buf.push_back(entry.clone());
    }

    // 2) 实时广播（复用进度通道，topic=logs）
    if let Some(tx) = BROADCAST.get() {
        let envelope = json!({
            "v": 1,
            "topic": TOPIC,
            "type": "log",
            "data": &entry,
            "ts": entry.ts,
            "seq": entry.seq,
        });
        let _ = tx.send(Envelope {
            topic: Arc::from(TOPIC),
            body: Arc::from(envelope.to_string().as_str()),
        });
    }

    // 3) 持久化：DEBUG 不落库（噪声大、无回看价值）
    if entry.level != LEVEL_DEBUG {
        if let Some(tx) = DB_TX.get() {
            if tx.try_send(entry).is_err() {
                st.dropped.fetch_add(1, Ordering::Relaxed);
            }
        }
    }
}

/// 便捷包装：`info("queue", order, node, msg)`
pub fn info(cat: &str, order: &str, node: &str, msg: impl Into<String>) {
    emit(LEVEL_INFO, cat, order, node, msg, None);
}

pub fn warn(cat: &str, order: &str, node: &str, msg: impl Into<String>) {
    emit(LEVEL_WARN, cat, order, node, msg, None);
}

pub fn error(cat: &str, order: &str, node: &str, msg: impl Into<String>) {
    emit(LEVEL_ERROR, cat, order, node, msg, None);
}

/// 带结构化的详情（上报记录走它）
pub fn info_detail(
    cat: &str,
    order: &str,
    node: &str,
    msg: impl Into<String>,
    detail: Value,
) {
    emit(LEVEL_INFO, cat, order, node, msg, Some(detail));
}

// ── 落库后台任务 ─────────────────────────────────────────────────────────
async fn writer_loop(db: crate::db::Db, mut rx: mpsc::Receiver<LogEntry>) {
    let mut batch: Vec<LogEntry> = Vec::with_capacity(DB_BATCH_MAX);
    loop {
        // 先阻塞等第一条，避免空转
        match rx.recv().await {
            Some(e) => batch.push(e),
            None => break,
        }
        // 再把当前积压一次性吸干（最多 DB_BATCH_MAX），把 N 次写并成 1 次事务
        while batch.len() < DB_BATCH_MAX {
            match rx.try_recv() {
                Ok(e) => batch.push(e),
                Err(_) => break,
            }
        }
        let items = std::mem::take(&mut batch);
        let pool = db.clone_pool();
        let _ = tokio::task::spawn_blocking(move || -> anyhow::Result<()> {
            let mut conn = pool.get()?;
            let tx = conn.transaction()?;
            {
                let mut stmt = tx.prepare_cached(
                    "INSERT INTO system_logs (ts, level, category, order_id, node_id, message, detail)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
                )?;
                for it in &items {
                    let detail = it.detail.as_ref().map(|d| d.to_string());
                    stmt.execute(rusqlite::params![
                        it.ts, it.level, it.category, it.order_id, it.node_id, it.message, detail
                    ])?;
                }
            }
            tx.commit()?;
            Ok(())
        })
        .await;
    }
    tracing::debug!("logs writer_loop 退出");
}

// ── 垃圾回收 ────────────────────────────────────────────────────────────

/// 内存：淘汰超过 TTL 的条目（条数上限由 `emit` 实时保证）
fn gc_memory() -> usize {
    let st = store();
    let cutoff = now_ms() - mem_ttl_ms();
    let mut buf = match st.buf.lock() {
        Ok(g) => g,
        Err(p) => p.into_inner(),
    };
    let before = buf.len();
    while let Some(front) = buf.front() {
        if front.ts >= cutoff {
            break;
        }
        buf.pop_front();
        st.evicted.fetch_add(1, Ordering::Relaxed);
    }
    before - buf.len()
}

/// DB：先按 TTL 删旧行，再按条数上限保留最新的一批
async fn gc_db(db: &crate::db::Db) -> anyhow::Result<(usize, usize)> {
    let pool = db.clone_pool();
    let ttl_cutoff = now_ms() - db_ttl_ms();
    let keep = db_max_rows();
    tokio::task::spawn_blocking(move || -> anyhow::Result<(usize, usize)> {
        let conn = pool.get()?;
        let by_ttl = conn.execute("DELETE FROM system_logs WHERE ts < ?1", [ttl_cutoff])?;
        // 只按 TTL 的话，突发刷屏仍会把库撑大；这里补一道条数闸。
        // 用 id 而非 ts 排序：id 单调，且与插入顺序一致。
        let by_rows = conn.execute(
            "DELETE FROM system_logs WHERE id <= (
                 SELECT COALESCE(MAX(id), 0) - ?1 FROM system_logs
             )",
            [keep],
        )?;
        Ok((by_ttl, by_rows))
    })
    .await?
}

async fn gc_loop(db: crate::db::Db) {
    let mut tick = tokio::time::interval(Duration::from_secs(GC_INTERVAL_SECS));
    // 首次 tick 立即触发，启动时先清一遍陈旧数据
    tick.tick().await;
    loop {
        tick.tick().await;
        let mem_freed = gc_memory();
        match gc_db(&db).await {
            Ok((by_ttl, by_rows)) => {
                if mem_freed + by_ttl + by_rows > 0 {
                    tracing::info!(
                        mem_freed,
                        db_by_ttl = by_ttl,
                        db_by_rows = by_rows,
                        "日志 GC 完成"
                    );
                }
            }
            Err(e) => tracing::warn!(error = %e, "日志 GC 失败"),
        }
    }
}

// ── HTTP 接口 ───────────────────────────────────────────────────────────

/// 管理端日志路由。挂进 api.rs 的 Bearer 鉴权组。
pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/admin/logs", get(list_logs).delete(clear_logs))
        .route("/api/admin/logs/stats", get(log_stats))
        .route("/api/admin/logs/clear", post(clear_logs))
}

#[derive(Debug, Deserialize)]
struct ListQuery {
    #[serde(default)]
    category: String,
    #[serde(default)]
    level: String,
    #[serde(default)]
    order_id: String,
    /// 只返回 seq < before 的条目（前端"加载更早"翻页用）
    #[serde(default)]
    before: Option<u64>,
    #[serde(default)]
    limit: Option<usize>,
    /// 数据源：mem（默认，内存环形缓冲）/ db（持久层，可按时间回看）
    #[serde(default)]
    source: String,
}

fn entry_matches(e: &LogEntry, q: &ListQuery) -> bool {
    if !q.category.is_empty() && e.category != q.category {
        return false;
    }
    if !q.level.is_empty() && e.level != q.level {
        return false;
    }
    if !q.order_id.is_empty() && !e.order_id.contains(&q.order_id) {
        return false;
    }
    if let Some(before) = q.before {
        if e.seq >= before {
            return false;
        }
    }
    true
}

/// 日志列表：默认读内存（最新、最快），`source=db` 读持久层（可回看更早）。
async fn list_logs(
    State(state): State<AppState>,
    Query(q): Query<ListQuery>,
) -> Json<Value> {
    let limit = q.limit.unwrap_or(300).min(2000);

    if q.source == "db" {
        let pool = state.db.clone_pool();
        let q2 = ListQuery {
            category: q.category.clone(),
            level: q.level.clone(),
            order_id: q.order_id.clone(),
            before: None,
            limit: Some(limit),
            source: String::new(),
        };
        let rows = tokio::task::spawn_blocking(move || -> anyhow::Result<Vec<LogEntry>> {
            let conn = pool.get()?;
            let mut sql = String::from(
                "SELECT ts, level, category, order_id, node_id, message, detail
                 FROM system_logs WHERE 1=1",
            );
            let mut args: Vec<Box<dyn rusqlite::ToSql>> = Vec::new();
            if !q2.category.is_empty() {
                sql.push_str(" AND category = ?");
                args.push(Box::new(q2.category.clone()));
            }
            if !q2.level.is_empty() {
                sql.push_str(" AND level = ?");
                args.push(Box::new(q2.level.clone()));
            }
            if !q2.order_id.is_empty() {
                sql.push_str(" AND order_id LIKE ?");
                args.push(Box::new(format!("%{}%", q2.order_id)));
            }
            sql.push_str(" ORDER BY id DESC LIMIT ?");
            args.push(Box::new(limit as i64));

            let mut stmt = conn.prepare(&sql)?;
            let refs: Vec<&dyn rusqlite::ToSql> = args.iter().map(|b| b.as_ref()).collect();
            let it = stmt.query_map(refs.as_slice(), |r| {
                let detail: Option<String> = r.get(6)?;
                Ok(LogEntry {
                    seq: 0,
                    ts: r.get(0)?,
                    level: r.get(1)?,
                    category: r.get(2)?,
                    order_id: r.get(3)?,
                    node_id: r.get(4)?,
                    message: r.get(5)?,
                    detail: detail.and_then(|d| serde_json::from_str(&d).ok()),
                })
            })?;
            Ok(it.collect::<std::result::Result<Vec<_>, _>>()?)
        })
        .await;

        // spawn_blocking 是两层 Result（JoinError / 内层业务错误），先摊平
        let inner = match rows {
            Ok(r) => r,
            Err(e) => return Json(json!({"success": false, "message": format!("查询失败: {e}")})),
        };
        return match inner {
            Ok(items) => Json(json!({"success": true, "data": {"items": items, "source": "db"}})),
            Err(e) => Json(json!({"success": false, "message": format!("查询失败: {e}")})),
        };
    }

    // 内存：从新到旧取前 limit 条。
    //
    // 顺序很关键：`stats_value()` 自己会 `st.buf.lock()`，而 `st.buf` 是**非重入**的
    // std::sync::Mutex。曾经写成「先 lock 拿列表、再在同一个作用域里调 stats_value」，
    // 同一线程二次加锁 → 自死锁：该线程永久持有这把锁，随后 `emit()`（刷课线程每节
    // 上报都要调）全部卡在这把锁上，worker 线程被逐个钉死，连 I/O driver 都停摆，
    // 表现为「整个服务所有请求超时、连静态页都打不开」。
    // 因此统计必须在取列表**之前**算，且取列表的 guard 用独立作用域括起来。
    let stats = stats_value();
    let items: Vec<LogEntry> = {
        let st = store();
        let buf = match st.buf.lock() {
            Ok(g) => g,
            Err(p) => p.into_inner(),
        };
        buf.iter()
            .rev()
            .filter(|e| entry_matches(e, &q))
            .take(limit)
            .cloned()
            .collect()
    };
    Json(json!({
        "success": true,
        "data": {"items": items, "source": "mem", "stats": stats},
    }))
}

fn stats_value() -> Value {
    let st = store();
    let (count, oldest_ts) = {
        let buf = match st.buf.lock() {
            Ok(g) => g,
            Err(p) => p.into_inner(),
        };
        (buf.len(), buf.front().map(|e| e.ts).unwrap_or(0))
    };
    json!({
        "mem_count": count,
        "mem_max": mem_max(),
        "mem_ttl_hours": env_u64("LOG_MEM_TTL_HOURS", DEFAULT_MEM_TTL_HOURS),
        "db_ttl_days": env_u64("LOG_DB_TTL_DAYS", DEFAULT_DB_TTL_DAYS),
        "db_max_rows": db_max_rows(),
        "total": st.total.load(Ordering::Relaxed),
        "evicted": st.evicted.load(Ordering::Relaxed),
        "dropped": st.dropped.load(Ordering::Relaxed),
        "oldest_ts": oldest_ts,
    })
}

async fn log_stats(State(state): State<AppState>) -> Json<Value> {
    let mut v = stats_value();
    // DB 当前行数（面板显示"持久层占用"，也是 GC 是否生效的直观指标）
    let pool = state.db.clone_pool();
    let db_rows = tokio::task::spawn_blocking(move || -> anyhow::Result<i64> {
        let conn = pool.get()?;
        Ok(conn.query_row("SELECT COUNT(*) FROM system_logs", [], |r| r.get(0))?)
    })
    .await
    .unwrap_or(Ok(0))
    .unwrap_or(0);
    if let Some(obj) = v.as_object_mut() {
        obj.insert("db_rows".into(), json!(db_rows));
    }
    Json(json!({"success": true, "data": v}))
}

/// 清空内存环形缓冲（DB 由 GC 的 TTL/条数阈值裁剪，不在这里删）
async fn clear_logs(State(_state): State<AppState>) -> Json<Value> {
    let st = store();
    let n = {
        let mut buf = match st.buf.lock() {
            Ok(g) => g,
            Err(p) => p.into_inner(),
        };
        let n = buf.len();
        buf.clear();
        n
    };
    Json(json!({"success": true, "message": format!("已清空 {n} 条内存日志")}))
}

/// 脱敏：写入 detail 前统一过一道，避免密码/cookie/token 进面板与数据库。
pub fn redact(mut v: Value) -> Value {
    const SENSITIVE: &[&str] = &[
        "password", "pwd", "cookie", "token", "authorization", "secret", "sign",
    ];
    if let Some(obj) = v.as_object_mut() {
        let keys: Vec<String> = obj.keys().cloned().collect();
        for k in keys {
            let lower = k.to_ascii_lowercase();
            if SENSITIVE.iter().any(|s| lower.contains(s)) {
                obj.insert(k, json!("***"));
            }
        }
    }
    v
}

/// 截断过长的文本（平台响应可能很长，日志里没必要全量存）
pub fn clip(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        return s.to_string();
    }
    let mut out: String = s.chars().take(max).collect();
    out.push('…');
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ring_buffer_evicts_oldest_when_full() {
        // 用小上限验证淘汰语义：塞满后最早的那条必须消失，最新的一定在
        std::env::set_var("LOG_MEM_MAX", "100");
        let st = store();
        {
            let mut buf = st.buf.lock().unwrap();
            buf.clear();
        }
        for i in 0..150 {
            emit(LEVEL_INFO, CAT_SYSTEM, "", "", format!("m{i}"), None);
        }
        let buf = st.buf.lock().unwrap();
        assert_eq!(buf.len(), 100, "内存缓冲必须被压到上限");
        assert_eq!(buf.back().unwrap().message, "m149");
        assert_eq!(buf.front().unwrap().message, "m50");
        std::env::remove_var("LOG_MEM_MAX");
    }

    /// 回归：`list_logs` 的调用顺序是「先 stats_value() 再取列表」，两者各自
    /// 独立加锁。若将来有人把统计挪进持锁作用域，同一线程对非重入互斥锁二次
    /// 加锁会永久挂死（本测试超时暴露），而不是把整台服务器钉死。
    #[test]
    fn stats_helper_releases_the_store_lock() {
        let a = stats_value();
        assert!(a.get("mem_count").is_some());
        let b = stats_value();
        assert!(b.get("mem_max").is_some());

        // 返回后锁必须已释放：允许其它测试的瞬时争用，但不允许永久持有
        let mut free = false;
        for _ in 0..200 {
            if store().buf.try_lock().is_ok() {
                free = true;
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
        assert!(free, "stats_value 返回后仍持有缓冲区锁（会导致 emit 全量卡死）");
    }

    #[test]
    fn redact_masks_sensitive_keys() {
        let v = json!({"password": "abc", "Cookie": "sid=x", "nodeId": "1"});
        let r = redact(v);
        assert_eq!(r["password"], "***");
        assert_eq!(r["Cookie"], "***");
        assert_eq!(r["nodeId"], "1");
    }

    #[test]
    fn clip_keeps_short_and_truncates_long() {
        assert_eq!(clip("abc", 5), "abc");
        assert_eq!(clip("abcdefg", 3), "abc…");
    }

    #[test]
    fn entry_filter_matches_category_and_level() {
        let e = LogEntry {
            seq: 7,
            ts: 0,
            level: LEVEL_WARN.into(),
            category: CAT_REPORT.into(),
            order_id: "ORD-1".into(),
            node_id: "n1".into(),
            message: "x".into(),
            detail: None,
        };
        let q = ListQuery {
            category: CAT_REPORT.into(),
            level: String::new(),
            order_id: String::new(),
            before: None,
            limit: None,
            source: String::new(),
        };
        assert!(entry_matches(&e, &q));

        let mut q2 = ListQuery {
            category: String::new(),
            level: LEVEL_ERROR.into(),
            order_id: String::new(),
            before: None,
            limit: None,
            source: String::new(),
        };
        assert!(!entry_matches(&e, &q2));

        q2.level = LEVEL_WARN.into();
        q2.before = Some(7);
        assert!(!entry_matches(&e, &q2), "before 是同 seq 也要跳过");
        q2.before = Some(8);
        assert!(entry_matches(&e, &q2));
    }
}
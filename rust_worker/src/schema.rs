//! SQLite schema 保证 — Rust 已接管建表（Phase 7 后不再依赖 Python create_all）
//!
//! DDL 逐字段翻译自 api/db/models.py（唯一权威定义）：
//!   String(255) -> VARCHAR(255)，Text -> TEXT，Integer -> INTEGER，
//!   Float -> FLOAT，Boolean -> INTEGER（默认 0）。
//! 全部 CREATE TABLE/INDEX IF NOT EXISTS，幂等、不动已有数据。
//!
//! 历史一次性迁移不在此重放（会在正常库上误伤），由旧库自带：
//!   - orders 的 commission_status/inviter_code、audit_logs 的 agent_id 遗留列重建
//!   - orders.paid_processed 从 commission_status 拷贝旧值
//! 保留的幂等迁移：
//!   - ypay_account 缺失列 ALTER TABLE ADD COLUMN（对应 api/database.py init_db）
//!   - ypay_settings 为空时从 vmq_settings 拷贝数据

use anyhow::{Context, Result};
use r2d2::Pool;
use r2d2_sqlite::SqliteConnectionManager;

/// 11 张表的建表语句 + 索引（对应 models.py 的 index=True）
const DDL: &str = r#"
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    nickname VARCHAR(255) DEFAULT '',
    contact VARCHAR(255) DEFAULT '',
    role VARCHAR(255) DEFAULT 'customer',
    created_at VARCHAR(255) NOT NULL,
    last_login VARCHAR(255),
    deleted_at VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(255) PRIMARY KEY,
    out_trade_no VARCHAR(255) DEFAULT '',
    ezfpy_trade_no VARCHAR(255) DEFAULT '',
    payment_channel VARCHAR(255) DEFAULT '',
    payment_time VARCHAR(255),
    paid_processed VARCHAR(255) DEFAULT 'unprocessed',
    user_id VARCHAR(255) DEFAULT '',
    customer_name VARCHAR(255) DEFAULT '',
    customer_contact VARCHAR(255) DEFAULT '',
    username VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    website_id INTEGER NOT NULL,
    task_type VARCHAR(255) DEFAULT 'video',
    course_ids TEXT DEFAULT '[]',
    video_count INTEGER DEFAULT 0,
    exam_count INTEGER DEFAULT 0,
    price FLOAT DEFAULT 0.0,
    notes TEXT DEFAULT '',
    status VARCHAR(255) DEFAULT 'pending',
    paid INTEGER DEFAULT 0,
    task_id VARCHAR(255),
    admin_note TEXT DEFAULT '',
    created_at VARCHAR(255) NOT NULL,
    updated_at VARCHAR(255),
    accepted_at VARCHAR(255),
    started_at VARCHAR(255),
    finished_at VARCHAR(255),
    deleted_at VARCHAR(255),
    speed_mode VARCHAR(255) DEFAULT 'balanced'
);

CREATE TABLE IF NOT EXISTS credentials (
    order_id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(255) DEFAULT '',
    password_enc TEXT DEFAULT '',
    nonce VARCHAR(64) DEFAULT '',
    created_at VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS system_config (
    config_key VARCHAR(255) PRIMARY KEY,
    config_value TEXT DEFAULT '',
    updated_at VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id VARCHAR(255) PRIMARY KEY,
    event_type VARCHAR(255) NOT NULL,
    operator VARCHAR(255) DEFAULT 'system',
    detail TEXT DEFAULT '',
    order_id VARCHAR(255) DEFAULT '',
    user_id VARCHAR(255) DEFAULT '',
    created_at VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS vmq_settings (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ypay_settings (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ypay_account (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type VARCHAR(255) NOT NULL,
    code VARCHAR(255) DEFAULT '',
    name VARCHAR(255) DEFAULT '',
    status INTEGER DEFAULT 0,
    is_status INTEGER DEFAULT 1,
    qr_url TEXT DEFAULT '',
    zfb_pid VARCHAR(255) DEFAULT '',
    alipay_appid VARCHAR(255) DEFAULT '',
    alipay_public_key TEXT DEFAULT '',
    alipay_private_key TEXT DEFAULT '',
    cookie TEXT DEFAULT '',
    wx_guid VARCHAR(255) DEFAULT '',
    qq VARCHAR(255) DEFAULT '',
    cloud_id VARCHAR(255) DEFAULT '',
    qr_type VARCHAR(255) DEFAULT '',
    memo TEXT DEFAULT '',
    remark TEXT DEFAULT '',
    channel_mode INTEGER DEFAULT 1,
    app_public_cert TEXT DEFAULT '',
    alipay_public_cert TEXT DEFAULT '',
    alipay_root_cert TEXT DEFAULT '',
    create_time VARCHAR(255) NOT NULL,
    deleted_at VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS ypay_order (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type VARCHAR(255) NOT NULL,
    account_id INTEGER DEFAULT 0,
    trade_no VARCHAR(255) UNIQUE NOT NULL,
    out_trade_no VARCHAR(255) NOT NULL,
    name VARCHAR(255) DEFAULT '',
    money FLOAT DEFAULT 0.0,
    truemoney FLOAT DEFAULT 0.0,
    qrcode TEXT DEFAULT '',
    h5_qrurl TEXT DEFAULT '',
    status INTEGER DEFAULT 0,
    notify_url TEXT DEFAULT '',
    return_url TEXT DEFAULT '',
    ip VARCHAR(255) DEFAULT '',
    create_time VARCHAR(255) NOT NULL,
    out_time VARCHAR(255) NOT NULL,
    end_time VARCHAR(255),
    deleted_at VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS ypay_tmp_price (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    price FLOAT UNIQUE NOT NULL,
    oid VARCHAR(255) DEFAULT '',
    create_time VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS queue_jobs_school (
    job_id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    website_id INTEGER NOT NULL,
    job_type VARCHAR(255) DEFAULT 'video',
    course_ids TEXT DEFAULT '[]',
    status VARCHAR(255) DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    progress FLOAT DEFAULT 0.0,
    total_steps INTEGER DEFAULT 0,
    completed_steps INTEGER DEFAULT 0,
    current_step_name VARCHAR(255) DEFAULT '',
    error_message TEXT DEFAULT '',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    task_id VARCHAR(255),
    order_id VARCHAR(255),
    result_data TEXT DEFAULT '{}',
    verified INTEGER DEFAULT 0,
    created_at VARCHAR(255) NOT NULL,
    started_at VARCHAR(255),
    finished_at VARCHAR(255),
    deleted_at VARCHAR(255),
    speed_mode VARCHAR(255) DEFAULT 'balanced',
    vid VARCHAR(64) DEFAULT ''
);
CREATE TABLE IF NOT EXISTS queue_jobs_chaoxing (
    job_id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    website_id INTEGER NOT NULL,
    job_type VARCHAR(255) DEFAULT 'video',
    course_ids TEXT DEFAULT '[]',
    status VARCHAR(255) DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    progress FLOAT DEFAULT 0.0,
    total_steps INTEGER DEFAULT 0,
    completed_steps INTEGER DEFAULT 0,
    current_step_name VARCHAR(255) DEFAULT '',
    error_message TEXT DEFAULT '',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    task_id VARCHAR(255),
    order_id VARCHAR(255),
    result_data TEXT DEFAULT '{}',
    verified INTEGER DEFAULT 0,
    created_at VARCHAR(255) NOT NULL,
    started_at VARCHAR(255),
    finished_at VARCHAR(255),
    deleted_at VARCHAR(255),
    speed_mode VARCHAR(255) DEFAULT 'balanced'
);

-- AI 调用用量与费用（每次 DeepSeek 调用一行；后台看板的 AI 成本来源）
CREATE TABLE IF NOT EXISTS ai_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at VARCHAR(255) NOT NULL,
    scene VARCHAR(64) DEFAULT '',
    model VARCHAR(64) DEFAULT '',
    thinking INTEGER DEFAULT 0,
    prompt_tokens INTEGER DEFAULT 0,
    cache_hit_tokens INTEGER DEFAULT 0,
    cache_miss_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    cost_yuan FLOAT DEFAULT 0.0,
    ok INTEGER DEFAULT 1
);

-- 访客身份（邀请与刷课卡的载体）。vid 由服务端下发到 HttpOnly cookie，
-- 不依赖浏览器 localStorage —— 清缓存会丢身份，所以领卡时必须留联系方式。
CREATE TABLE IF NOT EXISTS visitors (
    vid VARCHAR(64) PRIMARY KEY,
    invite_code VARCHAR(32) UNIQUE NOT NULL,
    ref_code VARCHAR(32) DEFAULT '',
    contact VARCHAR(255) DEFAULT '',
    ua VARCHAR(255) DEFAULT '',
    created_at VARCHAR(255) NOT NULL,
    last_seen VARCHAR(255)
);

-- 邀请关系（一个被邀请人只记一次；converted=1 表示已转化为有效邀请）
CREATE TABLE IF NOT EXISTS invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inviter_vid VARCHAR(64) NOT NULL,
    invitee_vid VARCHAR(64) NOT NULL,
    ref_code VARCHAR(32) NOT NULL,
    converted INTEGER DEFAULT 0,
    converted_order_id VARCHAR(64) DEFAULT '',
    created_at VARCHAR(255) NOT NULL,
    UNIQUE(invitee_vid)
);

-- 刷课卡：有效期内免单（可配置有效天数；一张卡可代表不限次或限次）
CREATE TABLE IF NOT EXISTS brush_cards (
    card_id VARCHAR(64) PRIMARY KEY,
    code VARCHAR(32) UNIQUE NOT NULL,
    owner_vid VARCHAR(64) NOT NULL,
    contact VARCHAR(255) DEFAULT '',
    source VARCHAR(32) DEFAULT 'invite',
    granted_at VARCHAR(255) NOT NULL,
    expires_at VARCHAR(255) NOT NULL,
    used_orders INTEGER DEFAULT 0,
    revoked INTEGER DEFAULT 0
);

-- 运行日志（实时日志面板的持久层）。
-- 内存环形缓冲只保留最近若干条，落库是为了重启后仍能回看上报/失败记录；
-- 行数上限由 logs.rs 的 GC 循环按 TTL + 条数双阈值裁剪（见 gc_loop）。
CREATE TABLE IF NOT EXISTS system_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    level VARCHAR(16) NOT NULL,
    category VARCHAR(32) NOT NULL,
    order_id VARCHAR(64) DEFAULT '',
    node_id VARCHAR(64) DEFAULT '',
    message TEXT DEFAULT '',
    detail TEXT
);

-- 教学平台域名（域名监控的落库真源）。同一平台可有多行（主域 + 镜像/备用），
-- 由 (website_id, host) 唯一约束保证不重复，is_primary 保证同平台只有一个主域。
-- website_id 语义同 scan::platform_base_url；只登记 3 个教学平台，其余首页链接不入库。
CREATE TABLE IF NOT EXISTS platform_domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    website_id INTEGER NOT NULL,
    platform_name TEXT NOT NULL,
    host TEXT NOT NULL,
    base_url TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    reachable INTEGER NOT NULL DEFAULT -1,
    is_alias INTEGER NOT NULL DEFAULT 0,
    last_checked_at TEXT,
    updated_at TEXT NOT NULL
);
"#;

/// 索引（统一在建表+补列之后执行，避免老库缺列导致建索引失败）
const INDEX_DDL: &str = r#"
CREATE INDEX IF NOT EXISTS ix_users_deleted_at ON users (deleted_at);
CREATE INDEX IF NOT EXISTS ix_orders_paid_processed ON orders (paid_processed);
CREATE INDEX IF NOT EXISTS ix_orders_user_id ON orders (user_id);
CREATE INDEX IF NOT EXISTS ix_orders_status ON orders (status);
CREATE INDEX IF NOT EXISTS ix_orders_deleted_at ON orders (deleted_at);
CREATE INDEX IF NOT EXISTS ix_audit_logs_event_type ON audit_logs (event_type);
CREATE INDEX IF NOT EXISTS ix_ypay_account_deleted_at ON ypay_account (deleted_at);
CREATE INDEX IF NOT EXISTS ix_ypay_order_out_trade_no ON ypay_order (out_trade_no);
CREATE INDEX IF NOT EXISTS ix_ypay_order_status ON ypay_order (status);
CREATE INDEX IF NOT EXISTS ix_ypay_order_deleted_at ON ypay_order (deleted_at);
CREATE INDEX IF NOT EXISTS ix_ypay_tmp_price_price ON ypay_tmp_price (price);
CREATE INDEX IF NOT EXISTS ix_queue_jobs_school_username ON queue_jobs_school (username);
CREATE INDEX IF NOT EXISTS ix_queue_jobs_school_status ON queue_jobs_school (status);
CREATE INDEX IF NOT EXISTS ix_queue_jobs_school_deleted_at ON queue_jobs_school (deleted_at);
CREATE INDEX IF NOT EXISTS ix_queue_jobs_chaoxing_username ON queue_jobs_chaoxing (username);
CREATE INDEX IF NOT EXISTS ix_queue_jobs_chaoxing_status ON queue_jobs_chaoxing (status);
CREATE INDEX IF NOT EXISTS ix_queue_jobs_chaoxing_deleted_at ON queue_jobs_chaoxing (deleted_at);
CREATE INDEX IF NOT EXISTS ix_ai_usage_created_at ON ai_usage (created_at);
CREATE INDEX IF NOT EXISTS ix_invites_inviter ON invites (inviter_vid);
CREATE INDEX IF NOT EXISTS ix_invites_ref ON invites (ref_code);
CREATE INDEX IF NOT EXISTS ix_brush_cards_owner ON brush_cards (owner_vid);
CREATE INDEX IF NOT EXISTS ix_system_logs_ts ON system_logs (ts);
CREATE INDEX IF NOT EXISTS ix_system_logs_category ON system_logs (category);
CREATE INDEX IF NOT EXISTS ix_system_logs_order ON system_logs (order_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_pd_site_host ON platform_domains (website_id, host);
CREATE INDEX IF NOT EXISTS ix_pd_host ON platform_domains (host);
"#;

/// ypay_account 老库可能缺失的列（对应 api/database.py 的 _add_columns_if_missing）
const YPAY_ACCOUNT_EXTRA_COLUMNS: &[(&str, &str)] = &[
    ("alipay_appid", "VARCHAR(255) DEFAULT ''"),
    ("alipay_public_key", "TEXT"),
    ("alipay_private_key", "TEXT"),
    ("cookie", "TEXT"),
    ("wx_guid", "VARCHAR(255) DEFAULT ''"),
    ("qq", "VARCHAR(255) DEFAULT ''"),
    ("cloud_id", "VARCHAR(255) DEFAULT ''"),
    ("qr_type", "VARCHAR(255) DEFAULT ''"),
    ("memo", "TEXT"),
    ("remark", "TEXT"),
    ("channel_mode", "INTEGER DEFAULT 1"),
    ("app_public_cert", "TEXT"),
    ("alipay_public_cert", "TEXT"),
    ("alipay_root_cert", "TEXT"),
];

/// 老库（DDL 早于该列）缺失的列：orders / queue_jobs_school 的刷课档位
const SPEED_MODE_COLUMN: &[(&str, &str)] = &[("speed_mode", "VARCHAR(255) DEFAULT 'balanced'")];

/// 订单上的访客标识（营销归因：付款成功后据此把邀请记为有效）
const ORDER_VISITOR_COLUMN: &[(&str, &str)] = &[("vid", "VARCHAR(64) DEFAULT ''")];

/// 队列任务所属通道：付费（答题/考试）与免费（刷视频）。
///
/// 与 `priority` 正交：`lane` 决定占哪条并发额度，`priority` 只决定池内先后。
/// 老库缺列时默认 'paid' —— 历史任务都是付费单，落付费池即当前行为。
const LANE_COLUMN: &[(&str, &str)] = &[("lane", "VARCHAR(16) DEFAULT 'paid'")];

/// 幂等补列：表里缺失的列用 ALTER TABLE ADD COLUMN 补上（已存在的跳过）
fn add_missing_columns(
    conn: &rusqlite::Connection,
    table: &str,
    cols: &[(&str, &str)],
) -> Result<()> {
    let existing: std::collections::HashSet<String> = {
        let mut stmt = conn.prepare(&format!("PRAGMA table_info({table})"))?;
        let rows = stmt.query_map([], |r| r.get::<_, String>(1))?;
        rows.collect::<std::result::Result<_, _>>()?
    };
    for (col, def) in cols {
        if !existing.contains(*col) {
            conn.execute_batch(&format!("ALTER TABLE {table} ADD COLUMN {col} {def}"))
                .with_context(|| format!("迁移失败: {table} 添加列 {col}"))?;
        }
    }
    Ok(())
}

/// 保证 schema 存在：建表 + 幂等轻量迁移。每次启动调用，可重复执行。
pub fn ensure_schema(pool: &Pool<SqliteConnectionManager>) -> Result<()> {
    let conn = pool.get().context("获取连接失败")?;
    conn.execute_batch(DDL).context("建表失败")?;

    // 缺失列补齐（老库兼容，幂等）
    add_missing_columns(&conn, "ypay_account", YPAY_ACCOUNT_EXTRA_COLUMNS)?;
    add_missing_columns(&conn, "orders", SPEED_MODE_COLUMN)?;
    add_missing_columns(&conn, "queue_jobs_school", SPEED_MODE_COLUMN)?;
    add_missing_columns(&conn, "queue_jobs_chaoxing", SPEED_MODE_COLUMN)?;
    add_missing_columns(&conn, "orders", ORDER_VISITOR_COLUMN)?;
    add_missing_columns(&conn, "queue_jobs_school", LANE_COLUMN)?;
    add_missing_columns(&conn, "queue_jobs_chaoxing", LANE_COLUMN)?;

    conn.execute_batch(INDEX_DDL).context("建索引失败")?;

    // 域名监控首次装配：写入 3 个学校平台的静态默认值
    // （3 个平台由用户 2026-10-01 确认；首页的 suwankj 链接已废弃、不登记）
    // 守卫按 website_id 逐条判断：整表判空会让第一条插入后把其余两条一起跳过
    conn.execute_batch(
        "INSERT INTO platform_domains
            (website_id, platform_name, host, base_url, is_primary, reachable, is_alias, updated_at)
         SELECT 1, '在线课程测评考试平台', 'cdcass.taiskeji.com', 'https://cdcass.taiskeji.com', 1, -1, 0,
                strftime('%Y-%m-%dT%H:%M:%S', 'now', '+8 hours')
         WHERE NOT EXISTS (SELECT 1 FROM platform_domains WHERE website_id = 1);
         INSERT INTO platform_domains
            (website_id, platform_name, host, base_url, is_primary, reachable, is_alias, updated_at)
         SELECT 2, '劳动课程测评考试平台', 'cdcas.duxingkej.com', 'https://cdcas.duxingkej.com', 1, -1, 0,
                strftime('%Y-%m-%dT%H:%M:%S', 'now', '+8 hours')
         WHERE NOT EXISTS (SELECT 1 FROM platform_domains WHERE website_id = 2);
         INSERT INTO platform_domains
            (website_id, platform_name, host, base_url, is_primary, reachable, is_alias, updated_at)
         SELECT 3, '公益课程平台', 'cdcas.chaoxiankeji.com', 'https://cdcas.chaoxiankeji.com', 1, -1, 0,
                strftime('%Y-%m-%dT%H:%M:%S', 'now', '+8 hours')
         WHERE NOT EXISTS (SELECT 1 FROM platform_domains WHERE website_id = 3);",
    )
    .context("初始化域名监控默认数据失败")?;

    // ypay_settings 为空时从 vmq_settings 迁移（对应 Python init_db 末尾逻辑，幂等）
    conn.execute_batch(
        "INSERT INTO ypay_settings (key, value)
         SELECT key, value FROM vmq_settings
         WHERE NOT EXISTS (SELECT 1 FROM ypay_settings)",
    )
    .context("迁移失败: vmq_settings -> ypay_settings")?;

    // 历史加密凭据 → 明文回迁（用户规则：密码只存明文；幂等，可重跑）
    match crate::crypto::restore_plaintext_credentials(&conn) {
        Ok(0) => {}
        Ok(n) => tracing::info!(restored = n, "历史密文密码已回迁为明文"),
        Err(e) => tracing::warn!(error = %e, "历史密文回迁失败（保留密文行，下次启动重试）"),
    }

    Ok(())
}

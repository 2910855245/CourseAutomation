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
    deleted_at VARCHAR(255)
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
    deleted_at VARCHAR(255)
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
    deleted_at VARCHAR(255)
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

/// 保证 schema 存在：建表 + 幂等轻量迁移。每次启动调用，可重复执行。
pub fn ensure_schema(pool: &Pool<SqliteConnectionManager>) -> Result<()> {
    let conn = pool.get().context("获取连接失败")?;
    conn.execute_batch(DDL).context("建表失败")?;

    // ypay_account 缺失列补齐（老库兼容，幂等）
    let existing: std::collections::HashSet<String> = {
        let mut stmt = conn.prepare("PRAGMA table_info(ypay_account)")?;
        let rows = stmt.query_map([], |r| r.get::<_, String>(1))?;
        rows.collect::<std::result::Result<_, _>>()?
    };
    for (col, def) in YPAY_ACCOUNT_EXTRA_COLUMNS {
        if !existing.contains(*col) {
            conn.execute_batch(&format!("ALTER TABLE ypay_account ADD COLUMN {col} {def}"))
                .with_context(|| format!("迁移失败: ypay_account 添加列 {col}"))?;
        }
    }

    conn.execute_batch(INDEX_DDL).context("建索引失败")?;

    // ypay_settings 为空时从 vmq_settings 迁移（对应 Python init_db 末尾逻辑，幂等）
    conn.execute_batch(
        "INSERT INTO ypay_settings (key, value)
         SELECT key, value FROM vmq_settings
         WHERE NOT EXISTS (SELECT 1 FROM ypay_settings)",
    )
    .context("迁移失败: vmq_settings -> ypay_settings")?;

    // orders.password 明文 → 加密凭据表（幂等，仅首次有效）
    match crate::crypto::migrate_plaintext_credentials(&conn) {
        Ok(0) => {}
        Ok(n) => tracing::info!(migrated = n, "明文密码已迁移至加密凭据表"),
        Err(e) => tracing::warn!(error = %e, "明文凭据迁移失败（保留原列，下次启动重试）"),
    }

    Ok(())
}

//! SQLite 访问层 — 与 Python 侧共享同一 data/*.db（WAL 多进程安全）
//!
//! rusqlite 直连 SQL（无 ORM），r2d2 连接池 + spawn_blocking 执行。
//! 与 Python api/database.py 的建表/迁移职责分离：Rust 只读+写业务数据，
//! 表结构由 Python 侧的 create_all 保证（迁移期双跑，Phase 7 后 Rust 接管建表）。

use anyhow::{Context, Result};
use r2d2::Pool;
use r2d2_sqlite::SqliteConnectionManager;
use serde_json::{json, Value};

#[derive(Clone)]
pub struct Db {
    pool: Pool<SqliteConnectionManager>,
}

impl Db {
    /// 打开（或创建）SQLite 数据库：WAL + busy_timeout，连接池上限 8
    pub fn open(path: &str) -> Result<Self> {
        if let Some(dir) = std::path::Path::new(path).parent() {
            if !dir.as_os_str().is_empty() && !dir.exists() {
                std::fs::create_dir_all(dir)
                    .with_context(|| format!("创建数据目录失败: {}", dir.display()))?;
            }
        }
        let manager = SqliteConnectionManager::file(path)
            .with_init(|c| {
                c.execute_batch(
                    "PRAGMA journal_mode=WAL;
                     PRAGMA synchronous=NORMAL;
                     PRAGMA busy_timeout=5000;
                     PRAGMA foreign_keys=ON;",
                )
            });
        let pool = Pool::builder()
            .max_size(8)
            .build(manager)
            .with_context(|| format!("打开数据库失败: {path}"))?;
        // 连接预热
        pool.get().context("数据库连接预热失败")?;
        Ok(Db { pool })
    }

    /// 查询订单统计（与 Python db.get_stats 对齐）
    pub async fn order_stats(&self) -> Result<Value> {
        let pool = self.pool.clone();
        tokio::task::spawn_blocking(move || -> Result<Value> {
            let conn = pool.get().context("获取连接失败")?;
            let mut stmt = conn.prepare(
                "SELECT status, COUNT(*), COALESCE(SUM(price), 0)
                 FROM orders GROUP BY status",
            )?;
            let rows = stmt.query_map([], |r| {
                Ok((
                    r.get::<_, String>(0)?,
                    r.get::<_, i64>(1)?,
                    r.get::<_, f64>(2)?,
                ))
            })?;
            let mut by_status = serde_json::Map::new();
            let mut total_orders = 0i64;
            let mut total_revenue = 0.0f64;
            for row in rows {
                let (status, count, revenue) = row?;
                total_orders += count;
                total_revenue += revenue;
                by_status.insert(status, json!({"count": count, "revenue": revenue}));
            }
            Ok(json!({
                "total_orders": total_orders,
                "total_revenue": total_revenue,
                "by_status": by_status,
            }))
        })
        .await
        .context("spawn_blocking 失败")?
    }

    /// 通用表计数（队列统计用）
    pub async fn table_count(&self, table: &'static str) -> Result<i64> {
        let pool = self.pool.clone();
        tokio::task::spawn_blocking(move || -> Result<i64> {
            let conn = pool.get().context("获取连接失败")?;
            // 表名来自代码常量，无注入风险
            let sql = format!("SELECT COUNT(*) FROM {}", table);
            let count: i64 = conn.query_row(&sql, [], |r| r.get(0))?;
            Ok(count)
        })
        .await
        .context("spawn_blocking 失败")?
    }
}

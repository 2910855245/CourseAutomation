//! 任务队列与调度器（Rust 版）— 取代 Python task_queue + job_executor + task_runner
//!
//! 与 Python 共享 SQLite 队列表（queue_jobs_school / queue_jobs_chaoxing），
//! 原子认领（pending/retrying → running）+ tokio task 执行 + status.json 协议 +
//! 完成/失败/重试/等待语义对齐 Python。
//!
//! 灰度开关 RUST_QUEUE_ENABLED：默认关闭，Python 调度器继续工作；
//! 开启后仅接管学校任务（学习通登录待 wreq 落地后再接管）。

use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::Result;
use serde::Deserialize;
use serde_json::json;

use crate::db::Db;
use crate::scan::ScanTaskInput;
use crate::AppState;

const SCHOOL_TABLE: &str = "queue_jobs_school";

#[derive(Debug, Clone, Deserialize)]
pub struct QueueJob {
    pub job_id: String,
    pub username: String,
    pub password: String,
    pub website_id: i64,
    #[serde(default)]
    pub job_type: String,
    #[serde(default)]
    pub course_ids: String, // JSON 数组字符串
    #[serde(default)]
    pub order_id: String,
    #[serde(default)]
    pub max_retries: i64,
    #[serde(default)]
    pub retry_count: i64,
}

pub(crate) fn now_str() -> String {
    SystemTime::now().duration_since(UNIX_EPOCH)
        .map(|d| chrono_lite(d.as_secs()))
        .unwrap_or_default()
}

/// 简易 ISO 时间（避免引入 chrono 依赖）
fn chrono_lite(secs: u64) -> String {
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
    let sod = secs % 86400;
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}",
        y, m + 1, rem + 1, sod / 3600, (sod % 3600) / 60, sod % 60
    )
}

/// 原子认领下一个待执行任务
async fn claim_next_job(db: &Db) -> Result<Option<QueueJob>> {
    let pool_guard = db.raw_pool().clone();
    let row = tokio::task::spawn_blocking(move || -> Result<Option<QueueJob>> {
        let mut conn = pool_guard.get()?;
        let tx = conn.transaction()?;
        let job = tx.query_row(
            &format!(
                "SELECT job_id, username, password, website_id, job_type, course_ids, order_id, max_retries, retry_count
                 FROM {SCHOOL_TABLE}
                 WHERE status IN ('pending','retrying')
                 ORDER BY priority ASC, created_at ASC LIMIT 1"
            ),
            [],
            |r| {
                Ok(QueueJob {
                    job_id: r.get(0)?,
                    username: r.get(1)?,
                    password: r.get(2)?,
                    website_id: r.get(3)?,
                    job_type: r.get::<_, String>(4)?,
                    course_ids: r.get::<_, String>(5)?,
                    order_id: r.get::<_, Option<String>>(6)?.unwrap_or_default(),
                    max_retries: r.get::<_, i64>(7)?,
                    retry_count: r.get::<_, i64>(8)?,
                })
            },
        );
        match job {
            Ok(job) => {
                tx.execute(
                    &format!(
                        "UPDATE {SCHOOL_TABLE} SET status='running', started_at=?1 WHERE job_id=?2"
                    ),
                    rusqlite::params![now_str(), job.job_id],
                )?;
                tx.commit()?;
                Ok(Some(job))
            }
            Err(rusqlite::Error::QueryReturnedNoRows) => {
                tx.rollback()?;
                Ok(None)
            }
            Err(e) => {
                tx.rollback()?;
                Err(e.into())
            }
        }
    })
    .await??;
    Ok(row)
}

async fn update_job(db: &Db, job_id: &str, fields: &[(&str, String)]) -> Result<()> {
    if fields.is_empty() {
        return Ok(());
    }
    let pool_guard = db.raw_pool().clone();
    let job_id = job_id.to_string();
    let sets: Vec<String> = fields.iter().enumerate()
        .map(|(i, (k, _))| format!("{k}=?{}", i + 1))
        .collect();
    let values: Vec<String> = fields.iter().map(|(_, v)| v.clone()).collect();
    let n = fields.len();
    tokio::task::spawn_blocking(move || -> Result<()> {
        let conn = pool_guard.get()?;
        let sql = format!("UPDATE {SCHOOL_TABLE} SET {} WHERE job_id=?{}",
                          sets.join(", "), n + 1);
        conn.execute(&sql, rusqlite::params_from_iter(
            values.iter().map(|v| v.as_str()).chain(std::iter::once(job_id.as_str())),
        ))?;
        Ok(())
    })
    .await??;
    Ok(())
}

/// 执行单个学校任务：登录 → 扫描+刷课 → 状态更新（status.json 协议）
async fn execute_school_job(state: &AppState, job: &QueueJob) {
    let base_url = crate::scan::platform_base_url(job.website_id);
    let tmpdir = std::env::temp_dir().join(format!("task_{}", job.job_id));
    let _ = tokio::fs::create_dir_all(&tmpdir).await;
    let status_file = tmpdir.join("status.json").to_string_lossy().to_string();

    // 会话复用：缓存/落盘 cookie 有效则跳过登录（避免频繁登录触发平台风控）
    let session = match crate::session::get_session(&base_url, &job.username, &job.password).await {
        Ok(s) => s,
        Err(e) => {
            let _ = update_job(&state.db, &job.job_id,
                               &[("status", "failed".into()), ("error_message", format!("登录失败: {e}"))]).await;
            return;
        }
    };

    // course_ids 解析（JSON 数组或 "cid:clid" 字符串）
    let course_ids: Vec<String> = serde_json::from_str(&job.course_ids)
        .unwrap_or_else(|_| job.course_ids.split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect());

    let task = ScanTaskInput {
        order_id: if job.order_id.is_empty() { job.job_id.clone() } else { job.order_id.clone() },
        username: job.username.clone(),
        password: job.password.clone(),
        base_url: base_url.clone(),
        cookie_str: session.cookie_str,
        course_ids,
        status_file: status_file.clone(),
        push_ws: false,
    };

    let result = crate::scan::run_scan_and_study(&task, "", "").await;
    match result {
        Ok(()) => {
            let _ = update_job(&state.db, &job.job_id,
                               &[("status", "completed".into()), ("progress", "100".into()),
                                 ("current_step_name", "刷课完成".into()),
                                 ("finished_at", now_str())]).await;
            tracing::info!(job_id = %job.job_id, "任务完成");
        }
        Err(e) => {
            // 重试语义（对齐 Python：retry_count < max_retries → retrying，否则 failed）
            if job.retry_count < job.max_retries.max(0) {
                let _ = update_job(&state.db, &job.job_id,
                                   &[("status", "retrying".into()),
                                     ("error_message", e.to_string()),
                                     ("retry_count", (job.retry_count + 1).to_string())]).await;
            } else {
                let _ = update_job(&state.db, &job.job_id,
                                   &[("status", "failed".into()),
                                     ("error_message", e.to_string()),
                                     ("finished_at", now_str())]).await;
            }
            tracing::warn!(job_id = %job.job_id, error = %e, "任务失败");
        }
    }
    let _ = tokio::fs::remove_dir_all(&tmpdir).await;
}

/// 调度器主循环（每队列一个 tokio task）
///
/// 并发上限与暂停状态都从 system_config 动态读取（管理端可热更新）：
///   - `queue_max_workers`：同时执行的任务数上限
///   - `queue_paused` / `queue_paused_school` / `queue_paused_chaoxing`：暂停开关
pub async fn dispatcher_loop(state: Arc<AppState>) {
    tracing::info!("Rust 队列调度器启动（学校任务）");
    let active = Arc::new(std::sync::atomic::AtomicUsize::new(0));
    // 配置缓存：(上次刷新时间, 并发上限, 是否暂停)，避免每轮都查库
    let mut cfg_cache: (std::time::Instant, usize, bool) =
        (std::time::Instant::now(), default_max_workers(), false);
    loop {
        if !std::env::var("RUST_QUEUE_ENABLED").map(|v| v == "true").unwrap_or(false) {
            tokio::time::sleep(std::time::Duration::from_secs(10)).await;
            continue;
        }
        if cfg_cache.0.elapsed() > std::time::Duration::from_secs(5) {
            let (max, paused) = read_runtime_config(&state.db).await;
            cfg_cache = (std::time::Instant::now(), max, paused);
        }
        if cfg_cache.2 {
            tokio::time::sleep(std::time::Duration::from_secs(2)).await;
            continue;
        }
        if active.load(std::sync::atomic::Ordering::Relaxed) >= cfg_cache.1 {
            tokio::time::sleep(std::time::Duration::from_secs(1)).await;
            continue;
        }
        match claim_next_job(&state.db).await {
            Ok(Some(job)) => {
                let state2 = state.clone();
                let active2 = active.clone();
                active.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                tokio::spawn(async move {
                    execute_school_job(&state2, &job).await;
                    active2.fetch_sub(1, std::sync::atomic::Ordering::Relaxed);
                });
            }
            Ok(None) => tokio::time::sleep(std::time::Duration::from_secs(2)).await,
            Err(e) => {
                tracing::error!(error = %e, "认领任务失败");
                tokio::time::sleep(std::time::Duration::from_secs(5)).await;
            }
        }
    }
}

/// 默认并发上限：环境变量 > CPU 核数-1（夹在 1..=8）
fn default_max_workers() -> usize {
    std::env::var("RUST_QUEUE_MAX_WORKERS").ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or_else(|| std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4).saturating_sub(1).clamp(1, 8))
}

/// 读取运行期配置（并发上限 + 暂停），失败时退回默认值
async fn read_runtime_config(db: &Db) -> (usize, bool) {
    let max = config_get(db, "queue_max_workers").await
        .and_then(|v| v.parse::<usize>().ok())
        .filter(|n| *n > 0)
        .unwrap_or_else(default_max_workers);
    let paused = config_get(db, "queue_paused").await.map(|v| v == "1").unwrap_or(false)
        || config_get(db, "queue_paused_school").await.map(|v| v == "1").unwrap_or(false);
    (max, paused)
}

/// 读系统配置（键不存在返回 None）
pub async fn config_get(db: &Db, key: &str) -> Option<String> {
    let pool = db.clone_pool();
    let key = key.to_string();
    tokio::task::spawn_blocking(move || -> Option<String> {
        let conn = pool.get().ok()?;
        conn.query_row(
            "SELECT config_value FROM system_config WHERE config_key=?1",
            rusqlite::params![key],
            |r| r.get::<_, String>(0),
        ).ok()
    })
    .await
    .ok()
    .flatten()
}

/// 写系统配置（upsert）
pub async fn config_set(db: &Db, key: &str, value: &str) -> Result<()> {
    let pool = db.clone_pool();
    let key = key.to_string();
    let value = value.to_string();
    tokio::task::spawn_blocking(move || -> Result<()> {
        let conn = pool.get()?;
        conn.execute(
            "INSERT INTO system_config (config_key, config_value, updated_at)
             VALUES (?1, ?2, ?3)
             ON CONFLICT(config_key) DO UPDATE SET config_value=excluded.config_value,
                                                  updated_at=excluded.updated_at",
            rusqlite::params![key, value, now_str()],
        )?;
        Ok(())
    })
    .await??;
    Ok(())
}

/// 提交任务（对齐 Python queue.submit_job 的核心字段）
pub async fn submit_job(db: &Db, job: serde_json::Value) -> Result<serde_json::Value> {
    let job_id = format!("JOB-{:08x}", SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos() as u64 & 0xffffffff);
    let created = now_str();
    let pool_guard = db.raw_pool().clone();
    let job_id2 = job_id.clone();
    tokio::task::spawn_blocking(move || -> Result<()> {
        let conn = pool_guard.get()?;
        conn.execute(
            &format!(
                "INSERT INTO {SCHOOL_TABLE}
                 (job_id, username, password, website_id, job_type, course_ids, status, priority,
                  progress, total_steps, completed_steps, current_step_name, error_message,
                  retry_count, max_retries, task_id, order_id, result_data, verified,
                  created_at, started_at, finished_at, deleted_at)
                 VALUES (?1,?2,?3,?4,?5,?6,'pending',0,0,0,0,'','',0,3,NULL,?7,'{{}}',0,?8,NULL,NULL,NULL)"
            ),
            rusqlite::params![
                job_id2,
                job["username"].as_str().unwrap_or(""),
                job["password"].as_str().unwrap_or(""),
                job["website_id"].as_i64().unwrap_or(1),
                job["job_type"].as_str().unwrap_or("video"),
                job["course_ids"].as_str().unwrap_or("[]"),
                job["order_id"].as_str().unwrap_or(""),
                created,
            ],
        )?;
        Ok(())
    })
    .await??;
    Ok(json!({"ok": true, "job_id": job_id}))
}

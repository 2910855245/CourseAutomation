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
use crate::login::login_school;
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

fn now_str() -> String {
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
    let ocr_url = std::env::var("OCR_SERVICE_URL").unwrap_or_default();
    let tmpdir = std::env::temp_dir().join(format!("task_{}", job.job_id));
    let _ = tokio::fs::create_dir_all(&tmpdir).await;
    let status_file = tmpdir.join("status.json").to_string_lossy().to_string();

    // 登录
    let session = match login_school(&base_url, &job.username, &job.password, &ocr_url).await {
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
        ocr_url: format!("{}/api/internal/ocr", std::env::var("SITE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into())),
        relogin_url: format!("{}/api/internal/relogin", std::env::var("SITE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into())),
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
pub async fn dispatcher_loop(state: Arc<AppState>) {
    tracing::info!("Rust 队列调度器启动（学校任务）");
    let semaphore = Arc::new(tokio::sync::Semaphore::new(
        std::env::var("RUST_QUEUE_MAX_WORKERS").ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4).min(8)),
    ));
    loop {
        if !std::env::var("RUST_QUEUE_ENABLED").map(|v| v == "true").unwrap_or(false) {
            tokio::time::sleep(std::time::Duration::from_secs(10)).await;
            continue;
        }
        match claim_next_job(&state.db).await {
            Ok(Some(job)) => {
                let state2 = state.clone();
                let sem = semaphore.clone();
                tokio::spawn(async move {
                    let _permit = sem.acquire().await;
                    execute_school_job(&state2, &job).await;
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

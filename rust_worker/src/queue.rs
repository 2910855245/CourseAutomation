//! 任务队列与调度器（Rust 版）— 取代 Python task_queue + job_executor + task_runner
//!
//! 原子认领（pending/retrying → running）+ tokio task 执行 + status.json 协议 +
//! 完成/失败/重试语义。
//!
//! 开关 RUST_QUEUE_ENABLED：**默认开启**。历史上它是 Python→Rust 迁移期的灰度
//! 开关（默认关闭，让 Python 调度器继续干活）。Python 已完全移除，这个默认值
//! 就成了静默失灵：调度器每 10s 空转一圈，任何入队任务都不会被执行，而管理端
//! 的队列监控还显示"运行中"。现在只保留显式 `false` 作为应急停用手段
//! （常规暂停请用管理端的 queue_paused，它不影响进程且可热恢复）。

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::Result;
use serde::Deserialize;
use serde_json::json;

use crate::db::Db;
use crate::progress;
use crate::scan::ScanTaskInput;
use crate::AppState;

/// 队列种类：学校平台 / 学习通。两者的队列表、暂停开关、执行器不同，
/// 但认领、重试、终态回写、双通道（付费/免费）语义完全一致 —— 共用一套实现，
/// 差异全部收敛到本枚举。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum QueueKind {
    School,
    Chaoxing,
}

impl QueueKind {
    pub fn table(self) -> &'static str {
        match self {
            QueueKind::School => "queue_jobs_school",
            QueueKind::Chaoxing => "queue_jobs_chaoxing",
        }
    }
    /// 分队列暂停开关（全局 queue_paused 对所有队列生效）
    fn paused_key(self) -> &'static str {
        match self {
            QueueKind::School => "queue_paused_school",
            QueueKind::Chaoxing => "queue_paused_chaoxing",
        }
    }
    fn name(self) -> &'static str {
        match self {
            QueueKind::School => "school",
            QueueKind::Chaoxing => "chaoxing",
        }
    }
}

/// 队列通道。免费（刷视频）与付费（答题/考试）各有**独立**的并发额度，
/// 互不挤占：付费单永远不会排在免费积压后面，免费人流也吃不掉付费槽位。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Lane {
    Paid,
    Free,
}

impl Lane {
    pub fn as_str(self) -> &'static str {
        match self {
            Lane::Paid => "paid",
            Lane::Free => "free",
        }
    }
}

/// 由订单的 `paid_processed` 派生 (通道, 池内优先级)。
///
/// 这是**唯一判定表**，入队的两条路径（支付成功 / 管理员补入队）都必须走它，
/// 否则管理员手动入队会把免费单扔进付费池抢额度。
///
/// 免费的三种来源里只有「持卡」享受插队（priority 1），其余普通免费单为 2。
pub fn lane_and_priority(paid_processed: &str) -> (Lane, i64) {
    let p = paid_processed.trim();
    if let Some(reason) = p.strip_prefix("free:") {
        let priority = if reason == "card" { 1 } else { 2 };
        (Lane::Free, priority)
    } else {
        (Lane::Paid, 0)
    }
}

/// 四条通道的在跑计数：每个队列种类 ×（付费/免费）各一个。
/// 分种类计数是管理端队列监控能分别显示 school / chaoxing 在跑数的前提
/// （此前所有在跑数都记在学校头上，学习通恒显 0）。
/// 学校·付费
static ACTIVE_WORKERS_PAID: AtomicUsize = AtomicUsize::new(0);
/// 学校·免费
static ACTIVE_WORKERS_FREE: AtomicUsize = AtomicUsize::new(0);
/// 学习通·付费
static ACTIVE_WORKERS_CX_PAID: AtomicUsize = AtomicUsize::new(0);
/// 学习通·免费
static ACTIVE_WORKERS_CX_FREE: AtomicUsize = AtomicUsize::new(0);

/// worker 槽位的 RAII 守卫。
///
/// 必须用 Drop 而不是在 `execute_school_job().await` 之后手写 `fetch_sub`：
/// 刷课链路上任何一个 panic（数组越界、第三方库、unwrap）都会让 tokio 直接
/// 终止那个 task，`fetch_sub` 那行永远执行不到。结果是**每 panic 一次就永久
/// 少一个并发槽位**，累积到上限之后调度器恒判"已满"，新任务永不被认领 ——
/// 服务静默停摆，而队列监控还显示"运行中"。
/// Drop 在 panic 展开时同样会执行，所以槽位一定会被还回来。
///
/// 槽位记在自己所属通道的计数器上：两条通道额度独立，归还时也必须还对池子。
struct WorkerSlot(QueueKind, Lane);

impl WorkerSlot {
    fn acquire(kind: QueueKind, lane: Lane) -> Self {
        counter(kind, lane).fetch_add(1, Ordering::Relaxed);
        WorkerSlot(kind, lane)
    }
}

impl Drop for WorkerSlot {
    fn drop(&mut self) {
        counter(self.0, self.1).fetch_sub(1, Ordering::Relaxed);
    }
}

fn counter(kind: QueueKind, lane: Lane) -> &'static AtomicUsize {
    match (kind, lane) {
        (QueueKind::School, Lane::Paid) => &ACTIVE_WORKERS_PAID,
        (QueueKind::School, Lane::Free) => &ACTIVE_WORKERS_FREE,
        (QueueKind::Chaoxing, Lane::Paid) => &ACTIVE_WORKERS_CX_PAID,
        (QueueKind::Chaoxing, Lane::Free) => &ACTIVE_WORKERS_CX_FREE,
    }
}

/// 指定队列种类、指定通道当前在跑的 worker 数
pub fn active_workers_in_kind(kind: QueueKind, lane: Lane) -> usize {
    counter(kind, lane).load(Ordering::Relaxed)
}

/// 学校队列指定通道当前在跑的 worker 数（既有调用点语义不变）
pub fn active_workers_in(lane: Lane) -> usize {
    active_workers_in_kind(QueueKind::School, lane)
}

/// 全部队列所有通道的在跑总数（健康检查/看板用）
pub fn active_workers() -> usize {
    active_workers_in_kind(QueueKind::School, Lane::Paid)
        + active_workers_in_kind(QueueKind::School, Lane::Free)
        + active_workers_in_kind(QueueKind::Chaoxing, Lane::Paid)
        + active_workers_in_kind(QueueKind::Chaoxing, Lane::Free)
}

/// 并发上限的硬边界。Rust 侧任务全为 I/O 等待（视频墙钟 + 平台请求），
/// 单任务内存开销极小，因此上限远高于 Python 版；超过 64 之后真正的瓶颈
/// 已经不是 worker 数而是平台出站闸门（见 platform_client::wait_rate_limit）。
const MAX_WORKERS_CEILING: usize = 64;

/// 免费通道默认并发数（管理端可热改）
const DEFAULT_FREE_WORKERS: usize = 8;
/// 免费通道并发上限的硬边界，与付费通道同量级：免费单里只有视频，且被钉在
/// 保守档（串行），真正贴着平台风险的是进程内会话总数，由 study::GLOBAL_STUDY_SESSIONS
/// 那道闸统一兜住 —— 免费池开大只会先撞上它，不会绕过它。
const MAX_FREE_WORKERS_CEILING: usize = 64;

/// 免费通道并发数的配置键（后台可热改）
pub const CFG_FREE_MAX_WORKERS: &str = "free_max_workers";

/// 调度器每轮尝试通道的顺序：**付费优先**。
///
/// 这是"付费免排队"这条商业承诺的实现点，抽成常量并被回归测试钉住：
/// 顺序一旦反过来，付费单就会排在免费积压后面（免费单动辄几小时，
/// 等于付费用户白花钱排队）。两条通道额度独立，所以"优先"不会饿死免费。
const LANE_ATTEMPT_ORDER: [Lane; 2] = [Lane::Paid, Lane::Free];

/// 调度器是否启用（默认启用；仅显式 RUST_QUEUE_ENABLED=false 才停用）
fn dispatcher_enabled() -> bool {
    std::env::var("RUST_QUEUE_ENABLED")
        .map(|v| !matches!(v.trim().to_lowercase().as_str(), "false" | "0" | "no" | "off"))
        .unwrap_or(true)
}

/// 供管理端队列监控读取（暴露调度器真实开关状态，避免监控显示"运行中"而实际空转）
pub fn dispatcher_enabled_public() -> bool {
    dispatcher_enabled()
}

/// 是否应重试（抽成纯函数以便单测）
fn should_retry(retry_count: i64, max_retries: i64) -> bool {
    retry_count < max_retries.max(0)
}

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
    /// 刷课节奏档位（turbo/balanced/gentle；老任务为空 → 均衡）
    #[serde(default)]
    pub speed_mode: String,
}

/// 本地时区偏移（北京时间 UTC+8）。
///
/// 库里的时间戳统一由 [`now_str`] 写入，与看板的"今日/本周"口径必须同源；
/// 用 UTC 会让"今日"在北京时间早上 8 点翻篇（Python 版是本地时间，属移植回归）。
pub(crate) const LOCAL_OFFSET_SECS: u64 = 8 * 3600;

/// 当前本地时间（自 epoch 起的秒数 + 时区偏移，用于日期前缀计算）
pub(crate) fn local_secs() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() + LOCAL_OFFSET_SECS)
        .unwrap_or(LOCAL_OFFSET_SECS)
}

pub(crate) fn now_str() -> String {
    iso_from_secs(local_secs())
}

/// 秒时间戳（已含时区偏移）→ "YYYY-MM-DDTHH:MM:SS"
pub(crate) fn iso_from_secs(secs: u64) -> String {
    chrono_lite(secs)
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

/// 原子认领下一个待执行任务（限定通道）。
///
/// `lane` 既能防止付费通道捞走免费单、也防止免费通道在付费未满时抢走付费单；
/// 额度判断留在调度循环里（见 `dispatcher_loop`），这里不做计数 —— 否则
/// "查额度 → 认领" 之间会出现超发窗口。
async fn claim_next_job(state: &AppState, kind: QueueKind, lane: Lane) -> Result<Option<QueueJob>> {
    let pool_guard = state.db.raw_pool().clone();
    let table = kind.table();
    let row = tokio::task::spawn_blocking(move || -> Result<Option<QueueJob>> {
        let mut conn = pool_guard.get()?;
        let tx = conn.transaction()?;
        let job = tx.query_row(
            &format!(
                // deleted_at IS NULL 不可省：队列监控的「删除」是软删除
                // （UPDATE ... SET deleted_at），漏掉这个过滤会把管理员已经
                // 删掉的任务继续捞出来执行。
                "SELECT job_id, username, password, website_id, job_type, course_ids, order_id, max_retries, retry_count, speed_mode
                 FROM {table}
                 WHERE status IN ('pending','retrying') AND deleted_at IS NULL AND lane=?1
                 ORDER BY priority ASC, created_at ASC LIMIT 1"
            ),
            rusqlite::params![lane.as_str()],
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
                    speed_mode: r.get::<_, Option<String>>(9)?.unwrap_or_default(),
                })
            },
        );
        match job {
            Ok(job) => {
                let now = now_str();
                tx.execute(
                    &format!(
                        "UPDATE {table} SET status='running', started_at=?1 WHERE job_id=?2"
                    ),
                    rusqlite::params![now, job.job_id],
                )?;
                // 订单侧同步置 running：此前只有支付链路（ypay_db）会写 running，
                // 后台「立即执行 / 重新入队」进来的任务会一直停在 queued —— 看板按
                // status='running' 统计"执行中"时漏掉这些订单，客户侧也停在"排队中"。
                // 已 running 的也一并刷新时间戳：进程重启后任务会被重新认领，旧时间戳
                // 会让看板的"卡单（执行超 6 小时）"把刚重启的健康单也算进去。
                if !job.order_id.is_empty() {
                    tx.execute(
                        "UPDATE orders SET status='running', started_at=?1, updated_at=?1 \
                         WHERE order_id=?2 AND status IN ('pending','accepted','queued','paid','running')",
                        rusqlite::params![now, job.order_id],
                    )?;
                }
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
    if let Some(job) = &row {
        progress::broadcast(state, "queue", "job.update", json!({
            "job_id": job.job_id,
            "order_id": job.order_id,
            "status": "running",
        }));
    }
    Ok(row)
}

/// 任务成功收口：把"已刷节数"对齐到整单总节数（见调用点的说明）
async fn sync_completed_steps(state: &AppState, job: &QueueJob, kind: QueueKind) {
    let pool = state.db.raw_pool().clone();
    let job_id = job.job_id.clone();
    let table = kind.table();
    let _ = tokio::task::spawn_blocking(move || -> Result<()> {
        let conn = pool.get()?;
        conn.execute(
            &format!("UPDATE {table} SET completed_steps = total_steps WHERE job_id = ?1"),
            rusqlite::params![job_id],
        )?;
        Ok(())
    })
    .await;
}

/// 写成功后统一广播 `job.update`（topic `queue`）——队列状态变更的唯一扼流点。
/// 若任务挂在订单上，额外向 `order:{order_id}` 发一条 `order.update` 作为
/// 「该订单有变化」的信号；前端收到后应重新拉取该订单，而不是把队列状态
/// 直接当作订单状态。
async fn update_job(state: &AppState, job: &QueueJob, kind: QueueKind,
                    fields: &[(&str, String)]) -> Result<()> {
    if fields.is_empty() {
        return Ok(());
    }
    let pool_guard = state.db.raw_pool().clone();
    let job_id = job.job_id.clone();
    let table = kind.table();
    let sets: Vec<String> = fields.iter().enumerate()
        .map(|(i, (k, _))| format!("{k}=?{}", i + 1))
        .collect();
    let values: Vec<String> = fields.iter().map(|(_, v)| v.clone()).collect();
    let n = fields.len();
    tokio::task::spawn_blocking(move || -> Result<()> {
        let conn = pool_guard.get()?;
        let sql = format!("UPDATE {table} SET {} WHERE job_id=?{}",
                          sets.join(", "), n + 1);
        conn.execute(&sql, rusqlite::params_from_iter(
            values.iter().map(|v| v.as_str()).chain(std::iter::once(job_id.as_str())),
        ))?;
        Ok(())
    })
    .await??;

    let get = |key: &str| -> Option<String> {
        fields.iter().find(|(name, _)| *name == key).map(|(_, v)| v.clone())
    };
    if let Some(status) = get("status") {
        progress::broadcast(state, "queue", "job.update", json!({
            "job_id": &job.job_id,
            "order_id": &job.order_id,
            "status": &status,
            "progress": get("progress"),
            "step": get("current_step_name"),
            "error": get("error_message"),
        }));
        if !job.order_id.is_empty() {
            let topic = format!("order:{}", job.order_id);
            progress::broadcast(state, &topic, "order.update", json!({
                "order_id": &job.order_id,
                "status": &status,
            }));
        }
    }
    Ok(())
}

/// 终态回写订单。
///
/// 此前队列只更新 `queue_jobs_*` 并广播信号，**从不改 orders.status**：
/// 任务失败/完成之后订单仍停在 queued/running，顾客看到的是"永远排队中"，
/// 只能靠管理员手动点「完成/标记失败」收尾。这里在任务进入终态时同步订单，
/// 且只在订单仍处于流转中状态时改写，避免覆盖管理员的人工决策。
async fn sync_order_state(state: &AppState, job: &QueueJob, status: &str, note: &str) {
    if job.order_id.is_empty() {
        return;
    }
    let pool = state.db.clone_pool();
    let oid = job.order_id.clone();
    let status = status.to_string();
    let status_for_sql = status.clone();
    let note = note.to_string();
    let now = now_str();
    let result = tokio::task::spawn_blocking(move || -> Result<usize> {
        let conn = pool.get()?;
        let n = conn.execute(
            "UPDATE orders SET status=?1, admin_note=?2, finished_at=?3, updated_at=?3
             WHERE order_id=?4
               AND deleted_at IS NULL
               AND status IN ('pending','accepted','queued','running','paid','waiting')",
            rusqlite::params![status_for_sql, note, now, oid],
        )?;
        Ok(n)
    })
    .await;
    match result {
        Ok(Ok(0)) => {} // 订单已被人为推进到终态，不覆盖
        Ok(Ok(_)) => {
            progress::broadcast(state, &format!("order:{}", job.order_id), "order.update", json!({
                "order_id": &job.order_id,
                "status": &status,
            }));
        }
        Ok(Err(e)) => tracing::warn!(job_id = %job.job_id, error = %e, "回写订单状态失败"),
        Err(e) => tracing::warn!(job_id = %job.job_id, error = %e, "回写订单状态失败（spawn_blocking 异常）"),
    }
}

/// 任务失败统一入口：按重试策略决定 → retrying 还是 failed（终态）。
///
/// **所有**失败路径都必须走这里。历史上登录失败是一条独立的提前 return，
/// 直接写死 `status='failed'`，绕过了重试策略 —— 一次网络抖动或 OCR 抖动
/// 就会把留给它的 3 次重试全部作废，且不写 finished_at。
async fn handle_job_failure(state: &AppState, job: &QueueJob, kind: QueueKind, err: &str) {
    if should_retry(job.retry_count, job.max_retries) {
        let _ = update_job(state, job, kind,
                           &[("status", "retrying".into()),
                             ("error_message", err.to_string()),
                             ("retry_count", (job.retry_count + 1).to_string())]).await;
        tracing::warn!(job_id = %job.job_id, attempt = job.retry_count + 1,
                       max = job.max_retries, error = %err, "任务失败，等待重试");
    } else {
        let _ = update_job(state, job, kind,
                           &[("status", "failed".into()),
                             ("error_message", err.to_string()),
                             ("finished_at", now_str())]).await;
        sync_order_state(state, job, "failed", err).await;
        tracing::warn!(job_id = %job.job_id, error = %err, "任务失败（已用尽重试）");
    }
}

/// 执行单个学校任务：登录 → 扫描+刷课 → 状态更新
async fn execute_school_job(state: &AppState, job: &QueueJob) {
    let base_url = crate::scan::platform_base_url(job.website_id);

    // 任务行里的 password 不可信：凭据迁移后 orders.password 明文列被清空，
    // 历史任务随之带着空密码入库。真值在 credentials 表 —— 执行时统一解密，
    // 解不到才回退任务行。否则 cookie 过期后重登必然「密码不可为空」。
    let password = {
        let db = state.db.clone_pool();
        let oid = job.order_id.clone();
        tokio::task::spawn_blocking(move || {
            let conn = db.get().ok()?;
            crate::crypto::load_password(&conn, &oid)
        })
        .await
        .ok()
        .flatten()
        .filter(|p| !p.is_empty())
        .unwrap_or_else(|| job.password.clone())
    };

    // 会话复用：缓存/落盘 cookie 有效则跳过登录（避免频繁登录触发平台风控）
    let session = match crate::session::get_session(&base_url, &job.username, &password).await {
        Ok(s) => s,
        Err(e) => {
            let raw = e.to_string();
            tracing::warn!(job_id = %job.job_id, error = %raw, "学校平台登录失败");
            let msg = if school_credential_error(&raw) {
                "登录失败：账号或密码不正确（或账号不存在/被锁定），请核对后重新提交".to_string()
            } else {
                format!("登录失败: {raw}")
            };
            if school_credential_error(&raw) {
                // 凭据类失败：直接终态，不进入队列重试（避免把账号刷到锁定）
                let _ = update_job(state, job, QueueKind::School,
                                   &[("status", "failed".into()),
                                     ("error_message", msg.clone()),
                                     ("finished_at", now_str())]).await;
                sync_order_state(state, job, "failed", &msg).await;
            } else {
                handle_job_failure(state, job, QueueKind::School, &msg).await;
            }
            return;
        }
    };

    // course_ids 解析（JSON 数组或 "cid:clid" 字符串）
    let course_ids: Vec<String> = serde_json::from_str(&job.course_ids)
        .unwrap_or_else(|_| job.course_ids.split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect());

    // 考试环节所需的 AI 凭据与开关：在这一层解析（队列侧有 db），
    // 让 scan/exam 保持"纯执行"、不依赖数据库
    let api_key = crate::llm::effective_api_key(&state.db).await;
    let ai_model = crate::llm::configured_model(&state.db, "deepseek_model",
                                                crate::llm::MODEL_FLASH).await;
    let exam_enabled = crate::queue::config_get(&state.db, "exam_solve_enabled").await
        .map(|v| v != "0").unwrap_or(true);

    let task = ScanTaskInput {
        order_id: if job.order_id.is_empty() { job.job_id.clone() } else { job.order_id.clone() },
        username: job.username.clone(),
        password,
        base_url: base_url.clone(),
        cookie_str: session.cookie_str,
        course_ids,
        // 队列任务同样要推进度：否则管理端只能靠手动刷新看任务跑到哪了
        push_ws: true,
        speed_mode: job.speed_mode.clone(),
        task_type: job.job_type.clone(),
        api_key,
        ai_model,
        exam_enabled,
    };

    let result = crate::scan::run_scan_and_study(&task, &state.push_url, &state.push_token).await;
    match result {
        Ok(()) => {
            let _ = update_job(state, job, QueueKind::School,
                               &[("status", "completed".into()), ("progress", "100".into()),
                                 ("current_step_name", "刷课完成".into()),
                                 ("finished_at", now_str())]).await;
            // 步数收口：成功路径上"已刷节数"必然等于整单总节数（引擎零失败才返回 Ok）。
            // 此前只改文案不改步数，重扫后无待刷的任务会停在上一轮的旧值（如 52/89），
            // 与平台已 100% 的状态对不上，看起来就像"进度少了几节"。
            sync_completed_steps(state, job, QueueKind::School).await;
            sync_order_state(state, job, "completed", "").await;
            tracing::info!(job_id = %job.job_id, "任务完成");
        }
        Err(e) => handle_job_failure(state, job, QueueKind::School, &e.to_string()).await,
    }
}

/// 凭据类登录失败何时该"立刻终态、不再重试"（学校与学习通共用）。
///
/// 密码错/账号被锁/账号不存在这类失败重试只会**白刷平台的错误次数**
/// （两个平台都是超过 5 次即锁号）——与 login.rs 的快速失败列表同一条安全约定。
/// 网络抖动类（DNS/超时）才交给队列的重试策略。
fn cx_credential_error(msg: &str) -> bool {
    ["密码", "账号", "锁定", "验证码", "不存在", "不能为空"]
        .iter()
        .any(|k| msg.contains(k))
}

/// 学校平台侧同名判定：登录错误里出现这些词就不要再让队列重试 3 轮
/// （实测一个不存在的学号会打满 3×10 次登录请求，白白逼近平台锁号线）
fn school_credential_error(msg: &str) -> bool {
    cx_credential_error(msg)
}

/// 执行单个学习通任务：登录（cx_login）→ 扫描 + 刷必学/积分视频（cx_scan/cx_study）。
///
/// 与学校任务的差别：
/// - 登录协议完全不同（AES 加密表单 /fanyalogin），且学习通会话不落盘复用，
///   每个任务登录一次；凭据错误立即终态（见 [`cx_credential_error`]）。
/// - 执行器自带节奏（cx_study 按视频时长自适应上报），不消费 speed_mode。
async fn execute_chaoxing_job(state: &AppState, job: &QueueJob) {
    // 密码：orders 明文列优先（load_password 兼容历史密文），解不到才回退任务行
    let password = {
        let db = state.db.clone_pool();
        let oid = job.order_id.clone();
        tokio::task::spawn_blocking(move || {
            let conn = db.get().ok()?;
            crate::crypto::load_password(&conn, &oid)
        })
        .await
        .ok()
        .flatten()
        .filter(|p| !p.is_empty())
        .unwrap_or_else(|| job.password.clone())
    };

    let session = match crate::cx_login::login(&job.username, &password).await {
        Ok(s) => s,
        Err(e) => {
            // 平台原文（login 会把响应 JSON 一起带出来）只进日志；写给客户端的
            // admin_note 必须是干净文案 —— 顾客不该看到 {"msg2":...} 这种原始报文
            let raw = e.to_string();
            let credential = cx_credential_error(&raw);
            let msg = if credential {
                "学习通账号或密码不正确（或账号被锁定），请确认后重试".to_string()
            } else {
                format!("学习通登录失败：{raw}")
            };
            tracing::warn!(job_id = %job.job_id, error = %raw, "学习通登录失败");
            if credential {
                // 凭据类失败：直接终态，不进入重试（避免把账号刷到锁定）
                let _ = update_job(state, job, QueueKind::Chaoxing,
                                   &[("status", "failed".into()),
                                     ("error_message", msg.clone()),
                                     ("finished_at", now_str())]).await;
                sync_order_state(state, job, "failed", &msg).await;
            } else {
                handle_job_failure(state, job, QueueKind::Chaoxing, &msg).await;
            }
            return;
        }
    };

    // course_ids 解析（JSON 数组或 "cid,cid" 字符串；cx 侧过滤只用 courseId 段）
    let course_ids: Vec<String> = serde_json::from_str(&job.course_ids)
        .unwrap_or_else(|_| job.course_ids.split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect());

    let task = crate::cx_scan::ScanCxTaskInput {
        order_id: if job.order_id.is_empty() { job.job_id.clone() } else { job.order_id.clone() },
        cookie_str: session.cookie_str.clone(),
        uid: session.uid.clone(),
        fid: session.fid.clone(),
        ua: String::new(), // 空 → 执行器用默认桌面 UA（与登录同栈）
        course_ids,
        status_file: None, // 直连执行不需要 Python 时代的中间状态文件
        push_ws: true,
    };

    match crate::cx_scan::run_cx_scan_and_study(&task, &state.push_url, &state.push_token).await {
        Ok(()) => {
            let _ = update_job(state, job, QueueKind::Chaoxing,
                               &[("status", "completed".into()), ("progress", "100".into()),
                                 ("current_step_name", "学习通刷课完成".into()),
                                 ("finished_at", now_str())]).await;
            sync_completed_steps(state, job, QueueKind::Chaoxing).await;
            sync_order_state(state, job, "completed", "").await;
            tracing::info!(job_id = %job.job_id, "学习通任务完成");
        }
        Err(e) => {
            let msg = e.to_string();
            // "无可处理任务"（课程已结束 / 没有积分视频）重试不会改变结果：
            // 直接终态，省掉 3 次无谓的登录+扫描，也让顾客尽快看到明确原因
            if msg.contains(crate::cx_scan::NO_WORK_PREFIX) {
                let _ = update_job(state, job, QueueKind::Chaoxing,
                                   &[("status", "failed".into()),
                                     ("error_message", msg.clone()),
                                     ("finished_at", now_str())]).await;
                sync_order_state(state, job, "failed", &msg).await;
                tracing::warn!(job_id = %job.job_id, error = %msg, "学习通无可处理任务（不重试）");
            } else {
                handle_job_failure(state, job, QueueKind::Chaoxing, &msg).await;
            }
        }
    }
}

/// 启动时回收上次运行遗留的 running 任务。
///
/// `claim_next_job` 只挑 `pending`/`retrying`，所以进程被 kill / 崩溃时留在
/// `running` 的行**永远不会再被任何人认领** —— 对应订单会永久停在「执行中」，
/// 既不会重试也不会失败，只能人工改库。启动瞬间本进程不可能有在跑的任务，
/// 因此把 running 全部退回 pending 是安全的（幂等）。
///
/// 两个队列都要回收：调度器只挑 pending/retrying，崩溃/重启遗留的 running
/// 行会永久卡住（订单永远停在"执行中"），本进程启动瞬间不可能有在跑任务。
///
/// 回收分两步：**所属订单已终态的直接收尾（不复活）**，其余才退回 pending。
/// 无条件退回会让已判失败的订单在每次重启时被复活重跑。
async fn reclaim_stale_running(state: &AppState, kind: QueueKind) {
    let pool = state.db.clone_pool();
    let table = kind.table();
    let result = tokio::task::spawn_blocking(move || -> Result<usize> {
        let conn = pool.get()?;
        let now = now_str();
        // 第一步：所属订单已经是终态（已完成/已失败/已取消/已删除）的 running 任务
        // **不复活**，直接收尾。
        //
        // 为什么：只按 running 无条件退回 pending 的话，一条订单已判失败、只因进程
        // 被杀时留在 running 的任务，会在**每次重启时被复活重跑**（线上实测
        // ORD-B2270270：订单 05:24 已 failed，15:45 重启又把它拉起来跑）。表现是
        // 顾客看到"失败"、队列里却还在 running，而且对已失败的课反复登录上报，
        // 白白推高平台风控/锁号风险。
        let closed = conn.execute(
            &format!(
                "UPDATE {table} SET status='failed', finished_at=?1,
                        error_message='所属订单已终态（完成/失败/取消），不再自动重跑；如需重刷请在后台手动入队'
                 WHERE status='running' AND deleted_at IS NULL
                   AND order_id IN (SELECT order_id FROM orders
                                     WHERE deleted_at IS NOT NULL
                                        OR status IN ('completed','failed','cancelled'))"
            ),
            rusqlite::params![now],
        )?;
        if closed > 0 {
            tracing::warn!(count = closed, queue = kind.name(),
                           "已把「订单已终态」的遗留任务收尾（不再复活重跑）");
        }
        // 第二步：其余（订单仍在进行中）退回 pending 重新调度
        let n = conn.execute(
            &format!(
                "UPDATE {table} SET status='pending', started_at=NULL
                 WHERE status='running' AND deleted_at IS NULL"
            ),
            [],
        )?;
        Ok(n)
    })
    .await;
    match result {
        Ok(Ok(0)) => {}
        Ok(Ok(n)) => tracing::warn!(count = n, queue = kind.name(),
                                    "已把上次运行遗留的 running 任务退回 pending，即将重新调度"),
        Ok(Err(e)) => tracing::error!(error = %e, queue = kind.name(), "回收遗留 running 任务失败"),
        Err(e) => tracing::error!(error = %e, queue = kind.name(),
                                  "回收遗留 running 任务失败（spawn_blocking 异常）"),
    }
}

/// 调度器主循环（每队列一个 tokio task）
///
/// 并发上限与暂停状态都从 system_config 动态读取（管理端可热更新）：
///   - `queue_max_workers`：**付费通道**同时执行的任务数上限
///   - `free_max_workers`：**免费通道**同时执行的任务数上限
///   - `queue_paused` / `queue_paused_school` / `queue_paused_chaoxing`：暂停开关
///
/// 两条通道额度独立、互不挤占：每轮先填付费槽位再填免费槽位，因此付费单永远
/// 不会排在免费积压后面；免费人流吃满了也只会卡住免费通道自己。
pub async fn dispatcher_loop(state: Arc<AppState>, kind: QueueKind) {
    tracing::info!(queue = kind.name(), table = kind.table(), "Rust 队列调度器启动");
    reclaim_stale_running(&state, kind).await;
    // 配置缓存：(上次刷新时间, 付费上限, 免费上限, 是否暂停)，避免每轮都查库
    let mut cfg_cache: RuntimeConfig = RuntimeConfig::initial();
    loop {
        // 显式 false 才停用（常规暂停走 queue_paused 热配置，不重启进程）
        if !dispatcher_enabled() {
            tokio::time::sleep(std::time::Duration::from_secs(5)).await;
            continue;
        }
        if cfg_cache.refreshed_at.elapsed() > std::time::Duration::from_secs(5) {
            cfg_cache = read_runtime_config(&state.db, kind).await;
        }
        if cfg_cache.paused {
            tokio::time::sleep(std::time::Duration::from_secs(2)).await;
            continue;
        }

        // 先付费后免费。任一条认领成功就立刻重试另一条（不 sleep），
        // 全部拿不到才退避 —— 空转成本只有一次索引查询。
        let mut claimed_any = false;
        let mut errored = false;
        for lane in LANE_ATTEMPT_ORDER {
            if active_workers_in_kind(kind, lane) >= cfg_cache.max_workers(lane) {
                continue;
            }
            // 额度变量、认领通道、槽位通道必须来自同一个 (队列, lane)，
            // 否则会出现"按付费额度放行、却认领了免费单"的错配
            match claim_next_job(&state, kind, lane).await {
                Ok(Some(job)) => {
                    claimed_any = true;
                    let state2 = state.clone();
                    // 槽位由 RAII 守卫持有：任务 panic 时 Drop 依然会归还槽位，
                    // 且归还到它所属队列与通道的计数器上
                    let slot = WorkerSlot::acquire(kind, lane);
                    let order_id = job.order_id.clone();
                    let order_id_task = order_id.clone();
                    let handle = tokio::spawn(async move {
                        let _slot = slot;
                        match kind {
                            QueueKind::School => execute_school_job(&state2, &job).await,
                            QueueKind::Chaoxing => execute_chaoxing_job(&state2, &job).await,
                        }
                        // 跑完自行摘除登记，避免表无限增长（panic 时留一条无效句柄，
                        // 对外部 abort 一个已结束的任务是无害空操作）
                        if !order_id_task.is_empty() {
                            state2.tasks.remove(&order_id_task);
                        }
                    });
                    // 登记 AbortHandle：管理端「取消」运行中的任务要能真的停下来，
                    // 只改库状态的话任务会继续跑完并把状态覆盖回 completed
                    if !order_id.is_empty() && !handle.is_finished() {
                        state.tasks.insert(order_id, handle.abort_handle());
                    }
                }
                Ok(None) => {}
                Err(e) => {
                    tracing::error!(error = %e, lane = lane.as_str(), "认领任务失败");
                    errored = true;
                }
            }
        }
        if claimed_any {
            continue;
        }
        tokio::time::sleep(std::time::Duration::from_secs(if errored { 5 } else { 2 })).await;
    }
}

/// 调度器运行期配置（热加载，每 5s 刷新一次）
struct RuntimeConfig {
    refreshed_at: std::time::Instant,
    paid_max: usize,
    free_max: usize,
    paused: bool,
}

impl RuntimeConfig {
    fn initial() -> Self {
        Self {
            refreshed_at: std::time::Instant::now(),
            paid_max: default_max_workers(),
            free_max: default_free_max_workers(),
            paused: false,
        }
    }

    fn max_workers(&self, lane: Lane) -> usize {
        match lane {
            Lane::Paid => self.paid_max,
            Lane::Free => self.free_max,
        }
    }
}

/// 免费通道默认并发数。
///
/// 免费是成本项，但不再压到 2 路：免费单只有视频，且服务端已把档位钉成保守档
/// （整单串行），单条订单本来就不会打出并发峰；真正的总闸是进程内视频会话数
/// （study::GLOBAL_STUDY_SESSIONS），免费池开得比它大也只会先排在那里。
/// 默认与 CPU 核数相当，管理端可热改（1..=64）。
fn default_free_max_workers() -> usize {
    std::env::var("RUST_FREE_MAX_WORKERS").ok()
        .and_then(|v| v.parse::<usize>().ok())
        .filter(|n| *n > 0)
        .unwrap_or(DEFAULT_FREE_WORKERS)
        .clamp(1, MAX_FREE_WORKERS_CEILING)
}

/// 默认并发上限：环境变量 > CPU 核数-1，夹在 1..=64。
/// Rust 任务全是 I/O 等待，上限远高于 Python 时代的 8。
fn default_max_workers() -> usize {
    std::env::var("RUST_QUEUE_MAX_WORKERS").ok()
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or_else(|| std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4).saturating_sub(1).max(1))
        .clamp(1, MAX_WORKERS_CEILING)
}

/// 读取运行期配置（两条通道的并发上限 + 暂停），失败时退回默认值
async fn read_runtime_config(db: &Db, kind: QueueKind) -> RuntimeConfig {
    // 夹在 1..=64：管理端写入的值不应能把进程拖垮（每个 worker 都是一条
    // 常驻 tokio 任务 + 一个临时目录），越界值一律按边界处理而不是照单全收。
    let paid_max = config_get(db, "queue_max_workers").await
        .and_then(|v| v.parse::<usize>().ok())
        .filter(|n| *n > 0)
        .unwrap_or_else(default_max_workers)
        .clamp(1, MAX_WORKERS_CEILING);
    let free_max = config_get(db, CFG_FREE_MAX_WORKERS).await
        .and_then(|v| v.parse::<usize>().ok())
        .filter(|n| *n > 0)
        .unwrap_or_else(default_free_max_workers)
        .clamp(1, MAX_FREE_WORKERS_CEILING);
    let paused = config_get(db, "queue_paused").await.map(|v| v == "1").unwrap_or(false)
        || config_get(db, kind.paused_key()).await.map(|v| v == "1").unwrap_or(false);
    RuntimeConfig { refreshed_at: std::time::Instant::now(), paid_max, free_max, paused }
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

/// 同步版配置读取（已在 spawn_blocking 闭包内、拿到连接时使用，避免再起一层嵌套）
pub fn config_get_blocking(conn: &rusqlite::Connection, key: &str) -> Option<String> {
    conn.query_row(
        "SELECT config_value FROM system_config WHERE config_key=?1",
        rusqlite::params![key],
        |r| r.get::<_, String>(0),
    )
    .ok()
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_should_retry_respects_budget() {
        // retry_count 从 0 起算：max=3 时应允许 3 次重试（0,1,2 都重试，3 才终态）
        assert!(should_retry(0, 3));
        assert!(should_retry(1, 3));
        assert!(should_retry(2, 3));
        assert!(!should_retry(3, 3));
        // max_retries=0 表示不重试（负数同样按 0 处理，避免 max() 溢出语义歧义）
        assert!(!should_retry(0, 0));
        assert!(!should_retry(0, -1));
    }

    #[test]
    fn test_default_max_workers_within_ceiling() {
        let n = default_max_workers();
        assert!(n >= 1 && n <= MAX_WORKERS_CEILING, "默认并发越界: {n}");
    }

    #[test]
    fn test_dispatcher_enabled_defaults_on() {
        // 不设变量 → 默认启用（这是本次修复的核心：此前默认关闭导致队列空转）
        std::env::remove_var("RUST_QUEUE_ENABLED");
        assert!(dispatcher_enabled());
        // 显式 false → 停用
        std::env::set_var("RUST_QUEUE_ENABLED", "false");
        assert!(!dispatcher_enabled());
        std::env::set_var("RUST_QUEUE_ENABLED", "true");
        assert!(dispatcher_enabled());
        std::env::remove_var("RUST_QUEUE_ENABLED");
    }

    // ── 双通道：判定表 / 额度 / 池隔离 ──────────────────────────────────

    /// 通道与优先级完全由 `paid_processed` 决定。这张表被支付入队和管理员补入队
    /// 两条路径共用，判定错一条就会让免费单落进付费池抢额度。
    #[test]
    fn test_lane_and_priority_table() {
        // 真实付款（ypay 回写的成功标记）→ 付费池，池内第一档
        assert_eq!(lane_and_priority("paid"), (Lane::Paid, 0));
        assert_eq!(lane_and_priority(""), (Lane::Paid, 0));
        assert_eq!(lane_and_priority("unprocessed"), (Lane::Paid, 0));
        // 持卡免费单：免考试费 + 插队
        assert_eq!(lane_and_priority("free:card"), (Lane::Free, 1));
        // 其余免费来源都不插队
        assert_eq!(lane_and_priority("free:global"), (Lane::Free, 2));
        assert_eq!(lane_and_priority("free:video"), (Lane::Free, 2));
        // 未知的 free: 子类型一律按普通免费处理，绝不因为新来源被误判进付费池
        assert_eq!(lane_and_priority("free:whatever"), (Lane::Free, 2));
        // 前后空白不该改变判定
        assert_eq!(lane_and_priority("  free:card  "), (Lane::Free, 1));
    }

    #[test]
    fn test_free_max_workers_default_within_ceiling() {
        let n = default_free_max_workers();
        assert!(n >= 1 && n <= MAX_FREE_WORKERS_CEILING, "免费默认并发越界: {n}");
        // 免费通道的上界不得反超付费通道：否则免费单能拿到比付费更大的额度，
        // "付费优先"的承诺直接被额度配置架空
        assert!(MAX_FREE_WORKERS_CEILING <= MAX_WORKERS_CEILING);
    }

    /// 池隔离 + 付费免排队。
    ///
    /// 场景刻意造得对免费最有利、对付费最不利：3 条免费单的 created_at 全部早于
    /// 唯一那条付费单（免费积压在前），且两条通道额度都为 1。此时一轮调度
    /// 必须先认领付费单 —— 这就是"付费免排队"的可验证形式。
    #[test]
    fn test_paid_lane_never_queues_behind_free_backlog() {
        let dir = std::env::temp_dir().join(format!("rust_worker_lane_test_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("lane.db");
        let _ = std::fs::remove_file(&path);
        let db = Db::open(path.to_str().unwrap()).unwrap();
        {
            let conn = db.clone_pool().get().unwrap();
            // 3 条免费（普通 2 条 + 持卡 1 条）与 1 条付费；付费单 created_at 最晚
            let rows = [
                ("JOB-FREE-A", "free", 2, "2026-01-01 00:00:01"),
                ("JOB-FREE-CARD", "free", 1, "2026-01-01 00:00:02"),
                ("JOB-FREE-B", "free", 2, "2026-01-01 00:00:03"),
                ("JOB-PAID", "paid", 0, "2026-01-01 00:00:04"),
            ];
            for (id, lane, prio, ts) in rows {
                conn.execute(
                    "INSERT INTO queue_jobs_school
                     (job_id, username, password, website_id, job_type, course_ids, status,
                      priority, lane, progress, total_steps, completed_steps, current_step_name,
                      error_message, retry_count, max_retries, order_id, result_data, verified,
                      created_at, speed_mode)
                     VALUES (?1,'u','p',1,'video','[]','pending',?2,?3,0,0,0,'','',0,3,
                             ?1,'{}',0,?4,'gentle')",
                    rusqlite::params![id, prio, lane, ts],
                )
                .unwrap();
            }
        }
        let pool = db.clone_pool();

        // 复刻调度器一轮的认领决策（两条通道额度各 1）：按 LANE_ATTEMPT_ORDER 依次尝试
        let claim = |lane: Lane| -> Option<String> {
            let conn = pool.get().unwrap();
            let id: String = conn.query_row(
                "SELECT job_id FROM queue_jobs_school
                 WHERE status IN ('pending','retrying') AND deleted_at IS NULL AND lane=?1
                 ORDER BY priority ASC, created_at ASC LIMIT 1",
                rusqlite::params![lane.as_str()], |r| r.get(0)).unwrap();
            conn.execute("UPDATE queue_jobs_school SET status='running' WHERE job_id=?1",
                         rusqlite::params![id]).unwrap();
            Some(id)
        };
        let claimed: Vec<String> = LANE_ATTEMPT_ORDER.iter().filter_map(|l| claim(*l)).collect();
        assert_eq!(claimed, vec!["JOB-PAID", "JOB-FREE-CARD"],
                   "一轮调度必须先拿付费单，再按 priority 拿免费单");

        // 付费通道只拿付费单；免费通道按 priority（持卡先于普通）再按 created_at
        let mut free_rest = Vec::new();
        for _ in 0..2 {
            free_rest.push(claim(Lane::Free).unwrap());
        }
        assert_eq!(free_rest, vec!["JOB-FREE-A", "JOB-FREE-B"]);
        let conn = pool.get().unwrap();
        let pending_paid: i64 = conn.query_row(
            "SELECT COUNT(*) FROM queue_jobs_school WHERE lane='paid' AND status='pending'",
            [], |r| r.get(0)).unwrap();
        assert_eq!(pending_paid, 0, "付费单不该被免费通道留下");
        drop(conn);
        let _ = std::fs::remove_file(&path);
    }
}

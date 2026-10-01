//! 扫描结果快照（进程内）—— 下单与计价的**服务端真相源**。
//!
//! 为什么必须有它：定价要知道"这门课还剩几场考试/作业"。此前这个事实来自客户端
//! 把扫描响应原样回传的 `course_details` —— 只要伪造 `exam_total: 0`，后端就算出
//! 0 元并放行执行，付费考试被白做（0 元白嫖通道）。现在扫描接口亲见的结果在这里
//! 留档，下单/试算一律回查快照：客户端只能"选择课程"，不能"定义事实"。
//!
//! 存储与生命周期：进程内 `RwLock<HashMap>`，键 `(username, website_id)`，TTL 2 小时。
//! 进程重启即失效 —— 用户重新扫描一次即可（扫描→下单本来就发生在同一段会话里）；
//! 宁可让极少数跨重启的下单收到"请重新扫描"，也不能退回信任客户端传值。

use std::collections::HashMap;
use std::sync::{Arc, OnceLock, RwLock};
use std::time::{Duration, Instant};

use serde_json::{json, Value};

/// 快照有效期。扫描到下单通常间隔几分钟；2 小时足够覆盖"扫完先想想"的场景，
/// 又不会让过期数据长期可用（事实变化后旧快照会低估/高估考试数）。
const TTL: Duration = Duration::from_secs(2 * 3600);

struct Snapshot {
    at: Instant,
    /// course_id → 计价需要的课程事实（与客户端 course_details 同形，但由服务端写入）
    courses: HashMap<String, Value>,
}

type Key = (String, i64);

static SNAPSHOTS: OnceLock<RwLock<HashMap<Key, Arc<Snapshot>>>> = OnceLock::new();

fn map() -> &'static RwLock<HashMap<Key, Arc<Snapshot>>> {
    SNAPSHOTS.get_or_init(|| RwLock::new(HashMap::new()))
}

/// 课程 ID 归一化：兼容 "courseId:classId" 旧格式，快照键只用 courseId。
fn norm_cid(raw: &str) -> &str {
    raw.split(':').next().unwrap_or("").trim()
}

/// 扫描成功后留档。只收 `records_loaded == true` 的课程：明细没拉到（子扫描失败）
/// 的课程视为"未亲见"，不进快照 —— 后续对它下单会拿到"请重新扫描"，
/// 而不是拿一份 0 考试的错误事实去算出 0 元。
pub fn save(username: &str, website_id: i64, courses: &[Value]) {
    let username = username.trim();
    if username.is_empty() || courses.is_empty() {
        return;
    }
    let mut m: HashMap<String, Value> = HashMap::new();
    for c in courses {
        if c["records_loaded"].as_bool() != Some(true) {
            continue;
        }
        let cid = c["course_id"].as_str().unwrap_or("").trim();
        if cid.is_empty() {
            continue;
        }
        m.insert(cid.to_string(), json!({
            "course_id": cid,
            "video_total": c["video_total"].as_i64().unwrap_or(0),
            "video_completed": c["video_completed"].as_i64().unwrap_or(0),
            // 学习通扫描没有这两个字段 → 0；学校平台的 exam_total 已含作业，
            // 与前端回传的 course_details 口径一致（定价只消费这几个数）
            "exam_total": c["exam_total"].as_i64().unwrap_or(0),
            "exam_done": c["exam_done"].as_i64().unwrap_or(0),
            "homework_total": c["homework_total"].as_i64().unwrap_or(0),
            "homework_done": c["homework_done"].as_i64().unwrap_or(0),
        }));
    }
    if m.is_empty() {
        return;
    }
    let mut g = map().write().unwrap_or_else(|e| e.into_inner());
    // 顺手清理过期条目，避免 Map 无限增长（快照数量 = 用户数×平台数，量级很小）
    let now = Instant::now();
    g.retain(|_, v| now.duration_since(v.at) < TTL);
    g.insert((username.to_string(), website_id), Arc::new(Snapshot { at: now, courses: m }));
}

/// 按选中课程回查事实（顺序与入参一致）。任一课程缺失或快照过期 → Err。
///
/// 空 `course_ids` 返回空表（调用方自行决定语义，例如纯视频单）。
pub fn resolve(username: &str, website_id: i64, course_ids: &[String]) -> Result<Vec<Value>, String> {
    const STALE: &str = "扫描数据已过期，请重新扫描后再提交订单";
    let username = username.trim();
    if username.is_empty() {
        return Err(STALE.to_string());
    }
    let g = map().read().unwrap_or_else(|e| e.into_inner());
    let Some(snap) = g.get(&(username.to_string(), website_id)) else {
        return Err(STALE.to_string());
    };
    if snap.at.elapsed() >= TTL {
        return Err(STALE.to_string());
    }
    let mut out = Vec::with_capacity(course_ids.len());
    for raw in course_ids {
        let cid = norm_cid(raw);
        match snap.courses.get(cid) {
            Some(v) => out.push(v.clone()),
            None => {
                return Err(format!(
                    "课程 {cid} 不在最近一次扫描结果中（或该课程明细未拉取成功），请重新扫描后再提交"
                ))
            }
        }
    }
    Ok(out)
}

/// 试算接口专用：请求没带平台号时，在三个学校平台的快照里找一遍。
/// 学习通（4）不参与明细定价（一口价），不参与查找。
pub fn resolve_any_school_platform(username: &str, course_ids: &[String]) -> Result<Vec<Value>, String> {
    for wid in [1i64, 2, 3] {
        if let Ok(v) = resolve(username, wid, course_ids) {
            return Ok(v);
        }
    }
    Err("扫描数据已过期，请重新扫描后再试算".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn course(id: &str, exam_total: i64, exam_done: i64, loaded: bool) -> Value {
        json!({
            "course_id": id, "records_loaded": loaded,
            "video_total": 10, "video_completed": 3,
            "exam_total": exam_total, "exam_done": exam_done,
        })
    }

    #[test]
    fn test_save_and_resolve_roundtrip() {
        save("u_snap_a", 1, &[course("C1", 2, 0, true), course("C2", 1, 1, true)]);
        let got = resolve("u_snap_a", 1, &["C2".into(), "C1".into()]).unwrap();
        assert_eq!(got.len(), 2);
        assert_eq!(got[0]["course_id"], "C2");
        assert_eq!(got[1]["exam_total"], 2);
        // "cid:clid" 旧格式也要能查到
        let got2 = resolve("u_snap_a", 1, &["C1:999".into()]).unwrap();
        assert_eq!(got2[0]["course_id"], "C1");
    }

    #[test]
    fn test_unloaded_or_missing_course_is_rejected() {
        save("u_snap_b", 1, &[course("C1", 0, 0, true), course("C2", 3, 0, false)]);
        // records_loaded=false 的课程不进快照：查不到 → 拒（不能拿 0 考试当免费）
        assert!(resolve("u_snap_b", 1, &["C2".into()]).is_err());
        // 完全没扫过的课程 → 拒
        assert!(resolve("u_snap_b", 1, &["C9".into()]).is_err());
        // 没扫过的用户名 → 拒
        assert!(resolve("u_snap_nobody", 1, &["C1".into()]).is_err());
    }

    #[test]
    fn test_platform_isolation() {
        save("u_snap_c", 2, &[course("CC", 5, 0, true)]);
        assert!(resolve("u_snap_c", 2, &["CC".into()]).is_ok());
        // 平台 1 没有这份快照
        assert!(resolve("u_snap_c", 1, &["CC".into()]).is_err());
        // 跨平台查找能命中
        assert!(resolve_any_school_platform("u_snap_c", &["CC".into()]).is_ok());
    }
}
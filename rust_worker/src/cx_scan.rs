//! 学习通扫描 + 视频计划构造 — 协议对齐 chaoxing_worker._build_video_plan
//!
//! 覆盖 Python 侧：fetch_course_list / fetch_knowledge_list / fetch_must_learn_kids /
//! ScoreRuleParser.fetch_rules / PointsExecutor.get_status / _fetch_person_id。
//! 登录（rnet TLS 指纹）保留在 Python crawl 子进程，cookie 透传本模块。
//!
//! 完成后：链式进入 cx_study::run_cx_study 刷视频，并写 cx_plan.json
//! （person_ids / must_learn_points / video_points）供 Python quiz 阶段读取。

use std::collections::HashSet;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result};
use regex::Regex;
use reqwest::Client;
use serde::Deserialize;
use serde_json::{json, Value};

use crate::cx_study::{run_cx_study, CxPoint, CxTaskInput};
use crate::platform_client::{CONNECT_TIMEOUT, REQUEST_TIMEOUT};

const VIDEO_REFERER: &str =
    "https://mooc1.chaoxing.com/ananas/modules/video/index.html?v=2025-0725-1842";

#[derive(Debug, Deserialize)]
pub struct ScanCxTaskInput {
    pub order_id: String,
    pub cookie_str: String,
    pub uid: String,
    #[serde(default)]
    pub fid: String,
    #[serde(default)]
    pub ua: String,
    #[serde(default)]
    pub course_ids: Vec<String>,
    pub status_file: String,
    #[serde(default)]
    pub push_ws: bool,
}

fn now_ms() -> u128 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0)
}

fn default_ua() -> &'static str {
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

fn make_client(ua: &str) -> Client {
    Client::builder()
        .danger_accept_invalid_certs(true)
        .connect_timeout(CONNECT_TIMEOUT)
        .timeout(REQUEST_TIMEOUT)
        .user_agent(if ua.is_empty() { default_ua() } else { ua })
        .build()
        .expect("构建 HTTP client 失败")
}

/// 课程条目（对齐 crawler.fetch_course_list 返回）
#[derive(Debug, Clone)]
struct CxCourse {
    course_id: String,
    class_id: String,
    name: String,
    ended: bool,
}

async fn fetch_course_list(client: &Client, cookie: &str) -> Result<Vec<CxCourse>> {
    let url = "https://mooc1-1.chaoxing.com/mooc-ans/visit/courselistdata";
    let resp = client.post(url)
        .header("Cookie", cookie)
        .header("Referer", "https://mooc1.chaoxing.com/")
        .header("Content-Type", "application/x-www-form-urlencoded")
        .body("courseType=1&courseFolderId=0&baseEducation=0&superstarClass=&courseFolderSize=0")
        .send().await
        .context("课程列表请求失败")?;
    let html = resp.text().await.context("课程列表读取失败")?;
    Ok(parse_course_list(&html))
}

/// 解析课程列表 HTML（对齐 Python：li[@class="course clearfix"] 的 xpath 提取）
fn parse_course_list(html: &str) -> Vec<CxCourse> {
    use scraper::{Html, Selector};

    let doc = Html::parse_document(html);
    let sel = Selector::parse("li.course.clearfix").unwrap();
    let mut courses = Vec::new();
    let mut seen = HashSet::new();
    for li in doc.select(&sel) {
        let course_id = li.value().attr("courseid").unwrap_or("").to_string();
        let class_id = li.value().attr("clazzid").unwrap_or("").to_string();
        if course_id.is_empty() || class_id.is_empty() {
            continue;
        }
        if !seen.insert((course_id.clone(), class_id.clone())) {
            continue;
        }
        let name = li.select(&Selector::parse(".course-name").unwrap()).next()
            .and_then(|e| e.value().attr("title"))
            .unwrap_or("未知课程").to_string();
        let ended = li.select(&Selector::parse(".not-open-tip").unwrap()).next()
            .map(|e| {
                let t = e.text().collect::<String>().to_lowercase();
                t.contains("closed") || t.contains("已结束")
            })
            .unwrap_or(false);
        courses.push(CxCourse { course_id, class_id, name, ended });
    }
    courses
}

/// 知识点列表（分页，对齐 crawler.fetch_knowledge_list 的 goKnowledge 解析）
async fn fetch_knowledge_list(client: &Client, cookie: &str, uid: &str,
                              course_id: &str, class_id: &str) -> Result<Vec<(String, String)>> {
    let re = Regex::new(
        r"goKnowledge\((\d+),(\d+),(?:&#39;|')(\d+)(?:&#39;|'),(?:&#39;|')(\d+)(?:&#39;|')\)",
    ).unwrap();
    let title_re = Regex::new(r#"<p class="book-name[^"]*">(.*?)</p>"#).unwrap();

    let mut points: Vec<(String, String)> = Vec::new(); // (kid, name)
    let mut page = 1u32;
    loop {
        let url = format!("https://tsjy.chaoxing.com/plaza/knowledge-list?courseId={course_id}");
        let form = format!(
            "personId={uid}&classId={class_id}&userId={uid}&classifyId=&element=0&point=0&name=&page={page}&pageSize=100"
        );
        let resp = client.post(&url)
            .header("Cookie", cookie)
            .header("Referer", format!("https://tsjy.chaoxing.com/plaza/knowledge-all?courseId={course_id}"))
            .header("Content-Type", "application/x-www-form-urlencoded")
            .body(form)
            .send().await
            .with_context(|| format!("知识点列表请求失败 page={page}"))?;
        let html = resp.text().await.context("知识点列表读取失败")?;
        let titles: Vec<String> = title_re.captures_iter(&html)
            .map(|c| strip_tags(&c[1]))
            .collect();
        let mut match_count = 0usize;
        for (i, cap) in re.captures_iter(&html).enumerate() {
            match_count += 1;
            let kid = cap[2].to_string();
            let name = titles.get(i).cloned().unwrap_or_else(|| format!("知识点{kid}"));
            if !points.iter().any(|(k, _)| k == &kid) {
                points.push((kid, name));
            }
        }
        if match_count < 100 {
            break;
        }
        page += 1;
    }
    Ok(points)
}

/// 必学知识点（classifyId=1）
async fn fetch_must_learn_kids(client: &Client, cookie: &str, uid: &str,
                               course_id: &str, class_id: &str) -> Result<Vec<String>> {
    let re = Regex::new(
        r"goKnowledge\((\d+),(\d+),(?:&#39;|')(\d+)(?:&#39;|'),(?:&#39;|')(\d+)(?:&#39;|')\)",
    ).unwrap();
    let url = format!("https://tsjy.chaoxing.com/plaza/knowledge-list?courseId={course_id}");
    let form = format!(
        "personId={uid}&classId={class_id}&userId={uid}&classifyId=1&element=0&point=0&name=&page=1&pageSize=100"
    );
    let resp = client.post(&url)
        .header("Cookie", cookie)
        .header("Referer", format!("https://tsjy.chaoxing.com/plaza/knowledge-all?courseId={course_id}"))
        .header("Content-Type", "application/x-www-form-urlencoded")
        .body(form)
        .send().await
        .context("必学列表请求失败")?;
    let html = resp.text().await.context("必学列表读取失败")?;
    let mut seen = HashSet::new();
    let mut kids = Vec::new();
    for cap in re.captures_iter(&html) {
        let kid = cap[2].to_string();
        if seen.insert(kid.clone()) {
            kids.push(kid);
        }
    }
    Ok(kids)
}

/// personId（cpi）：对齐 Python _fetch_person_id
async fn fetch_person_id(client: &Client, cookie: &str, course_id: &str) -> Result<String> {
    let resp = client.get("https://mooc1-api.chaoxing.com/mycourse/backclazzdata?view=json&rss=1")
        .header("Cookie", cookie)
        .send().await
        .context("backclazzdata 请求失败")?;
    let data: Value = resp.json().await.context("backclazzdata 解析失败")?;
    for ch in data["channelList"].as_array().cloned().unwrap_or_default() {
        let content = ch.get("content").cloned().unwrap_or_default();
        for c in content["course"]["data"].as_array().cloned().unwrap_or_default() {
            if c["id"].as_str() == Some(course_id) {
                return Ok(ch["cpi"].as_str().unwrap_or("").to_string());
            }
        }
    }
    Ok(String::new())
}

/// 积分状态（对齐 PointsExecutor.get_status）
async fn fetch_points_status(client: &Client, cookie: &str,
                             course_id: &str, class_id: &str) -> Result<(u64, u64)> {
    let url = format!(
        "https://bigdata-score.chaoxing.com/tsjy/point/getCount?courseid={course_id}&classid={class_id}"
    );
    let resp = client.get(&url).header("Cookie", cookie).send().await
        .context("积分状态请求失败")?;
    let data: Value = resp.json().await.context("积分状态解析失败")?;
    if data["status"].as_bool() != Some(true) {
        return Ok((0, 0));
    }
    let total: u64 = data["itemTotalScore"].as_array().cloned().unwrap_or_default()
        .iter().map(|i| i["score"].as_u64().unwrap_or(0)).sum();
    let day: u64 = data["itemDayScore"].as_array().cloned().unwrap_or_default()
        .iter().map(|i| i["score"].as_u64().unwrap_or(0)).sum();
    Ok((total, day))
}

/// 积分规则（对齐 ScoreRuleParser.fetch_rules 的正则解析）
async fn fetch_rules(client: &Client, cookie: &str, uid: &str,
                     course_id: &str, class_id: &str) -> Result<(u64, u64, u64)> {
    // 返回 (target, daily_limit, video_daily_cap)
    let url = format!(
        "https://tsjy.chaoxing.com/plaza/score-record?courseId={course_id}&personId={uid}&classId={class_id}&userId={uid}"
    );
    let referer = format!("https://tsjy.chaoxing.com/plaza/knowledge-all?courseId={course_id}");
    let resp = client.get(&url).header("Cookie", cookie).header("Referer", &referer)
        .send().await.context("积分规则页请求失败")?;
    let html = resp.text().await.context("积分规则页读取失败")?;

    let iframe_re = Regex::new(r#"<iframe[^>]*src="([^"]*bigdata-score\.chaoxing\.com[^"]*)"[^>]*>"#).unwrap();
    let iframe_src = iframe_re.captures(&html)
        .map(|c| c[1].to_string())
        .unwrap_or_default();

    let rules_html = if iframe_src.is_empty() {
        html
    } else {
        let iframe_url = if iframe_src.starts_with("//") {
            format!("https:{iframe_src}")
        } else if iframe_src.starts_with("http") {
            iframe_src
        } else {
            format!("https://bigdata-score.chaoxing.com{iframe_src}")
        };
        match client.get(&iframe_url).header("Cookie", cookie).header("Referer", &url)
            .send().await {
            Ok(r) => r.text().await.unwrap_or_default(),
            Err(_) => html,
        }
    };
    Ok(parse_rules(&rules_html))
}

fn parse_rules(html: &str) -> (u64, u64, u64) {
    let target = Regex::new(r"(?:至少)?需要获得(\d+)积分").unwrap()
        .captures(html).and_then(|c| c[1].parse().ok()).unwrap_or(0);
    let daily_limit = Regex::new(r"每日新增积分上限为(\d+)积分").unwrap()
        .captures(html).and_then(|c| c[1].parse().ok()).unwrap_or(0);
    // 视频行的每日上限：表格行 "视频" + "上限N" 或 "N分/天"
    let row_re = Regex::new(r"<tr[^>]*>(.*?)</tr>").unwrap();
    let td_re = Regex::new(r"<td[^>]*>(.*?)</td>").unwrap();
    let mut video_daily_cap = 0u64;
    for row in row_re.captures_iter(html) {
        let cells: Vec<String> = td_re.captures_iter(&row[1])
            .map(|c| strip_tags(&c[1])).collect();
        if cells.len() < 3 || !cells[0].contains("视频") {
            continue;
        }
        let rate_text = &cells[2];
        if !rate_text.contains("无上限") {
            if let Some(cap) = Regex::new(r"上限(\d+)").unwrap().captures(rate_text) {
                video_daily_cap = cap[1].parse().unwrap_or(0);
            } else if rate_text.contains("/天") {
                if let Some(r) = Regex::new(r"(\d+)分").unwrap().captures(rate_text) {
                    video_daily_cap = r[1].parse().unwrap_or(0);
                }
            }
        }
    }
    (target, daily_limit, video_daily_cap)
}

fn strip_tags(s: &str) -> String {
    let re = Regex::new(r"<[^>]+>").unwrap();
    re.replace_all(s, "").trim().to_string()
}

async fn write_cx_status(status_file: &str, phase: &str, message: &str,
                         done_flag: Option<bool>, success: Option<bool>,
                         extra: &[(&str, Value)]) {
    let mut map = serde_json::Map::new();
    map.insert("phase".into(), phase.into());
    map.insert("message".into(), message.into());
    map.insert("updated_at".into(), json!(now_ms() as f64 / 1000.0));
    for (k, v) in extra {
        map.insert(k.to_string(), v.clone());
    }
    if let Some(d) = done_flag {
        map.insert("done".into(), d.into());
    }
    if let Some(s) = success {
        map.insert("success".into(), s.into());
    }
    let body = Value::Object(map).to_string();
    let tmp = format!("{}.tmp", status_file);
    if tokio::fs::write(&tmp, body).await.is_ok() {
        let _ = tokio::fs::rename(&tmp, status_file).await;
    }
}

/// 完整链路：扫描 → 计划 → 链式刷视频（对齐 chaoxing_worker crawl 阶段）
pub async fn run_cx_scan_and_study(task: &ScanCxTaskInput, push_url: &str,
                                   push_token: &str) -> Result<()> {
    let client = make_client(&task.ua);
    let cookie = &task.cookie_str;

    let filter: HashSet<String> = task.course_ids.iter()
        .map(|c| c.split(':').next().unwrap_or("").to_string())
        .filter(|c| !c.is_empty())
        .collect();

    write_cx_status(&task.status_file, "crawl", "正在获取学习通课程...", None, None, &[]).await;
    let courses = fetch_course_list(&client, cookie).await?;
    let selected: Vec<CxCourse> = courses.into_iter()
        .filter(|c| !c.ended && (filter.is_empty() || filter.contains(&c.course_id)))
        .collect();
    if selected.is_empty() {
        write_cx_status(&task.status_file, "error", "未找到进行中的课程",
                        Some(true), Some(false), &[]).await;
        anyhow::bail!("未找到进行中的课程");
    }
    write_cx_status(&task.status_file, "crawl",
                    &format!("获取到 {} 门课程", selected.len()), None, None, &[]).await;

    let mut video_points: Vec<CxPoint> = Vec::new();
    let mut must_learn_points: Vec<CxPoint> = Vec::new();
    let mut person_ids: serde_json::Map<String, Value> = serde_json::Map::new();

    for course in &selected {
        let cname = &course.name;
        write_cx_status(&task.status_file, "crawl",
                        &format!("扫描课程: {cname}"), None, None, &[]).await;

        let (target, _daily_limit, video_daily_cap) =
            fetch_rules(&client, cookie, &task.uid, &course.course_id, &course.class_id)
                .await.unwrap_or((0, 0, 0));
        let (total, day_score) =
            fetch_points_status(&client, cookie, &course.course_id, &course.class_id)
                .await.unwrap_or((0, 0));
        let remaining = target.saturating_sub(day_score).min(target.saturating_sub(total));

        write_cx_status(&task.status_file, "chaoxing_points",
                        &format!("[{cname}] 积分 {total}/{target} 今日+{day_score}"),
                        None, None,
                        &[("points_total", json!(total)), ("points_target", json!(target))]).await;

        // 积分视频选择（对齐 Python _build_video_plan 的 min(3, remaining) 逻辑）
        if total < target && remaining > 0 {
            let points = fetch_knowledge_list(&client, cookie, &task.uid,
                                              &course.course_id, &course.class_id).await?;
            let mut earned = 0u64;
            for (kid, name) in points {
                if earned >= remaining || (video_daily_cap > 0 && earned >= video_daily_cap) {
                    break;
                }
                video_points.push(CxPoint {
                    cid: course.course_id.clone(),
                    kid,
                    clid: course.class_id.clone(),
                    name,
                });
                earned += remaining.saturating_sub(earned).min(3);
            }
        }

        // 必学 + personId
        let person_id = fetch_person_id(&client, cookie, &course.course_id).await.unwrap_or_default();
        person_ids.insert(course.course_id.clone(), json!(person_id));
        if let Ok(kids) = fetch_must_learn_kids(&client, cookie, &task.uid,
                                                &course.course_id, &course.class_id).await {
            for kid in kids {
                let name = format!("必学{kid}");
                must_learn_points.push(CxPoint {
                    cid: course.course_id.clone(),
                    kid,
                    clid: course.class_id.clone(),
                    name,
                });
            }
        }
    }

    // 写计划文件（Python quiz 阶段读取）
    let plan = json!({
        "video_points": video_points,
        "must_learn_points": must_learn_points,
        "person_ids": person_ids,
        "day_count": 1,
    });
    let plan_path = task.status_file.replace("status.json", "cx_plan.json");
    let _ = tokio::fs::write(&plan_path, plan.to_string()).await;

    let all_points: Vec<CxPoint> = video_points.into_iter()
        .chain(must_learn_points.into_iter())
        .collect();
    if all_points.is_empty() {
        write_cx_status(&task.status_file, "error", "无视频任务",
                        Some(true), Some(false), &[]).await;
        anyhow::bail!("无视频任务");
    }

    write_cx_status(&task.status_file, "study_must_learn",
                    &format!("扫描完成，共 {} 个知识点视频", all_points.len()),
                    None, None, &[]).await;

    // 链式进入刷视频（cx_study）
    let study_task = CxTaskInput {
        order_id: task.order_id.clone(),
        cookie_str: task.cookie_str.clone(),
        uid: task.uid.clone(),
        fid: task.fid.clone(),
        ua: if task.ua.is_empty() { default_ua().to_string() } else { task.ua.clone() },
        course_name: format!("{}门课程", selected.len()),
        points: all_points,
        status_file: task.status_file.clone(),
        push_ws: task.push_ws,
    };
    run_cx_study(&study_task, push_url, push_token).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_course_list() {
        let html = r#"<li class="course clearfix" courseid="100" clazzid="200">
            <span class="course-name" title="高等数学"></span>
            <a class="not-open-tip">Course has closed</a>
        </li>
        <li class="course clearfix" courseid="101" clazzid="201">
            <span class="course-name" title="大学英语"></span>
        </li>"#;
        let courses = parse_course_list(html);
        assert_eq!(courses.len(), 2);
        assert_eq!(courses[0].name, "高等数学");
        assert!(courses[0].ended);
        assert_eq!(courses[1].course_id, "101");
        assert!(!courses[1].ended);
    }

    #[test]
    fn test_parse_rules() {
        let html = r#"至少需要获得200积分 每日新增积分上限为50积分
        <tr><td>视频</td><td>视频观看时长得分不得低于180积分</td><td>1分/分钟 上限50</td></tr>
        <tr><td>登录</td><td>每天首次登录得1分</td><td>1分/天</td></tr>"#;
        let (target, daily_limit, video_cap) = parse_rules(html);
        assert_eq!(target, 200);
        assert_eq!(daily_limit, 50);
        assert_eq!(video_cap, 50);
    }

    #[test]
    fn test_strip_tags() {
        assert_eq!(strip_tags("<p>标题</p>"), "标题");
    }
}

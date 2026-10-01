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
    /// 中间状态/计划文件（Python daemon 时代产物）。队列直连执行传 None：
    /// 进度走 push_url 推送，计划不再落盘（此前写出的 cx_plan.json 无人读取）
    #[serde(default)]
    pub status_file: Option<String>,
    #[serde(default)]
    pub push_ws: bool,
}

fn now_ms() -> u128 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0)
}

fn default_ua() -> &'static str {
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

pub(crate) fn make_client(ua: &str) -> Client {
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

/// 我的课程（`backclazzdata`：channelList 每条带 courseId / clazzId / personId）。
///
/// 这条接口比 courselistdata 更完整：带班级名与任课老师，且是后续任务点/上报要用的
/// 三元组（courseId + clazzId + personId）的唯一来源。
#[derive(Debug, Clone)]
pub struct CxCourseInfo {
    pub course_id: String,
    pub class_id: String,
    pub person_id: String,
    pub name: String,
    pub class_name: String,
    pub teacher: String,
}

fn num_str(v: &Value) -> String {
    if let Some(n) = v.as_i64() {
        n.to_string()
    } else {
        v.as_str().unwrap_or("").trim().to_string()
    }
}

/// 我的课程（`backclazzdata`）。`client` 必须挂登录得到的 cookie jar：
/// 学习通各子站的 host 级 cookie 不同，手工拼一个 Cookie 头会在部分站点被判未登录。
pub async fn fetch_my_courses(client: &Client) -> Result<Vec<CxCourseInfo>> {
    let resp = client
        .get("https://mooc1-api.chaoxing.com/mycourse/backclazzdata?view=json&rss=1")
        .header("Referer", "https://mooc1.chaoxing.com/")
        .send()
        .await
        .context("学习通课程列表请求失败")?;
    let v: Value = resp.json().await.context("学习通课程列表解析失败（返回非 JSON）")?;
    let mut out: Vec<CxCourseInfo> = Vec::new();
    for ch in v["channelList"].as_array().cloned().unwrap_or_default() {
        let content = &ch["content"];
        let course = match content["course"]["data"].as_array().and_then(|a| a.first()) {
            Some(c) => c.clone(),
            None => continue,
        };
        let course_id = num_str(&course["id"]);
        let class_id = num_str(&ch["key"]);
        if course_id.is_empty() || class_id.is_empty() || course_id == "0" {
            continue;
        }
        if out.iter().any(|c| c.course_id == course_id && c.class_id == class_id) {
            continue;
        }
        out.push(CxCourseInfo {
            course_id,
            class_id,
            person_id: num_str(&ch["cpi"]),
            name: course["name"].as_str().unwrap_or("").trim().to_string(),
            class_name: content["name"].as_str().unwrap_or("").trim().to_string(),
            teacher: course["teacherfactor"].as_str().unwrap_or("").trim().to_string(),
        });
    }
    Ok(out)
}

/// 课程规则（学习广场首页内联 JS 的 `rule` 变量）。
///
/// 网络课的有效期在这里：`isEffectiveDate=false` 表示不在有效学习时间内，
/// 平台会关闭一切学习入口（2026-10-01 实测：modify-node 返回“没有权限”、
/// 上报接口统一 403）——此时期望值是“不可学”，而不是“还有 N 个待学”。
#[derive(Debug, Default, Clone)]
pub struct CxCourseRule {
    pub effective: bool,
    pub begin_date: String,
    pub end_date: String,
}

/// 单门课的任务概览 —— "有网课看网课、有作业做作业、有考试做考试"的量化依据。
///
/// 三个来源（2026-10-01 线上实测，参数与字段均已验证）：
/// - 作业：`mooc-ans/work/api/task`（列表）+ `work/api/unfinished`（明确未完成数）
/// - 考试：`exam-ans/mooc2/exam/task`（`stuStatus=3` 为已完成，其余按"还能做"计数）
/// - 网课：学习广场知识点（`tsjy/plaza/knowledge-list`，文本标注「学习中 / 已学完」）
#[derive(Debug, Default, Clone)]
pub struct CxCourseTasks {
    pub work_total: u32,
    pub work_pending: u32,
    pub exam_total: u32,
    pub exam_pending: u32,
    /// 视频/知识点：总数与已学完数（学习广场）
    pub video_total: u32,
    pub video_completed: u32,
    /// 有效期（仅学习广场课有；非广场课拉不到 rule，保持 None）
    pub rule: Option<CxCourseRule>,
}

/// 拉取课程规则（plaza 首页注入的 `var rule = '{...}'`）。
/// 非广场课没有这个页面，返回 None —— 调用方按“无法判定”处理。
pub async fn fetch_course_rule(client: &Client, uid: &str,
                               course: &CxCourseInfo) -> Option<CxCourseRule> {
    crate::platform_client::wait_rate_limit().await;
    let url = format!(
        "https://tsjy.chaoxing.com/plaza/?courseId={}&personId={}&classId={}&userId={}",
        course.course_id, course.person_id, course.class_id, uid
    );
    let resp = client.get(&url)
        .header("Referer", "https://tsjy.chaoxing.com/plaza/index")
        .send().await.ok()?;
    let html = resp.text().await.ok()?;
    parse_course_rule(&html)
}

/// 从 plaza 首页抽 `var rule = '{...}'`（纯函数以便单测）
fn parse_course_rule(html: &str) -> Option<CxCourseRule> {
    let re = Regex::new(r"var rule = '([^']+)'").ok()?;
    let caps = re.captures(html)?;
    let v: Value = serde_json::from_str(&caps[1]).ok()?;
    Some(CxCourseRule {
        effective: v["isEffectiveDate"].as_bool().unwrap_or(false),
        begin_date: v["beginDate"].as_str().unwrap_or("").to_string(),
        end_date: v["endDate"].as_str().unwrap_or("").to_string(),
    })
}

/// 作业与考试的完成判定：`stuStatus=3` 为已完成；其余只有在"时间窗还没关"时才算待办，
/// 已过期的旧任务不能当成可做（否则会去做平台早就关闭的作业）。
fn count_tasks(items: &[Value], now: i64) -> (u32, u32) {
    let total = items.len() as u32;
    let pending = items
        .iter()
        .filter(|t| {
            let done = t["stuStatus"].as_i64().unwrap_or(0) == 3;
            if done {
                return false;
            }
            let start = t["startTime"].as_i64().unwrap_or(0);
            let end = t["endTime"].as_i64().unwrap_or(0);
            (start == 0 || start <= now) && (end == 0 || end > now)
        })
        .count() as u32;
    (total, pending)
}

/// 学习广场知识点的「总数 / 已学完」——从渲染文本里数状态词（接口不返回结构化状态）
fn count_points(html: &str) -> (u32, u32) {
    let text = strip_tags(html);
    let learned = text.matches("\u{5df2}\u{5b66}\u{5b8c}").count() as u32; // 已学完
    let learning = text.matches("\u{5b66}\u{4e60}\u{4e2d}").count() as u32; // 学习中
    (learned + learning, learned)
}

/// 拉取单门课的三类任务概览。任何一路失败都只降级为 0（不拖垮整次扫描）
pub async fn fetch_course_tasks(client: &Client, uid: &str,
                                course: &CxCourseInfo) -> CxCourseTasks {
    let mut t = CxCourseTasks::default();
    let now = now_ms() as i64;

    crate::platform_client::wait_rate_limit().await;
    if let Ok(resp) = client
        .get(format!(
            "https://mooc1.chaoxing.com/mooc-ans/work/api/task?courseId={}&classId={}&pageNum=1&pageSize=100",
            course.course_id, course.class_id))
        .header("Referer", format!("https://mooc1.chaoxing.com/mooc-ans/mycourse/stu?courseid={}&clazzid={}",
                                   course.course_id, course.class_id))
        .send().await
    {
        if let Ok(v) = resp.json::<Value>().await {
            let items = v["data"].as_array().cloned().unwrap_or_default();
            let (total, pending) = count_tasks(&items, now);
            t.work_total = total;
            t.work_pending = pending;
        }
    }

    crate::platform_client::wait_rate_limit().await;
    if let Ok(resp) = client
        .get(format!(
            "https://mooc1.chaoxing.com/exam-ans/mooc2/exam/task?courseId={}&classId={}",
            course.course_id, course.class_id))
        .header("Referer", format!("https://mooc1.chaoxing.com/exam-ans/mooc2/exam/exam-list?courseid={}&clazzid={}",
                                   course.course_id, course.class_id))
        .send().await
    {
        if let Ok(v) = resp.json::<Value>().await {
            let items = v["data"].as_array().cloned().unwrap_or_default();
            let (total, pending) = count_tasks(&items, now);
            t.exam_total = total;
            t.exam_pending = pending;
        }
    }

    // 学习广场（知识点视频）：课程没开广场/没资源时接口返回空块，计数自然为 0
    if !course.person_id.is_empty() {
        crate::platform_client::wait_rate_limit().await;
        let url = format!("https://tsjy.chaoxing.com/plaza/knowledge-list?courseId={}", course.course_id);
        if let Ok(resp) = client
            .post(&url)
            .header("Referer", format!("https://tsjy.chaoxing.com/plaza/knowledge-all?courseId={}", course.course_id))
            .header("Content-Type", "application/x-www-form-urlencoded")
            .body(format!(
                "personId={}&classId={}&userId={}&classifyId=&element=0&point=0&name=&page=1&pageSize=100",
                course.person_id, course.class_id, uid))
            .send().await
        {
            if let Ok(html) = resp.text().await {
                let (total, done) = count_points(&html);
                t.video_total = total;
                t.video_completed = done;
            }
        }
        // 有效期：过期课程的“未学完”只是历史遗留状态，平台已不许学
        t.rule = fetch_course_rule(client, uid, course).await;
    }
    t
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

async fn write_cx_status(status_file: Option<&str>, phase: &str, message: &str,
                         done_flag: Option<bool>, success: Option<bool>,
                         extra: &[(&str, Value)]) {
    let Some(status_file) = status_file else { return };
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

    write_cx_status(task.status_file.as_deref(), "crawl", "正在获取学习通课程...", None, None, &[]).await;
    let courses = fetch_course_list(&client, cookie).await?;
    let selected: Vec<CxCourse> = courses.into_iter()
        .filter(|c| !c.ended && (filter.is_empty() || filter.contains(&c.course_id)))
        .collect();
    if selected.is_empty() {
        write_cx_status(task.status_file.as_deref(), "error", "未找到进行中的课程",
                        Some(true), Some(false), &[]).await;
        anyhow::bail!("未找到进行中的课程");
    }
    write_cx_status(task.status_file.as_deref(), "crawl",
                    &format!("获取到 {} 门课程", selected.len()), None, None, &[]).await;

    let mut video_points: Vec<CxPoint> = Vec::new();
    let mut must_learn_points: Vec<CxPoint> = Vec::new();
    let mut person_ids: serde_json::Map<String, Value> = serde_json::Map::new();

    for course in &selected {
        let cname = &course.name;
        write_cx_status(task.status_file.as_deref(), "crawl",
                        &format!("扫描课程: {cname}"), None, None, &[]).await;

        let (target, _daily_limit, video_daily_cap) =
            fetch_rules(&client, cookie, &task.uid, &course.course_id, &course.class_id)
                .await.unwrap_or((0, 0, 0));
        let (total, day_score) =
            fetch_points_status(&client, cookie, &course.course_id, &course.class_id)
                .await.unwrap_or((0, 0));
        let remaining = target.saturating_sub(day_score).min(target.saturating_sub(total));

        write_cx_status(task.status_file.as_deref(), "chaoxing_points",
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

    // 计划文件（Python 时代留给外部 quiz 阶段的中间产物）：只在传了 status_file
    // 时落盘；队列直连执行传 None，计划随本次执行直接消费，不产生死文件
    if let Some(status_file) = task.status_file.as_deref() {
        let plan = json!({
            "video_points": video_points,
            "must_learn_points": must_learn_points,
            "person_ids": person_ids,
            "day_count": 1,
        });
        let plan_path = status_file.replace("status.json", "cx_plan.json");
        let _ = tokio::fs::write(&plan_path, plan.to_string()).await;
    }

    let all_points: Vec<CxPoint> = video_points.into_iter()
        .chain(must_learn_points.into_iter())
        .collect();
    if all_points.is_empty() {
        write_cx_status(task.status_file.as_deref(), "error", "无视频任务",
                        Some(true), Some(false), &[]).await;
        anyhow::bail!("无视频任务");
    }

    write_cx_status(task.status_file.as_deref(), "study_must_learn",
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

    /// 作业/考试计数：已完成(3)不计；过期的旧任务不算"可做"（否则会去做平台已关闭的作业）
    #[test]
    fn test_count_tasks_respects_status_and_window() {
        let now = 1_700_000_000_000i64;
        let items = vec![
            json!({"stuStatus": 3, "startTime": 0, "endTime": 0}),
            json!({"stuStatus": 1, "startTime": 0, "endTime": 0}),
            json!({"stuStatus": 1, "startTime": 0, "endTime": now + 1000}),
            json!({"stuStatus": 1, "startTime": 0, "endTime": now - 1000}),
            json!({"stuStatus": 0, "startTime": now + 10_000, "endTime": 0}),
        ];
        let (total, pending) = count_tasks(&items, now);
        assert_eq!(total, 5);
        assert_eq!(pending, 2, "只有未交且窗口开着的两条才算待办");
    }

    /// 学习广场知识点：接口不给结构化状态，从渲染文本里数「学习中 / 已学完」
    #[test]
    fn test_count_points_from_rendered_text() {
        let html = r#"<div class="book-name">学习中 必学 甲</div>
                      <div class="book-name">已学完 乙</div>
                      <div class="book-name">学习中 必学 丙</div>"#;
        assert_eq!(count_points(html), (3, 1));
    }

    /// 课程规则（plaza 首页 `var rule = '{...}'`）：过期课程必须识别为不可学，
    /// 否则“29 个待学”会误导下单（平台对过期课程统一 403）
    #[test]
    fn test_parse_course_rule() {
        let html = r#"<script>
            var rule = '{"fid":"336900","isEffectiveDate":false,"courseMinScore":0,"endDate":"2026-06-14","beginDate":"2026-04-01","courseId":"260982075"}';
            var joinClassId = '140481754';
        </script>"#;
        let r = parse_course_rule(html).expect("应解析出 rule");
        assert!(!r.effective);
        assert_eq!(r.begin_date, "2026-04-01");
        assert_eq!(r.end_date, "2026-06-14");

        // 有效期内
        let html2 = r#"var rule = '{"isEffectiveDate":true,"beginDate":"2026-09-01","endDate":"2027-01-10"}';"#;
        let r2 = parse_course_rule(html2).unwrap();
        assert!(r2.effective);

        // 非广场课：没有 rule → None（不能误判为过期）
        assert!(parse_course_rule("<html>no rule here</html>").is_none());
    }

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

//! 学校平台课程扫描 — 协议对齐 worker.py crawl 阶段
//!
//! 覆盖 Python 侧 get_courses_with_diag（课程列表 HTML 解析）与
//! get_course_nodes_from_api 的视频分页拉取。扫描完成后直接链式进入
//! study::run_study（视频列表无缝衔接），Python 只需登录后提交一次任务。
//!
//! 注意：考试/作业的清洗与验证留在 Python（考试阶段会重新扫描，
//! 且含大量平台特判逻辑）；本模块只产出刷课所需的视频列表。

use anyhow::{Context, Result};
use rand::RngExt;
use reqwest::Client;
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use crate::study::{run_study, TaskInput, Video};

// ── 扫描并发控制（全模块共享） ────────────────────────────────────────────

/// 单平台在飞 HTTP 请求上限：对服务器压力抹平，并发但不猛打
pub const SCAN_CONCURRENCY: usize = 8;

static SCAN_SEM: tokio::sync::OnceCell<Arc<tokio::sync::Semaphore>> =
    tokio::sync::OnceCell::const_new();

/// 全局扫描信号量（所有分页/记录请求都需先 acquire）
pub async fn scan_sem() -> &'static Arc<tokio::sync::Semaphore> {
    SCAN_SEM.get_or_init(|| async { Arc::new(tokio::sync::Semaphore::new(SCAN_CONCURRENCY)) }).await
}

#[derive(Debug, Deserialize)]
pub struct ScanTaskInput {
    pub order_id: String,
    #[serde(default)]
    pub username: String,
    #[serde(default)]
    pub password: String,
    pub base_url: String,
    pub cookie_str: String,
    #[serde(default)]
    pub course_ids: Vec<String>, // "courseId" 或 "courseId:classId"
    #[serde(default)]
    pub push_ws: bool,
    /// 刷课节奏档位（turbo/balanced/gentle；缺省/未知 → 均衡）
    #[serde(default)]
    pub speed_mode: String,
    /// 订单类型（video / exam / full）：exam、full 刷完视频后要接着做未完成的考试
    #[serde(default)]
    pub task_type: String,
    /// 考试答题用的 AI Key 与模型（由调用方从 system_config/env 解析后传入）
    #[serde(default)]
    pub api_key: String,
    #[serde(default)]
    pub ai_model: String,
    /// 考试环节总开关（关闭时只刷视频，考试留给人工）
    #[serde(default)]
    pub exam_enabled: bool,
}

/// 课程条目（从 /user/index HTML 解析）
pub struct CourseItem {
    pub name: String,
    pub course_id: String,
    pub study_record_url: String,
    /// .name a 的 href（detail_link，对齐 get_courses）
    #[allow(dead_code)]
    pub detail_link: String,
}

/// 学校平台 base_url：测试钩子 → 域名监控缓存（动态）→ 静态默认表
/// 测试钩子：RUST_TEST_BASE_URL 环境变量覆盖（mock 平台 E2E 用）
pub fn platform_base_url(website_id: i64) -> String {
    let override_url = std::env::var("RUST_TEST_BASE_URL")
        .ok()
        .filter(|u| !u.is_empty());
    resolve_base_url(override_url, website_id)
}

/// 优先级实现（与进程环境解耦，便于确定性地单测三层回退）
pub(crate) fn resolve_base_url(override_url: Option<String>, website_id: i64) -> String {
    if let Some(url) = override_url {
        return url;
    }
    // 域名监控（domain.rs）写库后即时生效：域名一换，新起的任务立刻用新域名
    if let Some(url) = crate::domain::cached_base_url(website_id) {
        return url;
    }
    static_base_url(website_id)
}

/// 静态默认表（缓存与钩子都未命中时的兜底）
fn static_base_url(website_id: i64) -> String {
    // 注意：这里是**静默兜底**——未列出的 website_id 会被当成学校平台 1 去登录。
    // 学习通（id=4）绝不能落到这条兜底上：那会拿用户的手机号+密码去登录
    // 在线课程测评考试平台，若该手机号在那边也存在，就会刷错人的课。
    match website_id {
        2 => "https://cdcas.duxingkej.com".to_string(),
        3 => "https://cdcas.chaoxiankeji.com".to_string(),
        // 学习通站点本身；登录另需 TLS 指纹伪装（见 school_exam::scan_chaoxing 注释）
        4 => "https://mooc1.chaoxing.com".to_string(),
        // 1 及未知 id：平台 1 体系（首页上那条已废弃的 suwankj 不再登记，
        // 2026-10-01 用户确认）
        _ => "https://cdcass.taiskeji.com".to_string(),
    }
}

/// 解析 "HH:MM:SS" / "MM:SS" / 秒数 为秒
pub fn parse_duration_secs(s: &str) -> u64 {
    let s = s.trim();
    if s.is_empty() {
        return 0;
    }
    if let Ok(n) = s.parse::<u64>() {
        return n;
    }
    if let Ok(n) = s.parse::<f64>() {
        return n.round() as u64;
    }
    let parts: Vec<&str> = s.split(':').collect();
    if parts.len() == 2 {
        if let (Ok(m), Ok(sec)) = (parts[0].parse::<u64>(), parts[1].parse::<u64>()) {
            return m * 60 + sec;
        }
    }
    if parts.len() == 3 {
        if let (Ok(h), Ok(m), Ok(sec)) = (
            parts[0].parse::<u64>(),
            parts[1].parse::<u64>(),
            parts[2].parse::<u64>(),
        ) {
            return h * 3600 + m * 60 + sec;
        }
    }
    0
}

/// 从 URL 中提取 courseId=（与 Python 一致）
fn extract_course_id(url: &str) -> String {
    let mut out = String::new();
    for part in url.split(['&', '?']) {
        if let Some(v) = part.strip_prefix("courseId=") {
            out = v.to_string();
        }
    }
    out
}

/// 解析课程列表（对齐 get_courses_with_diag 的 xpath 提取）
pub async fn fetch_course_list(client: &Client, cookie: &str, base_url: &str) -> Result<Vec<CourseItem>> {
    let html = fetch_course_list_html(client, cookie, base_url).await?;
    Ok(parse_course_list(&html))
}

/// 抓取课程列表页原始 HTML（降负载：调用方可复用同一响应做二次解析，
/// 避免对 /user/index 发第二次 17KB 请求）
pub async fn fetch_course_list_html(client: &Client, cookie: &str, base_url: &str) -> Result<String> {
    let url = format!("{}/user/index", base_url.trim_end_matches('/'));
    // 整页导航请求，不能带 X-Requested-With（否则平台走 AJAX 分支渲染 500「数据出现异常」）
    let resp = client.get(&url)
        .header("Cookie", cookie)
        .send().await
        .context("获取课程列表失败")?;
    let html = resp.text().await.context("课程列表读取失败")?;

    // 登录失效诊断（对齐 Python 的 302/登录页特征）
    if html.contains("SQLSTATE") || html.contains("数据出现异常") {
        anyhow::bail!("平台数据库异常");
    }
    Ok(html)
}

/// 解析课程列表 HTML（对齐 get_courses_with_diag 的 xpath 提取）：
/// //div[contains(@class,"user-course")]//div[@class="item"]，
/// 名称取 .name a 文本，course_id 从 .status a 的 courseId= 参数提取
pub fn parse_course_list(html: &str) -> Vec<CourseItem> {
    use scraper::{Html, Selector};

    let doc = Html::parse_document(html);
    let item_sel = Selector::parse(".user-course .item").unwrap();
    let name_sel = Selector::parse(".name a").unwrap();
    let status_sel = Selector::parse(".status a").unwrap();

    let mut courses = Vec::new();
    let mut seen = HashSet::new();
    for item in doc.select(&item_sel) {
        let name = item.select(&name_sel).next()
            .map(|a| a.text().collect::<String>().trim().to_string())
            .unwrap_or_default();
        if name.is_empty() {
            continue;
        }
        let detail_link = item.select(&name_sel).next()
            .and_then(|a| a.value().attr("href"))
            .unwrap_or("")
            .to_string();
        let study_record_url = item.select(&status_sel).next()
            .and_then(|a| a.value().attr("href"))
            .unwrap_or("")
            .to_string();
        let course_id = extract_course_id(&study_record_url);
        if course_id.is_empty() || !seen.insert(course_id.clone()) {
            continue;
        }
        courses.push(CourseItem { name, course_id, study_record_url, detail_link });
    }
    courses
}

/// 拉取单门课程的视频（分页 study_record/video.json，对齐 get_course_nodes_from_api）
/// 优化：第 1 页拿到 pageCount 后剩余页并发预取（推测分页），不再逐页串行
/// 从 JSON 值里取时长（秒），兼容平台可能给出的多种形态。
///
/// 平台在不同站点/接口把同一字段返回成字符串（`"10:30"`、`"630"`）或数字（`630`）。
/// 此前只走 `as_str()`：拿到数字就静默兜底成 0，而 0 会让扫描侧判"待刷"、
/// 刷课侧判"已完成"，最终收钱不干活还报 100%（见 `study::video_is_done` 的说明）。
///
/// 返回 `None` 表示**拿不到可用时长**（字段缺失 / 非数值 / 为 0）——
/// 调用方必须把它当成"不知道"，不能当成 0。
fn duration_secs_of(v: &Value) -> Option<u64> {
    let secs = if let Some(s) = v.as_str() {
        if s.trim().is_empty() {
            return None;
        }
        parse_duration_secs(s)
    } else if let Some(n) = v.as_u64() {
        n
    } else if let Some(n) = v.as_f64() {
        if !n.is_finite() || n < 0.0 {
            return None;
        }
        n.round() as u64
    } else {
        return None;
    };
    if secs == 0 { None } else { Some(secs) }
}

/// 字段取值：优先 camelCase，缺失时退回 snake_case（不同站点两种写法都出现过）
fn field<'a>(item: &'a Value, camel: &str, snake: &str) -> &'a Value {
    match item.get(camel) {
        Some(v) if !v.is_null() => v,
        _ => item.get(snake).unwrap_or(&Value::Null),
    }
}

/// 已学时长（秒）：拿不到一律记 0。
/// 与视频总时长的差别是关键 —— 0 是"一点没看"的自然取值，
/// 而"不知道总时长"必须表达为 `None`，绝不能糊成 0（见 [`duration_secs_of`]）。
fn viewed_secs(item: &Value) -> u64 {
    duration_secs_of(field(item, "viewedDuration", "viewed_duration")).unwrap_or(0)
}

/// 平台元数据里的视频总时长（秒）：`videoDuration` 字段（"HH:MM:SS"）。
///
/// **绝不能拿 `duration` 字段当总时长** —— 线上实测它等于已学秒数
/// （与 viewedDuration 同义，如"已学 2:44"的视频 duration="164"）。
/// 把它当长度会让"已学 164s / 实际 476s"的视频被算成"已完成"而整节跳过，
/// 客户付了钱、平台上一节没动。
///
/// `videoDuration` 多数准确，但存在少量失真（实测同一课程多个不同视频
/// 都写成 00:02:35，真实长度 273~710s 不等），所以它只是**兜底**：
/// 媒体探测（mvhd）能拿到时以文件真值为准（见 [`fill_durations_from_media`]）。
fn meta_duration_secs(item: &Value) -> Option<u64> {
    duration_secs_of(field(item, "videoDuration", "video_duration"))
}

// ── 用视频文件真值校准时长 ──────────────────────────────────────────────
//
// 平台的 /user/study_record/video 接口里"每节总长"只有两个来源，都不完美：
//   - `duration` 字段：**不是总长**，线上实测等于已学秒数（与 viewedDuration 同义）；
//   - `videoDuration` 字段："HH:MM:SS"，多数准确，但存在失真
//     （实测同一课程多个不同视频都写成 00:02:35，真实长度 273~710s 不等）。
// 把前者当总长会让"已学 164s / 实际 476s"的视频被当成"已完成"而跳过。
//
// 权威来源是文件本身：MP4 的 moov/mvhd 里带 timescale 与 duration，
// 范围请求取文件头（或尾）几百 KB 就能命中，不依赖平台接口、平台改版也不受影响。
// 签名地址过期的（auth_key 失效）探不动，退回 videoDuration 兜底。

/// 单次范围取多少字节：moov 要么在文件头，要么被流式优化挪到文件尾
const MEDIA_PROBE_BYTES: u64 = 512 * 1024;

/// 媒体探测的进程级并发上限。CDN 不是平台、不必走 0.5s 出站闸门，
/// 但一次扫描可能有上百节要补，无节制打会把自己变成流量放大器。
const MEDIA_PROBE_CONCURRENCY: usize = 6;

static MEDIA_PROBE_SEM: tokio::sync::OnceCell<Arc<tokio::sync::Semaphore>> =
    tokio::sync::OnceCell::const_new();

async fn media_probe_sem() -> &'static Arc<tokio::sync::Semaphore> {
    MEDIA_PROBE_SEM
        .get_or_init(|| async { Arc::new(tokio::sync::Semaphore::new(MEDIA_PROBE_CONCURRENCY)) })
        .await
}

/// 进程级视频时长缓存（key → 秒）。
///
/// 为什么必须有：探测一次要 GET 512KB×1~2 段才能读到 mvhd，41 节就是一二十兆
/// 流量 + 二十来秒墙钟，而**时长是恒定值** —— 每次扫描/刷课重探是纯浪费，
/// 老板反馈的"扫描卡半天"大头就在这里（列表接口只花 3 秒）。
///
/// key 用 `base_url#course_id#node_id`：三个学校平台是同款软件，course_id / node_id
/// 各自独立分配，不带站点前缀会串台；串台会把别的学校的时长当成自己的，
/// 短了这节课永远刷不完、长了平台不认账，都是订单失败。
///
/// 只存进程内存不落库：这是纯加速用的派生数据，重启后重探一次即可，
/// 而落库要为它把 Db 句柄一路穿到扫描/刷课/考试三条调用链上，不值当。
static DURATION_CACHE: std::sync::OnceLock<std::sync::Mutex<HashMap<String, u64>>> =
    std::sync::OnceLock::new();

/// 缓存条数上限。到顶就整表清空 —— 这类数据任何时候都可以重建，
/// 与其做 LRU 不如用一个粗暴但有界的上限，避免长跑进程无限吃内存。
const DURATION_CACHE_MAX: usize = 20_000;

fn duration_cache() -> &'static std::sync::Mutex<HashMap<String, u64>> {
    DURATION_CACHE.get_or_init(|| std::sync::Mutex::new(HashMap::new()))
}

fn duration_cache_key(base_url: &str, course_id: &str, node_id: &str) -> String {
    format!("{}#{}#{}", base_url.trim_end_matches('/'), course_id, node_id)
}

pub(crate) fn duration_cache_get(key: &str) -> Option<u64> {
    duration_cache().lock().ok()?.get(key).copied()
}

pub(crate) fn duration_cache_put(key: String, secs: u64) {
    let Ok(mut m) = duration_cache().lock() else { return };
    if m.len() >= DURATION_CACHE_MAX {
        m.clear();
    }
    m.insert(key, secs);
}

fn be32(b: &[u8], i: usize) -> Option<u32> {
    b.get(i..i + 4).map(|s| u32::from_be_bytes(s.try_into().unwrap()))
}

fn be64(b: &[u8], i: usize) -> Option<u64> {
    b.get(i..i + 8).map(|s| u64::from_be_bytes(s.try_into().unwrap()))
}

/// 从 MP4 字节流里读出时长（秒）：定位 `mvhd` 原子，按 version 取 timescale 与 duration。
/// 返回 `None` = 这批字节里没有可用的 moov（需要换个范围再取）。
pub fn mp4_duration_secs(buf: &[u8]) -> Option<u64> {
    let i = buf.windows(4).position(|w| w == b"mvhd")?;
    let ver = *buf.get(i + 4)?;
    let mut p = i + 8; // 跳过 "mvhd" + version(1) + flags(3)
    let (timescale, duration) = if ver == 1 {
        p += 8 + 8; // creation / modification（64 位）
        let ts = be32(buf, p)? as u64;
        (ts, be64(buf, p + 4)?)
    } else {
        p += 4 + 4; // creation / modification（32 位）
        let ts = be32(buf, p)? as u64;
        (ts, be32(buf, p + 4)? as u64)
    };
    if timescale == 0 || duration == 0 {
        return None;
    }
    // 向上取整：209.2s 的视频要按 210s 去报，少报一秒就可能不算完成
    Some(duration.div_ceil(timescale))
}

/// 取视频文件时长：先头后尾（moov 通常在头，流式优化的文件在尾）。
/// 整体重试一轮并加抖动：CDN 偶发瞬时拒绝（实测同一批探测时会整轮失败，
/// 下一轮又全好），一次失败就放弃会让一批视频退回元数据兜底值。
async fn probe_media_duration(client: &Client, url: &str) -> Option<u64> {
    for attempt in 0..2 {
        if attempt > 0 {
            tokio::time::sleep(std::time::Duration::from_millis(
                200 + rand::random::<u64>() % 400)).await;
        }
        for range in [
            format!("bytes=0-{}", MEDIA_PROBE_BYTES - 1),
            format!("bytes=-{MEDIA_PROBE_BYTES}"),
        ] {
            let resp = match client.get(url).header("Range", range).send().await {
                Ok(r) if r.status().is_success() => r,
                _ => continue,
            };
            let body = match resp.bytes().await {
                Ok(b) => b,
                Err(_) => continue,
            };
            if let Some(secs) = mp4_duration_secs(&body) {
                return Some(secs);
            }
        }
    }
    // 两轮都拿不到：多为签名地址已过期（auth_key 失效），或 CDN 不支持 Range。
    // 留下实际地址，否则"补不到时长"永远只是个数字，没法定位。
    tracing::warn!(url = %url, "视频文件读不出时长（退回平台元数据兜底）");
    None
}

/// 用视频文件真值校准时长（并发受限）。
///
/// 只要拿得到文件地址就都探一遍，不只是补"缺时长"的：
/// 平台元数据存在失真（实测多个不同视频同为 00:02:35），文件真值才权威。
/// 探测成功取两者较大值（mvhd 一般比元数据大 1~2s，多报无妨；元数据偏小时以真值为准）；
/// 探测失败（签名地址过期等）保留元数据值；两者都拿不到才留 `None`，
/// 由刷课侧显式失败 —— 绝不猜一个数字糊过去。
async fn fill_durations_from_media(client: &Client, base_url: &str, videos: &mut [Video]) {
    // 第一遍吃缓存：命中的直接抬到文件真值，不再为它发一次探测请求。
    // （这一遍是"扫描提速"的全部收益来源 —— 同一节课只在进程内被探一次）
    let mut pending: Vec<(usize, String, String)> = Vec::new();
    let mut hits = 0usize;
    let mut with_file = 0usize;
    for (i, v) in videos.iter_mut().enumerate() {
        let Some(url) = v.local_file.clone() else { continue };
        with_file += 1;
        let key = duration_cache_key(base_url, &v.course_id, &v.node_id);
        match duration_cache_get(&key) {
            Some(secs) => {
                // 与平台元数据取较大值，口径与探测成功后完全一致
                v.duration = Some(v.duration.map_or(secs, |d| d.max(secs)));
                hits += 1;
            }
            None => pending.push((i, url, key)),
        }
    }
    if pending.is_empty() {
        if hits > 0 {
            tracing::info!(hits, with_file, "视频时长全部命中缓存，跳过媒体探测");
        }
        return;
    }
    let total = pending.len();
    let sem = media_probe_sem().await.clone();
    let mut set = tokio::task::JoinSet::new();
    for (idx, url, key) in pending {
        let permit = match sem.clone().acquire_owned().await {
            Ok(p) => p,
            Err(_) => break,
        };
        let c = client.clone();
        set.spawn(async move {
            let _permit = permit;
            (idx, key, probe_media_duration(&c, &url).await)
        });
    }
    let mut filled = 0usize;
    while let Some(r) = set.join_next().await {
        if let Ok((idx, key, Some(secs))) = r {
            // 与平台元数据取较大值：真实文件长度才是人肉播放能到达的上限
            videos[idx].duration = Some(match videos[idx].duration {
                Some(d) => d.max(secs),
                None => secs,
            });
            // 只缓存探测成功的：失败值（None）不写，下次仍会重试
            duration_cache_put(key, secs);
            filled += 1;
        }
    }
    let without = videos.iter().filter(|v| v.duration.is_none()).count();
    if filled < total {
        tracing::warn!(filled, total, cached = hits, without,
                       "部分视频文件读不出时长（有元数据的已退回兜底值，无元数据的会显式失败）");
    } else {
        tracing::info!(filled, total, cached = hits, "已用视频文件校准全部时长");
    }
}

pub async fn fetch_course_videos(client: &Client, cookie: &str, base_url: &str,
                             course_id: &str, course_name: &str) -> Result<Vec<Video>> {
    let base = format!("{}/user/study_record/video", base_url.trim_end_matches('/'));

    let parse_items = |items: &[Value]| -> Vec<Video> {
        let mut out = Vec::new();
        // 时长解析不出来时，把第一条原始条目打出来（每次调用最多一条，避免刷屏）。
        // 这种"看不懂的数据"正是静默故障的源头，必须留下可查的证据。
        let mut unparsed: Option<String> = None;
        for item in items {
            let node_id = item["id"].as_str().unwrap_or("").to_string();
            if node_id.is_empty() {
                continue;
            }
            let duration = meta_duration_secs(item);
            if duration.is_none() && unparsed.is_none() {
                let raw = serde_json::to_string(item).unwrap_or_default();
                unparsed = Some(raw.chars().take(400).collect());
            }
            out.push(Video {
                node_id,
                // 校准值（会被媒体探测抬高）用于"还要刷多久"，平台原值用于"是否已学"
                duration,
                platform_duration: duration,
                // 平台自己的判定（state 里带"已学"）：与平台页面一致，优先采信
                platform_done: item["state"].as_str()
                    .map(|s| s.contains("\u{5df2}\u{5b66}")).unwrap_or(false),
                viewed_duration: viewed_secs(item),
                local_file: field(item, "localFile", "local_file").as_str()
                    .filter(|s| !s.is_empty()).map(str::to_string),
                name: item["name"].as_str().unwrap_or(course_name).to_string(),
                course_id: course_id.to_string(),
            });
        }
        if let Some(raw) = unparsed {
            // 元数据没给可用时长（videoDuration 缺失/不可解析）是常态、不是异常，
            // 所以只留 debug：真正的信号在 fill_durations_from_media 的校准统计里。
            tracing::debug!(course_id, raw = %raw, "列表接口未给元数据时长（将从视频文件探测）");
        }
        out
    };

    // 单页拉取（带并发信号量 + 抖动，对齐 exam/work 的取页策略）
    // 独立 async fn 而非闭包：可被多次调用做并发预取
    async fn fetch_video_page(client: &Client, cookie: &str, base: &str,
                              course_id: &str, page: u32) -> Option<Value> {
        let jitter = rand::random::<u64>() % 100;
        tokio::time::sleep(std::time::Duration::from_millis(jitter)).await;
        let _permit = scan_sem().await.acquire().await.ok()?;
        let url = format!("{}?courseId={}&page={}", base, course_id, page);
        let resp = client.get(&url)
            .header("Cookie", cookie)
            .header("X-Requested-With", "XMLHttpRequest")
            .send().await.ok()?;
        if resp.status().as_u16() != 200 {
            return None;
        }
        resp.json::<Value>().await.ok()
    }

    // 第 1 页：探测 pageCount + 拿首批数据
    let first = match fetch_video_page(client, cookie, &base, course_id, 1).await {
        Some(d) if d["status"].as_bool() == Some(true) => d,
        _ => return Ok(Vec::new()),
    };
    let mut videos = parse_items(first["list"].as_array().map(|a| a.as_slice()).unwrap_or(&[]));
    let page_count = first["pageInfo"]["pageCount"].as_u64().unwrap_or(1) as u32;
    if page_count <= 1 {
        // 分页收尾统一在这里补时长，避免多页时漏掉
        fill_durations_from_media(client, base_url, &mut videos).await;
        return Ok(videos);
    }
    // 推测预取：剩余页并发全发
    let mut futs = Vec::new();
    for page in 2..=page_count {
        futs.push(fetch_video_page(client, cookie, &base, course_id, page));
    }
    for d in futures_util::future::join_all(futs).await.into_iter().flatten() {
        if d["status"].as_bool() == Some(true) {
            if let Some(list) = d["list"].as_array() {
                videos.extend(parse_items(list));
            }
        }
    }
    fill_durations_from_media(client, base_url, &mut videos).await;
    Ok(videos)
}

/// 完整任务：扫描全部课程视频 → 链式进入刷课
pub async fn run_scan_and_study(task: &ScanTaskInput, push_url: &str,
                                push_token: &str) -> Result<()> {
    let base_url = task.base_url.trim_end_matches('/').to_string();
    let client = crate::platform_client::build_client_with_ua(
        crate::platform_client::SHORT_UA, false, None);

    // course_ids 过滤集（兼容 "courseId" 与 "courseId:classId" 两种格式）
    let filter: HashSet<String> = task.course_ids.iter()
        .map(|c| c.split(':').next().unwrap_or("").to_string())
        .filter(|c| !c.is_empty())
        .collect();

    let courses = fetch_course_list(&client, &task.cookie_str, &base_url).await?;
    let selected: Vec<&CourseItem> = courses.iter()
        .filter(|c| filter.is_empty() || filter.contains(&c.course_id))
        .collect();
    // 考试环节要按课程回访考试清单，先把 (course_id, name) 留一份
    let exam_courses: Vec<(String, String)> = selected.iter()
        .map(|c| (c.course_id.clone(), c.name.clone()))
        .collect();
    if selected.is_empty() {
        anyhow::bail!("未找到课程");
    }

    // 并发扫描各课程视频（每课程一个 tokio task）。
    // 并发度与错峰由档位决定：急速档全量并行，温柔档一次只扫 1~2 门并长间隔错开。
    let profile = crate::speed::SpeedMode::parse(&task.speed_mode).profile();
    let shared_client = Arc::new(client);
    let cookie = Arc::new(task.cookie_str.clone());
    let scan_sem = Arc::new(tokio::sync::Semaphore::new(profile.scan_concurrency.max(1)));
    let mut handles = Vec::new();
    for course in selected {
        // 先取扫描许可再派发：超出并发的课程会在此等待，天然形成分批扫描
        let permit = match scan_sem.clone().acquire_owned().await {
            Ok(p) => p,
            Err(_) => break,
        };
        let c = shared_client.clone();
        let ck = cookie.clone();
        let b = base_url.clone();
        let cid = course.course_id.clone();
        let cname = course.name.clone();
        let jitter = profile.scan_jitter();
        handles.push(tokio::spawn(async move {
            let _permit = permit;
            // 启动抖动：把同批课程的首请求错开，避免瞬间并发突发打到平台
            if !jitter.is_zero() {
                tokio::time::sleep(jitter).await;
            }
            let videos = fetch_course_videos(&c, &ck, &b, &cid, &cname).await;
            (cname, cid, videos)
        }));
        // 课程之间错峰：温柔档拉长到几十秒，急速档为零
        profile.sleep_course_stagger().await;
    }
    let mut all_videos: Vec<Video> = Vec::new();
    let mut scan_failed = 0u64;
    for h in handles {
        match h.await {
            Ok((cname, cid, Ok(vids))) => {
                if vids.is_empty() {
                    eprintln!("[scan] 课程无视频: {cname} (id={cid})");
                }
                all_videos.extend(vids);
            }
            Ok((cname, cid, Err(e))) => {
                scan_failed += 1;
                eprintln!("[scan] 课程扫描失败: {cname} (id={cid}) err={e}");
            }
            Err(e) => {
                scan_failed += 1;
                eprintln!("[scan] 课程扫描任务失败: {e}");
            }
        }
    }
    if scan_failed > 0 {
        tracing::warn!(scan_failed, total = all_videos.len(), "部分课程扫描失败（其余课程照常刷课）");
    }
    if all_videos.is_empty() {
        anyhow::bail!("未找到任何视频");
    }

    // 只把"还没刷满"的视频放进队列。
    // 扫描在计费阶段用的就是这个判据（study::video_is_done），这里复用同一个函数：
    // 两边各算各的，就会出现"收了 N 节的钱、实际只刷 M 节"，进度分母也会虚高。
    let scanned = all_videos.len();
    all_videos.retain(|v| !crate::study::video_is_done(v));
    let skipped = scanned - all_videos.len();
    if skipped > 0 {
        eprintln!("[scan] 已有完成进度的 {skipped} 节不再重复刷（本单待刷 {} 节）", all_videos.len());
    }
    if all_videos.is_empty() {
        // 视频全都已经刷满了：没有要做的活，直接进入考试环节，
        // 而不是当成错误（那是"扫描失败"才会有的结论）
        tracing::info!(order_id = %task.order_id, "所选课程视频均已完成，跳过刷课");
        if needs_exam(&task.task_type) {
            solve_exams(task, &shared_client, &base_url, &exam_courses, push_url, push_token).await?;
        }
        return Ok(());
    }

    // 链式进入刷课（复用 study::run_study）
    let study_task = TaskInput {
        order_id: task.order_id.clone(),
        username: task.username.clone(),
        password: task.password.clone(),
        base_url: base_url.clone(),
        cookies: task.cookie_str.split(';').filter_map(|pair| {
            let (k, v) = pair.split_once('=')?;
            Some(crate::study::CookieKV {
                name: k.trim().to_string(),
                value: v.trim().to_string(),
            })
        }).collect(),
        videos: all_videos,
        concurrency: 0,
        push_ws: task.push_ws,
        speed_mode: task.speed_mode.clone(),
        // 分母用量：把已刷满、被上面 retain 跳过的节数带进刷课任务，
        // 让进度条按整单累计而不是按"本轮剩余"重算（否则每次重扫都归零）
        already_done: skipped as u64,
    };
    run_study(&study_task, push_url, push_token).await?;

    // 视频刷完 → 接着做考试（考试/全包订单）。
    // 这一步此前完全缺失：exam/full 订单只刷视频就被标记完成，等于收了考试的钱没做考试。
    if needs_exam(&task.task_type) {
        solve_exams(task, &shared_client, &base_url, &exam_courses, push_url, push_token).await?;
    }
    Ok(())
}

/// 是否需要在刷课之后执行考试环节
fn needs_exam(task_type: &str) -> bool {
    matches!(task_type, "exam" | "full")
}

/// 逐课程拉取未完成的考试并交给 AI 作答（沿用订单所选档位的节奏错峰）。
///
/// 失败语义：只要有考试没做成，就返回 Err 让队列按重试策略再跑一遍 ——
/// 视频此时已刷完，重跑只会补考试，代价很小；比"悄悄少做几场考试还报成功"诚实。
async fn solve_exams(task: &ScanTaskInput, client: &Client, base_url: &str,
                     courses: &[(String, String)], push_url: &str, push_token: &str) -> Result<()> {
    if !task.exam_enabled {
        tracing::warn!(order_id = %task.order_id, "考试环节已关闭，跳过考试");
        return Ok(());
    }
    if task.api_key.is_empty() {
        anyhow::bail!("考试环节需要 AI Key，但当前未配置");
    }
    let profile = crate::speed::SpeedMode::parse(&task.speed_mode).profile();
    let mut total = 0usize;
    let mut ok = 0usize;
    let mut failed: Vec<String> = Vec::new();

    for (course_id, course_name) in courses {
        let exams = crate::school_exam::list_actionable_exams(
            client, &task.cookie_str, base_url, course_id).await;
        if exams.is_empty() {
            continue;
        }
        tracing::info!(course = %course_name, count = exams.len(), "开始处理考试");
        for e in &exams {
            let work_id = e["work_id"].as_str().unwrap_or("");
            let node_id = e["node_id"].as_str().unwrap_or("");
            let name = e["name"].as_str().unwrap_or("");
            if work_id.is_empty() {
                continue;
            }
            total += 1;
            match crate::exam::solve_exam(base_url, &task.cookie_str, work_id, course_id, node_id,
                                          &task.api_key, &task.ai_model, "exam", None).await {
                Ok(r) if r["success"].as_bool() == Some(true) => {
                    ok += 1;
                    tracing::info!(course = %course_name, exam = %name, "考试完成");
                }
                Ok(r) => {
                    let msg = r["error"].as_str().unwrap_or("未知原因").to_string();
                    failed.push(format!("{course_name}/{name}: {msg}"));
                    tracing::warn!(course = %course_name, exam = %name, error = %msg, "考试未通过");
                }
                Err(e) => {
                    failed.push(format!("{course_name}/{name}: {e}"));
                    tracing::warn!(course = %course_name, exam = %name, error = %e, "考试执行失败");
                }
            }
            // 考试之间同样按档位错峰（保守档会拉长到几十秒）
            profile.sleep_course_stagger().await;
        }
    }

    if total == 0 {
        tracing::info!(order_id = %task.order_id, "没有需要处理的考试");
        return Ok(());
    }
    if failed.is_empty() {
        tracing::info!(order_id = %task.order_id, total, passed = ok, "全部考试已完成");
        return Ok(());
    }
    anyhow::bail!("{} 场考试未完成（共 {} 场）：{}", failed.len(), total, failed.join("；"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_needs_exam_only_for_exam_and_full() {
        // 只有"考试"与"全包"订单才需要跑考试环节，纯视频订单不该多打平台请求
        assert!(needs_exam("exam"));
        assert!(needs_exam("full"));
        assert!(!needs_exam("video"));
        assert!(!needs_exam("chaoxing_points"));
        assert!(!needs_exam(""));
    }

    /// 时长缓存：同一节课第二次扫描必须命中，且站点前缀不同不许串台。
    ///
    /// 串台是这里唯一有破坏性的错误：三个平台同款软件、course_id/node_id
    /// 各自独立编号，key 里少了 base_url 就会把别校的时长当成自己的 ——
    /// 短了这节课永远刷不完，长了平台不认账，两种都是订单失败。
    #[test]
    fn test_duration_cache_key_isolates_platforms() {
        let a = duration_cache_key("https://p1.example.com/", "c1", "n1");
        let b = duration_cache_key("https://p2.example.com", "c1", "n1");
        assert_ne!(a, b, "不同站点的同名课程不能共用一条缓存");
        // 末尾斜杠不参与区分（同一站点的两种写法必须同 key）
        assert_eq!(a, duration_cache_key("https://p1.example.com", "c1", "n1"));

        let key = "https://cache-test.example.com#c#n";
        assert_eq!(duration_cache_get(key), None);
        duration_cache_put(key.to_string(), 273);
        assert_eq!(duration_cache_get(key), Some(273));
    }

    #[test]
    fn test_parse_duration() {
        assert_eq!(parse_duration_secs("00:00:02"), 2);
        assert_eq!(parse_duration_secs("01:05:30"), 3930);
        assert_eq!(parse_duration_secs("03:45"), 225);
        assert_eq!(parse_duration_secs("120"), 120);
        assert_eq!(parse_duration_secs(""), 0);
        assert_eq!(parse_duration_secs("abc"), 0);
    }

    /// 时长解析必须兼容"数字"形态。
    ///
    /// 回归背景：此前只走 `as_str()`，平台返回数字时静默兜底成 0，
    /// 导致扫描判"待刷"、刷课判"已完成"，收钱不干活还报 100%。
    #[test]
    fn test_duration_secs_of_accepts_number_and_string() {
        // 数字（最可能的线上形态）
        assert_eq!(duration_secs_of(&json!(630)), Some(630));
        assert_eq!(duration_secs_of(&json!(630.4)), Some(630));
        // 字符串：秒数 / MM:SS / HH:MM:SS
        assert_eq!(duration_secs_of(&json!("630")), Some(630));
        assert_eq!(duration_secs_of(&json!("03:45")), Some(225));
        assert_eq!(duration_secs_of(&json!("01:05:30")), Some(3930));
        // 拿不到可用时长 → None（**不能**退化成 0）
        assert_eq!(duration_secs_of(&json!(0)), None);
        assert_eq!(duration_secs_of(&json!("0")), None);
        assert_eq!(duration_secs_of(&json!("")), None);
        assert_eq!(duration_secs_of(&json!("abc")), None);
        assert_eq!(duration_secs_of(&json!(-5)), None);
        assert_eq!(duration_secs_of(&Value::Null), None);
    }

    /// 总时长必须取 `videoDuration`，**绝不能**取 `duration` 字段。
    ///
    /// 回归背景：线上实测 `duration` 字段等于已学秒数（与 viewedDuration 同义）。
    /// 一次真实事故：某节实际长 476s、已学 164s（平台进度 0.35），
    /// 但 `duration="164"` 被当成总长后，这一节被判"已看完"而整节跳过 ——
    /// 客户付了钱、平台上一节没动。
    #[test]
    fn test_meta_duration_prefers_video_duration_over_viewed_field() {
        // 线上原始条目（节选）：duration=已学秒数，videoDuration=总长
        let item = json!({"id": "1838789", "duration": "164", "videoDuration": "00:07:55",
                          "viewedDuration": "00:02:44"});
        assert_eq!(meta_duration_secs(&item), Some(475), "总长必须取 videoDuration");
        assert_eq!(viewed_secs(&item), 164, "已学取 viewedDuration");
        // 只有 duration（=已学）时，不能把已学当成总长
        assert_eq!(meta_duration_secs(&json!({"duration": "164"})), None);
        // videoDuration 缺失/为 0 → None（交给媒体探测），不能退化成已学秒数
        assert_eq!(meta_duration_secs(&json!({"videoDuration": "00:00:00"})), None);
        assert_eq!(meta_duration_secs(&json!({})), None);
    }

    /// 扫描侧与刷课侧必须对"是否已学"给出一致结论
    #[test]
    fn test_video_is_done_agrees_on_missing_duration() {
        let mk = |duration: Value, viewed: u64| crate::study::Video {
            node_id: "n1".into(),
            duration: duration.as_u64(),
            platform_duration: duration.as_u64(),
            platform_done: false,
            viewed_duration: viewed,
            local_file: None,
            name: "v".into(),
            course_id: "c".into(),
        };
        // 已看满 → 已学
        assert!(crate::study::video_is_done(&mk(json!(600), 600)));
        assert!(crate::study::video_is_done(&mk(json!(600), 700)));
        // 没看满 → 未学
        assert!(!crate::study::video_is_done(&mk(json!(600), 0)));
        // 时长未知 → **绝不算已学**（不知道就不许宣布完成）
        assert!(!crate::study::video_is_done(&mk(Value::Null, 0)));
        assert!(!crate::study::video_is_done(&mk(Value::Null, 999)));
    }

    /// 进度口径以平台为准：媒体探测把时长抬高后，"平台已学"的节不能被算成待刷
    #[test]
    fn test_video_is_done_uses_platform_length() {
        let mut v = crate::study::Video {
            node_id: "n1".into(),
            duration: Some(710),          // 文件真值（平台元数据失真时更长）
            platform_duration: Some(155), // 平台自己的元数据
            platform_done: false,
            viewed_duration: 160,
            local_file: None,
            name: "v".into(),
            course_id: "c".into(),
        };
        assert!(crate::study::video_is_done(&v), "平台显示已学 → 我们也要算已完成");
        v.viewed_duration = 100;
        assert!(!crate::study::video_is_done(&v), "平台还没看满 → 仍待刷");
        // 平台元数据缺失时退回校准值，结论不变
        v.platform_duration = None;
        assert!(!crate::study::video_is_done(&v));
        v.viewed_duration = 710;
        assert!(crate::study::video_is_done(&v));
    }

    /// 线上实测：平台 state 标"已学"、但 viewed 比 videoDuration 少 19 秒、
    /// 又比文件真值短得多 —— 这种节必须算已完成，否则进度永远少于平台页面
    #[test]
    fn test_video_is_done_follows_platform_state() {
        let raw = json!({
            "id": "1838899",
            "videoDuration": "00:14:44",
            "viewedDuration": "00:14:25",
            "state": "<span style=\"color: #2bbc66\">已学</span>",
        });
        let v = crate::study::Video {
            node_id: "1838899".into(),
            duration: Some(900),  // 媒体探测抬高后的真值
            platform_duration: meta_duration_secs(&raw),
            platform_done: raw["state"].as_str().map(|s| s.contains("已学")).unwrap_or(false),
            viewed_duration: viewed_secs(&raw),
            local_file: None,
            name: "5.2 科学运动".into(),
            course_id: "1023687".into(),
        };
        assert_eq!(v.platform_duration, Some(884));
        assert_eq!(v.viewed_duration, 865);
        assert!(crate::study::video_is_done(&v), "平台标已学的节必须算完成（与页面一致）");
        // 同一节若平台标的是"未学完"，则按数值判未完成
        let mut v2 = v.clone();
        v2.platform_done = false;
        v2.viewed_duration = 100;
        assert!(!crate::study::video_is_done(&v2));
    }

    /// 构造一个 version 0 的 mvhd 片段（线上实测就是这么排布的）
    fn mvhd_v0(timescale: u32, duration: u32) -> Vec<u8> {
        let mut b = b"\x00\x00\x00\x24ftypisom".to_vec();
        b.extend_from_slice(b"\x00\x00\x00\x6cmvhd");
        b.push(0);                       // version 0
        b.extend_from_slice(&[0, 0, 0]); // flags
        b.extend_from_slice(&0u32.to_be_bytes()); // creation
        b.extend_from_slice(&0u32.to_be_bytes()); // modification
        b.extend_from_slice(&timescale.to_be_bytes());
        b.extend_from_slice(&duration.to_be_bytes());
        b
    }

    /// 时长从视频文件读：平台列表接口不给时长，这是唯一的兜底来源。
    /// 取值必须与线上真实数据一致（timescale=1000, duration=209174 → 210s）。
    #[test]
    fn test_mp4_duration_from_mvhd() {
        assert_eq!(mp4_duration_secs(&mvhd_v0(1000, 209_174)), Some(210)); // 向上取整
        assert_eq!(mp4_duration_secs(&mvhd_v0(1000, 600_000)), Some(600));
        assert_eq!(mp4_duration_secs(&mvhd_v0(90_000, 90_000)), Some(1));
        // 没有 moov（比如取到的是纯媒体数据段）→ None，交给调用方换范围重试
        assert_eq!(mp4_duration_secs(b"\x00\x00\x00\x08mdat...."), None);
        // timescale/duration 为 0 → 不可用，不能返回 0 冒充"已看完"
        assert_eq!(mp4_duration_secs(&mvhd_v0(0, 1234)), None);
        assert_eq!(mp4_duration_secs(&mvhd_v0(1000, 0)), None);
        // 截断的字节流不能 panic
        assert_eq!(mp4_duration_secs(&mvhd_v0(1000, 1000)[..10]), None);
    }

    #[test]
    fn test_course_list_parse() {
        let html = r#"<html><body>
<div class="user-course">
  <div class="item">
    <div class="name"><a href="/user/node?courseId=101">高等数学</a></div>
    <div class="note"><div class="status"><a href="/user/study_record?courseId=101">学习记录</a></div></div>
  </div>
  <div class="item">
    <div class="name"><a href="/user/node?courseId=102">大学英语</a></div>
    <div class="note"><div class="status"><a href="/user/study_record?courseId=102">学习记录</a></div></div>
  </div>
</div>
<div class="other"><div class="item"><div class="name"><a href="/x?courseId=999">干扰项</a></div></div></div>
</body></html>"#;
        let courses = parse_course_list(html);
        assert_eq!(courses.len(), 2, "应解析出 2 门课程且过滤 user-course 外的干扰项: {:?}",
                   courses.iter().map(|c| (&c.name, &c.course_id)).collect::<Vec<_>>());
        assert_eq!(courses[0].name, "高等数学");
        assert_eq!(courses[0].course_id, "101");
        assert_eq!(courses[1].name, "大学英语");
        assert_eq!(courses[1].course_id, "102");
    }
}
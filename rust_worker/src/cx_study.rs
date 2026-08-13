//! 学习通必学/积分视频刷课 — 协议与 infrastructure/chaoxing/reporter.py 1:1 对齐
//!
//! 覆盖 Python 侧 process_knowledge_videos / play_video / report_progress /
//! get_enc_info / get_marg / get_video_info（每日积分视频与必学视频共用此协议）。
//!
//! TLS 语义对齐 Python：
//! - 会话请求（enc/marg/status）：reqwest native-tls（系统 TLS 栈）
//! - 进度上报：系统 TLS + 强制 HTTP/1.1（urllib 语义；CDN 对指纹/HTTP2 返回 403）

use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result};
use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};
use reqwest::Client;
use serde::Deserialize;
use serde_json::json;
use tokio::sync::Mutex;

const ENC_SECRET: &str = "d_yHJ!$pdA~5";
const VIDEO_REFERER: &str =
    "https://mooc1.chaoxing.com/ananas/modules/video/index.html?v=2025-0725-1842";
// 与 Python SPEED_PROFILES['fast'] 一致（chaoxing_worker 使用 speed='fast'）
const SPEED_FAST: &[(u64, (f64, f64))] =
    &[(60, (5.0, 10.0)), (300, (10.0, 20.0)), (600, (15.0, 30.0)), (99999, (20.0, 40.0))];

#[derive(Debug, Clone, Deserialize)]
pub struct CxPoint {
    pub cid: String, // course_id
    pub kid: String, // knowledge_id
    pub clid: String, // class_id
    #[serde(default)]
    pub name: String, // 知识点名称
}

#[derive(Debug, Deserialize)]
pub struct CxTaskInput {
    pub order_id: String,
    pub cookie_str: String,
    pub uid: String,
    #[serde(default)]
    pub fid: String,
    #[serde(default)]
    pub ua: String,
    #[serde(default)]
    pub course_name: String,
    pub points: Vec<CxPoint>,
    pub status_file: String,
    #[serde(default)]
    pub push_ws: bool,
}

fn now_ms() -> u128 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0)
}

fn calc_enc(clazz_id: &str, userid: &str, jobid: &str, object_id: &str,
            play_time: u64, duration: u64) -> String {
    let raw = format!(
        "[{}][{}][{}][{}][{}][{}][{}][0_{}]",
        clazz_id, userid, jobid, object_id,
        play_time * 1000, ENC_SECRET, duration * 1000, duration
    );
    format!("{:x}", md5::compute(raw.as_bytes()))
}

/// 上报专用客户端：系统 TLS + HTTP/1.1（urllib 语义）
fn make_report_client() -> Client {
    Client::builder()
        .danger_accept_invalid_certs(true)
        .http1_only()
        .build()
        .expect("构建上报 client 失败")
}

/// 会话客户端：系统 TLS（enc/marg/status 接口）
fn make_session_client(ua: &str) -> Client {
    Client::builder()
        .danger_accept_invalid_certs(true)
        .user_agent(if ua.is_empty() {
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36".to_string()
        } else {
            ua.to_string()
        })
        .build()
        .expect("构建会话 client 失败")
}

async fn get_enc_info(client: &Client, cookie: &str, uid: &str,
                      cid: &str, kid: &str, clid: &str) -> Result<(String, String)> {
    // 返回 (domain, classId)；enc 字段暂不参与后续请求（与 Python 一致：enc 仅返回未用）
    let url = format!(
        "https://tsjy.chaoxing.com/plaza/user/{}/{}/modify-node?classId={}&userId={}",
        cid, kid, clid, uid
    );
    let resp = client.get(&url)
        .header("Cookie", cookie)
        .header("Referer", format!("https://tsjy.chaoxing.com/plaza/knowledge-all?courseId={}", cid))
        .send().await
        .with_context(|| format!("获取enc失败 kid={kid}"))?;
    let data: serde_json::Value = resp.json().await.context("enc响应解析失败")?;
    if data["code"].as_i64() == Some(1) {
        let d = &data["data"];
        Ok((d["domain"].as_str().unwrap_or("").to_string(),
            d["classId"].as_str().unwrap_or(clid).to_string()))
    } else {
        anyhow::bail!("enc接口返回异常: {}", data["code"])
    }
}

async fn get_marg(client: &Client, cookie: &str, domain: &str, kid: &str,
                  cid: &str, clid: &str) -> Result<serde_json::Value> {
    let url = format!(
        "{}/mooc-ans/knowledge/cards?clazzid={}&courseid={}&knowledgeid={}",
        domain, clid, cid, kid
    );
    let resp = client.get(&url).header("Cookie", cookie).send().await
        .with_context(|| format!("获取mArg失败 kid={kid}"))?;
    let text = resp.text().await.context("mArg响应读取失败")?;
    // try{ mArg = {...}; 提取（与 Python 正则一致）
    let re = regex_lite(&text);
    match re {
        Some(v) => Ok(v),
        None => anyhow::bail!("mArg 未找到 kid={kid}"),
    }
}

fn regex_lite(text: &str) -> Option<serde_json::Value> {
    let start = text.find("mArg")?;
    let after = &text[start..];
    let brace = after.find('{')? + start;
    // 简单括号配对（mArg 结构无嵌套字符串花括号风险极低；失败则回退整段解析）
    let bytes = text.as_bytes();
    let mut depth = 0usize;
    let mut end = brace;
    for (i, &b) in bytes.iter().enumerate().skip(brace) {
        if b == b'{' { depth += 1; }
        else if b == b'}' {
            depth -= 1;
            if depth == 0 { end = i + 1; break; }
        }
    }
    serde_json::from_str(&text[brace..end]).ok()
}

async fn get_video_info(client: &Client, cookie: &str, fid: &str,
                        object_id: &str) -> Result<(u64, String)> {
    let url = format!(
        "https://mooc1-1.chaoxing.com/ananas/status/{}?k={}&flag=normal&ro=0&_dc={}",
        object_id, fid, now_ms()
    );
    let resp = client.get(&url)
        .header("Cookie", cookie)
        .header("Referer", VIDEO_REFERER)
        .send().await
        .with_context(|| format!("获取视频信息失败 object_id={object_id}"))?;
    if resp.status().as_u16() != 200 {
        anyhow::bail!("视频信息状态码 {}", resp.status());
    }
    let data: serde_json::Value = resp.json().await.context("视频信息解析失败")?;
    Ok((data["duration"].as_u64().unwrap_or(0),
        data["dtoken"].as_str().unwrap_or("").to_string()))
}

#[allow(clippy::too_many_arguments)]
async fn report_progress(client: &Client, cookie: &str, ua: &str,
                         uid: &str, cpi: &str, dtoken: &str,
                         clazz_id: &str, jobid: &str, object_id: &str,
                         duration: u64, play_time: u64, other_info: &str,
                         course_id: &str, is_drag: u64, report_url: &str) -> Result<serde_json::Value> {
    let enc = calc_enc(clazz_id, uid, jobid, object_id, play_time, duration);
    let mut params: HashMap<&str, String> = HashMap::new();
    params.insert("clazzId", clazz_id.to_string());
    params.insert("playingTime", play_time.to_string());
    params.insert("duration", duration.to_string());
    params.insert("clipTime", format!("0_{duration}"));
    params.insert("objectId", object_id.to_string());
    params.insert("otherInfo", other_info.to_string());
    params.insert("courseId", course_id.to_string());
    params.insert("jobid", jobid.to_string());
    params.insert("userid", uid.to_string());
    params.insert("isdrag", is_drag.to_string());
    params.insert("view", "pc".to_string());
    params.insert("enc", enc);
    params.insert("dtype", "Video".to_string());
    params.insert("rt", "0.9".to_string());
    params.insert("_t", now_ms().to_string());
    params.insert("attDuration", duration.to_string());
    params.insert("courseEngineInfo", "false".to_string());

    let base = if report_url.is_empty() {
        let mut u = format!("https://mooc1-1.chaoxing.com/mooc-ans/multimedia/log/a/{}", cpi);
        if !dtoken.is_empty() {
            u.push('/');
            u.push_str(dtoken);
        }
        u
    } else if !dtoken.is_empty() {
        format!("{}/{}", report_url.trim_end_matches('/'), dtoken)
    } else {
        report_url.to_string()
    };

    let mut last_err = String::from("未知错误");
    for attempt in 0..3u32 {
        let qs: String = params.iter()
            .map(|(k, v)| format!("{}={}", k, percent_encode(v)))
            .collect::<Vec<_>>().join("&");
        let full_url = format!("{}?{}", base, qs);
        match client.get(&full_url)
            .header("Cookie", cookie)
            .header("Referer", VIDEO_REFERER)
            .header("User-Agent", ua)
            .send().await
        {
            Ok(resp) => {
                let code = resp.status().as_u16();
                if code == 200 {
                    return resp.json().await.context("上报响应解析失败");
                } else if code == 403 {
                    last_err = "403".to_string();
                    if attempt < 2 {
                        tokio::time::sleep(Duration::from_secs(2)).await;
                    }
                } else {
                    last_err = format!("状态码 {code}");
                    anyhow::bail!("进度上报异常 {last_err}");
                }
            }
            Err(e) => {
                last_err = e.to_string();
                if attempt < 2 {
                    tokio::time::sleep(Duration::from_secs(1)).await;
                }
            }
        }
    }
    anyhow::bail!("进度上报重试失败: {last_err}")
}

fn percent_encode(s: &str) -> String {
    let mut out = String::with_capacity(s.len() * 3);
    for b in s.as_bytes() {
        match *b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(*b as char)
            }
            _ => out.push_str(&format!("%{:02X}", b)),
        }
    }
    out
}

fn calc_interval(duration: u64) -> f64 {
    let (lo, hi) = SPEED_FAST.iter()
        .find(|(t, _)| duration <= *t)
        .map(|(_, r)| r)
        .unwrap_or(&(30.0, 60.0));
    let mut rng = rand::thread_rng();
    rng.gen_range(*lo..*hi)
}

#[allow(clippy::too_many_arguments)]
async fn play_video(report_client: &Client,
                    cookie: &str, ua: &str, uid: &str, cpi: &str,
                    dtoken: &str, clazz_id: &str, jobid: &str,
                    object_id: &str, duration: u64, other_info: &str,
                    course_id: &str, report_url: &str) -> Result<bool> {
    // 首次上报 playingTime=0（初始化会话，浏览器行为；isdrag=3）
    match report_progress(report_client, cookie, ua, uid, cpi, dtoken, clazz_id, jobid,
                          object_id, duration, 0, other_info, course_id, 3, report_url).await {
        Ok(_) => {}
        Err(e) => anyhow::bail!("首次上报失败: {e}"),
    }

    let mut played: u64 = 0;
    let mut fail_streak = 0u32;
    // ThreadRng 不 Send（跨 await 会破坏 tokio::spawn），用 StdRng
    let mut rng = StdRng::from_entropy();

    while played < duration {
        let interval = calc_interval(duration);
        let jitter_lo = ((interval * 0.7) as u64).max(1);
        let jitter_hi = ((interval * 1.3) as u64).max(jitter_lo + 1);
        let next_time = (played + rng.gen_range(jitter_lo..jitter_hi)).min(duration - 1);
        let is_drag: u64 = if next_time >= duration.saturating_sub(2) { 4 } else { 0 };

        match report_progress(report_client, cookie, ua, uid, cpi, dtoken, clazz_id, jobid,
                              object_id, duration, next_time, other_info, course_id,
                              is_drag, report_url).await {
            Ok(resp) => {
                fail_streak = 0;
                if resp["isPassed"].as_bool().unwrap_or(false) {
                    return Ok(true);
                }
            }
            Err(_) => {
                fail_streak += 1;
                if fail_streak >= 3 {
                    anyhow::bail!("连续3次上报失败");
                }
            }
        }

        played = next_time;
        if is_drag == 4 {
            break;
        }
        let wait = interval * rng.gen_range(0.5..0.8);
        tokio::time::sleep(Duration::from_secs_f64(wait)).await;
    }
    Ok(true)
}

struct CxProgress {
    total: u64,
    done: u64,
    failed: u64,
}

async fn write_cx_status(status_file: &str, course_name: &str,
                         progress: &Mutex<CxProgress>, phase: &str,
                         message: &str, done_flag: Option<bool>, success: Option<bool>) {
    let p = progress.lock().await;
    let mut map = serde_json::Map::new();
    map.insert("phase".into(), phase.into());
    map.insert("course_name".into(), course_name.into());
    map.insert("study_total".into(), p.total.into());
    map.insert("study_done".into(), p.done.into());
    map.insert("study_failed".into(), p.failed.into());
    map.insert("message".into(), message.into());
    map.insert("updated_at".into(), json!(now_ms() as f64 / 1000.0));
    if let Some(d) = done_flag {
        map.insert("done".into(), d.into());
    }
    if let Some(s) = success {
        map.insert("success".into(), s.into());
    }
    let body = serde_json::Value::Object(map).to_string();
    let tmp = format!("{}.tmp", status_file);
    if tokio::fs::write(&tmp, body).await.is_ok() {
        let _ = tokio::fs::rename(&tmp, status_file).await;
    }
}

/// 处理单个知识点的全部视频（对应 Python process_knowledge_videos）
async fn process_point(session_client: &Client, report_client: &Client,
                       cookie: &str, ua: &str, uid: &str,
                       point: &CxPoint, progress: &Mutex<CxProgress>) -> Result<u64> {
    let _ = progress; // 进度统计由调用方维护（与 Python on_progress 回调一致）
    let (domain, clazz_id) = get_enc_info(session_client, cookie, uid,
                                          &point.cid, &point.kid, &point.clid).await?;
    let marg = get_marg(session_client, cookie, &domain, &point.kid, &point.cid, &clazz_id).await?;
    let defaults = marg.get("defaults").cloned().unwrap_or_default();
    let cpi = defaults["cpi"].as_str().unwrap_or("").to_string();
    let report_url = defaults["reportUrl"].as_str().unwrap_or("").to_string();
    let ktoken = defaults["ktoken"].as_str().unwrap_or("").to_string();

    let attachments = marg["attachments"].as_array().cloned().unwrap_or_default();
    let video_tasks: Vec<serde_json::Value> = attachments.into_iter()
        .filter(|a| a["type"].as_str() == Some("video") && !a["isPassed"].as_bool().unwrap_or(false))
        .collect();
    if video_tasks.is_empty() {
        return Ok(0);
    }

    let mut played_count = 0u64;
    for task in &video_tasks {
        let jobid = task["jobid"].as_str().unwrap_or("").to_string();
        let prop = task.get("property").cloned().unwrap_or_default();
        let object_id = task["objectId"].as_str().unwrap_or("")
            .to_string();
        let object_id = if object_id.is_empty() {
            prop["objectid"].as_str().unwrap_or("").to_string()
        } else {
            object_id
        };
        if object_id.is_empty() {
            continue;
        }
        let mut duration = task["attDuration"].as_u64().unwrap_or(0);
        if duration == 0 {
            if let Ok((d, _)) = get_video_info(session_client, cookie, "", &object_id).await {
                duration = d;
            }
        }
        if duration == 0 {
            anyhow::bail!("无法获取时长 object_id={object_id}");
        }
        let (_, mut dtoken) = get_video_info(session_client, cookie, "", &object_id)
            .await
            .unwrap_or((0, String::new()));
        if dtoken.is_empty() {
            dtoken = ktoken.clone();
        }
        let other_info = task["otherInfo"].as_str().unwrap_or("").split('&').next().unwrap_or("").to_string();

        match play_video(report_client, cookie, ua, uid, &cpi, &dtoken,
                         &clazz_id, &jobid, &object_id, duration, &other_info,
                         &point.cid, &report_url).await {
            Ok(_) => played_count += 1,
            Err(e) => {
                eprintln!("[cx_study] 视频播放失败 kid={} err={}", point.kid, e);
                let mut p = progress.lock().await;
                p.failed += 1;
                drop(p);
            }
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
    Ok(played_count)
}

pub async fn run_cx_study(task: &CxTaskInput, push_url: &str,
                          push_token: &str) -> Result<()> {
    let session_client = make_session_client(&task.ua);
    let report_client = make_report_client();
    let progress = Arc::new(Mutex::new(CxProgress {
        total: task.points.len() as u64,
        done: 0,
        failed: 0,
    }));
    let total = task.points.len() as u64;

    write_cx_status(&task.status_file, &task.course_name, &progress, "study_must_learn",
                    &format!("[{}] 开始刷必学/积分视频 (共{}个知识点)", task.course_name, total),
                    None, None).await;

    let mut done_total = 0u64;
    let mut failed_total = 0u64;
    for (i, point) in task.points.iter().enumerate() {
        let kname = point.name.clone();
        write_cx_status(&task.status_file, &task.course_name, &progress, "study_must_learn",
                        &format!("[{}] 必学 {}/{}: {}",
                                 task.course_name, i + 1, total,
                                 truncate(&kname, 30)),
                        None, None).await;

        match process_point(&session_client, &report_client, &task.cookie_str,
                            &task.ua, &task.uid, point, &progress).await {
            Ok(played) => {
                if played > 0 {
                    done_total += 1;
                }
                {
                    let mut p = progress.lock().await;
                    p.done = done_total;
                    p.failed = failed_total;
                }
                write_cx_status(&task.status_file, &task.course_name, &progress,
                                "study_must_learn",
                                &format!("[{}] {} 完成", task.course_name, truncate(&kname, 20)),
                                None, None).await;
            }
            Err(e) => {
                failed_total += 1;
                {
                    let mut p = progress.lock().await;
                    p.failed = failed_total;
                }
                eprintln!("[cx_study] 知识点处理失败 kid={} err={}", point.kid, e);
                write_cx_status(&task.status_file, &task.course_name, &progress,
                                "study_must_learn",
                                &format!("[{}] {} 失败: {}", task.course_name,
                                         truncate(&kname, 20), e),
                                None, None).await;
            }
        }

        // WS 推送进度
        if task.push_ws {
            let p = progress.lock().await;
            let _ = session_client.post(push_url)
                .header("Content-Type", "application/json")
                .header("X-Worker-Token", push_token)
                .json(&json!({
                    "type": "progress",
                    "phase": "study_must_learn",
                    "study_done": p.done,
                    "study_total": p.total,
                    "message": format!("[{}] {}", task.course_name, truncate(&kname, 20)),
                }))
                .timeout(Duration::from_secs(2))
                .send().await;
        }
    }

    let success = failed_total == 0;
    write_cx_status(&task.status_file, &task.course_name, &progress, "done",
                    &format!("学习通视频刷课完成 done={done_total} failed={failed_total}"),
                    Some(true), Some(success)).await;
    eprintln!("[cx_study] 任务完成 order_id={} done={done_total} failed={failed_total}",
              task.order_id);
    if !success {
        anyhow::bail!("部分知识点失败 {failed_total}");
    }
    Ok(())
}

fn truncate(s: &str, n: usize) -> String {
    let chars: Vec<char> = s.chars().take(n).collect();
    chars.into_iter().collect()
}

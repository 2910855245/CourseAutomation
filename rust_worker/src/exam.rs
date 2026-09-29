//! 考试 AI 答题（Rust 版）— 协议对齐 services/ai_service.py + exam_fetcher.py + exam_answerer.py
//!
//! solve_exam：心跳保活 → 开始作业 → 抓题 → DeepSeek 逐题作答（带题缓存）→
//! 逐题提交(失败重试) → 验证重试 → 空答案拒绝交卷 → final_submit 交卷。
//! 测试钩子：DEEPSEEK_BASE_URL 环境变量覆盖（mock E2E 用）。

use anyhow::{bail, Context, Result};
use dashmap::DashMap;
use rand::RngExt;
use regex::Regex;
use reqwest::Client;
use serde_json::{json, Value};
use std::sync::LazyLock;

use crate::llm::{confidence_heuristic, ChatRequest, LlmClient};

fn make_client() -> Client {
    crate::platform_client::build_client_with_ua(
        crate::platform_client::SHORT_UA, false, None)
}

/// 题级答案缓存（对齐 AIAnswerer._cache：key = 题干前 100 字符）
static ANSWER_CACHE: LazyLock<DashMap<String, String>> = LazyLock::new(DashMap::new);

/// 置信度低于该值时触发思考模式复核。
/// 0.6 取自启发式的"不确定"档（confidence_heuristic 里格式可疑的选择题就是 0.6），
/// 也就是"格式没对上、模型多半在蒙"的那些题。
const REVIEW_THRESHOLD: f64 = 0.6;

/// 低置信度复核：用思考模式重算一题（思考模式下官方不支持 logprobs，
/// 所以不做二次比较，复核给出非空答案就采纳）。None = 复核失败，保留首次答案。
async fn review_low_confidence(llm: &LlmClient, model: &str, topic: &Value) -> Option<(String, f64)> {
    match ask_deepseek_with(llm, model, topic, Some(true)).await {
        Ok((ans, conf)) if !ans.is_empty() => Some((ans, conf)),
        Ok(_) => None,
        Err(e) => {
            tracing::warn!(error = %e, "低置信度复核失败，保留首次答案");
            None
        }
    }
}

/// DeepSeek 单题调用（对齐 AIAnswerer.ask_one_topic：
/// temperature=0.1, max_tokens=1024, logprobs=true/top_logprobs=5）
/// 返回 (answer, confidence)
pub async fn ask_deepseek(llm: &LlmClient, model: &str, topic: &Value) -> Result<(String, f64)> {
    ask_deepseek_with(llm, model, topic, None).await
}

/// 同上，但可显式指定是否走思考模式（None=由模型名语义决定）
pub async fn ask_deepseek_with(llm: &LlmClient, model: &str, topic: &Value,
                               thinking: Option<bool>) -> Result<(String, f64)> {
    let q_type = topic["q_type"].as_str().unwrap_or("");
    let is_choice = q_type.contains("单选") || q_type.contains("多选") || q_type.contains("判断");
    let prompt = build_prompt(topic);
    // logprobs 用于置信度；解析失败由 llm 内部重试（429/5xx/空响应）
    let mut req = ChatRequest::new("exam", model, &prompt)
        .temperature(0.1)
        .max_tokens(1024)
        .logprobs(true);
    if let Some(t) = thinking {
        req = req.thinking(t);
    }
    let reply = llm.chat(req).await?;
    let answer = extract_answer(&reply.content, is_choice);
    // 置信度：优先 logprobs（chat 内部已算），拿不到走启发式（对齐 _calc_confidence）
    let mut confidence = reply.confidence;
    if confidence <= 0.0 {
        confidence = confidence_heuristic(&answer, is_choice);
    }
    Ok((answer, confidence))
}

/// 构造 prompt（对齐 _build_prompt 的模板）
fn build_prompt(topic: &Value) -> String {
    let question = topic["question"].as_str().unwrap_or("");
    let q_type = topic["q_type"].as_str().unwrap_or("");
    let options: Vec<String> = topic["options"].as_array().cloned().unwrap_or_default()
        .iter().filter_map(|o| o.as_str()).map(|s| s.to_string()).collect();
    let is_choice = q_type.contains("单选") || q_type.contains("多选") || q_type.contains("判断");

    let lang_keywords = ["C语言", "c语言", "C++", "c++", "Python", "python", "Java", "java",
                         "JavaScript", "javascript", "Go", "golang", "Rust", "rust",
                         "编程", "代码", "程序", "算法", "函数", "循环", "数组"];
    let is_programming = lang_keywords.iter().any(|kw| question.contains(kw));

    let type_hint = if q_type.contains("多选") {
        "这是一道多选题，有多个正确答案。请仔细分析每个选项，返回所有正确选项的字母（如 ABC、ABD），不要解释。注意：多选少选均不得分。"
    } else if q_type.contains("判断") {
        "这是一道判断题，A表示正确，B表示错误，只返回一个字母。请仔细分析题干中的关键词。"
    } else if is_choice {
        "这是一道单选题，请仔细分析所有选项后返回最准确的答案字母（如 A/B/C/D），不要解释。"
    } else if is_programming {
        "这是一道编程题，请直接返回完整的代码实现（包含必要的注释），不要只给答案。代码要能直接运行。"
    } else {
        "这是一道填空/简答题，请直接返回答案内容（不要返回选项字母），简洁作答，不要解释。"
    };

    if options.is_empty() {
        format!("{type_hint}\n\n题目：{question}\n\n答案：")
    } else {
        format!("{type_hint}\n\n题目：{question}\n\n选项：\n{}\n\n答案：", options.join("\n"))
    }
}

/// 从 AI 响应提取答案（对齐 _extract_answer：选择题取字母，其余去代码块/前缀取内容）
fn extract_answer(content: &str, is_choice: bool) -> String {
    if !is_choice {
        // 去掉代码块标记 ```lang ... ```
        let text = Regex::new(r"(?s)^```\w*\s*\n?").unwrap()
            .replace(content.trim(), "").to_string();
        let text = Regex::new(r"\n?```\s*$").unwrap().replace(&text, "").to_string();
        let text = text.trim().trim_matches('"').trim_matches('\'');
        // 去掉可能的 "答案：" 前缀
        let text = Regex::new(r"^答案[：:]\s*").unwrap().replace(text, "").to_string();
        return if text.is_empty() {
            content.chars().take(5000).collect()
        } else {
            text.chars().take(5000).collect()
        };
    }
    // 多选答案：如 "ABC"、"A B C"、"A、B、C"（对齐 Python findall [A-Ha-h]）
    let letters: Vec<char> = content.chars()
        .filter(|c| c.is_ascii_alphabetic() && matches!(c.to_ascii_uppercase(), 'A'..='H'))
        .collect();
    if letters.len() > 1 {
        return letters.iter().collect::<String>().to_uppercase();
    }
    if let Some(c) = letters.first() {
        return c.to_ascii_uppercase().to_string();
    }
    content.chars().take(50).collect()
}

/// 在线心跳（对齐 OnlineHeartbeat：GET {base}/user/online，随机 15~25s 间隔）
struct OnlineHeartbeat {
    handle: tokio::task::JoinHandle<()>,
}

impl OnlineHeartbeat {
    fn start(client: Client, cookie: String, base_url: String) -> Self {
        let handle = tokio::spawn(async move {
            let url = format!("{}/user/online", base_url.trim_end_matches('/'));
            loop {
                match client.get(&url).header("Cookie", &cookie)
                    .timeout(std::time::Duration::from_secs(10))
                    .send().await
                {
                    Ok(r) if r.status().as_u16() == 200 => tracing::debug!("心跳成功"),
                    Ok(r) => tracing::warn!(status = r.status().as_u16(), "心跳异常"),
                    Err(e) => tracing::warn!(error = %e, "心跳失败"),
                }
                // 对齐 Python random.uniform(15, 25)
                let secs = rand::rng().random_range(15..=25);
                tokio::time::sleep(std::time::Duration::from_secs(secs)).await;
            }
        });
        Self { handle }
    }
}

impl Drop for OnlineHeartbeat {
    fn drop(&mut self) {
        self.handle.abort();
    }
}

/// 抓题（对齐 TopicFetcher.fetch：start_work 双端点回退 → 页面 → 解析 topics）
async fn fetch_topics(client: &Client, cookie: &str, base_url: &str,
                      work_id: &str, course_id: &str, node_id: &str,
                      item_type: &str) -> Result<(Vec<Value>, String)> {
    let base = base_url.trim_end_matches('/');
    // start_work（对齐 Python：按类型决定 exam/work 端点尝试顺序，status 为真即采纳）
    let (first, second) = if item_type == "exam" {
        (("/user/exam/start", "examId"), ("/user/work/start", "workId"))
    } else {
        (("/user/work/start", "workId"), ("/user/exam/start", "examId"))
    };
    let mut data = json!({});
    for (endpoint, id_key) in [first, second] {
        let resp = client.post(format!("{base}{endpoint}"))
            .header("Cookie", cookie)
            .header("X-Requested-With", "XMLHttpRequest")
            .form(&[(id_key, work_id.to_string()),
                    ("courseId", course_id.to_string()),
                    ("nodeId", node_id.to_string())])
            .send().await
            .context("开始作业请求失败")?;
        let d: Value = resp.json().await.context("开始作业响应解析失败")?;
        if d["status"].as_bool() == Some(true) {
            data = d;
            break;
        }
        // 已删除/已结束的直接报错，不浪费时间获取页面
        let msg = d["msg"].as_str().unwrap_or("");
        if msg.contains("已删除") || msg.contains("已结束") || msg.contains("已经结束") || msg.contains("不存在") {
            bail!("开始作业失败: {msg}");
        }
        data = d;
    }

    let mut submit_type = if item_type == "exam" { "exam" } else { "work" }.to_string();

    let page_url = data["url"].as_str().unwrap_or("").to_string();
    let html = if page_url.is_empty() {
        let url = format!("{base}/user/work?workId={work_id}&courseId={course_id}&nodeId={node_id}");
        client.get(&url).header("Cookie", cookie).send().await
            .context("获取作业页面失败")?.text().await.unwrap_or_default()
    } else {
        let url = if page_url.starts_with('/') { format!("{base}{page_url}") } else { page_url };
        client.get(&url).header("Cookie", cookie).send().await
            .context("获取作业页面失败")?.text().await.unwrap_or_default()
    };
    if html.contains("/exam/") || html.contains("examId") {
        submit_type = "exam".to_string();
    }
    Ok((parse_topics(&html), submit_type))
}

/// 解析题目（对齐 exam_fetcher._parse_topics_from_forms：
/// form 结构解析 + <p> 题干拼接 + uploader-btn 项目题检测）
fn parse_topics(html: &str) -> Vec<Value> {
    use scraper::{Html, Selector};
    let doc = Html::parse_document(html);
    let form_sel = Selector::parse("form").unwrap();

    // 页面级文件上传按钮（项目提交题型特征）
    let has_uploader = doc.select(&Selector::parse("a.uploader-btn").unwrap()).next().is_some();

    let mut topics = Vec::new();
    for form in doc.select(&form_sel) {
        let action = form.value().attr("action").unwrap_or("");
        if !action.contains("submit") {
            continue;
        }
        let num = form.select(&Selector::parse(".num span").unwrap()).next()
            .map(|e| e.text().collect::<String>().trim().parse::<i64>().unwrap_or(0))
            .unwrap_or(0);
        let name_el = match form.select(&Selector::parse(".name").unwrap()).next() {
            Some(e) => e,
            None => continue,
        };
        // 题目文本（input 替换为 _____，剥标签）
        let name_html = name_el.html();
        let name_html = Regex::new(r#"<input[^>]*class="exam-input"[^>]*/?>"#).unwrap()
            .replace_all(&name_html, " _____ ").to_string();
        let question = Regex::new(r"<[^>]+>").unwrap().replace_all(&name_html, "");
        let question = Regex::new(r"\s+").unwrap().replace_all(&question, " ").trim().to_string();
        if question.is_empty() {
            continue;
        }

        // 拼接 <p> 中的补充要求（对齐 Python question_parts 逻辑）
        let mut question_parts = vec![question.clone()];
        for p in form.select(&Selector::parse("p").unwrap()) {
            let t = p.text().collect::<String>().trim().to_string();
            if !t.is_empty() && !question.contains(&t) {
                question_parts.push(t);
            }
        }
        let full_question = question_parts.join("\n");

        let mut options = Vec::new();
        if let Some(list_el) = form.select(&Selector::parse(".list").unwrap()).next() {
            for label in list_el.select(&Selector::parse("label").unwrap()) {
                let t = label.text().collect::<String>().trim().to_string();
                if !t.is_empty() {
                    options.push(t);
                }
            }
        }
        let q_type = form.select(&Selector::parse(".type").unwrap()).next()
            .map(|e| e.text().collect::<String>().trim().to_string())
            .unwrap_or_default();
        let is_choice = q_type.contains("单选") || q_type.contains("多选") || q_type.contains("判断");

        // 项目提交题（简答 + 文件上传特征）
        let is_project = has_uploader
            && (q_type.contains("简答") || full_question.contains("上传")
                || full_question.contains("压缩") || full_question.contains("提交"));

        // answer_id：topic-head data-id 或题号
        let head_id = form.select(&Selector::parse(".topic-head").unwrap()).next()
            .and_then(|a| a.value().attr("data-id"))
            .unwrap_or("");
        let answer_id = if head_id.is_empty() { num.to_string() } else { head_id.to_string() };

        let blank_count = form.select(&Selector::parse("input.exam-input").unwrap()).count();

        let topic_type = if is_project {
            "project"
        } else if is_choice {
            "choice"
        } else {
            "text"
        };

        topics.push(json!({
            "number": num,
            "topic_id": answer_id,
            "answer_id": answer_id,
            "question": full_question,
            "options": options,
            "q_type": q_type,
            "type": topic_type,
            "blank_count": blank_count,
        }));
    }
    topics
}

/// 构造提交表单字段（对齐 WorkSubmitter.submit_topic：
/// 多选 answer[] 重复键 / 填空 answer_N 按 `,` 拆分 / 其余单 answer 键）
fn build_submit_pairs(work_id: &str, answer_id: &str, answer: &str,
                      q_type: &str, blank_count: usize, submit_type: &str,
                      node_id: &str) -> Vec<(String, String)> {
    let id_key = if submit_type == "exam" { "examId" } else { "workId" };
    let mut pairs: Vec<(String, String)> = vec![
        ("answerId".into(), answer_id.to_string()),
        (id_key.into(), work_id.to_string()),
    ];
    if q_type.contains("多选") && answer.len() > 1 {
        for ch in answer.chars().filter(|c| matches!(c.to_ascii_uppercase(), 'A'..='H')) {
            pairs.push(("answer[]".into(), ch.to_ascii_uppercase().to_string()));
        }
    } else if q_type.contains("填空") && blank_count > 0 {
        // 对齐 Python：answer.split(',') 逐空填充，不足用最后一段/原答案补齐
        let parts: Vec<String> = answer.split(',')
            .map(|p| p.trim().to_string())
            .filter(|p| !p.is_empty())
            .collect();
        for i in 0..blank_count {
            let val = parts.get(i).cloned()
                .or_else(|| parts.last().cloned())
                .unwrap_or_else(|| answer.to_string());
            pairs.push((format!("answer_{}", i + 1), val));
        }
    } else {
        pairs.push(("answer".into(), answer.to_string()));
    }
    if submit_type == "exam" && !node_id.is_empty() {
        pairs.push(("nodeId".into(), node_id.to_string()));
    }
    pairs
}

/// 提交单题（对齐 WorkSubmitter.submit_topic）
async fn submit_topic(client: &Client, cookie: &str, base_url: &str,
                      work_id: &str, answer_id: &str, answer: &str,
                      q_type: &str, blank_count: usize, submit_type: &str,
                      node_id: &str) -> Result<Value> {
    let base = base_url.trim_end_matches('/');
    let url = if submit_type == "exam" {
        format!("{base}/user/exam/submit")
    } else {
        format!("{base}/user/work/submit")
    };
    let pairs = build_submit_pairs(work_id, answer_id, answer, q_type,
                                   blank_count, submit_type, node_id);
    let resp = client.post(&url)
        .header("Cookie", cookie)
        .header("X-Requested-With", "XMLHttpRequest")
        .header("Referer", base)
        .form(&pairs)
        .send().await
        .context("提交答案请求失败")?;
    let body = resp.text().await.unwrap_or_default();
    if body.trim().is_empty() {
        return Ok(json!({"status": false, "msg": "服务器返回空响应"}));
    }
    serde_json::from_str(&body).or_else(|_| Ok(json!({"status": false, "msg": "响应非JSON"})))
}

/// 交卷（对齐 WorkSubmitter.final_submit：finish=1 + 最后一题的答案字段）
async fn final_submit(client: &Client, cookie: &str, base_url: &str,
                      work_id: &str, answer_id: &str, answer: &str,
                      q_type: &str, blank_count: usize, submit_type: &str,
                      node_id: &str) -> Result<Value> {
    let base = base_url.trim_end_matches('/');
    let url = if submit_type == "exam" {
        format!("{base}/user/exam/submit")
    } else {
        format!("{base}/user/work/submit")
    };
    let id_key = if submit_type == "exam" { "examId" } else { "workId" };
    let mut pairs: Vec<(String, String)> = vec![
        (id_key.into(), work_id.to_string()),
        ("finish".into(), "1".into()),
    ];
    if !answer_id.is_empty() {
        pairs.push(("answerId".into(), answer_id.to_string()));
    }
    if !answer.is_empty() {
        if q_type.contains("填空") && blank_count > 0 {
            let parts: Vec<String> = answer.split(',')
                .map(|p| p.trim().to_string())
                .filter(|p| !p.is_empty())
                .collect();
            for i in 0..blank_count {
                let val = parts.get(i).cloned()
                    .or_else(|| parts.last().cloned())
                    .unwrap_or_else(|| answer.to_string());
                pairs.push((format!("answer_{}", i + 1), val));
            }
        } else {
            pairs.push(("answer".into(), answer.to_string()));
        }
    }
    if submit_type == "exam" && !node_id.is_empty() {
        pairs.push(("nodeId".into(), node_id.to_string()));
    }
    let resp = client.post(&url)
        .header("Cookie", cookie)
        .header("X-Requested-With", "XMLHttpRequest")
        .header("Referer", base)
        .form(&pairs)
        .send().await
        .context("交卷请求失败")?;
    let body = resp.text().await.unwrap_or_default();
    if body.trim().is_empty() {
        return Ok(json!({"status": false, "msg": "服务器返回空响应"}));
    }
    serde_json::from_str(&body).or_else(|_| Ok(json!({"status": false, "msg": "响应非JSON"})))
}

/// 完整答题（对齐 ai_service.solve_exam 全流程）
/// `thinking`：None=按模型名语义决定；Some(true/false)=强制开关思考模式。
/// 低置信度复核（见 review_low_confidence）只在第一次作答置信度 < 0.6 时触发。
pub async fn solve_exam(base_url: &str, cookie_str: &str,
                        work_id: &str, course_id: &str, node_id: &str,
                        api_key: &str, model: &str,
                        item_type: &str, thinking: Option<bool>) -> Result<Value> {
    if api_key.is_empty() {
        bail!("DEEPSEEK_API_KEY 未配置");
    }
    let client = make_client();
    let llm = LlmClient::new(api_key, "");

    // 心跳保活（离开作用域自动 abort，对齐 heartbeat.start/stop）
    let _heartbeat = OnlineHeartbeat::start(
        client.clone(), cookie_str.to_string(), base_url.to_string());

    let (topics, submit_type) = fetch_topics(&client, cookie_str, base_url,
                                             work_id, course_id, node_id, item_type).await?;
    if topics.is_empty() {
        bail!("未获取到题目");
    }
    tracing::info!(work_id, total = topics.len(), "开始 AI 答题");

    // 逐题 AI 作答（带题级缓存，对齐 AIAnswerer._cache）
    let mut answers: Vec<(String, String)> = Vec::new(); // (answer_id, answer)
    let mut reviewed = 0usize;
    for topic in &topics {
        let answer_id = topic["answer_id"].as_str().unwrap_or("").to_string();
        let cache_key: String = topic["question"].as_str().unwrap_or("")
            .chars().take(100).collect();
        if let Some(cached) = ANSWER_CACHE.get(&cache_key) {
            tracing::info!(answer_id, "命中题缓存");
            answers.push((answer_id, cached.clone()));
            continue;
        }
        let mut answer = String::new();
        let mut confidence = 0.0f64;
        for _attempt in 0..3 {
            match ask_deepseek_with(&llm, model, topic, thinking).await {
                Ok((ans, conf)) => {
                    answer = ans;
                    confidence = conf;
                    if !answer.is_empty() {
                        break;
                    }
                }
                Err(e) => tracing::warn!(error = %e, "AI 调用失败"),
            }
            tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        }
        // 低置信度复核：快模型答得没把握时，用思考模式再算一遍（仅此一处额外开销）
        if !answer.is_empty() && confidence < REVIEW_THRESHOLD && thinking != Some(true) {
            if let Some((better, _)) = review_low_confidence(&llm, model, topic).await {
                if !better.is_empty() {
                    tracing::info!(number = %topic["number"], from = %answer, to = %better,
                                   confidence, "低置信度已由思考模式复核");
                    reviewed += 1;
                    answer = better;
                }
            }
        }
        if answer.is_empty() {
            tracing::warn!(number = %topic["number"], "AI 未返回答案");
        } else {
            ANSWER_CACHE.insert(cache_key, answer.clone());
        }
        tracing::info!(number = %topic["number"], answer = %answer, confidence,
                       "第{}题作答完成", topic["number"]);
        answers.push((answer_id, answer));
        tokio::time::sleep(std::time::Duration::from_millis(300)).await;
    }
    if reviewed > 0 {
        tracing::info!(reviewed, "低置信度复核完成");
    }

    // 逐题提交（空答案跳过，失败重试 3 次）
    let mut submitted = 0usize;
    let mut skipped = 0usize;
    let mut failed_aids: Vec<String> = Vec::new();
    for (topic, (answer_id, answer)) in topics.iter().zip(answers.iter()) {
        let q_type = topic["q_type"].as_str().unwrap_or("").to_string();
        let blank_count = topic["blank_count"].as_u64().unwrap_or(0) as usize;
        if answer.is_empty() {
            skipped += 1;
            tracing::warn!(answer_id, "跳过：AI 未返回答案");
            continue;
        }
        let mut ok = false;
        for attempt in 0..3 {
            let r = submit_topic(&client, cookie_str, base_url, work_id,
                                 answer_id, answer, &q_type, blank_count,
                                 &submit_type, node_id).await?;
            if r["status"].as_bool() != Some(false) {
                ok = true;
                break;
            }
            tracing::warn!(answer_id, attempt, msg = %r["msg"].as_str().unwrap_or(""), "提交失败");
            tokio::time::sleep(std::time::Duration::from_secs(1)).await;
        }
        if ok {
            submitted += 1;
        } else {
            tracing::error!(answer_id, "提交最终失败");
            failed_aids.push(answer_id.clone());
        }
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    }

    // 提交失败的题目重试一轮（对齐 solve_exam 的验证+重试段）
    if !failed_aids.is_empty() {
        tracing::info!(count = failed_aids.len(), "重试失败题目");
        let mut still_failed = Vec::new();
        for aid in &failed_aids {
            let (topic, (_, answer)) = topics.iter().zip(answers.iter())
                .find(|(_, (a, _))| a == aid)
                .map(|(t, x)| (t, x.clone()))
                .unwrap();
            if answer.is_empty() {
                continue;
            }
            let q_type = topic["q_type"].as_str().unwrap_or("").to_string();
            let blank_count = topic["blank_count"].as_u64().unwrap_or(0) as usize;
            let mut ok = false;
            for _attempt in 0..3 {
                let r = submit_topic(&client, cookie_str, base_url, work_id,
                                     aid, &answer, &q_type, blank_count,
                                     &submit_type, node_id).await?;
                if r["status"].as_bool() != Some(false) {
                    submitted += 1;
                    ok = true;
                    break;
                }
                tokio::time::sleep(std::time::Duration::from_secs(1)).await;
            }
            if !ok {
                still_failed.push(aid.clone());
            }
        }
        failed_aids = still_failed;
    }

    // 有题目被跳过（AI 未返回答案）→ 拒绝交卷
    if skipped > 0 {
        tracing::error!(skipped, "有题目 AI 未返回答案，拒绝交卷");
        return Ok(json!({
            "success": false,
            "submitted": submitted,
            "total": topics.len(),
            "skipped": skipped,
            "final": Value::Null,
            "error": format!("AI未返回{skipped}道题的答案，拒绝交卷"),
        }));
    }

    // 交卷（finish=1，带最后一题答案）
    let (last_aid, last_answer) = answers.last()
        .map(|(a, b)| (a.clone(), b.clone()))
        .unwrap_or_default();
    let last_topic = topics.last().cloned().unwrap_or(json!({}));
    let last_q_type = last_topic["q_type"].as_str().unwrap_or("");
    let last_blank = last_topic["blank_count"].as_u64().unwrap_or(0) as usize;
    let final_ans = if last_answer.is_empty() { "A".to_string() } else { last_answer };
    let final_ret = final_submit(&client, cookie_str, base_url, work_id,
                                 &last_aid, &final_ans, last_q_type, last_blank,
                                 &submit_type, node_id).await?;
    tracing::info!(result = %final_ret, "交卷结果");

    let success = submitted > 0 && final_ret["status"].as_bool() != Some(false);
    Ok(json!({
        "success": success,
        "submitted": submitted,
        "total": topics.len(),
        "failed": failed_aids.len(),
        "final": final_ret,
        "error": if success { Value::Null } else if submitted > 0 {
            json!(format!("提交{}/{}题，交卷失败", submitted, topics.len()))
        } else {
            json!("全部题目提交失败")
        },
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_build_prompt() {
        let t = json!({"question": "1+1=?", "options": ["A. 1", "B. 2"], "q_type": "单选题"});
        let p = build_prompt(&t);
        assert!(p.contains("单选题"), "{}", p);
        assert!(p.contains("A. 1"), "{}", p);
        assert!(p.contains("题目：1+1=?"), "{}", p);
    }

    #[test]
    fn test_extract_answer() {
        // 对齐 Python _extract_answer：抽取所有 [A-Ha-h] 字母
        assert_eq!(extract_answer("B", true), "B");
        assert_eq!(extract_answer("答案：ABD", true), "ABD");
        assert_eq!(extract_answer("答：A B C", true), "ABC");
        assert_eq!(extract_answer("3.14", false), "3.14");
        // 非选择题去代码块与"答案："前缀
        assert_eq!(extract_answer("```python\nprint(1)\n```", false), "print(1)");
        assert_eq!(extract_answer("答案：42", false), "42");
    }

    #[test]
    fn test_parse_topics() {
        let html = r#"<form action="/user/work/submit">
          <div class="num"><span>1</span></div>
          <div class="name">1、1+1等于几？</div>
          <div class="list"><label>A. 1</label><label>B. 2</label></div>
          <div class="type">单选题</div>
        </form>
        <form action="/user/work/submit">
          <div class="num"><span>2</span></div>
          <div class="name">2、填空：<input class="exam-input" type="text"></div>
          <p>请写出完整单词</p>
          <div class="type">填空题</div>
        </form>"#;
        let topics = parse_topics(html);
        assert_eq!(topics.len(), 2);
        assert_eq!(topics[0]["question"], "1、1+1等于几？");
        assert_eq!(topics[0]["options"].as_array().unwrap().len(), 2);
        assert_eq!(topics[1]["blank_count"], 1);
        assert!(topics[1]["question"].as_str().unwrap().contains("_____"));
        // <p> 题干拼接
        assert!(topics[1]["question"].as_str().unwrap().contains("请写出完整单词"));
    }

    #[test]
    fn test_parse_topics_project() {
        // uploader-btn → 简答题标记为 project
        let html = r#"<a class="uploader-btn">上传文件</a>
        <form action="/user/work/submit">
          <div class="num"><span>1</span></div>
          <div class="name">1、请提交项目压缩包</div>
          <div class="type">简答题</div>
        </form>"#;
        let topics = parse_topics(html);
        assert_eq!(topics.len(), 1);
        assert_eq!(topics[0]["type"], "project");
    }

    #[test]
    fn test_build_submit_pairs() {
        // 多选 answer[] 重复键
        let pairs = build_submit_pairs("7", "11", "ac", "多选题", 0, "work", "");
        let ans: Vec<&str> = pairs.iter().filter(|(k, _)| k == "answer[]").map(|(_, v)| v.as_str()).collect();
        assert_eq!(ans, vec!["A", "C"]);

        // 填空按 `,` 拆分（对齐 Python answer.split(',')，不足用最后一段补齐）
        let pairs = build_submit_pairs("7", "12", "北京, 上海", "填空题", 3, "exam", "9");
        let get = |k: &str| pairs.iter().find(|(kk, _)| kk == k).map(|(_, v)| v.clone()).unwrap();
        assert_eq!(get("answer_1"), "北京");
        assert_eq!(get("answer_2"), "上海");
        assert_eq!(get("answer_3"), "上海");
        assert_eq!(get("examId"), "7");
        assert_eq!(get("nodeId"), "9");

        // 单选走单 answer 键
        let pairs = build_submit_pairs("7", "13", "B", "单选题", 0, "work", "");
        assert!(pairs.iter().any(|(k, v)| k == "answer" && v == "B"));
    }
}

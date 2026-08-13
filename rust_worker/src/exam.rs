//! 考试 AI 答题（Rust 版）— 协议对齐 services/ai_service.py + exam_fetcher.py + exam_answerer.py
//!
//! solve_exam：开始作业 → 抓题 → DeepSeek 逐题作答 → 提交。
//! 测试钩子：DEEPSEEK_BASE_URL 环境变量覆盖（mock E2E 用）。

use anyhow::{bail, Context, Result};
use regex::Regex;
use reqwest::Client;
use serde_json::{json, Value};

fn make_client() -> Client {
    Client::builder()
        .danger_accept_invalid_certs(true)
        .user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        .build()
        .expect("构建考试 client 失败")
}

/// DeepSeek 调用（对齐 AIAnswerer._build_prompt + chat.completions）
pub async fn ask_deepseek(api_key: &str, model: &str, prompt: &str,
                          base_url: &str) -> Result<String> {
    let url = format!("{}/chat/completions", base_url.trim_end_matches('/'));
    let resp: Value = make_client().post(&url)
        .header("Authorization", format!("Bearer {api_key}"))
        .json(&json!({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1024,
        }))
        .timeout(std::time::Duration::from_secs(30))
        .send().await
        .context("DeepSeek 请求失败")?
        .json().await
        .context("DeepSeek 响应解析失败")?;
    let content = resp["choices"][0]["message"]["content"]
        .as_str().unwrap_or("").trim().to_string();
    if content.is_empty() {
        bail!("DeepSeek 返回空答案");
    }
    Ok(content)
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

/// 从 AI 响应提取答案（对齐 _extract_answer：选择题取字母，其余取内容）
fn extract_answer(content: &str, is_choice: bool) -> String {
    if !is_choice {
        return content.trim().to_string();
    }
    // 优先匹配纯字母答案
    let letter = Regex::new(r"(?i)^\s*([A-F]+)\s*$").unwrap();
    if let Some(c) = letter.captures(content.trim()) {
        return c[1].to_uppercase();
    }
    let multi = Regex::new(r"(?i)答(?:案)?[：:是\s]*([A-F][、,，\s]*)+").unwrap();
    if let Some(c) = multi.captures(content) {
        let letters: String = c[0].chars().filter(|ch| ch.is_ascii_alphabetic()).collect();
        if !letters.is_empty() {
            return letters.to_uppercase();
        }
    }
    content.trim().chars().take(20).collect()
}

/// 抓题（对齐 TopicFetcher.fetch：start_work → 页面 → 解析 topics）
async fn fetch_topics(client: &Client, cookie: &str, base_url: &str,
                      work_id: &str, course_id: &str, node_id: &str,
                      item_type: &str) -> Result<(Vec<Value>, String)> {
    let base = base_url.trim_end_matches('/');
    // start_work（work/exam 两种端点，按类型排序尝试）
    let (endpoint, id_key) = if item_type == "exam" {
        ("/user/exam/start", "examId")
    } else {
        ("/user/work/start", "workId")
    };
    let resp = client.post(format!("{base}{endpoint}"))
        .header("Cookie", cookie)
        .header("X-Requested-With", "XMLHttpRequest")
        .form(&[(id_key, work_id.to_string()),
                ("courseId", course_id.to_string()),
                ("nodeId", node_id.to_string())])
        .send().await
        .context("开始作业请求失败")?;
    let data: Value = resp.json().await.context("开始作业响应解析失败")?;
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

/// 解析题目（对齐 exam_fetcher._parse_topics 的 form 结构解析）
fn parse_topics(html: &str) -> Vec<Value> {
    use scraper::{Html, Selector};
    let doc = Html::parse_document(html);
    let form_sel = Selector::parse("form").unwrap();

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

        // answer_id：topic-head data-id 或题号
        let head_id = form.select(&Selector::parse(".topic-head").unwrap()).next()
            .and_then(|a| a.value().attr("data-id"))
            .unwrap_or("");
        let answer_id = if head_id.is_empty() { num.to_string() } else { head_id.to_string() };

        let blank_count = form.select(&Selector::parse("input.exam-input").unwrap()).count();

        topics.push(json!({
            "number": num,
            "topic_id": answer_id,
            "answer_id": answer_id,
            "question": question,
            "options": options,
            "q_type": q_type,
            "blank_count": blank_count,
        }));
    }
    topics
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
    let id_key = if submit_type == "exam" { "examId" } else { "workId" };

    // 多选题：answer[] 重复键
    let is_multi = q_type.contains("多选") && answer.len() > 1;
    let mut pairs: Vec<(String, String)> = vec![
        ("answerId".into(), answer_id.to_string()),
        (id_key.into(), work_id.to_string()),
    ];
    if is_multi {
        for ch in answer.chars().filter(|c| c.is_ascii_alphabetic()) {
            pairs.push(("answer[]".into(), ch.to_ascii_uppercase().to_string()));
        }
    } else if q_type.contains("填空") && blank_count > 0 {
        for i in 0..blank_count {
            let idx = i.min(answer.chars().count().saturating_sub(1));
            let part: String = answer.chars().nth(idx).map(|c| c.to_string()).unwrap_or_default();
            pairs.push((format!("answer_{}", i + 1), part));
        }
    } else {
        pairs.push(("answer".into(), answer.to_string()));
    }

    let resp = client.post(&url)
        .header("Cookie", cookie)
        .header("X-Requested-With", "XMLHttpRequest")
        .header("Referer", if submit_type == "exam" && !node_id.is_empty() {
            format!("{base}/user/exam")
        } else { base.to_string() })
        .form(&pairs)
        .send().await
        .context("提交答案请求失败")?;
    let body = resp.text().await.unwrap_or_default();
    if body.trim().is_empty() {
        return Ok(json!({"status": false, "msg": "服务器返回空响应"}));
    }
    serde_json::from_str(&body).or_else(|_| Ok(json!({"status": false, "msg": "响应非JSON"})))
}

/// 完整答题（对齐 ai_service.solve_exam）
pub async fn solve_exam(base_url: &str, cookie_str: &str,
                        work_id: &str, course_id: &str, node_id: &str,
                        api_key: &str, model: &str,
                        item_type: &str) -> Result<Value> {
    if api_key.is_empty() {
        bail!("DEEPSEEK_API_KEY 未配置");
    }
    let client = make_client();
    let deepseek_base = std::env::var("DEEPSEEK_BASE_URL")
        .unwrap_or_else(|_| "https://api.deepseek.com".to_string());

    let (topics, submit_type) = fetch_topics(&client, cookie_str, base_url,
                                             work_id, course_id, node_id, item_type).await?;
    if topics.is_empty() {
        bail!("未获取到题目");
    }
    tracing::info!(work_id, total = topics.len(), "开始 AI 答题");

    let mut submitted = 0usize;
    let mut failed = 0usize;
    for topic in &topics {
        let q_type = topic["q_type"].as_str().unwrap_or("").to_string();
        let is_choice = q_type.contains("单选") || q_type.contains("多选") || q_type.contains("判断");
        let prompt = build_prompt(topic);
        let mut answer = String::new();
        for _attempt in 0..3 {
            match ask_deepseek(api_key, model, &prompt, &deepseek_base).await {
                Ok(content) => {
                    answer = extract_answer(&content, is_choice);
                    if !answer.is_empty() {
                        break;
                    }
                }
                Err(e) => tracing::warn!(error = %e, "AI 调用失败"),
            }
            tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        }
        if answer.is_empty() {
            failed += 1;
            continue;
        }
        let blank_count = topic["blank_count"].as_u64().unwrap_or(0) as usize;
        let r = submit_topic(&client, cookie_str, base_url, work_id,
                             topic["answer_id"].as_str().unwrap_or(""),
                             &answer, &q_type, blank_count, &submit_type, node_id).await?;
        if r["status"].as_bool().unwrap_or(false) {
            submitted += 1;
        } else {
            failed += 1;
            tracing::warn!(msg = %r["msg"].as_str().unwrap_or(""), "提交失败");
        }
    }
    let success = failed == 0;
    Ok(json!({
        "success": success,
        "submitted": submitted,
        "total": topics.len(),
        "failed": failed,
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
        assert_eq!(extract_answer("B", true), "B");
        assert_eq!(extract_answer("答案：ABD", true), "ABD");
        assert_eq!(extract_answer("3.14", false), "3.14");
        assert_eq!(extract_answer("答：A B C", true), "ABC");
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
          <div class="type">填空题</div>
        </form>"#;
        let topics = parse_topics(html);
        assert_eq!(topics.len(), 2);
        assert_eq!(topics[0]["question"], "1、1+1等于几？");
        assert_eq!(topics[0]["options"].as_array().unwrap().len(), 2);
        assert_eq!(topics[1]["blank_count"], 1);
        assert!(topics[1]["question"].as_str().unwrap().contains("_____"));
    }
}

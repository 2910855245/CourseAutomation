//! 学习通测验 AI 答题 + 讨论生成（Rust 版）
//! — 协议对齐 worker.py ask_deepseek/_extract_json_answers/_format_answer_for_submit
//! — 以及 services/discuss.py generate_discussion
//!
//! 纯函数/薄壳封装，不注册路由；供 cx 刷课流程在遇到测验节点时调用。
//! 调用方传 deepseek_api_key（为空时 ask_deepseek 返回空、generate_discussion 走降级文案）。

use regex::Regex;
use serde_json::{json, Value};

use crate::llm::LlmClient;

/// quiz 专用 system prompt（对齐 quiz.py）
const QUIZ_SYSTEM: &str = "你是学习通答题助手。直接给出正确答案，用JSON格式输出。判断题答案为true（对）或false（错），单选题答案为A/B/C/D，多选题答案如AB/ACD。必须用JSON数组格式输出，每题一个对象。";

/// 构造批量答题 prompt（对齐 quiz.py：题干 + 选项去前缀 + JSON 输出要求）
fn build_quiz_prompt(questions: &[Value]) -> String {
    let mut lines = vec!["请回答以下学习通题目。直接给出答案，不要解释。\n".to_string()];
    let opt_prefix = Regex::new(r"^[A-Da-d]\s*").unwrap();
    for (i, q) in questions.iter().enumerate() {
        let text = q["text"].as_str().unwrap_or("");
        lines.push(format!("第{}题: {}", i + 1, text));
        if let Some(options) = q["options"].as_array() {
            for (j, opt) in options.iter().enumerate() {
                let label = (b'A' + j as u8) as char;
                let clean = opt_prefix.replace(opt.as_str().unwrap_or(""), "");
                lines.push(format!("  {label}. {clean}"));
            }
        }
    }
    lines.push(format!(
        "\n共{}题，请按以下JSON格式输出答案：\n```json\n[{{\"num\": 1, \"answer\": \"A或true\"}}, {{\"num\": 2, \"answer\": \"B\"}}]\n```",
        questions.len()
    ));
    lines.join("\n")
}

/// 批量答题（对齐 quiz.py：temperature=0.1，一次请求多题，返回 [{qid, answer}]）
/// questions: [{"qid": "...", "text": "...", "options": [...]}]
pub async fn ask_deepseek(llm: &LlmClient, questions: &[Value], model: &str) -> Vec<Value> {
    if questions.is_empty() || llm.api_key.is_empty() {
        return Vec::new();
    }
    let prompt = build_quiz_prompt(questions);
    match llm.chat(model, QUIZ_SYSTEM, &prompt, 0.1, 4096, false).await {
        Ok(reply) => extract_json_answers(&reply.content, questions),
        Err(e) => {
            tracing::warn!(error = %e, "学习通测验 AI 调用失败");
            Vec::new()
        }
    }
}

/// 从 AI 回复提取 JSON 答案（对齐 _extract_json_answers：
/// 优先 \[.*\] DOTALL 整体提取，失败走行级 fallback）
pub fn extract_json_answers(content: &str, questions: &[Value]) -> Vec<Value> {
    // 首选：JSON 数组整体提取（兼容 ```json 包裹）
    let arr_re = Regex::new(r"(?s)\[.*\]").unwrap();
    if let Some(m) = arr_re.find(content) {
        if let Ok(Value::Array(items)) = serde_json::from_str::<Value>(m.as_str()) {
            let mut out = Vec::new();
            for item in &items {
                let num = item["num"].as_u64().unwrap_or(0) as usize;
                if num == 0 || num > questions.len() {
                    continue;
                }
                let qid = questions[num - 1]["qid"].as_str().unwrap_or("");
                let ans = item["answer"].as_str().unwrap_or("");
                if !qid.is_empty() && !ans.is_empty() {
                    out.push(json!({"qid": qid, "answer": ans}));
                }
            }
            if !out.is_empty() {
                return out;
            }
        }
    }
    // fallback：行级解析（行内含 qid 且带 answer: X 的行）
    let line_re = Regex::new(r#"(?i)["']?answer["']?\s*[:=]\s*["']?([A-D]+|true|false)"#).unwrap();
    let mut out = Vec::new();
    for line in content.lines() {
        let caps = match line_re.captures(line) {
            Some(c) => c,
            None => continue,
        };
        let ans = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        for q in questions {
            let qid = q["qid"].as_str().unwrap_or("");
            if !qid.is_empty() && line.contains(qid) {
                out.push(json!({"qid": qid, "answer": ans}));
                break;
            }
        }
    }
    out
}

/// 格式化答案用于提交（对齐 _format_answer_for_submit：
/// 判断题归一 true/false，其余原样大写）
pub fn format_answer_for_submit(qtype: &str, answer: &str) -> String {
    let ans = answer.trim();
    if qtype == "judgment" {
        if ["TRUE", "对", "A", "T", "1"].contains(&ans.to_uppercase().as_str()) {
            "true".to_string()
        } else {
            "false".to_string()
        }
    } else {
        ans.to_uppercase()
    }
}

/// 生成讨论内容（对齐 discuss.py：temperature=0.8, max_tokens=200,
/// model=deepseek-chat；失败/无 key 降级固定文案）
/// 返回 (title, body)
pub async fn generate_discussion(llm: &LlmClient, course_name: &str,
                                 knowledge_name: &str) -> (String, String) {
    let fallback = || (
        "学习心得".to_string(),
        "通过本节课程的学习，对相关知识有了更深入的理解，收获很大。".to_string(),
    );
    if llm.api_key.is_empty() {
        return fallback();
    }
    let prompt = format!(
        "请为以下课程知识点写一段学习讨论内容。\n课程：{course_name}\n知识点：{knowledge_name}\n\n要求：\n1. 标题简洁（10-20字）\n2. 内容积极正面，体现学习收获（100-200字）\n3. 直接输出，格式如下：\n标题：xxx\n内容：xxx"
    );
    let reply = match llm.chat("deepseek-chat", "", &prompt, 0.8, 200, false).await {
        Ok(r) => r,
        Err(e) => {
            tracing::warn!(error = %e, "讨论生成失败，使用降级文案");
            return fallback();
        }
    };
    let title_re = Regex::new(r"(?s)标题[：:]\s*(.+)").unwrap();
    let body_re = Regex::new(r"(?s)内容[：:]\s*(.+)").unwrap();
    let title = title_re.captures(&reply.content)
        .and_then(|c| c.get(1))
        .map(|m| m.as_str().trim().lines().next().unwrap_or("").trim().to_string())
        .filter(|s: &String| !s.is_empty());
    let body = body_re.captures(&reply.content)
        .and_then(|c| c.get(1))
        .map(|m| m.as_str().trim().to_string())
        .filter(|s: &String| !s.is_empty());
    match (title, body) {
        (Some(t), Some(b)) => (t.chars().take(20).collect(), b.chars().take(200).collect()),
        _ => fallback(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn qs() -> Vec<Value> {
        vec![
            json!({"qid": "q1", "text": "1+1=?", "options": ["1", "2", "3", "4"]}),
            json!({"qid": "q2", "text": "地球是圆的", "options": []}),
        ]
    }

    #[test]
    fn test_build_quiz_prompt() {
        let p = build_quiz_prompt(&qs());
        assert!(p.contains("第1题: 1+1=?"));
        assert!(p.contains("第2题: 地球是圆的"));
        // 选项带 label，且去掉原前缀
        let p2 = build_quiz_prompt(&[json!({"qid":"x","text":"t","options":["A 甲","B. 乙","c 丙"]})]);
        assert!(p2.contains("A. 甲"), "{p2}");
        assert!(p2.contains("B. . 乙"), "{p2}"); // 对齐 Python re.sub(r'^[A-Da-d]\s*')："." 保留
        assert!(p2.contains("C. 丙"), "{p2}");
        assert!(p.contains("共2题"));
    }

    #[test]
    fn test_extract_json_answers_array() {
        // ```json 包裹的 JSON 数组
        let content = "```json\n[{\"num\": 1, \"answer\": \"B\"}, {\"num\": 2, \"answer\": \"true\"}]\n```";
        let out = extract_json_answers(content, &qs());
        assert_eq!(out.len(), 2);
        assert_eq!(out[0], json!({"qid": "q1", "answer": "B"}));
        assert_eq!(out[1], json!({"qid": "q2", "answer": "true"}));

        // 裸数组 + 超范围 num 被丢弃
        let out = extract_json_answers("[{\"num\": 9, \"answer\": \"A\"}]", &qs());
        assert!(out.is_empty());
    }

    #[test]
    fn test_extract_json_answers_fallback() {
        // 非 JSON 格式 → 行级 fallback（行内带 qid 且 answer: X）
        let content = "q1: answer: A\nq2 answer=true";
        let out = extract_json_answers(content, &qs());
        assert!(out.contains(&json!({"qid": "q1", "answer": "A"})));
        assert!(out.contains(&json!({"qid": "q2", "answer": "true"})));
    }

    #[test]
    fn test_format_answer_for_submit() {
        // 判断题：真值集合 → true，其余 → false（对齐 Python 大小写不敏感）
        for a in ["true", "TRUE", "对", "A", "t", "1"] {
            assert_eq!(format_answer_for_submit("judgment", a), "true", "{a}");
        }
        for a in ["false", "错", "B", "0", "F"] {
            assert_eq!(format_answer_for_submit("judgment", a), "false", "{a}");
        }
        // 选择题：原样大写
        assert_eq!(format_answer_for_submit("single", "b"), "B");
        assert_eq!(format_answer_for_submit("multiple", "acd"), "ACD");
        assert_eq!(format_answer_for_submit("single", " C "), "C");
    }

    #[test]
    fn test_discussion_parse() {
        // 解析正则与 generate_discussion 内部一致（纯函数路径单测）
        let title_re = Regex::new(r"(?s)标题[：:]\s*(.+)").unwrap();
        let body_re = Regex::new(r"(?s)内容[：:]\s*(.+)").unwrap();
        let content = "标题：我的学习心得\n内容：这节课讲得非常好，我收获了很多知识。";
        let t = title_re.captures(content).unwrap().get(1).unwrap().as_str();
        let b = body_re.captures(content).unwrap().get(1).unwrap().as_str();
        assert_eq!(t.trim().lines().next().unwrap(), "我的学习心得");
        assert!(b.contains("收获"));
    }
}

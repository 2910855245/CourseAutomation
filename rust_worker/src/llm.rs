//! DeepSeek 共享客户端 — 协议对齐 exam_answerer.py AIAnswerer + ai_service.py _cached_config
//!
//! reqwest 直连 chat/completions，不走 async-openai。
//! 置信度对齐 _calc_confidence：logprobs 前 5 个 token 平均取 exp，失败走启发式。

use anyhow::{bail, Context, Result};
use dashmap::DashMap;
use reqwest::Client;
use serde_json::{json, Value};
use std::sync::LazyLock;
use std::time::{Duration, Instant};

use crate::db::Db;

fn make_client() -> Client {
    Client::builder()
        .user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        .build()
        .expect("构建 LLM client 失败")
}

/// chat 回复：内容 + 置信度
pub struct ChatReply {
    pub content: String,
    pub confidence: f64,
}

pub struct LlmClient {
    pub api_key: String,
    pub base_url: String,
    client: Client,
}

impl LlmClient {
    /// base_url 为空时读 env DEEPSEEK_BASE_URL，默认 https://api.deepseek.com
    pub fn new(api_key: &str, base_url: &str) -> Self {
        let base = if base_url.is_empty() {
            std::env::var("DEEPSEEK_BASE_URL")
                .unwrap_or_else(|_| "https://api.deepseek.com".to_string())
        } else {
            base_url.to_string()
        };
        Self {
            api_key: api_key.to_string(),
            base_url: base.trim_end_matches('/').to_string(),
            client: make_client(),
        }
    }

    /// 聊天补全（对齐 AIAnswerer.ask_one_topic 的请求参数；
    /// logprobs=true 时带 top_logprobs=5，用于置信度计算）
    pub async fn chat(&self, model: &str, system: &str, user: &str,
                      temperature: f64, max_tokens: u32, logprobs: bool) -> Result<ChatReply> {
        let mut messages = Vec::new();
        if !system.is_empty() {
            messages.push(json!({"role": "system", "content": system}));
        }
        messages.push(json!({"role": "user", "content": user}));

        let mut body = json!({
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": false,
        });
        if logprobs {
            body["logprobs"] = json!(true);
            body["top_logprobs"] = json!(5);
        }

        let url = format!("{}/chat/completions", self.base_url);
        let resp = self.client.post(&url)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .json(&body)
            .timeout(Duration::from_secs(30))
            .send().await
            .context("DeepSeek 请求失败")?;
        let status = resp.status().as_u16();
        let text = resp.text().await.unwrap_or_default();
        if status != 200 {
            bail!("DeepSeek HTTP {status}: {}", &text[..text.len().min(200)]);
        }
        let v: Value = serde_json::from_str(&text).context("DeepSeek 响应解析失败")?;
        let content = v["choices"][0]["message"]["content"]
            .as_str().unwrap_or("").trim().to_string();
        if content.is_empty() {
            bail!("DeepSeek 返回空答案");
        }
        let confidence = confidence_from_logprobs(&v, &content);
        Ok(ChatReply { content, confidence })
    }
}

/// 置信度计算（对齐 _calc_confidence 的 logprobs 分支；is_choice 分支见 confidence_heuristic）
/// 前 5 个 token 平均 logprob 取 exp，钳位 [0.1, 1.0]，保留 2 位小数
pub fn confidence_from_logprobs(resp: &Value, _content: &str) -> f64 {
    let items = resp["choices"][0]["logprobs"]["content"].as_array();
    if let Some(items) = items {
        let logprobs: Vec<f64> = items.iter().take(5)
            .filter_map(|t| t["logprob"].as_f64())
            .collect();
        if !logprobs.is_empty() {
            let avg = logprobs.iter().sum::<f64>() / logprobs.len() as f64;
            // logprob 越接近 0 越自信：e^(-1)≈0.37, e^0=1.0
            let c = avg.exp().clamp(0.1, 1.0);
            return (c * 100.0).round() / 100.0;
        }
    }
    0.0
}

/// 启发式置信度（对齐 _calc_confidence 的降级分支：
/// 选择题格式正确 0.85 / 否则 0.6；非选择题有答案 0.75 / 否则 0.5）
pub fn confidence_heuristic(answer: &str, is_choice: bool) -> f64 {
    if answer.is_empty() {
        return 0.0;
    }
    if is_choice {
        if !answer.is_empty() && answer.len() <= 4
            && answer.chars().all(|c| matches!(c, 'A'..='H'))
        {
            0.85
        } else {
            0.6
        }
    } else {
        0.75
    }
}

// ── system_config 带 TTL 缓存读取（对齐 _cached_config，TTL=300s）──

static CONFIG_CACHE: LazyLock<DashMap<String, (String, Instant)>> = LazyLock::new(DashMap::new);
const CONFIG_TTL_SECS: u64 = 300;

/// 从 system_config 表读配置（TTL=300s 进程内缓存，失败回退 default）
pub async fn cached_config(db: &Db, key: &str, default: &str) -> String {
    if let Some(entry) = CONFIG_CACHE.get(key) {
        if entry.1.elapsed().as_secs() < CONFIG_TTL_SECS {
            return entry.0.clone();
        }
    }
    let pool = db.clone_pool();
    let key_s = key.to_string();
    let val = tokio::task::spawn_blocking(move || -> Option<String> {
        let conn = pool.get().ok()?;
        conn.query_row(
            "SELECT config_value FROM system_config WHERE config_key=?1",
            rusqlite::params![key_s], |r| r.get::<_, String>(0),
        ).ok()
    }).await.ok().flatten().filter(|s: &String| !s.is_empty());

    let val = val.unwrap_or_else(|| default.to_string());
    CONFIG_CACHE.insert(key.to_string(), (val.clone(), Instant::now()));
    val
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_confidence_from_logprobs() {
        // 前 5 个 token 平均 logprob 取 exp：5 个 -0.1 → exp(-0.1)≈0.90
        let resp = json!({"choices": [{"logprobs": {"content": [
            {"logprob": -0.1}, {"logprob": -0.1}, {"logprob": -0.1},
            {"logprob": -0.1}, {"logprob": -0.1}, {"logprob": -5.0}
        ]}}]});
        let c = confidence_from_logprobs(&resp, "A");
        assert!((c - 0.90).abs() < 0.01, "c={c}");

        // 低置信度钳位到 0.1
        let low = json!({"choices": [{"logprobs": {"content": [{"logprob": -9.0}]}}]});
        assert_eq!(confidence_from_logprobs(&low, "A"), 0.1);

        // 无 logprobs → 0.0（由调用方走启发式）
        let none = json!({"choices": [{"logprobs": null}]});
        assert_eq!(confidence_from_logprobs(&none, "A"), 0.0);
    }

    #[test]
    fn test_confidence_heuristic() {
        assert_eq!(confidence_heuristic("", true), 0.0);
        assert_eq!(confidence_heuristic("B", true), 0.85);
        assert_eq!(confidence_heuristic("ABD", true), 0.85);
        assert_eq!(confidence_heuristic("答案很长不确定", true), 0.6);
        assert_eq!(confidence_heuristic("3.14", false), 0.75);
    }
}

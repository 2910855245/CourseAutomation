//! DeepSeek 共享客户端
//!
//! 对齐 2026-09 的 DeepSeek 官方文档：
//!   - 模型名：`deepseek-flash`（DeepSeek-V4.1-Flash）/ `deepseek-v4-pro`。
//!     旧的 `deepseek-chat` / `deepseek-reasoner` 已于 2026-07-24 弃用，
//!     老配置库里存的名字由 [`resolve_model`] 自动归一化，不需要人工改配置。
//!   - 思考模式：`thinking: {type: enabled|disabled}` + `reasoning_effort`，
//!     思考模式下 temperature/top_p 等参数会被忽略（不再下发，避免误解）。
//!   - JSON Output：`response_format: {type: json_object}`（prompt 中必须含 "json"）。
//!   - 图像理解：`content` 传多模态数组（仅 deepseek-flash 支持）。
//!   - 上下文硬盘缓存：命中/未命中 tokens 在 `usage` 中返回，命中价是未命中的 1/50。
//!   - 分时计价：周一至周五 9-12 / 14-18（北京时间）为高峰，其余为空闲（半价）。
//!
//! 每次调用结束后把 tokens 与估算费用写入 `ai_usage` 表（后台看板的 AI 成本来源）。

use anyhow::{anyhow, Context, Result};
use dashmap::DashMap;
use reqwest::Client;
use serde_json::{json, Value};
use std::sync::{LazyLock, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use crate::db::Db;

/// 当前在售模型（官方文档：旧名 deepseek-chat/deepseek-reasoner 已弃用）
pub const MODEL_FLASH: &str = "deepseek-flash";
pub const MODEL_PRO: &str = "deepseek-v4-pro";

/// 请求超时：思考模式下模型要先输出思维链，30s 不够用
const TIMEOUT_NORMAL_SECS: u64 = 60;
const TIMEOUT_THINKING_SECS: u64 = 180;
/// 可重试错误的最大尝试次数（429 / 5xx / 网络抖动）
const MAX_ATTEMPTS: u32 = 3;

fn make_client() -> Client {
    Client::builder()
        .user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        // 连接超时与请求超时分开：连不上时不该等满整个请求超时
        .connect_timeout(Duration::from_secs(10))
        .build()
        .expect("构建 LLM client 失败")
}

/// 归一化模型名 → (实际请求的模型, 是否默认走思考模式)
///
/// 老库里的 `deepseek-chat`/`deepseek-reasoner`/`deepseek-v4-flash` 现在都已
/// 下线或改名，直接照发会 401/404。统一在这里映射：chat→flash 非思考，
/// reasoner→flash 思考（旧语义就是"推理"，保留行为）。
pub fn resolve_model(name: &str) -> (String, bool) {
    let n = name.trim().to_ascii_lowercase();
    match n.as_str() {
        "" | "deepseek-chat" | "deepseek-flash" | "deepseek-v4-flash"
        | "deepseek-v4-flash-vision-exp" => (MODEL_FLASH.to_string(), false),
        "deepseek-reasoner" => (MODEL_FLASH.to_string(), true),
        "deepseek-v4-pro" | "deepseek-pro" => (MODEL_PRO.to_string(), false),
        // 未知名字原样下发，但不加思考参数：让官方返回明确报错而不是静默走错模型
        _ => (name.trim().to_string(), false),
    }
}

/// 元/百万 tokens 单价 → (缓存命中, 缓存未命中, 输出)
fn price_per_million(model: &str, peak: bool) -> (f64, f64, f64) {
    let pro = model.to_ascii_lowercase().contains("pro");
    match (pro, peak) {
        (false, false) => (0.02, 1.0, 4.0),
        (false, true) => (0.04, 2.0, 8.0),
        (true, false) => (0.15, 4.5, 13.5),
        (true, true) => (0.30, 9.0, 27.0),
    }
}

/// 北京时间是否处于高峰时段（周一至周五 9:00-12:00、14:00-18:00）。
/// 注：中国法定节假日不在本表内计算，属已知近似（最多把空闲价算成高峰价）。
pub fn is_peak_at(utc_secs: u64) -> bool {
    let bj = utc_secs + 8 * 3600;
    let days = bj / 86400;
    let sod = (bj % 86400) as u32;
    let weekday = ((days + 4) % 7) as u32; // 1970-01-01 是周四 → 0=周日
    if weekday == 0 || weekday == 6 {
        return false;
    }
    let h = sod / 3600;
    (9..12).contains(&h) || (14..18).contains(&h)
}

fn now_utc_secs() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}

// ── 用量与费用 ──────────────────────────────────────────────────────────

#[derive(Debug, Clone, Default, serde::Serialize)]
pub struct Usage {
    pub prompt_tokens: i64,
    pub cache_hit_tokens: i64,
    pub cache_miss_tokens: i64,
    pub completion_tokens: i64,
    /// 按官方分时单价估算的费用（元）
    pub cost_yuan: f64,
}

impl Usage {
    /// 从响应 usage 字段解析并计价；无 usage 时返回 None
    pub fn from_response(v: &Value, model: &str) -> Option<Usage> {
        let u = v.get("usage")?;
        if u.is_null() {
            return None;
        }
        let prompt = u["prompt_tokens"].as_i64().unwrap_or(0);
        let hit = u["prompt_cache_hit_tokens"].as_i64().unwrap_or(0);
        // 老版本响应可能没有 miss 字段，用 prompt - hit 兜底
        let miss = u["prompt_cache_miss_tokens"].as_i64().unwrap_or((prompt - hit).max(0));
        let out = u["completion_tokens"].as_i64().unwrap_or(0);
        let (p_hit, p_miss, p_out) = price_per_million(model, is_peak_at(now_utc_secs()));
        let cost = hit as f64 * p_hit / 1e6
            + miss as f64 * p_miss / 1e6
            + out as f64 * p_out / 1e6;
        Some(Usage {
            prompt_tokens: prompt,
            cache_hit_tokens: hit,
            cache_miss_tokens: miss,
            completion_tokens: out,
            cost_yuan: (cost * 1e6).round() / 1e6,
        })
    }
}

/// 用量落库句柄（main.rs 启动时注入）。未注入时静默跳过，不影响调用链。
static USAGE_DB: OnceLock<Db> = OnceLock::new();

pub fn init_usage_db(db: Db) {
    let _ = USAGE_DB.set(db);
}

/// 记录一次 AI 调用（成功与失败都记，看板要算成功率）
fn record_usage(scene: &str, model: &str, thinking: bool, usage: Option<&Usage>, ok: bool) {
    let Some(db) = USAGE_DB.get() else { return };
    let pool = db.clone_pool();
    let scene = scene.to_string();
    let model = model.to_string();
    let u = usage.cloned().unwrap_or_default();
    let now = crate::queue::now_str();
    let task = move || {
        if let Ok(conn) = pool.get() {
            let _ = conn.execute(
                "INSERT INTO ai_usage
                   (created_at, scene, model, thinking, prompt_tokens, cache_hit_tokens,
                    cache_miss_tokens, completion_tokens, cost_yuan, ok)
                 VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10)",
                rusqlite::params![
                    now, scene, model, thinking as i64, u.prompt_tokens, u.cache_hit_tokens,
                    u.cache_miss_tokens, u.completion_tokens, u.cost_yuan, ok as i64
                ],
            );
        }
    };
    if let Ok(handle) = tokio::runtime::Handle::try_current() {
        handle.spawn_blocking(task);
    } else {
        task();
    }
}

// ── 请求 ────────────────────────────────────────────────────────────────

/// chat 回复：内容 + 置信度 + 用量
pub struct ChatReply {
    pub content: String,
    pub confidence: f64,
    pub usage: Option<Usage>,
}

/// 一次 chat 请求。用链式 setter 组装，避免 8 个位置参数读不出含义。
pub struct ChatRequest {
    scene: String,
    model: String,
    system: String,
    user: String,
    images: Vec<String>,
    temperature: f64,
    max_tokens: u32,
    logprobs: bool,
    json: bool,
    thinking: Option<bool>,
}

impl ChatRequest {
    pub fn new(scene: &str, model: &str, user: &str) -> Self {
        Self {
            scene: scene.to_string(),
            model: model.to_string(),
            system: String::new(),
            user: user.to_string(),
            images: Vec::new(),
            temperature: 0.1,
            max_tokens: 2048,
            logprobs: false,
            json: false,
            thinking: None,
        }
    }

    pub fn system(mut self, s: &str) -> Self { self.system = s.to_string(); self }
    pub fn images(mut self, urls: &[String]) -> Self { self.images = urls.to_vec(); self }
    pub fn temperature(mut self, t: f64) -> Self { self.temperature = t; self }
    pub fn max_tokens(mut self, n: u32) -> Self { self.max_tokens = n; self }
    pub fn logprobs(mut self, on: bool) -> Self { self.logprobs = on; self }
    /// JSON Output（prompt 里必须出现 "json" 字样，官方要求）
    pub fn json(mut self, on: bool) -> Self { self.json = on; self }
    pub fn thinking(mut self, on: bool) -> Self { self.thinking = Some(on); self }
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

    /// 聊天补全。429/5xx/网络抖动自动重试（最多 MAX_ATTEMPTS 次）。
    pub async fn chat(&self, req: ChatRequest) -> Result<ChatReply> {
        let (model, default_thinking) = resolve_model(&req.model);
        let thinking = req.thinking.unwrap_or(default_thinking);

        let mut messages = Vec::new();
        if !req.system.is_empty() {
            messages.push(json!({"role": "system", "content": req.system}));
        }
        if req.images.is_empty() {
            messages.push(json!({"role": "user", "content": req.user}));
        } else {
            // 多模态：文本 + 图片 URL（图像理解仅 deepseek-flash 支持）
            let mut parts = vec![json!({"type": "text", "text": req.user})];
            for url in &req.images {
                parts.push(json!({"type": "image_url", "image_url": {"url": url}}));
            }
            messages.push(json!({"role": "user", "content": parts}));
        }

        let mut body = json!({
            "model": model,
            "messages": messages,
            "stream": false,
            "max_tokens": req.max_tokens,
        });
        if thinking {
            // 思考模式下 temperature 等参数会被忽略，干脆不下发
            body["thinking"] = json!({"type": "enabled"});
            body["reasoning_effort"] = json!("high");
        } else {
            body["thinking"] = json!({"type": "disabled"});
            body["temperature"] = json!(req.temperature);
        }
        if req.logprobs {
            body["logprobs"] = json!(true);
            body["top_logprobs"] = json!(5);
        }
        if req.json {
            body["response_format"] = json!({"type": "json_object"});
        }

        let url = format!("{}/chat/completions", self.base_url);
        let timeout = Duration::from_secs(if thinking {
            TIMEOUT_THINKING_SECS
        } else {
            TIMEOUT_NORMAL_SECS
        });

        let mut last_err: Option<anyhow::Error> = None;
        // 每收到一次响应就记一次账（失败也计费）；纯网络错误没有响应，最后补记
        let mut recorded = false;
        for attempt in 1..=MAX_ATTEMPTS {
            let sent = self.client.post(&url)
                .header("Authorization", format!("Bearer {}", self.api_key))
                .json(&body)
                .timeout(timeout)
                .send()
                .await;
            match sent {
                Ok(resp) => {
                    let status = resp.status().as_u16();
                    let text = resp.text().await.unwrap_or_default();
                    if status == 200 {
                        let v: Value = serde_json::from_str(&text)
                            .context("DeepSeek 响应解析失败")?;
                        let content = v["choices"][0]["message"]["content"]
                            .as_str().unwrap_or("").trim().to_string();
                        let usage = Usage::from_response(&v, &model);
                        recorded = true;
                        if content.is_empty() {
                            // JSON Output 偶发返回空 content（官方已知问题）→ 重试
                            record_usage(&req.scene, &model, thinking, usage.as_ref(), false);
                            last_err = Some(anyhow!("DeepSeek 返回空答案"));
                        } else {
                            let confidence = confidence_from_logprobs(&v, &content);
                            record_usage(&req.scene, &model, thinking, usage.as_ref(), true);
                            return Ok(ChatReply { content, confidence, usage });
                        }
                    } else {
                        let err = anyhow!(
                            "DeepSeek HTTP {status}: {}",
                            crate::platform_client::preview(&text, 200)
                        );
                        recorded = true;
                        record_usage(&req.scene, &model, thinking, None, false);
                        // 密钥/参数类 4xx 重试无意义，直接失败
                        if !retryable_status(status) {
                            return Err(err);
                        }
                        last_err = Some(err);
                    }
                }
                Err(e) => {
                    // 网络层错误：没有响应，本次不记账
                    last_err = Some(anyhow!("DeepSeek 请求失败: {e}"));
                    recorded = false;
                }
            }
            if attempt < MAX_ATTEMPTS {
                // 1s / 2s 退避，避开 429 的瞬时拥塞
                tokio::time::sleep(Duration::from_secs(attempt as u64)).await;
            }
        }
        if !recorded {
            record_usage(&req.scene, &model, thinking, None, false);
        }
        Err(last_err.unwrap_or_else(|| anyhow!("DeepSeek 调用失败")))
    }
}

/// 是否值得重试：限流与 5xx 是瞬时的；4xx（密钥/参数错）重试无意义
fn retryable_status(status: u16) -> bool {
    status == 429 || status == 408 || (500..600).contains(&status)
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

/// 读管理端配置的模型名（空配置回退 default），供各调用点使用。
/// 归一化在 [`resolve_model`] 里做，这里保留原始值便于看板展示"配置了什么"。
pub async fn configured_model(db: &Db, key: &str, default: &str) -> String {
    let v = cached_config(db, key, default).await;
    if v.trim().is_empty() { default.to_string() } else { v }
}

/// 管理端「思考模式」总开关（未配置 → None，由模型名语义决定）
pub async fn configured_thinking(db: &Db) -> Option<bool> {
    match cached_config(db, "deepseek_thinking", "").await.trim() {
        "1" | "true" => Some(true),
        "0" | "false" => Some(false),
        _ => None,
    }
}

/// 当前生效的 API Key：数据库配置优先，回退环境变量（与 test_deepseek 同口径）
pub async fn effective_api_key(db: &Db) -> String {
    let db_key = cached_config(db, "deepseek_api_key", "").await;
    if !db_key.is_empty() {
        return db_key;
    }
    std::env::var("DEEPSEEK_API_KEY").unwrap_or_default()
}

/// 验证码视觉识别兜底。
///
/// 本地 ddddocr 是首选（免费、毫秒级）；但它的输出是"尽力而为"——遇到扭曲、
/// 粘连、低对比度的验证码会给出非法结果，此时登录直接失败。这里用
/// deepseek-flash 的图像理解（官方支持 base64 data URL）再读一次。
/// 只在本地 OCR 连续判不出可信结果时调用，因此正常路径零成本、零延迟。
///
/// 开关：系统配置 `deepseek_vision_ocr`（默认开），置 "0" 可关闭。
pub async fn recognize_captcha_vision(img: &[u8], mime: &str) -> Option<String> {
    let db = USAGE_DB.get()?;
    if cached_config(db, "deepseek_vision_ocr", "1").await.trim() == "0" {
        return None;
    }
    let key = effective_api_key(db).await;
    if key.is_empty() || img.is_empty() {
        return None;
    }
    use base64::Engine as _;
    let data_url = format!(
        "data:{mime};base64,{}",
        base64::engine::general_purpose::STANDARD.encode(img)
    );
    let client = LlmClient::new(&key, "");
    let reply = client.chat(
        ChatRequest::new(
            "captcha_vision",
            MODEL_FLASH,
            "这是一张登录验证码图片。请只输出图中的 4 位字母或数字，不要解释、不要标点。",
        )
        .images(&[data_url])
        .temperature(0.0)
        .max_tokens(24),
    ).await.ok()?;
    // 模型可能带空格或引号，抽取其中的字母数字后按本地同一口径校验
    let cleaned: String = reply.content.chars()
        .filter(|c| c.is_ascii_alphanumeric())
        .take(4)
        .collect();
    if crate::ocr::plausible(&cleaned) {
        tracing::info!(code = %cleaned, "视觉兜底识别验证码成功");
        Some(cleaned)
    } else {
        tracing::warn!(raw = %reply.content, "视觉兜底返回不可信验证码");
        None
    }
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

    #[test]
    fn test_resolve_model_maps_legacy_names() {
        // 已弃用/下线的老名字必须被映射到当前在售模型，否则线上必然 401
        assert_eq!(resolve_model("deepseek-chat"), (MODEL_FLASH.to_string(), false));
        assert_eq!(resolve_model("deepseek-reasoner"), (MODEL_FLASH.to_string(), true));
        assert_eq!(resolve_model("deepseek-v4-flash"), (MODEL_FLASH.to_string(), false));
        assert_eq!(resolve_model("  DeepSeek-Flash "), (MODEL_FLASH.to_string(), false));
        assert_eq!(resolve_model("deepseek-v4-pro"), (MODEL_PRO.to_string(), false));
        // 空配置 → flash 非思考
        assert_eq!(resolve_model(""), (MODEL_FLASH.to_string(), false));
        // 未知名字原样下发（让官方明确报错，而不是静默换模型）
        assert_eq!(resolve_model("foo-bar"), ("foo-bar".to_string(), false));
    }

    #[test]
    fn test_peak_hour_windows() {
        // 2026-09-29 是周二。北京时间 10:00 = UTC 02:00
        let tue_02_utc = 1790647200u64; // 2026-09-29T02:00:00Z
        assert!(is_peak_at(tue_02_utc));
        // 同一天的北京时间 13:00（午休）→ UTC 05:00 → 空闲
        assert!(!is_peak_at(tue_02_utc + 3 * 3600));
        // 北京时间 15:00 → UTC 07:00 → 高峰
        assert!(is_peak_at(tue_02_utc + 5 * 3600));
        // 北京时间 20:00 → UTC 12:00 → 空闲
        assert!(!is_peak_at(tue_02_utc + 10 * 3600));
        // 2026-09-27 是周日 → 全天空闲（北京时间 10:00）
        assert!(!is_peak_at(tue_02_utc - 2 * 86400));
    }

    #[test]
    fn test_usage_cost_estimation() {
        // 高峰时段（周二 北京时间 10:00）flash：命中 1M、未命中 1M、输出 1M
        // = 0.04 + 2 + 8 = 10.04 元
        let v = json!({"usage": {
            "prompt_tokens": 2_000_000,
            "prompt_cache_hit_tokens": 1_000_000,
            "prompt_cache_miss_tokens": 1_000_000,
            "completion_tokens": 1_000_000,
        }});
        let u = Usage::from_response(&v, MODEL_FLASH).expect("usage");
        assert_eq!(u.prompt_tokens, 2_000_000);
        assert_eq!(u.completion_tokens, 1_000_000);
        // 费用随当前时段浮动，这里只断言量级与字段可解析
        assert!(u.cost_yuan > 0.0 && u.cost_yuan < 30.0, "cost={}", u.cost_yuan);

        // 缺 miss 字段时用 prompt-hit 兜底
        let v2 = json!({"usage": {"prompt_tokens": 100, "prompt_cache_hit_tokens": 40}});
        let u2 = Usage::from_response(&v2, MODEL_FLASH).unwrap();
        assert_eq!(u2.cache_miss_tokens, 60);

        // 没有 usage 字段 → None（不写脏数据）
        assert!(Usage::from_response(&json!({}), MODEL_FLASH).is_none());
    }

    #[test]
    fn test_retryable_status() {
        assert!(retryable_status(429));
        assert!(retryable_status(503));
        assert!(!retryable_status(401)); // 密钥错重试无意义
        assert!(!retryable_status(400)); // prompt 错重试无意义
    }
}

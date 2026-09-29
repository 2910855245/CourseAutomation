// 对齐 services/ypay_qr.py 的二维码生成/渠道分发逻辑。
// 说明：
// - qr_image（PNG base64）生成不在此实现，Rust 端统一返回 None（对齐 Python make_qr_base64 失败时返回 None 的形状）。
// - alipay_dmf/alipay_official 不移植 RSA2 官方 SDK，对齐 Python SDK ImportError 时回落 qr_url 的行为。
// - wxpay_cloud/wxpay_jym_cloud/wxpay_skd 云端 API 在 Python 侧本来就是 TODO 返回 None，Rust 同样回落 qr_url。

use regex::Regex;
use reqwest::Client;
use serde_json::Value;
use std::sync::OnceLock;

/// 对齐 urllib.parse.quote(s, safe='')：仅保留 A-Za-z0-9 与 "_.-~"，其余百分号编码（大写 hex）
/// 把支付二维码内容渲染成 PNG 的 data URL。
///
/// 为什么必须有这个函数：前端所有收银台界面只认 `qr_image`（`<img :src>`），
/// 而此前四个创建/查询支付单的 handler 一律返回 `qr_image: null` ——
/// 结果支付弹窗永远停在「生成二维码中…」，用户根本无法扫码，收入链路归零。
/// 后端出图（而不是前端用 JS 库渲染）是因为支付入口散落多处，集中在服务端
/// 只需一个实现，且返回体形状不变、前端零改动。
///
/// 失败返回 None：调用方保持原有的空值兜底语义，不影响下单主流程。
pub fn render_qr_data_url(content: &str) -> Option<String> {
    use base64::Engine as _;
    use image::ImageEncoder as _;

    let content = content.trim();
    if content.is_empty() {
        return None;
    }
    // 内容过长时（部分渠道码带上长签名）QR 版本会暴涨，交给 QrCode::new 报错即可
    let code = qrcode::QrCode::new(content.as_bytes()).ok()?;
    // 用 Luma<u8> 而不是 Luminance 别名：后者在 image 关闭默认特性时不可见
    let img = code
        .render::<image::Luma<u8>>()
        .min_dimensions(260, 260)
        .quiet_zone(true)
        .build();

    let mut png = Vec::new();
    image::codecs::png::PngEncoder::new(&mut png)
        .write_image(
            img.as_raw(),
            img.width(),
            img.height(),
            image::ExtendedColorType::L8,
        )
        .ok()?;

    Some(format!(
        "data:image/png;base64,{}",
        base64::engine::general_purpose::STANDARD.encode(&png)
    ))
}

/// 渲染失败时回落到 Null（保持与历史响应形状一致）
pub fn render_qr_image_value(content: &str) -> serde_json::Value {
    match render_qr_data_url(content) {
        Some(url) => serde_json::Value::String(url),
        None => serde_json::Value::Null,
    }
}

pub fn quote_full(s: &str) -> String {
    percent_encode(s, false)
}

/// 对齐 urllib.parse.quote 默认 safe='/'：额外保留 '/'
pub fn quote_keep_slash(s: &str) -> String {
    percent_encode(s, true)
}

fn percent_encode(s: &str, keep_slash: bool) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.as_bytes() {
        let c = *b as char;
        let safe = c.is_ascii_alphanumeric() || matches!(c, '_' | '.' | '-' | '~') || (keep_slash && c == '/');
        if safe {
            out.push(c);
        } else {
            out.push_str(&format!("%{:02X}", b));
        }
    }
    out
}

fn img_url_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?i)^https?://.*\.(png|jpg|jpeg|gif|webp)(\?.*)?$").unwrap())
}

/// 对齐 _detect_qr_content_type
pub fn detect_qr_content_type(content: &str) -> &'static str {
    let content = content.trim();
    if content.is_empty() {
        return "raw";
    }
    if content.starts_with("data:image/") {
        return "image_url";
    }
    if img_url_regex().is_match(content) {
        return "image_url";
    }
    if content.starts_with("wxp://") || content.contains("wx.tenpay.com") {
        return "wxpay";
    }
    if content.starts_with("https://qr.alipay.com/")
        || content.starts_with("alipays://")
        || content.contains("render.alipay.com")
    {
        return "alipay";
    }
    if content.starts_with("http://") || content.starts_with("https://") {
        return "url";
    }
    "raw"
}

/// 对齐 _wx_h5_url
fn wx_h5(qr_url: &str) -> String {
    if qr_url.starts_with("wxp://") {
        String::new()
    } else {
        qr_url.to_string()
    }
}

/// 对齐 gen_alipay_transfer_qr；返回 (qr_content, h5_qrurl)
fn gen_alipay_transfer_qr(zfb_pid: &str, money: f64, out_trade_no: &str, site_url: &str, channel_mode: i64) -> (String, String) {
    if zfb_pid.is_empty() {
        return (String::new(), String::new());
    }
    // 对齐 Python str(money)：10.0 → "10.0"
    let amount = crate::pay::py_float_str(money);
    let transfer_url = match channel_mode {
        1 => format!(
            "alipays://platformapi/startapp?appId=20000116&actionType=toAccount&goBack=NO&amount={}&userId={}&memo={}",
            amount, zfb_pid, out_trade_no
        ),
        2 => format!(
            "alipays://platformapi/startapp?appId=20000116&actionType=toAccount&goBack=NO&amount={}&userId={}",
            amount, zfb_pid
        ),
        3 => format!(
            "alipays://platformapi/startapp?appId=20000116&actionType=toAccount&goBack=NO&userId={}",
            zfb_pid
        ),
        _ => format!(
            "{}/alipayTransfer.php?amount={}&remark={}&payeeId={}",
            site_url, amount, out_trade_no, zfb_pid
        ),
    };
    // 双层 quote：内层 safe=''，外层默认 safe='/'
    let qr_content = quote_keep_slash(&format!(
        "https://render.alipay.com/p/c/mdeduct-landing?scheme={}",
        quote_full(&transfer_url)
    ));
    let h5 = format!("alipays://platformapi/startapp?appId=20000067&url={}", qr_content);
    (qr_content, h5)
}

/// 对齐 _gen_lakala_qr；成功返回 Some(url)，失败 None
async fn gen_lakala_qr(client: &Client, account: &Value, money: f64, out_trade_no: &str) -> Option<String> {
    let remark = account.get("remark").and_then(Value::as_str).unwrap_or("").trim().to_string();
    let memo = account.get("memo").and_then(Value::as_str).unwrap_or("").trim().to_string();
    let token = if !remark.is_empty() { remark } else { memo };
    if token.is_empty() {
        tracing::warn!("[YPay] 拉卡拉渠道缺少 memo 密钥");
        return None;
    }
    let name = account.get("name").and_then(Value::as_str).unwrap_or("").trim();
    let shop_name = if name.is_empty() { "支付" } else { name };
    let body = serde_json::json!({
        "amount": (money * 100.0).round() as i64,
        "orderNo": out_trade_no,
        "shopName": shop_name,
    });
    let resp = client
        .post("https://wallet.lakala.com/m/a/code/generate")
        .header("Authorization", token)
        .header(reqwest::header::CONTENT_TYPE, "application/json")
        .json(&body)
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .ok()?;
    let data: Value = resp.json().await.ok()?;
    if data.get("retCode").and_then(Value::as_str) != Some("000000") {
        return None;
    }
    data.pointer("/respData/url").and_then(Value::as_str).map(str::to_string)
}

/// 对齐 generate_qrcode：返回 (qr_content, h5_qrurl)；失败返回 ("", "")
pub async fn generate_qrcode(
    client: &Client,
    account: &Value,
    money: f64,
    trade_no: &str,
    out_trade_no: &str,
    site_url: &str,
) -> (String, String) {
    let code = account.get("code").and_then(Value::as_str).unwrap_or("");
    let qr_url = account.get("qr_url").and_then(Value::as_str).unwrap_or("").to_string();
    let zfb_pid = account.get("zfb_pid").and_then(Value::as_str).unwrap_or("").to_string();
    let cloud_id = account.get("cloud_id").and_then(Value::as_str).unwrap_or("").to_string();
    let channel_mode = account.get("channel_mode").and_then(Value::as_i64).unwrap_or(0);

    let direct = |h5: &str| (qr_url.clone(), h5.to_string());
    let fallback = |code: &str| -> (String, String) {
        // 对齐 _fallback_qr：qr_url 兜底
        if !qr_url.is_empty() {
            if code.contains("wxpay") {
                return (qr_url.clone(), wx_h5(&qr_url));
            }
            return (qr_url.clone(), qr_url.clone());
        }
        (String::new(), String::new())
    };

    match code {
        // 直传码：直接返回上传的收款码
        "wxpay_dy" | "wxpay_software" => direct(&wx_h5(&qr_url)),
        "wxpay_cloudzs" => {
            // 云端助手记录的通用二维码：尝试提取内层真实收款链接
            if qr_url.starts_with("http") {
                if let Ok(parsed) = serde_json::from_str::<Value>(&qr_url) {
                    let inner = ["qr_url", "url", "code_url"]
                        .iter()
                        .find_map(|k| parsed.get(*k).and_then(Value::as_str))
                        .unwrap_or("");
                    if !inner.is_empty() {
                        return (inner.to_string(), wx_h5(inner));
                    }
                }
            }
            direct(&wx_h5(&qr_url))
        }
        "wxpay_cloud" | "wxpay_jym_cloud" | "wxpay_skd" => {
            // Python 侧云端 API 为 TODO（返回 None），这里对齐返回 None 并回落 qr_url
            if !cloud_id.is_empty() {
                tracing::warn!("[YPay] 云端渠道 {} 的 API 未实现（与 Python 一致），回落 qr_url", code);
            }
            fallback(code)
        }
        "alipay_software" => direct("alipays://"),
        "alipay_grmg" | "alipay_mck" => {
            // 账单链接模式
            if zfb_pid.is_empty() {
                tracing::warn!("[YPay] 支付宝渠道 {} 未配置 zfb_pid", code);
                return if !qr_url.is_empty() { direct("alipays://") } else { (String::new(), String::new()) };
            }
            gen_alipay_transfer_qr(&zfb_pid, money, out_trade_no, site_url, channel_mode)
        }
        // 官方 SDK 不移植，对齐 Python SDK ImportError 时回落 qr_url
        "alipay_dmf" | "alipay_official" => direct("alipays://"),
        "lkl_alipay" | "lkl_wxpay" => {
            match gen_lakala_qr(client, account, money, out_trade_no).await {
                Some(url) => (url.clone(), url),
                None => (String::new(), String::new()),
            }
        }
        "dougong_wxpay" | "dougong_alipay" | "lebrush_wxpay" | "lebrush_alipay" => {
            let is_wx = code.contains("wxpay");
            if is_wx {
                let h5 = if qr_url.is_empty() { "weixin://".to_string() } else { wx_h5(&qr_url) };
                (qr_url, h5)
            } else {
                let h5 = if qr_url.is_empty() { "alipays://".to_string() } else { qr_url.clone() };
                (qr_url, h5)
            }
        }
        _ => fallback(code),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use base64::Engine as _;

    /// 回归测试：收银台二维码必须真的出图。
    /// 此前 qr_image 恒为 null，导致支付弹窗永远停在「生成二维码中…」。
    #[test]
    fn test_render_qr_data_url_produces_valid_png() {
        // 覆盖三种真实渠道码形态：微信 schema / 支付宝 schema / http 图片
        for content in [
            "wxp://f2f0abcdefghijklmn",
            "https://qr.alipay.com/abc123456",
            "https://example.com/pay.png",
        ] {
            let url = render_qr_data_url(content)
                .unwrap_or_else(|| panic!("应能为 {content} 生成二维码"));
            assert!(url.starts_with("data:image/png;base64,"), "应为 PNG data URL: {url}");
            let b64 = url.trim_start_matches("data:image/png;base64,");
            let bytes = base64::engine::general_purpose::STANDARD
                .decode(b64)
                .expect("data URL 里的 base64 应可解码");
            // PNG magic number：确认不是空图或错误格式
            assert_eq!(&bytes[..8], b"\x89PNG\r\n\x1a\n", "应为合法 PNG");
            assert!(bytes.len() > 200, "PNG 体积过小，疑似未真正渲染: {} 字节", bytes.len());
        }
    }

    #[test]
    fn test_render_qr_empty_content_is_null() {
        // 内容为空（渠道未返回码）时保持历史语义：回落到 null，不 panic
        assert!(render_qr_data_url("").is_none());
        assert!(render_qr_data_url("   ").is_none());
        assert!(render_qr_image_value("").is_null());
    }

    #[test]
    fn test_detect_qr_content_type() {
        assert_eq!(detect_qr_content_type("https://x.com/a.png"), "image_url");
        assert_eq!(detect_qr_content_type("https://x.com/a.jpg?x=1"), "image_url");
        assert_eq!(detect_qr_content_type("wxp://f2f0abc"), "wxpay");
        assert_eq!(detect_qr_content_type("https://wx.tenpay.com/x"), "wxpay");
        assert_eq!(detect_qr_content_type("https://qr.alipay.com/abc"), "alipay");
        assert_eq!(detect_qr_content_type("alipays://platformapi/x"), "alipay");
        assert_eq!(detect_qr_content_type("https://render.alipay.com/p/x"), "alipay");
        assert_eq!(detect_qr_content_type("https://example.com/pay"), "url");
        assert_eq!(detect_qr_content_type("some raw text"), "raw");
        assert_eq!(detect_qr_content_type(""), "raw");
    }

    #[test]
    fn test_quote() {
        assert_eq!(quote_full("a/b?c=d&e=f"), "a%2Fb%3Fc%3Dd%26e%3Df");
        assert_eq!(quote_keep_slash("a/b?c=d"), "a/b%3Fc%3Dd");
        assert_eq!(quote_full("alipays://platformapi/startapp?appId=1"), "alipays%3A%2F%2Fplatformapi%2Fstartapp%3FappId%3D1");
        // ~ 不编码（对齐 Python quote 的 always-safe 字符集）
        assert_eq!(quote_full("a~b_c.d-e"), "a~b_c.d-e");
    }

    #[test]
    fn test_gen_alipay_transfer_qr() {
        let (qr, h5) = gen_alipay_transfer_qr("2088xxxx", 10.5, "OUT1", "http://s", 1);
        // 对齐 Python：外层 quote(safe='/') 把 ':' '?' '=' 全编码，仅 '/' 保留
        assert!(qr.starts_with("https%3A//render.alipay.com/p/c/mdeduct-landing%3Fscheme%3D"));
        assert!(qr.contains("mdeduct-landing%3Fscheme%3D"));
        assert!(!qr.contains("?scheme="), "{qr}");
        assert!(h5.starts_with("alipays://platformapi/startapp?appId=20000067&url="));
        let (qr2, _) = gen_alipay_transfer_qr("2088", 10.5, "O", "http://s", 9);
        assert!(qr2.contains("alipayTransfer.php"));
        let (empty, _) = gen_alipay_transfer_qr("", 10.5, "O", "http://s", 1);
        assert!(empty.is_empty());
    }
}

//! 验证码 OCR — 使用 CNWeiWei/ddddocr-rs（crates.io 发布版，tract 1.x 后端）
//!
//! 不重复造轮子：管线（LANCZOS/PIL 灰度/归一化/CTC）由 ddddocr-core 元数据驱动，
//! 与 Python ddddocr 新一代引擎对齐。模型与字符集外部提供：
//! - OCR_MODEL_PATH  默认 site-packages/ddddocr/common_old.onnx
//!   （ddddocr 默认模型；common.onnx 是 beta=True 模型，输出分布不同，勿混用）
//! - OCR_CHARSET_PATH 默认 rust_worker/ddddocr_charset.json（8210 字符，已导出）

use std::borrow::Cow;
use std::sync::OnceLock;

use anyhow::{bail, Context, Result};
use ddddocr_core::traits::OcrEngine;
use crate::ocr_ort::session::{build_session, OcrRuntime};

use ddddocr_core::{Charset, ModelMetadata, Normalization, OcrBuilder, Resize};

/// 手动加载 ONNX Runtime DLL 并通过 set_api 注入（只执行一次，幂等）。
fn init_ort_from_dll() -> Result<()> {
    static ORT_INIT: OnceLock<Result<(), String>> = OnceLock::new();
    let r = ORT_INIT.get_or_init(|| {
        let dll_path = std::env::var("ORT_DYLIB_PATH").unwrap_or_else(|_| {
            r"D:\dev\python\Lib\site-packages\onnxruntime\capi\onnxruntime.dll".to_string()
        });
        (|| -> Result<(), String> {
            let lib = unsafe { libloading::Library::new(&dll_path) }
                .map_err(|e| format!("dlopen {dll_path} 失败: {e}"))?;
            type GetApiBase = unsafe extern "C" fn() -> *const ort::sys::OrtApiBase;
            let get_base: libloading::Symbol<GetApiBase> = unsafe { lib.get(b"OrtGetApiBase") }
                .map_err(|e| format!("OrtGetApiBase 导出缺失: {e}"))?;
            let base = unsafe { get_base() };
            if base.is_null() {
                return Err("OrtGetApiBase 返回空指针".into());
            }
            // API 版本协商：请求 ort-sys 编译期绑定的版本（17），
            // DLL 返回 <= 该版本且 >= 其最低支持的 OrtApi 表
            let api: *const ort::sys::OrtApi = unsafe { ((*base).GetApi)(ort::sys::ORT_API_VERSION) };
            if api.is_null() {
                return Err(format!("GetApi({}) 返回空指针，DLL 版本过低", ort::sys::ORT_API_VERSION));
            }
            std::mem::forget(lib); // 保持 DLL 常驻
            if !ort::set_api(unsafe { api.read() }) {
                return Err("ort::set_api 被抢占（API 已设置）".into());
            }
            Ok(())
        })()
    });
    match r {
        Ok(()) => Ok(()),
        Err(e) => bail!("{e}"),
    }
}

pub struct CaptchaOcr {
    runtime: &'static OcrRuntime,
}

impl CaptchaOcr {
    pub fn load(model_path: &str, charset_path: &str) -> Result<Self> {
        let charset_json = std::fs::read_to_string(charset_path)
            .with_context(|| format!("字符集读取失败: {charset_path}"))?;
        let tokens: Vec<String> = serde_json::from_str(&charset_json)
            .context("字符集解析失败")?;
        if tokens.len() < 100 {
            bail!("字符集异常: 仅 {} 项", tokens.len());
        }
        let charset = Charset::new(tokens.into_iter().map(Cow::Owned).collect());

        // 新一代引擎元数据：DynamicWidth(64) 对应 Python 的 resize=[-1, 64]
        let metadata = ModelMetadata::new(
            charset,
            false,
            Resize::DynamicWidth(64),
            1,
            Normalization::ZeroToOne,
        );

        // alternative-backend 模式：手动 dlopen ONNX Runtime DLL 并注入 API。
        // 绕过 ort load-dynamic 的版本检查——其仅比较 minor 版本号（要求 >= 1.23），
        // 而实际 ABI 兼容按 OrtApiBase::GetApi(17) 协商，Python 的 1.20.1 DLL 完全可用。
        init_ort_from_dll()?;

        let session = build_session(model_path)?;
        let runtime: &'static OcrRuntime = Box::leak(Box::new(OcrRuntime::new(session, metadata)));
        tracing::info!(model_path, "OCR 引擎就绪（ddddocr-rs + ONNX Runtime）");
        Ok(CaptchaOcr { runtime })
    }

    pub fn recognize(&self, img_bytes: &[u8]) -> Result<String> {
        let img = image::load_from_memory(img_bytes).context("图片解码失败")?;
        // 每次调用临时构建 Ocr（build_with 为轻量包装，无推理开销）
        let ocr = OcrBuilder::new().build_with(self.runtime);
        let result = ocr.predict(&img).map_err(|e| anyhow::anyhow!("{e}"))?;
        Ok(result.into_text())
    }
}

pub static ENGINE: OnceLock<Result<CaptchaOcr, String>> = OnceLock::new();

pub fn engine() -> Result<&'static CaptchaOcr> {
    let r = ENGINE.get_or_init(|| {
        let model_path = std::env::var("OCR_MODEL_PATH")
            .unwrap_or_else(|_| r"D:\dev\python\Lib\site-packages\ddddocr\common_old.onnx".to_string());
        let charset_path = std::env::var("OCR_CHARSET_PATH")
            .unwrap_or_else(|_| {
                std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                    .join("ddddocr_charset.json")
                    .to_string_lossy()
                    .to_string()
            });
        CaptchaOcr::load(&model_path, &charset_path).map_err(|e| e.to_string())
    });
    match r {
        Ok(e) => Ok(e),
        Err(e) => bail!("{e}"),
    }
}

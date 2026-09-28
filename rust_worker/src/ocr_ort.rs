//! Vendored from ddddocr-ort 0.2.4 (MIT OR Apache-2.0, CNWeiWei/ddddocr-rs).
//! 只保留 OCR + CPU 路径：源码直接内置后，ort 的 feature 由本 crate 全权控制
//! （原 crate 的 default features 会强制开启 ort/api-27，超出本机 ORT 1.20 的 ABI）。

pub mod session {
    use std::sync::{Arc, Mutex, MutexGuard};

    use anyhow::{anyhow, Result};
    use ddddocr_core::error::TensorError;
    use ddddocr_core::traits::{InferenceEngine, Info, Loader, OcrEngine};
    use ddddocr_core::types::{AxisDim, ModelInfo, TensorInfo, TensorType};
    use ddddocr_core::utils::normalize_ocr_logits;
    use ddddocr_core::{ModelMetadata, OcrOutput};
    use ndarray::Array4;
    use ort::inputs;
    use ort::session::Session as OrtSession;
    use ort::value::{PrimitiveTensorElementType, TensorElementType, TensorRef, Value, ValueType};

    /// ORT 会话句柄：推理时通过互斥锁串行访问。
    pub type Session = Arc<Mutex<OrtSession>>;

    /// OCR 推理运行时：持有 ORT 会话与模型元数据。
    pub struct OcrRuntime {
        pub session: Session,
        pub metadata: ModelMetadata,
    }

    impl OcrRuntime {
        pub fn new(session: Session, metadata: ModelMetadata) -> Self {
            Self { session, metadata }
        }

        fn resolve_outlets(&self, outlets: &[ort::value::Outlet]) -> ddddocr_core::error::Result<Vec<TensorInfo>> {
            Ok(outlets
                .iter()
                .map(|outlet| TensorInfo {
                    name: outlet.name().to_string(),
                    shape: resolve_shape(outlet.dtype()),
                    tensor_type: tensor_type_from_ort(outlet.dtype()),
                })
                .collect())
        }
    }

    fn tensor_type_from_ort(dtype: &ValueType) -> TensorType {
        match dtype.tensor_type() {
            Some(TensorElementType::Float32) => TensorType::F32,
            Some(TensorElementType::Int64) => TensorType::I64,
            _ => TensorType::Other,
        }
    }

    fn resolve_shape(dtype: &ValueType) -> Vec<AxisDim> {
        dtype
            .tensor_shape()
            .map(|shape| {
                shape
                    .iter()
                    .map(|&dim| {
                        if dim >= 0 {
                            AxisDim::Static(dim as usize)
                        } else {
                            AxisDim::Dynamic("dynamic".to_string())
                        }
                    })
                    .collect()
            })
            .unwrap_or_default()
    }

    impl OcrEngine for OcrRuntime {
        fn metadata(&self) -> &ModelMetadata {
            &self.metadata
        }
    }

    fn lock_session(session: &Session) -> Result<MutexGuard<'_, OrtSession>, TensorError> {
        session
            .lock()
            .map_err(|_| TensorError::Engine("获取 Session 锁失败 (Poisoned)".to_string()))
    }

    fn extract_tensor<T: PrimitiveTensorElementType>(
        value: &Value,
    ) -> Result<(ndarray::ArrayViewD<'_, T>, Vec<usize>), TensorError> {
        let (shape_ref, slice) = value
            .try_extract_tensor::<T>()
            .map_err(|_| TensorError::Engine("无法获取张量内存视图".to_string()))?;
        let shape: Vec<usize> = shape_ref.iter().map(|v| *v as usize).collect();
        let view = ndarray::ArrayViewD::from_shape(shape.as_slice(), slice)
            .map_err(|_| TensorError::Engine("构建 ndarray ArrayViewD 失败".to_string()))?;
        Ok((view, shape))
    }

    impl InferenceEngine for OcrRuntime {
        type Output = OcrOutput;

        fn inference(&self, input_array: Array4<f32>) -> Result<Self::Output, TensorError> {
            let mut session_guard = lock_session(&self.session)?;
            let result = session_guard
                .run(inputs![TensorRef::from_array_view(&input_array)
                    .map_err(|e| TensorError::Engine(format!("构建输入失败: {e}")))?])
                .map_err(|e| TensorError::Engine(format!("执行模型推理失败: {e}")))?;
            let raw_value = &result[0];

            match raw_value.dtype().tensor_type() {
                Some(TensorElementType::Int64) => {
                    let (view, actual_shape) = extract_tensor::<i64>(raw_value)?;
                    let array1 = view
                        .to_owned()
                        .into_dimensionality::<ndarray::Ix1>()
                        .map_err(|_| TensorError::DimensionMismatch {
                            expected: "1D 字符索引静态矩阵".to_string(),
                            actual: actual_shape,
                        })?;
                    Ok(OcrOutput::Indices(array1))
                }
                Some(TensorElementType::Float32) => {
                    let shape = raw_value.shape();
                    let (view, shape_vec) = extract_tensor::<f32>(raw_value)?;
                    normalize_ocr_logits(view, shape_vec.as_slice())
                }
                _ => Err(TensorError::UnknownOutputFormat),
            }
        }
    }

    impl Info for OcrRuntime {
        fn input_info(&self) -> ddddocr_core::error::Result<Vec<TensorInfo>> {
            let guard = lock_session(&self.session).map_err(ddddocr_core::error::DdddError::from)?;
            self.resolve_outlets(guard.inputs())
        }

        fn output_info(&self) -> ddddocr_core::error::Result<Vec<TensorInfo>> {
            let guard = lock_session(&self.session).map_err(ddddocr_core::error::DdddError::from)?;
            self.resolve_outlets(guard.outputs())
        }

        fn model_info(&self) -> ddddocr_core::error::Result<ModelInfo> {
            Ok(ModelInfo {
                inputs: self.input_info()?,
                outputs: self.output_info()?,
                providers: None,
            })
        }
    }

    /// 从文件路径构建 ORT 会话（CPU，单线程配置可选）。
    pub fn build_session(model_path: &str) -> Result<Session> {
        let session = OrtSession::builder()
            .map_err(|e| anyhow!("构建 ORT SessionBuilder 失败: {e}"))?
            .commit_from_file(model_path)
            .map_err(|e| anyhow!("加载 ONNX 模型失败 {model_path}: {e}"))?;
        Ok(Arc::new(Mutex::new(session)))
    }
}

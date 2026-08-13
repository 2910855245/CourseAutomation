"""OCR sidecar 服务 — 独立进程承载 ddddocr。

为什么独立进程：
- 主进程（granian）不再加载 onnxruntime+模型（~70MB）与执行 CPU 推理
- 崩溃隔离：OCR 库异常不带走 API 主进程
- 可独立重启/升级，不用重启整个服务

运行方式:
    uvicorn ocr_sidecar:app --host 127.0.0.1 --port 17018
生产环境用 deploy/ocr-sidecar.service（systemd）。

注：曾对照测试 Rust 移植版 86maid/ddddocr（同一 ONNX 模型文件），
在真实平台验证码上与本进程的新一代 ddddocr 引擎 75% 输出不一致
（大小写/字符判别差异），为保证登录成功率保留 Python 引擎。
"""
import base64

import uvicorn
from fastapi import FastAPI
from loguru import logger
from pydantic import BaseModel

app = FastAPI(title="OCR Sidecar", docs_url=None, redoc_url=None)

_ocr = None


def _get_ocr():
    """懒加载 ddddocr 单例（模型加载较重，进程内只加载一次）"""
    global _ocr
    if _ocr is None:
        import ddddocr
        _ocr = ddddocr.DdddOcr(show_ad=False)
    return _ocr


class OcrRequest(BaseModel):
    image_base64: str


@app.get("/health")
def health():
    return {"ok": True, "model_loaded": _ocr is not None}


@app.post("/ocr")
def ocr(req: OcrRequest):
    try:
        img = base64.b64decode(req.image_base64)
        code = _get_ocr().classification(img)
        return {"code": code}
    except Exception as e:
        logger.error(f"OCR 识别失败: {e}")
        return {"code": "", "error": str(e)}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=17018, log_level="info")

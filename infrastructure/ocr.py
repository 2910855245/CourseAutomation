"""OCR 客户端 — 调用独立 OCR sidecar 服务（默认 127.0.0.1:17018）。

ddddocr 已从主进程剥离：模型加载与 CPU 推理全部移入 ocr_sidecar.py 进程，
这里只保留与旧接口一致的 HTTP 包装（classification(img_bytes) -> str），
所有调用点（登录/重登/need_code 验证码）零改动。
"""
import base64

import httpx

from config import settings


class OcrClient:
    """ddddocr 接口兼容包装"""

    def __init__(self, base_url: str, timeout: float = 15.0):
        self._url = base_url.rstrip("/") + "/ocr"
        self._timeout = timeout

    def classification(self, img_bytes) -> str:
        payload = {"image_base64": base64.b64encode(img_bytes).decode()}
        try:
            resp = httpx.post(self._url, json=payload, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                raise RuntimeError(f"OCR sidecar 识别失败: {data['error']}")
            return data.get("code", "") or ""
        except httpx.HTTPError as e:
            raise RuntimeError(f"OCR sidecar 不可达 ({self._url}): {e}") from e


_ocr = None


def get_ocr() -> OcrClient:
    """懒加载 OCR 客户端单例（进程内只建一次）"""
    global _ocr
    if _ocr is None:
        _ocr = OcrClient(settings.ocr_service_url)
    return _ocr

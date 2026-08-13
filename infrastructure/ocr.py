"""ddddocr 单例 — 全库唯一 OCR 实例（此前 3 份拷贝）。"""

_ocr_instance = None


def get_ocr():
    """懒加载 ddddocr 单例（模型加载较重，进程内只加载一次）"""
    global _ocr_instance
    if _ocr_instance is None:
        import ddddocr
        _ocr_instance = ddddocr.DdddOcr(show_ad=False)
    return _ocr_instance

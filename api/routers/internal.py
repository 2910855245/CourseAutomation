"""内部 sidecar 端点 — 供 Rust 刷课守护进程回调。

- POST /api/internal/ocr     验证码识别（need_code==1 图形码 / ==2 点选码）
- POST /api/internal/relogin 平台重新登录（返回新 cookie）

鉴权：X-Worker-Token 校验（与 /live/push 一致），localhost 来源豁免。
"""

import base64
import hmac

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.models import ApiResponse
from config import settings

router = APIRouter(prefix="/api/internal", tags=["内部回调"])


def _check_token(request: Request):
    if not settings.worker_token:
        return
    client_host = request.client.host if request.client else ""
    if client_host in ("127.0.0.1", "::1", "localhost"):
        return
    token = request.headers.get("X-Worker-Token", "")
    if not token or not hmac.compare_digest(token, settings.worker_token):
        raise HTTPException(status_code=401, detail="无效的 Worker 凭证")


class OcrRequest(BaseModel):
    image_base64: str
    need_code: int = 1
    verify_token: str = ""
    base_url: str = ""
    node_id: str = ""


@router.post("/ocr", response_model=ApiResponse)
def internal_ocr(req: OcrRequest, request: Request):
    """验证码识别：图形码 ddddocr；点选码走 XCaptchaSolver（盾点服务）"""
    _check_token(request)
    try:
        img = base64.b64decode(req.image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="图片数据无效")

    if req.need_code == 2:
        from infrastructure.school.captcha import XCaptchaSolver
        ak = settings.captcha_ak or '38570387e765646dff8372d4ec9e3c38'
        dun_url = settings.captcha_url or 'https://shixun.kaikangxinxi.com/api/dunclick.json'
        solver = XCaptchaSolver(dun_url, ak, req.verify_token)
        try:
            solver.solve()  # 盾点服务按 verify token 记账，成功后平台侧即放行
            return ApiResponse(data={"code": "", "solved": True})
        except Exception as e:
            return ApiResponse(success=False, message=f"点选验证码处理失败: {e}")
    else:
        try:
            from infrastructure.ocr import get_ocr
            code = get_ocr().classification(img)
        except Exception as e:
            return ApiResponse(success=False, message=f"OCR 识别失败: {e}")
        # 平台要求 4 字符 + 下划线格式
        return ApiResponse(data={"code": f"{code}_", "solved": True})


class ReloginRequest(BaseModel):
    base_url: str
    username: str
    password: str


@router.post("/relogin", response_model=ApiResponse)
def internal_relogin(req: ReloginRequest, request: Request):
    """平台重新登录（Rust daemon cookie 过期时回调），返回新 cookie 列表"""
    _check_token(request)
    from config.platforms import WEBSITES
    from services.multi_platform_auth import login_single_platform

    website_id = None
    for wid, info in WEBSITES.items():
        if info.get("base_url", "").rstrip("/") == req.base_url.rstrip("/"):
            website_id = wid
            break
    if website_id is None:
        return ApiResponse(success=False, message=f"未识别的平台: {req.base_url}")

    try:
        _, ok, session, msg = login_single_platform(website_id, req.username, req.password)
    except Exception as e:
        return ApiResponse(success=False, message=f"登录异常: {e}")
    if not ok:
        return ApiResponse(success=False, message=msg or "登录失败")

    cookies = [{"name": c.name, "value": c.value} for c in session.cookies]
    return ApiResponse(data={"ok": True, "cookies": cookies})

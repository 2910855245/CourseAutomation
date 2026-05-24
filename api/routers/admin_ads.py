import json
import os

from loguru import logger
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import get_current_admin, get_current_user
from api.database import db
from api.models import ApiResponse

router = APIRouter(prefix="/api/admin", tags=["管理-广告&代理设置"])


def _require_admin(current_user: dict = Depends(get_current_user)):
    return get_current_admin(current_user)


# ── 广告管理 ──

class AdCreateRequest(BaseModel):
    slot: int
    name: str = ""
    html_content: str = ""

class AdUpdateRequest(BaseModel):
    name: str = None
    html_content: str = None
    is_active: int = None


@router.get("/ads", response_model=ApiResponse)
def list_ads(admin: dict = Depends(_require_admin)):
    return ApiResponse(data=db.list_ads())


@router.post("/ads", response_model=ApiResponse)
def create_ad(body: AdCreateRequest, admin: dict = Depends(_require_admin)):
    if body.slot < 1 or body.slot > db.MAX_ADS:
        return {"code": -1, "message": f"广告位编号必须在 1-{db.MAX_ADS} 之间"}
    result = db.create_ad(slot=body.slot, name=body.name, html_content=body.html_content)
    if not result:
        return {"code": -1, "message": "添加失败，该位置可能已被占用"}
    return ApiResponse(data=result, message="添加成功")


@router.put("/ads/{ad_id}", response_model=ApiResponse)
def update_ad(ad_id: int, body: AdUpdateRequest, admin: dict = Depends(_require_admin)):
    fields = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.html_content is not None:
        fields["html_content"] = body.html_content
    if body.is_active is not None:
        fields["is_active"] = body.is_active
    if not fields:
        return {"code": -1, "message": "没有需要更新的字段"}
    ok = db.update_ad(ad_id, **fields)
    return ApiResponse(success=ok, message="更新成功" if ok else "更新失败")


@router.delete("/ads/{ad_id}", response_model=ApiResponse)
def delete_ad(ad_id: int, admin: dict = Depends(_require_admin)):
    ok = db.delete_ad(ad_id)
    return ApiResponse(success=ok, message="删除成功" if ok else "删除失败")


# ── 公开广告接口（无需登录）──

public_ads_router = APIRouter(prefix="/api/ads", tags=["广告公开接口"])


@public_ads_router.get("", response_model=ApiResponse)
def list_active_ads():
    return ApiResponse(data=db.list_active_ads())


@public_ads_router.get("/{ad_id}/page")
def render_ad_page(ad_id: int):
    from fastapi.responses import HTMLResponse
    ad = db.get_ad(ad_id)
    if not ad or not ad["is_active"]:
        raise HTTPException(status_code=404, detail="广告不存在")
    return HTMLResponse(content=ad["html_content"])


# ── 代理设置 ──

class ProxySettingsRequest(BaseModel):
    enabled: bool = False
    url: str = ""
    username: str = ""
    password: str = ""


@router.get("/proxy")
def get_proxy_settings(admin: dict = Depends(_require_admin)):
    return ApiResponse(data={
        "enabled": db.ypay_setting_get("proxy_enabled", "0") == "1",
        "url": db.ypay_setting_get("proxy_url", ""),
        "username": db.ypay_setting_get("proxy_username", ""),
        "password": db.ypay_setting_get("proxy_password", ""),
    })


@router.post("/proxy")
def save_proxy_settings(payload: ProxySettingsRequest, admin: dict = Depends(_require_admin)):
    db.ypay_setting_set("proxy_enabled", "1" if payload.enabled else "0")
    db.ypay_setting_set("proxy_url", payload.url.strip())
    db.ypay_setting_set("proxy_username", payload.username.strip())
    db.ypay_setting_set("proxy_password", payload.password.strip())
    _data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
    os.makedirs(_data_dir, exist_ok=True)
    with open(os.path.join(_data_dir, "proxy.json"), "w") as f:
        json.dump({
            "enabled": payload.enabled,
            "url": payload.url.strip(),
            "username": payload.username.strip(),
            "password": payload.password.strip(),
        }, f)
    return ApiResponse(message="代理设置已保存")


@router.post("/proxy/test")
def test_proxy(payload: ProxySettingsRequest, admin: dict = Depends(_require_admin)):
    url = payload.url.strip()
    if not url:
        return ApiResponse(success=False, message="请输入代理地址")
    try:
        import httpx
        proxies = {"http": url, "https": url}
        if payload.username:
            from urllib.parse import quote
            user = quote(payload.username, safe='')
            pwd = quote(payload.password, safe='') if payload.password else ''
            if "://" in url:
                scheme, rest = url.split("://", 1)
                creds = f"{user}:{pwd}@" if pwd else f"{user}@"
                auth_url = f"{scheme}://{creds}{rest}"
            else:
                auth_url = f"http://{user}:{pwd}@{url}" if pwd else f"http://{user}@{url}"
            proxies["http"] = auth_url
            proxies["https"] = auth_url
            proxies["https"] = proxies["http"]
        resp = httpx.get("https://myip.ipip.net", proxies=proxies, timeout=10)
        if resp.status_code == 200:
            exit_ip = resp.text.strip()[:100]
            return ApiResponse(data={"exit_ip": exit_ip}, message=f"代理连通，出口 {exit_ip}")
        return ApiResponse(success=False, message=f"代理返回异常状态码 {resp.status_code}")
    except httpx.ProxyError:
        return ApiResponse(success=False, message="代理连接失败：代理地址不可达")
    except httpx.ConnectTimeout:
        return ApiResponse(success=False, message="代理连接超时：代理服务器无响应")
    except Exception as e:
        return ApiResponse(success=False, message=f"代理测试失败：{str(e)[:80]}")

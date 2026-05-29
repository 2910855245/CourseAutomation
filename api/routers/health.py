"""平台健康监控 API 路由"""
import json
from typing import List

from loguru import logger
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.auth import get_current_admin
from api.models import ApiResponse


router = APIRouter(prefix="/api/health", tags=["健康监控"])


@router.get("/ready")
async def readiness_probe():
    """Kubernetes readiness probe — 检查数据库和队列是否就绪"""
    checks = {}
    healthy = True

    # 数据库连通性
    try:
        from api.database import db
        db.config_get("_readiness_ping")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:100]}"
        healthy = False

    # 队列是否已启动
    try:
        from api.services.task_queue import school_queue
        stats = school_queue.get_stats()
        checks["queue"] = "ok"
    except Exception as e:
        checks["queue"] = f"error: {str(e)[:100]}"
        healthy = False

    status_code = 200 if healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if healthy else "not_ready", "checks": checks},
    )


@router.get("/live")
async def liveness_probe():
    """Kubernetes liveness probe — 进程存活即返回 200"""
    return {"status": "alive"}

CONFIG_HEALTH_INTERVAL = "health_check_interval"
CONFIG_HEALTH_ACCOUNTS = "health_check_accounts"
DEFAULT_INTERVAL = 3600


@router.get("/summary", response_model=ApiResponse)
async def health_summary(admin=Depends(get_current_admin)):
    """获取平台健康检查摘要"""
    from infrastructure.platform_health import get_health_summary
    return ApiResponse(data=get_health_summary())


class IntervalRequest(BaseModel):
    interval: int = Field(..., ge=300, le=86400, description="检查间隔（秒），范围 300-86400")


@router.get("/interval", response_model=ApiResponse)
async def get_interval(admin=Depends(get_current_admin)):
    """获取健康检查间隔"""
    from api.database import db
    val = db.config_get(CONFIG_HEALTH_INTERVAL)
    return ApiResponse(data={"interval": int(val) if val else DEFAULT_INTERVAL})


@router.put("/interval", response_model=ApiResponse)
async def set_interval(req: IntervalRequest, admin=Depends(get_current_admin)):
    """设置健康检查间隔"""
    from api.database import db
    db.config_set(CONFIG_HEALTH_INTERVAL, str(req.interval))
    import infrastructure.platform_health as ph
    ph.CHECK_INTERVAL = req.interval
    return ApiResponse(message=f"检查间隔已设置为 {req.interval} 秒", data={"interval": req.interval})


def _get_accounts() -> list:
    from api.database import db
    raw = db.config_get(CONFIG_HEALTH_ACCOUNTS)
    if raw:
        try:
            return json.loads(raw)
        except Exception as e:
            pass
    # 兼容旧的单账号配置
    old_user = db.config_get("health_check_username") or ""
    old_pass = db.config_get("health_check_password") or ""
    if old_user:
        accounts = [{"username": old_user, "password": old_pass, "active": True}]
        db.config_set(CONFIG_HEALTH_ACCOUNTS, json.dumps(accounts, ensure_ascii=False))
        return accounts
    return []


def _get_active_account(website_id: int = None) -> dict:
    """获取活跃的检测账号，根据平台类型返回对应的账号"""
    accounts = _get_accounts()
    if website_id:
        # 学习通 (website_id=4) 使用 chaoxing 类型账号
        target_type = "chaoxing" if website_id == 4 else "school"
        for a in accounts:
            if a.get("website_type", "school") == target_type and a.get("active"):
                return a
        # fallback: 同类型第一个
        for a in accounts:
            if a.get("website_type", "school") == target_type:
                return a
    # 默认返回任意活跃账号
    for a in accounts:
        if a.get("active"):
            return a
    return accounts[0] if accounts else {}


@router.get("/account", response_model=ApiResponse)
async def get_health_account(admin=Depends(get_current_admin)):
    """获取健康检测账号列表"""
    accounts = _get_accounts()
    return ApiResponse(data={"accounts": accounts})


class AccountItem(BaseModel):
    username: str
    password: str
    active: bool = False
    website_type: str = "school"  # "school" 或 "chaoxing"


class AccountsRequest(BaseModel):
    accounts: List[AccountItem]


@router.put("/account", response_model=ApiResponse)
async def set_health_account(req: AccountItem, admin=Depends(get_current_admin)):
    """设置健康检测账号（学校平台/学习通分开）"""
    accounts = _get_accounts()
    target_type = req.website_type or "school"
    found = False
    for a in accounts:
        if a.get("website_type", "school") == target_type:
            a["username"] = req.username
            a["password"] = req.password
            a["active"] = True
            found = True
        else:
            a["active"] = a.get("website_type", "school") != target_type
    if not found:
        accounts.append({"username": req.username, "password": req.password, "active": True, "website_type": target_type})
    from api.database import db
    db.config_set(CONFIG_HEALTH_ACCOUNTS, json.dumps(accounts, ensure_ascii=False))
    type_name = "学习通" if target_type == "chaoxing" else "学校平台"
    return ApiResponse(message=f"{type_name}检测账号已设置为 {req.username}")


@router.put("/accounts", response_model=ApiResponse)
async def set_health_accounts(req: AccountsRequest, admin=Depends(get_current_admin)):
    """批量设置健康检测账号"""
    from api.database import db
    accounts = [{"username": a.username, "password": a.password, "active": a.active} for a in req.accounts]
    db.config_set(CONFIG_HEALTH_ACCOUNTS, json.dumps(accounts, ensure_ascii=False))
    return ApiResponse(message="账号设置已保存")


def _save_login_error(wid: int, username: str, login_error: str) -> dict:
    """构建登录失败结果并持久化到 JSON 文件"""
    import os
    from datetime import datetime

    from config import WEBSITES
    from infrastructure.platform_health import HEALTH_ALL_FILE, _load_json, _save_json

    platform_name = WEBSITES.get(wid, {}).get("name", f"平台{wid}")
    error_msg = login_error or "登录失败，请检查账号密码是否正确"
    error_result = {
        "website_id": wid,
        "website_name": platform_name,
        "username": username,
        "check_time": datetime.now().isoformat(),
        "overall": "critical",
        "checks": {"auth": {"status": "failed", "message": error_msg}},
        "error": error_msg,
    }
    per_platform_file = os.path.join(os.path.dirname(HEALTH_ALL_FILE), f"platform_health_{wid}.json")
    _save_json(per_platform_file, error_result)
    all_results = _load_json(HEALTH_ALL_FILE)
    if "platforms" not in all_results:
        all_results["platforms"] = {}
    all_results["platforms"][str(wid)] = error_result
    all_results["last_check"] = datetime.now().isoformat()
    _save_json(HEALTH_ALL_FILE, all_results)
    return error_result


def _get_session_or_login(pool, wid: int, username: str, password: str):
    """尝试获取已有会话，失败则登录。返回 (session_info, login_error)。"""
    session_info = pool.get(username, wid)
    if session_info:
        return session_info, ""
    try:
        from config import set_current_website
        set_current_website(wid)
        session_info = pool.restore(username, wid)
    except Exception:
        pass
    if session_info:
        return session_info, ""
    login_error = ""
    try:
        session_info = pool.login(username, password, wid)
    except Exception as e:
        login_error = str(e)[:200]
    return session_info, login_error


@router.post("/check/all", response_model=ApiResponse)
async def run_all_checks(admin=Depends(get_current_admin)):
    """手动触发所有平台的健康检查"""
    from api.services.session_pool import pool
    from config import WEBSITES
    from infrastructure.platform_health import PlatformHealthChecker

    results = {}
    checked_websites = set()

    for wid in WEBSITES:
        if wid in checked_websites:
            continue
        checked_websites.add(wid)
        active = _get_active_account(wid)
        target_username = active.get("username", "")
        target_password = active.get("password", "")

        if not target_username or not target_password:
            results[str(wid)] = {"website_id": wid, "error": "未配置检测账号"}
            continue

        session_info, login_error = _get_session_or_login(pool, wid, target_username, target_password)
        if not session_info:
            results[str(wid)] = _save_login_error(wid, target_username, login_error)
            continue
        checker = PlatformHealthChecker()
        results[str(wid)] = checker.run_full_check(session_info.session, wid, username=target_username)

    return ApiResponse(data=results)


@router.post("/check/{website_id}", response_model=ApiResponse)
async def run_check(website_id: int, admin=Depends(get_current_admin)):
    """手动触发指定平台的健康检查"""
    from api.services.session_pool import pool
    from config import WEBSITES
    from infrastructure.platform_health import PlatformHealthChecker

    if website_id not in WEBSITES:
        raise HTTPException(status_code=404, detail="平台不存在")

    active = _get_active_account(website_id)
    target_username = active.get("username", "")
    target_password = active.get("password", "")

    if not target_username or not target_password:
        raise HTTPException(status_code=400, detail=f"请先在健康检查设置中配置{'学习通' if website_id == 4 else '学校平台'}检测账号")

    session_info, login_error = _get_session_or_login(pool, website_id, target_username, target_password)
    if not session_info:
        return ApiResponse(data=_save_login_error(website_id, target_username, login_error))

    checker = PlatformHealthChecker()
    return ApiResponse(data=checker.run_full_check(session_info.session, website_id, username=target_username))

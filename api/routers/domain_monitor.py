from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.auth import get_current_admin
from api.models import ApiResponse
from api.services import domain_monitor

router = APIRouter(prefix="/api/admin/domain-monitor", tags=["域名监听"])


@router.get("/status", response_model=ApiResponse)
def get_status(admin: dict = Depends(get_current_admin)):
    return ApiResponse(data=domain_monitor.get_status())


@router.post("/check", response_model=ApiResponse)
def manual_check(admin: dict = Depends(get_current_admin)):
    result = domain_monitor.check_once()
    return ApiResponse(data=result)


class DomainAdd(BaseModel):
    domain: str
    name: str
    url: str


@router.post("/add", response_model=ApiResponse)
def add_domain(payload: DomainAdd, admin: dict = Depends(get_current_admin)):
    ok = domain_monitor.add_domain(payload.domain, payload.name, payload.url)
    if not ok:
        return ApiResponse(success=False, message="域名已存在")
    return ApiResponse(message="添加成功")


class DomainRemove(BaseModel):
    domain: str


@router.post("/remove", response_model=ApiResponse)
def remove_domain(payload: DomainRemove, admin: dict = Depends(get_current_admin)):
    ok = domain_monitor.remove_domain(payload.domain)
    if not ok:
        return ApiResponse(success=False, message="域名不存在")
    return ApiResponse(message="删除成功")


class IntervalSet(BaseModel):
    interval: int


@router.post("/interval", response_model=ApiResponse)
def set_interval(payload: IntervalSet, admin: dict = Depends(get_current_admin)):
    from api.database import db
    if payload.interval < 300:
        return ApiResponse(success=False, message="间隔不能小于300秒")
    db.config_set("domain_monitor_interval", str(payload.interval))
    return ApiResponse(message=f"检查间隔已设置为 {payload.interval} 秒")


# ==================== JS 反作弊监控 ====================

@router.get("/js-status", response_model=ApiResponse)
def get_js_status(admin: dict = Depends(get_current_admin)):
    return ApiResponse(data=domain_monitor.get_js_status())


@router.post("/js-check", response_model=ApiResponse)
def manual_js_check(admin: dict = Depends(get_current_admin)):
    result = domain_monitor.check_js_changes()
    return ApiResponse(data=result)


@router.get("/health", response_model=ApiResponse)
def get_health(admin: dict = Depends(get_current_admin)):
    return ApiResponse(data=domain_monitor.check_platform_health())


@router.get("/alerts", response_model=ApiResponse)
def get_alerts(
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin),
):
    return ApiResponse(data=domain_monitor.get_alerts(limit))


@router.post("/alerts/clear", response_model=ApiResponse)
def clear_alerts(admin: dict = Depends(get_current_admin)):
    domain_monitor.clear_alerts()
    return ApiResponse(message="告警历史已清除")


@router.post("/sync", response_model=ApiResponse)
def sync_platforms(admin: dict = Depends(get_current_admin)):
    """手动触发平台同步（从学校官网重新发现）"""
    result = domain_monitor.sync_from_school()
    return ApiResponse(data=result)


@router.get("/platforms", response_model=ApiResponse)
def list_active_platforms(admin: dict = Depends(get_current_admin)):
    """获取所有活跃平台（含 website_id 映射）"""
    platforms = domain_monitor.get_active_platforms()
    return ApiResponse(data=platforms)

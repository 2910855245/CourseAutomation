from loguru import logger
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.auth import get_optional_user
from api.models import ApiResponse
from services.scan_service import scan_all_platforms, scan_platform

router = APIRouter(prefix="/api/courses", tags=["课程扫描"])



@router.get("/platforms", response_model=ApiResponse)
def list_platforms():
    """获取平台列表（从 domain_monitor 统一数据源读取）"""
    from api.services.domain_monitor import get_active_platforms
    platforms = get_active_platforms()
    items = [{"id": wid, "name": info["name"], "base_url": info["base_url"]}
             for wid, info in platforms.items()]
    return ApiResponse(data=items)


class ScanRequest(BaseModel):
    username: str = Field(..., min_length=1, description="平台学号")
    password: str = Field(..., min_length=1, description="平台密码")
    include_records: bool = Field(default=True, description="是否包含学习记录(较慢)")
    force_refresh: bool = Field(default=False, description="强制刷新，忽略缓存")


class ReloginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="平台学号")
    password: str = Field(..., min_length=1, description="平台新密码")
    website_id: int = Field(..., description="平台ID")
    include_records: bool = Field(default=True, description="是否包含学习记录(较慢)")


@router.post("/scan", response_model=ApiResponse)
def scan_platforms(req: ScanRequest, current_user: dict = Depends(get_optional_user)):
    results = scan_all_platforms(req.username, req.password, req.include_records,
                                  force_refresh=req.force_refresh)
    logger.info(f"扫描结果: {len(results)} 个平台")

    total_courses = sum(len(r["courses"]) for r in results)
    ok_platforms = sum(1 for r in results if r["status"] == "ok")

    return ApiResponse(
        message=f"扫描完成: {ok_platforms}/{len(results)} 个平台登录成功, 共 {total_courses} 门课程",
        data={"platforms": results},
    )


@router.post("/relogin", response_model=ApiResponse)
def relogin_platform(req: ReloginRequest, current_user: dict = Depends(get_optional_user)):
    """单平台重新登录（用于密码错误后重试）"""
    from api.services.session_pool import pool as session_pool
    session_pool.remove(req.username, req.website_id)

    result = scan_platform(req.username, req.password, req.website_id, req.include_records)
    return ApiResponse(
        message=f"平台{'登录成功' if result['status'] == 'ok' else '登录失败'}",
        data={"platform": result},
    )


class ChaoxingScanRequest(BaseModel):
    username: str = Field(..., min_length=1, description="学习通账号（手机号）")
    password: str = Field(..., min_length=1, description="学习通密码")
    force_refresh: bool = Field(default=False, description="强制刷新，忽略缓存")


@router.post("/scan/chaoxing", response_model=ApiResponse)
def scan_chaoxing(req: ChaoxingScanRequest, current_user: dict = Depends(get_optional_user)):
    """学习通账号密码扫描"""
    from services.scan_service import scan_chaoxing

    result = scan_chaoxing(req.username, req.password, force_refresh=req.force_refresh)

    total_courses = len(result.get("courses", []))
    status = result.get("status", "error")

    if status == "ok":
        return ApiResponse(
            message=f"学习通扫描完成，共 {total_courses} 门课程",
            data={"platform": result},
        )
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=result.get("error", "扫描失败"))

from fastapi import APIRouter, Depends, HTTPException

from loguru import logger

from api.auth import get_current_user
from api.models import AccountStatus, ApiResponse, LoginRequest
from api.services.session_pool import pool as session_pool

router = APIRouter(prefix="/api/accounts", tags=["账号管理"])


@router.post("/login", response_model=ApiResponse)
def login_account(req: LoginRequest):
    try:
        info = session_pool.login(req.username, req.password, req.website_id)
        return ApiResponse(
            success=True,
            message="登录成功",
            data={
                "username": info.username,
                "website_id": info.website_id,
                "student_name": info.student_name,
            },
        )
    except Exception as e:
        logger.error("登录失败: {}", e)
        raise HTTPException(status_code=400, detail="登录失败，请检查账号信息")


@router.get("/status", response_model=ApiResponse)
def check_status(username: str, website_id: int, current_user: dict = Depends(get_current_user)):
    valid = session_pool.check_valid(username, website_id)
    info = session_pool.get(username, website_id)
    return ApiResponse(
        success=True,
        data=AccountStatus(
            username=username,
            website_id=website_id,
            student_name=info.student_name if info else "",
            is_valid=valid,
            last_used=info.last_used.isoformat() if info else None,
        ).dict(),
    )


@router.post("/refresh-cookie", response_model=ApiResponse)
def refresh_cookie(req: LoginRequest, current_user: dict = Depends(get_current_user)):
    try:
        session_pool.remove(req.username, req.website_id)
        info = session_pool.login(req.username, req.password, req.website_id)
        return ApiResponse(
            success=True,
            message="Cookie已刷新",
            data={
                "username": info.username,
                "student_name": info.student_name,
            },
        )
    except Exception as e:
        logger.error("刷新Cookie失败: {}", e)
        raise HTTPException(status_code=400, detail="刷新Cookie失败，请检查账号信息")


@router.get("/list", response_model=ApiResponse)
def list_sessions(current_user: dict = Depends(get_current_user)):
    return ApiResponse(data=session_pool.list_all())

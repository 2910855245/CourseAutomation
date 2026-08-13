from datetime import datetime

from loguru import logger
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import get_current_admin, get_current_user, hash_password
from api.database import db
from api.models import ApiResponse, TopUpRequest

router = APIRouter(prefix="/api/admin", tags=["管理-用户"])


def _require_admin(current_user: dict = Depends(get_current_user)):
    return get_current_admin(current_user)


@router.get("/users", response_model=ApiResponse)
def list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(_require_admin),
):
    users = db.list_users(limit=limit, offset=offset)
    total = db.count_users()
    for u in users:
        u.pop("password_hash", None)
    return ApiResponse(data={"total": total, "items": users})


@router.post("/users/{user_id}/topup", response_model=ApiResponse)
def topup_user(user_id: str, req: TopUpRequest, admin: dict = Depends(_require_admin)):
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    ok = db.update_user_balance(
        user_id, req.amount, "admin_topup",
        note=req.note or f"管理员充值 {req.amount}元",
    )
    if not ok:
        raise HTTPException(status_code=500, detail="充值失败")
    user = db.get_user(user_id)
    return ApiResponse(
        message=f"充值成功，当前余额: {user['balance']}元",
        data={"balance": user["balance"]},
    )


@router.delete("/users/{user_id}", response_model=ApiResponse)
def delete_user(user_id: str, admin: dict = Depends(_require_admin)):
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user["role"] == "admin":
        raise HTTPException(status_code=400, detail="不能删除管理员账户")
    if user["user_id"] == admin.get("user_id"):
        raise HTTPException(status_code=400, detail="不能删除自己的账户")
    ok = db.soft_delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=500, detail="删除失败")
    return ApiResponse(message=f"用户 {user['username']} 已删除")


@router.post("/users/{user_id}/deduct", response_model=ApiResponse)
def deduct_user(user_id: str, req: TopUpRequest, admin: dict = Depends(_require_admin)):
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user["balance"] < req.amount:
        raise HTTPException(status_code=400, detail=f"余额不足，当前: {user['balance']}元")
    ok = db.update_user_balance(
        user_id, -req.amount, "admin_deduct",
        note=req.note or f"管理员扣费 {req.amount}元",
    )
    if not ok:
        raise HTTPException(status_code=500, detail="扣费失败")
    user = db.get_user(user_id)
    return ApiResponse(
        message=f"扣费成功，当前余额: {user['balance']}元",
        data={"balance": user["balance"]},
    )


class SetRoleBody(BaseModel):
    role: str


@router.post("/users/{user_id}/role", response_model=ApiResponse)
def set_user_role(user_id: str, body: SetRoleBody, admin: dict = Depends(_require_admin)):
    if body.role not in ("admin", "customer"):
        raise HTTPException(status_code=400, detail="无效的角色")
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not db.update_user(user_id, role=body.role):
        raise HTTPException(status_code=500, detail="设置角色失败")
    role_names = {"admin": "管理员", "customer": "普通用户"}
    return ApiResponse(message=f"用户 {user['username']} 已设置为 {role_names.get(body.role, body.role)}")

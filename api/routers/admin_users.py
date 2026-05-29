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


@router.get("/users/unified", response_model=ApiResponse)
def list_users_unified(
    role: str = Query(None),
    agent_status: str = Query(None),
    search: str = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(_require_admin),
):
    result = db.list_users_with_agents(
        role=role, agent_status=agent_status, search=search,
        limit=limit, offset=offset,
    )
    return ApiResponse(data=result)


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


# ── 子管理员 ──

@router.get("/sub-admins", response_model=ApiResponse)
def list_sub_admins(admin: dict = Depends(_require_admin)):
    subs = db.list_sub_admins()
    for s in subs:
        s.pop("password_hash", None)
        agent = db.get_agent_by_user_id(s["user_id"])
        s["agent"] = {"agent_id": agent["agent_id"], "tier_level": agent.get("tier_level", 0), "referral_code": agent.get("referral_code", ""), "total_commission": agent.get("total_commission", 0)} if agent else None
    return ApiResponse(data={"items": subs})


class CreateSubAdminBody(BaseModel):
    user_id: str
    username: str
    password: str
    nickname: str = ""


def _check_password_strength(pwd: str):
    import re
    if len(pwd) < 6:
        raise HTTPException(status_code=400, detail="密码长度至少6位")
    if not (re.search(r'[a-zA-Z]', pwd) and re.search(r'\d', pwd)):
        raise HTTPException(status_code=400, detail="密码需同时包含字母和数字")


@router.post("/sub-admins/create", response_model=ApiResponse)
def create_sub_admin(body: CreateSubAdminBody, admin: dict = Depends(_require_admin)):
    _check_password_strength(body.password)
    if db.get_user(body.user_id):
        raise HTTPException(status_code=400, detail="该用户ID已存在")
    if db.get_user_by_username(body.username):
        raise HTTPException(status_code=400, detail="该用户名已存在")
    now = datetime.now().isoformat()
    session = db._get_session()
    try:
        from api.database import User
        user = User(
            user_id=body.user_id,
            username=body.username,
            password_hash=hash_password(body.password),
            nickname=body.nickname or body.username,
            role="sub_admin",
            balance=0.0,
            total_spent=0.0,
            order_count=0,
            created_at=now,
            last_login=now,
        )
        session.add(user)
        session.commit()
        return ApiResponse(message=f"合伙人 {body.username} 创建成功", data={"user_id": body.user_id, "username": body.username, "role": "sub_admin"})
    except Exception as e:
        logger.error("创建合伙人失败: {}", e)
        session.rollback()
        raise HTTPException(status_code=500, detail="创建失败")
    finally:
        session.close()


class SetRoleBody(BaseModel):
    role: str


@router.post("/users/{user_id}/role", response_model=ApiResponse)
def set_user_role(user_id: str, body: SetRoleBody, admin: dict = Depends(_require_admin)):
    if body.role not in ("admin", "sub_admin", "customer"):
        raise HTTPException(status_code=400, detail="无效的角色")
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    ok = db.set_role(user_id, body.role)
    if not ok:
        raise HTTPException(status_code=500, detail="设置角色失败")
    role_names = {"admin": "管理员", "sub_admin": "合伙人", "customer": "普通用户"}
    return ApiResponse(message=f"用户 {user['username']} 已设置为 {role_names.get(body.role, body.role)}")


@router.post("/sub-admins/{user_id}/revoke", response_model=ApiResponse)
def revoke_sub_admin(user_id: str, admin: dict = Depends(_require_admin)):
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user["role"] != "sub_admin":
        raise HTTPException(status_code=400, detail="该用户不是合伙人")
    db.set_role(user_id, "customer")
    return ApiResponse(message=f"已撤销 {user['username']} 的合伙人权限")

import threading
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth import blacklist_token, create_token, get_current_user, hash_password, verify_captcha, verify_password
from api.database import db
from api.models import ApiResponse, RegisterRequest, UserLoginRequest

router = APIRouter(prefix="/api/users", tags=["用户管理"])

# 登录限频：每 IP 60秒内最多 5 次
_login_rate_lock = threading.Lock()
_login_rate_counters: dict = {}
_LOGIN_WINDOW = 60
_LOGIN_MAX = 5


def _check_login_rate(ip: str) -> None:
    now = time.time()
    with _login_rate_lock:
        entries = _login_rate_counters.get(ip, [])
        entries = [t for t in entries if t > now - _LOGIN_WINDOW]
        if len(entries) >= _LOGIN_MAX:
            raise HTTPException(status_code=429, detail="登录尝试过于频繁，请60秒后再试")
        entries.append(now)
        _login_rate_counters[ip] = entries


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., max_length=200)
    new_password: str = Field(..., min_length=6, max_length=200)


class UpdateProfileRequest(BaseModel):
    nickname: Optional[str] = Field(default=None, max_length=50)
    contact: Optional[str] = Field(default=None, max_length=200)


@router.post("/register", response_model=ApiResponse)
def register(req: RegisterRequest):
    verify_captcha(req.captcha_token, req.captcha_answer)
    existing = db.get_user_by_username(req.username)
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = db.create_user(
        username=req.username,
        password_hash=hash_password(req.password),
        nickname=req.nickname,
        contact=req.contact,
    )

    token = create_token(user["user_id"], user["username"], user["role"])

    return ApiResponse(
        message="注册成功！",
        data={
            "user_id": user["user_id"],
            "username": user["username"],
            "role": user["role"],
            "token": token,
        },
    )


@router.post("/login", response_model=ApiResponse)
def login(req: UserLoginRequest, request: Request = None):
    client_ip = request.client.host if request and request.client else ""
    if client_ip:
        _check_login_rate(client_ip)

    verify_captcha(req.captcha_token, req.captcha_answer)

    user = db.get_user_by_login(req.username)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user["password_hash"].startswith("$2b$") and not user["password_hash"].startswith("$2a$"):
        db.update_user(user["user_id"], password_hash=hash_password(req.password))
    db.update_user_login(user["user_id"])
    token = create_token(user["user_id"], user["username"], user["role"])
    return ApiResponse(
        message="登录成功",
        data={
            "user_id": user["user_id"],
            "username": user["username"],
            "nickname": user["nickname"],
            "role": user["role"],
            "balance": user["balance"],
            "token": token,
        },
    )


@router.get("/me", response_model=ApiResponse)
def get_my_info(current_user: dict = Depends(get_current_user)):
    user = db.get_user(current_user["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return ApiResponse(
        data={
            "user_id": user["user_id"],
            "username": user["username"],
            "nickname": user["nickname"],
            "contact": user["contact"],
            "role": user["role"],
            "balance": user["balance"],
            "total_spent": user["total_spent"],
            "order_count": user["order_count"],
            "created_at": user["created_at"],
            "last_login": user["last_login"],
        },
    )


@router.post("/logout", response_model=ApiResponse)
def logout(current_user: dict = Depends(get_current_user)):
    token = current_user.get("_token", "")
    if token:
        blacklist_token(token)
    return ApiResponse(message="已退出登录")


@router.post("/change-password", response_model=ApiResponse)
def change_password(req: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    user = db.get_user(current_user["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not verify_password(req.old_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="原密码不正确")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少6位")
    db.update_user(current_user["user_id"], password_hash=hash_password(req.new_password))
    token = current_user.get("_token", "")
    if token:
        blacklist_token(token)
    return ApiResponse(message="密码修改成功，请重新登录")


@router.put("/profile", response_model=ApiResponse)
def update_profile(req: UpdateProfileRequest, current_user: dict = Depends(get_current_user)):
    updates = {}
    if req.nickname is not None:
        updates["nickname"] = req.nickname
    if req.contact is not None:
        updates["contact"] = req.contact
    if not updates:
        raise HTTPException(status_code=400, detail="没有需要更新的内容")
    db.update_user(current_user["user_id"], **updates)
    return ApiResponse(message="资料已更新")

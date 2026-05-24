from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from loguru import logger
from fastapi import Depends, Header, HTTPException

from config import settings


SECRET_KEY = settings.jwt_secret_key
ALGORITHM = settings.jwt_algorithm
TOKEN_EXPIRE_HOURS = settings.jwt_expire_hours

_token_blacklist_in_memory: dict = {}
_blacklist_lock = threading.Lock()


def _is_blacklisted_in_memory(token_jti: str) -> bool:
    with _blacklist_lock:
        exp = _token_blacklist_in_memory.get(token_jti)
        if exp is None:
            return False
        if datetime.now(timezone.utc).timestamp() > exp:
            del _token_blacklist_in_memory[token_jti]
            return False
        return True


def _add_to_blacklist_in_memory(token_jti: str, expires_in: int):
    with _blacklist_lock:
        exp = datetime.now(timezone.utc).timestamp() + max(expires_in, 60)
        _token_blacklist_in_memory[token_jti] = exp
        if len(_token_blacklist_in_memory) > 1000:
            now = datetime.now(timezone.utc).timestamp()
            expired = [k for k, v in _token_blacklist_in_memory.items() if now > v]
            for k in expired:
                del _token_blacklist_in_memory[k]


def _blacklist_key(token_jti: str) -> str:
    return f"jwt:blacklist:{token_jti}"


def blacklist_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
        token_jti = payload.get("jti")
        if not token_jti:
            return
        exp = payload.get("exp", 0)
        ttl = max(exp - int(datetime.now(timezone.utc).timestamp()), 0)
    except jwt.InvalidTokenError:
        return

    from api.redis_client import redis_client
    if redis_client.available:
        redis_client.set(_blacklist_key(token_jti), "1", ex=max(ttl, 60))
        logger.info(f"Token 已加入 Redis 黑名单 jti={token_jti[:16]}")
    else:
        _add_to_blacklist_in_memory(token_jti, ttl)
        logger.info(f"Token 已加入内存黑名单 jti={token_jti[:16]}")


def is_token_blacklisted(token: str) -> bool:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
        token_jti = payload.get("jti")
        if not token_jti:
            return False
    except jwt.InvalidTokenError:
        return False

    from api.redis_client import redis_client
    if redis_client.available:
        return redis_client.exists(_blacklist_key(token_jti))
    return _is_blacklisted_in_memory(token_jti)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_sha256(password: str, password_hash: str) -> bool:
    salt = hashlib.sha256(SECRET_KEY.encode()).hexdigest()[:16]
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest() == password_hash


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("$2b$") or password_hash.startswith("$2a$"):
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    logger.warning("使用旧版 SHA256 密码验证，建议重新哈希为 bcrypt")
    return _verify_sha256(password, password_hash)


def create_token(user_id: str, username: str, role: str) -> str:
    import uuid
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "jti": uuid.uuid4().hex,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    if is_token_blacklisted(token):
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {
            "user_id": payload["sub"],
            "username": payload["username"],
            "role": payload["role"],
        }
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    token = authorization[len("Bearer "):].strip() if authorization.startswith("Bearer ") else authorization.strip()
    info = verify_token(token)
    if not info:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    return {"_token": token, **info}


GUEST_USER = {
    "user_id": "guest",
    "username": "guest",
    "role": "guest",
}


def get_optional_user(authorization: str = Header(None)):
    if not authorization:
        return GUEST_USER
    token = authorization[len("Bearer "):].strip() if authorization.startswith("Bearer ") else authorization.strip()
    info = verify_token(token)
    if not info:
        return GUEST_USER
    return {"_token": token, **info}


def get_current_admin(user_info: dict = Depends(get_current_user)):
    if user_info is None:
        raise HTTPException(status_code=401, detail="未认证")
    if user_info.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user_info


def get_current_sub_admin(user_info: dict = Depends(get_current_user)):
    if user_info is None:
        raise HTTPException(status_code=401, detail="未认证")
    role = user_info.get("role", "")
    if role not in ("admin", "sub_admin"):
        raise HTTPException(status_code=403, detail="需要合伙人或管理员权限")
    return user_info


def verify_captcha(token: str, answer: str):
    """验证验证码，失败抛 HTTPException。各接口在函数体内调用。"""
    from api.services.captcha import captcha_service
    if not captcha_service.verify(token, answer):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

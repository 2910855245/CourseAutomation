import os
import sys

from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services.session_pool import pool as session_pool


def get_session_or_401(username: str, password: str, website_id: int):
    info = session_pool.get_or_login(username, password, website_id)
    if not info or not info.session:
        raise HTTPException(status_code=401, detail="登录失败，请检查账号密码")
    return info

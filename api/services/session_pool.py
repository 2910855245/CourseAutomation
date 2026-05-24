from __future__ import annotations

import hashlib
import os
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx
from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import (
    get_base_url,
    set_current_account,
    set_current_website,
    update_paths_for_current_account,
    update_url_config,
)
from infrastructure.course_crawler import extract_student_name
from infrastructure.http_session import check_cookie_valid, safe_request
from services.multi_platform_auth import load_platform_cookie, login_single_platform, save_platform_cookie


MAX_POOL_SIZE = 200
SESSION_TTL_HOURS = 6
CLEANUP_INTERVAL_SECONDS = 300


def _on_request(request: httpx.Request):
    logger.debug("HTTP {} {}", request.method, request.url)


def _on_response(response: httpx.Response):
    if response.status_code >= 400:
        logger.warning("HTTP {} {} → {}", response.request.method, response.url, response.status_code)


def _create_optimized_session() -> httpx.Client:
    """创建优化的 Session，支持连接池复用、HTTP/2、自动重试和事件钩子"""
    transport = httpx.HTTPTransport(retries=3, connections=10, max_connections=20)
    session = httpx.Client(
        timeout=httpx.Timeout(30.0),
        verify=False,
        transport=transport,
        http2=True,
        event_hooks={
            "request": [_on_request],
            "response": [_on_response],
        },
    )

    # 设置默认 headers
    from config import get_random_user_agent
    session.headers.update({
        'User-Agent': get_random_user_agent(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    })

    return session


@dataclass
class SessionInfo:
    session: httpx.Client
    username: str
    website_id: int
    password_hash: str = ""
    student_name: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    is_valid: bool = True


class SessionPool:
    def __init__(self, max_size: int = MAX_POOL_SIZE, ttl_hours: float = SESSION_TTL_HOURS):
        self._pool: Dict[str, SessionInfo] = {}
        self._lock = threading.Lock()
        self._max_size = max_size
        self._ttl = timedelta(hours=ttl_hours)
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def _make_key(self, username: str, website_id: int) -> str:
        return f"{username}_{website_id}"

    def _cleanup_loop(self):
        import time
        while True:
            time.sleep(CLEANUP_INTERVAL_SECONDS)
            self._evict_expired()

    def _evict_expired(self):
        now = datetime.now()
        with self._lock:
            expired_keys = [
                key for key, info in self._pool.items()
                if (now - info.last_used) > self._ttl
            ]
            for key in expired_keys:
                del self._pool[key]
            if expired_keys:
                logger.info(f"清理过期会话 count={len(expired_keys)}")

    def _evict_lru(self):
        if len(self._pool) < self._max_size:
            return
        lru_key = min(self._pool, key=lambda k: self._pool[k].last_used)
        del self._pool[lru_key]
        logger.info(f"LRU淘汰会话 key={lru_key}")

    def get(self, username: str, website_id: int) -> Optional[SessionInfo]:
        key = self._make_key(username, website_id)
        with self._lock:
            info = self._pool.get(key)
            if info:
                if (datetime.now() - info.last_used) > self._ttl:
                    del self._pool[key]
                    return None
                info.last_used = datetime.now()
            return info

    def login(self, username: str, password: str, website_id: int) -> SessionInfo:
        wid, ok, session, msg = login_single_platform(website_id, username, password)
        if not ok or not session:
            raise Exception(f"登录失败: {msg}")

        student_name = ""
        try:
            set_current_website(website_id)
            set_current_account(username)
            update_url_config()
            update_paths_for_current_account()
            resp = safe_request(session, f"{get_base_url()}/user/index")
            if resp:
                student_name = extract_student_name(resp.text) or ""
        except Exception as e:
            pass

        save_platform_cookie(username, website_id, session)

        session_info = SessionInfo(
            session=session,
            username=username,
            website_id=website_id,
            password_hash=hashlib.sha256(password.encode()).hexdigest(),
            student_name=student_name,
        )
        key = self._make_key(username, website_id)
        with self._lock:
            self._evict_lru()
            self._pool[key] = session_info
        logger.info(f"会话登录 username={username} website_id={website_id}")
        return session_info

    def restore(self, username: str, website_id: int, password: str = "") -> Optional[SessionInfo]:
        try:
            session = _create_optimized_session()
            if not load_platform_cookie(username, website_id, session):
                return None

            set_current_website(website_id)
            set_current_account(username)
            update_url_config()
            update_paths_for_current_account()

            base_url = get_base_url()
            resp = safe_request(session, f"{base_url}/user/index")
            if not resp:
                return None

            student_name = ""
            try:
                student_name = extract_student_name(resp.text) or ""
            except Exception as e:
                pass

            session_info = SessionInfo(
                session=session,
                username=username,
                website_id=website_id,
                password_hash=hashlib.sha256(password.encode()).hexdigest() if password else "",
                student_name=student_name,
            )
            key = self._make_key(username, website_id)
            with self._lock:
                self._evict_lru()
                self._pool[key] = session_info
            logger.info(f"会话恢复 username={username} website_id={website_id}")
            return session_info
        except Exception as e:
            return None

    def get_or_login(self, username: str, password: str, website_id: int) -> SessionInfo:
        cached = self.get(username, website_id)
        if cached:
            if cached.password_hash == hashlib.sha256(password.encode()).hexdigest():
                return cached
            self.remove(username, website_id)
        return self.login(username, password, website_id)

    def remove(self, username: str, website_id: int) -> bool:
        key = self._make_key(username, website_id)
        with self._lock:
            return self._pool.pop(key, None) is not None

    def list_all(self) -> List[dict]:
        with self._lock:
            return [
                {
                    "username": info.username,
                    "website_id": info.website_id,
                    "student_name": info.student_name,
                    "is_valid": info.is_valid,
                    "last_used": info.last_used.isoformat(),
                }
                for info in self._pool.values()
            ]

    def check_valid(self, username: str, website_id: int) -> bool:
        info = self.get(username, website_id)
        if not info:
            return False
        try:
            set_current_account(username)
            update_url_config()
            valid = check_cookie_valid(info.session)
            info.is_valid = valid
            return valid
        except Exception as e:
            info.is_valid = False
            return False

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "active_sessions": len(self._pool),
                "max_size": self._max_size,
                "ttl_hours": self._ttl.total_seconds() / 3600,
            }


pool = SessionPool()

"""HTTP 客户端 — 精简自 infrastructure/http_session.py"""
import json
import time
from urllib.parse import urlparse

import httpx
from loguru import logger

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_base_url, get_random_user_agent

_SSL_SKIP_DOMAINS = {
    "cdcas.suwankj.com",
    "cdcass.taiskeji.com",
    "cdcas.taiskeji.com",
    "cdcas.duxingkej.com",
    "cdcas.chaoxiankeji.com",
}


def _should_skip_ssl(url: str = None) -> bool:
    if not url:
        return False
    try:
        hostname = urlparse(url).hostname or ""
        return any(hostname == d or hostname.endswith("." + d) for d in _SSL_SKIP_DOMAINS)
    except Exception:
        return False


def create_sync_client(base_url: str = None, **kwargs) -> httpx.Client:
    url = base_url or get_base_url()
    skip = _should_skip_ssl(url)
    verify = kwargs.pop("verify", not skip)
    defaults = {
        "timeout": httpx.Timeout(30.0),
        "verify": verify,
        "follow_redirects": True,
    }
    defaults.update(kwargs)
    return httpx.Client(**defaults)


def get_dynamic_headers(ref_url: str = None) -> dict:
    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    if ref_url:
        headers["Referer"] = ref_url
    return headers


def safe_request(session, url, ref_url=None, retries=3, delay=1):
    for attempt in range(retries):
        try:
            headers = get_dynamic_headers(ref_url)
            resp = session.get(url, headers=headers, timeout=15, follow_redirects=False)
            if resp.status_code == 302:
                location = resp.headers.get("Location", "")
                if "login" in location.lower():
                    return None
                redirect_url = location if location.startswith("http") else url.rstrip("/") + "/" + location.lstrip("/")
                resp = session.get(redirect_url, headers=headers, timeout=15)
            resp.raise_for_status()
            if "SQLSTATE" in resp.text or "数据出现异常" in resp.text:
                time.sleep(delay * (2 ** attempt))
                continue
            return resp
        except Exception:
            time.sleep(delay * (2 ** attempt))
    return None


def check_cookie_valid(session, base_url: str = None) -> bool:
    base = (base_url or get_base_url()).rstrip("/")
    try:
        resp = session.get(f"{base}/user/index", follow_redirects=False, timeout=10)
        if resp.status_code == 302:
            location = resp.headers.get("Location", "")
            return "login" not in location.lower()
        if resp.status_code == 200:
            content = resp.text.lower()
            return "login" not in content[:1000] and ("用户中心" in content or "个人中心" in content)
        return False
    except Exception:
        return False

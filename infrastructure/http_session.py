import json
import os
import time
from urllib.parse import urlparse

import httpx
from loguru import logger

from config import get_account_cookies_path, get_base_url, get_random_user_agent

# 已知的目标平台域名白名单，这些平台的SSL证书可能不被CA信任，
# 仅对这些域名跳过SSL验证（而非全局禁用）
_SSL_SKIP_DOMAINS = {
    "cdcas.suwankj.com",
    "cdcas.taiskeji.com",
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


def _on_request(request: httpx.Request):
    logger.debug("HTTP {} {}", request.method, request.url)


def _on_response(response: httpx.Response):
    if response.status_code >= 400:
        logger.warning("HTTP {} {} → {}", response.request.method, response.url, response.status_code)


def create_async_client(**kwargs) -> httpx.AsyncClient:
    """创建异步 HTTP 客户端，支持 HTTP/2 和事件钩子

    默认启用SSL验证。仅当目标域在白名单中时才跳过验证。
    调用方可显式传入 verify=False 覆盖。
    """
    verify = kwargs.pop("verify", True)
    defaults = {
        "timeout": httpx.Timeout(30.0),
        "verify": verify,
        "http2": True,
        "follow_redirects": True,
        "event_hooks": {
            "request": [_on_request],
            "response": [_on_response],
        },
    }
    defaults.update(kwargs)
    if not defaults["verify"]:
        logger.debug("SSL verification disabled for client")
    return httpx.AsyncClient(**defaults)


def create_platform_client(base_url: str = None, **kwargs) -> httpx.AsyncClient:
    """为已知目标平台创建HTTP客户端，自动跳过SSL验证仅对白名单域名生效"""
    url = base_url or get_base_url()
    skip = _should_skip_ssl(url)
    if skip:
        logger.debug("Target platform domain in SSL skip whitelist: {}", urlparse(url).hostname)
    return create_async_client(verify=not skip, **kwargs)


def create_sync_client(base_url: str = None, **kwargs) -> httpx.Client:
    """创建同步HTTP客户端，仅对白名单域名跳过SSL验证

    统一替代代码库中的 httpx.Client(verify=False, ...) 调用。
    """
    url = base_url or get_base_url()
    skip = _should_skip_ssl(url)
    verify = kwargs.pop("verify", not skip)
    if skip:
        logger.debug("Target platform domain in SSL skip whitelist: {}", urlparse(url).hostname)
    defaults = {
        "timeout": httpx.Timeout(30.0),
        "verify": verify,
        "follow_redirects": True,
    }
    defaults.update(kwargs)
    return httpx.Client(**defaults)


def get_dynamic_headers(ref_url: str = None) -> dict:
    """获取动态的请求头，模拟真实浏览器指纹"""
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


def check_rate_limit(session, url: str, max_retries: int = 3) -> bool:
    """检测是否触发频率限制，自动等待重试

    Returns: True 表示正常，False 表示被限制且重试失败
    """
    # 中文教育平台常见的限流关键词
    _rate_limit_keywords = ('频率', '请求过快', '稍后再试', '访问过于频繁', '操作频繁')

    for attempt in range(max_retries):
        try:
            resp = session.get(url, timeout=10)
        except Exception:
            logger.warning("频率检测请求异常 attempt={}/{}", attempt + 1, max_retries)
            time.sleep(10 * (attempt + 1))
            continue

        if resp.status_code == 429:
            wait = int(resp.headers.get('Retry-After', 30 + attempt * 15))
            logger.info("HTTP 429 限流，等待 {}s", wait)
            time.sleep(wait)
            continue

        text = resp.text or ""
        if any(kw in text for kw in _rate_limit_keywords):
            wait = 20 + attempt * 10
            logger.info("检测到限流关键词，等待 {}s", wait)
            time.sleep(wait)
            continue

        return True

    logger.warning("频率限制重试耗尽 url={}", url)
    return False

def save_cookie(session):
    """保存Cookie到当前账号的文件夹"""
    from config import get_current_account
    username = get_current_account()
    if not username:
        return
    
    cookie_path = get_account_cookies_path(username)
    os.makedirs(os.path.dirname(cookie_path), exist_ok=True)
    
    with open(cookie_path, 'w', encoding='utf-8') as f:
        json.dump(dict(session.cookies), f)

def load_cookie(session) -> bool:
    """从当前账号加载Cookie"""
    from config import get_current_account
    username = get_current_account()
    if not username:
        return False
    
    cookie_path = get_account_cookies_path(username)
    if not os.path.exists(cookie_path):
        return False
    
    try:
        with open(cookie_path, encoding='utf-8') as f:
            cookie_dict = json.load(f)
        session.cookies.update(cookie_dict)
        return True
    except Exception as e:
        return False

def check_cookie_valid(session) -> bool:
    try:
        user_center_url = f"{get_base_url()}/user/index"
        headers = get_dynamic_headers()
        res = session.get(user_center_url, headers=headers, follow_redirects=False, timeout=10)
        # 检查是否被重定向到登录页 (302 重定向到 /user/login)
        if res.status_code == 302:
            location = res.headers.get('Location', '')
            return 'login' not in location.lower()
        # 检查是否直接返回200
        if res.status_code == 200:
            content = res.text.lower()
            return 'login' not in content[:1000] and ('用户中心' in content or '个人中心' in content)
        return False
    except Exception as e:
        return False

def safe_json_parse(resp):
    """处理 UTF-8 BOM 头，安全解析 JSON"""
    content = resp.content
    if content.startswith(b'\xef\xbb\xbf'):
        content = content[3:]
    try:
        return json.loads(content.decode('utf-8'))
    except Exception as e:
        raise e

def safe_request(session, url, ref_url=None, retries=3, delay=1):
    for attempt in range(retries):
        try:
            headers = get_dynamic_headers(ref_url)
            resp = session.get(url, headers=headers, timeout=15, follow_redirects=False)
            
            # 检查是否被重定向到登录页
            if resp.status_code == 302:
                location = resp.headers.get('Location', '')
                if 'login' in location.lower():
                    return None
                # 跟随重定向
                redirect_url = location if location.startswith('http') else url.rstrip('/') + '/' + location.lstrip('/')
                resp = session.get(redirect_url, headers=headers, timeout=15)
            
            resp.raise_for_status()
            if "SQLSTATE" in resp.text or "数据出现异常" in resp.text:
                time.sleep(delay * (2 ** attempt))
                continue
            return resp
        except Exception as e:
            time.sleep(delay * (2 ** attempt))
    return None
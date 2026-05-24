"""登录与心跳模块"""

import random
import threading
from typing import Optional

import httpx
from loguru import logger
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)



def normalize_base_url(url: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


class LoginHelper:
    def __init__(self, base_url: str):
        self.base_url = normalize_base_url(base_url)
        self.session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        })

    def _get_csrf_token(self) -> Optional[str]:
        resp = self.session.get(f"{self.base_url}/user/login", timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        meta = soup.find('meta', attrs={'name': 'csrf-token'})
        if meta:
            return meta.get('content')
        return None

    def _get_captcha(self) -> str:
        resp = self.session.get(f"{self.base_url}/captcha", timeout=15)
        if resp.status_code == 200:
            try:
                from infrastructure.captcha import recognize_captcha
                return recognize_captcha(resp.content)
            except Exception as e:
                return "0000"
        return "0000"

    def login(self, username: str, password: str) -> Optional[httpx.Client]:
        token = self._get_csrf_token()
        captcha = self._get_captcha()
        data = {
            "username": username,
            "password": password,
            "captcha": captcha,
        }
        if token:
            data["_token"] = token
        resp = self.session.post(f"{self.base_url}/user/login", data=data, timeout=15)
        if "login" not in resp.url.lower() and resp.status_code == 200:
            logger.info("登录成功")
            return self.session
        logger.error(f"登录失败: status={resp.status_code}, url={resp.url}")
        return None


class OnlineHeartbeat:
    def __init__(self, session: httpx.Client, online_url: str, login_url: str = ''):
        self.session = session
        self.online_url = online_url
        self.login_url = login_url
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("心跳线程已启动")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("心跳线程已停止")

    def _run(self):
        while not self._stop_event.is_set():
            try:
                resp = self.session.get(self.online_url, timeout=10)
                if resp.status_code == 200:
                    logger.debug("心跳成功")
                else:
                    logger.warning(f"心跳异常: status={resp.status_code}")
            except Exception as e:
                logger.warning(f"心跳失败: {e}")
            self._stop_event.wait(random.uniform(15, 25))

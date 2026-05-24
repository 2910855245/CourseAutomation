import random
import threading
import time
from typing import Optional

import httpx

from config import get_random_user_agent
from infrastructure.dashboard import DashboardDisplay
from infrastructure.http_session import safe_json_parse


class HeartbeatKeeper:
    def __init__(self, base_url: str, cookie_str: str, interval: int = 120, max_errors: int = 10):
        self.base_url = base_url.rstrip('/')
        self.heartbeat_url = f"{self.base_url}/user/online"
        self.base_interval = interval
        self.max_errors = max_errors
        self.error_count = 0
        self.session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
        self.session.headers.update({
            'User-Agent': get_random_user_agent(),
            'X-Requested-With': 'XMLHttpRequest'
        })
        self._set_cookie(cookie_str)
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _set_cookie(self, cookie_str: str):
        for item in cookie_str.split(';'):
            if '=' in item:
                k, v = item.strip().split('=', 1)
                self.session.cookies.set(k, v)

    def send_heartbeat(self) -> bool:
        dash = DashboardDisplay.instance()
        try:
            resp = self.session.post(self.heartbeat_url, timeout=10)
            if resp.status_code == 200:
                data = safe_json_parse(resp)
                dash.debug(f"[heartbeat] {data}")
                if data.get('status') is False and data.get('offline'):
                    dash.info("[heartbeat] 强制下线!")
                    self._try_sync_cookie()
                    # 同步 Cookie 后重试一次心跳
                    try:
                        resp2 = self.session.post(self.heartbeat_url, timeout=10)
                        if resp2.status_code == 200:
                            data2 = safe_json_parse(resp2)
                            if data2.get('status'):
                                self.error_count = 0
                                return True
                    except Exception as e:
                        pass
                    self.error_count += 1
                    return False
                self.error_count = 0
                return True
        except Exception as e:
            dash.debug(f"[heartbeat] 异常: {e}")
        self.error_count += 1
        return False

    def _try_sync_cookie(self):
        try:
            from infrastructure.study_reporter import StudyReporter
            if StudyReporter._shared_cookie_str:
                self._set_cookie(StudyReporter._shared_cookie_str)
                DashboardDisplay.instance().debug("[heartbeat] 已同步StudyReporter刷新后的Cookie")
        except Exception as e:
            pass

    def _get_random_interval(self) -> int:
        """返回随机心跳间隔，90-150秒之间，更像真人"""
        return random.randint(90, 150)

    @logger.catch
    def _run_loop(self):
        while self._running:
            success = self.send_heartbeat()
            if not success and self.error_count >= self.max_errors:
                DashboardDisplay.instance().debug("[heartbeat] 连续失败，停止保活")
                break
            interval = self._get_random_interval()
            for _ in range(interval):
                if not self._running:
                    break
                time.sleep(1)

    def start(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self):
        self._running = False
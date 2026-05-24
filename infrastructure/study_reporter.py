import threading
import time
from typing import Optional

import httpx

from config import HEADERS
from infrastructure.captcha import ImageCaptchaSolver, XCaptchaSolver
from infrastructure.dashboard import DashboardDisplay
from infrastructure.http_session import safe_json_parse
from services.auth_service import login


class StudyReporter:
    _relogin_lock = threading.Lock()
    _first_report_lock = threading.Lock()
    _shared_cookie_str = None
    _shared_username = None
    _shared_password = None

    @classmethod
    def set_shared_credentials(cls, username, password):
        cls._shared_username = username
        cls._shared_password = password

    def __init__(
        self,
        base_url: str,
        node_id: str,
        cookie_str: str,
        video_duration: int = 0,
        report_interval: int = 30,
        viewed_duration: int = 0,
        course_name: str = "",
        video_name: str = "",
        captcha_ak: str = '38570387e765646dff8372d4ec9e3c38',
        captcha_url: str = 'https://shixun.kaikangxinxi.com/api/dunclick.json'
    ):
        self.base_url = base_url.rstrip('/')
        self.node_id = node_id
        self.video_duration = video_duration
        self.report_interval = report_interval
        self.session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
        self.session.headers.update({
            'User-Agent': HEADERS['User-Agent'],
            'X-Requested-With': 'XMLHttpRequest'
        })
        self._set_cookie(cookie_str)
        self.image_captcha = ImageCaptchaSolver(base_url, cookie_str=cookie_str)
        self.captcha_ak = captcha_ak
        self.captcha_url = captcha_url
        self.study_id: int = 0
        self.total_time: int = 0
        self.last_reported_time: int = 0
        self.viewed_duration: int = viewed_duration
        self.course_name: str = course_name
        self.video_name: str = video_name
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._dash = DashboardDisplay.instance()
        self._captcha_retry_count = 0
        self._max_captcha_retries = 7
        self._relogin_retry_count = 0
        self._max_relogin_retries = 3

    def _get_current_report_interval(self) -> int:
        remaining = max(0, self.video_duration - self.viewed_duration - self.total_time)
        if remaining <= 5:
            return 1
        elif remaining <= 15:
            return 3
        elif remaining <= 30:
            return 5
        elif remaining <= 60:
            return 10
        elif remaining <= 180:
            return 15
        elif remaining <= 300:
            return 20
        else:
            return self.report_interval

    def _set_cookie(self, cookie_str: str):
        for item in cookie_str.split(';'):
            if '=' in item:
                k, v = item.strip().split('=', 1)
                self.session.cookies.set(k, v)

    def _relogin(self) -> bool:
        with StudyReporter._relogin_lock:
            if StudyReporter._shared_cookie_str:
                self._set_cookie(StudyReporter._shared_cookie_str)
                self.image_captcha = ImageCaptchaSolver(self.base_url, cookie_str=StudyReporter._shared_cookie_str)
                self._dash.debug("[relogin] 使用已刷新Cookie")
                return True
            try:
                uname = StudyReporter._shared_username
                pwd = StudyReporter._shared_password
                if not uname or not pwd:
                    self._dash.debug("[relogin] 无共享凭据，使用默认账号")
                temp_session = httpx.Client(timeout=httpx.Timeout(30.0))
                login(temp_session, username=uname, password=pwd)
                cookie_str = '; '.join([f"{c.name}={c.value}" for c in temp_session.cookies])
                StudyReporter._shared_cookie_str = cookie_str
                self._set_cookie(cookie_str)
                self.image_captcha = ImageCaptchaSolver(self.base_url, cookie_str=cookie_str)
                self._dash.debug("[relogin] 重新登录成功")
                return True
            except Exception as e:
                self._dash.debug(f"[relogin] 失败: {e}")
                return False

    def _handle_need_code_2(self, verify_token: str) -> bool:
        self._dash.debug("[captcha] 触发点选验证码")
        max_retries = self._max_captcha_retries
        for attempt in range(max_retries + 1):
            solver = XCaptchaSolver(self.captcha_url, self.captcha_ak, verify_token)
            try:
                solver.solve()
                self._dash.debug(f"[captcha] 点选验证通过 (尝试 {attempt + 1}/{max_retries + 1})")
                return True
            except Exception as e:
                self._dash.debug(f"[captcha] 点选验证失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                if attempt < max_retries:
                    time.sleep(1)
                else:
                    self._dash.debug(f"[captcha] 点选验证码重试次数超过限制 ({max_retries}次)，放弃本次验证")
        return False

    def _handle_need_code_1(self) -> str:
        self._dash.debug("[captcha] 触发图形验证码")
        code = self.image_captcha.solve(auto_underscore=True)
        self._dash.debug(f"[captcha] 识别结果: {code}")
        return code

    def _report(self, force: bool = False, captcha_code: str = None) -> bool:
        if self.video_duration > 0 and self.total_time >= self.video_duration:
            return True
        url = f"{self.base_url}/user/node/study"
        data = {
            'nodeId': self.node_id,
            'studyId': self.study_id,
            'studyTime': self.total_time
        }
        if captcha_code:
            if len(captcha_code) > 4:
                captcha_code = captcha_code[:4]
            data['code'] = captcha_code
        if force and self.total_time < 1:
            data['studyTime'] = 1
        self._dash.debug(f"[report] nodeId={self.node_id} studyId={self.study_id} studyTime={data['studyTime']} force={force}")
        try:
            resp = self.session.post(url, data=data, timeout=10)
            resp.raise_for_status()
            result = safe_json_parse(resp)
            self._dash.debug(f"[report] resp: {result}")
        except Exception as e:
            self._dash.debug(f"[report] 请求异常: {e}")
            return False
        if result.get('status'):
            self._captcha_retry_count = 0
            self._relogin_retry_count = 0
            if result.get('state') == 1:
                self._dash.debug("[report] 课程异常，studyId重置")
                self.study_id = 0
            else:
                self.study_id = result.get('studyId', self.study_id)
                self._dash.update(self.node_id, self.total_time, self.study_id)
            self._dash.mark_report_success(self.node_id)
            return True
        else:
            if result.get('offline'):
                msg = result.get('msg', '')
                self._dash.debug(f"[report] 会话过期: {msg}，自动重登...")
                if self._relogin_retry_count >= self._max_relogin_retries:
                    self._dash.debug(f"[report] 重登次数超过限制({self._max_relogin_retries})，放弃")
                    return False
                self._relogin_retry_count += 1
                time.sleep(1)
                if self._relogin():
                    return self._report(force=force, captcha_code=captcha_code)
                return False
            if result.get('msg') and '登录超时' in str(result.get('msg')):
                self._dash.debug("[report] 登录超时，自动重登...")
                if self._relogin_retry_count >= self._max_relogin_retries:
                    self._dash.debug(f"[report] 重登次数超过限制({self._max_relogin_retries})，放弃")
                    return False
                self._relogin_retry_count += 1
                time.sleep(1)
                if self._relogin():
                    return self._report(force=force, captcha_code=captcha_code)
                return False
            need_code = result.get('need_code')
            if need_code == 1:
                if self._captcha_retry_count >= self._max_captcha_retries:
                    self._dash.debug(f"[report] 验证码重试次数超过限制 ({self._max_captcha_retries}次)，放弃本次上报")
                    return False
                self._captcha_retry_count += 1
                self._dash.debug(f"[report] 验证码重试 {self._captcha_retry_count}/{self._max_captcha_retries}")
                time.sleep(0.3 * self._captcha_retry_count)
                code = self._handle_need_code_1()
                return self._report(force=True, captcha_code=code)
            elif need_code == 2:
                if self._captcha_retry_count >= self._max_captcha_retries:
                    self._dash.debug(f"[report] 验证码重试次数超过限制 ({self._max_captcha_retries}次)，放弃本次上报")
                    return False
                self._captcha_retry_count += 1
                self._dash.debug(f"[report] 验证码重试 {self._captcha_retry_count}/{self._max_captcha_retries}")
                time.sleep(0.3 * self._captcha_retry_count)
                verify_token = result.get('verifyToken')
                if not verify_token:
                    self._dash.debug("[report] 缺少 verifyToken")
                    return False
                if not self._handle_need_code_2(verify_token):
                    self._dash.debug("[report] 点选验证失败")
                    return False
                return self._report(force=True)
            else:
                self._dash.debug(f"[report] 未知响应: {result}")
                return False

    def _run_loop(self):
        label = self.video_name or self.course_name or ''
        self._dash.register(self.node_id, label, self.video_duration, self.viewed_duration, self.report_interval)
        self._dash.debug(f"[start] {label} nodeId={self.node_id} dur={self.video_duration}s viewed={self.viewed_duration}s")
        with StudyReporter._first_report_lock:
            self._dash.debug(f"[start] {label} 开始首次上报(串行)...")
            if not self._report(force=True):
                self._dash.mark_failed(self.node_id)
                self._dash.debug(f"[start] {label} 首次上报失败，终止")
                return
            self._dash.debug(f"[start] {label} 首次上报成功 studyId={self.study_id}")
            time.sleep(0.5)
        last_report_time = time.time()
        actual_target = self.video_duration - self.viewed_duration
        while self._running:
            time.sleep(1)
            self.total_time += 1
            if actual_target > 0 and self.total_time >= actual_target:
                self._dash.mark_done(self.node_id)
                ok = self._report(force=False)
                if not ok:
                    self._dash.debug(f"[done] {label} 最后上报失败，手动同步total_time={self.total_time}")
                    self._dash.update(self.node_id, self.total_time, self.study_id)
                    self._dash.mark_report_success(self.node_id)
                self._dash.debug(f"[done] {label} 学习完成")
                break
            current_interval = self._get_current_report_interval()
            if time.time() - last_report_time >= current_interval:
                if not self._report(force=False):
                    self._dash.update(self.node_id, self.total_time, self.study_id)
                    self._dash.mark_failed(self.node_id)
                    self._dash.debug(f"[error] {label} 上报失败，暂停")
                    break
                last_report_time = time.time()

    def start(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self):
        self._running = False

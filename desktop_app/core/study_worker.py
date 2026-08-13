"""视频刷课引擎 — 精简自 study_worker.py，回调式进度"""
import json
import os
import random
import sys
import threading
import time
from collections import defaultdict

from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ocr_instance = None


def _get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        import ddddocr
        _ocr_instance = ddddocr.DdddOcr(show_ad=False)
    return _ocr_instance


class LightStudyReporter:
    """单视频学习上报器"""
    _first_report_lock = threading.Lock()
    _shared_cookie_str = None
    _shared_username = None
    _shared_password = None
    _rate_lock = threading.Lock()
    _next_request_time = 0.0
    _request_spacing = 0.5

    def __init__(self, base_url, node_id, cookie_str, video_duration=0,
                 viewed_duration=0, course_name="", video_name="",
                 report_interval=30, shared_session=None):
        self.base_url = base_url.rstrip("/")
        self.node_id = node_id
        self.video_duration = video_duration
        self.viewed_duration = viewed_duration
        self.report_interval = report_interval
        self.course_name = course_name
        self.video_name = video_name

        if shared_session is not None:
            self.session = shared_session
        else:
            import requests
            self.session = requests.Session()
            self.session.verify = False
            self.session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-Requested-With": "XMLHttpRequest",
            })
        self._set_cookie(cookie_str)

        self.study_id = 0
        self.total_time = 0
        self._start_time = 0
        self._running = False
        self._thread = None
        self._captcha_retry = 0
        self._max_captcha = 7
        self._relogin_retry = 0
        self._max_relogin = 3
        self.completed = False
        self.error_msg = ""

    def _set_cookie(self, cookie_str):
        for item in cookie_str.split(";"):
            if "=" in item:
                k, v = item.strip().split("=", 1)
                self.session.cookies.set(k, v)

    def _get_interval(self):
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
        return self.report_interval

    def _solve_image_captcha(self):
        try:
            resp = self.session.get(
                f"{self.base_url}/service/code",
                params={"r": "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=8))},
                timeout=10,
            )
            resp.raise_for_status()
            ocr = _get_ocr()
            code = ocr.classification(resp.content).strip() + "_"
            return code
        except Exception as e:
            logger.error("[captcha] 图形验证码失败: %s", e)
            return None

    def _report(self, force=False, captcha_code=None):
        if not force and self.video_duration > 0 and self.total_time >= self.video_duration:
            return True
        url = f"{self.base_url}/user/node/study"
        data = {"nodeId": self.node_id, "studyId": self.study_id, "studyTime": self.total_time}
        if captcha_code:
            data["code"] = captcha_code[:4] if len(captcha_code) > 4 else captcha_code
        if force and self.total_time < 1:
            data["studyTime"] = 1
        try:
            resp = self.session.post(url, data=data, timeout=10)
            resp.raise_for_status()
            result = resp.json()
        except Exception as e:
            logger.error("[report] 请求异常: %s", e)
            return False
        if result.get("status"):
            self._captcha_retry = 0
            self._relogin_retry = 0
            if result.get("state") == 1:
                self.study_id = 0
            else:
                self.study_id = result.get("studyId", self.study_id)
            return True
        if result.get("offline") or "登录超时" in str(result.get("msg", "")):
            if self._relogin_retry >= self._max_relogin:
                return False
            self._relogin_retry += 1
            time.sleep(1)
            if self._do_relogin():
                return self._report(force=force, captcha_code=captcha_code)
            return False
        need_code = result.get("need_code")
        if need_code == 1:
            if self._captcha_retry >= self._max_captcha:
                return False
            self._captcha_retry += 1
            time.sleep(0.3 * self._captcha_retry)
            code = self._solve_image_captcha()
            if code:
                return self._report(force=True, captcha_code=code)
            return False
        return False

    def _do_relogin(self):
        uname = LightStudyReporter._shared_username
        pwd = LightStudyReporter._shared_password
        if not uname or not pwd:
            return False
        try:
            import requests as req
            ocr = _get_ocr()
            s = req.Session()
            s.verify = False
            s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            login_url = f"{self.base_url}/user/login"
            captcha_url = f"{self.base_url}/service/code"
            s.get(login_url, timeout=15)
            captcha_resp = s.get(captcha_url, timeout=15)
            code = ocr.classification(captcha_resp.content)
            data = {"username": uname, "password": pwd, "code": code, "redirect": "", "remember": "on"}
            resp = s.post(login_url, data=data, allow_redirects=False, timeout=15)
            if resp.status_code == 302 or '"status":true' in resp.text:
                cookie_str = "; ".join([f"{c.name}={c.value}" for c in s.cookies])
                LightStudyReporter._shared_cookie_str = cookie_str
                self._set_cookie(cookie_str)
                return True
        except Exception as e:
            logger.error("[relogin] 异常: %s", e)
        return False

    @classmethod
    def _wait_rate_limit(cls):
        now = time.time()
        with cls._rate_lock:
            wait = cls._next_request_time - now
        if wait > 0:
            time.sleep(wait)
        with cls._rate_lock:
            cls._next_request_time = max(cls._next_request_time, time.time()) + cls._request_spacing

    _MIN_RATIO = 2.1

    def _wait_for_ratio(self):
        if self.video_duration <= 0:
            return
        min_wall = self.video_duration * self._MIN_RATIO
        elapsed = time.time() - self._start_time
        if elapsed < min_wall:
            wait = min_wall - elapsed
            deadline = time.time() + wait
            while self._running and time.time() < deadline:
                time.sleep(min(5, deadline - time.time()))

    def _run_loop(self):
        logger.info("[start] %s nodeId=%s dur=%ds viewed=%ds",
                     self.video_name, self.node_id, self.video_duration, self.viewed_duration)
        with LightStudyReporter._first_report_lock:
            LightStudyReporter._wait_rate_limit()
            if not self._report(force=True):
                self.error_msg = "首次上报失败"
                return
            time.sleep(0.5)
        self._start_time = time.time()
        last_report = time.time()
        actual_target = self.video_duration - self.viewed_duration
        if actual_target <= 0:
            self.total_time = self.video_duration
            self._wait_for_ratio()
            self.completed = True
            return
        while self._running:
            time.sleep(1)
            self.total_time += 1
            if self.total_time >= actual_target:
                LightStudyReporter._wait_rate_limit()
                if self._report(force=True):
                    self._wait_for_ratio()
                    self.completed = True
                else:
                    self.error_msg = "最终上报失败"
                break
            interval = self._get_interval()
            if time.time() - last_report >= interval:
                LightStudyReporter._wait_rate_limit()
                if not self._report(force=False):
                    self.error_msg = "上报失败"
                    break
                last_report = time.time()

    def start(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self):
        self._running = False

    @property
    def is_alive(self):
        return self._thread is not None and self._thread.is_alive()


class LightHeartbeat:
    def __init__(self, base_url, cookie_str, shared_session=None):
        self.base_url = base_url.rstrip("/")
        self.url = f"{self.base_url}/user/online"
        if shared_session is not None:
            self.session = shared_session
        else:
            import requests
            self.session = requests.Session()
            self.session.verify = False
            self.session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-Requested-With": "XMLHttpRequest",
            })
        self._set_cookie(cookie_str)
        self._running = False
        self._thread = None

    def _set_cookie(self, cookie_str):
        for item in cookie_str.split(";"):
            if "=" in item:
                k, v = item.strip().split("=", 1)
                self.session.cookies.set(k, v)

    def _run_loop(self):
        _consecutive_errors = 0
        while self._running:
            try:
                resp = self.session.post(self.url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") is False and data.get("offline"):
                        _consecutive_errors += 1
                        if LightStudyReporter._shared_cookie_str:
                            self._set_cookie(LightStudyReporter._shared_cookie_str)
                    else:
                        _consecutive_errors = 0
            except Exception:
                _consecutive_errors += 1
            if _consecutive_errors >= 30:
                break
            interval = random.randint(90, 150)
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


class StudyWorker:
    """视频刷课工作线程（回调式，无 PyQt 依赖）"""

    def __init__(self, base_url, cookie_str, username, password, videos,
                 on_progress=None, on_finished=None, on_log=None):
        self.base_url = base_url
        self.cookie_str = cookie_str
        self.username = username
        self.password = password
        self.videos = videos
        self.on_progress = on_progress    # callback(dict)
        self.on_finished = on_finished    # callback(bool, str)
        self.on_log = on_log              # callback(str)
        self._running = False
        self._all_reporters = []
        self._thread = None

    def _log(self, msg):
        if self.on_log:
            self.on_log(msg)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        for r in self._all_reporters:
            r.stop()

    def _run(self):
        LightStudyReporter._shared_username = self.username
        LightStudyReporter._shared_password = self.password
        LightStudyReporter._shared_cookie_str = self.cookie_str

        heartbeat = LightHeartbeat(self.base_url, self.cookie_str)
        heartbeat.start()

        course_groups = defaultdict(list)
        for v in self.videos:
            cid = v.get("course_id", "") or "unknown"
            course_groups[cid].append(v)

        self._log(f"视频分组: {len(course_groups)} 个课程, 共 {len(self.videos)} 个视频")

        progress_lock = threading.Lock()
        all_reporters = []

        def _make_session():
            import requests as _req
            s = _req.Session()
            s.verify = False
            s.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-Requested-With": "XMLHttpRequest",
            })
            return s

        def _run_course_videos(cid, course_videos):
            course_reporters = []
            for v in course_videos:
                r = LightStudyReporter(
                    base_url=self.base_url, node_id=v["node_id"],
                    cookie_str=self.cookie_str, video_duration=v["duration"],
                    viewed_duration=v.get("viewed_duration", 0),
                    course_name=v.get("course_name", ""), video_name=v.get("name", ""),
                    shared_session=_make_session(),
                )
                with progress_lock:
                    all_reporters.append(r)
                    course_reporters.append(r)
                r.start()
                time.sleep(LightStudyReporter._request_spacing)
            while any(r.is_alive for r in course_reporters):
                time.sleep(5)
                done = sum(1 for r in all_reporters if not r.is_alive)
                total_study = sum(min(r.total_time, r.video_duration) for r in all_reporters)
                total_dur = sum(r.video_duration for r in all_reporters)
                pct = int(total_study / total_dur * 100) if total_dur > 0 else 0
                if self.on_progress:
                    self.on_progress({"done": done, "total": len(self.videos), "pct": pct,
                                      "message": f"刷视频中 {done}/{len(self.videos)} ({pct}%)"})

        course_threads = []
        for cid, group_videos in course_groups.items():
            t = threading.Thread(target=_run_course_videos, args=(cid, group_videos), daemon=True)
            t.start()
            course_threads.append(t)
            time.sleep(0.5)

        while any(t.is_alive() for t in course_threads):
            time.sleep(5)
            if not self._running:
                break

        heartbeat.stop()

        completed = sum(1 for r in all_reporters if r.completed)
        self._all_reporters = all_reporters

        if completed == len(self.videos):
            if self.on_finished:
                self.on_finished(True, f"全部完成 {completed}/{len(self.videos)}")
        else:
            if self.on_finished:
                self.on_finished(False, f"部分完成 {completed}/{len(self.videos)}")

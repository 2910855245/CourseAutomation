import sys
import os
import json
import time
import random
import threading
import signal
import traceback
import structlog

logger = structlog.get_logger(__name__)

_ocr_instance = None

def _get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        import ddddocr
        _ocr_instance = ddddocr.DdddOcr(show_ad=False)
    return _ocr_instance


def send_status(status_file, **kwargs):
    data = {}
    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as f:
                data = json.load(f)
        except Exception:
            pass
    data.update(kwargs)
    data["updated_at"] = time.time()
    try:
        with open(status_file, "w") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


class LightStudyReporter:
    _first_report_lock = threading.Lock()
    _shared_cookie_str = None
    _shared_username = None
    _shared_password = None
    _rate_lock = threading.Lock()
    _next_request_time = 0.0
    _request_spacing = 0.5

    def __init__(self, base_url, node_id, cookie_str, video_duration=0,
                 viewed_duration=0, course_name="", video_name="",
                 report_interval=30, captcha_ak=None, captcha_url=None,
                 shared_session=None):
        self.base_url = base_url.rstrip('/')
        self.node_id = node_id
        self.video_duration = video_duration
        self.viewed_duration = viewed_duration
        self.report_interval = report_interval
        self.course_name = course_name
        self.video_name = video_name
        self.captcha_ak = captcha_ak or '38570387e765646dff8372d4ec9e3c38'
        self.captcha_url = captcha_url or 'https://shixun.kaikangxinxi.com/api/dunclick.json'

        if shared_session is not None:
            self.session = shared_session
        else:
            import requests
            self.session = requests.Session()
            self.session.verify = False
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'X-Requested-With': 'XMLHttpRequest'
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
        for item in cookie_str.split(';'):
            if '=' in item:
                k, v = item.strip().split('=', 1)
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

    def _solve_click_captcha(self, verify_token):
        for attempt in range(self._max_captcha + 1):
            try:
                s = self.session
                resp = s.get(self.captcha_url, params={'act': 'token', 'ak': self.captcha_ak}, timeout=10)
                data = resp.json()
                key = data['key']
                img_url = data['img'] + '?k=' + key
                resp2 = s.post(self.captcha_url, data={'act': 'icon', 'key': key}, timeout=10)
                icons = resp2.json()['captcha_icon']
                resp3 = s.get(img_url, timeout=10)
                img_bytes = resp3.content
                try:
                    ocr = _get_ocr()
                    points = ocr.click(img_bytes)
                except ImportError:
                    points = [{'x': random.randint(50, 250), 'y': random.randint(50, 250)} for _ in range(len(icons))]
                ivalue = "||".join([f"{p['x']}-{p['y']}" for p in points])
                resp4 = s.post(self.captcha_url, data={'act': 'check', 'ivalue': ivalue, 'key': key, 'verify': verify_token}, timeout=10)
                result = resp4.json()
                if result.get('status') == 1:
                    logger.info("[captcha] 点选验证通过")
                    return True
                logger.warning("[captcha] 点选验证失败 %d/%d", attempt + 1, self._max_captcha + 1)
            except Exception as e:
                logger.warning("[captcha] 点选验证异常: %s", e)
            if attempt < self._max_captcha:
                time.sleep(1)
        return False

    def _solve_image_captcha(self):
        try:
            resp = self.session.get(f"{self.base_url}/service/code",
                                    params={'r': ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))},
                                    timeout=10)
            resp.raise_for_status()
            img_bytes = resp.content
            try:
                ocr = _get_ocr()
                code = ocr.classification(img_bytes).strip()
            except ImportError:
                code = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=4))
            code += '_'
            logger.info("[captcha] 图形验证码: %s", code)
            return code
        except Exception as e:
            logger.error("[captcha] 图形验证码失败: %s", e)
            return None

    def _report(self, force=False, captcha_code=None):
        if not force and self.video_duration > 0 and self.total_time >= self.video_duration:
            return True
        url = f"{self.base_url}/user/node/study"
        data = {
            'nodeId': self.node_id,
            'studyId': self.study_id,
            'studyTime': self.total_time
        }
        if captcha_code:
            data['code'] = captcha_code[:4] if len(captcha_code) > 4 else captcha_code
        if force and self.total_time < 1:
            data['studyTime'] = 1
        try:
            resp = self.session.post(url, data=data, timeout=10)
            resp.raise_for_status()
            result = resp.json()
        except Exception as e:
            logger.error("[report] 请求异常: %s", e)
            return False
        if result.get('status'):
            self._captcha_retry = 0
            self._relogin_retry = 0
            if result.get('state') == 1:
                self.study_id = 0
            else:
                self.study_id = result.get('studyId', self.study_id)
            return True
        if result.get('offline') or '登录超时' in str(result.get('msg', '')):
            if self._relogin_retry >= self._max_relogin:
                logger.error("[report] 重登次数超限")
                return False
            self._relogin_retry += 1
            time.sleep(1)
            if self._do_relogin():
                return self._report(force=force, captcha_code=captcha_code)
            return False
        need_code = result.get('need_code')
        if need_code == 1:
            if self._captcha_retry >= self._max_captcha:
                logger.error("[report] 图形验证码重试超限")
                return False
            self._captcha_retry += 1
            time.sleep(0.3 * self._captcha_retry)
            code = self._solve_image_captcha()
            if code:
                return self._report(force=True, captcha_code=code)
            return False
        elif need_code == 2:
            if self._captcha_retry >= self._max_captcha:
                logger.error("[report] 点选验证码重试超限")
                return False
            self._captcha_retry += 1
            time.sleep(0.3 * self._captcha_retry)
            vt = result.get('verifyToken')
            if vt and self._solve_click_captcha(vt):
                return self._report(force=True)
            return False
        logger.warning("[report] 未知响应: %s", result)
        return False

    def _do_relogin(self):
        uname = LightStudyReporter._shared_username
        pwd = LightStudyReporter._shared_password
        if not uname or not pwd:
            logger.error("[relogin] 无用户名或密码，跳过")
            return False
        try:
            import requests as req
            ocr = _get_ocr()
            s = req.Session()
            s.verify = False
            s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            login_url = f"{self.base_url}/user/login"
            captcha_url = f"{self.base_url}/service/code"
            # 访问登录页获取session
            s.get(login_url, timeout=15)
            # 获取验证码
            captcha_resp = s.get(captcha_url, timeout=15)
            code = ocr.classification(captcha_resp.content)
            data = {
                'username': uname, 'password': pwd,
                'code': code, 'redirect': '', 'remember': 'on'
            }
            resp = s.post(login_url, data=data, allow_redirects=False, timeout=15)
            if resp.status_code == 302 or '"status":true' in resp.text:
                cookie_str = '; '.join([f"{c.name}={c.value}" for c in s.cookies])
                LightStudyReporter._shared_cookie_str = cookie_str
                self._set_cookie(cookie_str)
                # 保存cookie到文件
                try:
                    from config import get_account_cookies_path, WEBSITES
                    website_id = getattr(self, '_website_id', None)
                    if not website_id:
                        for wid, winfo in WEBSITES.items():
                            if winfo.get("base_url", "").rstrip('/') == self.base_url:
                                website_id = wid
                                break
                    if website_id:
                        cookie_path = get_account_cookies_path(uname, website_id)
                        os.makedirs(os.path.dirname(cookie_path), exist_ok=True)
                        with open(cookie_path, 'w', encoding='utf-8') as f:
                            json.dump({'cookie': cookie_str}, f)
                        logger.info("[relogin] cookie已保存到 %s", cookie_path)
                except Exception as ce:
                    logger.warning("[relogin] 保存cookie失败: %s", ce)
                logger.info("[relogin] 重新登录成功")
                return True
            logger.error("[relogin] 登录失败: status=%d", resp.status_code)
        except Exception as e:
            logger.error("[relogin] 异常: %s", e)
        return False

    @classmethod
    def _wait_rate_limit(cls):
        """全局请求速率控制，确保所有线程的HTTP请求间隔 >= _request_spacing 秒"""
        now = time.time()
        with cls._rate_lock:
            wait = cls._next_request_time - now
        if wait > 0:
            time.sleep(wait)
        with cls._rate_lock:
            cls._next_request_time = max(cls._next_request_time, time.time()) + cls._request_spacing

    _MIN_RATIO = 2.1  # wall_time / video_duration 安全阈值

    def _wait_for_ratio(self):
        """等待 wall_time 达到安全比率后再标记完成，防止平台检测并行刷课"""
        if self.video_duration <= 0:
            return
        min_wall = self.video_duration * self._MIN_RATIO
        elapsed = time.time() - self._start_time
        if elapsed < min_wall:
            wait = min_wall - elapsed
            logger.info("[ratio] %s 等待 %.0fs (ratio %.1f→%.1f)",
                        self.video_name, wait, elapsed / self.video_duration, self._MIN_RATIO)
            # 分段 sleep，支持中途停止
            deadline = time.time() + wait
            while self._running and time.time() < deadline:
                time.sleep(min(5, deadline - time.time()))

    def _run_loop(self):
        logger.info("[start] %s nodeId=%s dur=%ds viewed=%ds",
                    self.video_name, self.node_id, self.video_duration, self.viewed_duration)
        with LightStudyReporter._first_report_lock:
            LightStudyReporter._wait_rate_limit()
            if not self._report(force=True):
                logger.error("[start] %s 首次上报失败", self.video_name)
                self.error_msg = "首次上报失败"
                return
            logger.info("[start] %s 首次上报成功 studyId=%s", self.video_name, self.study_id)
            time.sleep(0.5)
        self._start_time = time.time()
        last_report = time.time()
        actual_target = self.video_duration - self.viewed_duration
        # 视频已看完，等待 ratio 达标后标记完成
        if actual_target <= 0:
            self._wait_for_ratio()
            self.completed = True
            logger.info("[done] %s 已看完 (viewed=%d >= duration=%d)", self.video_name, self.viewed_duration, self.video_duration)
            return
        while self._running:
            time.sleep(1)
            self.total_time += 1
            if self.total_time >= actual_target:
                LightStudyReporter._wait_rate_limit()
                ok = self._report(force=True)
                if ok:
                    self._wait_for_ratio()
                    self.completed = True
                    logger.info("[done] %s 学习完成 total=%ds", self.video_name, self.total_time)
                else:
                    self.error_msg = "最终上报失败"
                    logger.warning("[done] %s 最终上报失败 total=%ds", self.video_name, self.total_time)
                break
            interval = self._get_interval()
            if time.time() - last_report >= interval:
                LightStudyReporter._wait_rate_limit()
                if not self._report(force=False):
                    self.error_msg = "上报失败"
                    logger.error("[error] %s 上报失败", self.video_name, self.total_time)
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
    def __init__(self, base_url, cookie_str, interval=120, shared_session=None):
        self.base_url = base_url.rstrip('/')
        self.url = f"{self.base_url}/user/online"
        self.interval = interval
        if shared_session is not None:
            self.session = shared_session
        else:
            import requests
            self.session = requests.Session()
            self.session.verify = False
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'X-Requested-With': 'XMLHttpRequest'
            })
        self._set_cookie(cookie_str)
        self._running = False
        self._thread = None
        self._errors = 0

    def _set_cookie(self, cookie_str):
        for item in cookie_str.split(';'):
            if '=' in item:
                k, v = item.strip().split('=', 1)
                self.session.cookies.set(k, v)

    def _get_random_interval(self):
        """返回随机心跳间隔，90-150秒"""
        return random.randint(90, 150)

    def _run_loop(self):
        _consecutive_errors = 0
        while self._running:
            try:
                resp = self.session.post(self.url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('status') is False and data.get('offline'):
                        _consecutive_errors += 1
                        if LightStudyReporter._shared_cookie_str:
                            self._set_cookie(LightStudyReporter._shared_cookie_str)
                    else:
                        _consecutive_errors = 0
                        self._errors = 0
            except Exception:
                _consecutive_errors += 1
                self._errors += 1
            # 连续 30 次失败（约 1 小时）才退出心跳，容忍网络波动
            if _consecutive_errors >= 30:
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


def _parse_duration_str(dur_str):
    try:
        parts = str(dur_str).split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return int(dur_str)
    except (ValueError, AttributeError):
        return 0


def _verify_platform_progress(base_url, session, videos):
    from collections import defaultdict

    course_videos = defaultdict(list)
    for v in videos:
        cid = v.get("course_id", "")
        if cid:
            course_videos[cid].append(v)

    # Map node_id -> progress% from platform API
    node_progress = {}

    for cid in course_videos:
        try:
            api_url = f"{base_url}/user/study_record/video"
            page = 1
            while True:
                resp = session.get(api_url, params={"courseId": cid, "page": page},
                                    timeout=15, headers={"X-Requested-With": "XMLHttpRequest"})
                if resp.status_code != 200:
                    break
                data = resp.json()
                records = data.get("list", []) if isinstance(data, dict) else []
                if not records:
                    break
                for item in records:
                    node_id = str(item.get("id", "") or item.get("nodeId", ""))
                    # 优先用 viewedDuration/duration 计算真实进度
                    # progress 字段在某些平台始终返回 "1.00"（固定值），不可靠
                    viewed_dur_str = item.get("viewedDuration", "")
                    total_dur_str = str(item.get("duration", "0"))
                    if viewed_dur_str and total_dur_str and total_dur_str.replace(".", "").isdigit():
                        viewed_secs = _parse_duration_str(viewed_dur_str)
                        total_secs = int(float(total_dur_str))
                        if total_secs > 0:
                            prog = viewed_secs / total_secs * 100
                        else:
                            prog = 0
                    else:
                        prog = float(item.get("progress", 0) or 0)
                    if node_id:
                        node_progress[node_id] = prog
                page_info = data.get("pageInfo", {})
                if page >= page_info.get("pageCount", 1):
                    break
                page += 1
        except Exception as e:
            logger.warning("[verify] 查询课程 %s 进度失败: %s", cid, e)

    total_dur = 0
    total_viewed = 0
    for v in videos:
        dur = v["duration"]
        total_dur += dur
        node_id = str(v.get("node_id", ""))
        prog = node_progress.get(node_id, 0)
        # progress is percentage (0-100), convert to viewed duration
        viewed = int(dur * prog / 100) if prog > 0 else 0
        total_viewed += min(viewed, dur)

    # 检查考试完成情况（日志记录，用于排查"考试已完成但被重复作答"的问题）
    exam_with_score = 0
    exam_total = 0
    for cid in course_videos:
        try:
            api_url = f"{base_url}/user/study_record/exam"
            resp = session.get(api_url, params={"courseId": cid}, timeout=15,
                               headers={"X-Requested-With": "XMLHttpRequest"})
            if resp.status_code == 200:
                data = resp.json()
                records = data.get("list", []) if isinstance(data, dict) else []
                for item in records:
                    exam_total += 1
                    score = item.get("finalScore")
                    if score and str(score).replace(".", "", 1).isdigit() and float(score) > 0:
                        exam_with_score += 1
        except Exception:
            pass
    if exam_total > 0:
        logger.info("[verify] 考试记录: %d/%d 有分数", exam_with_score, exam_total)

    if total_dur <= 0:
        return 100
    return min(100, int(total_viewed / total_dur * 100))


def _load_checkpoint(checkpoint_file: str) -> dict:
    """加载断点续传检查点"""
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed_nodes": [], "progress": {}}


def _save_checkpoint(checkpoint_file: str, checkpoint: dict):
    """保存断点续传检查点"""
    try:
        os.makedirs(os.path.dirname(checkpoint_file), exist_ok=True)
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[checkpoint] 保存失败: {e}")


def run(params_file, status_file, videos_file):
    with open(params_file, "r", encoding="utf-8") as f:
        params = json.load(f)
    with open(videos_file, "r", encoding="utf-8") as f:
        videos = json.load(f)

    base_url = params["base_url"]
    cookie_str = params["cookie_str"]
    username = params.get("username", "")
    password = params.get("password", "")

    LightStudyReporter._shared_username = username
    LightStudyReporter._shared_password = password
    LightStudyReporter._shared_cookie_str = cookie_str

    # 断点续传：加载检查点，过滤已完成的视频
    checkpoint_file = os.path.join(os.path.dirname(status_file), "checkpoint.json")
    checkpoint = _load_checkpoint(checkpoint_file)
    completed_nodes = set(checkpoint.get("completed_nodes", []))

    if completed_nodes:
        original_count = len(videos)
        videos = [v for v in videos if v.get("node_id") not in completed_nodes]
        logger.info(f"[checkpoint] 已跳过 {original_count - len(videos)} 个已完成视频，剩余 {len(videos)} 个")

    if not videos:
        logger.info("[checkpoint] 所有视频已完成，无需处理")
        send_status(status_file, phase="done", done=True, success=True, video_pct=100,
                    message="所有视频已完成（断点续传）")
        return

    send_status(status_file, phase="video", video_done=0, video_total=len(videos),
                message=f"开始刷视频 (共{len(videos)}个)")

    import requests as _req

    def _make_session():
        s = _req.Session()
        s.verify = False
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-Requested-With': 'XMLHttpRequest'
        })
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api', 'services'))
            from proxy_config import get_proxy_config
            cfg = get_proxy_config()
            if cfg["enabled"]:
                s.proxies.update(cfg["proxies"])
        except Exception:
            pass
        return s

    heartbeat = LightHeartbeat(base_url, cookie_str, shared_session=_make_session())
    heartbeat.start()

    # 启动时立即检查cookie有效性
    if username and password:
        try:
            _test_s = _make_session()
            for pair in cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    _test_s.cookies.set(k.strip(), v.strip())
            _test_r = _test_s.get(f"{base_url}/user/index", timeout=10, allow_redirects=False)
            if _test_r.status_code in (302, 401, 403):
                logger.warning("[cookie] 启动时cookie已过期，尝试重新登录")
                _tmp = LightStudyReporter(base_url, "", cookie_str, 0, 0, "", "", _make_session())
                if _tmp._do_relogin():
                    cookie_str = LightStudyReporter._shared_cookie_str
                    heartbeat._set_cookie(cookie_str)
                    logger.info("[cookie] 启动时重新登录成功")
                else:
                    logger.error("[cookie] 启动时重新登录失败")
        except Exception as e:
            logger.debug("[cookie] 启动检查异常: %s", e)

    # 按课程分组：课程内串行，课程间并发
    from collections import defaultdict
    course_groups = defaultdict(list)
    for v in videos:
        cid = v.get("course_id", "") or "unknown"
        course_groups[cid].append(v)

    logger.info("视频分组: %d 个课程, 共 %d 个视频", len(course_groups), len(videos))

    # 共享进度追踪
    progress_lock = threading.Lock()
    all_reporters = []  # 所有 reporter 实例，用于最终统计

    def _run_course_videos(cid, course_videos):
        """单个课程内的视频：每隔0.5秒启动一个，HTTP请求由全局限速器串行化"""
        logger.info("[course-%s] 开始处理 %d 个视频", cid, len(course_videos))
        course_reporters = []
        for i, v in enumerate(course_videos):
            r = LightStudyReporter(
                base_url=base_url,
                node_id=v["node_id"],
                cookie_str=cookie_str,
                video_duration=v["duration"],
                viewed_duration=v.get("viewed_duration", 0),
                course_name=v.get("course_name", ""),
                video_name=v.get("name", ""),
                shared_session=_make_session(),
            )
            with progress_lock:
                all_reporters.append(r)
                course_reporters.append(r)
            r.start()
            time.sleep(LightStudyReporter._request_spacing)
        logger.info("[course-%s] 已启动全部 %d 个视频", cid, len(course_videos))
        # 等待本课程所有视频完成
        while any(r.is_alive for r in course_reporters):
            time.sleep(5)
        done = sum(1 for r in course_reporters if r.completed)
        logger.info("[course-%s] 课程处理完毕: 成功=%d/%d", cid, done, len(course_videos))

    # 每个课程启动一个线程，课程内串行
    course_threads = []
    for cid, group_videos in course_groups.items():
        t = threading.Thread(
            target=_run_course_videos,
            args=(cid, group_videos),
            daemon=True,
            name=f"course-{cid}",
        )
        t.start()
        course_threads.append(t)
        time.sleep(0.5)  # 课程间启动间隔

    logger.info("已启动 %d 个课程线程（共 %d 个视频）", len(course_threads), len(videos))

    # Cookie续期：定期检查cookie有效性，过期则重新登录
    last_cookie_check = time.time()
    _cookie_refresh_count = 0

    def _refresh_cookie_if_expired():
        nonlocal cookie_str, _cookie_refresh_count
        if not username or not password:
            return
        try:
            test_session = _make_session()
            # 解析cookie字符串
            for pair in cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    test_session.cookies.set(k.strip(), v.strip())
            resp = test_session.get(f"{base_url}/user/index", timeout=10, allow_redirects=False)
            if resp.status_code in (302, 401, 403):
                logger.warning("[cookie] cookie已过期，尝试重新登录 (第%d次)", _cookie_refresh_count + 1)
                # 创建临时LightStudyReporter实例调用_do_relogin
                tmp = LightStudyReporter(base_url, "", cookie_str, 0, 0, "", "", _make_session())
                if tmp._do_relogin():
                    cookie_str = LightStudyReporter._shared_cookie_str
                    _cookie_refresh_count += 1
                    # 更新所有正在运行的reporter和heartbeat的cookie
                    new_cookie = LightStudyReporter._shared_cookie_str
                    with progress_lock:
                        for r in all_reporters:
                            if r.is_alive:
                                r._set_cookie(new_cookie)
                    heartbeat._set_cookie(new_cookie)
                    logger.info("[cookie] 重新登录成功，已更新cookie（含所有活跃线程）")
                else:
                    logger.error("[cookie] 重新登录失败")
        except Exception as e:
            logger.debug("[cookie] 检查异常: %s", e)

    # 进度监控：等待所有课程线程结束
    last_checkpoint_save = time.time()
    while True:
        time.sleep(5)
        # 每30分钟检查一次cookie有效性
        if time.time() - last_cookie_check > 1800:
            last_cookie_check = time.time()
            _refresh_cookie_if_expired()
        alive_count = sum(1 for t in course_threads if t.is_alive())
        with progress_lock:
            done = sum(1 for r in all_reporters if not r.is_alive)
            total_study = sum(min(r.total_time, r.video_duration) for r in all_reporters)
            total_dur = sum(r.video_duration for r in all_reporters)
            # 收集已完成的视频节点ID
            newly_completed = [r.node_id for r in all_reporters if r.completed and r.node_id not in completed_nodes]

        # 每60秒保存一次检查点
        if time.time() - last_checkpoint_save > 60 or newly_completed:
            if newly_completed:
                completed_nodes.update(newly_completed)
            checkpoint["completed_nodes"] = list(completed_nodes)
            checkpoint["progress"] = {
                "done": done,
                "total": len(videos),
                "pct": int(total_study / total_dur * 100) if total_dur > 0 else 0
            }
            _save_checkpoint(checkpoint_file, checkpoint)
            last_checkpoint_save = time.time()

        pct = int(total_study / total_dur * 100) if total_dur > 0 else 0
        send_status(status_file, phase="video", video_done=done, video_total=len(videos),
                    video_pct=pct, total_study_time=total_study, total_duration=total_dur,
                    message=f"刷视频中 {done}/{len(videos)} ({pct}%) 课程线程活跃:{alive_count}")

        if alive_count == 0:
            break

    completed_count = sum(1 for r in all_reporters if r.completed)
    error_count = len(all_reporters) - completed_count
    logger.info("上报线程结束: 成功=%d 异常=%d 总计=%d", completed_count, error_count, len(all_reporters))

    if error_count > 0:
        for r in all_reporters:
            if not r.completed:
                logger.warning("[异常] %s: %s", r.video_name, r.error_msg or "未完成")

    heartbeat.stop()

    _verify_session = _make_session()
    for item in cookie_str.split(';'):
        if '=' in item:
            k, v = item.strip().split('=', 1)
            _verify_session.cookies.set(k, v)
    actual_pct = _verify_platform_progress(base_url, _verify_session, videos)
    logger.info("平台实际进度: %d%%", actual_pct)

    if actual_pct >= 100:
        send_status(status_file, phase="done", done=True, success=True, video_pct=100,
                    message="任务完成")
        logger.info("所有视频学习完成")
    elif completed_count == len(all_reporters) and actual_pct < 95:
        send_status(status_file, phase="done", done=True, success=False, video_pct=actual_pct,
                    message=f"上报完成但平台进度仅{actual_pct}%，可能被平台限制")
        logger.warning("上报完成但平台进度仅 %d%%", actual_pct)
    else:
        send_status(status_file, phase="done", done=True, success=False, video_pct=actual_pct,
                    message=f"部分视频未完成 {completed_count}/{len(all_reporters)} 平台进度{actual_pct}%")
        logger.warning("部分视频未完成 平台进度 %d%%", actual_pct)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("用法: python study_worker.py <params_file> <status_file> <videos_file>")
        sys.exit(1)

    def handle_signal(signum, frame):
        logger.info("收到信号 %d，退出", signum)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        run(sys.argv[1], sys.argv[2], sys.argv[3])
    except Exception as e:
        logger.error("异常: %s\n%s", e, traceback.format_exc())
        send_status(sys.argv[2], phase="error", message=f"异常: {e}", done=True, success=False)
        sys.exit(1)

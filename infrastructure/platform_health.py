"""平台健康监控 — 定期检查目标平台各功能是否正常"""
import json
import os
import sys
import threading
import time
from datetime import datetime
from typing import Dict, Optional

from loguru import logger

from config import WEBSITES, get_base_url, set_current_website, update_url_config


# 健康检查结果存储路径
HEALTH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "health")
HEALTH_FILE = os.path.join(HEALTH_DIR, "platform_health.json")
HEALTH_ALL_FILE = os.path.join(HEALTH_DIR, "platform_health_all.json")

# 检查间隔（秒）
CHECK_INTERVAL = 3600  # 1小时


def _ensure_dir():
    os.makedirs(HEALTH_DIR, exist_ok=True)


def _load_json(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            pass
    return {}


def _save_json(path: str, data: dict):
    _ensure_dir()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class PlatformHealthChecker:
    """平台健康检查器"""

    def __init__(self, session=None, website_id: int = None):
        self.session = session
        self.website_id = website_id
        self.results: Dict = {}
        self._last_check = 0

    def run_full_check(self, session=None, website_id: int = None, username: str = "") -> Dict:
        """执行完整健康检查"""
        session = session or self.session
        website_id = website_id or self.website_id
        if not session or website_id is None:
            return {"error": "缺少 session 或 website_id"}

        # 设置当前平台上下文，确保 USER_CENTER_URL 等全局变量正确
        try:
            set_current_website(website_id)
            update_url_config()
        except Exception as e:
            pass

        # 优先用扫描结果的平台名，fallback 到 WEBSITES 配置
        try:
            from api.services.domain_monitor import get_active_platforms
            active = get_active_platforms()
            platform_name = active.get(website_id, {}).get("name", "") or WEBSITES.get(website_id, {}).get("name", "未知")
        except Exception as e:
            platform_name = WEBSITES.get(website_id, {}).get("name", "未知")

        results = {
            "website_id": website_id,
            "website_name": platform_name,
            "username": username,
            "check_time": datetime.now().isoformat(),
            "checks": {},
            "overall": "healthy",
        }

        # 1. 登录态检查
        results["checks"]["auth"] = self._check_auth(session)

        # 2. 课程列表检查
        results["checks"]["courses"] = self._check_courses(session)

        # 3. 学习上报接口检查
        results["checks"]["study_report"] = self._check_study_report(session)

        # 4. 考试接口检查（复用课程列表结果）
        cached_courses = results["checks"]["courses"].get("_courses")
        results["checks"]["exam_api"] = self._check_exam_api(session, cached_courses)

        # 判断整体状态
        failed = [k for k, v in results["checks"].items() if v.get("status") == "failed"]
        warn = [k for k, v in results["checks"].items() if v.get("status") == "warning"]
        if failed:
            results["overall"] = "critical"
            results["failed_checks"] = failed
        elif warn:
            results["overall"] = "degraded"
            results["warning_checks"] = warn

        self.results = results
        self._last_check = time.time()

        # 保存单平台结果
        per_platform_file = os.path.join(HEALTH_DIR, f"platform_health_{website_id}.json")
        _save_json(per_platform_file, results)

        # 更新聚合文件（所有平台）
        all_results = _load_json(HEALTH_ALL_FILE)
        if "platforms" not in all_results:
            all_results["platforms"] = {}
        all_results["platforms"][str(website_id)] = results
        all_results["last_check"] = datetime.now().isoformat()
        _save_json(HEALTH_ALL_FILE, all_results)

        # 兼容旧格式
        _save_json(HEALTH_FILE, results)
        return results

    def _check_auth(self, session) -> Dict:
        """检查登录态是否有效"""
        try:
            from config import USER_CENTER_URL
            from infrastructure.http_session import safe_request
            resp = safe_request(session, USER_CENTER_URL)
            if not resp:
                return {"status": "failed", "message": "请求用户中心失败"}
            if "登录" in resp.text and "password" in resp.text.lower():
                return {"status": "failed", "message": "Cookie已过期，需要重新登录"}
            return {"status": "healthy", "message": "登录态正常"}
        except Exception as e:
            return {"status": "failed", "message": f"检查异常: {e}"}

    def _check_courses(self, session) -> Dict:
        """检查课程列表能否正常获取"""
        try:
            from infrastructure.course_crawler import get_courses
            courses = get_courses(session)
            if not courses:
                return {"status": "warning", "message": "获取课程列表为空（可能该平台暂无课程）"}
            return {
                "status": "healthy",
                "message": f"获取到 {len(courses)} 门课程",
                "course_count": len(courses),
                "_courses": courses,
            }
        except Exception as e:
            return {"status": "failed", "message": f"课程列表获取异常: {e}"}

    def _check_study_report(self, session) -> Dict:
        """检查学习上报接口是否可用"""
        try:
            base_url = get_base_url()
            resp = session.get(f"{base_url}/user/node/study", params={
                "nodeId": "test_health_check",
                "studyTime": "0",
                "duration": "0",
            }, timeout=10)
            # 只要不是500就算接口可用
            if resp.status_code >= 500:
                return {"status": "failed", "message": f"学习上报接口返回 {resp.status_code}"}
            return {
                "status": "healthy",
                "message": f"学习上报接口响应 {resp.status_code}",
                "status_code": resp.status_code,
            }
        except Exception as e:
            return {"status": "failed", "message": f"学习上报接口异常: {e}"}

    def _check_exam_api(self, session, courses=None) -> Dict:
        """检查考试/作业记录接口是否可用"""
        try:
            base_url = get_base_url()
            if courses is None:
                from infrastructure.course_crawler import get_courses
                courses = get_courses(session)
            if not courses:
                return {"status": "warning", "message": "无课程，跳过考试接口检查"}

            cid = courses[0].get("course_id")
            if not cid:
                return {"status": "warning", "message": "无课程ID，跳过考试接口检查"}

            headers = {"X-Requested-With": "XMLHttpRequest"}
            # 测试作业记录接口
            resp = session.get(f"{base_url}/user/study_record/work",
                               params={"courseId": cid, "page": 1},
                               headers=headers, timeout=10)
            if resp.status_code >= 500:
                return {"status": "failed", "message": f"考试接口返回 {resp.status_code}"}

            data = resp.json()
            if not data.get("status"):
                return {"status": "failed", "message": "考试接口返回异常"}

            return {
                "status": "healthy",
                "message": "考试接口响应正常",
                "status_code": resp.status_code,
            }
        except Exception as e:
            return {"status": "failed", "message": f"考试接口异常: {e}"}

    def get_last_result(self) -> Optional[Dict]:
        """获取上次检查结果"""
        if self.results:
            return self.results
        return _load_json(HEALTH_FILE) or None

    def needs_check(self) -> bool:
        """是否需要执行检查"""
        return time.time() - self._last_check > CHECK_INTERVAL


class HealthMonitorDaemon:
    """后台健康监控守护线程"""

    def __init__(self, session_pool=None):
        self._session_pool = session_pool
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("健康监控守护线程已启动")

    def stop(self):
        self._running = False
        logger.info("健康监控守护线程已停止")

    @logger.catch
    def _loop(self):
        while self._running:
            self._run_checks()
            # 从数据库读取间隔，支持运行时修改
            try:
                from api.database import db
                val = db.config_get("health_check_interval")
                interval = int(val) if val else CHECK_INTERVAL
            except Exception:
                interval = CHECK_INTERVAL
            time.sleep(interval)

    def _run_checks(self):
        if not self._session_pool:
            return

        # 优先使用配置的检测账号
        def _get_accounts_list():
            try:
                import json
                from api.database import db
                raw = db.config_get("health_check_accounts")
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
            return []

        accounts = _get_accounts_list()
        if not accounts:
            logger.warning("未配置健康检测账号，跳过自动检查")
            return

        def _get_account_for_platform(wid):
            target_type = "chaoxing" if wid == 4 else "school"
            for a in accounts:
                if a.get("website_type", "school") == target_type and a.get("active"):
                    return a
            return None

        checked_websites = set()

        from config import WEBSITES
        for wid in WEBSITES:
            if wid in checked_websites:
                continue
            checked_websites.add(wid)
            acct = _get_account_for_platform(wid)
            if not acct:
                continue
            target_username = acct.get("username", "")
            target_password = acct.get("password", "")
            session_info = self._session_pool.get(target_username, wid)
            if not session_info:
                try:
                    set_current_website(wid)
                    session_info = self._session_pool.restore(target_username, wid)
                except Exception as e:
                    pass
            if not session_info:
                try:
                    session_info = self._session_pool.login(target_username, target_password, wid)
                except Exception as e:
                    pass
            if session_info:
                try:
                    checker = PlatformHealthChecker()
                    result = checker.run_full_check(session_info.session, wid, username=target_username)
                    if result.get("overall") != "healthy":
                        logger.warning("平台健康检查异常",
                                       website=wid,
                                       overall=result.get("overall"),
                                       failed=result.get("failed_checks", []))
                except Exception as e:
                    logger.error(f"健康检查失败 username={target_username} error={str(e)}")


def get_health_summary() -> Dict:
    """获取健康检查摘要（供 API 调用），返回所有平台的聚合结果"""
    all_data = _load_json(HEALTH_ALL_FILE)
    platforms = all_data.get("platforms", {})

    if not platforms:
        # 兼容旧的单平台格式
        data = _load_json(HEALTH_FILE)
        if not data:
            return {"status": "unknown", "message": "尚未执行健康检查", "platforms": {}}
        wid = str(data.get("website_id", ""))
        platforms = {wid: data} if wid else {}

    # 聚合所有平台的 checks
    aggregated_checks = {}
    check_keys = ["auth", "courses", "study_report", "exam_api"]

    for key in check_keys:
        statuses = []
        messages = []
        for wid, pdata in platforms.items():
            check = pdata.get("checks", {}).get(key)
            if check:
                statuses.append(check.get("status", "unknown"))
                pname = pdata.get("website_name", f"平台{wid}")
                messages.append(f"{pname}: {check.get('message', '')}")

        if not statuses:
            aggregated_checks[key] = {"status": "unknown", "message": "未检测"}
        elif all(s == "healthy" for s in statuses):
            aggregated_checks[key] = {"status": "healthy", "message": "; ".join(messages)}
        elif any(s == "failed" for s in statuses):
            aggregated_checks[key] = {"status": "failed", "message": "; ".join(messages)}
        else:
            aggregated_checks[key] = {"status": "warning", "message": "; ".join(messages)}

    # 整体状态
    all_statuses = [p.get("overall", "unknown") for p in platforms.values()]
    if all(s == "healthy" for s in all_statuses):
        overall = "healthy"
    elif any(s == "critical" for s in all_statuses):
        overall = "critical"
    elif any(s == "degraded" for s in all_statuses):
        overall = "degraded"
    else:
        overall = "unknown"

    return {
        "status": overall,
        "check_time": all_data.get("last_check"),
        "platform_count": len(platforms),
        "platforms": {
            wid: {
                "name": p.get("website_name", ""),
                "overall": p.get("overall", "unknown"),
                "check_time": p.get("check_time"),
            }
            for wid, p in platforms.items()
        },
        "platform_checks": {
            wid: {
                "name": p.get("website_name", ""),
                "username": p.get("username", ""),
                "checks": p.get("checks", {}),
                "error": p.get("error", ""),
            }
            for wid, p in platforms.items()
        },
        "checks": aggregated_checks,
    }

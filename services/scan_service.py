import json
import os
import threading
import time
from typing import Dict, Optional

from loguru import logger

from config import (
    DATA_DIR,
    WEBSITES,
    set_current_account,
    set_current_website,
    update_paths_for_current_account,
    update_url_config,
)
from infrastructure.course_crawler import get_course_nodes_from_api, get_courses
from infrastructure.data_cleaner import clean_course_data
from infrastructure.task_filter import get_all_actionable


_config_lock = threading.Lock()

# 已删除作业/考试的页面特征
_DELETED_MARKERS = ["已不存在", "已被删除", "可能已被删除", "信息已不存在"]


def _verify_exam_exists(session, base_url: str, work_id, node_id, course_id) -> bool:
    """尝试访问考试/作业页面，确认是否真的存在。

    返回 True 表示存在（或无法确认删除），False 表示明确已删除。
    只有 API 明确返回"已删除"消息时才返回 False。

    注意：不调用 start_work，避免消耗有限的答题机会。
    """
    from infrastructure.http_session import safe_request
    from infrastructure.exam_login import normalize_base_url
    base = normalize_base_url(base_url)

    wid = int(work_id) if str(work_id).isdigit() else work_id
    cid = int(course_id) if str(course_id).isdigit() else 0
    nid = int(node_id) if str(node_id).isdigit() else 0

    try:
        # 直接 GET 页面检测，不调用 start_work（避免消耗答题机会）
        exam_page_url = f"{base}/user/work?workId={wid}&courseId={cid}&nodeId={nid}"
        resp = safe_request(session, exam_page_url)
        if not resp:
            return True  # 请求失败时保守认为存在
        html = resp.content.decode('utf-8', errors='replace')
        # 只有明确的删除标记才判定删除
        for marker in _DELETED_MARKERS:
            if marker in html:
                return False
        # 检查是否有题目
        if 'topic-item' in html or 'courseexamcon-main' in html:
            return True

        # 无题目，保守认为存在（避免误删）
        return True
    except Exception as e:
        logger.debug("验证考试存在性异常 work_id={}: {}", work_id, e)
        return True  # 异常时不标记删除，避免误判

SCAN_CACHE_TTL = 1800  # 缓存有效期 30 分钟


def _get_scan_cache_path(username: str, website_id: int) -> str:
    website_name = WEBSITES.get(website_id, {}).get("name", f"平台{website_id}")
    safe_ws = website_name.replace(" ", "_")
    cache_dir = os.path.join(DATA_DIR, "accounts", username, "scan_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{safe_ws}.json")


def save_scan_cache(username: str, website_id: int, data: dict):
    """缓存扫描结果"""
    path = _get_scan_cache_path(username, website_id)
    cache = {"saved_at": time.time(), "data": data}
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception as e:
        logger.warning("写入扫描缓存失败: {}", e)


def load_scan_cache(username: str, website_id: int) -> Optional[dict]:
    """加载扫描缓存，超过 TTL 返回 None"""
    path = _get_scan_cache_path(username, website_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            cache = json.load(f)
        if time.time() - cache.get("saved_at", 0) > SCAN_CACHE_TTL:
            return None
        return cache.get("data")
    except Exception as e:
        return None


def _set_platform_context(username: str, website_id: int):
    set_current_website(website_id)
    set_current_account(username)
    update_url_config()
    update_paths_for_current_account()


def scan_course(session, course_id: str, course_name: str,
                username: str = "", website_id: int = 0) -> dict:
    """扫描单门课程：爬取 → 清洗 → 筛选

    返回: {videos, exams, works, nodes, tasks, missed, pending}
    """
    from config import get_base_url
    raw = get_course_nodes_from_api(session, course_id, course_name)
    cleaned = clean_course_data(raw)

    # 验证考试/作业是否真的存在（检测已删除）
    # 包括 actionable 和未交的（避免已删除的被计入 pending）
    base_url = get_base_url()
    for exam in cleaned.get("exams", []):
        need_verify = exam.get("is_actionable") or "未交" in exam.get("submit_status", "")
        if need_verify:
            if not _verify_exam_exists(session, base_url, exam["work_id"], exam["node_id"], course_id):
                exam["is_deleted"] = True
                exam["is_actionable"] = False
                exam["is_done"] = True
                exam["submit_status"] = "已删除"
                logger.info("考试已删除: {} (work_id={})", exam.get("name"), exam["work_id"])

    for work in cleaned.get("works", []):
        need_verify = work.get("is_actionable") or "未交" in work.get("submit_status", "")
        if need_verify:
            if not _verify_exam_exists(session, base_url, work["work_id"], work["node_id"], course_id):
                work["is_deleted"] = True
                work["is_actionable"] = False
                work["is_done"] = True
                work["submit_status"] = "已删除"
                logger.info("作业已删除: {} (work_id={})", work.get("name"), work["work_id"])

    actionable = get_all_actionable(cleaned)
    result = {**cleaned, **actionable}

    # 缓存详细节点数据
    if username and website_id:
        _save_course_cache(username, website_id, course_id, course_name, result)

    return result


def _save_course_cache(username: str, website_id: int, course_id: str,
                       course_name: str, data: dict):
    """缓存单门课程的详细扫描结果"""
    website_name = WEBSITES.get(website_id, {}).get("name", f"平台{website_id}")
    safe_ws = website_name.replace(" ", "_")
    cache_dir = os.path.join(DATA_DIR, "accounts", username, "courses", safe_ws)
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{course_id}.json")
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "course_id": course_id,
                "course_name": course_name,
                "cached_at": time.time(),
                "videos": data.get("videos", []),
                "exams": data.get("exams", []),
                "works": data.get("works", []),
                "tasks": data.get("tasks", []),
                "actionable_exams": data.get("actionable_exams", []),
            }, f, ensure_ascii=False)
    except Exception as e:
        logger.warning("写入课程缓存失败: {}", e)


def load_course_cache(username: str, website_id: int, course_id: str) -> Optional[dict]:
    """加载单门课程缓存，超过 TTL 返回 None"""
    website_name = WEBSITES.get(website_id, {}).get("name", f"平台{website_id}")
    safe_ws = website_name.replace(" ", "_")
    cache_file = os.path.join(DATA_DIR, "accounts", username, "courses", safe_ws, f"{course_id}.json")
    if not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file, encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("cached_at", 0) > SCAN_CACHE_TTL:
            return None
        return data
    except Exception as e:
        return None


def scan_platform(username: str, password: str, website_id: int,
                  include_records: bool = True,
                  platform_name: str = None) -> dict:
    """扫描单个平台全部课程

    返回: {website_id, name, status, student_name, courses, tasks}
    """
    from api.services.session_pool import pool as session_pool

    if not platform_name:
        platform_name = WEBSITES.get(website_id, {}).get("name", f"平台{website_id}")

    # 学习通使用独立的登录流程
    website_info = WEBSITES.get(website_id, {})
    if website_info.get("type") == "chaoxing":
        return scan_chaoxing(username, password, account_name=username)

    # 1. 登录
    try:
        info = session_pool.get_or_login(username, password, website_id)
        session = info.session
    except Exception as e:
        logger.error("扫描平台登录失败 - website_id={} user={}: {}", website_id, username, e)
        detail = str(e)
        if "验证码" in detail:
            error_msg = "验证码识别失败，请重试"
        elif "密码" in detail or "password" in detail.lower():
            error_msg = "密码错误"
        elif "不存在" in detail or "not found" in detail.lower():
            error_msg = "账号不存在"
        elif "超时" in detail or "timeout" in detail.lower():
            error_msg = "连接超时，请重试"
        else:
            error_msg = "登录失败，请检查账号密码"
        return {
            "website_id": website_id,
            "name": platform_name,
            "status": "login_failed",
            "error": error_msg,
            "courses": [],
            "tasks": [],
        }

    # 2. 获取课程列表
    try:
        with _config_lock:
            _set_platform_context(username, website_id)
            courses_raw = get_courses(session)
    except Exception as e:
        logger.error("获取课程列表失败: {}", e)
        return {
            "website_id": website_id,
            "name": platform_name,
            "status": "error",
            "error": f"获取课程列表失败: {e}",
            "courses": [],
            "tasks": [],
        }

    # 3. 逐课程扫描
    courses = []
    all_tasks = []

    for c in courses_raw:
        course_id = c.get("course_id", "")
        course_name = c.get("name", "未知课程")

        course_entry = {
            "course_id": course_id,
            "course_name": course_name,
            "detail_link": c.get("detail_link", ""),
            "study_record_url": c.get("study_record_url", ""),
            "video_total": 0,
            "video_completed": 0,
            "video_pending": 0,
            "video_actionable": 0,
            "exam_total": 0,
            "exam_done": 0,
            "exam_deleted": 0,
            "exam_missed": 0,
            "exam_pending": 0,
            "exam_actionable": 0,
            "records_loaded": False,
        }

        if include_records and course_id:
            try:
                with _config_lock:
                    _set_platform_context(username, website_id)
                result = scan_course(session, course_id, course_name,
                                     username=username, website_id=website_id)

                videos = result.get("videos", [])
                exams = result.get("exams", [])
                works = result.get("works", [])
                tasks = result.get("tasks", [])
                missed = result.get("missed", [])
                pending = result.get("pending", [])
                actionable_videos = result.get("actionable_videos", [])

                video_total = len(videos)
                video_actionable = len(actionable_videos)
                video_completed = video_total - video_actionable

                exam_total = len(exams) + len(works)
                exam_done = sum(1 for e in exams + works if e.get("is_done"))
                exam_deleted = sum(1 for e in exams + works if e.get("is_deleted"))
                exam_actionable = len([t for t in tasks if t.get("task_type") == "exam"])
                exam_missed = len(missed)
                exam_pending = len(pending)

                # 已删除的不计入 exam_total（对用户不可操作）
                exam_active_total = exam_total - exam_deleted

                course_entry.update({
                    "video_total": video_total,
                    "video_completed": video_completed,
                    "video_pending": video_actionable,
                    "video_actionable": video_actionable,
                    "exam_total": exam_active_total,
                    "exam_done": exam_done,
                    "exam_deleted": exam_deleted,
                    "exam_missed": exam_missed,
                    "exam_pending": exam_pending,
                    "exam_actionable": exam_actionable,
                    "records_loaded": True,
                })

                # 给 tasks 加上平台和课程标识
                for t in tasks:
                    t["website_id"] = website_id
                    t["platform_name"] = platform_name
                    t["course_name"] = course_name
                    t["course_id"] = course_id
                all_tasks.extend(tasks)

            except Exception as e:
                logger.error("扫描课程 {} 失败: {}", course_name, e)

        courses.append(course_entry)

    result = {
        "website_id": website_id,
        "name": platform_name,
        "status": "ok",
        "student_name": info.student_name or "",
        "courses": courses,
        "tasks": all_tasks,
    }

    save_scan_cache(username, website_id, result)
    return result


def _discover_and_match() -> Dict[int, Dict]:
    """从 domain_monitor 获取活跃平台列表（统一数据源）

    返回: {website_id: {name, base_url}, ...}
    """
    from api.services.domain_monitor import get_active_platforms
    platforms = get_active_platforms()
    if not platforms:
        logger.warning("平台发现失败，使用默认配置")
        return dict(WEBSITES)
    return {wid: {"name": p["name"], "base_url": p["base_url"]} for wid, p in platforms.items()}


def scan_all_platforms(username: str, password: str,
                       include_records: bool = True) -> list:
    """扫描所有平台（先从学校官网发现平台列表）"""
    platforms = _discover_and_match()
    results = []
    for wid, pinfo in platforms.items():
        result = scan_platform(username, password, wid, include_records,
                               platform_name=pinfo.get("name"))
        results.append(result)
    results.sort(key=lambda x: x["website_id"])
    return results


def get_actionable_tasks_all(username: str, password: str,
                             website_id: int = None) -> list:
    """只返回可操作任务列表（视频+考试+作业合并）"""
    if website_id is not None:
        result = scan_platform(username, password, website_id)
        return result.get("tasks", [])

    platforms = _discover_and_match()
    all_tasks = []
    for wid, pinfo in platforms.items():
        result = scan_platform(username, password, wid,
                               platform_name=pinfo.get("name"))
        all_tasks.extend(result.get("tasks", []))
    return all_tasks


def scan_chaoxing(username: str, password: str, account_name: str = "") -> dict:
    """扫描学习通平台（账号密码登录）

    返回: {website_id, name, status, student_name, courses, tasks}
    """
    from infrastructure.chaoxing_session import ChaoxingSession
    from infrastructure.chaoxing.scanner import scan_chaoxing as _scan

    session = ChaoxingSession()
    if not session.login(username, password):
        return {
            "website_id": 4,
            "name": "学习通",
            "status": "login_failed",
            "error": "账号或密码错误",
            "courses": [],
            "tasks": [],
        }

    result = _scan(session)

    # 缓存结果
    if account_name:
        save_scan_cache(account_name, 4, result)

    return result

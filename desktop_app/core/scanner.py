"""课程扫描 — 精简自 services/scan_service.py"""
import json
import os
import re
import time
from typing import Dict, List, Optional

from loguru import logger

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR, WEBSITES, get_base_url, set_current_account, set_current_website, update_paths_for_current_account, update_url_config
from core.crawler import get_course_nodes_from_api, get_courses

_DELETED_MARKERS = ["已不存在", "已被删除", "可能已被删除", "信息已不存在"]
SCAN_CACHE_TTL = 1800


def _verify_exam_exists(session, base_url: str, work_id, node_id, course_id, chapter_id: str = "") -> bool:
    from core.http_client import safe_request
    base = base_url.rstrip("/")
    wid = int(work_id) if str(work_id).isdigit() else work_id
    cid = int(course_id) if str(course_id).isdigit() else 0
    nid = int(node_id) if str(node_id).isdigit() else 0
    chid = int(chapter_id) if chapter_id and str(chapter_id).isdigit() else 0
    try:
        if chid:
            exam_page_url = f"{base}/user/node/exam?courseId={cid}&chapterId={chid}&nodeId={nid}"
        else:
            exam_page_url = f"{base}/user/work?workId={wid}&courseId={cid}&nodeId={nid}"
        resp = safe_request(session, exam_page_url)
        if not resp:
            return True
        html = resp.content.decode("utf-8", errors="replace")
        for marker in _DELETED_MARKERS:
            if marker in html:
                return False
        if "topic-item" in html or "courseexamcon-main" in html:
            return True
        return True
    except Exception:
        return True


def _clean_html(text) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", str(text)).strip()


def _parse_duration(dur_str) -> int:
    try:
        parts = str(dur_str).split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return int(dur_str)
    except (ValueError, AttributeError):
        return 0


VIDEO_NOT_DONE = {"未学", "未学完", "学习中"}
EXAM_DONE_KEYWORDS = {"已交", "已阅", "已批阅", "已完成", "已通过", "已批改"}


def classify_video(raw_video: dict) -> dict:
    duration_sec = int(raw_video.get("duration", 0))
    if duration_sec <= 0:
        duration_sec = _parse_duration(raw_video.get("videoDuration", "0"))
    progress = float(raw_video.get("progress", 0))
    viewed_sec = int(duration_sec * progress)
    raw_state = _clean_html(raw_video.get("state", ""))
    if raw_state and raw_state not in VIDEO_NOT_DONE:
        status = raw_state
    elif progress >= 1.0:
        status = "已学"
    elif progress > 0:
        status = "未学完"
    elif raw_state:
        status = raw_state
    else:
        status = "未学"
    return {
        "course_name": raw_video.get("course_name", ""),
        "course_id": raw_video.get("course_id", ""),
        "name": raw_video.get("name", ""),
        "node_id": raw_video.get("id", ""),
        "duration": duration_sec,
        "viewed_duration": viewed_sec,
        "progress": progress,
        "video_url": raw_video.get("localFile", ""),
        "status": status,
    }


def classify_exam(raw_exam: dict, now: float = None) -> dict:
    if now is None:
        now = time.time()
    submit_status = _clean_html(raw_exam.get("state", "")) or "未交"
    start_ts = end_ts = 0
    try:
        start_ts = int(raw_exam.get("startTime", 0)) if raw_exam.get("startTime") else 0
        end_ts = int(raw_exam.get("endTime", 0)) if raw_exam.get("endTime") else 0
    except (ValueError, TypeError):
        pass
    if start_ts > 0 and now < start_ts:
        time_status = "未开始"
    elif end_ts > 0 and now > end_ts:
        time_status = "已结束"
    else:
        time_status = "进行中"
    is_actionable = (submit_status in ("未交", "继续做题", "在做")) and time_status == "进行中"
    final_score = _clean_html(raw_exam.get("finalScore", "-"))
    score_str = str(final_score).strip()
    has_valid_score = (score_str and score_str not in ("-", "--", "null", "None", "")
                       and score_str.replace(".", "", 1).isdigit() and float(score_str) > 0)
    is_expired = submit_status == "未交" and time_status == "已结束"
    is_not_started = time_status == "未开始"
    return {
        "course_name": raw_exam.get("course_name", ""),
        "course_id": raw_exam.get("course_id", ""),
        "name": raw_exam.get("title", raw_exam.get("name", "")),
        "work_id": raw_exam.get("id", ""),
        "node_id": raw_exam.get("nodeId", ""),
        "chapter_id": raw_exam.get("chapterId", ""),
        "exam_url": raw_exam.get("url", ""),
        "submit_status": submit_status,
        "time_status": time_status,
        "is_actionable": False if is_not_started else is_actionable,
        "is_done": True if is_not_started else (submit_status in EXAM_DONE_KEYWORDS or has_valid_score or is_expired),
        "is_deleted": False,
        "is_pending": is_not_started,
        "final_score": final_score,
        "start_time": raw_exam.get("startTime", ""),
        "end_time": raw_exam.get("endTime", ""),
        "submit_time": raw_exam.get("submitTime", raw_exam.get("finishTime", "")),
        "frequency": raw_exam.get("frequency", ""),
        "topic_number": raw_exam.get("topicNumber", ""),
    }


def clean_course_data(raw_data: dict, now: float = None) -> dict:
    cleaned_videos = [classify_video(v) for v in raw_data.get("videos", [])]
    cleaned_exams = [classify_exam(e, now) for e in raw_data.get("exams", [])]
    cleaned_works = [classify_exam(w, now) for w in raw_data.get("works", [])]
    cleaned_nodes = []
    for v in cleaned_videos:
        cleaned_nodes.append({"nodeId": v["node_id"], "name": v["name"], "node_type": "video"})
    for e in cleaned_exams:
        cleaned_nodes.append({"nodeId": e["node_id"], "name": e["name"], "node_type": "exam"})
    for w in cleaned_works:
        cleaned_nodes.append({"nodeId": w["node_id"], "name": w["name"], "node_type": "work"})
    return {"nodes": cleaned_nodes, "videos": cleaned_videos, "exams": cleaned_exams, "works": cleaned_works}


def get_all_actionable(cleaned_data: dict) -> dict:
    actionable_videos = [v for v in cleaned_data.get("videos", []) if v.get("status") != "已学"]
    actionable_exams = [e for e in cleaned_data.get("exams", []) + cleaned_data.get("works", [])
                        if e.get("is_actionable") and not e.get("is_pending")]
    tasks = [{**v, "task_type": "video"} for v in actionable_videos]
    tasks += [{**e, "task_type": "exam"} for e in actionable_exams]
    missed = [e for e in cleaned_data.get("exams", []) + cleaned_data.get("works", [])
              if e.get("submit_status") == "未交" and e.get("time_status") == "已结束"]
    pending = [e for e in cleaned_data.get("exams", []) + cleaned_data.get("works", []) if e.get("is_pending")]
    return {"actionable_videos": actionable_videos, "actionable_exams": actionable_exams,
            "tasks": tasks, "missed": missed, "pending": pending}


def scan_course(session, course_id: str, course_name: str, username: str = "", website_id: int = 0) -> dict:
    raw = get_course_nodes_from_api(session, course_id, course_name)
    cleaned = clean_course_data(raw)
    base_url = get_base_url()
    for exam in cleaned.get("exams", []):
        need_verify = exam.get("is_actionable") or "未交" in exam.get("submit_status", "")
        if need_verify:
            chapter_id = exam.get("chapter_id", "")
            if not _verify_exam_exists(session, base_url, exam["work_id"], exam["node_id"], course_id, chapter_id):
                exam["is_deleted"] = True
                exam["is_actionable"] = False
                exam["is_done"] = True
                exam["submit_status"] = "已删除"
    for work in cleaned.get("works", []):
        need_verify = work.get("is_actionable") or "未交" in work.get("submit_status", "")
        if need_verify:
            chapter_id = work.get("chapter_id", "")
            if not _verify_exam_exists(session, base_url, work["work_id"], work["node_id"], course_id, chapter_id):
                work["is_deleted"] = True
                work["is_actionable"] = False
                work["is_done"] = True
                work["submit_status"] = "已删除"
    actionable = get_all_actionable(cleaned)
    return {**cleaned, **actionable}


def _get_scan_cache_path(username: str, website_id: int) -> str:
    website_name = WEBSITES.get(website_id, {}).get("name", f"平台{website_id}")
    safe_ws = website_name.replace(" ", "_")
    cache_dir = os.path.join(DATA_DIR, "accounts", username, "scan_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{safe_ws}.json")


def save_scan_cache(username: str, website_id: int, data: dict):
    path = _get_scan_cache_path(username, website_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"saved_at": time.time(), "data": data}, f, ensure_ascii=False)
    except Exception as e:
        logger.warning("写入扫描缓存失败: {}", e)


def load_scan_cache(username: str, website_id: int) -> Optional[dict]:
    path = _get_scan_cache_path(username, website_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            cache = json.load(f)
        if time.time() - cache.get("saved_at", 0) > SCAN_CACHE_TTL:
            return None
        return cache.get("data")
    except Exception:
        return None


def scan_platform(username: str, password: str, website_id: int, force_refresh: bool = False) -> dict:
    """扫描单个平台全部课程"""
    from core.auth import login_single_platform, save_platform_cookie, load_platform_cookie, check_platform_cookie_valid
    from core.http_client import create_sync_client

    platform_name = WEBSITES.get(website_id, {}).get("name", f"平台{website_id}")
    website_info = WEBSITES.get(website_id, {})

    # 学习通走独立流程
    if website_info.get("type") == "chaoxing":
        return _scan_chaoxing(username, password, force_refresh=force_refresh)

    if not force_refresh:
        cached = load_scan_cache(username, website_id)
        if cached:
            return cached

    # 登录
    session = create_sync_client(website_info["base_url"])
    cookie_loaded = load_platform_cookie(username, website_id, session)
    if cookie_loaded and check_platform_cookie_valid(session, website_id):
        pass  # cookie 有效
    else:
        wid, ok, session, msg = login_single_platform(website_id, username, password)
        if not ok:
            return {"website_id": website_id, "name": platform_name, "status": "login_failed",
                    "error": msg, "courses": [], "tasks": []}
        save_platform_cookie(username, website_id, session)

    # 获取课程
    set_current_website(website_id)
    set_current_account(username)
    update_url_config()
    update_paths_for_current_account()

    courses_raw = get_courses(session)
    if not courses_raw:
        return {"website_id": website_id, "name": platform_name, "status": "error",
                "error": "未获取到课程", "courses": [], "tasks": []}

    courses = []
    all_tasks = []
    for c in courses_raw:
        cid = c.get("course_id", "")
        cname = c.get("name", "未知课程")
        course_entry = {
            "course_id": cid, "course_name": cname,
            "video_total": 0, "video_completed": 0, "video_pending": 0,
            "exam_total": 0, "exam_done": 0, "exam_actionable": 0,
        }
        if cid:
            try:
                result = scan_course(session, cid, cname, username=username, website_id=website_id)
                videos = result.get("videos", [])
                exams = result.get("exams", [])
                works = result.get("works", [])
                tasks = result.get("tasks", [])
                actionable_videos = result.get("actionable_videos", [])
                course_entry.update({
                    "video_total": len(videos),
                    "video_completed": len(videos) - len(actionable_videos),
                    "video_pending": len(actionable_videos),
                    "exam_total": len(exams) + len(works),
                    "exam_done": sum(1 for e in exams + works if e.get("is_done")),
                    "exam_actionable": len([t for t in tasks if t.get("task_type") == "exam"]),
                })
                for t in tasks:
                    t["website_id"] = website_id
                    t["platform_name"] = platform_name
                    t["course_name"] = cname
                    t["course_id"] = cid
                all_tasks.extend(tasks)
            except Exception as e:
                logger.error("扫描课程 {} 失败: {}", cname, e)
        courses.append(course_entry)

    result = {
        "website_id": website_id, "name": platform_name, "status": "ok",
        "student_name": "", "courses": courses, "tasks": all_tasks,
    }
    save_scan_cache(username, website_id, result)
    return result


def _scan_chaoxing(username: str, password: str, force_refresh: bool = False) -> dict:
    """学习通扫描（简化版）"""
    try:
        from infrastructure.chaoxing_session import ChaoxingSession
        from infrastructure.chaoxing.scanner import scan_chaoxing as _scan
    except ImportError:
        return {"website_id": 4, "name": "学习通", "status": "error",
                "error": "学习通模块不可用", "courses": [], "tasks": []}

    if not force_refresh:
        cached = load_scan_cache(username, 4)
        if cached:
            return cached

    session = ChaoxingSession()
    if not session.login(username, password):
        return {"website_id": 4, "name": "学习通", "status": "login_failed",
                "error": "账号或密码错误", "courses": [], "tasks": []}

    result = _scan(session)
    save_scan_cache(username, 4, result)
    return result

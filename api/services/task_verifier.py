from __future__ import annotations

"""任务完成核查 — 任务报告完成后，回查平台学习记录确认是否真完成"""
from typing import Dict, List

from loguru import logger



def verify_task_completion(username: str, website_id: int,
                           course_ids: List[str], job_type: str) -> Dict:
    """核查任务是否真正在平台上完成

    Returns:
        {"verified": bool, "detail": str}
    """
    try:
        from api.services.session_pool import pool
        session_info = pool.get(username, website_id)
        if not session_info:
            return {"verified": False, "detail": "会话已过期，无法核查"}

        session = session_info.session
        from config import (
            get_base_url,
            set_current_account,
            set_current_website,
            update_paths_for_current_account,
            update_url_config,
        )
        set_current_website(website_id)
        set_current_account(username)
        update_url_config()
        update_paths_for_current_account()

        base_url = get_base_url()

        from infrastructure.study_record_crawler import StudyRecordCrawler
        crawler = StudyRecordCrawler(session, base_url)

        for cid in course_ids:
            if job_type == "video":
                result = _verify_videos(crawler, cid)
            elif job_type in ("exam", "work"):
                result = _verify_exams(crawler, cid, job_type)
            else:
                result = {"verified": True, "detail": "未知任务类型，跳过核查"}

            if not result["verified"]:
                return result

        return {"verified": True, "detail": "核查通过"}
    except Exception as e:
        logger.warning(f"核查异常 error={str(e)}")
        return {"verified": False, "detail": f"核查异常: {e}"}


def _verify_videos(crawler, course_id: str) -> Dict:
    """核查视频是否全部已学"""
    try:
        records = crawler.fetch_all_records(course_id, "video")
        if not records:
            return {"verified": False, "detail": "未获取到视频记录"}

        total = len(records)
        done = sum(1 for r in records if "已学" in r.get("status", ""))
        pending = total - done

        if pending == 0:
            return {"verified": True, "detail": f"全部 {total} 个视频已学完"}
        else:
            return {"verified": False, "detail": f"{pending}/{total} 个视频未完成"}
    except Exception as e:
        return {"verified": False, "detail": f"视频记录查询失败: {e}"}


def _verify_exams(crawler, course_id: str, job_type: str) -> Dict:
    """核查考试/作业是否已提交"""
    try:
        record_type = "work" if job_type == "work" else "exam"
        records = crawler.fetch_all_records(course_id, record_type)
        if not records:
            return {"verified": False, "detail": "未获取到考试/作业记录"}

        total = len(records)
        submitted = 0
        for r in records:
            status = r.get("status", "")
            score = r.get("score", "")
            # 已提交/已阅/有分数 都算完成
            if any(kw in status for kw in ("已交", "已阅", "已完成")) or (score and score != "-"):
                submitted += 1

        pending = total - submitted
        label = "作业" if job_type == "work" else "考试"

        if pending == 0:
            return {"verified": True, "detail": f"全部 {total} 个{label}已提交"}
        else:
            return {"verified": False, "detail": f"{pending}/{total} 个{label}未提交"}
    except Exception as e:
        return {"verified": False, "detail": f"{label}记录查询失败: {e}"}

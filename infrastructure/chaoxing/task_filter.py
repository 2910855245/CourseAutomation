"""学习通任务筛选 — 提取可操作任务"""
from typing import List, Dict


def get_actionable_courses(cleaned_courses: List[Dict]) -> List[Dict]:
    """返回有待刷视频的课程列表（有积分系统且积分未满）"""
    return [c for c in cleaned_courses
            if c.get("has_points_system") and c.get("video_pending", 0) > 0]


def get_actionable_tasks(cleaned_courses: List[Dict]) -> List[Dict]:
    """返回所有可操作任务（积分未满或有待完成作业的课程）

    每项带 task_type 标识：chaoxing_points / chaoxing_work / chaoxing_both
    """
    tasks = []
    for c in cleaned_courses:
        has_points = c.get("has_points_system")
        remaining = c.get("points_remaining", 0)
        work_pending = c.get("work_pending", 0)

        need_points = has_points and remaining > 0
        need_work = work_pending > 0

        if not need_points and not need_work:
            continue

        if need_points and need_work:
            task_type = "chaoxing_both"
        elif need_work:
            task_type = "chaoxing_work"
        else:
            task_type = "chaoxing_points"

        tasks.append({
            "task_type": task_type,
            "course_id": c["course_id"],
            "class_id": c["class_id"],
            "course_name": c["course_name"],
            "website_id": 4,
            "platform_name": "学习通",
            "points_remaining": remaining,
            "days_needed": c.get("days_needed", 0),
            "video_count": c.get("video_total", 0),
            "total_minutes": c.get("total_minutes", 0),
            "work_total": c.get("work_total", 0),
            "work_pending": work_pending,
        })
    return tasks


def get_done_courses(cleaned_courses: List[Dict]) -> List[Dict]:
    """返回已完成的课程（有积分系统且积分已满）"""
    return [c for c in cleaned_courses
            if c.get("has_points_system") and c.get("points_remaining", 0) <= 0]


def get_no_points_courses(cleaned_courses: List[Dict]) -> List[Dict]:
    """返回无积分系统的课程（无法刷课）"""
    return [c for c in cleaned_courses if not c.get("has_points_system")]

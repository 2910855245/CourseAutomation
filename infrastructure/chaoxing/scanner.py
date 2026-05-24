"""学习通扫描入口 — 爬取 → 清洗 → 筛选，统一返回标准化格式"""
from loguru import logger

from infrastructure.chaoxing_session import ChaoxingSession
from infrastructure.chaoxing.crawler import (
    fetch_course_list,
    fetch_knowledge_list,
    fetch_points,
)
from infrastructure.chaoxing.cleaner import clean_courses, clean_course_full
from infrastructure.chaoxing.task_filter import get_actionable_tasks, get_done_courses, get_no_points_courses
from infrastructure.chaoxing_quiz import get_work_list



def scan_chaoxing(session: ChaoxingSession) -> dict:
    """扫描学习通全部课程

    流程: 抓取课程列表 → 排除已结束 → 逐课爬取知识点+积分 → 清洗 → 筛选任务

    返回: {website_id, name, status, student_name, courses, tasks}
    """
    user_info = session.get_user_info()
    student_name = user_info.get("name", "")

    # 1. 抓取课程列表（含已结束标记）
    raw_courses = fetch_course_list(session)
    if not raw_courses:
        return {
            "website_id": 4,
            "name": "学习通",
            "status": "error",
            "error": "获取课程列表失败",
            "courses": [],
            "tasks": [],
        }

    # 2. 清洗：排除已结束课程
    active_courses = clean_courses(raw_courses)
    ended_count = len(raw_courses) - len(active_courses)
    if ended_count:
        logger.info(f"排除已结束课程 ended={ended_count} active={len(active_courses)}")

    # 3. 逐课爬取知识点 + 积分 + 作业，清洗
    courses = []
    for c in active_courses:
        cid = c["course_id"]
        clid = c["class_id"]

        points = fetch_points(session, cid, clid)
        raw_points = fetch_knowledge_list(session, cid, clid)

        # 检测作业列表
        try:
            works = get_work_list(session, cid, clid)
            work_total = len(works)
            # 状态为空或含"未"视为待完成
            work_pending = sum(1 for w in works
                               if not w.get('status') or '未' in w.get('status', ''))
            work_completed = work_total - work_pending
        except Exception as e:
            logger.warning(f"获取作业列表失败 course_id={cid} error={str(e)}")
            work_total, work_pending, work_completed = 0, 0, 0

        cleaned = clean_course_full(
            {"courseId": cid, "classId": clid, "name": c["course_name"]},
            raw_points,
            points,
            work_total=work_total,
            work_pending=work_pending,
            work_completed=work_completed,
        )
        # 保留教师信息
        cleaned["teacher"] = c.get("teacher", "")
        courses.append(cleaned)

    # 4. 筛选任务
    tasks = get_actionable_tasks(courses)
    done = get_done_courses(courses)
    no_points = get_no_points_courses(courses)

    logger.info("学习通扫描完成",
                total=len(courses),
                actionable=len(tasks),
                done=len(done),
                no_points=len(no_points),
                ended_skipped=ended_count)

    # 5. 汇总积分
    total_points = 0
    for c in courses:
        pts = c.get('points', {})
        if pts and pts.get('total') is not None:
            total_points = max(total_points, pts['total'])

    return {
        "website_id": 4,
        "name": "学习通",
        "status": "ok",
        "student_name": student_name,
        "school_name": user_info.get("school_name", ""),
        "student_code": user_info.get("student_code", ""),
        "points_total": total_points,
        "points_target": 200,
        "courses": courses,
        "tasks": tasks,
    }

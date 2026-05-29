"""学习通扫描入口 — 爬取 → 清洗 → 筛选，统一返回标准化格式"""
from loguru import logger

from infrastructure.chaoxing_session import ChaoxingSession
from infrastructure.chaoxing.crawler import (
    fetch_course_list,
    fetch_knowledge_list,
    fetch_points,
    fetch_must_learn_kids,
    fetch_must_learn_completion,
    fetch_all_video_completion,
)
from infrastructure.chaoxing.cleaner import clean_courses, clean_course_full
from infrastructure.chaoxing.task_filter import get_actionable_tasks, get_done_courses, get_no_points_courses
from infrastructure.chaoxing_quiz import get_work_list
from infrastructure.chaoxing_points import ScoreRuleParser, PointsRule



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

    # 3. 获取 cpi 映射（courseId → cpi）
    cpi_map = {}
    try:
        resp = session.get('https://mooc1-api.chaoxing.com/mycourse/backclazzdata?view=json&rss=1')
        for ch in resp.json().get('channelList', []):
            content = ch.get('content', {})
            if isinstance(content, dict):
                for cr in content.get('course', {}).get('data', []):
                    cpi_map[str(cr.get('id', ''))] = str(ch.get('cpi', ''))
    except Exception as e:
        logger.warning(f"获取cpi映射失败 error={str(e)}")

    # 4. 逐课爬取知识点 + 积分 + 作业 + 必学完成状态，清洗
    courses = []
    for c in active_courses:
        cid = c["course_id"]
        clid = c["class_id"]
        cpi = cpi_map.get(cid, "")

        points = fetch_points(session, cid, clid)
        raw_points = fetch_knowledge_list(session, cid, clid)

        # 获取积分规则
        try:
            points_rule = ScoreRuleParser.fetch_rules(session, cid, clid)
        except Exception as e:
            logger.warning(f"获取积分规则失败 course_id={cid} error={str(e)}")
            points_rule = PointsRule()

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

        # 获取必学知识点完成状态
        must_learn_status = {}
        if cpi:
            try:
                must_learn_kids = fetch_must_learn_kids(session, cid, clid)
                if must_learn_kids:
                    must_learn_status = fetch_must_learn_completion(
                        session, cid, clid, cpi, must_learn_kids)
            except Exception as e:
                logger.warning(f"获取必学完成状态失败 course_id={cid} error={str(e)}")

        # 获取所有视频知识点的完成状态（cards API isPassed）
        video_completion_map = {}
        if cpi:
            video_kids = [p["knowledgeId"] for p in raw_points if p.get("has_video")]
            if video_kids:
                try:
                    logger.info(f"检查视频完成状态 course={c['course_name']} count={len(video_kids)}")
                    video_completion_map = fetch_all_video_completion(
                        session, cid, clid, cpi, video_kids)
                except Exception as e:
                    logger.warning(f"获取视频完成状态失败 course_id={cid} error={str(e)}")

        cleaned = clean_course_full(
            {"courseId": cid, "classId": clid, "name": c["course_name"]},
            raw_points,
            points,
            work_total=work_total,
            work_pending=work_pending,
            work_completed=work_completed,
            must_learn_status=must_learn_status,
            video_completion_map=video_completion_map,
        )
        # 保留教师信息
        cleaned["teacher"] = c.get("teacher", "")
        # 附加积分规则
        cleaned["points_rule"] = {
            "target": points_rule.target,
            "daily_limit": points_rule.daily_limit,
            "video_min": points_rule.video_min,
            "must_read": points_rule.must_read,
        }
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

"""学习通扫描入口 — 爬取 → 清洗 → 筛选，统一返回标准化格式"""
import concurrent.futures
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



def _process_single_course(session: ChaoxingSession, c: dict, cpi: str,
                           quick_mode: bool = True) -> dict:
    """处理单门课程（可并行调用）"""
    cid = c["course_id"]
    clid = c["class_id"]

    # 并行获取：积分、知识点、作业
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        f_points = pool.submit(fetch_points, session, cid, clid)
        f_raw_points = pool.submit(fetch_knowledge_list, session, cid, clid)
        f_works = pool.submit(get_work_list, session, cid, clid)

        points = f_points.result()
        raw_points = f_raw_points.result()

        try:
            works = f_works.result()
            work_total = len(works)
            work_pending = sum(1 for w in works
                               if not w.get('status') or '未' in w.get('status', ''))
            work_completed = work_total - work_pending
        except Exception as e:
            logger.warning(f"获取作业列表失败 course_id={cid} error={str(e)}")
            work_total, work_pending, work_completed = 0, 0, 0

    # 积分规则
    try:
        points_rule = ScoreRuleParser.fetch_rules(session, cid, clid)
    except Exception as e:
        logger.warning(f"获取积分规则失败 course_id={cid} error={str(e)}")
        points_rule = PointsRule()

    # 必学 + 视频完成状态
    must_learn_status = {}
    video_completion_map = {}

    if cpi:
        video_kids = [p["knowledgeId"] for p in raw_points if p.get("has_video")]

        # 快速模式：跳过必学检测，只检测视频
        if quick_mode:
            if video_kids:
                logger.info(f"检查视频完成状态 course={c['course_name']} count={len(video_kids)} quick=True")
                video_completion_map = fetch_all_video_completion(
                    session, cid, clid, cpi, video_kids, quick_mode=True)
        else:
            # 完整模式：必学 + 视频并行
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                f_must = None
                try:
                    must_learn_kids = fetch_must_learn_kids(session, cid, clid)
                    if must_learn_kids:
                        f_must = pool.submit(
                            fetch_must_learn_completion, session, cid, clid, cpi, must_learn_kids)
                except Exception as e:
                    logger.warning(f"获取必学完成状态失败 course_id={cid} error={str(e)}")

                f_video = None
                if video_kids:
                    logger.info(f"检查视频完成状态 course={c['course_name']} count={len(video_kids)} quick=False")
                    f_video = pool.submit(
                        fetch_all_video_completion, session, cid, clid, cpi, video_kids,
                        quick_mode=False)

                if f_must:
                    try:
                        must_learn_status = f_must.result()
                    except Exception:
                        pass
                if f_video:
                    try:
                        video_completion_map = f_video.result()
                    except Exception:
                        pass

    # 清洗
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
    cleaned["teacher"] = c.get("teacher", "")
    cleaned["points_rule"] = {
        "target": points_rule.target,
        "daily_limit": points_rule.daily_limit,
        "video_min": points_rule.video_min,
        "must_read": points_rule.must_read,
    }
    return cleaned


def _fetch_cpi_map(session: ChaoxingSession) -> dict:
    """获取 courseId → cpi 映射"""
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
    return cpi_map


def scan_chaoxing(session: ChaoxingSession, quick_mode: bool = True) -> dict:
    """扫描学习通全部课程

    流程: 并行抓取课程列表+CPI → 排除已结束 → 并行爬取知识点+积分 → 清洗 → 筛选任务

    返回: {website_id, name, status, student_name, courses, tasks}
    """
    user_info = session.get_user_info()
    student_name = user_info.get("name", "")

    # 1. 并行获取课程列表 + CPI 映射
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f_courses = pool.submit(fetch_course_list, session)
        f_cpi = pool.submit(_fetch_cpi_map, session)
        raw_courses = f_courses.result()
        cpi_map = f_cpi.result()

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

    # 4. 并行处理各课程
    courses = []

    def _process(c):
        cid = c["course_id"]
        cpi = cpi_map.get(cid, "")
        return _process_single_course(session, c, cpi, quick_mode=quick_mode)

    # 课程不多时直接串行，避免 session 竞争
    if len(active_courses) <= 2:
        for c in active_courses:
            courses.append(_process(c))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(_process, c): c for c in active_courses}
            for future in concurrent.futures.as_completed(futures):
                try:
                    courses.append(future.result())
                except Exception as e:
                    c = futures[future]
                    logger.error(f"课程处理失败 {c.get('course_name')}: {e}")

    # 5. 筛选任务
    tasks = get_actionable_tasks(courses)
    done = get_done_courses(courses)
    no_points = get_no_points_courses(courses)

    logger.info("学习通扫描完成",
                total=len(courses),
                actionable=len(tasks),
                done=len(done),
                no_points=len(no_points),
                ended_skipped=ended_count)

    # 6. 汇总积分
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

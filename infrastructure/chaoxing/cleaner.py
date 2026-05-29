"""学习通数据清洗 — 像学校平台一样标准化、排除已结束课程"""
from typing import List, Dict


# ── 课程清洗 ──────────────────────────────────────────────

def clean_courses(raw_courses: list) -> List[Dict]:
    """清洗课程列表：排除已结束、去重、标准化字段

    输入: crawler.fetch_course_list 原始列表
    输出: 清洗后的列表，仅保留可操作课程
    """
    cleaned = []
    for c in raw_courses:
        if c.get("ended"):
            continue
        cleaned.append({
            "course_id": c["courseId"],
            "class_id": c["classId"],
            "course_name": c["name"],
            "teacher": c.get("teacher", ""),
            "cover_url": c.get("cover_url", ""),
        })
    return cleaned


# ── 视频清洗 ──────────────────────────────────────────────

def classify_video(raw_point: dict, points_info: dict = None) -> dict:
    """清洗单个知识点（视频），判定完成状态

    输入: crawler.fetch_knowledge_list 单条记录
    输出: 标准化 dict，含 status 字段
    """
    video_minutes = raw_point.get("video_minutes", 0)
    has_video = raw_point.get("has_video", False)

    # 学习通的积分制：总分200，视频每天上限50分
    # 通过积分推算视频完成度
    video_score = 0
    if points_info:
        video_score = points_info.get("video", 0)

    if not has_video:
        status = "无视频"
    elif video_score >= 200:
        status = "已学"
    elif video_score > 0:
        status = "未学完"
    else:
        status = "未学"

    return {
        "knowledge_id": raw_point.get("knowledgeId", ""),
        "class_id": raw_point.get("classId", ""),
        "name": raw_point.get("name", "未知"),
        "has_video": has_video,
        "video_minutes": video_minutes,
        "video_score": video_score,
        "status": status,
    }


def classify_videos(raw_points: list, points_info: dict = None) -> List[Dict]:
    """批量清洗视频知识点"""
    return [classify_video(p, points_info) for p in raw_points]


# ── 课程完整数据清洗 ──────────────────────────────────────

def clean_course_full(raw_course: dict, raw_points: list, points_info: dict,
                      work_total: int = 0, work_pending: int = 0, work_completed: int = 0,
                      must_learn_status: dict = None) -> dict:
    """清洗单门课程的完整数据

    输入:
        raw_course: crawler.fetch_course_list 单条记录
        raw_points: crawler.fetch_knowledge_list 返回列表
        points_info: crawler.fetch_points 返回字典

    输出: 标准化的课程数据 dict
    """
    cleaned_videos = classify_videos(raw_points, points_info)
    video_points = [v for v in cleaned_videos if v["has_video"]]
    total_minutes = sum(v["video_minutes"] for v in video_points)

    # 统计视频状态
    video_done = sum(1 for v in video_points if v["status"] == "已学")
    video_pending = len(video_points) - video_done

    # 必学知识点完成状态
    ml_video_done, ml_video_total = 0, 0
    ml_quiz_done, ml_quiz_total = 0, 0
    ml_read_done, ml_read_total = 0, 0
    must_learn_done = True  # 默认完成（无必学时）

    if must_learn_status:
        for kid, status in must_learn_status.items():
            ml_video_done += status.get("video_done", 0)
            ml_video_total += status.get("video_total", 0)
            ml_quiz_done += status.get("quiz_done", 0)
            ml_quiz_total += status.get("quiz_total", 0)
            ml_read_done += status.get("read_done", 0)
            ml_read_total += status.get("read_total", 0)
        # 有必学知识点时，必须全部完成
        must_learn_done = all(s.get("all_done", False) for s in must_learn_status.values())
        # 如果没有任何任务（纯讨论/笔记知识点），也算完成
        if ml_video_total + ml_quiz_total + ml_read_total == 0:
            must_learn_done = True

    # 积分系统：空字典表示该课程无积分系统
    has_points = bool(points_info)
    remaining = points_info.get("remaining", 0) if has_points else 0
    days_needed = points_info.get("days_needed", 0) if has_points else 0

    return {
        "course_id": raw_course["courseId"],
        "class_id": raw_course["classId"],
        "course_name": raw_course["name"],
        "teacher": raw_course.get("teacher", ""),
        # 视频统计
        "video_total": len(video_points),
        "video_completed": video_done,
        "video_pending": video_pending,
        "video_actionable": video_pending,
        # 考试/作业（学习通暂不支持，预留字段）
        "exam_total": 0,
        "exam_done": 0,
        "exam_deleted": 0,
        "exam_pending": 0,
        "exam_actionable": 0,
        "records_loaded": True,
        # 学习通特有
        "has_points_system": has_points,
        "work_total": work_total,
        "work_pending": work_pending,
        "work_completed": work_completed,
        "points_total": points_info.get("total", 0) if has_points else 0,
        "points_video": points_info.get("video", 0) if has_points else 0,
        "points_remaining": remaining,
        "days_needed": days_needed,
        "study_days": points_info.get("study_days", 0) if has_points else 0,
        "total_minutes": total_minutes,
        # 必学知识点完成状态
        "must_learn_done": must_learn_done,
        "must_learn_video_done": ml_video_done,
        "must_learn_video_total": ml_video_total,
        "must_learn_quiz_done": ml_quiz_done,
        "must_learn_quiz_total": ml_quiz_total,
        "must_learn_read_done": ml_read_done,
        "must_learn_read_total": ml_read_total,
    }

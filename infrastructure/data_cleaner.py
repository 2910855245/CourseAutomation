import re
import time


def clean_html(text) -> str:
    """移除HTML标签，提取纯文本"""
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', str(text)).strip()


def parse_duration(dur_str) -> int:
    """将 HH:MM:SS 或 MM:SS 格式转为秒数"""
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
    """清洗视频数据，判定学习状态

    输入: course_crawler 原始 video dict
    输出: 清洗后的 dict，增加 status 字段
    """
    duration_sec = int(raw_video.get("duration", 0))
    if duration_sec <= 0:
        duration_sec = parse_duration(raw_video.get("videoDuration", "0"))
    progress = float(raw_video.get("progress", 0))
    # API的viewedDuration不可靠(部分观看也返完整时长), 用progress*duration推算真实已看秒数
    viewed_sec = int(duration_sec * progress)

    raw_state = clean_html(raw_video.get("state", ""))
    # 信任API的state字段，仅当state不可用时才用progress推算
    if raw_state and raw_state not in VIDEO_NOT_DONE:
        status = raw_state  # API明确标记已学
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


def _parse_time_status(start_time, end_time, now: float = None) -> str:
    """根据 startTime/endTime 判定时间状态"""
    if now is None:
        now = time.time()
    try:
        start_ts = int(start_time) if start_time else 0
        end_ts = int(end_time) if end_time else 0
    except (ValueError, TypeError):
        return "进行中"

    if start_ts > 0 and now < start_ts:
        return "未开始"
    if end_ts > 0 and now > end_ts:
        return "已结束"
    return "进行中"


def classify_exam(raw_exam: dict, now: float = None) -> dict:
    """清洗考试数据，判定提交状态和时间状态

    输出增加:
      - submit_status: 未交/已交/已阅/已批阅/已完成/已通过/已批改
      - time_status: 未开始/进行中/已结束
      - is_actionable: bool (未交 + 进行中)
    """
    submit_status = clean_html(raw_exam.get("state", "")) or "未交"
    time_status = _parse_time_status(raw_exam.get("startTime"), raw_exam.get("endTime"), now)
    # 继续做题/在做 = 用户已开始但未提交，可操作
    is_actionable = (submit_status in ("未交", "继续做题", "在做")) and time_status == "进行中"

    final_score = clean_html(raw_exam.get("finalScore", "-"))

    # 判断是否有有效分数（平台显示prog=0%但score=100的情况）
    score_str = str(final_score).strip()
    has_valid_score = (
        score_str
        and score_str not in ("-", "--", "null", "None", "")
        and score_str.replace(".", "", 1).isdigit()
        and float(score_str) > 0
    )

    # 考试已结束且未提交(且不是"继续做题"状态) → 视为已完成（用户无法再操作）
    is_expired = submit_status == "未交" and time_status == "已结束"

    return {
        "course_name": raw_exam.get("course_name", ""),
        "course_id": raw_exam.get("course_id", ""),
        "name": raw_exam.get("title", raw_exam.get("name", "")),
        "work_id": raw_exam.get("id", ""),
        "node_id": raw_exam.get("nodeId", ""),
        "submit_status": submit_status,
        "time_status": time_status,
        "is_actionable": is_actionable,
        "is_done": submit_status in EXAM_DONE_KEYWORDS or has_valid_score or is_expired,
        "is_deleted": False,
        "final_score": final_score,
        "start_time": raw_exam.get("startTime", ""),
        "end_time": raw_exam.get("endTime", ""),
        "submit_time": raw_exam.get("submitTime", raw_exam.get("finishTime", "")),
        "frequency": raw_exam.get("frequency", ""),
        "topic_number": raw_exam.get("topicNumber", ""),
    }


def classify_work(raw_work: dict, now: float = None) -> dict:
    """清洗作业数据，逻辑同 classify_exam"""
    return classify_exam(raw_work, now)


def clean_course_data(raw_data: dict, now: float = None) -> dict:
    """清洗整个课程数据

    输入: get_course_nodes_from_api 原始返回
    输出: 清洗后的 {nodes, videos, exams, works}
    """
    cleaned_videos = [classify_video(v, ) for v in raw_data.get("videos", [])]
    cleaned_exams = [classify_exam(e, now) for e in raw_data.get("exams", [])]
    cleaned_works = [classify_work(w, now) for w in raw_data.get("works", [])]

    # 重建 nodes（保持原有结构兼容性）
    cleaned_nodes = []
    for v in cleaned_videos:
        cleaned_nodes.append({
            "nodeId": v["node_id"],
            "name": v["name"],
            "url": f"/user/node?nodeId={v['node_id']}",
            "node_type": "video",
            "hidden_params": {
                "node_type": "video",
                "video-duration": str(v["duration"]),
                "video-file": v["video_url"],
            },
            "chapterId": "",
        })
    for e in cleaned_exams:
        cleaned_nodes.append({
            "nodeId": e["node_id"],
            "name": e["name"],
            "url": f"/user/node?nodeId={e['node_id']}",
            "node_type": "exam",
            "hidden_params": {
                "node_type": "exam",
                "work_id": e["work_id"],
                "topic_number": e["topic_number"],
                "frequency": e["frequency"],
                "start_time": e["start_time"],
                "end_time": e["end_time"],
                "final_score": e["final_score"],
            },
            "chapterId": "",
        })
    for w in cleaned_works:
        cleaned_nodes.append({
            "nodeId": w["node_id"],
            "name": w["name"],
            "url": f"/user/node?nodeId={w['node_id']}",
            "node_type": "work",
            "hidden_params": {
                "node_type": "work",
                "work_id": w["work_id"],
                "topic_number": w["topic_number"],
                "frequency": w["frequency"],
                "final_score": w["final_score"],
            },
            "chapterId": "",
        })

    return {
        "nodes": cleaned_nodes,
        "videos": cleaned_videos,
        "exams": cleaned_exams,
        "works": cleaned_works,
    }

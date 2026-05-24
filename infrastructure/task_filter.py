from typing import List


def get_actionable_videos(cleaned_data: dict) -> List[dict]:
    """返回未完成的视频列表"""
    return [v for v in cleaned_data.get("videos", []) if v.get("status") != "已学"]


def get_actionable_exams(cleaned_data: dict) -> List[dict]:
    """返回可操作的考试/作业列表（未交 + 进行中）"""
    result = []
    for item in cleaned_data.get("exams", []) + cleaned_data.get("works", []):
        if item.get("is_actionable"):
            result.append(item)
    return result


def get_missed_exams(cleaned_data: dict) -> List[dict]:
    """返回已错过的考试/作业列表（未交 + 已结束）"""
    result = []
    for item in cleaned_data.get("exams", []) + cleaned_data.get("works", []):
        if item.get("submit_status") == "未交" and item.get("time_status") == "已结束":
            result.append(item)
    return result


def get_pending_exams(cleaned_data: dict) -> List[dict]:
    """返回待开放的考试/作业列表（未交 + 未开始）"""
    result = []
    for item in cleaned_data.get("exams", []) + cleaned_data.get("works", []):
        if item.get("submit_status") == "未交" and item.get("time_status") == "未开始":
            result.append(item)
    return result


def get_actionable_tasks(cleaned_data: dict) -> List[dict]:
    """返回所有可操作任务（视频+考试+作业合并），每项带 task_type 标识"""
    tasks = []
    for v in get_actionable_videos(cleaned_data):
        tasks.append({**v, "task_type": "video"})
    for e in get_actionable_exams(cleaned_data):
        tasks.append({**e, "task_type": "exam"})
    return tasks


def get_all_actionable(cleaned_data: dict) -> dict:
    """返回所有分类结果（key 带 actionable_ 前缀，避免与 cleaned 数据冲突）"""
    return {
        "actionable_videos": get_actionable_videos(cleaned_data),
        "actionable_exams": get_actionable_exams(cleaned_data),
        "tasks": get_actionable_tasks(cleaned_data),
        "missed": get_missed_exams(cleaned_data),
        "pending": get_pending_exams(cleaned_data),
    }

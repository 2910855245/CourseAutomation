"""定价领域服务：课程类型检测 + 打包定价计算。

路由层（api/routers/pricing.py）只做端点编排，业务逻辑统一在本模块，
供 orders/order_service/前端 calculate 共用，避免三处计价实现漂移。
"""
from __future__ import annotations

from typing import Protocol

from api.database import db


def get_or_default(key: str, default: float) -> float:
    val = db.config_get(key)
    return float(val) if val else default


def get_pricing_config() -> dict:
    """打包定价完整配置（与数据库 config 表对应）"""
    return {
        "price_small": get_or_default("price_small", 3.0),
        "price_medium": get_or_default("price_medium", 5.0),
        "price_large": get_or_default("price_large", 6.0),
        "discount_25": get_or_default("discount_25", 0.7),
        "discount_50": get_or_default("discount_50", 0.5),
        "discount_75": get_or_default("discount_75", 0.3),
        "price_minimum": get_or_default("price_minimum", 2.0),
        "price_exam_only": get_or_default("price_exam_only", 5.0),
        "price_homework_only": get_or_default("price_homework_only", 3.0),
        "price_chaoxing": get_or_default("price_chaoxing", 8.0),
    }


class CourseLike(Protocol):
    video_total: int
    video_completed: int
    exam_total: int
    exam_done: int
    homework_total: int
    homework_done: int


def detect_course_type(c: CourseLike) -> str:
    """检测课程类型：video / exam_only / homework_only / exam_homework / unknown

    当视频全部完成、只剩考试或作业未完成时，按考试/作业类型计价。
    """
    has_video = c.video_total > 0
    video_all_done = has_video and c.video_completed >= c.video_total
    has_exam = c.exam_total > 0 and c.exam_done < c.exam_total
    has_homework = c.homework_total > 0 and c.homework_done < c.homework_total

    if video_all_done:
        if has_exam and not has_homework:
            return "exam_only"
        if has_homework and not has_exam:
            return "homework_only"
        if has_exam and has_homework:
            return "exam_homework"
        return "video"  # 全部完成，无待做内容
    if has_video:
        return "video"
    if has_exam and not has_homework:
        return "exam_only"
    if has_homework and not has_exam:
        return "homework_only"
    if has_exam and has_homework:
        return "exam_homework"
    return "unknown"


def calculate_package_price(video_total: int, video_completed: int) -> float:
    """打包模式：按视频数分档 + 进度折扣 + 最低收费"""
    if video_total <= 0:
        return 0.0
    cfg = get_pricing_config()

    match video_total:
        case n if n <= 30:
            base = cfg["price_small"]
        case n if n <= 80:
            base = cfg["price_medium"]
        case _:
            base = cfg["price_large"]

    progress = (video_completed / video_total * 100) if video_total > 0 else 0
    match progress:
        case p if p <= 25:
            coeff = 1.0
        case p if p <= 50:
            coeff = cfg["discount_25"]
        case p if p <= 75:
            coeff = cfg["discount_50"]
        case _:
            coeff = cfg["discount_75"]

    return max(cfg["price_minimum"], round(base * coeff, 2))


def package_label(video_total: int, video_completed: int) -> str:
    tier = "小课" if video_total <= 30 else ("中课" if video_total <= 80 else "大课")
    progress = round(video_completed / video_total * 100) if video_total > 0 else 0
    return f"{tier} {video_total}视频 {progress}%进度"

import json
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from api.database import db

router = APIRouter(prefix="/api/pricing", tags=["套餐定价"])


def _get_or_default(key: str, default: float) -> float:
    val = db.config_get(key)
    return float(val) if val else default


@router.get("")
def get_pricing():
    price_small = _get_or_default("price_small", 3.00)
    price_medium = _get_or_default("price_medium", 5.00)
    price_large = _get_or_default("price_large", 6.00)
    discount_25 = _get_or_default("discount_25", 0.7)
    discount_50 = _get_or_default("discount_50", 0.5)
    discount_75 = _get_or_default("discount_75", 0.3)
    price_minimum = _get_or_default("price_minimum", 2.00)
    price_exam_only = _get_or_default("price_exam_only", 5.00)
    price_homework_only = _get_or_default("price_homework_only", 3.00)
    price_chaoxing = _get_or_default("price_chaoxing", 8.00)

    return {
        "code": 0,
        "data": {
            "priceSmall": round(price_small, 2),
            "priceMedium": round(price_medium, 2),
            "priceLarge": round(price_large, 2),
            "discount25": round(discount_25, 2),
            "discount50": round(discount_50, 2),
            "discount75": round(discount_75, 2),
            "priceMinimum": round(price_minimum, 2),
            "priceExamOnly": round(price_exam_only, 2),
            "priceHomeworkOnly": round(price_homework_only, 2),
            "priceChaoxing": round(price_chaoxing, 2),
        },
    }


class MarketInput(BaseModel):
    avg_price: float          # 市场平均价
    max_price: float          # 市场最高价
    min_price: Optional[float] = None  # 市场最低价（可选）
    my_cost_per_course: Optional[float] = 0.5  # 你的单课边际成本
    extra_info: Optional[str] = ""  # 其他市场信息（可选）


class CourseItem(BaseModel):
    course_id: str
    video_total: int = 0
    video_completed: int = 0
    exam_total: int = 0
    exam_done: int = 0
    exam_actionable: int = 0
    homework_total: int = 0
    homework_done: int = 0


class CalculateRequest(BaseModel):
    courses: List[CourseItem]


def _detect_course_type(c: CourseItem) -> str:
    """检测课程类型：video / exam_only / homework_only / mixed

    当视频全部完成、只剩考试或作业未完成时，按考试/作业类型计价。
    """
    has_video = c.video_total > 0
    video_all_done = has_video and c.video_completed >= c.video_total
    has_exam = c.exam_total > 0 and c.exam_done < c.exam_total
    has_homework = c.homework_total > 0 and c.homework_done < c.homework_total

    # 视频全部完成，只剩考试/作业 → 按考试/作业计价
    if video_all_done:
        if has_exam and not has_homework:
            return "exam_only"
        if has_homework and not has_exam:
            return "homework_only"
        if has_exam and has_homework:
            return "exam_homework"
        return "video"  # 全部完成，无待做内容

    # 有视频未完成 → 走视频打包价
    if has_video:
        return "video"
    if has_exam and not has_homework:
        return "exam_only"
    if has_homework and not has_exam:
        return "homework_only"
    if has_exam and has_homework:
        return "exam_homework"
    return "unknown"


def _calculate_package_price_backend(video_total: int, video_completed: int) -> float:
    """打包模式：按视频数分档 + 进度折扣"""
    if video_total <= 0:
        return 0.0
    price_small = _get_or_default("price_small", 3.0)
    price_medium = _get_or_default("price_medium", 5.0)
    price_large = _get_or_default("price_large", 6.0)
    discount_25 = _get_or_default("discount_25", 0.7)
    discount_50 = _get_or_default("discount_50", 0.5)
    discount_75 = _get_or_default("discount_75", 0.3)
    price_minimum = _get_or_default("price_minimum", 2.0)

    if video_total <= 30:
        base = price_small
    elif video_total <= 80:
        base = price_medium
    else:
        base = price_large

    progress = (video_completed / video_total * 100) if video_total > 0 else 0
    if progress <= 25:
        coeff = 1.0
    elif progress <= 50:
        coeff = discount_25
    elif progress <= 75:
        coeff = discount_50
    else:
        coeff = discount_75

    return max(price_minimum, round(base * coeff, 2))


@router.post("/calculate")
def calculate_pricing(req: CalculateRequest):
    """根据课程数据计算每门课价格（打包定价）"""
    price_exam_only = _get_or_default("price_exam_only", 5.0)
    price_homework_only = _get_or_default("price_homework_only", 3.0)

    results = []
    total = 0.0

    for c in req.courses:
        course_type = _detect_course_type(c)

        if course_type == "video":
            price = _calculate_package_price_backend(c.video_total, c.video_completed)
            label = _package_label(c.video_total, c.video_completed)
        elif course_type == "exam_only":
            price = price_exam_only
            label = "纯考试"
        elif course_type == "homework_only":
            price = price_homework_only
            label = "纯作业"
        elif course_type == "exam_homework":
            price = max(price_exam_only, price_homework_only)
            label = "考试+作业"
        else:
            price = 0.0
            label = "未知"

        total += price
        results.append({
            "course_id": c.course_id,
            "type": course_type,
            "price": price,
            "label": label,
        })

    return {
        "code": 0,
        "data": {
            "courses": results,
            "total": round(total, 2),
            "pricing_mode": "package",
        },
    }


def _package_label(video_total: int, video_completed: int) -> str:
    if video_total <= 30:
        tier = "小课"
    elif video_total <= 80:
        tier = "中课"
    else:
        tier = "大课"
    progress = round(video_completed / video_total * 100) if video_total > 0 else 0
    return f"{tier} {video_total}视频 {progress}%进度"


@router.post("/recommend")
def recommend_pricing(market: MarketInput):
    """调用 DeepSeek AI 根据市场行情推荐定价方案"""
    from api.services.pricing_service import recommend_pricing as _recommend
    avg = market.avg_price
    mx = market.max_price
    mn = market.min_price or avg * 0.5
    cost = market.my_cost_per_course
    extra = market.extra_info or ""
    return _recommend(avg, mx, mn, cost, extra)


@router.post("/apply-package")
def apply_package_pricing(config: dict):
    """一键应用打包定价方案"""
    mapping = {
        "priceSmall": "price_small",
        "priceMedium": "price_medium",
        "priceLarge": "price_large",
        "discount25": "discount_25",
        "discount50": "discount_50",
        "discount75": "discount_75",
        "priceMinimum": "price_minimum",
        "priceExamOnly": "price_exam_only",
        "priceHomeworkOnly": "price_homework_only",
        "priceChaoxing": "price_chaoxing",
    }
    applied = {}
    for frontend_key, db_key in mapping.items():
        if frontend_key in config:
            db.config_set(db_key, str(config[frontend_key]))
            applied[db_key] = config[frontend_key]
    db.config_set("pricing_mode", "package")
    return {"code": 0, "message": "打包定价已应用", "data": applied}

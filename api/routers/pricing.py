import json
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from api.database import db
from api.services.pricing_service import (
    calculate_package_price as _calculate_package_price_backend,
    detect_course_type as _detect_course_type,
    get_or_default as _get_or_default,
    package_label as _package_label,
)

router = APIRouter(prefix="/api/pricing", tags=["套餐定价"])


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

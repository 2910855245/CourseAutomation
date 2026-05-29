"""订单服务 — 批量订单价格计算与校验"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from loguru import logger
from fastapi import HTTPException

from api.database import db



def validate_new_order(uid: str, client_ip: str, course_ids: list, price: float,
                       video_count: int, username: str) -> None:
    """新订单的风控校验（黑名单、频率、参数、价格），不通过则抛 HTTPException"""
    from api.services.risk import risk_control

    if uid and risk_control.is_blacklisted(user_id=uid):
        raise HTTPException(status_code=403, detail="账户已被限制，请联系客服")
    if client_ip and risk_control.is_blacklisted(ip=client_ip):
        raise HTTPException(status_code=403, detail="IP已被限制")

    rate_result = risk_control.can_create_order(user_id=uid or "", ip=client_ip)
    if not rate_result["allowed"]:
        raise HTTPException(status_code=429, detail=rate_result["reason"])

    param_check = risk_control.validate_order_params(
        course_count=len(course_ids or []), order_amount=price, username=username,
    )
    if not param_check["valid"]:
        raise HTTPException(status_code=400, detail="; ".join(param_check["errors"]))

    # 价格校验：以后端计算为准，不拒绝订单
    if price > 0:
        from api.routers.pricing import _calculate_package_price_backend
        expected = _calculate_package_price_backend(video_count, 0)
        if abs(price - expected) > 0.01:
            logger.bind(front_price=price, expected=expected).info("单订单价格校正")

    # 课程去重
    if uid:
        for cid in (course_ids or []):
            if not risk_control.can_order_course(user_id=uid, course_id=str(cid)):
                raise HTTPException(status_code=429, detail="该课程24小时内已下单，请勿重复操作")


def retry_order(original: dict, uid: str) -> dict:
    """基于失败订单创建新订单，返回新订单 dict"""
    eligible = ("failed", "cancelled", "amount_mismatch")
    if original["status"] not in eligible:
        raise HTTPException(
            status_code=400,
            detail=f"只有失败/已取消/金额不匹配的订单才能重试，当前状态: {original['status']}",
        )

    course_ids = original.get("course_ids", [])
    if isinstance(course_ids, str):
        try:
            course_ids = json.loads(course_ids) if course_ids else []
        except Exception:
            course_ids = []

    new_order = db.create_order(
        customer_name=original.get("customer_name", ""),
        username=original["username"],
        password=original["password"],
        website_id=original["website_id"],
        task_type=original.get("task_type", "full"),
        course_ids=course_ids,
        user_id=uid,
        inviter_code=original.get("inviter_code"),
        price=original["price"],
        video_count=original.get("video_count", 50),
        exam_count=original.get("exam_count", 0),
    )
    if not new_order or "order_id" not in new_order:
        raise HTTPException(status_code=500, detail="重新创建订单失败")

    db.audit_log("order_retried", order_id=new_order["order_id"],
                 detail=f"来自失败订单 {original.get('order_id')} 的重试")
    return new_order


def compute_batch_price(orders: list, website_prices: Dict[str, float] = None) -> Tuple[float, List[str]]:
    """计算批量订单的后端校验总价（与 /api/pricing/calculate 逻辑一致）。"""
    from api.routers.pricing import _calculate_package_price_backend
    from api.routers.pricing import _get_or_default as _pricing_get

    price_exam_only = _pricing_get("price_exam_only", 5.0)
    price_homework_only = _pricing_get("price_homework_only", 3.0)
    price_chaoxing = _pricing_get("price_chaoxing", 8.0)

    computed_total = 0.0
    detail_lines = []

    for item in orders:
        if item.website_id == 4:
            item_computed = price_chaoxing
        elif item.course_details:
            item_computed = 0.0
            for cd in item.course_details:
                cd_price = _price_single_course(
                    cd, _calculate_package_price_backend, price_exam_only, price_homework_only)
                item_computed += cd_price
        else:
            item_computed = _calculate_package_price_backend(item.video_count, 0)

        item_computed = round(item_computed, 2)
        computed_total += item_computed
        detail_lines.append(f"平台{item.website_id}: 打包定价={item_computed:.2f},前端传={item.price}")

    return round(computed_total, 2), detail_lines


def _price_single_course(cd, calc_video_fn, price_exam: float, price_homework: float) -> float:
    """单门课定价（与 /api/pricing/calculate 的 _detect_course_type 逻辑一致）"""
    has_video = cd.video_total > 0
    video_all_done = has_video and cd.video_completed >= cd.video_total
    has_exam = cd.exam_total > 0 and cd.exam_done < cd.exam_total
    has_homework = cd.homework_total > 0 and cd.homework_done < cd.homework_total

    # 视频全部完成 → 只剩考试/作业时按考试/作业计价；否则仍按视频打包价
    if video_all_done:
        if has_exam and not has_homework:
            return price_exam
        if has_homework and not has_exam:
            return price_homework
        if has_exam and has_homework:
            return max(price_exam, price_homework)
        return calc_video_fn(cd.video_total, cd.video_completed)  # 与前端一致：全部完成仍收视频价

    # 有视频未完成 → 按视频打包价
    if has_video:
        return calc_video_fn(cd.video_total, cd.video_completed)

    # 无视频 → 按考试/作业收费
    if has_exam and not has_homework:
        return price_exam
    if has_homework and not has_exam:
        return price_homework
    if has_exam and has_homework:
        return max(price_exam, price_homework)
    return 0.0


def validate_order_amount(front_total: float, back_total: float, detail_lines: List[str], is_privileged: bool) -> None:
    """校验前后端金额一致性，不一致则抛出异常"""
    from fastapi import HTTPException

    if not is_privileged and abs(front_total - back_total) > 0.015:
        logger.bind(front_total=front_total, back_total=back_total).warning(
            "订单金额异常 details={}", " | ".join(detail_lines))
        raise HTTPException(
            status_code=400,
            detail=f"订单金额异常(前端¥{front_total:.2f}/后端¥{back_total:.2f})，请刷新页面重试",
        )


def submit_free_order(order: dict, username: str, password: str, website_id: int) -> None:
    """免费订单直接入队执行"""
    from api.services.task_queue import get_queue_for_type

    oid = order.get("order_id")
    db.pay_order(oid)

    task_type = order.get("task_type", "full")
    if task_type not in ("video", "exam", "full", "chaoxing_points"):
        task_type = "full"

    q = get_queue_for_type(task_type)
    if q.get_job_by_order_id(oid):
        return

    course_ids = order.get("course_ids", [])
    if isinstance(course_ids, str):
        course_ids = json.loads(course_ids) if course_ids else []

    q.submit_job(
        username=username,
        password=password,
        website_id=website_id,
        job_type=task_type,
        course_ids=course_ids if course_ids else [],
        order_id=oid,
    )
    db.start_order(oid, "")


def enqueue_paid_orders(paid_order_ids: list) -> int:
    """将余额支付成功的订单提交到任务队列，返回成功提交数。"""
    from api.services.task_queue import get_queue_for_type

    submitted = 0
    for oid in paid_order_ids:
        try:
            order = db.get_order(oid)
            if not order or order.get("status") != "paid":
                continue
            task_type = order.get("task_type", "full")
            if task_type not in ("video", "exam", "full", "chaoxing_points"):
                task_type = "full"
            q = get_queue_for_type(task_type)
            if q.get_job_by_order_id(oid):
                continue
            course_ids = order.get("course_ids", [])
            if isinstance(course_ids, str):
                course_ids = json.loads(course_ids) if course_ids else []
            q.submit_job(
                username=order["username"],
                password=order["password"],
                website_id=order["website_id"],
                job_type=task_type,
                course_ids=course_ids if course_ids else [],
                order_id=oid,
            )
            db.start_order(oid, "")
            submitted += 1
        except Exception as e:
            logger.bind(order_id=oid).error("余额支付后提交任务失败 error={}", str(e))
    return submitted

"""佣金服务 — 订单佣金计算与分发"""
from __future__ import annotations

import json

from loguru import logger

from api.database import db



def _distribute_agent_commissions(order: dict, agent: dict) -> None:
    """计算并分发代理三级佣金"""
    from api.services.crack import crack_engine
    from api.services.risk import risk_control

    order_amount = order.get("price", 0)
    parent_agent = db.get_agent(agent.get("parent_agent_id", "")) if agent.get("parent_agent_id") else None
    grandparent_agent = None
    if parent_agent and parent_agent.get("parent_agent_id"):
        grandparent_agent = db.get_agent(parent_agent["parent_agent_id"])

    commissions = crack_engine.calculate_commissions(order_amount, agent, parent_agent, grandparent_agent)
    for c in commissions:
        db.create_commission(
            agent_id=c["agent_id"],
            order_id=order["order_id"],
            user_id=c.get("user_id", "") or order.get("user_id", ""),
            order_amount=order_amount,
            commission_rate=c["rate"],
            commission_amount=c["amount"],
            tier_level=c["level"],
        )
        db.increment_agent_balance(c["agent_id"], c["amount"])
        risk_control.log_audit("commission_distributed", agent_id=c["agent_id"],
                               order_id=order["order_id"],
                               detail=f"第{c['level']}级佣金 ¥{c['amount']}")

    # 更新流水和自动升级
    new_total_flow = (agent.get("total_flow", 0) or 0) + order_amount
    db.update_agent(agent["agent_id"], total_flow=new_total_flow)
    agent["total_flow"] = new_total_flow
    new_level = crack_engine.check_tier_upgrade(agent)
    if new_level:
        db.update_agent(agent["agent_id"], tier_level=new_level)
        db.audit_log("agent_upgraded", agent_id=agent["agent_id"],
                     detail=f"代理升级 L{agent.get('tier_level')}→L{new_level}")


def _distribute_invite_reward(order: dict) -> None:
    """分发邀请人奖励"""
    from api.services.crack import crack_engine
    from infrastructure.redis_client import redis_client

    inviter_code = (order.get("inviter_code") or "").strip()
    if not inviter_code or inviter_code.lstrip("0") == "0000000":
        return

    inviter_agent = db.get_agent_by_referral_code(inviter_code)
    target_uid = inviter_agent.get("user_id", "") if inviter_agent else inviter_code.lstrip("0")

    reward = crack_engine.calculate_user_reward(order.get("price", 0))
    if target_uid:
        db.user_invite_add_reward(target_uid, reward["amount"])
        db.update_user_balance(target_uid, reward["amount"], "invite_reward",
                               note=f"邀请返佣-订单{order['order_id']}",
                               order_id=order["order_id"])
        if redis_client.available:
            try:
                redis_client.zadd("invite:rank:week:latest", {target_uid: reward["amount"]})
            except Exception:
                pass


def _enqueue_paid_order(order_id: str) -> None:
    """已支付订单入队执行"""
    from api.services.task_queue import get_queue_for_type

    full_order = db.get_order(order_id)
    if not full_order or full_order.get("status") != "paid":
        return

    task_type = full_order.get("task_type", "full")
    if task_type not in ("video", "exam", "full", "chaoxing_points"):
        task_type = "full"

    q = get_queue_for_type(task_type)
    if q.get_job_by_order_id(order_id):
        return

    course_ids = full_order.get("course_ids", [])
    if isinstance(course_ids, str):
        course_ids = json.loads(course_ids) if course_ids else []

    q.submit_job(
        username=full_order["username"],
        password=full_order["password"],
        website_id=full_order["website_id"],
        job_type=task_type,
        course_ids=course_ids if course_ids else [],
        order_id=order_id,
    )
    db.start_order(order_id, "")


def process_order_commissions(order: dict, agent: dict = None) -> bool:
    """处理订单佣金分发 + 邀请奖励 + 入队执行。

    Returns:
        True 表示已处理，False 表示已处理过或异常
    """
    from api.services.risk import risk_control

    if order.get("paid") and order.get("commission_status") == "processed":
        return False

    try:
        if agent and agent.get("agent_id"):
            _distribute_agent_commissions(order, agent)

        _distribute_invite_reward(order)
        db.update_order(order["order_id"], commission_status="processed")
        _enqueue_paid_order(order["order_id"])
        return True
    except Exception as e:
        risk_control.log_audit("commission_error", order_id=order.get("order_id", ""), detail=str(e))
        return False

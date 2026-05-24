from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import get_current_sub_admin
from api.database import db
from api.models import ApiResponse
from api.utils import mask_password as _mask_pwd

router = APIRouter(prefix="/api/sub-admin", tags=["合伙人管理"])


class SetTierBody(BaseModel):
    tier_level: int


class SetRateBody(BaseModel):
    commission_rate: float


class UpdateAgentBody(BaseModel):
    display_name: str = ""
    contact: str = ""
    welcome_text: str = ""


def _get_managed_agent_ids(admin: dict) -> list:
    """获取当前合伙人管理的代理 ID 列表"""
    return db.get_managed_agent_ids(admin["user_id"])


def _require_managed_agent(agent_id: str, admin: dict):
    """校验代理是否归当前合伙人管理，不属于则 403"""
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="代理不存在")
    if agent.get("managed_by") != admin["user_id"]:
        raise HTTPException(status_code=403, detail="无权操作该代理")
    return agent


@router.get("/stats", response_model=ApiResponse)
def get_stats(admin: dict = Depends(get_current_sub_admin)):
    agent_ids = _get_managed_agent_ids(admin)
    if not agent_ids:
        return ApiResponse(data={"total_orders": 0, "total_revenue": 0, "by_status": {}, "agent_upgrades": {"revenue": 0, "count": 0}})
    agents = [db.get_agent(aid) for aid in agent_ids]
    agents = [a for a in agents if a]
    total_orders = 0
    total_revenue = 0.0
    by_status = {}
    for a in agents:
        for key in ("total_orders", "total_completed_orders"):
            pass
    # 从代理的推荐码关联的订单统计
    referral_codes = [a["referral_code"] for a in agents if a.get("referral_code")]
    if referral_codes:
        from sqlalchemy import func, select, update, delete
        from sqlalchemy.orm import sessionmaker

        from api.database import Agent, Order, engine
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            code_subquery = select(Agent.referral_code).filter(Agent.agent_id.in_(agent_ids))
            rows = session.execute(
                select(
                    Order.status,
                    func.count(Order.order_id),
                    func.coalesce(func.sum(Order.price), 0),
                ).filter(Order.inviter_code.in_(code_subquery)).group_by(Order.status)
            ).all()
            for status, cnt, rev in rows:
                total_orders += cnt
                total_revenue += rev
                by_status[status] = {"count": cnt, "revenue": float(rev)}
        finally:
            session.close()
    return ApiResponse(data={
        "total_orders": total_orders,
        "total_revenue": float(total_revenue),
        "by_status": by_status,
        "agent_upgrades": {"revenue": 0, "count": 0},
    })


@router.get("/orders", response_model=ApiResponse)
def list_orders(
    status: str = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(get_current_sub_admin),
):
    agent_ids = _get_managed_agent_ids(admin)
    orders = db.list_orders(status=status, limit=limit, offset=offset, agent_ids=agent_ids or None)
    total = db.count_orders(status=status, agent_ids=agent_ids or None)
    return ApiResponse(data={"total": total, "items": [_mask_pwd(o) for o in orders]})


@router.post("/orders/{order_id}/accept", response_model=ApiResponse)
def accept_order(order_id: str, admin: dict = Depends(get_current_sub_admin)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order["status"] != "pending":
        raise HTTPException(status_code=400, detail="当前状态不允许接单")
    db.accept_order(order_id)
    return ApiResponse(message=f"订单 {order_id} 已接单")


@router.post("/orders/{order_id}/complete", response_model=ApiResponse)
def complete_order(order_id: str, admin: dict = Depends(get_current_sub_admin)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order["status"] not in ("running", "accepted"):
        raise HTTPException(status_code=400, detail=f"当前状态 [{order['status']}] 不可标记完成")
    if not db.complete_order(order_id):
        raise HTTPException(status_code=400, detail="状态变更失败，请刷新后重试")
    if order["user_id"]:
        db.increment_user_order_stats(order["user_id"], order["price"])
    try:
        from api.routers.agents import calculate_commission
        calculate_commission(order_id, order.get("user_id"), order.get("price", 0))
    except Exception as e:
        pass
    return ApiResponse(message=f"订单 {order_id} 已标记完成")


@router.post("/orders/{order_id}/fail", response_model=ApiResponse)
def fail_order(order_id: str, admin_note: str = Query(""), admin: dict = Depends(get_current_sub_admin)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order["status"] in ("completed", "cancelled", "failed"):
        raise HTTPException(status_code=400, detail=f"当前状态 [{order['status']}] 不可标记失败")
    if order.get("paid") and order["price"] > 0 and order["user_id"]:
        db.update_user_balance(
            order["user_id"],
            order["price"],
            "order_refund",
            note=f"订单 {order_id} 失败退款",
            order_id=order_id,
        )
    db.fail_order(order_id, error=admin_note or "管理员手动失败")
    if order.get("task_id"):
        from api.services.task_manager import manager as task_manager
        task_manager.cancel_task(order["task_id"])
    return ApiResponse(message=f"订单 {order_id} 已标记失败")


@router.get("/agents", response_model=ApiResponse)
def list_agents(
    status: str = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(get_current_sub_admin),
):
    managed_by = admin["user_id"]
    agents = db.list_agents(status=status, limit=limit, offset=offset, managed_by=managed_by)
    total = db.count_agents(status=status, managed_by=managed_by)
    enriched = []
    for a in agents:
        user = db.get_user(a["user_id"])
        a["username"] = user["username"] if user else "未知"
        a["nickname"] = user["nickname"] if user else ""
        referral_count = db.count_referrals(a["agent_id"])
        a["referral_count"] = referral_count
        enriched.append(a)
    return ApiResponse(data={"total": total, "items": enriched})


@router.get("/commissions", response_model=ApiResponse)
def list_commissions(
    agent_id: str = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(get_current_sub_admin),
):
    agent_ids = _get_managed_agent_ids(admin)
    if agent_id and agent_id not in (agent_ids or []):
        raise HTTPException(status_code=403, detail="无权查看该代理佣金")
    commissions = db.get_commissions(agent_id=agent_id, agent_ids=agent_ids if not agent_id else None, limit=limit, offset=offset)
    total = db.count_commissions(agent_id=agent_id, agent_ids=agent_ids if not agent_id else None)
    return ApiResponse(data={"total": total, "items": commissions})


@router.get("/withdrawals", response_model=ApiResponse)
def list_withdrawals(
    status: str = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(get_current_sub_admin),
):
    agent_ids = _get_managed_agent_ids(admin)
    withdrawals = db.list_all_withdrawals(status=status, limit=limit, offset=offset, agent_ids=agent_ids or None)
    total = db.count_all_withdrawals(status=status, agent_ids=agent_ids or None)
    for w in withdrawals:
        agent = db.get_agent(w.get("agent_id", ""))
        if agent:
            w["agent_display_name"] = agent.get("display_name", "")
            w["wechat_qr"] = agent.get("wechat_qr", "")
        else:
            w["agent_display_name"] = ""
            w["wechat_qr"] = ""
    return ApiResponse(data={"total": total, "items": withdrawals})


@router.post("/withdrawals/{withdrawal_id}/approve", response_model=ApiResponse)
def approve_withdrawal(withdrawal_id: str, admin: dict = Depends(get_current_sub_admin)):
    w = db.get_withdrawal(withdrawal_id)
    if not w:
        raise HTTPException(status_code=404, detail="提现记录不存在")
    _require_managed_agent(w["agent_id"], admin)
    db.update_withdrawal_status(withdrawal_id, "completed")
    return ApiResponse(message="提现已批准")


@router.post("/withdrawals/{withdrawal_id}/reject", response_model=ApiResponse)
def reject_withdrawal(withdrawal_id: str, admin: dict = Depends(get_current_sub_admin)):
    w = db.get_withdrawal(withdrawal_id)
    if not w:
        raise HTTPException(status_code=404, detail="提现记录不存在")
    _require_managed_agent(w["agent_id"], admin)
    db.update_withdrawal_status(withdrawal_id, "rejected")
    return ApiResponse(message="提现已拒绝")


@router.post("/agents/{agent_id}/approve", response_model=ApiResponse)
def approve_agent(agent_id: str, admin: dict = Depends(get_current_sub_admin)):
    agent = _require_managed_agent(agent_id, admin)
    if agent["status"] != "pending":
        raise HTTPException(status_code=400, detail="只能审批待审核的代理")
    db.update_agent(agent_id, status="active")
    return ApiResponse(message="代理已批准")


@router.post("/agents/{agent_id}/suspend", response_model=ApiResponse)
def suspend_agent(agent_id: str, admin: dict = Depends(get_current_sub_admin)):
    _require_managed_agent(agent_id, admin)
    db.update_agent(agent_id, status="suspended")
    return ApiResponse(message="代理已暂停")


@router.post("/agents/{agent_id}/reactivate", response_model=ApiResponse)
def reactivate_agent(agent_id: str, admin: dict = Depends(get_current_sub_admin)):
    _require_managed_agent(agent_id, admin)
    db.update_agent(agent_id, status="active")
    return ApiResponse(message="代理已恢复")


@router.put("/agents/{agent_id}/tier", response_model=ApiResponse)
def set_agent_tier(agent_id: str, body: SetTierBody, admin: dict = Depends(get_current_sub_admin)):
    if body.tier_level < 1 or body.tier_level > 3:
        raise HTTPException(status_code=400, detail="代理等级范围: 1-3")
    _require_managed_agent(agent_id, admin)
    db.update_agent(agent_id, tier_level=body.tier_level)
    return ApiResponse(message=f"代理等级已更新为 L{body.tier_level}")


@router.put("/agents/{agent_id}/commission-rate", response_model=ApiResponse)
def set_agent_commission_rate(agent_id: str, body: SetRateBody, admin: dict = Depends(get_current_sub_admin)):
    if body.commission_rate < 0 or body.commission_rate > 0.5:
        raise HTTPException(status_code=400, detail="佣金比例范围: 0% - 50%")
    _require_managed_agent(agent_id, admin)
    db.update_agent(agent_id, flow_commission_rate=body.commission_rate)
    return ApiResponse(message=f"佣金比例已更新为 {body.commission_rate * 100:.0f}%")


@router.put("/agents/{agent_id}/info", response_model=ApiResponse)
def update_agent_info(agent_id: str, body: UpdateAgentBody, admin: dict = Depends(get_current_sub_admin)):
    _require_managed_agent(agent_id, admin)
    updates = {}
    if body.display_name:
        updates["display_name"] = body.display_name
    if body.contact:
        updates["contact"] = body.contact
    if body.welcome_text:
        updates["welcome_text"] = body.welcome_text
    if updates:
        db.update_agent(agent_id, **updates)
    return ApiResponse(message="代理信息已更新")

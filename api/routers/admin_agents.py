from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import get_current_admin
from api.database import db
from api.models import ApiResponse

router = APIRouter(prefix="/api/admin/agents", tags=["管理-代理"])


class AdminSetRateRequest(BaseModel):
    rate: float = Field(ge=0, le=0.5)


@router.get("/", response_model=ApiResponse)
def admin_list_agents(
    status: str = None,
    limit: int = 50,
    offset: int = 0,
    admin: dict = Depends(get_current_admin),
):
    agents = db.list_agents(status=status, limit=limit, offset=offset)
    total = db.count_agents(status=status)
    enriched = []
    for a in agents:
        user = db.get_user(a["user_id"])
        a["username"] = user["username"] if user else "未知"
        a["nickname"] = user["nickname"] if user else ""
        referral_count = db.count_referrals(a["agent_id"])
        a["referral_count"] = referral_count
        enriched.append(a)
    return ApiResponse(data={"total": total, "items": enriched})


@router.get("/stats", response_model=ApiResponse)
def admin_agent_stats(admin: dict = Depends(get_current_admin)):
    stats = db.get_agent_stats()
    return ApiResponse(data=stats)


@router.post("/{agent_id}/approve", response_model=ApiResponse)
def approve_agent(agent_id: str, admin: dict = Depends(get_current_admin)):
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="代理不存在")
    if agent["status"] == "active":
        return ApiResponse(message="代理已经是激活状态")
    db.update_agent(agent_id, status="active")
    return ApiResponse(message=f"代理 {agent_id} 已审核通过")


@router.post("/{agent_id}/suspend", response_model=ApiResponse)
def suspend_agent(agent_id: str, admin: dict = Depends(get_current_admin)):
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="代理不存在")
    db.update_agent(agent_id, status="suspended")
    return ApiResponse(message=f"代理 {agent_id} 已暂停")


@router.post("/{agent_id}/reactivate", response_model=ApiResponse)
def reactivate_agent(agent_id: str, admin: dict = Depends(get_current_admin)):
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="代理不存在")
    db.update_agent(agent_id, status="active")
    return ApiResponse(message=f"代理 {agent_id} 已重新激活")


@router.post("/{agent_id}/rate", response_model=ApiResponse)
def set_commission_rate(
    agent_id: str,
    body: AdminSetRateRequest,
    admin: dict = Depends(get_current_admin),
):
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="代理不存在")
    db.update_agent(agent_id, flow_commission_rate=body.rate)
    return ApiResponse(message=f"佣金比例已设置为 {body.rate*100}%")


@router.get("/commissions", response_model=ApiResponse)
def admin_list_commissions(
    agent_id: str = None,
    limit: int = 50,
    offset: int = 0,
    admin: dict = Depends(get_current_admin),
):
    commissions = db.get_commissions(agent_id=agent_id, limit=limit, offset=offset)
    total = db.count_commissions(agent_id=agent_id)
    return ApiResponse(data={"total": total, "items": commissions})


@router.post("/commissions/clear", response_model=ApiResponse)
def admin_clear_commissions(admin: dict = Depends(get_current_admin)):
    count = db.clear_commissions()
    return ApiResponse(message=f"已清除 {count} 条佣金记录")


@router.get("/withdrawals", response_model=ApiResponse)
def admin_list_withdrawals(
    status: str = None,
    limit: int = 50,
    offset: int = 0,
    admin: dict = Depends(get_current_admin),
):
    withdrawals = db.list_all_withdrawals(status=status, limit=limit, offset=offset)
    total = db.count_all_withdrawals(status=status)
    for w in withdrawals:
        agent = db.get_agent(w["agent_id"])
        w["agent_name"] = agent.get("display_name") or agent.get("referral_code") if agent else ""
    return ApiResponse(data={"total": total, "items": withdrawals})


@router.post("/withdrawals/clear", response_model=ApiResponse)
def admin_clear_withdrawals(admin: dict = Depends(get_current_admin)):
    count = db.clear_withdrawals()
    return ApiResponse(message=f"已清除 {count} 条提现记录")


@router.post("/withdrawals/{withdrawal_id}/approve", response_model=ApiResponse)
def admin_approve_withdrawal(
    withdrawal_id: str,
    admin: dict = Depends(get_current_admin),
):
    w = db.get_withdrawal(withdrawal_id)
    if not w:
        raise HTTPException(status_code=404, detail="提现记录不存在")
    if w["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"当前状态 [{w['status']}] 不可审核")
    db.update_withdrawal_status(withdrawal_id, "completed", "管理员审核通过")
    return ApiResponse(message=f"提现 {withdrawal_id} 已通过")


@router.post("/withdrawals/{withdrawal_id}/reject", response_model=ApiResponse)
def admin_reject_withdrawal(
    withdrawal_id: str,
    admin: dict = Depends(get_current_admin),
):
    w = db.get_withdrawal(withdrawal_id)
    if not w:
        raise HTTPException(status_code=404, detail="提现记录不存在")
    if w["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"当前状态 [{w['status']}] 不可审核")
    db.update_withdrawal_status(withdrawal_id, "rejected", "管理员拒绝")
    return ApiResponse(message=f"提现 {withdrawal_id} 已拒绝，金额已退回")


class WithdrawRulesUpdate(BaseModel):
    min_amount: Optional[float] = None
    max_daily_count: Optional[int] = None
    max_daily_amount: Optional[float] = None
    fee_rate: Optional[float] = None
    fee_fixed: Optional[float] = None
    settlement_cycle: Optional[str] = None
    auto_approve_max: Optional[float] = None
    presets: Optional[str] = None


@router.get("/withdraw-rules", response_model=ApiResponse)
def admin_get_withdraw_rules(admin: dict = Depends(get_current_admin)):
    rules = db.get_withdraw_rules()
    return ApiResponse(data=rules)


@router.put("/withdraw-rules", response_model=ApiResponse)
def admin_set_withdraw_rules(body: WithdrawRulesUpdate, admin: dict = Depends(get_current_admin)):
    field_map = {
        "min_amount": "withdraw_min_amount",
        "max_daily_count": "withdraw_max_daily_count",
        "max_daily_amount": "withdraw_max_daily_amount",
        "fee_rate": "withdraw_fee_rate",
        "fee_fixed": "withdraw_fee_fixed",
        "settlement_cycle": "withdraw_settlement_cycle",
        "auto_approve_max": "withdraw_auto_approve_max",
        "presets": "withdraw_presets",
    }
    for field, db_key in field_map.items():
        val = getattr(body, field, None)
        if val is not None:
            db.set_platform_setting(db_key, str(val))

    rules = db.get_withdraw_rules()
    return ApiResponse(message="提现规则已更新", data=rules)

import base64
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import get_current_user, get_optional_user
from api.database import db
from api.models import ApiResponse

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")


from api.utils import generate_referral_code as _generate_referral_code
from api.utils import generate_slug as _generate_slug


class AgentProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=50)
    wechat_qr: Optional[str] = Field(default=None, max_length=500)


class QrUploadRequest(BaseModel):
    image: str = Field(..., max_length=1_000_000)  # base64 data URI


class WithdrawRequest(BaseModel):
    amount: float = Field(gt=0)


router = APIRouter(prefix="/api/agents", tags=["代理分销"])


_AGENT_SENSITIVE_FIELDS = {"user_id", "parent_agent_id", "subdomain_slug"}

def sanitize_agent(agent: dict) -> dict:
    return {k: v for k, v in agent.items() if k not in _AGENT_SENSITIVE_FIELDS}


class ApplyAgentRequest(BaseModel):
    pay_type: int = Field(default=2, ge=1, le=2, description="支付方式 1=微信 2=支付宝")


@router.post("/apply", response_model=ApiResponse)
def apply_agent(body: ApplyAgentRequest = ApplyAgentRequest(), current_user: dict = Depends(get_current_user)):
    from api.services.agent_service import register_agent
    result = register_agent(current_user["user_id"], current_user.get("username", ""), body.pay_type)

    if result.get("already_agent"):
        return ApiResponse(message="你已经是代理", data=result["agent"])
    if result.get("need_pay"):
        return ApiResponse(data=result)
    return ApiResponse(message="注册成功，代理已开通！", data=result.get("agent"))


@router.get("/me", response_model=ApiResponse)
def get_my_agent(current_user: dict = Depends(get_current_user)):
    agent = db.get_agent_by_user_id(current_user["user_id"])
    if not agent:
        return ApiResponse(data=None, message="你还不是代理")
    return ApiResponse(data=sanitize_agent(agent))


@router.get("/profile", response_model=ApiResponse)
def get_agent_profile(current_user: dict = Depends(get_current_user)):
    agent = db.get_agent_by_user_id(current_user["user_id"])
    if not agent:
        raise HTTPException(status_code=404, detail="你还不是代理，请先申请")

    earnings = db.get_agent_earnings(agent["agent_id"])
    referral_count = db.count_referrals(agent["agent_id"])
    agent["referral_count"] = referral_count
    agent.update(earnings)
    return ApiResponse(data=sanitize_agent(agent))


@router.put("/profile", response_model=ApiResponse)
def update_agent_profile(
    body: AgentProfileUpdate,
    current_user: dict = Depends(get_current_user),
):
    agent = db.get_agent_by_user_id(current_user["user_id"])
    if not agent:
        raise HTTPException(status_code=404, detail="你还不是代理")
    if agent["status"] != "active":
        raise HTTPException(status_code=403, detail=f"代理状态: {agent['status']}")

    fields = {}
    if body.display_name is not None:
        fields["display_name"] = body.display_name
    if body.wechat_qr is not None:
        fields["wechat_qr"] = body.wechat_qr

    if fields:
        db.update_agent(agent["agent_id"], **fields)
    agent = db.get_agent(agent["agent_id"])
    return ApiResponse(message="资料已更新", data=agent)


@router.post("/upload-qr-base64", response_model=ApiResponse)
def upload_qr_base64(
    body: QrUploadRequest,
    current_user: dict = Depends(get_current_user),
):
    agent = db.get_agent_by_user_id(current_user["user_id"])
    if not agent:
        raise HTTPException(status_code=404, detail="你还不是代理")

    data_uri = body.image
    if "," not in data_uri:
        raise HTTPException(status_code=400, detail="图片格式无效")

    header, encoded = data_uri.split(",", 1)
    ext = "png"
    if "jpeg" in header or "jpg" in header:
        ext = "jpg"
    elif "webp" in header:
        ext = "webp"
    elif "gif" in header:
        ext = "gif"

    try:
        img_bytes = base64.b64decode(encoded)
    except Exception as e:
        raise HTTPException(status_code=400, detail="图片数据无效")

    if len(img_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片大小不能超过5MB")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = f"qr_{agent['agent_id']}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(img_bytes)

    url_path = f"/uploads/{filename}"
    db.update_agent(agent["agent_id"], wechat_qr=url_path)
    return ApiResponse(message="二维码上传成功", data={"url": url_path})


@router.get("/dashboard", response_model=ApiResponse)
def get_agent_dashboard(current_user: dict = Depends(get_current_user)):
    agent = db.get_agent_by_user_id(current_user["user_id"])
    if not agent:
        raise HTTPException(status_code=404, detail="你还不是代理")

    earnings = db.get_agent_earnings(agent["agent_id"])
    referral_count = db.count_referrals(agent["agent_id"])
    recent_commissions = db.get_commissions(agent_id=agent["agent_id"], limit=10)
    recent_referrals = db.list_referrals(agent["agent_id"], limit=10)
    recent_withdrawals = db.get_withdrawals(agent["agent_id"], limit=10)

    return ApiResponse(data={
        "agent": sanitize_agent(agent),
        "earnings": earnings,
        "referral_count": referral_count,
        "referral_link": f"/#/agent?ref={agent['referral_code']}",
        "subsite_link": f"/#/subsite/{agent.get('subdomain_slug', '')}" if agent.get('subdomain_slug') else "",
        "recent_commissions": recent_commissions,
        "recent_referrals": recent_referrals,
        "recent_withdrawals": recent_withdrawals,
    })


@router.get("/link", response_model=ApiResponse)
def get_referral_link(current_user: dict = Depends(get_current_user)):
    agent = db.get_agent_by_user_id(current_user["user_id"])
    if not agent:
        raise HTTPException(status_code=404, detail="你还不是代理")
    return ApiResponse(data={
        "referral_code": agent["referral_code"],
        "referral_link": f"/#/agent?ref={agent['referral_code']}",
        "subdomain_slug": agent.get("subdomain_slug", ""),
        "subsite_link": f"/#/subsite/{agent.get('subdomain_slug', '')}" if agent.get("subdomain_slug") else "",
    })


@router.get("/referrals", response_model=ApiResponse)
def list_my_referrals(
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    agent = db.get_agent_by_user_id(current_user["user_id"])
    if not agent:
        raise HTTPException(status_code=404, detail="你还不是代理")

    referrals = db.list_referrals(agent["agent_id"], limit=limit, offset=offset)
    total = db.count_referrals(agent["agent_id"])
    return ApiResponse(data={"total": total, "items": referrals})


@router.get("/commissions", response_model=ApiResponse)
def list_my_commissions(
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    agent = db.get_agent_by_user_id(current_user["user_id"])
    if not agent:
        raise HTTPException(status_code=404, detail="你还不是代理")

    commissions = db.get_commissions(agent_id=agent["agent_id"], limit=limit, offset=offset)
    total = db.count_commissions(agent_id=agent["agent_id"])
    return ApiResponse(data={"total": total, "items": commissions})


@router.get("/withdrawals", response_model=ApiResponse)
def list_my_withdrawals(
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    agent = db.get_agent_by_user_id(current_user["user_id"])
    if not agent:
        raise HTTPException(status_code=404, detail="你还不是代理")

    withdrawals = db.get_withdrawals(agent["agent_id"], limit=limit, offset=offset)
    total = db.count_withdrawals(agent["agent_id"])
    return ApiResponse(data={"total": total, "items": withdrawals})


@router.post("/withdraw", response_model=ApiResponse)
def request_withdrawal(
    body: WithdrawRequest,
    current_user: dict = Depends(get_current_user),
):
    from api.services.agent_service import validate_withdrawal
    agent = db.get_agent_by_user_id(current_user["user_id"])
    if not agent:
        raise HTTPException(status_code=404, detail="你还不是代理")

    info = validate_withdrawal(agent, body.amount)
    result = db.withdraw_agent_balance(agent["agent_id"], info["amount"], info["fee"])
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    fee_text = f"（扣除手续费 ¥{info['fee']:.2f}，实际到账 ¥{info['actual_amount']:.2f}）" if info["fee"] > 0 else ""
    return ApiResponse(message=f"提现申请已提交 ¥{info['amount']:.2f}{fee_text}")


@router.get("/withdraw-rules", response_model=ApiResponse)
def get_withdraw_rules(current_user: dict = Depends(get_current_user)):
    agent = db.get_agent_by_user_id(current_user["user_id"])
    if not agent:
        raise HTTPException(status_code=404, detail="你还不是代理")
    rules = db.get_withdraw_rules()
    today_stats = db.agent_withdraw_stats_today(agent["agent_id"])
    return ApiResponse(data={
        **rules,
        "available_balance": agent["available_balance"],
        "frozen_balance": agent.get("frozen_balance", 0),
        "today_count": today_stats["count"],
        "today_total": today_stats["total"],
        "today_remaining_count": max(0, rules["max_daily_count"] - today_stats["count"]) if rules["max_daily_count"] > 0 else None,
        "today_remaining_amount": max(0, rules["max_daily_amount"] - today_stats["total"]) if rules["max_daily_amount"] > 0 else None,
    })


def calculate_commission(order_id: str, user_id: str, order_amount: float):
    if order_amount <= 0:
        return

    # 原子抢占，防止重复发放佣金
    if not db.claim_commission(order_id):
        return

    try:
        order = db.get_order(order_id)
        if not order:
            return
        user = db.get_user(user_id)
        agent = None

        if user and user.get("referred_by"):
            agent = db.get_agent(user["referred_by"])
        if not agent and order.get("inviter_code"):
            agent = db.get_agent_by_referral_code(order["inviter_code"])

        if not agent or agent["status"] != "active":
            return

        from api.services.crack import crack_engine
        parent_agent = db.get_agent(agent.get("parent_agent_id", "")) if agent.get("parent_agent_id") else None
        commissions = crack_engine.calculate_commissions(order_amount, agent, parent_agent, None)
        for c in commissions:
            db.create_commission(
                agent_id=c["agent_id"],
                order_id=order_id,
                user_id=user_id,
                order_amount=order_amount,
                commission_rate=c["rate"],
                commission_amount=c["amount"],
                tier_level=c["level"],
            )
            db.increment_agent_balance(c["agent_id"], c["amount"])

        db.mark_commission_done(order_id)
    except Exception as e:
        # 失败时回滚状态，允许重试
        db.update_order(order_id, commission_status="unprocessed")
        raise


@router.get("/subsite/{slug}", response_model=ApiResponse)
def get_subsite_info(slug: str):
    agent = db.get_agent_by_subdomain(slug)
    if not agent:
        raise HTTPException(status_code=404, detail="代理不存在")
    user = db.get_user(agent["user_id"])
    return ApiResponse(data={
        "agent_id": agent["agent_id"],
        "display_name": agent.get("display_name") or (user["nickname"] if user else ""),
        "welcome_text": agent.get("welcome_text", ""),
        "wechat_qr": agent.get("wechat_qr", ""),
        "referral_code": agent["referral_code"],
    })


@router.get("/child-agents", response_model=ApiResponse)
def get_child_agents(current_user: dict = Depends(get_optional_user)):
    uid = current_user["user_id"]
    if uid == "guest":
        raise HTTPException(status_code=401, detail="请先登录")
    agent = db.get_agent_by_user_id(uid)
    if not agent:
        return ApiResponse(data=[])
    children = db.get_child_agents(agent["agent_id"])
    return ApiResponse(data=children)


class UpgradeRequest(BaseModel):
    target_tier: int = Field(ge=2, le=3, description="目标等级 (2或3)")
    pay_type: int = Field(default=1, description="支付方式 1=微信 2=支付宝")


@router.get("/upgrade-info", response_model=ApiResponse)
def get_upgrade_info(current_user: dict = Depends(get_current_user)):
    agent = db.get_agent_by_user_id(current_user["user_id"])
    if not agent:
        raise HTTPException(status_code=404, detail="你还不是代理")
    if agent["status"] != "active":
        raise HTTPException(status_code=403, detail=f"代理状态: {agent['status']}")
    current_tier = agent.get("tier_level", 1)
    if current_tier >= 3:
        return ApiResponse(data={"current_tier": 3, "upgradable": False, "message": "已是最顶级"})

    upgrade_enabled = db.config_get("agent_upgrade_fee_enabled") == "true"
    l2_fee = float(db.config_get("agent_upgrade_l2_fee") or 200)
    l3_fee = float(db.config_get("agent_upgrade_l3_fee") or 300)

    options = []
    if current_tier < 2:
        options.append({"tier": 2, "fee": l2_fee, "label": f"L{current_tier} → L2", "enabled": upgrade_enabled})
    elif current_tier < 3:
        options.append({"tier": 3, "fee": l3_fee, "label": f"L{current_tier} → L3", "enabled": upgrade_enabled})

    return ApiResponse(data={
        "current_tier": current_tier,
        "upgradable": bool(options),
        "upgrade_enabled": upgrade_enabled,
        "options": options,
    })


@router.post("/request-upgrade", response_model=ApiResponse)
def request_upgrade(body: UpgradeRequest, current_user: dict = Depends(get_current_user)):
    from api.services.agent_service import create_payment_order, validate_upgrade
    agent = db.get_agent_by_user_id(current_user["user_id"])
    if not agent:
        raise HTTPException(status_code=404, detail="你还不是代理")

    fee = validate_upgrade(agent, body.target_tier)
    pay_id = f"AGENTUP-{agent['agent_id']}-L{body.target_tier}-{uuid.uuid4().hex[:6]}"
    payment = create_payment_order(body.pay_type, fee, pay_id, f"代理升级-L{body.target_tier}")
    payment["target_tier"] = body.target_tier
    payment["submit_url"] = payment["pay_url"]
    return ApiResponse(data=payment)

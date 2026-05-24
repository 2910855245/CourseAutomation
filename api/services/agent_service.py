"""代理服务 — 注册、升级、提现的业务逻辑"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from loguru import logger
from fastapi import HTTPException

from api.database import db



def create_payment_order(pay_type: int, price: float, pay_id: str, name: str) -> dict:
    """创建 YPay 支付订单，返回支付信息 dict。失败抛 HTTPException。"""
    from api.services.ypay_service import ypay
    from api.utils import get_site_url, make_qr_base64, retry

    site_url = get_site_url()

    @retry(max_attempts=2, delay=0.5, exceptions=(ConnectionError, TimeoutError, OSError))
    def _create():
        return ypay.create_order(
            pay_type=pay_type, price=price, out_trade_no=pay_id,
            name=name, notify_url=f"{site_url}/api/payment/notify",
            return_url=f"{site_url}/#/agent", ip="", floating=False,
        )

    try:
        result = _create()
    except Exception as e:
        logger.error(f"create_payment_order_error error={str(e)} pay_type={pay_type}")
        raise HTTPException(status_code=500, detail=f"创建支付失败: {str(e)}")

    if not result:
        channel = db.ypay_pick_channel(pay_type)
        if not channel:
            type_name = {1: "微信", 2: "支付宝"}.get(pay_type, "未知")
            raise HTTPException(status_code=500, detail=f"未配置{type_name}收款通道，请在后台管理中添加")
        raise HTTPException(status_code=500, detail="创建支付失败，请检查收款码配置是否正确")

    trade_no = result.get("trade_no", "")
    pay_link = result.get("qrcode", "")
    pay_url = ypay.build_pay_url(trade_no)
    qr_image = make_qr_base64(pay_link) if pay_link else make_qr_base64(pay_url)

    return {
        "trade_no": trade_no,
        "pay_id": pay_id,
        "fee": price,
        "qr_image": qr_image,
        "pay_url": pay_url,
        "pay_link": pay_link,
        "h5_qrurl": result.get("h5_qrurl", ""),
    }


def register_agent(uid: str, username: str, pay_type: int = 2) -> Optional[Dict[str, Any]]:
    """注册代理。需要付费时返回支付信息 dict，否则返回 None（已直接创建）。"""
    existing = db.get_agent_by_user_id(uid)
    if existing:
        return {"already_agent": True, "agent": existing}

    registration_enabled = db.config_get("agent_registration_fee_enabled") == "true"
    if registration_enabled:
        fee = float(db.config_get("agent_registration_fee") or 9.9)
        if fee > 0:
            pay_id = f"AGENTREG-{uid}-{uuid.uuid4().hex[:6]}"
            payment = create_payment_order(pay_type, fee, pay_id, f"代理注册费 - {username}")
            payment["need_pay"] = True
            return payment

    # 免费注册
    user = db.get_user(uid)
    parent_agent_id = ""
    grandparent_agent_id = ""
    if user and user.get("referred_by"):
        parent = db.get_agent(user["referred_by"])
        if parent and parent["status"] == "active":
            parent_agent_id = parent["agent_id"]
            grandparent_agent_id = parent.get("parent_agent_id", "")

    from api.routers.agents import _generate_referral_code, _generate_slug
    referral_code = _generate_referral_code()
    subdomain_slug = _generate_slug()
    agent = db.create_agent(
        user_id=uid, referral_code=referral_code,
        parent_agent_id=parent_agent_id, grandparent_agent_id=grandparent_agent_id,
        tier_level=1, subdomain_slug=subdomain_slug,
    )
    if parent_agent_id:
        parent = db.get_agent(parent_agent_id)
        if parent:
            db.update_agent(parent_agent_id, invite_count=(parent.get("invite_count") or 0) + 1)

    return {"created": True, "agent": agent}


def validate_upgrade(agent: dict, target_tier: int) -> float:
    """校验升级条件，返回升级费用。不通过抛 HTTPException。"""
    if agent["status"] != "active":
        raise HTTPException(status_code=403, detail=f"代理状态: {agent['status']}")
    current_tier = agent.get("tier_level", 1)
    if target_tier <= current_tier:
        raise HTTPException(status_code=400, detail="目标等级必须高于当前等级")

    upgrade_enabled = db.config_get("agent_upgrade_fee_enabled") == "true"
    if not upgrade_enabled:
        raise HTTPException(status_code=400, detail="付费升级暂未开放")

    if target_tier == 2:
        fee = float(db.config_get("agent_upgrade_l2_fee") or 200)
    else:
        fee = float(db.config_get("agent_upgrade_l3_fee") or 300)

    if fee <= 0:
        raise HTTPException(status_code=400, detail="升级费用配置异常")
    return fee


def handle_agent_registration(pay_id: str) -> str:
    """代理注册付费回调: AGENTREG-{uid}-{uuid}。返回 "success" 或 "fail"。"""
    try:
        inner = pay_id[len("AGENTREG-"):]
        last_hyphen = inner.rfind("-")
        uid = inner[:last_hyphen]
        if db.get_agent_by_user_id(uid):
            return "success"
        user = db.get_user(uid)
        parent_agent_id = ""
        grandparent_agent_id = ""
        if user and user.get("referred_by"):
            parent = db.get_agent(user["referred_by"])
            if parent and parent["status"] == "active":
                parent_agent_id = parent["agent_id"]
                grandparent_agent_id = parent.get("parent_agent_id", "")
        from api.utils import generate_referral_code, generate_slug
        db.create_agent(user_id=uid, referral_code=generate_referral_code(),
                        parent_agent_id=parent_agent_id,
                        grandparent_agent_id=grandparent_agent_id,
                        tier_level=1, subdomain_slug=generate_slug())
        if parent_agent_id:
            parent = db.get_agent(parent_agent_id)
            if parent:
                db.update_agent(parent_agent_id, invite_count=(parent.get("invite_count") or 0) + 1)
        logger.info(f"agent_registration_paid user_id={uid}")
        return "success"
    except Exception as e:
        logger.error(f"agent_registration_failed error={str(e)}")
        return "fail"


def handle_agent_upgrade(pay_id: str, price: str, really_price: str) -> str:
    """代理升级付费回调: AGENTUP-{agent_id}-L{target}-{uuid}。返回 "success" 或 "fail"。"""
    try:
        inner = pay_id[len("AGENTUP-"):]
        last_hyphen = inner.rfind("-")
        second_last = inner.rfind("-", 0, last_hyphen)
        agent_id = inner[:second_last]
        target_tier = int(inner[second_last + 1:last_hyphen].replace("L", ""))

        agent = db.get_agent(agent_id)
        if not agent:
            logger.warning(f"agent_upgrade_agent_not_found agent_id={agent_id}")
            return "fail"

        ypay_order = db.ypay_get_order_by_out_trade_no(pay_id)
        if ypay_order and ypay_order.get("status") != 1:
            db.ypay_mark_paid(ypay_order["trade_no"])

        if agent.get("tier_level", 0) >= target_tier:
            return "success"

        db.update_agent(agent_id, tier_level=target_tier)
        db.audit_log("agent_upgrade_paid", agent_id=agent_id,
                     detail=f"付费升级 L{agent.get('tier_level')}->L{target_tier} 实付{really_price}")
        logger.info(f"agent_upgraded_via_payment agent_id={agent_id} new_tier={target_tier}")
        return "success"
    except Exception as e:
        logger.error(f"agent_upgrade_handler_error error={str(e)}")
        return "fail"


def validate_withdrawal(agent: dict, amount: float) -> Dict[str, Any]:
    """校验提现条件，返回 {amount, fee, actual_amount}。不通过抛 HTTPException。"""
    if agent["status"] != "active":
        raise HTTPException(status_code=403, detail=f"代理状态: {agent['status']}")

    rules = db.get_withdraw_rules()
    amount = round(amount, 2)

    if amount < rules["min_amount"]:
        raise HTTPException(status_code=400,
                            detail=f"单笔最低提现金额为 ¥{rules['min_amount']:.0f}，当前输入 ¥{amount:.2f}")

    presets = rules.get("presets", "").strip()
    if presets:
        preset_list = [float(x.strip()) for x in presets.split(",") if x.strip()]
        if preset_list and amount not in preset_list:
            raise HTTPException(status_code=400, detail=f"请选择预设提现金额: {presets}")

    if amount > agent["available_balance"]:
        raise HTTPException(status_code=400,
                            detail=f"可提现余额不足，当前可提现: ¥{agent['available_balance']:.2f}")

    today_stats = db.agent_withdraw_stats_today(agent["agent_id"])
    if rules["max_daily_count"] > 0 and today_stats["count"] >= rules["max_daily_count"]:
        raise HTTPException(status_code=400,
                            detail=f"今日提现次数已达上限（{rules['max_daily_count']}次/天），请明天再试")
    if rules["max_daily_amount"] > 0 and today_stats["total"] + amount > rules["max_daily_amount"]:
        raise HTTPException(status_code=400,
                            detail=f"今日累计提现已达上限（¥{rules['max_daily_amount']:.0f}/天），当前已提 ¥{today_stats['total']:.2f}")

    fee = 0.0
    if rules["fee_rate"] > 0:
        fee = round(amount * rules["fee_rate"], 2)
    if rules["fee_fixed"] > 0:
        fee = rules["fee_fixed"]
    actual_amount = round(amount - fee, 2)

    if amount + fee > agent["available_balance"]:
        raise HTTPException(status_code=400,
                            detail=f"余额不足以支付手续费，提现金额+手续费共 ¥{amount + fee:.2f}")

    return {"amount": amount, "fee": fee, "actual_amount": actual_amount}

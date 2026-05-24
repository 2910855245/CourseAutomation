import json
import uuid
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from api.auth import get_optional_user
from api.database import db
from api.models import ApiResponse
from api.redis_client import redis_client
from api.services.crack import crack_engine
from api.services.risk import risk_control
from api.services.ypay_service import ypay
from config import settings

router = APIRouter(prefix="/api/payment", tags=["支付"])


def _process_order_commissions(order: dict, agent: dict = None) -> bool:
    from api.services.commission_service import process_order_commissions
    return process_order_commissions(order, agent)


def _handle_agent_registration(pay_id: str) -> str:
    from api.services.agent_service import handle_agent_registration
    return handle_agent_registration(pay_id)


def _handle_agent_upgrade(pay_id: str, price: str, really_price: str) -> str:
    from api.services.agent_service import handle_agent_upgrade
    return handle_agent_upgrade(pay_id, price, really_price)


class PaymentCreateRequest(BaseModel):
    order_id: str
    pay_type: int = 1


@router.post("/create")
def payment_create(payload: PaymentCreateRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_optional_user)):
    # 游客可创建支付，但记录 IP 便于审计
    order = db.get_order(payload.order_id)
    if not order:
        return {"code": 404, "message": "订单不存在"}
    if order["paid"]:
        return {"code": 400, "message": "订单已支付"}

    site_url = _get_site_url()
    result = ypay.create_order(
        pay_type=payload.pay_type,
        price=order["price"],
        out_trade_no=payload.order_id,
        name=f"网课代刷-{order.get('username', '')}",
        notify_url=f"{site_url}/api/payment/notify",
        return_url=f"{site_url}/#/orders",
        ip="",
        floating=True,
    )

    if not result:
        return {"code": -1, "message": "创建支付订单失败，请检查收款通道是否在线"}

    trade_no = result["trade_no"]
    pay_link = result.get("qrcode", "")
    pay_url = ypay.build_pay_url(trade_no)
    qr_image = _make_qr_base64(pay_link) if pay_link else _make_qr_base64(pay_url)

    db.update_order(payload.order_id, out_trade_no=trade_no)
    background_tasks.add_task(
        db.audit_log, "payment_created", order_id=payload.order_id,
        detail=f"YPay支付订单:{trade_no} 金额:{order['price']}")

    return {
        "code": 0,
        "data": {
            "mode": "ypay",
            "trade_no": trade_no,
            "out_trade_no": payload.order_id,
            "order_id": payload.order_id,
            "pay_url": pay_url,
            "pay_link": pay_link,
            "price": order["price"],
            "really_price": result["truemoney"],
            "pay_type": payload.pay_type,
            "qr_image": qr_image,
            "h5_qrurl": result.get("h5_qrurl", ""),
        },
    }


@router.post("/notify", response_class=PlainTextResponse)
async def payment_notify(request: Request):
    try:
        body = await request.form()
        params = {k: str(v) for k, v in body.items() if v is not None}
    except Exception as e:
        return "fail"

    # Run blocking DB operations in a thread to avoid blocking the event loop
    import asyncio
    return await asyncio.to_thread(_payment_notify_sync, params)


def _payment_notify_sync(params: dict) -> str:
    pay_id = params.get("payId", "")
    param = params.get("param", "")
    pay_type = params.get("type", "")
    price = params.get("price", "")
    really_price = params.get("reallyPrice", "")
    sign = params.get("sign", "")

    if not pay_id or not sign:
        return "fail"

    if not ypay.verify_callback_sign(pay_id, param, pay_type, price, really_price, sign):
        return "fail"

    if pay_id.startswith("AGENTREG-"):
        return _handle_agent_registration(pay_id)
    if pay_id.startswith("AGENTUP-"):
        return _handle_agent_upgrade(pay_id, price, really_price)

    trade_no = pay_id if pay_id and pay_id.startswith("Y") else param
    ypay_order = db.ypay_get_order(trade_no)
    if not ypay_order:
        ypay_order = db.ypay_get_order_by_out_trade_no(param)

    if not ypay_order:
        # 签名已验证但订单不存在，返回 success 防止 YPay 无限重试
        return "success"

    trade_no = ypay_order["trade_no"]

    if ypay_order["status"] != 1:
        db.ypay_mark_paid(trade_no)

    order_id = ypay_order.get("out_trade_no", trade_no)
    order = db.get_order(order_id)
    if not order:
        # 签名已验证，返回 success 防止无限重试
        return "success"
    if order.get("commission_status") == "processed":
        return "success"

    if not db.claim_commission(order_id):
        return "success"

    channel_name = {"1": "wechat", "2": "alipay", "3": "lkl"}.get(pay_type, "unknown")
    db.confirm_payment(order_id, payment_trade_no=trade_no, payment_channel=channel_name)

    fresh_order = db.get_order(order_id)
    agent = None
    if fresh_order and fresh_order.get("user_id"):
        user = db.get_user(fresh_order["user_id"])
        if user and user.get("referred_by"):
            agent = db.get_agent(user["referred_by"])
    if not agent and fresh_order and fresh_order.get("inviter_code"):
        agent = db.get_agent_by_referral_code(fresh_order["inviter_code"])
    _process_order_commissions(fresh_order, agent=agent)
    db.mark_commission_done(order_id)

    db.audit_log("payment_confirm", order_id=order_id,
                 detail=f"YPay支付成功 ¥{price} 实付¥{really_price}")

    return "success"


def _check_agent_upgraded(out_trade_no: str) -> bool:
    """Lightweight check: is the agent already at or above target tier?"""
    try:
        inner = out_trade_no[len("AGENTUP-"):]
        last_hyphen = inner.rfind("-")
        second_last = inner.rfind("-", 0, last_hyphen)
        agent_id = inner[:second_last]
        target_tier_str = inner[second_last + 1:last_hyphen]
        target_tier = int(target_tier_str.replace("L", ""))
        agent = db.get_agent(agent_id)
        return bool(agent and agent.get("tier_level", 0) >= target_tier)
    except Exception as e:
        return False


def _paid_response(order_id: str) -> JSONResponse:
    return JSONResponse(
        content={"code": 0, "paid": True, "order_id": order_id, "message": "支付成功"},
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )


def _unpaid_response(message: str = "未支付或处理中", **extra) -> JSONResponse:
    content = {"code": 0, "paid": False, "message": message, **extra}
    return JSONResponse(
        content=content,
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )


@router.get("/check/{out_trade_no}")
def check_payment(out_trade_no: str, order_id: str = Query("")):
    ypay_order = db.ypay_get_order(out_trade_no)
    if not ypay_order:
        ypay_order = db.ypay_get_order_by_out_trade_no(out_trade_no)
    if not ypay_order and order_id:
        ypay_order = db.ypay_get_order_by_out_trade_no(order_id)

    if not ypay_order:
        return _unpaid_response("支付单不存在")

    trade_no = ypay_order["trade_no"]
    actual_order_id = ypay_order.get("out_trade_no", "")

    if ypay_order["status"] == 1:
        if actual_order_id.startswith("AGENTREG-"):
            result = _handle_agent_registration(actual_order_id)
            return _paid_response(actual_order_id) if result == "success" else {"code": -1, "message": "代理注册处理失败"}
        if actual_order_id.startswith("AGENTUP-"):
            if _check_agent_upgraded(actual_order_id):
                return _paid_response(actual_order_id)
            result = _handle_agent_upgrade(actual_order_id, str(ypay_order.get("money", "")), str(ypay_order.get("truemoney", "")))
            return _paid_response(actual_order_id) if result == "success" else {"code": -1, "message": "代理升级处理失败"}

        # Regular order — check if commission already processed
        fresh_order = db.get_order(actual_order_id)
        if fresh_order and fresh_order.get("commission_status") == "processed":
            return _paid_response(actual_order_id)

        # Fallback: process commission if notify callback missed it
        if not db.claim_commission(actual_order_id):
            return _paid_response(actual_order_id)

        from api.services.task_queue import school_queue, chaoxing_queue
        if school_queue.get_job_by_order_id(actual_order_id) or chaoxing_queue.get_job_by_order_id(actual_order_id):
            return _paid_response(actual_order_id)

        db.confirm_payment(actual_order_id, payment_trade_no=trade_no, payment_channel="ypay")

        updated_order = db.get_order(actual_order_id)
        agent = None
        if updated_order and updated_order.get("user_id"):
            user = db.get_user(updated_order["user_id"])
            if user and user.get("referred_by"):
                agent = db.get_agent(user["referred_by"])
        if not agent and updated_order and updated_order.get("inviter_code"):
            agent = db.get_agent_by_referral_code(updated_order["inviter_code"])
        _process_order_commissions(updated_order, agent=agent)
        db.mark_commission_done(actual_order_id)

        db.audit_log("payment_confirm", order_id=actual_order_id,
                     detail=f"YPay支付成功(轮询) 金额:{ypay_order.get('money', '')}")
        return _paid_response(actual_order_id)

    # AGENTUP fallback: even if ypay status not updated, check if agent already upgraded
    if actual_order_id.startswith("AGENTUP-") and _check_agent_upgraded(actual_order_id):
        db.ypay_mark_paid(trade_no)
        return _paid_response(actual_order_id)

    if ypay_order.get("end_time") and ypay_order["status"] == 0:
        return _unpaid_response("订单已过期", expired=True)

    return _unpaid_response()


from api.utils import get_site_url as _get_site_url
from api.utils import make_qr_base64 as _make_qr_base64


def _make_check_token(order_id: str, out_trade_no: str) -> str:
    import hashlib
    return hashlib.md5(f"{order_id}:{out_trade_no}:{settings.jwt_secret_key}".encode()).hexdigest()[:16]


class BatchPaymentCreateRequest(BaseModel):
    order_ids: List[str] = Field(..., min_length=1, description="订单ID列表")
    pay_type: int = Field(default=1, description="支付方式 1=微信 2=支付宝")


@router.post("/batch-create")
def batch_payment_create(payload: BatchPaymentCreateRequest, current_user: dict = Depends(get_optional_user)):
    orders = []
    for oid in payload.order_ids:
        o = db.get_order(oid)
        if not o:
            return {"code": 404, "message": f"订单 {oid} 不存在"}
        if o.get("paid"):
            continue
        orders.append(o)

    if not orders:
        return {"code": 400, "message": "没有待支付的订单"}

    total_price = sum(o["price"] for o in orders)
    batch_id = f"BATCH-{uuid.uuid4().hex[:8].upper()}"

    site_url = _get_site_url()
    result = ypay.create_order(
        pay_type=payload.pay_type,
        price=total_price,
        out_trade_no=batch_id,
        name=f"批量支付-{len(orders)}笔订单",
        notify_url=f"{site_url}/api/payment/notify",
        return_url=f"{site_url}/#/orders",
        ip="",
        floating=True,
    )

    if not result:
        return {"code": -1, "message": "创建支付订单失败"}

    trade_no = result["trade_no"]
    pay_link = result.get("qrcode", "")
    pay_url = ypay.build_pay_url(trade_no)
    qr_image = _make_qr_base64(pay_link) if pay_link else _make_qr_base64(pay_url)

    for o in orders:
        db.update_order(o["order_id"], out_trade_no=batch_id)

    for o in orders:
        db.audit_log("batch_payment_created", order_id=o["order_id"],
                     detail=f"批量支付 batch={batch_id} 金额:{total_price}")

    return {
        "code": 0,
        "data": {
            "mode": "ypay_batch",
            "batch_id": batch_id,
            "trade_no": trade_no,
            "out_trade_no": batch_id,
            "order_ids": [o["order_id"] for o in orders],
            "pay_url": pay_url,
            "pay_link": pay_link,
            "total_price": total_price,
            "really_price": result["truemoney"],
            "pay_type": payload.pay_type,
            "qr_image": qr_image,
            "h5_qrurl": result.get("h5_qrurl", ""),
        },
    }


@router.get("/batch-check/{batch_id}")
def batch_check_payment(batch_id: str, out_trade_no: str = Query(""), token: str = Query("")):
    ypay_order = db.ypay_get_order(out_trade_no)
    if not ypay_order:
        ypay_order = db.ypay_get_order_by_out_trade_no(out_trade_no)
    if not ypay_order:
        return _unpaid_response("支付单不存在")

    if ypay_order.get("end_time") and ypay_order["status"] == 0:
        return _unpaid_response("订单已过期", expired=True)

    if ypay_order["status"] != 1:
        return _unpaid_response()

    param = ypay_order.get("out_trade_no", "")
    session = db._get_session()
    try:
        from api.database import Order as OrderModel
        orders = session.scalars(select(OrderModel).filter(OrderModel.out_trade_no == out_trade_no)).all()
        order_ids = [o.order_id for o in orders]
    finally:
        session.close()

    if not order_ids:
        return _unpaid_response("订单关联异常")

    paid_count = 0
    for oid in order_ids:
        order = db.get_order(oid)
        if not order:
            continue
        if order.get("paid") and order.get("commission_status") == "processed":
            paid_count += 1
            continue

        if not db.claim_commission(oid):
            paid_count += 1
            continue

        from api.services.task_queue import school_queue, chaoxing_queue
        if school_queue.get_job_by_order_id(oid) or chaoxing_queue.get_job_by_order_id(oid):
            paid_count += 1
            continue

        db.confirm_payment(oid, payment_trade_no=out_trade_no, payment_channel="ypay")
        fresh_order = db.get_order(oid)
        agent = None
        if fresh_order and fresh_order.get("user_id"):
            user = db.get_user(fresh_order["user_id"])
            if user and user.get("referred_by"):
                agent = db.get_agent(user["referred_by"])
        if not agent and fresh_order and fresh_order.get("inviter_code"):
            agent = db.get_agent_by_referral_code(fresh_order["inviter_code"])
        _process_order_commissions(fresh_order, agent=agent)
        db.mark_commission_done(oid)
        paid_count += 1

        db.audit_log("batch_payment_confirm", order_id=oid,
                     detail=f"批量支付确认 batch={batch_id}")

    if paid_count >= len(order_ids):
        return JSONResponse(
            content={"code": 0, "paid": True, "paid_count": paid_count, "message": "全部支付成功"},
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
        )

    return _unpaid_response()
import io
import uuid as _uuid
from datetime import datetime
from io import BytesIO

import qrcode
from loguru import logger
from PIL import Image

try:
    from pyzbar.pyzbar import decode as qr_decode
except (ImportError, OSError, FileNotFoundError):
    qr_decode = None
from typing import List

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from api.database import db
from api.services.ypay_service import ypay


router = APIRouter(prefix="/api/ypay", tags=["YPay支付"])

def _detect_type(content: str) -> str:
    """Detect QR content type for frontend rendering."""
    import re
    if not content:
        return "raw"
    c = content.strip()
    if c.startswith("data:image/"):
        return "image_url"
    if re.match(r'https?://.*\.(png|jpg|jpeg|gif|webp)(\?.*)?$', c, re.IGNORECASE):
        return "image_url"
    if c.startswith("wxp://") or "wx.tenpay.com" in c:
        return "wxpay"
    if c.startswith("https://qr.alipay.com/") or c.startswith("alipays://") or "render.alipay.com" in c:
        return "alipay"
    if c.startswith("http://") or c.startswith("https://"):
        return "url"
    return "raw"


from api.utils import get_site_url as _get_site_url
from api.utils import make_qr_base64 as _make_qr_base64


def _get_server_ip() -> str:
    """获取服务器本机对外 IP（通过 UDP 探测，排除内网 IP）"""
    import ipaddress as _ipaddr
    import socket as _socket

    # 先从 site_url 配置中提取 IP（如果配的是 IP 而非域名）
    site_url = _get_site_url()
    host_part = site_url.replace("http://", "").replace("https://", "").split(":")[0].split("/")[0]
    if all(c in "0123456789." for c in host_part):
        return host_part

    # 通过 UDP 探测获取本机 IP
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        # 如果是内网 IP，尝试从已知配置获取公网 IP
        if _ipaddr.ip_address(ip).is_private:
            return "38.76.190.251"
        return ip
    except Exception as e:
        return "38.76.190.251"



@router.post("/decode-qr")
async def decode_qr(file: UploadFile = File(...)):
    """上传二维码图片，自动解码并返回内容"""
    if not file.content_type or not file.content_type.startswith("image/"):
        return {"code": -1, "message": "请上传图片文件"}
    try:
        contents = await file.read()
        if len(contents) > 10 * 1024 * 1024:
            return {"code": -1, "message": "图片大小不能超过10MB"}
        img = Image.open(BytesIO(contents))
        if qr_decode is None:
            return {"code": -1, "message": "二维码解码库未安装，请安装 pyzbar 和 zbar native 库"}
        decoded = qr_decode(img)
        if not decoded:
            return {"code": -1, "message": "未检测到二维码，请手动输入"}
        data = decoded[0].data.decode("utf-8")
        return {"code": 0, "message": "解码成功", "data": data}
    except Exception as e:
        logger.error(f"decode_qr_error error={str(e)}")
        return {"code": -1, "message": f"解码失败: {str(e)}"}


class PayCreateRequest(BaseModel):
    order_id: str
    pay_type: int = 1


@router.post("/create")
def pay_create(payload: PayCreateRequest):
    order = db.get_order(payload.order_id)
    if not order:
        return {"code": 404, "message": "订单不存在"}
    if order["paid"]:
        return {"code": 400, "message": "订单已支付"}

    site_url = _get_site_url()
    notify_url = f"{site_url}/api/payment/notify"

    result = ypay.create_order(
        pay_type=payload.pay_type,
        price=order["price"],
        out_trade_no=payload.order_id,
        name=f"网课代刷-{order.get('username', '')}",
        notify_url=notify_url,
        return_url=f"{site_url}/#/orders",
        ip="",
        floating=True,
    )

    if not result:
        return {"code": -1, "message": "创建支付订单失败，请检查收款通道是否在线"}

    trade_no = result["trade_no"]
    pay_url = ypay.build_pay_url(trade_no)

    # 根据 qr_content_type 决定返回什么给前端
    qr_content = result.get("qrcode", "")
    qr_content_type = result.get("qr_content_type", _detect_type(qr_content))

    if qr_content_type == "image_url":
        # 直接是图片URL，前端直接展示
        qr_image = qr_content
    else:
        # wxp://、alipay链接等，生成二维码图片
        qr_image = _make_qr_base64(qr_content) if qr_content else _make_qr_base64(pay_url)

    db.update_order(payload.order_id, out_trade_no=trade_no)
    db.audit_log("ypay_created", order_id=payload.order_id,
                 detail=f"YPay订单:{trade_no} 金额:{order['price']}")

    return {
        "code": 0,
        "data": {
            "mode": "ypay",
            "trade_no": trade_no,
            "out_trade_no": payload.order_id,
            "order_id": payload.order_id,
            "pay_url": pay_url,
            "price": order["price"],
            "really_price": result["truemoney"],
            "pay_type": payload.pay_type,
            "qr_image": qr_image,
            "qr_content_type": qr_content_type,
            "channel_code": result.get("channel_code", ""),
            "channel_name": result.get("channel_name", ""),
            "qrcode_content": qr_content,
            "h5_qrurl": result.get("h5_qrurl", ""),
        },
    }


@router.get("/check/{trade_no}")
def pay_check(trade_no: str, order_id: str = Query("")):
    order_data = db.ypay_get_order(trade_no)
    if not order_data:
        return JSONResponse(
            content={"code": 0, "paid": False, "message": "未找到支付订单"},
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
        )

    _no_cache = {"X-Accel-Buffering": "no", "Cache-Control": "no-store"}

    if order_data["status"] == 1:
        actual_order_id = order_data.get("out_trade_no", "") or order_id
        # Handle agent registration / upgrade payments
        if actual_order_id.startswith("AGENTREG-"):
            from api.routers.payment import _handle_agent_registration
            result = _handle_agent_registration(actual_order_id)
            return JSONResponse(
                content={"code": 0, "paid": True, "message": "支付成功" if result == "success" else "处理失败", "really_price": order_data.get("truemoney", 0)},
                headers=_no_cache,
            )
        if actual_order_id.startswith("AGENTUP-"):
            from api.routers.payment import _handle_agent_upgrade
            result = _handle_agent_upgrade(actual_order_id, str(order_data.get("money", "")), str(order_data.get("truemoney", "")))
            return JSONResponse(
                content={"code": 0, "paid": True, "message": "支付成功" if result == "success" else "处理失败", "really_price": order_data.get("truemoney", 0)},
                headers=_no_cache,
            )
        anti_order = db.get_order(actual_order_id) if actual_order_id else None
        # Only process if not already done (avoid heavy work on every poll)
        if anti_order and not anti_order.get("paid"):
            db.confirm_payment(actual_order_id, payment_trade_no=trade_no, payment_channel="ypay")
            _process_paid_order(actual_order_id, already_confirmed=True)
        elif anti_order and anti_order.get("paid") and anti_order.get("commission_status") != "processed":
            _process_paid_order(actual_order_id, already_confirmed=True)
        return JSONResponse(
            content={"code": 0, "paid": True, "message": "支付成功", "really_price": order_data.get("truemoney", 0)},
            headers=_no_cache,
        )

    remaining = 0
    if order_data["out_time"]:
        try:
            out_dt = datetime.fromisoformat(order_data["out_time"])
            now = datetime.now().replace(tzinfo=None)
            out_dt_naive = out_dt.replace(tzinfo=None) if out_dt.tzinfo else out_dt
            remaining = max(0, int((out_dt_naive - now).total_seconds()))
        except Exception as e:
            pass

    if remaining <= 0 and order_data["status"] == 0:
        return JSONResponse(
            content={"code": 0, "paid": False, "message": "订单已过期", "expired": True},
            headers=_no_cache,
        )

    return JSONResponse(
        content={"code": 0, "paid": False, "message": "等待支付", "remaining": remaining},
        headers=_no_cache,
    )


@router.get("/order/{trade_no}")
def pay_order_detail(trade_no: str):
    order_data = db.ypay_get_order(trade_no)
    if not order_data:
        return {"code": -1, "message": "支付订单不存在"}

    qr_content = order_data.get("qrcode", "")
    qr_content_type = ypay._detect_qr_content_type_fn(qr_content) if hasattr(ypay, '_detect_qr_content_type_fn') else _detect_type(qr_content)

    if order_data["status"] == 1:
        return {
            "code": 0,
            "data": {
                "trade_no": order_data["trade_no"],
                "out_trade_no": order_data["out_trade_no"],
                "type": order_data["type"],
                "pay_type": order_data["pay_type"],
                "money": order_data["money"],
                "truemoney": order_data["truemoney"],
                "status": 1,
                "paid": True,
                "message": "支付成功",
            },
        }

    # 根据 qr_content_type 决定前端如何展示
    qr_image = None
    if qr_content_type == "image_url":
        # 直接是图片URL，前端直接展示
        qr_image = qr_content
    else:
        # wxp://、alipay链接、普通URL等，需要生成二维码图片
        qr_image = _make_qr_base64(qr_content)

    return {
        "code": 0,
        "data": {
            "trade_no": order_data["trade_no"],
            "out_trade_no": order_data["out_trade_no"],
            "type": order_data["type"],
            "pay_type": order_data["pay_type"],
            "money": order_data["money"],
            "truemoney": order_data["truemoney"],
            "qrcode": qr_content,
            "qr_content_type": qr_content_type,
            "status": order_data["status"],
            "qr_image": qr_image,
            "pay_url": ypay.build_pay_url(trade_no),
        },
    }


def _process_paid_order(order_id: str, already_confirmed: bool = False):
    from api.routers.payment import _process_order_commissions
    try:
        fresh_order = db.get_order(order_id)
        if not fresh_order:
            return
        if fresh_order.get("paid") and fresh_order.get("commission_status") == "processed":
            return

        if not already_confirmed and not fresh_order.get("paid"):
            db.confirm_payment(order_id, payment_trade_no=f"YPAY-{order_id}", payment_channel="ypay")
            fresh_order = db.get_order(order_id)

        if fresh_order.get("commission_status") != "processed":
            if not db.claim_commission(order_id):
                return
            agent = None
            if fresh_order.get("user_id"):
                user = db.get_user(fresh_order["user_id"])
                if user and user.get("referred_by"):
                    agent = db.get_agent(user["referred_by"])
            if not agent and fresh_order.get("inviter_code"):
                agent = db.get_agent_by_referral_code(fresh_order["inviter_code"])
            _process_order_commissions(fresh_order, agent=agent)
            db.mark_commission_done(order_id)
    except Exception as e:
        logger.error(f"ypay_process_paid_error order_id={order_id} error={str(e)}")


class BatchCreateRequest(BaseModel):
    order_ids: List[str]
    pay_type: int = 1


@router.post("/batch-create")
def batch_pay_create(payload: BatchCreateRequest):
    orders = []
    skipped = []
    for oid in payload.order_ids:
        o = db.get_order(oid)
        if not o:
            return {"code": 404, "message": f"订单 {oid} 不存在"}
        if o.get("paid"):
            skipped.append(oid)
            continue
        if o.get("status") not in ("pending", "awaiting_payment"):
            skipped.append(oid)
            continue
        orders.append(o)

    if not orders:
        return {"code": 400, "message": "没有待支付的订单"}

    total_price = sum(o["price"] for o in orders)
    batch_id = f"BATCH-{_uuid.uuid4().hex[:8].upper()}"

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
        db.audit_log("batch_ypay_created", order_id=o["order_id"],
                     detail=f"批量支付 batch={batch_id}")

    return {
        "code": 0,
        "data": {
            "mode": "ypay_batch",
            "batch_id": batch_id,
            "trade_no": trade_no,
            "out_trade_no": batch_id,
            "order_ids": [o["order_id"] for o in orders],
            "skipped_ids": skipped,
            "pay_url": pay_url,
            "pay_link": pay_link,
            "total_price": total_price,
            "really_price": result["truemoney"],
            "pay_type": payload.pay_type,
            "qr_image": qr_image,
            "h5_qrurl": result.get("h5_qrurl", ""),
        },
    }


@router.get("/qrcode/{trade_no}")
def pay_qrcode(trade_no: str):
    pay_url = ypay.build_pay_url(trade_no)
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(pay_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


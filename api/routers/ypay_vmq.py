from datetime import datetime

from loguru import logger

try:
    from pyzbar.pyzbar import decode as qr_decode
except (ImportError, OSError, FileNotFoundError):
    qr_decode = None

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from api.compat import to_thread_impl
from api.database import db
from api.services.ypay_service import ypay


from api.routers.ypay_routes import _process_paid_order

router = APIRouter(prefix="/api/ypay", tags=["YPay VMQ"])

@router.post("/vmq/heart", response_class=PlainTextResponse)
async def vmq_heart(request: Request):
    qp = dict(request.query_params) or {}
    t = qp.get("t", "")
    sign = qp.get("sign", "")

    if not t or not sign:
        try:
            body = await request.form()
            t = body.get("t", "") or t
            sign = body.get("sign", "") or sign
        except Exception as e:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    import urllib.parse
                    body_dict = dict(urllib.parse.parse_qsl(body_bytes.decode("utf-8", errors="replace")))
                    t = body_dict.get("t", t)
                    sign = body_dict.get("sign", sign)
            except Exception as e:
                pass

    if not t or not sign:
        return "fail"

    return await to_thread_impl(_vmq_heart_sync, t, sign, request)


@router.post("/vmq/push", response_class=PlainTextResponse)
async def vmq_push(request: Request):
    qp = dict(request.query_params) or {}
    t = qp.get("t", "")
    ptype = qp.get("type", "")
    price = qp.get("price", "")
    sign = qp.get("sign", "")

    if not ptype or not price:
        try:
            body = await request.form()
            t = body.get("t", "") or t
            ptype = body.get("type", "") or ptype
            price = body.get("price", "") or price
            sign = body.get("sign", "") or sign
        except Exception as e:
            pass

    if not ptype or not price:
        return "fail"

    return await to_thread_impl(_vmq_push_sync, ptype, price, t, sign)


def _vmq_heart_sync(t: str, sign: str, request: Request) -> str:
    if not ypay.verify_heart_sign(t, sign):
        _handle_heart_fail(request)
        return "fail"
    _handle_heart_success(request)
    db.ypay_close_expired_orders()
    return "success"


def _vmq_push_sync(ptype: str, price: str, t: str, sign: str) -> str:
    if not ypay.verify_push_sign(ptype, price, t, sign):
        return "fail"
    try:
        price_f = float(price)
        ptype_i = int(ptype)
    except (ValueError, TypeError):
        return "fail"
    order = ypay.match_payment(price_f, ptype_i)
    if not order:
        return "notify"
    out_trade_no = order.get("out_trade_no", "")
    if out_trade_no:
        _process_paid_order(out_trade_no)
    logger.info("vmq_push_matched_ypay trade_no={} price={}", order["trade_no"], price_f)
    return "success"


def _handle_heart_fail(request: Request):
    fail_count = int(db.ypay_setting_get("sign_fail_count", "0")) + 1
    db.ypay_setting_set("sign_fail_count", str(fail_count))
    db.ypay_setting_set("sign_fail_time", datetime.now().isoformat())
    if fail_count >= 3:
        db.ypay_setting_set("monitor_status", "key_mismatch")


def _handle_heart_success(request: Request):
    raw_ip = "unknown"
    try:
        if request.client and request.client.host:
            raw_ip = request.client.host.split(",")[0].strip()
    except Exception as e:
        pass
    now = datetime.now().isoformat()
    db.ypay_setting_set("sign_fail_count", "0")
    db.ypay_setting_set("monitor_last_heart", now)
    db.ypay_setting_set("monitor_status", "online")
    db.ypay_setting_set("monitor_ip", raw_ip)

    accounts = db.ypay_list_accounts()
    for acc in accounts:
        if acc["status"] != 1:
            db.ypay_update_account(acc["id"], status=1)


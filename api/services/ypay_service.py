import random
import time as _time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger

from api.services.ypay_qr import (
    _detect_qr_content_type,
    _hash_md5,
    generate_qrcode,
)


# Payment type constants (matching Vmq app push types)
WECHAT = 1
ALIPAY = 2
LKL = 3

PAY_TYPE_MAP = {
    WECHAT: "wxpay",
    ALIPAY: "alipay",
    LKL: "lkl",
}

CHANNEL_TO_VMQ_TYPE = {
    "wxpay_dy": WECHAT, "wxpay_software": WECHAT,
    "wxpay_cloud": WECHAT, "wxpay_jym_cloud": WECHAT,
    "wxpay_skd": WECHAT, "wxpay_cloudzs": WECHAT,
    "alipay_software": ALIPAY, "alipay_grmg": ALIPAY,
    "alipay_mck": ALIPAY, "alipay_dmf": ALIPAY,
    "alipay_official": ALIPAY,
    "lkl_wxpay": WECHAT, "lkl_alipay": ALIPAY,
    "dougong_alipay": ALIPAY, "dougong_wxpay": WECHAT,
    "lebrush_alipay": ALIPAY, "lebrush_wxpay": WECHAT,
}

_FLOAT_OFFSETS = [0.01, 0.02, 0.03, 0.04, 0.05, -0.01, -0.02, -0.03]


def _compute_floating_price(base: float, existing: List[float]) -> float:
    offsets = _FLOAT_OFFSETS[:]
    random.shuffle(offsets)
    for off in offsets:
        candidate = round(base + off, 2)
        if candidate > 0 and candidate not in existing:
            return candidate
    return base


def generate_trade_no() -> str:
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    uid = uuid.uuid4().hex[:6].upper()
    return f"Y{ts}{uid}"


class YPayService:

    def create_order(
        self,
        *,
        pay_type: int = WECHAT,
        price: float,
        out_trade_no: str = "",
        name: str = "",
        notify_url: str = "",
        return_url: str = "",
        ip: str = "",
        floating: bool = True,
    ) -> Optional[Dict[str, Any]]:
        from api.database import db

        trade_no = generate_trade_no()
        money = round(Decimal(str(price)), 2)

        db.ypay_close_expired_orders()

        account = db.ypay_pick_channel(pay_type)
        if not account:
            logger.warning(f"ypay_no_channel pay_type={pay_type}")
            return None

        logger.info("ypay_channel_picked pay_type={} code={} name={} has_qr_url={}", pay_type, account.get("code"), account.get("name"), bool(account.get("qr_url")))

        if floating:
            existing = db.ypay_get_active_prices(account["id"])
            really_price = _compute_floating_price(float(money), existing)
        else:
            really_price = float(money)

        locked = db.ypay_lock_price(really_price, trade_no)
        if locked is None:
            logger.warning(f"ypay_lock_price_failed price={really_price} trade_no={trade_no}")
            return None

        code = account.get("code", "")
        type_str = account.get("type", PAY_TYPE_MAP.get(pay_type, "wxpay"))
        if code in ("lkl_alipay", "dougong_alipay", "lebrush_alipay"):
            type_str = "alipay"
        elif code in ("lkl_wxpay", "dougong_wxpay", "lebrush_wxpay"):
            type_str = "wxpay"

        qrcode, h5_qrurl = generate_qrcode(account, really_price, trade_no, out_trade_no, self._get_site_url)
        if not qrcode:
            logger.warning("ypay_qrcode_failed code={} trade_no={} qr_url={}", code, trade_no, account.get("qr_url", "")[:50])
            db.ypay_release_price(really_price)
            return None

        timeout_seconds = int(db.ypay_setting_get("pay_timeout", "300"))
        out_time = datetime.now() + timedelta(seconds=timeout_seconds)

        order = db.ypay_create_order(
            trade_no=trade_no,
            out_trade_no=out_trade_no,
            pay_type=pay_type,
            type_str=type_str,
            name=name,
            money=float(money),
            truemoney=float(really_price),
            account_id=account["id"],
            qrcode=qrcode,
            h5_qrurl=h5_qrurl,
            notify_url=notify_url,
            return_url=return_url,
            ip=ip,
            out_time=out_time.isoformat(),
        )

        if not order:
            db.ypay_release_price(really_price)
            return None

        order["qr_content_type"] = _detect_qr_content_type(qrcode)
        order["channel_code"] = code
        order["channel_name"] = account.get("name", "")

        logger.info("ypay_order_created trade_no={} price={} really_price={} pay_type={} code={} qr_content_type={}", trade_no, float(money), really_price, pay_type, code, order["qr_content_type"])
        return order

    def check_order(self, trade_no: str) -> Optional[Dict[str, Any]]:
        from api.database import db
        order = db.ypay_get_order(trade_no)
        if order:
            order["qr_content_type"] = _detect_qr_content_type(order.get("qrcode", ""))
        return order

    def match_payment(self, price: float, pay_type: int) -> Optional[Dict[str, Any]]:
        from api.database import db

        db.ypay_close_expired_orders()

        base_price = round(float(Decimal(str(price))), 2)

        order = db.ypay_find_pending_by_price(base_price, pay_type)
        if not order:
            return None

        if abs(float(order["truemoney"]) - base_price) >= 0.01:
            logger.info("ypay_amount_mismatch pushed={} order={} trade_no={}", base_price, order["truemoney"], order["trade_no"])
            return None

        if not db.ypay_mark_paid(order["trade_no"]):
            return None
        db.ypay_release_price(order["truemoney"])

        notify_url = order.get("notify_url", "")
        if notify_url:
            import threading
            cb_key = db.ypay_setting_get("key", "")
            t = threading.Thread(target=self._send_callback, args=(order, notify_url, cb_key), daemon=True)
            t.start()

            logger.info("ypay_payment_matched trade_no={} price={} truemoney={}", order["trade_no"], base_price, order["truemoney"])
        return order

    def build_pay_url(self, trade_no: str) -> str:
        from api.database import db
        from config import settings
        site_url = (db.ypay_setting_get("site_url", "") or settings.site_url or "http://localhost:8000").rstrip("/")
        return f"{site_url}/#/payment/{trade_no}"

    def verify_callback_sign(self, pay_id: str, param: str, pay_type: str,
                              price: str, really_price: str, sign: str) -> bool:
        from api.database import db
        key = db.ypay_setting_get("key", "")
        if not key:
            return False
        expected = _hash_md5(f"{pay_id}{param}{pay_type}{price}{really_price}{key}")
        return sign == expected

    def verify_heart_sign(self, t: str, sign: str) -> bool:
        from api.database import db
        key = db.ypay_setting_get("key", "")
        if not key:
            return False
        if not self._validate_timestamp(t):
            return False
        candidates = [
            _hash_md5(t + key),
            _hash_md5(key + t),
        ]
        if t.isdigit():
            ts = int(t)
            if ts > 1e12:
                t_sec = str(ts // 1000)
                candidates.append(_hash_md5(t_sec + key))
                candidates.append(_hash_md5(key + t_sec))
        return sign in candidates

    def verify_push_sign(self, ptype: str, price: str, t: str, sign: str) -> bool:
        from api.database import db
        key = db.ypay_setting_get("key", "")
        if not key:
            return False
        if not self._validate_timestamp(t):
            return False
        candidates = [
            _hash_md5(ptype + price + t + key),
            _hash_md5(key + ptype + price + t),
            _hash_md5(t + key),
            _hash_md5(key + t),
        ]
        return sign in candidates

    def _validate_timestamp(self, t: str, max_offset_minutes: int = 120) -> bool:
        if not t or not t.isdigit():
            return False
        try:
            ts = int(t)
            if ts > 1e12:
                ts = ts // 1000
            now = int(_time.time())
            diff = abs(now - ts)
            return diff <= max_offset_minutes * 60
        except (ValueError, TypeError):
            return False

    def _send_callback(self, order: Dict[str, Any], notify_url: str, key: str = ""):
        import httpx
        if not key:
            from api.database import db
            key = db.ypay_setting_get("key", "")

        pay_id = order.get("trade_no", "")
        param = order.get("out_trade_no", "")
        ptype = str(order.get("pay_type", "1"))
        price_str = str(order.get("money", "0"))
        really_price_str = str(order.get("truemoney", "0"))

        sign_str = f"{pay_id}{param}{ptype}{price_str}{really_price_str}{key}"
        payload = {
            "payId": pay_id,
            "param": param,
            "type": ptype,
            "price": price_str,
            "reallyPrice": really_price_str,
            "sign": _hash_md5(sign_str),
        }
        for attempt in range(2):
            try:
                with httpx.Client(timeout=httpx.Timeout(5.0)) as client:
                    resp = client.post(notify_url, data=payload)
                    if resp.status_code == 200:
                        text = resp.text.strip().lower()
                        if text in ("success", "ok", "1", "true"):
                            logger.info(f"ypay_callback_success trade_no={pay_id} attempt={{attempt + 1}}")
                            return
                        logger.warning(f"ypay_callback_bad_response trade_no={pay_id} attempt={attempt + 1} body={text[:100]}")
                    else:
                        logger.warning(f"ypay_callback_http_error trade_no={pay_id} attempt={attempt + 1} status={resp.status_code}")
                if attempt < 1:
                    _time.sleep(2)
            except Exception as e:
                logger.warning("ypay_callback_retry trade_no={} attempt={} error={}", pay_id, attempt + 1, str(e))
                if attempt < 1:
                    _time.sleep(2 ** (attempt + 1))
        logger.error(f"ypay_callback_failed trade_no={pay_id} notify_url={notify_url}")

    def _send_async_notify(self, url: str, max_retries: int = 3):
        import httpx
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        text = resp.text.strip().lower()
                        if text in ("success", "ok", "1", "true"):
                            return
                if attempt < max_retries - 1:
                    _time.sleep(2 ** (attempt + 1))
            except Exception as e:
                logger.warning(f"ypay_async_notify_retry attempt={{attempt + 1}} error={str(e)}")
                if attempt < max_retries - 1:
                    _time.sleep(2 ** (attempt + 1))
        logger.error(f"ypay_async_notify_failed url={url}")

    def _get_site_url(self) -> str:
        from api.database import db
        from config import settings
        return (db.ypay_setting_get("site_url", "") or settings.site_url or "http://localhost:8000").rstrip("/")


ypay = YPayService()

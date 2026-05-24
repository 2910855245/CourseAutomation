from __future__ import annotations

import base64
import io
import random
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

import qrcode

from config import settings

# 中国时区 UTC+8
_CHINA_TZ = timezone(timedelta(hours=8))


def now() -> datetime:
    """返回中国时区的当前时间（替代 datetime.now()）"""
    return datetime.now(_CHINA_TZ)


def now_str() -> str:
    """返回中国时区的当前时间字符串"""
    return now().strftime("%Y-%m-%d %H:%M:%S")


def now_iso() -> str:
    """返回中国时区的当前时间 ISO 格式"""
    return now().isoformat()


def mask_password(order: dict) -> dict:
    if not order:
        return order
    d = dict(order)
    pwd = d.get("password", "")
    if not pwd:
        d["password"] = ""
    else:
        d["password"] = "***"
    return d


def make_qr_base64(data: str) -> Optional[str]:
    try:
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        return None


def get_site_url() -> str:
    from api.database import db
    try:
        db_url = db.ypay_setting_get("site_url", "")
        if db_url:
            return db_url.strip().rstrip("/")
    except Exception as e:
        pass
    return (settings.site_url or "http://localhost:8000").strip().rstrip("/")


def generate_referral_code() -> str:
    from api.database import db
    chars = string.ascii_uppercase + string.digits
    while True:
        code = "REF" + "".join(random.choices(chars, k=6))
        if not db.get_agent_by_referral_code(code):
            return code


def generate_slug() -> str:
    from api.database import db
    chars = string.ascii_lowercase + string.digits
    while True:
        slug = "agent" + "".join(random.choices(chars, k=5))
        if not db.get_agent_by_subdomain(slug):
            return slug


def get_agent_fees_data() -> dict:
    from api.database import db
    return {
        "registration_enabled": db.config_get("agent_registration_fee_enabled") == "true",
        "registration_fee": float(db.config_get("agent_registration_fee") or 100),
        "upgrade_enabled": db.config_get("agent_upgrade_fee_enabled") == "true",
        "upgrade_l2_fee": float(db.config_get("agent_upgrade_l2_fee") or 200),
        "upgrade_l3_fee": float(db.config_get("agent_upgrade_l3_fee") or 300),
    }


def set_agent_fees_data(body) -> None:
    from api.database import db
    db.config_set("agent_registration_fee_enabled", "true" if body.registration_enabled else "false")
    db.config_set("agent_registration_fee", str(body.registration_fee))
    db.config_set("agent_upgrade_fee_enabled", "true" if body.upgrade_enabled else "false")
    db.config_set("agent_upgrade_l2_fee", str(body.upgrade_l2_fee))
    db.config_set("agent_upgrade_l3_fee", str(body.upgrade_l3_fee))


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple = (Exception,)):
    """重试装饰器，用于支付等关键路径。

    用法:
        @retry(max_attempts=3, delay=0.5, exceptions=(ConnectionError, TimeoutError))
        def call_external_api():
            ...
    """
    import functools
    import time as _time

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            wait = delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts:
                        _time.sleep(wait)
                        wait *= backoff
            raise last_exc
        return wrapper
    return decorator

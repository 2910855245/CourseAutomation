"""通用工具：密码脱敏、二维码、站点 URL、ID 生成。"""

from __future__ import annotations

import base64
import io
import json
import uuid

import qrcode

from config import settings


def mask_password(order: dict) -> dict:
    """订单展示层密码脱敏（***）"""
    if not order:
        return order
    d = dict(order)
    pwd = d.get("password", "")
    d["password"] = "***" if pwd else ""
    return d


def make_qr_base64(data: str) -> str | None:
    """内容 → 二维码 PNG base64（data:image/png;base64,...）"""
    try:
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
    except Exception:
        return None


def get_site_url() -> str:
    """站点 URL：优先数据库配置，回退 settings"""
    from api.database import db
    try:
        db_url = db.ypay_setting_get("site_url", "")
        if db_url:
            return db_url.strip().rstrip("/")
    except Exception:
        pass
    return (settings.site_url or "http://localhost:8000").strip().rstrip("/")


def gen_id(prefix: str, n: int = 8) -> str:
    """业务 ID 生成：PREFIX-XXXXXXXX（大写 hex）"""
    return f"{prefix}-{uuid.uuid4().hex[:n].upper()}"


def parse_course_ids(course_ids) -> list:
    """course_ids str/list/None → list（订单字段解析，多处分身归一）"""
    if isinstance(course_ids, str):
        try:
            course_ids = json.loads(course_ids) if course_ids else []
        except (json.JSONDecodeError, ValueError):
            course_ids = []
    if not isinstance(course_ids, list):
        course_ids = []
    return course_ids


VALID_TASK_TYPES = ("video", "exam", "full", "chaoxing_points")


def normalize_task_type(task_type: str) -> str:
    """task_type 白名单归一（非法值回退 full）"""
    return task_type if task_type in VALID_TASK_TYPES else "full"

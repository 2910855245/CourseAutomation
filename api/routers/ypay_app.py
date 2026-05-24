import hashlib
import json
import time
from datetime import datetime

from loguru import logger

try:
    from pyzbar.pyzbar import decode as qr_decode
except (ImportError, OSError, FileNotFoundError):
    qr_decode = None
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from api.compat import to_thread_impl
from api.database import db
from api.models import ApiResponse
from api.services.ypay_service import ypay
from config import settings


from api.routers.ypay_routes import _process_paid_order

router = APIRouter(prefix="/api/ypay", tags=["YPay APP"])
raw_router = APIRouter(tags=["YPay原生接口"])

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



@router.api_route("/app-heart", methods=["GET", "POST"], response_class=PlainTextResponse)
async def ypay_app_heart(request: Request):
    qp = dict(request.query_params)
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
        _ypay_handle_heart_fail(request)
        return json.dumps({"code": -1, "msg": "参数缺失"}, ensure_ascii=False)

    if not ypay.verify_heart_sign(t, sign):
        _ypay_handle_heart_fail(request)
        return json.dumps({"code": -1, "msg": "密钥错误"}, ensure_ascii=False)

    _ypay_handle_heart_success(request)
    db.ypay_close_expired_orders()
    return json.dumps({"code": 1, "msg": "success"}, ensure_ascii=False)


@router.api_route("/app-offline", methods=["GET", "POST"], response_class=PlainTextResponse)
async def ypay_app_offline(request: Request):
    """APP主动通知下线"""
    qp = dict(request.query_params)
    t = qp.get("t", "")
    sign = qp.get("sign", "")

    if not t or not sign:
        try:
            body = await request.form()
            t = body.get("t", "") or t
            sign = body.get("sign", "") or sign
        except Exception as e:
            pass

    if not t or not sign:
        return json.dumps({"code": -1, "msg": "参数缺失"}, ensure_ascii=False)

    if not ypay.verify_heart_sign(t, sign):
        return json.dumps({"code": -1, "msg": "密钥错误"}, ensure_ascii=False)

    db.ypay_setting_set("monitor_status", "offline")
    db.ypay_setting_set("monitor_last_heart", "")
    logger.info("app_offline_notify detail=APP主动通知下线")
    return json.dumps({"code": 1, "msg": "已标记离线"}, ensure_ascii=False)


def _ypay_handle_heart_fail(request: Request):
    fail_count = int(db.ypay_setting_get("sign_fail_count", "0")) + 1
    db.ypay_setting_set("sign_fail_count", str(fail_count))
    db.ypay_setting_set("sign_fail_time", datetime.now().isoformat())
    # 连续失败10次才标记为 key_mismatch（避免误判）
    if fail_count >= 10:
        db.ypay_setting_set("monitor_status", "key_mismatch")
    _ypay_record_heart(False)


def _ypay_handle_heart_success(request: Request):
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
    _ypay_record_heart(True)
    accounts = db.ypay_list_accounts()
    for acc in accounts:
        if acc["status"] != 1:
            db.ypay_update_account(acc["id"], status=1)


def _ypay_record_heart(ok: bool):
    try:
        history = db.ypay_setting_get("heart_history", "")
        entries = [e for e in history.split(",") if e][-19:]
        entries.append(f"{int(time.time())}:{'ok' if ok else 'fail'}")
        db.ypay_setting_set("heart_history", ",".join(entries))
    except Exception as e:
        pass


# ============================================================
# APP 支付推送 (兼容 GET+POST, 兼容 VMQ 签名格式)
# ============================================================

@router.api_route("/app-push", methods=["GET", "POST"], response_class=PlainTextResponse)
async def ypay_app_push(request: Request):
    qp = dict(request.query_params)
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
        return json.dumps({"code": -1, "msg": "参数缺失"}, ensure_ascii=False)

    if not ypay.verify_push_sign(ptype, price, t, sign):
        return json.dumps({"code": -1, "msg": "签名错误"}, ensure_ascii=False)

    return await to_thread_impl(_ypay_app_push_sync, ptype, price)


def _ypay_app_push_sync(ptype: str, price: str) -> str:
    try:
        price_f = float(price)
        ptype_i = int(ptype)
    except (ValueError, TypeError):
        return json.dumps({"code": -1, "msg": "参数格式错误"}, ensure_ascii=False)

    order = ypay.match_payment(price_f, ptype_i)
    if not order:
        logger.info(f"ypay_push_no_match price={price_f} ptype={ptype_i}")
        return json.dumps({"code": 0, "msg": "notify"}, ensure_ascii=False)

    out_trade_no = order.get("out_trade_no", "")
    if out_trade_no:
        _ypay_process_paid_order_safe(out_trade_no)

    logger.info("ypay_push_matched trade_no={} price={} out_trade_no={}", order["trade_no"], price_f, out_trade_no)
    return json.dumps({"code": 1, "msg": "成功"}, ensure_ascii=False)


def _ypay_process_paid_order_safe(order_id: str):
    _process_paid_order(order_id, already_confirmed=False)


# ============================================================
# APP 配对二维码
# ============================================================

@router.get("/app-qrcode")
def ypay_app_qrcode(request: Request):
    key = db.ypay_setting_get("key", "")
    if not key:
        key = settings.vmqpay_key or ""
    if not key:
        return {"code": -1, "message": "请先配置通讯密钥"}

    site_url = _get_site_url()
    host = site_url.replace("http://", "").replace("https://", "").rstrip("/")

    is_domain = "." in host.split(":")[0] and not all(c in "0123456789." for c in host.split(":")[0])
    is_local = host.startswith("localhost") or host.startswith("127.0.0.1")

    if is_local:
        # localhost 无法被 APP 访问，使用服务器公网 IP + 端口
        server_ip = _get_server_ip()
        port = host.split(":")[1] if ":" in host else str(settings.port or 8000)
        host = f"{server_ip}:{port}"
    elif is_domain:
        # 域名通过 nginx 反代，APP 直接用域名 + 443 端口即可
        host = host.split(":")[0]

    pair_data = f"{host}/{key}"
    qr_b64 = _make_qr_base64(pair_data)

    return ApiResponse(data={
        "pair_data": pair_data,
        "qr_image": qr_b64,
        "host": host,
    })


# ============================================================
# APP 配对确认
# ============================================================

class PairConfirmRequest(BaseModel):
    pair_session: str = ""
    key_hash: str = ""


@router.post("/pair-confirm")
def ypay_pair_confirm(payload: PairConfirmRequest, request: Request):
    # 验证 key_hash：APP 端计算 md5(pair_session + key)，服务端同样计算
    expected_key = db.ypay_setting_get("key", "")
    if not expected_key or not payload.key_hash:
        return json.dumps({"code": 0, "msg": "密钥未配置"}, ensure_ascii=False)
    expected_hash = hashlib.md5((payload.pair_session + expected_key).encode()).hexdigest()
    if payload.key_hash != expected_hash:
        fail_count = int(db.ypay_setting_get("sign_fail_count", "0")) + 1
        db.ypay_setting_set("sign_fail_count", str(fail_count))
        logger.warning("ypay_pair_confirm_key_mismatch")
        return json.dumps({"code": 0, "msg": "密钥错误"}, ensure_ascii=False)

    raw_ip = "unknown"
    try:
        if request.client and request.client.host:
            raw_ip = request.client.host.split(",")[0].strip()
    except Exception as e:
        pass

    now = datetime.now().isoformat()
    db.ypay_setting_set("monitor_last_heart", now)
    db.ypay_setting_set("monitor_status", "online")
    db.ypay_setting_set("monitor_ip", raw_ip)
    db.ypay_setting_set("sign_fail_count", "0")

    logger.info(f"ypay_pair_confirm ip={raw_ip}")
    return json.dumps({"code": 1, "msg": "配对成功"}, ensure_ascii=False)


# ============================================================
# APP 配对状态
# ============================================================

@router.get("/pair-status")
def ypay_pair_status():
    monitor_status = db.ypay_setting_get("monitor_status", "offline")
    monitor_heart = db.ypay_setting_get("monitor_last_heart", "")
    is_online = False
    seconds_ago = -1
    if monitor_heart:
        try:
            last = datetime.fromisoformat(monitor_heart)
            delta = (datetime.now().replace(tzinfo=None) - last.replace(tzinfo=None)).total_seconds()
            seconds_ago = int(delta)
            is_online = seconds_ago <= 180
        except Exception as e:
            pass

    return ApiResponse(data={
        "paired": monitor_status != "offline" or is_online,
        "is_online": is_online,
        "monitor_status": monitor_status,
        "seconds_ago": seconds_ago,
    })


# ============================================================
# APP 信息 & 下载
# ============================================================

def _parse_apk_info(apk_path: str) -> dict:
    """从 APK 文件中解析包名和版本号"""
    import subprocess
    result = {"package": "", "version": ""}
    try:
        out = subprocess.check_output(
            ["aapt", "dump", "badging", apk_path],
            stderr=subprocess.DEVNULL, timeout=10
        ).decode("utf-8", errors="ignore")
        for line in out.splitlines():
            if line.startswith("package:"):
                import re
                m = re.search(r"name='([^']+)'", line)
                if m:
                    result["package"] = m.group(1)
                m = re.search(r"versionName='([^']+)'", line)
                if m:
                    result["version"] = m.group(1)
                break
    except Exception as e:
        pass
    return result


@router.get("/app-info")
def ypay_app_info():
    import os
    apk_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static", "ypay-monitor.apk")
    info = _parse_apk_info(apk_path) if os.path.isfile(apk_path) else {}
    return ApiResponse(data={
        "app_name": "收款监控",
        "version": info.get("version") or "3.5",
        "package": info.get("package") or "com.shinian.pay",
        "download_url": "/api/ypay/app-download",
    })


@router.get("/app-download")
def ypay_app_download():
    import os
    apk_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static", "ypay-monitor.apk")
    if not os.path.isfile(apk_path):
        return JSONResponse(status_code=404, content={"code": -1, "message": "APK 文件不存在"})
    from fastapi.responses import FileResponse
    return FileResponse(apk_path, media_type="application/vnd.android.package-archive", filename="ypay-monitor.apk")


@raw_router.get("/api/app/download-qr")
def app_download_qrcode(request: Request):
    """返回APK下载二维码图片（<img src> 直接用）"""
    site_url = _get_site_url()
    host = site_url.replace("http://", "").replace("https://", "").rstrip("/")
    is_domain = "." in host.split(":")[0] and not all(c in "0123456789." for c in host.split(":")[0])
    is_local = host.startswith("localhost") or host.startswith("127.0.0.1")
    if is_local:
        server_ip = _get_server_ip()
        port = host.split(":")[1] if ":" in host else str(settings.port or 8000)
        host = f"{server_ip}:{port}"
        download_url = f"http://{host}/api/ypay/app-download"
    elif is_domain:
        host = host.split(":")[0]
        download_url = f"https://{host}/api/ypay/app-download"
    else:
        download_url = f"http://{host}/api/ypay/app-download"
    qr_b64 = _make_qr_base64(download_url)
    # 如果是浏览器直接访问(img标签)，返回PNG图片；否则返回JSON
    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return ApiResponse(data={"qr_image": qr_b64, "download_url": download_url})
    if "text/html" in accept or "image/" in accept:
        import base64 as _b64

        from fastapi.responses import Response as _Response
        b64_data = qr_b64.split(",", 1)[1] if "," in (qr_b64 or "") else ""
        if b64_data:
            return _Response(content=_b64.b64decode(b64_data), media_type="image/png")
    return ApiResponse(data={"qr_image": qr_b64, "download_url": download_url})


# ============================================================
# 重置连接
# ============================================================

@raw_router.api_route("/appHeart", methods=["GET", "POST"], response_class=PlainTextResponse)
async def legacy_app_heart(request: Request):
    return await ypay_app_heart(request)


@raw_router.api_route("/appPush", methods=["GET", "POST"], response_class=PlainTextResponse)
async def legacy_app_push(request: Request):
    return await ypay_app_push(request)


# ============================================================
# 通道测试

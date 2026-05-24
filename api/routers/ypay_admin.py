import random
import string
import time
import uuid as _uuid
from datetime import datetime

from loguru import logger

try:
    from pyzbar.pyzbar import decode as qr_decode
except (ImportError, OSError, FileNotFoundError):
    qr_decode = None
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.auth import get_current_admin
from api.database import db
from api.models import ApiResponse
from api.services.ypay_service import ypay



router = APIRouter(prefix="/api/ypay", tags=["YPay管理"])

class AccountAddRequest(BaseModel):
    type: str = ""
    code: str = ""
    name: str = ""
    qr_url: str = ""
    zfb_pid: str = ""
    alipay_appid: str = ""
    alipay_public_key: str = ""
    alipay_private_key: str = ""
    cookie: str = ""
    wx_guid: str = ""
    qq: str = ""
    cloud_id: str = ""
    qr_type: str = ""
    memo: str = ""
    remark: str = ""
    app_public_cert: str = ""
    alipay_public_cert: str = ""
    alipay_root_cert: str = ""
    channel_mode: int = -1  # -1 表示不更新
    is_status: int = -1  # -1 表示不更新


@router.get("/accounts")
def list_accounts(admin: dict = Depends(get_current_admin)):
    return ApiResponse(data=db.ypay_list_accounts())


@router.post("/accounts")
def add_account(payload: AccountAddRequest, admin: dict = Depends(get_current_admin)):
    if not payload.type:
        return {"code": -1, "message": "请选择通道类型"}
    result = db.ypay_add_account(
        atype=payload.type,
        code=payload.code,
        name=payload.name,
        qr_url=payload.qr_url,
        zfb_pid=payload.zfb_pid,
        alipay_appid=payload.alipay_appid,
        alipay_public_key=payload.alipay_public_key,
        alipay_private_key=payload.alipay_private_key,
        cookie=payload.cookie,
        wx_guid=payload.wx_guid,
        qq=payload.qq,
        cloud_id=payload.cloud_id,
        qr_type=payload.qr_type,
        memo=payload.memo,
        remark=payload.remark,
        app_public_cert=payload.app_public_cert,
        alipay_public_cert=payload.alipay_public_cert,
        alipay_root_cert=payload.alipay_root_cert,
        channel_mode=payload.channel_mode if payload.channel_mode >= 0 else 1,
    )
    if not result:
        return {"code": -1, "message": "添加失败"}
    return ApiResponse(data=result, message="添加成功")


@router.put("/accounts/{account_id}")
def update_account(account_id: int, payload: AccountAddRequest, admin: dict = Depends(get_current_admin)):
    fields = {}
    if payload.type: fields["type"] = payload.type
    if payload.code: fields["code"] = payload.code
    if payload.name: fields["name"] = payload.name
    if payload.qr_url: fields["qr_url"] = payload.qr_url
    if payload.zfb_pid: fields["zfb_pid"] = payload.zfb_pid
    if payload.alipay_appid: fields["alipay_appid"] = payload.alipay_appid
    if payload.alipay_public_key: fields["alipay_public_key"] = payload.alipay_public_key
    if payload.alipay_private_key: fields["alipay_private_key"] = payload.alipay_private_key
    if payload.cookie: fields["cookie"] = payload.cookie
    if payload.wx_guid: fields["wx_guid"] = payload.wx_guid
    if payload.qq: fields["qq"] = payload.qq
    if payload.cloud_id: fields["cloud_id"] = payload.cloud_id
    if payload.qr_type: fields["qr_type"] = payload.qr_type
    if payload.memo: fields["memo"] = payload.memo
    if payload.remark: fields["remark"] = payload.remark
    if payload.app_public_cert: fields["app_public_cert"] = payload.app_public_cert
    if payload.alipay_public_cert: fields["alipay_public_cert"] = payload.alipay_public_cert
    if payload.alipay_root_cert: fields["alipay_root_cert"] = payload.alipay_root_cert
    if payload.channel_mode >= 0: fields["channel_mode"] = payload.channel_mode
    if payload.is_status >= 0: fields["is_status"] = payload.is_status
    if not fields:
        return {"code": -1, "message": "没有需要更新的字段"}
    ok = db.ypay_update_account(account_id, **fields)
    return ApiResponse(success=ok, message="更新成功" if ok else "更新失败")


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, admin: dict = Depends(get_current_admin)):
    ok = db.ypay_delete_account(account_id)
    return ApiResponse(success=ok, message="删除成功" if ok else "删除失败")


@router.get("/orders")
def list_orders(limit: int = 20, page: int = 1, status: Optional[int] = None, admin: dict = Depends(get_current_admin)):
    offset = (page - 1) * limit
    orders = db.ypay_list_orders(limit=limit, offset=offset, status=status)
    total = db.ypay_count_orders(status=status)
    return ApiResponse(data={"items": orders, "total": total})


@router.post("/close-expired")
def close_expired(admin: dict = Depends(get_current_admin)):
    count = db.ypay_close_expired_orders()
    return ApiResponse(data={"closed": count}, message=f"已关闭 {count} 个过期订单")


@router.post("/clear-orders", response_model=ApiResponse)
def clear_ypay_orders(admin: dict = Depends(get_current_admin)):
    count = db.clear_ypay_orders()
    return ApiResponse(message=f"已清除 {count} 条支付订单")


@router.get("/status")
def ypay_status(admin: dict = Depends(get_current_admin)):
    monitor_status = db.ypay_setting_get("monitor_status", "offline")
    monitor_heart = db.ypay_setting_get("monitor_last_heart", "")

    seconds_ago = -1
    is_online = False
    if monitor_heart:
        try:
            last = datetime.fromisoformat(monitor_heart)
            delta = (datetime.now().replace(tzinfo=None) - last.replace(tzinfo=None)).total_seconds()
            seconds_ago = int(delta)
            is_online = seconds_ago <= 180
        except Exception as e:
            pass

    sign_fail = int(db.ypay_setting_get("sign_fail_count", "0"))
    status_display = "online" if is_online else "offline"
    if sign_fail >= 3 and not is_online:
        status_display = "key_mismatch"

    return ApiResponse(data={
        "is_online": is_online,
        "seconds_ago": seconds_ago,
        "monitor_status": status_display,
        "monitor_last_heart": monitor_heart,
        "monitor_ip": db.ypay_setting_get("monitor_ip", ""),
        "total_orders": db.ypay_count_orders(),
        "pending_orders": db.ypay_count_orders(status=0),
        "paid_orders": db.ypay_count_orders(status=1),
        "sign_fail_count": sign_fail,
    })


@router.get("/test")
def ypay_test(admin: dict = Depends(get_current_admin)):
    results = []
    all_ok = True

    key = db.ypay_setting_get("key", "")
    if key:
        results.append({"name": "通讯密钥", "ok": True, "msg": "已配置"})
    else:
        results.append({"name": "通讯密钥", "ok": False, "msg": "未设置"})
        all_ok = False

    accounts = db.ypay_list_accounts()
    wx_count = sum(1 for a in accounts if a["type"] == "wxpay" and a["is_status"] == 1)
    ali_count = sum(1 for a in accounts if a["type"] == "alipay" and a["is_status"] == 1)
    qq_count = sum(1 for a in accounts if a["type"] == "qqpay" and a["is_status"] == 1)
    lkl_count = sum(1 for a in accounts if a["type"] == "lkl" and a["is_status"] == 1)
    usdt_count = sum(1 for a in accounts if a["type"] == "usdt" and a["is_status"] == 1)
    total_active = wx_count + ali_count + qq_count + lkl_count + usdt_count

    if total_active > 0:
        parts = []
        if wx_count: parts.append(f"微信 {wx_count}")
        if ali_count: parts.append(f"支付宝 {ali_count}")
        if qq_count: parts.append(f"QQ {qq_count}")
        if lkl_count: parts.append(f"拉卡拉 {lkl_count}")
        if usdt_count: parts.append(f"USDT {usdt_count}")
        results.append({"name": "收款通道", "ok": True, "msg": "，".join(parts) + " 个"})
    else:
        results.append({"name": "收款通道", "ok": False, "msg": "未添加任何收款通道"})
        all_ok = False

    monitor_heart = db.ypay_setting_get("monitor_last_heart", "")
    if monitor_heart:
        try:
            last = datetime.fromisoformat(monitor_heart)
            delta = (datetime.now().replace(tzinfo=None) - last.replace(tzinfo=None)).total_seconds()
            if delta <= 180:
                results.append({"name": "监控端连接", "ok": True, "msg": f"在线（{int(delta)}秒前）"})
            else:
                results.append({"name": "监控端连接", "ok": False, "msg": f"离线（{int(delta // 60)}分钟前）"})
                all_ok = False
        except Exception as e:
            results.append({"name": "监控端连接", "ok": False, "msg": "无法解析"})
            all_ok = False
    else:
        results.append({"name": "监控端连接", "ok": False, "msg": "从未连接"})
        all_ok = False

    return ApiResponse(data={
        "all_ok": all_ok,
        "checks": results,
        "summary": "所有检查通过" if all_ok else "存在配置问题",
    })


# ============================================================
# 配置管理
# ============================================================

@router.get("/config/get")
def ypay_config_get(admin: dict = Depends(get_current_admin)):
    cfg = db.ypay_setting_all()
    cfg["key_set"] = bool(cfg.get("key", ""))
    return ApiResponse(data=cfg)


class ConfigSaveRequest(BaseModel):
    key: Optional[str] = None
    close_time: Optional[str] = None
    pay_timeout: Optional[str] = None
    site_url: Optional[str] = None


@router.post("/config/save")
def ypay_config_save(payload: ConfigSaveRequest, admin: dict = Depends(get_current_admin)):
    if payload.key is not None:
        old_key = db.ypay_setting_get("key", "")
        if payload.key and payload.key != old_key:
            db.ypay_setting_set("key", payload.key)
            db.ypay_setting_set("sign_fail_count", "0")
            db.ypay_setting_set("sign_fail_time", "")
            db.ypay_setting_set("monitor_status", "offline")
            db.ypay_setting_set("monitor_last_heart", "")
            db.ypay_setting_set("heart_history", "")
            logger.info("ypay_key_changed_monitor_reset")
    if payload.close_time is not None:
        db.ypay_setting_set("close_time", payload.close_time)
    if payload.pay_timeout is not None:
        db.ypay_setting_set("pay_timeout", payload.pay_timeout)
    if payload.site_url is not None:
        db.ypay_setting_set("site_url", payload.site_url)
    return ApiResponse(message="配置已保存")


# ============================================================
# 密钥重新生成
# ============================================================

@router.post("/regenerate-key")
def ypay_regenerate_key(admin: dict = Depends(get_current_admin)):
    new_key = "".join(random.choices(string.ascii_letters + string.digits, k=16))
    db.ypay_setting_set("key", new_key)
    db.ypay_setting_set("sign_fail_count", "0")
    db.ypay_setting_set("sign_fail_time", "")
    db.ypay_setting_set("monitor_status", "offline")
    db.ypay_setting_set("monitor_last_heart", "")
    db.ypay_setting_set("heart_history", "")
    logger.info("ypay_key_regenerated")
    return ApiResponse(data={"key": new_key}, message="密钥已重新生成")


# ============================================================
# APP 心跳 (兼容 GET+POST, 兼容 VMQ 签名格式)

@router.post("/reset-connection")
def ypay_reset_connection(admin: dict = Depends(get_current_admin)):
    db.ypay_setting_set("sign_fail_count", "0")
    db.ypay_setting_set("sign_fail_time", "")
    db.ypay_setting_set("monitor_status", "offline")
    db.ypay_setting_set("monitor_last_heart", "")
    db.ypay_setting_set("heart_history", "")
    logger.info("ypay_connection_reset")
    return ApiResponse(message="连接状态已重置")


# ============================================================
# 诊断测试
# ============================================================

@router.get("/diagnose")
def ypay_diagnose(admin: dict = Depends(get_current_admin)):
    results = []
    all_ok = True

    key = db.ypay_setting_get("key", "")
    if key:
        results.append({"name": "通讯密钥", "ok": True, "msg": f"已配置（{len(key)}位）"})
    else:
        results.append({"name": "通讯密钥", "ok": False, "msg": "未设置"})
        all_ok = False

    accounts = db.ypay_list_accounts()
    wx_count = sum(1 for a in accounts if a["type"] == "wxpay" and a["is_status"] == 1)
    ali_count = sum(1 for a in accounts if a["type"] == "alipay" and a["is_status"] == 1)
    lkl_count = sum(1 for a in accounts if a["type"] == "lkl" and a["is_status"] == 1)
    total_active = wx_count + ali_count + lkl_count
    if total_active > 0:
        parts = []
        if wx_count: parts.append(f"微信 {wx_count}")
        if ali_count: parts.append(f"支付宝 {ali_count}")
        if lkl_count: parts.append(f"拉卡拉 {lkl_count}")
        results.append({"name": "收款通道", "ok": True, "msg": "，".join(parts) + " 个"})
    else:
        results.append({"name": "收款通道", "ok": False, "msg": "未添加任何收款通道"})
        all_ok = False

    monitor_heart = db.ypay_setting_get("monitor_last_heart", "")
    if monitor_heart:
        try:
            last = datetime.fromisoformat(monitor_heart)
            delta = (datetime.now().replace(tzinfo=None) - last.replace(tzinfo=None)).total_seconds()
            if delta <= 180:
                results.append({"name": "监控端连接", "ok": True, "msg": f"在线（{int(delta)}秒前）"})
            else:
                results.append({"name": "监控端连接", "ok": False, "msg": f"离线（{int(delta // 60)}分钟前）"})
                all_ok = False
        except Exception as e:
            results.append({"name": "监控端连接", "ok": False, "msg": "无法解析"})
            all_ok = False
    else:
        results.append({"name": "监控端连接", "ok": False, "msg": "从未连接"})
        all_ok = False

    history = db.ypay_setting_get("heart_history", "")
    if history:
        entries = [e for e in history.split(",") if e]
        ok_count = sum(1 for e in entries if e.endswith(":ok"))
        total = len(entries)
        rate = round(ok_count / total * 100) if total > 0 else 0
        results.append({"name": "心跳健康率", "ok": rate >= 80, "msg": f"{rate}%（{ok_count}/{total}）"})
    else:
        results.append({"name": "心跳健康率", "ok": False, "msg": "无数据"})

    return ApiResponse(data={
        "all_ok": all_ok,
        "checks": results,
        "monitor_status": db.ypay_setting_get("monitor_status", "offline"),
        "sign_fail_count": int(db.ypay_setting_get("sign_fail_count", "0")),
        "monitor_ip": db.ypay_setting_get("monitor_ip", ""),
    })


# ============================================================
# 根路径兼容端点 (raw_router) - VMQ 协议兼容
# ============================================================

@router.post("/channel-test/{account_id}")
def channel_test(account_id: int, admin: dict = Depends(get_current_admin)):
    """测试指定通道的配置是否正确，生成测试二维码"""
    accounts = db.ypay_list_accounts()
    account = next((a for a in accounts if a["id"] == account_id), None)
    if not account:
        return {"code": -1, "message": "通道不存在"}

    checks = []
    code = account.get("code", "")
    atype = account.get("type", "")
    qr_url = account.get("qr_url", "")
    zfb_pid = account.get("zfb_pid", "")

    # 基本检查
    checks.append({"name": "通道类型", "ok": bool(atype), "msg": atype or "未设置"})
    checks.append({"name": "通道代码", "ok": bool(code), "msg": code or "未设置"})
    checks.append({"name": "启用状态", "ok": account.get("is_status") == 1, "msg": "已启用" if account.get("is_status") == 1 else "已停用"})

    # 按通道类型检查必要配置
    if code in ("alipay_dmf", "alipay_official"):
        appid = account.get("alipay_appid", "")
        priv = account.get("alipay_private_key", "")
        pub = account.get("alipay_public_key", "")
        app_cert = account.get("app_public_cert", "")
        checks.append({"name": "APPID", "ok": bool(appid), "msg": appid[:8] + "..." if appid else "未配置"})
        checks.append({"name": "应用私钥", "ok": bool(priv), "msg": "已配置" if priv else "未配置"})
        if app_cert:
            checks.append({"name": "签名模式", "ok": True, "msg": "证书模式"})
            checks.append({"name": "应用公钥证书", "ok": bool(app_cert), "msg": "已配置" if app_cert else "未配置"})
            checks.append({"name": "支付宝公钥证书", "ok": bool(account.get("alipay_public_cert", "")), "msg": "已配置" if account.get("alipay_public_cert") else "未配置"})
            checks.append({"name": "支付宝根证书", "ok": bool(account.get("alipay_root_cert", "")), "msg": "已配置" if account.get("alipay_root_cert") else "未配置"})
        else:
            checks.append({"name": "签名模式", "ok": bool(pub), "msg": "普通公钥模式" if pub else "未配置"})
            checks.append({"name": "支付宝公钥", "ok": bool(pub), "msg": "已配置" if pub else "未配置"})
    elif code in ("alipay_software", "alipay_grmg", "alipay_mck"):
        checks.append({"name": "收款码", "ok": bool(qr_url), "msg": "已配置" if qr_url else "未配置"})
    elif zfb_pid or atype == "alipay":
        checks.append({"name": "支付宝PID", "ok": bool(zfb_pid), "msg": zfb_pid[:8] + "..." if zfb_pid else "未配置"})
        checks.append({"name": "收款码", "ok": bool(qr_url), "msg": "已配置" if qr_url else "未配置"})
    elif atype == "wxpay":
        checks.append({"name": "收款码/URL", "ok": bool(qr_url), "msg": "已配置" if qr_url else "未配置"})
        if code == "wxpay_dy":
            wxname = account.get("wx_guid", "")
            checks.append({"name": "店员微信", "ok": bool(wxname), "msg": wxname or "未配置"})
        elif code in ("wxpay_cloud", "wxpay_jym_cloud"):
            cloud_id = account.get("cloud_id", "")
            checks.append({"name": "云端ID", "ok": bool(cloud_id), "msg": cloud_id or "未配置"})
    elif atype == "lkl":
        remark = account.get("remark", "") or account.get("memo", "")
        checks.append({"name": "Authorization令牌", "ok": bool(remark), "msg": "已配置" if remark else "未配置"})
        checks.append({"name": "商户名称", "ok": bool(account.get("name", "")), "msg": account.get("name", "") or "未配置"})
    elif code in ("dougong_alipay", "dougong_wxpay"):
        checks.append({"name": "斗拱插件", "ok": bool(qr_url), "msg": "已配置" if qr_url else "未配置"})
    elif code in ("lebrush_alipay", "lebrush_wxpay"):
        checks.append({"name": "乐刷插件", "ok": bool(qr_url), "msg": "已配置" if qr_url else "未配置"})

    # 尝试生成测试二维码
    test_trade_no = f"TEST{int(time.time())}"
    try:
        qrcode_content, h5_url = ypay._generate_qrcode(account, 0.01, test_trade_no, "TEST")
        qr_ok = bool(qrcode_content)
        checks.append({"name": "QR码生成", "ok": qr_ok, "msg": "成功" if qr_ok else "失败"})
    except Exception as e:
        qrcode_content = ""
        h5_url = ""
        checks.append({"name": "QR码生成", "ok": False, "msg": str(e)[:50]})

    # 生成二维码图片
    qr_image = None
    if qrcode_content:
        qr_image = _make_qr_base64(qrcode_content)

    all_ok = all(c["ok"] for c in checks)

    return ApiResponse(data={
        "checks": checks,
        "all_ok": all_ok,
        "qr_image": qr_image,
        "qrcode_content": qrcode_content[:200] if qrcode_content else "",
        "h5_url": h5_url[:200] if h5_url else "",
    })


# ============================================================
# 支付测试（按通道）
# ============================================================

_CODE_PAY_TYPE = {
    "wxpay_dy": 1, "wxpay_software": 1, "wxpay_cloud": 1,
    "wxpay_jym_cloud": 1, "wxpay_skd": 1, "wxpay_cloudzs": 1,
    "alipay_software": 2, "alipay_grmg": 2, "alipay_mck": 2,
    "alipay_dmf": 2, "alipay_official": 2,
    "lkl_wxpay": 1, "lkl_alipay": 2,
    "dougong_wxpay": 1, "dougong_alipay": 2,
    "lebrush_wxpay": 1, "lebrush_alipay": 2,
}


@router.post("/pay-test/create/{account_id}")
def ypay_pay_test_create(account_id: int, admin: dict = Depends(get_current_admin)):
    accounts = db.ypay_list_accounts()
    account = next((a for a in accounts if a["id"] == account_id), None)
    if not account:
        return {"code": -1, "message": "通道不存在"}

    batch_id = f"TEST-{_uuid.uuid4().hex[:8].upper()}"
    price = round(random.uniform(0.01, 0.10), 2)

    code = account.get("code", "")
    atype = account.get("type", "wxpay")
    pay_type = _CODE_PAY_TYPE.get(code, 1 if atype == "wxpay" else 2)
    type_str = "alipay" if code in ("lkl_alipay", "dougong_alipay", "lebrush_alipay") or atype == "alipay" else "wxpay"

    from datetime import timedelta
    trade_no = f"PT{int(time.time())}{_uuid.uuid4().hex[:6].upper()}"
    out_time = (datetime.now() + timedelta(seconds=300)).isoformat()

    try:
        qrcode_content, h5_url = ypay._generate_qrcode(account, price, trade_no, batch_id)
    except Exception as e:
        logger.error(f"pay_test_qr_error error={str(e)}")
        return {"code": -1, "message": f"生成测试二维码失败: {str(e)[:80]}"}

    if not qrcode_content:
        return {"code": -1, "message": "生成测试二维码失败，请检查通道配置"}

    order = db.ypay_create_order(
        trade_no=trade_no, out_trade_no=batch_id, pay_type=pay_type,
        type_str=type_str, name="支付测试", money=price, truemoney=price,
        account_id=account_id, qrcode=qrcode_content, h5_qrurl=h5_url or "",
        notify_url="", return_url="", ip="", out_time=out_time,
    )
    if not order:
        return {"code": -1, "message": "创建测试订单失败"}

    qr_image = _make_qr_base64(qrcode_content)

    return ApiResponse(data={
        "batch_id": batch_id,
        "trade_no": trade_no,
        "really_price": price,
        "qr_image": qr_image,
    })


@router.get("/pay-test/check/{batch_id}")
def ypay_pay_test_check(batch_id: str, trade_no: str = Query(""), admin: dict = Depends(get_current_admin)):
    if trade_no:
        order = db.ypay_get_order(trade_no)
        if order and order["status"] == 1:
            return ApiResponse(data={"paid": True, "message": "支付成功"})
    order = db.ypay_get_order_by_out_trade_no(batch_id)
    if order and order["status"] == 1:
        return ApiResponse(data={"paid": True, "message": "支付成功"})
    return ApiResponse(data={"paid": False, "message": "等待支付"})
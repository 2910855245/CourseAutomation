"""YPay 各支付渠道 QR 码生成逻辑。

从 ypay_service.py 提取，保持每个渠道的生成方法独立可维护。
"""

import hashlib
import json
import re
import urllib.parse
from typing import Any, Dict, Optional, Tuple

from loguru import logger



def _hash_md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _detect_qr_content_type(content: str) -> str:
    if not content:
        return "raw"
    c = content.strip()
    if c.startswith("data:image/"):
        return "image_url"
    if re.match(r'https?://.*\.(png|jpg|jpeg|gif|webp)(\?.*)?$', c, re.IGNORECASE):
        return "image_url"
    if c.startswith("wxp://") or "wx.tenpay.com" in c:
        return "wxpay"
    if (c.startswith("https://qr.alipay.com/") or
        c.startswith("alipays://") or
        "render.alipay.com" in c):
        return "alipay"
    if c.startswith("http://") or c.startswith("https://"):
        return "url"
    return "raw"


def _wx_h5(url: str) -> str:
    if not url:
        return ""
    if url.startswith("wxp://"):
        return ""
    return url


# ─────────────────────────────────────────────
# 主入口：根据 channel code 分发到对应生成器
# ─────────────────────────────────────────────

def generate_qrcode(account: Dict[str, Any], money: float,
                    trade_no: str, out_trade_no: str,
                    get_site_url: callable) -> Tuple[str, str]:
    code = account.get("code", "")

    if code == "wxpay_dy":
        return _gen_wxpay_store_qr(account)
    if code == "wxpay_software":
        return _gen_wxpay_software_qr(account)
    if code == "wxpay_cloudzs":
        return _gen_wxpay_tip_qr(account)
    if code == "wxpay_cloud":
        return _gen_wxpay_cloud_qr(account, money, trade_no)
    if code == "wxpay_jym_cloud":
        return _gen_wxpay_jym_qr(account, money, trade_no)
    if code == "wxpay_skd":
        return _gen_wxpay_receipt_qr(account, money, trade_no)

    if code == "alipay_software":
        return _gen_alipay_software_qr(account)
    if code in ("alipay_grmg", "alipay_mck"):
        return _gen_alipay_transfer_qr(account, money, out_trade_no)
    if code == "alipay_dmf":
        return _gen_alipay_f2f_qr(account, money, out_trade_no, get_site_url)
    if code == "alipay_official":
        return _gen_alipay_official_qr(account, money, out_trade_no, get_site_url)

    if code in ("lkl_alipay", "lkl_wxpay"):
        return _gen_lkl_qrcode(account, money, out_trade_no)
    if code in ("dougong_alipay", "dougong_wxpay"):
        return _gen_dougong_qrcode(account, code)
    if code in ("lebrush_alipay", "lebrush_wxpay"):
        return _gen_lebrush_qrcode(account, code)

    # Fallback
    qr_url = account.get("qr_url", "")
    if qr_url:
        if "wxpay" in code:
            return qr_url, _wx_h5(qr_url)
        return qr_url, qr_url
    logger.warning(f"ypay_unknown_channel code={code}")
    return "", ""


# ─────────────────────────────────────────────
# 微信通道
# ─────────────────────────────────────────────

def _gen_wxpay_store_qr(account: Dict) -> Tuple[str, str]:
    qr_url = account.get("qr_url", "").strip()
    if not qr_url:
        logger.warning(f"wxpay_dy_no_qr_url account_id={account.get('id')}")
        return "", ""
    return qr_url, _wx_h5(qr_url)


def _gen_wxpay_software_qr(account: Dict) -> Tuple[str, str]:
    qr_url = account.get("qr_url", "").strip()
    if not qr_url:
        logger.warning(f"wxpay_software_no_qr_url account_id={account.get('id')}")
        return "", ""
    return qr_url, _wx_h5(qr_url)


def _gen_wxpay_tip_qr(account: Dict) -> Tuple[str, str]:
    raw = account.get("qr_url", "").strip()
    if not raw:
        return "", ""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            inner = data.get("qr_url", "") or data.get("url", "") or data.get("code_url", "")
            if inner:
                return inner, _wx_h5(inner)
    except (json.JSONDecodeError, TypeError):
        pass
    return raw, _wx_h5(raw)


def _gen_wxpay_cloud_qr(account: Dict, money: float, trade_no: str) -> Tuple[str, str]:
    cloud_id = account.get("cloud_id", "")
    qr_url = account.get("qr_url", "").strip()
    if cloud_id:
        dynamic_url = _call_wxpay_cloud_api(cloud_id, money, trade_no)
        if dynamic_url:
            return dynamic_url, _wx_h5(dynamic_url)
        logger.warning(f"wxpay_cloud_api_failed cloud_id={cloud_id} trade_no={trade_no}")
    if qr_url:
        return qr_url, _wx_h5(qr_url)
    logger.warning(f"wxpay_cloud_no_qr account_id={account.get('id')}")
    return "", ""


def _gen_wxpay_jym_qr(account: Dict, money: float, trade_no: str) -> Tuple[str, str]:
    cloud_id = account.get("cloud_id", "")
    qr_url = account.get("qr_url", "").strip()
    if cloud_id:
        dynamic_url = _call_wxpay_cloud_api(cloud_id, money, trade_no)
        if dynamic_url:
            return dynamic_url, _wx_h5(dynamic_url)
        logger.warning(f"wxpay_jym_api_failed cloud_id={cloud_id} trade_no={trade_no}")
    if qr_url:
        return qr_url, _wx_h5(qr_url)
    logger.warning(f"wxpay_jym_no_qr account_id={account.get('id')}")
    return "", ""


def _gen_wxpay_receipt_qr(account: Dict, money: float, trade_no: str) -> Tuple[str, str]:
    receipt_url = _call_wxpay_receipt_api(account, money, trade_no)
    if receipt_url:
        return receipt_url, _wx_h5(receipt_url)
    qr_url = account.get("qr_url", "").strip()
    if qr_url:
        return qr_url, _wx_h5(qr_url)
    logger.warning(f"wxpay_skd_no_qr account_id={account.get('id')}")
    return "", ""


def _call_wxpay_cloud_api(cloud_id: str, money: float, trade_no: str) -> Optional[str]:
    # TODO: 实现云端API对接
    return None


def _call_wxpay_receipt_api(account: Dict, money: float, trade_no: str) -> Optional[str]:
    # TODO: 实现收款单API对接
    return None


# ─────────────────────────────────────────────
# 支付宝通道
# ─────────────────────────────────────────────

def _gen_alipay_software_qr(account: Dict) -> Tuple[str, str]:
    qr_url = account.get("qr_url", "").strip()
    if not qr_url:
        logger.warning(f"alipay_software_no_qr_url account_id={account.get('id')}")
        return "", ""
    return qr_url, "alipays://"


def _gen_alipay_transfer_qr(account: Dict, money: float, out_trade_no: str) -> Tuple[str, str]:
    zfb_pid = account.get("zfb_pid", "")
    if not zfb_pid:
        qr_url = account.get("qr_url", "")
        return (qr_url, "alipays://") if qr_url else ("", "")

    channel_mode = account.get("channel_mode", 1)
    amount = str(money)

    if channel_mode == 1:
        transfer_url = (
            f"alipays://platformapi/startapp?appId=20000116"
            f"&actionType=toAccount&goBack=NO"
            f"&amount={amount}&userId={zfb_pid}&memo={out_trade_no}"
        )
    elif channel_mode == 2:
        transfer_url = (
            f"alipays://platformapi/startapp?appId=20000116"
            f"&actionType=toAccount&goBack=NO"
            f"&amount={amount}&userId={zfb_pid}"
        )
    elif channel_mode == 3:
        transfer_url = (
            f"alipays://platformapi/startapp?appId=20000116"
            f"&actionType=toAccount&goBack=NO"
            f"&userId={zfb_pid}"
        )
    else:
        from config import settings
        app_url = settings.site_url or "http://localhost:8000"
        transfer_url = (
            f"{app_url}/alipayTransfer.php?"
            f"amount={amount}&remark={out_trade_no}&payeeId={zfb_pid}"
        )

    qr_content = urllib.parse.quote(
        f"https://render.alipay.com/p/c/mdeduct-landing?"
        f"scheme={urllib.parse.quote(transfer_url, safe='')}"
    )
    h5_url = f"alipays://platformapi/startapp?appId=20000067&url={qr_content}"
    return qr_content, h5_url


def _gen_alipay_f2f_qr(account: Dict, money: float, out_trade_no: str,
                       get_site_url: callable) -> Tuple[str, str]:
    result = _call_alipay_sdk(account, money, out_trade_no, "precreate", get_site_url)
    if result:
        return result
    fallback = account.get("qr_url", "")
    return (fallback, "alipays://") if fallback else ("", "")


def _gen_alipay_official_qr(account: Dict, money: float, out_trade_no: str,
                            get_site_url: callable) -> Tuple[str, str]:
    result = _call_alipay_sdk(account, money, out_trade_no, "page_pay", get_site_url)
    if result:
        return result
    fallback = account.get("qr_url", "")
    return (fallback, "alipays://") if fallback else ("", "")


def _call_alipay_sdk(account: Dict, money: float, out_trade_no: str,
                     mode: str, get_site_url: callable) -> Optional[Tuple[str, str]]:
    try:
        from alipay import AliPay, DCAliPay

        def _ensure_pem(key: str, kind: str) -> str:
            key = (key or "").strip()
            if not key:
                return key
            begin_marker = f"-----BEGIN {kind} KEY-----"
            end_marker = f"-----END {kind} KEY-----"
            if "-----BEGIN" in key:
                return key
            return f"{begin_marker}\n{key}\n{end_marker}"

        app_id = account.get("alipay_appid", "")
        private_key = _ensure_pem(account.get("alipay_private_key", ""), "PRIVATE")
        alipay_public_key = _ensure_pem(account.get("alipay_public_key", ""), "PUBLIC")

        if not app_id or not private_key:
            return None

        site_url = get_site_url()
        notify_url = f"{site_url}/api/payment/notify"

        app_public_cert = account.get("app_public_cert", "")
        if app_public_cert:
            if not account.get("alipay_public_cert") or not account.get("alipay_root_cert"):
                logger.warning("alipay_cert_incomplete msg=证书模式需要三份证书文件，缺少支付宝公钥证书或根证书")
                return None
            alipay = DCAliPay(
                appid=app_id,
                app_notify_url=notify_url,
                app_private_key_string=private_key,
                app_public_key_cert_string=app_public_cert,
                alipay_public_key_cert_string=account.get("alipay_public_cert", ""),
                alipay_root_cert_string=account.get("alipay_root_cert", ""),
                sign_type="RSA2",
                debug=False,
            )
        else:
            if not alipay_public_key:
                return None
            alipay = AliPay(
                appid=app_id,
                app_notify_url=notify_url,
                app_private_key_string=private_key,
                alipay_public_key_string=alipay_public_key,
                sign_type="RSA2",
                debug=False,
            )

        if mode == "precreate":
            result = alipay.api_alipay_trade_precreate(
                out_trade_no=out_trade_no,
                total_amount=money,
                subject=f"订单-{out_trade_no}",
                notify_url=notify_url,
            )
            if result.get("code") == "10000":
                return result.get("qr_code", ""), "alipays://"

        elif mode == "page_pay":
            return_url = f"{site_url}/#/orders"
            order_string = alipay.api_alipay_trade_page_pay(
                out_trade_no=out_trade_no,
                total_amount=money,
                subject=f"订单-{out_trade_no}",
                return_url=return_url,
                notify_url=notify_url,
            )
            if order_string:
                pay_url = "https://openapi.alipay.com/gateway.do?" + order_string
                return pay_url, pay_url

    except ImportError:
        logger.warning("alipay_sdk_not_installed msg=pip install python-alipay-sdk")
    except Exception as e:
        logger.error(f"alipay_sdk_error error={str(e)}")
    return None


# ─────────────────────────────────────────────
# 拉卡拉通道
# ─────────────────────────────────────────────

def _gen_lkl_qrcode(account: Dict, money: float, out_trade_no: str) -> Tuple[str, str]:
    import httpx
    auth_token = account.get("remark", "") or account.get("memo", "")
    if not auth_token:
        logger.warning(f"lkl_no_auth_token account_id={account.get('id')}")
        return "", ""

    amount_fen = int(round(money * 100))
    payload = {
        "amount": amount_fen,
        "orderNo": out_trade_no,
        "shopName": account.get("name", "支付"),
    }
    headers = {
        "Authorization": auth_token,
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0)) as client:
            resp = client.post(
                "https://wallet.lakala.com/m/a/code/generate",
                json=payload,
                headers=headers,
            )
            data = resp.json()
            if data.get("retCode") == "000000":
                url = data.get("respData", {}).get("url", "")
                if url:
                    return url, url
            logger.warning(f"lkl_api_error retCode={data.get('retCode')} retMsg={data.get('retMsg')}")
    except Exception as e:
        logger.error(f"lkl_api_exception error={str(e)}")
    return "", ""


# ─────────────────────────────────────────────
# 第三方插件通道
# ─────────────────────────────────────────────

def _gen_dougong_qrcode(account: Dict, code: str) -> Tuple[str, str]:
    qr_url = account.get("qr_url", "")
    if "wxpay" in code:
        h5url = _wx_h5(qr_url) if qr_url else "weixin://"
    else:
        h5url = qr_url if qr_url else "alipays://"
    logger.info(f"dougong_plugin_fallback code={code}")
    return qr_url, h5url


def _gen_lebrush_qrcode(account: Dict, code: str) -> Tuple[str, str]:
    qr_url = account.get("qr_url", "")
    if "wxpay" in code:
        h5url = _wx_h5(qr_url) if qr_url else "weixin://"
    else:
        h5url = qr_url if qr_url else "alipays://"
    logger.info(f"lebrush_plugin_fallback code={code}")
    return qr_url, h5url

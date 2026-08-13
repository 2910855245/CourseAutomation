"""VMQ and YPay payment operations mixin"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update, func

from api.db._base import _db_logger

logger = _db_logger

# Lazy-loaded model references
_VmqSetting = _VmqPayOrder = _TmpPrice = _YpaySetting = _YpayTmpPrice = _YpayOrder = _YpayAccount = _Ad = None


def _resolve_models():
    global _VmqSetting, _VmqPayOrder, _TmpPrice, _YpaySetting, _YpayTmpPrice, _YpayOrder, _YpayAccount
    if _VmqSetting is None:
        from api.db.models import (
            TmpPrice,
            VmqPayOrder,
            VmqSetting,
            YpayAccount,
            YpayOrder,
            YpaySetting,
            YpayTmpPrice,
        )
        _VmqSetting, _VmqPayOrder, _TmpPrice, _YpaySetting, _YpayTmpPrice, _YpayOrder, _YpayAccount = VmqSetting, VmqPayOrder, TmpPrice, YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount
    return _VmqSetting, _VmqPayOrder, _TmpPrice, _YpaySetting, _YpayTmpPrice, _YpayOrder, _YpayAccount


class PaymentDBMixin:
    # ── VMQ 支付 ──












    def ypay_setting_get(self, key: str, default: str = "") -> str:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            s = session.scalars(select(YpaySetting).filter(YpaySetting.key == key)).first()
            return (s.value.strip() if s and s.value else default)
        finally:
            session.close()

    def ypay_setting_set(self, key: str, value: str):
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        value = (value or "").strip()
        session = self._get_session()
        try:
            session.merge(YpaySetting(key=key, value=value))
            session.commit()
        except Exception as e:
            logger.exception("ypay_setting_set 失败")
            session.rollback()
        finally:
            session.close()

    def ypay_setting_all(self) -> Dict[str, str]:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            return {s.key: s.value for s in session.scalars(select(YpaySetting)).all()}
        finally:
            session.close()

    def ypay_lock_price(self, price: float, oid: str) -> Optional[float]:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            from sqlalchemy.exc import IntegrityError
            now = datetime.now().isoformat()
            for _ in range(10):
                try:
                    t = YpayTmpPrice(price=price, oid=oid, create_time=now)
                    session.add(t)
                    session.flush()
                    session.commit()
                    return price
                except IntegrityError:
                    session.rollback()
                    price = round(price + 0.01, 2)
                except Exception as e:
                    logger.exception("ypay_lock_price 失败")
                    session.rollback()
                    return None
            return None
        finally:
            session.close()

    def ypay_release_price(self, price: float):
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            session.execute(delete(YpayTmpPrice).filter(YpayTmpPrice.price == price)).rowcount
            session.commit()
        except Exception as e:
            logger.exception("ypay_release_price 失败")
            session.rollback()
        finally:
            session.close()

    def ypay_get_active_prices(self, account_id: int) -> List[float]:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            now = datetime.now().isoformat()
            orders = session.scalars(select(YpayOrder.truemoney).filter(
                YpayOrder.account_id == account_id,
                YpayOrder.status == 0,
                YpayOrder.out_time > now,
            )).all()
            return list(orders)
        finally:
            session.close()

    def ypay_find_pending_by_price(self, price: float, pay_type: int) -> Optional[Dict[str, Any]]:
        from sqlalchemy import func as sqlfunc
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        type_str = {1: "wxpay", 2: "alipay", 3: "lkl"}.get(pay_type, "wxpay")
        session = self._get_session()
        try:
            o = session.scalars(select(YpayOrder).filter(
                sqlfunc.abs(YpayOrder.truemoney - price) < 0.01,
                YpayOrder.type == type_str,
                YpayOrder.status == 0,
            )).first()
            if not o:
                return None
            return self._ypay_order_to_dict(o)
        finally:
            session.close()

    def ypay_pick_channel(self, pay_type: int) -> Optional[Dict[str, Any]]:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        from api.db_engine import USE_MYSQL
        session = self._get_session()
        try:
            type_str = {1: "wxpay", 2: "alipay", 3: "lkl"}.get(pay_type, "wxpay")
            from sqlalchemy import delete, select, update, func as sqlfunc
            account = session.scalars(select(YpayAccount).filter(
                YpayAccount.type == type_str,
                YpayAccount.status == 1,
                YpayAccount.is_status == 1,
            ).order_by(sqlfunc.rand() if USE_MYSQL else sqlfunc.random())).first()
            if not account:
                return None
            return {
                "id": account.id,
                "type": account.type,
                "code": account.code,
                "name": account.name,
                "status": account.status,
                "is_status": account.is_status,
                "qr_url": account.qr_url,
                "zfb_pid": account.zfb_pid,
                "alipay_appid": account.alipay_appid,
                "alipay_public_key": account.alipay_public_key,
                "alipay_private_key": account.alipay_private_key,
                "cookie": account.cookie,
                "wx_guid": account.wx_guid,
                "qq": account.qq,
                "cloud_id": account.cloud_id,
                "qr_type": account.qr_type,
                "memo": account.memo,
                "remark": account.remark,
                "channel_mode": account.channel_mode,
                "app_public_cert": account.app_public_cert,
                "alipay_public_cert": account.alipay_public_cert,
                "alipay_root_cert": account.alipay_root_cert,
                "create_time": account.create_time,
            }
        finally:
            session.close()

    def ypay_create_order(self, *, trade_no: str, out_trade_no: str,
                          pay_type: int, type_str: str, name: str,
                          money: float, truemoney: float, account_id: int,
                          qrcode: str, h5_qrurl: str, notify_url: str,
                          return_url: str, ip: str, out_time: str) -> Optional[Dict[str, Any]]:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            now = datetime.now().isoformat()
            order = YpayOrder(
                type=type_str,
                account_id=account_id,
                trade_no=trade_no,
                out_trade_no=out_trade_no,
                name=name,
                money=money,
                truemoney=truemoney,
                qrcode=qrcode,
                h5_qrurl=h5_qrurl,
                status=0,
                notify_url=notify_url,
                return_url=return_url,
                ip=ip,
                create_time=now,
                out_time=out_time,
            )
            session.add(order)
            session.commit()
            return {
                "id": order.id,
                "trade_no": order.trade_no,
                "out_trade_no": order.out_trade_no,
                "type": order.type,
                "pay_type": pay_type,
                "name": order.name,
                "money": order.money,
                "truemoney": order.truemoney,
                "qrcode": order.qrcode,
                "h5_qrurl": order.h5_qrurl,
                "status": order.status,
                "account_id": order.account_id,
                "notify_url": order.notify_url,
                "return_url": order.return_url,
                "ip": order.ip,
                "create_time": order.create_time,
                "out_time": order.out_time,
                "end_time": order.end_time,
            }
        except Exception as e:
            logger.exception("ypay_create_order 失败")
            session.rollback()
            return None
        finally:
            session.close()

    def ypay_get_order(self, trade_no: str) -> Optional[Dict[str, Any]]:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            o = session.scalars(select(YpayOrder).filter(YpayOrder.trade_no == trade_no)).first()
            if not o:
                return None
            return self._ypay_order_to_dict(o)
        finally:
            session.close()

    def ypay_get_order_by_out_trade_no(self, out_trade_no: str) -> Optional[Dict[str, Any]]:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            o = session.scalars(select(YpayOrder).filter(YpayOrder.out_trade_no == out_trade_no)).first()
            if not o:
                return None
            return self._ypay_order_to_dict(o)
        finally:
            session.close()

    @staticmethod
    def _ypay_order_to_dict(o) -> Dict[str, Any]:
        return {
            "id": o.id,
            "trade_no": o.trade_no,
            "out_trade_no": o.out_trade_no,
            "type": o.type,
            "pay_type": {"wxpay": 1, "alipay": 2, "lkl": 3}.get(o.type, 1),
            "name": o.name,
            "money": o.money,
            "truemoney": o.truemoney,
            "qrcode": o.qrcode,
            "h5_qrurl": o.h5_qrurl,
            "status": o.status,
            "account_id": o.account_id,
            "notify_url": o.notify_url,
            "return_url": o.return_url,
            "ip": o.ip,
            "create_time": o.create_time,
            "out_time": o.out_time,
            "end_time": o.end_time,
        }

    def ypay_mark_paid(self, trade_no: str) -> bool:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            now = datetime.now().isoformat()
            o = session.scalars(select(YpayOrder).filter(YpayOrder.trade_no == trade_no)).first()
            if not o:
                return False
            o.status = 1
            o.end_time = now
            session.execute(delete(YpayTmpPrice).filter(YpayTmpPrice.oid == trade_no)).rowcount
            session.commit()
            return True
        except Exception as e:
            logger.exception("ypay_mark_paid 失败")
            session.rollback()
            return False
        finally:
            session.close()

    def ypay_close_expired_orders(self) -> int:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            now = datetime.now().isoformat()
            orders = session.scalars(select(YpayOrder).filter(
                YpayOrder.status == 0,
                YpayOrder.out_time < now,
            )).all()
            count = 0
            for o in orders:
                o.status = -1
                o.end_time = now
                session.execute(delete(YpayTmpPrice).filter(YpayTmpPrice.oid == o.trade_no)).rowcount
                count += 1
            session.commit()
            return count
        except Exception as e:
            logger.exception("ypay_close_expired_orders 失败")
            session.rollback()
            return 0
        finally:
            session.close()

    def clear_ypay_orders(self) -> int:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            from datetime import datetime
            count = session.execute(update(YpayOrder).filter(
                YpayOrder.status != 0,
                YpayOrder.deleted_at.is_(None),
            ).values(deleted_at=datetime.now().isoformat())).rowcount
            session.commit()
            return count
        except Exception as e:
            logger.exception("clear_ypay_orders 失败")
            session.rollback()
            return 0
        finally:
            session.close()

    def ypay_list_accounts(self) -> List[Dict[str, Any]]:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            accounts = session.scalars(select(YpayAccount).order_by(YpayAccount.create_time.desc())).all()
            return [
                {
                    "id": a.id, "type": a.type, "code": a.code, "name": a.name,
                    "status": a.status, "is_status": a.is_status, "qr_url": a.qr_url,
                    "zfb_pid": a.zfb_pid, "alipay_appid": a.alipay_appid,
                    "alipay_public_key": a.alipay_public_key, "alipay_private_key": a.alipay_private_key,
                    "cookie": a.cookie, "wx_guid": a.wx_guid, "qq": a.qq,
                    "cloud_id": a.cloud_id, "qr_type": a.qr_type, "memo": a.memo,
                    "remark": a.remark, "channel_mode": a.channel_mode,
                    "app_public_cert": a.app_public_cert, "alipay_public_cert": a.alipay_public_cert,
                    "alipay_root_cert": a.alipay_root_cert, "create_time": a.create_time,
                }
                for a in accounts
            ]
        finally:
            session.close()

    def ypay_add_account(self, *, atype: str, code: str, name: str = "",
                         qr_url: str = "", zfb_pid: str = "",
                         alipay_appid: str = "", alipay_public_key: str = "",
                         alipay_private_key: str = "", cookie: str = "",
                         wx_guid: str = "", qq: str = "", cloud_id: str = "",
                         qr_type: str = "", memo: str = "", remark: str = "",
                         channel_mode: int = 1,
                         app_public_cert: str = "", alipay_public_cert: str = "",
                         alipay_root_cert: str = "") -> Optional[Dict[str, Any]]:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            now = datetime.now().isoformat()
            acc = YpayAccount(
                type=atype, code=code, name=name, status=0, is_status=1,
                qr_url=qr_url, zfb_pid=zfb_pid, alipay_appid=alipay_appid,
                alipay_public_key=alipay_public_key, alipay_private_key=alipay_private_key,
                cookie=cookie, wx_guid=wx_guid, qq=qq, cloud_id=cloud_id,
                qr_type=qr_type, memo=memo, remark=remark, channel_mode=channel_mode,
                app_public_cert=app_public_cert, alipay_public_cert=alipay_public_cert,
                alipay_root_cert=alipay_root_cert, create_time=now,
            )
            session.add(acc)
            session.commit()
            return {
                "id": acc.id, "type": acc.type, "code": acc.code, "name": acc.name,
                "status": acc.status, "is_status": acc.is_status, "qr_url": acc.qr_url,
                "zfb_pid": acc.zfb_pid, "alipay_appid": acc.alipay_appid,
                "alipay_public_key": acc.alipay_public_key, "alipay_private_key": acc.alipay_private_key,
                "cookie": acc.cookie, "wx_guid": acc.wx_guid, "qq": acc.qq,
                "cloud_id": acc.cloud_id, "qr_type": acc.qr_type, "memo": acc.memo,
                "remark": acc.remark, "channel_mode": acc.channel_mode,
                "app_public_cert": acc.app_public_cert, "alipay_public_cert": acc.alipay_public_cert,
                "alipay_root_cert": acc.alipay_root_cert, "create_time": acc.create_time,
            }
        except Exception as e:
            logger.exception("ypay_add_account 失败")
            session.rollback()
            return None
        finally:
            session.close()

    def ypay_update_account(self, account_id: int, **fields) -> bool:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            count = session.execute(update(YpayAccount).filter(YpayAccount.id == account_id).values(fields)).rowcount
            session.commit()
            return count > 0
        except Exception as e:
            logger.exception("ypay_update_account 失败")
            session.rollback()
            return False
        finally:
            session.close()

    def ypay_delete_account(self, account_id: int) -> bool:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            from datetime import datetime
            count = session.execute(update(YpayAccount).filter(
                YpayAccount.id == account_id,
                YpayAccount.deleted_at.is_(None),
            ).values(deleted_at=datetime.now().isoformat())).rowcount
            session.commit()
            return count > 0
        except Exception as e:
            logger.exception("ypay_delete_account 失败")
            session.rollback()
            return False
        finally:
            session.close()

    def ypay_list_orders(self, limit: int = 50, offset: int = 0, status: int = None) -> List[Dict[str, Any]]:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            q = select(YpayOrder).order_by(YpayOrder.create_time.desc())
            if status is not None:
                q = q.where(YpayOrder.status == status)
            orders = session.scalars(q.offset(offset).limit(limit)).all()
            return [self._ypay_order_to_dict(o) for o in orders]
        finally:
            session.close()

    def ypay_count_orders(self, status: int = None) -> int:
        YpaySetting, YpayTmpPrice, YpayOrder, YpayAccount = _resolve_models()
        session = self._get_session()
        try:
            q = select(func.count(YpayOrder.id))
            if status is not None:
                q = q.where(YpayOrder.status == status)
            return session.scalar(q) or 0
        finally:
            session.close()

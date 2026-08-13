"""Order CRUD and statistics mixin"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, or_, select, update

from api.db._base import _db_logger
from api.utils import gen_id

logger = _db_logger

# Lazy-loaded model references
_Order = _User = _YpayOrder = None


def _resolve_models():
    global _Order, _User, _YpayOrder
    if _Order is None:
        from api.db.models import Order, User, YpayOrder
        _Order, _User, _YpayOrder = Order, User, YpayOrder
    return _Order, _User, _YpayOrder


def _order_to_dict(order) -> dict:
    import json

    return {
        "order_id": order.order_id,
        "out_trade_no": order.out_trade_no,
        "payment_trade_no": order.payment_trade_no,
        "payment_channel": order.payment_channel,
        "payment_time": order.payment_time,
        "paid_processed": order.paid_processed,
        "user_id": order.user_id,
        "customer_name": order.customer_name,
        "customer_contact": order.customer_contact,
        "username": order.username,
        "password": order.password,
        "website_id": order.website_id,
        "task_type": order.task_type,
        "course_ids": json.loads(order.course_ids) if isinstance(order.course_ids, str) else order.course_ids,
        "video_count": order.video_count,
        "exam_count": order.exam_count,
        "price": order.price,
        "notes": order.notes,
        "status": order.status,
        "paid": order.paid,
        "task_id": order.task_id,
        "admin_note": order.admin_note,
        "created_at": order.created_at,
        "updated_at": order.updated_at or "",
        "accepted_at": order.accepted_at,
        "started_at": order.started_at,
        "finished_at": order.finished_at,
    }


class OrderDBMixin:
    def create_order(self, *, customer_name="", customer_contact="",
                     username: str, password: str, website_id: int,
                     task_type="video", course_ids=None, video_count=50,
                     exam_count=0, price=0.0, notes="", user_id="") -> Dict[str, Any]:
        Order, User, YpayOrder = _resolve_models()
        order_id = gen_id("ORD")
        now = datetime.now().isoformat()
        session = self._get_session()
        try:
            order = Order(
                order_id=order_id,
                user_id=user_id or "",
                customer_name=customer_name,
                customer_contact=customer_contact,
                username=username,
                password=password,
                website_id=website_id,
                task_type=task_type,
                course_ids=json.dumps(course_ids or []),
                video_count=video_count,
                exam_count=exam_count,
                price=price,
                notes=notes,
                status="pending",
                created_at=now,
                updated_at=now,
            )
            session.add(order)
            session.commit()
            return self.get_order(order_id)
        except Exception as e:
            logger.exception("create_order 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        Order, User, YpayOrder = _resolve_models()
        session = self._get_session()
        try:
            order = session.scalars(select(Order).filter(Order.order_id == order_id)).first()
            return _order_to_dict(order) if order else None
        finally:
            session.close()

    def list_orders(self, status: Optional[str] = None,
                    user_id: Optional[str] = None,
                    search: Optional[str] = None,
                    sort_by: str = "created_at",
                    sort_dir: str = "desc",
                    limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        Order, User, YpayOrder = _resolve_models()
        _ALLOWED_SORT_FIELDS = {
            "created_at", "updated_at", "price", "status", "username",
            "customer_name", "order_id", "finished_at", "payment_time",
        }
        session = self._get_session()
        try:
            stmt = select(Order)
            if status:
                stmt = stmt.where(Order.status == status)
            if user_id:
                stmt = stmt.where(Order.user_id == user_id)
            if search:
                like = f"%{search}%"
                stmt = stmt.where(
                    or_(Order.username.like(like),
                        Order.customer_name.like(like),
                        Order.order_id.like(like))
                )
            if sort_by not in _ALLOWED_SORT_FIELDS:
                sort_by = "created_at"
            col = getattr(Order, sort_by)
            if sort_dir == "asc":
                stmt = stmt.order_by(col.asc())
            else:
                stmt = stmt.order_by(col.desc())
            stmt = stmt.offset(offset).limit(limit)
            return [_order_to_dict(o) for o in session.scalars(stmt).all()]
        finally:
            session.close()

    def count_orders(self, status: Optional[str] = None,
                     user_id: Optional[str] = None,
                     search: Optional[str] = None) -> int:
        Order, User, YpayOrder = _resolve_models()
        session = self._get_session()
        try:
            stmt = select(func.count(Order.order_id))
            if status:
                stmt = stmt.where(Order.status == status)
            if user_id:
                stmt = stmt.where(Order.user_id == user_id)
            if search:
                like = f"%{search}%"
                stmt = stmt.where(
                    or_(Order.username.like(like),
                        Order.customer_name.like(like),
                        Order.order_id.like(like))
                )
            return session.scalar(stmt)
        finally:
            session.close()

    def update_order(self, order_id: str, **fields) -> bool:
        Order, User, YpayOrder = _resolve_models()
        if not fields:
            return False
        if "course_ids" in fields and isinstance(fields["course_ids"], list):
            fields["course_ids"] = json.dumps(fields["course_ids"])
        fields["updated_at"] = datetime.now().isoformat()
        session = self._get_session()
        try:
            count = session.execute(update(Order).filter(Order.order_id == order_id).values(**fields)).rowcount
            session.commit()
            return count > 0
        except Exception as e:
            logger.exception("update_order 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def _update_order_if_status(self, order_id: str, expected_status, **fields) -> bool:
        Order, User, YpayOrder = _resolve_models()
        fields["updated_at"] = datetime.now().isoformat()
        session = self._get_session()
        try:
            if isinstance(expected_status, str):
                expected_status = (expected_status,)
            count = session.execute(update(Order).filter(
                Order.order_id == order_id,
                Order.status.in_(expected_status),
            ).values(**fields)).rowcount
            session.commit()
            return count > 0
        except Exception as e:
            logger.exception("_update_order_if_status 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def accept_order(self, order_id: str, admin_note: str = "") -> bool:
        Order, User, YpayOrder = _resolve_models()
        return self._update_order_if_status(
            order_id, "pending",
            status="accepted",
            accepted_at=datetime.now().isoformat(),
            admin_note=admin_note,
        )

    def start_order(self, order_id: str, task_id: str) -> bool:
        Order, User, YpayOrder = _resolve_models()
        return self._update_order_if_status(
            order_id, ("paid", "accepted", "queued", "retrying"),
            status="running", task_id=task_id,
            started_at=datetime.now().isoformat(),
        )

    def complete_order(self, order_id: str) -> bool:
        Order, User, YpayOrder = _resolve_models()
        # 也允许 cancelled 状态的订单恢复为 completed（任务完成后自动恢复）
        return self._update_order_if_status(
            order_id, ("pending", "running", "paid", "cancelled", "accepted"),
            status="completed",
            finished_at=datetime.now().isoformat(),
        )

    def fail_order(self, order_id: str, error: str = "") -> bool:
        Order, User, YpayOrder = _resolve_models()
        return self._update_order_if_status(
            order_id, ("pending", "running", "paid", "cancelled", "accepted"),
            status="failed",
            finished_at=datetime.now().isoformat(),
            admin_note=error,
        )

    def cancel_order(self, order_id: str) -> bool:
        Order, User, YpayOrder = _resolve_models()
        return self._update_order_if_status(
            order_id, "pending",
            status="cancelled",
            finished_at=datetime.now().isoformat(),
        )

    def auto_cancel_expired_pending(self, minutes: int = 5) -> int:
        Order, User, YpayOrder = _resolve_models()
        session = self._get_session()
        try:
            cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
            count = session.execute(update(Order).filter(
                Order.status == "pending",
                Order.paid == False,
                Order.created_at < cutoff,
            ).values(
                status="cancelled",
                finished_at=datetime.now().isoformat(),
            )).rowcount
            session.commit()
            return count
        except Exception as e:
            logger.exception("auto_cancel_expired_pending 失败")
            session.rollback()
            return 0
        finally:
            session.close()

    def clear_history_orders(self, user_id: Optional[str] = None) -> int:
        Order, User, YpayOrder = _resolve_models()
        session = self._get_session()
        try:
            now = datetime.now().isoformat()
            if user_id:
                count = session.execute(update(Order).filter(
                    Order.status.in_(["completed", "failed", "cancelled"]),
                    Order.user_id == user_id,
                    Order.deleted_at.is_(None),
                ).values(deleted_at=now)).rowcount
            else:
                count = session.execute(update(Order).filter(
                    Order.status.in_(["completed", "failed", "cancelled"]),
                    or_(Order.user_id.is_(None), Order.user_id == ""),
                    Order.deleted_at.is_(None),
                ).values(deleted_at=now)).rowcount
            session.commit()
            return count
        except Exception as e:
            logger.exception("clear_history_orders 失败")
            session.rollback()
            return 0
        finally:
            session.close()

    def get_stats(self) -> Dict[str, Any]:
        Order, User, YpayOrder = _resolve_models()
        session = self._get_session()
        try:
            rows = session.execute(
                select(
                    Order.status,
                    func.count(Order.order_id),
                    func.coalesce(func.sum(Order.price), 0),
                ).group_by(Order.status)
            ).all()
            stats = {
                "total_orders": 0,
                "total_revenue": 0.0,
                "by_status": {},
            }
            for status, cnt, total_price in rows:
                stats["total_orders"] += cnt
                stats["total_revenue"] += total_price
                stats["by_status"][status] = {
                    "count": cnt,
                    "revenue": total_price,
                }
            return stats
        finally:
            session.close()

    def get_dashboard_stats(self) -> Dict[str, Any]:
        Order, User, YpayOrder = _resolve_models()
        session = self._get_session()
        try:
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            week_start = (now - timedelta(days=7)).isoformat()

            total_orders = session.scalar(select(func.count(Order.order_id))) or 0
            orders_today = session.scalar(select(func.count(Order.order_id)).filter(
                Order.created_at >= today_start
            )) or 0
            orders_week = session.scalar(select(func.count(Order.order_id)).filter(
                Order.created_at >= week_start
            )) or 0

            completed_orders = session.scalar(select(func.count(Order.order_id)).filter(
                Order.status == "completed"
            )) or 0

            total_revenue = session.scalar(select(func.coalesce(func.sum(Order.price), 0))) or 0.0
            revenue_today = session.scalar(select(func.coalesce(func.sum(Order.price), 0)).filter(
                Order.created_at >= today_start
            )) or 0.0
            revenue_week = session.scalar(select(func.coalesce(func.sum(Order.price), 0)).filter(
                Order.created_at >= week_start
            )) or 0.0

            platform_dist = session.execute(
                select(Order.website_id, func.count(Order.order_id), func.coalesce(func.sum(Order.price), 0))
                .group_by(Order.website_id)
                .order_by(func.count(Order.order_id).desc())
                .limit(6)
            ).all()
            # 补充未出现但有配置的平台（如学习通），显示为 0
            from config import WEBSITES
            existing_wids = {wid for wid, _, _ in platform_dist}
            for wid in WEBSITES:
                if wid not in existing_wids:
                    platform_dist.append((wid, 0, 0.0))

            task_type_dist = session.execute(
                select(Order.task_type, func.count(Order.order_id), func.coalesce(func.sum(Order.price), 0))
                .group_by(Order.task_type)
            ).all()

            status_dist = session.execute(
                select(Order.status, func.count(Order.order_id))
                .group_by(Order.status)
            ).all()

            recent_7_days = []
            for i in range(6, -1, -1):
                day = (now - timedelta(days=i))
                day_start = day.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                day_end_ts = (day_start[:10] + "T23:59:59")
                day_label = day.strftime("%m/%d")
                cnt = session.scalar(select(func.count(Order.order_id)).filter(
                    Order.created_at >= day_start, Order.created_at < day_end_ts
                )) or 0
                rev = session.scalar(select(func.coalesce(func.sum(Order.price), 0)).filter(
                    Order.created_at >= day_start, Order.created_at < day_end_ts
                )) or 0.0
                recent_7_days.append({"date": day_label, "orders": cnt, "revenue": round(rev, 2)})

            recent_orders = session.scalars(select(Order).order_by(
                Order.created_at.desc()
            ).limit(6)).all()
            recent_order_items = []
            for o in recent_orders:
                recent_order_items.append({
                    "order_id": o.order_id,
                    "username": o.username,
                    "website_id": o.website_id,
                    "task_type": o.task_type,
                    "price": o.price,
                    "status": o.status,
                    "created_at": o.created_at,
                })

            pending_orders = session.scalar(select(func.count(Order.order_id)).filter(
                Order.status == "pending"
            )) or 0
            running_orders = session.scalar(select(func.count(Order.order_id)).filter(
                Order.status == "running"
            )) or 0
            failed_orders = session.scalar(select(func.count(Order.order_id)).filter(
                Order.status == "failed"
            )) or 0

            return {
                "orders": {
                    "total": total_orders,
                    "today": orders_today,
                    "week": orders_week,
                    "completed": completed_orders,
                    "pending": pending_orders,
                    "running": running_orders,
                    "failed": failed_orders,
                    "completion_rate": round(completed_orders / total_orders * 100, 1) if total_orders > 0 else 0,
                },
                "revenue": {
                    "total": round(total_revenue, 2),
                    "today": round(revenue_today, 2),
                    "week": round(revenue_week, 2),
                },
                "platform_distribution": [
                    {"website_id": wid, "count": cnt, "revenue": round(rev, 2)}
                    for wid, cnt, rev in platform_dist
                ],
                "task_type_distribution": [
                    {"task_type": tt, "count": cnt, "revenue": round(rev, 2)}
                    for tt, cnt, rev in task_type_dist
                ],
                "status_distribution": [
                    {"status": st, "count": cnt}
                    for st, cnt in status_dist
                ],
                "recent_7_days": recent_7_days,
                "recent_orders": recent_order_items,
            }
        finally:
            session.close()

    def complete_order_full(self, order_id: str, payment_trade_no: str = "",
                             payment_channel: str = "") -> bool:
        Order, User, YpayOrder = _resolve_models()
        now = datetime.now().isoformat()
        return self.update_order(
            order_id, status="completed", paid=True,
            paid_processed="processed",
            payment_trade_no=payment_trade_no, payment_channel=payment_channel,
            payment_time=now, finished_at=now,
        )

    def confirm_payment(self, order_id: str, payment_trade_no: str = "",
                         payment_channel: str = "") -> bool:
        Order, User, YpayOrder = _resolve_models()
        now = datetime.now().isoformat()
        session = self._get_session()
        try:
            updated = session.execute(update(Order).filter(
                Order.order_id == order_id,
                Order.status.in_(["pending", "awaiting_payment"]),
            ).values(
                status="paid", paid=True,
                payment_trade_no=payment_trade_no,
                payment_channel=payment_channel,
                payment_time=now,
            )).rowcount
            session.commit()
            return updated > 0
        except Exception as e:
            session.rollback()
            logger.exception(f"confirm_payment failed order_id={order_id}")
            return False
        finally:
            session.close()

    def claim_payment_processing(self, order_id: str) -> bool:
        """支付处理幂等闸门：unprocessed → processing，并发下只有一次返回 True"""
        Order, User, YpayOrder = _resolve_models()
        session = self._get_session()
        try:
            updated = session.execute(update(Order).filter(
                Order.order_id == order_id,
                Order.paid_processed == "unprocessed",
            ).values(paid_processed="processing")).rowcount
            session.commit()
            return updated > 0
        except Exception as e:
            logger.exception("claim_payment_processing 失败")
            session.rollback()
            return False
        finally:
            session.close()

    def mark_payment_processed(self, order_id: str) -> bool:
        Order, User, YpayOrder = _resolve_models()
        return self.update_order(order_id, paid_processed="processed")

    def admin_reset_and_mark_paid(self, order_id: str) -> bool:
        """管理员操作前置：cancelled 重置 pending + 未支付标 admin_free 已付"""
        order = self.get_order(order_id)
        if not order:
            return False
        if order["status"] == "cancelled":
            self.update_order(order_id, status="pending", finished_at=None)
        if not order.get("paid"):
            from datetime import datetime
            self.update_order(order_id, paid=True, payment_channel="admin_free",
                              payment_time=datetime.now().isoformat())
        return True

    def recover_stuck_paid_processing(self, minutes: int = 10) -> int:
        """启动时回收卡死的支付处理状态：claim 后进程崩溃会永久停在 processing。

        只回收"未支付成功且超过 N 分钟未更新"的订单，避免误伤处理中的回调。
        """
        Order, User, YpayOrder = _resolve_models()
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        session = self._get_session()
        try:
            updated = session.execute(update(Order).filter(
                Order.paid_processed == "processing",
                Order.status.notin_(["paid", "running", "completed"]),
                or_(Order.updated_at.is_(None), Order.updated_at < cutoff),
            ).values(paid_processed="unprocessed")).rowcount
            session.commit()
            if updated:
                logger.warning(f"回收卡死的支付处理状态 count={updated}")
            return updated
        except Exception as e:
            logger.exception("recover_stuck_paid_processing 失败")
            session.rollback()
            return 0
        finally:
            session.close()

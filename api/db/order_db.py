"""Order CRUD and statistics mixin"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, or_, select, update

from api.db._base import _db_logger

logger = _db_logger

# Lazy-loaded model references
_Order = _User = _Agent = _Commission = _WalletTransaction = _YpayOrder = None


def _resolve_models():
    global _Order, _User, _Agent, _Commission, _WalletTransaction, _YpayOrder
    if _Order is None:
        from api.db.models import Agent, Commission, Order, User, WalletTransaction, YpayOrder
        _Order, _User, _Agent, _Commission, _WalletTransaction, _YpayOrder = Order, User, Agent, Commission, WalletTransaction, YpayOrder
    return _Order, _User, _Agent, _Commission, _WalletTransaction, _YpayOrder


def _order_to_dict(order) -> dict:
    import json

    from api.crypto import decrypt_password
    return {
        "order_id": order.order_id,
        "out_trade_no": order.out_trade_no,
        "payment_trade_no": order.payment_trade_no,
        "payment_channel": order.payment_channel,
        "payment_time": order.payment_time,
        "commission_status": order.commission_status,
        "user_id": order.user_id,
        "customer_name": order.customer_name,
        "customer_contact": order.customer_contact,
        "username": order.username,
        "password": decrypt_password(order.password),
        "website_id": order.website_id,
        "task_type": order.task_type,
        "course_ids": json.loads(order.course_ids) if isinstance(order.course_ids, str) else order.course_ids,
        "video_count": order.video_count,
        "exam_count": order.exam_count,
        "price": order.price,
        "notes": order.notes,
        "inviter_code": order.inviter_code,
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
                     exam_count=0, price=0.0, notes="", user_id="", inviter_code="") -> Dict[str, Any]:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        from api.crypto import encrypt_password
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now().isoformat()
        session = self._get_session()
        try:
            order = Order(
                order_id=order_id,
                user_id=user_id or "",
                customer_name=customer_name,
                customer_contact=customer_contact,
                username=username,
                password=encrypt_password(password),
                website_id=website_id,
                task_type=task_type,
                course_ids=json.dumps(course_ids or []),
                video_count=video_count,
                exam_count=exam_count,
                price=price,
                notes=notes,
                inviter_code=inviter_code,
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

    def deduct_user_balance_for_payment(self, user_id: str, amount: float,
                                         order_id: str) -> bool:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        session = self._get_session()
        try:
            count = session.execute(update(User).filter(
                User.user_id == user_id,
                User.balance >= amount,
            ).values(
                balance=User.balance - amount,
            )).rowcount
            if count == 0:
                session.rollback()
                return False
            now = datetime.now().isoformat()
            tx_id = f"TX-{uuid.uuid4().hex[:8].upper()}"
            tx = WalletTransaction(
                tx_id=tx_id,
                user_id=user_id,
                amount=-amount,
                tx_type="order_payment",
                balance_after=session.scalar(select(User.balance).filter(User.user_id == user_id)),
                note=f"订单 {order_id} 支付",
                order_id=order_id,
                created_at=now,
            )
            session.add(tx)
            session.commit()
            return True
        except Exception as e:
            logger.exception("deduct_user_balance_for_payment 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
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
                    agent_ids: Optional[List[str]] = None,
                    limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
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
            if agent_ids:
                stmt = stmt.where(Order.inviter_code.in_(
                    select(Agent.referral_code).filter(Agent.agent_id.in_(agent_ids))
                ))
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
                     search: Optional[str] = None,
                     agent_ids: Optional[List[str]] = None) -> int:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        session = self._get_session()
        try:
            stmt = select(func.count(Order.order_id))
            if status:
                stmt = stmt.where(Order.status == status)
            if user_id:
                stmt = stmt.where(Order.user_id == user_id)
            if agent_ids:
                stmt = stmt.where(Order.inviter_code.in_(
                    select(Agent.referral_code).filter(Agent.agent_id.in_(agent_ids))
                ))
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
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
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
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
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
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        return self._update_order_if_status(
            order_id, "pending",
            status="accepted",
            accepted_at=datetime.now().isoformat(),
            admin_note=admin_note,
        )

    def start_order(self, order_id: str, task_id: str) -> bool:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        return self._update_order_if_status(
            order_id, ("paid", "accepted", "queued", "retrying"),
            status="running", task_id=task_id,
            started_at=datetime.now().isoformat(),
        )

    def complete_order(self, order_id: str) -> bool:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        return self._update_order_if_status(
            order_id, ("pending", "running", "paid"),
            status="completed",
            finished_at=datetime.now().isoformat(),
        )

    def fail_order(self, order_id: str, error: str = "") -> bool:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        return self._update_order_if_status(
            order_id, ("pending", "running", "paid"),
            status="failed",
            finished_at=datetime.now().isoformat(),
            admin_note=error,
        )

    def cancel_order(self, order_id: str) -> bool:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        return self._update_order_if_status(
            order_id, "pending",
            status="cancelled",
            finished_at=datetime.now().isoformat(),
        )

    def auto_cancel_expired_pending(self, minutes: int = 5) -> int:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
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
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
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

    def pay_order(self, order_id: str) -> bool:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        session = self._get_session()
        try:
            order = session.scalars(select(Order).filter(Order.order_id == order_id).with_for_update()).first()
            if not order:
                return False
            if order.paid:
                return True
            if not order.user_id:
                return False
            user = session.scalars(select(User).filter(User.user_id == order.user_id).with_for_update()).first()
            if not user:
                return False
            is_vip = user.role in ("admin", "sub_admin")
            if not is_vip and user.balance < order.price:
                return False
            now = datetime.now().isoformat()
            if not is_vip:
                user.balance -= order.price
                session.add(WalletTransaction(
                    tx_id=f"TX-{uuid.uuid4().hex[:8].upper()}", user_id=order.user_id, amount=-order.price,
                    tx_type="order_payment", balance_after=user.balance,
                    note=f"订单 {order_id} 支付", order_id=order_id, created_at=now,
                ))
            order.paid = True
            order.status = "paid"
            order.payment_channel = "balance" if not is_vip else "vip_free"
            order.payment_time = now
            order.updated_at = now
            session.commit()
            return True
        except Exception as e:
            logger.exception("pay_order 失败")
            session.rollback()
            return False
        finally:
            session.close()

    def pay_user_orders(self, user_id: str) -> Dict[str, Any]:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        session = self._get_session()
        try:
            orders = session.scalars(select(Order).filter(
                Order.user_id == user_id,
                Order.paid == False,
                Order.status == "pending",
)).all()
            unpaid = [o for o in orders]
            if not unpaid:
                return {"paid": 0, "total_price": 0, "failed": 0}
            user = session.scalars(select(User).filter(User.user_id == user_id).with_for_update()).first()
            if not user:
                return {"paid": 0, "total_price": 0, "failed": 0}
            is_vip = user.role in ("admin", "sub_admin")
            total = sum(o.price for o in unpaid)
            if not is_vip and user.balance < total:
                return {"paid": 0, "total_price": round(total, 2), "failed": len(unpaid),
                        "error": f"余额不足，需要 ¥{total:.2f}，当前余额 ¥{user.balance:.2f}"}
            paid_order_ids = []
            now = datetime.now().isoformat()
            for o in unpaid:
                if not is_vip:
                    user.balance -= o.price
                o.paid = True
                o.status = "paid"
                o.payment_time = now
                o.payment_channel = "balance" if not is_vip else "vip_free"
                paid_order_ids.append(o.order_id)
                if not is_vip:
                    tx = WalletTransaction(
                        tx_id=f"TX-{uuid.uuid4().hex[:8].upper()}",
                        user_id=user_id,
                        amount=-o.price,
                        tx_type="order_payment",
                        balance_after=user.balance,
                        note=f"订单 {o.order_id} 支付",
                        order_id=o.order_id,
                        created_at=now,
                    )
                    session.add(tx)
            session.commit()
            return {"paid": len(unpaid), "total_price": round(total, 2), "failed": 0, "paid_order_ids": paid_order_ids}
        except Exception as e:
            logger.exception("pay_user_orders 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def _get_agent_upgrade_stats(self, session, since: str = None) -> Dict[str, Any]:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        stmt = select(
            func.count(YpayOrder.id),
            func.coalesce(func.sum(YpayOrder.truemoney), 0),
        ).filter(
            YpayOrder.out_trade_no.like("AGENTUP-%"),
            YpayOrder.status == 1,
        )
        if since:
            stmt = stmt.filter(YpayOrder.create_time >= since)
        cnt, total = session.execute(stmt).one()
        return {"count": cnt or 0, "revenue": float(total or 0)}

    def get_stats(self) -> Dict[str, Any]:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        session = self._get_session()
        try:
            rows = session.execute(
                select(
                    Order.status,
                    func.count(Order.order_id),
                    func.coalesce(func.sum(Order.price), 0),
                ).group_by(Order.status)
            ).all()
            upgrade_stats = self._get_agent_upgrade_stats(session)
            stats = {
                "total_orders": 0,
                "total_revenue": 0.0,
                "by_status": {},
                "agent_upgrades": upgrade_stats,
            }
            for status, cnt, total_price in rows:
                stats["total_orders"] += cnt
                stats["total_revenue"] += total_price
                stats["by_status"][status] = {
                    "count": cnt,
                    "revenue": total_price,
                }
            stats["total_revenue"] += upgrade_stats["revenue"]
            return stats
        finally:
            session.close()

    def get_dashboard_stats(self) -> Dict[str, Any]:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        session = self._get_session()
        try:
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            week_start = (now - timedelta(days=7)).isoformat()

            total_users = session.scalar(select(func.count(User.user_id))) or 0
            new_users_today = session.scalar(select(func.count(User.user_id)).filter(
                User.created_at >= today_start
            )) or 0
            new_users_week = session.scalar(select(func.count(User.user_id)).filter(
                User.created_at >= week_start
            )) or 0

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

            upgrade_all = self._get_agent_upgrade_stats(session)
            upgrade_today = self._get_agent_upgrade_stats(session, since=today_start)
            upgrade_week = self._get_agent_upgrade_stats(session, since=week_start)
            total_revenue += upgrade_all["revenue"]
            revenue_today += upgrade_today["revenue"]
            revenue_week += upgrade_week["revenue"]

            active_agents = session.scalar(select(func.count(Agent.agent_id)).filter(
                Agent.status == "active"
            )) or 0
            pending_agents = session.scalar(select(func.count(Agent.agent_id)).filter(
                Agent.status == "pending"
            )) or 0

            total_agents = session.scalar(select(func.count(Agent.agent_id))) or 0
            new_agents_today = session.scalar(select(func.count(Agent.agent_id)).filter(
                Agent.created_at >= today_start
            )) or 0
            new_agents_week = session.scalar(select(func.count(Agent.agent_id)).filter(
                Agent.created_at >= week_start
            )) or 0
            rejected_agents = session.scalar(select(func.count(Agent.agent_id)).filter(
                Agent.status == "rejected"
            )) or 0
            agents_by_tier = session.execute(
                select(Agent.tier_level, func.count(Agent.agent_id))
                .filter(Agent.status == "active")
                .group_by(Agent.tier_level)
            ).all()

            total_commission = session.scalar(select(
                func.coalesce(func.sum(Commission.commission_amount), 0)
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
                up_rev = session.scalar(select(
                    func.coalesce(func.sum(YpayOrder.truemoney), 0)
                ).filter(
                    YpayOrder.out_trade_no.like("AGENTUP-%"),
                    YpayOrder.status == 1,
                    YpayOrder.create_time >= day_start,
                    YpayOrder.create_time <= day_end_ts,
                )) or 0.0
                recent_7_days.append({"date": day_label, "orders": cnt, "revenue": round(rev + up_rev, 2)})

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

            top_agents = []
            top_agents_raw = session.scalars(select(Agent).filter(
                Agent.status == "active"
            ).order_by(Agent.total_commission.desc()).limit(5)).all()
            for a in top_agents_raw:
                user = session.scalars(select(User).filter(User.user_id == a.user_id)).first()
                top_agents.append({
                    "agent_id": a.agent_id,
                    "display_name": a.display_name or (user.nickname if user else "") or (user.username if user else ""),
                    "total_earnings": a.total_commission,
                    "referral_code": a.referral_code,
                    "commission_rate": a.flow_commission_rate,
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
                "users": {
                    "total": total_users,
                    "new_today": new_users_today,
                    "new_week": new_users_week,
                },
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
                "agents": {
                    "active": active_agents,
                    "pending": pending_agents,
                    "total": total_agents,
                    "rejected": rejected_agents,
                    "new_today": new_agents_today,
                    "new_week": new_agents_week,
                    "total_commission": round(total_commission, 2),
                    "by_tier": {str(tl): cnt for tl, cnt in agents_by_tier},
                },
                "agent_upgrades": {
                    "count": upgrade_all["count"],
                    "revenue": round(upgrade_all["revenue"], 2),
                    "today_count": upgrade_today["count"],
                    "today_revenue": round(upgrade_today["revenue"], 2),
                    "week_count": upgrade_week["count"],
                    "week_revenue": round(upgrade_week["revenue"], 2),
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
                "top_agents": top_agents,
            }
        finally:
            session.close()

    def complete_order_full(self, order_id: str, payment_trade_no: str = "",
                             payment_channel: str = "") -> bool:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        now = datetime.now().isoformat()
        return self.update_order(
            order_id, status="completed", paid=True, commission_status="processed",
            payment_trade_no=payment_trade_no, payment_channel=payment_channel,
            payment_time=now, finished_at=now,
        )

    def confirm_payment(self, order_id: str, payment_trade_no: str = "",
                         payment_channel: str = "") -> bool:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
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

    def claim_commission(self, order_id: str) -> bool:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        session = self._get_session()
        try:
            updated = session.execute(update(Order).filter(
                Order.order_id == order_id,
                Order.commission_status == "unprocessed",
            ).values(commission_status="processing")).rowcount
            session.commit()
            return updated > 0
        except Exception as e:
            logger.exception("claim_commission 失败")
            session.rollback()
            return False
        finally:
            session.close()

    def mark_commission_done(self, order_id: str) -> bool:
        Order, User, Agent, Commission, WalletTransaction, YpayOrder = _resolve_models()
        return self.update_order(order_id, commission_status="processed")

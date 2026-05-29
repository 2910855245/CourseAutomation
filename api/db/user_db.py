"""User CRUD operations mixin"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update, func, or_

from api.db._base import _db_logger

logger = _db_logger

# Lazy-loaded model references - resolved at first method call
_User = _Agent = _WalletTransaction = None


def _resolve_models():
    global _User, _Agent, _WalletTransaction
    if _User is None:
        from api.db.models import Agent, User, WalletTransaction
        _User, _Agent, _WalletTransaction = User, Agent, WalletTransaction
    return _User, _Agent, _WalletTransaction


def _user_to_dict(user) -> Dict[str, Any]:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "password_hash": user.password_hash,
        "nickname": user.nickname,
        "contact": user.contact,
        "role": user.role,
        "balance": user.balance,
        "total_spent": user.total_spent,
        "order_count": user.order_count,
        "referred_by": user.referred_by,
        "created_at": user.created_at,
        "last_login": user.last_login,
    }


class UserDBMixin:
    def create_user(self, username: str, password_hash: str,
                    nickname: str = "", contact: str = "",
                    role: str = "customer", referred_by: str = None) -> Dict[str, Any]:
        User, _, _ = _resolve_models()
        user_id = f"USR-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now().isoformat()
        session = self._get_session()
        try:
            user = User(
                user_id=user_id, username=username, password_hash=password_hash,
                nickname=nickname, contact=contact, role=role,
                balance=0.0, total_spent=0.0, order_count=0,
                referred_by=referred_by, created_at=now, last_login=now,
            )
            session.add(user)
            session.commit()
            return self.get_user(user_id)
        except Exception as e:
            logger.exception("create_user 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        User, _, _ = _resolve_models()
        session = self._get_session()
        try:
            user = session.scalars(select(User).filter(User.user_id == user_id)).first()
            return _user_to_dict(user) if user else None
        finally:
            session.close()

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        User, _, _ = _resolve_models()
        session = self._get_session()
        try:
            user = session.scalars(select(User).filter(User.username == username)).first()
            return _user_to_dict(user) if user else None
        finally:
            session.close()

    def get_user_by_login(self, login_name: str) -> Optional[Dict[str, Any]]:
        """登录查找：先按 user_id 查，再按 username 查"""
        User, _, _ = _resolve_models()
        session = self._get_session()
        try:
            user = session.scalars(
                select(User).filter(or_(User.user_id == login_name, User.username == login_name))
            ).first()
            return _user_to_dict(user) if user else None
        finally:
            session.close()

    def get_user_balance(self, user_id: str) -> float:
        User, _, _ = _resolve_models()
        session = self._get_session()
        try:
            user = session.scalars(select(User).filter(User.user_id == user_id)).first()
            return user.balance if user else 0.0
        finally:
            session.close()

    def update_user_login(self, user_id: str):
        User, _, _ = _resolve_models()
        session = self._get_session()
        try:
            session.execute(update(User).filter(User.user_id == user_id).values(
                last_login=datetime.now().isoformat()
            ))
            session.commit()
        except Exception as e:
            logger.exception("update_user_login 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def soft_delete_user(self, user_id: str) -> bool:
        User, _, _ = _resolve_models()
        session = self._get_session()
        try:
            user = session.scalars(select(User).filter(User.user_id == user_id)).first()
            if not user or user.deleted_at:
                return False
            if user.role == "admin":
                return False
            session.execute(update(User).filter(User.user_id == user_id).values(
                deleted_at=datetime.now().isoformat()
            ))
            session.commit()
            return True
        except Exception as e:
            logger.exception("soft_delete_user 失败")
            session.rollback()
            return False
        finally:
            session.close()

    def update_user(self, user_id: str, **fields) -> bool:
        User, _, _ = _resolve_models()
        if not fields:
            return False
        session = self._get_session()
        try:
            count = session.execute(update(User).filter(User.user_id == user_id).values(**fields)).rowcount
            session.commit()
            return count > 0
        except Exception as e:
            logger.exception("update_user 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def list_users(self, limit: int = 100, offset: int = 0, include_deleted: bool = False) -> List[Dict[str, Any]]:
        User, _, _ = _resolve_models()
        session = self._get_session()
        try:
            stmt = select(User).order_by(User.created_at.desc())
            if not include_deleted:
                stmt = stmt.where(User.deleted_at.is_(None))
            users = session.scalars(stmt.offset(offset).limit(limit)).all()
            return [_user_to_dict(u) for u in users]
        finally:
            session.close()

    def count_users(self, include_deleted: bool = False) -> int:
        User, _, _ = _resolve_models()
        session = self._get_session()
        try:
            stmt = select(func.count(User.user_id))
            if not include_deleted:
                stmt = stmt.where(User.deleted_at.is_(None))
            return session.scalar(stmt)
        finally:
            session.close()

    def get_user_stats(self) -> Dict[str, Any]:
        User, _, _ = _resolve_models()
        session = self._get_session()
        try:
            total = session.scalar(select(func.count(User.user_id)))
            admins = session.scalar(select(func.count(User.user_id)).filter(User.role == "admin"))
            customers = session.scalar(select(func.count(User.user_id)).filter(User.role == "customer"))
            total_balance = session.scalar(select(func.coalesce(func.sum(User.balance), 0.0)))
            total_spent = session.scalar(select(func.coalesce(func.sum(User.total_spent), 0.0)))
            return {
                "total": total,
                "admins": admins,
                "customers": customers,
                "total_balance": round(float(total_balance), 2),
                "total_spent": round(float(total_spent), 2),
            }
        finally:
            session.close()

    def list_users_with_agents(self, role: str = None, agent_status: str = None,
                               search: str = None, limit: int = 100, offset: int = 0,
                               include_deleted: bool = False, include_admin: bool = False) -> Dict[str, Any]:
        User, Agent, _ = _resolve_models()
        session = self._get_session()
        try:
            # Agent.user_id 存的是 username（历史原因），所以用 username 关联
            query = select(User, Agent).outerjoin(Agent, User.username == Agent.user_id)
            count_query = select(func.count(User.user_id)).outerjoin(Agent, User.username == Agent.user_id)
            if not include_deleted:
                query = query.where(User.deleted_at.is_(None))
                count_query = count_query.where(User.deleted_at.is_(None))
            if not include_admin:
                query = query.where(User.role != "admin")
                count_query = count_query.where(User.role != "admin")

            if role and role != 'all':
                if role == 'agent':
                    query = query.where(Agent.agent_id.isnot(None))
                    count_query = count_query.where(Agent.agent_id.isnot(None))
                elif role == 'customer':
                    query = query.where(Agent.agent_id.is_(None))
                    count_query = count_query.where(Agent.agent_id.is_(None))
                else:
                    query = query.where(User.role == role)
                    count_query = count_query.where(User.role == role)

            if agent_status and agent_status != 'all':
                if agent_status == 'none':
                    query = query.where(Agent.agent_id.is_(None))
                    count_query = count_query.where(Agent.agent_id.is_(None))
                else:
                    query = query.where(Agent.status == agent_status)
                    count_query = count_query.where(Agent.status == agent_status)

            if search:
                like = f"%{search}%"
                query = query.where(or_(User.username.like(like), User.nickname.like(like)))
                count_query = count_query.where(or_(User.username.like(like), User.nickname.like(like)))

            total = session.scalar(count_query)
            rows = session.execute(query.order_by(User.created_at.desc()).offset(offset).limit(limit)).all()

            items = []
            for user, agent in rows:
                d = _user_to_dict(user)
                d.pop("password_hash", None)
                if agent:
                    d["agent"] = {
                        "agent_id": agent.agent_id, "referral_code": agent.referral_code,
                        "tier_level": agent.tier_level, "status": agent.status,
                        "flow_commission_rate": agent.flow_commission_rate,
                        "available_balance": agent.available_balance,
                        "total_commission": agent.total_commission,
                        "withdrawn_amount": agent.withdrawn_amount,
                    }
                    d["referral_count"] = session.scalar(select(func.count(Agent.agent_id)).filter(
                        Agent.parent_agent_id == agent.agent_id
                    ))
                else:
                    d["agent"] = None
                    d["referral_count"] = 0
                items.append(d)

            total_users = session.scalar(select(func.count(User.user_id)))
            total_agents = session.scalar(select(func.count(Agent.agent_id))) if items else 0
            active_agents = session.scalar(select(func.count(Agent.agent_id)).filter(Agent.status == "active")) if items else 0
            pending_agents = session.scalar(select(func.count(Agent.agent_id)).filter(Agent.status == "pending")) if items else 0
            return {
                "items": items, "total": total, "total_users": total_users,
                "stats": {
                    "total_users": total_users,
                    "total_agents": total_agents,
                    "active_agents": active_agents,
                    "pending_agents": pending_agents,
                },
            }
        finally:
            session.close()

    def update_user_balance(self, user_id: str, amount: float,
                            tx_type: str, note: str = "",
                            order_id: str = None) -> bool:
        User, _, WalletTransaction = _resolve_models()
        session = self._get_session()
        try:
            user = session.scalars(select(User).filter(User.user_id == user_id).with_for_update()).first()
            if not user:
                return False
            user.balance += amount
            tx_id = f"TX-{uuid.uuid4().hex[:8].upper()}"
            tx = WalletTransaction(
                tx_id=tx_id, user_id=user_id, amount=amount, tx_type=tx_type,
                balance_after=user.balance, note=note, order_id=order_id,
                created_at=datetime.now().isoformat(),
            )
            session.add(tx)
            session.commit()
            return True
        except Exception as e:
            logger.exception("update_user_balance 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def get_user_transactions(self, user_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        _, _, WalletTransaction = _resolve_models()
        session = self._get_session()
        try:
            txs = session.scalars(select(WalletTransaction).filter(
                WalletTransaction.user_id == user_id
            ).order_by(WalletTransaction.created_at.desc()).offset(offset).limit(limit)).all()
            return [{"tx_id": t.tx_id, "user_id": t.user_id, "amount": t.amount,
                     "tx_type": t.tx_type, "balance_after": t.balance_after,
                     "note": t.note, "order_id": t.order_id, "created_at": t.created_at} for t in txs]
        finally:
            session.close()

    def list_sub_admins(self) -> List[Dict[str, Any]]:
        User, _, _ = _resolve_models()
        session = self._get_session()
        try:
            users = session.scalars(select(User).filter(User.role == "sub_admin")).all()
            return [_user_to_dict(u) for u in users]
        finally:
            session.close()

    def set_role(self, user_id: str, role: str) -> bool:
        User, _, _ = _resolve_models()
        session = self._get_session()
        try:
            count = session.execute(update(User).filter(User.user_id == user_id).values(role=role)).rowcount
            session.commit()
            return count > 0
        except Exception as e:
            logger.exception("set_role 失败")
            session.rollback()
            return False
        finally:
            session.close()

    def increment_user_order_stats(self, user_id: str, price: float):
        User, _, _ = _resolve_models()
        session = self._get_session()
        try:
            session.execute(update(User).filter(User.user_id == user_id).values({
                User.order_count: User.order_count + 1,
                User.total_spent: User.total_spent + price,
            }))
            session.commit()
        except Exception as e:
            logger.exception("increment_user_order_stats 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def get_user_by_referral_code(self, referral_code: str) -> Optional[Dict[str, Any]]:
        User, Agent, _ = _resolve_models()
        session = self._get_session()
        try:
            agent = session.scalars(select(Agent).filter(Agent.referral_code == referral_code)).first()
            if not agent:
                return None
            user = session.scalars(select(User).filter(User.user_id == agent.user_id)).first()
            return _user_to_dict(user) if user else None
        finally:
            session.close()

"""User CRUD operations mixin"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update, func, or_

from api.db._base import _db_logger


logger = _db_logger

# Lazy-loaded model references - resolved at first method call
_User = None


def _resolve_models():
    global _User
    if _User is None:
        from api.db.models import User
        _User = User
    return _User, None


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
        "created_at": user.created_at,
        "last_login": user.last_login,
    }


class UserDBMixin:
    def create_user(self, username: str, password_hash: str,
                    nickname: str = "", contact: str = "",
                    role: str = "customer") -> Dict[str, Any]:
        User, _ = _resolve_models()
        user_id = gen_id("USR")
        now = datetime.now().isoformat()
        session = self._get_session()
        try:
            user = User(
                user_id=user_id, username=username, password_hash=password_hash,
                nickname=nickname, contact=contact, role=role,
                balance=0.0, total_spent=0.0, order_count=0,
                created_at=now, last_login=now,
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
        User, _ = _resolve_models()
        session = self._get_session()
        try:
            user = session.scalars(select(User).filter(User.user_id == user_id)).first()
            return _user_to_dict(user) if user else None
        finally:
            session.close()

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        User, _ = _resolve_models()
        session = self._get_session()
        try:
            user = session.scalars(select(User).filter(User.username == username)).first()
            return _user_to_dict(user) if user else None
        finally:
            session.close()

    def get_user_by_login(self, login_name: str) -> Optional[Dict[str, Any]]:
        """登录查找：先按 user_id 查，再按 username 查"""
        User, _ = _resolve_models()
        session = self._get_session()
        try:
            user = session.scalars(
                select(User).filter(or_(User.user_id == login_name, User.username == login_name))
            ).first()
            return _user_to_dict(user) if user else None
        finally:
            session.close()

    def update_user_login(self, user_id: str):
        User, _ = _resolve_models()
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
        User, _ = _resolve_models()
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
        User, _ = _resolve_models()
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
        User, _ = _resolve_models()
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
        User, _ = _resolve_models()
        session = self._get_session()
        try:
            stmt = select(func.count(User.user_id))
            if not include_deleted:
                stmt = stmt.where(User.deleted_at.is_(None))
            return session.scalar(stmt)
        finally:
            session.close()

    def increment_user_order_stats(self, user_id: str, price: float):
        User, _ = _resolve_models()
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

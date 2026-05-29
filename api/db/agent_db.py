"""Agent, Commission, Withdrawal, Channel, Invite, Config, Audit operations mixin"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select, update

from api.db._base import _db_logger

logger = _db_logger

# Lazy-loaded model references
_Agent = _Commission = _Withdrawal = _Channel = _UserInvite = _SystemConfig = _AuditLog = _User = None


def _resolve_models():
    global _Agent, _Commission, _Withdrawal, _Channel, _UserInvite, _SystemConfig, _AuditLog, _User
    if _Agent is None:
        from api.db.models import Agent, AuditLog, Channel, Commission, SystemConfig, User, UserInvite, Withdrawal
        _Agent, _Commission, _Withdrawal, _Channel, _UserInvite, _SystemConfig, _AuditLog, _User = Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User
    return _Agent, _Commission, _Withdrawal, _Channel, _UserInvite, _SystemConfig, _AuditLog, _User


class AgentDBMixin:
    def create_agent(self, *, user_id: str, referral_code: str,
                     parent_agent_id: str = "", grandparent_agent_id: str = "",
                     tier_level: int = 1, subdomain_slug: str = "",
                     status: str = "active") -> Dict[str, Any]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        agent_id = f"AGT-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now().isoformat()
        session = self._get_session()
        try:
            agent = Agent(
                agent_id=agent_id,
                user_id=user_id,
                referral_code=referral_code,
                parent_agent_id=parent_agent_id or "",
                grandparent_agent_id=grandparent_agent_id or "",
                tier_level=tier_level,
                subdomain_slug=subdomain_slug,
                available_balance=0.0,
                frozen_balance=0.0,
                withdrawn_amount=0.0,
                total_commission=0.0,
                status=status,
                created_at=now,
            )
            session.add(agent)
            session.commit()
            return self._agent_to_dict(agent)
        except Exception as e:
            logger.exception("create_agent 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            agent = session.scalars(select(Agent).filter(Agent.agent_id == agent_id)).first()
            return self._agent_to_dict(agent) if agent else None
        finally:
            session.close()

    def get_agent_by_subdomain(self, slug: str) -> Optional[Dict[str, Any]]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            agent = session.scalars(select(Agent).filter(Agent.subdomain_slug == slug)).first()
            return self._agent_to_dict(agent) if agent else None
        finally:
            session.close()

    def get_agent_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            agent = session.scalars(select(Agent).filter(Agent.user_id == user_id)).first()
            return self._agent_to_dict(agent) if agent else None
        finally:
            session.close()

    def get_child_agents(self, parent_agent_id: str) -> list:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            children = session.scalars(select(Agent).filter(
                Agent.parent_agent_id == parent_agent_id,
                Agent.status == "active",
            )).all()
            return [self._agent_to_dict(a) for a in children]
        finally:
            session.close()

    def get_agent_by_referral_code(self, referral_code: str) -> Optional[Dict[str, Any]]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            agent = session.scalars(select(Agent).filter(Agent.referral_code == referral_code)).first()
            return self._agent_to_dict(agent) if agent else None
        finally:
            session.close()

    @staticmethod
    def _agent_to_dict(agent) -> Dict[str, Any]:
        return {
            "agent_id": agent.agent_id,
            "user_id": agent.user_id,
            "referral_code": agent.referral_code,
            "subdomain_slug": agent.subdomain_slug,
            "display_name": agent.display_name,
            "contact_phone": agent.contact_phone,
            "contact_qq": agent.contact_qq,
            "contact_wechat": agent.contact_wechat,
            "available_balance": agent.available_balance,
            "frozen_balance": agent.frozen_balance,
            "withdrawn_amount": agent.withdrawn_amount,
            "total_commission": agent.total_commission,
            "parent_agent_id": agent.parent_agent_id,
            "grandparent_agent_id": agent.grandparent_agent_id,
            "tier_level": agent.tier_level,
            "total_flow": agent.total_flow,
            "invite_count": agent.invite_count,
            "join_fee_paid": agent.join_fee_paid,
            "cost_discount": agent.cost_discount,
            "flow_commission_rate": agent.flow_commission_rate,
            "subsite_active": agent.subsite_active,
            "subsite_name": agent.subsite_name,
            "subsite_domain": agent.subsite_domain,
            "subsite_template": agent.subsite_template,
            "wechat_qr": agent.wechat_qr,
            "welcome_text": agent.welcome_text,
            "contact": agent.contact,
            "status": agent.status,
            "created_at": agent.created_at,
        }

    def list_agents(self, status: str = None, limit: int = 100, offset: int = 0, managed_by: str = None) -> List[Dict[str, Any]]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            stmt = select(Agent)
            if status:
                stmt = stmt.where(Agent.status == status)
            if managed_by:
                stmt = stmt.where(Agent.managed_by == managed_by)
            stmt = stmt.order_by(Agent.created_at.desc()).offset(offset).limit(limit)
            return [self._agent_to_dict(a) for a in session.scalars(stmt).all()]
        finally:
            session.close()

    def count_agents(self, status: str = None, managed_by: str = None) -> int:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            stmt = select(func.count(Agent.agent_id))
            if status:
                stmt = stmt.where(Agent.status == status)
            if managed_by:
                stmt = stmt.where(Agent.managed_by == managed_by)
            return session.scalar(stmt)
        finally:
            session.close()

    def get_managed_agent_ids(self, managed_by: str) -> List[str]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            return [a.agent_id for a in session.execute(select(Agent.agent_id).filter(Agent.managed_by == managed_by)).scalars().all()]
        finally:
            session.close()

    def update_agent(self, agent_id: str, **fields) -> bool:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        if not fields:
            return False
        session = self._get_session()
        try:
            count = session.execute(update(Agent).filter(Agent.agent_id == agent_id).values(**fields)).rowcount
            session.commit()
            return count > 0
        except Exception as e:
            logger.exception("update_agent 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def increment_agent_balance(self, agent_id: str, amount: float) -> bool:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            count = session.execute(update(Agent).filter(Agent.agent_id == agent_id).values(
                available_balance=Agent.available_balance + amount,
                total_commission=Agent.total_commission + amount,
            )).rowcount
            session.commit()
            return count > 0
        except Exception as e:
            logger.exception("increment_agent_balance 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def create_commission(self, *, order_id: str, agent_id: str, user_id: str,
                          order_amount: float, commission_rate: float,
                          commission_amount: float, tier_level: int = 1) -> Dict[str, Any]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        comm_id = f"COM-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now().isoformat()
        session = self._get_session()
        try:
            c = Commission(
                commission_id=comm_id, order_id=order_id, agent_id=agent_id,
                referred_user_id=user_id, order_amount=order_amount,
                commission_rate=commission_rate, commission_amount=commission_amount,
                level=tier_level, status="pending", created_at=now,
            )
            session.add(c)
            session.commit()
            return {
                "commission_id": comm_id, "order_id": order_id, "agent_id": agent_id,
                "user_id": user_id, "order_amount": order_amount,
                "commission_rate": commission_rate, "commission_amount": commission_amount,
                "tier_level": tier_level, "status": "pending", "created_at": now,
            }
        except Exception as e:
            logger.exception("create_commission 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def list_commissions(self, agent_id: str = None, agent_ids: list = None, status: str = None,
                         limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            stmt = select(Commission)
            if agent_id:
                stmt = stmt.where(Commission.agent_id == agent_id)
            elif agent_ids:
                stmt = stmt.where(Commission.agent_id.in_(agent_ids))
            if status:
                stmt = stmt.where(Commission.status == status)
            stmt = stmt.order_by(Commission.created_at.desc()).offset(offset).limit(limit)
            return [
                {
                    "commission_id": c.commission_id, "order_id": c.order_id,
                    "agent_id": c.agent_id, "user_id": c.referred_user_id,
                    "order_amount": c.order_amount, "commission_rate": c.commission_rate,
                    "commission_amount": c.commission_amount, "tier_level": c.level,
                    "status": c.status, "created_at": c.created_at,
                }
                for c in session.scalars(stmt).all()
            ]
        finally:
            session.close()

    def count_commissions(self, agent_id: str = None, agent_ids: list = None, status: str = None) -> int:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            stmt = select(func.count(Commission.commission_id))
            if agent_id:
                stmt = stmt.where(Commission.agent_id == agent_id)
            elif agent_ids:
                stmt = stmt.where(Commission.agent_id.in_(agent_ids))
            if status:
                stmt = stmt.where(Commission.status == status)
            return session.scalar(stmt)
        finally:
            session.close()

    def withdraw_agent_balance(self, agent_id: str, amount: float, fee: float = 0.0) -> Dict[str, Any]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            count = session.execute(update(Agent).filter(
                Agent.agent_id == agent_id,
                Agent.available_balance >= amount + fee,
            ).values(
                available_balance=Agent.available_balance - (amount + fee),
                frozen_balance=Agent.frozen_balance + (amount + fee),
            )).rowcount
            if count == 0:
                session.rollback()
                return {"error": "余额不足或提现失败，请刷新后重试"}
            withdrawal_id = f"WD-{uuid.uuid4().hex[:8].upper()}"
            now = datetime.now().isoformat()
            w = Withdrawal(
                withdrawal_id=withdrawal_id, agent_id=agent_id,
                amount=amount, fee_amount=fee, method="balance",
                status="pending", created_at=now,
            )
            session.add(w)
            session.commit()
            return {"withdrawal_id": withdrawal_id, "amount": amount, "fee": fee}
        except Exception as e:
            logger.exception("withdraw_agent_balance 失败")
            session.rollback()
            return {"error": "提现申请失败，请稍后重试"}
        finally:
            session.close()

    def create_withdrawal(self, agent_id: str, amount: float, method: str = "balance", fee_amount: float = 0.0) -> Dict[str, Any]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        withdrawal_id = f"WD-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now().isoformat()
        session = self._get_session()
        try:
            withdrawal = Withdrawal(
                withdrawal_id=withdrawal_id,
                agent_id=agent_id,
                amount=amount,
                fee_amount=fee_amount,
                method=method,
                status="pending",
                created_at=now,
            )
            session.add(withdrawal)
            session.commit()
            return {
                "withdrawal_id": withdrawal_id,
                "agent_id": agent_id,
                "amount": amount,
                "method": method,
                "status": "pending",
                "created_at": now,
            }
        except Exception as e:
            logger.exception("create_withdrawal 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def get_withdrawals(self, agent_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            stmt = select(Withdrawal).filter(Withdrawal.agent_id == agent_id)
            stmt = stmt.order_by(Withdrawal.created_at.desc()).offset(offset).limit(limit)
            return [
                {
                    "withdrawal_id": w.withdrawal_id,
                    "agent_id": w.agent_id,
                    "amount": w.amount,
                    "method": w.method,
                    "status": w.status,
                    "account": w.account,
                    "admin_note": w.admin_note,
                    "processed_at": w.processed_at,
                    "created_at": w.created_at,
                }
                for w in session.scalars(stmt).all()
            ]
        finally:
            session.close()

    def count_withdrawals(self, agent_id: str) -> int:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            return session.scalar(select(func.count(Withdrawal.withdrawal_id)).filter(
                Withdrawal.agent_id == agent_id
            ))
        finally:
            session.close()

    def count_all_withdrawals(self, status: str = None, agent_ids: List[str] = None) -> int:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            stmt = select(func.count(Withdrawal.withdrawal_id))
            if status:
                stmt = stmt.where(Withdrawal.status == status)
            if agent_ids:
                stmt = stmt.where(Withdrawal.agent_id.in_(agent_ids))
            return session.scalar(stmt) or 0
        finally:
            session.close()

    def list_all_withdrawals(self, status: str = None, limit: int = 50, offset: int = 0, agent_ids: List[str] = None) -> List[Dict[str, Any]]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            stmt = select(Withdrawal)
            if status:
                stmt = stmt.where(Withdrawal.status == status)
            if agent_ids:
                stmt = stmt.where(Withdrawal.agent_id.in_(agent_ids))
            stmt = stmt.order_by(Withdrawal.created_at.desc()).offset(offset).limit(limit)
            return [
                {
                    "withdrawal_id": w.withdrawal_id,
                    "agent_id": w.agent_id,
                    "amount": w.amount,
                    "method": w.method,
                    "status": w.status,
                    "account": w.account,
                    "admin_note": w.admin_note,
                    "processed_at": w.processed_at,
                    "created_at": w.created_at,
                }
                for w in session.scalars(stmt).all()
            ]
        finally:
            session.close()

    def update_withdrawal_status(self, withdrawal_id: str, status: str, admin_note: str = "") -> bool:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            w = session.scalars(select(Withdrawal).filter(
                Withdrawal.withdrawal_id == withdrawal_id
            ).with_for_update()).first()
            if not w:
                return False
            if w.status in ("completed", "rejected"):
                session.commit()
                return True
            w.status = status
            w.admin_note = admin_note
            w.processed_at = datetime.now().isoformat()
            agent = session.scalars(select(Agent).filter(
                Agent.agent_id == w.agent_id
            ).with_for_update()).first()
            if agent:
                if status == "rejected":
                    refund = w.amount + (w.fee_amount or 0)
                    agent.available_balance += refund
                    agent.frozen_balance -= refund
                elif status == "completed":
                    agent.withdrawn_amount += w.amount
                    agent.frozen_balance -= (w.amount + (w.fee_amount or 0))
            session.commit()
            return True
        except Exception as e:
            logger.exception("update_withdrawal_status 失败")
            session.rollback()
            return False
        finally:
            session.close()

    def get_withdrawal(self, withdrawal_id: str) -> Optional[Dict[str, Any]]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            w = session.scalars(select(Withdrawal).filter(Withdrawal.withdrawal_id == withdrawal_id)).first()
            if not w:
                return None
            return {
                "withdrawal_id": w.withdrawal_id,
                "agent_id": w.agent_id,
                "amount": w.amount,
                "method": w.method,
                "status": w.status,
                "account": w.account,
                "admin_note": w.admin_note,
                "processed_at": w.processed_at,
                "created_at": w.created_at,
            }
        finally:
            session.close()

    def channel_create(self, name: str, service_type: str, settle_price: float = 0.0) -> Dict[str, Any]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        channel_id = f"CH-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now().isoformat()
        session = self._get_session()
        try:
            ch = Channel(
                channel_id=channel_id, name=name, service_type=service_type,
                settle_price=settle_price,
                created_at=now,
            )
            session.add(ch)
            session.commit()
            return {
                "channel_id": ch.channel_id, "name": ch.name, "service_type": ch.service_type,
                "settle_price": ch.settle_price, "status": ch.status, "created_at": ch.created_at,
            }
        except Exception as e:
            logger.exception("channel_create 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def channel_list(self, service_type: str = "", status: str = "active") -> List[Dict[str, Any]]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            stmt = select(Channel)
            if service_type:
                stmt = stmt.where(Channel.service_type == service_type)
            if status:
                stmt = stmt.where(Channel.status == status)
            return [
                {
                    "channel_id": c.channel_id, "name": c.name, "service_type": c.service_type,
                    "settle_price": c.settle_price, "current_load": c.current_load,
                    "max_load": c.max_load, "completion_rate": c.completion_rate,
                    "avg_speed": c.avg_speed, "score": c.score, "status": c.status,
                    "created_at": c.created_at,
                }
                for c in session.scalars(stmt).all()
            ]
        finally:
            session.close()

    def channel_update(self, channel_id: str, **fields) -> bool:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            count = session.execute(update(Channel).filter(Channel.channel_id == channel_id).values(**fields)).rowcount
            session.commit()
            return count > 0
        except Exception as e:
            logger.exception("channel_update 失败")
            session.rollback()
            return False
        finally:
            session.close()

    def channel_best_for_dispatch(self, service_type: str, needed: int = 1) -> Optional[Dict[str, Any]]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            candidates = session.scalars(select(Channel).filter(
                Channel.service_type == service_type,
                Channel.status == "active",
                Channel.current_load < Channel.max_load,
            ).order_by(Channel.score.desc()).limit(5)).all()
            if not candidates:
                return None
            best = min(candidates, key=lambda c: c.current_load)
            return {
                "channel_id": best.channel_id, "name": best.name,
                "service_type": best.service_type, "settle_price": best.settle_price,
                "current_load": best.current_load, "score": best.score,
            }
        finally:
            session.close()

    def user_invite_create(self, inviter_user_id: str, invited_user_id: str) -> Optional[Dict[str, Any]]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        invite_id = f"UI-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now().isoformat()
        session = self._get_session()
        try:
            existing = session.scalars(select(UserInvite).filter(
                UserInvite.invited_user_id == invited_user_id
            )).first()
            if existing:
                return None
            ui = UserInvite(
                invite_id=invite_id, inviter_user_id=inviter_user_id,
                invited_user_id=invited_user_id, created_at=now,
            )
            session.add(ui)
            session.commit()
            return {"invite_id": invite_id, "inviter_user_id": inviter_user_id, "invited_user_id": invited_user_id}
        except Exception as e:
            logger.exception("user_invite_create 失败")
            session.rollback()
            return None
        finally:
            session.close()

    def user_invite_get_by_invited(self, invited_user_id: str) -> Optional[Dict[str, Any]]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            ui = session.scalars(select(UserInvite).filter(UserInvite.invited_user_id == invited_user_id)).first()
            if not ui:
                return None
            return {
                "invite_id": ui.invite_id, "inviter_user_id": ui.inviter_user_id,
                "invited_user_id": ui.invited_user_id, "total_reward": ui.total_reward,
                "invite_count": ui.invite_count, "created_at": ui.created_at,
            }
        finally:
            session.close()

    def user_invite_get_by_inviter(self, inviter_user_id: str) -> Optional[Dict[str, Any]]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            ui = session.scalars(select(UserInvite).filter(UserInvite.inviter_user_id == inviter_user_id)).first()
            if not ui:
                return None
            return {
                "invite_id": ui.invite_id, "inviter_user_id": ui.inviter_user_id,
                "invited_user_id": ui.invited_user_id, "total_reward": ui.total_reward,
                "invite_count": ui.invite_count, "created_at": ui.created_at,
            }
        finally:
            session.close()

    def user_invite_add_reward(self, inviter_user_id: str, amount: float) -> bool:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            ui = session.scalars(select(UserInvite).filter(UserInvite.inviter_user_id == inviter_user_id)).first()
            if not ui:
                ui = UserInvite(
                    invite_id=f"UI-{uuid.uuid4().hex[:8].upper()}",
                    inviter_user_id=inviter_user_id, invited_user_id="SYSTEM",
                    created_at=datetime.now().isoformat(),
                )
                session.add(ui)
            ui.total_reward = (ui.total_reward or 0) + amount
            if amount > 0:
                ui.invite_count = (ui.invite_count or 0) + 1
            session.commit()
            return True
        except Exception as e:
            logger.exception("user_invite_add_reward 失败")
            session.rollback()
            return False
        finally:
            session.close()

    def config_get(self, key: str) -> Optional[str]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            c = session.scalars(select(SystemConfig).filter(SystemConfig.config_key == key)).first()
            return c.config_value if c else None
        finally:
            session.close()

    def config_set(self, key: str, value: str) -> bool:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        now = datetime.now().isoformat()
        session = self._get_session()
        try:
            session.merge(SystemConfig(config_key=key, config_value=value, updated_at=now))
            session.commit()
            return True
        except Exception as e:
            logger.exception("config_set 失败")
            session.rollback()
            return False
        finally:
            session.close()

    def config_all(self) -> Dict[str, str]:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            return {c.config_key: c.config_value for c in session.scalars(select(SystemConfig)).all()}
        finally:
            session.close()

    def audit_log(self, event_type: str, operator: str = "system", detail: str = "",
                  order_id: str = "", agent_id: str = "", user_id: str = ""):
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        log_id = f"AL-{uuid.uuid4().hex[:12].upper()}"
        now = datetime.now().isoformat()
        session = self._get_session()
        try:
            al = AuditLog(
                log_id=log_id, event_type=event_type, operator=operator,
                detail=detail, order_id=order_id, agent_id=agent_id,
                user_id=user_id, created_at=now,
            )
            session.add(al)
            session.commit()
        except Exception as e:
            logger.exception("audit_log 失败")
            session.rollback()
        finally:
            session.close()

    def clear_commissions(self) -> int:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            count = session.execute(update(Commission).filter(
                Commission.deleted_at.is_(None),
            ).values(deleted_at=datetime.now().isoformat())).rowcount
            session.commit()
            return count
        except Exception as e:
            logger.exception("clear_commissions 失败")
            session.rollback()
            return 0
        finally:
            session.close()

    def clear_withdrawals(self) -> int:
        Agent, Commission, Withdrawal, Channel, UserInvite, SystemConfig, AuditLog, User = _resolve_models()
        session = self._get_session()
        try:
            count = session.execute(update(Withdrawal).filter(
                Withdrawal.deleted_at.is_(None),
            ).values(deleted_at=datetime.now().isoformat())).rowcount
            session.commit()
            return count
        except Exception as e:
            logger.exception("clear_withdrawals 失败")
            session.rollback()
            return 0
        finally:
            session.close()

    def count_referrals(self, agent_id: str) -> int:
        """统计代理的下级代理数量"""
        Agent, *_ = _resolve_models()
        session = self._get_session()
        try:
            return session.scalar(select(func.count(Agent.agent_id)).filter(
                Agent.parent_agent_id == agent_id
            ))
        finally:
            session.close()

    def get_agent_stats(self) -> Dict[str, Any]:
        """代理系统总览统计"""
        Agent, Commission, Withdrawal, *_ = _resolve_models()
        session = self._get_session()
        try:
            total = session.scalar(select(func.count(Agent.agent_id)))
            active = session.scalar(select(func.count(Agent.agent_id)).filter(Agent.status == "active"))
            suspended = session.scalar(select(func.count(Agent.agent_id)).filter(Agent.status == "suspended"))
            total_commission = session.scalar(select(func.coalesce(func.sum(Commission.commission_amount), 0.0)))
            total_withdrawn = session.scalar(select(func.coalesce(func.sum(Withdrawal.amount), 0.0)).filter(
                Withdrawal.status == "completed"))
            pending_withdrawals = session.scalar(select(func.count(Withdrawal.withdrawal_id)).filter(
                Withdrawal.status == "pending"))
            return {
                "total_agents": total,
                "active_agents": active,
                "suspended_agents": suspended,
                "total_commission": round(float(total_commission), 2),
                "total_withdrawn": round(float(total_withdrawn), 2),
                "pending_withdrawals": pending_withdrawals,
            }
        finally:
            session.close()

    def get_commissions(self, agent_id: str = None, agent_ids: list = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """佣金列表（admin_agents 路由调用的名称）"""
        return self.list_commissions(agent_id=agent_id, agent_ids=agent_ids, limit=limit, offset=offset)

    def get_withdraw_rules(self) -> Dict[str, Any]:
        """获取提现规则配置"""
        defaults = {
            "min_amount": 10.0,
            "max_daily_count": 3,
            "max_daily_amount": 5000.0,
            "fee_rate": 0.0,
            "fee_fixed": 0.0,
            "settlement_cycle": "instant",
            "auto_approve_max": 0.0,
            "presets": "10,50,100,200,500",
        }
        try:
            rules = {}
            for key, default_val in defaults.items():
                db_key = f"withdraw_{key}"
                val = self.config_get(db_key)
                if val:
                    if isinstance(default_val, float):
                        rules[key] = float(val)
                    elif isinstance(default_val, int):
                        rules[key] = int(val)
                    else:
                        rules[key] = val
                else:
                    rules[key] = default_val
            return rules
        except Exception:
            return defaults

    def set_platform_setting(self, key: str, value: str):
        """设置平台配置（兼容 admin_agents 路由调用）"""
        self.config_set(key, value)

"""Config (SystemConfig) and Audit operations mixin"""

import uuid
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import select

from api.db._base import _db_logger

logger = _db_logger

# Lazy-loaded model references
_SystemConfig = _AuditLog = None


def _resolve_models():
    global _SystemConfig, _AuditLog
    if _SystemConfig is None:
        from api.db.models import AuditLog, SystemConfig
        _SystemConfig, _AuditLog = SystemConfig, AuditLog
    return _SystemConfig, _AuditLog


class ConfigDBMixin:
    def config_get(self, key: str) -> Optional[str]:
        SystemConfig, AuditLog = _resolve_models()
        session = self._get_session()
        try:
            c = session.scalars(select(SystemConfig).filter(SystemConfig.config_key == key)).first()
            return c.config_value if c else None
        finally:
            session.close()

    def config_set(self, key: str, value: str) -> bool:
        SystemConfig, AuditLog = _resolve_models()
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
        SystemConfig, AuditLog = _resolve_models()
        session = self._get_session()
        try:
            return {c.config_key: c.config_value for c in session.scalars(select(SystemConfig)).all()}
        finally:
            session.close()

    def audit_log(self, event_type: str, operator: str = "system", detail: str = "",
                  order_id: str = "", user_id: str = ""):
        SystemConfig, AuditLog = _resolve_models()
        log_id = f"AL-{uuid.uuid4().hex[:12].upper()}"
        now = datetime.now().isoformat()
        session = self._get_session()
        try:
            al = AuditLog(
                log_id=log_id, event_type=event_type, operator=operator,
                detail=detail, order_id=order_id,
                user_id=user_id, created_at=now,
            )
            session.add(al)
            session.commit()
        except Exception as e:
            logger.exception("audit_log 失败")
            session.rollback()
        finally:
            session.close()

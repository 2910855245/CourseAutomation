import json
from contextlib import contextmanager
from typing import Any, Dict

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

# 模型定义已移至 api.db.models，此处重新导出以保持兼容
from api.db.models import (
    AuditLog,
    Base,
    ChaoxingJobModel,
    JobBase,
    Order,
    SchoolJobModel,
    User,
    VmqSetting,
    YpaySetting,
)
from api.db_engine import USE_MYSQL, engine

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

from loguru import logger

import re as _re

# 白名单：只允许已知表名，防止 SQL 注入
_KNOWN_TABLES = {
    "users", "orders", "wallet_transactions", "agents", "commissions",
    "withdrawals", "ypay_account", "ypay_order", "ypay_config",
    "pricing_config", "ads", "sub_admins", "login_logs", "risk_config",
    "risk_blacklist", "risk_logs", "task_queue", "study_records",
    "proxy_config", "admin_settings",
}
# 列名只允许小写字母和下划线
_COL_RE = _re.compile(r'^[a-z_][a-z0-9_]*$')
# 列定义只允许安全字符（类型、NOT NULL、DEFAULT 等）
_COL_DEF_RE = _re.compile(r'^[a-zA-Z0-9_\s(),.]+$', )


def _validate_table_name(table_name: str):
    if table_name not in _KNOWN_TABLES:
        raise ValueError(f"未知表名: {table_name}")


def _validate_column_name(col: str):
    if not _COL_RE.match(col):
        raise ValueError(f"非法列名: {col}")


def _validate_column_def(col_def: str):
    if not _COL_DEF_RE.match(col_def):
        raise ValueError(f"非法列定义: {col_def}")


def _get_existing_columns(table_name: str) -> set:
    """获取表中已存在的列名"""
    _validate_table_name(table_name)
    try:
        with engine.connect() as _conn:
            if USE_MYSQL:
                result = _conn.execute(text(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name"
                ), {"table_name": table_name})
                return {row[0] for row in result}
            else:
                # SQLite PRAGMA 不支持参数绑定，但已通过白名单校验
                result = _conn.execute(text(f"PRAGMA table_info({table_name})"))
                return {row[1] for row in result}
    except Exception as e:
        return set()


def _add_columns_if_missing(table_name: str, columns: dict):
    """只添加不存在的列"""
    _validate_table_name(table_name)
    existing = _get_existing_columns(table_name)
    for col, col_def in columns.items():
        if col in existing:
            continue
        _validate_column_name(col)
        _validate_column_def(col_def)
        try:
            with engine.connect() as _conn:
                _conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col} {col_def}"))
                _conn.commit()
            logger.info(f"迁移: 添加列 table={table_name} column={col}")
        except Exception as e:
            logger.warning(f"迁移失败 table={table_name} column={col} error={str(e)}")


def init_db():
    Base.metadata.create_all(bind=engine)

    _add_columns_if_missing("ypay_account", {
        "alipay_appid": "VARCHAR(255) DEFAULT ''",
        "alipay_public_key": "TEXT",
        "alipay_private_key": "TEXT",
        "cookie": "TEXT",
        "wx_guid": "VARCHAR(255) DEFAULT ''",
        "qq": "VARCHAR(255) DEFAULT ''",
        "cloud_id": "VARCHAR(255) DEFAULT ''",
        "qr_type": "VARCHAR(255) DEFAULT ''",
        "memo": "TEXT",
        "remark": "TEXT",
        "channel_mode": "INTEGER DEFAULT 1",
        "app_public_cert": "TEXT",
        "alipay_public_cert": "TEXT",
        "alipay_root_cert": "TEXT",
    })

    _add_columns_if_missing("agents", {
        "wechat_qr": "VARCHAR(255) DEFAULT ''",
        "welcome_text": "TEXT",
        "contact": "VARCHAR(255) DEFAULT ''",
        "managed_by": "VARCHAR(255) DEFAULT ''",
    })

    _add_columns_if_missing("withdrawals", {
        "fee_amount": "FLOAT DEFAULT 0.0",
    })
    # Migrate vmq_settings data to ypay_settings if ypay_settings is empty
    try:
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            ypay_count = session.scalar(select(func.count()).select_from(YpaySetting))
            if ypay_count == 0:
                vmq_rows = session.scalars(select(VmqSetting)).all()
                if vmq_rows:
                    for row in vmq_rows:
                        session.add(YpaySetting(key=row.key, value=row.value))
                    session.commit()
                    from loguru import logger
                    logger.info(f"migrated_vmq_settings_to_ypay count={len(vmq_rows)}")
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"VMQ设置迁移到YPAY失败 error={str(e)}")
        pass


init_db()


from api.crypto import decrypt_password


def _order_to_dict(order: Order) -> Dict[str, Any]:
    d = {
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
    return d


def _user_to_dict(user: User) -> Dict[str, Any]:
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


from loguru import logger

from api.db.agent_db import AgentDBMixin
from api.db.order_db import OrderDBMixin
from api.db.payment_db import PaymentDBMixin
from api.db.user_db import UserDBMixin


class Database(UserDBMixin, OrderDBMixin, AgentDBMixin, PaymentDBMixin):
    def __init__(self):
        self._session_factory = SessionLocal

    def _get_session(self) -> Session:
        return self._session_factory()

    @contextmanager
    def _session_scope(self):
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            logger.exception("_session_scope 失败")
            session.rollback()
            raise
        finally:
            session.close()

    def _order_to_dict(self, order) -> Dict[str, Any]:
        return _order_to_dict(order)

    def _user_to_dict(self, user) -> Dict[str, Any]:
        return _user_to_dict(user)


db = Database()

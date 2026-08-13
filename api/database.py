import json
import os
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
from api.db_engine import engine

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

from loguru import logger

import re as _re

# 白名单：只允许已知表名，防止 SQL 注入
_KNOWN_TABLES = {
    "users", "orders", "audit_logs",
    "ypay_account", "ypay_order", "ypay_config",
    "pricing_config", "ads", "sub_admins", "login_logs", "risk_config",
    "risk_blacklist", "risk_logs", "task_queue", "study_records",
    "proxy_config", "admin_settings",
}
# 列名只允许小写字母和下划线
_COL_RE = _re.compile(r'^[a-z_][a-z0-9_]*$')
# 列定义只允许安全字符（类型、NOT NULL、DEFAULT 等；含单引号以支持字符串默认值）
_COL_DEF_RE = _re.compile(r"^[a-zA-Z0-9_\s(),.'-]+$")


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


def _migrate_legacy_encrypted_passwords():
    """一次性迁移：把历史 ENC:/ENC2: 加密的订单密码解密为明文。

    密码已改为明文存储，此迁移只为兼容旧库数据；迁移完成后不再有加解密逻辑。
    依赖旧的 PASSWORD_ENCRYPTION_KEY 环境变量（若历史 .env 仍保留该键）。
    """
    import base64
    import hashlib

    _key_env = os.environ.get("PASSWORD_ENCRYPTION_KEY", "")
    if not _key_env:
        return
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        return
    derived = hashlib.sha256(_key_env.encode()).digest()

    def _decrypt_legacy(stored: str) -> str:
        if stored.startswith("ENC2:"):
            raw = base64.b64decode(stored[len("ENC2:"):])
            nonce, ct = raw[:12], raw[12:]
            return AESGCM(derived).decrypt(nonce, ct, None).decode("utf-8")
        if stored.startswith("ENC:"):
            raw = base64.b64decode(stored[len("ENC:"):])
            return bytes(b ^ derived[i % len(derived)] for i, b in enumerate(raw)).decode("utf-8")
        return stored

    try:
        session = SessionLocal()
        try:
            rows = session.scalars(
                select(Order).filter(
                    Order.password.like("ENC:%") | Order.password.like("ENC2:%")
                )
            ).all()
            for o in rows:
                try:
                    o.password = _decrypt_legacy(o.password)
                except Exception:
                    continue  # 解不开的旧行保持原样，不阻塞启动
            session.commit()
            if rows:
                logger.info(f"迁移: 旧加密订单密码已转明文 count={len(rows)}")
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"迁移失败 旧密码转明文 error={str(e)}")


def _rebuild_legacy_table(table_model, legacy_cols):
    """旧库表残留已废弃的 NOT NULL 列（模型已不再写入），重建表以去除。

    - 按当前模型 DDL 重建表并迁移数据
    """
    tbl = table_model.__tablename__
    existing = _get_existing_columns(tbl)
    hits = [c for c in legacy_cols if c in existing]
    if not hits:
        return
    try:
        from sqlalchemy.schema import CreateTable
        ddl = str(CreateTable(table_model.__table__).compile(dialect=engine.dialect))
        new_ddl = ddl.replace(f"CREATE TABLE {tbl}", f"CREATE TABLE {tbl}_new")
        keep = [c.name for c in table_model.__table__.columns]
        cols_sql = ", ".join(f'"{c}"' for c in keep)
        with engine.connect() as _conn:
            _conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            _conn.execute(text(new_ddl))
            _conn.execute(text(f'INSERT INTO {tbl}_new ({cols_sql}) SELECT {cols_sql} FROM {tbl}'))
            _conn.execute(text(f"DROP TABLE {tbl}"))
            _conn.execute(text(f"ALTER TABLE {tbl}_new RENAME TO {tbl}"))
            _conn.commit()
        logger.info(f"迁移: 表 {tbl} 已重建（移除遗留列 {hits}）")
    except Exception as e:
        logger.warning(f"迁移失败 重建表 {tbl} error={str(e)}")


def init_db():
    Base.metadata.create_all(bind=engine)

    _migrate_legacy_encrypted_passwords()

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

    # paid_processed: 支付处理幂等列（取代 commission_status 的幂等语义）
    _orders_cols_before = _get_existing_columns("orders")
    _add_columns_if_missing("orders", {
        "paid_processed": "VARCHAR(32) DEFAULT 'unprocessed'",
    })
    if "paid_processed" not in _orders_cols_before and "commission_status" in _orders_cols_before:
        try:
            with engine.connect() as _conn:
                _conn.execute(text(
                    "UPDATE orders SET paid_processed = commission_status "
                    "WHERE commission_status IN ('processing', 'processed')"
                ))
                _conn.commit()
            logger.info("迁移: orders.paid_processed 已从 commission_status 拷贝旧值")
        except Exception as e:
            logger.warning(f"迁移失败 paid_processed 拷贝 error={str(e)}")

    # 旧库遗留 NOT NULL 列（commission_status/inviter_code/agent_id）会导致模型插入失败，重建表
    _rebuild_legacy_table(Order, ("commission_status", "inviter_code"))
    _rebuild_legacy_table(AuditLog, ("agent_id",))

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
                    logger.info(f"migrated_vmq_settings_to_ypay count={len(vmq_rows)}")
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"VMQ设置迁移到YPAY失败 error={str(e)}")
        pass




def _user_to_dict(user: User) -> Dict[str, Any]:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "password_hash": user.password_hash,
        "nickname": user.nickname,
        "contact": user.contact,
        "role": user.role,
        "created_at": user.created_at,
        "last_login": user.last_login,
    }


from loguru import logger

from api.db.config_db import ConfigDBMixin
from api.db.order_db import OrderDBMixin
from api.db.payment_db import PaymentDBMixin
from api.db.user_db import UserDBMixin


class Database(UserDBMixin, OrderDBMixin, ConfigDBMixin, PaymentDBMixin):
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
        from api.db.order_db import _order_to_dict
        return _order_to_dict(order)

    def _user_to_dict(self, user) -> Dict[str, Any]:
        return _user_to_dict(user)


db = Database()

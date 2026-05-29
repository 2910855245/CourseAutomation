"""Shared imports, logger, and soft-delete filter for database mixins"""

from sqlalchemy import event
from sqlalchemy.orm import Session

from loguru import logger

_db_logger = logger


@event.listens_for(Session, "do_orm_execute")
def _soft_delete_filter(orm_execute_state):
    """自动为所有带 deleted_at 字段的模型查询追加 WHERE deleted_at IS NULL"""
    if not orm_execute_state.is_select:
        return

    stmt = orm_execute_state.statement
    for desc in stmt.column_descriptions:
        entity = desc.get("entity")
        if entity is not None and hasattr(entity, "deleted_at"):
            stmt = stmt.filter(entity.deleted_at.is_(None))
            orm_execute_state.statement = stmt
            break

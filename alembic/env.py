import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 从环境变量读取数据库 URL
database_url = os.environ.get("DATABASE_URL", "sqlite:///data/orders.db")
config.set_main_option("sqlalchemy.url", database_url)

# 导入模型 metadata 用于 autogenerate
# 合并两个 metadata（主表 + 队列表）
from sqlalchemy import MetaData  # noqa: E402

from api.db.models import Base  # noqa: E402
from api.services.task_queue import JobBase  # noqa: E402

target_metadata = MetaData()
for table in Base.metadata.tables.values():
    table.tometadata(target_metadata)
for table in JobBase.metadata.tables.values():
    table.tometadata(target_metadata)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""SQLite 引擎（唯一存储）。

单机单运营场景下 SQLite WAL + busy_timeout 完全够用；
零额外内存/进程，备份 = sqlite3 .backup 一条命令。
"""

import os

from sqlalchemy import create_engine, text

from config import settings

DB_PATH = settings.db_path

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},
)
with engine.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL"))
    conn.execute(text("PRAGMA foreign_keys=ON"))
    conn.execute(text("PRAGMA busy_timeout=5000"))
    conn.commit()

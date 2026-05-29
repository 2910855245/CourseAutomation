import os

from sqlalchemy import create_engine, text

from config import settings

DB_PATH = settings.db_path
DATABASE_URL = settings.database_url
USE_MYSQL = DATABASE_URL.startswith("mysql") if DATABASE_URL else False

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

if USE_MYSQL:
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        pool_pre_ping=True,
    )
else:
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()

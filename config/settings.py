"""纯环境配置：Settings 定义与校验。无任何 import 副作用。"""

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(ROOT_DIR, ".env"))


class Settings(BaseSettings):
    jwt_secret_key: str = Field(default="", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_hours: int = Field(default=72, alias="JWT_EXPIRE_HOURS")
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    debug: bool = Field(default=False, alias="DEBUG")
    db_path: str = Field(default="data/orders.db", alias="DB_PATH")
    database_url: str = Field(default="", alias="DATABASE_URL")
    rate_limit_requests: int = Field(default=600, alias="RATE_LIMIT_REQUESTS")
    rate_limit_window_seconds: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    site_url: str = Field(default="http://localhost:8000", alias="SITE_URL")
    vmqpay_url: str = Field(default="", alias="VMQPAY_URL")
    vmqpay_key: str = Field(default="", alias="VMQPAY_KEY")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")
    worker_token: str = Field(default="", alias="WORKER_TOKEN")
    captcha_ak: str = Field(default="", alias="CAPTCHA_AK")
    captcha_url: str = Field(default="", alias="CAPTCHA_URL")

    model_config = {"env_file": os.path.join(ROOT_DIR, ".env"), "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def validate_settings() -> None:
    """必填配置校验。由 run.py / manage.py / worker bootstrap 显式调用。"""
    _missing = [name for name, val in (
        ("JWT_SECRET_KEY", settings.jwt_secret_key),
        ("DATABASE_URL", settings.database_url),
    ) if not val]
    if _missing:
        from loguru import logger
        logger.error(f"缺少必填环境变量 missing={_missing}")
        raise SystemExit(1)

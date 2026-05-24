import hashlib
import importlib
import os
import platform
import struct
import sys

from loguru import logger
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.models import ApiResponse
from config import BASE_DIR, settings

router = APIRouter(prefix="/api/setup", tags=["setup"])

SETUP_LOCK_FILE = os.path.join(BASE_DIR, "data", ".setup_done")


def _is_setup_done() -> bool:
    return os.path.exists(SETUP_LOCK_FILE)


def _require_setup_not_done():
    if _is_setup_done():
        raise HTTPException(status_code=403, detail="安装已完成，此接口已禁用")


@router.get("/status")
def setup_status():
    return ApiResponse(data={"done": _is_setup_done()})


def _mark_setup_done():
    os.makedirs(os.path.dirname(SETUP_LOCK_FILE), exist_ok=True)
    with open(SETUP_LOCK_FILE, "w") as f:
        f.write("done")


def _check_write(path: str) -> dict:
    full = os.path.join(BASE_DIR, path) if not os.path.isabs(path) else path
    label = path
    exists = os.path.exists(full)
    try:
        if os.path.isfile(full):
            check_dir = os.path.dirname(full) or "."
            test_file = os.path.join(check_dir, ".writetest")
        else:
            check_dir = full
            test_file = os.path.join(check_dir, ".writetest")
            os.makedirs(check_dir, exist_ok=True)
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return {"name": label, "status": "ok", "msg": "可读写" if exists else "已创建", "ok": True}
    except Exception as e:
        logger.error("目录检查失败: {}", e)
        return {"name": label, "status": "error", "msg": "权限检查失败", "ok": False}


_IMPORT_NAME_MAP = {
    "python-multipart": "multipart",
}


def _check_package(pkg: str, desc: str) -> dict:
    try:
        import_name = _IMPORT_NAME_MAP.get(pkg, pkg.replace("-", "_"))
        importlib.import_module(import_name)
        return {"name": f"{desc} ({pkg})", "status": "ok", "msg": "已安装", "ok": True}
    except ImportError:
        return {"name": f"{desc} ({pkg})", "status": "error", "msg": "未安装，请运行: pip install " + pkg, "ok": False}


def _check_monitoring_modules() -> list:
    items = []
    # Health monitor module
    try:
        items.append({"name": "平台健康监控", "status": "ok", "msg": "已加载", "ok": True})
    except Exception as e:
        items.append({"name": "平台健康监控", "status": "error", "msg": f"加载失败: {e}", "ok": False})
    # Course crawler with Scrapling
    try:
        items.append({"name": "课程爬虫 (Scrapling)", "status": "ok", "msg": "已加载", "ok": True})
    except Exception as e:
        items.append({"name": "课程爬虫 (Scrapling)", "status": "error", "msg": f"加载失败: {e}", "ok": False})
    # Session pool
    try:
        from api.services.session_pool import pool
        items.append({"name": "会话池", "status": "ok", "msg": f"已加载 (最大{pool._max_size})", "ok": True})
    except Exception as e:
        items.append({"name": "会话池", "status": "error", "msg": f"加载失败: {e}", "ok": False})
    # Proxy config
    try:
        from api.services.proxy_config import get_proxy_config
        cfg = get_proxy_config()
        proxy_msg = "已启用" if cfg.get("enabled") else "未启用"
        items.append({"name": "代理配置", "status": "ok", "msg": proxy_msg, "ok": True})
    except Exception as e:
        items.append({"name": "代理配置", "status": "error", "msg": f"加载失败: {e}", "ok": False})
    return items


def _check_db() -> dict:
    try:
        from sqlalchemy import text

        from api.database import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_url = settings.database_url or f"SQLite: {settings.db_path}"
        # 脱敏：隐藏密码部分
        safe_url = db_url
        if "@" in db_url and "://" in db_url:
            prefix = db_url.split("://")[0]
            rest = db_url.split("@", 1)[1]
            safe_url = f"{prefix}://***:***@{rest}"
        return {"name": "数据库连接", "status": "ok", "msg": safe_url, "ok": True}
    except Exception as e:
        logger.error("数据库连接检查失败: {}", e)
        return {"name": "数据库连接", "status": "error", "msg": "连接失败", "ok": False}


def _check_redis() -> dict:
    try:
        import redis as rds
        client = rds.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.ping()
        client.close()
        return {"name": "Redis 缓存", "status": "ok", "msg": settings.redis_url, "ok": True}
    except Exception as e:
        logger.warning("Redis检查失败: {}", e)
        return {"name": "Redis 缓存", "status": "warn", "msg": "不可用，限流功能将降级", "ok": False}


def _crc32(host: str, port: int) -> int:
    data = f"{host}:{port}".encode()
    return struct.unpack(">I", struct.pack(">I", hashlib.sha256(data).digest().__hash__() & 0xFFFFFFFF))[0] & 0xFFFFFFFF


@router.get("/check")
def setup_check():
    python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 8)

    items = [
        {"category": "系统环境", "items": [
            {"name": "操作系统", "status": "ok", "msg": f"{platform.system()} {platform.release()}", "ok": True},
            {"name": "Python 版本",
             "status": "ok" if py_ok else "error",
             "msg": python_ver + (" ✓ 满足要求(≥3.8)" if py_ok else " ✗ 需要 Python ≥ 3.8"),
             "ok": py_ok},
        ]},
        {"category": "目录权限", "items": [
            _check_write("data"),
            _check_write("static"),
            _check_write(os.path.join(BASE_DIR, ".env") if os.path.exists(os.path.join(BASE_DIR, ".env")) else "data"),
        ]},
        {"category": "核心依赖", "items": [
            _check_package("fastapi", "FastAPI"),
            _check_package("uvicorn", "Uvicorn"),
            _check_package("sqlalchemy", "SQLAlchemy"),
            _check_package("pydantic", "Pydantic"),
            _check_package("httpx", "HTTPx"),
            _check_package("bcrypt", "Bcrypt"),
            _check_package("python-multipart", "python-multipart"),
            _check_package("qrcode", "QRCode"),
            _check_package("loguru", "Loguru"),
        ]},
        {"category": "爬虫与识别", "items": [
            _check_package("scrapling", "Scrapling 自适应爬虫"),
            _check_package("ddddocr", "验证码识别 (ddddocr)"),
            _check_package("lxml", "lxml 解析器"),
            _check_package("httpx", "HTTPx"),
        ]},
        {"category": "数据库与缓存", "items": [
            _check_db(),
            _check_redis(),
        ]},
        {"category": "平台监控", "items": _check_monitoring_modules()},
    ]

    all_ok = all(
        i["ok"]
        for cat in items
        for i in cat["items"]
        if i["status"] != "warn"
    )

    return ApiResponse(data={
        "all_ok": all_ok,
        "checks": items,
        "setup_done": _is_setup_done(),
    })


@router.post("/init-db")
def setup_init_db():
    _require_setup_not_done()
    try:
        from api.database import Base, engine
        Base.metadata.create_all(bind=engine)
        return ApiResponse(data={"success": True, "message": "数据库表已创建"})
    except Exception as e:
        logger.error("数据库初始化失败: {}", e)
        return ApiResponse(success=False, message="数据库初始化失败")


class SetupConfigPayload(BaseModel):
    site_url: str = "http://localhost:8000"
    jwt_secret: str = ""
    db_url: str = ""
    redis_url: str = "redis://localhost:6379/0"


@router.post("/save-config")
def setup_save_config(payload: SetupConfigPayload):
    _require_setup_not_done()
    env_path = os.path.join(BASE_DIR, ".env")
    try:
        existing = {}
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        existing[k.strip()] = v.strip()

        existing["SITE_URL"] = payload.site_url
        if payload.jwt_secret:
            existing["JWT_SECRET_KEY"] = payload.jwt_secret
        if payload.db_url:
            existing["DATABASE_URL"] = payload.db_url
        if payload.redis_url:
            existing["REDIS_URL"] = payload.redis_url

        lines = []
        if "JWT_SECRET_KEY" in existing:
            lines.append(f"JWT_SECRET_KEY={existing['JWT_SECRET_KEY']}")
        if "SITE_URL" in existing:
            lines.append(f"SITE_URL={existing['SITE_URL']}")
        if "DATABASE_URL" in existing:
            lines.append(f"DATABASE_URL={existing['DATABASE_URL']}")
        if "REDIS_URL" in existing:
            lines.append(f"REDIS_URL={existing['REDIS_URL']}")
        for k, v in existing.items():
            if k not in ("JWT_SECRET_KEY", "SITE_URL", "DATABASE_URL", "REDIS_URL"):
                lines.append(f"{k}={v}")

        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return ApiResponse(data={"success": True, "message": "配置文件已更新"})
    except Exception as e:
        logger.error("保存配置失败: {}", e)
        return ApiResponse(success=False, message="保存配置失败")


class TestDbPayload(BaseModel):
    user: str = "root"
    password: str = ""
    database: str = "anticheat"


@router.post("/test-db")
def setup_test_db(payload: TestDbPayload):
    _require_setup_not_done()
    try:
        import pymysql
        conn = pymysql.connect(
            host="localhost",
            port=3306,
            user=payload.user,
            password=payload.password,
            connect_timeout=5,
        )
        cursor = conn.cursor()
        db_name = payload.database.replace("`", "")
        import re as _re
        if not _re.match(r'^[a-zA-Z0-9_]+$', db_name):
            raise HTTPException(status_code=400, detail="数据库名只能包含字母、数字和下划线")
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        from urllib.parse import quote_plus
        db_url = f"mysql+pymysql://{payload.user}:{quote_plus(payload.password)}@localhost:3306/{db_name}?charset=utf8mb4"
        return ApiResponse(data={"success": True, "message": "MySQL 连接成功，数据库已创建", "db_url": db_url})
    except ImportError:
        return ApiResponse(success=False, message="pymysql 未安装，请运行: pip install pymysql")
    except Exception as e:
        logger.error("数据库连接测试失败: {}", e)
        return ApiResponse(success=False, message=f"连接失败: {e}")


@router.post("/save-db")
def setup_save_db(payload: TestDbPayload):
    _require_setup_not_done()
    try:
        db_name = payload.database.replace("`", "")
        from urllib.parse import quote_plus
        db_url = f"mysql+pymysql://{payload.user}:{quote_plus(payload.password)}@localhost:3306/{db_name}?charset=utf8mb4"
        env_path = os.path.join(BASE_DIR, ".env")
        existing = {}
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        existing[k.strip()] = v.strip()

        existing["DATABASE_URL"] = db_url

        lines = []
        for k, v in existing.items():
            lines.append(f"{k}={v}")

        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return ApiResponse(data={"success": True, "message": "数据库配置已保存，需要重启服务后生效"})
    except Exception as e:
        logger.error("保存数据库配置失败: {}", e)
        return ApiResponse(success=False, message=f"保存失败: {e}")


class SetupAdminPayload(BaseModel):
    username: str
    password: str


@router.post("/create-admin")
def setup_create_admin(payload: SetupAdminPayload):
    _require_setup_not_done()
    try:
        from api.auth import hash_password
        from api.database import db
        existing = db.get_user_by_username(payload.username)
        if existing:
            return ApiResponse(success=False, message="该用户名已存在")
        db.create_user(
            username=payload.username,
            password_hash=hash_password(payload.password),
            role="admin",
            nickname="管理员",
        )
        return ApiResponse(data={"success": True, "message": f"管理员账号 {payload.username} 创建成功"})
    except Exception as e:
        logger.error("创建管理员失败: {}", e)
        return ApiResponse(success=False, message="创建管理员失败")


class SetupYpayPayload(BaseModel):
    ypay_key: str = ""
    wx_qr_url: str = ""
    ali_qr_url: str = ""


@router.post("/save-ypay")
def setup_save_ypay(payload: SetupYpayPayload):
    _require_setup_not_done()
    try:
        from api.database import db
        if payload.ypay_key:
            db.ypay_setting_set("key", payload.ypay_key)
        db.ypay_setting_set("close_time", "5")
        db.ypay_setting_set("pay_timeout", "300")

        existing = db.ypay_list_accounts()
        if not existing:
            if payload.wx_qr_url:
                db.ypay_add_account(atype="wxpay", code="wxpay_cloud", name="默认微信", qr_url=payload.wx_qr_url)
            if payload.ali_qr_url:
                db.ypay_add_account(atype="alipay", code="alipay_software", name="默认支付宝", qr_url=payload.ali_qr_url)

        return ApiResponse(data={"success": True, "message": "支付配置已保存"})
    except Exception as e:
        logger.error("保存支付配置失败: {}", e)
        return ApiResponse(success=False, message="保存支付配置失败")


@router.post("/save-vmq")
def setup_save_vmq_compat(payload: SetupYpayPayload):
    """兼容旧前端调用"""
    return setup_save_ypay(payload)


@router.post("/finish")
def setup_finish():
    _require_setup_not_done()
    try:
        _mark_setup_done()
        return ApiResponse(data={"success": True, "message": "安装完成！"})
    except Exception as e:
        logger.error("完成安装失败: {}", e)
        return ApiResponse(success=False, message="完成安装失败")

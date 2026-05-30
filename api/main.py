from __future__ import annotations

import os
import platform
import sys
import threading
import time
from contextlib import asynccontextmanager
from typing import Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

# --- loguru 配置：文件轮转 + 上下文绑定 ---
_log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "logs")
os.makedirs(_log_dir, exist_ok=True)

# 移除默认 stderr handler，重新添加带格式的
logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | {message}")

# 文件日志：按 10MB 轮转，保留 30 天，自动压缩
logger.add(
    os.path.join(_log_dir, "app_{time:YYYY-MM-DD}.log"),
    level="DEBUG",
    rotation="10 MB",
    retention="30 days",
    compression="gz",
    encoding="utf-8",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
)

# 错误日志单独文件，方便排查
logger.add(
    os.path.join(_log_dir, "error_{time:YYYY-MM-DD}.log"),
    level="ERROR",
    rotation="10 MB",
    retention="90 days",
    compression="gz",
    encoding="utf-8",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
)

if sys.platform == 'win32':
    ver = platform.version().split('.')
    major, minor = int(ver[0]), int(ver[1])
    if (major, minor) < (6, 1):
        print("当前系统版本过低，仅支持 Windows 7 及以上系统")  # noqa: T201
        sys.exit(1)

import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.auth import get_current_admin
from api.models import ApiResponse
from api.routers import (
    accounts,
    admin,
    admin_ads,
    admin_agents,
    admin_users,
    captcha,
    config_admin,
    courses,
    crack_admin,
    invite,
    orders,
    payment,
    pricing,
    progress,
    queue,
    scan,
    setup,
    sub_admin,
    tasks,
    users,
    wallet,
    ypay_admin,
    ypay_app,
    ypay_routes,
    ypay_vmq,
)
from api.routers import domain_monitor as domain_monitor_router
from api.routers import health as health_router
from api.routers.agents import router as agents_router
from config import settings


@asynccontextmanager
async def lifespan(app):
    from api.startup import run_startup
    run_startup(settings)
    logger.info("API 服务已就绪")
    yield
    # Graceful shutdown
    logger.info("API 服务正在关闭...")
    try:
        from api.services.task_queue import school_queue, chaoxing_queue
        school_queue.stop()
        chaoxing_queue.stop()
        logger.info("任务队列已停止")
    except Exception as e:
        logger.warning(f"关闭队列时出错 error={str(e)}")


_TAGS_METADATA = [
    {"name": "用户管理", "description": "注册、登录、个人资料、修改密码"},
    {"name": "订单管理", "description": "创建订单、重试、取消、查询进度"},
    {"name": "支付管理", "description": "支付创建、回调通知、批量支付、退款"},
    {"name": "代理分销", "description": "代理注册、升级、提现、推荐链接"},
    {"name": "后台管理", "description": "管理员仪表盘、用户管理、订单审核"},
    {"name": "YPay支付", "description": "支付通道管理、订单查询、二维码生成"},
    {"name": "YPay VMQ", "description": "V免签协议：心跳、支付推送回调"},
    {"name": "YPay APP", "description": "Android 监控 APP：配对、心跳、推送"},
    {"name": "健康监控", "description": "平台健康检查、账号检测、间隔配置"},
    {"name": "任务队列", "description": "队列状态、任务列表、暂停/恢复"},
    {"name": "课程扫描", "description": "平台课程列表、扫描进度"},
    {"name": "系统配置", "description": "首次配置向导、全局设置"},
]

app = FastAPI(
    title="在线课程自动化平台 API",
    description=(
        "基于 FastAPI 的全栈在线课程自动化 SaaS 平台。\n\n"
        "支持多平台视频学习、考试辅助；\n"
        "三级代理分销体系；YPay 聚合支付；\n"
        "后台任务队列调度；Android 收款监控 APP。"
    ),
    version="6.0.0",
    openapi_tags=_TAGS_METADATA,
    lifespan=lifespan,
)

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_rate_limit_lock = threading.Lock()
_rate_limit_counters: Dict[str, list] = {}


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """为每条日志自动绑定请求上下文（client_ip + path）"""
    client_ip = request.client.host if request.client else "unknown"
    bound_logger = logger.bind(client_ip=client_ip, path=request.url.path)
    # 替换全局 logger，让后续 handler 中的日志自动带上下文
    import contextvars
    _log_ctx = contextvars.ContextVar('log_ctx', default=None)
    _log_ctx.set(bound_logger)
    response = await call_next(request)
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    # 支付回调/安装向导/YPay通知/课程扫描/验证码 不做限流
    if path.startswith("/api/payment/notify") or path.startswith("/api/setup/") or path.startswith("/api/ypay/vmq/") or path.startswith("/api/courses/") or path.startswith("/api/captcha/"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    key = f"rate:{client_ip}"
    now = time.time()
    window = settings.rate_limit_window_seconds
    max_requests = settings.rate_limit_requests

    from api.redis_client import redis_client
    if redis_client.available:
        try:
            allowed = redis_client.rate_limit_lua(key, max_requests, window)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "请求过于频繁，请稍后再试"},
                    headers={"Retry-After": str(window)},
                )
        except Exception as e:
            pass
    else:
        cutoff = now - window
        with _rate_limit_lock:
            entries = _rate_limit_counters.get(key, [])
            filtered = [t for t in entries if t > cutoff]
            if len(filtered) >= max_requests:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "请求过于频繁，请稍后再试"},
                    headers={"Retry-After": str(window)},
                )
            filtered.append(now)
            _rate_limit_counters[key] = filtered
            if len(_rate_limit_counters) > 10000:
                cutoff_cleanup = now - window * 2
                expired_keys = [k for k, v in _rate_limit_counters.items()
                                if not v or v[-1] < cutoff_cleanup]
                for k in expired_keys:
                    del _rate_limit_counters[k]

    return await call_next(request)


@app.middleware("http")
async def no_cache_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    # 仅对 HTML 页面设置 no-cache，静态资源（CSS/JS/图片）允许浏览器缓存
    if not path.startswith("/api/") and not path.startswith("/appHeart") and not path.startswith("/appPush"):
        is_static = path.startswith("/static/assets/") or path.startswith("/uploads/")
        if not is_static:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
    return response


app.include_router(accounts.router)
app.include_router(scan.router)
app.include_router(courses.router)
app.include_router(progress.router)
app.include_router(tasks.router)
app.include_router(users.router)
app.include_router(wallet.router)
app.include_router(orders.router)
app.include_router(admin.router)
app.include_router(admin_users.router)
app.include_router(admin_ads.router)
app.include_router(admin_ads.public_ads_router)
app.include_router(queue.router)
app.include_router(payment.router)
app.include_router(ypay_routes.router)
app.include_router(ypay_vmq.router)
app.include_router(ypay_app.router)
app.include_router(ypay_admin.router)
app.include_router(agents_router)
app.include_router(admin_agents.router)
app.include_router(crack_admin.router)
app.include_router(config_admin.router)
app.include_router(config_admin.announcement_router)
app.include_router(invite.router)
app.include_router(pricing.router)
app.include_router(sub_admin.router)

app.include_router(ypay_app.raw_router)
app.include_router(setup.router)
app.include_router(captcha.router)
app.include_router(domain_monitor_router.router)
app.include_router(health_router.router)

# --- 监控APP接口 (前端 /api/app/* 代理到 /api/ypay/*) ---
@app.get("/api/app/pair-qrcode", response_model=ApiResponse)
def app_pair_qrcode(request: Request):
    """APP配对二维码 - 使用真实通讯密钥"""
    return ypay_app.ypay_app_qrcode(request)


@app.get("/api/app/pair-status")
def app_pair_status():
    """APP配对状态"""
    return ypay_app.ypay_pair_status()


@app.get("/api/app/info")
def app_info():
    """APP信息"""
    apk_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "ypay-monitor.apk")
    return ApiResponse(data={
        "app_name": "ypay-monitor", "version": "1.0",
        "apk_exists": os.path.exists(apk_path),
        "apk_size_mb": round(os.path.getsize(apk_path) / (1024 * 1024), 2) if os.path.exists(apk_path) else 0,
        "download_url": "/api/ypay/app-download",
    })


@app.get("/api/app/download")
def app_download():
    """APP下载"""
    apk_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "ypay-monitor.apk")
    if os.path.exists(apk_path):
        return FileResponse(apk_path, media_type="application/vnd.android.package-archive", filename="ypay-monitor.apk")
    return JSONResponse({"detail": "APK不存在"}, status_code=404)


@app.get("/api/info")
def api_info():
    return {
        "name": "网课代刷平台 API",
        "version": "6.0.0",
    }


@app.get("/api/redis/health")
def redis_health(admin: dict = Depends(get_current_admin)):
    from api.redis_client import redis_client
    return redis_client.health_check()


@app.get("/api/system/status")
def system_status(admin: dict = Depends(get_current_admin)):
    from api.services.task_manager import manager as tm
    from api.services.task_queue import get_combined_stats
    tasks = tm.list_tasks()
    running = sum(1 for t in tasks if t.status == "running")
    pending = sum(1 for t in tasks if t.status == "pending")
    completed = sum(1 for t in tasks if t.status == "completed")
    failed = sum(1 for t in tasks if t.status == "failed")

    from api.database import db
    order_stats = db.get_stats()

    from api.redis_client import redis_client
    redis_status = redis_client.health_check()

    return {
        "tasks": {
            "running": running,
            "pending": pending,
            "completed": completed,
            "failed": failed,
            "total": len(tasks),
        },
        "queue": get_combined_stats(),
        "orders": order_stats,
        "redis": redis_status,
        "rate_limit": {
            "max_requests": settings.rate_limit_requests,
            "window_seconds": settings.rate_limit_window_seconds,
            "enabled": redis_client.available,
        },
    }


@app.get("/api/admin/dashboard")
def admin_dashboard(admin: dict = Depends(get_current_admin)):
    from api.database import db
    return ApiResponse(data=db.get_dashboard_stats())


app.mount("/static", StaticFiles(directory="static"), name="static")

_uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(_uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_uploads_dir), name="uploads")


@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("api"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": "接口不存在"})
    if full_path in ("appHeart", "appPush"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": "接口不存在"})
    import os
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    file_path = os.path.normpath(os.path.join(static_dir, full_path))
    if not file_path.startswith(os.path.normpath(static_dir) + os.sep) and file_path != os.path.normpath(static_dir):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={"detail": "禁止访问"})
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse("static/index.html")


if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )

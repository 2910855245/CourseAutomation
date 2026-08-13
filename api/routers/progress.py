import asyncio
import glob
import json
import os
import sys
import threading
from typing import List

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from loguru import logger

from api.models import ApiResponse
from services.session_pool import pool as session_pool

router = APIRouter(prefix="/api/progress", tags=["学习进度"])

# WebSocket 连接管理
_ws_clients: List[WebSocket] = []
_MAX_WS_CLIENTS = 50

# Redis Pub/Sub 频道
_WS_CHANNEL = "ws:live:broadcast"


@router.websocket("/ws/live")
async def websocket_progress(websocket: WebSocket):
    """实时进度推送 WebSocket 端点"""
    if len(_ws_clients) >= _MAX_WS_CLIENTS:
        await websocket.close(code=1013, reason="服务器连接数已满")
        return
    await websocket.accept()
    _ws_clients.append(websocket)
    logger.bind(ws_count=len(_ws_clients)).info("WebSocket 客户端连接")
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                await websocket.send_text('{"type":"heartbeat"}')
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)
        logger.bind(ws_count=len(_ws_clients)).debug("WebSocket 客户端断开")


async def _local_broadcast(message: str):
    """向本进程的 WebSocket 客户端广播"""
    if not _ws_clients:
        return
    disconnected = []
    for client in _ws_clients:
        try:
            await client.send_text(message)
        except Exception:
            disconnected.append(client)
    for client in disconnected:
        _ws_clients.remove(client)


async def broadcast_progress(data: dict):
    """向所有 WebSocket 客户端广播进度更新（通过 Redis Pub/Sub 解决多进程问题）"""
    message = json.dumps(data, ensure_ascii=False)
    # 先广播本进程
    await _local_broadcast(message)
    # 再通过 Redis 发布给其他进程
    try:
        from api.redis_client import redis_client
        if redis_client.available:
            redis_client.client.publish(_WS_CHANNEL, message)
    except Exception:
        pass


def _start_redis_subscriber():
    """后台线程：订阅 Redis 频道，将消息广播到本进程的 WebSocket 客户端"""
    import time as _time
    from api.redis_client import redis_client

    if not redis_client.available:
        logger.info("Redis 不可用，跳过 WebSocket 订阅线程")
        return

    def _subscriber():
        while True:
            try:
                if not redis_client.available:
                    _time.sleep(5)
                    redis_client._maybe_reconnect()
                    continue
                pubsub = redis_client.client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(_WS_CHANNEL)
                logger.info("Redis WebSocket 订阅已启动 channel={}", _WS_CHANNEL)
                while True:
                    message = pubsub.get_message(timeout=1.0)
                    if message is None:
                        continue
                    if message["type"] != "message":
                        continue
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8", errors="replace")
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.run_coroutine_threadsafe(_local_broadcast(data), loop)
                        else:
                            loop.run_until_complete(_local_broadcast(data))
                    except RuntimeError:
                        pass
            except Exception as e:
                logger.warning("Redis WebSocket 订阅异常: {}", str(e))
                _time.sleep(3)

    t = threading.Thread(target=_subscriber, daemon=True, name="ws-redis-sub")
    t.start()
    logger.info("Redis WebSocket 订阅线程已启动")


def get_task_status_from_files() -> dict:
    """从任务状态文件读取实时进度"""
    status_files = glob.glob("/tmp/task_*/status.json") if os.name != "nt" else []
    # Windows 路径
    if not status_files:
        import tempfile
        temp_dir = tempfile.gettempdir()
        status_files = glob.glob(os.path.join(temp_dir, "task_*", "status.json"))

    tasks = []
    for f in status_files:
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
                data["status_file"] = f
                tasks.append(data)
        except Exception as e:
            pass
    return {"tasks": tasks, "count": len(tasks)}


@router.get("/live/status", response_model=ApiResponse)
def get_live_status():
    """读取任务状态文件（无鉴权读取进度供调试）"""
    return ApiResponse(data=get_task_status_from_files())


@router.post("/live/push", response_model=ApiResponse)
async def push_progress_update(request: Request, data: dict):
    """接收 worker 推送的进度更新并广播到 WebSocket 客户端

    鉴权：配置 WORKER_TOKEN 后校验 X-Worker-Token（localhost 来源豁免，
    兼容升级窗口期的旧 worker 进程）。
    """
    from config import settings
    if settings.worker_token:
        client_host = request.client.host if request.client else ""
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            import hmac
            token = request.headers.get("X-Worker-Token", "")
            if not token or not hmac.compare_digest(token, settings.worker_token):
                raise HTTPException(status_code=401, detail="无效的 Worker 凭证")
    await broadcast_progress(data)
    return ApiResponse(message="已推送")

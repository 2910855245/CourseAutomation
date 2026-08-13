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
    """向本进程 WebSocket 客户端广播进度更新（单 worker 部署，进程内广播足够）"""
    message = json.dumps(data, ensure_ascii=False)
    await _local_broadcast(message)


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

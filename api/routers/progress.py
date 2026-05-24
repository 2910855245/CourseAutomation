import asyncio
import glob
import json
import os
import sys
from typing import List

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from loguru import logger

from api.models import ApiResponse, ProgressSummary
from api.services.session_pool import pool as session_pool

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


async def broadcast_progress(data: dict):
    """向所有 WebSocket 客户端广播进度更新"""
    if not _ws_clients:
        return
    message = json.dumps(data, ensure_ascii=False)
    disconnected = []
    for client in _ws_clients:
        try:
            await client.send_text(message)
        except Exception as e:
            disconnected.append(client)
    for client in disconnected:
        _ws_clients.remove(client)


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


def _get_session(username: str, password: str, website_id: int):
    try:
        return session_pool.get_or_login(username, password, website_id)
    except Exception as e:
        logger.error("Session获取失败: {}", e)
        raise HTTPException(status_code=401, detail="登录失败，请检查账号信息")


@router.get("/", response_model=ApiResponse)
def get_progress(username: str = Query(...), password: str = Query(...), website_id: int = Query(...)):
    from services.data_loader import DataLoader
    _get_session(username, password, website_id)
    try:
        loader = DataLoader()
        courses = loader.load_courses(force_reload=True)
        records = loader.load_study_records(force_reload=True)

        total_videos = 0
        completed_videos = 0
        total_exams = 0
        completed_exams = 0

        for course in courses:
            nodes = course.get("nodes", [])
            for node in nodes:
                ntype = node.get("node_type", "")
                if ntype == "video":
                    total_videos += 1
                    hidden = node.get("hidden_params", {})
                    wid = hidden.get("work_id", "")
                    progress = loader.get_video_progress(
                        course.get("course_name", ""),
                        node.get("name", ""),
                        records,
                        node,
                    )
                    if progress.get("status") == "已学":
                        completed_videos += 1
                elif ntype in ("exam", "work"):
                    hidden = node.get("hidden_params", {})
                    if hidden.get("work_id"):
                        total_exams += 1

        video_pct = completed_videos / total_videos if total_videos else 1.0
        exam_pct = completed_exams / total_exams if total_exams else 1.0
        if total_videos + total_exams > 0:
            overall = (completed_videos + completed_exams) / (total_videos + total_exams)
        else:
            overall = 1.0

        return ApiResponse(data=ProgressSummary(
            total_courses=len(courses),
            total_videos=total_videos,
            completed_videos=completed_videos,
            video_pct=round(video_pct * 100, 1),
            total_exams=total_exams,
            completed_exams=completed_exams,
            exam_pct=round(exam_pct * 100, 1),
            overall_pct=round(overall * 100, 1),
        ).dict())
    except Exception as e:
        logger.error("获取进度失败: {}", e)
        raise HTTPException(status_code=500, detail="获取进度失败")


@router.get("/{course_id}", response_model=ApiResponse)
def get_course_progress(course_id: str, username: str = Query(...), password: str = Query(...),
                        website_id: int = Query(...)):
    from services.data_loader import DataLoader
    _get_session(username, password, website_id)
    try:
        loader = DataLoader()
        courses = loader.load_courses(force_reload=True)
        records = loader.load_study_records(force_reload=True)

        target = None
        for c in courses:
            if c.get("course_id") == course_id:
                target = c
                break
        if not target:
            raise HTTPException(status_code=404, detail="课程不存在")

        videos = []
        for node in target.get("nodes", []):
            if node.get("node_type") == "video":
                progress = loader.get_video_progress(
                    target.get("course_name", ""),
                    node.get("name", ""),
                    records,
                    node,
                )
                videos.append({
                    "node_id": node.get("node_id", ""),
                    "name": node.get("name", ""),
                    "duration": progress.get("total", 0),
                    "viewed": progress.get("viewed", 0),
                    "status": progress.get("status", ""),
                })

        total = len(videos)
        done = sum(1 for v in videos if v["status"] == "已学")
        return ApiResponse(data={
            "course_id": course_id,
            "course_name": target.get("course_name", ""),
            "total_videos": total,
            "completed": done,
            "pct": round(done / total * 100, 1) if total else 100,
            "videos": videos,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取课程进度失败: {}", e)
        raise HTTPException(status_code=500, detail="获取课程进度失败")


@router.post("/sync", response_model=ApiResponse)
def sync_progress(username: str = Query(...), password: str = Query(...), website_id: int = Query(...)):
    from infrastructure.study_record_crawler import get_all_study_records
    from services.data_loader import DataLoader
    info = _get_session(username, password, website_id)
    try:
        loader = DataLoader()
        courses = loader.load_courses(force_reload=True)
        get_all_study_records(info.session, courses, website_id)
        loader.reload()
        return ApiResponse(message="学习记录已同步")
    except Exception as e:
        logger.error("同步学习记录失败: {}", e)
        raise HTTPException(status_code=500, detail="同步学习记录失败")


@router.get("/live/status", response_model=ApiResponse)
def get_live_status():
    """获取实时任务状态（从状态文件读取）"""
    status = get_task_status_from_files()
    return ApiResponse(data=status)


@router.post("/live/push", response_model=ApiResponse)
async def push_progress_update(data: dict):
    """接收 worker 推送的进度更新并广播到 WebSocket 客户端"""
    await broadcast_progress(data)
    return ApiResponse(message="已推送")

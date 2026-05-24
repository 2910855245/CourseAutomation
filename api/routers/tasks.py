from loguru import logger
from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user
from api.models import ApiResponse, CreateTaskRequest
from api.services.task_manager import manager as task_manager

router = APIRouter(prefix="/api/tasks", tags=["任务管理"])


@router.post("/", response_model=ApiResponse)
def create_task(req: CreateTaskRequest, current_user: dict = Depends(get_current_user)):
    try:
        task = task_manager.create_task(
            username=req.username,
            password=req.password,
            website_id=req.website_id,
            task_type=req.task_type.value,
            course_ids=req.course_ids,
            video_count=req.video_count,
            exam_config=req.exam_config.dict() if req.exam_config else None,
        )
        task_manager.start_task(task.task_id)
        return ApiResponse(
            success=True,
            message="任务已创建并开始执行",
            data=task.to_dict(),
        )
    except Exception as e:
        logger.error("创建任务失败: {}", e)
        raise HTTPException(status_code=500, detail="创建任务失败")


@router.get("/", response_model=ApiResponse)
def list_tasks(username: str = None, current_user: dict = Depends(get_current_user)):
    tasks = task_manager.list_tasks(username=username)
    return ApiResponse(data=[t.to_dict() for t in tasks])


@router.get("/{task_id}", response_model=ApiResponse)
def get_task(task_id: str, current_user: dict = Depends(get_current_user)):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(data=task.to_detail_dict())


@router.delete("/{task_id}", response_model=ApiResponse)
def cancel_task(task_id: str, current_user: dict = Depends(get_current_user)):
    ok = task_manager.cancel_task(task_id)
    if not ok:
        raise HTTPException(status_code=400, detail="无法取消该任务（可能已完成或不存在）")
    return ApiResponse(message="任务已取消")

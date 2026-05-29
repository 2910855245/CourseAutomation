from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import get_current_admin, get_current_user
from api.models import ApiResponse
from api.services.task_queue import (
    school_queue,
    chaoxing_queue,
    get_combined_stats,
    get_queue_by_job_id,
)

router = APIRouter(prefix="/api/queue", tags=["任务队列"])


def _require_admin(current_user: dict = Depends(get_current_user)):
    return get_current_admin(current_user)


@router.get("/stats", response_model=ApiResponse)
def get_queue_stats(
    queue: str = Query(None, description="按队列筛选: school|chaoxing，不传返回合并数据"),
    admin: dict = Depends(_require_admin),
):
    if queue == "school":
        return ApiResponse(data=school_queue.get_stats())
    elif queue == "chaoxing":
        return ApiResponse(data=chaoxing_queue.get_stats())
    return ApiResponse(data=get_combined_stats())


@router.get("/detect", response_model=ApiResponse)
def detect_concurrency(admin: dict = Depends(_require_admin)):
    from api.services.task_queue import QueueManager
    w, sw = school_queue.detect_concurrency()
    import os
    total_mem_gb = QueueManager._get_total_mem_gb()
    stats = get_combined_stats()
    return ApiResponse(data={
        "cpu_count": os.cpu_count() or 2,
        "total_mem_gb": round(total_mem_gb, 1),
        "recommended_workers": w,
        "recommended_study_workers": sw,
        "current_workers": stats["max_workers"],
        "current_study_workers": stats.get("school", {}).get("max_study_workers", 0),
    })


@router.get("/jobs", response_model=ApiResponse)
def list_jobs(
    status: str = Query(None, description="按状态筛选: pending/running/waiting/completed/failed/cancelled/retrying"),
    queue: str = Query(None, description="按队列筛选: school|chaoxing，不传返回全部"),
    admin: dict = Depends(_require_admin),
):
    tagged_jobs = []
    if queue != "chaoxing":
        for j in school_queue.list_jobs(status=status):
            d = j.to_dict()
            d["queue"] = "school"
            tagged_jobs.append(d)
    if queue != "school":
        for j in chaoxing_queue.list_jobs(status=status):
            d = j.to_dict()
            d["queue"] = "chaoxing"
            tagged_jobs.append(d)
    tagged_jobs.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return ApiResponse(data=tagged_jobs)


@router.get("/jobs/{job_id}", response_model=ApiResponse)
def get_job(job_id: str, admin: dict = Depends(_require_admin)):
    q = get_queue_by_job_id(job_id)
    if not q:
        raise HTTPException(status_code=404, detail="任务不存在")
    job = q.get_job(job_id)
    return ApiResponse(data=job.to_dict())


@router.post("/jobs/{job_id}/cancel", response_model=ApiResponse)
def cancel_job(job_id: str, admin: dict = Depends(_require_admin)):
    q = get_queue_by_job_id(job_id)
    if not q:
        raise HTTPException(status_code=404, detail="任务不存在")
    ok = q.cancel_job(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="无法取消该任务")
    return ApiResponse(message=f"任务 {job_id} 已取消")


@router.delete("/jobs/{job_id}", response_model=ApiResponse)
def delete_job(job_id: str, admin: dict = Depends(_require_admin)):
    q = get_queue_by_job_id(job_id)
    if not q:
        raise HTTPException(status_code=404, detail="任务不存在")
    ok = q.delete_job(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="无法删除该任务（执行中的任务不能删除）")
    return ApiResponse(message=f"任务 {job_id} 已删除")


@router.post("/jobs/{job_id}/retry", response_model=ApiResponse)
def retry_job(job_id: str, admin: dict = Depends(_require_admin)):
    q = get_queue_by_job_id(job_id)
    if not q:
        raise HTTPException(status_code=404, detail="任务不存在")
    ok = q.retry_job(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="只能重试已失败的任务")
    return ApiResponse(message=f"任务 {job_id} 已重新入队")


@router.post("/pause/{queue_name}", response_model=ApiResponse)
def pause_queue_by_name(queue_name: str, admin: dict = Depends(_require_admin)):
    if queue_name == "school":
        school_queue.pause()
        return ApiResponse(message="学校平台队列已暂停")
    elif queue_name == "chaoxing":
        chaoxing_queue.pause()
        return ApiResponse(message="学习通队列已暂停")
    elif queue_name == "all":
        school_queue.pause()
        chaoxing_queue.pause()
        return ApiResponse(message="全部队列已暂停")
    raise HTTPException(status_code=400, detail="queue_name 必须是 school/chaoxing/all")


@router.post("/pause", response_model=ApiResponse)
def pause_queue(admin: dict = Depends(_require_admin)):
    school_queue.pause()
    chaoxing_queue.pause()
    return ApiResponse(message="队列已暂停")


@router.post("/resume/{queue_name}", response_model=ApiResponse)
def resume_queue_by_name(queue_name: str, admin: dict = Depends(_require_admin)):
    if queue_name == "school":
        school_queue.resume()
        return ApiResponse(message="学校平台队列已恢复")
    elif queue_name == "chaoxing":
        chaoxing_queue.resume()
        return ApiResponse(message="学习通队列已恢复")
    elif queue_name == "all":
        school_queue.resume()
        chaoxing_queue.resume()
        return ApiResponse(message="全部队列已恢复")
    raise HTTPException(status_code=400, detail="queue_name 必须是 school/chaoxing/all")


@router.post("/resume", response_model=ApiResponse)
def resume_queue(admin: dict = Depends(_require_admin)):
    school_queue.resume()
    chaoxing_queue.resume()
    return ApiResponse(message="队列已恢复")


@router.post("/clear", response_model=ApiResponse)
def clear_history(admin: dict = Depends(_require_admin)):
    count = school_queue.cleanup_old_jobs(days=0) + chaoxing_queue.cleanup_old_jobs(days=0)
    return ApiResponse(message=f"已清除 {count} 条历史记录", data={"cleared": count})


@router.post("/config", response_model=ApiResponse)
def set_queue_config(
    max_workers: int = Query(None, ge=1, le=20, description="最大并发数"),
    auto: bool = Query(False, description="自动检测并发数"),
    queue: str = Query(None, description="指定队列: school|chaoxing，不传则两个都更新"),
    admin: dict = Depends(_require_admin),
):
    if queue == "school":
        school_queue.update_config(max_workers=max_workers, auto=auto)
    elif queue == "chaoxing":
        chaoxing_queue.update_config(max_workers=max_workers, auto=auto)
    else:
        school_queue.update_config(max_workers=max_workers, auto=auto)
        chaoxing_queue.update_config(max_workers=max_workers, auto=auto)
    return ApiResponse(
        message="配置已更新",
        data=get_combined_stats(),
    )


@router.post("/auto-correct", response_model=ApiResponse)
def trigger_auto_correct(admin: dict = Depends(_require_admin)):
    """手动触发一次自动纠错扫描"""
    school_queue.trigger_correction()
    chaoxing_queue.trigger_correction()
    return ApiResponse(message="纠错扫描已完成", data=get_combined_stats())


@router.get("/error-stats", response_model=ApiResponse)
def get_error_stats(admin: dict = Depends(_require_admin)):
    """查看失败任务的错误分类统计"""
    school_stats = school_queue.get_error_stats()
    chaoxing_stats = chaoxing_queue.get_error_stats()
    return ApiResponse(data={"school": school_stats, "chaoxing": chaoxing_stats})

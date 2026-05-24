import threading

from loguru import logger
from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import get_current_admin, get_current_user
from api.database import db
from api.models import AcceptOrderRequest, ApiResponse
from api.services.task_manager import manager as task_manager

router = APIRouter(prefix="/api/admin", tags=["管理员操作"])

from api.utils import mask_password as _mask_pwd


def _require_admin(current_user: dict = Depends(get_current_user)):
    return get_current_admin(current_user)


@router.get("/stats", response_model=ApiResponse)
def get_stats(admin: dict = Depends(_require_admin)):
    stats = db.get_stats()
    user_stats = db.get_user_stats()
    stats["users"] = user_stats
    return ApiResponse(data=stats)


@router.get("/orders", response_model=ApiResponse)
def admin_list_orders(
    status: str = Query(None, description="按状态筛选"),
    user_id: str = Query(None, description="按用户筛选"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(_require_admin),
):
    orders = db.list_orders(status=status, user_id=user_id, limit=limit, offset=offset)
    total = db.count_orders(status=status, user_id=user_id)
    from api.routers.orders import _inject_task_progress
    enriched = _inject_task_progress(orders)
    return ApiResponse(data={"total": total, "items": [_mask_pwd(o) for o in enriched]})


@router.post("/orders/{order_id}/accept", response_model=ApiResponse)
def accept_order(order_id: str, req: AcceptOrderRequest = AcceptOrderRequest(),
                 admin: dict = Depends(_require_admin)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"只能接受 pending 状态的订单，当前状态: {order['status']}",
        )
    db.accept_order(order_id, admin_note=req.admin_note)
    return ApiResponse(
        message=f"订单 {order_id} 已接受",
        data=_mask_pwd(db.get_order(order_id)),
    )


@router.post("/orders/{order_id}/execute", response_model=ApiResponse)
def execute_order(order_id: str, admin: dict = Depends(_require_admin)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order["status"] not in ("pending", "accepted"):
        raise HTTPException(
            status_code=400,
            detail=f"无法执行，当前状态: {order['status']}",
        )

    import json
    course_ids = order.get("course_ids") or []
    if isinstance(course_ids, str):
        try:
            course_ids = json.loads(course_ids) if course_ids else []
        except (json.JSONDecodeError, ValueError):
            course_ids = []
    if not isinstance(course_ids, list):
        course_ids = []

    try:
        task = task_manager.create_task(
            username=order["username"],
            password=order["password"],
            website_id=order["website_id"],
            task_type=order["task_type"],
            course_ids=course_ids if course_ids else None,
            video_count=order["video_count"],
        )
        task_manager.start_task(task.task_id)
        db.start_order(order_id, task.task_id)

        _start_order_monitor(order_id, task.task_id)

        return ApiResponse(
            success=True,
            message=f"订单 {order_id} 已开始执行",
            data={
                "order_id": order_id,
                "task_id": task.task_id,
                "status": "running",
            },
        )
    except Exception as e:
        logger.error("执行订单失败: {}", e)
        db.fail_order(order_id, error="执行失败")
        raise HTTPException(status_code=500, detail="执行失败")


@router.post("/orders/{order_id}/accept-and-execute", response_model=ApiResponse)
def accept_and_execute(order_id: str, req: AcceptOrderRequest = AcceptOrderRequest(),
                       admin: dict = Depends(_require_admin)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order["status"] not in ("pending",):
        raise HTTPException(
            status_code=400,
            detail=f"只能对 pending 状态的订单执行此操作，当前状态: {order['status']}",
        )

    db.accept_order(order_id, admin_note=req.admin_note)

    import json
    course_ids = order["course_ids"]
    if isinstance(course_ids, str):
        try:
            course_ids = json.loads(course_ids)
        except (json.JSONDecodeError, TypeError):
            course_ids = []

    try:
        task = task_manager.create_task(
            username=order["username"],
            password=order["password"],
            website_id=order["website_id"],
            task_type=order["task_type"],
            course_ids=course_ids if course_ids else None,
            video_count=order["video_count"],
        )
        task_manager.start_task(task.task_id)
        db.start_order(order_id, task.task_id)

        _start_order_monitor(order_id, task.task_id)

        return ApiResponse(
            success=True,
            message=f"订单 {order_id} 已接受并开始执行",
            data={
                "order_id": order_id,
                "task_id": task.task_id,
                "status": "running",
            },
        )
    except Exception as e:
        logger.error("执行订单失败: {}", e)
        db.fail_order(order_id, error="执行失败")
        raise HTTPException(status_code=500, detail="执行失败")


@router.post("/orders/{order_id}/enqueue", response_model=ApiResponse)
def enqueue_order(order_id: str, req: AcceptOrderRequest = AcceptOrderRequest(),
                  admin: dict = Depends(_require_admin)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"只能对 pending 状态的订单入队，当前状态: {order['status']}",
        )

    db.accept_order(order_id, admin_note=req.admin_note)

    import json
    course_ids = order["course_ids"]
    if isinstance(course_ids, str):
        try:
            course_ids = json.loads(course_ids)
        except (json.JSONDecodeError, TypeError):
            course_ids = []

    from api.services.task_queue import get_queue_for_type
    task_type = order["task_type"] if order["task_type"] in ("video", "exam", "full", "chaoxing_points") else "full"
    q = get_queue_for_type(task_type)
    job = q.submit_job(
        username=order["username"],
        password=order["password"],
        website_id=order["website_id"],
        job_type=task_type,
        course_ids=course_ids if course_ids else [],
        order_id=order_id,
    )

    db.start_order(order_id, "")

    return ApiResponse(
        message=f"订单 {order_id} 已入队等待执行",
        data={
            "order_id": order_id,
            "job_id": job.job_id,
            "queue_position": q.get_stats()["pending"],
        },
    )


@router.post("/orders/{order_id}/fail", response_model=ApiResponse)
def fail_order(order_id: str, req: AcceptOrderRequest = AcceptOrderRequest(),
               admin: dict = Depends(_require_admin)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order["status"] in ("completed", "cancelled", "failed"):
        raise HTTPException(status_code=400, detail=f"当前状态 [{order['status']}] 不可标记失败")

    if order.get("paid") and order["price"] > 0 and order["user_id"]:
        db.update_user_balance(
            order["user_id"],
            order["price"],
            "order_refund",
            note=f"订单 {order_id} 失败退款",
            order_id=order_id,
        )

    db.fail_order(order_id, error=req.admin_note)
    if order.get("task_id"):
        task_manager.cancel_task(order["task_id"])
    return ApiResponse(message=f"订单 {order_id} 已标记失败")


@router.post("/orders/{order_id}/complete", response_model=ApiResponse)
def complete_order(order_id: str, admin: dict = Depends(_require_admin)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order["status"] not in ("running", "accepted"):
        raise HTTPException(status_code=400, detail=f"当前状态 [{order['status']}] 不可标记完成")
    if order["user_id"]:
        db.increment_user_order_stats(order["user_id"], order["price"])
    db.complete_order(order_id)
    try:
        from api.routers.agents import calculate_commission
        calculate_commission(order_id, order.get("user_id"), order.get("price", 0))
    except Exception:
        pass
    return ApiResponse(message=f"订单 {order_id} 已标记完成")


@router.get("/tasks/{order_id}", response_model=ApiResponse)
def get_order_task(order_id: str, admin: dict = Depends(_require_admin)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    task_id = order.get("task_id")
    if not task_id:
        return ApiResponse(data={"status": order["status"], "task": None})
    task = task_manager.get_task(task_id)
    if not task:
        return ApiResponse(data={"status": order["status"], "task": None})
    return ApiResponse(data={"status": order["status"], "task": task.to_detail_dict()})


def _start_order_monitor(order_id: str, task_id: str):
    def _monitor():
        import time

        from api.services.task_manager import recovered_order_mappings
        max_checks = 360
        checks = 0
        while checks < max_checks:
            time.sleep(10)
            checks += 1
            task = task_manager.get_task(task_id)
            if not task:
                break
            if task.status_file and order_id not in recovered_order_mappings:
                recovered_order_mappings[order_id] = task.status_file
            if task.status == "completed":
                order = db.get_order(order_id)
                if order and order["user_id"]:
                    db.increment_user_order_stats(order["user_id"], order["price"])
                    from api.routers.agents import calculate_commission
                    calculate_commission(order_id, order["user_id"], order["price"])
                db.complete_order(order_id)
                break
            elif task.status == "failed":
                order = db.get_order(order_id)
                if order and order.get("paid") and order["price"] > 0 and order["user_id"]:
                    db.update_user_balance(
                        order["user_id"],
                        order["price"],
                        "order_refund",
                        note=f"订单 {order_id} 失败退款",
                        order_id=order_id,
                    )
                db.fail_order(order_id, error=task.error_message or "任务执行失败")
                break
            elif task.status == "cancelled":
                order = db.get_order(order_id)
                if order and order.get("paid") and order["price"] > 0 and order["user_id"]:
                    db.update_user_balance(
                        order["user_id"],
                        order["price"],
                        "order_refund",
                        note=f"订单 {order_id} 取消退款",
                        order_id=order_id,
                    )
                db.update_order(order_id, status="cancelled")
                break
        else:
            logger.warning("订单监控超时: order={} task={}", order_id, task_id)
            db.fail_order(order_id, error="任务执行超时")

    t = threading.Thread(target=_monitor, daemon=True)
    t.start()

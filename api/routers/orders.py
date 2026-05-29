import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from api.auth import get_current_user, get_optional_user
from api.database import db
from api.models import ApiResponse, BatchOrderRequest, CreateOrderRequest
from api.services.risk import risk_control


def _scan_task_dirs() -> dict:
    """扫描 /tmp/task_*/status.json，返回 {路径: {data, username}} 缓存"""
    import glob as _glob
    cache = {}
    for d in _glob.glob("/tmp/task_*/status.json"):
        try:
            with open(d, encoding="utf-8") as f:
                data = json.load(f)
            params_file = d.replace("status.json", "params.json")
            username = ""
            try:
                with open(params_file, encoding="utf-8") as f:
                    params = json.load(f)
                username = params.get("username", "")
            except Exception:
                pass
            cache[d] = {"data": data, "username": username}
        except Exception:
            continue
    return cache


def _read_status_from_cache(cache: dict, sf: str) -> Optional[Dict[str, Any]]:
    """从缓存中读取状态文件的进度信息"""
    info = cache.get(sf)
    if not info:
        return None
    data = info["data"]
    if data.get("done") and data.get("success"):
        return {"progress": 100, "item": "刷课完成"}
    pct = data.get("video_pct", 0)
    if pct == 0:
        done = data.get("video_done", 0)
        total = data.get("video_total", 0)
        if total > 0:
            pct = round(done / total * 100)
    return {"progress": pct, "item": data.get("message", "")}


def _inject_task_progress(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from api.services.task_manager import manager as task_manager
    from api.services.task_manager import recovered_order_mappings
    from api.services.task_queue import school_queue, chaoxing_queue

    task_dir_cache = _scan_task_dirs()

    for o in orders:
        if o.get("status") == "running":
            oid = o.get("order_id", "")
            tid = o.get("task_id", "")

            if tid:
                task = task_manager.get_task(tid)
                if task:
                    o["progress"] = task.progress
                    o["current_item"] = task.current_item
                    continue

            job = school_queue.get_job_by_order_id(oid) or chaoxing_queue.get_job_by_order_id(oid)
            if job:
                o["progress"] = job.progress
                o["current_item"] = job.current_step_name
                if job.status == "waiting":
                    o["status"] = "waiting"
                continue

            if oid in recovered_order_mappings:
                result = _read_status_from_cache(task_dir_cache, recovered_order_mappings[oid])
                if result:
                    o["progress"] = result["progress"]
                    o["current_item"] = result["item"]
                    continue

            o["progress"] = 0
        elif o.get("status") == "completed":
            o["progress"] = 100
        else:
            o.setdefault("progress", 0)
    return orders

router = APIRouter(prefix="/api/orders", tags=["订单管理"])


def _calculate_package_price(video_total: int, video_completed: int, config: dict) -> float:
    """根据打包定价模型计算单门课价格：分档 + 进度折扣 + 最低收费"""
    if video_total <= 0:
        return 0.0

    # 分档
    if video_total <= 30:
        base = config.get("price_small", 3.0)
    elif video_total <= 80:
        base = config.get("price_medium", 5.0)
    else:
        base = config.get("price_large", 6.0)

    # 进度折扣
    progress = (video_completed / video_total * 100) if video_total > 0 else 0
    if progress <= 25:
        coeff = 1.0
    elif progress <= 50:
        coeff = config.get("discount_25", 0.7)
    elif progress <= 75:
        coeff = config.get("discount_50", 0.5)
    else:
        coeff = config.get("discount_75", 0.3)

    price = base * coeff
    minimum = config.get("price_minimum", 2.0)
    return max(minimum, round(price, 2))


def _get_pricing_config() -> dict:
    """获取打包定价配置"""
    return {
        "price_small": float(db.config_get("price_small") or "3"),
        "price_medium": float(db.config_get("price_medium") or "5"),
        "price_large": float(db.config_get("price_large") or "6"),
        "discount_25": float(db.config_get("discount_25") or "0.7"),
        "discount_50": float(db.config_get("discount_50") or "0.5"),
        "discount_75": float(db.config_get("discount_75") or "0.3"),
        "price_minimum": float(db.config_get("price_minimum") or "2"),
    }


@router.post("/", response_model=ApiResponse)
def create_order(
    req: CreateOrderRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_optional_user),
):
    from api.services.order_service import validate_new_order

    uid = current_user["user_id"] if current_user["user_id"] != "guest" else None
    client_ip = current_user.get("ip", "")
    validate_new_order(uid, client_ip, req.course_ids, req.price, req.video_count, req.username)

    order = db.create_order(
        customer_name=req.customer_name or "",
        customer_contact=req.customer_contact or "",
        username=req.username,
        password=req.password,
        website_id=req.website_id,
        task_type=req.task_type.value,
        course_ids=req.course_ids,
        video_count=req.video_count,
        exam_count=req.exam_count,
        price=req.price,
        notes=req.notes,
        user_id=uid,
    )

    background_tasks.add_task(
        risk_control.log_audit, "order_created", uid or "", order["order_id"],
        f"金额¥{req.price} 平台{req.website_id}")

    return ApiResponse(
        success=True,
        message=f"订单 {order['order_id']} 已创建",
        data={"order": _mask_password(order)},
    )


@router.post("/batch", response_model=ApiResponse)
def create_batch_orders(
    req: BatchOrderRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_optional_user),
):
    uid = current_user["user_id"] if current_user["user_id"] != "guest" else None
    if uid and risk_control.is_blacklisted(user_id=uid):
        raise HTTPException(status_code=403, detail="账户已被限制")

    is_privileged = False
    if uid:
        user = db.get_user(uid)
        if user:
            role = user.get("role", "")
            if role in ("admin", "sub_admin"):
                is_privileged = True

    from api.services.order_service import compute_batch_price, submit_free_order
    computed_total, detail_lines = compute_batch_price(req.orders)
    total_price = round(sum(o.price for o in req.orders), 2)

    # 后端计算价格为准，覆盖前端传来的价格
    if abs(total_price - computed_total) > 0.015 and not is_privileged:
        from loguru import logger
        logger.bind(front_total=total_price, back_total=computed_total).info(
            "价格校验-以后端为准 details={}", " | ".join(detail_lines))
        # 按比例分配后端价格到各订单
        if total_price > 0:
            ratio = computed_total / total_price
            for item in req.orders:
                item.price = round(item.price * ratio, 2)
            # 修正浮点误差：将差额加到第一个订单
            diff = round(computed_total - sum(o.price for o in req.orders), 2)
            if diff != 0 and req.orders:
                req.orders[0].price = round(req.orders[0].price + diff, 2)
        total_price = computed_total

    free_order = total_price == 0 and is_privileged

    created = []
    for item in req.orders:
        if not item.course_ids and item.video_count == 0:
            continue
        order = db.create_order(
            customer_name="",
            customer_contact="",
            username=req.username,
            password=req.password,
            website_id=item.website_id,
            task_type=item.task_type.value,
            course_ids=item.course_ids,
            video_count=item.video_count,
            exam_count=item.exam_count,
            price=item.price,
            notes="",
            user_id=uid,
            inviter_code=req.inviter_code,
        )
        # 管理员/合伙人下单直接入队执行（免支付）
        if free_order or is_privileged:
            submit_free_order(order, req.username, req.password, item.website_id)
        created.append(_mask_password(order))

    return ApiResponse(
        success=True,
        message=f"成功创建 {len(created)} 个订单",
        data={
            "orders": created,
            "total_price": total_price,
            "paid": free_order,
        },
    )


@router.post("/pay", response_model=ApiResponse)
def pay_orders(current_user: dict = Depends(get_optional_user)):
    uid = current_user["user_id"] if current_user["user_id"] != "guest" else None
    if not uid:
        raise HTTPException(status_code=401, detail="请先登录")
    result = db.pay_user_orders(uid)
    if result.get("error"):
        return ApiResponse(success=False, message=result["error"], data=result)

    from api.services.order_service import enqueue_paid_orders
    enqueue_paid_orders(result.get("paid_order_ids", []))

    return ApiResponse(
        success=True,
        message=f"已支付 {result['paid']} 个订单，合计 ¥{result['total_price']:.2f}",
        data=result,
    )


@router.get("/", response_model=ApiResponse)
def list_orders(
    status: str = Query(None, description="按状态筛选"),
    search: str = Query(None, description="搜索用户名/订单号"),
    sort_by: str = Query("created_at", description="排序字段: created_at/price"),
    sort_dir: str = Query("desc", description="排序方向: asc/desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_optional_user),
):
    uid = current_user["user_id"] if current_user["user_id"] != "guest" else None
    if uid:
        user = db.get_user(uid)
        role = user.get("role") if user else None
        if role in ("admin", "sub_admin"):
            uid = None
    offset = (page - 1) * page_size
    orders = db.list_orders(status=status, user_id=uid, search=search,
                            sort_by=sort_by, sort_dir=sort_dir,
                            limit=page_size, offset=offset)
    total = db.count_orders(status=status, user_id=uid, search=search)
    enriched = _inject_task_progress(orders)
    return ApiResponse(
        data={
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "items": [_mask_password(o) for o in enriched],
        },
    )


@router.get("/active-courses", response_model=ApiResponse)
def get_active_courses(username: str = Query("")):
    """Return course_ids that have active (running/pending/queued) orders for a username. No auth needed."""
    if not username.strip():
        return ApiResponse(data=[])
    session = db._get_session()
    try:
        from api.database import Order as OrderModel
        active_statuses = ["pending", "accepted", "queued", "running", "retrying", "paid"]
        orders = session.scalars(select(OrderModel).filter(
            OrderModel.username == username.strip(),
            OrderModel.status.in_(active_statuses)
        )).all()
        course_ids = set()
        for o in orders:
            if o.course_ids:
                import json
                ids = json.loads(o.course_ids) if isinstance(o.course_ids, str) else o.course_ids
                for cid in ids:
                    course_ids.add(str(cid))
        return ApiResponse(data=list(course_ids))
    finally:
        session.close()


@router.get("/{order_id}", response_model=ApiResponse)
def get_order(order_id: str, current_user: dict = Depends(get_optional_user)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    # Inject task progress
    enriched = _inject_task_progress([order])[0]
    uid = current_user["user_id"] if current_user["user_id"] != "guest" else None
    # 任何人都可以用订单号查看订单详情（已脱敏）
    if not uid:
        return ApiResponse(data=_mask_password(enriched))
    # 非本人需要管理员权限
    if order.get("user_id") and order["user_id"] != uid:
        user = db.get_user(uid)
        if not user or user.get("role") not in ("admin", "sub_admin"):
            raise HTTPException(status_code=403, detail="无权查看此订单")
    return ApiResponse(data=_mask_password(enriched))


@router.delete("/{order_id}", response_model=ApiResponse)
def cancel_order(order_id: str, current_user: dict = Depends(get_optional_user)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    uid = current_user["user_id"] if current_user["user_id"] != "guest" else None
    # 如果订单有关联用户，则必须登录验证身份；游客创建的订单无需登录即可取消
    if order.get("user_id"):
        if not uid:
            raise HTTPException(status_code=401, detail="请先登录")
        if order["user_id"] != uid:
            user = db.get_user(uid)
            if not user or user.get("role") not in ("admin", "sub_admin"):
                raise HTTPException(status_code=403, detail="无权操作此订单")
    if order["status"] not in ("pending",):
        raise HTTPException(status_code=400, detail=f"当前状态 [{order['status']}] 不允许取消")

    cancelled = db.cancel_order(order_id)
    if not cancelled:
        raise HTTPException(status_code=409, detail="订单取消失败，可能已被其他操作处理")

    if order.get("paid") and order["price"] > 0 and order["user_id"]:
        db.update_user_balance(
            order["user_id"],
            order["price"],
            "order_refund",
            note=f"订单 {order_id} 取消退款",
            order_id=order_id,
        )

    risk_control.log_audit("order_cancelled", user_id=order.get("user_id", ""),
                           order_id=order_id, detail="用户取消订单")
    return ApiResponse(message=f"订单 {order_id} 已取消")


@router.post("/clear-history", response_model=ApiResponse)
def clear_history(current_user: dict = Depends(get_optional_user)):
    uid = current_user["user_id"] if current_user["user_id"] != "guest" else None
    try:
        count = db.clear_history_orders(user_id=uid)
        return ApiResponse(message=f"已清除 {count} 条历史订单")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清除历史失败: {str(e)}")


from api.utils import mask_password as _mask_password


class BatchAction(BaseModel):
    order_ids: list


@router.post("/batch-cancel", response_model=ApiResponse)
def batch_cancel_orders(
    body: BatchAction,
    current_user: dict = Depends(get_optional_user),
):
    uid = current_user["user_id"] if current_user["user_id"] != "guest" else None
    if not uid:
        raise HTTPException(status_code=401, detail="请先登录")
    count = 0
    for oid in body.order_ids:
        order = db.get_order(oid)
        if not order or order["status"] != "pending":
            continue
        if uid and order.get("user_id") != uid:
            continue
        cancelled = db.cancel_order(oid)
        if not cancelled:
            continue
        if order.get("paid") and order["price"] > 0 and order["user_id"]:
            db.update_user_balance(order["user_id"], order["price"], "order_refund",
                                   note=f"订单 {oid} 取消退款", order_id=oid)
        count += 1
    return ApiResponse(message=f"成功取消 {count} 个订单")


@router.post("/retry/{order_id}", response_model=ApiResponse)
def retry_order(order_id: str, current_user: dict = Depends(get_optional_user)):
    uid = current_user["user_id"] if current_user["user_id"] != "guest" else None
    if not uid:
        raise HTTPException(status_code=401, detail="请先登录")
    original = db.get_order(order_id)
    if not original:
        raise HTTPException(status_code=404, detail="订单不存在")
    if original.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="无权操作")

    from api.services.order_service import retry_order as _retry
    new_order = _retry(original, uid)

    return ApiResponse(data={"order_id": new_order["order_id"],
                              "message": "已重新创建订单，请支付"})


@router.get("/audit-log/{order_id}", response_model=ApiResponse)
def get_order_audit_log(order_id: str, current_user: dict = Depends(get_current_user)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    uid = current_user["user_id"]
    user = db.get_user(uid)
    if order.get("user_id") != uid and (not user or user.get("role") not in ("admin", "sub_admin")):
        raise HTTPException(status_code=403, detail="无权查看此订单审计日志")
    session = db._get_session()
    try:
        from api.database import AuditLog as AuditLogModel
        logs = session.scalars(select(AuditLogModel).filter(
            AuditLogModel.order_id == order_id
        ).order_by(AuditLogModel.created_at.asc())).all()
        return ApiResponse(data=[{
            "event": l.event_type,
            "detail": l.detail,
            "created_at": l.created_at,
        } for l in logs])
    finally:
        session.close()


@router.get("/notifications", response_model=ApiResponse)
def get_notifications(current_user: dict = Depends(get_optional_user)):
    uid = current_user["user_id"] if current_user["user_id"] != "guest" else None
    if not uid:
        return ApiResponse(data=[])
    recent = db.list_orders(user_id=uid, limit=10, offset=0)
    alerts = []
    for o in recent:
        if o["status"] == "failed":
            alerts.append({
                "type": "danger",
                "order_id": o["order_id"],
                "message": f"订单 {o['order_id']} 执行失败",
                "time": o.get("updated_at", ""),
            })
        elif o["status"] == "completed":
            alerts.append({
                "type": "success",
                "order_id": o["order_id"],
                "message": f"订单 {o['order_id']} 已完成",
                "time": o.get("updated_at", ""),
            })
    return ApiResponse(data=alerts[:5])

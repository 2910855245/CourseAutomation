from loguru import logger
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import get_current_admin, get_current_user
from api.database import db
from api.models import AcceptOrderRequest, ApiResponse

router = APIRouter(prefix="/api/admin", tags=["管理员操作"])


class AdminLoginRequest(BaseModel):
    username: str = Field(..., description="管理员用户名")
    password: str = Field(..., description="密码")
    captcha_token: str = Field(default="", description="验证码token")
    captcha_answer: str = Field(default="", description="验证码答案")


@router.post("/login", response_model=ApiResponse)
def admin_login(req: AdminLoginRequest):
    """管理员登录（唯一账号体系）。限频 + 验证码 + bcrypt。"""
    import threading
    import time as _time
    from api.auth import create_token, verify_captcha, verify_password

    verify_captcha(req.captcha_token, req.captcha_answer)

    user = db.get_user_by_login(req.username)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    db.update_user_login(user["user_id"])
    token = create_token(user["user_id"], user["username"], user["role"])
    return ApiResponse(
        message="登录成功",
        data={"user_id": user["user_id"], "username": user["username"], "role": user["role"], "token": token},
    )

from api.utils import mask_password as _mask_pwd


from api.utils import parse_course_ids as _parse_course_ids


from api.auth import require_admin as _require_admin



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


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., max_length=200)
    new_password: str = Field(..., min_length=6, max_length=200)


@router.post("/change-password", response_model=ApiResponse)
def change_admin_password(req: ChangePasswordRequest, admin: dict = Depends(_require_admin)):
    """管理员改密（原用户体系 change-password 迁移）"""
    from api.auth import hash_password, verify_password
    user = db.get_user(admin["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="账号不存在")
    if not verify_password(req.old_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="原密码不正确")
    db.update_user(admin["user_id"], password_hash=hash_password(req.new_password))
    return ApiResponse(message="密码修改成功")


@router.post("/orders/{order_id}/accept", response_model=ApiResponse)
def accept_order(order_id: str, req: AcceptOrderRequest = AcceptOrderRequest(),
                 admin: dict = Depends(_require_admin)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    # 管理员操作：允许 pending/cancelled 状态
    if order["status"] not in ("pending", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"只能接受 pending/cancelled 状态的订单，当前状态: {order['status']}",
        )

    db.admin_reset_and_mark_paid(order_id)

    db.accept_order(order_id, admin_note=req.admin_note)
    return ApiResponse(
        message=f"订单 {order_id} 已接受",
        data=_mask_pwd(db.get_order(order_id)),
    )




@router.post("/orders/{order_id}/enqueue", response_model=ApiResponse)
def enqueue_order(order_id: str, req: AcceptOrderRequest = AcceptOrderRequest(),
                  admin: dict = Depends(_require_admin)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    # 管理员入队：允许 pending/accepted/cancelled 状态的订单
    if order["status"] not in ("pending", "accepted", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"只能对 pending/accepted/cancelled 状态的订单入队，当前状态: {order['status']}",
        )

    db.admin_reset_and_mark_paid(order_id)
    if db.get_order(order_id)["status"] == "pending":
        db.accept_order(order_id, admin_note=req.admin_note)

    from services.order_service import enqueue_order
    enqueue_order(order_id)

    return ApiResponse(
        message=f"订单 {order_id} 已入队等待执行",
        data={"order_id": order_id},
    )


@router.post("/orders/{order_id}/fail", response_model=ApiResponse)
def fail_order(order_id: str, req: AcceptOrderRequest = AcceptOrderRequest(),
               admin: dict = Depends(_require_admin)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order["status"] in ("completed", "cancelled", "failed"):
        raise HTTPException(status_code=400, detail=f"当前状态 [{order['status']}] 不可标记失败")

    db.fail_order(order_id, error=req.admin_note)
    return ApiResponse(message=f"订单 {order_id} 已标记失败")


@router.post("/orders/{order_id}/complete", response_model=ApiResponse)
def complete_order(order_id: str, admin: dict = Depends(_require_admin)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order["status"] not in ("running", "accepted"):
        raise HTTPException(status_code=400, detail=f"当前状态 [{order['status']}] 不可标记完成")
    db.complete_order(order_id)
    return ApiResponse(message=f"订单 {order_id} 已标记完成")



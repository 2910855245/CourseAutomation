from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    VIDEO = "video"
    EXAM = "exam"
    FULL = "full"
    CHAOXING_POINTS = "chaoxing_points"


class CaptchaMixin(BaseModel):
    captcha_token: str = Field(default="", description="验证码token")
    captcha_answer: str = Field(default="", description="验证码答案")


class CreateOrderRequest(BaseModel):
    model_config = {"json_schema_extra": {
        "examples": [{
            "username": "student_2024",
            "password": "s3cret!",
            "website_id": 1,
            "task_type": "video",
            "course_ids": ["CRS-001", "CRS-002"],
            "video_count": 30,
            "exam_count": 0,
            "price": 5.0,
        }]
    }}
    customer_name: str = Field(default="", max_length=100, description="客户名称")
    customer_contact: str = Field(default="", max_length=200, description="客户联系方式(微信/手机)")
    username: str = Field(..., max_length=100, description="平台账号")
    password: str = Field(..., max_length=200, description="平台密码")
    website_id: int = Field(..., ge=1, le=4, description="平台ID")
    task_type: TaskType = Field(default=TaskType.VIDEO, description="任务类型")
    course_ids: Optional[List[str]] = Field(default=None, description="指定课程ID列表")
    video_count: int = Field(default=50, ge=1, description="视频数量限制")
    exam_count: int = Field(default=0, ge=0, description="考试数量限制")
    price: float = Field(default=0.0, ge=0, description="订单金额(元)")
    notes: str = Field(default="", max_length=500, description="备注")


class AcceptOrderRequest(BaseModel):
    admin_note: str = Field(default="", max_length=500, description="管理员备注")


class RegisterRequest(CaptchaMixin):
    model_config = {"json_schema_extra": {
        "examples": [{
            "username": "new_user",
            "password": "mypassword123",
            "nickname": "小明",
            "contact": "wx_ming",
        }]
    }}
    username: str = Field(..., min_length=3, max_length=32, description="用户名")
    password: str = Field(..., min_length=6, max_length=200, description="密码")
    nickname: str = Field(default="", max_length=50, description="昵称")
    contact: str = Field(default="", max_length=200, description="联系方式(微信/手机)")


class UserLoginRequest(CaptchaMixin):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class TopUpRequest(BaseModel):
    user_id: str = Field(..., max_length=30, description="用户ID")
    amount: float = Field(..., gt=0, description="充值金额(元)")
    note: str = Field(default="", max_length=500, description="备注")


class CourseDetail(BaseModel):
    video_total: int = Field(default=0, ge=0, description="课程视频总数")
    video_completed: int = Field(default=0, ge=0, description="已完成视频数")
    exam_total: int = Field(default=0, ge=0, description="考试总数")
    exam_done: int = Field(default=0, ge=0, description="已完成考试数")
    homework_total: int = Field(default=0, ge=0, description="作业总数")
    homework_done: int = Field(default=0, ge=0, description="已完成作业数")


class BatchOrderItem(BaseModel):
    website_id: int = Field(..., ge=1, le=4, description="平台ID")
    task_type: TaskType = Field(default=TaskType.VIDEO, description="任务类型")
    course_ids: List[str] = Field(default_factory=list, description="已选课程ID列表")
    video_count: int = Field(default=50, ge=0, description="视频数量")
    exam_count: int = Field(default=0, ge=0, description="考试数量")
    price: float = Field(default=0.0, ge=0, description="该平台订单金额(元)")
    course_details: List[CourseDetail] = Field(default_factory=list, description="每门课的视频数和完成数")


class BatchOrderRequest(BaseModel):
    model_config = {"json_schema_extra": {
        "examples": [{
            "username": "student_2024",
            "password": "s3cret!",
            "orders": [
                {"website_id": 1, "task_type": "video", "course_ids": ["CRS-001"], "video_count": 20, "price": 3.0},
                {"website_id": 2, "task_type": "full", "course_ids": ["CRS-003"], "video_count": 10, "price": 5.0},
            ],
        }]
    }}
    username: str = Field(..., max_length=100, description="平台账号")
    password: str = Field(..., max_length=200, description="平台密码")
    orders: List[BatchOrderItem] = Field(..., min_length=1, max_length=20, description="各平台订单列表")


class ApiResponse(BaseModel):
    model_config = {"json_schema_extra": {
        "examples": [
            {"success": True, "message": "操作成功", "data": {"id": "ORD-001"}},
            {"success": False, "message": "参数错误", "data": None},
        ]
    }}
    success: bool = True
    message: str = "ok"
    data: Optional[Any] = None

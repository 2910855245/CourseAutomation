from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    VIDEO = "video"
    EXAM = "exam"
    FULL = "full"
    CHAOXING_POINTS = "chaoxing_points"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WebsiteID(int, Enum):
    SUWAN = 1
    JINENG = 2
    ZHONGJIAXINSHENG = 3
    LAODONG = 4


class ExamConfig(BaseModel):
    ai_model: str = Field(default="gpt-4", description="AI模型选择")
    auto_submit: bool = Field(default=True, description="是否自动提交")


class CreateTaskRequest(BaseModel):
    username: str = Field(..., description="平台账号")
    password: str = Field(..., description="平台密码")
    website_id: int = Field(..., ge=1, le=4, description="平台ID: 1=粟湾 2=技能 3=中嘉鑫盛 4=劳动")
    task_type: TaskType = Field(default=TaskType.VIDEO, description="任务类型")
    course_ids: Optional[List[str]] = Field(default=None, description="指定课程ID列表，空=全部")
    video_count: int = Field(default=50, ge=1, description="视频数量限制")
    exam_config: Optional[ExamConfig] = Field(default=None, description="AI考试配置")


class CaptchaMixin(BaseModel):
    captcha_token: str = Field(default="", description="验证码token")
    captcha_answer: str = Field(default="", description="验证码答案")


class LoginRequest(BaseModel):
    username: str = Field(..., description="平台账号")
    password: str = Field(..., description="平台密码")
    website_id: int = Field(..., ge=1, le=4, description="平台ID")


class RefreshCoursesRequest(BaseModel):
    username: str = Field(..., description="平台账号")
    password: str = Field(..., description="平台密码")
    website_id: int = Field(..., ge=1, le=4, description="平台ID")


class TaskItem(BaseModel):
    task_id: str
    username: str
    website_id: int
    task_type: TaskType
    status: TaskStatus
    progress: float = Field(default=0.0, description="进度百分比 0-100")
    total_items: int = Field(default=0, description="总项目数")
    completed_items: int = Field(default=0, description="已完成数")
    current_item: str = Field(default="", description="当前执行项")
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_message: Optional[str] = None
    course_ids: Optional[List[str]] = None


class TaskProgressDetail(BaseModel):
    task_id: str
    status: TaskStatus
    progress: float
    total_items: int
    completed_items: int
    current_item: str
    logs: List[Dict[str, Any]] = Field(default_factory=list)


class CourseInfo(BaseModel):
    course_id: str
    course_name: str
    platform: str
    video_total: int = 0
    video_completed: int = 0
    video_pct: float = 0.0
    exam_total: int = 0
    exam_done: int = 0


class VideoInfo(BaseModel):
    node_id: str
    name: str
    duration: int = 0
    viewed_duration: int = 0
    status: str = ""


class ExamInfo(BaseModel):
    exam_id: str
    name: str
    status: str = ""
    can_answer: bool = False
    work_id: Optional[str] = None


class CourseDetail(BaseModel):
    course_id: str
    course_name: str
    platform: str
    videos: List[VideoInfo] = Field(default_factory=list)
    exams: List[ExamInfo] = Field(default_factory=list)


class ProgressSummary(BaseModel):
    total_courses: int = 0
    total_videos: int = 0
    completed_videos: int = 0
    video_pct: float = 0.0
    total_exams: int = 0
    completed_exams: int = 0
    exam_pct: float = 0.0
    overall_pct: float = 0.0


class AccountStatus(BaseModel):
    username: str
    website_id: int
    student_name: str = ""
    is_valid: bool = False
    last_login: Optional[str] = None


class OrderStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
    website_id: int = Field(..., ge=1, le=4, description="平台ID: 1=粟湾 2=技能 3=中嘉鑫盛 4=劳动")
    task_type: TaskType = Field(default=TaskType.VIDEO, description="任务类型")
    course_ids: Optional[List[str]] = Field(default=None, description="指定课程ID列表")
    video_count: int = Field(default=50, ge=1, description="视频数量限制")
    exam_count: int = Field(default=0, ge=0, description="考试数量限制")
    price: float = Field(default=0.0, ge=0, description="订单金额(元)")
    notes: str = Field(default="", max_length=500, description="备注")


class OrderItem(BaseModel):
    order_id: str
    customer_name: str
    customer_contact: str
    username: str
    website_id: int
    task_type: str
    course_ids: List[str] = Field(default_factory=list)
    video_count: int
    price: float
    notes: str
    status: str
    task_id: Optional[str] = None
    admin_note: str
    created_at: str
    accepted_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class AcceptOrderRequest(BaseModel):
    admin_note: str = Field(default="", max_length=500, description="管理员备注")


class OrderStats(BaseModel):
    total_orders: int = 0
    total_revenue: float = 0.0
    by_status: Dict[str, Any] = Field(default_factory=dict)


class UserRole(str, Enum):
    CUSTOMER = "customer"
    ADMIN = "admin"


class RegisterRequest(CaptchaMixin):
    model_config = {"json_schema_extra": {
        "examples": [{
            "username": "new_user",
            "password": "mypassword123",
            "nickname": "小明",
            "contact": "wx_ming",
            "referral_code": "REF-ABC123",
        }]
    }}
    username: str = Field(..., min_length=3, max_length=32, description="用户名")
    password: str = Field(..., min_length=6, max_length=200, description="密码")
    nickname: str = Field(default="", max_length=50, description="昵称")
    contact: str = Field(default="", max_length=200, description="联系方式(微信/手机)")
    referral_code: Optional[str] = Field(default=None, max_length=20, description="代理推荐码")


class UserLoginRequest(CaptchaMixin):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserInfo(BaseModel):
    user_id: str
    username: str
    nickname: str
    contact: str
    role: str
    balance: float = 0.0
    total_spent: float = 0.0
    order_count: int = 0
    created_at: str
    last_login: Optional[str] = None


class TopUpRequest(BaseModel):
    user_id: str = Field(..., max_length=30, description="用户ID")
    amount: float = Field(..., gt=0, description="充值金额(元)")
    note: str = Field(default="", max_length=500, description="备注")


class PaymentCreateRequest(BaseModel):
    amount: float = Field(..., gt=0, description="充值金额(元)")


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
            "inviter_code": "REF-ABC123",
        }]
    }}
    username: str = Field(..., max_length=100, description="平台账号")
    password: str = Field(..., max_length=200, description="平台密码")
    orders: List[BatchOrderItem] = Field(..., min_length=1, max_length=20, description="各平台订单列表")
    inviter_code: str = Field(default="", max_length=20, description="邀请人推荐码")


class TransactionItem(BaseModel):
    tx_id: str
    user_id: str
    amount: float
    tx_type: str
    balance_after: float
    note: str
    order_id: Optional[str] = None
    created_at: str


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


# ── Response Models（替代 Dict[str, Any] 返回类型）──────────────────────


class UserResponse(BaseModel):
    user_id: str
    username: str
    nickname: str = ""
    contact: str = ""
    role: str = "customer"
    balance: float = 0.0
    total_spent: float = 0.0
    order_count: int = 0
    referred_by: Optional[str] = None
    created_at: str = ""
    last_login: Optional[str] = None


class OrderResponse(BaseModel):
    order_id: str
    out_trade_no: str = ""
    payment_trade_no: str = ""
    payment_channel: str = ""
    payment_time: Optional[str] = None
    commission_status: str = "unprocessed"
    user_id: str = ""
    customer_name: str = ""
    customer_contact: str = ""
    username: str
    website_id: int
    task_type: str = "video"
    course_ids: str = "[]"
    video_count: int = 0
    exam_count: int = 0
    price: float = 0.0
    notes: str = ""
    inviter_code: str = ""
    status: str = "pending"
    paid: bool = False
    task_id: Optional[str] = None
    admin_note: str = ""
    created_at: str
    updated_at: Optional[str] = None
    accepted_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class AgentResponse(BaseModel):
    agent_id: str
    user_id: str
    referral_code: str
    subdomain_slug: str = ""
    display_name: str = ""
    contact_phone: str = ""
    contact_qq: str = ""
    contact_wechat: str = ""
    available_balance: float = 0.0
    frozen_balance: float = 0.0
    withdrawn_amount: float = 0.0
    total_commission: float = 0.0
    parent_agent_id: Optional[str] = None
    grandparent_agent_id: Optional[str] = None
    tier_level: int = 1
    total_flow: float = 0.0
    invite_count: int = 0
    join_fee_paid: float = 0.0
    cost_discount: float = 0.9
    flow_commission_rate: float = 0.0
    subsite_active: bool = False
    subsite_name: str = ""
    subsite_domain: str = ""
    subsite_template: str = "default"
    wechat_qr: str = ""
    welcome_text: str = ""
    contact: str = ""
    managed_by: Optional[str] = None
    status: str = "active"
    created_at: str


class CommissionResponse(BaseModel):
    commission_id: str
    agent_id: str
    order_id: str
    referred_user_id: str
    order_amount: float
    commission_rate: float
    commission_amount: float
    level: int = 1
    status: str = "confirmed"
    created_at: str


class WithdrawalResponse(BaseModel):
    withdrawal_id: str
    agent_id: str
    amount: float
    fee_amount: float = 0.0
    method: str = "balance"
    status: str = "pending"
    account: str = ""
    admin_note: str = ""
    processed_at: Optional[str] = None
    created_at: str


class QueueJobResponse(BaseModel):
    job_id: str
    username: str
    website_id: int
    job_type: str = "video"
    course_ids: list = []
    status: str = "pending"
    priority: int = 0
    progress: float = 0.0
    total_steps: int = 0
    completed_steps: int = 0
    current_step_name: str = ""
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3
    task_id: Optional[str] = None
    order_id: Optional[str] = None
    result_data: dict = {}
    verified: bool = False
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class PaymentAccountResponse(BaseModel):
    id: int
    type: str
    code: str = ""
    name: str = ""
    status: int = 0
    is_status: int = 1
    qr_url: str = ""
    memo: str = ""
    remark: str = ""
    channel_mode: int = 1
    create_time: str

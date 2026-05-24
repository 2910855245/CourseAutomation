from typing import Optional

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

S = String(255)


class Base(DeclarativeBase):
    pass


# ── 队列任务模型 ──────────────────────────────────────────

class JobBase(Base):
    """队列任务基类，继承自统一的 Base"""
    __abstract__ = True


def _make_job_model(table_name: str):
    """动态创建队列表模型（用 type() 保证类名唯一，避免 SAWarning）"""
    cls_name = f"JobModel_{table_name}"
    attrs = {
        "__tablename__": table_name,
        "__table_args__": {"extend_existing": True},
        "job_id": mapped_column(S, primary_key=True),
        "username": mapped_column(S, nullable=False, index=True),
        "password": mapped_column(S, nullable=False),
        "website_id": mapped_column(Integer, nullable=False),
        "job_type": mapped_column(S, default="video"),
        "course_ids": mapped_column(Text, default="[]"),
        "status": mapped_column(S, default="pending", index=True),
        "priority": mapped_column(Integer, default=0),
        "progress": mapped_column(Float, default=0.0),
        "total_steps": mapped_column(Integer, default=0),
        "completed_steps": mapped_column(Integer, default=0),
        "current_step_name": mapped_column(S, default=""),
        "error_message": mapped_column(Text, default=""),
        "retry_count": mapped_column(Integer, default=0),
        "max_retries": mapped_column(Integer, default=3),
        "task_id": mapped_column(S, nullable=True),
        "order_id": mapped_column(S, nullable=True),
        "result_data": mapped_column(Text, default="{}"),
        "verified": mapped_column(Boolean, default=False),
        "created_at": mapped_column(S, nullable=False),
        "started_at": mapped_column(S, nullable=True),
        "finished_at": mapped_column(S, nullable=True),
    }
    return type(cls_name, (JobBase,), attrs)


SchoolJobModel = _make_job_model("queue_jobs_school")
ChaoxingJobModel = _make_job_model("queue_jobs_chaoxing")


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(S, primary_key=True)
    username: Mapped[str] = mapped_column(S, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(S, nullable=False)
    nickname: Mapped[str] = mapped_column(S, default="")
    contact: Mapped[str] = mapped_column(S, default="")
    role: Mapped[str] = mapped_column(S, default="customer")
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    total_spent: Mapped[float] = mapped_column(Float, default=0.0)
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    referred_by: Mapped[Optional[str]] = mapped_column(S, nullable=True, index=True)
    created_at: Mapped[str] = mapped_column(S, nullable=False)
    last_login: Mapped[Optional[str]] = mapped_column(S, nullable=True)


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(S, primary_key=True)
    out_trade_no: Mapped[str] = mapped_column(S, default="")
    payment_trade_no: Mapped[str] = mapped_column("ezfpy_trade_no", S, default="")
    payment_channel: Mapped[str] = mapped_column(S, default="")
    payment_time: Mapped[Optional[str]] = mapped_column(S, nullable=True)
    commission_status: Mapped[str] = mapped_column(S, default="unprocessed", index=True)
    user_id: Mapped[str] = mapped_column(S, default="", index=True)
    customer_name: Mapped[str] = mapped_column(S, default="")
    customer_contact: Mapped[str] = mapped_column(S, default="")
    username: Mapped[str] = mapped_column(S, nullable=False)
    password: Mapped[str] = mapped_column(S, nullable=False)
    website_id: Mapped[int] = mapped_column(Integer, nullable=False)
    task_type: Mapped[str] = mapped_column(S, default="video")
    course_ids: Mapped[str] = mapped_column(Text, default="[]")
    video_count: Mapped[int] = mapped_column(Integer, default=0)
    exam_count: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    inviter_code: Mapped[str] = mapped_column(S, default="", index=True)
    status: Mapped[str] = mapped_column(S, default="pending", index=True)
    paid: Mapped[bool] = mapped_column(Integer, default=False)
    task_id: Mapped[Optional[str]] = mapped_column(S, nullable=True)
    admin_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(S, nullable=False)
    updated_at: Mapped[Optional[str]] = mapped_column(S, nullable=True)
    accepted_at: Mapped[Optional[str]] = mapped_column(S, nullable=True)
    started_at: Mapped[Optional[str]] = mapped_column(S, nullable=True)
    finished_at: Mapped[Optional[str]] = mapped_column(S, nullable=True)


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    tx_id: Mapped[str] = mapped_column(S, primary_key=True)
    user_id: Mapped[str] = mapped_column(S, nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    tx_type: Mapped[str] = mapped_column(S, nullable=False)
    balance_after: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str] = mapped_column(Text, default="")
    order_id: Mapped[Optional[str]] = mapped_column(S, nullable=True)
    created_at: Mapped[str] = mapped_column(S, nullable=False)


class Agent(Base):
    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(S, primary_key=True)
    user_id: Mapped[str] = mapped_column(S, nullable=False, index=True)
    referral_code: Mapped[str] = mapped_column(S, unique=True, nullable=False)
    subdomain_slug: Mapped[str] = mapped_column(S, default="")
    display_name: Mapped[str] = mapped_column(S, default="")
    contact_phone: Mapped[str] = mapped_column(S, default="")
    contact_qq: Mapped[str] = mapped_column(S, default="")
    contact_wechat: Mapped[str] = mapped_column(S, default="")
    available_balance: Mapped[float] = mapped_column(Float, default=0.0)
    frozen_balance: Mapped[float] = mapped_column(Float, default=0.0)
    withdrawn_amount: Mapped[float] = mapped_column(Float, default=0.0)
    total_commission: Mapped[float] = mapped_column(Float, default=0.0)
    parent_agent_id: Mapped[Optional[str]] = mapped_column(S, nullable=True, index=True)
    grandparent_agent_id: Mapped[Optional[str]] = mapped_column(S, nullable=True)
    tier_level: Mapped[int] = mapped_column(Integer, default=1)
    total_flow: Mapped[float] = mapped_column(Float, default=0.0)
    invite_count: Mapped[int] = mapped_column(Integer, default=0)
    join_fee_paid: Mapped[float] = mapped_column(Float, default=0.0)
    cost_discount: Mapped[float] = mapped_column(Float, default=0.9)
    flow_commission_rate: Mapped[float] = mapped_column(Float, default=0.0)
    subsite_active: Mapped[bool] = mapped_column(Integer, default=False)
    subsite_name: Mapped[str] = mapped_column(S, default="")
    subsite_domain: Mapped[str] = mapped_column(S, default="")
    subsite_template: Mapped[str] = mapped_column(S, default="default")
    wechat_qr: Mapped[str] = mapped_column(S, default="")
    welcome_text: Mapped[str] = mapped_column(S, default="")
    contact: Mapped[str] = mapped_column(S, default="")
    managed_by: Mapped[Optional[str]] = mapped_column(S, nullable=True, index=True)
    status: Mapped[str] = mapped_column(S, default="active", index=True)
    created_at: Mapped[str] = mapped_column(S, nullable=False)


class Commission(Base):
    __tablename__ = "commissions"

    commission_id: Mapped[str] = mapped_column(S, primary_key=True)
    agent_id: Mapped[str] = mapped_column(S, nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(S, nullable=False)
    referred_user_id: Mapped[str] = mapped_column(S, nullable=False)
    order_amount: Mapped[float] = mapped_column(Float, nullable=False)
    commission_rate: Mapped[float] = mapped_column(Float, nullable=False)
    commission_amount: Mapped[float] = mapped_column(Float, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(S, default="confirmed", index=True)
    created_at: Mapped[str] = mapped_column(S, nullable=False)


class Withdrawal(Base):
    __tablename__ = "withdrawals"

    withdrawal_id: Mapped[str] = mapped_column(S, primary_key=True)
    agent_id: Mapped[str] = mapped_column(S, nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    fee_amount: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(S, default="balance")
    status: Mapped[str] = mapped_column(S, default="pending", index=True)
    account: Mapped[str] = mapped_column(S, default="")
    admin_note: Mapped[str] = mapped_column(S, default="")
    processed_at: Mapped[Optional[str]] = mapped_column(S, nullable=True)
    created_at: Mapped[str] = mapped_column(S, nullable=False)


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(S, primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[str] = mapped_column(S, nullable=False)


class Channel(Base):
    __tablename__ = "channels"
    channel_id: Mapped[str] = mapped_column(S, primary_key=True)
    name: Mapped[str] = mapped_column(S, nullable=False)
    service_type: Mapped[str] = mapped_column(S, nullable=False)
    settle_price: Mapped[float] = mapped_column(Float, default=0.0)
    current_load: Mapped[int] = mapped_column(Integer, default=0)
    max_load: Mapped[int] = mapped_column(Integer, default=10)
    completion_rate: Mapped[float] = mapped_column(Float, default=1.0)
    avg_speed: Mapped[float] = mapped_column(Float, default=0.0)
    score: Mapped[float] = mapped_column(Float, default=5.0)
    status: Mapped[str] = mapped_column(S, default="active")
    created_at: Mapped[str] = mapped_column(S, nullable=False)


class UserInvite(Base):
    __tablename__ = "user_invites"
    invite_id: Mapped[str] = mapped_column(S, primary_key=True)
    inviter_user_id: Mapped[str] = mapped_column(S, nullable=False)
    invited_user_id: Mapped[str] = mapped_column(S, unique=True, nullable=False)
    total_reward: Mapped[float] = mapped_column(Float, default=0.0)
    invite_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(S, nullable=False)


class SystemConfig(Base):
    __tablename__ = "system_config"
    config_key: Mapped[str] = mapped_column(S, primary_key=True)
    config_value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[str] = mapped_column(S, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    log_id: Mapped[str] = mapped_column(S, primary_key=True)
    event_type: Mapped[str] = mapped_column(S, nullable=False, index=True)
    operator: Mapped[str] = mapped_column(S, default="system")
    detail: Mapped[str] = mapped_column(Text, default="")
    order_id: Mapped[str] = mapped_column(S, default="")
    agent_id: Mapped[str] = mapped_column(S, default="")
    user_id: Mapped[str] = mapped_column(S, default="")
    created_at: Mapped[str] = mapped_column(S, nullable=False)


class VmqPayOrder(Base):
    __tablename__ = "vmq_pay_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pay_id: Mapped[str] = mapped_column(S, nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(S, default="")
    param: Mapped[str] = mapped_column(S, default="")
    pay_type: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    really_price: Mapped[float] = mapped_column(Float, default=0.0)
    state: Mapped[int] = mapped_column(Integer, default=0)
    is_auto: Mapped[int] = mapped_column(Integer, default=1)
    qrcode_url: Mapped[str] = mapped_column(Text, default="")
    notify_url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(S, nullable=False)
    paid_at: Mapped[Optional[str]] = mapped_column(S, nullable=True)
    closed_at: Mapped[Optional[str]] = mapped_column(S, nullable=True)


class TmpPrice(Base):
    __tablename__ = "tmp_price"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    price: Mapped[float] = mapped_column(Float, unique=True, nullable=False, index=True)
    oid: Mapped[str] = mapped_column(S, default="")
    created_at: Mapped[str] = mapped_column(S, nullable=False)


class VmqSetting(Base):
    __tablename__ = "vmq_settings"
    key: Mapped[str] = mapped_column(S, primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")

    USERNAME = "username"
    PASSWORD = "password"
    KEY = "key"
    CLOSE_TIME = "close_time"
    PAY_TIMEOUT = "pay_timeout"
    UNIVERSAL_QR_WECHAT = "universal_qr_wechat"
    UNIVERSAL_QR_ALIPAY = "universal_qr_alipay"
    MONITOR_VERSION = "monitor_version"
    MONITOR_LAST_HEART = "monitor_last_heart"
    MONITOR_STATUS = "monitor_status"


class VmqQrcode(Base):
    __tablename__ = "vmq_qrcodes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    qrcode_id: Mapped[str] = mapped_column(S, nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    pay_type: Mapped[int] = mapped_column(Integer, default=1)
    qrcode_content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(S, nullable=False)


class YpaySetting(Base):
    __tablename__ = "ypay_settings"
    key: Mapped[str] = mapped_column(S, primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class YpayAccount(Base):
    __tablename__ = "ypay_account"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(S, nullable=False)
    code: Mapped[str] = mapped_column(S, default="")
    name: Mapped[str] = mapped_column(S, default="")
    status: Mapped[int] = mapped_column(Integer, default=0)
    is_status: Mapped[int] = mapped_column(Integer, default=1)
    qr_url: Mapped[str] = mapped_column(Text, default="")
    zfb_pid: Mapped[str] = mapped_column(S, default="")
    alipay_appid: Mapped[str] = mapped_column(S, default="")
    alipay_public_key: Mapped[str] = mapped_column(Text, default="")
    alipay_private_key: Mapped[str] = mapped_column(Text, default="")
    cookie: Mapped[str] = mapped_column(Text, default="")
    wx_guid: Mapped[str] = mapped_column(S, default="")
    qq: Mapped[str] = mapped_column(S, default="")
    cloud_id: Mapped[str] = mapped_column(S, default="")
    qr_type: Mapped[str] = mapped_column(S, default="")
    memo: Mapped[str] = mapped_column(Text, default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    channel_mode: Mapped[int] = mapped_column(Integer, default=1)
    app_public_cert: Mapped[str] = mapped_column(Text, default="")
    alipay_public_cert: Mapped[str] = mapped_column(Text, default="")
    alipay_root_cert: Mapped[str] = mapped_column(Text, default="")
    create_time: Mapped[str] = mapped_column(S, nullable=False)


class YpayOrder(Base):
    __tablename__ = "ypay_order"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(S, nullable=False)
    account_id: Mapped[int] = mapped_column(Integer, default=0)
    trade_no: Mapped[str] = mapped_column(S, unique=True, nullable=False)
    out_trade_no: Mapped[str] = mapped_column(S, nullable=False, index=True)
    name: Mapped[str] = mapped_column(S, default="")
    money: Mapped[float] = mapped_column(Float, default=0.0)
    truemoney: Mapped[float] = mapped_column(Float, default=0.0)
    qrcode: Mapped[str] = mapped_column(Text, default="")
    h5_qrurl: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[int] = mapped_column(Integer, default=0, index=True)
    notify_url: Mapped[str] = mapped_column(Text, default="")
    return_url: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(S, default="")
    create_time: Mapped[str] = mapped_column(S, nullable=False)
    out_time: Mapped[str] = mapped_column(S, nullable=False)
    end_time: Mapped[Optional[str]] = mapped_column(S, nullable=True)


class YpayTmpPrice(Base):
    __tablename__ = "ypay_tmp_price"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    price: Mapped[float] = mapped_column(Float, unique=True, nullable=False, index=True)
    oid: Mapped[str] = mapped_column(S, default="")
    create_time: Mapped[str] = mapped_column(S, nullable=False)


class Ad(Base):
    __tablename__ = "ads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(S, default="")
    html_content: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    create_time: Mapped[str] = mapped_column(S, nullable=False)

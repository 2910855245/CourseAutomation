from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import delete, func, select, update

from api.db.models import ChaoxingJobModel, JobBase, SchoolJobModel
from api.db_engine import engine



class QueueJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"
    WAITING = "waiting"


class QueueJobType(str, Enum):
    VIDEO = "video"
    EXAM = "exam"
    ALL = "all"
    MANUAL = "manual"
    CHAOXING_POINTS = "chaoxing_points"


# ── Dataclass ─────────────────────────────────────────────

@dataclass
class QueueJob:
    job_id: str = ""
    username: str = ""
    password: str = ""
    website_id: int = 1
    job_type: str = "video"
    course_ids: list = field(default_factory=list)
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
    result_data: dict = field(default_factory=dict)
    verified: bool = False
    created_at: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def __lt__(self, other):
        return self.priority < other.priority

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "username": self.username,
            "website_id": self.website_id,
            "job_type": self.job_type,
            "course_ids": self.course_ids,
            "status": self.status,
            "priority": self.priority,
            "progress": self.progress,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "current_step_name": self.current_step_name,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "task_id": self.task_id,
            "order_id": self.order_id,
            "result_data": self.result_data,
            "verified": self.verified,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def _model_to_job(m) -> QueueJob:
    return QueueJob(
        job_id=m.job_id,
        username=m.username,
        password=m.password,
        website_id=m.website_id,
        job_type=m.job_type,
        course_ids=json.loads(m.course_ids) if m.course_ids else [],
        status=m.status,
        priority=m.priority,
        progress=m.progress,
        total_steps=m.total_steps,
        completed_steps=m.completed_steps,
        current_step_name=m.current_step_name,
        error_message=m.error_message,
        retry_count=m.retry_count,
        max_retries=m.max_retries,
        task_id=m.task_id,
        order_id=m.order_id,
        result_data=json.loads(m.result_data) if m.result_data else {},
        verified=m.verified,
        created_at=m.created_at,
        started_at=m.started_at,
        finished_at=m.finished_at,
    )


# ── QueueManager（泛化）──────────────────────────────────

class QueueManager:
    def __init__(self, model_class, session_factory, name: str = ""):
        self._model = model_class
        self._session_factory = session_factory
        self._name = name
        self._workers: Dict[str, threading.Thread] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._running = False
        self._paused = False
        self._max_workers, self._max_study_workers = self._auto_detect_concurrency()
        self._study_semaphore = threading.BoundedSemaphore(self._max_study_workers)
        self._lock = threading.Lock()
        self._on_complete: Optional[Callable] = None
        self._on_fail: Optional[Callable] = None
        self._on_progress: Optional[Callable] = None

        from api.services.error_classifier import ErrorClassifier
        from api.services.job_executor import JobExecutor
        self._executor = JobExecutor(
            db_update_fn=self._db_update,
            db_get_fn=self._db_get,
            db_claim_fn=self._db_claim_job,
            clear_password_fn=self._clear_job_password,
            on_complete=lambda job: self._on_complete(job) if self._on_complete else None,
            on_fail=lambda job: self._on_fail(job) if self._on_fail else None,
            on_progress=lambda jid, p, s, n: self._on_job_progress(jid, p, s, n),
            get_study_semaphore=lambda: self._study_semaphore,
        )
        self._error_classifier = ErrorClassifier()

    @staticmethod
    def _get_total_mem_gb() -> float:
        """跨平台获取总内存(GB)"""
        import sys
        # Linux
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) / 1024 / 1024
        except Exception:
            pass
        # Windows
        if sys.platform == "win32":
            try:
                import ctypes
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                mem = MEMORYSTATUSEX()
                mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
                return mem.ullTotalPhys / (1024 ** 3)
            except Exception:
                pass
        # fallback: psutil
        try:
            import psutil
            return psutil.virtual_memory().total / (1024 ** 3)
        except Exception:
            pass
        return 2.0

    @staticmethod
    def _auto_detect_concurrency():
        """根据服务器 CPU 和内存自动设置并发数"""
        import os
        try:
            cpu_count = os.cpu_count() or 2
        except Exception:
            cpu_count = 2

        total_mem_gb = QueueManager._get_total_mem_gb()

        available_mb = max(512, total_mem_gb * 1024 - 1024)
        max_by_mem = int(available_mb / 250)
        max_by_cpu = max(2, cpu_count - 1)

        max_workers = max(2, min(max_by_mem, max_by_cpu, 20))
        max_study_workers = max(2, min(max_workers, int(available_mb / 200)))

        logger.info("自动检测并发: cpu={} mem={:.1f}GB max_workers={} max_study_workers={}",
                     cpu_count, total_mem_gb, max_workers, max_study_workers)
        return max_workers, max_study_workers

    def set_callbacks(self, on_complete=None, on_fail=None, on_progress=None):
        self._on_complete = on_complete
        self._on_fail = on_fail
        self._on_progress = on_progress

    # ── 数据库操作 ─────────────────────────────────────────

    def _db_add(self, job: QueueJob):
        session = self._session_factory()
        try:
            model = self._model(
                job_id=job.job_id,
                username=job.username,
                password=job.password,
                website_id=job.website_id,
                job_type=job.job_type,
                course_ids=json.dumps(job.course_ids),
                status=job.status,
                priority=job.priority,
                max_retries=job.max_retries,
                order_id=job.order_id,
                created_at=job.created_at,
            )
            session.add(model)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _db_update(self, job_id: str, **fields):
        _log = logger.bind(job_id=job_id)
        session = self._session_factory()
        try:
            if "course_ids" in fields and isinstance(fields["course_ids"], list):
                fields["course_ids"] = json.dumps(fields["course_ids"])
            if "result_data" in fields and isinstance(fields["result_data"], dict):
                fields["result_data"] = json.dumps(fields["result_data"])
            session.execute(update(self._model).filter(self._model.job_id == job_id).values(**fields)).rowcount
            session.commit()
        except Exception as e:
            session.rollback()
            _log.error(f"数据库更新失败 fields={list(fields.keys())} error={str(e)}")
        finally:
            session.close()

    def _db_claim_job(self, job_id: str) -> bool:
        """原子认领任务：仅当状态为 pending/retrying 时设为 running，防止重复调度"""
        session = self._session_factory()
        try:
            now = datetime.now().isoformat()
            affected = session.execute(
                update(self._model)
                .filter(
                    self._model.job_id == job_id,
                    self._model.status.in_(["pending", "retrying"]),
                )
                .values(status="running", started_at=now)
            ).rowcount
            session.commit()
            return affected == 1
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()

    def _db_get(self, job_id: str) -> Optional[QueueJob]:
        session = self._session_factory()
        try:
            m = session.scalars(select(self._model).filter(self._model.job_id == job_id)).first()
            return _model_to_job(m) if m else None
        finally:
            session.close()

    def _db_pending_jobs(self) -> List[QueueJob]:
        session = self._session_factory()
        try:
            models = session.scalars(
                select(self._model)
                .filter(self._model.status.in_(["pending", "retrying"]))
                .order_by(self._model.priority.asc(), self._model.created_at.asc())
            ).all()
            return [_model_to_job(m) for m in models]
        finally:
            session.close()

    # ── 公开方法 ───────────────────────────────────────────

    def submit_job(self, *, username: str, password: str, website_id: int = 1,
                   job_type: str = "video", course_ids: list = None,
                   priority: int = 0, max_retries: int = 3, order_id: str = None) -> QueueJob:
        if order_id:
            existing = self.get_job_by_order_id(order_id)
            if existing and existing.status in ("pending", "running", "retrying"):
                logger.info(f"任务已存在，跳过重复提交 order_id={order_id} job_id={existing.job_id}")
                return existing

        session = self._session_factory()
        try:
            dup = session.scalars(select(self._model).filter(
                self._model.username == username,
                self._model.website_id == website_id,
                self._model.status.in_(["pending", "running", "retrying"]),
            )).first()
            if dup:
                logger.info(f"同账号任务已存在，跳过 username={username} website_id={website_id} existing_job_id={dup.job_id}")
                return _model_to_job(dup)
        finally:
            session.close()

        job_id = f"JOB-{uuid.uuid4().hex[:10].upper()}"
        job = QueueJob(
            job_id=job_id,
            username=username,
            password=password,
            website_id=website_id,
            job_type=job_type,
            course_ids=course_ids or [],
            status=QueueJobStatus.PENDING,
            priority=priority,
            max_retries=max_retries,
            order_id=order_id,
            created_at=datetime.now().isoformat(),
        )
        self._db_add(job)
        logger.info(f"任务提交 job_id={job_id} username={username} job_type={job_type} queue={self._name}")
        return job

    def get_job(self, job_id: str) -> Optional[QueueJob]:
        return self._db_get(job_id)

    def list_jobs(self, status: Optional[str] = None, username: Optional[str] = None) -> List[QueueJob]:
        session = self._session_factory()
        try:
            stmt = select(self._model)
            if status:
                stmt = stmt.where(self._model.status == status)
            if username:
                stmt = stmt.where(self._model.username == username)
            stmt = stmt.order_by(self._model.created_at.desc()).limit(1000)
            return [_model_to_job(m) for m in session.scalars(stmt).all()]
        finally:
            session.close()

    def get_job_by_order_id(self, order_id: str) -> Optional[QueueJob]:
        session = self._session_factory()
        try:
            model = session.scalars(select(self._model).filter(
                self._model.order_id == order_id
            ).order_by(self._model.created_at.desc())).first()
            return _model_to_job(model) if model else None
        finally:
            session.close()

    def get_jobs_by_order(self, order_id: str) -> List[QueueJob]:
        session = self._session_factory()
        try:
            models = session.scalars(select(self._model).filter(
                self._model.order_id == order_id
            ).order_by(self._model.created_at.desc())).all()
            return [_model_to_job(m) for m in models]
        finally:
            session.close()

    def cancel_job(self, job_id: str) -> bool:
        job = self._db_get(job_id)
        if not job:
            return False
        if job.status in (QueueJobStatus.COMPLETED, QueueJobStatus.CANCELLED):
            return False
        self._db_update(job_id, status=QueueJobStatus.CANCELLED, finished_at=datetime.now().isoformat())
        with self._lock:
            if job_id in self._workers:
                self._workers.pop(job_id, None)
        logger.info(f"任务取消 job_id={job_id}")
        return True

    def retry_job(self, job_id: str, force: bool = False) -> bool:
        job = self._db_get(job_id)
        if not job:
            return False
        if job.status != QueueJobStatus.FAILED:
            return False
        if not force:
            category = self._error_classifier.classify(job.error_message or "")
            if category == "fatal":
                logger.warning("任务为fatal错误，拒绝重试 job_id={} error={}", job_id, (job.error_message or "")[:80])
                return False
        password = job.password
        if not password and job.order_id:
            try:
                from api.database import db
                order = db.get_order(job.order_id)
                if order:
                    password = order.get("password", "")
            except Exception:
                pass
        self._db_update(
            job_id,
            status=QueueJobStatus.PENDING,
            password=password,
            retry_count=0,
            error_message="",
            progress=0.0,
        )
        logger.info(f"任务重试 job_id={job_id} has_password={bool(password)}")
        return True

    def pause(self):
        self._paused = True
        logger.info(f"队列已暂停 queue={self._name}")

    def resume(self):
        self._paused = False
        logger.info(f"队列已恢复 queue={self._name}")

    def set_max_workers(self, n: int):
        self._max_workers = max(1, min(n, 20))
        logger.info(f"最大并发数更新 max_workers={self._max_workers} queue={self._name}")

    def set_max_study_workers(self, n: int):
        new_max = max(1, min(n, 20))
        delta = new_max - self._max_study_workers
        self._max_study_workers = new_max
        if delta > 0:
            for _ in range(delta):
                try:
                    self._study_semaphore.release()
                except ValueError:
                    pass
        elif delta < 0:
            for _ in range(-delta):
                if not self._study_semaphore.acquire(blocking=False):
                    pass
        logger.info(f"最大 study 并发更新 max_study_workers={self._max_study_workers} queue={self._name}")

    def stop(self):
        self._running = False
        logger.info(f"队列管理器停止 queue={self._name}")

    # ── 调度器 ─────────────────────────────────────────────

    def _check_waiting_jobs(self):
        """检查 WAITING 任务，跨天后自动恢复为 PENDING"""
        now = datetime.now()
        # 00:00-00:10 不操作，避免并发
        if now.hour == 0 and now.minute < 10:
            return
        session = self._session_factory()
        try:
            waiting_jobs = session.scalars(
                select(self._model)
                .filter(self._model.status == QueueJobStatus.WAITING)
            ).all()
            if not waiting_jobs:
                return
            today = now.strftime("%Y-%m-%d")
            for job in waiting_jobs:
                # 超过 30 天未完成的任务标记失败
                created_date = (job.created_at or "")[:10]
                if created_date:
                    age_days = (now - datetime.strptime(created_date, "%Y-%m-%d")).days
                    if age_days > 30:
                        job.status = QueueJobStatus.FAILED
                        job.error_message = f"任务超过30天未完成（已等待{age_days}天）"
                        job.finished_at = now.strftime("%Y-%m-%dT%H:%M:%S")
                        logger.info(f"WAITING 任务超时标记失败 job_id={job.job_id} age_days={age_days}")
                        continue
                finished_date = (job.finished_at or "")[:10]
                if finished_date and finished_date < today:
                    job.status = QueueJobStatus.PENDING
                    job.current_step_name = ""
                    job.finished_at = None
                    logger.info(f"WAITING 任务自动恢复为 PENDING job_id={job.job_id}")
            session.commit()
        except Exception as e:
            logger.error(f"检查 WAITING 任务失败 error={str(e)}")
            session.rollback()
        finally:
            session.close()

    def _dispatcher_loop(self):
        _waiting_check_ts = 0
        while self._running:
            try:
                # waiting 检查每 60 秒执行一次即可
                now_ts = time.time()
                if now_ts - _waiting_check_ts > 60:
                    self._check_waiting_jobs()
                    _waiting_check_ts = now_ts

                if self._paused:
                    time.sleep(2)
                    continue

                with self._lock:
                    alive_count = sum(1 for t in self._workers.values() if t.is_alive())

                if alive_count >= self._max_workers:
                    time.sleep(2)
                    continue

                pending_jobs = self._db_pending_jobs()
                for job in pending_jobs:
                    if not self._running or self._paused:
                        break
                    with self._lock:
                        alive_count = sum(1 for t in self._workers.values() if t.is_alive())
                        if alive_count >= self._max_workers:
                            break
                        if job.job_id in self._workers and self._workers[job.job_id].is_alive():
                            continue
                    self._start_worker(job)
            except Exception as e:
                logger.error(f"调度器错误 queue={self._name} error={str(e)}")
            time.sleep(2)

    def _start_worker(self, job: QueueJob):
        def _worker():
            try:
                self._executor.execute(job, release_worker_fn=lambda jid: self._release_worker(jid))
            except Exception:
                pass
            finally:
                self._release_worker(job.job_id)

        t = threading.Thread(target=_worker, daemon=True, name=f"job-{self._name}-{job.job_id}")
        with self._lock:
            self._workers[job.job_id] = t
        t.start()

    def _release_worker(self, job_id: str):
        with self._lock:
            self._workers.pop(job_id, None)

    def _on_job_progress(self, job_id: str, progress: float, step: int, step_name: str):
        self._db_update(job_id, progress=progress, completed_steps=step, current_step_name=step_name)
        if self._on_progress:
            self._on_progress(job_id, progress, step, step_name)

    def get_stats(self) -> Dict[str, Any]:
        session = self._session_factory()
        try:
            pending = session.scalar(select(func.count()).select_from(self._model).filter(self._model.status == QueueJobStatus.PENDING))
            running = session.scalar(select(func.count()).select_from(self._model).filter(self._model.status == QueueJobStatus.RUNNING))
            waiting = session.scalar(select(func.count()).select_from(self._model).filter(self._model.status == QueueJobStatus.WAITING))
            completed = session.scalar(select(func.count()).select_from(self._model).filter(self._model.status == QueueJobStatus.COMPLETED))
            failed = session.scalar(select(func.count()).select_from(self._model).filter(self._model.status == QueueJobStatus.FAILED))
            total = session.scalar(select(func.count()).select_from(self._model))
            return {
                "pending": pending,
                "running": running,
                "waiting": waiting,
                "completed": completed,
                "failed": failed,
                "total": total,
                "active_workers": len(self._workers),
                "max_workers": self._max_workers,
                "active_study_workers": self._max_study_workers - (self._study_semaphore._value if hasattr(self._study_semaphore, '_value') else self._max_study_workers),
                "max_study_workers": self._max_study_workers,
                "paused": self._paused,
                "queue_name": self._name,
            }
        finally:
            session.close()

    def _clear_job_password(self, job_id: str):
        self._db_update(job_id, password="")

    def cleanup_old_jobs(self, days: int = 7) -> int:
        from datetime import timedelta
        cutoff_dt = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_dt.isoformat()
        session = self._session_factory()
        try:
            count = session.execute(delete(self._model).filter(
                self._model.status.in_(["completed", "failed", "cancelled"]),
                self._model.finished_at < cutoff_str,
            )).rowcount
            session.commit()
            if count > 0:
                logger.info(f"清理历史队列任务 count={count} older_than_days={days} queue={self._name}")
            return count
        except Exception:
            session.rollback()
            return 0
        finally:
            session.close()

    # ── 公开方法（供路由层调用）────────────────────────────

    def detect_concurrency(self) -> tuple:
        return self._auto_detect_concurrency()

    def update_config(self, max_workers: int = None, auto: bool = False):
        if auto:
            w, sw = self._auto_detect_concurrency()
            self.set_max_workers(w)
            self.set_max_study_workers(sw)
        elif max_workers is not None:
            self.set_max_workers(max_workers)

    def trigger_correction(self):
        self._error_classifier.auto_correct_errors()

    def get_error_stats(self) -> dict:
        return self._error_classifier.get_error_stats()

    def start(self):
        if self._running:
            return
        self._running = True
        from api.services.error_classifier import correction_loop
        from api.services.job_executor import JobExecutor
        JobExecutor.recover_stuck_jobs(self._session_factory, self._model)
        self._dispatcher_thread = threading.Thread(target=self._dispatcher_loop, daemon=True,
                                                    name=f"dispatcher-{self._name}")
        self._dispatcher_thread.start()
        self._correction_thread = threading.Thread(
            target=correction_loop, args=(lambda: self._running,),
            daemon=True, name=f"error-correction-{self._name}",
        )
        self._correction_thread.start()
        logger.info(f"队列管理器启动（含自动纠错） queue={self._name}")


# ── 创建两个队列实例 ──────────────────────────────────────

from api.database import SessionLocal

school_queue = QueueManager(SchoolJobModel, SessionLocal, name="school")
chaoxing_queue = QueueManager(ChaoxingJobModel, SessionLocal, name="chaoxing")

# 向后兼容：旧代码引用 queue_manager 指向学校队列
queue_manager = school_queue


def get_queue_for_type(job_type: str) -> QueueManager:
    """根据 job_type 返回对应的队列"""
    if job_type == "chaoxing_points":
        return chaoxing_queue
    return school_queue


def get_queue_by_job_id(job_id: str) -> Optional[QueueManager]:
    """根据 job_id 在两个队列中查找"""
    job = school_queue.get_job(job_id)
    if job:
        return school_queue
    job = chaoxing_queue.get_job(job_id)
    if job:
        return chaoxing_queue
    return None


def get_combined_stats() -> Dict[str, Any]:
    """合并两个队列的统计"""
    s = school_queue.get_stats()
    c = chaoxing_queue.get_stats()
    return {
        "pending": s["pending"] + c["pending"],
        "running": s["running"] + c["running"],
        "waiting": s.get("waiting", 0) + c.get("waiting", 0),
        "completed": s["completed"] + c["completed"],
        "failed": s["failed"] + c["failed"],
        "total": s["total"] + c["total"],
        "active_workers": s["active_workers"] + c["active_workers"],
        "max_workers": s["max_workers"] + c["max_workers"],
        "paused": s["paused"] or c["paused"],
        "school": s,
        "chaoxing": c,
    }


def migrate_old_queue_table():
    """迁移旧 queue_jobs 表数据到新表"""
    from sqlalchemy import text, inspect as sa_inspect, select, update, delete
    inspector = sa_inspect(engine)
    tables = inspector.get_table_names()
    if "queue_jobs" not in tables:
        return

    logger.info("检测到旧 queue_jobs 表，开始迁移数据...")
    session = SessionLocal()
    try:
        with engine.connect() as conn:
            # 读取旧表数据
            result = conn.execute(text("SELECT * FROM queue_jobs"))
            rows = result.fetchall()
            columns = result.keys()

        if not rows:
            with engine.connect() as conn:
                conn.execute(text("DROP TABLE IF EXISTS queue_jobs"))
                conn.commit()
            logger.info("旧表为空，已删除")
            return

        school_count = 0
        chaoxing_count = 0

        school_session = SessionLocal()
        chaoxing_session = SessionLocal()

        try:
            for row in rows:
                data = dict(zip(columns, row))
                job_type = data.get("job_type", "video")

                if job_type == "chaoxing_points":
                    model = ChaoxingJobModel(**{k: v for k, v in data.items() if hasattr(ChaoxingJobModel, k)})
                    chaoxing_session.add(model)
                    chaoxing_count += 1
                else:
                    model = SchoolJobModel(**{k: v for k, v in data.items() if hasattr(SchoolJobModel, k)})
                    school_session.add(model)
                    school_count += 1

            school_session.commit()
            chaoxing_session.commit()
        except Exception as e:
            school_session.rollback()
            chaoxing_session.rollback()
            logger.error(f"数据迁移失败 error={str(e)}")
            return
        finally:
            school_session.close()
            chaoxing_session.close()

        # 删除旧表
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS queue_jobs"))
            conn.commit()

        logger.info(f"队列数据迁移完成 school={school_count} chaoxing={chaoxing_count}")
    except Exception as e:
        logger.error(f"队列迁移异常 error={str(e)}")
    finally:
        session.close()


# ── 建表 + 迁移 ──────────────────────────────────────────

# 队列表已统一由 Base.metadata.create_all() 在 database.py 中创建
migrate_old_queue_table()

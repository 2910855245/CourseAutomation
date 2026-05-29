import json
import queue
import shutil
import threading
import time
import traceback
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger


recovered_order_mappings: Dict[str, str] = {}


class TaskRecord:
    def __init__(self, task_id, username, password, website_id, task_type,
                 course_ids=None, video_count=0, exam_config=None):
        self._lock = threading.Lock()
        self.task_id = task_id
        self.username = username
        self.password = password
        self.website_id = website_id
        self.task_type = task_type
        self.course_ids = course_ids or []
        self.video_count = video_count
        self.exam_config = exam_config or {}

        self.status = "pending"
        self.progress = 0.0
        self.total_items = 0
        self.completed_items = 0
        self.current_item = ""
        self.created_at = datetime.now().isoformat()
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.error_message: Optional[str] = None
        self.logs: List[Dict[str, Any]] = []
        self.status_file: Optional[str] = None
        self.tmpdir: Optional[str] = None

    def to_dict(self):
        with self._lock:
            return {
                "task_id": self.task_id,
                "username": self.username,
                "website_id": self.website_id,
                "task_type": self.task_type,
                "status": self.status,
                "progress": self.progress,
                "total_items": self.total_items,
                "completed_items": self.completed_items,
                "current_item": self.current_item,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "error_message": self.error_message,
                "course_ids": self.course_ids,
            }

    def to_detail_dict(self):
        with self._lock:
            d = {
                "task_id": self.task_id,
                "username": self.username,
                "website_id": self.website_id,
                "task_type": self.task_type,
                "status": self.status,
                "progress": self.progress,
                "total_items": self.total_items,
                "completed_items": self.completed_items,
                "current_item": self.current_item,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "error_message": self.error_message,
                "course_ids": self.course_ids,
                "logs": list(self.logs[-50:]),
            }
            return d

    def add_log(self, message, level="info"):
        with self._lock:
            self.logs.append({
                "time": datetime.now().isoformat(),
                "level": level,
                "message": message,
            })
            if len(self.logs) > 200:
                self.logs = self.logs[-100:]

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)


class TaskManager:
    def __init__(self, max_concurrent_heavy=1):
        self._tasks: Dict[str, TaskRecord] = {}
        self._lock = threading.Lock()
        self._heavy_queue = queue.Queue()
        self._heavy_semaphore = threading.Semaphore(max_concurrent_heavy)
        self._dispatcher = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._dispatcher.start()
        self._monitor = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor.start()

    def create_task(self, username, password, website_id, task_type,
                    course_ids=None, video_count=0, exam_config=None) -> TaskRecord:
        task_id = str(uuid.uuid4())[:8]
        task = TaskRecord(
            task_id=task_id,
            username=username,
            password=password,
            website_id=website_id,
            task_type=task_type,
            course_ids=course_ids,
            video_count=video_count,
            exam_config=exam_config,
        )
        with self._lock:
            self._tasks[task_id] = task
        return task

    def start_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.status != "pending":
            return False
        task.update(status="queued")
        task.add_log("任务已加入队列，等待执行")
        self._heavy_queue.put(task_id)
        return True

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        return self._tasks.get(task_id)

    def list_tasks(self, username: Optional[str] = None) -> List[TaskRecord]:
        tasks = list(self._tasks.values())
        if username:
            tasks = [t for t in tasks if t.username == username]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        with task._lock:
            if task.status in ("completed", "failed", "cancelled"):
                return False
            task.status = "cancelled"
            task.finished_at = datetime.now().isoformat()
        task.add_log("任务已取消", "warn")
        return True

    def _dispatch_loop(self):
        while True:
            task_id = self._heavy_queue.get()
            task = self._tasks.get(task_id)
            if not task or task.status == "cancelled":
                continue
            self._heavy_semaphore.acquire()
            t = threading.Thread(target=self._run_heavy_phase, args=(task_id,), daemon=True)
            t.start()

    def _run_heavy_phase(self, task_id: str):
        task = self._tasks.get(task_id)
        if not task:
            self._heavy_semaphore.release()
            return

        task.update(status="running", started_at=datetime.now().isoformat())
        task.add_log("开始执行（重阶段：登录+爬取）")

        try:
            from api.services.task_runner import TaskRunner

            def on_progress(pct, done, msg):
                task.update(progress=pct, completed_items=done, current_item=msg)

            runner = TaskRunner(
                username=task.username,
                password=task.password,
                website_id=task.website_id,
                on_progress=on_progress,
            )

            task.add_log(f"启动子进程: 平台{task.website_id}")
            result = runner.run(job_type=task.task_type, course_ids=task.course_ids)

            if isinstance(result, dict) and result.get("heavy_done"):
                task.status_file = result.get("status_file")
                task.tmpdir = result.get("tmpdir")
                # 在锁内检查+更新，防止取消状态被覆盖
                with task._lock:
                    if task.status == "cancelled":
                        return
                    task.status = "study_running"
                    task.current_item = "刷视频中"
                task.add_log("重阶段完成，刷课已在后台运行")
            elif isinstance(result, dict) and result.get("success"):
                task.update(status="completed", progress=100.0,
                            finished_at=datetime.now().isoformat())
                task.add_log("任务执行完成")
            elif isinstance(result, dict):
                task.update(status="failed",
                            error_message=result.get("message", "任务失败"),
                            finished_at=datetime.now().isoformat())
                task.add_log(f"任务失败: {result.get('message')}", "error")
            else:
                task.update(status="completed", progress=100.0,
                            finished_at=datetime.now().isoformat())
                task.add_log("任务执行完成")

        except Exception as e:
            task.update(status="failed", error_message=str(e),
                        finished_at=datetime.now().isoformat())
            task.add_log(f"任务执行失败: {e}", "error")
            traceback.print_exc()
        finally:
            self._heavy_semaphore.release()

    def _monitor_loop(self):
        cleanup_counter = 0
        while True:
            try:
                time.sleep(10)
                with self._lock:
                    tasks = [t for t in self._tasks.values() if t.status == "study_running"]
                for task in tasks:
                    try:
                        self._check_study_status(task)
                    except Exception as e:
                        pass
                cleanup_counter += 1
                if cleanup_counter >= 360:
                    cleanup_counter = 0
                    try:
                        self._cleanup_finished_tasks()
                    except Exception as e:
                        pass
            except Exception as e:
                pass

    def _cleanup_finished_tasks(self):
        cutoff = time.time() - 3600
        with self._lock:
            to_remove = []
            for tid, t in self._tasks.items():
                if t.status in ("completed", "failed") and t.finished_at and self._parse_time(t.finished_at) < cutoff:
                    to_remove.append(tid)
            for tid in to_remove:
                task = self._tasks.pop(tid)
                task.password = ""
                task.logs.clear()
        for order_id, sf_path in list(recovered_order_mappings.items()):
            if order_id not in self._tasks:
                recovered_order_mappings.pop(order_id, None)
        if to_remove:
            logger.info("清理已完成任务: {}个", len(to_remove))

    @staticmethod
    def _parse_time(ts):
        try:
            from datetime import datetime
            return datetime.fromisoformat(ts).timestamp()
        except Exception as e:
            return 0

    @staticmethod
    def _cleanup_task_tmpdir(task: TaskRecord):
        if task.tmpdir and os.path.exists(task.tmpdir):
            try:
                shutil.rmtree(task.tmpdir, ignore_errors=True)
                logger.info(f"已清理任务临时目录 task_id={task.task_id}")
            except Exception as e:
                pass
            task.tmpdir = None

    def _check_study_status(self, task: TaskRecord):
        sf = task.status_file
        if not sf or not os.path.exists(sf):
            return
        try:
            with open(sf, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return

        phase = data.get("phase", "")
        video_done = data.get("video_done", 0)
        video_total = data.get("video_total", 0)
        video_pct = data.get("video_pct", 0)
        message = data.get("message", "")

        if video_pct > 0:
            task.update(progress=float(video_pct), current_item=message or f"刷视频中 {video_done}/{video_total}")
        elif video_total > 0:
            task.update(current_item=message or f"刷视频中 {video_done}/{video_total}")

        if data.get("done"):
            if data.get("success"):
                task.update(status="completed", progress=100.0,
                            finished_at=datetime.now().isoformat())
                task.add_log("刷课完成")
            else:
                pct = data.get("video_pct", 0)
                task.update(status="failed",
                            progress=float(pct) if pct else task.progress,
                            error_message=data.get("message", "刷课未完全完成"),
                            finished_at=datetime.now().isoformat())
                task.add_log(f"刷课未完全完成: {data.get('message', '')}", "warn")
            self._cleanup_task_tmpdir(task)
        elif phase == "error":
            task.update(status="failed",
                        error_message=data.get("message", "刷课异常"),
                        finished_at=datetime.now().isoformat())
            task.add_log(f"刷课失败: {data.get('message')}", "error")
            self._cleanup_task_tmpdir(task)


manager = TaskManager()

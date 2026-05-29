import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, Optional

from loguru import logger

from config import WEBSITES


ProgressCallback = Callable[[float, int, str], None]

WORKER_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "worker.py"
)

CHAOXING_WORKER_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "chaoxing_worker.py"
)


class TaskRunner:
    def __init__(self, username: str, password: str, website_id: int,
                 on_progress: Optional[ProgressCallback] = None):
        self.username = username
        self.password = password
        self.website_id = website_id
        self._on_progress = on_progress
        self._progress = 0.0
        self._current_status = "等待中"
        self._running = False
        self._process: Optional[subprocess.Popen] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._params_file: Optional[str] = None
        self._status_file: Optional[str] = None
        self._tmpdir: Optional[str] = None

    def run(self, job_type: str = "full", course_ids: list = None) -> Dict[str, Any]:
        course_ids = course_ids or []
        self._running = True

        platform_name = WEBSITES.get(self.website_id, {}).get("name", f"平台{self.website_id}")

        params = {
            "username": self.username,
            "password": self.password,
            "website_id": self.website_id,
            "job_type": job_type,
            "course_ids": course_ids,
            "concurrency": 8,
        }

        self._tmpdir = tempfile.mkdtemp(prefix="task_")
        self._params_file = os.path.join(self._tmpdir, "params.json")
        self._status_file = os.path.join(self._tmpdir, "status.json")
        self._log_file = os.path.join(self._tmpdir, "worker.log")

        with open(self._params_file, "w", encoding="utf-8") as f:
            json.dump(params, f, ensure_ascii=False)

        python_exe = sys.executable

        # 学习通积分任务使用专用worker
        if job_type == "chaoxing_points":
            cmd = [python_exe, CHAOXING_WORKER_SCRIPT, self._params_file, self._status_file]
        else:
            cmd = [python_exe, WORKER_SCRIPT, self._params_file, self._status_file]
        logger.info("启动子进程: {}", " ".join(cmd))

        log_fh = open(self._log_file, "w", encoding="utf-8")
        try:
            worker_env = os.environ.copy()
            worker_env["MALLOC_ARENA_MAX"] = "2"
            worker_env["MALLOC_MMAP_THRESHOLD_"] = "65536"
            worker_env["PYTHONDONTWRITEBYTECODE"] = "1"
            self._process = subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(WORKER_SCRIPT),
                env=worker_env,
            )
        except Exception as e:
            log_fh.close()
            raise
        self._log_fh = log_fh

        try:
            while self._running and self._process.poll() is None:
                time.sleep(3)
                status_data = self._read_status()
                if status_data.get("heavy_done") or status_data.get("phase") == "study_running":
                    logger.info("重阶段完成，刷课进程已在后台运行")
                    break
        finally:
            if hasattr(self, '_log_fh') and self._log_fh:
                try:
                    self._log_fh.close()
                except Exception:
                    pass

        status_data = self._read_status()

        rc = self._process.returncode
        if not status_data:
            status_data = self._read_status_file()

        if status_data.get("heavy_done") or status_data.get("phase") == "study_running":
            logger.info("重阶段完成，刷课子进程已在后台运行")
            return {
                "platform": platform_name,
                "success": True,
                "heavy_done": True,
                "status_file": self._status_file,
                "tmpdir": self._tmpdir,
                "message": "重阶段完成，刷课已在后台运行",
            }
        elif rc == 42:
            logger.info("今日任务完成，等待明天恢复")
            return {
                "platform": platform_name,
                "success": True,
                "daily_done": True,
                "status_file": self._status_file,
                "message": status_data.get("message", "今日积分已满，明天继续"),
            }
        elif rc == 0 and status_data.get("success"):
            logger.info("任务完成")
            return {
                "platform": platform_name,
                "success": True,
                "message": status_data.get("message", "任务完成"),
            }
        else:
            msg = status_data.get("message", f"子进程退出码: {rc}")
            logger.error("任务失败: {}", msg)
            return {
                "platform": platform_name,
                "success": False,
                "message": msg,
            }

    def cancel(self):
        self._running = False
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def cleanup(self):
        if self._tmpdir and os.path.exists(self._tmpdir):
            try:
                shutil.rmtree(self._tmpdir, ignore_errors=True)
                logger.info("已清理临时目录: {}", self._tmpdir)
            except Exception as e:
                logger.warning("清理临时目录失败: {}", e)

    def _read_status_file(self) -> dict:
        if not self._status_file or not os.path.exists(self._status_file):
            return {}
        try:
            with open(self._status_file) as f:
                return json.load(f)
        except Exception as e:
            return {}

    def _read_status(self) -> dict:
        data = self._read_status_file()
        if not data:
            return {}

        phase = data.get("phase", "")
        message = data.get("message", "")
        video_done = data.get("video_done", 0)
        video_total = data.get("video_total", 0)

        # 学习通积分任务进度
        if phase == "chaoxing_points":
            points_total = data.get("points_total", 0)
            points_target = data.get("points_target", 200)
            if points_target > 0:
                self._progress = min(100.0, points_total / points_target * 100)
            self._current_status = message or f"积分 {points_total}/{points_target}"
        elif phase == "video" and video_total > 0:
            video_pct = data.get("video_pct", 0)
            if video_pct > 0:
                self._progress = float(video_pct)
            else:
                self._progress = video_done / video_total * 100
            self._current_status = message or f"刷视频中 {video_done}/{video_total} ({video_pct}%)"
        elif phase == "study_running":
            video_pct = data.get("video_pct", 0)
            if video_pct > 0:
                self._progress = float(video_pct)
            self._current_status = message or "刷视频中"
        elif phase in ("login", "crawl", "exam"):
            self._current_status = message or phase
        elif phase == "error":
            self._current_status = message

        if self._on_progress:
            self._on_progress(self._progress, video_done, self._current_status)

        return data

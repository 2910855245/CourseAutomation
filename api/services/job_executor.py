"""任务执行 + study阶段监控"""
import json
import os
import shutil
import sys
import threading
import time
from typing import Callable, Optional

from loguru import logger
from sqlalchemy import select



class JobExecutor:
    """负责单个任务的执行和 study 阶段监控"""

    def __init__(self, *, db_update_fn: Callable, db_get_fn: Callable,
                 db_claim_fn: Callable, clear_password_fn: Callable,
                 on_complete: Optional[Callable] = None,
                 on_fail: Optional[Callable] = None,
                 on_progress: Optional[Callable] = None,
                 get_study_semaphore: Callable = None):
        self._db_update = db_update_fn
        self._db_get = db_get_fn
        self._db_claim = db_claim_fn
        self._clear_password = clear_password_fn
        self._on_complete = on_complete
        self._on_fail = on_fail
        self._on_progress = on_progress
        self._get_study_semaphore = get_study_semaphore

    def execute(self, job, release_worker_fn: Callable = None):
        """执行单个任务。release_worker_fn 用于在进入 study 阶段时释放 worker 槽位。"""
        from api.services.task_queue import QueueJobStatus
        job_id = job.job_id
        runner = None
        try:
            if not self._db_claim(job_id):
                logger.warning(f"任务认领失败（已被其他调度器取走） job_id={job_id}")
                return
            # 学习通任务不清密码（daily_done后需要保留密码供明天重试）
            if job.website_id != 4:
                self._clear_password(job_id)
            logger.info(f"任务开始执行 job_id={job_id} username={job.username}")

            from api.services.task_runner import TaskRunner
            runner = TaskRunner(
                username=job.username,
                password=job.password,
                website_id=job.website_id,
                on_progress=lambda p, s, n: self._on_job_progress(job_id, p, s, n),
            )
            result = runner.run(job_type=job.job_type, course_ids=job.course_ids)

            if isinstance(result, dict) and not result.get("success", True):
                raise Exception(result.get("message", "任务失败"))

            if isinstance(result, dict) and result.get("heavy_done"):
                status_file = result.get("status_file")
                if status_file:
                    if release_worker_fn:
                        release_worker_fn(job_id)
                    semaphore = self._get_study_semaphore()
                    acquired = semaphore.acquire(blocking=False)
                    if not acquired:
                        logger.warning(f"study 并发已满，任务排队等待 job_id={job_id}")
                        acquired = semaphore.acquire(blocking=True, timeout=3600)
                        if not acquired:
                            logger.error(f"study 排队超时 job_id={job_id}")
                            self._db_update(job_id, status=QueueJobStatus.FAILED,
                                            error_message="study 并发排队超时（1小时）",
                                            finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
                            self._clear_password(job_id)
                            return
                    try:
                        mon_thread = threading.Thread(
                            target=self.monitor_study,
                            args=(job_id, status_file),
                            daemon=True,
                            name=f"monitor-{job_id}",
                        )
                        mon_thread.start()
                        runner = None
                    except Exception as e:
                        semaphore.release()
                        raise
                else:
                    self._db_update(job_id, status=QueueJobStatus.COMPLETED,
                                    progress=100.0, finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
                return
            elif isinstance(result, dict) and result.get("daily_done"):
                # 今日积分已满，标记为等待状态（不占 worker，明天自动恢复）
                progress = 0.0
                status_file = result.get("status_file")
                if status_file:
                    try:
                        with open(status_file) as f:
                            sd = json.load(f)
                        pt = sd.get("points_total", 0)
                        target = sd.get("points_target", 200)
                        if target > 0:
                            progress = min(100.0, pt / target * 100)
                    except Exception:
                        pass
                self._db_update(job_id,
                                status=QueueJobStatus.WAITING,
                                progress=progress,
                                current_step_name="等待明天继续",
                                error_message="",
                                finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
                logger.info(f"任务进入等待状态 job_id={job_id} progress={progress}")
                # 不清除密码 — 明天恢复时需要
                # 不触发 _on_complete（订单不标记完成，保持运行中直到真正完成）
                return
            else:
                self._db_update(
                    job_id,
                    status=QueueJobStatus.COMPLETED,
                    progress=100.0,
                    completed_steps=job.total_steps,
                    result_data=result if isinstance(result, dict) else {"result": str(result)},
                    finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                )

            logger.info(f"任务执行成功 job_id={job_id}")
            self._clear_password(job_id)
            self._start_verification(job_id, job)
            if self._on_complete:
                self._on_complete(job)

        except Exception as e:
            err_str = str(e)
            logger.error(f"任务执行失败 job_id={job_id} error={err_str}")
            # 登录失败 → 尝试从订单恢复密码后重试
            is_login_err = any(kw in err_str for kw in ("登录", "密码"))
            if is_login_err and job.order_id:
                try:
                    from api.database import db
                    order = db.get_order(job.order_id)
                    if order and order.get("password"):
                        logger.info(f"登录失败，恢复密码后重试 job_id={job_id}")
                        job.password = order["password"]
                        self._db_update(job_id, password=order["password"], retry_count=1)
                        if runner:
                            runner.cleanup()
                            runner = None
                        # 直接重跑TaskRunner，不走execute()（避免_db_claim失败）
                        from api.services.task_runner import TaskRunner
                        runner = TaskRunner(
                            username=job.username,
                            password=job.password,
                            website_id=job.website_id,
                            on_progress=lambda p, s, n: self._on_job_progress(job_id, p, s, n),
                        )
                        result = runner.run(job_type=job.job_type, course_ids=job.course_ids)
                        if isinstance(result, dict) and result.get("heavy_done"):
                            status_file = result.get("status_file")
                            if status_file:
                                if release_worker_fn:
                                    release_worker_fn(job_id)
                                semaphore = self._get_study_semaphore()
                                acquired = semaphore.acquire(blocking=False)
                                if not acquired:
                                    acquired = semaphore.acquire(blocking=True, timeout=3600)
                                if acquired:
                                    mon_thread = threading.Thread(
                                        target=self.monitor_study,
                                        args=(job_id, status_file),
                                        daemon=True, name=f"monitor-{job_id}",
                                    )
                                    mon_thread.start()
                                    runner = None
                                    return
                                else:
                                    raise Exception("study 并发排队超时（1小时）")
                            return
                        elif isinstance(result, dict) and result.get("daily_done"):
                            # 重试时今日积分已满，标记等待
                            progress = 0.0
                            sf = result.get("status_file")
                            if sf:
                                try:
                                    with open(sf) as f2:
                                        sd2 = json.load(f2)
                                    pt2 = sd2.get("points_total", 0)
                                    tgt2 = sd2.get("points_target", 200)
                                    if tgt2 > 0:
                                        progress = min(100.0, pt2 / tgt2 * 100)
                                except Exception:
                                    pass
                            self._db_update(job_id,
                                            status=QueueJobStatus.WAITING,
                                            progress=progress,
                                            current_step_name="等待明天继续",
                                            error_message="",
                                            finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
                            return
                        elif isinstance(result, dict) and not result.get("success", True):
                            raise Exception(result.get("message", "任务失败"))
                        else:
                            self._db_update(job_id, status=QueueJobStatus.COMPLETED,
                                            progress=100.0, finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
                            self._clear_password(job_id)
                            return
                except Exception as retry_err:
                    logger.error(f"重试登录仍然失败 job_id={job_id} error={str(retry_err)}")
                    err_str = str(retry_err)
            enhanced_err = self._enhance_error_message(str(e))
            if job.retry_count < job.max_retries:
                # 恢复密码以便下次重试
                pwd = job.password
                if not pwd and job.order_id:
                    try:
                        from api.database import db
                        _order = db.get_order(job.order_id)
                        if _order:
                            pwd = _order.get("password", "")
                    except Exception:
                        pass
                self._db_update(
                    job_id,
                    status=QueueJobStatus.RETRYING,
                    retry_count=job.retry_count + 1,
                    error_message=enhanced_err,
                    password=pwd,
                )
                logger.info(f"任务重试 job_id={job_id} retry={job.retry_count + 1}")
            else:
                self._db_update(
                    job_id,
                    status=QueueJobStatus.FAILED,
                    error_message=enhanced_err,
                    finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                )
                self._clear_password(job_id)
                if self._on_fail:
                    job.error_message = enhanced_err
                    self._on_fail(job)
        finally:
            if runner:
                runner.cleanup()

    def monitor_study(self, job_id: str, status_file: str):
        """监控 study 阶段的进度文件"""
        from api.services.task_queue import QueueJobStatus

        tmpdir = os.path.dirname(status_file)
        max_wait = 7200
        elapsed = 0
        stale_seconds = 0
        last_mtime = 0
        semaphore = self._get_study_semaphore()
        try:
            while elapsed < max_wait:
                time.sleep(10)
                elapsed += 10
                stale_seconds += 10
                try:
                    current_mtime = os.path.getmtime(status_file)
                    if current_mtime != last_mtime:
                        last_mtime = current_mtime
                        stale_seconds = 0
                    with open(status_file, encoding="utf-8") as f:
                        data = json.load(f)
                except FileNotFoundError:
                    raise Exception("状态文件丢失，刷课进程异常退出")
                except Exception as e:
                    continue

                video_pct = data.get("video_pct", 0)
                video_done = data.get("video_done", 0)
                video_total = data.get("video_total", 0)
                message = data.get("message", "")

                # 学习通任务：从 points/study 字段计算进度
                if video_pct == 0:
                    phase = data.get("phase", "")
                    pt = data.get("points_total", 0)
                    pt_target = data.get("points_target", 0)
                    st_done = data.get("study_done", 0)
                    st_total = data.get("study_total", 0)
                    if phase == "study_must_learn" and st_total > 0:
                        # 从 message 中解析当前篇的百分比
                        import re as _re
                        _m = _re.search(r'(\d+)%', message)
                        _cur_pct = int(_m.group(1)) / 100 if _m else 0
                        video_pct = min(100.0, (st_done + _cur_pct) / st_total * 100)
                    elif pt_target > 0:
                        video_pct = min(100.0, pt / pt_target * 100)

                self._db_update(job_id, progress=float(video_pct),
                                current_step_name=message or f"刷视频中 {video_done}/{video_total}")
                if self._on_progress:
                    self._on_progress(job_id, float(video_pct), video_done, message or f"刷视频中 {video_done}/{video_total}")

                if data.get("done") and data.get("success"):
                    phase = data.get("phase", "")
                    # 学习通 daily_done 不检查95%，只是今日暂停（保留密码供明天重试）
                    if phase == "daily_done":
                        self._db_update(job_id, status=QueueJobStatus.PENDING,
                                        progress=float(video_pct),
                                        current_step_name=message or "今日积分已满，明天继续")
                        return
                    actual_pct = data.get("video_pct", video_pct)
                    if actual_pct < 95:
                        raise Exception(f"平台实际进度仅{actual_pct}%，未达到完成标准(95%)")
                    self._db_update(job_id, status=QueueJobStatus.COMPLETED,
                                    progress=float(actual_pct), finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                                    current_step_name="刷课完成")
                    self._clear_password(job_id)
                    job = self._db_get(job_id)
                    if job:
                        self._start_verification(job_id, job)
                        if self._on_complete:
                            self._on_complete(job)
                    return
                elif data.get("done") and data.get("success") is False:
                    raise Exception(data.get("message", "刷课失败"))
                elif data.get("phase") == "error":
                    raise Exception(data.get("message", "刷课异常"))
                if data.get("phase") in ("video", "study_running") and stale_seconds >= 300:
                    study_pid = data.get("study_pid", 0)
                    if study_pid:
                        try:
                            os.kill(study_pid, 0)
                        except OSError:
                            raise Exception("刷课进程已中断（内存不足或异常退出），请重新提交")

            raise Exception("刷课超时")
        except Exception as e:
            logger.error(f"监控线程异常 job_id={job_id} error={str(e)}")
            self._db_update(job_id, status=QueueJobStatus.FAILED,
                            error_message=str(e),
                            finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
            self._clear_password(job_id)
            job = self._db_get(job_id)
            if job and self._on_fail:
                job.error_message = str(e)
                self._on_fail(job)
        finally:
            semaphore.release()
            if tmpdir and os.path.exists(tmpdir):
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception as e:
                    pass

    def _on_job_progress(self, job_id: str, progress: float, step: int, step_name: str):
        self._db_update(job_id, progress=progress, completed_steps=step, current_step_name=step_name)
        if self._on_progress:
            self._on_progress(job_id, progress, step, step_name)

    def _start_verification(self, job_id: str, job):
        """启动后台线程核查任务是否真正在平台上完成"""
        def _verify():
            try:
                from api.services.task_verifier import verify_task_completion
                result = verify_task_completion(
                    username=job.username,
                    website_id=job.website_id,
                    course_ids=job.course_ids or [],
                    job_type=job.job_type,
                )
                if result.get("verified"):
                    self._db_update(job_id, verified=True)
                    logger.info("任务核查通过 job_id={} detail={}", job_id, result.get("detail"))
                else:
                    logger.warning("任务核查未通过 job_id={} detail={}", job_id, result.get("detail"))
            except Exception as e:
                logger.warning(f"任务核查异常 job_id={job_id} error={str(e)}")

        t = threading.Thread(target=_verify, daemon=True, name=f"verify-{job_id}")
        t.start()

    @staticmethod
    def _enhance_error_message(err_msg: str) -> str:
        """如果错误信息像步骤名（如 '考试 1/2: xxx'），追加上下文使其可分类"""
        if not err_msg:
            return "未知错误（进程异常退出）"
        error_keywords = ("失败", "错误", "超时", "异常", "中断", "不存在", "删除", "禁用",
                          "登录", "密码", "题库", "期末考试", "不支持", "暂不支持",
                          "课程", "账号", "Cookie", "会话", "锁定",
                          "timeout", "error", "exception", "killed")
        if any(kw in err_msg for kw in error_keywords):
            return err_msg
        return f"步骤中断: {err_msg}（worker进程异常退出，请查看worker日志）"

    @staticmethod
    def recover_stuck_jobs(db_session_factory, db_model):
        """重启后将遗留的 running 任务重置为 pending，但跳过仍有活跃子进程的任务"""
        session = db_session_factory()
        try:
            running_jobs = session.scalars(select(db_model).filter(db_model.status == "running")).all()
            reset_count = 0
            for job in running_jobs:
                alive = False
                try:
                    import psutil
                    for proc in psutil.process_iter(["cmdline"]):
                        cmdline = proc.info.get("cmdline") or []
                        cmdline_str = " ".join(cmdline)
                        if ("study_worker" in cmdline_str or "chaoxing_worker" in cmdline_str) and job.order_id and job.order_id in cmdline_str:
                            alive = True
                            break
                except ImportError:
                    import subprocess as sp
                    try:
                        if sys.platform == "win32":
                            r = sp.run(["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
                                       capture_output=True, text=True, timeout=5)
                            alive = job.order_id in r.stdout if r.stdout else False
                        else:
                            r = sp.run(["pgrep", "-f", f"(study_worker|chaoxing_worker).*{job.order_id}"],
                                       capture_output=True, text=True, timeout=5)
                            alive = bool(r.stdout.strip())
                    except Exception as e:
                        pass
                if alive:
                    logger.info(f"恢复跳过-子进程存活 job_id={job.job_id} order_id={job.order_id}")
                    continue
                # 密码为空时从订单恢复
                if not job.password and job.order_id:
                    try:
                        from api.database import db
                        order = db.get_order(job.order_id)
                        if order and order.get("password"):
                            job.password = order["password"]
                            logger.info(f"从订单恢复密码 job_id={job.job_id}")
                    except Exception as e:
                        logger.warning(f"恢复密码失败 job_id={job.job_id} error={str(e)}")
                # waiting 任务保留进度，其他重置
                if job.status != "waiting":
                    job.progress = 0
                job.status = "pending"
                job.started_at = None
                reset_count += 1
            session.commit()
            if reset_count:
                logger.info(f"恢复卡死任务 count={reset_count}")
        except Exception as e:
            session.rollback()
            logger.error("恢复卡死任务失败 error={}", str(e))
        finally:
            session.close()

    @staticmethod
    def recover_unverified_jobs(db_session_factory, db_model):
        """启动时补核查：已完成但未核查的任务重新验证"""
        session = db_session_factory()
        try:
            jobs = session.scalars(select(db_model).filter(
                db_model.status == "completed",
                db_model.verified == 0,
            ).order_by(db_model.finished_at.desc()).limit(20)).all()
        finally:
            session.close()

        if not jobs:
            return

        logger.info(f"补核查未验证任务 count={len(jobs)}")

        def _batch_verify():
            import time as _time
            _time.sleep(30)  # 等待会话恢复完成
            from api.services.task_verifier import verify_task_completion
            for job in jobs:
                try:
                    result = verify_task_completion(
                        username=job.username,
                        website_id=job.website_id,
                        course_ids=job.course_ids or [],
                        job_type=job.job_type,
                    )
                    s = db_session_factory()
                    try:
                        db_job = s.get(db_model, job.job_id)
                        if db_job:
                            db_job.verified = 1 if result.get("verified") else 0
                            s.commit()
                    finally:
                        s.close()

                    if result.get("verified"):
                        logger.info("补核查通过 job_id={} detail={}", job.job_id, result.get("detail"))
                    else:
                        logger.warning("补核查未通过 job_id={} detail={}", job.job_id, result.get("detail"))
                except Exception as e:
                    logger.warning(f"补核查异常 job_id={job.job_id} error={str(e)}")

        t = threading.Thread(target=_batch_verify, daemon=True, name="recover-verify")
        t.start()

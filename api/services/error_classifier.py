"""错误分类 + 自动纠错逻辑"""
import time
from typing import Any, Callable, Dict

from loguru import logger



class ErrorClassifier:
    """将错误消息分类为 retryable / fatal / unknown，并提供自动纠错能力"""

    # 可重试的错误模式（子串匹配）
    RETRYABLE_PATTERNS = [
        "study 并发排队超时",
        "刷课进程已中断",
        "刷课超时",
        "状态文件丢失",
        "视频下载失败",
        # 登录/cookie相关 — cookie过期导致，恢复密码后可重试
        "密码不能为空",
        "密码不为空",
        "登录平台失败",
        "登录失败",
    ]

    # 不可重试的错误模式
    FATAL_PATTERNS = [
        "密码错误",
        "账号被禁用",
        "账号不存在",
        "学生信息不存在",
        "已不存在",
        "已被删除",
        "已被老师删除",
        # 考试类错误 — 平台限制，重试无意义
        "暂不支持",
        "不支持期末考试",
        "不支持考试",
        "不支持该考试",
        "尚未生成答题记录",
        "题库",
        "期末考试",
        # 平台进度为0% — 重试也不会更新
        "平台实际进度仅0%",
        "平台进度仅0%",
        "已完成的平台进度仅0%",
        "不能被平台欺骗",
        "已上报完成的平台进度仅0%",
    ]

    @classmethod
    def classify(cls, error_message: str) -> str:
        """分类错误: 'retryable' / 'fatal' / 'unknown'(默认retryable)"""
        if not error_message:
            return "retryable"
        clean = error_message
        if clean.startswith("[已标记]"):
            clean = clean[len("[已标记]"):]
        for pat in cls.FATAL_PATTERNS:
            if pat in clean:
                return "fatal"
        for pat in cls.RETRYABLE_PATTERNS:
            if pat in clean:
                return "retryable"
        return "retryable"

    @classmethod
    def auto_correct_errors(cls) -> int:
        """扫描失败任务，自动重试可恢复的错误。返回重置数量。"""
        from api.db.models import ChaoxingJobModel, SchoolJobModel
        from api.database import SessionLocal
        from api.services.task_queue import QueueJobStatus

        total_reset = 0
        for JobModel in [SchoolJobModel, ChaoxingJobModel]:
            total_reset += cls._auto_correct_one(JobModel, SessionLocal, QueueJobStatus)
        return total_reset

    @classmethod
    def _auto_correct_one(cls, JobModel, JobSession, QueueJobStatus) -> int:
        session = JobSession()
        try:
            failed_jobs = session.scalars(select(JobModel).filter(
                JobModel.status == QueueJobStatus.FAILED,
            )).all()

            if not failed_jobs:
                return 0

            retryable = []
            fatal = []

            for job in failed_jobs:
                category = cls.classify(job.error_message or "")
                if category == "retryable":
                    retryable.append(job)
                elif category == "fatal":
                    fatal.append(job)

            if not retryable and not fatal:
                return 0

            logger.info("纠错扫描: 可重试={} 不可重试={}", len(retryable), len(fatal))

            reset_count = 0
            for job in retryable:
                if job.retry_count >= 5:
                    logger.info(f"已达最大自动重试次数，跳过 job_id={job.job_id} retries={job.retry_count}")
                    continue
                # 从订单表恢复密码（executor执行后会清除密码，重试必须恢复）
                if not job.password and job.order_id:
                    try:
                        from api.database import db
                        order = db.get_order(job.order_id)
                        if order and order.get("password"):
                            job.password = order["password"]
                            logger.info(f"自动纠错: 恢复密码 job_id={job.job_id}")
                    except Exception as e:
                        pass
                job.status = QueueJobStatus.PENDING
                job.progress = 0
                job.error_message = ""
                job.started_at = None
                job.finished_at = None
                job.retry_count += 1
                reset_count += 1
                logger.info(f"自动纠错: 重置为pending job_id={job.job_id} username={job.username} retries={job.retry_count}")

            if reset_count:
                session.commit()
                logger.info(f"自动纠错完成 reset_count={reset_count}")
            else:
                session.rollback()

            for job in fatal:
                if not (job.error_message or "").startswith("[已标记]"):
                    job.error_message = "[已标记]" + (job.error_message or "")
            session.commit()

            return reset_count

        except Exception as e:
            session.rollback()
            logger.error(f"自动纠错异常 exc_info={True}")
            return 0
        finally:
            session.close()

    @classmethod
    def get_error_stats(cls) -> Dict[str, Any]:
        """返回失败任务的错误分类统计"""
        from api.db.models import ChaoxingJobModel, SchoolJobModel
        from api.database import SessionLocal
        from api.services.task_queue import QueueJobStatus

        retryable = []
        fatal = []
        unknown = []
        for JobModel in [SchoolJobModel, ChaoxingJobModel]:
            session = SessionLocal()
            try:
                failed = session.scalars(select(JobModel).filter(
                    JobModel.status == QueueJobStatus.FAILED
                )).all()
                for job in failed:
                    cat = cls.classify(job.error_message or "")
                    entry = {
                        "job_id": job.job_id,
                        "username": job.username,
                        "website_id": job.website_id,
                        "order_id": job.order_id,
                        "error": (job.error_message or "")[:200],
                        "retry_count": job.retry_count,
                    }
                    if cat == "retryable":
                        retryable.append(entry)
                    elif cat == "fatal":
                        fatal.append(entry)
                    else:
                        unknown.append(entry)
            finally:
                session.close()

        return {
            "retryable": retryable,
            "fatal": fatal,
            "unknown": unknown,
            "summary": {
                "retryable_count": len(retryable),
                "fatal_count": len(fatal),
                "unknown_count": len(unknown),
                "total_failed": len(retryable) + len(fatal) + len(unknown),
            },
        }


def correction_loop(running_flag: Callable[[], bool]):
    """纠错后台循环，每5分钟扫描一次。running_flag 返回 False 时退出。"""
    while running_flag():
        try:
            time.sleep(300)
            if not running_flag():
                break
            ErrorClassifier.auto_correct_errors()
        except Exception as e:
            logger.error(f"纠错线程异常 exc_info={True}")

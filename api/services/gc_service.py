import glob
import os
import shutil
import threading
import time
from datetime import datetime, timedelta

from loguru import logger



def cleanup_orphan_tmpdirs(max_age_hours: int = 24) -> int:
    count = 0
    cutoff = time.time() - max_age_hours * 3600
    for d in glob.glob("/tmp/task_*"):
        try:
            if os.path.isdir(d) and os.path.getmtime(d) < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                count += 1
        except Exception as e:
            pass
    if count > 0:
        logger.info(f"GC: 清理孤立临时目录 count={count}")
    return count


def cleanup_old_audit_logs(days: int = 30) -> int:
    try:
        from sqlalchemy import delete
        from api.database import db
        with db._session_scope() as session:
            from api.database import AuditLog
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            count = session.execute(delete(AuditLog).filter(AuditLog.created_at < cutoff)).rowcount
            if count > 0:
                logger.info(f"GC: 清理历史审计日志 count={count}")
            return count
    except Exception as e:
        logger.warning(f"GC: 清理审计日志失败 error={str(e)}")
        return 0


def cleanup_old_orders(days: int = 30) -> int:
    try:
        from sqlalchemy import delete
        from api.database import db
        with db._session_scope() as session:
            from api.database import Order
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            count = session.execute(delete(Order).filter(
                Order.status.in_(["completed", "failed", "cancelled"]),
                Order.updated_at < cutoff,
            )).rowcount
            if count > 0:
                logger.info(f"GC: 清理历史订单 count={count}")
            return count
    except Exception as e:
        logger.warning(f"GC: 清理历史订单失败 error={str(e)}")
        return 0


def cleanup_old_queue_jobs(days: int = 7) -> int:
    try:
        from api.services.task_queue import school_queue, chaoxing_queue
        return school_queue.cleanup_old_jobs(days=days) + chaoxing_queue.cleanup_old_jobs(days=days)
    except Exception as e:
        logger.warning(f"GC: 清理队列任务失败 error={str(e)}")
        return 0


def cleanup_stale_account_dirs(max_age_days: int = 90) -> int:
    try:
        from config import ACCOUNTS_DIR
        accounts_dir = ACCOUNTS_DIR
        if not os.path.isdir(accounts_dir):
            return 0
        cutoff = time.time() - max_age_days * 86400
        count = 0
        for name in os.listdir(accounts_dir):
            if name.startswith("."):
                continue
            dpath = os.path.join(accounts_dir, name)
            if not os.path.isdir(dpath):
                continue
            try:
                if os.path.getmtime(dpath) < cutoff:
                    shutil.rmtree(dpath, ignore_errors=True)
                    count += 1
            except Exception as e:
                pass
        if count > 0:
            logger.info(f"GC: 清理过期账号目录 count={count}")
        return count
    except Exception as e:
        logger.warning(f"GC: 清理账号目录失败 error={str(e)}")
        return 0


def cleanup_old_log_files(max_age_days: int = 30) -> int:
    try:
        from config import LOGS_DIR
        if not os.path.isdir(LOGS_DIR):
            return 0
        cutoff = time.time() - max_age_days * 86400
        count = 0
        for fname in os.listdir(LOGS_DIR):
            fpath = os.path.join(LOGS_DIR, fname)
            if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                try:
                    os.remove(fpath)
                    count += 1
                except Exception as e:
                    pass
        if count > 0:
            logger.info(f"GC: 清理历史日志文件 count={count}")
        return count
    except Exception as e:
        logger.warning(f"GC: 清理日志文件失败 error={str(e)}")
        return 0


def _gc_loop():
    time.sleep(60)
    logger.info("GC 服务启动")
    cycle = 0
    while True:
        try:
            cleanup_orphan_tmpdirs(max_age_hours=24)
            if cycle % 6 == 0:
                cleanup_old_queue_jobs(days=7)
            if cycle % 36 == 0:
                cleanup_old_audit_logs(days=30)
                cleanup_old_orders(days=30)
                cleanup_old_log_files(max_age_days=30)
            if cycle % 144 == 0:
                cleanup_stale_account_dirs(max_age_days=90)
        except Exception as e:
            logger.error(f"GC 循环异常 error={str(e)}")
        cycle += 1
        time.sleep(3600)


def start_gc_service():
    t = threading.Thread(target=_gc_loop, daemon=True, name="gc-service")
    t.start()
    logger.info("GC 定时服务已注册")

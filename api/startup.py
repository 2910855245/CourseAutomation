"""Startup logic extracted from main.py"""

import glob
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime

from loguru import logger



def _init_prices(db):
    default_prices = {"video_unit_price": "0.10", "exam_unit_price": "0.15"}
    for key, val in default_prices.items():
        if db.config_get(key) is None:
            db.config_set(key, val)
            logger.info(f"初始化默认价格配置 key={key} value={val}")


def _setup_queue_callbacks(db, queue):
    """为单个队列设置回调（school/chaoxing 各调一次）"""
    def _on_job_complete(job):
        if job.order_id:
            order = db.get_order(job.order_id)
            if order and order.get("status") not in ("completed", "cancelled"):
                if order["user_id"]:
                    db.increment_user_order_stats(order["user_id"], order["price"])
                db.complete_order(job.order_id)
                logger.info(f"订单完成 order_id={job.order_id}")
                try:
                    from api.routers.agents import calculate_commission
                    calculate_commission(job.order_id, order["user_id"], order["price"])
                except Exception as e:
                    logger.error(f"佣金计算失败 error={str(e)}")

    def _on_job_fail(job):
        if job.order_id:
            order = db.get_order(job.order_id)
            if not order:
                return
            # 在两个队列中查找该订单的活跃任务
            from api.services.task_queue import school_queue, chaoxing_queue
            has_active_jobs = False
            for q in (school_queue, chaoxing_queue):
                try:
                    active_jobs = q.get_jobs_by_order(job.order_id)
                    has_active_jobs = any(
                        j.status in ("pending", "running", "retrying") and j.job_id != job.job_id
                        for j in active_jobs
                    )
                    if has_active_jobs:
                        break
                except Exception:
                    pass
            if not has_active_jobs:
                if order.get("paid") and order["price"] > 0 and order["user_id"]:
                    if order.get("status") not in ("failed", "completed", "cancelled"):
                        db.update_user_balance(
                            order["user_id"],
                            order["price"],
                            "order_refund",
                            note=f"订单 {job.order_id} 失败退款",
                            order_id=job.order_id,
                        )
                db.fail_order(job.order_id, error=job.error_message or "任务执行失败")
                logger.error(f"订单失败 order_id={job.order_id} error={job.error_message}")
            else:
                logger.info("任务失败但有重试任务待执行，暂不标记订单失败",
                           order_id=job.order_id, job_id=job.job_id)

    queue.set_callbacks(on_complete=_on_job_complete, on_fail=_on_job_fail)


@logger.catch
def _auto_cancel_loop(db):
    while True:
        time.sleep(60)
        count = db.auto_cancel_expired_pending(minutes=5)
        if count > 0:
            logger.info(f"自动取消过期订单 count={count}")


@logger.catch
def _ypay_heartbeat_monitor(db):
    while True:
        time.sleep(30)
        monitor_status = db.ypay_setting_get("monitor_status", "offline")
        if monitor_status in ("offline", "key_mismatch"):
            continue
        monitor_heart = db.ypay_setting_get("monitor_last_heart", "")
        if not monitor_heart:
            continue
        try:
            last = datetime.fromisoformat(monitor_heart)
            delta = (datetime.now().replace(tzinfo=None) - last.replace(tzinfo=None)).total_seconds()
        except Exception:
            continue
        if delta > 180:
            db.ypay_setting_set("monitor_status", "offline")
            logger.warning(f"ypay_heartbeat_timeout seconds_ago={int(delta)} last_heart={monitor_heart}")
            pass


def _recovered_monitor(db, order_id, status_file):
    max_wait = 7200
    elapsed = 0
    stale_seconds = 0
    last_mtime = 0
    tmpdir = os.path.dirname(status_file)
    while elapsed < max_wait:
        time.sleep(10)
        elapsed += 10
        stale_seconds += 10
        try:
            order = db.get_order(order_id)
            if not order or order.get("status") != "running":
                return
            current_mtime = os.path.getmtime(status_file)
            if current_mtime != last_mtime:
                last_mtime = current_mtime
                stale_seconds = 0
            with open(status_file, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("done") or data.get("success"):
                db.complete_order(order_id)
                logger.info(f"恢复监控-订单完成 order_id={order_id}")
                shutil.rmtree(tmpdir, ignore_errors=True)
                return
            elif data.get("phase") == "error":
                db.fail_order(order_id, error=data.get("message", "刷课异常"))
                logger.error(f"恢复监控-订单失败 order_id={order_id}")
                shutil.rmtree(tmpdir, ignore_errors=True)
                return
            if data.get("phase") in ("video", "study_running") and stale_seconds >= 300:
                try:
                    result = subprocess.run(
                        ["pgrep", "-f", f"study_worker.*{os.path.basename(tmpdir)}$"],
                        capture_output=True, text=True, timeout=5
                    )
                    if not result.stdout.strip():
                        db.fail_order(order_id, error="刷课进程已中断，请重新提交")
                        logger.error(f"恢复监控-进程已死 order_id={order_id} status_file={status_file}")
                        shutil.rmtree(tmpdir, ignore_errors=True)
                        return
                except Exception as e:
                    pass
        except FileNotFoundError:
            db.fail_order(order_id, error="状态文件丢失")
            shutil.rmtree(tmpdir, ignore_errors=True)
            return
        except Exception as e:
            continue
    db.fail_order(order_id, error="任务执行超时")
    shutil.rmtree(tmpdir, ignore_errors=True)


def _recover_running_orders(db):
    time.sleep(5)
    try:
        running_orders = db.list_orders(status="running")
        if not running_orders:
            return
        logger.info(f"恢复运行中订单监控 count={len(running_orders)}")
        from api.services.task_manager import recovered_order_mappings
        from api.services.task_queue import school_queue, chaoxing_queue
        used_status_files = set()
        for order in running_orders:
            oid = order.get("order_id", "")
            username = order.get("username", "")
            if not username:
                continue
            existing_job = school_queue.get_job_by_order_id(oid) or chaoxing_queue.get_job_by_order_id(oid)
            if existing_job and existing_job.status in ("pending", "running", "retrying"):
                logger.info(f"恢复跳过-已有队列任务 order_id={oid} job_id={existing_job.job_id}")
                recovered_order_mappings[oid] = ""
                continue
            matched_status = None
            for sf in glob.glob("/tmp/task_*/status.json"):
                if sf in used_status_files:
                    continue
                try:
                    with open(sf, encoding="utf-8") as f:
                        data = json.load(f)
                    pf = sf.replace("status.json", "params.json")
                    with open(pf, encoding="utf-8") as f:
                        params = json.load(f)
                    if params.get("username") == username and data.get("phase") in (
                        "video", "study_running"):
                        if not data.get("done") and not data.get("success"):
                            matched_status = sf
                            break
                except Exception as e:
                    continue
            if matched_status:
                used_status_files.add(matched_status)
                recovered_order_mappings[oid] = matched_status
                threading.Thread(
                    target=_recovered_monitor,
                    args=(db, oid, matched_status),
                    daemon=True,
                ).start()
                logger.info(f"恢复订单监控 order_id={oid} status_file={matched_status}")
            else:
                for sf in glob.glob("/tmp/task_*/status.json"):
                    if sf in used_status_files:
                        continue
                    try:
                        with open(sf, encoding="utf-8") as f:
                            data = json.load(f)
                        pf = sf.replace("status.json", "params.json")
                        with open(pf, encoding="utf-8") as f:
                            params = json.load(f)
                        if params.get("username") == username and (
                            data.get("done") or data.get("success")):
                            db.complete_order(oid)
                            logger.info(f"恢复订单-已完成 order_id={oid}")
                            break
                    except Exception as e:
                        continue
    except Exception as e:
        logger.error(f"恢复订单监控失败 error={str(e)}")


def _restore_sessions(session_pool):
    try:
        from config import WEBSITES
        cookies_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "accounts")
        if not os.path.isdir(cookies_base):
            return
        restored = 0
        for user_dir in glob.glob(os.path.join(cookies_base, "*")):
            username = os.path.basename(user_dir)
            for wid in WEBSITES:
                try:
                    si = session_pool.restore(username, wid)
                    if si:
                        restored += 1
                except Exception as e:
                    pass
        if restored:
            logger.info(f"自动恢复会话 count={restored}")
    except Exception as e:
        logger.warning(f"自动恢复会话失败 error={str(e)}")


def run_startup(settings):
    from api.database import db
    from api.services.task_queue import school_queue, chaoxing_queue, migrate_old_queue_table

    _init_prices(db)

    # 迁移旧表数据（如果有）
    migrate_old_queue_table()

    # 两个队列各自启动
    _setup_queue_callbacks(db, school_queue)
    _setup_queue_callbacks(db, chaoxing_queue)
    school_queue.start()
    chaoxing_queue.start()

    threading.Thread(target=_auto_cancel_loop, args=(db,), daemon=True).start()
    threading.Thread(target=_ypay_heartbeat_monitor, args=(db,), daemon=True).start()
    threading.Thread(target=_recover_running_orders, args=(db,), daemon=True).start()

    from api.services.gc_service import start_gc_service
    start_gc_service()

    from api.services.domain_monitor import start_domain_monitor
    start_domain_monitor()

    from api.services.session_pool import pool as session_pool
    from infrastructure.platform_health import HealthMonitorDaemon

    _restore_sessions(session_pool)

    _health_monitor = HealthMonitorDaemon(session_pool=session_pool)
    _health_monitor.start()

    logger.info(f"API 服务启动 host={settings.host} port={settings.port}")

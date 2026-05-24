import json
import os
import signal
import subprocess
import sys
import time
import traceback

from loguru import logger

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())


_shutdown_requested = False


def send_status(status_file, **kwargs):
    data = {}
    if os.path.exists(status_file):
        try:
            with open(status_file) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    data.update(kwargs)
    data["updated_at"] = time.time()
    tmp_file = status_file + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_file, status_file)


def _apply_proxy(session):
    """加载隧道代理配置并应用到 session"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api', 'services'))
        from proxy_config import get_proxy_config
        cfg = get_proxy_config()
        if cfg["enabled"]:
            session.proxies.update(cfg["proxies"])
            logger.info("已启用隧道代理")
    except Exception as e:
        pass


def load_session(username, password, website_id):
    import httpx

    from config import WEBSITES, get_account_cookies_path, set_current_website, update_url_config
    from services.multi_platform_auth import (
        check_platform_cookie_valid,
        login_single_platform,
        save_platform_cookie,
    )

    set_current_website(website_id)
    update_url_config()

    base_url = WEBSITES.get(website_id, {}).get("base_url", "")

    # w=2 劳动教育平台session过期快，跳过缓存直接重新登录
    cookie_file = get_account_cookies_path(username, WEBSITES.get(website_id, {}).get("name"))
    if website_id != 2 and os.path.exists(cookie_file):
        session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
        _apply_proxy(session)
        with open(cookie_file, encoding="utf-8") as f:
            cookies = json.load(f)
        for c in cookies:
            if isinstance(c, dict):
                session.cookies.set(c["name"], c["value"])
            else:
                session.cookies.set(c, cookies[c])
        try:
            if check_platform_cookie_valid(session, website_id):
                return session, base_url
        except Exception as e:
            pass

    wid, ok, session, msg = login_single_platform(website_id, username, password)
    if not ok:
        raise Exception(f"登录平台失败: {msg}")

    _apply_proxy(session)
    save_platform_cookie(username, website_id, session)
    return session, base_url


def run_task(params_file, status_file):
    with open(params_file, encoding="utf-8") as f:
        params = json.load(f)

    username = params["username"]
    password = params["password"]
    website_id = params["website_id"]
    job_type = params.get("job_type", "full")
    course_ids = params.get("course_ids", [])
    concurrency = params.get("concurrency", 8)

    send_status(status_file, phase="login", message="正在登录...")

    try:
        session, base_url = load_session(username, password, website_id)
    except Exception as e:
        send_status(status_file, phase="error", message=f"登录失败: {e}", done=True, success=False)
        return

    send_status(status_file, phase="crawl", message="正在获取课程...")

    from infrastructure.course_crawler import get_courses
    from services.scan_service import load_course_cache, scan_course

    courses = get_courses(session)
    logger.info("获取到 {} 门课程", len(courses) if courses else 0)
    if not courses:
        send_status(status_file, phase="error", message="获取课程列表失败", done=True, success=False)
        return

    all_videos = []
    all_exams = []

    for i, course in enumerate(courses):
        cid = course.get("course_id", "")
        if course_ids and cid not in course_ids:
            continue
        cname = course.get("name", "")

        # 优先用课程缓存（下单前扫描的详细结果，30分钟内有效）
        cached = load_course_cache(username, website_id, cid)
        if cached:
            send_status(status_file, phase="crawl", message=f"缓存命中 {i+1}/{len(courses)}: {cname}")
            logger.info("课程缓存命中: {} (id={})", cname, cid)
            all_videos.extend(cached.get("videos", []))
            cached_exams = cached.get("exams", []) + cached.get("works", [])
            non_done_exams = [e for e in cached_exams if not e.get("is_done") and not e.get("is_deleted") and e.get("time_status", "进行中") == "进行中"]
            skipped = len([e for e in cached_exams if not e.get("is_done") and not e.get("is_deleted")]) - len(non_done_exams)
            if non_done_exams:
                all_exams.extend(non_done_exams)
                logger.info("  缓存考试: {} 个可考, {} 个未到/已过期", len(non_done_exams), skipped)
            else:
                logger.info("  缓存无可用考试数据，将实时获取")
                cached = None  # 回退到实时扫描

        if not cached:
            send_status(status_file, phase="crawl", message=f"解析课程 {i+1}/{len(courses)}: {cname}")
            logger.info("处理课程: {} (id={})", cname, cid)

            try:
                result = scan_course(session, cid, cname)
                all_videos.extend(result.get("videos", []))
                fresh_exams = result.get("exams", []) + result.get("works", [])
                non_done = [e for e in fresh_exams if not e.get("is_done") and not e.get("is_deleted") and e.get("time_status", "进行中") == "进行中"]
                skipped = len([e for e in fresh_exams if not e.get("is_done") and not e.get("is_deleted")]) - len(non_done)
                all_exams.extend(non_done)

                logger.info("  视频=%d 考试=%d 作业=%d 可考=%d 跳过=%d",
                            len(result.get("videos", [])),
                            len(result.get("exams", [])),
                            len(result.get("works", [])),
                            len(non_done), skipped)
            except Exception as e:
                logger.error("处理课程 {} 失败: {}", cname, e)

    logger.info("汇总: 视频={}, 考试/作业={}", len(all_videos), len(all_exams))

    if not all_videos and not all_exams:
        send_status(status_file, phase="error", message="未找到任何视频或考试", done=True, success=False)
        return

    cookie_str = "; ".join([f"{k}={v}" for k, v in session.cookies.items()])

    # ── 第一阶段：刷视频（必须在考试之前完成） ──
    video_success = True
    if job_type in ("video", "full", "all") and all_videos:
        task_dir = os.path.dirname(status_file)
        videos_file = os.path.join(task_dir, "videos.json")

        study_params = {
            "base_url": base_url,
            "cookie_str": cookie_str,
            "username": username,
            "password": password,
        }
        params.update(study_params)
        with open(params_file, "w", encoding="utf-8") as f:
            json.dump(params, f, ensure_ascii=False)
        with open(videos_file, "w", encoding="utf-8") as f:
            json.dump(all_videos, f, ensure_ascii=False)

        study_worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "study_worker.py")
        cmd = [sys.executable, study_worker_script, params_file, status_file, videos_file]

        study_log = os.path.join(task_dir, "study_worker.log")
        log_fh = open(study_log, "w", encoding="utf-8")

        current_pid = os.getpid()
        send_status(status_file, phase="study_running", heavy_done=True, study_pid=current_pid,
                    video_done=0, video_total=len(all_videos),
                    message=f"开始刷视频 (共{len(all_videos)}个)")

        logger.info("启动视频刷课子进程...")
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        try:
            proc = subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT,
                                    cwd=os.path.dirname(os.path.abspath(__file__)))
            send_status(status_file, study_pid=proc.pid)
            proc.wait()
            logger.info("视频刷课子进程退出，returncode={}", proc.returncode)
            if proc.returncode != 0:
                video_success = False
                logger.warning("视频刷课子进程异常退出")
        except Exception as e:
            logger.error("视频刷课子进程启动失败: {}", e)
            video_success = False
        finally:
            log_fh.close()

    # ── 第二阶段：考试/作业（视频完成后再执行） ──
    exam_success = True
    exam_errors = []
    if job_type in ("exam", "full", "all") and all_exams:
        send_status(status_file, phase="exam", message=f"视频完成，开始考试 (共{len(all_exams)}个)")
        try:
            from services.ai_service import AIService
            ai = AIService(session, website_id)
            for i, exam in enumerate(all_exams):
                if _shutdown_requested:
                    logger.info("收到退出信号，中断考试")
                    exam_errors.append("收到退出信号")
                    exam_success = False
                    break
                try:
                    send_status(status_file, phase="exam",
                                message=f"考试 {i+1}/{len(all_exams)}: {exam.get('name', '')}")
                    result = ai.solve_exam(
                        work_id=exam["work_id"],
                        course_id=exam.get("course_id"),
                        node_id=exam.get("node_id"),
                    )
                    if result.get("success"):
                        logger.info("考试完成: {} (提交{}题)", exam.get("name", ""), result.get("submitted", 0))
                    else:
                        err_msg = result.get("error", "未知错误")
                        if "已不存在" in err_msg or "已被删除" in err_msg or "可能已被删除" in err_msg:
                            logger.info("考试已删除，跳过: {}", exam.get("name", ""))
                        else:
                            logger.error("考试失败: {} - {}", exam.get("name", ""), err_msg)
                            exam_errors.append(f"{exam.get('name', '')}: {err_msg}")
                            exam_success = False
                except Exception as e:
                    err_str = str(e)
                    if "已不存在" in err_str or "已被删除" in err_str or "可能已被删除" in err_str:
                        logger.info("考试已删除，跳过: {}", exam.get("name", ""))
                    else:
                        logger.error("考试异常: {} - {}", exam.get("name", ""), e)
                        exam_errors.append(f"{exam.get('name', '')}: {err_str}")
                        exam_success = False
        except ImportError:
            logger.warning("AIService 不可用，跳过考试")

    # ── 全部完成 ──
    if video_success and exam_success:
        send_status(status_file, phase="done", done=True, success=True, message="任务完成")
    else:
        msg = []
        if not video_success:
            msg.append("视频部分失败")
        if not exam_success:
            msg.append("考试部分失败")
        full_msg = "，".join(msg)
        if exam_errors:
            full_msg += ": " + "; ".join(exam_errors[:3])
        send_status(status_file, phase="done", done=True, success=False, message=full_msg)
    logger.info("任务完成 video={} exam={}", video_success, exam_success)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python worker.py <params_file> <status_file>")
        sys.exit(1)

    def handle_signal(signum, frame):
        global _shutdown_requested
        _shutdown_requested = True
        logger.info("收到信号 {}，标记退出", signum)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        run_task(sys.argv[1], sys.argv[2])
    except Exception as e:
        logger.error("任务异常: {}\n{}", e, traceback.format_exc())
        try:
            send_status(sys.argv[2], phase="error", message=f"任务异常: {e}", done=True, success=False)
        except Exception as e:
            pass
        sys.exit(1)
    finally:
        # 确保退出前 status.json 有终态
        try:
            sf = sys.argv[2]
            if os.path.exists(sf):
                with open(sf) as f:
                    data = json.load(f)
                if not data.get("done") and data.get("phase") != "error":
                    send_status(sf, phase="error", message="进程异常退出（被kill或OOM）",
                                done=True, success=False)
        except Exception as e:
            pass

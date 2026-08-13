import json
import os
import signal
import sys
import time
import traceback

from loguru import logger

from config import validate_settings

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())


_shutdown_requested = False

from worker_common import ensure_terminal_status, send_status


def _apply_proxy(session):
    from worker_common import apply_proxy
    apply_proxy(session)


def _is_project_work(session, base_url, exam) -> bool:
    """检测作业是否为项目提交题（简答+文件上传）"""
    # 快速检查：名称包含项目相关关键词
    name = exam.get("name", "")
    topic_number = exam.get("topic_number", "")
    if topic_number == "1" and any(kw in name for kw in ("项目", "提交", "设计", "系统")):
        return True

    # 检查 topic_number
    try:
        if int(topic_number) > 1:
            return False
    except (ValueError, TypeError):
        pass

    # 访问 work 页面检测是否有文件上传按钮
    try:
        work_id = exam.get("work_id", "")
        node_id = exam.get("node_id", "")
        if not work_id or not node_id:
            return False
        resp = session.get(
            f"{base_url}/user/work",
            params={"workId": work_id, "nodeId": node_id},
            timeout=10,
            follow_redirects=True,
        )
        return 'uploader-btn' in resp.text
    except Exception:
        return False


def load_session(username, password, website_id):
    from infrastructure.http_session import create_sync_client

    from config import WEBSITES, get_account_cookies_path, set_current_website, update_url_config
    from services.multi_platform_auth import (
        check_platform_cookie_valid,
        login_single_platform,
        save_platform_cookie,
    )

    set_current_website(website_id)
    update_url_config()

    base_url = WEBSITES.get(website_id, {}).get("base_url", "")

    # 所有平台统一逻辑：先尝试缓存 Cookie，失效再重新登录
    cookie_file = get_account_cookies_path(username, WEBSITES.get(website_id, {}).get("name"))
    if os.path.exists(cookie_file):
        session = create_sync_client(base_url)
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

    from config import init_worker_context
    init_worker_context(params)

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

    from infrastructure.school.course_crawler import get_courses_with_diag
    from services.scan_service import load_course_cache, scan_course

    diag = get_courses_with_diag(session)
    courses = diag["courses"]
    logger.info("获取到 {} 门课程 (http={}, err={})", len(courses), diag.get("http_code"), diag.get("error"))

    # Cookie 过期 → 删除缓存，重新登录，验证 session 有效才继续
    if not courses and diag.get("error") and ("失效" in diag["error"] or "登录" in diag["error"]):
        logger.info("Cookie 过期，尝试重新登录...")
        send_status(status_file, phase="crawl", message="Cookie过期，重新登录中...")
        try:
            from config import get_account_cookies_path, WEBSITES
            from services.multi_platform_auth import login_single_platform, save_platform_cookie
            cookie_file = get_account_cookies_path(username, WEBSITES.get(website_id, {}).get("name"))
            if os.path.exists(cookie_file):
                os.remove(cookie_file)

            # 直接调用登录，不用 load_session（避免用了坏缓存）
            wid, ok, new_session, msg = login_single_platform(website_id, username, password)
            if not ok:
                logger.error("重新登录失败: {}", msg)
                diag["error"] = f"重新登录失败: {msg}"
            else:
                # 立即验证新 session 能否获取课程
                diag2 = get_courses_with_diag(new_session)
                if diag2["courses"]:
                    # 新 session 有效，保存 cookie 并继续
                    session = new_session
                    courses = diag2["courses"]
                    save_platform_cookie(username, website_id, session)
                    logger.info("重新登录成功，获取到 {} 门课程", len(courses))
                else:
                    # 新 session 也不能用，报告具体原因
                    logger.error("重新登录后仍无法获取课程: {}", diag2.get("error"))
                    diag["error"] = diag2.get("error") or "重新登录后仍无法获取课程"
        except Exception as e:
            logger.error("重新登录异常: {}", e)

    if not courses:
        err_msg = diag.get("error") or "未知原因"
        send_status(status_file, phase="error", message=err_msg, done=True, success=False)
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
        videos_from_cache = False
        if cached:
            send_status(status_file, phase="crawl", message=f"缓存命中 {i+1}/{len(courses)}: {cname}")
            logger.info("课程缓存命中: {} (id={})", cname, cid)
            all_videos.extend(cached.get("videos", []))
            videos_from_cache = True
            cached_exams = cached.get("exams", []) + cached.get("works", [])
            non_done_exams = [e for e in cached_exams if not e.get("is_done") and not e.get("is_deleted") and e.get("time_status", "进行中") == "进行中"]
            skipped = len([e for e in cached_exams if not e.get("is_done") and not e.get("is_deleted")]) - len(non_done_exams)
            if non_done_exams:
                all_exams.extend(non_done_exams)
                logger.info("  缓存考试: {} 个可考, {} 个未到/已过期", len(non_done_exams), skipped)
            else:
                logger.info("  缓存无可用考试数据，将实时获取")
                cached = None  # 回退到实时扫描（仅重新获取考试，视频已从缓存加载）

        if not cached:
            send_status(status_file, phase="crawl", message=f"解析课程 {i+1}/{len(courses)}: {cname}")
            logger.info("处理课程: {} (id={})", cname, cid)

            try:
                result = scan_course(session, cid, cname)
                if not videos_from_cache:
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

        study_params = {
            "base_url": base_url,
            "cookie_str": cookie_str,
            "username": username,
            "password": password,
        }
        params.update(study_params)
        with open(params_file, "w", encoding="utf-8") as f:
            json.dump(params, f, ensure_ascii=False)

        current_pid = os.getpid()
        send_status(status_file, phase="study_running", heavy_done=True, study_pid=current_pid,
                    video_done=0, video_total=len(all_videos),
                    message=f"开始刷视频 (共{len(all_videos)}个)")

        # ── 优先走 Rust 刷课守护进程（单进程多并发，内存 ~1-2MB/任务）──
        daemon_ok = False
        from config import settings
        if settings.rust_daemon_url:
            try:
                import urllib.request
                cookies_list = [{"name": k.strip(), "value": v.strip()}
                                for pair in cookie_str.split(";") if "=" in pair
                                for k, v in [pair.split("=", 1)]]
                payload = json.dumps({
                    "order_id": params.get("order_id", os.path.basename(task_dir)),
                    "username": username,
                    "password": password,
                    "base_url": base_url,
                    "cookies": cookies_list,
                    "videos": all_videos,
                    "status_file": status_file,
                    "push_ws": True,
                    "ocr_url": f"{settings.site_url.rstrip('/')}/api/internal/ocr",
                    "relogin_url": f"{settings.site_url.rstrip('/')}/api/internal/relogin",
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"{settings.rust_daemon_url}/submit", data=payload,
                    headers={"Content-Type": "application/json"}, method="POST")
                resp = json.loads(urllib.request.urlopen(req, timeout=5).read())
                if resp.get("ok"):
                    daemon_ok = True
                    send_status(status_file, study_pid=0)
                    logger.info("Rust 守护进程接手刷课 order_id={}", params.get("order_id", ""))
                    # 等待 daemon 写完终态（视频完成后 worker 才进入考试阶段）
                    total_dur = sum(v.get("duration", 0) for v in all_videos)
                    timeout_sec = max(600, total_dur * 2.5 + 120)
                    waited = 0
                    while waited < timeout_sec:
                        time.sleep(3)
                        waited += 3
                        try:
                            with open(status_file, encoding="utf-8") as f:
                                st = json.load(f)
                            if st.get("done"):
                                video_success = st.get("success", False)
                                if not video_success:
                                    logger.warning("Rust daemon 刷课失败: {}", st.get("message", ""))
                                break
                        except Exception:
                            continue
                    else:
                        video_success = False
                        logger.error("Rust daemon 刷课超时")
            except Exception as e:
                logger.warning("Rust 守护进程不可用，回退 Python 子进程: {}", e)

        if not daemon_ok:
            # 无 Python 回退：daemon 不可用则视频阶段明确失败（考试阶段仍继续）
            video_success = False
            send_status(status_file, phase="video",
                        message="Rust 刷课守护进程不可用，视频阶段失败",
                        video_pct=0)
            logger.error("Rust 刷课守护进程不可用，视频阶段失败（无 Python 回退）")

    # ── 第二阶段：考试/作业（视频完成后再执行） ──
    # 重新扫描考试列表（平台可能在刷视频期间更换了考试）
    if job_type in ("exam", "full", "all"):
        fresh_exams = []
        for course in courses:
            cid = course.get("course_id", "")
            if course_ids and cid not in course_ids:
                continue
            cname = course.get("name", "")
            try:
                result = scan_course(session, cid, cname)
                exams_works = result.get("exams", []) + result.get("works", [])
                non_done = [e for e in exams_works if not e.get("is_done") and not e.get("is_deleted") and e.get("time_status", "进行中") == "进行中"]
                fresh_exams.extend(non_done)
                logger.info("重新扫描 {}: 可做考试/作业={} 个", cname, len(non_done))
            except Exception as e:
                logger.warning("重新扫描 {} 失败: {}", cname, e)
        if fresh_exams:
            all_exams = fresh_exams
            logger.info("考试列表已更新: {} 个可做", len(all_exams))

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

                    # 检测是否为项目提交题（简答+文件上传）
                    is_project = _is_project_work(session, base_url, exam)

                    if is_project:
                        logger.info("检测到项目提交题: {}", exam.get("name", ""))
                        result = ai.solve_project_work(
                            work_id=int(exam["work_id"]),
                            course_id=int(exam.get("course_id", 0)),
                            node_id=int(exam.get("node_id", 0)),
                            question_text=exam.get("name", ""),
                            student_id=username,
                            student_name=exam.get("student_name", ""),
                        )
                    else:
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
    validate_settings()
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
        # 确保退出前 status.json 有终态（worker_common 统一实现）
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

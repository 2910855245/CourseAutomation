import sys
import os
import json
import time
import random
import threading
import signal
import traceback
from loguru import logger

from config import validate_settings


_ocr_instance = None

def _get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        import ddddocr
        _ocr_instance = ddddocr.DdddOcr(show_ad=False)
    return _ocr_instance


from worker_common import ensure_terminal_status, send_status


def run(params_file, status_file, videos_file):
    with open(params_file, "r", encoding="utf-8") as f:
        params = json.load(f)
    with open(videos_file, "r", encoding="utf-8") as f:
        videos = json.load(f)

    base_url = params["base_url"]
    cookie_str = params["cookie_str"]
    username = params.get("username", "")
    password = params.get("password", "")

    LightStudyReporter._shared_username = username
    LightStudyReporter._shared_password = password
    LightStudyReporter._shared_cookie_str = cookie_str

    # 断点续传：加载检查点，只跳过真正刷完的视频
    checkpoint_file = os.path.join(os.path.dirname(status_file), "checkpoint.json")
    checkpoint = _load_checkpoint(checkpoint_file)
    node_details = checkpoint.get("node_details", {})
    completed_nodes = set()

    # 只跳过 confirmed 完成的视频（有详细记录且 completed=True）
    skip_count = 0
    filtered_videos = []
    for v in videos:
        nid = v.get("node_id", "")
        detail = node_details.get(nid)
        if detail and detail.get("completed"):
            skip_count += 1
            completed_nodes.add(nid)
        else:
            filtered_videos.append(v)
    if skip_count:
        videos = filtered_videos
        logger.info(f"[checkpoint] 已跳过 {skip_count} 个确认完成的视频，剩余 {len(videos)} 个")
    if not videos:
        logger.info("[checkpoint] 所有视频已完成，无需处理")
        send_status(status_file, push_ws=True, phase="done", done=True, success=True, video_pct=100,
                    message="所有视频已完成（断点续传）")
        return

    if not videos:
        logger.info("[checkpoint] 所有视频已完成，无需处理")
        send_status(status_file, push_ws=True, phase="done", done=True, success=True, video_pct=100,
                    message="所有视频已完成（断点续传）")
        return

    send_status(status_file, push_ws=True, phase="video", video_done=0, video_total=len(videos),
                message=f"开始刷视频 (共{len(videos)}个)")

    import requests as _req

    def _make_session():
        s = _req.Session()
        s.verify = False
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-Requested-With': 'XMLHttpRequest'
        })
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api', 'services'))
            from proxy_config import get_proxy_config
            cfg = get_proxy_config()
            if cfg["enabled"]:
                s.proxies.update(cfg["proxies"])
        except Exception:
            pass
        return s

    heartbeat = LightHeartbeat(base_url, cookie_str, shared_session=_make_session())
    heartbeat.start()

    # 启动时立即检查cookie有效性
    if username and password:
        try:
            _test_s = _make_session()
            for pair in cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    _test_s.cookies.set(k.strip(), v.strip())
            _test_r = _test_s.get(f"{base_url}/user/index", timeout=10, allow_redirects=False)
            if _test_r.status_code in (302, 401, 403):
                logger.warning("[cookie] 启动时cookie已过期，尝试重新登录")
                _tmp = LightStudyReporter(base_url, "", cookie_str, 0, 0, "", "", _make_session())
                if _tmp._do_relogin():
                    cookie_str = LightStudyReporter._shared_cookie_str
                    heartbeat._set_cookie(cookie_str)
                    logger.info("[cookie] 启动时重新登录成功")
                else:
                    logger.error("[cookie] 启动时重新登录失败")
        except Exception as e:
            logger.debug("[cookie] 启动检查异常: %s", e)

    # 按课程分组：课程内串行，课程间并发
    from collections import defaultdict
    course_groups = defaultdict(list)
    for v in videos:
        cid = v.get("course_id", "") or "unknown"
        course_groups[cid].append(v)

    logger.info("视频分组: %d 个课程, 共 %d 个视频", len(course_groups), len(videos))

    # 共享进度追踪
    progress_lock = threading.Lock()
    all_reporters = []  # 所有 reporter 实例，用于最终统计

    def _run_course_videos(cid, course_videos):
        """单个课程内的视频：每隔0.5秒启动一个，HTTP请求由全局限速器串行化"""
        logger.info("[course-%s] 开始处理 %d 个视频", cid, len(course_videos))
        course_reporters = []
        for i, v in enumerate(course_videos):
            r = LightStudyReporter(
                base_url=base_url,
                node_id=v["node_id"],
                cookie_str=cookie_str,
                video_duration=v["duration"],
                viewed_duration=v.get("viewed_duration", 0),
                course_name=v.get("course_name", ""),
                video_name=v.get("name", ""),
                shared_session=_make_session(),
            )
            with progress_lock:
                all_reporters.append(r)
                course_reporters.append(r)
            r.start()
            time.sleep(LightStudyReporter._request_spacing)
        logger.info("[course-%s] 已启动全部 %d 个视频", cid, len(course_videos))
        # 等待本课程所有视频完成
        while any(r.is_alive for r in course_reporters):
            time.sleep(5)
        done = sum(1 for r in course_reporters if r.completed)
        logger.info("[course-%s] 课程处理完毕: 成功=%d/%d", cid, done, len(course_videos))

    # 每个课程启动一个线程，课程内串行
    course_threads = []
    for cid, group_videos in course_groups.items():
        t = threading.Thread(
            target=_run_course_videos,
            args=(cid, group_videos),
            daemon=True,
            name=f"course-{cid}",
        )
        t.start()
        course_threads.append(t)
        time.sleep(0.5)  # 课程间启动间隔

    logger.info("已启动 %d 个课程线程（共 %d 个视频）", len(course_threads), len(videos))

    # Cookie续期：定期检查cookie有效性，过期则重新登录
    last_cookie_check = time.time()
    _cookie_refresh_count = 0

    def _refresh_cookie_if_expired():
        nonlocal cookie_str, _cookie_refresh_count
        if not username or not password:
            return
        try:
            test_session = _make_session()
            # 解析cookie字符串
            for pair in cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    test_session.cookies.set(k.strip(), v.strip())
            resp = test_session.get(f"{base_url}/user/index", timeout=10, allow_redirects=False)
            if resp.status_code in (302, 401, 403):
                logger.warning("[cookie] cookie已过期，尝试重新登录 (第%d次)", _cookie_refresh_count + 1)
                # 创建临时LightStudyReporter实例调用_do_relogin
                tmp = LightStudyReporter(base_url, "", cookie_str, 0, 0, "", "", _make_session())
                if tmp._do_relogin():
                    cookie_str = LightStudyReporter._shared_cookie_str
                    _cookie_refresh_count += 1
                    # 更新所有正在运行的reporter和heartbeat的cookie
                    new_cookie = LightStudyReporter._shared_cookie_str
                    with progress_lock:
                        for r in all_reporters:
                            if r.is_alive:
                                r._set_cookie(new_cookie)
                    heartbeat._set_cookie(new_cookie)
                    logger.info("[cookie] 重新登录成功，已更新cookie（含所有活跃线程）")
                else:
                    logger.error("[cookie] 重新登录失败")
        except Exception as e:
            logger.debug("[cookie] 检查异常: %s", e)

    # 进度监控：等待所有课程线程结束
    last_checkpoint_save = time.time()
    while True:
        time.sleep(5)
        # 每30分钟检查一次cookie有效性
        if time.time() - last_cookie_check > 1800:
            last_cookie_check = time.time()
            _refresh_cookie_if_expired()
        alive_count = sum(1 for t in course_threads if t.is_alive())
        with progress_lock:
            done = sum(1 for r in all_reporters if not r.is_alive)
            total_study = sum(min(r.total_time, r.video_duration) for r in all_reporters)
            total_dur = sum(r.video_duration for r in all_reporters)

        # 每60秒保存一次检查点
        if time.time() - last_checkpoint_save > 60:
            node_details = checkpoint.get("node_details", {})
            for r in all_reporters:
                nid = r.node_id
                if not nid:
                    continue
                node_details[nid] = {
                    "duration": r.video_duration,
                    "watched": min(r.total_time, r.video_duration),
                    "completed": r.completed,
                }
                if r.completed:
                    completed_nodes.add(nid)
            checkpoint["node_details"] = node_details
            checkpoint["completed_nodes"] = list(completed_nodes)
            checkpoint["progress"] = {
                "done": done,
                "total": len(videos),
                "pct": int(total_study / total_dur * 100) if total_dur > 0 else 0
            }
            _save_checkpoint(checkpoint_file, checkpoint)
            last_checkpoint_save = time.time()

        pct = int(total_study / total_dur * 100) if total_dur > 0 else 0
        send_status(status_file, push_ws=True, phase="video", video_done=done, video_total=len(videos),
                    video_pct=pct, total_study_time=total_study, total_duration=total_dur,
                    message=f"刷视频中 {done}/{len(videos)} ({pct}%) 课程线程活跃:{alive_count}")

        if alive_count == 0:
            break

    completed_count = sum(1 for r in all_reporters if r.completed)
    error_count = len(all_reporters) - completed_count
    logger.info("上报线程结束: 成功=%d 异常=%d 总计=%d", completed_count, error_count, len(all_reporters))

    if error_count > 0:
        for r in all_reporters:
            if not r.completed:
                logger.warning("[异常] %s: %s", r.video_name, r.error_msg or "未完成")

    heartbeat.stop()

    _verify_session = _make_session()
    for item in cookie_str.split(';'):
        if '=' in item:
            k, v = item.strip().split('=', 1)
            _verify_session.cookies.set(k, v)
    actual_pct = _verify_platform_progress(base_url, _verify_session, videos)
    logger.info("平台实际进度: %d%%", actual_pct)

    if actual_pct < 0:
        # 会话过期，无法验证，标记失败让任务重试
        send_status(status_file, push_ws=True, phase="done", done=True, success=False, video_pct=0,
                    message="会话已过期，无法验证平台进度，请重试")
        logger.error("会话过期，无法验证平台进度")
    elif actual_pct >= 100:
        send_status(status_file, push_ws=True, phase="done", done=True, success=True, video_pct=100,
                    message="任务完成")
        logger.info("所有视频学习完成")
    elif completed_count == len(all_reporters) and actual_pct < 95:
        send_status(status_file, push_ws=True, phase="done", done=True, success=False, video_pct=actual_pct,
                    message=f"上报完成但平台进度仅{actual_pct}%，可能被平台限制")
        logger.warning("上报完成但平台进度仅 %d%%", actual_pct)
    else:
        send_status(status_file, push_ws=True, phase="done", done=True, success=False, video_pct=actual_pct,
                    message=f"部分视频未完成 {completed_count}/{len(all_reporters)} 平台进度{actual_pct}%")
        logger.warning("部分视频未完成 平台进度 %d%%", actual_pct)


if __name__ == "__main__":
    validate_settings()
    if len(sys.argv) < 4:
        print("用法: python study_worker.py <params_file> <status_file> <videos_file>")
        sys.exit(1)

    def handle_signal(signum, frame):
        logger.info("收到信号 %d，退出", signum)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        run(sys.argv[1], sys.argv[2], sys.argv[3])
    except Exception as e:
        logger.error("异常: %s\n%s", e, traceback.format_exc())
        send_status(sys.argv[2], push_ws=True, phase="error", message=f"异常: {e}", done=True, success=False)
        sys.exit(1)

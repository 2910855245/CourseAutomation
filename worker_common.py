"""worker 三脚本共享样板：状态原子写、WS 推送、信号处理、退出兜底、代理应用。

三个 worker（worker/study_worker/chaoxing_worker）各自维护过一份 send_status 副本，
且语义漂移（原子写/终态清理/WS 推送各有缺失）。统一以最完善的版本为基准：
- 原子写：tmp + fsync + os.replace（修复 study_worker 半写问题）
- 非终态更新自动清除旧的 done/success（防止 TaskRunner 误判完成）
- push_ws 开关：worker.py 重阶段不推送，study/chaoxing 推送
"""

import json
import os
import sys
import time


def send_status(status_file: str, push_ws: bool = False, **kwargs) -> dict:
    """原子写 status.json，返回写入后的完整数据"""
    data = {}
    if os.path.exists(status_file):
        try:
            with open(status_file, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    # 非终态更新时清除旧终态标记，防止进度更新保留 done/success 导致误判
    if not kwargs.get("done"):
        data.pop("done", None)
        data.pop("success", None)
    data.update(kwargs)
    data["updated_at"] = time.time()
    tmp_file = status_file + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_file, status_file)
    if push_ws:
        push_ws_update(status_file, data)
    return data


def push_ws_update(status_file: str, data: dict):
    """POST 进度到 API 触发 WebSocket 广播。URL 从 site_url 推导（不再硬编码端口）。"""
    try:
        import urllib.request
        from config import settings
        push_url = settings.site_url.rstrip("/") + "/api/progress/live/push"
        payload = json.dumps({
            "type": "progress",
            "job_id": os.path.basename(os.path.dirname(status_file)),
            "phase": data.get("phase", ""),
            "progress": data.get("progress", 0),
            "step_name": data.get("step_name", ""),
            "course_name": data.get("course_name", ""),
            "done": data.get("done", False),
            "success": data.get("success", False),
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            push_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Worker-Token": os.environ.get("WORKER_TOKEN", ""),
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


def register_signal_handlers(on_signal):
    """SIGTERM/SIGINT → on_signal()（worker 内设置 _shutdown_requested）"""
    import signal

    def _handler(signum, frame):
        on_signal()

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


def ensure_terminal_status(status_file: str):
    """退出兜底：无终态时写入 error（进程被 kill/OOM 时也要留下终态）"""
    try:
        if not os.path.exists(status_file):
            return
        with open(status_file, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("done") or data.get("success"):
            return
        send_status(status_file, phase="error", message="进程异常退出",
                    done=True, success=False)
    except Exception:
        pass


def apply_proxy(session):
    """加载隧道代理配置并应用到 session（httpx/requests 通用）"""
    try:
        from services.proxy_config import get_proxy_config
        cfg = get_proxy_config()
        if cfg["enabled"]:
            session.proxies.update(cfg["proxies"])
            from loguru import logger
            logger.info("已启用隧道代理")
    except Exception:
        pass


def bootstrap_worker() -> dict:
    """worker 入口引导：chdir + sys.path + 解析 argv + 初始化进程上下文。

    返回 (params_file, status_file) 路径元组。
    """
    base = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base)
    sys.path.insert(0, base)

    from config import init_worker_context, validate_settings
    validate_settings()

    if len(sys.argv) < 3:
        print(f"用法: python {os.path.basename(sys.argv[0])} <params.json> <status.json>", file=sys.stderr)
        sys.exit(2)
    params_file, status_file = sys.argv[1], sys.argv[2]
    with open(params_file, encoding="utf-8") as f:
        params = json.load(f)
    init_worker_context(params)
    return params_file, status_file

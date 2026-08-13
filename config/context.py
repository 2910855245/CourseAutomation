"""平台上下文（contextvars 版）。

替代旧 config.py 的进程级全局可变状态（CURRENT_WEBSITE / _current_account / URL 快照），
解决多线程并发下"A 请求读到 B 用户的平台/路径"竞态：

- 每个线程/请求通过 ContextVar 持有自己的 website_id / account；
- 未设置时回退进程级默认值（由 init_process_context 从 global_config.json 恢复）；
- worker 子进程通过 init_worker_context(params) 从任务参数初始化，天然隔离。
"""

import json
import os
import threading
from contextvars import ContextVar

from loguru import logger

from config.platforms import WEBSITES

_website_ctx: ContextVar[int] = ContextVar("website_id", default=0)      # 0 = 未设置，回退进程默认
_account_ctx: ContextVar[str | None] = ContextVar("account", default=None)

_process_default_website: int = 1
_context_lock = threading.Lock()

GLOBAL_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "global_config", "global_config.json",
)


def get_website_id() -> int:
    return _website_ctx.get() or _process_default_website


def get_website_config() -> dict:
    return WEBSITES.get(get_website_id(), WEBSITES[1])


def get_base_url() -> str:
    return get_website_config()["base_url"]


def get_account_username() -> str | None:
    return _account_ctx.get()


def set_website_id(website_id: int):
    """切换当前网站（校验后写进程默认 + 当前线程上下文）。

    保持旧"管理端全局切换"语义：所有新线程继承新默认值；
    旧线程（请求处理中）继续用自己上下文里的旧值。
    """
    global _process_default_website
    if website_id not in WEBSITES:
        raise ValueError(f"无效的网站ID: {website_id}")
    with _context_lock:
        _process_default_website = website_id
    _website_ctx.set(website_id)


def set_account_username(username: str | None):
    _account_ctx.set(username)


def init_process_context():
    """进程启动时初始化：从 global_config.json 恢复默认网站，并写入当前线程上下文。

    必须在任何 daemon 线程 spawn 之前调用（线程继承创建时的 context）。
    """
    try:
        with open(GLOBAL_CONFIG_FILE, encoding="utf-8") as f:
            saved = json.load(f).get("last_website_id")
        if saved in WEBSITES:
            global _process_default_website
            with _context_lock:
                _process_default_website = saved
            _website_ctx.set(saved)
            logger.info(f"进程上下文初始化 website_id={saved}")
            return
    except Exception as e:
        logger.warning(f"进程上下文初始化失败，使用默认平台 error={str(e)}")
    _website_ctx.set(_process_default_website)


def init_worker_context(params: dict):
    """worker 子进程入口调用：从任务参数设置上下文（与 API 进程完全隔离）"""
    wid = params.get("website_id") or _process_default_website
    if wid not in WEBSITES:
        wid = 1
    _website_ctx.set(wid)
    _account_ctx.set(params.get("username"))
    return wid

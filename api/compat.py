"""Python 3.8 兼容层 — 补齐 3.9+ 标准库缺失的功能"""
from __future__ import annotations

import asyncio
import functools


async def to_thread(func, *args, **kwargs):
    """asyncio.to_thread 的 Python 3.8 兼容实现。

    Python 3.9+ 已内置 asyncio.to_thread，此函数在 3.8 上提供等价行为。
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, functools.partial(func, *args, **kwargs)
    )


# 如果标准库已有 to_thread 则直接用标准版本
to_thread_impl = getattr(asyncio, "to_thread", to_thread)

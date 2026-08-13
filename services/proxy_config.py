"""隧道代理配置加载，供 worker.py / study_worker.py 使用，支持多代理轮换"""
import json
import os
import random

from loguru import logger

_log = logger

PROXY_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "proxy.json")

# 代理池：支持多个代理轮换
_proxy_pool: list = []
_proxy_index: int = 0


def _build_proxy_url(cfg: dict) -> str:
    """从配置项构建代理URL"""
    url = cfg.get("url", "")
    username = cfg.get("username", "")
    password = cfg.get("password", "")
    if username:
        if "://" in url:
            scheme, rest = url.split("://", 1)
            url = f"{scheme}://{username}:{password}@{rest}"
        else:
            url = f"http://{username}:{password}@{url}"
    return url


def get_proxy_config() -> dict:
    """从 data/proxy.json 读取代理配置，返回 {enabled, proxies}"""
    result = {"enabled": False, "proxies": {}}
    try:
        if not os.path.exists(PROXY_JSON):
            return result
        with open(PROXY_JSON) as f:
            cfg = json.load(f)

        # 支持单代理模式（向后兼容）
        if cfg.get("enabled") and cfg.get("url"):
            url = _build_proxy_url(cfg)
            result["enabled"] = True
            result["proxies"] = {"http": url, "https": url}
            _log.info("隧道代理已启用（单代理模式）", url=url[:60])
            return result

        # 支持多代理轮换模式
        if cfg.get("enabled") and cfg.get("proxies"):
            global _proxy_pool
            _proxy_pool = []
            for p in cfg["proxies"]:
                if isinstance(p, dict) and p.get("url"):
                    _proxy_pool.append(_build_proxy_url(p))
                elif isinstance(p, str):
                    _proxy_pool.append(p)

            if _proxy_pool:
                result["enabled"] = True
                result["proxies"] = {"http": _proxy_pool[0], "https": _proxy_pool[0]}
                _log.info("多代理轮换模式已启用", proxy_count=len(_proxy_pool))
    except Exception as e:
        _log.error("代理配置加载失败", error=str(e))
    return result


def get_next_proxy() -> dict:
    """获取下一个代理（轮换模式）"""
    global _proxy_index
    if not _proxy_pool:
        return get_proxy_config()

    url = _proxy_pool[_proxy_index % len(_proxy_pool)]
    _proxy_index += 1
    # 随机打乱顺序实现随机轮换
    if _proxy_index >= len(_proxy_pool):
        random.shuffle(_proxy_pool)
        _proxy_index = 0

    return {"enabled": True, "proxies": {"http": url, "https": url}}


def get_random_proxy() -> dict:
    """获取随机代理"""
    if not _proxy_pool:
        return get_proxy_config()

    url = random.choice(_proxy_pool)
    return {"enabled": True, "proxies": {"http": url, "https": url}}

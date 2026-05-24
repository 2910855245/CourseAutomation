from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime
from typing import Dict, List
from urllib.parse import urlparse

import httpx
from loguru import logger
from bs4 import BeautifulSoup


SCHOOL_URL = "https://www.cdcas.edu.cn/"

# 学校自有域名后缀，全部排除
SCHOOL_DOMAIN_SUFFIXES = (
    ".cdcas.edu.cn",
    ".cdcas.com",
    "cdcas.edu.cn",
    "cdcas.com",
    ".scedu.net",
    ".ihwrm.com",
    ".openai.chaoxing.com",
)

# 非课程平台域名，直接排除
EXCLUDED_DOMAINS = {
    "scnucas.com",          # 校长信箱
    "cdcas.fanruikji.com",  # 教师在线学习
}

# config keys
CONFIG_DOMAINS = "domain_monitor_known_domains"
CONFIG_LAST_CHECK = "domain_monitor_last_check"
CONFIG_LAST_CHANGE = "domain_monitor_last_change"
CONFIG_CHECK_INTERVAL = "domain_monitor_interval"

DEFAULT_INTERVAL = 3600  # 1小时

# JS 反作弊监控
CONFIG_JS_HASHES = "domain_monitor_js_hashes"
CONFIG_JS_LAST_CHECK = "domain_monitor_js_last_check"
CONFIG_JS_LAST_CHANGE = "domain_monitor_js_last_change"

# 告警历史
CONFIG_ALERTS = "domain_monitor_alerts"

# domain → website_id 映射
CONFIG_WEBSITE_MAP = "domain_monitor_website_map"

# 需要监控的 JS 文件路径（三个平台通用）
MONITORED_JS_FILES = [
    "/yeeui/yee.js",                          # 核心框架
    "/static/login/js/user.js",               # 登录逻辑
    "/static/home/js/course.js",              # 课程页面逻辑
    "/static/skin/js/sino.js",                # 页面逻辑
    "/static/common/js/browser.js",           # 浏览器检测
]


def _get_db():
    from api.database import db
    return db


def get_known_domains() -> Dict[str, dict]:
    """获取已知域名列表 {domain: {name, url, discovered_at}}"""
    db = _get_db()
    raw = db.config_get(CONFIG_DOMAINS)
    if raw:
        try:
            return json.loads(raw)
        except Exception as e:
            pass
    return {}


def save_known_domains(domains: Dict[str, dict]):
    db = _get_db()
    db.config_set(CONFIG_DOMAINS, json.dumps(domains, ensure_ascii=False))


def get_status() -> dict:
    db = _get_db()
    return {
        "known_domains": get_known_domains(),
        "last_check": db.config_get(CONFIG_LAST_CHECK) or "",
        "last_change": db.config_get(CONFIG_LAST_CHANGE) or "",
        "interval": int(db.config_get(CONFIG_CHECK_INTERVAL) or DEFAULT_INTERVAL),
        "school_url": SCHOOL_URL,
    }


def add_domain(domain: str, name: str, url: str) -> bool:
    """手动添加域名"""
    domains = get_known_domains()
    if domain not in domains:
        domains[domain] = {
            "name": name,
            "url": url,
            "discovered_at": datetime.now().isoformat(),
            "source": "manual",
        }
        save_known_domains(domains)
        _ensure_website_id(domain, name)
        logger.info(f"域名监听: 手动添加 domain={domain} name={name}")
        return True
    return False


def remove_domain(domain: str) -> bool:
    domains = get_known_domains()
    if domain in domains:
        del domains[domain]
        save_known_domains(domains)
        # 清理 website_id 映射
        mapping = _get_website_map()
        if domain in mapping:
            del mapping[domain]
            _save_website_map(mapping)
        return True
    return False


# ==================== JS 反作弊监控 ====================

def _get_all_monitor_domains() -> List[str]:
    """获取所有需要监控 JS 的平台域名"""
    known = get_known_domains()
    domains = [info["url"] for info in known.values() if info.get("url")]
    return domains


def get_js_hashes() -> Dict[str, str]:
    """获取所有已记录的 JS hash {full_url: md5}"""
    db = _get_db()
    raw = db.config_get(CONFIG_JS_HASHES)
    if raw:
        try:
            return json.loads(raw)
        except Exception as e:
            pass
    return {}


def save_js_hashes(hashes: Dict[str, str]):
    db = _get_db()
    db.config_set(CONFIG_JS_HASHES, json.dumps(hashes))


def check_js_changes() -> dict:
    """检查所有平台的关键 JS 文件是否有变更"""
    db = _get_db()
    result = {
        "checked_at": datetime.now().isoformat(),
        "changes": [],
        "errors": [],
        "files_checked": 0,
    }

    domains = _get_all_monitor_domains()
    old_hashes = get_js_hashes()
    new_hashes = dict(old_hashes)
    changed = False

    for base_url in domains:
        for js_path in MONITORED_JS_FILES:
            full_url = f"{base_url}{js_path}"
            result["files_checked"] += 1

            try:
                resp = httpx.get(full_url, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                if resp.status_code != 200:
                    continue

                content = resp.content
                md5_hash = hashlib.md5(content).hexdigest()

                if full_url in old_hashes:
                    if old_hashes[full_url] != md5_hash:
                        result["changes"].append({
                            "url": full_url,
                            "old_hash": old_hashes[full_url][:12],
                            "new_hash": md5_hash[:12],
                            "size": len(content),
                        })
                        changed = True
                        _record_alert("js_change", f"JS文件变更: {js_path} (hash {old_hashes[full_url][:8]}→{md5_hash[:8]})", base_url)
                        logger.warning(f"JS监控: 文件变更 url={full_url} old_hash={old_hashes[full_url][:12]} new_hash={md5_hash[:12]}")

                new_hashes[full_url] = md5_hash

            except Exception as e:
                result["errors"].append(f"{full_url}: {e}")

    save_js_hashes(new_hashes)
    db.config_set(CONFIG_JS_LAST_CHECK, result["checked_at"])

    if changed:
        db.config_set(CONFIG_JS_LAST_CHANGE, result["checked_at"])

    return result


def get_js_status() -> dict:
    """获取 JS 监控状态"""
    db = _get_db()
    hashes = get_js_hashes()
    domains = _get_all_monitor_domains()

    files = []
    for base_url in domains:
        for js_path in MONITORED_JS_FILES:
            full_url = f"{base_url}{js_path}"
            h = hashes.get(full_url, "")
            files.append({
                "url": full_url,
                "hash": h[:12] if h else "未记录",
            })

    return {
        "files": files,
        "total": len(files),
        "last_check": db.config_get(CONFIG_JS_LAST_CHECK) or "",
        "last_change": db.config_get(CONFIG_JS_LAST_CHANGE) or "",
    }


# ==================== 告警历史 ====================

def _record_alert(alert_type: str, message: str, domain: str = ""):
    """记录告警到 platform_settings"""
    db = _get_db()
    raw = db.config_get(CONFIG_ALERTS)
    alerts = []
    if raw:
        try:
            alerts = json.loads(raw)
        except Exception as e:
            pass
    alerts.insert(0, {
        "time": datetime.now().isoformat(),
        "type": alert_type,
        "message": message,
        "domain": domain,
    })
    # 只保留最近 200 条
    if len(alerts) > 200:
        alerts = alerts[:200]
    db.config_set(CONFIG_ALERTS, json.dumps(alerts, ensure_ascii=False))


def get_alerts(limit: int = 50) -> list:
    """获取告警历史"""
    db = _get_db()
    raw = db.config_get(CONFIG_ALERTS)
    if not raw:
        return []
    try:
        alerts = json.loads(raw)
        return alerts[:limit]
    except Exception as e:
        return []


def clear_alerts():
    """清除告警历史"""
    db = _get_db()
    db.config_set(CONFIG_ALERTS, "[]")


# ==================== 平台健康检测 ====================

def check_platform_health() -> dict:
    """检测所有已知平台的可达性"""
    known = get_known_domains()
    platforms = []
    for domain, info in known.items():
        url = info.get("url", f"https://{domain}")
        entry = {
            "domain": domain,
            "name": info.get("name", domain),
            "url": url,
            "reachable": False,
            "status_code": 0,
            "response_time_ms": 0,
            "error": "",
        }
        try:
            start = time.time()
            resp = httpx.get(url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }, follow_redirects=True)
            elapsed = int((time.time() - start) * 1000)
            entry["status_code"] = resp.status_code
            entry["response_time_ms"] = elapsed
            entry["reachable"] = resp.status_code < 500
        except httpx.ConnectTimeout:
            entry["error"] = "连接超时"
        except httpx.ConnectError:
            entry["error"] = "连接失败"
        except Exception as e:
            entry["error"] = str(e)[:80]
        platforms.append(entry)
    return {
        "checked_at": datetime.now().isoformat(),
        "platforms": platforms,
    }


# ==================== 平台统一数据源 ====================

def _get_website_map() -> Dict[str, int]:
    """读取 domain → website_id 映射"""
    db = _get_db()
    raw = db.config_get(CONFIG_WEBSITE_MAP)
    if raw:
        try:
            return json.loads(raw)
        except Exception as e:
            pass
    return {}


def _save_website_map(mapping: Dict[str, int]):
    db = _get_db()
    db.config_set(CONFIG_WEBSITE_MAP, json.dumps(mapping))


def _ensure_website_id(domain: str, name: str = "") -> int:
    """确保域名有对应的 website_id，没有则自动分配"""
    mapping = _get_website_map()

    if domain in mapping:
        return mapping[domain]

    # 尝试从 WEBSITES 匹配
    from config import WEBSITES
    for wid, winfo in WEBSITES.items():
        config_domain = winfo["base_url"].split("//")[-1].rstrip("/")
        if domain == config_domain:
            mapping[domain] = wid
            _save_website_map(mapping)
            return wid

    # 自动分配新 ID（从 WEBSITES 最大值 +1 开始）
    used_ids = set(mapping.values()) | set(WEBSITES.keys())
    new_id = max(used_ids) + 1 if used_ids else 1
    mapping[domain] = new_id
    _save_website_map(mapping)
    logger.info(f"平台检测: 自动分配 website_id domain={domain} name={name} id={new_id}")
    return new_id


def get_active_platforms() -> Dict[int, dict]:
    """获取所有活跃平台 — 统一数据源

    返回: {website_id: {name, base_url, domain, source}}
    如果 known_domains 为空，自动触发一次发现。
    """
    known = get_known_domains()

    if not known:
        logger.info("平台检测: known_domains 为空，执行首次发现")
        check_once()
        known = get_known_domains()

    result = {}
    for domain, info in known.items():
        wid = _ensure_website_id(domain, info.get("name", ""))
        result[wid] = {
            "name": info.get("name", domain),
            "base_url": info.get("url", f"https://{domain}"),
            "domain": domain,
            "source": info.get("source", "unknown"),
        }

    return result


def sync_from_school() -> dict:
    """手动触发从学校官网同步平台列表"""
    return check_once()


def _extract_platforms_from_html(html: str) -> List[dict]:
    """用 BeautifulSoup 从学校官网提取课程平台链接"""
    soup = BeautifulSoup(html, "lxml")
    platforms = []
    seen_domains = set()

    for a in soup.find_all("a", href=True):
        p_tag = a.find("p")
        if not p_tag:
            continue

        name = p_tag.get_text(strip=True)
        href = a["href"].strip()

        if not href or not href.startswith("http"):
            continue

        parsed = urlparse(href)
        domain = parsed.netloc.lower()

        if not domain or domain in seen_domains:
            continue

        # 排除学校自有域名后缀
        if any(domain.endswith(s) or domain == s for s in SCHOOL_DOMAIN_SUFFIXES):
            continue

        # 排除非课程平台
        if domain in EXCLUDED_DOMAINS:
            continue

        # 排除内网 IP
        if domain.startswith(("172.", "192.168.", "10.", "localhost", "127.")):
            continue

        # 排除端口号的内网地址
        if ":" in domain:
            continue

        # 排除明显不是课程平台的链接
        if not name or len(name) > 30:
            continue

        seen_domains.add(domain)
        platforms.append({
            "name": name,
            "domain": domain,
            "url": f"{parsed.scheme}://{domain}",
        })

    return platforms


def check_once() -> dict:
    """执行一次检查，返回结果"""
    db = _get_db()
    result = {
        "checked_at": datetime.now().isoformat(),
        "found": [],
        "new_domains": [],
        "changed_domains": [],
        "errors": [],
    }

    try:
        resp = httpx.get(SCHOOL_URL, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.encoding = resp.apparent_encoding
        resp.raise_for_status()
    except Exception as e:
        result["errors"].append(f"访问学校官网失败: {e}")
        logger.error(f"域名监听: 访问学校官网失败 error={str(e)}")
        return result

    platforms = _extract_platforms_from_html(resp.text)
    result["found"] = platforms

    known = get_known_domains()
    # 合并 config.py 中预配置的平台域名，避免重复报为"新发现"
    from config import WEBSITES
    for wid, winfo in WEBSITES.items():
        base_url = winfo.get("base_url", "")
        if base_url:
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            d = parsed.netloc.lower()
            if d:
                if d not in known:
                    known[d] = {
                        "name": winfo.get("name", ""),
                        "url": base_url,
                        "discovered_at": "preconfigured",
                        "source": "config",
                    }
                else:
                    # 已存在，强制同步 config 中的名字和标记
                    known[d]["source"] = "config"
                    known[d]["name"] = winfo.get("name", "")
    changed = False

    for p in platforms:
        domain = p["domain"]
        if domain not in known:
            # 新域名
            known[domain] = {
                "name": p["name"],
                "url": p["url"],
                "discovered_at": datetime.now().isoformat(),
                "source": "auto",
            }
            result["new_domains"].append(p)
            changed = True
            _ensure_website_id(domain, p["name"])
            _record_alert("new_domain", f"发现新平台: {p['name']} ({domain})", domain)
            logger.info("域名监听: 发现新平台 domain={} name={}", domain, p["name"])
        else:
            # 已知域名，检查名字是否变了（config 来源的不检查，以 config 为准）
            if known[domain].get("source") != "config":
                old_name = known[domain].get("name", "")
                if old_name and old_name != p["name"]:
                    result["changed_domains"].append({
                        "domain": domain,
                        "old_name": old_name,
                        "new_name": p["name"],
                    })
                    known[domain]["name"] = p["name"]
                    changed = True
                    _record_alert("name_change", f"平台名变更: {old_name} → {p['name']}", domain)
                    logger.info("域名监听: 平台名变更 domain={} old={} new={}", domain, old_name, p["name"])

    save_known_domains(known)
    db.config_set(CONFIG_LAST_CHECK, result["checked_at"])

    if changed:
        db.config_set(CONFIG_LAST_CHANGE, result["checked_at"])

    return result


def _monitor_loop():
    """后台定时检查循环"""
    time.sleep(30)  # 启动后等30秒再开始
    logger.info(f"平台监控服务启动 school_url={SCHOOL_URL}")

    while True:
        try:
            db = _get_db()
            interval = int(db.config_get(CONFIG_CHECK_INTERVAL) or DEFAULT_INTERVAL)

            # 1. 域名监听
            result = check_once()
            if result["new_domains"] or result["changed_domains"]:
                logger.warning("域名监听: 检测到变更",
                               new=[d["domain"] for d in result["new_domains"]],
                               changed=[d["domain"] for d in result["changed_domains"]])

            # 2. JS 反作弊监控
            js_result = check_js_changes()
            if js_result["changes"]:
                logger.warning("JS监控: 检测到文件变更",
                               changes=[c["url"] for c in js_result["changes"]])

        except Exception as e:
            logger.error(f"监控循环异常 error={str(e)}")

        time.sleep(interval)


_monitor_thread = None


def start_domain_monitor():
    global _monitor_thread
    if _monitor_thread and _monitor_thread.is_alive():
        return
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True, name="domain-monitor")
    _monitor_thread.start()
    logger.info("域名监听定时服务已注册")

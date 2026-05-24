"""平台发现模块 — 从学校官网自动获取课程平台链接"""

from typing import Dict, List
from urllib.parse import urlparse

import httpx
from loguru import logger
from bs4 import BeautifulSoup


SCHOOL_URL = "https://www.cdcas.edu.cn/"

# 学校自有域名后缀，排除
SCHOOL_DOMAIN_SUFFIXES = (
    ".cdcas.edu.cn",
    ".cdcas.com",
    "cdcas.edu.cn",
    "cdcas.com",
    ".scedu.net",
    ".ihwrm.com",
    ".openai.chaoxing.com",
)

# 非课程平台域名，排除
EXCLUDED_DOMAINS = {
    "scnucas.com",
    "cdcas.fanruikji.com",
}


def discover_platforms(school_url: str = SCHOOL_URL,
                       timeout: int = 15) -> List[Dict[str, str]]:
    """从学校官网获取课程平台列表

    返回: [{name, domain, base_url}, ...]
    """
    try:
        resp = httpx.get(school_url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.encoding = resp.apparent_encoding
        resp.raise_for_status()
    except Exception as e:
        logger.error("访问学校官网失败: {}", e)
        return []

    return _extract_platforms(resp.text)


def _extract_platforms(html: str) -> List[Dict[str, str]]:
    """从 HTML 提取课程平台链接"""
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

        if any(domain.endswith(s) or domain == s for s in SCHOOL_DOMAIN_SUFFIXES):
            continue

        if domain in EXCLUDED_DOMAINS:
            continue

        if domain.startswith(("172.", "192.168.", "10.", "localhost", "127.")):
            continue

        if ":" in domain:
            continue

        if not name or len(name) > 30:
            continue

        seen_domains.add(domain)
        platforms.append({
            "name": name,
            "domain": domain,
            "base_url": f"{parsed.scheme}://{domain}",
        })

    return platforms


def discover_as_websites(school_url: str = SCHOOL_URL) -> Dict[int, Dict]:
    """获取平台列表并转为 WEBSITES 格式 {id: {name, base_url}}"""
    platforms = discover_platforms(school_url)
    return {
        i + 1: {"name": p["name"], "base_url": p["base_url"]}
        for i, p in enumerate(platforms)
    }

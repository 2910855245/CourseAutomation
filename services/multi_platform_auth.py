"""
多平台认证服务
功能：高并发登录所有网站，保存Cookie到对应文件
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Tuple

import httpx
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import DATA_DIR, WEBSITES, get_account_cookies_path
from infrastructure.http_session import create_sync_client, get_dynamic_headers

# schoolId 缓存文件（按平台缓存，同一子域名下所有用户共享）
_SCHOOL_ID_CACHE_FILE = os.path.join(DATA_DIR, "global_config", "school_id_cache.json")

def _load_school_id_cache() -> dict:
    if os.path.exists(_SCHOOL_ID_CACHE_FILE):
        try:
            with open(_SCHOOL_ID_CACHE_FILE, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            pass
    return {}

def _save_school_id_cache(cache: dict):
    os.makedirs(os.path.dirname(_SCHOOL_ID_CACHE_FILE), exist_ok=True)
    with open(_SCHOOL_ID_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)

def _extract_school_ids(login_html: str):
    """从登录页提取 schoolId 选项列表，无则返回 None"""
    m = re.search(r'<select[^>]*id="schoolId"[^>]*>(.*?)</select>', login_html, re.DOTALL)
    if not m:
        return None
    options = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>', m.group(1))
    return [v for v in options if v]

_ocr_instance = None

def _get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        import ddddocr
        _ocr_instance = ddddocr.DdddOcr(show_ad=False)
    return _ocr_instance


def get_website_base_url(website_id: int) -> str:
    """动态获取网站基础URL"""
    website = WEBSITES.get(website_id)
    if website:
        return website["base_url"]
    return ""


def login_single_platform(website_id: int, username: str, password: str) -> Tuple[int, bool, httpx.Client, str]:
    """
    登录单个平台

    Returns:
        (website_id, success, session, message)
    """
    website = WEBSITES.get(website_id)
    if not website:
        return website_id, False, None, f"网站ID {website_id} 不存在"

    base_url = website["base_url"]
    login_url = f"{base_url}/user/login"
    captcha_url = f"{base_url}/service/code"

    session = create_sync_client(base_url)
    ocr = _get_ocr()
    max_retries = 10
    retry = 0

    # 检查该平台是否需要 schoolId
    school_ids = None
    cached_school_id = None
    school_id_index = 0
    try:
        login_headers = get_dynamic_headers()
        login_headers["Referer"] = login_url
        pre_check = session.get(login_url, headers=login_headers, timeout=15)
        school_ids = _extract_school_ids(pre_check.text)
        if school_ids:
            cache = _load_school_id_cache()
            cached_school_id = cache.get(str(website_id), "")
            if cached_school_id and cached_school_id in school_ids:
                school_id_index = school_ids.index(cached_school_id)
    except Exception as e:
        pass

    while retry < max_retries:
        retry += 1
        try:
            login_headers = get_dynamic_headers()
            login_headers["Referer"] = login_url
            session.get(login_url, headers=login_headers, timeout=15)

            captcha_headers = get_dynamic_headers(login_url)
            captcha_headers["Referer"] = login_url
            captcha_resp = session.get(captcha_url, headers=captcha_headers, timeout=15)
            code = ocr.classification(captcha_resp.content)

            data = {
                "username": username,
                "password": password,
                "code": code,
                "redirect": "",
                "remember": "on"
            }
            if school_ids and school_id_index < len(school_ids):
                data["schoolId"] = school_ids[school_id_index]

            result = session.post(login_url, data=data, headers=login_headers, follow_redirects=False, timeout=15)
            text = result.text

            if "验证码有误" in text:
                continue

            if "<title>操作成功提示</title>" in text or '"status":true' in text:
                # 登录成功，缓存 schoolId
                if school_ids and school_id_index < len(school_ids):
                    cache = _load_school_id_cache()
                    cache[str(website_id)] = school_ids[school_id_index]
                    _save_school_id_cache(cache)
                # 跟随重定向获取完整Cookie
                if result.status_code == 302:
                    redirect_url = result.headers.get('Location', '')
                    if redirect_url:
                        if not redirect_url.startswith('http'):
                            redirect_url = base_url + redirect_url
                        session.get(redirect_url, headers=login_headers, timeout=15)
                return website_id, True, session, "登录成功"

            if "<title>错误提示</title>" in text:
                detail = ""
                match = re.search(r'<div class="name">(.*?)</div>', text, re.DOTALL)
                if match:
                    detail = match.group(1).strip()
                if not detail:
                    match = re.search(r'<div class="errormain"[^>]*>(.*?)</div>', text, re.DOTALL)
                    if match:
                        detail = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                if not detail:
                    match = re.search(r'<h2[^>]*>(.*?)</h2>', text, re.DOTALL)
                    if match:
                        detail = match.group(1).strip()

                if "密码不可为空" in text:
                    return website_id, False, None, "密码不能为空"
                elif "学生学号不可为空" in text:
                    return website_id, False, None, "学号不能为空"

                # 如果该平台需要 schoolId 且还有未尝试的，任何错误都尝试下一个
                if school_ids and school_id_index + 1 < len(school_ids):
                    school_id_index += 1
                    retry = 0
                    continue

                if "学生信息不存在" in text:
                    return website_id, False, None, "账号或密码错误"
                else:
                    return website_id, False, None, detail or "登录失败"

            # 未知响应，也尝试下一个 schoolId
            if school_ids and school_id_index + 1 < len(school_ids):
                school_id_index += 1
                retry = 0
                continue

            return website_id, False, None, "登录失败：未知响应"

        except Exception as e:
            if retry >= max_retries:
                return website_id, False, None, f"登录异常: {e}"
            continue

    return website_id, False, None, "验证码重试次数过多"


def save_platform_cookie(username: str, website_id: int, session: httpx.Client):
    """保存指定平台的Cookie到统一data目录"""
    website = WEBSITES.get(website_id)
    if not website:
        return False
    
    website_name = website["name"]
    
    # 使用config中的统一路径
    cookies_path = get_account_cookies_path(username, website_name)
    
    # 保存Cookie (httpx 0.28+ cookies.items() 返回 (name, value) 元组)
    cookies = []
    for name, value in session.cookies.items():
        cookies.append({
            "name": name,
            "value": value,
            "domain": "",
            "path": "/"
        })
    
    with open(cookies_path, 'w', encoding='utf-8') as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    
    return True


def load_platform_cookie(username: str, website_id: int, session: httpx.Client) -> bool:
    """加载指定平台的Cookie"""
    website = WEBSITES.get(website_id)
    if not website:
        return False
    
    website_name = website["name"]
    cookies_path = get_account_cookies_path(username, website_name)
    
    if not os.path.exists(cookies_path):
        return False
    
    try:
        with open(cookies_path, encoding='utf-8') as f:
            cookies = json.load(f)
        
        session.cookies.clear()
        for cookie in cookies:
            session.cookies.set(
                name=cookie["name"],
                value=cookie["value"],
                domain=cookie.get("domain", ""),
                path=cookie.get("path", "/")
            )
        return True
    except Exception as e:
        return False


def login_all_platforms(username: str, password: str,
                       platform_passwords: Dict[int, str] = None) -> Dict[int, Tuple[bool, httpx.Client, str]]:
    """
    高并发获取所有平台Cookie
    Args:
        username: 学号
        password: 默认密码（所有平台的通用密码）
        platform_passwords: {website_id: password} 每个平台的独立密码，优先级高于 password
    
    Returns:
        {website_id: (success, session, message)}
    """
    if platform_passwords is None:
        platform_passwords = {}

    def get_password_for(wid: int) -> str:
        return platform_passwords.get(wid, password)

    results = {}
    website_ids = list(WEBSITES.keys())
    total = len(website_ids)

    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

    from infrastructure.rich_ui import _pct_color_rich, console

    # 自定义颜色进度条：根据实时进度动态变色
    class DynamicBarColumn(BarColumn):
        def render(self, task):
            if task.total is None or task.total == 0:
                pct = 0.0
            else:
                pct = task.completed / task.total
            self.complete_style = _pct_color_rich(pct)
            self.finished_style = "green"
            return super().render(task)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]平台:[/bold cyan] {task.description}"),
        DynamicBarColumn(bar_width=40),
        TextColumn("[white]{task.completed}/{task.total}[/white]"),
        TextColumn("{task.fields[status]}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(
            description="准备登录...",
            total=total,
            status="[dim]初始化...[/dim]"
        )

        completed = 0

        # 并发登录所有平台
        with ThreadPoolExecutor(max_workers=len(website_ids)) as executor:
            futures = {}
            for wid in website_ids:
                pwd = get_password_for(wid)
                futures[executor.submit(login_single_platform, wid, username, pwd)] = wid

            for future in as_completed(futures):
                wid = futures[future]
                website_id, success, session, message = future.result()
                completed += 1
                website_name = WEBSITES[website_id]['name']

                if success:
                    status = "[green]✓ 获取成功[/green]"
                    save_platform_cookie(username, website_id, session)
                    results[website_id] = (True, session, message)
                else:
                    status = f"[red]✗ {message}[/red]"
                    results[website_id] = (False, None, message)

                progress.update(task, completed=completed, description=website_name, status=status)

    return results


def retry_failed_platforms(username: str, failed_ids: Dict[int, str],
                          platform_passwords: Dict[int, str] = None) -> Dict[int, Tuple[bool, httpx.Client, str]]:
    """
    用独立密码重试登录失败的平台

    Args:
        username: 学号
        failed_ids: {website_id: 失败原因} 需要重试的平台
        platform_passwords: {website_id: password} 每个平台的独立密码

    Returns:
        {website_id: (success, session, message)}
    """
    if platform_passwords is None:
        platform_passwords = {}

    results = {}
    # 并发重试
    with ThreadPoolExecutor(max_workers=len(failed_ids)) as executor:
        futures = {}
        for wid in failed_ids:
            pwd = platform_passwords.get(wid)
            if not pwd:
                results[wid] = (False, None, "未提供该平台的密码")
                continue
            futures[executor.submit(login_single_platform, wid, username, pwd)] = wid

        for future in as_completed(futures):
            wid = futures[future]
            website_id, success, session, message = future.result()
            if success:
                save_platform_cookie(username, website_id, session)
            results[website_id] = (success, session, message)

    return results


def check_platform_cookie_valid(session: httpx.Client, website_id: int) -> bool:
    """检查指定平台的Cookie是否有效"""
    website = WEBSITES.get(website_id)
    if not website:
        return False
    
    base_url = website["base_url"]
    user_center_url = f"{base_url}/user/index"
    
    try:
        resp = session.get(user_center_url, follow_redirects=False, timeout=10)
        # 检查是否被重定向到登录页 (302 重定向到 /user/login)
        if resp.status_code == 302:
            location = resp.headers.get('Location', '')
            return 'login' not in location.lower()
        # 检查是否直接返回200但内容包含登录页特征
        if resp.status_code == 200:
            # 检查页面内容是否包含登录表单
            content = resp.text.lower()
            return 'login' not in content[:1000] and ('用户中心' in content or '个人中心' in content)
        return False
    except Exception as e:
        return False


def get_platform_login_status(username: str) -> Dict[int, bool]:
    """获取账号在所有平台的登录状态"""
    status = {}

    for website_id, cfg in WEBSITES.items():
        session = create_sync_client(cfg["base_url"])
        try:
            cookie_ok = load_platform_cookie(username, website_id, session)
            if cookie_ok:
                status[website_id] = check_platform_cookie_valid(session, website_id)
            else:
                status[website_id] = False
        finally:
            session.close()

    return status

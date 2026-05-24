import re

import urllib3

from config import PASSWORD, USERNAME, get_base_url
from infrastructure.http_session import get_dynamic_headers

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_ocr_instance = None

def _get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        import ddddocr
        _ocr_instance = ddddocr.DdddOcr(show_ad=False)
    return _ocr_instance


def _show_error_panel(title, html):
    from rich.panel import Panel
    from rich.text import Text

    from infrastructure.rich_ui import console
    body = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    body = re.sub(r'<style[^>]*>.*?</style>', '', body, flags=re.DOTALL)
    body = re.sub(r'<[^>]+>', ' ', body)
    body = re.sub(r'var\s+\w+\s*=\s*\{[^}]*\}', '', body)
    body = re.sub(r'\{[^{}]*"(?:msg|status|refresh_code)"[^{}]*\}', '', body)
    body = body.replace('\\u', '')
    body = re.sub(r'["\']\s*[,;]\s*', '', body)
    body = re.sub(r'\s+', ' ', body).strip()
    body = body.replace(' .', '.').replace(' ,', ',')
    if len(body) > 120:
        body = body[:120] + "..."
    panel = Panel(
        Text(body or title, style="dim"),
        title=f"[bold red]{title}[/bold red]",
        border_style="red",
        padding=(0, 2),
        width=60,
    )
    console.print(panel)


def login(session, username=None, password=None, max_retries=10):
    """登录函数，可传入账号密码，否则用配置文件"""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    from infrastructure.rich_ui import console

    if username is None:
        username = USERNAME
    if password is None:
        password = PASSWORD
    
    base_url = get_base_url()
    login_url = f"{base_url}/user/login"
    captcha_url = f"{base_url}/service/code"
    
    ocr = _get_ocr()
    retry = 0
    
    # verify=False already set in session constructor
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("初始化...", total=None)
        
        while retry < max_retries:
            retry += 1
            progress.update(task, description=f"尝试登录 ({retry}/{max_retries})...")

            login_headers = get_dynamic_headers()
            session.get(login_url, headers=login_headers, timeout=15)

            progress.update(task, description="获取验证码...")
            captcha_headers = get_dynamic_headers(login_url)
            captcha_resp = session.get(captcha_url, headers=captcha_headers, timeout=15)

            progress.update(task, description="识别验证码...")
            code = ocr.classification(captcha_resp.content)
            progress.update(task, description=f"验证码: {code}")

            data = {
                "username": username,
                "password": password,
                "code": code,
                "redirect": "",
                "remember": "on"
            }

            progress.update(task, description="提交登录...")
            # 禁止重定向，防止丢失错误页面
            result = session.post(login_url, data=data, headers=login_headers, follow_redirects=False, timeout=15)
            text = result.text

            # 1. 验证码错误 -> 递增延迟后重试
            if "验证码有误" in text:
                wait = 1 + retry * 0.5
                progress.update(task, description=f"验证码错误，{wait:.1f}s后重试...")
                time.sleep(wait)
                continue
            
            # 2. 登录成功判断
            if "<title>操作成功提示</title>" in text or '"status":true' in text:
                progress.update(task, description="登录成功！")
                return
            
            # 3. 账号/密码错误（错误提示页面）
            if "<title>错误提示</title>" in text:
                # 提取错误详情
                detail = ""
                # 尝试提取错误信息
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
                if not detail:
                    # 尝试从 JavaScript 中提取
                    match = re.search(r'var data =\{[^}]*"msg":"([^"]*)"', text, re.DOTALL)
                    if match:
                        detail = match.group(1)
                        # 处理 unicode 转义
                        detail = detail.encode().decode('unicode_escape') if '\\u' in detail else detail
                # 常见错误处理
                if "密码不可为空" in text:
                    raise Exception("密码不能为空")
                elif "学生学号不可为空" in text:
                    raise Exception("学号不能为空")
                elif "学生信息不存在" in text:
                    raise Exception("账号或密码错误")
                else:
                    _show_error_panel(detail or "登录失败", text)
                    raise Exception(detail or "登录失败")
            
            # 4. 其他未知响应
            _show_error_panel("未知响应", text)
            raise Exception("登录失败：未知响应")
    
    raise Exception("验证码重试次数过多")

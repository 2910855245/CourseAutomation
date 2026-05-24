#!/usr/bin/env python3
"""远程服务器管理工具 — 本地调 bug 用"""
import io
import os
import sys
import time

try:
    import paramiko
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt
    from rich.table import Table
    console = Console()
except ImportError:
    print("需要: pip install paramiko rich")
    sys.exit(1)

# ─── 配置 ─────────────────────────────
# 优先从环境变量读取，否则从 script/.env.local 文件加载
import dotenv as _dotenv

_dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), ".env.local"), override=False)

HOST = os.environ.get("REMOTE_HOST", "38.76.190.251")
PORT = int(os.environ.get("REMOTE_PORT", "22"))
USER = os.environ.get("REMOTE_USER", "root")

def _load_ssh_key():
    key_path = os.environ.get("SSH_KEY_PATH", os.path.join(os.path.dirname(__file__), "ssh_key"))
    if os.path.isfile(key_path):
        with open(key_path) as f:
            return f.read()
    return os.environ.get("SSH_KEY", "")

SSH_KEY = _load_ssh_key()

# 宝塔面板登录信息
BT_PANEL_URL = os.environ.get("BT_PANEL_URL", "https://38.76.190.251:23687/b7a5e757")
BT_USERNAME = os.environ.get("BT_USERNAME", "")
BT_PASSWORD = os.environ.get("BT_PASSWORD", "")

PROJECT_ROOT = "/www/wwwroot/anti_course"
LOCAL_ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = f"{PROJECT_ROOT}/venv/bin/python"
APP_LOG = "/tmp/app.log"
# ─────────────────────────────────────

_ssh = None

def connect():
    global _ssh
    if _ssh: return _ssh
    kf = io.StringIO(SSH_KEY)
    key = paramiko.Ed25519Key.from_private_key(kf)
    _ssh = paramiko.SSHClient()
    _ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    _ssh.connect(HOST, PORT, USER, pkey=key, timeout=15, allow_agent=False, look_for_keys=False)
    return _ssh

def run(cmd, timeout=30):
    s, o, e = connect().exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8', errors='replace'), e.read().decode('utf-8', errors='replace')

def upload(local_path, remote_path):
    sftp = connect().open_sftp()
    sftp.put(local_path, remote_path)
    sftp.close()

def download(remote_path, local_path):
    sftp = connect().open_sftp()
    sftp.get(remote_path, local_path)
    sftp.close()

# ─── 服务管理 ─────────────────────────

def status():
    out, _ = run("ps aux | grep 'python.*run.py' | grep -v grep")
    if out.strip():
        pid = out.split()[1]
        mem_out, _ = run(f"ps -p {pid} -o rss= --no-headers")
        mem = round(int(mem_out.strip() or 0) / 1024, 1)
        _, _ = run("curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/")
        http = _
        table = Table(title="服务状态")
        table.add_column("项", style="cyan")
        table.add_column("值", style="white")
        table.add_row("状态", f"[green]Running[/green]  PID={pid}")
        table.add_row("内存", f"{mem} MB")
        table.add_row("HTTP", f"{http}")
        console.print(table)
        return True
    else:
        console.print("[red]服务未运行[/red]")
        return False

def svc_start():
    run("pkill -f 'python.*run.py' 2>/dev/null", 5)
    time.sleep(1)
    run(f"cd {PROJECT_ROOT} && nohup {VENV_PYTHON} run.py > {APP_LOG} 2>&1 &", 5)
    time.sleep(4)
    status()

def svc_stop():
    run("pkill -f 'python.*run.py' 2>/dev/null", 5)
    console.print("[yellow]已发送停止信号[/yellow]")

def svc_restart():
    svc_stop()
    time.sleep(2)
    svc_start()

def svc_logs(lines=20):
    out, _ = run(f"tail -{lines} {APP_LOG}")
    console.print(Panel(out.strip() or "(空)", title=f"最近 {lines} 行日志"))

# ─── 文件同步 ─────────────────────────

def sync_file(rel_path):
    """同步单个文件到服务器并重启"""
    local = os.path.join(LOCAL_ROOT, rel_path)
    remote = f"{PROJECT_ROOT}/{rel_path}"
    if not os.path.exists(local):
        console.print(f"[red]文件不存在: {local}[/red]")
        return
    upload(local, remote)
    console.print(f"[green]已上传: {rel_path}[/green]")
    if Confirm.ask("重启服务?", default=True):
        svc_restart()

def sync_all():
    """同步整个项目"""
    import subprocess
    import tempfile
    zip_path = os.path.join(tempfile.gettempdir(), "anti_course_sync.zip")
    subprocess.run(["powershell", "-Command",
        f"Compress-Archive -Path (Get-ChildItem '{LOCAL_ROOT}' -Exclude '__pycache__','*.pyc','deploy.py','.claude','data') -DestinationPath '{zip_path}' -Force"],
        capture_output=True)
    upload(zip_path, "/root/anti_course_sync.zip")
    run(f"cd {PROJECT_ROOT} && unzip -o /root/anti_course_sync.zip 2>&1 | tail -3", 30)
    console.print("[green]全量同步完成[/green]")
    if Confirm.ask("重启服务?", default=True):
        svc_restart()

def pull_file(rel_path):
    """从服务器拉文件到本地"""
    remote = f"{PROJECT_ROOT}/{rel_path}"
    local = os.path.join(LOCAL_ROOT, rel_path)
    os.makedirs(os.path.dirname(local), exist_ok=True)
    download(remote, local)
    console.print(f"[green]已下载: {rel_path}[/green]")

def edit_remote(rel_path):
    """拉下来 → 用编辑器改 → 推回去"""
    pull_file(rel_path)
    local = os.path.join(LOCAL_ROOT, rel_path)
    os.startfile(local)
    console.print(f"[yellow]编辑完 {rel_path} 后按回车推回服务器[/yellow]")
    input()
    upload(local, f"{PROJECT_ROOT}/{rel_path}")
    console.print(f"[green]已推回: {rel_path}[/green]")
    if Confirm.ask("重启?", default=True):
        svc_restart()

# ─── 快捷修复 ─────────────────────────

def fix_bt():
    """修复宝塔 pyenv_tool.py bug"""
    script = '''import shutil
p = "/www/server/panel/mod/project/python/pyenv_tool.py"
shutil.copy(p, p + ".bak")
with open(p) as f: c = f.read()
c = c.replace('cmd = [self.pip_bin(), "install"]', 'pip_bin = self.pip_bin() or "pip3"\\n        cmd = [pip_bin, "install"]')
with open(p, "w") as f: f.write(c)
print("OK")'''
    run(f"python3 -c '{script}'", 10)
    console.print("[green]宝塔 bug 已修复[/green]")

def fix_qr():
    """同步修复过的 QR 相关文件"""
    for f in ["api/main.py", "api/routers/ypay_routes.py"]:
        upload(os.path.join(LOCAL_ROOT, f), f"{PROJECT_ROOT}/{f}")
        console.print(f"  已上传: {f}")
    svc_restart()

def fix_env():
    """更新 .env 数据库配置（从环境变量读取）"""
    mysql_url = os.environ.get("MYSQL_URL", "")
    if not mysql_url:
        console.print("[red]请设置 MYSQL_URL 环境变量[/red]")
        return
    run(f"sed -i 's|DATABASE_URL=.*|DATABASE_URL={mysql_url}|' {PROJECT_ROOT}/.env", 5)
    console.print("[green]数据库配置已更新[/green]")

# ─── 菜单 ─────────────────────────────

def menu():
    console.clear()
    banner = """
╔══════════════════════════════╗
║   远程服务器管理工具        ║
╚══════════════════════════════╝
"""
    console.print(banner, style="bold cyan")
    console.print(f"  服务器: [cyan]{HOST}:{PORT}[/cyan]")

    console.print()
    console.print("  [bold]服务管理[/bold]")
    console.print("  [1] 查看状态    [2] 启动    [3] 停止    [4] 重启    [5] 日志")
    console.print()
    console.print("  [bold]快速修复[/bold]")
    console.print("  [6] 修复 QR 接口    [7] 修复宝塔 bug    [8] 修复数据库配置")
    console.print()
    console.print("  [bold]文件同步[/bold]")
    console.print("  [9] 同步单个文件    [0] 全量同步    [e] 远程编辑")
    console.print()
    console.print("  [q] 退出")
    console.print()

def main():
    try:
        connect()
    except Exception as e:
        console.print(f"[red]连接失败: {e}[/red]")
        return

    while True:
        menu()
        c = Prompt.ask("选择", choices=["1","2","3","4","5","6","7","8","9","0","e","q"], default="1")

        actions = {
            "1": status,
            "2": svc_start,
            "3": svc_stop,
            "4": svc_restart,
            "5": svc_logs,
            "6": fix_qr,
            "7": fix_bt,
            "8": fix_env,
            "9": lambda: sync_file(Prompt.ask("文件路径", default="api/main.py")),
            "0": sync_all,
            "e": lambda: edit_remote(Prompt.ask("编辑文件", default="api/main.py")),
        }

        if c == "q":
            break

        try:
            actions.get(c, lambda: None)()
        except Exception as e:
            console.print(f"[red]错误: {e}[/red]")

        if c != "1":
            input("\n按回车继续...")

if __name__ == "__main__":
    main()

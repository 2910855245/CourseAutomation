#!/usr/bin/env python3
"""刷课系统管理脚本"""
import os
import signal
import subprocess
import sys
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))

try:
    from rich.align import Align  # noqa: F401
    from rich.console import Console
    from rich.live import Live  # noqa: F401
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.text import Text
    console = Console()
except ImportError:
    print("请安装 rich: pip install rich")
    sys.exit(1)

VENV = os.path.join(os.getcwd(), "venv", "bin", "python")
PID_FILE = os.path.join(os.getcwd(), "server.pid")
LOG_FILE = "/tmp/anti_course.log"
APP_SCRIPT = "run.py"

def get_pid():
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None

def get_process():
    try:
        result = subprocess.run(
            ["ps", "-p", str(get_pid()), "-o", "pid,rss,pcpu,etime,cmd", "--no-headers"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return ""

def is_running():
    pid = get_pid()
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def get_memory_mb():
    try:
        pid = get_pid()
        if not pid: return 0
        result = subprocess.run(["ps", "-p", str(pid), "-o", "rss=", "--no-headers"],
                              capture_output=True, text=True, timeout=5)
        return round(int(result.stdout.strip() or 0) / 1024, 1)
    except Exception:
        return 0

def show_status():
    running = is_running()
    status_text = Text("● Running", style="bold green") if running else Text("● Stopped", style="bold red")
    pid = get_pid()
    mem = get_memory_mb()

    table = Table(show_header=False, box=None, padding=(0, 4))
    table.add_column("key", style="cyan")
    table.add_column("val", style="white")
    table.add_row("状态", status_text)
    table.add_row("端口", "8000")
    table.add_row("PID", str(pid or "-"))
    table.add_row("内存", f"{mem} MB")
    if running:
        proc = get_process()
        if proc:
            parts = proc.split()
            if len(parts) >= 4:
                table.add_row("运行时长", parts[3])

    console.print()
    console.print(Panel(table, title="[bold]刷课系统状态[/bold]", border_style="blue"))

    # Quick log view
    if os.path.exists(LOG_FILE):
        try:
            result = subprocess.run(["tail", "-8", LOG_FILE], capture_output=True, text=True, timeout=5)
            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            if lines:
                console.print(Panel("\n".join(lines[-5:]), title="[dim]最近日志[/dim]", border_style="dim"))
        except Exception:
            pass

def start():
    if is_running():
        console.print("[yellow]⚠ 服务已在运行[/yellow]")
        return False

    python = VENV if os.path.exists(VENV) else sys.executable
    log = open(LOG_FILE, "a")
    proc = subprocess.Popen(
        [python, APP_SCRIPT],
        stdout=log, stderr=subprocess.STDOUT,
        cwd=os.getcwd(),
        preexec_fn=os.setsid
    )
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    log.close()

    time.sleep(2)
    if is_running():
        console.print(f"[green]✓ 服务已启动 PID={proc.pid}[/green]")
        return True
    else:
        console.print("[red]✗ 启动失败，检查日志[/red]")
        console.print(f"[dim]tail -20 {LOG_FILE}[/dim]")
        return False

def stop():
    pid = get_pid()
    if not pid:
        console.print("[yellow]服务未运行[/yellow]")
        return

    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        console.print(f"[green]✓ 已发送停止信号 PID={pid}[/green]")
        for _ in range(10):
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except OSError:
                console.print("[green]✓ 服务已停止[/green]")
                if os.path.exists(PID_FILE):
                    os.remove(PID_FILE)
                return
        # Force kill
        os.killpg(os.getpgid(pid), signal.SIGKILL)
        console.print("[yellow]✓ 强制停止[/yellow]")
    except ProcessLookupError:
        console.print("[dim]进程已不存在[/dim]")
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)

def restart():
    console.print("[cyan]重启中...[/cyan]")
    stop()
    time.sleep(2)
    start()

def show_logs():
    if not os.path.exists(LOG_FILE):
        console.print("[yellow]日志文件不存在[/yellow]")
        return
    try:
        result = subprocess.run(["tail", "-30", LOG_FILE], capture_output=True, text=True, timeout=5)
        console.print(Panel(result.stdout.strip() or "(空)", title="[bold]最近30行日志[/bold]", border_style="dim"))
    except Exception:
        console.print("[red]读取日志失败[/red]")

def show_menu():
    banner = """
    ╔══════════════════════════════════╗
    ║      刷课 SaaS 管理系统         ║
    ╚══════════════════════════════════╝
    """
    console.clear()
    console.print(banner, style="bold cyan", justify="center")
    show_status()

    console.print()
    console.print("  [1]  启动服务", style="green")
    console.print("  [2]  停止服务", style="red")
    console.print("  [3]  重启服务", style="yellow")
    console.print("  [4]  查看日志", style="cyan")
    console.print("  [5]  刷新状态", style="blue")
    console.print("  [q]  退出")
    console.print()

def main():
    while True:
        show_menu()
        choice = Prompt.ask("选择", choices=["1","2","3","4","5","q"], default="5")

        if choice == "1":
            start()
        elif choice == "2":
            stop()
        elif choice == "3":
            restart()
        elif choice == "4":
            show_logs()
        elif choice == "5":
            pass
        elif choice == "q":
            console.print("[dim]再见[/dim]")
            break

        if choice != "5":
            input("\n按回车继续...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]已退出[/dim]")

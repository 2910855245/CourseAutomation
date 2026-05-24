import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import getpass
import json
import time
from datetime import datetime
from typing import Dict

import httpx
from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt

console = Console()

from config import (
    BASE_URL,
    CURRENT_WEBSITE,
    WEBSITES,
    get_account_course_info_dir,
    get_account_records_dir,
    get_current_website_config,
    save_global_config,
    update_paths_for_current_account,
    update_url_config,
)
from infrastructure.course_crawler import get_courses
from infrastructure.dashboard import DashboardDisplay
from infrastructure.http_session import check_cookie_valid
from presentation.account_manager import AccountConfig, SuwanUser
from presentation.study_cli import StudyCLI
from presentation.utils import clear_screen
from services.course_service import extract_user_id_from_course
from services.multi_platform_auth import (
    check_platform_cookie_valid,
    load_platform_cookie,
    login_all_platforms,
    retry_failed_platforms,
)
from services.study_record_service import StudyRecordService
from services.study_service import StudyMultiplexer


def show_progress_bar(current, total, prefix="进度", suffix="完成", length=50):
    """显示进度条 - Rich 版"""
    pct = current / total if total > 0 else 0
    from infrastructure.rich_ui import _pct_color_rich
    color = _pct_color_rich(pct)
    with Progress(
        TextColumn("{task.description}"),
        BarColumn(bar_width=length, complete_style=color, finished_style=color),
        TextColumn("[white]{task.percentage:>3.0f}%[/white]"),
        TextColumn("{task.fields[suffix]}"),
        console=console,
    ) as progress:
        task = progress.add_task(
            description=prefix,
            total=total,
            suffix=suffix
        )
        progress.update(task, completed=current)
        if current == total:
            progress.stop()


from rich.progress import BarColumn

from services.course_service import process_single_course


def login_with_per_platform_passwords(username, password, account_config=None):
    """
    智能登录所有平台：
    1. 先从账号配置加载已保存的各平台独立密码
    2. 用通用密码 + 独立密码并发登录
    3. 对密码错误的失败平台，提示用户输入该平台独立密码
    4. 重试成功后将独立密码持久化保存
    """
    # 加载已保存的平台独立密码
    platform_passwords = {}
    if account_config:
        platform_passwords = account_config.load_platform_passwords(username)

    results = login_all_platforms(username, password, platform_passwords)

    failed = {}
    for wid, (ok, _, msg) in results.items():
        if not ok:
            failed[wid] = msg

    if account_config:
        account_config.log_debug_info(username, f"登录结果: 成功={[wid for wid,(ok,_,_) in results.items() if ok]}, 失败={failed}", "INFO")

    if not failed:
        return results

    # 筛选出"密码相关"的失败（排除验证码重试过多这类临时失败）
    pwd_failed = {}
    for wid, msg in failed.items():
        if "密码" in msg and "学生信息不存在" not in msg:
            pwd_failed[wid] = msg

    if not pwd_failed:
        return results

    console.print()
    for wid, msg in pwd_failed.items():
        name = WEBSITES[wid]['name']
        console.print(f"  [red]✗[/red] {name}: {msg}")

    # 一次性选择：重试 或 退出
    console.print()
    if account_config:
        account_config.log_debug_info(username, f"密码不匹配，等待用户输入: {list(pwd_failed.keys())}", "WARNING")
    choice = Prompt.ask("[yellow][?] 是否重新输入密码？[/yellow]", choices=["y", "n"], default="y")
    if choice == "n":
        console.print("[dim]已跳过，将使用已成功的平台[/dim]")
        time.sleep(1)
        return results

    console.print("\n[dim]提示：如果该平台密码与通用密码相同，可能是账号不存在，无需输入。[/dim]")
    console.print()
    new_passwords = {}
    for wid in pwd_failed:
        name = WEBSITES[wid]['name']
        pwd = getpass.getpass(f"  [{name}] 密码（留空跳过）: ")
        if pwd.strip():
            new_passwords[wid] = pwd.strip()

    if not new_passwords:
        return results

    # 用新密码重试
    console.print("\n[yellow]正在用独立密码重试...[/yellow]")
    retry_results = retry_failed_platforms(username, failed, new_passwords)
    results.update(retry_results)

    # 保存成功的独立密码
    if account_config:
        saved_passwords = {wid: pwd for wid, pwd in new_passwords.items()
                          if retry_results.get(wid, (False,))[0]}
        if saved_passwords:
            platform_passwords.update(saved_passwords)
            account_config.save_platform_passwords(username, platform_passwords)
            console.print(f"[green]已保存 {len(saved_passwords)} 个平台的独立密码[/green]")

    return results


def auto_initialize_account(session, account_config, username, is_platform_switch=False):
    """第一次登录时自动初始化账号数据（Rich 实时进度条版）"""
    account_config.log_debug_info(username, f"开始自动初始化账号: {username}", "INFO")

    # 获取学生姓名
    try:
        from config import USER_CENTER_URL
        from infrastructure.course_crawler import extract_student_name
        from infrastructure.http_session import safe_request
        resp = safe_request(session, USER_CENTER_URL)
        if resp:
            student_name = extract_student_name(resp.text)
            if student_name:
                account_config.set_student_name(username, student_name)
                account_config.log_debug_info(username, f"获取到学生姓名: {student_name}", "INFO")
    except Exception as e:
        account_config.log_debug_info(username, f"获取学生姓名失败: {e}", "WARNING")

    # 抓取课程列表
    account_config.log_debug_info(username, "开始抓取课程信息", "INFO")
    courses = get_courses(session)
    if not courses:
        console.print("[yellow]该平台暂无课程数据[/yellow]")
        account_config.log_debug_info(username, "该平台暂无课程数据", "INFO")
        # 标记初始化完成，即使没有课程
        account_config.set_first_login_done(username)
        return True

    account_config.log_debug_info(username, f"获取到课程数量: {len(courses)}", "INFO")
    course_info_dir = get_account_course_info_dir()

    # 计算总步骤数：课程抓取 (N) + 学习记录抓取 (M)
    # 学习记录的数量近似等于课程数量（每门课都会抓一次）
    total_steps = len(courses) * 2  # 课程 + 记录

    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

    from infrastructure.rich_ui import _pct_color_rich

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
        TextColumn("[progress.description]{task.description}"),
        DynamicBarColumn(bar_width=40),
        TextColumn("[white]{task.percentage:>3.0f}%[/white]"),
        console=console,
        transient=False,   # 进度条始终保留
    ) as progress:
        task = progress.add_task("准备初始化...", total=total_steps)

        # --- 第一步：抓取课程详情 ---
        progress.update(task, description="正在抓取课程信息")
        # 逐个处理课程（可按需调整并发度，这里用顺序以便进度条更平滑）
        for course in courses:
            process_single_course(session, course, course_info_dir, max_workers=8, silent=True)
            progress.advance(task)

        # --- 第二步：抓取学习记录 ---
        account_config.log_debug_info(username, "开始抓取学习记录", "INFO")
        record_service = StudyRecordService(session, username)
        course_files = load_course_files()
        total_records = len(course_files)

        # 如果课程文件数量与课程数不一致（可能有些课程没抓成功），动态调整总步数
        progress.update(task, total=len(courses) + total_records)
        progress.update(task, description="正在抓取学习记录")

        for i, file in enumerate(course_files):
            try:
                # 处理单个课程的学习记录
                result = process_course_record(session, file, course_files, silent=True)
                account_config.log_debug_info(username, result, "INFO")
            except Exception as e:
                account_config.log_debug_info(username, f"处理 {file} 失败: {e}", "ERROR")
            progress.advance(task)

        # 完成
        account_config.set_first_login_done(username)
        account_config.log_debug_info(username, "自动初始化完成", "INFO")
        progress.update(task, description="初始化完成！", completed=total_steps)

    time.sleep(1)  # 让用户看到完成状态
    return True


def _get_greeting():
    """获取当前时段问候语 - 更精细的时段划分"""
    hour = datetime.now().hour
    if 5 <= hour < 8:
        return "清晨好"
    elif 8 <= hour < 11:
        return "上午好"
    elif 11 <= hour < 13:
        return "中午好"
    elif 13 <= hour < 17:
        return "下午好"
    elif 17 <= hour < 19:
        return "傍晚好"
    elif 19 <= hour < 22:
        return "晚上好"
    else:
        return "夜深了"


def _fmt_duration(seconds):
    """格式化秒数为可读时长"""
    if seconds <= 0:
        return "0s"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    elif minutes > 0:
        return f"{minutes}m {secs:02d}s"
    else:
        return f"{secs}s"


def show_main_menu(account_config=None, session=None):
    """全新主菜单 —— 课程与考试融合在一张表中"""
    from infrastructure.rich_ui import render_main_menu
    from services.data_loader import DataLoader

    clear_screen()

    current_website = get_current_website_config()
    website_name = current_website.get("name", "未知平台")
    greeting = _get_greeting()

    student_name = ""
    if account_config:
        current_username = account_config.get_current_username()
        if current_username:
            student_name = account_config.get_student_name(current_username)

    data_loader = DataLoader()
    courses = data_loader.load_courses(simple=True)
    study_records = data_loader.load_study_records()
    work_records = _load_work_records()

    # ── 汇总统计 ──
    total_videos = 0
    completed_videos = 0
    total_video_duration = 0
    total_viewed_duration = 0
    total_exams = 0
    completed_exams = 0

    merged_rows = []

    for course in courses:
        course_data = course.get('data', {})
        course_name = course_data.get('course_name', course.get('name', ''))
        course_id = course_data.get('course_id', '')
        nodes = course_data.get('nodes', [])

        # 视频统计
        videos = [n for n in nodes if n.get('node_type') == 'video']
        v_total = len(videos)
        v_done = 0
        for v in videos:
            vname = v.get('name', '')
            p = data_loader.get_video_progress(course_name, vname, study_records, v)
            total_video_duration += p['total']
            total_viewed_duration += min(p['viewed'], p['total'])
            if p['status'] == '已学' or (p['total'] > 0 and p['viewed'] >= p['total']):
                v_done += 1
        v_pct = v_done / v_total if v_total > 0 else 0

        total_videos += v_total
        completed_videos += v_done

        # 考试统计：work_records 已完成的 {work_id} + study_records 已交/已阅 title + exam JSON 状态
        done_ids = {k.split('_', 1)[1] for k in work_records if k.startswith(f"{course_id}_")}
        server_done_titles = set()
        server_status_map = {}
        if course_name in study_records:
            for wr in study_records[course_name].get('data', {}).get('work', []):
                title = wr.get('title', '').strip()
                if title:
                    server_status_map[title] = wr.get('status', '')
                if wr.get('status', '') in ('已交', '已阅'):
                    server_done_titles.add(title)

        e_total = 0
        e_done = 0
        for n in nodes:
            ntype = n.get('node_type', '')
            if ntype not in ('work', 'exam'):
                continue
            hidden = n.get('hidden_params', {})
            nname = n.get('name', '')
            wid = hidden.get('work_id', '')
            if wid:
                if server_status_map.get(nname, '') == '未交':
                    continue
                e_total += 1
                if wid in done_ids or nname in server_done_titles:
                    e_done += 1
        total_exams += e_total
        completed_exams += e_done

        # 跳过无视频也无考试的课程
        if v_total == 0 and e_total == 0:
            continue

        merged_rows.append({
            'index': len(merged_rows) + 1,
            'name': course_name,
            'course_id': course_id,
            'video_pct': v_pct,
            'video_done': v_done,
            'video_total': v_total,
            'exam_done': e_done,
            'exam_total': e_total,
        })

    panel = render_main_menu(
        greeting=greeting,
        student_name=student_name,
        website_name=website_name,
        merged_rows=merged_rows,
        completed_videos=completed_videos,
        total_videos=total_videos,
        total_video_duration=total_video_duration,
        total_viewed_duration=total_viewed_duration,
        completed_exams=completed_exams,
        total_exams=total_exams,
    )
    console.print(panel)
    return merged_rows


def _handle_delete_account(accounts, account_config, session):
    """处理删除账号的通用逻辑"""
    from infrastructure.rich_ui import render_delete_account_menu

    clear_screen()
    current_username = account_config.get_current_username() if account_config else ''
    student_names = {}
    if account_config:
        for acc in accounts:
            uname = acc.get('username', '')
            if uname:
                student_names[uname] = account_config.get_student_name(uname)
    panel = render_delete_account_menu(accounts, current_username, student_names)
    console.print(panel)

    delete_choice = Prompt.ask("请选择要删除的账号")
    if delete_choice == "0":
        return
    
    try:
        delete_index = int(delete_choice) - 1
        if 0 <= delete_index < len(accounts):
            selected_account = accounts[delete_index]
            username = selected_account.get("username")
            
            if Confirm.ask(f"\n确定要删除账号【{username}】吗？这将同时删除该账号的 Cookie！"):
                account_config.load_account_cookie(username, session)
                user = SuwanUser(BASE_URL, session)
                user.logout_server()
                account_config.delete_account(username)
                console.print(f"\n[green]账号【{username}】已删除！[/green]")
        else:
            console.print("\n[red]无效选项！[/red]")
    except ValueError:
        console.print("\n[red]无效选项！[/red]")


def show_website_switch_menu():
    """显示平台切换菜单 - Rich 版"""
    import config
    from infrastructure.rich_ui import render_website_menu

    clear_screen()

    current_website = get_current_website_config()
    current_name = current_website.get("name", "未知")

    panel = render_website_menu(WEBSITES, config.CURRENT_WEBSITE, current_name)
    console.print(panel)


def switch_website(session, account_config):
    """切换平台"""
    global CURRENT_WEBSITE
    
    # 显示切换菜单
    show_website_switch_menu()
    choice = input("\n请选择: ").strip() or "0"
    
    if choice == "0":
        return False, None
    
    try:
        new_website_id = int(choice)
        if new_website_id not in WEBSITES:
            console.print("\n[red]无效选项！[/red]")
            return False, None
        
        if new_website_id == CURRENT_WEBSITE:
            console.print("\n[yellow]已经是当前平台，无需切换！[/yellow]")
            return False, None
        
        # 开始切换
        new_website = WEBSITES[new_website_id]
        new_name = new_website.get("name", "未知")
        
        # 保存当前用户名，避免清理会话后丢失
        current_username = account_config.get_current_username()
        
        # 停止后台更新并清理会话
        from services.auto_updater import get_auto_updater
        updater = get_auto_updater()
        updater.stop()
        session.cookies.clear()
        
        # 更新配置
        import config
        config.CURRENT_WEBSITE = new_website_id
        update_url_config()
        save_global_config()
        CURRENT_WEBSITE = new_website_id
        global BASE_URL
        BASE_URL = config.BASE_URL
        update_paths_for_current_account()
        
        # 尝试使用当前账号的新平台Cookie自动登录
        if current_username:
            success, website_id, message = try_login_with_platform_cookie(
                current_username, session, new_website_id
            )
            if success:
                console.print(f"\n[green][OK] 已切换到【{new_name}】[/green]")
                account_config.set_current_account(current_username)
                update_paths_for_current_account()
                
                # 检查是否需要自动初始化
                if account_config.is_first_login(current_username):
                    init_ok = auto_initialize_account(session, account_config, current_username, is_platform_switch=True)
                    if not init_ok:
                        # 初始化失败，让用户决定是重试还是跳过
                        retry = Confirm.ask("初始化失败，是否重试？", default=True)
                        if retry:
                            init_ok = auto_initialize_account(session, account_config, current_username, is_platform_switch=True)
                        # 无论是否重试，都继续进入主菜单
                
                # 启动后台自动更新
                updater = get_auto_updater()
                updater.check_and_update(session, current_username, account_config)
                
                return False, new_website_id
            else:
                console.print("[yellow]>>> 新平台Cookie无效，需要重新登录[/yellow]")
        
        # 确保路径已更新
        update_paths_for_current_account()
        
        console.print(f"[green]>>> 已成功切换到【{new_name}】！[/green]")
        console.print("[yellow]>>> 请重新登录[/yellow]")
        console.print()
        
        # 返回 True 表示需要重新初始化
        return True, new_website_id
        
    except ValueError:
        console.print("\n[red]无效选项！[/red]")
        return False, None
    except Exception as e:
        console.print(f"\n[red]切换平台时出错: {e}[/red]")
        time.sleep(1)
        return False, None


def show_account_select_menu(accounts, account_config=None):
    """显示账号选择菜单 - Rich 版"""
    from infrastructure.rich_ui import render_account_menu

    clear_screen()

    current_username = ""
    student_names = {}
    if account_config:
        current_username = account_config.get_current_username()
        # 获取所有账号的学生姓名
        for acc in accounts:
            username = acc.get('username', '')
            if username:
                student_names[username] = account_config.get_student_name(username)

    panel = render_account_menu(accounts, current_username, student_names)
    console.print(panel)


def auto_update_records(session, course_id=None, course_name=None, silent=False):
    if course_id and course_name:
        if not silent:
            console.print(f"\n[yellow]>>> 正在更新 {course_name} 的学习记录...[/yellow]")
        try:
            from config import get_current_account
            username = get_current_account()
            record_service = StudyRecordService(session, username)
            course_files = load_course_files()
            user_id = None
            course_info_dir = get_account_course_info_dir()
            for file in course_files:
                with open(os.path.join(course_info_dir, file), encoding='utf-8') as f:
                    course_data = json.load(f)
                if course_data.get('course_id') == course_id:
                    user_id = extract_user_id_from_course(course_data, course_files, course_info_dir)
                    break
            if not user_id:
                if not silent:
                    console.print("[yellow]无法获取用户ID，回退到全量更新[/yellow]")
                record_service.run_auto(silent=silent)
                return
            record_service.update_video_only(course_id, user_id, silent=silent)
            if not silent:
                console.print(f"[green]{course_name} 视频记录更新成功[/green]")
        except Exception as e:
            if not silent:
                console.print(f"[red]学习记录更新失败: {e}[/red]")
    else:
        if not silent:
            console.print("\n[yellow]>>> 正在更新学习记录...[/yellow]")
        try:
            from config import get_current_account
            username = get_current_account()
            record_service = StudyRecordService(session, username)
            record_service.run_auto(silent=silent)
            if not silent:
                console.print("[green]学习记录更新成功[/green]")
        except Exception as e:
            if not silent:
                console.print(f"[red]学习记录更新失败: {e}[/red]")


def load_course_files():
    """加载课程文件列表"""
    from services.course_service import load_course_files as load_course_files_service
    return load_course_files_service()


def select_course_from_files(course_files):
    """让用户从课程文件中选择一个"""
    if not course_files:
        return None, None
    
    console.print("[bold]请选择要抓取学习记录的课程:[/bold]")
    course_info_dir = get_account_course_info_dir()
    for i, file in enumerate(course_files, 1):
        try:
            with open(os.path.join(course_info_dir, file), encoding='utf-8') as f:
                course_data = json.load(f)
            course_name = course_data.get('course_name', '未知课程')
            course_id = course_data.get('course_id', '未知ID')
            console.print(f"{i}. {course_name} (ID: {course_id})")
        except Exception as e:
            console.print(f"{i}. {file} (解析失败: {e})")
    
    while True:
        try:
            selection = int(Prompt.ask("请输入课程编号"))
            if 1 <= selection <= len(course_files):
                return course_files[selection - 1], selection - 1
            console.print("[red]输入无效，请重新输入[/red]")
        except ValueError:
            console.print("[red]请输入有效的数字[/red]")


def process_course_record(session, file, course_files, silent=False):
    """处理单个课程的学习记录"""
    try:
        from config import get_current_account
        username = get_current_account()
        course_info_dir = get_account_course_info_dir()
        with open(os.path.join(course_info_dir, file), encoding='utf-8') as f:
            course_data = json.load(f)
        course_id = course_data.get('course_id')
        course_name = course_data.get('course_name', '未知课程')
        
        if not course_id:
            return f"{course_name}: 缺少课程ID，跳过"
        
        user_id = extract_user_id_from_course(course_data, course_files, course_info_dir)
        
        if not user_id:
            return f"{course_name}: 无法获取用户ID"
        
        record_service = StudyRecordService(session, username)
        record_service.run(course_id, user_id, silent=silent)
        return f"{course_name}: 学习记录抓取完成"
    except Exception as e:
        return f"处理 {file} 时出错: {e}"


def try_login_with_platform_cookie(username, session, target_website_id=None):
    """
    尝试使用指定平台或所有平台的Cookie登录
    
    Args:
        username: 账号
        session: httpx.Client
        target_website_id: 指定平台ID，None则尝试所有平台
    
    Returns:
        (success, website_id, message)
    """
    if target_website_id:
        # 尝试指定平台
        cookie_ok = load_platform_cookie(username, target_website_id, session)
        if cookie_ok and check_platform_cookie_valid(session, target_website_id):
            website_name = WEBSITES[target_website_id]["name"]
            console.print(f"[green][OK] [{website_name}] Cookie有效，直接登录！[/green]")
            return True, target_website_id, "Cookie登录成功"
        else:
            return False, target_website_id, "Cookie无效"
    else:
        # 尝试所有平台
        for website_id in WEBSITES.keys():
            cookie_ok = load_platform_cookie(username, website_id, session)
            if cookie_ok and check_platform_cookie_valid(session, website_id):
                website_name = WEBSITES[website_id]["name"]
                console.print(f"[green][OK] [{website_name}] Cookie有效，直接登录！[/green]")
                return True, website_id, "Cookie登录成功"
        
        return False, None, "所有平台Cookie无效"


def interactive_login_new_account(account_config, session, default_website_id=1):
    """登录新账号 - 高并发登录所有网站 - Rich 版"""
    from services.auto_updater import get_auto_updater

    clear_screen()

    # 登录界面 - 顶部标题框（靠左，内容居中）
    title_panel = Panel(
        Align.center("[bold cyan]登 录[/bold cyan]"),
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
        width=60,
    )
    console.print(title_panel)
    console.print()

    console.print("[cyan]学号[/cyan]:", end="")
    username = input()
    console.print("[cyan]密码[/cyan]:", end="")
    password = input()

    if not username or not password:
        console.print("\n[red][X] 学号和密码不能为空[/red]")
        return False

    try:
        account_config.log_debug_info(username, "开始登录流程", "INFO")
        results = login_with_per_platform_passwords(username, password, account_config)
        account_config.log_debug_info(username, f"登录完成, 结果: {[(wid, s) for wid, (s, _, _) in results.items()]}", "INFO")

        from infrastructure.study_reporter import StudyReporter
        StudyReporter.set_shared_credentials(username, password)
        success_count = sum(1 for success, _, _ in results.values() if success)
        total_count = len(results)

        if success_count == 0:
            console.print("\n[red][X] 账号密码不正确[/red]")
            time.sleep(1)
            return False

        console.print(f"[green][OK] 成功获取 {success_count}/{total_count} 个平台Cookie[/green]")
        account_config.log_debug_info(username, "已打印成功获取", "INFO")

        if default_website_id in results and results[default_website_id][0]:
            account_config.log_debug_info(username, f"默认平台{default_website_id}成功,开始配置", "INFO")
            import config
            config.CURRENT_WEBSITE = default_website_id
            update_url_config()
            save_global_config()
            CURRENT_WEBSITE = default_website_id
            BASE_URL = config.BASE_URL
            account_config.log_debug_info(username, "URL配置已更新", "INFO")

            session.cookies.update(results[default_website_id][1].cookies)
            account_config.log_debug_info(username, "Cookie已更新,开始add_account", "INFO")
            account_config.add_account(username, session)
            account_config.log_debug_info(username, "add_account完成", "INFO")
            update_paths_for_current_account()
            account_config.log_debug_info(username, "已设置默认平台配置", "INFO")

            console.print(f"[green][OK] 已登录默认平台: {WEBSITES[default_website_id]['name']}[/green]")

            is_first = account_config.is_first_login(username)
            account_config.log_debug_info(username, f"是否首次登录: {is_first}", "INFO")
            if is_first:
                account_config.log_debug_info(username, "开始自动初始化", "INFO")
                init_success = auto_initialize_account(session, account_config, username)
                account_config.log_debug_info(username, f"自动初始化完成: {init_success}", "INFO")
                if not init_success:
                    console.print("\n[yellow][!] 初始化失败，可能是网络问题或课程抓取失败[/yellow]")
                    retry = Confirm.ask("是否重试初始化？", default=True)
                    if retry:
                        init_success = auto_initialize_account(session, account_config, username)
                        if not init_success:
                            console.print("\n[red][!] 初始化再次失败，将跳过初始化[/red]")

            account_config.log_debug_info(username, "开始自动更新检查", "INFO")
            updater = get_auto_updater()
            updater.check_and_update(session, username, account_config)
            account_config.log_debug_info(username, "自动更新检查完成", "INFO")

            return True
        else:
            account_config.log_debug_info(username, f"默认平台{default_website_id}失败,尝试其他平台", "WARNING")
            for wid, (success, sess, msg) in results.items():
                if success:
                    account_config.log_debug_info(username, f"切换到平台{wid}", "INFO")
                    import config
                    config.CURRENT_WEBSITE = wid
                    update_url_config()
                    save_global_config()
                    CURRENT_WEBSITE = wid
                    BASE_URL = config.BASE_URL

                    session.cookies.update(sess.cookies)
                    account_config.log_debug_info(username, "Cookie更新完成,开始add_account", "INFO")
                    account_config.add_account(username, session)
                    account_config.log_debug_info(username, "add_account完成", "INFO")
                    update_paths_for_current_account()

                    console.print(f"[green][OK] 已切换到可用平台: {WEBSITES[wid]['name']}[/green]")

                    if account_config.is_first_login(username):
                        init_success = auto_initialize_account(session, account_config, username)
                        if not init_success:
                            # 初始化失败，提供选项
                            console.print("\n[yellow][!] 初始化失败，可能是网络问题或课程抓取失败[/yellow]")
                            retry = Confirm.ask("是否重试初始化？", default=True)
                            if retry:
                                # 重新尝试初始化
                                init_success = auto_initialize_account(session, account_config, username)
                                if not init_success:
                                    console.print("\n[red][!] 初始化再次失败，将跳过初始化[/red]")
                            # 无论是否成功，都继续执行后续流程

                    updater = get_auto_updater()
                    updater.check_and_update(session, username, account_config)

                    return True

            console.print("\n[red]所有平台登录失败！[/red]")
            return False

    except Exception as e:
        console.print(f"\n[red]登录失败: {e}[/red]")
        return False


def _do_single_work_threaded_w(item, cookies_dict, headers):
    """_do_single_work_threaded 的无进度条包装，返回 True/False，抑制日志"""
    import os

    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn

    from config import BASE_URL
    # loguru 自带格式化，无需手动调整级别
    try:
        dummy_console = Console(file=open(os.devnull, 'w', encoding='utf-8'), width=80)
        progr = Progress(SpinnerColumn(), TextColumn("{task.description}"), console=dummy_console, transient=True)
        progr.start()
        try:
            tid = progr.add_task("", total=100)
            return _do_single_work_threaded(item, True, cookies_dict, headers, BASE_URL, progr, tid)
        finally:
            progr.stop()
    finally:
        anti_logger.setLevel(old_level)
        for h, lv in old_handlers:
            h.setLevel(lv)


def _handle_all_in_one(session, account_config):
    """一键全清：同时完成未完成视频 + 未完成考试"""
    import threading
    import time as _time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from config import BASE_URL
    from infrastructure.dashboard import DashboardDisplay
    from infrastructure.rich_ui import render_all_in_one_dashboard
    from services.data_loader import DataLoader
    from services.study_service import StudyMultiplexer

    # ── 收集数据 ──
    study_cli = StudyCLI()
    all_videos = []
    for course in study_cli.courses:
        all_videos.extend(study_cli.get_videos_from_course(course, 2))
    video_tasks = study_cli.create_tasks(all_videos) if all_videos else []
    batch_size = min(len(video_tasks), 50) if video_tasks else 0
    video_tasks = video_tasks[:batch_size] if batch_size else []

    work_records = _load_work_records()
    study_records = DataLoader().load_study_records()
    courses = DataLoader().load_courses(simple=True)

    # 复用考试详情页统一的状态判断，只取 [未开始] 的项
    all_exams = []
    for course in courses:
        cd = course.get('data', {})
        cn = cd.get('course_name', course.get('name', ''))
        cid = cd.get('course_id', '')
        nodes = cd.get('nodes', [])
        if not cid or not nodes:
            continue
        items = _build_exam_items_for_course(cn, cid, nodes, work_records, study_records)
        for it in items:
            if it['is_done'] or it['status_text'] in ('[已超时]', '[未交]'):
                continue
            if not it.get('can_answer', False):
                continue
            all_exams.append({
                'course_name': cn, 'course_id': cid,
                'node_name': it['name'], 'node_id': it['node_id'],
                'node_type': it['node_type'], 'url': it['url'],
                'work_id': it['work_id'],
                'is_work': it['tag'] == '练习',
                'hidden': {},
            })

    all_exams = all_exams[:50] if len(all_exams) > 50 else all_exams

    if not video_tasks and not all_exams:
        console.print("[green]没有待处理的任务！[/green]")
        _time.sleep(2)
        return

    # ── 共享状态 ──
    state_lock = threading.Lock()
    video_state = {
        'total': len(video_tasks), 'done': 0, 'failed': 0,
        'slots': [],
        'start_time': _time.time(),
    }
    exam_state = {
        'total': len(all_exams), 'done': 0, 'failed': 0,
        'slots': [],
        'start_time': _time.time(),
    }

    for t in video_tasks:
        video_state['slots'].append({
            'video_name': t.video_name,
            'duration': t.duration,
            'viewed': t.viewed_duration,
            'total_time': 0,
            'done': False,
            'failed': False,
        })
    for e in all_exams:
        exam_state['slots'].append({
            'name': e['node_name'] or e.get('course_name', ''),
            'progress': 0,
            'done': False,
            'failed': False,
        })

    # ── 任务统计面板 ──
    clear_screen()
    console.print()
    console.print("[bold cyan]  一键全清 - 待处理[/bold cyan]")
    console.print()
    if video_tasks:
        console.print(f"  [green]待完成视频:[/green] {len(video_tasks)} 项")
    if all_exams:
        console.print(f"  [dodger_blue2]待完成考试/作业:[/dodger_blue2] {len(all_exams)} 项")
        for i, e in enumerate(all_exams[:15], 1):
            ename = e['node_name']
            if len(ename) > 40:
                ename = ename[:40] + "…"
            console.print(f"    [dim][{i}][/dim] {ename}")
        if len(all_exams) > 15:
            console.print(f"    [dim]...还有 {len(all_exams) - 15} 项[/dim]")
    console.print()
    console.print("[dim]  开始后按 Ctrl+C 停止[/dim]")
    console.print()

    go = Confirm.ask("[bold cyan]是否开始一键全清？[/bold cyan]", default=False)
    if not go:
        return
    clear_screen()

    stop_event = threading.Event()
    dashboard_running = True

    total_video_duration = sum(t.duration for t in video_tasks) if video_tasks else 0

    def _dash_loop():
        from rich.live import Live
        with Live(console=console, refresh_per_second=4, screen=True) as live:
            while dashboard_running and not stop_event.is_set():
                with state_lock:
                    v_done = video_state['done']
                    v_failed = video_state['failed']
                    v_total = video_state['total']
                    e_done = exam_state['done']
                    e_failed = exam_state['failed']
                    e_total = exam_state['total']
                    v_slots_copy = list(video_state['slots'])
                    e_slots_copy = list(exam_state['slots'])
                v_pct = (v_done + v_failed) / v_total if v_total > 0 else 0
                e_pct = (e_done + e_failed) / e_total if e_total > 0 else 0
                elapsed = _time.time() - video_state['start_time']

                completed_dur = 0
                remain_dur = 0
                for s in v_slots_copy:
                    s_done_dur = s['viewed'] + s['total_time']
                    if s['done'] or s['failed']:
                        completed_dur += s['duration']
                    else:
                        completed_dur += min(s_done_dur, s['duration'])
                        remain_dur += max(0, s['duration'] - s_done_dur)

                if elapsed > 5 and completed_dur > 0:
                    speed = completed_dur / elapsed
                    countdown = remain_dur / speed if speed > 0 else remain_dur
                else:
                    countdown = remain_dur

                panel = render_all_in_one_dashboard(
                    video_stats={'total': v_total, 'done': v_done, 'failed': v_failed,
                                 'progress': v_pct, 'slots': v_slots_copy},
                    exam_stats={'total': e_total, 'done': e_done, 'failed': e_failed,
                                'progress': e_pct, 'slots': e_slots_copy},
                    elapsed=elapsed,
                    total_duration=total_video_duration,
                    max_remain=remain_dur,
                    model_name="DeepSeek",
                    countdown=countdown,
                )
                live.update(panel)
                _time.sleep(0.5)
    dash_thread = threading.Thread(target=_dash_loop, daemon=True)
    dash_thread.start()

    # ── 视频线程 ──
    def _video_worker():
        if not video_tasks:
            return
        cookie_str = '; '.join([f"{c.name}={c.value}" for c in session.cookies])
        mux = StudyMultiplexer(BASE_URL, cookie_str)
        for t in video_tasks:
            mux.add_task(t)
        mux.start_all()
        DashboardDisplay.instance()._running = False
        try:
            while not stop_event.is_set():
                all_done = True
                with state_lock:
                    for i, s in enumerate(video_state['slots']):
                        if i < len(video_tasks):
                            slot = DashboardDisplay.instance()._slots.get(video_tasks[i].node_id)
                            if slot:
                                s['total_time'] = slot.get('total_time', 0)
                                s['done'] = slot.get('done', False)
                                s['failed'] = slot.get('failed', False)
                            if not s['done'] and not s['failed']:
                                all_done = False
                    if all_done:
                        video_state['done'] = video_state['total']
                    else:
                        done = sum(1 for s in video_state['slots'] if s['done'] or s['failed'])
                        video_state['done'] = done
                if all_done:
                    break
                _time.sleep(1)
        finally:
            mux.stop_all()
            with state_lock:
                for s in video_state['slots']:
                    s['done'] = True
                    s['failed'] = s.get('failed', False)

    # ── 考试线程 ──
    def _exam_worker():
        if not all_exams:
            return
        # 标记全部为"处理中"
        with state_lock:
            for s in exam_state['slots']:
                s['progress'] = 0.01
        cookies_dict = {c.name: c.value for c in session.cookies}
        headers = dict(session.headers)
        max_w = min(3, len(all_exams))
        with ThreadPoolExecutor(max_workers=max_w) as executor:
            futures = {}
            for idx, item in enumerate(all_exams):
                fut = executor.submit(
                    _do_single_work_threaded_w, item, cookies_dict, headers,
                )
                futures[fut] = idx
            for fut in as_completed(futures):
                if stop_event.is_set():
                    break
                idx = futures[fut]
                try:
                    ok = fut.result(timeout=300)
                except Exception as e:
                    ok = False
                _update_exam(idx, ok)

    def _update_exam(idx, ok):
        with state_lock:
            if idx < len(exam_state['slots']):
                exam_state['slots'][idx]['done'] = ok
                exam_state['slots'][idx]['failed'] = not ok
                exam_state['slots'][idx]['progress'] = 1.0 if ok else 0
            done = sum(1 for s in exam_state['slots'] if s['done'])
            failed = sum(1 for s in exam_state['slots'] if s['failed'])
            exam_state['done'] = done
            exam_state['failed'] = failed

    v_thread = threading.Thread(target=_video_worker, daemon=True)
    e_thread = threading.Thread(target=_exam_worker, daemon=True)

    v_thread.start()
    e_thread.start()

    try:
        while v_thread.is_alive() or e_thread.is_alive():
            _time.sleep(1)
            if stop_event.is_set():
                break
    except KeyboardInterrupt:
        stop_event.set()

    stop_event.set()
    v_thread.join(timeout=5)
    e_thread.join(timeout=5)

    dashboard_running = False
    dash_thread.join(timeout=3)
    clear_screen()

    if all_exams:
        auto_update_records(session, silent=True)

    console.print("\n[green][OK] 一键全清完成！[/green]")
    console.print("[dim]2秒后返回主菜单...[/dim]")
    _time.sleep(2)


def main():
    """主程序"""
    global CURRENT_WEBSITE, BASE_URL
    
    import atexit
    
    # 注册退出时的清理函数
    def cleanup():
        try:
            from services.auto_updater import get_auto_updater
            updater = get_auto_updater()
            updater.stop()
        except Exception as e:
            pass
    
    atexit.register(cleanup)
    
    session = httpx.Client(timeout=httpx.Timeout(30.0))
    account_config = AccountConfig()
    
    # 检查上次状态
    last_state = account_config.get_last_state()
    
    # 登录流程
    login_completed = False
    while not login_completed:
        accounts = account_config.get_accounts()
        
        if not accounts:
            # 没有账号，需要登录
            success = interactive_login_new_account(account_config, session)
            while not success:
                success = interactive_login_new_account(account_config, session)
            login_completed = True
        else:
            # 检查上次状态，如果是 login 则显示账号选择界面
            if last_state == "login":
                show_account_select_menu(accounts, account_config)
                choice = Prompt.ask("请选择")
                
                if choice == "0":
                    console.print("\n程序退出")
                    console.print()
                    Prompt.ask("按任意键退出...")
                    return
                
                if choice.lower() == "n":
                    success = interactive_login_new_account(account_config, session)
                    if success:
                        login_completed = True
                    continue
                
                if choice.lower() == "d":
                    _handle_delete_account(accounts, account_config, session)
                    continue
                
                if choice.lower() == "r":
                    username = account_config.get_current_username()
                    if not username:
                        console.print("\n[red]没有当前账号，请先选择账号或登录新账号[/red]")
                        time.sleep(1)
                        continue
                    console.print(f"\n[yellow]重新登录: {username}[/yellow]")
                    password = Prompt.ask("  密码")
                    try:
                        results = login_with_per_platform_passwords(username, password, account_config)
                        from infrastructure.study_reporter import StudyReporter
                        StudyReporter.set_shared_credentials(username, password)
                        if CURRENT_WEBSITE in results and results[CURRENT_WEBSITE][0]:
                            session.cookies.update(results[CURRENT_WEBSITE][1].cookies)
                        else:
                            for wid, (succ, sess, _) in results.items():
                                if succ:
                                    import config as cfg
                                    cfg.CURRENT_WEBSITE = wid
                                    update_url_config()
                                    save_global_config()
                                    CURRENT_WEBSITE = wid
                                    BASE_URL = cfg.BASE_URL
                                    session.cookies.update(sess.cookies)
                                    break
                        account_config.add_account(username, session)
                        from config import update_paths_for_current_account
                        update_paths_for_current_account()
                        console.print("[green]重新登录成功！[/green]")
                        account_config.set_last_state("main")
                        login_completed = True
                    except Exception as e:
                        console.print(f"\n[red]登录失败: {e}[/red]")
                        time.sleep(1)
                    continue
                
                try:
                    index = int(choice) - 1
                    if 0 <= index < len(accounts):
                        selected_account = accounts[index]
                        username = selected_account.get("username")
                        
                        console.print(f"\n[yellow]正在登录: {username}[/yellow]")
                        
                        # 尝试使用多平台Cookie登录（优先当前平台）
                        success, website_id, message = try_login_with_platform_cookie(
                            username, session, CURRENT_WEBSITE
                        )
                        
                        if not success:
                            # 当前平台失败，尝试其他平台
                            console.print("[yellow]当前平台Cookie无效，尝试其他平台...[/yellow]")
                            success, website_id, message = try_login_with_platform_cookie(
                                username, session, None
                            )
                        
                        if success:
                            # 切换到对应的平台配置
                            if website_id != CURRENT_WEBSITE:
                                import config
                                config.CURRENT_WEBSITE = website_id
                                update_url_config()
                                save_global_config()
                                CURRENT_WEBSITE = website_id
                                BASE_URL = config.BASE_URL
                                console.print(f"[green]已自动切换到平台: {WEBSITES[website_id]['name']}[/green]")
                            
                            account_config.set_current_account(username)
                            from config import update_paths_for_current_account
                            update_paths_for_current_account()
                            
                            # 检查是否需要自动初始化（当前平台）
                            if account_config.is_first_login(username):
                                init_ok = auto_initialize_account(session, account_config, username)
                                if not init_ok:
                                    # 初始化失败，让用户决定是重试还是跳过
                                    retry = Confirm.ask("初始化失败，是否重试？", default=True)
                                    if retry:
                                        init_ok = auto_initialize_account(session, account_config, username)
                                    # 无论是否重试，都继续进入主菜单
                            
                            # 启动后台自动更新
                            from services.auto_updater import get_auto_updater
                            updater = get_auto_updater()
                            updater.check_and_update(session, username, account_config)
                            
                            login_completed = True
                        else:
                            console.print(f"\n[yellow]Cookie已过期，需要重新输入 {username} 的密码[/yellow]")
                            password = Prompt.ask("  密码")
                            try:
                                # 高并发重新登录所有平台（支持各平台独立密码）
                                results = login_with_per_platform_passwords(username, password, account_config)
                                from infrastructure.study_reporter import StudyReporter
                                StudyReporter.set_shared_credentials(username, password)
                                # 使用当前平台或第一个成功的平台
                                if CURRENT_WEBSITE in results and results[CURRENT_WEBSITE][0]:
                                    session.cookies.update(results[CURRENT_WEBSITE][1].cookies)
                                else:
                                    for wid, (succ, sess, _) in results.items():
                                        if succ:
                                            import config
                                            config.CURRENT_WEBSITE = wid
                                            update_url_config()
                                            save_global_config()
                                            CURRENT_WEBSITE = wid
                                            BASE_URL = config.BASE_URL
                                            session.cookies.update(sess.cookies)
                                            break
                                
                                account_config.add_account(username, session)
                                from config import update_paths_for_current_account
                                update_paths_for_current_account()
                                
                                console.print("[green]登录成功！[/green]")
                                
                                # 检查是否需要自动初始化
                                if account_config.is_first_login(username):
                                    init_ok = auto_initialize_account(session, account_config, username)
                                    if not init_ok:
                                        # 初始化失败，让用户决定是重试还是跳过
                                        retry = Confirm.ask("初始化失败，是否重试？", default=True)
                                        if retry:
                                            init_ok = auto_initialize_account(session, account_config, username)
                                        # 无论是否重试，都继续进入主菜单
                                
                                # 启动后台自动更新
                                from services.auto_updater import get_auto_updater
                                updater = get_auto_updater()
                                updater.check_and_update(session, username, account_config)
                                
                                login_completed = True
                            except Exception as e:
                                console.print(f"\n[red]登录失败: {e}[/red]")
                                continue
                    else:
                        console.print("\n[red]无效选项！[/red]")
                        continue
                except ValueError:
                    console.print("\n[red]无效选项！[/red]")
                    continue
            else:
                # 尝试自动登录最近的账号
                last_login_account = account_config.get_last_login_account()
                if last_login_account:
                    username = last_login_account.get("username")
                    
                    # 尝试加载 Cookie
                    cookie_ok = account_config.load_account_cookie(username, session)
                    if cookie_ok and check_cookie_valid(session):
                        account_config.set_current_account(username)
                        from config import update_paths_for_current_account
                        update_paths_for_current_account()
                        
                        # 启动后台自动更新
                        from services.auto_updater import get_auto_updater
                        updater = get_auto_updater()
                        updater.check_and_update(session, username, account_config)
                        
                        login_completed = True
                    else:
                        console.print(f"\n[yellow]Cookie已过期，需要重新输入 {username} 的密码[/yellow]")
                        password = Prompt.ask("  密码")
                        try:
                            from services.auth_service import login
                            login(session, username, password)
                            from infrastructure.study_reporter import StudyReporter
                            StudyReporter.set_shared_credentials(username, password)
                            account_config.add_account(username, session)
                            from config import update_paths_for_current_account
                            update_paths_for_current_account()
                            
                            # 启动后台自动更新
                            from services.auto_updater import get_auto_updater
                            updater = get_auto_updater()
                            updater.check_and_update(session, username, account_config)
                            
                            login_completed = True
                        except Exception as e:
                            console.print(f"[red]登录失败: {e}[/red]")
                            # 显示账号选择菜单
                            show_account_select_menu(accounts, account_config)
                            choice = Prompt.ask("请选择")
                            
                            if choice == "0":
                                console.print("\n程序退出")
                                console.print()
                                Prompt.ask("按任意键退出...")
                                return
                            
                            if choice.lower() == "n":
                                success = interactive_login_new_account(account_config, session)
                                if success:
                                    login_completed = True
                                continue
                            
                            if choice.lower() == "d":
                                _handle_delete_account(accounts, account_config, session)
                                continue
                            
                            try:
                                index = int(choice) - 1
                                if 0 <= index < len(accounts):
                                    selected_account = accounts[index]
                                    username = selected_account.get("username")
                                    
                                    console.print(f"\n[yellow]正在登录: {username}[/yellow]")
                                    
                                    cookie_ok = account_config.load_account_cookie(username, session)
                                    if cookie_ok and check_cookie_valid(session):
                                        console.print("[green]Cookie有效，直接登录！[/green]")
                                        account_config.set_current_account(username)
                                        from config import update_paths_for_current_account
                                        update_paths_for_current_account()
                                        
                                        # 检查是否需要自动初始化
                                        if account_config.is_first_login(username):
                                            init_ok = auto_initialize_account(session, account_config, username)
                                            if not init_ok:
                                                # 初始化失败，让用户决定是重试还是跳过
                                                retry = Confirm.ask("初始化失败，是否重试？", default=True)
                                                if retry:
                                                    init_ok = auto_initialize_account(session, account_config, username)
                                                # 无论是否重试，都继续进入主菜单
                                        
                                        # 启动后台自动更新
                                        from services.auto_updater import get_auto_updater
                                        updater = get_auto_updater()
                                        updater.check_and_update(session, username, account_config)
                                        
                                        login_completed = True
                                    else:
                                        console.print("[red]Cookie无效，请重新登录...[/red]")
                                        password = Prompt.ask("  密码")
                                        try:
                                            from services.auth_service import login
                                            login(session, username, password)
                                            from infrastructure.study_reporter import StudyReporter
                                            StudyReporter.set_shared_credentials(username, password)
                                            account_config.add_account(username, session)
                                            from config import update_paths_for_current_account
                                            update_paths_for_current_account()
                                            
                                            console.print("[green]登录成功！[/green]")
                                            
                                            # 启动后台自动更新
                                            from services.auto_updater import get_auto_updater
                                            updater = get_auto_updater()
                                            updater.check_and_update(session, username, account_config)
                                            
                                            # 检查是否需要自动初始化
                                            if account_config.is_first_login(username):
                                                init_ok = auto_initialize_account(session, account_config, username)
                                                if not init_ok:
                                                    # 初始化失败，让用户决定是重试还是跳过
                                                    retry = Confirm.ask("初始化失败，是否重试？", default=True)
                                                    if retry:
                                                        init_ok = auto_initialize_account(session, account_config, username)
                                                    # 无论是否重试，都继续进入主菜单
                                            
                                            login_completed = True
                                        except Exception as e:
                                            console.print(f"\n[red]登录失败: {e}[/red]")
                                            continue
                                else:
                                    console.print("\n[red]无效选项！[/red]")
                                    continue
                            except ValueError:
                                console.print("\n[red]无效选项！[/red]")
                                continue
                else:
                    # 没有最近登录的账号，显示选择菜单
                    show_account_select_menu(accounts, account_config)
                    choice = Prompt.ask("请选择")
                    
                    if choice == "0":
                        console.print("\n程序退出")
                        return
                    
                    if choice.lower() == "n":
                        success = interactive_login_new_account(account_config, session)
                        if success:
                            login_completed = True
                        continue
                    
                    if choice.lower() == "d":
                        _handle_delete_account(accounts, account_config, session)
                        continue
                    
                    try:
                        index = int(choice) - 1
                        if 0 <= index < len(accounts):
                            selected_account = accounts[index]
                            username = selected_account.get("username")
                            
                            console.print(f"\n[yellow]正在登录: {username}[/yellow]")
                            
                            # 尝试使用所有平台的Cookie登录
                            login_success, website_id, message = try_login_with_platform_cookie(username, session)
                            if login_success:
                                # 更新当前平台
                                if website_id:
                                    import config
                                    config.CURRENT_WEBSITE = website_id
                                    update_url_config()
                                    save_global_config()
                                    CURRENT_WEBSITE = website_id
                                    BASE_URL = config.BASE_URL
                                    update_paths_for_current_account()
                                    console.print(f"[green]已自动切换到平台: {WEBSITES[website_id]['name']}[/green]")
                                
                                account_config.set_current_account(username)
                                login_completed = True
                            else:
                                console.print("[red]Cookie无效，请重新登录...[/red]")
                                password = Prompt.ask("  密码")
                                try:
                                    from services.auth_service import login
                                    login(session, username, password)
                                    from infrastructure.study_reporter import StudyReporter
                                    StudyReporter.set_shared_credentials(username, password)
                                    account_config.add_account(username, session)
                                    console.print("[green]登录成功！[/green]")
                                    login_completed = True
                                except Exception as e:
                                    console.print(f"\n[red]登录失败: {e}[/red]")
                                    continue
                        else:
                            console.print("\n[red]无效选项！[/red]")
                            continue
                    except ValueError:
                        console.print("\n[red]无效选项！[/red]")
                        continue

    # 登录成功，进入主菜单
    account_config.set_last_state("main")
    from config import update_paths_for_current_account
    update_paths_for_current_account()

    from infrastructure.session_logger import get_session_logger
    get_session_logger().start()

    while True:
        course_list = show_main_menu(account_config, session)

        if not course_list:
            console.print("\n[yellow]当前平台无课程数据，已自动返回登录界面[/yellow]")
            time.sleep(2)
            account_config.set_last_state("login")
            get_session_logger().stop()
            return "RELOGIN"

        choice = Prompt.ask("\n请选择").strip().lower()
        
        if choice == "s":
            clear_screen()
            if not check_cookie_valid(session):
                console.print("[yellow][!] Cookie已过期，尝试重新登录...[/yellow]")
                current_username = account_config.get_current_username()
                if current_username:
                    password = Prompt.ask("  密码")
                    login_results = login_with_per_platform_passwords(current_username, password, account_config)
                    from infrastructure.study_reporter import StudyReporter
                    StudyReporter.set_shared_credentials(current_username, password)
                    from services.multi_platform_auth import load_platform_cookie
                    load_platform_cookie(current_username, CURRENT_WEBSITE, session)
                    if check_cookie_valid(session):
                        console.print("[green][[OK]] 重新登录成功！[/green]")
                    else:
                        console.print("[red][!] 重新登录失败，请重新登录！[/red]")
                        time.sleep(2)
                        continue
                else:
                    console.print("[red][!] Cookie已过期，请重新登录！[/red]")
                    time.sleep(2)
                    continue

            from services.auto_updater import get_auto_updater
            updater = get_auto_updater()
            updater.stop()

            _handle_all_in_one(session, account_config)

            console.print("\n[green][OK] 所有任务已完成！[/green]")
            console.print("[yellow]>>> 2秒后自动返回主菜单...[/yellow]")
            time.sleep(2)
        
        elif choice == "r":
            # 刷新数据 - 从网页重新抓取课程和学习记录
            console.print("\n[yellow]>>> 正在从网页刷新数据...[/yellow]")
            
            # 检查 Cookie 有效性
            if not check_cookie_valid(session):
                console.print("[yellow][!] Cookie已过期，尝试重新登录...[/yellow]")
                current_username = account_config.get_current_username()
                if current_username:
                    password = Prompt.ask("  密码")
                    try:
                        from services.auth_service import login
                        login(session, current_username, password)
                        from infrastructure.study_reporter import StudyReporter
                        StudyReporter.set_shared_credentials(current_username, password)
                        account_config.add_account(current_username, session)
                        console.print("[green]重新登录成功！[/green]")
                    except Exception as e:
                        console.print(f"[red]重新登录失败: {e}[/red]")
                        time.sleep(2)
                        continue
                else:
                    console.print("[red][!] Cookie已过期，请重新登录！[/red]")
                    time.sleep(2)
                    continue

            # 实际从网页抓取课程
            from infrastructure.course_crawler import get_courses
            from services.auto_updater import get_auto_updater
            from services.course_service import fetch_all_courses

            console.print("[dim]正在拉取课程列表...[/dim]")
            try:
                updater = get_auto_updater()
                
                courses = get_courses(session)
                if courses:
                    course_info_dir = get_account_course_info_dir()
                    console.print(f"[dim]正在抓取 {len(courses)} 门课程详情...[/dim]")
                    fetch_all_courses(session, courses, course_info_dir, silent=True)
                    console.print(f"[green]课程数据已刷新 ({len(courses)}门)[/green]")
                else:
                    console.print("[yellow]未获取到课程列表[/yellow]")

                # 抓取学习记录
                current_username = account_config.get_current_username()
                if current_username:
                    from services.study_record_service import StudyRecordService
                    record_service = StudyRecordService(session, current_username)
                    record_service.run_auto()
                    console.print("[green]学习记录已刷新[/green]")
                
                updater.save_timestamp()
            except Exception as e:
                console.print(f"[red]刷新失败: {e}[/red]")
                time.sleep(1)
            continue

        elif choice == "a":
            _handle_ai_exam_all(session, account_config)
            continue

        elif choice == "n":
            from infrastructure.dashboard import DashboardDisplay
            from services.data_loader import DataLoader
            from services.study_service import StudyMultiplexer
            
            study_cli = StudyCLI()
            all_videos = []
            for course in study_cli.courses:
                all_videos.extend(study_cli.get_videos_from_course(course, 2))
            
            if not all_videos:
                console.print("\n[yellow]没有找到任何视频[/yellow]")
                time.sleep(1)
                continue
            
            study_records = DataLoader().load_study_records()
            unfinished = []
            for v in all_videos:
                course_name = v.get('course_name', '')
                video_name = v.get('name', '')
                progress = DataLoader().get_video_progress(course_name, video_name, study_records, v)
                if progress['status'] != '已学':
                    unfinished.append(v)
            
            if not unfinished:
                console.print("\n[green]所有视频已完成！[/green]")
                time.sleep(1)
                continue
            
            video_tasks = study_cli.create_tasks(unfinished)
            batch_size = min(len(video_tasks), 50)
            video_tasks = video_tasks[:batch_size]
            
            clear_screen()
            console.print()
            console.print("[bold cyan]  视频挂机[/bold cyan]")
            console.print()
            console.print(f"  [green]待完成视频:[/green] {len(video_tasks)} 项")
            console.print()
            for i, t in enumerate(video_tasks[:15], 1):
                vname = t.video_name
                if len(vname) > 40:
                    vname = vname[:40] + "…"
                console.print(f"    [dim][{i}][/dim] {vname}")
            if len(video_tasks) > 15:
                console.print(f"    [dim]...还有 {len(video_tasks) - 15} 项[/dim]")
            console.print()
            console.print("[dim]  开始后按 Ctrl+C 停止[/dim]")
            console.print()
            
            go = Confirm.ask("[bold cyan]是否开始视频挂机？[/bold cyan]", default=False)
            if not go:
                continue
            
            if not check_cookie_valid(session):
                console.print("[yellow][!] Cookie已过期，尝试重新登录...[/yellow]")
                current_username = account_config.get_current_username()
                if current_username:
                    password = Prompt.ask("  密码")
                    login_results = login_with_per_platform_passwords(current_username, password, account_config)
                    from infrastructure.study_reporter import StudyReporter
                    StudyReporter.set_shared_credentials(current_username, password)
                    from services.multi_platform_auth import load_platform_cookie
                    load_platform_cookie(current_username, CURRENT_WEBSITE, session)
                    if check_cookie_valid(session):
                        console.print("[green][[OK]] 重新登录成功！[/green]")
                    else:
                        console.print("[red][!] 重新登录失败，请重新登录！[/red]")
                        time.sleep(2)
                        continue
                else:
                    console.print("[red][!] Cookie已过期，请重新登录！[/red]")
                    time.sleep(2)
                    continue
            
            from services.auto_updater import get_auto_updater
            updater = get_auto_updater()
            
            cookie_str = '; '.join([f"{c.name}={c.value}" for c in session.cookies])
            clear_screen()
            dashboard = DashboardDisplay.instance()
            dashboard.set_status_hint(f"启动 {len(video_tasks)} 个视频模拟，按 Ctrl+C 可停止")
            mux = StudyMultiplexer(BASE_URL, cookie_str)
            for task in video_tasks:
                mux.add_task(task)
            mux.start_all()
            try:
                while True:
                    time.sleep(1)
                    if dashboard.all_done():
                        console.print("\n[green][OK] 所有视频已完成！[/green]")
                        break
            except KeyboardInterrupt:
                console.print("\n[yellow]收到停止信号，正在停止所有模拟...[/yellow]")
            mux.stop_all()
            time.sleep(1)
            dashboard.stop()
            time.sleep(0.5)
            clear_screen()
            
            console.print("\n[green][OK] 视频挂机完成！[/green]")
            console.print("[yellow]>>> 2秒后自动返回主菜单...[/yellow]")
            time.sleep(2)
            continue

        elif choice.lower().startswith("e"):
            try:
                idx = int(choice[1:])
                if 1 <= idx <= len(course_list):
                    selected = course_list[idx - 1]
                    if selected.get('exam_total', 0) > 0:
                        _show_exam_detail(selected, session, account_config)
                    else:
                        console.print("[yellow]该课程无考试[/yellow]")
                        time.sleep(1)
                else:
                    console.print("[red]无效编号[/red]")
                    time.sleep(0.5)
            except (ValueError, IndexError):
                console.print("[red]无效输入[/red]")
                time.sleep(0.5)
            continue
        
        elif choice == "c":
            did_switch, website_id = switch_website(session, account_config)
            if did_switch:
                account_config.set_last_state("login")
                get_session_logger().stop()
                return "RELOGIN"
            # 切换平台成功且已自动登录，直接刷新主菜单
            continue
        
        elif choice == "l":
            from services.auto_updater import get_auto_updater
            updater = get_auto_updater()
            updater.stop()
            session.cookies.clear()
            console.print("\n[green]已退出登录[/green]")
            account_config.set_last_state("login")
            get_session_logger().stop()
            return "RELOGIN"
        
        elif choice == "0":
            # 退出程序
            from services.auto_updater import get_auto_updater
            updater = get_auto_updater()
            updater.stop()
            
            console.print("[green]感谢使用，再见！[/green]")
            console.print()
            get_session_logger().stop()
            return "EXIT"
        
        else:
            try:
                idx = int(choice)
                if 1 <= idx <= len(course_list):
                    selected = course_list[idx - 1]
                    _show_course_detail(selected, session, account_config)
                else:
                    console.print("[red]无效选项！[/red]")
                    time.sleep(0.5)
            except ValueError:
                console.print("[red]无效输入！[/red]")
                time.sleep(0.5)


def _resolve_work_id(session, base_url, node_id):
    import re
    node_url = f"{base_url}/user/node?nodeId={node_id}"
    try:
        resp = session.get(node_url, follow_redirects=True, timeout=15)
        html = resp.text

        wkid = node_id
        cid = ''
        chid = ''
        nid = node_id

        m = re.search(r'href="([^"]*workId=\d+[^"]*)"', html)
        if m:
            link = m.group(1).replace('&amp;', '&')
            lm = re.search(r'workId=(\d+)', link)
            if lm: wkid = lm.group(1)
            lm = re.search(r'courseId=(\d+)', link)
            if lm: cid = lm.group(1)
            lm = re.search(r'chapterId=(\d+)', link)
            if lm: chid = lm.group(1)
            lm = re.search(r'nodeId=(\d+)', link)
            if lm: nid = lm.group(1)

            if link.startswith('/'):
                link = base_url + link
            elif not link.startswith('http'):
                link = base_url + '/' + link.lstrip('/')
            resp2 = session.get(link, follow_redirects=True, timeout=15)
            html = resp2.text
            resp = resp2

        target_url = resp.url if resp else ''
        lm = re.search(r'workId=(\d+)', target_url)
        if lm: wkid = lm.group(1)
        lm = re.search(r'courseId=(\d+)', target_url)
        if lm: cid = lm.group(1)
        lm = re.search(r'chapterId=(\d+)', target_url)
        if lm: chid = lm.group(1)
        lm = re.search(r'nodeId=(\d+)', target_url)
        if lm: nid = lm.group(1)

        rtype = 'exam' if 'examId' in target_url else 'work'

        if '.topic-item' not in html or 'data-workId' not in html:
            candidates = [
                f"{base_url}/user/work?workId={wkid}&nodeId={nid}",
                f"{base_url}/user/work?workId={wkid}",
            ]
            if cid:
                candidates.insert(0, f"{base_url}/user/work?workId={wkid}&nodeId={nid}&courseId={cid}")
            for candidate in candidates:
                resp3 = session.get(candidate, follow_redirects=True, timeout=15)
                if 'topic-item' in resp3.text or 'data-workId' in resp3.text:
                    html = resp3.text
                    resp = resp3
                    break

        return wkid, rtype, resp.url if resp else node_url, html, cid, nid
    except Exception as e:
        pass
    return node_id, 'work', None, None, '', node_id


def _get_work_records_path():
    return os.path.join(get_account_records_dir(), "work_records.json")


def _load_work_records() -> Dict:
    path = _get_work_records_path()
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            pass
    return {}


def _save_work_record(course_id: str, work_id: int, course_name: str, node_name: str):
    records = _load_work_records()
    key = f"{course_id}_{work_id}"
    records[key] = {
        "course_id": course_id,
        "work_id": work_id,
        "course_name": course_name,
        "node_name": node_name,
        "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    path = _get_work_records_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def _handle_ai_work(session):
    """AI自动答题——从课程JSON自动提取作业/考试并调用DeepSeek作答"""
    from config import DEEPSEEK_API_KEY

    clear_screen()

    if not DEEPSEEK_API_KEY:
        console.print("[red]DeepSeek API Key 未配置[/red]")
        Prompt.ask("\n按任意键返回...")
        return

    from config import get_account_course_info_dir
    from services.data_loader import DataLoader

    data_loader = DataLoader()
    courses = data_loader.load_courses(simple=True)
    if not courses:
        console.print("[yellow]未找到课程数据，请先执行 R 刷新[/yellow]")
        time.sleep(2)
        return

    work_items = []
    course_info_dir = get_account_course_info_dir()
    course_files = {}
    for fn in os.listdir(course_info_dir):
        if fn.endswith('.json'):
            fp = os.path.join(course_info_dir, fn)
            try:
                with open(fp, encoding='utf-8') as f:
                    cd = json.load(f)
                course_files[cd.get('course_name', '')] = cd
            except Exception as e:
                pass

    FINISHED_STATUSES = {'超时结束', '已阅', '已交'}
    from datetime import datetime as dt
    now = dt.now()

    study_records = data_loader.load_study_records()

    for course in courses:
        course_data = course.get('data', {})
        if not course_data:
            course_name = course.get('name', '')
            if course_name in course_files:
                course_data = course_files[course_name]
            else:
                continue
        course_name = course_data.get('course_name', '未知课程')
        course_id = course_data.get('course_id', '')
        nodes = course_data.get('nodes', [])
        for node in nodes:
            ntype = node.get('node_type', '')
            if ntype not in ('work', 'exam'):
                continue

            hidden = node.get('hidden_params', {})
            exams = hidden.get('exams', [])
            work_id = hidden.get('work_id', '')
            work_url = hidden.get('work_url', '')

            if not work_id and not exams:
                continue

            if exams:
                active_exams = []
                for ex in exams:
                    ex_status = ex.get('status', '')
                    ex_end_time = ex.get('end_time', '')
                    if ex_status in FINISHED_STATUSES:
                        continue
                    if ex_end_time:
                        try:
                            end_dt = dt.strptime(ex_end_time, '%Y-%m-%d %H:%M:%S')
                            if now > end_dt:
                                continue
                        except ValueError:
                            try:
                                end_dt = dt.strptime(ex_end_time, '%Y-%m-%d')
                                if now > end_dt:
                                    continue
                            except ValueError:
                                pass
                    active_exams.append(ex)

                if not active_exams:
                    continue

                all_not_started = all(
                    e.get('status', '') == '未开始' for e in active_exams
                )

                work_items.append({
                    'course_name': course_name,
                    'course_id': course_id,
                    'node_name': node.get('name', ''),
                    'node_id': node.get('nodeId', ''),
                    'node_type': ntype,
                    'url': node.get('url', ''),
                    'not_started': all_not_started,
                    'active_exams': active_exams,
                    'all_exams': exams,
                    'work_id': work_id,
                    'is_work': 'work' in hidden.get('types', []) and ntype == 'exam',
                    'can_answer': bool(work_id),
                })
            elif work_id:
                work_items.append({
                    'course_name': course_name,
                    'course_id': course_id,
                    'node_name': node.get('name', ''),
                    'node_id': node.get('nodeId', ''),
                    'node_type': ntype,
                    'url': work_url or node.get('url', ''),
                    'work_id': work_id,
                    'not_started': False,
                    'is_work': ntype == 'work' or 'work' in hidden.get('types', []),
                    'can_answer': True,
                })

    if not work_items:
        console.print("[yellow]所有课程均未找到可做的作业或考试（已完成/已过期的已自动过滤）[/yellow]")
        time.sleep(2)
        return

    # 显示考试仪表盘
    work_records = _load_work_records()

    # 构建 server_status_map 用于排除 [未交] 项
    server_status_map = {}
    for cn, sr in study_records.items():
        for wr in sr.get('data', {}).get('work', []):
            title = wr.get('title', '').strip()
            if title:
                server_status_map[f"{cn}_{title}"] = wr.get('status', '')

    total_pending = 0
    total_done = 0
    for item in work_items:
        iwid = item.get('work_id', '')
        icid = item.get('course_id', '')
        is_done = bool(iwid and icid and f"{icid}_{iwid}" in work_records)
        cn = item.get('course_name', '')
        nname = item.get('node_name', '')
        if server_status_map.get(f"{cn}_{nname}", '') == '未交':
            item['_skip_stats'] = True
            continue
        if is_done:
            total_done += 1
        elif not item.get('not_started', False):
            total_pending += 1
    total_count = sum(1 for it in work_items if not it.get('_skip_stats', False))

    current_website = get_current_website_config()
    platform_name = current_website.get("name", "粟湾平台")

    practice_items = [it for it in work_items if it.get('is_work', False)]
    exam_items = [it for it in work_items if not it.get('is_work', False)]

    idx = 0
    index_map = {}

    def _build_rows(items):
        nonlocal idx
        rows = []
        for item in items:
            is_gray = item.get('not_started', False)
            is_done = False
            iwid = item.get('work_id', '')
            icid = item.get('course_id', '')
            if iwid and icid:
                is_done = f"{icid}_{iwid}" in work_records

            is_weijiao = item.get('_skip_stats', False)

            tag = "练习" if item.get('is_work') else "考试"
            if is_done:
                tag_color = "green"; name_color = "green"; status_text = "[已交]"
            elif is_weijiao:
                tag_color = "dim"; name_color = "dim"; status_text = "[未交]"
            elif is_gray:
                tag_color = "dim"; name_color = "dim"; status_text = "[未开始]"
            else:
                tag_color = "yellow" if item.get('is_work') else "magenta"
                name_color = "white"; status_text = ""

            idx += 1
            is_selectable = not is_gray and not is_done and not is_weijiao and item.get('can_answer', False)
            if is_selectable:
                index_map[idx] = item
            rows.append((idx, tag, tag_color, item['node_name'], status_text, name_color, is_selectable, item['course_name']))
        return rows

    practice_rows = _build_rows(practice_items)
    exam_rows = _build_rows(exam_items)

    from infrastructure.rich_ui import render_exam_dashboard
    course_groups = [("日常练习", practice_rows), ("考试", exam_rows)]
    panel = render_exam_dashboard(platform_name, total_pending, total_done, total_count, course_groups)
    console.print(panel)

    choice = Prompt.ask("\n请选择").strip()
    if choice == "0":
        return
    if choice.lower() == "r":
        auto_update_records(session)
        _handle_ai_work(session)
        return

    if choice.lower() == "a":
        all_pending = [it for n, it in sorted(index_map.items())]
        if not all_pending:
            console.print("[yellow]没有待做的作业/考试[/yellow]")
            time.sleep(1)
            _handle_ai_work(session)
            return
        console.print(f"\n[bold cyan]共 {len(all_pending)} 个待处理[/bold cyan]")
        auto_submit = Confirm.ask("[yellow][!] 是否自动提交并交卷？[/yellow]", default=False)
        _run_batch_works(session, all_pending, auto_submit)
        console.print("\n[dim]3秒后返回AI答题页...[/dim]")
        time.sleep(3)
        _handle_ai_work(session)
        return

    try:
        sel = int(choice)
        if sel not in index_map:
            console.print("[red]无效选项[/red]")
            time.sleep(1)
            return
    except ValueError:
        console.print("[red]无效输入[/red]")
        time.sleep(1)
        return

    item = index_map[sel]

    auto_submit = Confirm.ask("[yellow][!] 是否自动提交答案并交卷？[/yellow]", default=False)
    _run_single_work(session, item, auto_submit)

    console.print("\n[dim]3秒后返回AI答题页...[/dim]")
    time.sleep(3)
    _handle_ai_work(session)
    return


def _handle_ai_exam_all(session, account_config):
    """主菜单按 [A] AI考试 —— 直接执行全部未完成的考试，不选个数，先确认"""
    from config import DEEPSEEK_API_KEY

    if not DEEPSEEK_API_KEY:
        console.print("[red]DeepSeek API Key 未配置[/red]")
        time.sleep(2)
        return

    work_records = _load_work_records()
    from services.data_loader import DataLoader
    data_loader = DataLoader()
    courses = data_loader.load_courses(simple=True)
    study_records = data_loader.load_study_records()

    all_pending = []
    for course in courses:
        cd = course.get('data', {})
        cn = cd.get('course_name', course.get('name', ''))
        cid = cd.get('course_id', '')
        nodes = cd.get('nodes', [])
        if not cid or not nodes:
            continue
        items = _build_exam_items_for_course(cn, cid, nodes, work_records, study_records)
        for it in items:
            if it['is_done'] or it['status_text'] in ('[已超时]', '[未交]'):
                continue
            if not it.get('can_answer', False):
                continue
            all_pending.append({
                'course_name': cn, 'course_id': cid,
                'node_name': it['name'], 'node_id': it['node_id'],
                'node_type': it['node_type'], 'url': it['url'],
                'work_id': it['work_id'],
                'is_work': it['tag'] == '练习',
                'hidden': {},
            })

    if not all_pending:
        console.print("[green]所有考试和练习都已完成！[/green]")
        time.sleep(2)
        return

    console.print()
    console.print(f"[bold cyan]共 {len(all_pending)} 个待处理的考试/练习[/bold cyan]")
    console.print()

    if not Confirm.ask("[yellow][!] 是否开始AI考试？[/yellow]", default=True):
        console.print("[dim]已取消[/dim]")
        time.sleep(1)
        return

    auto_submit = Confirm.ask("[yellow][!] 是否自动提交答案并交卷？[/yellow]", default=False)
    _run_batch_works(session, all_pending, auto_submit)

    console.print("\n[green][OK] 全部考试处理完毕[/green]")
    console.print("[dim]2秒后返回主菜单...[/dim]")
    time.sleep(2)


def _build_exam_items_for_course(course_name, course_id, nodes, work_records, study_records=None):
    """考试/作业列表。状态来自 server 端 study_records，已交/已阅=已完成，未交=未交，其他=未开始。"""
    done_ids = {k.split('_', 1)[1] for k in work_records if k.startswith(f"{course_id}_")}
    # 完整 server 状态映射：title -> status
    server_status_map = {}
    if study_records and course_name in study_records:
        for wr in study_records[course_name].get('data', {}).get('work', []):
            title = wr.get('title', '').strip()
            if title:
                server_status_map[title] = wr.get('status', '')

    items = []
    for node in nodes:
        ntype = node.get('node_type', '')
        if ntype not in ('work', 'exam'):
            continue
        hidden = node.get('hidden_params', {})
        node_name = node.get('name', '')
        nid = node.get('nodeId', '')
        nurl = node.get('url', '')

        wid = hidden.get('work_id', '')
        if wid:
            server_status = server_status_map.get(node_name, '')
            if wid in done_ids or server_status in ('已交', '已阅'):
                is_done = True
                status_text = '[已完成]'
            elif server_status == '未交':
                is_done = False
                status_text = '[未交]'
            else:
                is_done = False
                status_text = '[未开始]'
            tag = "练习" if (ntype == 'work' or 'work' in hidden.get('types', [])) else "考试"
            hp_exams = hidden.get('exams', [])
            _end_time = hp_exams[0].get('end_time', '') if hp_exams else ''
            items.append({
                'name': node_name, 'node_id': nid, 'work_id': wid,
                'node_type': ntype, 'url': nurl,
                'tag': tag, 'tag_color': 'yellow' if tag == '练习' else 'magenta',
                'is_done': is_done, 'status_text': status_text,
                'end_time': _end_time,
                'can_answer': True,
            })

        sub_exams = hidden.get('exams', [])
        for ex in sub_exams:
            eid = ex.get('exam_id', '')
            if not eid:
                continue
            ex_status = ex.get('status', '')
            ex_name = ex.get('title', node_name)
            if ex_status == '超时结束':
                is_done = False
                status_text = '[已超时]'
            elif (eid in done_ids) or (ex_status in ('已交', '已阅')):
                is_done = True
                status_text = '[已完成]'
            elif ex_status == '未交':
                is_done = False
                status_text = '[未交]'
            else:
                is_done = False
                status_text = '[未开始]'
            items.append({
                'name': ex_name, 'node_id': nid, 'work_id': eid,
                'node_type': ntype, 'url': nurl,
                'tag': '考试', 'tag_color': 'magenta',
                'is_done': is_done, 'status_text': status_text,
                'end_time': ex.get('end_time', ''),
                'can_answer': False,
            })

    # 排序：未完成 → 已完成 → 未交/已超时
    def _prio(it):
        s = it.get('status_text', '')
        if s == '[未开始]':
            return 0
        if s == '[已完成]':
            return 1
        return 2
    items.sort(key=_prio)
    return items


def _calc_exam_stats(exam_items):
    countable = [e for e in exam_items if e.get('status_text') != '[未交]']
    answerable = [e for e in countable if e.get('can_answer', False)]
    if not answerable:
        return len(exam_items), 0, len(exam_items), 1.0
    total = len(countable)
    done = sum(1 for e in countable if e['is_done'])
    a_done = sum(1 for e in answerable if e['is_done'])
    pct = a_done / len(answerable)
    return total, done, total - done, pct


def _show_exam_detail(exam_info, session, account_config):
    """考试详情页 —— 与课程详情页保持一致的交互逻辑"""
    from infrastructure.rich_ui import render_exam_detail

    course_name = exam_info['name']
    course_data = None
    from services.data_loader import DataLoader
    data_loader = DataLoader()
    courses = data_loader.load_courses(simple=True)
    for c in courses:
        cd = c.get('data', {})
        cn = cd.get('course_name', c.get('name', ''))
        if cn == course_name:
            course_data = cd
            break

    course_id = course_data.get('course_id', '') if course_data else ''
    nodes = course_data.get('nodes', []) if course_data else []
    work_records = _load_work_records()
    study_records = data_loader.load_study_records()

    exam_items = _build_exam_items_for_course(course_name, course_id, nodes, work_records, study_records)
    total_count, total_done, total_pending, exam_pct = _calc_exam_stats(exam_items)

    PAGE_SIZE = 10
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    current_page = 1

    while True:
        start = (current_page - 1) * PAGE_SIZE
        end = min(start + PAGE_SIZE, total_count)
        page_items = exam_items[start:end]

        rows = []
        for i, item in enumerate(page_items, 1):
            global_idx = start + i
            rows.append({
                'idx': global_idx,
                'name': item['name'],
                'tag': item['tag'],
                'tag_color': item['tag_color'],
                'is_done': item['is_done'],
                'status_text': item['status_text'],
            })

        clear_screen()
        panel = render_exam_detail(
            course_name=course_name,
            exam_pct=exam_pct,
            total_done=total_done,
            total_pending=total_pending,
            total_count=total_count,
            exam_rows=rows,
            current_page=current_page,
            total_pages=total_pages,
            has_prev=current_page > 1,
            has_next=current_page < total_pages,
        )
        console.print(panel)

        choice = Prompt.ask("\n请选择").strip().lower()
        if choice == "0":
            return
        elif choice == "s":
            pending_items = [e for e in exam_items if not e['is_done'] and e.get('can_answer', False)]
            if not pending_items:
                console.print("[green]本课所有可答题的考试已完成！[/green]")
                time.sleep(1)
                continue
            console.print(f"\n[bold cyan]共 {len(pending_items)} 个待处理[/bold cyan]")
            auto_submit = Confirm.ask("[yellow][!] 是否自动提交并交卷？[/yellow]", default=False)
            pending_full = []
            for e in pending_items:
                pending_full.append({
                    'course_name': course_name,
                    'course_id': course_id,
                    'node_name': e['name'],
                    'node_id': e['node_id'],
                    'work_id': e['work_id'],
                    'node_type': e['node_type'],
                    'url': e['url'],
                    'is_work': e['tag'] == '练习',
                })
            _run_batch_works(session, pending_full, auto_submit)
            work_records = _load_work_records()
            study_records = data_loader.load_study_records()
            exam_items = _build_exam_items_for_course(course_name, course_id, nodes, work_records, study_records)
            total_done, total_pending, exam_pct = _calc_exam_stats(exam_items)[1:]
            console.print("\n[dim]2秒后刷新...[/dim]")
            time.sleep(2)
        elif choice == "p" and current_page > 1:
            current_page -= 1
        elif choice == "n" and current_page < total_pages:
            current_page += 1
        else:
            try:
                idx = int(choice)
                if 1 <= idx <= total_count:
                    item = exam_items[idx - 1]
                    if item['is_done']:
                        console.print("[yellow]该考试已完成[/yellow]")
                        time.sleep(1)
                        continue
                    if not item.get('can_answer', False):
                        console.print("[yellow]该考试无'开始做题'入口，无法答题[/yellow]")
                        time.sleep(1)
                        continue
                    auto_submit = Confirm.ask("[yellow][!] 是否自动提交答案并交卷？[/yellow]", default=False)
                    _run_single_work(session, {
                        'course_name': course_name,
                        'course_id': course_id,
                        'node_name': item['name'],
                        'node_id': item['node_id'],
                        'work_id': item['work_id'],
                        'node_type': item['node_type'],
                        'url': item['url'],
                        'is_work': item['tag'] == '练习',
                    }, auto_submit)
                    work_records = _load_work_records()
                    study_records = data_loader.load_study_records()
                    exam_items = _build_exam_items_for_course(course_name, course_id, nodes, work_records, study_records)
                    total_done, total_pending, exam_pct = _calc_exam_stats(exam_items)[1:]
                    console.print("\n[dim]2秒后刷新...[/dim]")
                    time.sleep(2)
                else:
                    console.print("[red]无效选项[/red]")
                    time.sleep(0.5)
            except ValueError:
                console.print("[red]无效输入[/red]")
                time.sleep(0.5)


def _run_single_work(session, item, auto_submit=False, silent=False):
    """执行单个作业/考试的AI答题全流程"""
    from config import BASE_URL, DEEPSEEK_API_KEY
    from infrastructure.anti_test import AIAnswerer, OnlineHeartbeat, TopicFetcher, WorkSubmitter

    heartbeat = None
    try:
        if not silent:
            console.print()

        resolved_id, resolved_type, redirect_url, redirect_html, resolved_cid, resolved_nid = _resolve_work_id(session, BASE_URL, item['node_id'])
        course_id = int(resolved_cid) if resolved_cid else int(item.get('course_id', 0))
        node_id = int(resolved_nid) if resolved_nid else int(item['node_id'])
        work_id = int(resolved_id)

        heartbeat = OnlineHeartbeat(
            session=session,
            online_url=f'{BASE_URL}/user/online',
            login_url=f'{BASE_URL}/user/login'
        )
        heartbeat.start()

        fetcher = TopicFetcher(session, BASE_URL)
        work_data = fetcher.fetch(work_id, course_id, node_id, direct_url=redirect_url, redirect_html=redirect_html)

        if not work_data['topics']:
            if not silent:
                console.print(f"  [yellow]{item['node_name']}: 没有题目[/yellow]")
            heartbeat.stop()
            return None

        topics = work_data['topics']
        total_topics = len(topics)

        answerer = AIAnswerer(DEEPSEEK_API_KEY)
        answers = {}

        if silent:
            console.print(f"  [dim]├─ AI答题 ({total_topics}题)[/dim] ", end="")
            for i, topic in enumerate(topics):
                ai_res = answerer.ask_one_topic(topic)
                answer = ai_res.get('answer', '').strip()
                if not answer:
                    answer = 'A'
                answers[topic['topic_id']] = answer
                console.print(".", end="", highlight=False)
            console.print(" [OK]", style="green")
        else:
            ai_progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=30, complete_style="cyan", finished_style="green"),
                TextColumn("[cyan]{task.completed}/{task.total}[/cyan]"),
                console=console,
                transient=True,
            )
            with ai_progress:
                ai_task = ai_progress.add_task(
                    f"[bold cyan]AI 答题中 ({item['node_name']})[/bold cyan]",
                    total=total_topics,
                )
                for i, topic in enumerate(topics):
                    tid = topic['topic_id']
                    q = topic['question']
                    ai_progress.update(ai_task, description=f"[cyan]第{topic['number']}题[/cyan] {q[:30]}...")
                    ai_res = answerer.ask_one_topic(topic)
                    answer = ai_res.get('answer', '').strip()
                    if not answer:
                        answer = 'A'
                    answers[tid] = answer
                    ai_progress.update(ai_task, advance=1)

        filename = f"answers_{item['course_name']}_{item['node_name']}.json"
        safe_filename = filename.replace(" ", "_").replace("，", "_").replace(":", "").replace("：", "")\
                                .replace("\"", "").replace("<", "").replace(">", "").replace("|", "")\
                                .replace("?", "").replace("*", "").replace("\\", "").replace("/", "")
        output = {
            'work_id': work_data['work_id'],
            'work_title': work_data['work_title'],
            'course_name': item['course_name'],
            'node_name': item['node_name'],
            'answers': answers
        }
        with open(safe_filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        if auto_submit and work_data['node_id']:
            exam_referer = redirect_url or f"{BASE_URL}/user/work?workId={work_id}&nodeId={node_id}&courseId={course_id}"
            submitter = WorkSubmitter(session, BASE_URL, int(work_data['work_id']), exam_referer)
            last_aid = ''
            last_ans = ''

            if silent:
                console.print(f"  [dim]├─ 提交 ({total_topics}题)[/dim] ", end="")
                for topic in topics:
                    aid = topic.get('answer_id', topic.get('topic_id', ''))
                    last_aid = aid
                    ans = answers.get(topic['topic_id'], 'A')
                    last_ans = ans
                    ret = submitter.submit_topic(aid, ans)
                    if ret.get('status') == False:
                        console.print("[red]✗[/red]", end="")
                    else:
                        console.print(".", end="", highlight=False)
                    time.sleep(0.6)
                console.print(" [OK]", style="green")
            else:
                submit_progress = Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(bar_width=30, complete_style="green", finished_style="green"),
                    TextColumn("[green]{task.completed}/{task.total}[/green]"),
                    console=console,
                    transient=True,
                )
                with submit_progress:
                    sub_task = submit_progress.add_task("[bold green]正在提交答案...[/bold green]", total=total_topics)
                    for topic in topics:
                        aid = topic.get('answer_id', topic.get('topic_id', ''))
                        last_aid = aid
                        ans = answers.get(topic['topic_id'], 'A')
                        last_ans = ans
                        ret = submitter.submit_topic(aid, ans)
                        if ret.get('status') == False:
                            console.print(f"  [red][X] 提交失败 {aid}: {ret.get('msg')}[/red]")
                        submit_progress.update(sub_task, advance=1)
                        time.sleep(0.8)

            final = submitter.final_submit(last_aid, last_ans)

            if final.get('status') == False:
                if not silent:
                    console.print(f"  [red][X] 交卷失败: {final.get('msg')}[/red]")
                return False
            else:
                if silent:
                    console.print("  [dim]└─[/dim] [green]交卷成功[/green]")
                else:
                    console.print("  [green][OK] 交卷成功！[/green]")
                _save_work_record(item.get('course_id', ''), int(work_data['work_id']),
                                  item['course_name'], item['node_name'])
                return True
        else:
            if not silent:
                console.print(f"  [green][OK] 答案已保存到 {safe_filename}[/green]")
            return True

    except Exception as e:
        if not silent:
            console.print(f"  [red]AI答题出错: {e}[/red]")
        return False
    finally:
        if heartbeat:
            try:
                heartbeat.stop()
            except Exception:
                pass


def _run_batch_works(session, items, auto_submit=False):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from config import BASE_URL

    total = len(items)
    max_workers = min(3, total)
    console.print(f"\n[bold cyan]开始全部答题 {total} 项（{max_workers} 线程并发）[/bold cyan]")

    # loguru 自带格式化，无需手动调整级别

    cookies_dict = {c.name: c.value for c in session.cookies}
    headers = dict(session.headers)

    progr = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=25),
        TextColumn("{task.completed:.0f}/{task.total:.0f}"),
        console=console,
        transient=False,
    )
    task_map = {}

    for idx, item in enumerate(items):
        tid = progr.add_task(f"[dim]{item['course_name']} - {item['node_name']}[/dim]", total=100)
        task_map[idx] = tid

    progr.start()

    success_count = 0
    fail_count = 0

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for idx, item in enumerate(items):
                fut = executor.submit(
                    _do_single_work_threaded,
                    item, auto_submit, cookies_dict, headers, BASE_URL,
                    progr, task_map[idx],
                )
                futures[fut] = idx

            for fut in as_completed(futures):
                idx = futures[fut]
                item = items[idx]
                try:
                    ok = fut.result(timeout=300)
                except Exception as e:
                    ok = False
                    progr.update(task_map[idx], description=f"[red]{item['node_name']} 异常[/red]")
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
    finally:
        progr.stop()
        anti_logger.setLevel(old_level)
        for h, lv in old_handler_levels:
            h.setLevel(lv)

    console.print(f"\n[bold]全部答题完成:[/bold] [green]成功 {success_count}[/green] / [red]失败 {fail_count}[/red] / 共 {total}")

    ref_progress = Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console, transient=True)
    ref_progress.start()
    ref_task = ref_progress.add_task("[dim]正在刷新学习记录...[/dim]", total=None)
    try:
        auto_update_records(session, silent=True)
    finally:
        ref_progress.stop()


def _do_single_work_threaded(item, auto_submit, cookies_dict, headers, base_url, progr, task_id):
    import httpx as _requests

    from config import DEEPSEEK_API_KEY
    from infrastructure.anti_test import AIAnswerer, OnlineHeartbeat, TopicFetcher, WorkSubmitter

    session = _httpx.Client(timeout=httpx.Timeout(30.0))
    session.headers.update(headers)
    for k, v in cookies_dict.items():
        session.cookies.set(k, v)

    total_steps = 100
    progr.update(task_id, description=f"[dim]{item['node_name']} 解析中...[/dim]")

    try:
        heartbeat = OnlineHeartbeat(
            session=session,
            online_url=f'{base_url}/user/online',
            login_url=f'{base_url}/user/login'
        )
        heartbeat.start()

        node_url = f"{base_url}/user/node?nodeId={item['node_id']}"
        resp = session.get(node_url, follow_redirects=True, timeout=15)
        html = resp.text

        import re
        wkid = item['node_id']
        cid = item.get('course_id', '')
        nid = item['node_id']
        m = re.search(r'href="([^"]*workId=\d+[^"]*)"', html)
        if m:
            link = m.group(1).replace('&amp;', '&')
            lm = re.search(r'workId=(\d+)', link)
            if lm: wkid = lm.group(1)
            lm = re.search(r'courseId=(\d+)', link)
            if lm: cid = lm.group(1)
            lm = re.search(r'nodeId=(\d+)', link)
            if lm: nid = lm.group(1)
            if link.startswith('/'):
                link = base_url + link
            elif not link.startswith('http'):
                link = base_url + '/' + link.lstrip('/')
            resp2 = session.get(link, follow_redirects=True, timeout=15)
            html = resp2.text
            resp = resp2

        target_url = resp.url if resp else ''
        lm = re.search(r'workId=(\d+)', target_url)
        if lm: wkid = lm.group(1)
        lm = re.search(r'courseId=(\d+)', target_url)
        if lm: cid = lm.group(1)
        lm = re.search(r'nodeId=(\d+)', target_url)
        if lm: nid = lm.group(1)

        if '.topic-item' not in html:
            candidates = [
                f"{base_url}/user/work?workId={wkid}&nodeId={nid}",
                f"{base_url}/user/work?workId={wkid}",
            ]
            if cid:
                candidates.insert(0, f"{base_url}/user/work?workId={wkid}&nodeId={nid}&courseId={cid}")
            for candidate in candidates:
                resp3 = session.get(candidate, follow_redirects=True, timeout=15)
                if 'topic-item' in resp3.text:
                    html = resp3.text
                    break

        course_id = int(cid) if cid else int(item.get('course_id', 0))
        node_id = int(nid) if nid else int(item['node_id'])
        work_id = int(wkid)

        redirect_url_actual = resp.url if resp else None

        fetcher = TopicFetcher(session, base_url)
        work_data = fetcher.fetch(work_id, course_id, node_id, direct_url=redirect_url_actual, redirect_html=html)

        if not work_data or not work_data.get('topics'):
            progr.update(task_id, description=f"[yellow]{item['node_name']}: 无题目[/yellow]", completed=total_steps)
            heartbeat.stop()
            return False

        topics = work_data['topics']
        total_topics = len(topics)

        answerer = AIAnswerer(DEEPSEEK_API_KEY)
        answers = {}

        half_steps = 50
        progr.update(task_id, description=f"[cyan]AI答题[/cyan] {item['node_name']}", completed=0, total=total_steps)
        for i, topic in enumerate(topics):
            ai_res = answerer.ask_one_topic(topic)
            answer = ai_res.get('answer', '').strip() or 'A'
            answers[topic['topic_id']] = answer
            pct = (i + 1) * half_steps // total_topics
            progr.update(task_id, completed=pct)

        if auto_submit and work_data.get('node_id'):
            ref = redirect_url_actual or f"{base_url}/user/work?workId={work_id}&nodeId={node_id}&courseId={course_id}"
            submitter = WorkSubmitter(session, base_url, int(work_data['work_id']), ref)
            last_aid = ''
            last_ans = ''

            for i, topic in enumerate(topics):
                aid = topic.get('answer_id', topic.get('topic_id', ''))
                last_aid = aid
                ans = answers.get(topic['topic_id'], 'A')
                last_ans = ans
                ret = submitter.submit_topic(aid, ans)
                pct = half_steps + (i + 1) * half_steps // total_topics
                progr.update(task_id, description=f"[green]提交中[/green] {item['node_name']}", completed=pct)
                time.sleep(0.5)

            final = submitter.final_submit(last_aid, last_ans)
            if final.get('status'):
                _save_work_record(item.get('course_id', ''), int(work_data['work_id']),
                                  item['course_name'], item['node_name'])
                progr.update(task_id, description=f"[green]✓ {item['node_name']}[/green]", completed=total_steps)
                heartbeat.stop()
                return True
            else:
                progr.update(task_id, description=f"[red]交卷失败 {item['node_name']}[/red]", completed=total_steps)
                heartbeat.stop()
                return False
        else:
            progr.update(task_id, description=f"[dim]已保存 {item['node_name']}[/dim]", completed=total_steps)
            heartbeat.stop()
            return True

    except Exception as e:
        progr.update(task_id, description=f"[red]异常 {item['node_name']}[/red]", completed=total_steps)
        return False


def _show_course_detail(course_info, session, account_config):
    """显示课程详情并提供学习入口 - Rich 版"""
    from infrastructure.rich_ui import render_course_detail
    from services.data_loader import DataLoader

    data_loader = DataLoader()
    courses = data_loader.load_courses(simple=True)

    course_name = course_info['name']
    course_data = None
    for c in courses:
        if c.get('data', {}).get('course_name') == course_name:
            course_data = c.get('data', {})
            break

    if not course_data:
        console.print("[red]课程数据未找到[/red]")
        time.sleep(2)
        return

    nodes = course_data.get('nodes', [])
    videos = [n for n in nodes if n.get('node_type') == 'video']
    if not videos:
        console.print("[red]该课程没有视频[/red]")
        time.sleep(2)
        return

    PAGE_SIZE = 10
    total_pages = (len(videos) + PAGE_SIZE - 1) // PAGE_SIZE if videos else 1
    current_page = 1

    while True:
        clear_screen()
        study_records = data_loader.load_study_records()

        # 计算课程总体进度
        completed = 0
        total_viewed = 0
        total_dur = 0
        video_rows = []

        for i, video in enumerate(videos, 1):
            video_name = video.get('name', '未知视频')
            progress = data_loader.get_video_progress(course_name, video_name, study_records, video)
            viewed = progress['viewed']
            duration = progress['total']
            total_viewed += viewed
            total_dur += duration

            if duration > 0:
                pct = int(min(viewed / duration, 1.0) * 100)
                if progress['status'] == '已学' or pct >= 100:
                    status_text = '已完成'
                    completed += 1
                elif pct > 0:
                    status_text = '进行中'
                else:
                    status_text = '未开始'
            else:
                pct = 0
                status_text = '未开始'

            video_rows.append({
                'idx': i,
                'name': video_name,
                'duration': duration,
                'pct': pct,
                'status_text': status_text,
            })

        # 排序算法：优先显示进行中，再是未开始的，最后是已完成的（各类别内部按进度倒序）
        def sort_key(row):
            pct = row['pct']
            if 0 < pct < 100:
                # 进行中：优先级最高，按进度倒序
                return (0, -pct)
            elif pct == 0:
                # 未开始：优先级次之
                return (1, 0)
            else:
                # 已完成：优先级最低，按进度倒序（都是100%）
                return (2, -pct)

        video_rows.sort(key=sort_key)
        # 重新编号
        for i, row in enumerate(video_rows, 1):
            row['idx'] = i

        course_pct = int(completed / len(videos) * 100) if videos else 0

        # 分页
        start_idx = (current_page - 1) * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, len(video_rows))
        page_rows = video_rows[start_idx:end_idx]

        panel = render_course_detail(
            course_name=course_name,
            course_pct=course_pct,
            total_viewed=total_viewed,
            total_dur=total_dur,
            completed=completed,
            total_videos=len(videos),
            video_rows=page_rows,
            current_page=current_page,
            total_pages=total_pages,
            has_prev=current_page > 1,
            has_next=current_page < total_pages,
        )
        console.print(panel)

        choice = Prompt.ask("\n请选择").strip().lower()

        if choice == "0":
            return
        elif choice == "n" and current_page < total_pages:
            current_page += 1
            continue
        elif choice == "p" and current_page > 1:
            current_page -= 1
            continue
        elif choice == "s":
            # 学习本课程所有未完成
            study_cli = StudyCLI()
            # 找到对应课程
            for c in study_cli.courses:
                if c.get('course_name') == course_name:
                    study_cli.selected_course_id = c.get('course_id')
                    study_cli.selected_course_name = course_name
                    break
            
            unfinished = [v for v in videos if data_loader.get_video_progress(course_name, v.get('name', ''), study_records, v)['status'] != '已学']
            if not unfinished:
                console.print("\n[yellow][!] 该课程没有未完成的视频[/yellow]")
                time.sleep(2)
                continue
            
            tasks = study_cli.create_tasks(unfinished, course_name)
            if not tasks:
                continue
            
            if not check_cookie_valid(session):
                console.print("[yellow][!] Cookie已过期，尝试重新登录...[/yellow]")
                # 获取当前用户名
                current_username = account_config.get_current_username()
                if current_username:
                    # 重新获取密码
                    password = Prompt.ask("  密码")
                    # 重新登录所有平台（支持各平台独立密码）
                    login_results = login_with_per_platform_passwords(current_username, password, account_config)
                    from infrastructure.study_reporter import StudyReporter
                    StudyReporter.set_shared_credentials(current_username, password)
                    # 重新加载 Cookie
                    from services.multi_platform_auth import load_platform_cookie
                    load_platform_cookie(current_username, CURRENT_WEBSITE, session)
                    # 检查是否登录成功
                    if check_cookie_valid(session):
                        console.print("[green][[OK]] 重新登录成功！[/green]")
                    else:
                        console.print("[red][!] 重新登录失败，请重新登录！[/red]")
                        time.sleep(2)
                        continue
                else:
                    console.print("[red][!] Cookie已过期，请重新登录！[/red]")
                    time.sleep(2)
                    continue
            
            from services.auto_updater import get_auto_updater
            updater = get_auto_updater()
            
            cookie_str = '; '.join([f"{c.name}={c.value}" for c in session.cookies])
            console.print(f"[green]共加载 {len(tasks)} 个视频任务[/green]")
            time.sleep(2)
            clear_screen()
            dashboard = DashboardDisplay.instance()
            dashboard.set_status_hint(f"启动 {len(tasks)} 个视频模拟，按 Ctrl+C 可停止")
            mux = StudyMultiplexer(BASE_URL, cookie_str)
            for task in tasks:
                mux.add_task(task)
            mux.start_all()
            try:
                while True:
                    time.sleep(1)
                    if dashboard.all_done():
                        console.print("\n[green][OK] 所有视频已完成！[/green]")
                        break
            except KeyboardInterrupt:
                console.print("\n[yellow]收到停止信号，正在停止所有模拟...[/yellow]")
            mux.stop_all()
            time.sleep(1)
            # 等待仪表盘线程完全结束
            dashboard.stop()
            time.sleep(0.5)
            clear_screen()
            
            auto_update_records(session, study_cli.selected_course_id, study_cli.selected_course_name)

            # 检查是否全部完成
            study_records_check = data_loader.load_study_records()
            all_done = True
            for v in videos:
                p = data_loader.get_video_progress(course_name, v.get('name', ''), study_records_check, v)
                if p['status'] != '已学':
                    all_done = False
                    break
            if all_done:
                console.print("\n[green][OK] 该课程全部完成！返回主菜单...[/green]")
                time.sleep(2)
                return

            console.print("\n[yellow]>>> 2秒后自动返回...[/yellow]")
            time.sleep(2)
        else:
            try:
                vid_idx = int(choice)
                if 1 <= vid_idx <= len(videos):
                    # 单个视频学习
                    selected_video = videos[vid_idx - 1]
                    study_cli = StudyCLI()
                    for c in study_cli.courses:
                        if c.get('course_name') == course_name:
                            study_cli.selected_course_id = c.get('course_id')
                            study_cli.selected_course_name = course_name
                            break
                    
                    tasks = study_cli.create_tasks([selected_video], course_name)
                    if tasks:
                        if not check_cookie_valid(session):
                            console.print("[yellow][!] Cookie已过期，尝试重新登录...[/yellow]")
                            # 获取当前用户名
                            current_username = account_config.get_current_username()
                            if current_username:
                                # 重新获取密码
                                password = Prompt.ask("  密码")
                                # 重新登录所有平台（支持各平台独立密码）
                                login_results = login_with_per_platform_passwords(current_username, password, account_config)
                                from infrastructure.study_reporter import StudyReporter
                                StudyReporter.set_shared_credentials(current_username, password)
                                # 重新加载 Cookie
                                from services.multi_platform_auth import load_platform_cookie
                                load_platform_cookie(current_username, CURRENT_WEBSITE, session)
                                # 检查是否登录成功
                                if check_cookie_valid(session):
                                    console.print("[green][[OK]] 重新登录成功！[/green]")
                                else:
                                    console.print("[red][!] 重新登录失败，请重新登录！[/red]")
                                    time.sleep(2)
                                    continue
                            else:
                                console.print("[red][!] Cookie已过期，请重新登录！[/red]")
                                time.sleep(2)
                                continue
                        
                        from services.auto_updater import get_auto_updater
                        updater = get_auto_updater()
                        
                        cookie_str = '; '.join([f"{c.name}={c.value}" for c in session.cookies])
                        dashboard = DashboardDisplay.instance()
                        dashboard.set_status_hint("启动 1 个视频模拟，按 Ctrl+C 可停止")
                        mux = StudyMultiplexer(BASE_URL, cookie_str)
                        mux.add_task(tasks[0])
                        mux.start_all()
                        try:
                            while True:
                                time.sleep(1)
                                if dashboard.all_done():
                                    break
                        except KeyboardInterrupt:
                            console.print("\n[yellow]收到停止信号...[/yellow]")
                        mux.stop_all()
                        time.sleep(1)
                        # 等待仪表盘线程完全结束
                        dashboard.stop()
                        time.sleep(0.5)
                        clear_screen()
                        
                        auto_update_records(session, study_cli.selected_course_id, study_cli.selected_course_name)

                        # 检查是否全部完成
                        study_records_check = data_loader.load_study_records()
                        all_done = True
                        for v in videos:
                            p = data_loader.get_video_progress(course_name, v.get('name', ''), study_records_check, v)
                            if p['status'] != '已学':
                                all_done = False
                                break
                        if all_done:
                            console.print("\n[green][OK] 该课程全部完成！返回主菜单...[/green]")
                            time.sleep(2)
                            return

                        console.print("\n[yellow]>>> 2秒后自动返回...[/yellow]")
                        time.sleep(2)
                else:
                    console.print("[red]无效选项！[/red]")
                    time.sleep(0.5)
            except ValueError:
                console.print("[red]无效输入！[/red]")
                time.sleep(0.5)


def check_windows_version():
    if sys.platform != 'win32':
        return
    import platform
    ver = platform.version().split('.')
    major, minor = int(ver[0]), int(ver[1])
    if (major, minor) < (6, 1):
        console.print("[red]当前系统版本过低，仅支持 Windows 7 及以上系统[/red]")
        console.print("[dim]按任意键退出...[/dim]")
        input()
        sys.exit(1)


def run_program():
    """运行程序，处理退出和重启"""
    check_windows_version()
    while True:
        try:
            result = main()
            if result == "RESTART":
                console.print("\n" + "=" * 60)
                console.print("正在重新初始化...")
                console.print("=" * 60)
                console.print()
                continue
            elif result == "RELOGIN":
                console.print("\n" + "=" * 60)
                console.print("返回登录界面...")
                console.print("=" * 60)
                console.print()
                continue
            else:
                break
        except KeyboardInterrupt:
            console.print("\n\n[yellow]程序已退出。[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]程序出错: {e}[/red]")
            break


if __name__ == "__main__":
    run_program()

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time

from rich.align import Align
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from config import get_account_dir
from infrastructure.rich_ui import (
    console,
    render_course_select_menu,
    render_settings_menu,
    render_simple_menu,
    render_task_summary,
    render_video_list_table,
)
from models import CourseTask
from services.data_loader import DataLoader


class StudyCLI:
    def __init__(self):
        self.data_loader = DataLoader()
        self.reload()
        self.current_batch = 0
        self.total_batches = 0
        self.batch_size = 10
        self.current_tasks = []
        self.settings = {
            'simulation_speed': 1.0,
            'heartbeat_interval': 120,
            'report_interval': 30,
            'test_mode': False
        }
        self.selected_course_id = None
        self.selected_course_name = None
        self.STATE_FILE = os.path.join(get_account_dir(), 'last_study_state.json')

    def reload(self):
        self.courses = self.data_loader.load_courses()
        self.study_records = self.data_loader.load_study_records()

    def _save_last_state(self, course_id, course_name, video_ids=None):
        try:
            data = {'course_id': course_id, 'course_name': course_name}
            if video_ids:
                data['video_ids'] = video_ids
            with open(self.STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception as e:
            pass

    def _load_last_state(self):
        if not os.path.exists(self.STATE_FILE):
            return None, None, None
        try:
            with open(self.STATE_FILE, encoding='utf-8') as f:
                data = json.load(f)
            return data.get('course_id'), data.get('course_name'), data.get('video_ids')
        except Exception as e:
            return None, None, None

    def get_course_status(self, course):
        if 'data' in course:
            course_data = course.get('data', {})
            course_name = course_data.get('course_name', course.get('name', ''))
        else:
            course_data = course
            course_name = course.get('course_name', course.get('name', ''))
        nodes = course_data.get('nodes', [])
        videos = [n for n in nodes if n.get('node_type') == 'video']
        total = len(videos)
        completed = 0
        for video in videos:
            video_name = video.get('name', '')
            progress = self.data_loader.get_video_progress(course_name, video_name, self.study_records, video)
            if progress['status'] == '已学' or (progress['total'] > 0 and progress['viewed'] >= progress['total']):
                completed += 1
        completion_rate = str(int(completed / total * 100)) + '%' if total > 0 else 'N/A'
        return {'total': total, 'completed': completed, 'completion_rate': completion_rate}

    def get_videos_from_course(self, course, filter_type=1):
        if 'data' in course:
            course_data = course.get('data', {})
            course_name = course_data.get('course_name', course.get('name', ''))
        else:
            course_data = course
            course_name = course.get('course_name', course.get('name', ''))
        nodes = course_data.get('nodes', [])
        videos = [n for n in nodes if n.get('node_type') == 'video']
        result = []
        for video in videos:
            video_name = video.get('name', '')
            progress = self.data_loader.get_video_progress(course_name, video_name, self.study_records, video)
            is_completed = progress['status'] == '已学'
            viewed = progress['viewed']
            duration = progress['total']
            pct = viewed / duration if duration > 0 else 0
            if filter_type == 1:
                result.append(video)
            elif filter_type == 2 and not is_completed:
                result.append(video)
            elif filter_type == 3 and 0 < pct < 1.0 and not is_completed:
                result.append(video)
            elif filter_type == 4 and pct == 0 and not is_completed:
                result.append(video)
        return result

    def filter_videos(self, videos, course_name, filter_type=2):
        result = []
        for video in videos:
            video_name = video.get('name', '')
            progress = self.data_loader.get_video_progress(course_name, video_name, self.study_records, video)
            viewed = progress['viewed']
            duration = progress['total']
            pct = viewed / duration if duration > 0 else 0
            if filter_type == 2 and pct < 1.0:
                result.append(video)
            elif filter_type == 3 and 0 < pct < 1.0:
                result.append(video)
            elif filter_type == 4 and pct == 0:
                result.append(video)
        return result

    def show_main_menu(self):
        console.clear()
        buttons = Text()
        buttons.append("[1]", style="bold yellow")
        buttons.append(" 继续上次学习  ", style="white")
        buttons.append("[2]", style="bold yellow")
        buttons.append(" 快速学习未完成  ", style="white")
        buttons.append("[3]", style="bold yellow")
        buttons.append(" 选择课程学习  ", style="white")
        buttons.append("[4]", style="bold yellow")
        buttons.append(" 选择视频学习  ", style="white")
        buttons.append("[5]", style="bold yellow")
        buttons.append(" 学习设置  ", style="white")
        buttons.append("[6]", style="bold red")
        buttons.append(" 返回主菜单", style="white")
        panel = render_simple_menu(
            title="学习模拟",
            items=["请选择学习方式:"],
            footer_buttons=buttons,
        )
        console.print(panel)
        while True:
            try:
                choice = IntPrompt.ask('请选择')
                if 1 <= choice <= 6:
                    return choice
                console.print('[red]输入无效，请重新输入[/red]')
            except ValueError:
                console.print('[red]请输入有效的数字[/red]')

    def show_video_count_menu(self, video_count=0):
        from rich.console import Console
        _console = Console()
        _console.clear()
        from rich import box
        from rich.text import Text

        term_width = min(_console.width or 80, 80)
        inner_width = min(term_width - 6, 74)

        table = Table(show_header=False, box=None, padding=(0, 0), collapse_padding=True, width=inner_width)
        table.add_column(justify="left")

        # 顶部信息 - 已找到视频数量
        if video_count > 0:
            info_text = Text()
            info_text.append(">>> 已找到 ", style="green")
            info_text.append(f"{video_count}", style="bold green")
            info_text.append(" 个未完成视频", style="green")
            table.add_row(info_text)
            table.add_row("")

        # 选项列表 - 使用 Text 拼接实现真正的紧凑排列
        options_text = Text()
        options = [
            ("1", "5个视频"),
            ("2", "10个视频"),
            ("3", "15个视频"),
            ("4", "全部视频"),
            ("5", "自定义数量"),
        ]
        for i, (idx, desc) in enumerate(options):
            if i > 0:
                options_text.append("\n")  # 只换一行，不加额外空行
            options_text.append(f"[{idx}]", style="dim")
            options_text.append(f" {desc}", style="white")
            if idx == "4":
                options_text.append(" 夯到爆!", style="bold red")

        table.add_row(options_text)
        table.add_row("")

        # 底部按钮 - 右下角
        buttons = Text()
        buttons.append("[0]", style="dim")
        buttons.append(" 返回", style="white")
        table.add_row(Align.right(buttons))

        panel = Panel(
            table,
            title="[bold cyan]视频数量[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
            width=term_width,
        )
        _console.print(panel)
        _console.print()

        choice = self._safe_input_int('请选择', None, 0, 5)
        if choice == 0:
            return 0
        elif choice == 1:
            return 5
        elif choice == 2:
            return 10
        elif choice == 3:
            return 15
        elif choice == 4:
            return video_count if video_count > 0 else 9999
        else:
            return self._safe_input_int('请输入视频数量', 10, 1, 100)

    def show_video_filter_menu(self):
        console.clear()
        panel = render_simple_menu(
            title="视频范围",
            items=["1. 所有视频", "2. 未完成视频 [推荐]", "3. 进行中视频", "4. 未开始视频"],
            footer_buttons=Text.from_markup("[dim][0][/dim] 返回"),
        )
        console.print(panel)
        return self._safe_input_int('请选择', None, 0, 4)

    def show_course_menu(self):
        console.clear()
        if not self.courses:
            console.print('[yellow]未找到任何课程信息，请先执行功能1抓取课程信息。[/yellow]')
            return None

        panel = render_course_select_menu(self.courses, self.get_course_status, self.study_records)
        console.print(panel)

        while True:
            choice = Prompt.ask('请选择').strip().lower()
            if choice == '0' or choice == 'q':
                return None
            try:
                selection = int(choice)
                if 1 <= selection <= len(self.courses):
                    return self.courses[selection - 1]
                console.print('[red]输入无效，请重新输入[/red]')
            except ValueError:
                console.print('[red]请输入有效的数字或 [0] 返回[/red]')

    def show_settings_menu(self):
        console.clear()
        if not self.courses:
            console.print('[yellow]未找到任何课程信息，请先执行功能1抓取课程信息。[/yellow]')
            return self.settings

        panel = render_settings_menu(self.settings)
        console.print(panel)

        while True:
            choice = Prompt.ask('请选择').strip().lower()
            if choice == '0' or choice == 'q':
                break
            try:
                selection = int(choice)
                if selection == 1:
                    speed = float(Prompt.ask('请输入模拟速度 (0.5-2.0)'))
                    if 0.5 <= speed <= 2.0:
                        self.settings['simulation_speed'] = speed
                elif selection == 2:
                    interval = int(Prompt.ask('请输入心跳间隔 (60-300秒)'))
                    if 60 <= interval <= 300:
                        self.settings['heartbeat_interval'] = interval
                elif selection == 3:
                    interval = int(Prompt.ask('请输入上报间隔 (10-60秒)'))
                    if 10 <= interval <= 60:
                        self.settings['report_interval'] = interval
                else:
                    console.print('[red]输入无效，请重新输入[/red]')
                    continue
                return self.show_settings_menu()
            except ValueError:
                console.print('[red]请输入有效的数字或 [0] 返回[/red]')
        return self.settings

    def _safe_input_int(self, prompt, default, min_val=None, max_val=None):
        while True:
            try:
                value = int(Prompt.ask(prompt))
                if min_val is not None and value < min_val:
                    continue
                if max_val is not None and value > max_val:
                    continue
                return value
            except ValueError:
                if default is not None:
                    return default
                console.print('[red]请输入有效的数字[/red]')

    def show_task_summary(self, tasks, batch_num, total_batches):
        console.clear()
        panel = render_task_summary(tasks, batch_num, total_batches, self.settings)
        console.print(panel)
        confirm = Prompt.ask('是否开始学习？(y/n)').strip().lower()
        return confirm == 'y'

    def create_tasks(self, videos, course_name=None):
        tasks = []
        course_name = course_name or self.selected_course_name
        for video in videos:
            duration_str = video.get('hidden_params', {}).get('video-duration')
            if duration_str:
                duration = int(duration_str)
            else:
                duration = 600
            # 获取已有观看进度
            video_name = video.get('name', '')
            progress = self.data_loader.get_video_progress(course_name, video_name, self.study_records, video)
            viewed_duration = progress['viewed']
            task = CourseTask(
                course_name=course_name,
                video_name=video_name,
                node_id=video.get('nodeId', ''),
                duration=duration,
                viewed_duration=viewed_duration
            )
            tasks.append(task)
        return tasks

    def _process_batch_and_return(self, videos, course_name, batch_size):
        self.current_tasks = self.create_tasks(videos, course_name)
        self.total_batches = (len(self.current_tasks) + batch_size - 1) // batch_size
        self.current_batch = 0
        actual_batch = self.current_tasks[:batch_size]
        return actual_batch, self.settings, len(actual_batch)

    def _display_video_list(self, videos, course_name):
        console.clear()
        panel = render_video_list_table(videos, course_name, self.data_loader.get_video_progress, self.study_records)
        console.print(panel)

    def _handle_continue_learning(self):
        self.selected_course_id = None
        self.selected_course_name = None

        last_id, last_name, last_video_ids = self._load_last_state()
        if not last_id:
            console.print('\n[yellow][!] 无学习记录，自动跳转至课程选择...[/yellow]')
            time.sleep(1)
            return self._handle_select_course()

        course = None
        for c in self.courses:
            if c.get('course_id') == last_id:
                course = c
                break

        if not course:
            console.print('\n[yellow][!] 课程已失效，自动跳转至课程选择...[/yellow]')
            time.sleep(1)
            return self._handle_select_course()

        self.selected_course_id = last_id
        self.selected_course_name = last_name
        course_name = course.get('course_name', '')

        if last_video_ids:
            all_course_videos = [n for n in course.get('nodes', []) if n.get('node_type') == 'video']
            videos = [v for v in all_course_videos if v.get('nodeId') in last_video_ids]
            if not videos:
                console.print('\n[yellow][!] 视频已完成，自动跳转至课程选择...[/yellow]')
                time.sleep(1)
                return self._handle_select_course()
            filtered = self.filter_videos(videos, course_name, 2)
            if not filtered:
                console.print('\n[yellow][!] 视频已完成，自动跳转至课程选择...[/yellow]')
                time.sleep(1)
                return self._handle_select_course()
            videos = filtered
            console.print()
            console.print(f'[green]>>> 继续学习: {course_name}[/green]')
            console.print(f'[dim]>>> 上次选了{len(last_video_ids)}个，剩余{len(videos)}个未完成[/dim]')
        else:
            videos = self.get_videos_from_course(course, 2)
            if not videos:
                console.print('\n[yellow][!] 该课程无未完成视频，自动跳转至课程选择...[/yellow]')
                time.sleep(1)
                return self._handle_select_course()
            console.print()
            console.print(f'[green]>>> 继续学习: {course_name}[/green]')
            console.print(f'[dim]>>> 检测到 {len(videos)}个未完成视频[/dim]')

        batch_size = self.show_video_count_menu()
        if batch_size == 0:
            return [], {}, 0
        return self._process_batch_and_return(videos, course_name, batch_size)

    def _handle_quick_study(self):
        self.selected_course_id = None
        self.selected_course_name = None
        self._save_last_state(None, None, None)
        all_videos = []
        for course in self.courses:
            videos = self.get_videos_from_course(course, 2)
            all_videos.extend(videos)
        if not all_videos:
            console.print('\n[yellow][!] 没有未完成的视频[/yellow]')
            time.sleep(1)
            return [], {}, 0
        batch_size = self.show_video_count_menu(len(all_videos))
        if batch_size == 0:
            return [], {}, 0
        return self._process_batch_and_return(all_videos, None, batch_size)

    def _handle_select_course(self):
        course = self.show_course_menu()
        if course is None:
            return [], {}, 0
        self.selected_course_id = course.get('course_id')
        self.selected_course_name = course.get('course_name', '')
        filter_type = self.show_video_filter_menu()
        if filter_type == 0:
            return [], {}, 0
        videos = self.get_videos_from_course(course, filter_type)
        if not videos:
            console.print('\n[yellow][!] 该课程没有符合条件的视频[/yellow]')
            time.sleep(1)
            return [], {}, 0
        course_name = course.get('course_name', '')
        self._display_video_list(videos, course_name)
        console.print()
        console.print(f'[green]>>> 已选择 {len(videos)}个视频[/green]')
        batch_size = self.show_video_count_menu()
        if batch_size == 0:
            return [], {}, 0
        return self._process_batch_and_return(videos, course_name, batch_size)

    def _handle_select_videos(self):
        course = self.show_course_menu()
        if course is None:
            return [], {}, 0
        self.selected_course_id = course.get('course_id')
        self.selected_course_name = course.get('course_name', '')
        videos = [n for n in course.get('nodes', []) if n.get('node_type') == 'video']
        if not videos:
            console.print('\n[yellow][!] 该课程没有视频内容[/yellow]')
            time.sleep(1)
            return [], {}, 0
        course_name = course.get('course_name', '')
        self._display_video_list(videos, course_name)
        console.print()
        selected = Prompt.ask('请输入要学习的视频编号，用逗号分隔').strip()
        if not selected:
            return [], {}, 0
        try:
            indices = [int(i.strip()) for i in selected.split(',')]
            selected_videos = [videos[i-1] for i in indices if 1 <= i <= len(videos)]
        except ValueError:
            console.print('\n[yellow][!] 输入无效[/yellow]')
            time.sleep(1)
            return [], {}, 0
        if not selected_videos:
            return [], {}, 0
        self._save_last_state(course.get('course_id'), course_name, [v.get('nodeId') for v in selected_videos])
        batch_size = self.show_video_count_menu()
        if batch_size == 0:
            return [], {}, 0
        return self._process_batch_and_return(selected_videos, course_name, batch_size)

    def _handle_settings(self):
        return self.show_settings_menu()

    def run(self):
        while True:
            choice = self.show_main_menu()
            if choice == 6:
                return None, {}, 0
            elif choice == 1:
                return self._handle_continue_learning()
            elif choice == 2:
                return self._handle_quick_study()
            elif choice == 3:
                return self._handle_select_course()
            elif choice == 4:
                return self._handle_select_videos()
            elif choice == 5:
                result = self._handle_settings()
                if result is None:
                    return None, {}, 0
                continue

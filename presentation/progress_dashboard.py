import threading
import time

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

from services.data_loader import DataLoader

console = Console()


class ProgressDashboard:
    def __init__(self, session, username, account_config):
        self.session = session
        self.username = username
        self.account_config = account_config
        self.data_loader = DataLoader()
        self.running = False
        self.thread = None
        self.update_interval = 30

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def _update_loop(self):
        while self.running:
            try:
                self.data_loader.reload()
                time.sleep(self.update_interval)
            except Exception as e:
                time.sleep(5)

    def get_overall_progress(self):
        courses = self.data_loader.load_courses(simple=True)
        study_records = self.data_loader.load_study_records()
        total_videos = 0
        completed_videos = 0
        total_duration = 0
        total_viewed = 0
        for course in courses:
            course_data = course.get('data', {})
            course_name = course_data.get('course_name', course.get('name', ''))
            nodes = course_data.get('nodes', [])
            videos = [n for n in nodes if n.get('node_type') == 'video']
            total_videos += len(videos)
            for video in videos:
                video_name = video.get('name', '')
                progress = self.data_loader.get_video_progress(course_name, video_name, study_records, video)
                if progress['status'] == '已学' or (progress['total'] > 0 and progress['viewed'] >= progress['total']):
                    completed_videos += 1
                total_duration += progress['total']
                total_viewed += progress['viewed']
        overall_pct = completed_videos / total_videos if total_videos > 0 else 0
        return {
            'total_videos': total_videos,
            'completed_videos': completed_videos,
            'overall_pct': overall_pct,
            'total_duration': total_duration,
            'total_viewed': total_viewed,
        }

    def get_course_progress_list(self):
        courses = self.data_loader.load_courses(simple=True)
        study_records = self.data_loader.load_study_records()
        course_list = []
        for course in courses:
            course_data = course.get('data', {})
            course_name = course_data.get('course_name', course.get('name', ''))
            nodes = course_data.get('nodes', [])
            videos = [n for n in nodes if n.get('node_type') == 'video']
            total = len(videos)
            if total == 0:
                continue
            completed = 0
            for video in videos:
                video_name = video.get('name', '')
                progress = self.data_loader.get_video_progress(course_name, video_name, study_records, video)
                if progress['status'] == '已学' or (progress['total'] > 0 and progress['viewed'] >= progress['total']):
                    completed += 1
            pct = completed / total
            course_list.append({
                'name': course_name,
                'completed': completed,
                'total': total,
                'pct': pct,
            })
        return course_list

    def _fmt_time(self, seconds):
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

    def render(self):
        overall = self.get_overall_progress()
        courses = self.get_course_progress_list()

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="overall", size=6),
            Layout(name="courses"),
            Layout(name="footer", size=3),
        )

        header_text = Text("学习进度仪表盘", style="bold cyan", justify="center")
        layout["header"].update(Panel(header_text, border_style="cyan"))

        overall_table = Table(show_header=False, box=None, padding=(0, 2))
        overall_table.add_column("指标", style="bold")
        overall_table.add_column("数值", style="green")
        overall_table.add_row("总视频数", str(overall['total_videos']))
        overall_table.add_row("已完成", str(overall['completed_videos']))
        overall_table.add_row("总时长", self._fmt_time(overall['total_duration']))
        overall_table.add_row("已观看", self._fmt_time(overall['total_viewed']))

        bar = Progress(
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        )
        bar.add_task("overall", completed=int(overall['overall_pct'] * 100), total=100)

        overall_panel = Panel(
            Text.assemble(
                ("总体进度\n", "bold underline"),
                bar,
                "\n",
                overall_table,
            ),
            title="总体",
            border_style="green",
        )
        layout["overall"].update(overall_panel)

        course_table = Table(title="课程进度", box=None, padding=(0, 1))
        course_table.add_column("课程", style="bold")
        course_table.add_column("进度", style="green")
        course_table.add_column("完成/总数", style="dim")
        for c in courses:
            bar_str = "█" * int(c['pct'] * 20) + "░" * (20 - int(c['pct'] * 20))
            course_table.add_row(
                c['name'],
                f"{bar_str} {int(c['pct'] * 100)}%",
                f"{c['completed']}/{c['total']}",
            )
        layout["courses"].update(Panel(course_table, border_style="blue"))

        footer_text = Text("按 [Ctrl+C] 退出仪表盘", style="dim", justify="center")
        layout["footer"].update(Panel(footer_text, border_style="dim"))

        return layout

    def show(self):
        try:
            with Live(self.render(), refresh_per_second=1, console=console) as live:
                while self.running:
                    time.sleep(1)
                    live.update(self.render())
        except KeyboardInterrupt:
            self.stop()
            console.print("\n[yellow]仪表盘已关闭[/yellow]")

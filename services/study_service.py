import json
import os
from typing import Dict, List, Optional

from config import TEST_MODE, TEST_VIDEO_COUNT
from infrastructure.dashboard import DashboardDisplay
from infrastructure.heartbeat import HeartbeatKeeper
from infrastructure.rich_ui import console
from infrastructure.study_reporter import StudyReporter
from models import CourseTask


class StudyMultiplexer:
    def __init__(self, base_url: str, cookie_str: str):
        self.base_url = base_url
        self.cookie_str = cookie_str
        self.reporters: Dict[str, StudyReporter] = {}
        self.heartbeat: Optional[HeartbeatKeeper] = None

    def add_task(self, task: CourseTask):
        if task.node_id in self.reporters:
            raise ValueError(f"任务 {task.node_id} 已存在")
        reporter = StudyReporter(
            base_url=self.base_url,
            node_id=task.node_id,
            cookie_str=self.cookie_str,
            video_duration=task.duration,
            report_interval=task.report_interval,
            viewed_duration=task.viewed_duration,
            course_name=task.course_name,
            video_name=task.video_name
        )
        self.reporters[task.node_id] = reporter

    def start_all(self):
        dash = DashboardDisplay.instance()
        dash.debug("[mux] 启动心跳保活...")
        if self.heartbeat is None:
            self.heartbeat = HeartbeatKeeper(self.base_url, self.cookie_str)
            self.heartbeat.start()
        dash.debug(f"[mux] 启动 {len(self.reporters)} 个学习上报线程...")
        for reporter in self.reporters.values():
            reporter.start()
        dash.start()

    def stop_all(self):
        for reporter in self.reporters.values():
            reporter.stop()
        if self.heartbeat:
            self.heartbeat.stop()
        DashboardDisplay.instance().stop()

    def wait_all(self):
        for reporter in self.reporters.values():
            if reporter._thread:
                reporter._thread.join()

    def get_status(self) -> Dict:
        total = len(self.reporters)
        done = 0
        running = 0
        for r in self.reporters.values():
            if r._thread and r._thread.is_alive():
                running += 1
            elif r._thread and not r._thread.is_alive():
                done += 1
        return {
            "total": total,
            "done": done,
            "running": running,
            "all_done": done >= total and total > 0,
        }

def load_tasks_from_json(course_dir: str) -> List[CourseTask]:
    tasks = []
    for filename in os.listdir(course_dir):
        if not filename.endswith('.json'):
            continue
        filepath = os.path.join(course_dir, filename)
        with open(filepath, encoding='utf-8') as f:
            data = json.load(f)
        course_name = data.get('course_name', '')
        for node in data.get('nodes', []):
            if node.get('node_type') != 'video':
                continue
            params = node.get('hidden_params', {})
            duration_str = params.get('video-duration')
            if duration_str:
                duration = int(duration_str)
                tasks.append(CourseTask(
                    node_id=node['nodeId'],
                    duration=duration,
                    course_name=course_name,
                    video_name=node.get('name', '')
                ))
    if TEST_MODE and len(tasks) > TEST_VIDEO_COUNT:
        console.print(f"[测试模式] 仅选取前 {TEST_VIDEO_COUNT} 个视频任务进行模拟")
        tasks = tasks[:TEST_VIDEO_COUNT]
    return tasks

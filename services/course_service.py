import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from rich.progress import BarColumn, Progress, TextColumn

from infrastructure.course_crawler import (
    get_course_nodes_from_api,
)
from infrastructure.data_cleaner import clean_course_data
from infrastructure.rich_ui import console


def process_single_course(session, course, output_dir, max_workers=16, silent=False):
    """处理单门课程：爬取 → 清洗 → 保存"""
    if not silent:
        console.print(f"\n正在处理课程: {course['name']}")

    course_id = course.get("course_id", "")
    if not course_id:
        if not silent:
            console.print("  跳过：无课程ID")
        return None

    try:
        raw_data = get_course_nodes_from_api(session, course_id, course["name"])
        api_data = clean_course_data(raw_data)
    except Exception as e:
        if not silent:
            console.print(f"  [red]API 获取失败: {e}[/red]")
        return None

    all_nodes = api_data["nodes"]

    if not all_nodes:
        if not silent:
            console.print("  未获取到任何节点，跳过")
        return None

    if not silent:
        video_count = len(api_data["videos"])
        exam_count = len(api_data["exams"])
        work_count = len(api_data["works"])
        console.print(f"  视频={video_count} 考试={exam_count} 作业={work_count}")

    course_data = {
        'course_name': course['name'],
        'detail_link': course.get('detail_link', ''),
        'course_id': course_id,
        'nodes': all_nodes,
        'total_nodes': len(all_nodes),
        'api_data': api_data,
    }

    safe_name = course['name'].replace('/', '').replace('\\', '').replace(':', '') \
                            .replace('*', '').replace('?', '').replace('"', '') \
                            .replace('<', '').replace('>', '').replace('|', '') \
                            .replace('：', '').replace('、', '')
    json_file = os.path.join(output_dir, f"{safe_name}.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(course_data, f, ensure_ascii=False, indent=2)

    if not silent:
        console.print(f"  [green][OK] 已保存: {json_file}[/green]")
    return course_data


def extract_user_id_from_course(course_data: Dict, all_course_files: List[str] = None, course_json_dir: str = None) -> Optional[str]:
    nodes = course_data.get('nodes', [])
    for node in nodes:
        hidden_params = node.get('hidden_params', {})
        if 'user-id' in hidden_params:
            return hidden_params['user-id']

    if all_course_files and course_json_dir:
        current_name = course_data.get('course_name', '')
        for other_file in all_course_files:
            try:
                with open(os.path.join(course_json_dir, other_file), encoding='utf-8') as f:
                    other_data = json.load(f)
                if other_data.get('course_name', '') == current_name:
                    continue
                for node in other_data.get('nodes', []):
                    user_id = node.get('hidden_params', {}).get('user-id')
                    if user_id:
                        return user_id
            except Exception as e:
                continue
    return None


def fetch_all_courses(session, courses, output_dir, max_course_workers=8, silent=False, progress_callback=None):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    total = len(courses)
    completed = 0

    with Progress(
        TextColumn("[bold cyan]抓取课程:[/bold cyan] {task.description}"),
        BarColumn(bar_width=40, complete_style="green"),
        TextColumn("[green]{task.completed}/{task.total}[/green]"),
        console=console,
        transient=silent
    ) as progress:
        task = progress.add_task("初始化", total=total)

        with ThreadPoolExecutor(max_workers=max_course_workers) as executor:
            futures = [executor.submit(process_single_course, session, course, output_dir, 8, silent) for course in courses]
            for future in as_completed(futures):
                try:
                    future.result()
                    completed += 1
                    progress.update(task, completed=completed, description="处理中...")
                    if progress_callback:
                        progress_callback(completed, total)
                except Exception as e:
                    if not silent:
                        console.print(f"[red]课程处理出错: {e}[/red]")


def load_course_files():
    """加载课程文件列表"""
    import os

    from config import get_account_course_info_dir
    course_files = []
    course_info_dir = get_account_course_info_dir()
    if os.path.exists(course_info_dir):
        for file in os.listdir(course_info_dir):
            if file.endswith('.json'):
                course_files.append(file)
    return course_files

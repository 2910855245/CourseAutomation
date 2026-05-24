import json
import os

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import get_account_course_info_dir, get_account_study_records_dir, get_base_url
from infrastructure.rich_ui import console
from infrastructure.study_record_crawler import StudyRecordCrawler


class StudyRecordService:
    """学习记录服务"""
    def __init__(self, session, username: str = None):
        """初始化学习记录服务
        
        Args:
            session: requests会话对象
            username: 用户名（可选）
        """
        self.session = session
        self.crawler = StudyRecordCrawler(session, get_base_url())
        self.records_dir = get_account_study_records_dir(username)
        if not os.path.exists(self.records_dir):
            os.makedirs(self.records_dir, exist_ok=True)
        self._filename_cache = {}
        self._cache_loaded = False
    
    def get_course_info(self, course_id, user_id):
        """获取课程基本信息
        
        Args:
            course_id: 课程ID
            user_id: 用户ID
            
        Returns:
            课程基本信息字典
        """
        video_page_url = f"{get_base_url()}/user/study_record/video?courseId={course_id}&userId={user_id}"
        resp_html = self.session.get(video_page_url, timeout=15)
        resp_html.raise_for_status()
        course_info = self.crawler.extract_course_info_from_html(resp_html.text)
        return course_info
    
    def fetch_all_records(self, course_id, silent=False):
        """获取所有类型的学习记录
        
        Args:
            course_id: 课程ID
            silent: 是否静默执行
            
        Returns:
            包含所有记录的字典
        """
        if not silent:
            console.print("► 视频记录")
        videos = self.crawler.fetch_all_records(course_id, "video")
        if not silent:
            console.print("► 作业记录")
        works = self.crawler.fetch_all_records(course_id, "work")
        if not silent:
            console.print("► 考试记录")
        exams = self.crawler.fetch_all_records(course_id, "exam")
        if not silent:
            console.print("► 讨论记录")
        discusses = self.crawler.fetch_all_records(course_id, "discuss")
        
        return {
            "video": videos,
            "work": works,
            "exam": exams,
            "discuss": discusses
        }
    
    def save_records(self, course_id, course_info, records):
        """保存学习记录"""
        course_name = course_info.get("course_name", "unknown_course")
        safe_name = course_name.replace(" ", "_").replace("，", "_").replace("。", "")\
                              .replace(":", "").replace("：", "").replace("、", "")\
                              .replace("\"", "").replace("<", "").replace(">", "")\
                              .replace("|", "").replace("?", "").replace("*", "")\
                              .replace("\\", "").replace("/", "")
        if len(safe_name) > 50:
            safe_name = safe_name[:50]

        # 优先复用已有文件，避免课程名变更后产生僵尸文件
        existing_file = self._get_safe_filename(course_id)
        if existing_file and existing_file != f"{safe_name}_records.json":
            old_path = os.path.join(self.records_dir, existing_file)
            new_path = os.path.join(self.records_dir, f"{safe_name}_records.json")
            try:
                os.rename(old_path, new_path)
            except Exception as e:
                pass

        output_file = os.path.join(self.records_dir, f"{safe_name}_records.json")

        output = {
            "course_id": course_id,
            "course_info": course_info,
            "data": records
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        return output_file
    
    def run(self, course_id, user_id, silent=False):
        """运行完整的学习记录抓取流程

        Args:
            course_id: 课程ID
            user_id: 用户ID
            silent: 是否静默执行（不打印详细信息）

        Returns:
            保存的文件路径
        """
        if not silent:
            console.print("正在获取课程基本信息...")
        course_info = self.get_course_info(course_id, user_id)
        if not silent:
            info_table = Table(show_header=False, box=None, padding=(0, 1))
            for k, v in course_info.items():
                info_table.add_row(
                    Text(k, style="bold cyan"),
                    Text(str(v), style="white")
                )
            panel = Panel(
                info_table,
                title="课程基本信息",
                border_style="cyan",
                box=None
            )
            console.print(panel)

        if not silent:
            console.print("\n开始抓取记录...")
        records = self.fetch_all_records(course_id, silent)

        if not silent:
            console.print("\n保存学习记录...")
        output_file = self.save_records(course_id, course_info, records)

        if not silent:
            stats_table = Table(show_header=False, box=None, padding=(0, 2))
            stats_table.add_row("保存路径:", Text(output_file, style="dim"))
            stats_table.add_row("课程:", Text(course_info['course_name'], style="bold white"))
            stats_table.add_row("视频:", Text(str(len(records['video'])), style="green"))
            stats_table.add_row("作业:", Text(str(len(records['work'])), style="yellow"))
            stats_table.add_row("考试:", Text(str(len(records['exam'])), style="blue"))
            stats_table.add_row("讨论:", Text(str(len(records['discuss'])), style="magenta"))
            
            panel = Panel(
                stats_table,
                title="学习记录统计",
                border_style="green",
                box=None
            )
            console.print(panel)

        return output_file

    def update_video_only(self, course_id, user_id, silent=False):
        existing_filename = self._get_safe_filename(course_id)
        records_file = os.path.join(self.records_dir, existing_filename)
        existing = {}
        if os.path.exists(records_file):
            with open(records_file, encoding='utf-8') as f:
                existing = json.load(f)

        course_info = self.get_course_info(course_id, user_id)

        if not silent:
            console.print("► 视频记录")
        videos = self.crawler.fetch_all_records(course_id, "video")

        existing['course_id'] = course_id
        existing['course_info'] = course_info
        existing.setdefault('data', {})
        existing['data']['video'] = videos

        # 课程名变更时重命名文件
        course_name = course_info.get("course_name", "unknown_course")
        safe_name = course_name.replace(" ", "_").replace("，", "_").replace("。", "")\
                              .replace(":", "").replace("：", "").replace("、", "")\
                              .replace("\"", "").replace("<", "").replace(">", "")\
                              .replace("|", "").replace("?", "").replace("*", "")\
                              .replace("\\", "").replace("/", "")
        if len(safe_name) > 50:
            safe_name = safe_name[:50]
        expected_name = f"{safe_name}_records.json"
        if existing_filename != expected_name:
            new_path = os.path.join(self.records_dir, expected_name)
            try:
                os.rename(records_file, new_path)
                records_file = new_path
                self._filename_cache.pop(course_id, None)
            except Exception as e:
                pass

        with open(records_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    def _get_safe_filename(self, course_id):
        if course_id in self._filename_cache:
            return self._filename_cache[course_id]
        if not self._cache_loaded:
            for filename in os.listdir(self.records_dir):
                if filename.endswith('_records.json'):
                    filepath = os.path.join(self.records_dir, filename)
                    try:
                        with open(filepath, encoding='utf-8') as f:
                            data = json.load(f)
                        cid = data.get('course_id')
                        if cid:
                            self._filename_cache[cid] = filename
                    except Exception as e:
                        continue
            self._cache_loaded = True
        if course_id in self._filename_cache:
            return self._filename_cache[course_id]
        fallback = f"{course_id}_records.json"
        self._filename_cache[course_id] = fallback
        return fallback

    def run_auto(self):
        """自动抓取所有课程的学习记录"""
        course_files = []
        course_info_dir = get_account_course_info_dir()
        if os.path.exists(course_info_dir):
            for file in os.listdir(course_info_dir):
                if file.endswith('.json'):
                    course_files.append(file)

        if not course_files:
            return

        for file in course_files:
            try:
                with open(os.path.join(course_info_dir, file), encoding='utf-8') as f:
                    course_data = json.load(f)
                course_id = course_data.get('course_id')
                course_name = course_data.get('course_name', '未知课程')

                if not course_id:
                    continue

                nodes = course_data.get('nodes', [])
                user_id = None
                for node in nodes:
                    hidden_params = node.get('hidden_params', {})
                    if 'user-id' in hidden_params:
                        user_id = hidden_params['user-id']
                        break

                if not user_id:
                    for other_file in course_files:
                        if other_file == file:
                            continue
                        try:
                            with open(os.path.join(course_info_dir, other_file), encoding='utf-8') as f:
                                other_course_data = json.load(f)
                            other_nodes = other_course_data.get('nodes', [])
                            for other_node in other_nodes:
                                other_hidden_params = other_node.get('hidden_params', {})
                                if 'user-id' in other_hidden_params:
                                    user_id = other_hidden_params['user-id']
                                    break
                            if user_id:
                                break
                        except Exception as e:
                            continue

                if not user_id:
                    continue

                self.run(course_id, user_id, silent=True)
            except Exception as e:
                continue

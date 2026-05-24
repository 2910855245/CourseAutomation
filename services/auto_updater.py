import json
import os
import sys
import threading
import time
from typing import Optional


class AutoUpdater:
    """自动更新系统 - 启动时检测时间差，超过阈值则自动更新"""

    _instance: Optional['AutoUpdater'] = None
    _lock = threading.Lock()

    UPDATE_THRESHOLD_DAYS = 5

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self._initialized = True

        self._task_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._is_updating = False
        self._session = None
        self._username = None
        self._account_config = None

    def _get_timestamp_path(self):
        from config import get_account_dir
        return os.path.join(get_account_dir(), "last_update_time.json")

    def save_timestamp(self):
        try:
            path = self._get_timestamp_path()
            data = {"last_update": time.time()}
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception as e:
            pass

    def load_timestamp(self):
        try:
            path = self._get_timestamp_path()
            if os.path.exists(path):
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
                return data.get("last_update", 0)
        except Exception as e:
            pass
        return 0

    def needs_update(self):
        last = self.load_timestamp()
        if last <= 0:
            return True
        elapsed = time.time() - last
        return elapsed >= self.UPDATE_THRESHOLD_DAYS * 86400

    def check_and_update(self, session, username, account_config):
        if not self.needs_update():
            return False

        self._session = session
        self._username = username
        self._account_config = account_config

        if not self._task_lock.acquire(blocking=False):
            return False

        try:
            self._is_updating = True
            self._perform_update()
            return True
        except Exception as e:
            return False
        finally:
            self._is_updating = False
            self._task_lock.release()

    def is_updating(self):
        return self._is_updating

    def get_username(self):
        return self._username

    def start(self, session, username, account_config):
        self._session = session
        self._username = username
        self._account_config = account_config

    def stop(self):
        self.save_timestamp()

    def is_running(self):
        return False

    def _perform_update(self):
        try:
            self._fetch_courses_silent()
            self._fetch_records_silent()
            self.save_timestamp()
        except Exception as e:
            if self._account_config:
                self._account_config.log_debug_info(
                    self._username,
                    f"自动更新失败: {e}",
                    "ERROR"
                )

    def _fetch_courses_silent(self):
        original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

        try:
            from config import get_account_course_info_dir
            from infrastructure.course_crawler import get_courses
            from services.course_service import fetch_all_courses

            courses = get_courses(self._session)
            if courses:
                course_info_dir = get_account_course_info_dir()
                fetch_all_courses(self._session, courses, course_info_dir, silent=True)

        finally:
            sys.stdout.close()
            sys.stdout = original_stdout

    def _fetch_records_silent(self):
        original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

        try:
            from services.course_service import load_course_files
            from services.study_record_service import StudyRecordService

            course_files = load_course_files()
            if not course_files:
                return

            record_service = StudyRecordService(self._session, self._username)

            for file in course_files:
                try:
                    self._process_single_record_silent(file, course_files)
                except Exception as e:
                    pass

        finally:
            sys.stdout.close()
            sys.stdout = original_stdout

    def _process_single_record_silent(self, file, course_files):
        try:
            from config import get_account_course_info_dir
            from services.study_record_service import StudyRecordService

            course_info_dir = get_account_course_info_dir()
            file_path = os.path.join(course_info_dir, file)

            with open(file_path, encoding='utf-8') as f:
                course_data = json.load(f)

            course_id = course_data.get('course_id')
            if not course_id:
                return

            user_id = self._extract_user_id_from_course(course_data, course_files, course_info_dir)
            if not user_id:
                return

            record_service = StudyRecordService(self._session, self._username)
            record_service.update_video_only(course_id, user_id, silent=True)

        except Exception as e:
            pass

    def _extract_user_id_from_course(self, course_data, course_files, course_info_dir):
        try:
            nodes = course_data.get('nodes', [])
            for node in nodes:
                hidden_params = node.get('hidden_params', {})
                if 'user-id' in hidden_params:
                    return hidden_params['user-id']

            for other_file in course_files:
                try:
                    other_path = os.path.join(course_info_dir, other_file)
                    with open(other_path, encoding='utf-8') as f:
                        other_data = json.load(f)

                    other_nodes = other_data.get('nodes', [])
                    for node in other_nodes:
                        hidden_params = node.get('hidden_params', {})
                        if 'user-id' in hidden_params:
                            return hidden_params['user-id']
                except Exception as e:
                    continue

            return None

        except Exception as e:
            return None


def get_auto_updater() -> AutoUpdater:
    """获取自动更新器单例"""
    return AutoUpdater()

import json
import os

from config import (
    COURSE_DIR,
    get_account_course_info_dir,
    get_account_study_records_dir,
    get_current_account,
)


class DataLoader:
    """共享数据加载器"""
    
    def __init__(self, username: str = None):
        self.username = username or get_current_account()
        self.course_dir = COURSE_DIR
        self.course_json_dir = get_account_course_info_dir(self.username)
        self.records_dir = get_account_study_records_dir(self.username)

    def parse_duration(self, duration_str):
        if not duration_str:
            return 0
        try:
            parts = duration_str.split(':')
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            return int(parts[0]) if parts else 0
        except (ValueError, IndexError):
            return 0

    def load_courses(self, simple=False):
        courses = []
        if not os.path.exists(self.course_json_dir):
            return courses
        for filename in os.listdir(self.course_json_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.course_json_dir, filename)
                try:
                    with open(filepath, encoding='utf-8') as f:
                        data = json.load(f)
                    if simple:
                        courses.append({'name': filename.replace('.json', ''), 'data': data})
                    else:
                        courses.append(data)
                except Exception as e:
                    pass
        return courses

    def load_study_records(self):
        records = {}
        if not os.path.exists(self.records_dir):
            return records
        for filename in os.listdir(self.records_dir):
            if filename.endswith('_records.json'):
                filepath = os.path.join(self.records_dir, filename)
                try:
                    with open(filepath, encoding='utf-8') as f:
                        data = json.load(f)
                    course_name = data.get('course_info', {}).get('course_name')
                    if not course_name:
                        # 如果课程名称为空，尝试从文件名推断
                        course_name = filename.replace('_records.json', '')
                    if course_name:
                        records[course_name] = data
                except Exception as e:
                    pass
        return records

    def get_video_progress(self, course_name, video_name, study_records, video_node=None):
        # 优先使用官方学习记录，只用官方数据
        video_records = study_records[course_name].get('data', {}).get('video', []) if course_name in study_records else []

        # 如果有视频节点信息，尝试用时长匹配找到最合适的记录
        target_duration = 0
        if video_node:
            hidden_params = video_node.get('hidden_params', {})
            target_duration = int(hidden_params.get('video-duration', 0))

        max_viewed = 0
        max_total = target_duration  # 先从课程信息获取总时长作为默认
        video_status = '未学'
        
        # 先收集所有匹配标题的记录
        matching_records = []
        for vr in video_records:
            if vr.get('title', '') == video_name:
                viewed = self.parse_duration(vr.get('viewed_duration', '00:00:00'))
                total = self.parse_duration(vr.get('video_duration', '00:00:00'))
                status = vr.get('status', '未学')
                matching_records.append((viewed, total, status))

        if matching_records:
            if target_duration > 0:
                best_match = None
                min_diff = float('inf')
                for viewed, total, status in matching_records:
                    diff = abs(total - target_duration)
                    is_done = status in ['已学', '已完成', '完成']
                    if diff <= 5 and is_done:
                        best_match = (viewed, total, status)
                        break
                    if diff < min_diff or (diff == min_diff and is_done and not (
                        best_match and best_match[2] in ['已学', '已完成', '完成'])):
                        min_diff = diff
                        best_match = (viewed, total, status)
                if best_match:
                    max_viewed, max_total, video_status = best_match
            else:
                for viewed, total, status in matching_records:
                    if status in ['已学', '已完成', '完成']:
                        max_viewed = viewed
                        max_total = total
                        video_status = status
                        break
                if max_total == 0:
                    max_viewed, max_total, video_status = matching_records[0]
        elif video_records and target_duration > 0:
            # 标题不匹配，用时长回退匹配
            best_match = None
            min_diff = float('inf')
            for vr in video_records:
                total = self.parse_duration(vr.get('video_duration', '00:00:00'))
                diff = abs(total - target_duration)
                if diff < min_diff:
                    min_diff = diff
                    viewed = self.parse_duration(vr.get('viewed_duration', '00:00:00'))
                    status = vr.get('status', '未学')
                    best_match = (viewed, total, status)
            if best_match and min_diff <= 10:
                max_viewed, max_total, video_status = best_match

        # 确保总时长正确
        if max_total == 0 and target_duration > 0:
            max_total = target_duration

        max_viewed = min(max_viewed, max_total)

        # 识别更多状态，比如"未学完"也应该被考虑
        if (video_status in ['已学', '已完成', '完成'] or 
            '已学' in video_status or 
            '完成' in video_status) and max_total > 0:
            max_viewed = max_total

        if max_total == 0:
            return {'viewed': 0, 'total': 0, 'progress': 0, 'status': video_status}

        progress = int(max_viewed / max_total * 100)
        # 当 viewed >= total * 0.99 或官方状态为"已学"时，视为完成
        is_completed = (video_status in ['已学', '已完成', '完成'] or 
                       '已学' in video_status or 
                       '完成' in video_status or 
                       progress >= 100 or
                       (max_total > 0 and max_viewed >= max_total * 0.99))
        
        if is_completed:
            final_status = '已学'
            # 将 viewed 对齐为 total
            max_viewed = max_total
        elif progress > 0 or '未学完' in video_status or '进行' in video_status:
            final_status = '进行中' + str(progress) + '%'
        else:
            final_status = '未学'

        # 重新计算进度，确保完成时进度为100%
        if is_completed:
            progress = 100
        return {'viewed': max_viewed, 'total': max_total, 'progress': progress, 'status': final_status}

    def get_course_official_progress(self, course_name, study_records):
        if course_name not in study_records:
            return None
        course_info = study_records[course_name].get('course_info', {})
        if 'learning_progress' in course_info and course_info['learning_progress']:
            try:
                progress_str = course_info['learning_progress'].strip('%')
                return float(progress_str) / 100
            except ValueError:
                pass
        return None


data_loader = DataLoader()

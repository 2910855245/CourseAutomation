import re
import time as _time
from scrapling.parser import Adaptor
from typing import Dict, List, Any


def _compute_time_status(start_time, end_time, now: float = None) -> str:
    """根据 startTime/endTime (Unix时间戳) 判定时间状态: 未开始/进行中/已结束"""
    if now is None:
        now = _time.time()
    try:
        start_ts = int(start_time) if start_time else 0
        end_ts = int(end_time) if end_time else 0
    except (ValueError, TypeError):
        return "进行中"
    if start_ts > 0 and now < start_ts:
        return "未开始"
    if end_ts > 0 and now > end_ts:
        return "已结束"
    return "进行中"


class StudyRecordCrawler:
    """学习记录爬虫"""
    def __init__(self, session, base_url: str):
        """初始化学习记录爬虫
        
        Args:
            session: requests会话对象
            base_url: 基础URL
        """
        self.session = session
        self.base_url = base_url.rstrip('/')
    
    def extract_course_info_from_html(self, html_text: str) -> dict:
        """从视频记录页面 HTML 中提取课程基本信息
        
        Args:
            html_text: HTML文本
            
        Returns:
            课程基本信息字典
        """
        tree = Adaptor(html_text, adaptive=True)

        def _s(val):
            return str(val) if val is not None else ""

        # 课程名称（去除"课程名称："前缀）
        title_elem = tree.xpath("//div[@class='stuelearn-intro']/div[@class='title']/text()")
        course_name = ""
        if title_elem:
            course_name = _s(title_elem[0]).replace("课程名称：", "").strip()

        # 学习进度
        progress_elem = tree.xpath("//table[@class='score-table']//tr[2]/td/text()")
        progress = _s(progress_elem[0]).strip() if progress_elem else ""

        # 成绩策略链接
        tactics_elem = tree.xpath("//a[contains(@href,'tactics')]/@href")
        tactics_url = _s(tactics_elem[0]) if tactics_elem else ""

        # 主讲老师
        teacher_elem = tree.xpath("//span[@class='teacher color']/text()")
        teacher = _s(teacher_elem[0]).strip() if teacher_elem else ""

        # 开课时间和结束时间（位于第二个 <li> 中，两个 <span class='color'>）
        time_spans = tree.xpath("//ul/li[2]/span[@class='color']/text()")
        start_time = _s(time_spans[0]).strip() if len(time_spans) > 0 else ""
        end_time = _s(time_spans[1]).strip() if len(time_spans) > 1 else ""

        # 提示信息（第三个 <li>）
        notice_elem = tree.xpath("//ul/li[3]/text()")
        notice = _s(notice_elem[0]).strip() if notice_elem else ""

        return {
            "course_name": course_name,
            "learning_progress": progress,
            "score_strategy_url": tactics_url,
            "teacher": teacher,
            "start_time": start_time,
            "end_time": end_time,
            "notice": notice
        }
    
    def clean_state(self, raw_state: str, default: str = "未学") -> str:
        if not raw_state:
            return default
        text = re.sub(r'<[^>]+>', '', raw_state)
        text = text.replace('\\/', '/').strip()
        return text if text else default
    
    def fetch_all_records(self, course_id, record_type):
        """抓取指定类型全部记录（自动翻页，返回清洗后的列表）
        
        Args:
            course_id: 课程ID
            record_type: 记录类型 (video, work, exam, discuss)
            
        Returns:
            记录列表
        """
        api_url = f"{self.base_url}/user/study_record/{record_type}.json"
        all_data = []
        page = 1

        while True:
            resp = self.session.get(api_url, params={"courseId": course_id, "page": page}, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if not data.get("status"):
                break

            page_list = data.get("list", [])
            if not page_list:
                break

            for item in page_list:
                title = item.get("name") or item.get("title") or item.get("workName", "")
                state_default = "未交" if record_type in ("exam", "work") else "未学"
                state = self.clean_state(item.get("state", ""), default=state_default)

                if record_type == "video":
                    record = {
                        "title": title,
                        "begin_time": item.get("beginTime") or "",
                        "final_time": item.get("finalTime") or "",
                        "view_count": str(item.get("viewCount", "0")),
                        "viewed_duration": item.get("viewedDuration", "00:00:00"),
                        "video_duration": item.get("videoDuration", "00:00:00"),
                        "status": state
                    }
                elif record_type == "work":
                    start_ts = item.get("startTime", "")
                    end_ts = item.get("endTime", "")
                    record = {
                        "title": title,
                        "status": state,
                        "score": item.get("score", ""),
                        "submit_time": item.get("submitTime", ""),
                        "start_time": start_ts,
                        "deadline": end_ts,
                        "time_status": _compute_time_status(start_ts, end_ts),
                    }
                elif record_type == "exam":
                    start_ts = item.get("startTime", "")
                    end_ts = item.get("endTime", "")
                    record = {
                        "title": title,
                        "status": state,
                        "score": item.get("finalScore", "-"),
                        "submit_time": item.get("finishTime", ""),
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "time_status": _compute_time_status(start_ts, end_ts),
                    }
                elif record_type == "discuss":
                    record = {
                        "title": title,
                        "status": state,
                        "post_count": item.get("postCount", "0"),
                        "reply_count": item.get("replyCount", "0"),
                        "last_time": item.get("lastTime", "")
                    }
                else:
                    record = item
                all_data.append(record)

            page_info = data.get("pageInfo", {})
            total_pages = page_info.get("pageCount", 1)
            if page >= total_pages:
                break
            page += 1

        return all_data

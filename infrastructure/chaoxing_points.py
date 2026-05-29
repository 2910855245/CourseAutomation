"""
学习通积分规则自动解析与执行

自动读取课程积分规则，按规则执行每日积分任务：
- 登录 (+1/天，自动)
- 视频 (+1/分钟，有最低积分要求)
- 讨论 (+1/条，有每日上限)
- 笔记 (+1/条，有每日上限)
"""
import re
import time
import uuid
from loguru import logger
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable

from infrastructure.chaoxing_session import ChaoxingSession


# 积分类型映射
SCORE_TYPE_NAMES = {1: '登录', 2: '讨论', 3: '视频', 4: '笔记'}


@dataclass
class PointItem:
    """单项积分规则"""
    score_type: int          # 1=登录 2=讨论 3=视频 4=笔记
    name: str                # "登录" / "视频观看时长" / ...
    rate: float = 1.0        # 每次获得积分
    daily_cap: int = 0       # 每日上限 (0=无限)
    min_total: int = 0       # 累计最低要求 (0=无)
    desc: str = ""           # 描述


@dataclass
class PointsRule:
    """课程积分规则"""
    target: int = 200            # 总积分目标
    daily_limit: int = 50        # 每日上限
    video_min: int = 0           # 视频最低积分要求
    must_read: bool = False      # 有必学知识点
    items: List[PointItem] = field(default_factory=list)

    def get_item(self, score_type: int) -> Optional[PointItem]:
        for item in self.items:
            if item.score_type == score_type:
                return item
        return None


@dataclass
class ItemStatus:
    """单项积分状态"""
    day: int = 0       # 今日积分
    total: int = 0     # 累计积分


@dataclass
class PointsStatus:
    """当前积分状态"""
    total: int = 0
    day_score: int = 0
    study_days: int = 0
    items: Dict[int, ItemStatus] = field(default_factory=dict)

    def get_item(self, score_type: int) -> ItemStatus:
        return self.items.get(score_type, ItemStatus())


class ScoreRuleParser:
    """积分规则解析器"""

    @staticmethod
    def fetch_rules(session: ChaoxingSession, course_id: str, class_id: str) -> PointsRule:
        """一站式获取积分规则

        1. 请求积分规则页 → 提取 iframe URL 参数
        2. 请求 iframe 页 → 解析规则文本
        """
        rule = PointsRule()

        # Step 1: 获取积分规则页面
        url = f'https://tsjy.chaoxing.com/plaza/score-record?courseId={course_id}&personId={session.uid}&classId={class_id}&userId={session.uid}'
        try:
            resp = session.get(url, referer=f'https://tsjy.chaoxing.com/plaza/knowledge-all?courseId={course_id}')
            html = resp.text()
        except Exception as e:
            logger.warning(f"获取积分规则页失败 error={str(e)}")
            return rule

        # 提取 iframe URL 参数
        iframe_match = re.search(
            r'<iframe[^>]*src="([^"]*bigdata-score\.chaoxing\.com[^"]*)"[^>]*>',
            html
        )
        if not iframe_match:
            logger.warning("未找到积分规则iframe")
            # 尝试直接从页面解析
            ScoreRuleParser._parse_rule_text(html, rule)
            return rule

        iframe_url = iframe_match.group(1)
        # 提取参数
        params = {}
        for key in ['eExamRatio', 'eExamFlag', 'mustReadFlag', 'courseid', 'classid']:
            m = re.search(rf'{key}=([^&"]+)', iframe_url)
            if m:
                params[key] = m.group(1)

        # Step 2: 获取 iframe 内容
        if not iframe_url.startswith('http'):
            iframe_url = 'https:' + iframe_url if iframe_url.startswith('//') else 'https://bigdata-score.chaoxing.com' + iframe_url

        try:
            resp2 = session.get(iframe_url, referer=url)
            iframe_html = resp2.text()
        except Exception as e:
            logger.warning(f"获取积分规则iframe失败 error={str(e)}")
            return rule

        # Step 3: 解析规则
        ScoreRuleParser._parse_rules_html(iframe_html, rule, params)
        return rule

    @staticmethod
    def _parse_rules_html(html: str, rule: PointsRule, params: dict = None):
        """从 iframe HTML 解析积分规则"""
        # 解析总积分目标: "至少需要获得200积分" 或 "需要获得200积分"
        target_match = re.search(r'(?:至少)?需要获得(\d+)积分', html)
        if target_match:
            rule.target = int(target_match.group(1))

        # 解析每日上限: "每日新增积分上限为50积分"
        daily_match = re.search(r'每日新增积分上限为(\d+)积分', html)
        if daily_match:
            rule.daily_limit = int(daily_match.group(1))

        # 解析视频最低分: "视频观看时长得分不得低于180积分"
        video_min_match = re.search(r'视频观看时长得分不得低于(\d+)积分', html)
        if video_min_match:
            rule.video_min = int(video_min_match.group(1))

        # 解析必学知识点
        if '必学' in html or (params and params.get('mustReadFlag') == '1'):
            rule.must_read = True

        # 解析积分项表格
        # 表格行: <tr><td>登录</td><td>每天首次登录得1分</td><td>1分/天</td><td>无上限</td></tr>
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            if len(cells) < 3:
                continue

            name = re.sub(r'<[^>]+>', '', cells[0]).strip()
            desc = re.sub(r'<[^>]+>', '', cells[1]).strip()
            rate_text = re.sub(r'<[^>]+>', '', cells[2]).strip()

            # 判断积分类型
            score_type = 0
            if '登录' in name:
                score_type = 1
            elif '讨论' in name:
                score_type = 2
            elif '视频' in name:
                score_type = 3
            elif '笔记' in name:
                score_type = 4

            if score_type == 0:
                continue

            # 解析积分率: "1分/天" → 1.0, "1分/分钟" → 1.0
            rate_match = re.search(r'(\d+)分', rate_text)
            rate = float(rate_match.group(1)) if rate_match else 1.0

            # 解析每日上限
            daily_cap = 0
            if '无上限' not in rate_text:
                cap_match = re.search(r'上限(\d+)', rate_text)
                if cap_match:
                    daily_cap = int(cap_match.group(1))
                elif '/天' in rate_text:
                    # "1分/天" 表示每天只能得1分
                    daily_cap = int(rate)

            # 解析累计最低要求
            min_total = 0
            min_match = re.search(r'不低于(\d+)', desc)
            if min_match:
                min_total = int(min_match.group(1))

            item = PointItem(
                score_type=score_type,
                name=name,
                rate=rate,
                daily_cap=daily_cap,
                min_total=min_total,
                desc=desc,
            )
            rule.items.append(item)

        # 如果没有解析到积分项，添加默认项
        if not rule.items:
            rule.items = [
                PointItem(score_type=1, name='登录', rate=1.0, daily_cap=1, desc='每天首次登录'),
                PointItem(score_type=3, name='视频', rate=1.0, daily_cap=0, min_total=rule.video_min, desc='视频观看时长'),
                PointItem(score_type=2, name='讨论', rate=1.0, daily_cap=2, desc='发表讨论'),
                PointItem(score_type=4, name='笔记', rate=1.0, daily_cap=2, desc='发表笔记'),
            ]

    @staticmethod
    def _parse_rule_text(html: str, rule: PointsRule):
        """从纯文本解析规则（备用）"""
        target_match = re.search(r'(\d+)积分', html)
        if target_match:
            rule.target = int(target_match.group(1))


class PointsExecutor:
    """积分执行引擎"""

    def __init__(self, session: ChaoxingSession, course_id: str, class_id: str,
                 rule: PointsRule):
        self.session = session
        self.course_id = course_id
        self.class_id = class_id
        self.rule = rule

    def get_status(self) -> PointsStatus:
        """查询当前积分状态"""
        url = f'https://bigdata-score.chaoxing.com/tsjy/point/getCount?courseid={self.course_id}&classid={self.class_id}'
        try:
            data = self.session.get_json(url)
        except Exception as e:
            logger.warning(f"获取积分失败 error={str(e)}")
            return PointsStatus()

        if not data.get('status'):
            return PointsStatus()

        total_scores = {i['scoreType']: i['score'] for i in data.get('itemTotalScore', [])}
        day_scores = {i['scoreType']: i['score'] for i in data.get('itemDayScore', [])}
        study_days = data.get('studyDays', 0)

        items = {}
        for st in [1, 2, 3, 4]:
            items[st] = ItemStatus(
                day=day_scores.get(st, 0),
                total=total_scores.get(st, 0),
            )

        total_sum = sum(total_scores.values())
        day_sum = sum(day_scores.values())

        return PointsStatus(
            total=total_sum,
            day_score=day_sum,
            study_days=study_days,
            items=items,
        )

    def check_done(self, status: PointsStatus) -> bool:
        """检查是否达标"""
        if status.total < self.rule.target:
            return False
        # 检查视频最低分
        if self.rule.video_min > 0:
            video_item = status.get_item(3)
            if video_item.total < self.rule.video_min:
                return False
        return True

    def get_remaining_today(self, status: PointsStatus) -> int:
        """今日还能赚多少分"""
        return max(0, self.rule.daily_limit - status.day_score)

    def execute_daily(self, status_file: str = None,
                      on_progress: Callable = None) -> PointsStatus:
        """执行一天的积分任务

        1. 检查积分状态
        2. 刷视频（如果需要）
        3. 做作业（如果有待完成的）
        4. 发讨论（如果还有额度）
        5. 写笔记（如果还有额度）
        """
        status = self.get_status()
        if self.check_done(status):
            logger.info(f"积分已达标 total={status.total}")
            return status

        remaining = self.get_remaining_today(status)
        if remaining <= 0:
            logger.info(f"今日积分已满 day_score={status.day_score}")
            return status

        logger.info("开始积分任务",
                     total=status.total, target=self.rule.target,
                     today=status.day_score, remaining=remaining)

        # 1. 刷视频
        video_item = status.get_item(3)
        video_needs_more = (
            self.rule.video_min > 0 and video_item.total < self.rule.video_min
        )
        video_rule = self.rule.get_item(3)
        video_daily_cap = video_rule.daily_cap if video_rule else 0
        # daily_cap=0 表示无上限，只要还有 remaining 就应该刷视频
        video_under_cap = (video_daily_cap == 0) or (video_item.day < video_daily_cap)
        if remaining > 0 and (video_needs_more or video_under_cap):
            earned = self._play_videos(remaining, status_file, on_progress)
            remaining -= earned
            status = self.get_status()
            remaining = self.get_remaining_today(status)

        # 2. 做作业
        if remaining > 0:
            earned = self._answer_quizzes(remaining)
            remaining -= earned
            status = self.get_status()
            remaining = self.get_remaining_today(status)

        # 3. 发讨论
        if remaining > 0:
            earned = self._post_discussions(remaining)
            remaining -= earned
            status = self.get_status()
            remaining = self.get_remaining_today(status)

        # 4. 写笔记
        if remaining > 0:
            earned = self._post_notes(remaining)
            status = self.get_status()

        return status

    def _play_videos(self, remaining: int, status_file: str = None,
                     on_progress: Callable = None) -> int:
        """刷视频赚积分"""
        from infrastructure.chaoxing.crawler import fetch_knowledge_list
        from infrastructure.chaoxing_reporter import process_knowledge_videos

        knowledge_points = fetch_knowledge_list(self.session, self.course_id, self.class_id)
        video_points = [kp for kp in knowledge_points if kp['has_video']]

        if not video_points:
            logger.info("无视频知识点")
            return 0

        # 检查视频积分上限
        video_rule = self.rule.get_item(3)
        daily_cap = video_rule.daily_cap if video_rule else 0

        earned = 0
        for kp in video_points:
            if earned >= remaining:
                break
            if daily_cap > 0 and earned >= daily_cap:
                break

            kid = kp['knowledgeId']
            name = kp['name']

            def _on_progress(pct):
                if on_progress:
                    on_progress(f"刷视频中 {name} {pct}%")

            result = process_knowledge_videos(
                self.session, self.course_id, kid, self.class_id,
                knowledge_name=name, speed='normal',
                on_progress=_on_progress
            )

            if result.get('played', 0) > 0:
                earned += min(3, remaining - earned)
                logger.info(f"视频积分 earned={earned} name={name}")

            time.sleep(2)

        return earned

    def _answer_quizzes(self, remaining: int) -> int:
        """答题赚积分"""
        from infrastructure.chaoxing_quiz import get_work_list, solve_quiz, load_ref_hashes, AnswerCache

        works = get_work_list(self.session, self.course_id, self.class_id)
        if not works:
            logger.info("无待完成作业")
            return 0

        try:
            ref_hashes = load_ref_hashes()
        except Exception as e:
            logger.warning(f"加载字体参考失败，跳过答题 error={str(e)}")
            return 0

        cache = AnswerCache()
        import os
        api_key = os.environ.get('DEEPSEEK_API_KEY', '')
        if not api_key:
            try:
                from config import settings
                api_key = settings.deepseek_api_key
            except Exception:
                pass

        if not api_key:
            logger.warning("未配置DEEPSEEK_API_KEY，跳过答题")
            return 0

        earned = 0
        for work in works:
            if earned >= remaining:
                break

            wid = work.get('workId', '')
            title = work.get('title', '未知作业')
            work_url = f'https://mooc1.chaoxing.com/mooc-ans/work/{self.class_id}/do?workId={wid}&courseId={self.course_id}'

            result = solve_quiz(
                self.session, work_url, api_key,
                ref_hashes=ref_hashes, cache=cache
            )

            if result.get('success'):
                earned += min(3, remaining - earned)
                logger.info(f"答题积分 earned={earned} title={title}")

            time.sleep(3)

        return earned

    def _post_discussions(self, remaining: int) -> int:
        """发讨论赚积分"""
        from infrastructure.chaoxing_discuss import post_discussion

        # 检查讨论积分上限
        discuss_rule = self.rule.get_item(2)
        daily_cap = discuss_rule.daily_cap if discuss_rule else 2

        # 获取当前讨论积分
        status = self.get_status()
        discuss_item = status.get_item(2)
        already_today = discuss_item.day

        if daily_cap > 0 and already_today >= daily_cap:
            logger.info(f"今日讨论积分已满 today={already_today} cap={daily_cap}")
            return 0

        # 获取知识点列表（用于在知识点下发表讨论）
        from infrastructure.chaoxing.crawler import fetch_knowledge_list
        knowledge_points = fetch_knowledge_list(self.session, self.course_id, self.class_id)
        if not knowledge_points:
            logger.info("无知识点，跳过讨论")
            return 0

        # 获取讨论区bbsid
        from infrastructure.chaoxing_discuss import get_discuss_bbsid
        bbsid = get_discuss_bbsid(self.session, self.course_id, self.class_id,
                                   knowledge_points[0]['knowledgeId'])
        if not bbsid:
            logger.warning("获取讨论区bbsid失败")
            return 0

        # 讨论内容模板
        discuss_contents = [
            '学习了本节内容，收获很大，知识点讲解清晰易懂。',
            '本节内容很实用，对理解课程核心概念很有帮助。',
            '通过学习本节，对相关知识有了更深入的理解。',
            '课程内容安排合理，循序渐进，容易理解。',
            '本节重点突出，有助于掌握关键知识点。',
        ]

        earned = 0
        max_posts = min(remaining, daily_cap - already_today if daily_cap > 0 else remaining)

        for i in range(max_posts):
            if earned >= remaining:
                break

            content = discuss_contents[i % len(discuss_contents)]
            result = post_discussion(
                self.session, self.course_id, self.class_id,
                bbsid, content
            )

            if isinstance(result, dict) and result.get('success'):
                earned += 1
                logger.info(f"讨论积分 earned={earned}")

            time.sleep(3)

        return earned

    def _post_notes(self, remaining: int) -> int:
        """写笔记赚积分"""
        from infrastructure.chaoxing_discuss import post_note

        # 检查笔记积分上限
        note_rule = self.rule.get_item(4)
        daily_cap = note_rule.daily_cap if note_rule else 2

        # 获取当前笔记积分
        status = self.get_status()
        note_item = status.get_item(4)
        already_today = note_item.day

        if daily_cap > 0 and already_today >= daily_cap:
            logger.info(f"今日笔记积分已满 today={already_today} cap={daily_cap}")
            return 0

        # 获取知识点列表
        from infrastructure.chaoxing.crawler import fetch_knowledge_list
        knowledge_points = fetch_knowledge_list(self.session, self.course_id, self.class_id)
        if not knowledge_points:
            logger.info("无知识点，跳过笔记")
            return 0

        # 笔记内容模板
        note_contents = [
            '本节重点：核心概念理解与应用。',
            '学习笔记：关键知识点梳理与总结。',
            '课堂笔记：重点内容记录与反思。',
            '学习心得：通过本节学习，加深了对课程内容的理解。',
            '知识整理：本节内容要点归纳与提炼。',
        ]

        earned = 0
        max_posts = min(remaining, daily_cap - already_today if daily_cap > 0 else remaining)

        for i in range(max_posts):
            if earned >= remaining:
                break

            kp = knowledge_points[i % len(knowledge_points)]
            content = note_contents[i % len(note_contents)]

            result = post_note(
                self.session, self.course_id, self.class_id,
                kp['knowledgeId'], content
            )

            if isinstance(result, dict) and result.get('success'):
                earned += 1
                logger.info(f"笔记积分 earned={earned}")

            time.sleep(3)

        return earned

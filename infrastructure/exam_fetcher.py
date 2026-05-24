"""题目获取模块"""

import re
from typing import Dict, List

import httpx
from loguru import logger
from bs4 import BeautifulSoup



class TopicFetcher:
    def __init__(self, session: httpx.Client, base_url: str):
        self.session = session
        from infrastructure.exam_login import normalize_base_url
        self.base_url = normalize_base_url(base_url)
        self._submit_type = 'work'

    def start_work(self, work_id: int, course_id: int, node_id: int,
                   item_type: str = '') -> Dict:
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": self.base_url,
        }

        # 根据类型决定尝试顺序
        if item_type == 'exam':
            # 考试：先试 exam 端点
            endpoints = [
                (f"{self.base_url}/user/exam/start",
                 {'examId': str(work_id), 'courseId': str(course_id), 'nodeId': str(node_id)}),
                (f"{self.base_url}/user/work/start",
                 {'workId': str(work_id), 'courseId': str(course_id), 'nodeId': str(node_id)}),
            ]
        else:
            # 作业或未知：先试 work 端点
            endpoints = [
                (f"{self.base_url}/user/work/start",
                 {'workId': str(work_id), 'courseId': str(course_id), 'nodeId': str(node_id)}),
                (f"{self.base_url}/user/exam/start",
                 {'examId': str(work_id), 'courseId': str(course_id), 'nodeId': str(node_id)}),
            ]

        last_result = {}
        for url, data in endpoints:
            resp = self.session.post(url, data=data, headers=headers, timeout=15)
            result = resp.json()
            if result.get('status'):
                return result
            last_result = result

        # 两个都失败，返回最后一个
        return last_result

    def fetch(self, work_id: int, course_id: int, node_id: int,
              item_type: str = '') -> Dict:
        start_res = self.start_work(work_id, course_id, node_id, item_type=item_type)
        if not start_res.get('status'):
            msg = start_res.get('msg', '')
            logger.warning(f"开始作业失败: {start_res}")
            # 已删除/已结束的直接返回，不浪费时间获取页面
            if '已删除' in msg or '已结束' in msg or '已经结束' in msg or '不存在' in msg:
                return {
                    'work_id': work_id,
                    'work_title': '',
                    'node_id': str(node_id),
                    'exam_id': '',
                    'topics': [],
                    'error': msg,
                }

        url = f"{self.base_url}/user/work?workId={work_id}&courseId={course_id}&nodeId={node_id}"
        resp = self.session.get(url, timeout=15)
        html = resp.text

        # 检测是作业还是考试
        if '/exam/' in html or 'examId' in html:
            self._submit_type = 'exam'
        else:
            self._submit_type = 'work'

        return self._parse_topics(html, work_id)

    def _parse_topics(self, html: str, work_id: int) -> Dict:
        soup = BeautifulSoup(html, 'html.parser')

        # 提取页面级的 examId 和 nodeId（支持 name 或 id 属性）
        exam_id = ''
        node_id = ''
        hidden_inputs = soup.find_all('input', type='hidden')
        for inp in hidden_inputs:
            name = inp.get('name', '') or inp.get('id', '')
            value = inp.get('value', '')
            if 'examId' in name:
                exam_id = value
            elif 'nodeId' in name:
                node_id = value

        title_el = soup.find('h2') or soup.find('h3') or soup.find('title')
        work_title = title_el.get_text(strip=True) if title_el else f"作业{work_id}"

        # 优先从 form 解析（考试页面结构：每题一个 form）
        topics = self._parse_topics_from_forms(soup)

        if not topics:
            # 降级到原有的解析方式
            topic_items = soup.select('.topic-item, .question-item, .topic, .question')
            if not topic_items:
                topic_items = soup.find_all('div', class_=re.compile(r'topic|question'))
            for idx, item in enumerate(topic_items, 1):
                topic = self._parse_single_topic(item, idx)
                if topic:
                    topics.append(topic)

        if not topics:
            topics = self._parse_topics_regex(html)

        return {
            'work_id': work_id,
            'work_title': work_title,
            'node_id': node_id or str(work_id),
            'exam_id': exam_id,
            'topics': topics,
        }

    def _parse_topics_from_forms(self, soup: BeautifulSoup) -> List[Dict]:
        """从 form 元素解析题目（考试页面结构：每题一个 form）"""
        topics = []

        # 提取 topic-head 链接中的 data-id（这是真正的 answerId）
        topic_heads = soup.find_all('a', class_='topic-head')
        head_id_map = {}
        for idx, a in enumerate(topic_heads):
            data_id = a.get('data-id', '')
            if data_id:
                head_id_map[idx] = data_id

        forms = soup.find_all('form', action=lambda x: x and 'submit' in str(x))

        for idx, form in enumerate(forms):
            # 提取题号
            num_el = form.find('div', class_='num')
            number = len(topics) + 1
            if num_el:
                num_span = num_el.find('span')
                if num_span:
                    try:
                        number = int(num_span.get_text(strip=True))
                    except ValueError:
                        pass

            # 提取题目文本
            name_el = form.find('div', class_='name')
            question = name_el.get_text(strip=True) if name_el else ''
            if not question:
                continue

            # 提取选项
            options = []
            list_el = form.find('div', class_='list')
            if list_el:
                labels = list_el.find_all('label')
                for label in labels:
                    opt_text = label.get_text(strip=True)
                    if opt_text:
                        options.append(opt_text)

            # 提取题型
            type_el = form.find('div', class_='type')
            q_type = type_el.get_text(strip=True) if type_el else ''
            is_choice = '单选' in q_type or '多选' in q_type or '判断' in q_type

            # 使用 topic-head 的 data-id 作为 answer_id（服务器需要这个来识别题目）
            answer_id = head_id_map.get(idx, str(number))

            topics.append({
                'number': number,
                'topic_id': answer_id,
                'answer_id': answer_id,
                'question': question,
                'options': options,
                'type': 'choice' if is_choice else 'text',
                'q_type': q_type,
            })

        return topics

    def _parse_single_topic(self, item, number: int) -> Dict:
        text = item.get_text(separator='\n', strip=True)

        answer_id_el = item.find(attrs={'name': re.compile(r'answerId|topic_id')})
        answer_id = answer_id_el.get('value', '') if answer_id_el else ''

        topic_id_el = item.find(attrs={'name': re.compile(r'topicId|topic_id')})
        topic_id = topic_id_el.get('value', '') if topic_id_el else answer_id

        options = []
        option_els = item.find_all(['label', 'span', 'div'], class_=re.compile(r'option|choice'))
        for opt in option_els:
            opt_text = opt.get_text(strip=True)
            if opt_text and len(opt_text) < 200:
                options.append(opt_text)

        return {
            'number': number,
            'topic_id': topic_id or str(number),
            'answer_id': answer_id or topic_id or str(number),
            'question': text[:500],
            'options': options,
            'type': 'choice' if options else 'text',
        }

    def _parse_topics_regex(self, html: str) -> List[Dict]:
        topics = []
        pattern = r'topicId["\s:=]+(\d+)'
        ids = re.findall(pattern, html)
        if not ids:
            pattern = r'answerId["\s:=]+(\d+)'
            ids = re.findall(pattern, html)

        for idx, tid in enumerate(ids, 1):
            topics.append({
                'number': idx,
                'topic_id': tid,
                'answer_id': tid,
                'question': f'题目{idx}',
                'options': [],
                'type': 'choice',
            })
        return topics

"""题目获取模块"""

from typing import Dict, List

import httpx
import lxml.html
from loguru import logger


def _els_with_class(el, cls: str, tag: str = None):
    """找 el 子孙节点中 class 含指定 token 的元素（等价 BeautifulSoup find_all(class_=cls)）"""
    return [e for e in el.xpath(f'.//{tag or "*"}[@class]') if cls in e.get('class', '').split()]



class TopicFetcher:
    def __init__(self, session: httpx.Client, base_url: str):
        self.session = session
        from infrastructure.school.exam_login import normalize_base_url
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

        # 优先使用 start_work 返回的 URL（考试页面需要用 exam URL）
        page_url = start_res.get('url', '')
        if page_url:
            if page_url.startswith('/'):
                page_url = f"{self.base_url}{page_url}"
            resp = self.session.get(page_url, timeout=15)
        else:
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
        tree = lxml.html.document_fromstring(html)

        # 提取页面级的 examId 和 nodeId（支持 name 或 id 属性）
        exam_id = ''
        node_id = ''
        hidden_inputs = tree.xpath('//input[@type="hidden"]')
        for inp in hidden_inputs:
            name = inp.get('name', '') or inp.get('id', '')
            value = inp.get('value', '')
            if 'examId' in name:
                exam_id = value
            elif 'nodeId' in name:
                node_id = value

        title_el = None
        for tag in ('h2', 'h3', 'title'):
            found = tree.xpath(f'//{tag}')
            if found:
                title_el = found[0]
                break
        work_title = title_el.text_content().strip() if title_el is not None else f"作业{work_id}"

        # 优先从 form 解析（考试页面结构：每题一个 form）
        topics = self._parse_topics_from_forms(tree)

        if not topics:
            # 降级到原有的解析方式
            topic_items = [e for e in tree.xpath('//*[@class]')
                           if any(c in e.get('class', '').split()
                                  for c in ('topic-item', 'question-item', 'topic', 'question'))]
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

    def _parse_topics_from_forms(self, tree) -> List[Dict]:
        """从 form 元素解析题目（考试页面结构：每题一个 form）"""
        topics = []

        # 检测是否有文件上传按钮（项目提交题型）
        has_uploader = bool(_els_with_class(tree, 'uploader-btn', tag='a'))

        # 提取 topic-head 链接中的 data-id（这是真正的 answerId）
        topic_heads = _els_with_class(tree, 'topic-head', tag='a')
        head_id_map = {}
        for idx, a in enumerate(topic_heads):
            data_id = a.get('data-id', '')
            if data_id:
                head_id_map[idx] = data_id

        forms = [f for f in tree.xpath('.//form') if 'submit' in (f.get('action') or '')]

        for idx, form in enumerate(forms):
            # 提取题号
            num_el = _els_with_class(form, 'num', tag='div')
            number = len(topics) + 1
            if num_el:
                num_span = num_el[0].xpath('.//span')
                if num_span:
                    try:
                        number = int(num_span[0].text_content().strip())
                    except ValueError:
                        pass

            # 提取题目文本
            name_el = _els_with_class(form, 'name', tag='div')
            if not name_el:
                continue

            # 填空题：将 <input> 标签替换为占位符 _____
            name_html = lxml.html.tostring(name_el[0], encoding='unicode')
            import re
            name_html = re.sub(r'<input[^>]*class="exam-input"[^>]*/?>', ' _____ ', name_html)
            # 移除其他HTML标签，保留文本
            question = re.sub(r'<[^>]+>', '', name_html)
            question = re.sub(r'\s+', ' ', question).strip()

            if not question:
                continue

            # 提取完整题目描述（包含 <p> 标签中的要求）
            question_parts = [question]
            for p in form.xpath('.//p'):
                p_text = p.text_content().strip()
                if p_text and p_text not in question:
                    question_parts.append(p_text)
            full_question = '\n'.join(question_parts)

            # 提取选项
            options = []
            list_els = _els_with_class(form, 'list', tag='div')
            if list_els:
                for label in list_els[0].xpath('.//label'):
                    opt_text = label.text_content().strip()
                    if opt_text:
                        options.append(opt_text)

            # 提取题型
            type_els = _els_with_class(form, 'type', tag='div')
            q_type = type_els[0].text_content().strip() if type_els else ''
            is_choice = '单选' in q_type or '多选' in q_type or '判断' in q_type

            # 判断是否为项目提交题（简答 + 文件上传）
            is_project = has_uploader and ('简答' in q_type or '上传' in full_question or '压缩' in full_question or '提交' in full_question)

            # 使用 topic-head 的 data-id 作为 answer_id（服务器需要这个来识别题目）
            answer_id = head_id_map.get(idx, str(number))

            if is_project:
                topic_type = 'project'
            elif is_choice:
                topic_type = 'choice'
            else:
                topic_type = 'text'

            # 统计填空题的空格数量
            blank_count = 0
            if '填空' in q_type:
                blank_inputs = _els_with_class(form, 'exam-input', tag='input')
                blank_count = len(blank_inputs) if blank_inputs else 1

            topics.append({
                'number': number,
                'topic_id': answer_id,
                'answer_id': answer_id,
                'question': full_question,
                'options': options,
                'type': topic_type,
                'q_type': q_type,
                'blank_count': blank_count,
            })

        return topics

    def _parse_single_topic(self, item, number: int) -> Dict:
        text = '\n'.join(t.strip() for t in item.itertext() if t.strip())

        answer_id_els = item.xpath('.//input[@name="answerId" or @name="topic_id"]')
        answer_id = answer_id_els[0].get('value', '') if answer_id_els else ''

        topic_id_els = item.xpath('.//input[@name="topicId" or @name="topic_id"]')
        topic_id = topic_id_els[0].get('value', '') if topic_id_els else answer_id

        options = []
        option_els = [e for e in item.xpath('.//label | .//span | .//div')
                      if any(c in (e.get('class') or '').split() for c in ('option', 'choice'))]
        if not option_els:
            option_els = item.xpath('.//label')
        for opt in option_els:
            opt_text = opt.text_content().strip()
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
        """用 lxml 从 hidden input / topic-head 链接中提取题目ID"""
        tree = lxml.html.document_fromstring(html)
        topics = []
        seen = set()

        # 从 hidden input 提取 topicId / answerId
        for inp in tree.xpath('//input[@type="hidden"]'):
            name = inp.get('name', '') or inp.get('id', '')
            value = inp.get('value', '')
            if name in ('topicId', 'answerId', 'topic_id') and value and value not in seen:
                seen.add(value)
                topics.append({
                    'number': len(topics) + 1,
                    'topic_id': value,
                    'answer_id': value,
                    'question': f'题目{len(topics)+1}',
                    'options': [],
                    'type': 'choice',
                })

        # 从 topic-head 链接提取 data-id
        for a in _els_with_class(tree, 'topic-head', tag='a'):
            data_id = a.get('data-id', '')
            if data_id and data_id not in seen:
                seen.add(data_id)
                topics.append({
                    'number': len(topics) + 1,
                    'topic_id': data_id,
                    'answer_id': data_id,
                    'question': a.text_content().strip() or f'题目{len(topics)+1}',
                    'options': [],
                    'type': 'choice',
                })

        return topics

"""AI答题与提交模块"""

import json
import time
from typing import Dict, Optional

import httpx
from loguru import logger
from openai import OpenAI



class AIAnswerer:
    def __init__(self, api_key: str, model: str = "deepseek-chat", base_url: str = "https://api.deepseek.com"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self._cache: Dict[str, str] = {}

    def ask_one_topic(self, topic: Dict) -> Dict:
        cache_key = topic.get('question', '')[:100]
        if cache_key in self._cache:
            return {'answer': self._cache[cache_key], 'confidence': 1.0}

        q_type = topic.get('q_type', '')
        is_choice = '单选' in q_type or '多选' in q_type or '判断' in q_type

        prompt = self._build_prompt(topic)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200,
            )
            content = resp.choices[0].message.content.strip()
            answer = self._extract_answer(content, is_choice=is_choice)
            self._cache[cache_key] = answer
            return {'answer': answer, 'confidence': 0.9, 'raw': content}
        except Exception as e:
            logger.error(f"AI回答失败: {e}")
            return {'answer': '', 'confidence': 0, 'error': str(e)}

    def _build_prompt(self, topic: Dict) -> str:
        question = topic.get('question', '')
        options = topic.get('options', [])
        q_type = topic.get('q_type', '')
        is_choice = '单选' in q_type or '多选' in q_type or '判断' in q_type
        opt_text = '\n'.join(options) if options else ''

        if '多选' in q_type:
            type_hint = '这是一道多选题，请返回所有正确选项的字母（如 ABC、ABD），不要解释。'
        elif '判断' in q_type:
            type_hint = '这是一道判断题，A表示正确，B表示错误，只返回一个字母。'
        elif is_choice:
            type_hint = '请回答以下题目，只返回答案字母（如 A/B/C/D），不要解释。'
        else:
            type_hint = '这是一道填空/简答题，请直接返回答案内容（不要返回选项字母），简洁作答，不要解释。'

        if opt_text:
            return f"""{type_hint}

题目：{question}

选项：
{opt_text}

答案："""
        else:
            return f"""{type_hint}

题目：{question}

答案："""

    def _extract_answer(self, content: str, is_choice: bool = True) -> str:
        import re
        if not is_choice:
            # 非选择题：直接返回文本内容（去掉引号、多余空白）
            text = content.strip().strip('"').strip("'").strip('`')
            # 去掉可能的 "答案：" 前缀
            text = re.sub(r'^答案[：:]\\s*', '', text)
            return text[:500] if text else content[:500]
        # 多选答案：如 "ABC"、"A B C"、"A、B、C"
        multi = re.findall(r'[A-Ha-h]', content)
        if len(multi) > 1:
            return ''.join(multi).upper()
        # 单选答案
        if multi:
            return multi[0].upper()
        match = re.search(r'[A-Ha-h]', content)
        if match:
            return match.group(0).upper()
        return content[:50]


class WorkSubmitter:
    def __init__(self, session: httpx.Client, base_url: str, work_id: int,
                 referer_url: str = '', submit_type: str = 'work', node_id: str = ''):
        self.session = session
        from infrastructure.exam_login import normalize_base_url
        self.base_url = normalize_base_url(base_url)
        self.work_id = work_id
        self.referer_url = referer_url or self.base_url
        self.submit_type = submit_type
        self.node_id = node_id

    def _safe_json(self, resp) -> Dict:
        raw_bytes = resp.content or b''
        status = resp.status_code
        if not raw_bytes.strip():
            logger.error(f"服务器返回空响应 (status={status})")
            return {"status": False, "msg": "服务器返回空响应", "code": status}
        try:
            return resp.json()
        except Exception as e:
            try:
                raw = raw_bytes.decode('utf-8-sig')
                if raw.startswith('<') or raw.startswith('\n<'):
                    logger.error(f"服务器返回HTML而非JSON (status={status}, 前200字符: {raw[:200]})")
                    return {"status": False, "msg": "服务器返回HTML(可能需重新登录)", "code": status}
                return json.loads(raw)
            except Exception as e:
                logger.error(f"JSON解析失败 (status={status}, 内容: {raw_bytes[:200]!r}): {e}")
                return {"status": False, "msg": str(e), "code": status}

    def _post_json(self, url: str, data: Dict) -> Dict:
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": self.referer_url,
        }
        resp = self.session.post(url, data=data, headers=headers, timeout=15)
        return self._safe_json(resp)

    def _get_submit_url(self) -> str:
        if self.submit_type == 'exam':
            return f"{self.base_url}/user/exam/submit"
        return f"{self.base_url}/user/work/submit"

    def _get_id_key(self) -> str:
        return 'examId' if self.submit_type == 'exam' else 'workId'

    def submit_topic(self, answer_id: str, answer: str, q_type: str = '') -> Dict:
        url = self._get_submit_url()
        is_choice = '单选' in q_type or '多选' in q_type or '判断' in q_type

        # 多选题: answer[]=B&answer[]=C
        if '多选' in q_type and len(answer) > 1:
            data = [
                ('answerId', answer_id),
                (self._get_id_key(), str(self.work_id)),
            ]
            for ch in answer.upper():
                if ch in 'ABCDEFGH':
                    data.append(('answer[]', ch))
            if self.submit_type == 'exam' and self.node_id:
                data.append(('nodeId', self.node_id))
        elif not is_choice:
            # 非选择题（填空/简答）：用 content 字段
            data = {
                'content': answer,
                'answerId': answer_id,
                self._get_id_key(): str(self.work_id),
            }
            if self.submit_type == 'exam' and self.node_id:
                data['nodeId'] = self.node_id
        else:
            data = {
                'answer': answer,
                'answerId': answer_id,
                self._get_id_key(): str(self.work_id),
            }
            if self.submit_type == 'exam' and self.node_id:
                data['nodeId'] = self.node_id
        return self._post_json(url, data)

    def final_submit(self, answer_id: str = '', answer: str = '') -> Dict:
        url = self._get_submit_url()
        data = {
            self._get_id_key(): str(self.work_id),
            'finish': '1',
        }
        if answer_id:
            data['answerId'] = answer_id
        if answer:
            data['answer'] = answer
        if self.submit_type == 'exam' and self.node_id:
            data['nodeId'] = self.node_id
        return self._post_json(url, data)


class AIWorkRunner:
    def __init__(self, base_url: str, api_key: str,
                 cookie_str: Optional[str] = None,
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 model: str = "deepseek-chat"):
        from infrastructure.exam_login import LoginHelper, normalize_base_url
        self.base_url = normalize_base_url(base_url)
        self.api_key = api_key
        self.model = model
        self.session = None

        if cookie_str:
            self.session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
            self.session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            })
            for item in cookie_str.split(';'):
                item = item.strip()
                if '=' in item:
                    k, v = item.split('=', 1)
                    self.session.cookies.set(k.strip(), v.strip())
            logger.info("使用提供的 cookie 字符串。")
        elif username and password:
            helper = LoginHelper(self.base_url)
            self.session = helper.login(username, password)
            if self.session is None:
                raise Exception("登录失败。")
            self.session.headers.update({
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            })
        else:
            raise ValueError("必须提供 cookie_str 或 (username, password)。")

    def run(self, work_id: int, course_id: int, node_id: int, auto_submit: bool = False):
        from infrastructure.exam_login import OnlineHeartbeat
        heartbeat = OnlineHeartbeat(
            session=self.session,
            online_url=f'{self.base_url}/user/online',
            login_url=f'{self.base_url}/user/login'
        )
        try:
            heartbeat.start()

            fetcher = TopicFetcher(self.session, self.base_url)
            work_data = fetcher.fetch(work_id, course_id, node_id)
            logger.info(f"已获取作业 '{work_data['work_title']}'，共 {len(work_data['topics'])} 道题。")

            submit_type = fetcher._submit_type if hasattr(fetcher, '_submit_type') else 'work'
            if submit_type == 'exam':
                model = "deepseek-v4-flash"
            else:
                model = "deepseek-chat"
            logger.info(f"使用模型: {model} (类型: {submit_type})")

            answerer = AIAnswerer(self.api_key, model=model)
            answers = {}
            for topic in work_data['topics']:
                tid = topic['topic_id']
                ai_res = answerer.ask_one_topic(topic)
                answer = ai_res.get('answer', '').strip()
                if not answer:
                    q_type = topic.get('q_type', '')
                    is_ch = '单选' in q_type or '多选' in q_type or '判断' in q_type
                    answer = 'A' if is_ch else '暂无'
                answers[tid] = answer
                logger.info(f"第{topic['number']}题 -> {answer}（置信度 {ai_res.get('confidence', 0)}）")

            with open(f'answers_{work_id}.json', 'w', encoding='utf-8') as f:
                json.dump(answers, f, ensure_ascii=False, indent=2)
            logger.info(f"答案已保存到 answers_{work_id}.json")

            if auto_submit and work_data['node_id']:
                referer_url = self.base_url
                submit_type = fetcher._submit_type if hasattr(fetcher, '_submit_type') else 'work'
                submitter = WorkSubmitter(self.session, self.base_url, work_data['work_id'], referer_url, submit_type=submit_type, node_id=work_data.get('node_id', ''))
                logger.info("已启用自动提交，开始...")
                last_aid = ''
                ans = 'A'
                for topic in work_data['topics']:
                    aid = topic.get('answer_id', topic.get('topic_id', ''))
                    last_aid = aid
                    ans = answers.get(topic['topic_id'], answers.get(aid, 'A'))
                    q_type = topic.get('q_type', '')
                    ret = submitter.submit_topic(aid, ans, q_type=q_type)
                    if ret.get('status') == False:
                        logger.error(f"提交 {aid} 失败：{ret.get('msg')}")
                    else:
                        logger.info(f"已提交 {aid} -> {ans}")
                    time.sleep(0.5)
                final = submitter.final_submit(last_aid, ans)
                logger.info(f"最终提交结果：{final}")

            logger.info("任务完成。")
            return answers
        finally:
            heartbeat.stop()

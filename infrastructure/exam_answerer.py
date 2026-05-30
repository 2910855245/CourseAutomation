"""AI答题与提交模块"""

import json
import time
from typing import Dict, Optional

import httpx
from loguru import logger
from openai import OpenAI



class AIAnswerer:
    def __init__(self, api_key: str, model: str = "deepseek-v4-flash", base_url: str = "https://api.deepseek.com"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self._cache: Dict[str, str] = {}

    def ask_one_topic(self, topic: Dict, max_retries: int = 3) -> Dict:
        cache_key = topic.get('question', '')[:100]
        if cache_key in self._cache:
            return {'answer': self._cache[cache_key], 'confidence': 1.0}

        q_type = topic.get('q_type', '')
        is_choice = '单选' in q_type or '多选' in q_type or '判断' in q_type

        prompt = self._build_prompt(topic)
        token_limit = 1024

        last_error = None
        for attempt in range(max_retries):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=token_limit,
                    logprobs=True,
                    top_logprobs=5,
                    timeout=30,
                )
                content = resp.choices[0].message.content.strip()
                answer = self._extract_answer(content, is_choice=is_choice)

                # 如果答案为空且还有重试机会，继续重试
                if not answer and attempt < max_retries - 1:
                    logger.warning(f"AI返回空答案，重试 {attempt + 1}/{max_retries}")
                    time.sleep(1)
                    continue

                # 计算置信度
                confidence = self._calc_confidence(resp, answer, is_choice)

                self._cache[cache_key] = answer
                return {'answer': answer, 'confidence': confidence, 'raw': content}
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.warning(f"AI调用失败，重试 {attempt + 1}/{max_retries}: {e}")
                    time.sleep(2)
                    continue

        logger.error(f"AI回答失败（已重试{max_retries}次）: {last_error}")
        return {'answer': '', 'confidence': 0, 'error': str(last_error)}

    def _calc_confidence(self, resp, answer: str, is_choice: bool) -> float:
        """根据 logprobs 和答案质量计算置信度"""
        import math

        # 如果没有答案，置信度为0
        if not answer:
            return 0.0

        # 尝试从 logprobs 计算
        try:
            choice = resp.choices[0]
            if choice.logprobs and choice.logprobs.content:
                # 计算平均 logprob
                logprobs = []
                for token_info in choice.logprobs.content[:5]:  # 只看前5个token
                    if token_info.logprob is not None:
                        logprobs.append(token_info.logprob)

                if logprobs:
                    avg_logprob = sum(logprobs) / len(logprobs)
                    # 转换为 0-1 的置信度
                    # logprob 通常是负数，越接近0越自信
                    # e^(-1) ≈ 0.37, e^(0) = 1.0
                    confidence = min(1.0, max(0.1, math.exp(avg_logprob)))
                    return round(confidence, 2)
        except Exception:
            pass

        # 降级：基于答案格式的启发式判断
        if is_choice:
            # 选择题：答案格式正确就给较高置信度
            if answer in 'ABCDEFGH' or (len(answer) <= 4 and all(c in 'ABCDEFGH' for c in answer)):
                return 0.85
            return 0.6
        else:
            # 填空题：有答案就给中等置信度
            if len(answer) > 0:
                return 0.75
            return 0.5

    def _build_prompt(self, topic: Dict) -> str:
        question = topic.get('question', '')
        options = topic.get('options', [])
        q_type = topic.get('q_type', '')
        is_choice = '单选' in q_type or '多选' in q_type or '判断' in q_type
        opt_text = '\n'.join(options) if options else ''

        if '多选' in q_type:
            type_hint = '这是一道多选题，有多个正确答案。请仔细分析每个选项，返回所有正确选项的字母（如 ABC、ABD），不要解释。注意：多选少选均不得分。'
        elif '判断' in q_type:
            type_hint = '这是一道判断题，A表示正确，B表示错误，只返回一个字母。请仔细分析题干中的关键词。'
        elif is_choice:
            type_hint = '这是一道单选题，请仔细分析所有选项后返回最准确的答案字母（如 A/B/C/D），不要解释。'
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
            # 去掉代码块标记 ```lang ... ``` 或 ``` ... ```
            text = re.sub(r'^```\w*\s*\n?', '', content.strip())
            text = re.sub(r'\n?```\s*$', '', text)
            # 去掉引号、多余空白
            text = text.strip().strip('"').strip("'")
            # 去掉可能的 "答案：" 前缀
            text = re.sub(r'^答案[：:]\s*', '', text)
            return text[:5000] if text else content[:5000]
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
        logger.debug(f"提交数据: url={url}, data={data}")
        resp = self.session.post(url, data=data, headers=headers, timeout=15)
        result = self._safe_json(resp)
        logger.debug(f"提交结果: {result}")
        return result

    def _get_submit_url(self) -> str:
        if self.submit_type == 'exam':
            return f"{self.base_url}/user/exam/submit"
        return f"{self.base_url}/user/work/submit"

    def _get_id_key(self) -> str:
        return 'examId' if self.submit_type == 'exam' else 'workId'

    def submit_topic(self, answer_id: str, answer: str, q_type: str = '',
                     blank_count: int = 0) -> Dict:
        """提交单题答案

        Args:
            answer_id: 题目ID
            answer: 答案内容
            q_type: 题型（单选/多选/判断/填空/简答）
            blank_count: 填空题的空格数量（用于生成 answer_1, answer_2 等字段）
        """
        url = self._get_submit_url()
        is_choice = '单选' in q_type or '多选' in q_type or '判断' in q_type

        # 多选题: 需要 answer[]=A&answer[]=B 格式（重复key）
        if '多选' in q_type and len(answer) > 1:
            from urllib.parse import urlencode
            letters = [ch for ch in answer.upper() if ch in 'ABCDEFGH']
            pairs = [('answerId', answer_id), (self._get_id_key(), str(self.work_id))]
            for ch in letters:
                pairs.append(('answer[]', ch))
            if self.submit_type == 'exam' and self.node_id:
                pairs.append(('nodeId', self.node_id))
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": self.referer_url,
                "Content-Type": "application/x-www-form-urlencoded",
            }
            resp = self.session.post(url, content=urlencode(pairs).encode(), headers=headers, timeout=15)
            return self._safe_json(resp)
        elif '填空' in q_type and blank_count > 0:
            # 填空题: 需要 answer_1, answer_2 等格式
            from urllib.parse import urlencode
            parts = [p.strip() for p in answer.split(',') if p.strip()]
            pairs = [('answerId', answer_id), (self._get_id_key(), str(self.work_id))]
            for i in range(blank_count):
                val = parts[i] if i < len(parts) else (parts[-1] if parts else answer)
                pairs.append((f'answer_{i+1}', val))
            if self.submit_type == 'exam' and self.node_id:
                pairs.append(('nodeId', self.node_id))
            logger.debug(f"填空题提交: answer_id={answer_id}, blank_count={blank_count}, pairs={pairs}")
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": self.referer_url,
                "Content-Type": "application/x-www-form-urlencoded",
            }
            resp = self.session.post(url, content=urlencode(pairs).encode(), headers=headers, timeout=15)
            result = self._safe_json(resp)
            logger.debug(f"填空题结果: {result}")
            return result
        else:
            # 单选/判断/简答
            data = {
                'answer': answer,
                'answerId': answer_id,
                self._get_id_key(): str(self.work_id),
            }
            if self.submit_type == 'exam' and self.node_id:
                data['nodeId'] = self.node_id
        return self._post_json(url, data)

    def submit_topic_with_files(self, answer_id: str, answer: str,
                                 files_json: str = '[]', images_json: str = '[]') -> Dict:
        """提交带文件附件的题目（项目提交题型）"""
        url = self._get_submit_url()
        data = {
            'answer': answer,
            'answerId': answer_id,
            self._get_id_key(): str(self.work_id),
            'images': images_json,
            'files': files_json,
        }
        if self.submit_type == 'exam' and self.node_id:
            data['nodeId'] = self.node_id
        return self._post_json(url, data)

    def final_submit(self, answer_id: str = '', answer: str = '',
                     q_type: str = '', blank_count: int = 0) -> Dict:
        """交卷提交

        Args:
            answer_id: 最后一题的ID
            answer: 最后一题的答案
            q_type: 最后一题的题型
            blank_count: 填空题的空格数量
        """
        url = self._get_submit_url()
        data = {
            self._get_id_key(): str(self.work_id),
            'finish': '1',
        }
        if answer_id:
            data['answerId'] = answer_id
        if answer:
            # 填空题使用 answer_1 格式
            if '填空' in q_type and blank_count > 0:
                parts = [p.strip() for p in answer.split(',') if p.strip()]
                for i in range(blank_count):
                    val = parts[i] if i < len(parts) else (parts[-1] if parts else answer)
                    data[f'answer_{i+1}'] = val
            else:
                data['answer'] = answer
        if self.submit_type == 'exam' and self.node_id:
            data['nodeId'] = self.node_id
        logger.debug(f"交卷数据: {data}")
        return self._post_json(url, data)


class AIWorkRunner:
    def __init__(self, base_url: str, api_key: str,
                 cookie_str: Optional[str] = None,
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 model: str = "deepseek-v4-flash"):
        from infrastructure.exam_login import LoginHelper, normalize_base_url
        self.base_url = normalize_base_url(base_url)
        self.api_key = api_key
        self.model = model
        self.session = None

        if cookie_str:
            from infrastructure.http_session import create_sync_client
            self.session = create_sync_client()
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
            model = "deepseek-v4-flash"
            logger.info(f"使用模型: {model} (类型: {submit_type})")

            answerer = AIAnswerer(self.api_key, model=model)
            answers = {}
            total_topics = len(work_data['topics'])
            ai_failed = 0
            for topic in work_data['topics']:
                tid = topic['topic_id']
                q_type = topic.get('q_type', '')
                is_multi = '多选' in q_type
                is_choice = '单选' in q_type or is_multi or '判断' in q_type

                answer = ''
                # 最多重试 3 次（含首次）
                for attempt in range(3):
                    try:
                        ai_res = answerer.ask_one_topic(topic)
                        answer = ai_res.get('answer', '').strip()
                    except Exception as e:
                        logger.warning(f"第{topic['number']}题 AI 答题异常(第{attempt+1}次): {e}")
                        answer = ''

                    if not answer:
                        continue  # 空答案重试

                    # 校验答案有效性
                    if is_choice:
                        import re as _re
                        letters = _re.findall(r'[A-H]', answer.upper())
                        if not letters:
                            logger.warning(f"第{topic['number']}题 答案无有效选项: \"{answer}\", 重试")
                            answer = ''
                            continue
                        if is_multi and len(letters) < 2:
                            logger.warning(f"第{topic['number']}题 多选题仅1个选项: \"{answer}\", 重试")
                            answer = ''
                            continue

                    break  # 答案有效，跳出重试

                # 3 次重试后仍无有效答案
                if not answer or (is_choice and not re.findall(r'[A-H]', answer.upper())):
                    logger.error(f"第{topic['number']}题 AI 3次答题均失败，标记为失败")
                    ai_failed += 1
                    answers[tid] = ''
                else:
                    answers[tid] = answer
                logger.info(f"第{topic['number']}题 -> {answers[tid]}")

            with open(f'answers_{work_id}.json', 'w', encoding='utf-8') as f:
                json.dump(answers, f, ensure_ascii=False, indent=2)
            logger.info(f"答案已保存到 answers_{work_id}.json")

            if auto_submit and work_data['node_id']:
                # 题目没答完不准交卷
                if len(answers) < total_topics:
                    logger.error(f"题目未答完：共 {total_topics} 道，仅答 {len(answers)} 道，跳过提交")
                    return answers
                if ai_failed > 0:
                    logger.error(f"有 {ai_failed} 道题 AI 答题失败，跳过提交")
                    return answers
                # 校验所有答案非空
                empty_answers = [tid for tid, ans in answers.items() if not ans]
                if empty_answers:
                    logger.error(f"有 {len(empty_answers)} 道题答案为空，跳过提交")
                    return answers
                referer_url = self.base_url
                submit_type = fetcher._submit_type if hasattr(fetcher, '_submit_type') else 'work'
                submitter = WorkSubmitter(self.session, self.base_url, work_data['work_id'], referer_url, submit_type=submit_type, node_id=work_data.get('node_id', ''))
                logger.info("已启用自动提交，开始...")
                last_aid = ''
                ans = 'A'
                submit_ok = 0
                submit_fail = 0
                for topic in work_data['topics']:
                    aid = topic.get('answer_id', topic.get('topic_id', ''))
                    last_aid = aid
                    ans = answers.get(topic['topic_id'], answers.get(aid, 'A'))
                    q_type = topic.get('q_type', '')
                    # 最多重试 2 次
                    for attempt in range(3):
                        try:
                            ret = submitter.submit_topic(aid, ans, q_type=q_type)
                        except Exception as e:
                            logger.warning(f"提交异常(网络波动)，重试 {attempt+1}/2: {e}")
                            if attempt < 2:
                                time.sleep(1)
                                continue
                            submit_fail += 1
                            break
                        if ret.get('status') is False:
                            if attempt < 2:
                                logger.warning(f"答案保存异常(网络波动)，重试 {attempt+1}/2")
                                time.sleep(1)
                                continue
                            logger.error(f"答案保存失败(网络超时/服务器繁忙)：{aid}")
                            submit_fail += 1
                        else:
                            submit_ok += 1
                            logger.info(f"已提交 {aid} -> {ans}")
                        break
                    time.sleep(0.5)
                # 有题目提交失败则不交卷
                if submit_fail > 0:
                    logger.error(f"有 {submit_fail} 道题因网络波动保存失败（成功 {submit_ok}），跳过交卷")
                else:
                    final = submitter.final_submit(last_aid, ans)
                    logger.info(f"最终提交结果：{final}")

            logger.info("任务完成。")
            return answers
        finally:
            heartbeat.stop()

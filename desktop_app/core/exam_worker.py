"""AI 考试答题引擎 — 回调式，无 PyQt 依赖"""
import os
import sys
import threading
import time
from typing import Dict

from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ExamWorker:
    """考试答题工作线程（回调式）"""

    def __init__(self, session, base_url, api_key, exams, website_id=1,
                 on_progress=None, on_finished=None, on_log=None):
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.exams = exams
        self.website_id = website_id
        self.on_progress = on_progress
        self.on_finished = on_finished
        self.on_log = on_log
        self._running = False
        self._thread = None

    def _log(self, msg):
        if self.on_log:
            self.on_log(msg)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        total = len(self.exams)
        success_count = 0
        errors = []

        for i, exam in enumerate(self.exams):
            if not self._running:
                break

            exam_name = exam.get("name", f"考试{i+1}")
            if self.on_progress:
                self.on_progress({"current": i + 1, "total": total,
                                  "exam_name": exam_name, "message": f"答题 {i+1}/{total}: {exam_name}"})
            self._log(f"开始答题: {exam_name}")

            try:
                result = self._solve_single_exam(exam)
                if result.get("success"):
                    success_count += 1
                    self._log(f"✓ 完成: {exam_name} (提交{result.get('submitted', 0)}题)")
                else:
                    err = result.get("error", "未知错误")
                    errors.append(f"{exam_name}: {err}")
                    self._log(f"✗ 失败: {exam_name} - {err}")
            except Exception as e:
                errors.append(f"{exam_name}: {e}")
                self._log(f"✗ 异常: {exam_name} - {e}")

            time.sleep(1)

        if self.on_finished:
            if success_count == total:
                self.on_finished(True, f"全部完成 {success_count}/{total}")
            else:
                self.on_finished(False, f"完成 {success_count}/{total}: {'; '.join(errors[:3])}")

    def _solve_single_exam(self, exam: dict) -> Dict:
        from openai import OpenAI

        work_id = exam.get("work_id", "")
        course_id = exam.get("course_id", "")
        node_id = exam.get("node_id", "")
        wid = int(work_id) if str(work_id).isdigit() else work_id
        cid = int(course_id) if str(course_id).isdigit() else 0
        nid = int(node_id) if str(node_id).isdigit() else 0

        topics = self._fetch_topics(wid, cid, nid)
        if not topics:
            return {"success": False, "error": "未获取到题目"}

        self._log(f"  获取到 {len(topics)} 道题")

        client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
        answers = {}
        for topic in topics:
            tid = topic["topic_id"]
            try:
                answer = self._ask_ai(client, topic)
                answers[tid] = answer
                self._log(f"  第{topic.get('number', '?')}题 -> {answer[:50]}...")
            except Exception as e:
                answers[tid] = ""
                self._log(f"  第{topic.get('number', '?')}题 AI失败: {e}")
            time.sleep(0.3)

        submitted = 0
        for topic in topics:
            aid = topic.get("answer_id", topic.get("topic_id", ""))
            ans = answers.get(topic["topic_id"], answers.get(aid, ""))
            if not ans:
                continue
            try:
                ok = self._submit_answer(aid, ans, topic.get("q_type", ""), topic.get("blank_count", 0))
                if ok:
                    submitted += 1
            except Exception:
                pass
            time.sleep(0.5)

        if submitted > 0:
            last_topic = topics[-1] if topics else {}
            last_aid = last_topic.get("answer_id", last_topic.get("topic_id", ""))
            try:
                self._final_submit(last_aid, answers.get(last_aid, "A"))
            except Exception:
                pass

        return {"success": submitted > 0, "total": len(topics), "submitted": submitted}

    def _fetch_topics(self, work_id, course_id, node_id) -> list:
        try:
            base = self.base_url
            self.session.post(f"{base}/user/start_work",
                              data={"workId": work_id, "courseId": course_id, "nodeId": node_id}, timeout=15)
            resp = self.session.get(f"{base}/user/work",
                                    params={"workId": work_id, "courseId": course_id, "nodeId": node_id}, timeout=15)
            from scrapling.parser import Adaptor
            tree = Adaptor(resp.text, adaptive=True)
            topics = []
            items = tree.xpath('//div[contains(@class,"topic-item")]') or tree.xpath('//div[contains(@class,"courseexamcon")]')
            for idx, item in enumerate(items):
                html = str(item)
                q_type = "radio"
                if "type-radio" in html or "单选" in html:
                    q_type = "radio"
                elif "type-checkbox" in html or "多选" in html:
                    q_type = "checkbox"
                elif "type-blank" in html or "填空" in html:
                    q_type = "blank"
                elif "type-judge" in html or "判断" in html:
                    q_type = "judge"
                question = ""
                q_el = item.xpath('.//div[contains(@class,"topic-title")]') or item.xpath('.//div[contains(@class,"question")]')
                if q_el:
                    try:
                        question = q_el[0]._root.text_content().strip()[:500]
                    except Exception:
                        pass
                options = []
                for opt in (item.xpath('.//div[contains(@class,"option")]') or item.xpath('.//label')):
                    try:
                        t = opt._root.text_content().strip()
                        if t:
                            options.append(t)
                    except Exception:
                        pass
                topics.append({
                    "topic_id": item.attrib.get("data-id", str(idx)),
                    "answer_id": item.attrib.get("data-answer-id", item.attrib.get("data-id", str(idx))),
                    "number": idx + 1, "q_type": q_type,
                    "question": question, "options": options, "blank_count": 0,
                })
            return topics
        except Exception as e:
            logger.error("获取题目失败: %s", e)
            return []

    def _ask_ai(self, client, topic: dict) -> str:
        q_type = topic.get("q_type", "radio")
        question = topic.get("question", "")
        options = topic.get("options", [])
        prompt = f"题目类型: {q_type}\n题目: {question}\n"
        if options:
            prompt += "选项:\n" + "\n".join(options) + "\n"
        type_hint = {"radio": "请只回答一个选项字母（如 A）", "checkbox": "请回答多个选项字母（如 AB 或 ACD）",
                     "judge": "请只回答 对 或 错", "blank": "请直接回答填空内容"}
        prompt += type_hint.get(q_type, "请直接回答")
        resp = client.chat.completions.create(model="deepseek-chat",
                                               messages=[{"role": "user", "content": prompt}],
                                               max_tokens=100, temperature=0.1)
        return resp.choices[0].message.content.strip()

    def _submit_answer(self, answer_id, answer, q_type="", blank_count=0) -> bool:
        data = {"answerId": answer_id, "answer": answer}
        if q_type == "blank" and blank_count > 0:
            data["blankCount"] = blank_count
        resp = self.session.post(f"{self.base_url}/user/answer", data=data, timeout=10)
        return resp.json().get("status") is not False

    def _final_submit(self, answer_id, answer) -> dict:
        resp = self.session.post(f"{self.base_url}/user/submit_work",
                                 data={"answerId": answer_id, "answer": answer}, timeout=15)
        return resp.json()

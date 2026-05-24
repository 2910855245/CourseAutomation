"""
独立答题脚本 — 不依赖主项目的 config.py / 数据库 / FastAPI
依赖: pip install httpx beautifulsoup4 openai ddddocr loguru

用法:
  # 单账号单考试
  python standalone_exam.py --user 251010560108 --password xxx --platform 1 --work-id 12345 --course-id 678 --node-id 0

  # 单账号全部考试（扫描课程列表，遍历所有考试/作业）
  python standalone_exam.py --user 251010560108 --password xxx --platform 1

  # 批量账号（JSON 文件）
  python standalone_exam.py --accounts accounts.json

  accounts.json 格式:
  [
    {"username": "251010560108", "password": "xxx", "platform": 1},
    {"username": "251010560109", "password": "yyy", "platform": 2}
  ]
"""

import argparse
import json
import os
import random
import re
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from loguru import logger
import urllib3
from bs4 import BeautifulSoup
from openai import OpenAI

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== 平台配置 ====================
WEBSITES = {
    1: {"name": "在线课程测评考试平台", "base_url": "https://cdcas.suwankj.com"},
    2: {"name": "劳动课程测评考试平台", "base_url": "https://cdcas.taiskeji.com"},
    3: {"name": "公益课程平台", "base_url": "https://cdcas.chaoxiankeji.com"},
}

# DeepSeek API 配置（在此填入你的 key，或通过 --api-key 参数传入）
DEFAULT_API_KEY = ""
DEFAULT_API_BASE = "https://api.deepseek.com"

# 浏览器 UA 列表
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

# ==================== 工具函数 ====================

def normalize_base_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def get_dynamic_headers(ref_url: str = None) -> dict:
    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    if ref_url:
        headers["Referer"] = ref_url
    return headers


# ==================== OCR 验证码 ====================

_ocr_instance = None

def _get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        import ddddocr
        _ocr_instance = ddddocr.DdddOcr(show_ad=False)
    return _ocr_instance


# ==================== 登录模块 ====================

# schoolId 缓存（内存级别，同进程共享）
_school_id_cache: Dict[int, str] = {}


def _extract_school_ids(login_html: str) -> Optional[List[str]]:
    m = re.search(r'<select[^>]*id="schoolId"[^>]*>(.*?)</select>', login_html, re.DOTALL)
    if not m:
        return None
    options = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>', m.group(1))
    return [v for v in options if v]


def login_single_platform(website_id: int, username: str, password: str) -> Tuple[int, bool, httpx.Client, str]:
    """
    登录单个平台，返回 (website_id, success, session, message)
    """
    website = WEBSITES.get(website_id)
    if not website:
        return website_id, False, None, f"网站ID {website_id} 不存在"

    base_url = website["base_url"]
    login_url = f"{base_url}/user/login"
    captcha_url = f"{base_url}/service/code"

    session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
    ocr = _get_ocr()
    max_retries = 10
    retry = 0

    # 检查是否需要 schoolId
    school_ids = None
    school_id_index = 0
    try:
        login_headers = get_dynamic_headers()
        login_headers["Referer"] = login_url
        pre_check = session.get(login_url, headers=login_headers, timeout=15)
        school_ids = _extract_school_ids(pre_check.text)
        if school_ids:
            cached = _school_id_cache.get(website_id, "")
            if cached and cached in school_ids:
                school_id_index = school_ids.index(cached)
    except Exception:
        pass

    while retry < max_retries:
        retry += 1
        try:
            login_headers = get_dynamic_headers()
            login_headers["Referer"] = login_url
            session.get(login_url, headers=login_headers, timeout=15)

            captcha_headers = get_dynamic_headers(login_url)
            captcha_headers["Referer"] = login_url
            captcha_resp = session.get(captcha_url, headers=captcha_headers, timeout=15)
            code = ocr.classification(captcha_resp.content)

            data = {
                "username": username,
                "password": password,
                "code": code,
                "redirect": "",
                "remember": "on",
            }
            if school_ids and school_id_index < len(school_ids):
                data["schoolId"] = school_ids[school_id_index]

            result = session.post(login_url, data=data, headers=login_headers, follow_redirects=False, timeout=15)
            text = result.text

            if "验证码有误" in text:
                continue

            if "<title>操作成功提示</title>" in text or '"status":true' in text:
                if school_ids and school_id_index < len(school_ids):
                    _school_id_cache[website_id] = school_ids[school_id_index]
                if result.status_code == 302:
                    redirect_url = result.headers.get("Location", "")
                    if redirect_url:
                        if not redirect_url.startswith("http"):
                            redirect_url = base_url + redirect_url
                        session.get(redirect_url, headers=login_headers, timeout=15)
                return website_id, True, session, "登录成功"

            if "<title>错误提示</title>" in text:
                detail = ""
                match = re.search(r'<div class="name">(.*?)</div>', text, re.DOTALL)
                if match:
                    detail = match.group(1).strip()
                if not detail:
                    match = re.search(r'<div class="errormain"[^>]*>(.*?)</div>', text, re.DOTALL)
                    if match:
                        detail = re.sub(r"<[^>]+>", "", match.group(1)).strip()

                if "密码不可为空" in text:
                    return website_id, False, None, "密码不能为空"
                elif "学生学号不可为空" in text:
                    return website_id, False, None, "学号不能为空"

                if school_ids and school_id_index + 1 < len(school_ids):
                    school_id_index += 1
                    retry = 0
                    continue

                if "学生信息不存在" in text:
                    return website_id, False, None, "账号或密码错误"
                else:
                    return website_id, False, None, detail or "登录失败"

            # 未知响应，尝试下一个 schoolId
            if school_ids and school_id_index + 1 < len(school_ids):
                school_id_index += 1
                retry = 0
                continue

            return website_id, False, None, "登录失败：未知响应"

        except Exception as e:
            if retry >= max_retries:
                return website_id, False, None, f"登录异常: {e}"
            continue

    return website_id, False, None, "验证码重试次数过多"


# ==================== 心跳保活 ====================

class OnlineHeartbeat:
    def __init__(self, session: httpx.Client, online_url: str, login_url: str = ""):
        self.session = session
        self.online_url = online_url
        self.login_url = login_url
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self.session.get(self.online_url, timeout=10)
            except Exception:
                pass
            self._stop_event.wait(random.uniform(15, 25))


# ==================== 题目获取 ====================

class TopicFetcher:
    def __init__(self, session: httpx.Client, base_url: str):
        self.session = session
        self.base_url = normalize_base_url(base_url)
        self._submit_type = "work"

    def start_work(self, work_id: int, course_id: int, node_id: int,
                   item_type: str = "") -> Dict:
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": self.base_url,
        }

        if item_type == "exam":
            endpoints = [
                (f"{self.base_url}/user/exam/start",
                 {"examId": str(work_id), "courseId": str(course_id), "nodeId": str(node_id)}),
                (f"{self.base_url}/user/work/start",
                 {"workId": str(work_id), "courseId": str(course_id), "nodeId": str(node_id)}),
            ]
        else:
            endpoints = [
                (f"{self.base_url}/user/work/start",
                 {"workId": str(work_id), "courseId": str(course_id), "nodeId": str(node_id)}),
                (f"{self.base_url}/user/exam/start",
                 {"examId": str(work_id), "courseId": str(course_id), "nodeId": str(node_id)}),
            ]

        last_result = {}
        for url, data in endpoints:
            resp = self.session.post(url, data=data, headers=headers, timeout=15)
            result = resp.json()
            if result.get("status"):
                return result
            last_result = result

        return last_result

    def fetch(self, work_id: int, course_id: int, node_id: int,
              item_type: str = "") -> Dict:
        start_res = self.start_work(work_id, course_id, node_id, item_type=item_type)
        if not start_res.get("status"):
            msg = start_res.get("msg", "")
            logger.warning(f"开始作业失败: {start_res}")
            if "已删除" in msg or "已结束" in msg or "已经结束" in msg or "不存在" in msg:
                return {
                    "work_id": work_id,
                    "work_title": "",
                    "node_id": str(node_id),
                    "exam_id": "",
                    "topics": [],
                    "error": msg,
                }

        url = f"{self.base_url}/user/work?workId={work_id}&courseId={course_id}&nodeId={node_id}"
        resp = self.session.get(url, timeout=15)
        html = resp.text

        if "/exam/" in html or "examId" in html:
            self._submit_type = "exam"
        else:
            self._submit_type = "work"

        return self._parse_topics(html, work_id)

    def _parse_topics(self, html: str, work_id: int) -> Dict:
        soup = BeautifulSoup(html, "html.parser")

        exam_id = ""
        node_id = ""
        for inp in soup.find_all("input", type="hidden"):
            name = inp.get("name", "") or inp.get("id", "")
            value = inp.get("value", "")
            if "examId" in name:
                exam_id = value
            elif "nodeId" in name:
                node_id = value

        title_el = soup.find("h2") or soup.find("h3") or soup.find("title")
        work_title = title_el.get_text(strip=True) if title_el else f"作业{work_id}"

        topics = self._parse_topics_from_forms(soup)

        if not topics:
            topic_items = soup.select(".topic-item, .question-item, .topic, .question")
            if not topic_items:
                topic_items = soup.find_all("div", class_=re.compile(r"topic|question"))
            for idx, item in enumerate(topic_items, 1):
                topic = self._parse_single_topic(item, idx)
                if topic:
                    topics.append(topic)

        if not topics:
            topics = self._parse_topics_regex(html)

        return {
            "work_id": work_id,
            "work_title": work_title,
            "node_id": node_id or str(work_id),
            "exam_id": exam_id,
            "topics": topics,
        }

    def _parse_topics_from_forms(self, soup: BeautifulSoup) -> List[Dict]:
        topics = []

        topic_heads = soup.find_all("a", class_="topic-head")
        head_id_map = {}
        for idx, a in enumerate(topic_heads):
            data_id = a.get("data-id", "")
            if data_id:
                head_id_map[idx] = data_id

        forms = soup.find_all("form", action=lambda x: x and "submit" in str(x))

        for idx, form in enumerate(forms):
            num_el = form.find("div", class_="num")
            number = len(topics) + 1
            if num_el:
                num_span = num_el.find("span")
                if num_span:
                    try:
                        number = int(num_span.get_text(strip=True))
                    except ValueError:
                        pass

            name_el = form.find("div", class_="name")
            question = name_el.get_text(strip=True) if name_el else ""
            if not question:
                continue

            options = []
            list_el = form.find("div", class_="list")
            if list_el:
                for label in list_el.find_all("label"):
                    opt_text = label.get_text(strip=True)
                    if opt_text:
                        options.append(opt_text)

            type_el = form.find("div", class_="type")
            q_type = type_el.get_text(strip=True) if type_el else ""
            is_choice = "单选" in q_type or "多选" in q_type or "判断" in q_type

            answer_id = head_id_map.get(idx, str(number))

            topics.append({
                "number": number,
                "topic_id": answer_id,
                "answer_id": answer_id,
                "question": question,
                "options": options,
                "type": "choice" if is_choice else "text",
                "q_type": q_type,
            })

        return topics

    def _parse_single_topic(self, item, number: int) -> Dict:
        text = item.get_text(separator="\n", strip=True)

        answer_id_el = item.find(attrs={"name": re.compile(r"answerId|topic_id")})
        answer_id = answer_id_el.get("value", "") if answer_id_el else ""

        topic_id_el = item.find(attrs={"name": re.compile(r"topicId|topic_id")})
        topic_id = topic_id_el.get("value", "") if topic_id_el else answer_id

        options = []
        for opt in item.find_all(["label", "span", "div"], class_=re.compile(r"option|choice")):
            opt_text = opt.get_text(strip=True)
            if opt_text and len(opt_text) < 200:
                options.append(opt_text)

        return {
            "number": number,
            "topic_id": topic_id or str(number),
            "answer_id": answer_id or topic_id or str(number),
            "question": text[:500],
            "options": options,
            "type": "choice" if options else "text",
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
                "number": idx,
                "topic_id": tid,
                "answer_id": tid,
                "question": f"题目{idx}",
                "options": [],
                "type": "choice",
            })
        return topics


# ==================== AI 答题 ====================

class AIAnswerer:
    def __init__(self, api_key: str, model: str = "deepseek-chat", base_url: str = None):
        self.client = OpenAI(api_key=api_key, base_url=base_url or DEFAULT_API_BASE)
        self.model = model
        self._cache: Dict[str, str] = {}

    def ask_one_topic(self, topic: Dict) -> Dict:
        cache_key = topic.get("question", "")[:100]
        if cache_key in self._cache:
            return {"answer": self._cache[cache_key], "confidence": 1.0}

        q_type = topic.get("q_type", "")
        is_choice = "单选" in q_type or "多选" in q_type or "判断" in q_type

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
            return {"answer": answer, "confidence": 0.9, "raw": content}
        except Exception as e:
            logger.error(f"AI回答失败: {e}")
            return {"answer": "", "confidence": 0, "error": str(e)}

    def _build_prompt(self, topic: Dict) -> str:
        question = topic.get("question", "")
        options = topic.get("options", [])
        q_type = topic.get("q_type", "")
        is_choice = "单选" in q_type or "多选" in q_type or "判断" in q_type
        opt_text = "\n".join(options) if options else ""

        if "多选" in q_type:
            type_hint = "这是一道多选题，请返回所有正确选项的字母（如 ABC、ABD），不要解释。"
        elif "判断" in q_type:
            type_hint = "这是一道判断题，A表示正确，B表示错误，只返回一个字母。"
        elif is_choice:
            type_hint = "请回答以下题目，只返回答案字母（如 A/B/C/D），不要解释。"
        else:
            type_hint = "这是一道填空/简答题，请直接返回答案内容（不要返回选项字母），简洁作答，不要解释。"

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
        if not is_choice:
            text = content.strip().strip('"').strip("'").strip("`")
            text = re.sub(r"^答案[：:]\s*", "", text)
            return text[:500] if text else content[:500]
        multi = re.findall(r"[A-Ha-h]", content)
        if len(multi) > 1:
            return "".join(multi).upper()
        if multi:
            return multi[0].upper()
        match = re.search(r"[A-Ha-h]", content)
        if match:
            return match.group(0).upper()
        return content[:50]


# ==================== 答案提交 ====================

class WorkSubmitter:
    def __init__(self, session: httpx.Client, base_url: str, work_id: int,
                 referer_url: str = "", submit_type: str = "work", node_id: str = ""):
        self.session = session
        self.base_url = normalize_base_url(base_url)
        self.work_id = work_id
        self.referer_url = referer_url or self.base_url
        self.submit_type = submit_type
        self.node_id = node_id

    def _safe_json(self, resp) -> Dict:
        raw_bytes = resp.content or b""
        status = resp.status_code
        if not raw_bytes.strip():
            return {"status": False, "msg": "服务器返回空响应", "code": status}
        try:
            return resp.json()
        except Exception:
            try:
                raw = raw_bytes.decode("utf-8-sig")
                if raw.startswith("<") or raw.startswith("\n<"):
                    return {"status": False, "msg": "服务器返回HTML(可能需重新登录)", "code": status}
                return json.loads(raw)
            except Exception as e:
                return {"status": False, "msg": str(e), "code": status}

    def _post_json(self, url: str, data) -> Dict:
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": self.referer_url,
        }
        resp = self.session.post(url, data=data, headers=headers, timeout=15)
        return self._safe_json(resp)

    def _get_submit_url(self) -> str:
        if self.submit_type == "exam":
            return f"{self.base_url}/user/exam/submit"
        return f"{self.base_url}/user/work/submit"

    def _get_id_key(self) -> str:
        return "examId" if self.submit_type == "exam" else "workId"

    def submit_topic(self, answer_id: str, answer: str, q_type: str = "") -> Dict:
        url = self._get_submit_url()
        is_choice = "单选" in q_type or "多选" in q_type or "判断" in q_type

        if "多选" in q_type and len(answer) > 1:
            data = [
                ("answerId", answer_id),
                (self._get_id_key(), str(self.work_id)),
            ]
            for ch in answer.upper():
                if ch in "ABCDEFGH":
                    data.append(("answer[]", ch))
            if self.submit_type == "exam" and self.node_id:
                data.append(("nodeId", self.node_id))
        elif not is_choice:
            data = {
                "content": answer,
                "answerId": answer_id,
                self._get_id_key(): str(self.work_id),
            }
            if self.submit_type == "exam" and self.node_id:
                data["nodeId"] = self.node_id
        else:
            data = {
                "answer": answer,
                "answerId": answer_id,
                self._get_id_key(): str(self.work_id),
            }
            if self.submit_type == "exam" and self.node_id:
                data["nodeId"] = self.node_id
        return self._post_json(url, data)

    def final_submit(self, answer_id: str = "", answer: str = "") -> Dict:
        url = self._get_submit_url()
        data = {
            self._get_id_key(): str(self.work_id),
            "finish": "1",
        }
        if answer_id:
            data["answerId"] = answer_id
        if answer:
            data["answer"] = answer
        if self.submit_type == "exam" and self.node_id:
            data["nodeId"] = self.node_id
        return self._post_json(url, data)


# ==================== 课程扫描 ====================

def get_courses(session: httpx.Client, base_url: str) -> List[Dict]:
    """从用户中心获取课程列表"""
    resp = session.get(f"{base_url}/user/index", timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    course_nodes = soup.select("div.user-course div.item")
    courses = []
    for node in course_nodes:
        name_el = node.select_one("div.name a")
        name = name_el.get_text(strip=True) if name_el else "未知课程"
        detail_link = name_el.get("href", "") if name_el else ""
        if detail_link and not detail_link.startswith("http"):
            detail_link = base_url + detail_link

        study_link = node.select_one("div.note div.status a")
        study_record_url = study_link.get("href", "") if study_link else ""
        if study_record_url and not study_record_url.startswith("http"):
            study_record_url = base_url + study_record_url

        course_id = None
        if study_record_url and "courseId=" in study_record_url:
            course_id = study_record_url.split("courseId=")[-1].split("&")[0]
        elif detail_link and "courseId=" in detail_link:
            course_id = detail_link.split("courseId=")[-1].split("&")[0]

        if course_id:
            courses.append({
                "name": name,
                "detail_link": detail_link,
                "study_record_url": study_record_url,
                "course_id": course_id,
            })
    return courses


def scan_exams(session: httpx.Client, base_url: str, course_ids: List[str] = None) -> List[Dict]:
    """扫描所有课程的考试/作业"""
    courses = get_courses(session, base_url)
    if not courses:
        logger.warning("未获取到课程列表")
        return []

    logger.info(f"获取到 {len(courses)} 门课程")
    all_exams = []

    for course in courses:
        cid = course.get("course_id", "")
        cname = course.get("name", "")
        if course_ids and cid not in course_ids:
            continue

        # 获取课程详情页，提取考试/作业链接
        detail_link = course.get("detail_link", "")
        if not detail_link:
            continue

        try:
            resp = session.get(detail_link, timeout=15)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            # 提取 userId
            user_id = ""
            for link in soup.find_all("a", href=True):
                lh = link.get("href", "")
                if "study_record" in lh:
                    m = re.search(r"userId=(\d+)", lh)
                    if m:
                        user_id = m.group(1)
                    break

            # 通过 AJAX 获取考试记录
            for record_type in ["exam", "work"]:
                ajax_url = f"{base_url}/user/study_record/{record_type}?courseId={cid}&json=1"
                if user_id:
                    ajax_url += f"&userId={user_id}"
                try:
                    ajax_resp = session.get(ajax_url, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=15)
                    data = ajax_resp.json()
                    if data.get("status"):
                        for item in data.get("list", []):
                            item["course_id"] = cid
                            item["course_name"] = cname
                            item["item_type"] = record_type
                            all_exams.append(item)
                except Exception:
                    pass

            # 从页面 HTML 解析考试/作业链接（包含未开始的考试）
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if "/user/work" in href or "/user/exam" in href:
                    wid_match = re.search(r"(?:workId|examId)=(\d+)", href)
                    nid_match = re.search(r"nodeId=(\d+)", href)
                    if wid_match:
                        wid = wid_match.group(1)
                        nid = nid_match.group(1) if nid_match else "0"
                        item_type = "exam" if "/exam/" in href else "work"
                        # 去重
                        if not any(str(e.get("work_id", e.get("id", ""))) == wid for e in all_exams):
                            all_exams.append({
                                "work_id": wid,
                                "id": wid,
                                "name": text or f"考试{wid}",
                                "course_id": cid,
                                "course_name": cname,
                                "node_id": nid,
                                "item_type": item_type,
                                "is_done": False,
                            })

            # 从 study_record 页面解析（补充 AJAX 未覆盖的）
            for record_type in ["exam", "work"]:
                record_url = f"{base_url}/user/study_record/{record_type}?courseId={cid}"
                if user_id:
                    record_url += f"&userId={user_id}"
                try:
                    record_resp = session.get(record_url, timeout=15)
                    record_resp.encoding = "utf-8"
                    record_soup = BeautifulSoup(record_resp.text, "html.parser")
                    # 解析 datatable 中的链接
                    for a in record_soup.find_all("a", href=True):
                        href = a.get("href", "")
                        text = a.get_text(strip=True)
                        if "/user/work" in href or "/user/exam" in href:
                            wid_match = re.search(r"(?:workId|examId)=(\d+)", href)
                            nid_match = re.search(r"nodeId=(\d+)", href)
                            if wid_match:
                                wid = wid_match.group(1)
                                nid = nid_match.group(1) if nid_match else "0"
                                item_type = "exam" if "/exam/" in href else "work"
                                if not any(str(e.get("work_id", e.get("id", ""))) == wid for e in all_exams):
                                    all_exams.append({
                                        "work_id": wid,
                                        "id": wid,
                                        "name": text or f"考试{wid}",
                                        "course_id": cid,
                                        "course_name": cname,
                                        "node_id": nid,
                                        "item_type": item_type,
                                        "is_done": False,
                                    })
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"扫描课程失败: {cname} - {e}")

    return all_exams


# ==================== 单场考试答题 ====================

def solve_exam(session: httpx.Client, base_url: str, exam: Dict, api_key: str,
               model: str = "deepseek-chat") -> Dict:
    """完成一场考试/作业的答题+提交"""
    base = normalize_base_url(base_url)
    work_id = exam.get("work_id", exam.get("id", ""))
    course_id = exam.get("course_id", "")
    node_id = exam.get("node_id", "")

    wid = int(work_id) if str(work_id).isdigit() else work_id
    cid = int(course_id) if course_id and str(course_id).isdigit() else 0
    nid = int(node_id) if node_id and str(node_id).isdigit() else 0

    heartbeat = OnlineHeartbeat(
        session=session,
        online_url=f"{base}/user/online",
        login_url=f"{base}/user/login",
    )
    try:
        heartbeat.start()

        fetcher = TopicFetcher(session, base)
        item_type = exam.get("item_type", "")
        work_data = fetcher.fetch(wid, cid, nid, item_type=item_type)
        topics = work_data.get("topics", [])
        if not topics:
            err = work_data.get("error", "") or "未获取到题目"
            return {"success": False, "error": err, "types": {}}

        # 题型统计
        type_counts: Dict[str, int] = {}
        for t in topics:
            qt = t.get("q_type", "未知")
            type_counts[qt] = type_counts.get(qt, 0) + 1

        # AI 答题
        answerer = AIAnswerer(api_key, model=model)
        answers = {}
        for topic in topics:
            tid = topic["topic_id"]
            ai_res = answerer.ask_one_topic(topic)
            answer = ai_res.get("answer", "").strip()
            if not answer:
                q_type = topic.get("q_type", "")
                is_ch = "单选" in q_type or "多选" in q_type or "判断" in q_type
                answer = "A" if is_ch else "暂无"
            answers[tid] = answer
            time.sleep(0.3)

        # 提交
        real_work_id = work_data.get("work_id", wid)
        node_id_str = work_data.get("node_id", "")
        submit_type = getattr(fetcher, "_submit_type", "work")
        submitter = WorkSubmitter(session, base, real_work_id, submit_type=submit_type, node_id=node_id_str)
        submitted = 0
        last_aid = ""
        for topic in topics:
            aid = topic.get("answer_id", topic.get("topic_id", ""))
            last_aid = aid
            ans = answers.get(topic["topic_id"], answers.get(aid, "A"))
            q_type = topic.get("q_type", "")
            ret = submitter.submit_topic(aid, ans, q_type=q_type)
            if ret.get("status") is False:
                err = ret.get("msg", "")
                if "已结束" in err or "已经结束" in err:
                    return {"success": False, "error": "考试已结束", "types": type_counts, "submitted": 0}
                logger.error(f"提交 {aid} 失败: {err}")
            else:
                submitted += 1
            time.sleep(0.5)

        final = submitter.final_submit(last_aid, answers.get(last_aid, "A"))
        ok = submitted > 0 and final.get("status") is not False

        return {
            "success": ok,
            "total": len(topics),
            "submitted": submitted,
            "types": type_counts,
            "final": final,
            "error": None if ok else final.get("msg", "提交失败"),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "types": {}}
    finally:
        heartbeat.stop()


# ==================== 主流程 ====================

def run_single_exam(args):
    """单场考试模式"""
    website = WEBSITES.get(args.platform)
    if not website:
        print(f"错误: 平台 {args.platform} 不存在")
        return

    print(f"登录 {website['name']}...")
    _, ok, session, msg = login_single_platform(args.platform, args.user, args.password)
    if not ok:
        print(f"登录失败: {msg}")
        return
    print(f"登录成功")

    exam = {
        "work_id": args.work_id,
        "course_id": args.course_id or "",
        "node_id": args.node_id or "0",
        "item_type": args.item_type or "",
    }

    print(f"开始答题: work_id={args.work_id}")
    result = solve_exam(session, website["base_url"], exam, args.api_key, model=args.model)

    if result.get("success"):
        print(f"✓ 成功 ({result.get('submitted', 0)}/{result.get('total', 0)} 题)")
        for qt, cnt in result.get("types", {}).items():
            print(f"  {qt}: {cnt}题")
    else:
        print(f"✗ 失败: {result.get('error')}")


def run_account_exams(args):
    """单账号全部考试模式"""
    website = WEBSITES.get(args.platform)
    if not website:
        print(f"错误: 平台 {args.platform} 不存在")
        return

    base_url = website["base_url"]
    print(f"登录 {website['name']}...")
    _, ok, session, msg = login_single_platform(args.platform, args.user, args.password)
    if not ok:
        print(f"登录失败: {msg}")
        return
    print(f"登录成功")

    print("扫描考试...")
    exams = scan_exams(session, base_url)
    if not exams:
        print("无考试/作业")
        return

    pending = [e for e in exams if not e.get("is_done")]
    print(f"找到 {len(exams)} 个考试/作业, 待考 {len(pending)}")

    success = 0
    failed = 0
    for i, exam in enumerate(pending):
        name = exam.get("name", f"考试{exam.get('work_id', '?')}")
        print(f"\n[{i+1}/{len(pending)}] {name}")

        result = solve_exam(session, base_url, exam, args.api_key, model=args.model)

        if result.get("success"):
            success += 1
            print(f"  ✓ 成功 ({result.get('submitted', 0)}/{result.get('total', 0)} 题)")
        else:
            failed += 1
            print(f"  ✗ 失败: {result.get('error')}")

        time.sleep(1)

    print(f"\n汇总: 成功 {success}, 失败 {failed}, 共 {len(pending)}")


def run_batch_accounts(args):
    """批量账号模式"""
    with open(args.accounts, "r", encoding="utf-8") as f:
        accounts = json.load(f)

    print(f"加载 {len(accounts)} 个账号")

    total_success = 0
    total_failed = 0

    for i, acc in enumerate(accounts):
        username = acc["username"]
        password = acc["password"]
        platform = acc.get("platform", 1)
        website = WEBSITES.get(platform, {})
        base_url = website.get("base_url", "")
        platform_name = website.get("name", f"平台{platform}")

        print(f"\n{'─' * 60}")
        print(f"[{i+1}/{len(accounts)}] {username} @ {platform_name}")
        print(f"{'─' * 60}")

        # 登录
        _, ok, session, msg = login_single_platform(platform, username, password)
        if not ok:
            print(f"  ✗ 登录失败: {msg}")
            continue
        print(f"  ✓ 登录成功")

        # 扫描
        exams = scan_exams(session, base_url)
        pending = [e for e in exams if not e.get("is_done")]
        print(f"  考试/作业: {len(exams)} 个, 待考 {len(pending)}")

        for j, exam in enumerate(pending):
            name = exam.get("name", f"考试{exam.get('work_id', '?')}")
            print(f"  [{j+1}/{len(pending)}] {name}")

            result = solve_exam(session, base_url, exam, args.api_key, model=args.model)

            if result.get("success"):
                total_success += 1
                print(f"    ✓ 成功 ({result.get('submitted', 0)}/{result.get('total', 0)})")
            else:
                total_failed += 1
                print(f"    ✗ 失败: {result.get('error')}")

            time.sleep(1)

    print(f"\n{'=' * 60}")
    print(f"汇总: 成功 {total_success}, 失败 {total_failed}")


def main():
    parser = argparse.ArgumentParser(description="独立答题脚本 — 不依赖主项目")
    parser.add_argument("--user", "-u", help="用户名/学号")
    parser.add_argument("--password", "-p", help="密码")
    parser.add_argument("--platform", "-P", type=int, default=1, help="平台ID (1=在线课程 2=劳动课程 3=公益课程)")
    parser.add_argument("--work-id", "-w", help="考试/作业ID（单场模式）")
    parser.add_argument("--course-id", "-c", help="课程ID")
    parser.add_argument("--node-id", "-n", help="节点ID")
    parser.add_argument("--item-type", "-t", choices=["exam", "work"], help="类型: exam 或 work")
    parser.add_argument("--api-key", "-k", default=DEFAULT_API_KEY, help="DeepSeek API Key")
    parser.add_argument("--model", "-m", default="deepseek-chat", help="AI模型 (默认 deepseek-chat)")
    parser.add_argument("--accounts", "-a", help="批量账号 JSON 文件路径")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="API Base URL")

    args = parser.parse_args()

    # 更新全局 API base
    global DEFAULT_API_BASE
    DEFAULT_API_BASE = args.api_base

    if not args.api_key:
        print("错误: 请通过 --api-key 或在脚本顶部 DEFAULT_API_KEY 设置 API Key")
        sys.exit(1)

    if args.accounts:
        run_batch_accounts(args)
    elif args.user and args.password and args.work_id:
        run_single_exam(args)
    elif args.user and args.password:
        run_account_exams(args)
    else:
        parser.print_help()
        print("\n示例:")
        print("  单场考试: python standalone_exam.py -u 251010560108 -p xxx -P 1 -w 12345 -c 678")
        print("  全部考试: python standalone_exam.py -u 251010560108 -p xxx -P 1")
        print("  批量账号: python standalone_exam.py -a accounts.json -k sk-xxx")


if __name__ == "__main__":
    main()

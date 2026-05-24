import re
import time
from typing import Dict, List, Optional

from scrapling.parser import Adaptor

from config import VIDEO_PARAM_IDS
from infrastructure.http_session import get_dynamic_headers, safe_request


def _s(val) -> str:
    """将 Scrapling Selector 转为 str"""
    return str(val) if val is not None else ""


def _text(el) -> str:
    """从 scrapling Selector 元素中安全提取文本内容（兼容 0.2.x 和 0.4.x）"""
    try:
        return el._root.text_content().strip()
    except Exception:
        try:
            return str(el).strip()
        except Exception:
            return ""


def get_current_base_url():
    """动态获取当前基础URL"""
    from config import get_base_url
    return get_base_url()


def get_courses(session) -> List[Dict]:
    """从用户中心获取课程列表（HTML 爬取，无 API 替代）"""
    from config import USER_CENTER_URL
    resp = safe_request(session, USER_CENTER_URL)
    if not resp:
        return []

    resp.encoding = "utf-8"
    tree = Adaptor(resp.text, adaptive=True)
    course_nodes = tree.xpath('//div[contains(@class,"user-course")]//div[@class="item"]')
    courses = []
    for node in course_nodes:
        name = node.xpath('.//div[@class="name"]/a/text()')
        name = _s(name[0]).strip() if name else "未知课程"

        from config import BASE_URL
        detail_link = node.xpath('.//div[@class="name"]/a/@href')
        detail_link = BASE_URL + _s(detail_link[0]) if detail_link else ""

        study_record_href = node.xpath('.//div[@class="note"]/div[@class="status"]/a/@href')
        study_record_url = BASE_URL + _s(study_record_href[0]) if study_record_href else ""

        course_id = None
        if study_record_url and "courseId=" in study_record_url:
            course_id = study_record_url.split("courseId=")[-1].split("&")[0]
        elif detail_link and "courseId=" in detail_link:
            course_id = detail_link.split("courseId=")[-1].split("&")[0]

        courses.append({
            "name": name,
            "detail_link": detail_link,
            "study_record_url": study_record_url,
            "course_id": course_id
        })
    return courses


# ==================== API 方式获取节点数据 ====================

def get_course_nodes_from_api(session, course_id: str, course_name: str = "") -> Dict:
    """通过 study_record API 获取课程的全部节点数据（纯爬取，不清洗）

    返回: {nodes: [...], videos: [...], exams: [...], works: [...]}
    字段值为 API 原始值，清洗由 data_cleaner 模块负责。
    """
    from config import BASE_URL

    result = {
        "nodes": [],
        "videos": [],
        "exams": [],
        "works": [],
    }

    headers = {"X-Requested-With": "XMLHttpRequest"}

    # 1. 获取视频
    videos = _fetch_all_pages(session, f"{BASE_URL}/user/study_record/video",
                              course_id, headers)
    for item in videos:
        node_id = item.get("id", "")
        item["course_name"] = course_name
        item["course_id"] = course_id
        result["videos"].append(item)
        result["nodes"].append({
            "nodeId": node_id,
            "name": item.get("name", ""),
            "url": item.get("url", f"/user/node?nodeId={node_id}"),
            "node_type": "video",
            "hidden_params": {
                "node_type": "video",
                "video-duration": item.get("duration", "0"),
                "video-file": item.get("localFile", ""),
            },
            "chapterId": item.get("chapterId", ""),
        })

    # 2. 获取考试
    exams = _fetch_all_pages(session, f"{BASE_URL}/user/study_record/exam",
                             course_id, headers)
    for item in exams:
        node_id = item.get("nodeId", "")
        exam_id = item.get("id", "")
        item["course_name"] = course_name
        item["course_id"] = course_id
        result["exams"].append(item)
        result["nodes"].append({
            "nodeId": node_id,
            "name": item.get("title", item.get("name", "")),
            "url": item.get("url", f"/user/node?nodeId={node_id}"),
            "node_type": "exam",
            "hidden_params": {
                "node_type": "exam",
                "work_id": exam_id,
                "topic_number": item.get("topicNumber", ""),
                "frequency": item.get("frequency", ""),
                "start_time": item.get("startTime", ""),
                "end_time": item.get("endTime", ""),
                "final_score": item.get("finalScore", "-"),
            },
            "chapterId": item.get("chapterId", ""),
        })

    # 3. 获取作业
    works = _fetch_all_pages(session, f"{BASE_URL}/user/study_record/work",
                             course_id, headers)
    for item in works:
        node_id = item.get("nodeId", "")
        work_id = item.get("id", "")
        item["course_name"] = course_name
        item["course_id"] = course_id
        result["works"].append(item)
        result["nodes"].append({
            "nodeId": node_id,
            "name": item.get("title", item.get("name", "")),
            "url": item.get("url", f"/user/node?nodeId={node_id}"),
            "node_type": "work",
            "hidden_params": {
                "node_type": "work",
                "work_id": work_id,
                "topic_number": item.get("topicNumber", ""),
                "frequency": item.get("frequency", ""),
                "final_score": item.get("finalScore", "-"),
                "type_name": item.get("typeName", ""),
            },
            "chapterId": item.get("chapterId", ""),
        })

    return result


def _fetch_all_pages(session, base_url: str, course_id: str, headers: dict) -> List[dict]:
    """分页获取所有数据"""
    all_items = []
    page = 1
    while True:
        try:
            resp = session.get(base_url, params={
                "courseId": course_id, "page": page
            }, headers=headers, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data.get("status"):
                break
            items = data.get("list", [])
            if not items:
                break
            all_items.extend(items)
            page_info = data.get("pageInfo", {})
            if page >= page_info.get("pageCount", 1):
                break
            page += 1
        except Exception as e:
            break
    return all_items


# ==================== 旧的 HTML 爬取函数（保留作为 fallback）====================

def get_first_study_link(session, detail_url: str) -> Optional[str]:
    resp = safe_request(session, detail_url)
    if not resp:
        return None
    tree = Adaptor(resp.text, adaptive=True)
    possible_xpaths = [
        '//a[contains(@href,"/user/node?nodeId=")]/@href',
        '//div[contains(@class,"course-detail")]//a[contains(@href,"node")]/@href',
        '//a[starts-with(@href,"/user/node?nodeId=")]/@href',
    ]
    for xp in possible_xpaths:
        hrefs = tree.xpath(xp)
        if hrefs:
            from config import BASE_URL
            h = _s(hrefs[0])
            full_url = BASE_URL + h if h.startswith('/') else h
            return full_url
    return None


def extract_all_nodes_from_study_page(html_content: str) -> List[Dict]:
    tree = Adaptor(html_content, adaptive=True)
    nodes = []
    for a in tree.xpath('//div[@class="detmain-navlist"]//div[@class="item"]/a'):
        name = _text(a)
        href = a.attrib.get('href')
        node_id = _s(href).split('nodeId=')[-1].split('&')[0] if href and 'nodeId=' in _s(href) else None
        if node_id:
            nodes.append({'name': name, 'nodeId': node_id, 'url': href})
    if not nodes:
        for a in tree.xpath('//div[contains(@class,"detmain-navlist")]//a[contains(@href,"nodeId=")]'):
            name = _text(a)
            href = a.attrib.get('href')
            node_id = _s(href).split('nodeId=')[-1].split('&')[0] if href else None
            if node_id and not any(n['nodeId'] == node_id for n in nodes):
                nodes.append({'name': name, 'nodeId': node_id, 'url': href})
    return nodes


def extract_node_params(session, node_url: str, retries=2) -> Dict:
    from config import BASE_URL
    full_url = BASE_URL + node_url if node_url.startswith('/') else node_url
    for attempt in range(retries + 1):
        try:
            headers = get_dynamic_headers()
            resp = session.get(full_url, headers=headers, timeout=10)
            resp.raise_for_status()
            if "SQLSTATE" in resp.text or "数据出现异常" in resp.text:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                continue
            tree = Adaptor(resp.text, adaptive=True)
            params = {'node_type': 'unknown', 'types': []}

            has_video = False
            has_work = False
            has_exam = False
            has_material = False

            tab_links = tree.xpath('//div[@class="detmain-tabs"]//a/@href')
            for link in tab_links:
                link = _s(link)
                if '/user/node/work' in link:
                    has_work = True
                    if 'work' not in params['types']:
                        params['types'].append('work')
                elif '/user/node/exam' in link:
                    has_exam = True
                    if 'exam' not in params['types']:
                        params['types'].append('exam')
                elif '/user/node/material' in link:
                    has_material = True
                    if 'material' not in params['types']:
                        params['types'].append('material')
                elif '/user/node' in link and 'nodeId=' in link:
                    has_video = True
                    if 'video' not in params['types']:
                        params['types'].append('video')

            video_file = tree.xpath('//input[@id="video-file"]/@value')
            if video_file or tree.xpath('//video/@src'):
                has_video = True
                if 'video' not in params['types']:
                    params['types'].append('video')
                if video_file:
                    for pid in VIDEO_PARAM_IDS:
                        values = tree.xpath(f'//input[@id="{pid}"]/@value')
                        params[pid] = _s(values[0]) if values else None
                else:
                    params['video-file'] = _s(tree.xpath('//video/@src')[0])

            work_link = tree.xpath('//div[@class="detmain-stard"]/a[contains(@href,"workId=")]/@href')
            if work_link:
                has_work = True
                if 'work' not in params['types']:
                    params['types'].append('work')
                wl = _s(work_link[0])
                params['work_url'] = wl
                if 'workId=' in wl:
                    params['work_id'] = wl.split('workId=')[-1].split('&')[0]

            exam_rows = tree.xpath('//div[@class="detmain-head"]/div[@class="row"]')
            exams = []
            for row in exam_rows:
                exam = {}
                link = row.xpath('.//div[@class="detmain-stard"]/a[contains(@href,"examId=")]')
                if link:
                    exam['status'] = _text(link[0])
                    href = link[0].attrib.get('href')
                    exam['url'] = href
                    if href and 'examId=' in _s(href):
                        exam['exam_id'] = _s(href).split('examId=')[-1].split('&')[0]
                title = row.xpath('.//div[@class="detmain-title"]/text()')
                if title:
                    raw_title = _s(title[0]).strip()
                    if raw_title.startswith('考试标题：'):
                        exam['title'] = raw_title.replace('考试标题：', '').strip()
                    else:
                        exam['title'] = raw_title
                if exam:
                    exams.append(exam)
            if exams:
                has_exam = True
                if 'exam' not in params['types']:
                    params['types'].append('exam')
                params['exams'] = exams

            if not has_video and not has_work and not has_exam:
                if tree.xpath('//a[contains(@href,"/user/node/material")]'):
                    has_material = True
                    if 'material' not in params['types']:
                        params['types'].append('material')

            if has_exam:
                params['node_type'] = 'exam'
            elif has_work:
                params['node_type'] = 'work'
            elif has_video:
                params['node_type'] = 'video'
            elif has_material:
                params['node_type'] = 'material'

            return params
        except Exception as e:
            if attempt < retries:
                wait_time = 1.5 ** attempt
                time.sleep(wait_time)
                continue
    return {'node_type': 'error', 'types': []}


def extract_student_name(html_content: str) -> str:
    """从个人中心 HTML 中提取学生姓名"""
    tree = Adaptor(html_content, adaptive=True)
    xpaths = [
        '//div[@class="user-head"]//div[@class="name"]/text()',
        '//div[@class="con"]//div[@class="name"]/text()',
        '//div[contains(@class,"user")]//div[@class="name"]/text()',
        '//div[@class="name"]/text()',
        '//span[contains(text(),"同学")]/text()',
        '//*[contains(text(),"欢迎")]//text()',
    ]
    for xp in xpaths:
        names = tree.xpath(xp)
        for n in names:
            n = _s(n).strip()
            if n and len(n) >= 2:
                return n
    m = re.search(r'欢迎[你您][，,]?\s*([^\s<]{2,6})', html_content)
    if m:
        return m.group(1).strip()
    for match in re.finditer(r'<div[^>]*class="name"[^>]*>\s*([^\s<]{2,10})\s*</div>', html_content):
        return match.group(1).strip()
    return ""


def get_course_list(session, website_id: int = None) -> List[Dict]:
    return get_courses(session)


def get_course_content(session, course_id: str, website_id: int = None) -> Optional[str]:
    courses = get_courses(session)
    target = None
    for c in courses:
        cid = c.get("course_id") or c.get("id")
        if cid == course_id:
            target = c
            break
    if not target:
        return None
    study_url = target.get("study_record_url") or target.get("detail_link")
    if not study_url:
        return None
    from config import BASE_URL
    full_url = BASE_URL + study_url if study_url.startswith('/') else study_url
    resp = safe_request(session, full_url)
    if not resp:
        return None
    resp.encoding = "utf-8"
    return resp.text


def transform_course_content(content: Optional[str]) -> List[Dict]:
    if not content:
        return []
    return extract_all_nodes_from_study_page(content)

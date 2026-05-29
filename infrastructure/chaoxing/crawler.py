"""学习通课程爬取 — 使用 scrapling 解析，统一返回原始数据"""
import json
import re
import time

from loguru import logger
from scrapling.parser import Adaptor

from infrastructure.chaoxing_session import ChaoxingSession



def _s(val) -> str:
    return str(val).strip() if val is not None else ""


def _text(el) -> str:
    """从 scrapling Selector 元素中安全提取文本内容（兼容 0.2.x 和 0.4.x）"""
    try:
        return el._root.text_content().strip()
    except Exception:
        try:
            return str(el).strip()
        except Exception:
            return ""


# ── 课程列表 ──────────────────────────────────────────────

def fetch_course_list(session: ChaoxingSession) -> list:
    """抓取课程列表 HTML，用 scrapling 解析

    返回: [{courseId, classId, name, teacher, ended, cover_url}, ...]
    """
    url = "https://mooc1-1.chaoxing.com/mooc-ans/visit/courselistdata"
    data = {
        "courseType": "1",
        "courseFolderId": "0",
        "baseEducation": "0",
        "superstarClass": "",
        "courseFolderSize": "0",
    }
    try:
        resp = session.post(url, data=data, referer="https://mooc1.chaoxing.com/")
        html = resp.text()
    except Exception as e:
        logger.error(f"获取课程列表失败 error={str(e)}")
        return []

    tree = Adaptor(html, adaptive=True)
    courses = []
    seen = set()

    for li in tree.xpath('//li[@class="course clearfix"]'):
        course_id = _s(li.attrib.get("courseid", ""))
        class_id = _s(li.attrib.get("clazzid", ""))
        if not course_id or not class_id:
            continue
        key = (course_id, class_id)
        if key in seen:
            continue
        seen.add(key)

        # 课程名
        name_els = li.xpath('.//span[contains(@class,"course-name")]/@title')
        name = _s(name_els[0]) if name_els else "未知课程"

        # 教师
        teacher_els = li.xpath('.//p[@class="line2"]/@title')
        teacher = _s(teacher_els[0]) if teacher_els else ""

        # 封面
        cover_els = li.xpath('.//div[@class="course-cover"]//img/@src')
        cover_url = _s(cover_els[0]) if cover_els else ""

        # 是否已结束: <a class="not-open-tip">Course has closed</a> 或含"课程已结束"
        ended = False
        closed_els = li.xpath('.//a[contains(@class,"not-open-tip")]')
        if closed_els:
            closed_text = _text(closed_els[0])
            if "closed" in closed_text.lower() or "已结束" in closed_text:
                ended = True

        courses.append({
            "courseId": course_id,
            "classId": class_id,
            "name": name,
            "teacher": teacher,
            "ended": ended,
            "cover_url": cover_url,
        })

    logger.info("获取课程列表 total={} ended={}", len(courses), sum(1 for c in courses if c["ended"]))
    return courses


# ── 知识点列表 ────────────────────────────────────────────

def fetch_knowledge_list(session: ChaoxingSession, course_id: str, class_id: str,
                         page_size: int = 100) -> list:
    """抓取课程知识点，用 scrapling 解析

    返回: [{knowledgeId, classId, name, has_video, video_minutes}, ...]
    """
    all_points = []
    page = 1

    while True:
        url = f"https://tsjy.chaoxing.com/plaza/knowledge-list?courseId={course_id}"
        try:
            resp = session.post(url, data={
                "personId": session.uid,
                "classId": class_id,
                "userId": session.uid,
                "classifyId": "",
                "element": "0",
                "point": "0",
                "name": "",
                "page": str(page),
                "pageSize": str(page_size),
            }, referer=f"https://tsjy.chaoxing.com/plaza/knowledge-all?courseId={course_id}")
            html = resp.text()
        except Exception as e:
            logger.warning(f"获取知识点失败 course_id={course_id} error={str(e)}")
            break

        tree = Adaptor(html, adaptive=True)
        li_blocks = tree.xpath('//li[@class="list"]')
        if not li_blocks:
            break

        # 提取 goKnowledge 调用参数
        pattern = r"goKnowledge\((\d+),(\d+),(?:&#39;|')(\d+)(?:&#39;|'),(?:&#39;|')(\d+)(?:&#39;|')\)"
        matches = re.findall(pattern, html)

        for i, (cid, kid, clid, uid) in enumerate(matches):
            info = {
                "courseId": cid,
                "knowledgeId": kid,
                "classId": clid,
                "userId": uid,
                "name": "未知",
                "has_video": False,
                "video_minutes": 0,
            }
            if i < len(li_blocks):
                block = li_blocks[i]
                name_els = block.xpath('.//p[contains(@class,"book-name")]/text()')
                if name_els:
                    info["name"] = _s(name_els[0])
                tag_els = block.xpath('.//p[contains(@class,"book-tag")]/text()')
                if tag_els:
                    tag_text = _s(tag_els[0])
                    video_match = re.search(r"视频(\d+)分钟", tag_text)
                    if video_match:
                        info["has_video"] = True
                        info["video_minutes"] = int(video_match.group(1))
            all_points.append(info)

        if len(matches) < page_size:
            break
        page += 1
        time.sleep(0.5)

    logger.info(f"获取知识点 course_id={course_id} total={len(all_points)}")
    return all_points


# ── 积分状态 ──────────────────────────────────────────────

def fetch_points(session: ChaoxingSession, course_id: str, class_id: str) -> dict:
    """查询课程积分状态

    返回: {total, video, login, discussion, notes, study_days, remaining, days_needed}
    """
    url = f"https://bigdata-score.chaoxing.com/tsjy/point/getCount?courseid={course_id}&classid={class_id}"
    try:
        data = session.get_json(url)
    except Exception as e:
        logger.warning(f"获取积分失败 course_id={course_id} error={str(e)}")
        return {}

    if not data.get("status"):
        return {}

    total_scores = {i["scoreType"]: i["score"] for i in data.get("itemTotalScore", [])}
    day_scores = {i["scoreType"]: i["score"] for i in data.get("itemDayScore", [])}
    study_days = data.get("studyDays", 0)

    total_sum = sum(total_scores.values())
    remaining = max(0, 200 - total_sum)
    days_needed = (remaining + 49) // 50 if remaining > 0 else 0

    return {
        "total": total_sum,
        "video": total_scores.get(3, 0),
        "login": total_scores.get(1, 0),
        "discussion": total_scores.get(2, 0),
        "notes": total_scores.get(4, 0),
        "day_scores": day_scores,
        "study_days": study_days,
        "remaining": remaining,
        "days_needed": days_needed,
    }


# ── 视频信息 ──────────────────────────────────────────────

def fetch_video_info(session: ChaoxingSession, domain: str, object_id: str) -> dict:
    """获取视频信息（含 dtoken）"""
    url = f"{domain}/ananas/status/{object_id}?k={session.fid}&flag=normal"
    try:
        resp = session.get(url, referer="https://mooc1.chaoxing.com/ananas/modules/video/index.html?v=2025-0725-1842")
        if resp.status_code == 200:
            data = resp.json()
            return {
                "duration": data.get("duration", 0),
                "dtoken": data.get("dtoken", ""),
                "filename": data.get("filename", ""),
                "status": data.get("status", ""),
            }
    except Exception:
        pass
    return {}


# ── enc 信息 ──────────────────────────────────────────────

def fetch_enc_info(session: ChaoxingSession, course_id: str, knowledge_id: str,
                   class_id: str) -> dict:
    """获取 enc 信息"""
    url = f"https://tsjy.chaoxing.com/plaza/user/{course_id}/{knowledge_id}/modify-node?classId={class_id}&userId={session.uid}"
    referer = f"https://tsjy.chaoxing.com/plaza/knowledge-all?courseId={course_id}"
    try:
        data = session.get_json(url, referer=referer)
        if data.get("code") == 1 and "data" in data:
            result = data["data"]
            return {"domain": result["domain"], "classId": result["classId"], "enc": result["enc"]}
    except Exception as e:
        logger.warning(f"获取enc失败 error={str(e)}")
    return {}


# ── mArg（视频任务列表）────────────────────────────────────

def fetch_marg(session: ChaoxingSession, domain: str, knowledge_id: str,
               course_id: str, class_id: str) -> dict:
    """获取 mArg（视频任务列表）"""
    url = f"{domain}/mooc-ans/knowledge/cards?clazzid={class_id}&courseid={course_id}&knowledgeid={knowledge_id}"
    try:
        resp = session.get(url)
        match = re.search(r"try{\s+mArg\s*=\s*({.*?});", resp.text(), re.DOTALL)
        if match:
            return json.loads(match.group(1))
    except Exception as e:
        logger.warning(f"获取mArg失败 error={str(e)}")
    return {}


# ── 必学知识点完成状态 ──────────────────────────────────────

def fetch_must_learn_kids(session: ChaoxingSession, course_id: str, class_id: str) -> list:
    """获取必学知识点ID列表 (classifyId=1)

    返回: [knowledgeId, ...]
    """
    url = f"https://tsjy.chaoxing.com/plaza/knowledge-list?courseId={course_id}"
    try:
        resp = session.post(url, data={
            "personId": session.uid,
            "classId": class_id,
            "userId": session.uid,
            "classifyId": "1",
            "element": "0",
            "point": "0",
            "name": "",
            "page": "1",
            "pageSize": "100",
        }, referer=f"https://tsjy.chaoxing.com/plaza/knowledge-all?courseId={course_id}")
        html = resp.text()
    except Exception as e:
        logger.warning(f"获取必学知识点失败 course_id={course_id} error={str(e)}")
        return []

    pattern = r"goKnowledge\((\d+),(\d+),(?:&#39;|')(\d+)(?:&#39;|'),(?:&#39;|')(\d+)(?:&#39;|')\)"
    matches = re.findall(pattern, html)
    seen = set()
    kids = []
    for cid, kid, clid, uid in matches:
        if kid not in seen:
            seen.add(kid)
            kids.append(kid)
    return kids


def fetch_knowledge_completion(session: ChaoxingSession, course_id: str, class_id: str,
                                cpi: str, kid: str) -> dict:
    """检查单个知识点的视频/测评/阅读完成状态

    通过获取 cards 页面的 mArg，检查 attachments 的 isPassed 字段。

    返回: {video_done, video_total, quiz_done, quiz_total, read_done, read_total, all_done}
    """
    result = {
        "video_done": 0, "video_total": 0,
        "quiz_done": 0, "quiz_total": 0,
        "read_done": 0, "read_total": 0,
        "all_done": False,
    }

    base_url = (f"https://mooc1-1.chaoxing.com/mooc-ans/knowledge/cards"
                f"?clazzid={class_id}&courseid={course_id}&knowledgeid={kid}"
                f"&ut=s&cpi={cpi}&mooc2=1")

    # num=0: 视频
    try:
        resp = session.get(base_url + "&num=0", referer="https://mooc1-1.chaoxing.com/")
        match = re.search(r"try{\s+mArg\s*=\s*({.*?});", resp.text(), re.DOTALL)
        if match:
            marg = json.loads(match.group(1))
            for att in marg.get("attachments", []):
                if att.get("type") == "video":
                    result["video_total"] += 1
                    if att.get("isPassed"):
                        result["video_done"] += 1
    except Exception as e:
        logger.debug(f"获取视频卡片失败 kid={kid} error={str(e)}")

    # num=1: 阅读
    try:
        resp = session.get(base_url + "&num=1", referer="https://mooc1-1.chaoxing.com/")
        html = resp.text()
        if "insertreadV2" in html:
            match = re.search(r"try{\s+mArg\s*=\s*({.*?});", html, re.DOTALL)
            if match:
                marg = json.loads(match.group(1))
                for att in marg.get("attachments", []):
                    if att.get("type") == "read":
                        result["read_total"] += 1
                        if att.get("isPassed"):
                            result["read_done"] += 1
    except Exception as e:
        logger.debug(f"获取阅读卡片失败 kid={kid} error={str(e)}")

    # num=2: 测评
    try:
        resp = session.get(base_url + "&num=2", referer="https://mooc1-1.chaoxing.com/")
        html = resp.text()
        if "workid" in html.lower() or "workId" in html:
            match = re.search(r"try{\s+mArg\s*=\s*({.*?});", html, re.DOTALL)
            if match:
                marg = json.loads(match.group(1))
                for att in marg.get("attachments", []):
                    prop = att.get("property", {})
                    if prop.get("workid") or att.get("type") == "work":
                        result["quiz_total"] += 1
                        if att.get("isPassed"):
                            result["quiz_done"] += 1
    except Exception as e:
        logger.debug(f"获取测评卡片失败 kid={kid} error={str(e)}")

    # 判断是否全部完成
    total = result["video_total"] + result["quiz_total"] + result["read_total"]
    done = result["video_done"] + result["quiz_done"] + result["read_done"]
    result["all_done"] = total > 0 and done >= total

    return result


def fetch_must_learn_completion(session: ChaoxingSession, course_id: str, class_id: str,
                                 cpi: str, must_learn_kids: list) -> dict:
    """批量检查必学知识点的完成状态

    返回: {kid: {video_done, video_total, quiz_done, quiz_total, read_done, read_total, all_done}}
    """
    result = {}
    for kid in must_learn_kids:
        result[kid] = fetch_knowledge_completion(session, course_id, class_id, cpi, kid)
        time.sleep(0.3)

    done_count = sum(1 for v in result.values() if v["all_done"])
    logger.info(f"必学完成状态 course={course_id} total={len(must_learn_kids)} done={done_count}")
    return result


def fetch_all_video_completion(session: ChaoxingSession, course_id: str, class_id: str,
                                cpi: str, knowledge_ids: list, concurrency: int = 5) -> dict:
    """批量检查所有知识点的视频完成状态（并发版）

    通过 cards API 的 mArg.attachments[].isPassed 判断每个视频是否完成。
    比积分推算精确得多。

    返回: {kid: bool}  True=视频已学完, False=未学完
    """
    import concurrent.futures

    def _check_one(kid):
        try:
            base_url = (f"https://mooc1-1.chaoxing.com/mooc-ans/knowledge/cards"
                        f"?clazzid={class_id}&courseid={course_id}&knowledgeid={kid}"
                        f"&ut=s&cpi={cpi}&mooc2=1&num=0")
            resp = session.get(base_url, referer="https://mooc1-1.chaoxing.com/")
            html = resp.text()
            match = re.search(r"try{\s+mArg\s*=\s*({.*?});", html, re.DOTALL)
            if not match:
                return kid, False
            marg = json.loads(match.group(1))
            for att in marg.get("attachments", []):
                if att.get("type") == "video":
                    return kid, bool(att.get("isPassed"))
            return kid, False  # 无视频附件
        except Exception as e:
            logger.debug(f"检查视频状态失败 kid={kid} error={str(e)}")
            return kid, False

    result = {}
    done_count = 0

    # 并发查询
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_check_one, kid): kid for kid in knowledge_ids}
        for future in concurrent.futures.as_completed(futures):
            kid, passed = future.result()
            result[kid] = passed
            if passed:
                done_count += 1

    logger.info(f"视频完成状态 course={course_id} total={len(knowledge_ids)} done={done_count}")
    return result

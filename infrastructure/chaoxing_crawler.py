"""
学习通课程爬取

获取课程列表、知识点、积分状态。
"""
import re
import json
import time
from loguru import logger

from infrastructure.chaoxing_session import ChaoxingSession


SCORE_TYPES = {1: '签到', 2: '讨论', 3: '视频', 4: '笔记'}


def get_course_list(session: ChaoxingSession) -> list:
    """获取所有课程列表

    返回: [{courseId, classId, name}, ...]
    """
    url = 'https://mooc1-1.chaoxing.com/mooc-ans/visit/courselistdata'
    data = {
        'courseType': '1',
        'courseFolderId': '0',
        'baseEducation': '0',
        'superstarClass': '',
        'courseFolderSize': '0',
    }
    try:
        resp = session.post(url, data=data, referer='https://mooc1.chaoxing.com/')
        html = resp.text()
    except Exception as e:
        logger.error(f"获取课程列表失败 error={str(e)}")
        return []

    courses = []
    pattern = r'<li[^>]*class="[^"]*course[^"]*"[^>]*courseId="(\d+)"[^>]*clazzId="(\d+)"[^>]*>'
    for cid, clid in re.findall(pattern, html):
        name_match = re.search(
            rf'id="course_{cid}_{clid}"[^>]*>.*?title="([^"]+)"',
            html, re.DOTALL
        )
        name = name_match.group(1).strip() if name_match else '未知课程'
        courses.append({'courseId': cid, 'classId': clid, 'name': name})

    # 去重
    seen = set()
    unique = []
    for c in courses:
        key = (c['courseId'], c['classId'])
        if key not in seen:
            seen.add(key)
            unique.append(c)

    logger.info(f"获取课程列表 count={len(unique)}")
    return unique


def get_knowledge_list(session: ChaoxingSession, course_id: str, class_id: str,
                       page_size: int = 100) -> list:
    """获取课程知识点列表（分页）

    返回: [{knowledgeId, classId, name, has_video, video_minutes}, ...]
    """
    all_points = []
    page = 1

    while True:
        url = f'https://tsjy.chaoxing.com/plaza/knowledge-list?courseId={course_id}'
        try:
            resp = session.post(url, data={
                'personId': session.uid,
                'classId': class_id,
                'userId': session.uid,
                'classifyId': '',
                'element': '0',
                'point': '0',
                'name': '',
                'page': str(page),
                'pageSize': str(page_size),
            }, referer=f'https://tsjy.chaoxing.com/plaza/knowledge-all?courseId={course_id}')
            html = resp.text()
        except Exception as e:
            logger.warning(f"获取知识点失败 course_id={course_id} error={str(e)}")
            break

        pattern = r"goKnowledge\((\d+),(\d+),(?:&#39;|')(\d+)(?:&#39;|'),(?:&#39;|')(\d+)(?:&#39;|')\)"
        matches = re.findall(pattern, html)
        if not matches:
            break

        li_blocks = re.findall(r'<li class="list">(.*?)</li>', html, re.DOTALL)

        for i, (cid, kid, clid, uid) in enumerate(matches):
            info = {
                'courseId': cid,
                'knowledgeId': kid,
                'classId': clid,
                'userId': uid,
                'name': '未知',
                'has_video': False,
                'video_minutes': 0,
            }
            if i < len(li_blocks):
                block = li_blocks[i]
                name_match = re.search(r'class="book-name[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL)
                if name_match:
                    info['name'] = name_match.group(1).strip()
                tag_match = re.search(r'class="book-tag[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL)
                if tag_match:
                    video_match = re.search(r'视频(\d+)分钟', tag_match.group(1))
                    if video_match:
                        info['has_video'] = True
                        info['video_minutes'] = int(video_match.group(1))
            all_points.append(info)

        if len(matches) < page_size:
            break
        page += 1
        time.sleep(0.5)

    logger.info(f"获取知识点 course_id={course_id} total={len(all_points)}")
    return all_points


def get_points(session: ChaoxingSession, course_id: str, class_id: str) -> dict:
    """查询课程积分状态

    返回: {total, video, login, discussion, notes, study_days, remaining, days_needed}
    """
    url = f'https://bigdata-score.chaoxing.com/tsjy/point/getCount?courseid={course_id}&classid={class_id}'
    try:
        data = session.get_json(url)
    except Exception as e:
        logger.warning(f"获取积分失败 course_id={course_id} error={str(e)}")
        return {}

    if not data.get('status'):
        return {}

    total_scores = {i['scoreType']: i['score'] for i in data.get('itemTotalScore', [])}
    day_scores = {i['scoreType']: i['score'] for i in data.get('itemDayScore', [])}
    study_days = data.get('studyDays', 0)

    total_sum = sum(total_scores.values())
    remaining = max(0, 200 - total_sum)
    days_needed = (remaining + 49) // 50 if remaining > 0 else 0

    return {
        'total': total_sum,
        'video': total_scores.get(3, 0),
        'login': total_scores.get(1, 0),
        'discussion': total_scores.get(2, 0),
        'notes': total_scores.get(4, 0),
        'day_scores': day_scores,
        'study_days': study_days,
        'remaining': remaining,
        'days_needed': days_needed,
    }


def get_video_info(session: ChaoxingSession, domain: str, object_id: str) -> dict:
    """获取视频信息（含dtoken）"""
    url = f'{domain}/ananas/status/{object_id}?k={session.fid}&flag=normal'
    try:
        resp = session.get(url, referer='https://mooc1.chaoxing.com/ananas/modules/video/index.html?v=2025-0725-1842')
        if resp.status_code == 200:
            data = resp.json()
            return {
                'duration': data.get('duration', 0),
                'dtoken': data.get('dtoken', ''),
                'filename': data.get('filename', ''),
                'status': data.get('status', ''),
            }
    except Exception:
        pass
    return {}


def get_enc_info(session: ChaoxingSession, course_id: str, knowledge_id: str,
                 class_id: str) -> dict:
    """获取enc信息"""
    url = f'https://tsjy.chaoxing.com/plaza/user/{course_id}/{knowledge_id}/modify-node?classId={class_id}&userId={session.uid}'
    referer = f'https://tsjy.chaoxing.com/plaza/knowledge-all?courseId={course_id}'
    try:
        data = session.get_json(url, referer=referer)
        if data.get('code') == 1 and 'data' in data:
            result = data['data']
            return {'domain': result['domain'], 'classId': result['classId'], 'enc': result['enc']}
    except Exception as e:
        logger.warning(f"获取enc失败 error={str(e)}")
    return {}


def get_marg(session: ChaoxingSession, domain: str, knowledge_id: str,
             course_id: str, class_id: str, enc: str) -> dict:
    """获取mArg（视频任务列表）"""
    url = f'{domain}/mooc-ans/knowledge/cards?clazzid={class_id}&courseid={course_id}&knowledgeid={knowledge_id}'
    try:
        resp = session.get(url)
        match = re.search(r'try{\s+mArg\s*=\s*({.*?});', resp.text(), re.DOTALL)
        if match:
            return json.loads(match.group(1))
    except Exception as e:
        logger.warning(f"获取mArg失败 error={str(e)}")
    return {}


def scan_chaoxing_courses(session: ChaoxingSession) -> dict:
    """扫描学习通所有课程，返回标准化格式

    返回: {website_id, name, status, student_name, courses, tasks}
    """
    from infrastructure.chaoxing_points import ScoreRuleParser

    user_info = session.get_user_info()
    courses_raw = get_course_list(session)

    if not courses_raw:
        return {
            'website_id': 4,
            'name': '学习通',
            'status': 'error',
            'error': '获取课程列表失败',
            'courses': [],
            'tasks': [],
        }

    courses = []
    all_tasks = []

    for c in courses_raw:
        cid = c['courseId']
        clid = c['classId']
        name = c['name']

        # 查积分
        points = get_points(session, cid, clid)

        # 查积分规则
        try:
            rule = ScoreRuleParser.fetch_rules(session, cid, clid)
        except Exception:
            from infrastructure.chaoxing_points import PointsRule
            rule = PointsRule()

        # 查知识点
        knowledge_points = get_knowledge_list(session, cid, clid)
        video_points = [kp for kp in knowledge_points if kp['has_video']]
        total_minutes = sum(kp['video_minutes'] for kp in video_points)

        course_entry = {
            'course_id': cid,
            'class_id': clid,
            'course_name': name,
            'video_total': len(video_points),
            'video_completed': 0,
            'video_pending': len(video_points),
            'video_actionable': len(video_points),
            'exam_total': 0,
            'exam_done': 0,
            'exam_deleted': 0,
            'exam_pending': 0,
            'exam_actionable': 0,
            'records_loaded': True,
            # 学习通特有字段
            'points_total': points.get('total', 0),
            'points_video': points.get('video', 0),
            'points_remaining': points.get('remaining', 200),
            'days_needed': points.get('days_needed', 4),
            'study_days': points.get('study_days', 0),
            'total_minutes': total_minutes,
            # 积分规则
            'points_target': rule.target,
            'daily_limit': rule.daily_limit,
            'video_min': rule.video_min,
        }

        # 生成任务
        if points.get('remaining', 0) > 0:
            task = {
                'task_type': 'chaoxing_points',
                'course_id': cid,
                'class_id': clid,
                'course_name': name,
                'website_id': 4,
                'platform_name': '学习通',
                'points_remaining': points.get('remaining', 200),
                'days_needed': points.get('days_needed', 4),
                'video_count': len(video_points),
                'total_minutes': total_minutes,
            }
            all_tasks.append(task)

        courses.append(course_entry)

    return {
        'website_id': 4,
        'name': '学习通',
        'status': 'ok',
        'student_name': user_info.get('name', ''),
        'courses': courses,
        'tasks': all_tasks,
    }

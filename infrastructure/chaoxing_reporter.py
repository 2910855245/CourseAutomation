"""
学习通视频进度上报

enc签名 + dtoken获取 + 进度上报循环。
基于 rnet 模拟浏览器 TLS 指纹（随机轮换）。
"""
import re
import json
import time
import random
import hashlib
from loguru import logger

from infrastructure.chaoxing_session import ChaoxingSession


ENC_SECRET = 'd_yHJ!$pdA~5'
VIDEO_REFERER = 'https://mooc1.chaoxing.com/ananas/modules/video/index.html?v=2025-0725-1842'

# 上报间隔配置（秒），模拟真实播放速度
SPEED_PROFILES = {
    'fast':   {60: (5, 10), 300: (10, 20), 600: (15, 30), 99999: (20, 40)},
    'normal': {60: (8, 15), 300: (15, 30), 600: (25, 50), 99999: (30, 60)},
    'slow':   {60: (10, 20), 300: (20, 40), 600: (30, 60), 99999: (40, 80)},
}


def calc_enc(clazz_id: str, userid: str, jobid: str, object_id: str,
             play_time: int, duration: int) -> str:
    """计算 enc 签名（MD5）"""
    raw = (f'[{clazz_id}][{userid}][{jobid}][{object_id}]'
           f'[{play_time * 1000}][{ENC_SECRET}][{duration * 1000}]'
           f'[0_{duration}]')
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def get_video_info(session: ChaoxingSession, domain: str, object_id: str) -> dict:
    """获取视频信息（含dtoken）"""
    import time
    ts = int(time.time() * 1000)
    # 使用固定域名 mooc1-1（domain参数可能不正确）
    url = f'https://mooc1-1.chaoxing.com/ananas/status/{object_id}?k={session.fid}&flag=normal&ro=0&_dc={ts}'
    try:
        resp = session.get(url, referer=VIDEO_REFERER)
        if resp.status_code == 200:
            data = resp.json()
            result = {
                'duration': data.get('duration', 0),
                'dtoken': data.get('dtoken', ''),
                'filename': data.get('filename', ''),
                'status': data.get('status', ''),
            }
            logger.debug(f"get_video_info ok object_id={object_id} dtoken={result['dtoken']} duration={result['duration']}")
            return result
        else:
            logger.warning(f"get_video_info status={resp.status_code} object_id={object_id} url={url}")
    except Exception as e:
        logger.warning(f"get_video_info error object_id={object_id} error={str(e)}")
    return {}


def get_enc_info(session: ChaoxingSession, course_id: str, knowledge_id: str,
                 class_id: str) -> dict:
    """获取enc信息（domain + classId + enc）"""
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
             course_id: str, class_id: str) -> dict:
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


def report_progress(session: ChaoxingSession, cpi: str, dtoken: str,
                    clazz_id: str, jobid: str, object_id: str,
                    duration: int, play_time: int, other_info: str,
                    course_id: str, is_drag: int = 0,
                    face_enc: str = '', dur_enc: str = '',
                    report_url: str = '') -> dict:
    """上报视频播放进度

    返回: 响应JSON 或 None
    """
    rt_match = re.search(r'-rt_([1d])', other_info)
    rt = '0.9' if rt_match and rt_match.group(1) == 'd' else '1'

    enc = calc_enc(clazz_id, session.uid, jobid, object_id, play_time, duration)

    params = {
        'clazzId': str(clazz_id),
        'playingTime': str(play_time),
        'duration': str(duration),
        'clipTime': f'0_{duration}',
        'objectId': object_id,
        'otherInfo': other_info,
        'courseId': str(course_id),
        'jobid': jobid,
        'userid': session.uid,
        'isdrag': str(is_drag),
        'view': 'pc',
        'enc': enc,
        'dtype': 'Video',
        'rt': '0.9',
        '_t': str(int(time.time() * 1000)),
        'attDuration': str(duration),
        'courseEngineInfo': 'false',
    }
    if face_enc:
        params['videoFaceCaptureEnc'] = face_enc
    if dur_enc:
        params['attDurationEnc'] = dur_enc

    # 优先用平台返回的reportUrl + dtoken
    if report_url:
        url = f'{report_url}/{dtoken}' if dtoken else report_url
    else:
        url = f'https://mooc1-1.chaoxing.com/mooc-ans/multimedia/log/a/{cpi}'
        if dtoken:
            url += '/' + dtoken

    # 学习通 CDN 对 rnet 的进度上报请求返回 403（HTTP/2 帧差异等）
    # 使用 urllib 发送进度上报请求（系统 TLS 栈，稳定可用）
    import urllib.request
    import urllib.parse

    full_url = f'{url}?{urllib.parse.urlencode(params)}'

    for attempt in range(3):
        try:
            req = urllib.request.Request(full_url, method='GET')
            req.add_header('Cookie', session.cookie_str)
            req.add_header('Referer', VIDEO_REFERER)
            req.add_header('User-Agent', session.UA)

            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode('utf-8'))
                elif resp.status == 403:
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        logger.warning(f"进度上报403，重试失败 url={url}")
                        return None
                else:
                    logger.warning(f"进度上报异常状态码 status={resp.status} url={url}")
                    return None
        except urllib.error.HTTPError as e:
            if e.code == 403:
                if attempt < 2:
                    logger.warning(f"进度上报403，重试 attempt={attempt + 1}")
                    time.sleep(2)
                else:
                    logger.warning(f"进度上报403，重试失败 url={url}")
                    return None
            else:
                logger.warning(f"进度上报HTTP错误 status={e.code} url={url}")
                return None
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
            else:
                logger.warning(f"进度上报异常 error={str(e)}")
                return None
    return None


def calc_interval(duration: int, speed: str = 'normal') -> float:
    """根据视频时长和速度模式计算上报间隔"""
    profile = SPEED_PROFILES.get(speed, SPEED_PROFILES['normal'])
    for threshold, (lo, hi) in sorted(profile.items()):
        if duration <= threshold:
            return random.uniform(lo, hi)
    return random.uniform(30, 60)


def play_video(session: ChaoxingSession, cpi: str, dtoken: str,
               class_id: str, jobid: str, object_id: str,
               duration: int, other_info: str, course_id: str,
               video_name: str = '视频', speed: str = 'normal',
               face_enc: str = '', dur_enc: str = '',
               dry_run: bool = False,
               on_progress=None, report_url: str = '') -> bool:
    """播放单个视频（循环上报进度直到完成）

    参数:
        session: ChaoxingSession 实例
        cpi: 课程参数ID
        dtoken: 视频token
        class_id: 班级ID
        jobid: 任务ID
        object_id: 视频对象ID
        duration: 视频总时长（秒）
        other_info: 附加信息
        course_id: 课程ID
        video_name: 视频名称（日志用）
        speed: 速度模式 (fast/normal/slow)
        face_enc: 人脸识别加密
        dur_enc: 时长加密
        dry_run: 仅预览
        on_progress: 进度回调 (percent: int) -> None

    返回: 是否播放完成
    """
    interval = calc_interval(duration, speed)
    logger.info("开始播放 video={} duration={} interval={:.0f}s", video_name, duration, interval)

    if dry_run:
        logger.info(f"[DRY-RUN] 跳过实际播放 video={video_name}")
        return True

    # 首次上报 playingTime=0 (初始化会话，浏览器行为)
    result = report_progress(
        session, cpi, dtoken, class_id, jobid, object_id,
        duration, 0, other_info, course_id,
        is_drag=3, face_enc=face_enc, dur_enc=dur_enc,
        report_url=report_url
    )
    if not result:
        logger.warning("首次上报失败 video={}", video_name)
        return False

    played = 0
    fail_streak = 0

    while played < duration:
        interval = calc_interval(duration, speed)
        next_time = min(
            played + random.randint(max(1, int(interval * 0.7)), int(interval * 1.3)),
            duration - 1
        )
        is_drag = 4 if next_time >= duration - 2 else 0

        result = report_progress(
            session, cpi, dtoken, class_id, jobid, object_id,
            duration, next_time, other_info, course_id,
            is_drag=is_drag, face_enc=face_enc, dur_enc=dur_enc,
            report_url=report_url
        )

        if result:
            fail_streak = 0
            pct = next_time * 100 // duration
            logger.info(f"播放进度 video={video_name} percent={{f'{pct}%'}} time={{f'{next_time}/{duration}s'}}")
            if on_progress:
                on_progress(pct)
            if result.get('isPassed'):
                logger.info(f"播放完成 video={video_name}")
                return True
        else:
            fail_streak += 1
            if fail_streak >= 3:
                logger.warning(f"连续3次上报失败，放弃 video={video_name}")
                return False

        played = next_time
        if is_drag == 4:
            break

        wait = random.uniform(interval * 0.5, interval * 0.8)
        time.sleep(wait)

    logger.info(f"播放完成 video={video_name}")
    return True


def process_knowledge_videos(session: ChaoxingSession, course_id: str,
                             knowledge_id: str, class_id: str,
                             knowledge_name: str = '未知',
                             speed: str = 'normal',
                             dry_run: bool = False,
                             on_progress=None) -> dict:
    """处理单个知识点的所有视频

    返回: {success: bool, total: int, passed: int, played: int, failed: int}
    """
    logger.info(f"处理知识点 name={knowledge_name}")

    enc_info = get_enc_info(session, course_id, knowledge_id, class_id)
    if not enc_info:
        return {'success': False, 'total': 0, 'passed': 0, 'played': 0, 'failed': 0}

    marg = get_marg(session, enc_info['domain'], knowledge_id, course_id, enc_info['classId'])
    if not marg:
        return {'success': False, 'total': 0, 'passed': 0, 'played': 0, 'failed': 0}

    attachments = marg.get('attachments', [])
    defaults = marg.get('defaults', {})
    cpi = defaults.get('cpi', '')
    report_url = defaults.get('reportUrl', '')
    ktoken = defaults.get('ktoken', '')

    logger.debug(f"enc_info domain={enc_info.get('domain')} classId={enc_info.get('classId')}")
    logger.debug(f"mArg cpi={cpi} reportUrl={report_url} ktoken={ktoken} attachments={len(attachments)}")

    video_tasks = [a for a in attachments if a.get('type') == 'video']
    if not video_tasks:
        logger.info(f"无视频任务 knowledge={knowledge_name}")
        return {'success': False, 'total': 0, 'passed': 0, 'played': 0, 'failed': 0}

    unpassed = [t for t in video_tasks if not t.get('isPassed')]
    passed_count = len(video_tasks) - len(unpassed)

    if not unpassed:
        logger.info(f"所有视频已完成 knowledge={knowledge_name} total={len(video_tasks)}")
        return {'success': True, 'total': len(video_tasks), 'passed': passed_count, 'played': 0, 'failed': 0}

    logger.info(f"视频任务 total={len(video_tasks)} passed={passed_count} pending={len(unpassed)}")

    if dry_run:
        for i, task in enumerate(video_tasks):
            prop = task.get('property', {})
            name = prop.get('name', f'视频{i+1}')
            dur = task.get('attDuration', 0)
            status = '已完成' if task.get('isPassed') else f'待播放 ({dur}s)'
            logger.info(f"预览 index={{i + 1}} name={name} status={status}")
        return {'success': True, 'total': len(video_tasks), 'passed': passed_count, 'played': 0, 'failed': 0}

    played_count = 0
    failed_count = 0

    for i, task in enumerate(video_tasks):
        if task.get('isPassed'):
            continue

        jobid = task.get('jobid', '')
        prop = task.get('property', {})
        object_id = task.get('objectId', '') or prop.get('objectid', '')
        other_info = task.get('otherInfo', '').split('&')[0]

        if not object_id:
            continue

        duration = task.get('attDuration', 0)
        video_name = prop.get('name', f'视频{i+1}')

        # 获取时长和dtoken
        if duration <= 0:
            vinfo = get_video_info(session, enc_info['domain'], object_id)
            if vinfo:
                duration = vinfo.get('duration', 0)
        if duration <= 0:
            logger.warning(f"跳过视频（无法获取时长） video={video_name}")
            failed_count += 1
            continue

        vinfo = get_video_info(session, enc_info['domain'], object_id)
        dtoken = vinfo.get('dtoken', '') if vinfo else ''
        # 如果dtoken为空，尝试用marg里的ktoken
        if not dtoken:
            dtoken = defaults.get('ktoken', '')
        logger.debug(f"video={video_name} object_id={object_id} dtoken={dtoken} vinfo={vinfo}")

        face_enc = task.get('videoFaceCaptureEnc', '')
        dur_enc = task.get('attDurationEnc', '')

        ok = play_video(
            session, cpi, dtoken, enc_info['classId'], jobid, object_id,
            duration, other_info, course_id, video_name, speed,
            face_enc=face_enc, dur_enc=dur_enc, dry_run=dry_run,
            on_progress=on_progress,
            report_url=defaults.get('reportUrl', '')
        )

        if ok:
            played_count += 1
        else:
            failed_count += 1

        time.sleep(1)

    total = len(video_tasks)
    all_done = (played_count + passed_count) >= total
    logger.info(f"知识点完成 knowledge={knowledge_name} total={total} passed={passed_count} played={played_count} failed={failed_count}")

    return {
        'success': all_done or played_count > 0,
        'total': total,
        'passed': passed_count,
        'played': played_count,
        'failed': failed_count,
    }

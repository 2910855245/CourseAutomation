"""
学习通积分+答题Worker

专用Worker：加载cookie → 检查积分 → 每天刷视频+答题+讨论+笔记 → 循环直到达标。
积分达标后自动做作业/考试（DeepSeek AI 答题）。
通过 status.json 与主进程通信。

用法: python chaoxing_worker.py <params_file> <status_file>
"""
import json
import os
import sys
import time
import signal
import traceback
from datetime import datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from loguru import logger


_shutdown_requested = False


def _solve_tsjy_knowledge_quiz(session, cid, kid, clid, cpi, kname, api_key,
                                status_file, cname, total, done, failed):
    """解答tsjy知识点测评（quiz）"""
    import re
    import json as _json
    from infrastructure.chaoxing_quiz import solve_quiz, load_ref_hashes, AnswerCache

    # 获取知识点卡片页面（num=2 = 测评/作业）
    cards_url = (f'https://mooc1-1.chaoxing.com/mooc-ans/knowledge/cards'
                 f'?clazzid={clid}&courseid={cid}&knowledgeid={kid}'
                 f'&num=2&ut=s&cpi={cpi}&mooc2=1')
    try:
        resp = session.get(cards_url, referer='https://mooc1-1.chaoxing.com/')
        html = resp.text()
    except Exception as e:
        logger.warning(f"获取测评卡片失败 kid={kid} error={str(e)}")
        return

    # 提取 iframe data 属性中的 workid
    data_match = re.search(r'data="([^"]*workid[^"]*)"', html)
    if not data_match:
        logger.info(f"知识点无测评 kid={kid} name={kname}")
        return

    try:
        data_str = data_match.group(1).replace('&quot;', '"').replace('&amp;', '&')
        data = _json.loads(data_str)
    except Exception:
        logger.warning(f"解析测评data失败 kid={kid}")
        return

    workid = data.get('workid', '')
    jobid = data.get('jobid', data.get('_jobid', ''))
    enc = ''
    ktoken = ''

    # 从 mArg 提取 enc 和 ktoken
    marg_match = re.search(r'mArg\s*=\s*(\{.*?\});', html, re.DOTALL)
    if marg_match:
        try:
            marg = _json.loads(marg_match.group(1))
            for att in marg.get('attachments', []):
                if att.get('property', {}).get('workid') == workid:
                    enc = att.get('enc', '')
                    break
            defaults = marg.get('defaults', {})
            ktoken = defaults.get('ktoken', '')
        except Exception:
            pass

    if not workid:
        logger.info(f"知识点无workid kid={kid}")
        return

    # 构造 workHandle URL
    work_url = (f'https://mooc1-1.chaoxing.com/mooc-ans/workHandle/handle'
                f'?workId={workid}&courseid={cid}&knowledgeid={kid}'
                f'&userid=&ut=s&classId={clid}&jobid={jobid}'
                f'&type=&isphone=false&submit=false&enc={enc}'
                f'&utenc=&cpi={cpi}&ktoken={ktoken}'
                f'&mooc2=1&skipHeader=true&workExtInfoEnc=null'
                f'&oriNodeId=0&originJobId={jobid}'
                f'&teacherPreview=0&fromType=')

    send_status(status_file,
                phase="study_must_learn",
                course_name=cname,
                study_total=total,
                study_done=done,
                study_failed=failed,
                message=f"[{cname}] 测评: {kname[:30]}")

    logger.info(f"开始答题 name={kname} workId={workid}")

    try:
        ref_hashes = load_ref_hashes()
    except Exception:
        ref_hashes = {}

    cache = AnswerCache(enabled=False)

    result = solve_quiz(
        session, work_url, api_key,
        ref_hashes=ref_hashes,
        cache=cache,
        dry_run=False,
    )

    if result.get('success'):
        logger.info(f"测评完成 name={kname} questions={result.get('total', 0)} submitted={result.get('submitted', False)}")
    else:
        logger.warning(f"测评失败 name={kname} error={result.get('error', 'unknown')}")


def _do_tsjy_knowledge_read(session, cid, kid, clid, cpi, kname,
                             status_file, cname, total, done, failed):
    """处理tsjy知识点阅读（insertreadV2）任务

    阅读任务通过 /multimedia/readlog API 上报阅读时长，
    服务端每天更新一次，累计达到要求时长后自动完成。
    """
    import re
    import json as _json
    import urllib.request
    import urllib.parse

    # 获取知识点卡片页面（num=1 = 阅读）
    cards_url = (f'https://mooc1-1.chaoxing.com/mooc-ans/knowledge/cards'
                 f'?clazzid={clid}&courseid={cid}&knowledgeid={kid}'
                 f'&num=1&ut=s&cpi={cpi}&mooc2=1')
    try:
        resp = session.get(cards_url, referer='https://mooc1-1.chaoxing.com/')
        html = resp.text()
    except Exception as e:
        logger.warning(f"获取阅读卡片失败 kid={kid} error={str(e)}")
        return False

    if 'insertreadV2' not in html:
        logger.info(f"知识点无阅读任务 kid={kid} name={kname}")
        return False

    # 从 mArg 提取阅读附件
    read_items = []
    marg_match = re.search(r'mArg\s*=\s*(\{.*?\});', html, re.DOTALL)
    if marg_match:
        try:
            marg = _json.loads(marg_match.group(1))
            for att in marg.get('attachments', []):
                if att.get('type') == 'read':
                    read_items.append(att)
        except Exception:
            pass

    if not read_items:
        logger.info(f"知识点无阅读附件 kid={kid} name={kname}")
        return False

    # 检查是否全部已完成
    all_passed = all(att.get('isPassed') for att in read_items)
    if all_passed:
        logger.info(f"阅读已完成 kid={kid} name={kname}")
        return True

    send_status(status_file,
                phase="study_must_learn",
                course_name=cname,
                study_total=total,
                study_done=done,
                study_failed=failed,
                message=f"[{cname}] 阅读: {kname[:30]} ({len(read_items)}篇)")

    logger.info(f"开始处理阅读 name={kname} items={len(read_items)}")

    # 获取 topic course 文章列表
    # 通过第一个阅读项的 api/work 重定向获取 topic course 信息
    first_item = read_items[0]
    first_jobid = first_item.get('jobid', '')
    first_enc = first_item.get('enc', '')

    read_url = (f'https://mooc1-1.chaoxing.com/mooc-ans/api/work?api=1&workId='
                f'&jobid={first_jobid}&needRedirect=true&type=read'
                f'&knowledgeid={kid}&ut=s&isphone=false&clazzId={clid}'
                f'&enc={first_enc}&courseid={cid}&cpi={cpi}')

    topic_course_ids = []
    try:
        r1 = session.get(read_url, allow_redirects=False, referer='https://mooc1-1.chaoxing.com/')
        loc = ''
        try:
            loc = r1.headers['location']
            if isinstance(loc, bytes):
                loc = loc.decode()
        except KeyError:
            pass

        if loc.startswith('/'):
            loc = 'https://mooc1-1.chaoxing.com' + loc

        if loc.startswith('http'):
            r2 = session.get(loc, referer=read_url)
            text2 = r2.text()
            # 提取 topic course ID 列表
            course_links = re.findall(r'/mooc-ans/course/(\d+)\.html', text2)
            topic_course_ids = list(dict.fromkeys(course_links))  # 去重保序

            # 提取阅读时长要求
            req_match = re.search(r'阅读总时长达到<span>(\d+)</span>分钟', text2)
            time_match = re.search(r'您的阅读总时长：<span>([\d.]+)</span>分钟', text2)
            required_min = int(req_match.group(1)) if req_match else 60
            current_min = float(time_match.group(1)) if time_match else 0

            logger.info(f"阅读任务 name={kname} 当前={current_min}分钟 要求={required_min}分钟 文章数={len(topic_course_ids)}")
    except Exception as e:
        logger.warning(f"获取阅读任务信息失败 kid={kid} error={str(e)}")

    if not topic_course_ids:
        logger.warning(f"未获取到文章列表 kid={kid}")
        return False

    # 上报阅读时长 - 每篇文章调用 readlog API
    # 每次调用约注册 1 分钟阅读时长
    readlog_count = min(len(topic_course_ids), required_min + 10)  # 多发一些以确保足够
    success_count = 0

    for i, course_id in enumerate(topic_course_ids[:readlog_count]):
        if _shutdown_requested:
            break

        params = {
            'courseid': course_id,
            'chapterid': '0',
            'height': str(1000 + (i % 10) * 100),
            '_t': str(int(time.time() * 1000)),
        }
        url = f'https://mooc1-1.chaoxing.com/mooc-ans/multimedia/readlog?{urllib.parse.urlencode(params)}'
        try:
            req = urllib.request.Request(url, method='GET')
            req.add_header('Cookie', session.cookie_str)
            req.add_header('Referer', f'https://mooc1-1.chaoxing.com/mooc-ans/course/{course_id}.html')
            req.add_header('User-Agent', session.UA)
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode('utf-8')
                if body.strip() in ('{}', ''):
                    success_count += 1
        except Exception as e:
            logger.debug(f"readlog失败 course={course_id} error={str(e)}")

        if (i + 1) % 20 == 0:
            send_status(status_file,
                        phase="study_must_learn",
                        course_name=cname,
                        study_total=total,
                        study_done=done,
                        study_failed=failed,
                        message=f"[{cname}] 阅读上报 {i+1}/{readlog_count}: {kname[:20]}")
            time.sleep(1)

    logger.info(f"阅读上报完成 name={kname} sent={success_count}/{readlog_count}")
    logger.info(f"注意: 阅读时长由服务端每日更新，次日生效")
    return success_count > 0


def _study_must_learn(session, cid, clid, cname, status_file, api_key=''):
    """刷"必学"知识点视频+测评，返回 (done, failed, skipped) 计数"""
    import re
    from infrastructure.chaoxing_reporter import process_knowledge_videos

    done, failed, skipped = 0, 0, 0

    # 获取 personId (cpi) — 与 session.uid 不同
    person_id = ''
    try:
        resp = session.get('https://mooc1-api.chaoxing.com/mycourse/backclazzdata?view=json&rss=1')
        for ch in resp.json().get('channelList', []):
            content = ch.get('content', {})
            if isinstance(content, dict):
                for c in content.get('course', {}).get('data', []):
                    if str(c.get('id', '')) == cid:
                        person_id = str(ch.get('cpi', ''))
                        break
    except Exception:
        pass

    if not person_id:
        logger.warning(f"未找到personId course={cname} cid={cid}")
        return 0, 0, 0

    try:
        # 获取必学知识点列表 (classifyId=1)
        url = 'https://tsjy.chaoxing.com/plaza/knowledge-list?courseId=' + cid
        data = {
            'personId': person_id,
            'classId': clid,
            'userId': session.uid,
            'classifyId': '1',
            'element': '0',
            'point': '0',
            'name': '',
            'page': '1',
            'pageSize': '50',
        }
        resp = session.post(url, data=data, referer='https://tsjy.chaoxing.com/plaza/')
        html = resp.text()

        # 解析 goKnowledge(courseId, knowledgeId, classId, userId)
        pattern = r'goKnowledge\((\d+),(\d+),(?:&#39;|\'|")(\d+)(?:&#39;|\'|"),(?:&#39;|\'|")(\d+)(?:&#39;|\'|")\)'
        matches = re.findall(pattern, html)
        # 去重（每个li有两个a标签，knowledgeId相同）
        seen = set()
        kid_list = []
        for cid_g, kid, clid_g, uid_g in matches:
            if kid not in seen:
                seen.add(kid)
                kid_list.append(kid)

        # 解析标题
        titles = re.findall(r'<p class="book-name font16 color333 overhidden2">(.*?)</p>', html)

        if not kid_list:
            logger.info(f"无必学知识点 course={cname}")
            return 0, 0, 0

        logger.info(f"必学知识点 course={cname} count={len(kid_list)}")

        for i, kid in enumerate(kid_list):
            if _shutdown_requested:
                break

            kname = titles[i] if i < len(titles) else f'知识点{kid}'

            send_status(status_file,
                        phase="study_must_learn",
                        course_name=cname,
                        study_total=len(kid_list),
                        study_done=done,
                        study_failed=failed,
                        message=f"[{cname}] 必学 {i+1}/{len(kid_list)}: {kname[:30]}")

            logger.info(f"开始刷知识点 name={kname} knowledgeId={kid}")

            try:
                result = process_knowledge_videos(
                    session, cid, kid, clid,
                    knowledge_name=kname,
                    speed='normal',
                    dry_run=False,
                    on_progress=lambda pct: send_status(
                        status_file,
                        phase="study_must_learn",
                        course_name=cname,
                        study_total=len(kid_list),
                        study_done=done,
                        study_failed=failed,
                        message=f"[{cname}] {kname[:20]} {pct}%")
                )
                if result.get('success') and result.get('played', 0) > 0:
                    done += 1
                    logger.info(f"知识点完成 name={kname} played={result['played']}")
                elif result.get('total', 0) > 0 and result.get('passed', 0) >= result['total']:
                    skipped += 1
                    logger.info(f"知识点已全部完成 name={kname}")
                elif result.get('played', 0) == 0 and result.get('total', 0) > 0:
                    skipped += 1
                    logger.info(f"知识点无需播放 name={kname}")
                else:
                    failed += 1
                    logger.warning(f"知识点部分失败 name={kname} result={result}")
            except Exception as e:
                failed += 1
                logger.error(f"知识点异常 name={kname} error={str(e)}")

            # 刷知识点测评（quiz）
            if api_key:
                try:
                    _solve_tsjy_knowledge_quiz(
                        session, cid, kid, clid, person_id, kname, api_key, status_file,
                        cname, len(kid_list), done, failed)
                except Exception as e:
                    logger.warning(f"知识点测评异常 name={kname} error={str(e)}")

            # 处理知识点阅读（insertreadV2）
            try:
                _do_tsjy_knowledge_read(
                    session, cid, kid, clid, person_id, kname, status_file,
                    cname, len(kid_list), done, failed)
            except Exception as e:
                logger.warning(f"知识点阅读异常 name={kname} error={str(e)}")

    except Exception as e:
        logger.warning(f"获取必学列表失败 course={cname} error={str(e)}")

    return done, failed, skipped


def _solve_course_quizzes(session, cid, clid, cname, status_file, api_key):
    """为单个课程做作业/考试，返回 (done, failed, skipped) 计数"""
    from infrastructure.chaoxing_quiz import get_work_list, solve_quiz, load_ref_hashes, AnswerCache

    done, failed, skipped = 0, 0, 0

    try:
        works = get_work_list(session, cid, clid)
    except Exception as e:
        logger.warning(f"获取作业列表失败 course={cname} error={str(e)}")
        return 0, 0, 0

    if not works:
        logger.info(f"无作业/考试 course={cname}")
        return 0, 0, 0

    logger.info(f"作业/考试列表 course={cname} count={len(works)}")
    for w in works:
        logger.info(f"  [{w.get('type','?')}] {w.get('title','')} status={w.get('status','')} workId={w.get('workId','')}")

    # 加载字体参考哈希（可能为空，不影响流程）
    try:
        ref_hashes = load_ref_hashes()
    except Exception:
        ref_hashes = {}
        logger.warning("字体哈希表未加载，字体解码可能失败")

    cache = AnswerCache(enabled=False)

    for i, work in enumerate(works):
        if _shutdown_requested:
            break

        wid = work.get('workId', '')
        title = work.get('title', f'作业{wid}')
        work_status = work.get('status', '')
        item_type = work.get('type', 'work')

        # 跳过已完成的
        if '已完成' in work_status or '已批阅' in work_status:
            skipped += 1
            continue

        # 跳过"未开始"的考试
        if 'Not started' in work_status or '未开始' in work_status:
            skipped += 1
            logger.info(f"跳过未开始的考试 title={title} endTime={work.get('endTime', '')}")
            continue

        # 考试类型：使用 exam-ans 域名
        if item_type == 'exam':
            exam_id = work.get('examId', wid)
            work_url = (f'https://mooc1.chaoxing.com/exam-ans/exam/test/examcode/examnotes'
                        f'?courseId={cid}&classId={clid}&examId={exam_id}&cpi={work.get("cpi", "")}')
        else:
            # 作业类型：构造URL
            work_url = work.get('href', '')
            if not work_url:
                work_url = (f'https://mooc1.chaoxing.com/mooc-ans/work/selectWorkReply'
                            f'?workId={wid}&classId={clid}&courseId={cid}&ut=s')
            elif work_url.startswith('/'):
                work_url = f'https://mooc1.chaoxing.com{work_url}'

        send_status(status_file,
                    phase="quiz",
                    quiz_total=len(works),
                    quiz_done=done,
                    quiz_failed=failed,
                    course_name=cname,
                    message=f"[{cname}] 答题 {i+1}/{len(works)}: {title[:30]}")

        logger.info(f"开始答题 type={item_type} title={title} url={work_url}")

        try:
            result = solve_quiz(
                session, work_url, api_key,
                ref_hashes=ref_hashes,
                cache=cache,
                dry_run=False,
            )
            if result.get('success'):
                done += 1
                logger.info(f"答题完成 title={title} questions={result.get('total', 0)} submitted={result.get('submitted', False)}")
            else:
                failed += 1
                logger.warning(f"答题失败 title={title} error={result.get('error', 'unknown')}")
        except Exception as e:
            failed += 1
            logger.error(f"答题异常 title={title} error={str(e)}")

    return done, failed, skipped


def send_status(status_file, **kwargs):
    data = {}
    if os.path.exists(status_file):
        try:
            with open(status_file) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    # 清除终态标记，防止进度更新时保留旧的 done/success 导致 TaskRunner 误判
    if not kwargs.get("done"):
        data.pop("done", None)
        data.pop("success", None)
    data.update(kwargs)
    data["updated_at"] = time.time()
    tmp_file = status_file + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_file, status_file)


def run_task(params_file, status_file):
    with open(params_file, encoding="utf-8") as f:
        params = json.load(f)

    # 学习通用账号密码登录
    cx_username = params.get("username", "")
    cx_password = params.get("password", "")
    course_ids = params.get("course_ids", [])
    # course_ids 格式: ["courseId:classId", ...] 或 [{"courseId": ..., "classId": ..., "course_name": ...}]

    if not cx_username or not cx_password:
        send_status(status_file, phase="error", message="未提供学习通账号密码", done=True, success=False)
        return

    send_status(status_file, phase="login", message="正在登录学习通...")

    from infrastructure.chaoxing_session import ChaoxingSession

    session = ChaoxingSession()
    if not session.login(cx_username, cx_password):
        send_status(status_file, phase="error", message="学习通登录失败，请检查账号密码", done=True, success=False)
        return

    user_info = session.get_user_info()
    student_name = user_info.get('name', '未知')
    logger.info(f"登录成功 user={student_name} uid={session.uid}")

    # 解析课程列表
    from infrastructure.chaoxing.crawler import fetch_course_list as get_course_list

    if course_ids:
        # 从course_ids解析
        courses = []
        for cid in course_ids:
            if isinstance(cid, dict):
                # 兼容 snake_case 和 camelCase 两种格式
                courses.append({
                    'courseId': cid.get('courseId') or cid.get('course_id', ''),
                    'classId': cid.get('classId') or cid.get('class_id', ''),
                    'course_name': cid.get('course_name') or cid.get('name', ''),
                })
            elif isinstance(cid, str) and ':' in cid:
                parts = cid.split(':')
                courses.append({'courseId': parts[0], 'classId': parts[1]})
            else:
                courses.append({'courseId': cid, 'classId': ''})
    else:
        courses = get_course_list(session)
        # 排除已结束课程
        courses = [c for c in courses if not c.get("ended")]

    if not courses:
        send_status(status_file, phase="error", message="未找到课程", done=True, success=False)
        return

    logger.info(f"课程数量 count={len(courses)}")

    # 导入积分系统
    from infrastructure.chaoxing_points import ScoreRuleParser, PointsExecutor

    # 多天循环
    day_count = 0
    while not _shutdown_requested:
        day_count += 1
        today = datetime.now().strftime('%Y-%m-%d')
        logger.info(f"=== 开始新的一天 day={day_count} date={today}")

        # 检查所有课程积分
        all_done = True
        _any_hit_daily_limit = False
        for course in courses:
            if _shutdown_requested:
                break

            cid = course.get('courseId', '')
            clid = course.get('classId', '')
            cname = course.get('course_name', course.get('name', f'课程{cid}'))

            if not clid:
                # 需要获取classId
                all_courses = get_course_list(session)
                for ac in all_courses:
                    if ac['courseId'] == cid:
                        clid = ac['classId']
                        course['classId'] = clid
                        break

            # 获取积分规则
            try:
                rule = ScoreRuleParser.fetch_rules(session, cid, clid)
                logger.info(f"积分规则 course={cname} target={rule.target} daily_limit={rule.daily_limit} video_min={rule.video_min}")
            except Exception as e:
                logger.warning(f"获取积分规则失败，使用默认值 error={str(e)}")
                from infrastructure.chaoxing_points import PointsRule
                rule = PointsRule()

            # 创建执行器
            executor = PointsExecutor(session, cid, clid, rule)

            # 检查当前积分状态
            status = executor.get_status()
            total = status.total
            remaining = status.day_score
            today_total = remaining

            logger.info("积分状态 course={} total={} target={} today={} remaining={}", cname, total, rule.target, today_total, executor.get_remaining_today(status))

            send_status(status_file,
                        phase="chaoxing_points",
                        points_total=total,
                        points_target=rule.target,
                        days=day_count,
                        course_name=cname,
                        message=f"[{cname}] 积分 {total}/{rule.target} 今日+{today_total}")

            if executor.check_done(status):
                logger.info(f"课程积分达标 course={cname}")
                # 标记 heavy_done，让 TaskRunner 启动 monitor_study 追踪后续进度
                send_status(status_file,
                            phase="study_must_learn",
                            heavy_done=True,
                            points_total=total,
                            points_target=rule.target,
                            days=day_count,
                            course_name=cname,
                            message=f"[{cname}] 积分达标，开始刷必学内容")
                # 积分已达标，刷必学视频+做作业/考试
                _api_key = os.environ.get("DEEPSEEK_API_KEY", "")
                if not _api_key:
                    try:
                        from config import DEEPSEEK_API_KEY
                        _api_key = DEEPSEEK_API_KEY
                    except Exception:
                        pass
                if clid:
                    try:
                        s_done, s_fail, s_skip = _study_must_learn(
                            session, cid, clid, cname, status_file, api_key=_api_key)
                        if s_done or s_fail:
                            logger.info(f"必学视频汇总 course={cname} done={s_done} failed={s_fail} skipped={s_skip}")
                    except Exception as e:
                        logger.warning(f"必学视频阶段异常 course={cname} error={str(e)}")
                if _api_key and clid:
                    try:
                        q_done, q_fail, q_skip = _solve_course_quizzes(
                            session, cid, clid, cname, status_file, _api_key)
                        if q_done or q_fail:
                            logger.info(f"答题汇总 course={cname} done={q_done} failed={q_fail} skipped={q_skip}")
                    except Exception as e:
                        logger.warning(f"答题阶段异常 course={cname} error={str(e)}")
                continue

            all_done = False

            # 今日还有额度
            daily_remaining = executor.get_remaining_today(status)
            if daily_remaining <= 0:
                _any_hit_daily_limit = True
                logger.info(f"今日积分已满 course={cname}")
                continue

            # 执行积分任务
            def _on_progress(msg):
                send_status(status_file,
                            phase="chaoxing_points",
                            points_total=total,
                            points_target=rule.target,
                            days=day_count,
                            course_name=cname,
                            message=f"[{cname}] {msg}")

            final_status = executor.execute_daily(
                status_file=status_file,
                on_progress=_on_progress
            )

            logger.info(f"今日结束 course={cname} total={final_status.total} target={rule.target}")

            send_status(status_file,
                        phase="chaoxing_points",
                        points_total=final_status.total,
                        points_target=rule.target,
                        days=day_count,
                        course_name=cname,
                        message=f"[{cname}] 今日完成，积分 {final_status.total}/{rule.target}")

            # 积分任务完成后，刷必学视频+做作业/考试
            _api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if not _api_key:
                try:
                    from config import DEEPSEEK_API_KEY
                    _api_key = DEEPSEEK_API_KEY
                except Exception:
                    pass
            if clid:
                try:
                    s_done, s_fail, s_skip = _study_must_learn(
                        session, cid, clid, cname, status_file, api_key=_api_key)
                    if s_done or s_fail:
                        logger.info(f"必学视频汇总 course={cname} done={s_done} failed={s_fail} skipped={s_skip}")
                except Exception as e:
                    logger.warning(f"必学视频阶段异常 course={cname} error={str(e)}")
            _api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if not _api_key:
                try:
                    from config import DEEPSEEK_API_KEY
                    _api_key = DEEPSEEK_API_KEY
                except Exception:
                    pass
            if _api_key and clid:
                try:
                    q_done, q_fail, q_skip = _solve_course_quizzes(
                        session, cid, clid, cname, status_file, _api_key)
                    if q_done or q_fail:
                        logger.info(f"答题汇总 course={cname} done={q_done} failed={q_fail} skipped={q_skip}")
                except Exception as e:
                    logger.warning(f"答题阶段异常 course={cname} error={str(e)}")

        if all_done:
            logger.info("所有课程积分达标！")
            send_status(status_file,
                        phase="done", done=True, success=True,
                        message=f"全部达标！共{len(courses)}门课程，耗时{day_count}天",
                        points_total=rule.target,
                        days=day_count)
            return

        if _shutdown_requested:
            break

        if _any_hit_daily_limit:
            logger.info(f"今日积分已满，退出等待明天恢复 day={day_count}")
            send_status(status_file,
                        phase="daily_done", done=True, success=True,
                        points_total=total,
                        points_target=rule.target,
                        days=day_count,
                        message=f"今日积分已满 ({total}/{rule.target})，明天继续",
                        need_resume=True)
            sys.exit(42)

        # 今日任务完成但未达总目标，退出让调度器明天重新调度
        logger.info(f"今日任务完成，等待明天继续 day={day_count} total={total}/{rule.target}")
        send_status(status_file,
                    phase="daily_done", done=True, success=True,
                    points_total=total,
                    points_target=rule.target,
                    days=day_count,
                    message=f"今日任务完成 ({total}/{rule.target})，明天继续",
                    need_resume=True)
        sys.exit(42)

    if _shutdown_requested:
        send_status(status_file, phase="error", message="收到退出信号", done=True, success=False)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python chaoxing_worker.py <params_file> <status_file>")
        sys.exit(1)

    def handle_signal(signum, frame):
        global _shutdown_requested
        _shutdown_requested = True
        logger.info("收到信号 {}，标记退出", signum)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        run_task(sys.argv[1], sys.argv[2])
    except Exception as e:
        logger.error("任务异常: {}\n{}", e, traceback.format_exc())
        try:
            send_status(sys.argv[2], phase="error", message=f"任务异常: {e}", done=True, success=False)
        except Exception:
            pass
        sys.exit(1)
    finally:
        try:
            sf = sys.argv[2]
            if os.path.exists(sf):
                with open(sf) as f:
                    data = json.load(f)
                if not data.get("done") and data.get("phase") != "error":
                    send_status(sf, phase="error", message="进程异常退出", done=True, success=False)
        except Exception:
            pass

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

from config import validate_settings


_shutdown_requested = False


def _solve_tsjy_knowledge_quiz(session, cid, kid, clid, cpi, kname, api_key,
                                status_file, cname, total, done, failed):
    """解答tsjy知识点测评（quiz）"""
    import re
    import json as _json
    from infrastructure.chaoxing.quiz import solve_quiz, load_ref_hashes, AnswerCache

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


def _solve_course_quizzes(session, cid, clid, cname, status_file, api_key):
    """为单个课程做作业/考试，返回 (done, failed, skipped) 计数"""
    from infrastructure.chaoxing.quiz import get_work_list, solve_quiz, load_ref_hashes, AnswerCache

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


from worker_common import ensure_terminal_status, push_ws_update, send_status


# ── 阶段拆分辅助（WORKER_PHASE_SPLIT_CX）────────────────────────

def _get_api_key() -> str:
    _api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not _api_key:
        try:
            from config import DEEPSEEK_API_KEY
            _api_key = DEEPSEEK_API_KEY
        except Exception:
            pass
    if not _api_key:
        try:
            from api.database import db
            _api_key = db.config_get('deepseek_api_key') or ''
        except Exception:
            pass
    return _api_key


def _plan_file(status_file: str) -> str:
    return os.path.join(os.path.dirname(status_file), "cx_plan.json")


def _load_plan(status_file: str) -> dict:
    try:
        with open(_plan_file(status_file), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _run_quiz_phase(session, plan: dict, courses, status_file) -> None:
    """quiz 阶段：积分补足（测评/讨论/笔记）+ 必学测评/阅读 + 课程作业/考试。
    视频已由 daemon 完成。终止语义与完整流程一致（done / daily_done exit 42）。"""
    from infrastructure.chaoxing.points import ScoreRuleParser, PointsExecutor, PointsRule

    api_key = plan.get("api_key") or _get_api_key()
    person_ids = plan.get("person_ids", {})
    all_done = True
    _any_hit_daily_limit = False
    total = 0
    rule = PointsRule()

    for course in courses:
        if _shutdown_requested:
            break
        cid = course.get('courseId', '')
        clid = course.get('classId', '')
        cname = course.get('course_name', course.get('name', f'课程{cid}'))
        if not clid:
            continue

        try:
            rule = ScoreRuleParser.fetch_rules(session, cid, clid)
        except Exception:
            rule = PointsRule()
        executor = PointsExecutor(session, cid, clid, rule)
        try:
            status = executor.get_status()
        except Exception as e:
            logger.warning(f"积分状态获取失败 course={cname} error={str(e)}")
            all_done = False
            continue
        total = status.total

        if not executor.check_done(status):
            all_done = False
            remaining = executor.get_remaining_today(status)
            if remaining <= 0:
                _any_hit_daily_limit = True
                logger.info(f"今日积分已满 course={cname}")
            else:
                # 视频已由 daemon 刷完，用测评/讨论/笔记补足
                earned = executor._answer_quizzes(remaining)
                if earned > 0:
                    status = executor.get_status()
                    remaining = executor.get_remaining_today(status)
                if remaining > 0:
                    executor._post_discussions(remaining)
                    status = executor.get_status()
                    remaining = executor.get_remaining_today(status)
                if remaining > 0:
                    executor._post_notes(remaining)
                send_status(status_file,
                            phase="chaoxing_points",
                            points_total=status.total,
                            points_target=rule.target,
                            days=plan.get("day_count", 1),
                            course_name=cname,
                            message=f"[{cname}] 今日完成，积分 {status.total}/{rule.target}")
                if executor.get_remaining_today(status) <= 0:
                    _any_hit_daily_limit = True

        # 必学测评 + 阅读（视频部分已由 daemon 完成）
        person_id = person_ids.get(cid, '')
        if api_key and person_id and clid:
            must_plan = [p for p in plan.get("must_learn_points", []) if p["cid"] == cid]
            for i, mp in enumerate(must_plan):
                if _shutdown_requested:
                    break
                kname = mp["name"]
                send_status(status_file,
                            phase="study_must_learn",
                            course_name=cname,
                            study_total=len(must_plan),
                            study_done=i,
                            study_failed=0,
                            message=f"[{cname}] 测评: {kname[:30]}")
                try:
                    _solve_tsjy_knowledge_quiz(
                        session, cid, mp["kid"], clid, person_id, kname, api_key,
                        status_file, cname, len(must_plan), i, 0)
                except Exception as e:
                    logger.warning(f"知识点测评异常 name={kname} error={str(e)}")
                try:
                    _do_tsjy_knowledge_read(
                        session, cid, mp["kid"], clid, person_id, kname, status_file,
                        cname, len(must_plan), i, 0)
                except Exception as e:
                    logger.warning(f"知识点阅读异常 name={kname} error={str(e)}")

        # 课程作业/考试
        if api_key and clid:
            try:
                q_done, q_fail, q_skip = _solve_course_quizzes(
                    session, cid, clid, cname, status_file, api_key)
                logger.info(f"答题汇总 course={cname} done={q_done} failed={q_fail} skipped={q_skip}")
                if q_fail > 0:
                    all_done = False
            except Exception as e:
                logger.warning(f"答题阶段异常 course={cname} error={str(e)}")
                all_done = False

    if all_done:
        logger.info("所有课程积分达标！")
        send_status(status_file, phase="done", done=True, success=True,
                    message=f"全部达标！共{len(courses)}门课程",
                    points_total=total,
                    days=plan.get("day_count", 1),
                    video_pct=100)
        return

    if _shutdown_requested:
        send_status(status_file, push_ws=True, phase="error", message="收到退出信号", done=True, success=False)
        return

    # 与完整流程一致：今日额度用完 → daily_done，明天调度器重跑
    send_status(status_file,
                phase="daily_done", done=True, success=True,
                points_total=total,
                points_target=rule.target,
                days=plan.get("day_count", 1),
                message=f"今日任务完成 ({total}/{rule.target})，明天继续",
                need_resume=True)
    sys.exit(42)


def run_task(params_file, status_file):
    with open(params_file, encoding="utf-8") as f:
        params = json.load(f)

    from config import init_worker_context
    init_worker_context(params)

    # 阶段模式：full（完整流程，默认）/ crawl（计划+提交 daemon 后退出）/ quiz（考试阶段）
    phase = params.get("phase", "crawl")  # 完整流程已删除，仅 crawl/quiz 两阶段

    # 学习通用账号密码登录
    cx_username = params.get("username", "")
    cx_password = params.get("password", "")
    course_ids = params.get("course_ids", [])
    # course_ids 格式: ["courseId:classId", ...] 或 [{"courseId": ..., "classId": ..., "course_name": ...}]

    if not cx_username or not cx_password:
        send_status(status_file, push_ws=True, phase="error", message="未提供学习通账号密码", done=True, success=False)
        return

    send_status(status_file, push_ws=True, phase="login", message="正在登录学习通...")

    from infrastructure.chaoxing.session import ChaoxingSession

    # 先尝试用缓存的 Cookie（跳过登录）
    session = None
    try:
        from services.scan_service import _try_cached_session
        session = _try_cached_session(cx_username, cx_password)
        if session:
            logger.info(f"使用缓存Cookie登录 username={cx_username}")
    except Exception as e:
        logger.debug(f"尝试缓存Cookie失败: {e}")

    # 缓存无效，重新登录
    if session is None:
        session = ChaoxingSession()
        if not session.login(cx_username, cx_password):
            send_status(status_file, push_ws=True, phase="error", message="学习通登录失败，请检查账号密码", done=True, success=False)
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
        send_status(status_file, push_ws=True, phase="error", message="未找到课程", done=True, success=False)
        return

    logger.info(f"课程数量 count={len(courses)}")

    # ── crawl 阶段：扫描+计划+刷视频全链 Rust（/submit_cx_full），登录留在本进程（rnet 指纹）──
    if phase == "crawl":
        import urllib.request as _ur
        from config import settings as _rust_cfg
        _cids = [str(_c.get("course_id") or _c.get("courseId") or "") if isinstance(_c, dict) else str(_c)
                 for _c in course_ids]
        _cids = [c for c in _cids if c]
        _payload = json.dumps({
            "order_id": params.get("order_id", os.path.basename(os.path.dirname(status_file))),
            "cookie_str": session.cookie_str,
            "uid": session.uid,
            "fid": session.fid,
            "ua": session.UA,
            "course_ids": _cids,
            "status_file": status_file,
            "push_ws": True,
        }).encode("utf-8")
        try:
            _req = _ur.Request(f"{_rust_cfg.rust_daemon_url}/submit_cx_full", data=_payload,
                               headers={"Content-Type": "application/json"}, method="POST")
            _resp = json.loads(_ur.urlopen(_req, timeout=5).read())
            if _resp.get("ok"):
                send_status(status_file,
                            phase="study_must_learn",
                            heavy_done=True,
                            study_total=0,
                            study_done=0,
                            study_failed=0,
                            message="学习通扫描+刷课已提交 Rust daemon")
                logger.info("Rust daemon 接手学习通扫描+刷课 order_id={}", params.get("order_id", ""))
                return
            send_status(status_file, phase="error",
                        message=f"Rust daemon 拒绝任务: {_resp.get('message')}",
                        done=True, success=False)
            return
        except Exception as e:
            send_status(status_file, phase="error",
                        message=f"Rust daemon 不可用: {e}", done=True, success=False)
            return

    # ── quiz 阶段：daemon 完成视频后由主进程再起本进程 ──
    if phase == "quiz":
        plan = _load_plan(status_file)
        plan["api_key"] = _get_api_key()
        if plan:
            _run_quiz_phase(session, plan, plan.get("courses") or courses, status_file)
        else:
            send_status(status_file, phase="error", message="学习计划文件丢失", done=True, success=False)
        return

if __name__ == "__main__":
    validate_settings()
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
        ensure_terminal_status(sys.argv[2])

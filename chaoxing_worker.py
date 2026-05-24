"""
学习通积分Worker

专用Worker：加载cookie → 检查积分 → 每天刷视频+答题+讨论+笔记 → 循环直到达标。
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


def send_status(status_file, **kwargs):
    data = {}
    if os.path.exists(status_file):
        try:
            with open(status_file) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
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
                continue

            all_done = False

            # 今日还有额度
            daily_remaining = executor.get_remaining_today(status)
            if daily_remaining <= 0:
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

        # 今日积分已满，退出让系统明天自动恢复（不阻塞 worker）
        logger.info(f"今日积分任务完成，退出等待明天恢复 day={day_count}")
        send_status(status_file,
                    phase="daily_done", done=True, success=True,
                    points_total=total,
                    points_target=rule.target,
                    days=day_count,
                    message=f"今日积分已满 ({total}/{rule.target})，明天继续",
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

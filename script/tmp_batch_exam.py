"""
批量考试测试脚本 - 遍历所有账号的未完成考试并答题提交
用法: 在远程服务器上运行
"""
import json
import os
import sys
import time
import traceback
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from loguru import logger
from bs4 import BeautifulSoup

httpx.packages.urllib3.disable_warnings()

# ==================== 平台配置 ====================
WEBSITES = {
    1: {"name": "在线课程测评考试平台", "base_url": "https://cdcas.suwankj.com"},
    2: {"name": "劳动课程测评考试平台", "base_url": "https://cdcas.taiskeji.com"},
    3: {"name": "公益课程平台", "base_url": "https://cdcas.chaoxiankeji.com"},
}


def decrypt_password(stored: str) -> str:
    """AES-256-GCM 解密密码（兼容旧 XOR 格式）"""
    import base64
    import hashlib
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from config import settings

    if not stored:
        return stored
    key = hashlib.sha256(settings.password_encryption_key.encode()).digest()

    if stored.startswith("ENC2:"):
        try:
            raw = base64.b64decode(stored[5:])
            nonce, ct = raw[:12], raw[12:]
            return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
        except Exception:
            return ""
    if stored.startswith("ENC:"):
        try:
            raw = base64.b64decode(stored[4:])
            return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode("utf-8")
        except Exception:
            return ""
    return stored


def get_accounts_from_db():
    """从数据库获取所有账号（含加密密码），按 (username, website_id) 去重"""
    import sqlite3

    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "orders.db")
    if not os.path.exists(db_path):
        logger.warning(f"数据库不存在: {db_path}")
        return []

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT DISTINCT username, password, website_id FROM orders WHERE password != ''")
    rows = c.fetchall()
    conn.close()

    seen = set()
    accounts = []
    for username, enc_password, website_id in rows:
        key = (username, website_id)
        if key in seen:
            continue
        seen.add(key)
        password = decrypt_password(enc_password)
        if not password:
            logger.warning(f"  解密密码失败: {username} @ 网站{website_id}")
            continue
        platform_name = WEBSITES.get(website_id, {}).get("name", f"平台{website_id}")
        accounts.append({
            "username": username,
            "password": password,
            "website_id": website_id,
            "platform_name": platform_name,
        })
    return accounts


def make_session():
    """创建新的 session"""
    s = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
    })
    return s


def login_with_captcha(username, password, website_id):
    """使用已有的 login_single_platform 登录（含验证码识别）"""
    from services.multi_platform_auth import login_single_platform, save_platform_cookie
    wid, ok, session, msg = login_single_platform(website_id, username, password)
    if not ok:
        return None, msg
    save_platform_cookie(username, website_id, session)
    return session, msg


def save_cookies(username, website_id, session):
    """保存 cookies 到文件"""
    from config import ACCOUNTS_DIR
    platform_name = WEBSITES.get(website_id, {}).get("name", "")
    cookie_dir = os.path.join(ACCOUNTS_DIR, username, "cookies")
    os.makedirs(cookie_dir, exist_ok=True)
    cookie_file = os.path.join(cookie_dir, f"{platform_name}.json")
    cookie_data = [{"name": c.name, "value": c.value} for c in session.cookies]
    with open(cookie_file, "w", encoding="utf-8") as f:
        json.dump(cookie_data, f, ensure_ascii=False)


def get_courses_direct(session, user_center_url, base_url):
    """直接用 session.get 获取课程列表，绕过 safe_request"""
    resp = session.get(user_center_url, timeout=15, follow_redirects=True)
    resp.encoding = "utf-8"
    logger.info(f"    resp: status={resp.status_code} url={resp.url} len={len(resp.text)} login={'login' in resp.url or 'login' in resp.text[:500].lower()}")
    if resp.status_code != 200 or 'login' in resp.url.lower():
        logger.warning(f"    被重定向到登录页或非200: {resp.url}")
        return []
    logger.info(f"    HTML前300字: {resp.text[:300]}")
    soup = BeautifulSoup(resp.text, "html.parser")
    course_nodes = soup.select('div.user-course div.item')
    logger.info(f"    找到 {len(course_nodes)} 个 course nodes")
    courses = []
    for node in course_nodes:
        name_el = node.select_one('div.name a')
        name = name_el.get_text(strip=True) if name_el else "未知课程"
        detail_link = name_el.get('href', '') if name_el else ''
        if detail_link and not detail_link.startswith('http'):
            detail_link = base_url + detail_link

        study_link = node.select_one('div.note div.status a')
        study_record_url = study_link.get('href', '') if study_link else ''
        if study_record_url and not study_record_url.startswith('http'):
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


def scan_exams(session, website_id, username="", course_ids=None):
    """扫描所有课程的考试/作业"""
    from config import set_current_website, update_url_config
    from services.scan_service import load_course_cache, scan_course

    set_current_website(website_id)
    update_url_config()

    from config import USER_CENTER_URL
    base_url = WEBSITES[website_id]["base_url"]
    logger.info(f"  URL: {USER_CENTER_URL}")

    # 直接用 session.get 绕过 safe_request
    courses = get_courses_direct(session, USER_CENTER_URL, base_url)
    if not courses:
        logger.warning("  get_courses 返回空")
        return []

    logger.info(f"获取到 {len(courses)} 门课程")
    all_exams = []
    for course in courses:
        cid = course.get("course_id", "")
        cname = course.get("name", "")
        if course_ids and cid not in course_ids:
            continue

        # 优先用缓存（带 username）
        cached = None
        if username:
            cached = load_course_cache(username, website_id, cid)

        if cached:
            raw_exams = cached.get("exams", [])
            raw_works = cached.get("works", [])
            logger.info(f"  缓存命中 {cname}: {len(raw_exams) + len(raw_works)} 个考试/作业")
        else:
            try:
                result = scan_course(session, cid, cname)
                raw_exams = result.get("exams", [])
                raw_works = result.get("works", [])
                logger.info(f"  实时扫描 {cname}: {len(raw_exams) + len(raw_works)} 个考试/作业")
            except Exception as e:
                logger.warning(f"扫描课程失败: {cname} - {e}")
                continue

        for exam in raw_exams:
            exam["course_id"] = cid
            exam["course_name"] = cname
            exam["item_type"] = "exam"
            all_exams.append(exam)
        for exam in raw_works:
            exam["course_id"] = cid
            exam["course_name"] = cname
            exam["item_type"] = "work"
            all_exams.append(exam)

    return all_exams


def classify_question_types(topics):
    """统计题型分布"""
    type_counts = defaultdict(int)
    for t in topics:
        q_type = t.get("q_type", "未知")
        type_counts[q_type] += 1
    return dict(type_counts)


def solve_exam_direct(session, base_url, exam, api_key):
    """直接调用考试答题流程（复用 infrastructure 模块）"""
    from infrastructure.anti_test import (
        AIAnswerer,
        OnlineHeartbeat,
        TopicFetcher,
        normalize_base_url,
    )
    from infrastructure.exam_answerer import WorkSubmitter

    base = normalize_base_url(base_url)
    work_id = exam["work_id"]
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

        # 统计题型
        type_counts = classify_question_types(topics)

        # 选择模型
        submit_type = getattr(fetcher, "_submit_type", "work")
        model = "deepseek-chat"

        answerer = AIAnswerer(api_key, model=model)
        answers = {}
        for topic in topics:
            tid = topic["topic_id"]
            ai_res = answerer.ask_one_topic(topic)
            answer = ai_res.get("answer", "").strip()
            if not answer:
                q_type = topic.get("q_type", "")
                is_choice = '单选' in q_type or '多选' in q_type or '判断' in q_type
                answer = "A" if is_choice else "暂无"
            answers[tid] = answer
            time.sleep(0.3)

        # 提交
        real_work_id = work_data.get("work_id", wid)
        node_id_str = work_data.get("node_id", "")
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


def main():
    from config import DEEPSEEK_API_KEY
    api_key = DEEPSEEK_API_KEY
    if not api_key:
        try:
            from api.database import db
            api_key = db.config_get("deepseek_api_key") or ""
        except:
            pass
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY 未配置")
        return

    print("=" * 80)
    print("批量考试测试 - 全账号遍历")
    print("=" * 80)

    accounts = get_accounts_from_db()
    print(f"数据库中找到 {len(accounts)} 个账号")

    # 统计
    total_exams = 0
    total_success = 0
    total_failed = 0
    total_skipped = 0
    all_type_counts = defaultdict(int)
    results = []

    for i, acc in enumerate(accounts):
        username = acc["username"]
        password = acc["password"]
        website_id = acc["website_id"]
        platform = acc.get("platform_name", WEBSITES.get(website_id, {}).get("name", f"平台{website_id}"))
        base_url = WEBSITES[website_id]["base_url"]

        print(f"\n{'─' * 60}")
        print(f"[{i+1}/{len(accounts)}] {username} @ {platform}")
        print(f"{'─' * 60}")

        # 登录
        try:
            session, msg = login_with_captcha(username, password, website_id)
            if not session:
                print(f"  ✗ 登录失败: {msg}")
                results.append({"username": username, "platform": platform, "error": msg})
                continue
            print(f"  ✓ {msg}")
            save_cookies(username, website_id, session)
        except Exception as e:
            print(f"  ✗ 登录异常: {e}")
            results.append({"username": username, "platform": platform, "error": str(e)})
            continue

        # 扫描考试
        try:
            exams = scan_exams(session, website_id, username=username)
        except Exception as e:
            print(f"  ✗ 扫描失败: {e}")
            results.append({"username": username, "platform": platform, "error": f"扫描失败: {e}"})
            continue

        if not exams:
            print(f"  - 无考试/作业")
            results.append({"username": username, "platform": platform, "exams": 0})
            continue

        # 过滤已完成的
        pending = [e for e in exams if not e.get("is_done") and not e.get("is_deleted")]
        done_exams = [e for e in exams if e.get("is_done")]
        print(f"  找到 {len(exams)} 个考试/作业, 已完成 {len(done_exams)}, 待考 {len(pending)}")

        total_skipped += len(done_exams)

        # 逐个考试
        acc_result = {
            "username": username,
            "platform": platform,
            "exams": len(exams),
            "done": len(done_exams),
            "pending": len(pending),
            "success": 0,
            "failed": 0,
            "details": [],
        }

        for j, exam in enumerate(pending):
            exam_name = exam.get("name", f"考试{exam.get('work_id', '?')}")
            print(f"  [{j+1}/{len(pending)}] {exam_name}")

            try:
                result = solve_exam_direct(session, base_url, exam, api_key)
            except Exception as e:
                result = {"success": False, "error": str(e), "types": {}}

            # 统计题型
            for q_type, count in result.get("types", {}).items():
                all_type_counts[q_type] += count

            err = result.get("error", "") or ""
            skip_keywords = ["已删除", "已结束", "不存在", "还未开始", "已经结束", "尚未生成答题记录"]
            should_skip = any(kw in err for kw in skip_keywords)

            if result.get("success"):
                total_success += 1
                acc_result["success"] += 1
                print(f"    ✓ 成功 ({result.get('submitted', 0)}/{result.get('total', 0)} 题)")
                for q_type, count in result.get("types", {}).items():
                    print(f"      {q_type}: {count}题")
            elif should_skip:
                total_skipped += 1
                print(f"    ⊘ 跳过: {err}")
            else:
                total_failed += 1
                acc_result["failed"] += 1
                print(f"    ✗ 失败: {err}")

            total_exams += 1
            acc_result["details"].append({
                "name": exam_name,
                "work_id": exam.get("work_id"),
                "success": result.get("success"),
                "error": result.get("error"),
                "types": result.get("types"),
                "submitted": result.get("submitted", 0),
                "total": result.get("total", 0),
            })

            # 考试间隔
            time.sleep(1)

        results.append(acc_result)

    # ==================== 汇总报告 ====================
    print("\n" + "=" * 80)
    print("汇总报告")
    print("=" * 80)
    print(f"账号总数: {len(accounts)}")
    print(f"考试总数: {total_exams}")
    print(f"成功: {total_success}")
    print(f"失败: {total_failed}")
    print(f"已跳过(之前已完成): {total_skipped}")

    print(f"\n题型统计:")
    for q_type, count in sorted(all_type_counts.items(), key=lambda x: -x[1]):
        print(f"  {q_type}: {count}题")

    # 保存详细结果
    report_file = "exam_test_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "accounts": len(accounts),
                "total_exams": total_exams,
                "success": total_success,
                "failed": total_failed,
                "skipped": total_skipped,
                "type_counts": dict(all_type_counts),
            },
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到 {report_file}")


if __name__ == "__main__":
    main()

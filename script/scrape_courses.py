"""
用 Scrapling 抓取指定账号的课程学习记录（开始时间、完成时间）
输出 CSV
"""
import csv
import io
import json
import os
import re
import sys
import time

if os.name == "nt":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import httpx
import urllib3
from bs4 import BeautifulSoup
from scrapling import Adaptor

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://cdcas.suwankj.com"
TARGET_COURSES = ["创新思维", "自我认知与情绪管理", "图说人际关系", "人像摄影", "情商与智慧人生"]

ACCOUNTS = [
    {"username": "251060150506", "password": "a285991"},
]


def login(username, password):
    import ddddocr
    ocr = ddddocr.DdddOcr(show_ad=False)
    session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
    session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    for _ in range(10):
        try:
            session.get(f"{BASE_URL}/user/login", timeout=15)
            cap = session.get(f"{BASE_URL}/service/code", timeout=15)
            code = ocr.classification(cap.content)
            r = session.post(f"{BASE_URL}/user/login", data={
                "username": username, "password": password, "code": code,
                "redirect": "", "remember": "on",
            }, follow_redirects=False, timeout=15)
            if "验证码有误" in r.text:
                continue
            if "操作成功" in r.text or '"status":true' in r.text:
                if r.status_code == 302:
                    loc = r.headers.get("Location", "")
                    if loc:
                        session.get(BASE_URL + loc if not loc.startswith("http") else loc, timeout=15)
                return session
            if "学生信息不存在" in r.text or "错误提示" in r.text:
                return None
        except Exception:
            continue
    return None


def strip_html(text):
    """去掉 HTML 标签"""
    return re.sub(r"<[^>]+>", "", str(text)).strip()


def get_course_video_records(session, course_id):
    """通过 AJAX 获取课程视频学习记录"""
    url = f"{BASE_URL}/user/study_record?courseId={course_id}&json=1"
    try:
        r = session.get(url, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=15)
        data = r.json()
        return data.get("list", [])
    except Exception:
        return []


def get_course_exam_records(session, course_id):
    """获取考试/作业记录"""
    records = []
    for rtype in ["exam", "work"]:
        url = f"{BASE_URL}/user/study_record/{rtype}?courseId={course_id}&json=1"
        try:
            r = session.get(url, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=15)
            data = r.json()
            if data.get("status"):
                for item in data.get("list", []):
                    item["_type"] = rtype
                    records.append(item)
        except Exception:
            pass
    return records


def main():
    all_rows = []

    for acc in ACCOUNTS:
        username = acc["username"]
        password = acc["password"]
        print(f"\n{'='*60}")
        print(f"Account: {username}")
        print(f"{'='*60}")

        session = login(username, password)
        if not session:
            print(f"  LOGIN FAILED")
            continue
        print(f"  LOGIN OK")

        # 获取课程列表
        resp = session.get(f"{BASE_URL}/user/index", timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        courses = []
        for item in soup.select("div.user-course div.item"):
            name_el = item.select_one("div.name a")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            href = name_el.get("href", "")
            m = re.search(r"courseId=(\d+)", href)
            if m:
                courses.append({"name": name, "course_id": m.group(1)})

        print(f"  Courses: {len(courses)}")

        # 匹配目标课程
        for course in courses:
            matched = False
            for target in TARGET_COURSES:
                if target in course["name"]:
                    matched = True
                    break
            if not matched:
                continue

            cname = course["name"]
            cid = course["course_id"]
            print(f"\n  >> {cname} (id={cid})")

            # 视频学习记录
            videos = get_course_video_records(session, cid)
            print(f"    Videos: {len(videos)}")
            for v in videos:
                name = v.get("name", "")
                begin = v.get("beginTime", "")
                final = v.get("finalTime", "")
                progress = v.get("progress", "0")
                state = strip_html(v.get("state", ""))
                view_count = v.get("viewCount", 0)
                viewed = v.get("viewedDuration", "")
                total_dur = v.get("videoDuration", "")

                print(f"    [{progress}] {name} | begin={begin} final={final} | {state}")

                all_rows.append({
                    "account": username,
                    "course": cname,
                    "item_type": "video",
                    "name": name,
                    "begin_time": begin,
                    "finish_time": final,
                    "progress": progress,
                    "state": state,
                    "view_count": view_count,
                    "viewed_duration": viewed,
                    "total_duration": total_dur,
                })

            # 考试/作业记录
            exams = get_course_exam_records(session, cid)
            print(f"    Exams: {len(exams)}")
            for e in exams:
                ename = e.get("name", e.get("title", ""))
                score = e.get("finalScore", e.get("score", ""))
                total = e.get("totalScore", e.get("total", ""))
                state = strip_html(e.get("state", e.get("status", "")))
                create = e.get("createTime", "")
                finish = e.get("finishTime", e.get("updateTime", ""))

                print(f"    {ename} | score={score}/{total} | {state}")

                all_rows.append({
                    "account": username,
                    "course": cname,
                    "item_type": e.get("_type", "exam"),
                    "name": ename,
                    "begin_time": create,
                    "finish_time": finish,
                    "progress": "",
                    "state": state,
                    "view_count": "",
                    "viewed_duration": score,
                    "total_duration": total,
                })

            time.sleep(0.5)

    # 保存 CSV
    if all_rows:
        csv_file = "course_progress_251060150506.csv"
        fields = ["account", "course", "item_type", "name", "begin_time", "finish_time",
                  "progress", "state", "view_count", "viewed_duration", "total_duration"]
        with open(csv_file, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(all_rows)
        print(f"\nSaved to {csv_file} ({len(all_rows)} rows)")
    else:
        print("\nNo data collected")


if __name__ == "__main__":
    main()

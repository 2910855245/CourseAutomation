"""批量获取考试成绩 v2 - 使用正确的AJAX API"""
import sys, os, re, json, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib, base64, httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from config import settings
from bs4 import BeautifulSoup
httpx.packages.urllib3.disable_warnings()
from services.multi_platform_auth import login_single_platform

WEBSITES = {1: "https://cdcas.suwankj.com", 2: "https://cdcas.taiskeji.com", 3: "https://cdcas.chaoxiankeji.com"}
PLATFORM_NAMES = {1: "在线课程", 2: "劳动课程", 3: "公益课程"}


def decrypt_password(stored):
    if not stored: return stored
    key = hashlib.sha256(settings.password_encryption_key.encode()).digest()
    if stored.startswith("ENC2:"):
        try:
            raw = base64.b64decode(stored[5:])
            return AESGCM(key).decrypt(raw[:12], raw[12:], None).decode()
        except: return ""
    if stored.startswith("ENC:"):
        try:
            raw = base64.b64decode(stored[4:])
            return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode()
        except: return ""
    return stored


def get_accounts():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "orders.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT DISTINCT username, password, website_id FROM orders WHERE password != ''")
    rows = c.fetchall()
    conn.close()
    seen = set()
    accounts = []
    for u, p, w in rows:
        k = (u, w)
        if k in seen: continue
        seen.add(k)
        pw = decrypt_password(p)
        if pw: accounts.append((u, pw, w))
    return accounts


def fetch_records(session, base_url, record_type, course_id, user_id):
    """通过AJAX获取考试/作业记录"""
    url = f"{base_url}/user/study_record/{record_type}?courseId={course_id}&json=1"
    if user_id:
        url += f"&userId={user_id}"
    headers = {"X-Requested-With": "XMLHttpRequest"}
    try:
        resp = session.get(url, headers=headers, timeout=15)
        data = resp.json()
        if data.get("status"):
            return data.get("list", [])
    except:
        pass
    return []


def main():
    accounts = get_accounts()
    print(f"Total accounts: {len(accounts)}")

    all_results = []
    has_scores_count = 0

    for i, (username, password, wid) in enumerate(accounts):
        base = WEBSITES[wid]
        platform = PLATFORM_NAMES.get(wid, f"平台{wid}")

        try:
            _, ok, session, msg = login_single_platform(wid, username, password)
            if not ok:
                print(f"[{i+1}] {username} @ {platform}: {msg}")
                all_results.append({"username": username, "platform": platform, "error": msg})
                continue
        except Exception as e:
            print(f"[{i+1}] {username} @ {platform}: {e}")
            all_results.append({"username": username, "platform": platform, "error": str(e)})
            continue

        # 获取课程列表
        resp = session.get(f"{base}/user/index", timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        courses = soup.select("div.user-course div.item div.name a")

        acc_result = {"username": username, "platform": platform, "courses": []}
        found_any = False

        for cl in courses:
            cname = cl.get_text(strip=True)
            href = cl.get("href", "")
            if not href: continue
            if not href.startswith("http"): href = base + href

            resp2 = session.get(href, timeout=15)
            resp2.encoding = "utf-8"
            soup2 = BeautifulSoup(resp2.text, "html.parser")

            course_id = ""
            user_id = ""
            for link in soup2.find_all("a", href=True):
                lh = link.get("href", "")
                if "study_record" in lh:
                    m = re.search(r"courseId=(\d+)", lh)
                    if m: course_id = m.group(1)
                    m = re.search(r"userId=(\d+)", lh)
                    if m: user_id = m.group(1)
                    break

            if not course_id: continue

            # 获取考试和作业记录
            exams = fetch_records(session, base, "exam", course_id, user_id)
            works = fetch_records(session, base, "work", course_id, user_id)

            if exams or works:
                found_any = True
                course_data = {"name": cname, "course_id": course_id, "exams": exams, "works": works}
                acc_result["courses"].append(course_data)

                print(f"[{i+1}] {username} @ {platform} - {cname}:")
                for exam in exams:
                    name = exam.get("name", exam.get("title", "?"))
                    score = exam.get("score", exam.get("getScore", exam.get("totalScore", "?")))
                    total = exam.get("total", exam.get("totalScore", "?"))
                    status = exam.get("status", "")
                    print(f"    考试: {name} -> 得分{score}/{total} ({status})")
                for work in works:
                    name = work.get("name", work.get("title", "?"))
                    score = work.get("score", work.get("getScore", work.get("totalScore", "?")))
                    total = work.get("total", work.get("totalScore", "?"))
                    status = work.get("status", "")
                    print(f"    作业: {name} -> 得分{score}/{total} ({status})")

        if found_any:
            has_scores_count += 1
        all_results.append(acc_result)

    # 汇总
    print(f"\n{'='*80}")
    print(f"有考试成绩的账号: {has_scores_count}/{len(accounts)}")

    with open("exam_scores_report.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"详细结果已保存到 exam_scores_report.json")


if __name__ == "__main__":
    main()

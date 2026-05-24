"""查找datatable AJAX URL"""
import sys, os, re, json, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib, base64, httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from config import settings
from bs4 import BeautifulSoup
httpx.packages.urllib3.disable_warnings()
from services.multi_platform_auth import login_single_platform

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

for username, password, wid in accounts:
    if wid != 1: continue
    base = "https://cdcas.suwankj.com"
    try:
        _, ok, session, msg = login_single_platform(wid, username, password)
        if not ok: continue
        print(f"Logged in: {username}")
    except: continue

    resp = session.get(f"{base}/user/index", timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    courses = soup.select("div.user-course div.item div.name a")

    for cl in courses:
        name = cl.get_text(strip=True)
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

        # 获取考试记录页面
        exam_url = f"{base}/user/study_record/exam?courseId={course_id}&userId={user_id}"
        resp3 = session.get(exam_url, timeout=15)
        resp3.encoding = "utf-8"
        html = resp3.text

        # 查找 datatable 配置
        soup3 = BeautifulSoup(html, "html.parser")
        tables = soup3.find_all("table")
        for table in tables:
            yee = table.get("yee-module", "")
            if "datatable" in yee:
                print(f"\n{name} datatable:")
                for attr, val in table.attrs.items():
                    if attr.startswith("data-"):
                        print(f"  {attr}: {val}")

        # 查找页面中的JS
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        for script in scripts:
            if "datatable" in script or "exam" in script:
                lines = script.split("\n")
                for line in lines:
                    line = line.strip()
                    if line and len(line) < 300 and ("url" in line.lower() or "exam" in line.lower() or "datatable" in line.lower()):
                        print(f"JS: {line}")

        # 直接尝试datatable的AJAX URL模式
        for test_url in [
            f"{base}/user/study_record/exam?courseId={course_id}&userId={user_id}&json=1",
            f"{base}/user/study_record/exam_data?courseId={course_id}&userId={user_id}",
            f"{base}/api/study_record/exam?courseId={course_id}&userId={user_id}",
            f"{base}/user/study_record/exam/list?courseId={course_id}&userId={user_id}",
        ]:
            try:
                resp4 = session.get(test_url, timeout=10, headers={"X-Requested-With": "XMLHttpRequest"})
                if resp4.status_code == 200:
                    content = resp4.text[:500]
                    if content.strip().startswith("{") or content.strip().startswith("["):
                        print(f"\nAJAX {test_url}: {content}")
            except:
                pass

        break
    break

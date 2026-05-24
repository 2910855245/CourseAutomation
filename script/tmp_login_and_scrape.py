import sqlite3, json, sys, os, httpx, hashlib, base64
sys.stdout.reconfigure(encoding='utf-8')
httpx.packages.urllib3.disable_warnings()

ENCRYPTION_KEY = "change-me-encryption-key-32bytes!"
BASE_URL = "https://cdcas.taiskeji.com"
PLATFORM_NAME = "劳动课程测评考试平台"

def decrypt_password(stored):
    if not stored or not stored.startswith("ENC:"):
        return stored
    try:
        raw = base64.b64decode(stored[4:])
        derived = hashlib.sha256(ENCRYPTION_KEY.encode()).digest()
        return bytes(b ^ derived[i % len(derived)] for i, b in enumerate(raw)).decode("utf-8")
    except:
        return stored

# Get accounts with passwords
conn = sqlite3.connect("/www/wwwroot/anti_course/data/orders.db")
c = conn.cursor()
c.execute("SELECT DISTINCT username, password FROM orders WHERE website_id = 2 AND password != ''")
accounts = c.fetchall()
conn.close()

print(f"Found {len(accounts)} accounts with passwords")

from datetime import datetime

for username, enc_password in accounts:
    password = decrypt_password(enc_password)
    print(f"\n{'='*70}")
    print(f"账号: {username}")
    print(f"{'='*70}")

    session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'X-Requested-With': 'XMLHttpRequest',
    })

    try:
        # Get login page (for any CSRF tokens)
        session.get(f"{BASE_URL}/user/login", timeout=10)

        # Login
        login_resp = session.post(f"{BASE_URL}/user/login", data={
            'username': username,
            'password': password,
        }, follow_redirects=True, timeout=10)

        # Check login
        if '退出登录' not in login_resp.text:
            print(f"  登录失败")
            continue

        print(f"  登录成功")

        # Get video data
        resp = session.get(f"{BASE_URL}/user/study_record/video",
                           params={"courseId": "1011331", "page": 1},
                           timeout=15)
        data = resp.json()
        videos = data.get("list", [])
        print(f"  视频数: {len(videos)}")

        # Extract completion times
        completed = []
        for v in videos:
            ft = v.get("finalTime", "")
            if ft and ft != "-":
                completed.append({
                    "name": v.get("name", ""),
                    "final_time": ft,
                    "begin_time": v.get("beginTime", ""),
                    "progress": v.get("progress", "0"),
                    "view_count": v.get("viewCount", "0"),
                    "video_duration": v.get("videoDuration", ""),
                    "viewed_duration": v.get("viewedDuration", ""),
                })

        completed.sort(key=lambda x: x["final_time"])

        print(f"\n  完成时间序列:")
        for i, v in enumerate(completed):
            print(f"  [{i+1:2d}] {v['final_time']:20s} | {v['name'][:35]:35s} | 进度:{v['progress']} | 播放:{v['view_count']}次 | 时长:{v['video_duration']} | 已看:{v['viewed_duration']}")

        # Parallel detection
        print(f"\n  并行刷课检测 (间隔 < 60秒):")
        parallel_count = 0
        for i in range(1, len(completed)):
            try:
                t1 = completed[i-1]["final_time"]
                t2 = completed[i]["final_time"]
                dt1 = datetime.strptime(f"2026-{t1}", "%Y-%m-%d %H:%M:%S")
                dt2 = datetime.strptime(f"2026-{t2}", "%Y-%m-%d %H:%M:%S")
                diff = abs((dt2 - dt1).total_seconds())
                if diff < 60:
                    parallel_count += 1
                    print(f"    !!! {completed[i-1]['name'][:25]:25s} -> {completed[i]['name'][:25]:25s} | 间隔: {diff:.0f}秒")
            except:
                pass
        if parallel_count == 0:
            print(f"    未检测到并行刷课")
        else:
            print(f"    检测到 {parallel_count} 处并行刷课嫌疑!")

        # Update cookie file
        cookie_data = [{"name": c.name, "value": c.value, "domain": c.domain} for c in session.cookies]
        cookie_path = f'/www/wwwroot/anti_course/data/accounts/{username}/cookies/{PLATFORM_NAME}.json'
        os.makedirs(os.path.dirname(cookie_path), exist_ok=True)
        with open(cookie_path, 'w', encoding='utf-8') as f:
            json.dump(cookie_data, f, ensure_ascii=False)

    except Exception as e:
        print(f"  错误: {e}")

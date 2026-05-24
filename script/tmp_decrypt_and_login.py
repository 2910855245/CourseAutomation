import sqlite3, json, sys, os, httpx
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '/www/wwwroot/anti_course')
httpx.packages.urllib3.disable_warnings()

# Decrypt passwords using project's crypto module
from api.crypto import decrypt_password

BASE_URL = "https://cdcas.taiskeji.com"
PLATFORM_NAME = "劳动课程测评考试平台"

# Get accounts with passwords
conn = sqlite3.connect("/www/wwwroot/anti_course/data/orders.db")
c = conn.cursor()
c.execute("SELECT DISTINCT username, password FROM orders WHERE website_id = 2 AND password != ''")
accounts = c.fetchall()
conn.close()

print(f"Found {len(accounts)} accounts with passwords")

# Try each account
for username, enc_password in accounts:
    password = decrypt_password(enc_password)
    print(f"\n--- {username} (pw: {password[:3]}***) ---")

    session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'X-Requested-With': 'XMLHttpRequest',
    })

    # Login
    try:
        login_page = session.get(f"{BASE_URL}/user/login", timeout=10)
        login_resp = session.post(f"{BASE_URL}/user/login", data={
            'username': username,
            'password': password,
        }, follow_redirects=False, timeout=10)
        print(f"  Login status: {login_resp.status_code}")

        if login_resp.status_code in (302, 200):
            # Check if logged in
            check = session.get(f"{BASE_URL}/user/index", timeout=10)
            if '退出登录' in check.text:
                print(f"  登录成功!")
                # Get video data
                resp = session.get(f"{BASE_URL}/user/study_record/video",
                                   params={"courseId": "1011331", "page": 1},
                                   headers={"X-Requested-With": "XMLHttpRequest"},
                                   timeout=15)
                data = resp.json()
                videos = data.get("list", [])
                print(f"  视频数: {len(videos)}")

                # Sort by finalTime and analyze
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
                        })
                completed.sort(key=lambda x: x["final_time"])

                print(f"\n  完成时间序列:")
                for i, v in enumerate(completed):
                    print(f"  [{i+1:2d}] {v['final_time']:20s} | {v['name'][:35]:35s} | 进度:{v['progress']} | 播放:{v['view_count']}次")

                # Parallel detection
                from datetime import datetime
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

                # Save cookie for future use
                cookie_str = '; '.join([f"{c.name}={c.value}" for c in session.cookies])
                cookie_data = [{"name": c.name, "value": c.value, "domain": c.domain} for c in session.cookies]
                cookie_path = f'/www/wwwroot/anti_course/data/accounts/{username}/cookies/{PLATFORM_NAME}.json'
                with open(cookie_path, 'w', encoding='utf-8') as f:
                    json.dump(cookie_data, f, ensure_ascii=False)
                print(f"  Cookie已更新")
            else:
                print(f"  登录失败")
    except Exception as e:
        print(f"  错误: {e}")

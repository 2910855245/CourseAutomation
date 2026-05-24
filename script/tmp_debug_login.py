import json, sys, os, httpx
sys.stdout.reconfigure(encoding='utf-8')
httpx.packages.urllib3.disable_warnings()

BASE_URL = "https://cdcas.taiskeji.com"
PLATFORM_NAME = "劳动课程测评考试平台"

username = "251060150506"
cookie_path = f'/www/wwwroot/anti_course/data/accounts/{username}/cookies/{PLATFORM_NAME}.json'
with open(cookie_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

print("Cookie data type:", type(data))
print("Num cookies:", len(data))

session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
})

# Set cookies
for c in data:
    if 'name' in c and 'value' in c:
        session.cookies.set(c['name'], c['value'], domain=c.get('domain', ''))

print("Session cookies:", list(session.cookies.keys()))

# Check login
resp = session.get(f"{BASE_URL}/user/index", timeout=10, follow_redirects=True)
print(f"\nStatus: {resp.status_code}")
print(f"URL: {resp.url}")
print(f"Has '退出登录': {'退出登录' in resp.text}")
print(f"Has '个人中心': {'个人中心' in resp.text}")

import re
title = re.search(r'<title>(.*?)</title>', resp.text)
print(f"Title: {title.group(1) if title else 'N/A'}")

# Now test video API
resp2 = session.get(f"{BASE_URL}/user/study_record/video",
                    params={"courseId": "1011331", "page": 1},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                    timeout=15)
print(f"\nVideo API Status: {resp2.status_code}")
print(f"Content-Type: {resp2.headers.get('content-type','')}")
data2 = resp2.json() if resp2.status_code == 200 else {}
videos = data2.get("list", [])
print(f"Videos found: {len(videos)}")
if videos:
    v = videos[0]
    print(f"First video: {v.get('name','')} | finalTime={v.get('finalTime','')} | progress={v.get('progress','')}")

import json, sys, os, httpx
sys.stdout.reconfigure(encoding='utf-8')
httpx.packages.urllib3.disable_warnings()

BASE_URL = "https://cdcas.taiskeji.com"
PLATFORM_NAME = "劳动课程测评考试平台"

# Read one cookie
username = "251060150506"
cookie_path = f'/www/wwwroot/anti_course/data/accounts/{username}/cookies/{PLATFORM_NAME}.json'
with open(cookie_path, 'r', encoding='utf-8') as f:
    data = json.load(f)
cookie_str = '; '.join(f"{c['name']}={c['value']}" for c in data if 'name' in c)

session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'X-Requested-With': 'XMLHttpRequest',
})
for item in cookie_str.split(';'):
    if '=' in item:
        k, v = item.strip().split('=', 1)
        session.cookies.set(k, v)

course_id = "1011331"

# Fetch videos
print("=== 视频记录 ===")
resp = session.get(f"{BASE_URL}/user/study_record/video",
                   params={"courseId": course_id, "page": 1}, timeout=15)
print(f"Status: {resp.status_code}")
print(f"Content-Type: {resp.headers.get('content-type','')}")
text = resp.text[:3000]
print(text)

# Fetch exams
print("\n=== 考试记录 ===")
resp2 = session.get(f"{BASE_URL}/user/study_record/exam",
                    params={"courseId": course_id, "page": 1}, timeout=15)
print(f"Status: {resp2.status_code}")
print(resp2.text[:2000])

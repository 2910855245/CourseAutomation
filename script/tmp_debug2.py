import json, sys, os, httpx
sys.stdout.reconfigure(encoding='utf-8')
httpx.packages.urllib3.disable_warnings()

BASE_URL = "https://cdcas.taiskeji.com"
PLATFORM_NAME = "劳动课程测评考试平台"

# Read cookie for 251060150506
username = "251060150506"
cookie_path = f'/www/wwwroot/anti_course/data/accounts/{username}/cookies/{PLATFORM_NAME}.json'
print(f"Reading: {cookie_path}")
print(f"Exists: {os.path.exists(cookie_path)}")

with open(cookie_path, 'r', encoding='utf-8') as f:
    cookie_data = json.load(f)

print(f"Cookie count: {len(cookie_data)}")
for c in cookie_data:
    print(f"  {c.get('name')} = {c.get('value')[:30]}... domain={c.get('domain')}")

session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'X-Requested-With': 'XMLHttpRequest',
})
for c in cookie_data:
    if 'name' in c and 'value' in c:
        session.cookies.set(c['name'], c['value'], domain=c.get('domain', ''))

print(f"\nSession cookies: {list(session.cookies.keys())}")

# Test video API
resp = session.get(f"{BASE_URL}/user/study_record/video",
                   params={"courseId": "1011331", "page": 1}, timeout=15)
print(f"\nVideo API: status={resp.status_code}")
data = resp.json()
videos = data.get("list", [])
print(f"Videos: {len(videos)}")
for v in videos[:3]:
    print(f"  {v.get('name','')} | finalTime={v.get('finalTime','')} | progress={v.get('progress','')}")

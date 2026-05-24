import json, sys, os
sys.stdout.reconfigure(encoding='utf-8')

base = '/www/wwwroot/anti_course/data/accounts'
platform = '劳动课程测评考试平台'

all_cookies = {}
for username in os.listdir(base):
    cookie_path = os.path.join(base, username, 'cookies', f'{platform}.json')
    if not os.path.exists(cookie_path):
        continue
    try:
        with open(cookie_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            all_cookies[username] = data
    except:
        pass

# Save to a single file
with open('/tmp/all_cookies.json', 'w', encoding='utf-8') as f:
    json.dump(all_cookies, f, ensure_ascii=False)

print(f"Collected {len(all_cookies)} accounts")
for u, c in all_cookies.items():
    print(f"  {u}: {len(c)} cookies")

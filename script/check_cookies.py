import json, os, sys
sys.stdout.reconfigure(encoding='utf-8')

base = '/www/wwwroot/anti_course/data/accounts'
for username in os.listdir(base):
    cookie_dir = os.path.join(base, username, 'cookies')
    if not os.path.isdir(cookie_dir):
        continue
    for fname in os.listdir(cookie_dir):
        if not fname.endswith('.json'):
            continue
        fpath = os.path.join(cookie_dir, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                cookie_str = data.get('cookie', '')
            else:
                cookie_str = str(data)
            # Show first 80 chars of cookie
            print(f"{username}/{fname}: {len(cookie_str)} chars | {cookie_str[:80]}")
        except Exception as e:
            print(f"{username}/{fname}: ERROR {e}")

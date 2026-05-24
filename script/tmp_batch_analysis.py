import json, sys, hashlib, base64, httpx, time
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8')
httpx.packages.urllib3.disable_warnings()

import ddddocr

ENCRYPTION_KEY = 'change-me-encryption-key-32bytes!'
BASE_URL = 'https://cdcas.taiskeji.com'

def decrypt_password(stored):
    if not stored or not stored.startswith('ENC:'):
        return stored
    try:
        raw = base64.b64decode(stored[4:])
        derived = hashlib.sha256(ENCRYPTION_KEY.encode()).digest()
        return bytes(b ^ derived[i % len(derived)] for i, b in enumerate(raw)).decode('utf-8')
    except:
        return stored

def login_and_fetch(username, password, ocr, course_id='1011331'):
    session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

    for attempt in range(3):
        session.cookies.clear()
        session.get(f'{BASE_URL}/user/login', timeout=10)
        captcha_resp = session.get(f'{BASE_URL}/service/code', timeout=10)
        code = ocr.classification(captcha_resp.content)

        r = session.post(f'{BASE_URL}/user/login', data={
            'username': username, 'password': password,
            'code': code, 'redirect': '',
        }, follow_redirects=True, timeout=10)

        if 'status":true' in r.text:
            video_resp = session.get(f'{BASE_URL}/user/study_record/video',
                                     params={'courseId': course_id, 'page': 1},
                                     headers={'X-Requested-With': 'XMLHttpRequest'},
                                     timeout=15)
            data = video_resp.json()
            return data.get('list', [])
    return None

# Load passwords
with open('script/tmp_passwords.json', 'r', encoding='utf-8') as f:
    enc_passwords = json.load(f)

ocr = ddddocr.DdddOcr(show_ad=False)
all_results = {}

for username in enc_passwords:
    password = decrypt_password(enc_passwords[username])
    print(f'\n{"="*70}')
    print(f'Account: {username}')
    print(f'{"="*70}')

    videos = login_and_fetch(username, password, ocr)
    if videos is None:
        print('  Login failed')
        continue

    print(f'  Videos: {len(videos)}')

    completed = []
    for v in videos:
        ft = v.get('finalTime', '')
        if ft and ft != '-':
            completed.append({
                'name': v.get('name', ''),
                'final_time': ft,
                'begin_time': v.get('beginTime', ''),
                'progress': v.get('progress', '0'),
                'view_count': v.get('viewCount', '0'),
                'video_duration': v.get('videoDuration', ''),
                'viewed_duration': v.get('viewedDuration', ''),
            })

    completed.sort(key=lambda x: x['final_time'])
    print(f'  Completed: {len(completed)}')

    if not completed:
        continue

    print(f'  Timeline:')
    for i, v in enumerate(completed):
        print(f'    [{i+1:2d}] {v["final_time"]:20s} | {v["name"][:35]:35s} | progress:{v["progress"]} | views:{v["view_count"]}')

    # Parallel detection
    parallel_pairs = []
    for i in range(1, len(completed)):
        try:
            dt1 = datetime.strptime(f'2026-{completed[i-1]["final_time"]}', '%Y-%m-%d %H:%M:%S')
            dt2 = datetime.strptime(f'2026-{completed[i]["final_time"]}', '%Y-%m-%d %H:%M:%S')
            diff = abs((dt2 - dt1).total_seconds())
            if diff < 60:
                parallel_pairs.append({
                    'from': completed[i-1]['name'],
                    'to': completed[i]['name'],
                    'gap_seconds': diff,
                })
        except:
            pass

    if parallel_pairs:
        print(f'  PARALLEL DETECTED: {len(parallel_pairs)} instances')
        for p in parallel_pairs:
            print(f'    !!! {p["from"][:25]:25s} -> {p["to"][:25]:25s} | gap: {p["gap_seconds"]:.0f}s')
    else:
        print(f'  No parallel brushing detected')

    all_results[username] = {
        'total_videos': len(videos),
        'completed': len(completed),
        'videos': completed,
        'parallel_pairs': parallel_pairs,
        'parallel_count': len(parallel_pairs),
    }

    time.sleep(1)

# Save results
with open('script/tmp_parallel_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

# Summary
print(f'\n\n{"="*70}')
print(f'SUMMARY')
print(f'{"="*70}')
print(f'Accounts analyzed: {len(all_results)}')
for uname, r in all_results.items():
    status = f'PARALLEL x{r["parallel_count"]}' if r['parallel_count'] > 0 else 'OK'
    print(f'  {uname}: {r["completed"]}/{r["total_videos"]} completed | {status}')

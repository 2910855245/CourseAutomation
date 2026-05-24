import json, sys, hashlib, base64, httpx, time, csv
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8')
httpx.packages.urllib3.disable_warnings()

import ddddocr

ENCRYPTION_KEY = 'change-me-encryption-key-32bytes!'

PLATFORMS = {
    '1': {'name': '在线课程测评考试平台', 'base_url': 'https://cdcas.suwankj.com'},
    '2': {'name': '劳动课程测评考试平台', 'base_url': 'https://cdcas.taiskeji.com'},
    '3': {'name': '公益课程平台', 'base_url': 'https://cdcas.chaoxiankeji.com'},
}

def decrypt_password(stored):
    if not stored or not stored.startswith('ENC:'):
        return stored
    try:
        raw = base64.b64decode(stored[4:])
        derived = hashlib.sha256(ENCRYPTION_KEY.encode()).digest()
        return bytes(b ^ derived[i % len(derived)] for i, b in enumerate(raw)).decode('utf-8')
    except:
        return stored

def login_platform(base_url, username, password, ocr, max_retries=5):
    session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

    for attempt in range(max_retries):
        session.cookies.clear()
        try:
            session.get(f'{base_url}/user/login', timeout=10)
            captcha_resp = session.get(f'{base_url}/service/code', timeout=10)
            code = ocr.classification(captcha_resp.content)

            r = session.post(f'{base_url}/user/login', data={
                'username': username, 'password': password,
                'code': code, 'redirect': '',
            }, follow_redirects=True, timeout=10)

            if 'status":true' in r.text:
                return session
        except:
            pass
    return None

def fetch_all_videos(session, base_url, course_id):
    videos = []
    page = 1
    while True:
        try:
            resp = session.get(f'{base_url}/user/study_record/video',
                             params={'courseId': course_id, 'page': page},
                             headers={'X-Requested-With': 'XMLHttpRequest'},
                             timeout=15)
            data = resp.json()
            items = data.get('list', [])
            if not items:
                break
            videos.extend(items)
            page_info = data.get('pageInfo', {})
            if page >= page_info.get('pageCount', 1):
                break
            page += 1
        except:
            break
    return videos

def analyze_parallel(videos):
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
            })
    completed.sort(key=lambda x: x['final_time'])

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

    return completed, parallel_pairs

# Load accounts
with open('script/tmp_all_accounts.json', 'r', encoding='utf-8') as f:
    all_accounts = json.load(f)

ocr = ddddocr.DdddOcr(show_ad=False)
all_results = []
summary_rows = []

for wid, accounts in all_accounts.items():
    platform = PLATFORMS.get(wid, {})
    base_url = platform.get('base_url', '')
    platform_name = platform.get('name', f'Website {wid}')

    print(f'\n{"="*70}')
    print(f'Platform: {platform_name} ({base_url})')
    print(f'Accounts: {len(accounts)}')
    print(f'{"="*70}')

    for username, info in accounts.items():
        password = decrypt_password(info['password'])
        course_ids = info.get('course_ids', [])

        print(f'\n  --- {username} ---')

        session = login_platform(base_url, username, password, ocr)
        if not session:
            print(f'  Login FAILED')
            summary_rows.append({
                'username': username, 'platform': platform_name, 'platform_id': wid,
                'course_id': '-', 'course_name': '-', 'total_videos': 0,
                'completed': 0, 'parallel_count': 0, 'status': 'login_failed'
            })
            continue

        print(f'  Login OK')

        for course_id in course_ids:
            if not course_id:
                continue

            videos = fetch_all_videos(session, base_url, course_id)
            if not videos:
                print(f'  Course {course_id}: no data')
                continue

            completed, parallel_pairs = analyze_parallel(videos)
            course_name = videos[0].get('courseName', '') if videos else ''

            print(f'  Course {course_id}: {len(videos)} videos, {len(completed)} completed, {len(parallel_pairs)} parallel')

            if parallel_pairs:
                for p in parallel_pairs:
                    print(f'    !!! {p["from"][:25]:25s} -> {p["to"][:25]:25s} | gap: {p["gap_seconds"]:.0f}s')

            result = {
                'username': username,
                'platform': platform_name,
                'platform_id': wid,
                'course_id': course_id,
                'course_name': course_name,
                'total_videos': len(videos),
                'completed': len(completed),
                'videos': completed,
                'parallel_pairs': parallel_pairs,
                'parallel_count': len(parallel_pairs),
            }
            all_results.append(result)
            summary_rows.append({
                'username': username, 'platform': platform_name, 'platform_id': wid,
                'course_id': course_id, 'course_name': course_name,
                'total_videos': len(videos), 'completed': len(completed),
                'parallel_count': len(parallel_pairs),
                'status': 'parallel_detected' if parallel_pairs else 'ok'
            })

            time.sleep(0.5)

        time.sleep(1)

# Save detailed results
with open('script/tmp_full_parallel_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

# Save summary CSV
csv_path = 'script/parallel_brushing_report.csv'
with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'username', 'platform', 'platform_id', 'course_id', 'course_name',
        'total_videos', 'completed', 'parallel_count', 'status'
    ])
    writer.writeheader()
    writer.writerows(summary_rows)

# Print summary
print(f'\n\n{"="*70}')
print(f'SUMMARY REPORT')
print(f'{"="*70}')
print(f'Total records: {len(summary_rows)}')
parallel_count = sum(1 for r in summary_rows if r.get('parallel_count', 0) > 0)
ok_count = sum(1 for r in summary_rows if r.get('status') == 'ok')
fail_count = sum(1 for r in summary_rows if r.get('status') == 'login_failed')
print(f'Parallel detected: {parallel_count}')
print(f'OK (no parallel): {ok_count}')
print(f'Login failed: {fail_count}')

print(f'\n{"="*70}')
print(f'PARALLEL BRUSHING DETAILS')
print(f'{"="*70}')
for r in summary_rows:
    if r.get('parallel_count', 0) > 0:
        print(f'  {r["username"]:15s} | {r["platform"]:15s} | Course {r["course_id"]:10s} | {r["completed"]:3d} videos | {r["parallel_count"]:2d} parallel')

print(f'\nReport saved to: {csv_path}')
print(f'Details saved to: script/tmp_full_parallel_analysis.json')

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

def parse_duration(duration_str):
    """将 HH:MM:SS 格式转换为秒数"""
    if not duration_str:
        return 0
    try:
        parts = duration_str.split(':')
        if len(parts) == 3:
            h, m, s = map(int, parts)
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = map(int, parts)
            return m * 60 + s
    except:
        pass
    return 0

def analyze_video_data(videos):
    """分析单个课程的视频数据"""
    completed = []
    for v in videos:
        ft = v.get('finalTime', '')
        if ft and ft != '-':
            video_duration_sec = parse_duration(v.get('videoDuration', ''))
            viewed_duration_sec = parse_duration(v.get('viewedDuration', ''))

            # 计算观看时长与视频时长比例
            duration_ratio = viewed_duration_sec / video_duration_sec if video_duration_sec > 0 else 0

            # 计算从开始到完成的实际时间跨度
            begin_time = v.get('beginTime', '')
            time_span = 0
            if begin_time and ft:
                try:
                    dt1 = datetime.strptime(f'2026-{begin_time}', '%Y-%m-%d %H:%M:%S')
                    dt2 = datetime.strptime(f'2026-{ft}', '%Y-%m-%d %H:%M:%S')
                    time_span = abs((dt2 - dt1).total_seconds())
                except:
                    pass

            completed.append({
                'name': v.get('name', ''),
                'video_id': v.get('id', ''),
                'chapter_id': v.get('chapterId', ''),
                'final_time': ft,
                'begin_time': begin_time,
                'progress': v.get('progress', '0'),
                'view_count': v.get('viewCount', '0'),
                'video_duration': v.get('videoDuration', ''),
                'video_duration_sec': video_duration_sec,
                'viewed_duration': v.get('viewedDuration', ''),
                'viewed_duration_sec': viewed_duration_sec,
                'duration_ratio': round(duration_ratio, 2),
                'time_span': time_span,
                'time_span_hours': round(time_span / 3600, 2),
                'error': v.get('error', 0),
                'error_message': v.get('errorMessage', ''),
                'bid': v.get('bid', ''),
            })

    completed.sort(key=lambda x: x['final_time'])

    # 并行检测
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
                    'from_id': completed[i-1]['video_id'],
                    'to_id': completed[i]['video_id'],
                    'gap_seconds': diff,
                    'from_duration_ratio': completed[i-1]['duration_ratio'],
                    'to_duration_ratio': completed[i]['duration_ratio'],
                })
        except:
            pass

    # 统计分析
    stats = {
        'total_videos': len(videos),
        'completed_count': len(completed),
        'parallel_count': len(parallel_pairs),
        'parallel_rate': len(parallel_pairs) / len(completed) * 100 if completed else 0,
        'avg_duration_ratio': sum(v['duration_ratio'] for v in completed) / len(completed) if completed else 0,
        'avg_view_count': sum(int(v['view_count']) for v in completed) / len(completed) if completed else 0,
        'avg_time_span_hours': sum(v['time_span_hours'] for v in completed) / len(completed) if completed else 0,
        'low_ratio_count': sum(1 for v in completed if v['duration_ratio'] < 0.5),  # 观看时长不到视频时长一半
        'high_view_count': sum(1 for v in completed if int(v['view_count']) > 10),  # 观看次数超过10次
        'error_count': sum(1 for v in completed if v['error'] > 0),
    }

    return completed, parallel_pairs, stats

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

            completed, parallel_pairs, stats = analyze_video_data(videos)
            course_name = videos[0].get('courseName', '') if videos else ''

            print(f'  Course {course_id}: {len(videos)} videos, {len(completed)} completed, {len(parallel_pairs)} parallel')
            print(f'    Duration ratio avg: {stats["avg_duration_ratio"]:.2f}, Low ratio: {stats["low_ratio_count"]}')

            if parallel_pairs:
                for p in parallel_pairs[:3]:  # 只显示前3个
                    print(f'    !!! {p["from"][:25]:25s} -> {p["to"][:25]:25s} | gap: {p["gap_seconds"]:.0f}s | ratios: {p["from_duration_ratio"]:.2f}, {p["to_duration_ratio"]:.2f}')

            result = {
                'username': username,
                'platform': platform_name,
                'platform_id': wid,
                'course_id': course_id,
                'course_name': course_name,
                'stats': stats,
                'videos': completed,
                'parallel_pairs': parallel_pairs,
            }
            all_results.append(result)
            summary_rows.append({
                'username': username, 'platform': platform_name, 'platform_id': wid,
                'course_id': course_id, 'course_name': course_name,
                'total_videos': stats['total_videos'], 'completed': stats['completed_count'],
                'parallel_count': stats['parallel_count'],
                'parallel_rate': f"{stats['parallel_rate']:.1f}%",
                'avg_duration_ratio': f"{stats['avg_duration_ratio']:.2f}",
                'low_ratio_count': stats['low_ratio_count'],
                'avg_view_count': f"{stats['avg_view_count']:.1f}",
                'status': 'parallel_detected' if parallel_pairs else 'ok'
            })

            time.sleep(0.5)

        time.sleep(1)

# Save detailed results
with open('script/tmp_full_data_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

# Save summary CSV
csv_path = 'script/full_data_report.csv'
with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'username', 'platform', 'platform_id', 'course_id', 'course_name',
        'total_videos', 'completed', 'parallel_count', 'parallel_rate',
        'avg_duration_ratio', 'low_ratio_count', 'avg_view_count', 'status'
    ])
    writer.writeheader()
    writer.writerows(summary_rows)

# Print summary
print(f'\n\n{"="*70}')
print(f'FULL DATA ANALYSIS SUMMARY')
print(f'{"="*70}')
print(f'Total records: {len(summary_rows)}')
parallel_count = sum(1 for r in summary_rows if r.get('parallel_count', 0) > 0)
ok_count = sum(1 for r in summary_rows if r.get('status') == 'ok')
fail_count = sum(1 for r in summary_rows if r.get('status') == 'login_failed')
print(f'Parallel detected: {parallel_count}')
print(f'OK (no parallel): {ok_count}')
print(f'Login failed: {fail_count}')

print(f'\n{"="*70}')
print(f'DURATION RATIO ANALYSIS')
print(f'{"="*70}')
for r in summary_rows:
    if r.get('avg_duration_ratio') and r['avg_duration_ratio'] != '-':
        ratio = float(r['avg_duration_ratio'])
        if ratio < 0.5:
            print(f'  SUSPICIOUS: {r["username"]:15s} | {r["platform"]:15s} | Course {r["course_id"]:10s} | Ratio: {ratio:.2f} | Low ratio videos: {r["low_ratio_count"]}')

print(f'\nReport saved to: {csv_path}')
print(f'Details saved to: script/tmp_full_data_analysis.json')

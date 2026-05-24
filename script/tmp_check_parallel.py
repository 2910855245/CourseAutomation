import httpx, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
httpx.packages.urllib3.disable_warnings()

# Cookies from remote server
PLATFORMS = {
    '在线课程测评考试平台': {
        'base_url': 'https://cdcas.suwankj.com',
        'cookie': 'token=sid.G0QvHSdTiy8gdyBuswKEd9Su1edmTb',
        'website_id': 1,
    },
    '劳动课程测评考试平台': {
        'base_url': 'https://cdcas.taiskeji.com',
        'cookie': 'token=sid.X6gOhEPoY02UG2N2VwnY0WocMZt8L3',
        'website_id': 2,
    },
}

def make_session(cookie_str):
    s = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'X-Requested-With': 'XMLHttpRequest'
    })
    for item in cookie_str.split(';'):
        if '=' in item:
            k, v = item.strip().split('=', 1)
            s.cookies.set(k, v)
    return s

def check_platform(name, config, course_ids):
    print(f"\n{'='*60}")
    print(f"Platform: {name} (website_id={config['website_id']})")
    print(f"URL: {config['base_url']}")
    print(f"{'='*60}")

    s = make_session(config['cookie'])

    # Check login status
    resp = s.get(f"{config['base_url']}/user/index", timeout=10, follow_redirects=False)
    if resp.status_code in (302, 401, 403):
        print(f"  [!] Cookie expired (status={resp.status_code})")
        return
    print(f"  [+] Login OK")

    for course_id in course_ids:
        print(f"\n  --- Course {course_id} ---")

        # Fetch study records
        page = 1
        all_records = []
        while True:
            resp = s.get(f"{config['base_url']}/user/study_record/video",
                        params={"courseId": course_id, "page": page},
                        timeout=15)
            if resp.status_code != 200:
                print(f"  [!] API error: {resp.status_code}")
                break
            data = resp.json()
            records = data.get("list", []) if isinstance(data, dict) else []
            if not records:
                break
            all_records.extend(records)
            page_info = data.get("pageInfo", {})
            if page >= page_info.get("pageCount", 1):
                break
            page += 1

        print(f"  Total videos: {len(all_records)}")

        # Analyze each video for parallel brushing indicators
        parallel_pairs = []
        completed_videos = []

        for r in all_records:
            node_id = r.get('id', '') or r.get('nodeId', '')
            name = r.get('name', '')
            duration = r.get('duration', '0')
            viewed = r.get('viewedDuration', '')
            progress = r.get('progress', '')
            view_count = r.get('viewCount', 0)
            begin_time = r.get('beginTime', '')
            final_time = r.get('finalTime', '')
            status_val = r.get('status', '')

            # Parse duration to seconds
            def parse_dur(d):
                try:
                    parts = str(d).split(':')
                    if len(parts) == 3:
                        return int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                    elif len(parts) == 2:
                        return int(parts[0])*60 + int(parts[1])
                    return int(d)
                except:
                    return 0

            dur_sec = parse_dur(duration)
            viewed_sec = parse_dur(viewed)

            if viewed_sec > 0 or progress:
                completed_videos.append({
                    'node_id': node_id,
                    'name': name,
                    'duration': dur_sec,
                    'viewed': viewed_sec,
                    'progress': progress,
                    'view_count': view_count,
                    'begin_time': begin_time,
                    'final_time': final_time,
                })

            # Print detailed info
            pct = float(progress) if progress else 0
            if pct > 0:
                print(f"  [{pct:5.1f}%] {name[:40]:40s} dur={duration} viewed={viewed} views={view_count} begin={begin_time} final={final_time}")

        # Check for parallel brushing: adjacent videos completed within 60 seconds
        print(f"\n  Completed videos: {len(completed_videos)}")

        if len(completed_videos) >= 2:
            # Sort by final_time
            completed_videos.sort(key=lambda x: x.get('final_time', ''))
            for i in range(len(completed_videos) - 1):
                v1 = completed_videos[i]
                v2 = completed_videos[i+1]
                ft1 = v1.get('final_time', '')
                ft2 = v2.get('final_time', '')
                if ft1 and ft2:
                    try:
                        t1 = time.strptime(ft1, '%Y-%m-%d %H:%M:%S')
                        t2 = time.strptime(ft2, '%Y-%m-%d %H:%M:%S')
                        diff = abs(time.mktime(t2) - time.mktime(t1))
                        if diff < 60:
                            parallel_pairs.append((v1, v2, diff))
                    except:
                        pass

            if parallel_pairs:
                print(f"\n  [!!!] DETECTED {len(parallel_pairs)} parallel brushing pairs (间隔<60秒):")
                for v1, v2, diff in parallel_pairs[:10]:
                    print(f"    {v1['name'][:30]} -> {v2['name'][:30]} | interval={diff:.0f}s")
            else:
                print(f"\n  [+] No parallel brushing detected (all intervals >= 60s)")

            # Check view_count > 1
            multi_view = [v for v in completed_videos if v.get('view_count', 0) and int(v.get('view_count', 0)) > 1]
            if multi_view:
                print(f"\n  [!] {len(multi_view)} videos with view_count > 1:")
                for v in multi_view[:5]:
                    print(f"    {v['name'][:40]} views={v['view_count']}")

# Run checks
# ORD-D316F99A: website_id=1, course 1000838
check_platform('在线课程测评考试平台', PLATFORMS['在线课程测评考试平台'], ['1000838'])

# ORD-13457684: website_id=2, course 1011331
check_platform('劳动课程测评考试平台', PLATFORMS['劳动课程测评考试平台'], ['1011331'])

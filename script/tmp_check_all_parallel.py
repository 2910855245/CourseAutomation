import httpx, json, sys, time, io, os
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8')
import paramiko

# SSH to remote server
with open(os.path.join(os.path.dirname(__file__), 'ssh_key')) as f:
    ssh_key = f.read()

kf = io.StringIO(ssh_key)
key = paramiko.Ed25519Key.from_private_key(kf)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('38.76.190.251', 22, 'root', pkey=key, timeout=15, allow_agent=False, look_for_keys=False)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

httpx.packages.urllib3.disable_warnings()

PLATFORM_MAP = {
    '在线课程测评考试平台': 'https://cdcas.suwankj.com',
    '劳动课程测评考试平台': 'https://cdcas.taiskeji.com',
    '公益课程平台': 'https://cdcas.chaoxiankeji.com',
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

def parse_time(ts):
    """Parse time string like '05-23 17:43:32' or '2026-05-23 17:43:32'"""
    if not ts:
        return None
    for fmt in ['%Y-%m-%d %H:%M:%S', '%m-%d %H:%M:%S']:
        try:
            return datetime.strptime(ts, fmt)
        except:
            pass
    return None

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

def check_account_platform(username, platform_name, base_url, cookie_str):
    s = make_session(cookie_str)
    try:
        resp = s.get(f"{base_url}/user/index", timeout=10, follow_redirects=False)
        if resp.status_code in (302, 401, 403):
            return None
    except:
        return None

    # Get courses from scan cache
    out, _ = run(f'cat "/www/wwwroot/anti_course/data/accounts/{username}/scan_cache/{platform_name}.json" 2>/dev/null')
    courses = []
    try:
        cache = json.loads(out)
        if isinstance(cache, dict):
            # Format: {"saved_at": ..., "data": {"courses": [...]}}
            courses = cache.get('data', {}).get('courses', [])
            if not courses:
                courses = cache.get('courses', [])
        elif isinstance(cache, list):
            courses = cache
    except:
        pass

    if not courses:
        # Try courses dir
        out, _ = run(f'find "/www/wwwroot/anti_course/data/accounts/{username}/courses/{platform_name}/" -name "*.json" 2>/dev/null')
        course_files = [f.strip() for f in out.strip().split('\n') if f.strip()]
        for cf in course_files:
            out2, _ = run(f'cat "{cf}"')
            try:
                cd = json.loads(out2)
                if isinstance(cd, dict) and cd.get('course_id'):
                    courses.append(cd)
            except:
                pass

    if not courses:
        # Try API
        try:
            resp = s.get(f"{base_url}/user/study_record/video", params={"page": 1}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                records = data.get("list", []) if isinstance(data, dict) else []
                course_ids = list(set(r.get('courseId', '') for r in records if r.get('courseId')))
                courses = [{'course_id': cid, 'course_name': ''} for cid in course_ids]
        except:
            pass

    results = []
    for course in (courses or []):
        if isinstance(course, dict):
            course_id = course.get('course_id', '')
            course_name = course.get('course_name', '')
        else:
            course_id = str(course)
            course_name = ''
        if not course_id:
            continue

        # Fetch study records
        page = 1
        all_records = []
        while True:
            try:
                resp = s.get(f"{base_url}/user/study_record/video",
                            params={"courseId": course_id, "page": page},
                            timeout=15)
                if resp.status_code != 200:
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
            except:
                break

        if not all_records:
            continue

        # Analyze
        begin_times = []
        final_times = []
        completed = []
        multi_view = []
        overlapping = 0

        for r in all_records:
            bt = parse_time(r.get('beginTime', ''))
            ft = parse_time(r.get('finalTime', ''))
            vc = int(r.get('viewCount', 0) or 0)
            progress = float(r.get('progress', 0) or 0)
            dur = parse_dur(r.get('duration', '0'))

            if bt:
                begin_times.append(bt)
            if ft and progress >= 1:
                final_times.append((bt, ft, dur))
            if progress >= 1:
                completed.append(r)
            if vc > 1:
                multi_view.append({'name': r.get('name', ''), 'views': vc})

        # 1. beginTime clustering (within 60 seconds)
        begin_cluster = 0
        if len(begin_times) >= 2:
            begin_times.sort()
            for i in range(1, len(begin_times)):
                diff = (begin_times[i] - begin_times[i-1]).total_seconds()
                if diff < 60:
                    begin_cluster += 1

        # 2. finalTime clustering
        final_cluster = 0
        if len(final_times) >= 2:
            final_times.sort(key=lambda x: x[1])
            for i in range(1, len(final_times)):
                diff = (final_times[i][1] - final_times[i-1][1]).total_seconds()
                if diff < 60:
                    final_cluster += 1

        # 3. Time overlap detection
        if len(final_times) >= 2:
            sorted_records = sorted(final_times, key=lambda x: x[0] if x[0] else datetime.min)
            for i in range(len(sorted_records)):
                for j in range(i+1, len(sorted_records)):
                    bt_i, ft_i, dur_i = sorted_records[i]
                    bt_j, ft_j, dur_j = sorted_records[j]
                    if bt_i and ft_i and bt_j and ft_j:
                        # If video i's end time > video j's start time, they overlap
                        if ft_i > bt_j:
                            # But only if the overlap is significant (>30 seconds)
                            overlap = (ft_i - bt_j).total_seconds()
                            if overlap > 30:
                                overlapping += 1

        # Calculate risk score
        score = 0
        score += begin_cluster * 5
        score += final_cluster * 10
        score += len(multi_view) * 3
        score += overlapping * 8

        if begin_cluster > 5 or overlapping > 5:
            level = 'CRITICAL'
        elif begin_cluster > 3 or overlapping > 3:
            level = 'HIGH'
        elif begin_cluster > 0 or overlapping > 0:
            level = 'MEDIUM'
        else:
            level = 'LOW'

        results.append({
            'course_id': course_id,
            'course_name': course_name,
            'total_videos': len(all_records),
            'completed': len(completed),
            'begin_cluster': begin_cluster,
            'final_cluster': final_cluster,
            'overlapping': overlapping,
            'multi_view': len(multi_view),
            'multi_view_details': multi_view[:5],
            'score': score,
            'level': level,
        })

    return results

# Main
print("="*100)
print("COMPREHENSIVE PARALLEL BRUSHING DETECTION - ALL ACCOUNTS")
print("="*100)

out, _ = run('ls /www/wwwroot/anti_course/data/accounts/')
accounts = [d.strip() for d in out.strip().split('\n') if d.strip() and not d.startswith('.')]
print(f"Total accounts: {len(accounts)}")

all_results = {}
for username in accounts:
    # Get cookies
    out, _ = run(f'ls /www/wwwroot/anti_course/data/accounts/{username}/cookies/ 2>/dev/null')
    cookie_files = [f.strip() for f in out.strip().split('\n') if f.strip()]

    if not cookie_files:
        continue

    account_results = []
    for cf in cookie_files:
        platform_name = cf.replace('.json', '')
        base_url = PLATFORM_MAP.get(platform_name)
        if not base_url:
            continue

        out, _ = run(f'cat "/www/wwwroot/anti_course/data/accounts/{username}/cookies/{cf}"')
        try:
            cookie_list = json.loads(out)
            cookie_str = '; '.join([f"{c['name']}={c['value']}" for c in cookie_list])
        except:
            continue

        results = check_account_platform(username, platform_name, base_url, cookie_str)
        if results:
            for r in results:
                r['platform'] = platform_name
                account_results.append(r)

    if account_results:
        all_results[username] = account_results

# Print detailed results
print("\n" + "="*100)
print("DETAILED RESULTS")
print("="*100)

for username, results in sorted(all_results.items(), key=lambda x: max(r['score'] for r in x[1]), reverse=True):
    max_score = max(r['score'] for r in results)
    if max_score == 0:
        continue

    print(f"\n{'─'*100}")
    print(f"Account: {username} (max_score={max_score})")
    print(f"{'─'*100}")

    for r in sorted(results, key=lambda x: x['score'], reverse=True):
        if r['score'] == 0:
            continue
        print(f"  [{r['level']:8s}] {r['platform']:20s} | {r['course_name'][:35]:35s} | "
              f"videos={r['total_videos']:3d} completed={r['completed']:3d} | "
              f"begin={r['begin_cluster']:3d} final={r['final_cluster']:3d} "
              f"overlap={r['overlapping']:3d} multi_view={r['multi_view']:3d} | "
              f"score={r['score']:4d}")
        if r['multi_view_details']:
            for mv in r['multi_view_details'][:3]:
                print(f"           multi_view: {mv['name'][:40]} views={mv['views']}")

# Summary
print("\n" + "="*100)
print("RISK SUMMARY")
print("="*100)

risk_levels = {'CRITICAL': [], 'HIGH': [], 'MEDIUM': [], 'LOW': []}
for username, results in all_results.items():
    for r in results:
        if r['score'] > 0:
            risk_levels[r['level']].append(f"{username} | {r['platform']} | {r['course_name'][:30]} | score={r['score']}")

for level in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
    items = risk_levels[level]
    if items:
        print(f"\n{level} ({len(items)}):")
        for item in items:
            print(f"  {'[!!!]' if level == 'CRITICAL' else '[!!]' if level == 'HIGH' else '[!]'} {item}")

# Statistics
total_accounts = len(all_results)
accounts_with_risk = len([u for u, r in all_results.items() if any(x['score'] > 0 for x in r)])
print(f"\n{'='*100}")
print(f"STATISTICS")
print(f"{'='*100}")
print(f"Accounts checked: {len(accounts)}")
print(f"Accounts with study records: {total_accounts}")
print(f"Accounts with risk: {accounts_with_risk}")
print(f"CRITICAL: {len(risk_levels['CRITICAL'])}")
print(f"HIGH: {len(risk_levels['HIGH'])}")
print(f"MEDIUM: {len(risk_levels['MEDIUM'])}")
print(f"LOW: {len(risk_levels['LOW'])}")

ssh.close()

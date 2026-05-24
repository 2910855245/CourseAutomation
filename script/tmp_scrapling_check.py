import json, sys, hashlib, base64, httpx, time
sys.stdout.reconfigure(encoding='utf-8')
httpx.packages.urllib3.disable_warnings()

from scrapling import Fetcher
import ddddocr

ENCRYPTION_KEY = 'change-me-encryption-key-32bytes!'
BASE_URL = 'https://cdcas.suwankj.com'

def decrypt_password(stored):
    if not stored or not stored.startswith('ENC:'):
        return stored
    try:
        raw = base64.b64decode(stored[4:])
        derived = hashlib.sha256(ENCRYPTION_KEY.encode()).digest()
        return bytes(b ^ derived[i % len(derived)] for i, b in enumerate(raw)).decode('utf-8')
    except:
        return stored

# Load passwords
with open('script/tmp_passwords.json', 'r', encoding='utf-8') as f:
    enc_passwords = json.load(f)

username = '251060150506'
password = decrypt_password(enc_passwords.get(username, ''))

print(f'账号: {username}')
print(f'平台: {BASE_URL}')

# 用requests登录获取cookie
ocr = ddddocr.DdddOcr(show_ad=False)
session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)

for attempt in range(5):
    session.cookies.clear()
    session.get(f'{BASE_URL}/user/login', timeout=10)
    captcha_resp = session.get(f'{BASE_URL}/service/code', timeout=10)
    code = ocr.classification(captcha_resp.content)

    r = session.post(f'{BASE_URL}/user/login', data={
        'username': username, 'password': password,
        'code': code, 'redirect': '',
    }, follow_redirects=True, timeout=10)

    if 'status":true' in r.text:
        print('登录成功')
        break
else:
    print('登录失败')
    exit()

# 获取cookie字符串
cookie_str = '; '.join([f'{c.name}={c.value}' for c in session.cookies])

# 获取课程列表
print('\n获取课程列表...')
resp = session.get(f'{BASE_URL}/user/study_record',
                   headers={'X-Requested-With': 'XMLHttpRequest'},
                   timeout=10)

# 从之前的数据读取课程ID
with open('script/tmp_full_data_analysis.json', 'r', encoding='utf-8') as f:
    all_data = json.load(f)

# 找到该账号的数据
user_courses = [r for r in all_data if r['username'] == username]
print(f'该账号有 {len(user_courses)} 条课程记录')

for course in user_courses:
    course_id = course['course_id']
    platform = course['platform']
    print(f'\n{"="*70}')
    print(f'课程: {course_id} ({platform})')
    print(f'总视频: {course["stats"]["total_videos"]}')
    print(f'已完成: {course["stats"]["completed_count"]}')
    print(f'并行数: {course["stats"]["parallel_count"]}')
    print(f'并行率: {course["stats"]["parallel_rate"]:.1f}%')

    # 用scrapling获取学习记录页面
    print(f'\n用scrapling获取学习记录页面...')
    fetcher = Fetcher()

    # 构造cookie
    headers = {
        'Cookie': cookie_str,
        'X-Requested-With': 'XMLHttpRequest',
    }

    # 获取视频学习记录
    url = f'{BASE_URL}/user/study_record/video?courseId={course_id}&page=1'
    resp = session.get(url, headers={'X-Requested-With': 'XMLHttpRequest'}, timeout=10)
    data = resp.json()

    videos = data.get('list', [])
    print(f'API返回 {len(videos)} 个视频')

    # 分析并行刷课
    completed = []
    for v in videos:
        ft = v.get('finalTime', '')
        if ft and ft != '-':
            completed.append(v)

    completed.sort(key=lambda x: x.get('finalTime', ''))

    print(f'\n已完成视频时间线:')
    for i, v in enumerate(completed[:20]):  # 只显示前20个
        ft = v.get('finalTime', '')
        name = v.get('name', '')[:30]
        viewed = v.get('viewedDuration', '')
        video_dur = v.get('videoDuration', '')
        view_count = v.get('viewCount', '')

        # 计算与前一个视频的间隔
        gap = ''
        if i > 0:
            try:
                from datetime import datetime
                dt1 = datetime.strptime(f'2026-{completed[i-1]["finalTime"]}', '%Y-%m-%d %H:%M:%S')
                dt2 = datetime.strptime(f'2026-{ft}', '%Y-%m-%d %H:%M:%S')
                diff = abs((dt2 - dt1).total_seconds())
                gap = f'{diff:.0f}s'
                if diff < 60:
                    gap = f'⚠️ {gap}'
            except:
                pass

        print(f'  [{i+1:2d}] {ft:20s} | {name:30s} | 视频:{video_dur:10s} | 观看:{viewed:10s} | 次数:{view_count:3s} | 间隔:{gap}')

    # 检查是否有风控标记
    print(f'\n检查是否有风控标记...')
    check_urls = [
        f'{BASE_URL}/user/risk',
        f'{BASE_URL}/user/warning',
        f'{BASE_URL}/user/violation',
        f'{BASE_URL}/user/status',
    ]

    for check_url in check_urls:
        try:
            resp = session.get(check_url, timeout=10)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if data.get('status') is not None:
                        print(f'  {check_url}: {data}')
                except:
                    pass
        except:
            pass

    time.sleep(1)

print('\n' + '='*70)
print('结论: 该账号并行率很高但未被封号，可能原因:')
print('1. 平台没有严格检测并行刷课')
print('2. 平台只记录不处罚')
print('3. 平台的检测阈值比推测的更高')
print('4. 平台可能在积累证据，后续统一处理')

import json, sys, hashlib, base64, httpx
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

def login_and_check(username, password, ocr):
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
            return session
    return None

# Load passwords
with open('script/tmp_passwords.json', 'r', encoding='utf-8') as f:
    enc_passwords = json.load(f)

ocr = ddddocr.DdddOcr(show_ad=False)

# 只测试第一个账号
username = list(enc_passwords.keys())[0]
password = decrypt_password(enc_passwords[username])

print(f'测试账号: {username}')
print(f'检查其他API端点...')

session = login_and_check(username, password, ocr)
if not session:
    print('登录失败')
    exit()

print('登录成功')

# 检查各种可能的API端点
endpoints = [
    # 学习记录相关
    ('/user/study_record', 'GET', {'courseId': '1011331'}),
    ('/user/study_record/video', 'GET', {'courseId': '1011331', 'page': 1}),
    ('/user/study_record/exam', 'GET', {'courseId': '1011331'}),
    ('/user/study_record/work', 'GET', {'courseId': '1011331'}),

    # 用户信息
    ('/user/info', 'GET', {}),
    ('/user/profile', 'GET', {}),
    ('/user/dashboard', 'GET', {}),

    # 课程信息
    ('/user/course', 'GET', {}),
    ('/user/course/list', 'GET', {}),

    # 学习统计
    ('/user/study/statistics', 'GET', {}),
    ('/user/study/record', 'GET', {}),
    ('/user/study/log', 'GET', {}),

    # 设备/IP信息
    ('/user/device', 'GET', {}),
    ('/user/login/log', 'GET', {}),
    ('/user/login/record', 'GET', {}),

    # 风控相关
    ('/user/risk', 'GET', {}),
    ('/user/warning', 'GET', {}),
    ('/user/violation', 'GET', {}),
]

print('\n检查API端点:')
for endpoint, method, params in endpoints:
    try:
        if method == 'GET':
            resp = session.get(f'{BASE_URL}{endpoint}', params=params, timeout=10)
        else:
            resp = session.post(f'{BASE_URL}{endpoint}', data=params, timeout=10)

        status = resp.status_code
        content_type = resp.headers.get('Content-Type', '')

        # 尝试解析JSON
        try:
            data = resp.json()
            is_json = True
            keys = list(data.keys()) if isinstance(data, dict) else 'array'
        except:
            is_json = False
            keys = '-'

        print(f'  {endpoint:30s} | {status:3d} | JSON: {is_json:5s} | Keys: {keys}')

        # 如果是JSON且有数据，显示详情
        if is_json and isinstance(data, dict) and data.get('status') is not None:
            print(f'    Status: {data.get("status")}, Msg: {data.get("msg", "")[:50]}')

    except Exception as e:
        print(f'  {endpoint:30s} | ERROR: {str(e)[:50]}')

# 检查学习记录的详细字段
print('\n\n检查学习记录详细字段:')
resp = session.get(f'{BASE_URL}/user/study_record/video',
                   params={'courseId': '1011331', 'page': 1},
                   headers={'X-Requested-With': 'XMLHttpRequest'},
                   timeout=10)

data = resp.json()
if 'list' in data and data['list']:
    video = data['list'][0]
    print('\n视频记录所有字段:')
    for key, value in video.items():
        print(f'  {key:25s}: {value}')

    # 检查是否有IP、设备等字段
    print('\n\n检查是否有隐藏字段:')
    print(f'  Total fields: {len(video)}')

    # 检查是否有嵌套对象
    for key, value in video.items():
        if isinstance(value, (dict, list)):
            print(f'  Nested field: {key} = {type(value).__name__}')

# 检查用户信息
print('\n\n检查用户信息:')
resp = session.get(f'{BASE_URL}/user/info', timeout=10)
try:
    user_info = resp.json()
    print(f'User info keys: {list(user_info.keys())}')
    print(json.dumps(user_info, ensure_ascii=False, indent=2)[:2000])
except:
    print(f'User info response: {resp.text[:500]}')

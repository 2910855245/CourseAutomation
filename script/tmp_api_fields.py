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
            return data
    return None

# Load passwords
with open('script/tmp_passwords.json', 'r', encoding='utf-8') as f:
    enc_passwords = json.load(f)

ocr = ddddocr.DdddOcr(show_ad=False)

# 只测试第一个账号
username = list(enc_passwords.keys())[0]
password = decrypt_password(enc_passwords[username])

print(f'测试账号: {username}')
print(f'获取API完整返回数据...')

data = login_and_fetch(username, password, ocr)
if data:
    print('\nAPI返回的顶层字段:')
    print(list(data.keys()))

    print('\n完整返回数据示例:')
    print(json.dumps(data, ensure_ascii=False, indent=2)[:5000])
else:
    print('登录失败')

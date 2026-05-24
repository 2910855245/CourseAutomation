"""获取考试成绩"""
import sys, os, re, json, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib, base64, httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from config import settings
from bs4 import BeautifulSoup
httpx.packages.urllib3.disable_warnings()

from services.multi_platform_auth import login_single_platform

WEBSITES = {1: 'https://cdcas.suwankj.com', 2: 'https://cdcas.taiskeji.com', 3: 'https://cdcas.chaoxiankeji.com'}
PLATFORM_NAMES = {1: '在线课程', 2: '劳动课程', 3: '公益课程'}


def decrypt_password(stored):
    if not stored: return stored
    key = hashlib.sha256(settings.password_encryption_key.encode()).digest()
    if stored.startswith('ENC2:'):
        try:
            raw = base64.b64decode(stored[5:])
            nonce, ct = raw[:12], raw[12:]
            return AESGCM(key).decrypt(nonce, ct, None).decode('utf-8')
        except: return ''
    if stored.startswith('ENC:'):
        try:
            raw = base64.b64decode(stored[4:])
            return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode('utf-8')
        except: return ''
    return stored


def parse_record_table(html):
    """解析记录表格"""
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')
    records = []
    for table in tables:
        rows = table.find_all('tr')
        headers = []
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            cell_data = [c.get_text(strip=True) for c in cells]
            if not headers:
                # 检查是否是表头
                if any(kw in ''.join(cell_data) for kw in ['名称', '成绩', '得分', '分数', '时间', '状态']):
                    headers = cell_data
                    continue
            if headers and len(cell_data) >= len(headers):
                record = {}
                for j in range(len(headers)):
                    record[headers[j]] = cell_data[j]
                records.append(record)
            elif not headers and len(cell_data) > 1:
                records.append({f'col{i}': v for i, v in enumerate(cell_data)})
    return records


db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'orders.db')
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT DISTINCT username, password, website_id FROM orders WHERE password != ''")
rows = c.fetchall()
conn.close()

seen = set()
accounts = []
for username, enc_pw, wid in rows:
    key = (username, wid)
    if key in seen: continue
    seen.add(key)
    pw = decrypt_password(enc_pw)
    if not pw: continue
    accounts.append((username, pw, wid))

print(f'Total accounts: {len(accounts)}')
all_results = []

for i, (username, password, wid) in enumerate(accounts):
    base = WEBSITES[wid]
    platform = PLATFORM_NAMES.get(wid, f'平台{wid}')

    try:
        result_wid, ok, session, msg = login_single_platform(wid, username, password)
        if not ok:
            print(f'[{i+1}] {username} @ {platform}: 登录失败 - {msg}')
            all_results.append({'username': username, 'platform': platform, 'error': msg})
            continue
    except Exception as e:
        print(f'[{i+1}] {username} @ {platform}: 异常 - {e}')
        all_results.append({'username': username, 'platform': platform, 'error': str(e)})
        continue

    # 获取课程列表和 userId
    resp = session.get(f'{base}/user/index', timeout=15)
    resp.encoding = 'utf-8'
    soup = BeautifulSoup(resp.text, 'html.parser')

    # 从 study_record 链接中提取 userId
    courses = soup.select('div.user-course div.item div.name a')

    acc_result = {
        'username': username,
        'platform': platform,
        'courses': [],
    }

    for cl in courses:
        cname = cl.get_text(strip=True)
        href = cl.get('href', '')
        if not href: continue
        if not href.startswith('http'):
            href = base + href

        # 获取课程详情页
        resp2 = session.get(href, timeout=15)
        resp2.encoding = 'utf-8'
        soup2 = BeautifulSoup(resp2.text, 'html.parser')

        # 提取 courseId 和 userId
        course_id = ''
        user_id = ''
        study_record_url = ''

        for link in soup2.find_all('a', href=True):
            link_href = link.get('href', '')
            if 'study_record' in link_href:
                study_record_url = link_href
                m = re.search(r'courseId=(\d+)', link_href)
                if m: course_id = m.group(1)
                m = re.search(r'userId=(\d+)', link_href)
                if m: user_id = m.group(1)
                break

        if not course_id:
            continue

        course_data = {
            'name': cname,
            'course_id': course_id,
            'exams': [],
            'works': [],
        }

        # 获取考试记录
        for record_type in ['exam', 'work']:
            record_url = f'{base}/user/study_record/{record_type}?courseId={course_id}'
            if user_id:
                record_url += f'&userId={user_id}'

            try:
                resp3 = session.get(record_url, timeout=15)
                resp3.encoding = 'utf-8'
                records = parse_record_table(resp3.text)
                if records:
                    course_data[record_type + 's'] = records
            except Exception:
                pass

        if course_data['exams'] or course_data['works']:
            acc_result['courses'].append(course_data)
            print(f'[{i+1}] {username} @ {platform} - {cname}:')
            for exam in course_data['exams']:
                print(f'    考试: {exam}')
            for work in course_data['works']:
                print(f'    作业: {work}')

    all_results.append(acc_result)

# 汇总
print('\n' + '=' * 80)
print('汇总')
print('=' * 80)

has_scores = 0
no_scores = 0
login_fail = 0

for r in all_results:
    if 'error' in r:
        login_fail += 1
    elif r.get('courses'):
        has_scores += 1
    else:
        no_scores += 1

print(f'有考试成绩: {has_scores}')
print(f'无考试成绩: {no_scores}')
print(f'登录失败: {login_fail}')

with open('exam_scores_report.json', 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
print(f'\n详细结果已保存到 exam_scores_report.json')

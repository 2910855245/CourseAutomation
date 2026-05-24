"""查看考试成绩"""
import sys, os, json, sqlite3, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib, base64, httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from bs4 import BeautifulSoup
httpx.packages.urllib3.disable_warnings()

from config import settings
from services.multi_platform_auth import login_single_platform

WEBSITES = {1: 'https://cdcas.suwankj.com', 2: 'https://cdcas.taiskeji.com', 3: 'https://cdcas.chaoxiankeji.com'}
PLATFORM_NAMES = {1: '在线课程', 2: '劳动课程', 3: '公益课程'}


def decrypt_password(stored):
    if not stored:
        return stored
    key = hashlib.sha256(settings.password_encryption_key.encode()).digest()
    if stored.startswith('ENC2:'):
        try:
            raw = base64.b64decode(stored[5:])
            nonce, ct = raw[:12], raw[12:]
            return AESGCM(key).decrypt(nonce, ct, None).decode('utf-8')
        except:
            return ''
    if stored.startswith('ENC:'):
        try:
            raw = base64.b64decode(stored[4:])
            return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode('utf-8')
        except:
            return ''
    return stored


def get_accounts():
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
        if key in seen:
            continue
        seen.add(key)
        pw = decrypt_password(enc_pw)
        if not pw:
            continue
        accounts.append((username, pw, wid))
    return accounts


def get_exam_scores(session, base_url, course_name, course_href):
    """获取课程的考试成绩"""
    if not course_href.startswith('http'):
        course_href = base_url + course_href

    # 获取课程详情页
    resp = session.get(course_href, timeout=15)
    resp.encoding = 'utf-8'
    soup = BeautifulSoup(resp.text, 'html.parser')

    # 找学习成绩链接
    study_record_url = None
    for link in soup.find_all('a', href=True):
        text = link.get_text(strip=True)
        href = link.get('href', '')
        if '学习成绩' in text or 'study_record' in href:
            if not href.startswith('http'):
                href = base_url + href
            study_record_url = href
            break

    if not study_record_url:
        return None

    # 获取学习成绩页面
    resp2 = session.get(study_record_url, timeout=15)
    resp2.encoding = 'utf-8'
    html = resp2.text
    soup2 = BeautifulSoup(html, 'html.parser')

    # 提取 courseId
    course_id = ''
    m = re.search(r'courseId[=:](\d+)', study_record_url)
    if m:
        course_id = m.group(1)

    # 查找页面中的课程总分
    results = {
        'course_name': course_name,
        'course_id': course_id,
        'progress': '',
        'exams': [],
        'works': [],
    }

    # 学习进度
    progress_el = soup2.find('div', class_='stuelearn-top')
    if progress_el:
        text = progress_el.get_text(strip=True)
        m = re.search(r'(\d+)%', text)
        if m:
            results['progress'] = m.group(1) + '%'

    # 尝试 AJAX 获取考试记录
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    # 考试记录
    if course_id:
        for record_type in ['exam', 'work']:
            try:
                ajax_url = f"{base_url}/user/study_record/{record_type}?courseId={course_id}"
                resp3 = session.get(ajax_url, headers=headers, timeout=15)
                resp3.encoding = 'utf-8'
                html3 = resp3.text

                # 可能返回HTML片段或JSON
                soup3 = BeautifulSoup(html3, 'html.parser')
                tables = soup3.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    headers_row = []
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if cells:
                            cell_data = [c.get_text(strip=True) for c in cells]
                            if not headers_row and any('考试' in d or '作业' in d or '名称' in d or '成绩' in d for d in cell_data):
                                headers_row = cell_data
                            else:
                                record = {}
                                for j, val in enumerate(cell_data):
                                    if j < len(headers_row):
                                        record[headers_row[j]] = val
                                    else:
                                        record[f'col{j}'] = val
                                if record:
                                    if record_type == 'exam':
                                        results['exams'].append(record)
                                    else:
                                        results['works'].append(record)
            except Exception as e:
                pass

    return results


def main():
    accounts = get_accounts()
    print(f"Total accounts: {len(accounts)}")

    all_results = []
    success_count = 0
    fail_count = 0

    for i, (username, password, wid) in enumerate(accounts):
        base = WEBSITES[wid]
        platform = PLATFORM_NAMES.get(wid, f'平台{wid}')
        print(f'\n[{i+1}/{len(accounts)}] {username} @ {platform}')

        try:
            result_wid, ok, session, msg = login_single_platform(wid, username, password)
            if not ok:
                print(f'  登录失败: {msg}')
                fail_count += 1
                all_results.append({'username': username, 'platform': platform, 'error': msg})
                continue
            print(f'  登录成功')
        except Exception as e:
            print(f'  登录异常: {e}')
            fail_count += 1
            all_results.append({'username': username, 'platform': platform, 'error': str(e)})
            continue

        # 获取课程列表
        try:
            resp = session.get(f'{base}/user/index', timeout=15)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'html.parser')
            courses = soup.select('div.user-course div.item div.name a')
        except Exception as e:
            print(f'  获取课程失败: {e}')
            continue

        acc_result = {
            'username': username,
            'platform': platform,
            'courses': [],
        }

        for cl in courses:
            cname = cl.get_text(strip=True)
            href = cl.get('href', '')
            if not href:
                continue

            scores = get_exam_scores(session, base, cname, href)
            if scores:
                acc_result['courses'].append(scores)

                # 打印考试成绩
                exams = scores.get('exams', [])
                works = scores.get('works', [])
                progress = scores.get('progress', '')

                if exams or works:
                    print(f'  {cname} (进度:{progress})')
                    for exam in exams:
                        name = exam.get('考试名称', exam.get('名称', exam.get('col0', '?')))
                        score = exam.get('成绩', exam.get('得分', exam.get('col1', '?')))
                        print(f'    考试: {name} -> {score}分')
                    for work in works:
                        name = work.get('作业名称', work.get('名称', work.get('col0', '?')))
                        score = work.get('成绩', work.get('得分', work.get('col1', '?')))
                        print(f'    作业: {name} -> {score}分')
                else:
                    print(f'  {cname} (进度:{progress}) - 无考试记录')

        success_count += 1
        all_results.append(acc_result)

    # 汇总
    print('\n' + '=' * 80)
    print('汇总')
    print('=' * 80)
    print(f'成功登录: {success_count}')
    print(f'登录失败: {fail_count}')

    # 保存结果
    with open('exam_scores_report.json', 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f'\n详细结果已保存到 exam_scores_report.json')


if __name__ == '__main__':
    main()

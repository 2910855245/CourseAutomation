"""查找考试成绩API"""
import sys, os, re, json, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib, base64, httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from config import settings
from bs4 import BeautifulSoup
httpx.packages.urllib3.disable_warnings()

from services.multi_platform_auth import login_single_platform


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

for username, password, wid in accounts:
    base = 'https://cdcas.taiskeji.com' if wid == 2 else 'https://cdcas.suwankj.com'
    try:
        result_wid, ok, session, msg = login_single_platform(wid, username, password)
        if not ok: continue
    except: continue

    resp = session.get(f'{base}/user/index', timeout=15)
    resp.encoding = 'utf-8'
    soup = BeautifulSoup(resp.text, 'html.parser')
    courses = soup.select('div.user-course div.item div.name a')

    for cl in courses:
        name = cl.get_text(strip=True)
        href = cl.get('href', '')
        if not href: continue
        if not href.startswith('http'):
            href = base + href

        resp2 = session.get(href, timeout=15)
        resp2.encoding = 'utf-8'
        soup2 = BeautifulSoup(resp2.text, 'html.parser')

        for link in soup2.find_all('a', href=True):
            text = link.get_text(strip=True)
            lhref = link.get('href', '')
            if 'study_record' in lhref:
                if not lhref.startswith('http'):
                    lhref = base + lhref

                resp3 = session.get(lhref, timeout=15)
                resp3.encoding = 'utf-8'
                html = resp3.text

                # Save full HTML for analysis
                with open('/tmp/score_page.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f'Saved score page HTML for {name}')

                # Find all script content
                scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
                for i, script in enumerate(scripts):
                    if len(script.strip()) > 10:
                        print(f'\n--- Script {i} ({len(script)} chars) ---')
                        # Print lines with URL patterns
                        for line in script.split('\n'):
                            line = line.strip()
                            if line and any(kw in line.lower() for kw in ['url', 'ajax', 'fetch', 'get', 'post', 'exam', 'work', 'record', 'score']):
                                print(f'  {line[:200]}')

                # Find all onclick handlers
                onclicks = soup2.find_all(attrs={'onclick': True})
                for el in onclicks:
                    print(f'ONCLICK: {el.get("onclick")[:200]}')

                # Find all data-* attributes
                for el in soup2.find_all(True):
                    for attr, val in el.attrs.items():
                        if attr.startswith('data-') and any(kw in str(val).lower() for kw in ['exam', 'work', 'record', 'score']):
                            print(f'DATA: {attr}={val}')

                break
        break
    break

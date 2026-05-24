import sqlite3, json, sys, os, httpx, hashlib, base64
sys.stdout.reconfigure(encoding='utf-8')
httpx.packages.urllib3.disable_warnings()

ENCRYPTION_KEY = "change-me-encryption-key-32bytes!"
BASE_URL = "https://cdcas.taiskeji.com"

def decrypt_password(stored):
    if not stored or not stored.startswith("ENC:"):
        return stored
    try:
        raw = base64.b64decode(stored[4:])
        derived = hashlib.sha256(ENCRYPTION_KEY.encode()).digest()
        return bytes(b ^ derived[i % len(derived)] for i, b in enumerate(raw)).decode("utf-8")
    except:
        return stored

# Get one account
conn = sqlite3.connect("/www/wwwroot/anti_course/data/orders.db")
c = conn.cursor()
c.execute("SELECT DISTINCT username, password FROM orders WHERE website_id = 2 AND password != '' LIMIT 1")
row = c.fetchone()
conn.close()

username, enc_password = row
password = decrypt_password(enc_password)
print(f"Username: {username}")
print(f"Encrypted: {enc_password}")
print(f"Decrypted: {password}")

session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
})

# Get login page first
resp1 = session.get(f"{BASE_URL}/user/login", timeout=10)
print(f"\nLogin page: {resp1.status_code}")
print(f"Cookies after login page: {list(session.cookies.keys())}")

# Try login
resp2 = session.post(f"{BASE_URL}/user/login", data={
    'username': username,
    'password': password,
}, follow_redirects=False, timeout=10)
print(f"\nLogin POST: {resp2.status_code}")
print(f"Location: {resp2.headers.get('Location', 'N/A')}")
print(f"Response: {resp2.text[:500]}")

# Follow redirect
if resp2.status_code == 302:
    resp3 = session.get(resp2.headers['Location'], timeout=10)
    print(f"\nRedirect: {resp3.status_code}")
    print(f"Has '退出登录': {'退出登录' in resp3.text}")

# Try JSON login
resp4 = session.post(f"{BASE_URL}/user/login", json={
    'username': username,
    'password': password,
}, timeout=10)
print(f"\nJSON login: {resp4.status_code}")
print(f"Response: {resp4.text[:500]}")

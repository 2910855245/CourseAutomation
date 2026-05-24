import json, sys, hashlib, base64
sys.stdout.reconfigure(encoding='utf-8')

import ddddocr
from scrapling import Fetcher

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

# Load passwords
with open('script/tmp_passwords.json', 'r', encoding='utf-8') as f:
    enc_passwords = json.load(f)

print(f"Loaded {len(enc_passwords)} accounts")

ocr = ddddocr.DdddOcr(show_ad=False)
fetcher = Fetcher(auto_match=False)
results = {}

for username in list(enc_passwords.keys()):
    password = decrypt_password(enc_passwords[username])
    print(f"\n{'='*60}")
    print(f"Account: {username}")
    print(f"{'='*60}")

    try:
        # 1. Get login page
        login_page = fetcher.get(f"{BASE_URL}/user/login", stealthy_headers=True)
        session_cookies = {}
        for c in login_page.cookies:
            session_cookies[c] = login_page.cookies[c]

        # 2. Get captcha
        captcha_resp = fetcher.get(f"{BASE_URL}/service/code", cookies=session_cookies, stealthy_headers=True)
        captcha_bytes = captcha_resp.body if hasattr(captcha_resp, 'body') else b''
        if not captcha_bytes:
            captcha_bytes = captcha_resp.text.encode('latin-1') if captcha_resp.text else b''

        # 3. OCR captcha
        code = ocr.classification(captcha_bytes)
        print(f"  Captcha: {code}")

        # 4. Login
        all_cookies = dict(session_cookies)
        login_resp = fetcher.post(
            f"{BASE_URL}/user/login",
            data={
                'username': username,
                'password': password,
                'code': code,
                'redirect': '',
                'remember': 'on',
            },
            cookies=all_cookies,
            stealthy_headers=True,
            follow_redirects=True,
        )
        print(f"  Login status: {login_resp.status}")

        # Merge cookies from login response
        if hasattr(login_resp, 'cookies') and login_resp.cookies:
            for c in login_resp.cookies:
                all_cookies[c] = login_resp.cookies[c]

        # Check login
        has_logout = '退出登录' in login_resp.text
        if not has_logout:
            # Try to find error message
            if '验证码' in login_resp.text or 'code' in login_resp.text.lower():
                print(f"  Captcha error, retrying...")
            else:
                print(f"  Login failed")
            continue

        print(f"  Login SUCCESS")

        # 5. Fetch video records
        video_resp = fetcher.get(
            f"{BASE_URL}/user/study_record/video",
            params={"courseId": "1011331", "page": "1"},
            cookies=all_cookies,
            stealthy_headers=True,
        )

        try:
            data = json.loads(video_resp.text)
            videos = data.get("list", [])
            print(f"  Videos: {len(videos)}")

            if not videos:
                continue

            from datetime import datetime
            completed = []
            for v in videos:
                ft = v.get("finalTime", "")
                if ft and ft != "-":
                    completed.append({
                        "name": v.get("name", ""),
                        "final_time": ft,
                        "begin_time": v.get("beginTime", ""),
                        "progress": v.get("progress", "0"),
                        "view_count": v.get("viewCount", "0"),
                        "video_duration": v.get("videoDuration", ""),
                        "viewed_duration": v.get("viewedDuration", ""),
                    })

            completed.sort(key=lambda x: x["final_time"])
            print(f"  Completed: {len(completed)}")

            print(f"\n  Completion timeline:")
            for i, v in enumerate(completed):
                print(f"    [{i+1:2d}] {v['final_time']:20s} | {v['name'][:35]:35s} | progress:{v['progress']} | views:{v['view_count']}")

            print(f"\n  Parallel brushing detection (<60s gap):")
            parallel_count = 0
            for i in range(1, len(completed)):
                try:
                    t1 = completed[i-1]["final_time"]
                    t2 = completed[i]["final_time"]
                    dt1 = datetime.strptime(f"2026-{t1}", "%Y-%m-%d %H:%M:%S")
                    dt2 = datetime.strptime(f"2026-{t2}", "%Y-%m-%d %H:%M:%S")
                    diff = abs((dt2 - dt1).total_seconds())
                    if diff < 60:
                        parallel_count += 1
                        print(f"    !!! {completed[i-1]['name'][:25]:25s} -> {completed[i]['name'][:25]:25s} | gap: {diff:.0f}s")
                except:
                    pass
            if parallel_count == 0:
                print(f"    No parallel brushing detected")
            else:
                print(f"    DETECTED {parallel_count} parallel brushing instances!")

            results[username] = {
                "total": len(videos),
                "completed": len(completed),
                "videos": completed,
                "parallel_count": parallel_count,
            }

        except json.JSONDecodeError:
            print(f"  Not JSON: {video_resp.text[:200]}")

    except Exception as e:
        import traceback
        print(f"  Error: {e}")
        traceback.print_exc()

# Save results
with open('script/tmp_parallel_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\n\nResults saved to script/tmp_parallel_analysis.json")
print(f"Total accounts analyzed: {len(results)}")

import httpx, sys, re
sys.stdout.reconfigure(encoding='utf-8')
httpx.packages.urllib3.disable_warnings()

BASE_URL = "https://cdcas.taiskeji.com"

session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
})

resp = session.get(f"{BASE_URL}/user/login", timeout=10)
print(f"Status: {resp.status_code}")

# Find form fields
inputs = re.findall(r'<input[^>]*name=["\']([^"\']+)["\'][^>]*>', resp.text)
print(f"Form fields: {inputs}")

# Find form action
forms = re.findall(r'<form[^>]*action=["\']([^"\']+)["\'][^>]*>', resp.text)
print(f"Form actions: {forms}")

# Show relevant HTML section
login_section = re.search(r'<form[^>]*login[^>]*>.*?</form>', resp.text, re.DOTALL | re.IGNORECASE)
if login_section:
    print(f"\nLogin form HTML:")
    print(login_section.group(0)[:1000])
else:
    # Try to find any form
    form_section = re.search(r'<form[^>]*>.*?</form>', resp.text, re.DOTALL)
    if form_section:
        print(f"\nForm HTML:")
        print(form_section.group(0)[:1000])
    else:
        # Show raw HTML around "login" or "password"
        for keyword in ['login', 'password', 'submit', '登录', '密码']:
            idx = resp.text.find(keyword)
            if idx >= 0:
                print(f"\nAround '{keyword}':")
                print(resp.text[max(0,idx-200):idx+200])
                break

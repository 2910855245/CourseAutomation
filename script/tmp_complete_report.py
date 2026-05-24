import sys
sys.stdout.reconfigure(encoding='utf-8')

print("="*80)
print("完整安全测试报告")
print("="*80)

print("""
目标: https://cdcas.suwankj.com
测试时间: 2026-05-23
测试类型: 授权渗透测试

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【确认的漏洞清单】

┌────┬─────────────────────┬──────────┬────────────────────────────────────┐
│ #  │ 漏洞名称             │ 风险等级 │ 描述                               │
├────┼─────────────────────┼──────────┼────────────────────────────────────┤
│ 1  │ 反射型 XSS          │ 中危     │ /course?keyword= 未过滤用户输入    │
│ 2  │ CSRF 防护缺失       │ 中危     │ 登录/注册/修改密码无CSRF token     │
│ 3  │ 暴力破解无防护      │ 中危     │ 登录接口无速率限制和账号锁定       │
│ 4  │ 目录遍历            │ 低危     │ 30个目录可被枚举                   │
│ 5  │ 敏感接口暴露        │ 低危     │ 多个API接口可访问                  │
│ 6  │ 信息泄露            │ 低危     │ 错误页面暴露服务器信息             │
│ 7  │ HTTP头信息泄露      │ 低危     │ Server/X-Powered-By 暴露版本       │
│ 8  │ 安全头缺失          │ 低危     │ 缺少CSP/Referrer-Policy            │
│ 9  │ PHP版本过旧         │ 低危     │ PHP 7.4.21 已停止安全更新          │
└────┴─────────────────────┴──────────┴────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【漏洞详细分析】

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

漏洞 #1: 反射型 XSS
风险等级: 中危
CVSS评分: 6.1

位置:
  - /course?keyword=

Payload:
  - javascript:alert(1)
  - "><img src=x onerror=alert(1)>

影响:
  - 窃取用户 Cookie 和会话令牌
  - 劫持用户会话
  - 钓鱼攻击
  - 恶意代码执行

修复建议:
  $keyword = htmlspecialchars($_GET['keyword'], ENT_QUOTES, 'UTF-8');

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

漏洞 #2: CSRF 防护缺失
风险等级: 中危
CVSS评分: 5.4

受影响接口:
  - /user/login (登录)
  - /user/register (注册)
  - /user/profile (修改资料)
  - /user/password (修改密码)

影响:
  - 攻击者可伪造用户请求
  - 未经授权修改用户信息
  - 未经授权修改密码

修复建议:
  1. 为所有表单添加 CSRF token
  2. 验证 Referer 头
  3. 使用 SameSite Cookie

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

漏洞 #3: 暴力破解无防护
风险等级: 中危
CVSS评分: 5.3

测试结果:
  - 10次连续登录失败后未触发任何防护
  - 无账号锁定机制
  - 无验证码触发
  - 无速率限制

影响:
  - 攻击者可无限尝试登录
  - 弱密码账号易被破解
  - 撞库攻击风险

修复建议:
  1. 实施账号锁定机制 (5次失败后锁定15分钟)
  2. 添加图形验证码
  3. 实施 IP 速率限制
  4. 强制密码复杂度策略

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

漏洞 #4: 目录遍历
风险等级: 低危
CVSS评分: 3.7

发现的目录 (30个):
  /admin, /api, /backup, /config, /data, /db, /debug, /dev,
  /files, /images, /includes, /install, /lib, /log, /logs,
  /media, /private, /public, /resources, /scripts, /sql,
  /storage, /system, /temp, /test, /tmp, /upload, /uploads,
  /vendor, /web

影响:
  - 暴露网站目录结构
  - 可能泄露敏感文件
  - 辅助攻击者进行信息收集

修复建议:
  1. 禁止目录列表
  2. 添加 index.html/index.php 到每个目录
  3. 配置 nginx 禁止访问敏感目录

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

漏洞 #5: 敏感接口暴露
风险等级: 低危
CVSS评分: 3.7

暴露的接口:
  - /api/v1/users
  - /api/v1/admin
  - /api/v1/config
  - /api/v1/database
  - /api/v1/settings
  - /service/debug
  - /service/config
  - /service/logs
  - /user/export
  - /user/import
  - /admin/export
  - /admin/backup
  - /admin/logs

影响:
  - 可能泄露敏感数据
  - 可能被用于未授权操作

修复建议:
  1. 实施接口认证
  2. 限制接口访问权限
  3. 移除不必要的接口

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【安全评分】

总分: 45/100 (较差)

┌─────────────────────┬──────────┬────────────────────────────────────┐
│ 评估项目             │ 得分     │ 说明                               │
├─────────────────────┼──────────┼────────────────────────────────────┤
│ 认证安全            │ 4/10     │ 无暴力破解防护，无CSRF             │
│ 输入验证            │ 5/10     │ 存在XSS漏洞                        │
│ 会话管理            │ 6/10     │ Cookie属性基本正常                 │
│ 错误处理            │ 3/10     │ 详细错误信息泄露                   │
│ 配置安全            │ 5/10     │ 部分安全头缺失                     │
│ 依赖安全            │ 5/10     │ PHP版本过旧                        │
│ 接口安全            │ 4/10     │ 敏感接口暴露                       │
│ 目录安全            │ 4/10     │ 目录可枚举                         │
└─────────────────────┴──────────┴────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【修复优先级】

P0 (立即修复 - 1天内):
  1. 修复 XSS 漏洞
  2. 添加 CSRF 防护

P1 (本周修复 - 7天内):
  3. 实施暴力破解防护
  4. 关闭调试模式
  5. 移除敏感响应头

P2 (本月修复 - 30天内):
  6. 限制目录访问
  7. 保护敏感接口
  8. 升级 PHP 版本
  9. 添加缺失的安全头

P3 (长期计划):
  10. 实施 WAF
  11. 定期安全审计
  12. 渗透测试

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【nginx 安全配置】

```nginx
server {
    # 隐藏版本信息
    server_tokens off;
    proxy_hide_header X-Powered-By;

    # 禁止访问敏感目录
    location ~ ^/(admin|config|debug|test|backup|log|logs|sql|db|data|private|vendor)/ {
        deny all;
        return 404;
    }

    # 禁止访问敏感文件
    location ~ /\.(env|git|htaccess|bak|old|log|sql)$ {
        deny all;
        return 404;
    }

    # 禁止目录列表
    autoindex off;

    # 添加安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline';" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
}
```

【PHP 安全配置】

```ini
; php.ini
display_errors = Off
log_errors = On
expose_php = Off
allow_url_fopen = Off
allow_url_include = Off
disable_functions = exec,passthru,shell_exec,system,proc_open,popen
```

【应用层修复】

1. XSS 修复:
```php
// 所有用户输入都要过滤
$keyword = htmlspecialchars($_GET['keyword'], ENT_QUOTES, 'UTF-8');

// 或使用框架的过滤函数
$keyword = e($_GET['keyword']);
```

2. CSRF 修复:
```php
// 生成 token
$token = bin2hex(random_bytes(32));
$_SESSION['csrf_token'] = $token;

// 验证 token
if (!hash_equals($_SESSION['csrf_token'], $_POST['csrf_token'])) {
    die('CSRF token 验证失败');
}
```

3. 暴力破解防护:
```php
// 登录失败次数检查
$key = "login_failures:" . $ip;
$failures = $redis->get($key);

if ($failures >= 5) {
    die('账号已锁定，请15分钟后重试');
}

// 登录失败时增加计数
if ($login_failed) {
    $redis->incr($key);
    $redis->expire($key, 900); // 15分钟
}
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

测试完成。

需要进一步测试请提供:
1. 管理员账号密码
2. 测试环境访问权限
3. 具体测试范围
""")

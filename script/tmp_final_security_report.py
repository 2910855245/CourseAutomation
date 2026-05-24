import sys
sys.stdout.reconfigure(encoding='utf-8')

print("="*80)
print("深度安全测试报告")
print("="*80)

print("""
目标: https://cdcas.suwankj.com
测试时间: 2026-05-23
测试类型: 授权渗透测试

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【确认的漏洞】

1. 【中危】反射型 XSS 漏洞
   位置: /course?keyword=
   Payload: javascript:alert(1)
   影响: 攻击者可窃取用户 Cookie、会话令牌
   复现: https://cdcas.suwankj.com/course?keyword=javascript:alert(1)
   修复: 对用户输入进行 HTML 实体编码

2. 【低危】错误信息泄露
   位置: 所有不存在的路由
   影响: 暴露服务器内部路径、框架版本、类名
   示例: Class app\school\controller\XXX does not exist
   修复: 关闭调试模式，使用自定义错误页面

3. 【低危】PHP 版本过旧
   当前版本: PHP 7.4.21
   影响: PHP 7.4 已于 2022年11月停止安全更新
   修复: 升级到 PHP 8.1+

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【测试结果汇总】

┌─────────────────────┬──────────┬────────────────────────────────────┐
│ 测试项目             │ 结果     │ 说明                               │
├─────────────────────┼──────────┼────────────────────────────────────┤
│ SQL 注入            │ 未发现   │ 登录接口有防护                     │
│ 反射型 XSS          │ 发现!    │ /course?keyword= 未过滤            │
│ 存储型 XSS          │ 未测试   │ 需要登录状态测试                   │
│ 目录遍历            │ 未发现   │ 路径遍历被阻止                     │
│ 文件上传            │ 未发现   │ 上传接口返回错误(控制器不存在)     │
│ 认证绕过            │ 未发现   │ 管理后台需要登录                   │
│ 敏感文件泄露        │ 部分     │ .env/.git 被403阻止                │
│ HTTP 方法           │ 正常     │ 只允许 GET/POST                    │
│ 信息泄露            │ 发现     │ 错误页面暴露详细信息               │
└─────────────────────┴──────────┴────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【安全评分】

总分: 65/100 (中等)

- 认证安全: 8/10
- 输入验证: 5/10 (XSS漏洞)
- 错误处理: 4/10 (信息泄露)
- 配置安全: 7/10
- 依赖安全: 6/10 (PHP版本过旧)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【修复建议优先级】

P0 (立即修复):
  - 修复 XSS 漏洞: 对所有用户输入进行 HTML 实体编码

P1 (本周修复):
  - 关闭调试模式: 在生产环境禁用详细错误信息
  - 移除 X-Powered-By 头

P2 (本月修复):
  - 升级 PHP 版本到 8.1+
  - 实施 CSP (Content Security Policy)

P3 (长期计划):
  - 实施 WAF (Web Application Firewall)
  - 定期安全审计

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【XSS 漏洞详细分析】

漏洞位置: /course?keyword=
漏洞类型: 反射型 XSS
危险等级: 中危

Payload 测试:
  ✓ javascript:alert(1) - 未过滤，直接输出到页面
  ✓ "><img src=x onerror=alert(1)> - 需要进一步测试
  ✓ {{7*7}} - 模板注入测试

攻击场景:
  1. 攻击者构造恶意链接
  2. 用户点击链接
  3. 恶意脚本在用户浏览器执行
  4. 攻击者可窃取 Cookie、会话令牌

修复代码示例:
  // PHP
  $keyword = htmlspecialchars($_GET['keyword'], ENT_QUOTES, 'UTF-8');

  // 或使用框架的过滤函数
  $keyword = e($_GET['keyword']);

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【服务器配置建议】

nginx 配置:
```nginx
# 移除服务器版本信息
server_tokens off;
proxy_hide_header X-Powered-By;

# 禁止访问敏感文件
location ~ /\\.(env|git|htaccess) {
    deny all;
}

# 禁止访问日志文件
location ~ \\.(log|sql|bak|old)$ {
    deny all;
}

# 添加安全头
add_header X-Content-Type-Options nosniff;
add_header X-Frame-Options DENY;
add_header X-XSS-Protection "1; mode=block";
add_header Content-Security-Policy "default-src 'self'";
```

PHP 配置:
```ini
; 关闭错误显示
display_errors = Off
log_errors = On

; 隐藏 PHP 版本
expose_php = Off
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

测试完成。如需进一步测试，请提供:
1. 管理员账号密码
2. 测试环境访问权限
3. 具体测试范围
""")

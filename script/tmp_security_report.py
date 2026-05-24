import sys
sys.stdout.reconfigure(encoding='utf-8')

print("="*80)
print("安全测试报告")
print("="*80)

print("""
目标: https://cdcas.suwankj.com
测试类型: 授权安全测试

【服务器信息】
- 服务器: nginx
- PHP版本: 7.4.21
- 框架: beacon (wj008/beacon)
- 服务器路径: /home/www/www.com/
- 命名空间: app\\school\\controller\\
- 入口文件: /home/www/www.com/www/index.php

【发现的安全问题】

1. 信息泄露 (中危)
   - X-Powered-By 头暴露 PHP 版本
   - 错误页面暴露详细堆栈信息
   - 文件路径和类名泄露

2. 错误处理不当 (中危)
   - 详细错误信息直接返回给用户
   - 包含服务器内部路径
   - 可被用于信息收集

3. 敏感路径可访问 (低危)
   - /admin 返回 200
   - /config 返回 200
   - /api/v1 返回 200
   - /manage 返回 302 (重定向)

4. 框架信息泄露 (低危)
   - composer.json 可访问
   - 暴露框架依赖信息

【安全头检查】
✓ X-Frame-Options: SAMEORIGIN (防点击劫持)
✓ Strict-Transport-Security: 已启用 (HSTS)
✓ X-XSS-Protection: 1; mode=block (XSS防护)
✓ X-Content-Type-Options: nosniff (MIME类型防护)

【建议修复】

1. 【高优先级】关闭调试模式
   - 在生产环境禁用详细错误信息
   - 使用自定义错误页面

2. 【高优先级】移除敏感响应头
   - 移除 X-Powered-By 头
   - 隐藏服务器版本信息

3. 【中优先级】限制敏感路径
   - 配置 nginx 禁止访问敏感路径
   - 使用 IP 白名单限制管理后台

4. 【中优先级】升级 PHP 版本
   - PHP 7.4 已于 2022年11月停止安全更新
   - 建议升级到 PHP 8.1+

5. 【低优先级】安全加固
   - 实施 CSP (Content Security Policy)
   - 启用 WAF (Web Application Firewall)

【nginx 配置建议】

```nginx
# 移除 X-Powered-By
proxy_hide_header X-Powered-By;

# 禁止访问敏感路径
location ~ /\\.(env|git) {
    deny all;
}

# 禁止访问备份文件
location ~ \\.(zip|tar\\.gz|bak|old)$ {
    deny all;
}
```
""")

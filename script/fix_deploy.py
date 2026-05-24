#!/usr/bin/env python3
"""修复部署脚本 — 恢复 /assets/ 路径，上传静态文件"""
import os, sys

sys.path.insert(0, os.path.dirname(__file__))
from remote import run, upload

PROJECT_ROOT = "/www/wwwroot/anti_course"
LOCAL_STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

def fix_nginx():
    """修复 nginx 配置：移除错误的 /assets/ 重定向"""
    print("[1/4] 修复 nginx 配置...")

    conf_path = "/www/server/panel/vhost/nginx/shuakecdcas.top.conf"
    out, _ = run(f"cat {conf_path}")

    # 删除 /v2/ location 块
    import re
    # 移除 # New asset path (v2) 块
    out = re.sub(r'\s*# New asset path \(v2\).*?location /v2/ \{[^}]*\}', '', out, flags=re.DOTALL)
    # 移除 /static/assets/ 重定向
    out = re.sub(r'\s*# Redirect old /static/assets/ paths.*?location /static/assets/ \{[^}]*\}', '', out, flags=re.DOTALL)
    # 移除 /assets/ 重定向
    out = re.sub(r'\s*# Redirect old /assets/ paths.*?location /assets/ \{[^}]*\}', '', out, flags=re.DOTALL)

    # 写回
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "nginx_fix.conf")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(out)
    upload(tmp, conf_path)

    # 测试并重载
    out, err = run("nginx -t 2>&1")
    print(f"  nginx -t: {out.strip()}")
    run("nginx -s reload 2>&1")
    print("  nginx reloaded")


def upload_static():
    """上传静态文件"""
    print("[2/4] 上传静态文件...")

    # 上传 index.html
    upload(os.path.join(LOCAL_STATIC, "index.html"), f"{PROJECT_ROOT}/static/index.html")
    print("  index.html")

    # 上传 assets/ 目录
    assets_dir = os.path.join(LOCAL_STATIC, "assets")
    if os.path.isdir(assets_dir):
        run(f"mkdir -p {PROJECT_ROOT}/static/assets")
        for f in os.listdir(assets_dir):
            local = os.path.join(assets_dir, f)
            if os.path.isfile(local):
                upload(local, f"{PROJECT_ROOT}/static/assets/{f}")
                print(f"  assets/{f}")

    # 清理旧的 v2/v3 目录
    run(f"rm -rf {PROJECT_ROOT}/static/v2 {PROJECT_ROOT}/static/v3 2>/dev/null")
    print("  cleaned v2/v3 dirs")


def verify():
    """验证部署"""
    print("[3/4] 验证部署...")

    import time
    time.sleep(2)

    # 检查 index.html
    out, _ = run(f"cat {PROJECT_ROOT}/static/index.html")
    if "/assets/" in out:
        print("  index.html: OK (references /assets/)")
    else:
        print("  index.html: FAIL (no /assets/ reference)")
        return False

    # 检查 assets 目录
    out, _ = run(f"ls {PROJECT_ROOT}/static/assets/*.js 2>/dev/null | wc -l")
    count = int(out.strip())
    print(f"  assets/: {count} JS files")
    if count < 5:
        print("  WARNING: too few JS files!")
        return False

    # 测试 HTTP
    out, _ = run("curl -sI http://127.0.0.1:8000/assets/index-*.js 2>/dev/null | head -1")
    print(f"  HTTP test: {out.strip()}")

    return True


if __name__ == "__main__":
    try:
        from remote import connect
        connect()
        print("已连接到服务器\n")
    except Exception as e:
        print(f"连接失败: {e}")
        sys.exit(1)

    fix_nginx()
    upload_static()
    if verify():
        print("\n[4/4] 部署完成! 请访问 https://shuakecdcas.top/#/admin 验证")
    else:
        print("\n[4/4] 部署可能有问题，请检查")

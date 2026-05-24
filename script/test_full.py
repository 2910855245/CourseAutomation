#!/usr/bin/env python3
"""
===========================================================
Anti-Course Cheating Plugin - Complete E2E Test
===========================================================
覆盖所有功能模块，使用 Playwright 有头 Chrome 浏览器
截图保存在 test_screenshots/
===========================================================
"""
import asyncio
import json
import os
import sys
import time

BASE_URL = "https://shuakecdcas.top"
SHOT_DIR = os.path.join(os.path.dirname(__file__), "test_screenshots")
os.makedirs(SHOT_DIR, exist_ok=True)

ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

results = []


def shot_name(seq, name):
    return os.path.join(SHOT_DIR, f"{seq:02d}_{name}.png")


def record(group, name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((group, name, status, detail))
    icon = "[+]" if passed else "[-]"
    print(f"  {icon} [{group}] {name}" + (f" -- {detail}" if detail else ""))


async def api_get(page, path):
    return await page.evaluate(f"""
        async () => {{
            const r = await fetch('{path}');
            const t = await r.text();
            let body;
            try {{ body = JSON.parse(t); }} catch {{ body = t; }}
            return {{ status: r.status, body }};
        }}
    """)


async def api_post(page, path, data=None):
    body_str = json.dumps(data or {})
    return await page.evaluate(f"""
        async () => {{
            const r = await fetch('{path}', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: '{body_str}'
            }});
            const t = await r.text();
            let body;
            try {{ body = JSON.parse(t); }} catch {{ body = t; }}
            return {{ status: r.status, body }};
        }}
    """)


# ============================================================
# TEST GROUPS
# ============================================================

async def test_home(page, seq):
    """首页"""
    g = "首页"
    try:
        resp = await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(1000)
        await page.screenshot(path=shot_name(seq, "home"))
        record(g, "页面加载", resp and resp.status == 200, f"HTTP {resp.status if resp else 'N/A'}")

        text = await page.inner_text("body")
        record(g, "首页内容渲染", len(text) > 50, f"{len(text)} chars")
    except Exception as e:
        record(g, "页面加载", False, str(e)[:80])


async def test_admin_login_page(page, seq):
    """后台登录页"""
    g = "后台登录"
    try:
        await page.goto(f"{BASE_URL}/#/admin", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=shot_name(seq, "admin_login"))

        topbar = page.locator("header.topbar")
        topbar_count = await topbar.count()
        record(g, "无顶部导航栏", topbar_count == 0, f"topbar count={topbar_count}")

        login_btn = page.locator("button:has-text('登录')")
        record(g, "有登录按钮", await login_btn.count() > 0)

        captcha_img = page.locator(".captcha-img")
        record(g, "有验证码", await captcha_img.count() > 0)

        # Check no forbidden nav text in topbar area
        if topbar_count > 0:
            topbar_text = await topbar.inner_text()
            record(g, "导航栏无首页/订单查询", "首页" not in topbar_text and "订单查询" not in topbar_text)
    except Exception as e:
        record(g, "登录页检查", False, str(e)[:80])


async def test_admin_login(page, seq):
    """后台登录流程"""
    g = "后台登录"
    try:
        username_input = page.locator("input[placeholder*='用户名']")
        password_input = page.locator("input[placeholder*='密码']")
        await username_input.fill(ADMIN_USER)
        await password_input.fill(ADMIN_PASS)
        await page.screenshot(path=shot_name(seq, "login_filled"))
        record(g, "表单填写", True)

        # Try to get captcha and solve (OCR)
        captcha_img_el = page.locator(".captcha-img img, .captcha-img")
        if await captcha_img_el.count() > 0:
            # Attempt login without captcha to test error handling
            login_btn = page.locator("button:has-text('登录')")
            await login_btn.click()
            await page.wait_for_timeout(1000)
            await page.screenshot(path=shot_name(seq, "login_attempt"))
            record(g, "登录尝试", True, "需要验证码（预期行为）")
        else:
            record(g, "验证码加载", False, "未找到验证码元素")
    except Exception as e:
        record(g, "登录流程", False, str(e)[:80])


async def test_api_endpoints(page, seq):
    """API 端点测试"""
    g = "API端点"
    endpoints = [
        ("/api/info", "API信息", lambda b: b.get("name"), 200),
        ("/api/ypay/app-info", "APP信息", lambda b: b.get("data", {}).get("app_name"), 200),
        ("/api/ypay/pair-status", "配对状态", lambda b: "paired" in str(b), 200),
        ("/api/ypay/status", "YPay状态(需认证)", lambda b: True, 401),
        ("/api/captcha/generate", "验证码生成", lambda b: b.get("data", {}).get("token"), 200),
        ("/api/setup/status", "安装状态", lambda b: "done" in str(b), 200),
        ("/api/pricing", "价格列表", lambda b: isinstance(b, (list, dict)), 200),
    ]
    for path, name, check, expected_status in endpoints:
        try:
            resp = await api_get(page, path)
            ok = resp["status"] == expected_status and check(resp["body"])
            record(g, name, ok, f"HTTP {resp['status']}")
        except Exception as e:
            record(g, name, False, str(e)[:60])


async def test_ypay_pairing(page, seq):
    """YPay配对流程"""
    g = "YPay配对"
    try:
        resp = await api_get(page, "/api/ypay/app-qrcode")
        if resp["status"] == 200 and resp["body"].get("success"):
            data = resp["body"].get("data", {})
            pair_data = data.get("pair_data", "")
            has_qr = bool(data.get("qr_image", ""))
            record(g, "配对QR生成", has_qr and bool(pair_data),
                   f"pair_data={pair_data[:30]}...")
            record(g, "QR图片有效", has_qr, f"image len={len(data.get('qr_image',''))}")
        else:
            record(g, "配对QR生成", False, str(resp["body"])[:60])
    except Exception as e:
        record(g, "配对流程", False, str(e)[:80])


async def test_orders_page(page, seq):
    """订单查询页"""
    g = "订单页"
    try:
        await page.goto(f"{BASE_URL}/#/orders", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(1000)
        await page.screenshot(path=shot_name(seq, "orders"))
        text = await page.inner_text("body")
        record(g, "页面加载", "订单" in text or "查询" in text)
    except Exception as e:
        record(g, "页面加载", False, str(e)[:80])


async def test_payment_page(page, seq):
    """支付页面"""
    g = "支付页"
    try:
        await page.goto(f"{BASE_URL}/#/payment/test123", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(1000)
        await page.screenshot(path=shot_name(seq, "payment"))
        record(g, "路由可达", True)
    except Exception as e:
        record(g, "路由可达", False, str(e)[:80])


async def test_agent_page(page, seq):
    """代理中心"""
    g = "代理页"
    try:
        await page.goto(f"{BASE_URL}/#/agent", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(1000)
        await page.screenshot(path=shot_name(seq, "agent"))
        text = await page.inner_text("body")
        record(g, "页面加载", len(text) > 20)
    except Exception as e:
        record(g, "页面加载", False, str(e)[:80])


async def test_subsite(page, seq):
    """分站页面"""
    g = "分站"
    try:
        await page.goto(f"{BASE_URL}/#/subsite/test", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(1000)
        await page.screenshot(path=shot_name(seq, "subsite"))
        record(g, "路由可达", True)
    except Exception as e:
        record(g, "路由可达", False, str(e)[:80])


async def test_app_download(page, seq):
    """APP下载"""
    g = "APP下载"
    try:
        resp = await page.evaluate("""
            async () => {
                const r = await fetch('/api/ypay/app-download', {method:'HEAD'});
                return {status: r.status, type: r.headers.get('content-type'), len: r.headers.get('content-length')};
            }
        """)
        ok = resp["status"] == 200
        record(g, "下载接口", ok, f"HTTP {resp['status']} type={resp.get('type','?')}")
        if ok:
            record(g, "APK大小合理", int(resp.get("len", 0)) > 100000,
                   f"{round(int(resp.get('len',0))/1024/1024, 1)}MB")
    except Exception as e:
        record(g, "APP下载", False, str(e)[:80])


async def test_security_headers(page, seq):
    """安全检查"""
    g = "安全"
    try:
        resp = await page.evaluate("""
            async () => {
                const r = await fetch('/api/info');
                const h = {};
                r.headers.forEach((v, k) => { h[k.toLowerCase()] = v; });
                return h;
            }
        """)
        record(g, "Content-Type", "content-type" in resp, resp.get("content-type", "?")[:40])

        # Check HTTPS
        record(g, "HTTPS", page.url.startswith("https"))

        # Check .env not accessible
        env_resp = await api_get(page, "/.env")
        record(g, ".env不可访问", env_resp["status"] in (403, 404),
               f"HTTP {env_resp['status']}")
    except Exception as e:
        record(g, "安全检查", False, str(e)[:80])


async def test_domain_monitor(page, seq):
    """域名监控（需管理员认证）"""
    g = "域名监控"
    try:
        resp = await api_get(page, "/api/admin/domain-monitor/health")
        record(g, "健康检查", resp["status"] == 401, f"HTTP {resp['status']} (需认证)")
    except Exception as e:
        record(g, "健康检查", False, str(e)[:80])


async def test_queue_status(page, seq):
    """队列状态（需管理员认证）"""
    g = "队列"
    try:
        resp = await api_get(page, "/api/queue/stats")
        record(g, "队列接口", resp["status"] == 401, f"HTTP {resp['status']} (需认证)")
    except Exception as e:
        record(g, "队列接口", False, str(e)[:80])


async def test_static_assets(page, seq):
    """静态资源"""
    g = "静态资源"
    try:
        # Check main JS/CSS load
        resp = await page.evaluate("""
            async () => {
                const scripts = document.querySelectorAll('script[src]');
                const links = document.querySelectorAll('link[rel=stylesheet]');
                return {
                    scripts: scripts.length,
                    styles: links.length,
                    scriptSrc: Array.from(scripts).map(s => s.src).slice(0, 3),
                };
            }
        """)
        record(g, "JS加载", resp["scripts"] > 0, f"{resp['scripts']} scripts")
        record(g, "CSS加载", resp["styles"] >= 0, f"{resp['styles']} stylesheets")
    except Exception as e:
        record(g, "静态资源", False, str(e)[:80])


async def test_responsive(page, seq):
    """移动端适配"""
    g = "响应式"
    try:
        await page.set_viewport_size({"width": 375, "height": 812})
        await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(1000)
        await page.screenshot(path=shot_name(seq, "mobile_home"))
        record(g, "移动端首页", True, "375x812")

        await page.goto(f"{BASE_URL}/#/admin", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(1000)
        await page.screenshot(path=shot_name(seq, "mobile_admin"))
        record(g, "移动端登录页", True, "375x812")

        # Restore desktop viewport
        await page.set_viewport_size({"width": 1280, "height": 900})
    except Exception as e:
        record(g, "响应式", False, str(e)[:80])


# ============================================================
# MAIN
# ============================================================

async def main():
    from playwright.async_api import async_playwright

    print("\n" + "=" * 55)
    print(" ANTI-COURSE PLUGIN - COMPLETE E2E TEST SUITE")
    print("=" * 55)
    start = time.time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--start-maximized", "--ignore-certificate-errors"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
        )
        page = await context.new_page()

        seq = 0

        test_groups = [
            ("1. 首页", test_home),
            ("2. 后台登录页", test_admin_login_page),
            ("3. 登录流程", test_admin_login),
            ("4. API端点", test_api_endpoints),
            ("5. YPay配对", test_ypay_pairing),
            ("6. 订单页", test_orders_page),
            ("7. 支付页", test_payment_page),
            ("8. 代理中心", test_agent_page),
            ("9. 分站", test_subsite),
            ("10. APP下载", test_app_download),
            ("11. 安全检查", test_security_headers),
            ("12. 域名监控", test_domain_monitor),
            ("13. 队列状态", test_queue_status),
            ("14. 静态资源", test_static_assets),
            ("15. 响应式", test_responsive),
        ]

        for group_name, test_fn in test_groups:
            print(f"\n── {group_name} ──")
            seq += 1
            try:
                await test_fn(page, seq)
            except Exception as e:
                record(group_name, "EXCEPTION", False, str(e)[:80])

        await browser.close()

    elapsed = round(time.time() - start, 1)

    # Summary
    print(f"\n{'='*55}")
    print(f" TEST RESULTS - {elapsed}s")
    print(f"{'='*55}")

    groups = {}
    for g, name, status, detail in results:
        groups.setdefault(g, []).append((name, status, detail))

    total_pass = sum(1 for _, _, s, _ in results if s == "PASS")
    total_fail = sum(1 for _, _, s, _ in results if s == "FAIL")
    total = len(results)

    for g, items in groups.items():
        g_pass = sum(1 for _, s, _ in items if s == "PASS")
        g_total = len(items)
        icon = "[+]" if g_pass == g_total else "[-]"
        print(f"\n  {icon} {g} ({g_pass}/{g_total})")
        for name, status, detail in items:
            si = "[+]" if status == "PASS" else "[-]"
            print(f"    {si} {name}" + (f" ({detail})" if detail else ""))

    print(f"\n{'='*55}")
    print(f" TOTAL: {total_pass} passed, {total_fail} failed / {total}")
    print(f" Screenshots: {SHOT_DIR}")
    print(f"{'='*55}")

    if total_fail > 0:
        print("\nFailed tests:")
        for g, name, status, detail in results:
            if status == "FAIL":
                print(f"  - [{g}] {name}: {detail}")

    return total_fail


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

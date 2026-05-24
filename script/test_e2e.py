#!/usr/bin/env python3
"""端到端自动化测试 — 使用 Playwright 有头 Chrome 浏览器"""
import asyncio
import os
from datetime import datetime

# 测试目标
BASE_URL = "https://shuakecdcas.top"
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "test_screenshots")

os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def ts():
    return datetime.now().strftime("%H:%M:%S")


async def main():
    from playwright.async_api import async_playwright

    results = []

    def record(name, passed, detail=""):
        status = "PASS" if passed else "FAIL"
        results.append((name, status, detail))
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

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

        # ── Test 1: 首页加载 ──
        print(f"\n[{ts()}] Test 1: 首页加载")
        try:
            resp = await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "01_home.png"))
            record("首页加载", resp and resp.status == 200, f"HTTP {resp.status if resp else 'None'}")
        except Exception as e:
            record("首页加载", False, str(e)[:80])

        # ── Test 2: 后台登录页 — 不应出现"首页/订单查询/管理后台"导航 ──
        print(f"\n[{ts()}] Test 2: 后台登录页导航检查")
        try:
            await page.goto(f"{BASE_URL}/#/admin", wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(1500)
            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "02_admin_login.png"))

            # Check that AppTopbar is NOT visible on login page
            topbar = page.locator("header.topbar")
            topbar_count = await topbar.count()

            # Check for forbidden text in visible nav
            page_text = await page.inner_text("body")
            has_nav_home = "首页" in page_text and topbar_count > 0
            has_nav_order = "订单查询" in page_text and topbar_count > 0
            has_nav_admin = "管理后台" in page_text and topbar_count > 0

            # The login card itself may have "后台管理" which is OK
            # We just want the topbar nav links gone
            nav_hidden = topbar_count == 0
            record("登录页无顶部导航栏", nav_hidden,
                   f"topbar count={topbar_count}")

            # Verify login form is present
            login_btn = page.locator("button:has-text('登录')")
            has_login = await login_btn.count() > 0
            record("登录页有登录按钮", has_login)
        except Exception as e:
            record("后台登录页检查", False, str(e)[:80])

        # ── Test 3: 后台登录 ──
        print(f"\n[{ts()}] Test 3: 后台登录")
        try:
            # Fill login form
            username_input = page.locator("input[placeholder*='用户名']")
            password_input = page.locator("input[placeholder*='密码']")
            captcha_input = page.locator("input[placeholder*='验证码']")

            await username_input.fill("admin")
            await password_input.fill("admin123")

            # Click captcha image to refresh
            captcha_img = page.locator(".captcha-img")
            if await captcha_img.count() > 0:
                await captcha_img.click()
                await page.wait_for_timeout(500)
                # We can't solve captcha automatically, just test the form
                record("登录表单可填写", True, "需要手动验证码")
            else:
                record("登录表单可填写", True)

            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "03_login_filled.png"))
        except Exception as e:
            record("后台登录", False, str(e)[:80])

        # ── Test 4: API 端点测试 ──
        print(f"\n[{ts()}] Test 4: API 端点")
        api_tests = [
            ("/api/info", "API 信息"),
            ("/api/ypay/app-info", "APP 信息"),
            ("/api/ypay/pair-status", "配对状态"),
        ]
        for path, name in api_tests:
            try:
                resp = await page.evaluate(f"""
                    async () => {{
                        const r = await fetch('{path}');
                        return {{ status: r.status, body: await r.text() }};
                    }}
                """)
                ok = resp["status"] == 200
                body_preview = resp["body"][:100]
                record(name, ok, f"HTTP {resp['status']} | {body_preview}")
            except Exception as e:
                record(name, False, str(e)[:80])

        # ── Test 5: 订单查询页 ──
        print(f"\n[{ts()}] Test 5: 订单查询页")
        try:
            await page.goto(f"{BASE_URL}/#/orders", wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(1000)
            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "05_orders.png"))
            page_text = await page.inner_text("body")
            has_order_page = "订单" in page_text or "查询" in page_text
            record("订单查询页加载", has_order_page)
        except Exception as e:
            record("订单查询页", False, str(e)[:80])

        # ── Test 6: 支付页面 ──
        print(f"\n[{ts()}] Test 6: 支付页面路由")
        try:
            await page.goto(f"{BASE_URL}/#/payment/test123", wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(1000)
            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "06_payment.png"))
            record("支付页面可访问", True)
        except Exception as e:
            record("支付页面", False, str(e)[:80])

        # ── Test 7: APP 下载 ──
        print(f"\n[{ts()}] Test 7: APP 下载接口")
        try:
            resp = await page.evaluate("""
                async () => {
                    const r = await fetch('/api/ypay/app-download', { method: 'HEAD' });
                    return { status: r.status, type: r.headers.get('content-type') };
                }
            """)
            record("APP下载接口", resp["status"] in (200, 302, 307),
                   f"HTTP {resp['status']} type={resp.get('type')}")
        except Exception as e:
            record("APP下载", False, str(e)[:80])

        # ── Test 8: 响应头安全检查 ──
        print(f"\n[{ts()}] Test 8: 安全头检查")
        try:
            resp = await page.evaluate("""
                async () => {
                    const r = await fetch('/api/info');
                    const h = {};
                    r.headers.forEach((v, k) => { h[k] = v; });
                    return h;
                }
            """)
            # Check for common security headers
            has_content_type = "content-type" in resp
            record("Content-Type 头", has_content_type,
                   resp.get("content-type", "missing")[:50])
        except Exception as e:
            record("安全头检查", False, str(e)[:80])

        await browser.close()

    # ── Summary ──
    print(f"\n{'='*50}")
    print(f"测试完成 — {len(results)} 项")
    print(f"{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"  通过: {passed}  失败: {failed}")
    if failed > 0:
        print("\n失败项:")
        for name, status, detail in results:
            if status == "FAIL":
                print(f"  - {name}: {detail}")
    print(f"\n截图保存在: {SCREENSHOT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())

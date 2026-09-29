#!/usr/bin/env python3
"""刷课系统压测 / 入口防护验证脚本（只读为主，不动业务数据）。

用途
----
1. 性能：并发打真实的重路径（SPA 首页、静态资源、订单列表、经营看板），
   输出吞吐与 P50/P95/P99 延迟分布。
2. 防护：验证限流（429）与管理员登录失败封锁确实生效。
3. 基线：安全响应头、未知 /api 路径返回 404 JSON。

设计约束
--------
- **不写业务数据**：压测只打读接口；需要鉴权的两个重接口靠环境变量
  `JWT_SECRET_KEY` 现场签一个管理员 token（不落盘、不带出脚本）。
- 登录封锁用**不存在的账号名**验证，不会影响真实管理员。
- 默认连本机 127.0.0.1:17017，可用 `BASE_URL` 覆盖。

用法
----
    # 纯只读压测
    python tools/stress_test.py

    # 带上需要管理员鉴权的重接口（订单列表 / 经营看板）
    $env:JWT_SECRET_KEY="<与 .env 相同的值>"; python tools/stress_test.py

    # 自定义并发与每线程请求数
    $env:CONCURRENCY=32; $env:REQUESTS_PER_THREAD=50; python tools/stress_test.py
"""

import base64
import gzip
import hashlib
import hmac
import http.client
import json
import os
import re
import statistics
import sys
import threading
import time
import zlib

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:17017").rstrip("/")
CONCURRENCY = int(os.environ.get("CONCURRENCY", "16"))
REQUESTS_PER_THREAD = int(os.environ.get("REQUESTS_PER_THREAD", "30"))
RATE_LIMIT_PROBE = int(os.environ.get("RATE_LIMIT_PROBE", "80"))
TIMEOUT = float(os.environ.get("TIMEOUT", "15"))

_parsed = BASE_URL.split("://", 1)
SCHEME = _parsed[0] if len(_parsed) > 1 else "http"
HOSTPORT = _parsed[-1]
HOST = HOSTPORT.split(":")[0]
PORT = int(HOSTPORT.split(":")[1]) if ":" in HOSTPORT else (443 if SCHEME == "https" else 80)


# ── 工具 ────────────────────────────────────────────────────────────────

def _b64(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def admin_token() -> str:
    """按后端 auth.rs 的 HS256 规格现场签一个 admin token（不落盘）。"""
    secret = os.environ.get("JWT_SECRET_KEY", "")
    if not secret:
        return ""
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps(
        {"sub": "stress", "role": "admin", "exp": int(time.time()) + 1800},
        separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret.encode(), header + b"." + payload, hashlib.sha256).digest())
    return (header + b"." + payload + b"." + sig).decode()


def _decode_body(raw: bytes, headers: dict) -> bytes:
    """服务端开了 CompressionLayer：声明了 Accept-Encoding 就必须自己解压，
    否则拿到的是一堆二进制，json.loads 必然失败。"""
    enc = {k.lower(): v for k, v in headers.items()}.get("content-encoding", "")
    try:
        if "gzip" in enc:
            return gzip.decompress(raw)
        if "deflate" in enc:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    except Exception:
        return raw
    return raw


def request(method: str, path: str, token: str = "", body: bytes | None = None):
    """单次请求（不复用连接，用于低频探测）。返回 (状态码, 响应头, 已解压响应体)"""
    conn_cls = http.client.HTTPSConnection if SCHEME == "https" else http.client.HTTPConnection
    conn = conn_cls(HOST, PORT, timeout=TIMEOUT)
    try:
        headers = {"Accept-Encoding": "gzip"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if body is not None:
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        resp_headers = dict(resp.getheaders())
        return resp.status, resp_headers, _decode_body(resp.read(), resp_headers)
    finally:
        conn.close()


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((p / 100) * (len(ordered) - 1))))
    return ordered[idx]


# ── 阶段一：安全基线 ────────────────────────────────────────────────────

def check_headers() -> bool:
    print("\n═══ 1. 安全响应头 / 错误处理基线 ═══")
    ok = True

    status, headers, _ = request("GET", "/")
    lower = {k.lower(): v for k, v in headers.items()}
    expect = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "no-referrer",
        "permissions-policy": None,
        "content-security-policy": None,
    }
    for key, want in expect.items():
        got = lower.get(key)
        flag = "OK " if got else "缺失"
        if not got:
            ok = False
        if want and got != want:
            flag = f"值异常({got})"
            ok = False
        print(f"  [{flag}] {key}: {got or '—'}")

    csp = lower.get("content-security-policy", "")
    for must in ("frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'"):
        hit = must in csp
        print(f"  [{'OK ' if hit else '缺失'}] CSP 含 {must}")
        ok &= hit

    # 未知 API 路径必须是 404 JSON，而不是 200 + HTML
    status, headers, body = request("GET", "/api/definitely-not-exists")
    ctype = {k.lower(): v for k, v in headers.items()}.get("content-type", "")
    good = status == 404 and "json" in ctype
    print(f"  [{'OK ' if good else '异常'}] 未知 /api 路径 → {status} {ctype}")
    ok &= good

    # 未授权访问受保护接口必须 401
    status, _, _ = request("GET", "/api/orders/")
    good = status == 401
    print(f"  [{'OK ' if good else '异常'}] 未带 token 访问 /api/orders/ → {status}")
    ok &= good

    return ok


# ── 阶段二：并发压测 ────────────────────────────────────────────────────

def discover_assets() -> list[str]:
    """从首页 HTML 里抓出构建产物路径，用真实的大文件做静态资源压测。"""
    try:
        status, _, body = request("GET", "/")
        if status != 200:
            return []
        html = body.decode("utf-8", "ignore")
        return sorted(set(re.findall(r"/static/assets/[A-Za-z0-9._-]+", html)))[:6]
    except Exception:
        return []


def load_mix(token: str) -> list[tuple[str, str]]:
    """构造 (名称, 路径) 列表。带 token 时纳入两个 DB 重接口。"""
    mix = [
        ("SPA 首页", "/"),
        ("健康检查", "/health"),
        ("接口信息", "/api/info"),
        ("系统公告", "/api/announcement"),
    ]
    for asset in discover_assets():
        mix.append((f"静态 {asset.rsplit('/', 1)[-1][:24]}", asset))
    if token:
        mix.append(("订单列表(50)", "/api/orders/?limit=50"))
        mix.append(("经营看板", "/api/admin/dashboard"))
    return mix


def bench_one(name: str, path: str, token: str, concurrency: int, per_thread: int) -> dict:
    latencies: list[float] = []
    errors = 0
    statuses: dict[int, int] = {}
    lock = threading.Lock()

    def worker():
        nonlocal errors
        conn_cls = http.client.HTTPSConnection if SCHEME == "https" else http.client.HTTPConnection
        conn = conn_cls(HOST, PORT, timeout=TIMEOUT)
        headers = {"Accept-Encoding": "gzip", "Connection": "keep-alive"}
        if token and path.startswith("/api/") and not path.startswith("/api/announcement"):
            headers["Authorization"] = "Bearer " + token
        local_lat: list[float] = []
        local_err = 0
        local_status: dict[int, int] = {}
        try:
            for _ in range(per_thread):
                start = time.perf_counter()
                try:
                    conn.request("GET", path, headers=headers)
                    resp = conn.getresponse()
                    resp.read()
                    local_lat.append((time.perf_counter() - start) * 1000)
                    local_status[resp.status] = local_status.get(resp.status, 0) + 1
                    # 429 是限流生效的正常结果，单独统计，不算作故障
                    if resp.status >= 400 and resp.status != 429:
                        local_err += 1
                except Exception:
                    local_err += 1
                    # 连接坏了就重建，避免后续请求全部失败
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = conn_cls(HOST, PORT, timeout=TIMEOUT)
        finally:
            try:
                conn.close()
            except Exception:
                pass
        with lock:
            latencies.extend(local_lat)
            errors += local_err
            for k, v in local_status.items():
                statuses[k] = statuses.get(k, 0) + v

    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    started = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - started

    total = concurrency * per_thread
    return {
        "name": name,
        "path": path,
        "total": total,
        "done": len(latencies),
        "errors": errors,
        "rps": len(latencies) / elapsed if elapsed > 0 else 0,
        "avg": statistics.fmean(latencies) if latencies else 0.0,
        "p50": pct(latencies, 50),
        "p95": pct(latencies, 95),
        "p99": pct(latencies, 99),
        "max": max(latencies) if latencies else 0.0,
        "statuses": statuses,
        "elapsed": elapsed,
    }


def run_bench(token: str) -> list[dict]:
    print(f"\n═══ 2. 并发压测（并发 {CONCURRENCY} × 每线程 {REQUESTS_PER_THREAD} 次请求）═══")
    if not token:
        print("  提示：未提供 JWT_SECRET_KEY，跳过需要管理员鉴权的 DB 重接口")
    results = []
    for name, path in load_mix(token):
        r = bench_one(name, path, token, CONCURRENCY, REQUESTS_PER_THREAD)
        results.append(r)
        err_rate = (r["errors"] / r["total"] * 100) if r["total"] else 0
        throttled = r["statuses"].get(429, 0)
        extra = f"  限流 {throttled}" if throttled else ""
        print(f"  {name:<28} {r['rps']:>9.0f} req/s  "
              f"P50 {r['p50']:>7.1f}ms  P95 {r['p95']:>7.1f}ms  P99 {r['p99']:>7.1f}ms  "
              f"错误 {r['errors']}/{r['total']} ({err_rate:.1f}%){extra}")
    if any(r["statuses"].get(429, 0) for r in results):
        print("  提示：出现 429 说明限流已生效，吞吐不再代表引擎上限。"
              "纯性能测量请用 RATE_LIMIT_REQUESTS=1000000 启动后端。")
    return results


# ── 阶段三：防护验证 ────────────────────────────────────────────────────

def check_rate_limit() -> bool:
    print(f"\n═══ 3. 限流验证（连打敏感接口 {RATE_LIMIT_PROBE} 次）═══")
    hit_429 = 0
    retry_after = ""
    # /api/admin/login 属敏感前缀；用不存在的账号名，避免影响真实管理员
    body = json.dumps({"username": "", "password": ""}).encode()
    for _ in range(RATE_LIMIT_PROBE):
        try:
            status, headers, _ = request("POST", "/api/admin/login", body=body)
        except Exception:
            continue
        if status == 429:
            hit_429 += 1
            retry_after = retry_after or {k.lower(): v for k, v in headers.items()}.get("retry-after", "")
    good = hit_429 > 0 and retry_after != ""
    print(f"  [{'OK ' if good else '异常'}] 429 次数 {hit_429}，Retry-After={retry_after or '—'}")
    return good


def check_login_lockout() -> bool:
    print("\n═══ 4. 管理员登录失败封锁验证（用不存在的账号，不影响真实管理员）═══")
    fake = f"stress-nonexistent-{int(time.time())}"
    locked_msg = ""
    for i in range(1, 8):
        status, _, body = request("POST", "/api/admin/login",
                                  body=json.dumps({"username": fake, "password": f"wrong-{i}"}).encode())
        try:
            msg = json.loads(body).get("message", "")
        except Exception:
            msg = ""
        if "锁定" in msg:
            locked_msg = msg
            print(f"  第 {i} 次尝试触发锁定：{msg}")
            break
    # 限流可能先于封锁生效，此时也算防护生效
    if not locked_msg:
        status, _, body = request("POST", "/api/admin/login",
                                  body=json.dumps({"username": fake, "password": "wrong-final"}).encode())
        if status == 429:
            locked_msg = "被限流拦截"
    good = bool(locked_msg)
    print(f"  [{'OK ' if good else '异常'}] {locked_msg or '未触发任何防护'}")
    return good


def main() -> int:
    print(f"目标：{BASE_URL}")
    token = admin_token()
    print(f"管理员令牌：{'已由 JWT_SECRET_KEY 现场签发' if token else '无（跳过鉴权接口）'}")

    if os.environ.get("SKIP_BENCH") == "1":
        results = []
        print("\n═══ 2. 并发压测（SKIP_BENCH=1，已跳过）═══")
    else:
        results = run_bench(token)
    headers_ok = check_headers()
    # 顺序有意为之：封锁验证要放在限流验证之前。两者都打 /api/admin/login，
    # 若先做限流探测，敏感桶会被打满，封锁分支永远轮不到（测试会「假通过」）。
    lock_ok = check_login_lockout()
    limit_ok = check_rate_limit()

    print("\n═══ 汇总 ═══")
    total_req = sum(r["total"] for r in results)
    total_err = sum(r["errors"] for r in results)
    total_time = sum(r["elapsed"] for r in results)
    if total_time > 0:
        print(f"  压测请求 {total_req} 次，错误 {total_err} 次，"
              f"累计耗时 {total_time:.1f}s，综合吞吐 {total_req / total_time:.0f} req/s")
    print(f"  安全响应头基线 : {'通过' if headers_ok else '不通过'}")
    print(f"  限流           : {'通过' if limit_ok else '不通过'}")
    print(f"  登录失败封锁   : {'通过' if lock_ok else '不通过'}")

    worst_p99 = max((r["p99"] for r in results), default=0)
    print(f"  最差 P99       : {worst_p99:.1f}ms")

    failed = [r["name"] for r in results if r["errors"] > 0]
    if failed:
        print(f"  存在错误响应的路径：{', '.join(failed)}")

    ok = headers_ok and limit_ok and lock_ok and not failed
    print(f"\n结论：{'全部通过' if ok else '存在需要关注的问题'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

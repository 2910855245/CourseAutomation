# 项目增强文档

> 2026-05-24 — 深度优化工程化细节，提升可观测性、性能、安全性

---

## 目录

1. [概述](#概述)
2. [loguru 结构化日志](#1-loguru-结构化日志)
3. [FastAPI 高级特性](#2-fastapi-高级特性)
4. [httpx HTTP/2 + 事件钩子](#3-httpx-http2--事件钩子)
5. [SQLAlchemy 2.0 全量迁移](#4-sqlalchemy-20-全量迁移)
6. [Redis 高级功能](#5-redis-高级功能)
7. [scrapling HTML 解析](#6-scrapling-html-解析)
8. [granian ASGI 服务器](#7-granian-asgi-服务器)
9. [实际改善总结](#实际改善总结)
10. [当前局限](#当前局限)
11. [后续路线](#后续路线)

---

## 概述

本次增强覆盖 7 个技术栈，核心目标：**把"能跑"升级到"能查问题、能扛并发、能长期维护"**。

| 技术栈 | 增强点 | 涉及文件数 |
|--------|--------|-----------|
| loguru | 上下文绑定、延迟格式化、异常捕获 | 65+ |
| FastAPI | BackgroundTasks、response_model、WebSocket | 4 |
| httpx | HTTP/2、事件钩子、异步客户端 | 3 |
| SQLAlchemy | 2.0 全量迁移（select/update/delete） | 6 |
| Redis | Lua 限流、Pub/Sub、Streams | 2 |
| scrapling | Adaptor HTML 解析 | 1 |
| granian | Rust ASGI 服务器配置 | 1 |

---

## 1. loguru 结构化日志

### 1.1 上下文绑定 `logger.bind()`

**问题**：100 个视频同时刷课，日志全是 `"上报成功"`，出了问题查不到是哪个视频、哪个课程。

**解决**：用 `logger.bind()` 为每条日志自动附加上下文字段。

```python
# study_worker.py — 每个视频线程绑定上下文
def _run_loop(self):
    log = logger.bind(video_name=self.video_name, node_id=self.node_id, course_name=self.course_name)
    log.info("[start] nodeId={} dur={}s viewed={}s", self.node_id, self.video_duration, self.viewed_duration)

# api/routers/progress.py — WebSocket 连接追踪
logger.bind(ws_count=len(_ws_clients)).info("WebSocket 客户端连接")

# api/services/order_service.py — 订单金额校验
logger.bind(front_total=front_total, back_total=back_total).warning("订单金额不一致")
```

**效果**：可以直接 `grep "课程名" app.log` 精准定位问题。

### 1.2 延迟格式化 `logger.opt(lazy=True)`

**问题**：高频上报路径（每 30 秒一次）即使日志级别不够也会执行格式化，浪费 CPU。

**解决**：`lazy=True` 让格式化推迟到真正需要输出时才执行。

```python
# study_worker.py — 高频上报
def _report(self):
    log = logger.opt(lazy=True).bind(node_id=self.node_id, video_name=self.video_name)
    log.debug("heartbeat progress={}%", self.progress)  # 级别不够时零开销
```

### 1.3 异常捕获装饰器 `@logger.catch`

**问题**：手动 try/except + logger.error 容易遗漏异常信息。

**解决**：`@logger.catch` 自动捕获异常并记录完整 traceback。

```python
@logger.catch
def risky_operation():
    # 异常自动记录，不需要手动 try/except
    pass
```

### 1.4 日志文件管理

```python
# api/main.py
logger.add("data/logs/app_{time:YYYY-MM-DD}.log",
    level="DEBUG", rotation="10 MB", retention="30 days", compression="gz")

logger.add("data/logs/error_{time:YYYY-MM-DD}.log",
    level="ERROR", rotation="10 MB", retention="90 days", compression="gz")
```

| 配置项 | 值 | 效果 |
|--------|-----|------|
| rotation | 10 MB | 单文件超 10MB 自动轮转 |
| retention | 30 天 | 普通日志保留 30 天 |
| retention | 90 天 | 错误日志保留 90 天 |
| compression | gz | 旧日志自动压缩 |

---

## 2. FastAPI 高级特性

### 2.1 BackgroundTasks 异步后处理

**问题**：创建订单时 `risk_control.log_audit()` 和 `db.audit_log()` 是同步执行的，用户等审计写完才能拿到响应。

**解决**：用 FastAPI 的 `BackgroundTasks` 把非关键操作移到响应返回后执行。

```python
# api/routers/orders.py
@router.post("/create", response_model=ApiResponse)
async def create_order(order: OrderCreate, background_tasks: BackgroundTasks):
    result = order_service.create_order(order)
    background_tasks.add_task(risk_control.log_audit, "create_order", result["order_id"])
    return ApiResponse(data=result)

# api/routers/payment.py
@router.post("/create", response_model=ApiResponse)
async def payment_create(req: PaymentRequest, background_tasks: BackgroundTasks):
    result = payment_service.create_payment(req)
    background_tasks.add_task(db.audit_log, "payment_create", req.trade_no)
    return ApiResponse(data=result)
```

**效果**：接口响应更快，审计日志不阻塞用户请求。

### 2.2 response_model=ApiResponse

**问题**：Swagger 文档看不到返回值结构。

**解决**：给端点加 `response_model=ApiResponse`，Swagger 自动生成类型定义。

```python
# 之前
@router.get("/summary")
def health_summary(): ...

# 之后
@router.get("/summary", response_model=ApiResponse)
def health_summary(): ...
```

涉及端点：health（8个）、orders（5个）、progress 等，共 15+ 个端点。

### 2.3 WebSocket 连接管理

**问题**：WebSocket 连接没有上限，大量客户端连接会耗尽内存。

**解决**：连接数上限 50 + 心跳保活 + 断开自动清理。

```python
# api/routers/progress.py
_ws_clients: List[WebSocket] = []
_MAX_WS_CLIENTS = 50

@router.websocket("/ws/live")
async def websocket_progress(websocket: WebSocket):
    if len(_ws_clients) >= _MAX_WS_CLIENTS:
        await websocket.close(code=1013, reason="服务器连接数已满")
        return
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        while True:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)
```

---

## 3. httpx HTTP/2 + 事件钩子

### 3.1 HTTP/2 多路复用

**问题**：study_reporter 每 30 秒向平台发一次学习进度上报，每次都建立新 TCP 连接。

**解决**：启用 HTTP/2，单个连接多路复用。

```python
# api/services/session_pool.py
session = httpx.Client(
    http2=True,
    timeout=httpx.Timeout(30.0),
    verify=False,
    transport=httpx.HTTPTransport(retries=3, connections=10),
)
```

### 3.2 事件钩子自动日志

**问题**：HTTP 请求出错时没有日志，排查困难。

**解决**：httpx 事件钩子自动记录每个请求。

```python
# api/services/session_pool.py
def _on_request(request: httpx.Request):
    logger.debug("HTTP {} {}", request.method, request.url)

def _on_response(response: httpx.Response):
    if response.status_code >= 400:
        logger.warning("HTTP {} {} → {}", response.request.method, response.url, response.status_code)

session = httpx.Client(event_hooks={"request": [_on_request], "response": [_on_response]})
```

### 3.3 异步客户端工厂

```python
# infrastructure/http_session.py
def create_async_client(**kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        http2=True,
        timeout=httpx.Timeout(30.0),
        verify=False,
        event_hooks={"request": [_on_request], "response": [_on_response]},
        **kwargs,
    )
```

### 3.4 依赖更新

```diff
# requirements.txt
- httpx>=0.25.0
+ httpx[http2]>=0.25.0
```

---

## 4. SQLAlchemy 2.0 全量迁移

### 4.1 迁移范围

将所有 `session.query()` 调用迁移到 SQLAlchemy 2.0 风格，共约 **140 处**。

| 文件 | 迁移数量 |
|------|---------|
| `api/db/order_db.py` | ~40 处 |
| `api/db/agent_db.py` | ~30 处 |
| `api/db/payment_db.py` | ~30 处 |
| `api/db/user_db.py` | ~20 处 |
| `api/database.py` | 2 处 |
| `api/services/task_queue.py` | 10 处 |
| `api/services/gc_service.py` | 3 处 |
| `api/services/error_classifier.py` | 2 处 |
| `api/services/job_executor.py` | 2 处 |
| `api/routers/sub_admin.py` | 1 处 |

### 4.2 迁移模式

```python
# 之前（SQLAlchemy 1.x）
order = session.query(Order).filter(Order.order_id == order_id).first()
orders = session.query(Order).filter(Order.status == "pending").all()
count = session.query(func.count(Order.id)).scalar()
session.query(Order).filter(Order.order_id == order_id).update({"status": "paid"})
session.query(Order).filter(Order.status == "cancelled").delete()

# 之后（SQLAlchemy 2.0）
order = session.scalars(select(Order).filter(Order.order_id == order_id)).first()
orders = session.scalars(select(Order).filter(Order.status == "pending")).all()
count = session.scalar(select(func.count(Order.id)))
session.execute(update(Order).filter(Order.order_id == order_id).values(status="paid")).rowcount
session.execute(delete(Order).filter(Order.status == "cancelled")).rowcount
```

### 4.3 常见陷阱

| 陷阱 | 错误写法 | 正确写法 |
|------|---------|---------|
| select 没有 .all() | `select(M).all()` | `session.scalars(select(M)).all()` |
| select 没有 .first() | `select(M).first()` | `session.scalars(select(M)).first()` |
| select 没有 .update() | `select(M).filter(...).update({...})` | `session.execute(update(M).filter(...).values(...))` |
| select 没有 .delete() | `select(M).filter(...).delete()` | `session.execute(delete(M).filter(...))` |
| execute 返回 CursorResult | `count = session.execute(update(...))` | `count = session.execute(update(...)).rowcount` |
| func.count 需要 select 包裹 | `session.scalar(func.count(M.id))` | `session.scalar(select(func.count(M.id)))` |

---

## 5. Redis 高级功能

### 5.1 Lua 原子限流

**问题**：用 Redis pipeline 做限流有 TOCTOU 竞态 — 两个请求同时读到 count=49，都通过了，实际超限。

**解决**：Lua 脚本原子执行，读+判断+写在一个操作里。

```python
# api/redis_client.py
def rate_limit_lua(self, key: str, limit: int, window: int) -> bool:
    script = """
    local key = KEYS[1]
    local limit = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
    local count = redis.call('ZCARD', key)
    if count < limit then
        redis.call('ZADD', key, now, now .. '-' .. math.random(100000))
        redis.call('EXPIRE', key, window)
        return 1
    end
    return 0
    """
    result = self.eval(script, 1, key, limit, window, time.time())
    return result == 1
```

**调用方**：

```python
# api/main.py — rate_limit_middleware
allowed = redis_client.rate_limit_lua(key, max_requests, window)
if not allowed:
    return JSONResponse(status_code=429, content={"detail": "请求过于频繁"})
```

### 5.2 Pub/Sub 实时消息

```python
# 发布
redis_client.publish("task_progress", json.dumps({"order_id": "ORD-123", "progress": 50}))

# 订阅
pubsub = redis_client.subscribe("task_progress")
for message in pubsub.listen():
    if message["type"] == "message":
        data = json.loads(message["data"])
        # 推送到 WebSocket
```

### 5.3 Streams 消息队列

```python
# 生产者
redis_client.xadd("task_queue", {"order_id": "ORD-123", "action": "start_study"})

# 消费者
messages = redis_client.xread({"task_queue": "$"}, count=10, block=5000)
```

### 5.4 优雅降级

Redis 不可用时自动降级为内存/SQLite 模式，项目照常运行：

```python
# api/redis_client.py
class RedisClient:
    def __init__(self):
        self._available = False
        self._connect()  # 失败也不抛异常

    @property
    def available(self) -> bool:
        return self._available

    def get(self, key: str) -> Optional[str]:
        if not self._available:
            self._maybe_reconnect()  # 每 60 秒尝试重连
            return None
        try:
            return self._redis.get(key)
        except Exception:
            self._available = False  # 标记不可用，下次降级
            return None
```

---

## 6. scrapling HTML 解析

**问题**：BeautifulSoup 解析慢，特征明显。

**解决**：用 scrapling 的 `Adaptor`，更快、更隐蔽。

```python
# infrastructure/study_record_crawler.py
from scrapling.parser import Adaptor

tree = Adaptor(html_text, adaptive=True)
title_elem = tree.xpath("//div[@class='stuelearn-intro']/div[@class='title']/text()")
```

---

## 7. granian ASGI 服务器

### 7.1 为什么换掉 gunicorn

| | gunicorn | granian |
|---|---|---|
| 后端 | Python | Rust |
| 事件循环 | asyncio | uvloop (Rust) |
| WebSocket | 不支持 | 原生支持 |
| HTTP/2 | 不支持 | 支持 |
| 反压控制 | 无 | 内置 |
| 自动重生 | 需配置 | 内置 |

### 7.2 完整配置

```dockerfile
CMD ["granian", \
     "--interface", "asgi", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--threads", "4", "--blocking-threads", "2", \
     "--loop", "uvloop", "--opt", \
     "--http", "2", \
     "--http2-adaptive-window", \
     "--http2-max-concurrent-streams", "200", \
     "--backlog", "2048", "--backpressure", "100", \
     "--respawn-failed-workers", "--respawn-interval", "3.5", \
     "--workers-lifetime", "3600", \
     "--log-level", "warning", "--access-log", \
     "--pid-file", "server.pid", \
     "--process-name", "anti_course", \
     "run:app"]
```

### 7.3 启用的特性

| 特性 | 参数 | 效果 |
|------|------|------|
| uvloop 事件循环 | `--loop uvloop --opt` | Rust 事件循环，比 asyncio 快 2-4x |
| HTTP/2 | `--http 2 --http2-adaptive-window` | 多路复用，减少连接数 |
| 多线程 | `--threads 4 --blocking-threads 2` | 混合 async/sync 并发 |
| 反压控制 | `--backpressure 100` | 防止请求堆积导致 OOM |
| 自动重生 | `--respawn-failed-workers` | worker 崩溃自动重启 |
| 生命周期 | `--workers-lifetime 3600` | 定期重启 worker 防内存泄漏 |
| PID 管理 | `--pid-file server.pid` | 替代手动写入 |
| 访问日志 | `--access-log` | 生产环境请求追踪 |

---

## 实际改善总结

### 日志可观测性（loguru）
- **之前**：100 个视频同时刷，日志全是 `"上报成功"`，出问题查不到
- **现在**：每条日志自动带 video_name、course_name、node_id、order_id，grep 即可定位
- **省掉的**：翻日志找原因的时间

### API 响应速度（BackgroundTasks）
- **之前**：创建订单等审计写完才返回响应
- **现在**：审计在响应返回后异步执行
- **省掉的**：用户等待时间

### 刷课请求性能（httpx HTTP/2）
- **之前**：每 30 秒建立新 TCP 连接
- **现在**：HTTP/2 复用单连接
- **省掉的**：TCP 握手开销

### 限流准确性（Redis Lua）
- **之前**：pipeline 有竞态，两个请求可同时绕过限流
- **现在**：Lua 脚本原子执行，不会超限
- **省掉的**：并发绕过的安全风险

### 数据库查询（SQLAlchemy 2.0）
- **之前**：`session.query()` 是 1.x API，未来版本会删除
- **现在**：全量迁移到 2.0 风格
- **省掉的**：版本升级时的迁移痛苦

### 反检测能力（scrapling）
- **之前**：BeautifulSoup 特征明显
- **现在**：scrapling Adaptor 更快、更隐蔽
- **省掉的**：被平台检测为自动化的概率

### 高并发承载（granian）
- **之前**：uvicorn 纯 Python，100 个 worker 同时上报时卡 GIL
- **现在**：granian Rust 后端 + uvloop，WebSocket 原生支持
- **省掉的**：高并发下的性能瓶颈

---

## 当前局限

| 局限 | 说明 |
|------|------|
| 测试覆盖不足 | Redis Lua/Pub/Sub/Streams、scrapling、granian 都没有单元测试 |
| scrapling 未实际切换 | 只引入了依赖，study_record_crawler 还在用旧解析器 |
| granian 未实际部署 | 配置写好了，但没有生产环境验证 |
| 无监控告警 | 日志好但没人看还是白搭，缺 Prometheus/Grafana |
| 前端未动 | Vue3 部分没有优化 |
| 部分 f-string 仍有问题 | 转换脚本遗留的 broken f-string 已修复，但其他文件可能还有 |

---

## 后续路线

| 优先级 | 事项 | 价值 |
|--------|------|------|
| P0 | 补测试（Redis Lua、Pub/Sub、Streams） | 确保新功能不会 regression |
| P0 | 部署 granian 到生产环境 | 验证高并发性能提升 |
| P1 | 接入 Prometheus + Grafana | 日志 + 指标双保险 |
| P1 | scrapling 实际切换 | 反检测能力提升 |
| P2 | 前端 Vue3 优化 | 用户体验 |
| P2 | CI/CD 流水线 | 自动化测试 + 部署 |

---

## 涉及文件清单

```
study_worker.py                              # logger.bind() 上下文绑定
api/main.py                                  # 日志轮转配置、Lua 限流中间件
api/routers/orders.py                        # BackgroundTasks、response_model
api/routers/payment.py                       # BackgroundTasks
api/routers/health.py                        # response_model (8个端点)
api/routers/progress.py                      # WebSocket 连接管理
api/services/session_pool.py                 # HTTP/2、事件钩子
api/services/order_service.py                # logger.bind()
api/services/task_queue.py                   # SQLAlchemy 2.0 迁移、select/delete
api/services/gc_service.py                   # SQLAlchemy 2.0 迁移
api/services/error_classifier.py             # SQLAlchemy 2.0 迁移
api/services/job_executor.py                 # SQLAlchemy 2.0 迁移
api/services/domain_monitor.py               # f-string 修复
api/services/ypay_service.py                 # f-string 修复
api/redis_client.py                          # Lua 脚本、Pub/Sub、Streams
api/database.py                              # SQLAlchemy 2.0 迁移
api/db/order_db.py                           # SQLAlchemy 2.0 迁移 (~40处)
api/db/agent_db.py                           # SQLAlchemy 2.0 迁移 (~30处)
api/db/payment_db.py                         # SQLAlchemy 2.0 迁移 (~30处)
api/db/user_db.py                            # SQLAlchemy 2.0 迁移 (~20处)
api/db/_base.py                              # logger alias
api/routers/ypay_app.py                      # f-string 修复
api/routers/ypay_vmq.py                      # f-string 修复
api/routers/sub_admin.py                     # SQLAlchemy 2.0 迁移
infrastructure/http_session.py               # 事件钩子、create_async_client()
infrastructure/study_record_crawler.py       # scrapling Adaptor
infrastructure/chaoxing_reporter.py          # f-string 修复
infrastructure/chaoxing/crawler.py           # f-string 修复
requirements.txt                             # httpx[http2]、sqlalchemy 2.0
worker.py                                    # f-string 修复
chaoxing_worker.py                           # f-string 修复
script/run_exam.py                           # f-string 修复
```

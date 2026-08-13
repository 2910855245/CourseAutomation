# 2026-08-13 轻量化：单人运营模式

## 变更内容

- **删 MySQL**：SQLite 为唯一存储（WAL + busy_timeout），pymysql/USE_MYSQL 分支全删
- **删用户体系**：注册/登录/资料/改密全删，只留管理员登录（/api/admin/login）+ 改密（/api/admin/change-password）
- **删钱包账单**：余额/充值/扣费/余额支付/退款/交易流水全删，支付纯扫码
- **删 task_manager**：内存任务系统（2 常驻线程）删除，统一走持久化队列；admin 执行端点删
- User 模型瘦身（-3 字段）、WalletTransaction 表删、UsersTab/useUsers/用户侧栏删
- domain_monitor 不再改写源码，新平台写入 websites_extra.json 运行时合并
- 前端 vue-tsc 0 错误 + build 通过；活服冒烟（订单/管理员登录/验证码）全过

# 2026-08-13 全库优化重构（12 阶段）

## 变更内容

- **修 20+ bug**：游客订单鉴权洞（view token 方案）、paid_processed 卡死回收、worker 存活探测、SQLite busy_timeout、钱包原子扣款、重阶段超时、路径穿越净化、公告 XSS 等
- **结构重组**：config 三分拆（settings/platforms/context）+ contextvars 线程隔离；双层 services 合并为单层；infrastructure 重排为 school/chaoxing 子包
- **解耦**：scan_service 参数注入、计价逻辑下沉 pricing_service、import 副作用全部移入 run_startup
- **抽取**：worker_common.py、OCR 单例、gen_id/parse_course_ids/normalize_task_type、db.refund_order、enqueue_order
- **删除**：Redis 层整体（纯内存实现）、VMQ 旧协议、约 30 个死端点/模型/模块、desktop_app、测试/CI/alembic/Docker
- **前端**：adminState 透传改 Pinia 显式类型 store，11 个 @ts-nocheck 全部移除，vue-tsc 0 错误 + lint 0 警告
- 平台密码明文存储（无加密）；默认管理员 2910855245/woainima123 启动自动创建

# 2026-08-13 移除教师端与代理分销系统

## 变更内容

- 删除教师端：成都文理学院教师平台 (wid=5)、role 参数链、教师登录函数、前端学生/教师切换
- 删除三级代理分销系统：Agent/Commission/Withdrawal 模型、代理中心、佣金结算、提现、代理分站、合伙人管理、邀请码体系、AGENTREG/AGENTUP 注册费支付
- 支付幂等重构：`commission_status` 语义改为 `paid_processed` 支付处理幂等列（claim_payment_processing → confirm_payment → mark_payment_processed → enqueue），旧库自动加列并拷贝旧值
- 通用配置/审计方法从 agent_db.py 拆分为 `api/db/config_db.py`


# 2026-05-24 改动总结

## 1. 反检测优化 — study_worker.py

平台通过 beginTime/finalTime 重叠数检测并行刷课（阈值~10个并发）。修改了6处：

| 改动 | 之前 | 之后 |
|------|------|------|
| 课程内并发 | 无限制（全部同时启动） | `Semaphore(8)` 限制每课程最多8个 |
| 全局并发 | 无限制 | `Semaphore(10)` 限制跨课程总计最多10个 |
| studyTime上报 | 直接用 total_time | cap 到 `video_duration - viewed_duration`，防止 viewed > total |
| 完成时间 | 立即上报 | 随机延迟 5-15 秒 |
| 启动间隔 | 固定 0.5 秒 | 随机 1-3 秒 |
| 课程间间隔 | 固定 0.5 秒 | 随机 2-5 秒 |

额外修复：主线程等待 reporter 创建完成后再检查存活状态，防止空列表导致提前退出。

---

## 2. HTTP客户端迁移 — curl_cffi → rnet

将学习通模块的 HTTP 客户端从 curl_cffi 迁移到 rnet（Rust 后端，指纹库更大）。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `infrastructure/chaoxing_session.py` | 完全重写：curl_cffi → rnet.BlockingClient，指纹库从10个扩展到15个 |
| `infrastructure/chaoxing_reporter.py` | `resp.text` → `resp.text()`（属性改方法），docstring 更新 |
| `requirements.txt` | 新增 `rnet>=2.4.0` |

### rnet vs curl_cffi

| | curl_cffi | rnet |
|---|---|---|
| 后端 | C (libcurl) | Rust (reqwest) |
| 指纹数 | ~10个 | 70+个 |
| 异步 | 不支持 | 原生 async/await |
| 维护 | 慢 | 活跃 (v2.4.2) |

---

## 3. 前端Topbar修改 — AppTopbar.vue

| 改动 | 之前 | 之后 |
|------|------|------|
| 默认 title | `'后台管理'` | `'FUCK 文理网课'`（与首页一致） |
| 导航链接 | "订单查询" | "我的订单"（指向 /orders） |
| goToOrders 函数 | 存在 | 已删除（不再需要） |

### 涉及文件

| 文件 | 改动 |
|------|------|
| `frontend/src/components/AppTopbar.vue` | title默认值、导航链接文字、删除废弃函数 |
| `frontend/src/views/Orders.vue` | 无改动（已构建，title默认值自动生效） |

---

## 4. 数据采集脚本 — scrape_courses.py

创建 `script/scrape_courses.py`，用于抓取指定账号的课程学习记录并导出 CSV。

- 登录：ddddocr 验证码识别 + requests
- 数据源：`/user/study_record?courseId=xxx&json=1` AJAX 接口
- 输出：CSV（account, course, item_type, name, begin_time, finish_time, progress, state, view_count, viewed_duration, total_duration）

---

## 5. HTTP服务替换 — gunicorn → granian

将生产环境服务器从 gunicorn 替换为 granian（Rust 后端，全面利用其高级特性）。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `requirements.txt` | `gunicorn>=22.0.0` → `granian>=2.0.0` + 新增 `uvloop>=0.19.0` |
| `Dockerfile` | CMD 完整配置 granian 全部参数 |
| `gunicorn.conf.py` | 已删除（granian 用 CLI 参数，不需要配置文件） |
| `run.py` | 精简：移除冗余的 write_pid/handle_sigterm（granian 内置），开发模式加 reload |
| `backup.py` | 移除 gunicorn.conf.py 引用 |
| `docs/README.md` | 宝塔面板启动方式改为 granian |
| `docs/CLAUDE.md` | 生产启动命令更新 |
| `docs/ARCHITECTURE.md` | 目录结构和启动命令更新 |

### granian 完整配置

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

### 启用的 granian 特性

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

## 6. 日志库替换 — structlog → loguru

将结构化日志库从 structlog 替换为 loguru（零配置，一行 import 即用）。

### 涉及文件

- `requirements.txt` — `structlog>=23.0.0` → `loguru>=0.7.0`
- **65 个 .py 文件** — 全部替换 import 和日志调用
  - `import structlog` + `logger = structlog.get_logger(__name__)` → `from loguru import logger`
  - `logger.info("msg", key=val)` → `logger.info(f"msg key={val}")`
  - `logger.error("msg: %s", e)` → `logger.error(f"msg: {e}")`
- `api/main.py` — 删除 `structlog.configure(...)` 初始化块
- `script/run_exam.py` — 同上
- `api/routers/setup.py` — 向导检查 structlog → loguru

### structlog vs loguru

| | structlog | loguru |
|---|---|---|
| 初始化 | 需要 configure() 配置 processors | 零配置，`from loguru import logger` |
| 调用风格 | `logger.info("msg", key=val)` | `logger.info(f"msg key={val}")` |
| 文件输出 | 需手动配置 | 默认输出 stderr，可 `logger.add()` |
| 轮转/压缩 | 需自己实现 | 内置 rotation/compression |
| 代码量 | 62 文件 × 2 行初始化 | 62 文件 × 1 行 import |

---

## 7. HTTP客户端统一 — requests → httpx

将通用 HTTP 客户端从 requests 替换为 httpx（已有依赖，API 几乎完全兼容）。

### 涉及文件

- `requirements.txt` — 移除 `requests>=2.28.0`（httpx 已存在）
- **43 个 .py 文件** — 全部替换 import 和调用
  - `requests.Session()` → `httpx.Client(timeout=httpx.Timeout(30.0), verify=False)`
  - `requests.exceptions.ConnectTimeout` → `httpx.ConnectTimeout`
  - `requests.exceptions.ProxyError` → `httpx.ProxyError`
  - `allow_redirects=` → `follow_redirects=`（httpx 参数名不同）
- `api/services/session_pool.py` — `HTTPAdapter` → `httpx.HTTPTransport(retries=3, connections=10)`
- `infrastructure/http_session.py` — `requests.utils.dict_from_cookiejar` → `dict(session.cookies)`

### requests vs httpx

| | requests | httpx |
|---|---|---|
| 后端 | Python | Python (httpcore) |
| 异步 | 不支持 | 原生 async/await |
| HTTP/2 | 不支持 | 支持 |
| 默认超时 | 无（永远等待） | 5s（安全） |
| API | `Session()` | `Client()` |
| 参数名 | `allow_redirects` | `follow_redirects` |

---

## 涉及改动的文件清单

```
study_worker.py                              # 反检测：并发限制+时间随机化
infrastructure/chaoxing_session.py           # curl_cffi → rnet
infrastructure/chaoxing_reporter.py          # resp.text → resp.text()
requirements.txt                             # 移除 requests/gunicorn/structlog，新增 rnet/uvloop/loguru/granian
gunicorn.conf.py                             # 已删除
Dockerfile                                   # granian 完整配置（uvloop/HTTP2/自动重生等）
frontend/src/components/AppTopbar.vue        # topbar 导航修改
script/scrape_courses.py                     # 新增：课程数据采集脚本
run.py                                       # 精简：移除冗余 PID/signal 代码，开发模式加 reload
backup.py                                    # 移除 gunicorn.conf.py 引用
docs/README.md                               # 宝塔启动方式更新
docs/CLAUDE.md                               # 生产启动命令更新
docs/ARCHITECTURE.md                         # 目录结构和启动命令更新
65 个 .py 文件                                # structlog → loguru（import + 调用格式）
43 个 .py 文件                                # requests → httpx（import + API 适配）
```

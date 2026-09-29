# 2026-09-29 UI 重构 + WebSocket 实时化 + 技术栈升级

## 变更内容

- **品牌统一**：FUCK → Fuk；主色由墨黑 `#17181b` 改为品牌蓝 `#0071e3`（原先首页主 CTA 一直是黑色）
- **设计系统**：引入 Naive UI（按需自动导入）作为组件层；`src/theme/index.ts` 为品牌色/字体/圆角的单一真源；暗色模式（`[data-theme="dark"]`，index.html 内联脚本首屏防闪，前台与后台顶栏均可切换）
- **零改动桥接**：`store.toast()` 改为「实现可注入」，由 ToastBridge 注入 Naive message；confirm 由 ConfirmBridge 适配 Naive dialog —— 约 100 处 toast、4 处 showConfirm 调用点一行未改
- **WebSocket 重写**：统一信封 `{v,topic,type,data,ts,seq}`；服务端 topic 过滤 + 首帧 `auth`/`sub` 鉴权（`AUTH_WS_REQUIRED` 灰度，默认关）；前端 realtime store 单例（指数退避重连、75s 无帧判半开）；修掉队列任务进度从不广播、Admin 监听死分支、Orders.vue 重复建两条连接三处缺陷
- **前台**：Orders 收到 `order.update` 只重拉该条订单（去抖 300ms），WS 断开时才 60s 兜底轮询；Admin 进度帧 800ms 去抖合并刷新
- **图表**：后台概览换 ECharts（收入折线 + 订单柱、状态分布横条），独立 vendor-echarts 懒加载块
- **Rust 依赖**：rand 0.8→0.10、jsonwebtoken 9→11（显式 rust_crypto provider）、rusqlite 0.32→0.40 + r2d2_sqlite 0.25→0.35（同升）、reqwest 0.12→0.13（需开 form feature）、tower-http 0.6→0.7、scraper 0.20→0.27、md5/base64/bcrypt/aes-gcm/libloading 升级；dashmap 不升（仅有 RC）
- **前端工具链**：vue 3.5 / vite 8 / TS 6 / vue-tsc 3 / pinia 4 / vue-router 5；vite 8 下 manualChunks 改函数式、`__dirname` 改 `import.meta.url`；构建 4.1s → 0.7s
- **修既存 bug**：后台「财务报表」整页空白（访问已删除的 `dash.users`）、`/admin` 登录入口死锁、OrdersTab 表格在 769~859px 撑破整页、支付收款两张空 src 裂图、`pay::test_floating_price` 随机失败

## 验收

- Rust 单测 38 passed、前端单测 16 passed、`cargo build --release` 与 `npm run build`（vue-tsc）通过
- 接口冒烟全 PASS：静态资源、公开 API、JWT 鉴权 API（含无 token 401）、DB 读路径、游客查单、WS 信封 topic 推导
- 浏览器巡检：前台 3 路由 + 后台全部侧栏项，浅/暗各一轮，无 console 错误、无裂图、无横向溢出；全站 WS 连接数 = 1

## 上线前专家审计（四路并行：功能盘点 / 稳定性 / 前端死代码 / 安全）

### 修掉的安全问题

- **推送令牌名对不上**：出站读 `RUST_DAEMON_PUSH_TOKEN`、入站校验 `WORKER_TOKEN`，只设其一的结果是二选一 —— 要么所有进度推送被 401（前端永远看不到进度），要么完全不校验（任何人可向全体 WS 订阅者广播伪造的订单/支付帧）。现在两个键名都认，且未配置时随机生成进程内令牌，零配置也不再可伪造
- **WebSocket 默认全量广播**：任何人连上就能看到所有人的 order_id 与进度文本。`AUTH_WS_REQUIRED` 改为默认开启
- **任意文件写入**：`/submit_exam`、`/submit_full` 的 `status_file` 直接来自请求体并落盘，可覆盖任意路径文件 → 连同 6 个无调用方的 daemon 遗留端点一并删除
- **命令与信息泄露**：`/api/orders/audit-log/{id}` 完全无校验（猜到订单号即可读操作日志）→ 改为与查单同一套鉴权；`/api/jobs/submit`（无鉴权写队列表）删除；`/api/system/status` 移入鉴权组；`/api/*` 未知路径不再回退成 200 + HTML（此前会让「调了不存在的接口」看起来像成功，排查方向被带偏）
- **弱密钥兜底**：`view_token` 的密钥源与管理员 JWT 不统一（缺失时会退化成可离线枚举）→ 统一；新增启动自检，`JWT_SECRET_KEY` 缺失/过短直接拒绝启动

### 修掉的稳定性问题

- **所有出站 HTTP 客户端都没设超时**：平台无响应/TCP 半开时请求永久挂住，占死队列 worker 与扫描并发许可，队列整体停摆且无日志 → 统一 connect 10s / request 45s
- **进程重启后 `running` 任务永不回收**：`claim_next_job` 只挑 pending/retrying，崩溃时留下的 running 行再无人认领，订单永久停在「执行中」→ 调度器启动时回收（幂等）
- **三处按字节切片 panic**：DeepSeek 错误响应预览、API Key 掩码、支付回调响应预览，遇到中文即随机崩溃 → 改为按字符截断

### 补齐的功能（此前后端整段缺失）

- **系统公告**：`GET /api/announcement` + 管理端发布/停用。此前前端「系统通告」页与首页弹窗都调不到接口，公告功能整条链路是断的
- **支付配置**：`/api/ypay/config/get|save|status`。支付通讯密钥存在 `ypay_settings` 表并用于回调签名，但唯一的写入口没迁移过来 —— 等于密钥无法在后台轮换，而这是钱相关能力；同时拒绝把密钥存成空串（那会让签名校验永久失败）

### 删掉的无效功能（点了必然 404）

- **网络代理**页 + 3 个接口：后端无路由，`platform_client` 也不读任何代理配置，整套表单存不了也测不了
- **风险监控**页 + 8 个 `domain-monitor` 接口：一个都不存在，「全面检查」「添加域名」「保存间隔」全部必然失败；平台可用性看队列失败任务的 error_message 即可
- **假的图形验证码**：登录页有验证码输入框和「获取验证码」占位图，但 `admin_login` 明确不校验、`/api/captcha/generate` 也不存在。填了不生效的字段比没有更容易出事
- 顺带：`useSystemConfig` 的 `tierNames`（代理分销残留）等无用导出

### 本轮验收

- `cargo test` 38 passed、`npm test` 16 passed、`cargo build --release` 与 `vue-tsc + vite build` 通过
- 真实服务上跑 34 项回归（默认部署与显式配置 `WORKER_TOKEN` 两种模式各一轮）：旧端点不再响应、`/api` 未知路径 404 JSON、push 无/错令牌 401 而正确令牌 200、已鉴权连接收到广播而伪造凭证的连接业务帧 0 条、公告发布→读取→停用全链路、支付配置读写与空密钥拒绝、audit-log 鉴权边界 —— 全 PASS
- 浏览器实测：**用真实账号密码完成一次后台登录**（验证码字段已移除后登录路径正常）、侧栏两个死页已消失、公告发布后首页弹窗出现且停用后消失、站点 console 错误 0

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
| 默认 title | `'后台管理'` | `'Fuk 文理网课'`（与首页一致） |
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

# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指引。

## 项目概述

基于 FastAPI + Vue3 的全栈网课代刷 SaaS 平台。支持自动刷视频、自动考试，覆盖多个课程平台（粟湾平台、劳动教育平台、中嘉鑫盛、学习通）。支持多用户账号、三级代理分销体系、聚合支付（YPay/VMQ）。

## 常用命令

### 后端
```bash
pip install -r requirements.txt          # 安装 Python 依赖
python run.py                            # 启动开发服务器（端口 8000，uvicorn 热重载）
python manage.py                         # 交互式管理脚本（启动/停止/重启/日志，仅 Linux）
granian --interface asgi --host 0.0.0.0 --port 8000 run:app  # 生产环境（Rust ASGI 服务器）

# 测试
pytest                                   # 运行全部测试
pytest tests/test_auth.py                # 运行单个测试文件
pytest -k "test_name"                    # 按名称运行单个测试
pytest --cov                             # 带覆盖率运行

# 数据库迁移
alembic upgrade head                     # 执行迁移
alembic revision --autogenerate -m "msg" # 生成新迁移
```

### 前端
```bash
cd frontend
npm install
npm run build        # 类型检查 (vue-tsc --noEmit) + 构建到 ../static/
npm run dev          # 开发服务器，端口 5173，/api 代理到 localhost:8000
npm run test         # 单元测试 (vitest)
npm run lint         # ESLint 代码检查
npm run e2e          # Playwright E2E 测试
```

### Worker 子进程（由 API 自动启动）
```bash
python worker.py         # 课程爬取 worker
python study_worker.py   # 视频刷课 worker
```

## 架构

### 请求流程
1. Vue3 SPA 构建到 `static/`，由 FastAPI SPA fallback 提供服务
2. `/api/` 路由由 `api/routers/` 中的路由处理器处理
3. JWT 认证 + 内存黑名单（有 Redis 时自动切换 Redis）
4. 限流中间件：Redis 滑动窗口，无 Redis 时降级为内存限流
5. 所有非 API/非静态资源路由返回 `static/index.html`

### 后端分层

- **`api/main.py`** — FastAPI 应用入口。注册所有路由、CORS、限流中间件、no-cache 中间件、SPA fallback。生命周期钩子：自动创建管理员、初始化价格、启动双任务队列、恢复运行中订单、启动 GC/域名监控服务。
- **`api/database.py`** — SQLAlchemy ORM 模型（User, Order, WalletTransaction, Agent, Commission）+ `Database` 单例类封装所有数据库操作。默认 SQLite，通过 `DATABASE_URL` 切换 MySQL。通过表名/列名白名单防止 SQL 注入。
- **`api/auth.py`** — JWT 创建/验证、bcrypt 密码哈希、Token 黑名单（内存 + Redis 降级）
- **`api/routers/`** — 按业务域分组的路由处理器：`orders.py`、`payment.py`、`agents.py`、`admin.py`、`courses.py`、`setup.py`、`ypay_routes.py`、`ypay_vmq.py`、`ypay_app.py`、`wallet.py`、`pricing.py`、`invite.py`、`sub_admin.py` 等
- **`api/services/`** — 业务逻辑：`task_queue.py`（持久化任务队列，SQLAlchemy 后端，分 `school_queue` 和 `chaoxing_queue` 两个独立队列）、`task_runner.py`（子进程启动器）、`ypay_service.py`（支付集成）、`crack.py`（佣金计算）、`risk.py`（限流/黑名单）、`session_pool.py`（平台会话池）
- **`config.py`** — Pydantic `Settings` 模型，从 `.env` 加载。多网站配置（`WEBSITES` 字典）、按账号隔离的数据目录、URL 管理。`CURRENT_WEBSITE` 选择当前活跃平台。

### Worker 子进程模型
任务由 `task_runner.py` 作为子进程启动：
- Worker 将状态写入 `/tmp/task_*/status.json`，参数写入 `/tmp/task_*/params.json`
- 主 API 监控这些 JSON 文件以跟踪进度和检测失败
- `worker.py` 爬取课程结构（视频、章节）
- `study_worker.py` 模拟视频观看，定期发送学习进度上报

### 基础设施层 (`infrastructure/`)
底层平台交互：`http_session.py`（HTTP 封装，支持代理/反检测）、`course_crawler.py`（课程数据提取）、`study_reporter.py`（视频进度上报）、`captcha.py`（ddddocr 验证码识别）、`anti_test.py`（自动答题）、`platform_health.py`（平台健康监控守护进程）

### 服务层 (`services/`)
跨域业务服务：`auth_service.py`、`multi_platform_auth.py`（多站点登录）、`ai_service.py`（DeepSeek API 考试答题）、`course_service.py`、`study_service.py`

### 前端 (`frontend/src/`)
Vue3 SPA，使用 Pinia 状态管理、Vue Router、TypeScript。视图：Home（扫码+下单+支付）、Admin（完整管理后台，Tab 组件）、Agent（代理中心）、Orders（订单管理）、Setup（首次配置向导）、Subsite（代理子站）、Payment（支付页）、SubAdmin（合伙人管理）。

## 关键设计模式

- **多网站支持**：`config.py` 定义 `WEBSITES` 字典，`CURRENT_WEBSITE` 选择当前平台。用户数据按 `data/accounts/<username>/` 按用户+平台隔离
- **双任务队列**：`school_queue`（学校平台）和 `chaoxing_queue`（学习通）独立运行，各自有 SQLAlchemy 后端的任务表
- **支付回调**：YPay 集成 + HMAC 验证；VMQ 协议监听微信/支付宝；Android 监控 APP（`static/ypay-monitor.apk`）实时检测支付通知
- **代理佣金体系**：三级代理（入门/高级/合伙），根据销售额 + 邀请人数自动升级。佣金逻辑在 `api/services/crack.py`
- **Redis 可选**：限流和 JWT 黑名单自动降级为内存模式
- **代理支持**：隧道代理通过管理后台配置，应用于所有 Worker HTTP 请求以防止 IP 封禁

## 环境变量

`.env` 中必填项（参见 `.env.example`）：
- `JWT_SECRET_KEY` — JWT 签名密钥
- `DATABASE_URL` — MySQL 连接字符串（或 `sqlite:///data/orders.db`）
- `PASSWORD_ENCRYPTION_KEY` — 密码加密密钥

重要可选项：`REDIS_URL`、`SITE_URL`（支付回调地址）、`DEEPSEEK_API_KEY`（AI 考试答题）、`VMQPAY_URL`/`VMQPAY_KEY`（监控 APP 配对）、`CAPTCHA_AK`/`CAPTCHA_URL`（验证码服务）

## 数据目录结构

```
data/
├── orders.db              # SQLite 数据库
├── task_queue.db          # 持久化任务队列数据库
├── accounts/<username>/   # 按用户隔离的数据
│   ├── cookies/           # 平台会话 Cookie（按网站分文件）
│   ├── courses/<website>/ # 爬取的课程 JSON
│   └── records/<website>/ # 学习记录
├── global_config/         # 全局配置（上次选择的网站）
└── logs/                  # 按用户的日志文件
```

# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指引。

## 项目概述

基于 FastAPI + Vue3 的全栈在线课程自动化 SaaS 平台。支持多平台视频学习、考试辅助，覆盖多个课程平台（粟湾平台、劳动教育平台、中嘉鑫盛、学习通）。支持多用户账号、三级代理分销体系、聚合支付（YPay/VMQ）。

## 常用命令

### 后端

```bash
pip install -r requirements.txt          # 安装 Python 依赖
python run.py                            # 启动开发服务器（端口 8000，uvicorn 热重载）
granian --interface asgi --host 0.0.0.0 --port 8000 run:app  # 生产环境（Rust ASGI）
python manage.py                         # 交互式管理脚本（启动/停止/重启/日志，仅 Linux）

# 测试（需要设置环境变量）
pytest                                   # 运行全部测试
pytest tests/test_auth.py                # 运行单个测试文件
pytest -k "test_name"                    # 按名称运行单个测试
pytest --cov                             # 带覆盖率运行

# Lint
python -m ruff check .                   # 后端代码检查（ruff）
python -m ruff check . --fix             # 自动修复

# 数据库迁移
alembic upgrade head                     # 执行迁移
alembic revision --autogenerate -m "msg" # 生成新迁移
```

测试所需环境变量（见 `.github/workflows/ci.yml`）：

```bash
JWT_SECRET_KEY=test-secret
DATABASE_URL=sqlite:///test.db
PASSWORD_ENCRYPTION_KEY=encryption-key-32-chars!!
```

### 前端

```bash
cd frontend
npm install
npm run dev          # 开发服务器，端口 5173，/api 代理到 localhost:8000
npm run build        # 类型检查 (vue-tsc --noEmit) + 构建到 ../static/
npm test             # 单元测试 (vitest)
npm run lint         # ESLint 代码检查
npx playwright test  # E2E 测试（需要后端运行）
```

### Docker

```bash
docker compose up -d
```

Dockerfile 使用多阶段构建：Stage 1 构建前端（node:18-alpine），Stage 2 运行后端（python:3.11-slim + granian）。

### Worker 子进程（由 API 自动启动）

```bash
python worker.py         # 课程爬取 worker
python study_worker.py   # 视频刷课 worker
python chaoxing_worker.py # 学习通专用 worker
```

## 架构

### 请求流程

1. Vue3 SPA 构建到 `static/`，由 FastAPI SPA fallback 提供服务
2. `/api/` 路由由 `api/routers/` 中的路由处理器处理
3. JWT 认证 + 内存黑名单（有 Redis 时自动切换 Redis）
4. 限流中间件：Redis 滑动窗口，无 Redis 时降级为内存限流
5. 所有非 API/非静态资源路由返回 `static/index.html`

### 后端分层（Router → Service → Database → Infrastructure）

- **`run.py`** — 启动入口，设置中国时区、工作目录，导入 `api.main:app`。宝塔兼容：同时导出 `app` 变量供 granian 使用
- **`api/main.py`** — FastAPI 应用入口。注册所有路由、CORS、限流中间件、no-cache 中间件、SPA fallback。生命周期钩子：自动创建管理员、初始化价格、启动双任务队列、恢复运行中订单、启动 GC/域名监控服务
- **`api/startup.py`** — 从 main.py 提取的启动逻辑：初始化价格、设置队列回调、启动自动取消/心跳监控/订单恢复/会话恢复/健康监控守护线程
- **`api/database.py`** — SQLAlchemy ORM 模型（User, Order, WalletTransaction, Agent, Commission）+ `Database` 单例类封装所有数据库操作。默认 SQLite，通过 `DATABASE_URL` 切换 MySQL。通过表名/列名白名单防止 SQL 注入
- **`api/db/`** — 数据库子模块：`models.py`（ORM 模型定义，含动态队列任务模型 `SchoolJobModel`/`ChaoxingJobModel`）、`order_db.py`、`payment_db.py`、`agent_db.py`、`user_db.py`
- **`api/auth.py`** — JWT 创建/验证、bcrypt 密码哈希、Token 黑名单（内存 + Redis 降级）
- **`api/crypto.py`** — AES-256-GCM 密码加密（兼容旧 XOR 格式）
- **`api/dependencies.py`** — FastAPI 依赖注入（认证、数据库会话等）
- **`api/models.py`** — Pydantic 请求/响应模型（ApiResponse 等）
- **`api/routers/`** — 按业务域分组的路由处理器：`orders.py`、`payment.py`、`agents.py`、`admin.py`、`courses.py`、`setup.py`、`ypay_routes.py`、`ypay_vmq.py`、`ypay_app.py`、`wallet.py`、`pricing.py`、`invite.py`、`sub_admin.py`、`users.py`、`tasks.py`、`captcha.py`、`domain_monitor.py`、`health.py`、`scan.py`、`progress.py`、`queue.py`、`accounts.py` 等
- **`api/services/`** — 业务逻辑：`task_queue.py`（持久化任务队列，SQLAlchemy 后端，分 `school_queue` 和 `chaoxing_queue` 两个独立队列）、`task_runner.py`（子进程启动器）、`ypay_service.py`（支付集成）、`crack.py`（佣金计算）、`risk.py`（限流/黑名单）、`session_pool.py`（平台会话池）、`job_executor.py`、`order_service.py`、`commission_service.py`
- **`config.py`** — Pydantic `Settings` 模型，从 `.env` 加载。多网站配置（`WEBSITES` 字典）、按账号隔离的数据目录、URL 管理。`CURRENT_WEBSITE` 选择当前活跃平台

### Worker 子进程模型

任务由 `task_runner.py` 作为子进程启动：
- Worker 将状态写入 `/tmp/task_*/status.json`，参数写入 `/tmp/task_*/params.json`
- 主 API 监控这些 JSON 文件以跟踪进度和检测失败
- `worker.py` 爬取课程结构（视频、章节）
- `study_worker.py` 模拟视频观看，定期发送学习进度上报
- `chaoxing_worker.py` 学习通专用

### 基础设施层 (`infrastructure/`)

底层平台交互：`http_session.py`（HTTP 封装，支持代理/反检测）、`course_crawler.py`（课程数据提取）、`study_reporter.py`（视频进度上报）、`captcha.py`（ddddocr 验证码识别）、`anti_test.py`（自动答题）、`platform_health.py`（平台健康监控守护进程）

学习通专用：`chaoxing_session.py`（rnet 反检测会话，70+ TLS 指纹）、`chaoxing_crawler.py`、`chaoxing_quiz.py`、`chaoxing_reporter.py`、`chaoxing_discuss.py`、`chaoxing_points.py`、`chaoxing/` 子模块（crawler、scanner、cleaner、task_filter）

### 服务层 (`services/`)

跨域业务服务：`auth_service.py`、`multi_platform_auth.py`（多站点登录）、`ai_service.py`（DeepSeek API 考试答题）、`course_service.py`、`study_service.py`、`scan_service.py`、`auto_updater.py`

### 前端 (`frontend/src/`)

Vue3 SPA，使用 Pinia 状态管理、Vue Router、TypeScript。视图：Home（扫码+下单+支付）、Admin（完整管理后台，Tab 组件）、Agent（代理中心）、Orders（订单管理）、Setup（首次配置向导）、Subsite（代理子站）、Payment（支付页）、SubAdmin（合伙人管理）。

## 关键设计模式

- **多网站支持**：`config.py` 定义 `WEBSITES` 字典，`CURRENT_WEBSITE` 选择当前平台。用户数据按 `data/accounts/<username>/` 按用户+平台隔离
- **双任务队列**：`school_queue`（学校平台）和 `chaoxing_queue`（学习通）独立运行，各自有 SQLAlchemy 后端的任务表
- **支付回调**：YPay 集成 + HMAC 验证；VMQ 协议监听微信/支付宝；Android 监控 APP（`static/ypay-monitor.apk`）实时检测支付通知
- **代理佣金体系**：三级代理（入门/高级/合伙），根据销售额 + 邀请人数自动升级。佣金逻辑在 `api/services/crack.py`
- **Redis 可选**：限流和 JWT 黑名单自动降级为内存模式
- **隧道代理**：通过管理后台配置，应用于所有 Worker HTTP 请求以防止 IP 封禁

## 环境变量

`.env` 中必填项（参见 `.env.example`）：
- `JWT_SECRET_KEY` — JWT 签名密钥
- `DATABASE_URL` — MySQL 连接字符串（或 `sqlite:///data/orders.db`）
- `PASSWORD_ENCRYPTION_KEY` — 密码加密密钥

重要可选项：`REDIS_URL`、`SITE_URL`（支付回调地址）、`DEEPSEEK_API_KEY`（AI 考试答题）、`VMQPAY_URL`/`VMQPAY_KEY`（监控 APP 配对）、`CAPTCHA_AK`/`CAPTCHA_URL`（验证码服务）

## 默认管理员

首次启动自动创建：用户名 `admin`，密码 `admin123`。

## 已知问题和修复

### 任务队列无限循环 Bug

`job_executor.py` 中登录失败时会直接重试 + 设置重试状态，导致调度器重复创建 worker。修复方案：删除直接重试逻辑，只使用正常的重试机制。

### 学习通进度显示 0%

`study_worker.py` 中当视频已看完时（`viewed_duration >= video_duration`），`total_time` 没有设置，导致进度计算为 0%。修复方案：在 `actual_target <= 0` 时设置 `self.total_time = self.video_duration`。

### 学校平台扫描包含学习通

`scan_service.py` 的 `_discover_and_match()` 返回所有平台包括学习通，但学习通应该用单独的扫描函数。修复方案：排除 `website_id=4`。

### 学习通任务使用错误的 Worker

`task_runner.py` 只根据 `job_type` 决定使用哪个 worker，没有考虑 `website_id`。修复方案：`website_id=4` 时始终使用 `chaoxing_worker.py`。

## 编码规范

- Python 目标：3.8+（pyproject.toml），README 建议 3.10+ — 谨慎使用 3.10+ 特性
- Linting：ruff（line-length 120，select E/F/I/UP/B）
- 前端：ESLint + vue-tsc
- 日志：loguru（不用 stdlib logging）
- HTTP 客户端：httpx（通用）、rnet（学习通反检测）、scrapling（网页爬取）
- 密码加密：AES-256-GCM（新）+ XOR 兼容旧格式
- 依赖注入：FastAPI `Depends()`，不要在 `@app.middleware` 中使用

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

## 远程部署

生产服务器通过 SSH + paramiko 部署，凭据在 `script/.env.local`（不提交 git）。

```bash
# 1. 构建前端
cd frontend && npm run build

# 2. 同步后端代码（排除 data/frontend/node_modules 等）
python script/sync_code.py

# 3. 上传前端 static/ 到远程
python script/deploy.py

# 4. 重启服务（使用 granian，不是 systemd）
# 服务器上运行：
pkill -9 -f granian
cd /www/wwwroot/anti_course
nohup venv/bin/granian --interface asgi --host 0.0.0.0 --port 8000 run:app > /tmp/app.log 2>&1 &
```

远程路径：`/www/wwwroot/anti_course/`

### 服务器日志

- 应用日志：`/tmp/app.log`（当前运行）
- 历史日志：`/www/wwwroot/anti_course/data/logs/app_YYYY-MM-DD.log`
- 错误日志：`/www/wwwroot/anti_course/data/logs/error_YYYY-MM-DD.log`

### 学习通配置

学习通积分规则从平台页面动态解析，配置文件中的值只是默认值：
- `daily_limit` — 每日积分上限（从平台解析）
- `score_target` — 积分目标（从平台解析）
- `video_weight` — 视频积分上限

刷课速度在 `chaoxing_reporter.py` 中配置：
```python
SPEED_PROFILES = {
    'fast':   {60: (5, 10), 300: (10, 20), 600: (15, 30), 99999: (20, 40)},
    'normal': {60: (8, 15), 300: (15, 30), 600: (25, 50), 99999: (30, 60)},
    'slow':   {60: (10, 20), 300: (20, 40), 600: (30, 60), 99999: (40, 80)},
}
```

### script/ 目录工具

| 脚本 | 用途 |
|------|------|
| `remote.py` | 远程服务器管理工具（交互式菜单） |
| `sync_code.py` | 打包上传后端代码到远程 |
| `deploy.py` | 上传 `static/` 前端构建产物 |
| `deploy_fix.py` / `deploy_fix2.py` | 针对特定修复的增量部署 |
| `_remote_cmd.py` / `_remote_query.py` | SSH 远程执行命令/查询 |
| `reset_job.py` | 重置队列任务状态 |
| `check_cookies.py` | 检查平台 Cookie 有效性 |
| `fetch_exam.py` / `submit_exam.py` | 考试抓取/提交 |
| `run_exam.py` / `_run_batch_exam.py` | 运行考试 |
| `scrape_courses.py` | 课程爬取 |
| `migrate_sqlite_to_mysql.py` | SQLite 迁移 MySQL |
| `nginx_optimized.conf` | Nginx 配置模板 |

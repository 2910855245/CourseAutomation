# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-project workspace for an online course automation SaaS platform. The primary project is **Anti-Course Cheating Plugin** — a FastAPI + Vue3 full-stack system that automates video watching and exam completion for online course platforms (粟湾平台, 劳动教育平台, 中嘉鑫盛, 学习通). Supports multi-user accounts, aggregated payment processing, and background task workers.

## Sub-Projects

| Directory | Tech | Purpose |
|-----------|------|---------|
| `Anti-Course Cheating Plugin/` | Python (FastAPI) + Vue3 | Main SaaS platform |
| `Vmq-App-3.0/` | Android (Gradle) | Payment monitoring APP |

## Common Commands

### Anti-Course Cheating Plugin (main project)

```bash
cd "Anti-Course Cheating Plugin"

# Backend
pip install -r requirements.txt
python run.py                                    # Dev server (uvicorn, port 8000, hot reload)
granian --interface asgi --host 0.0.0.0 --port 8000 run:app  # Production (Rust ASGI)
python manage.py                                 # Interactive management menu (Linux)

# Frontend
cd frontend
npm install
npm run dev                                      # Dev server (port 5173, proxies /api to :8000)
npm run build                                    # Type check (vue-tsc) + build to ../static/

# Workers (auto-started by API as subprocesses)
python worker.py                                 # Course crawling worker
python chaoxing_worker.py                        # 学习通 worker

```

## Architecture — Anti-Course Cheating Plugin

### Request Flow

1. Vue3 SPA built to `static/`, served by FastAPI SPA fallback
2. `/api/` routes handled by `api/routers/`
3. JWT auth + in-memory token blacklist
4. In-memory sliding-window rate limit middleware
5. All non-API/non-static routes return `static/index.html`

### Backend Layers (4-layer architecture)

**Router → services（单层）→ Database → Infrastructure**

- **`run.py`** — Entry point. Sets China timezone, working dir, imports `api.main:app`. Exports `app` for granian/uvicorn compatibility
- **`api/main.py`** — FastAPI entry. Registers all routers, CORS, rate-limit, no-cache middleware, SPA fallback. Lifecycle: auto-creates admin, initializes pricing, starts dual task queues, recovers running orders, starts GC/domain-monitor services
- **`api/startup.py`** — Extracted startup logic: price init, queue callbacks, auto-cancel/heartbeat/order-recovery/session-restore daemon threads
- **`api/database.py`** — SQLAlchemy ORM models (User, Order, WalletTransaction) + `Database` singleton. SQLite default, MySQL via `DATABASE_URL`. Table/column name whitelisting prevents SQL injection
- **`api/db/`** — DB submodules: `models.py` (ORM models, dynamic queue job models `SchoolJobModel`/`ChaoxingJobModel`), `order_db.py`, `payment_db.py`, `config_db.py`, `user_db.py`
- **`api/auth.py`** — JWT create/verify, bcrypt password hashing, token blacklist (in-memory), view token
- **`api/routers/`** — Route handlers by domain: `orders.py`, `payment.py`, `admin.py`, `ypay_routes.py`, `ypay_vmq.py`, `ypay_app.py`, `pricing.py`, `users.py`, `captcha.py`, `domain_monitor.py`, `scan.py`, `progress.py`, `queue.py`
- **`services/`** — Business logic: `task_queue.py` (persistent queue, SQLAlchemy-backed, split into `school_queue` + `chaoxing_queue`), `task_runner.py` (subprocess launcher), `ypay_service.py`, `risk.py`, `session_pool.py`, `proxy_config.py`, `job_executor.py`, `order_service.py`
- **`config/`** — 包结构：`settings.py`（纯 env）、`platforms.py`（WEBSITES 静态数据）、`context.py`（contextvars 平台上下文）、`__init__.py`（兼容 shim + 账号路径）

### Worker Subprocess Model

`worker_common.py` 提供 worker 共享样板：`send_status`（原子写+终态清理+WS 推送开关）、`push_ws_update`（X-Worker-Token 鉴权）、`register_signal_handlers`、`ensure_terminal_status`、`apply_proxy`、`bootstrap_worker`。

Tasks dispatched as child processes by `task_runner.py`:
- `worker.py` — Crawls course structure (videos, chapters)
- 视频学习由 Rust daemon（rust_worker，:17017）执行，worker.py 提交任务；study_worker.py 已退役
- `chaoxing_worker.py` — 学习通专用 worker

Workers write status to `{tmp}/task_*/status.json` and params to `/tmp/task_*/params.json`（原子写 + 退出兜底由 worker_common.py 统一）。Main API monitors these files.

### Infrastructure Layer (`infrastructure/`)

Low-level platform interaction:
- `http_session.py` — HTTP wrapper with proxy/anti-detection support
- `ocr.py` — ddddocr singleton
- `school/` — 学校平台模块（course_crawler/captcha/exam_*/anti_test 等）
- `chaoxing/` — 学习通专用模块（session 含 rnet TLS 指纹、quiz/reporter/discuss/points/crawler/scanner）

### Services Layer (`services/`)

Cross-domain business services: `multi_platform_auth.py` (multi-site login), `ai_service.py` (DeepSeek API for exam answers), `scan_service.py`

### Frontend (`frontend/src/`)

Vue3 SPA with Pinia, Vue Router, TypeScript. Views: Home (scan + order + pay), Admin (full admin panel with tabs), Orders, Payment.

### Key Design Patterns

- **Multi-website support**: `config/platforms.py` `WEBSITES` dict; `config/context.py` contextvars（线程级平台上下文 + 进程默认回退）. User data isolated per `data/accounts/<username>/`
- **Dual task queues**: `school_queue` (school platforms) and `chaoxing_queue` (学习通) independent, each with SQLAlchemy-backed task tables
- **Payment**: YPay integration + HMAC verification; VMQ protocol for WeChat/Alipay monitoring; Android APP (`static/ypay-monitor.apk`) for real-time payment detection
- **Tunnel proxy**: Configured via admin panel, applied to all worker HTTP requests to prevent IP bans
- **Anti-detection**: rnet TLS fingerprint spoofing for 学习通, random user agents, semaphore-limited concurrency (max 8 per course, 10 global), randomized delays

### Configuration

- **`.env`** — Required: `JWT_SECRET_KEY`, `DATABASE_URL`. See `.env.example`
- Database: SQLite default (`data/orders.db`, WAL + busy_timeout), MySQL via `DATABASE_URL`
- Default admin: `2910855245` / `woainima123` (auto-created on first startup)

### Data Directory Structure

```
data/
├── orders.db              # SQLite database
├── task_queue.db          # Persistent task queue database
├── accounts/<username>/   # Per-user isolated data
│   ├── cookies/           # Platform session cookies (per website)
│   ├── courses/<website>/ # Crawled course JSON
│   └── records/<website>/ # Study records
├── global_config/         # Global config (last selected website)
└── logs/                  # Per-user log files
```

## Coding Conventions

- Python target: 3.10+
- Frontend: vue-tsc type check + vite build
- Logging: loguru (not stdlib logging)
- HTTP clients: httpx (general), rnet (anti-detection for 学习通)
- HTML parsing: lxml (C 加速 xpath，已替换 scrapling/beautifulsoup4)
- Sidecar services (systemd units in deploy/):
  - `rust_worker` (Rust, :17017) — 刷课循环，Python 侧经 worker.py 提交任务
  - `ocr_sidecar.py` (:17018) — ddddocr 验证码识别独立进程，主进程经 infrastructure/ocr.py HTTP 客户端调用（OcrClient.classification）
- Platform passwords stored in plaintext (no encryption)

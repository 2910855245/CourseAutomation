# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastAPI + Vue3 full-stack SaaS platform for online course automation. Automates video watching and exam completion for course platforms (粟湾平台, 劳动教育平台, 中嘉鑫盛). Supports multi-user accounts, agent/distributor commission tiers, and aggregated payment processing.

## Common Commands

### Backend
```bash
pip install -r requirements.txt          # Install Python dependencies
python run.py                            # Start dev server (port 8000, uvicorn)
python manage.py                         # Interactive management CLI (start/stop/restart/logs, Linux)
granian --interface asgi --host 0.0.0.0 --port 8000 run:app  # Production (Rust, fast)
```

### Frontend
```bash
cd frontend
npm install
npm run build        # Build to static/ (vue-tsc --noEmit && vite build)
npm run dev          # Dev server (vite, port 5173)
```

### Workers (subprocess-based, spawned by API)
```bash
python worker.py         # Course crawling worker
python study_worker.py   # Video study automation worker
```

## Architecture

### Request Flow
1. Vue3 SPA served from `static/` via FastAPI SPA fallback
2. API routes under `/api/` handled by routers in `api/routers/`
3. JWT auth with in-memory blacklist (Redis-backed when available)
4. Rate limiting middleware (Redis sliding window, in-memory fallback)
5. All non-API/non-static routes serve `static/index.html`

### Backend Layers

- **`api/main.py`** — FastAPI app entry, CORS, rate-limit middleware, SPA fallback, startup hooks (auto-create admin, init prices, start task queue, recover running orders)
- **`api/database.py`** — SQLAlchemy ORM (User, Order, WalletTransaction, Agent, Commission models) + all DB operations in a `Database` class. SQLite default, MySQL via `DATABASE_URL`
- **`api/auth.py`** — JWT token creation/validation, bcrypt password hashing, token blacklist
- **`api/routers/`** — Route handlers grouped by domain: `orders.py`, `payment.py`, `agents.py`, `admin.py`, `courses.py`, `setup.py`, `ypay_routes.py`, etc.
- **`api/services/`** — Business logic: `task_queue.py` (persistent job queue with SQLAlchemy backend), `task_runner.py` (subprocess spawner for workers), `ypay_service.py` (payment integration), `crack.py` (commission calculation), `risk.py` (rate limiting/blacklist), `session_pool.py` (platform session pooling)
- **`config.py`** — Pydantic `Settings` model loaded from `.env`. Multi-website config (`WEBSITES` dict), per-account data directories, URL management

### Worker Subprocess Model
Tasks are dispatched as child processes by `task_runner.py`:
- Workers write status to `/tmp/task_*/status.json` and params to `/tmp/task_*/params.json`
- Main API monitors these JSON files to track progress and detect failures
- `worker.py` crawls course structure (videos, chapters)
- `study_worker.py` simulates video watching by sending periodic study reports

### Infrastructure Layer (`infrastructure/`)
Low-level crawling/reporting: `http_session.py` (HTTP wrapper with proxy support), `course_crawler.py` (course data extraction), `study_reporter.py` (video progress reporting), `captcha.py` (OCR via ddddocr), `anti_test.py` (exam answering)

### Services Layer (`services/`)
Cross-cutting business services: `auth_service.py`, `multi_platform_auth.py` (multi-site login), `ai_service.py` (DeepSeek API for exam answers), `course_service.py`, `study_service.py`

### Frontend (`frontend/src/`)
Vue3 SPA with Pinia stores, Vue Router, TypeScript. Views: Home (scan+order+pay), Admin (full admin panel), Agent (distributor center), Orders, Setup (first-run wizard), Subsite (agent sub-site), Payment, SubAdmin (partner management).

## Key Patterns

- **Multi-website support**: `config.py` defines `WEBSITES` dict; `CURRENT_WEBSITE` selects active platform. Account data isolated per-user per-platform under `data/accounts/<username>/`
- **Payment callbacks**: YPay integration with HMAC verification; monitor APP (`static/ypay-monitor.apk`) listens for WeChat/Alipay notifications on Android
- **Agent commission system**: 3 tiers (入门/高级/合伙) with auto-upgrade based on sales volume + invite count. Commission logic in `api/services/crack.py`
- **Redis optional**: auto-degrades to in-memory for rate limiting and JWT blacklist
- **Proxy support**: tunnel proxy configured via admin panel, applied to all worker HTTP requests

## Environment Variables

Required in `.env` (see `.env.example`):
- `JWT_SECRET_KEY` — JWT signing key
- `DATABASE_URL` — MySQL connection string (or `sqlite:///data/orders.db`)
- `PASSWORD_ENCRYPTION_KEY` — encryption key for stored passwords

Key optional: `REDIS_URL`, `SITE_URL` (payment callback base), `DEEPSEEK_API_KEY` (AI exam answering), `VMQPAY_URL`/`VMQPAY_KEY` (monitor APP pairing)

## Data Directory Layout

```
data/
├── orders.db              # SQLite database
├── task_queue.db          # Persistent job queue database
├── accounts/<username>/   # Per-user data
│   ├── cookies/           # Platform session cookies (per website)
│   ├── courses/<website>/ # Crawled course JSON
│   └── records/<website>/ # Study records
├── global_config/         # Global config (last selected website)
└── logs/                  # Per-user log files
```

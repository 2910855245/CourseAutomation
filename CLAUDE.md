# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-project workspace for an online course automation SaaS platform. The primary project is **Anti-Course Cheating Plugin** — a FastAPI + Vue3 full-stack system that automates video watching and exam completion for online course platforms (粟湾平台, 劳动教育平台, 中嘉鑫盛, 学习通). Supports multi-user accounts, aggregated payment processing, and background task workers.

## Sub-Projects

| Directory | Tech | Purpose |
|-----------|------|---------|
| `Anti-Course Cheating Plugin/` | Python (FastAPI) + Vue3 | Main SaaS platform |
| `YPay_FastAPI/` | Python (FastAPI) + SQLAlchemy + Alembic | Payment gateway |
| `YPay_V7开源版/` | PHP (ThinkPHP) | Legacy payment system |
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

# Testing
pytest                                           # All tests
pytest tests/test_auth.py                        # Single file
pytest -k "test_name"                            # By name
pytest --cov                                     # With coverage

# Linting
python -m ruff check .                           # Backend lint (ruff)
python -m ruff check . --fix                     # Auto-fix

# Database migrations
alembic upgrade head                             # Run migrations
alembic revision --autogenerate -m "msg"         # Generate migration

# Frontend
cd frontend
npm install
npm run dev                                      # Dev server (port 5173, proxies /api to :8000)
npm run build                                    # Type check (vue-tsc) + build to ../static/
npm test                                         # Unit tests (vitest)
npm run lint                                     # ESLint
npx playwright test                              # E2E tests (needs backend running)

# Workers (auto-started by API as subprocesses)
python worker.py                                 # Course crawling worker
python study_worker.py                           # Video study worker
python chaoxing_worker.py                        # 学习通 worker

# Docker
docker compose up -d
```

### YPay_FastAPI

```bash
cd YPay_FastAPI
pip install -r requirements.txt
alembic upgrade head
python run.py
```

## Architecture — Anti-Course Cheating Plugin

### Request Flow

1. Vue3 SPA built to `static/`, served by FastAPI SPA fallback
2. `/api/` routes handled by `api/routers/`
3. JWT auth + blacklist (memory → Redis auto-fallback)
4. Rate limit middleware: Redis sliding window → in-memory fallback
5. All non-API/non-static routes return `static/index.html`

### Backend Layers (4-layer architecture)

**Router → Service → Database → Infrastructure**

- **`run.py`** — Entry point. Sets China timezone, working dir, imports `api.main:app`. Exports `app` for granian/uvicorn compatibility
- **`api/main.py`** — FastAPI entry. Registers all routers, CORS, rate-limit, no-cache middleware, SPA fallback. Lifecycle: auto-creates admin, initializes pricing, starts dual task queues, recovers running orders, starts GC/domain-monitor services
- **`api/startup.py`** — Extracted startup logic: price init, queue callbacks, auto-cancel/heartbeat/order-recovery/session-restore/health-monitor daemon threads
- **`api/database.py`** — SQLAlchemy ORM models (User, Order, WalletTransaction) + `Database` singleton. SQLite default, MySQL via `DATABASE_URL`. Table/column name whitelisting prevents SQL injection
- **`api/db/`** — DB submodules: `models.py` (ORM models, dynamic queue job models `SchoolJobModel`/`ChaoxingJobModel`), `order_db.py`, `payment_db.py`, `config_db.py`, `user_db.py`
- **`api/auth.py`** — JWT create/verify, bcrypt password hashing, token blacklist (memory + Redis fallback)
- **`api/crypto.py`** — AES-256-GCM password encryption (backward-compatible XOR)
- **`api/routers/`** — Route handlers by domain: `orders.py`, `payment.py`, `admin.py`, `ypay_routes.py`, `ypay_vmq.py`, `ypay_app.py`, `wallet.py`, `pricing.py`, `users.py`, `captcha.py`, `domain_monitor.py`, `scan.py`, `progress.py`, `queue.py`
- **`api/services/`** — Business logic: `task_queue.py` (persistent queue, SQLAlchemy-backed, split into `school_queue` + `chaoxing_queue`), `task_runner.py` (subprocess launcher), `ypay_service.py`, `risk.py`, `session_pool.py`, `proxy_config.py`, `job_executor.py`, `order_service.py`
- **`config.py`** — Pydantic `Settings` from `.env`. Multi-website config (`WEBSITES` dict), per-account data dirs, URL management. `CURRENT_WEBSITE` selects active platform

### Worker Subprocess Model

Tasks dispatched as child processes by `task_runner.py`:
- `worker.py` — Crawls course structure (videos, chapters)
- `study_worker.py` — Simulates video watching, sends periodic study reports
- `chaoxing_worker.py` — 学习通专用 worker

Workers write status to `/tmp/task_*/status.json` and params to `/tmp/task_*/params.json`. Main API monitors these files.

### Infrastructure Layer (`infrastructure/`)

Low-level platform interaction:
- `http_session.py` — HTTP wrapper with proxy/anti-detection support
- `course_crawler.py` — Course data extraction
- `captcha.py` — OCR via ddddocr
- `anti_test.py` — Auto exam answering
- `chaoxing/` — 学习通专用模块 (crawler, scanner, cleaner, task_filter)
- `chaoxing_session.py` — rnet-based HTTP client with TLS fingerprint spoofing (70+ fingerprints)
- `chaoxing_quiz.py` — 学习通考试
- `chaoxing_reporter.py` — 学习通学习进度上报
- `chaoxing_discuss.py` — 学习通讨论区
- `chaoxing_points.py` — 学习通积分

### Services Layer (`services/`)

Cross-domain business services: `multi_platform_auth.py` (multi-site login), `ai_service.py` (DeepSeek API for exam answers), `scan_service.py`

### Frontend (`frontend/src/`)

Vue3 SPA with Pinia, Vue Router, TypeScript. Views: Home (scan + order + pay), Admin (full admin panel with tabs), Orders, Payment.

### Key Design Patterns

- **Multi-website support**: `config.py` `WEBSITES` dict, `CURRENT_WEBSITE` selects platform. User data isolated per `data/accounts/<username>/`
- **Dual task queues**: `school_queue` (school platforms) and `chaoxing_queue` (学习通) independent, each with SQLAlchemy-backed task tables
- **Payment**: YPay integration + HMAC verification; VMQ protocol for WeChat/Alipay monitoring; Android APP (`static/ypay-monitor.apk`) for real-time payment detection
- **Redis optional**: Rate limiting and JWT blacklist auto-degrade to in-memory
- **Tunnel proxy**: Configured via admin panel, applied to all worker HTTP requests to prevent IP bans
- **Anti-detection**: rnet TLS fingerprint spoofing for 学习通, random user agents, semaphore-limited concurrency (max 8 per course, 10 global), randomized delays

### Configuration

- **`.env`** — Required: `JWT_SECRET_KEY`, `DATABASE_URL`, `PASSWORD_ENCRYPTION_KEY`. See `.env.example`
- **`config.py`** — Pydantic Settings model. `WEBSITES` dict maps platform IDs to names/URLs
- Database: SQLite default (`data/orders.db`), MySQL via `DATABASE_URL`. Redis optional (auto-degrades to in-memory rate limiting)
- Default admin: `admin` / `admin123` (auto-created on first startup)

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

## YPay_FastAPI

FastAPI payment gateway with SQLAlchemy + Alembic. Key files: `app/main.py`, `app/models/` (user, account, order), `app/services/` (order, notify), `app/api/v1/endpoints/` (pay, software, console).

## Root-Level Scripts

| File | Purpose |
|------|---------|
| `cc_v4pro_mimo.py` | Claude Code installer/manager — multi-provider API key management |
| `vmq_server_remote.py` | V免签 payment monitoring FastAPI router (VMQ protocol) |
| `scrape_teachers*.py` | Teacher contact scrapers (BeautifulSoup variants) |
| `brute_force_*.py` / `captcha_bypass.py` | Captcha/brute-force testing scripts |

## Coding Conventions

- Python target: 3.8+ (pyproject.toml), but README says 3.10+ — use 3.10+ features cautiously
- Linting: ruff (line-length 120, select E/F/I/UP/B, many ignores for compatibility)
- Frontend: ESLint + vue-tsc
- Logging: loguru (not stdlib logging)
- HTTP clients: httpx (general), rnet (anti-detection for 学习通), scrapling (web scraping)
- Password encryption: AES-256-GCM (new) with XOR backward compatibility

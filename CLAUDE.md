# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-project workspace for an online course automation platform. The primary project is **Anti-Course Cheating Plugin** — a Rust (axum) + Vue3 full-stack system that automates video watching and exam completion for online course platforms (学校平台 1/2/3, 学习通). 单人运营：只有管理员账号，下单用户为游客（凭 view_token 查单），聚合支付收款。**Python 后端已彻底移除，唯一服务进程是 `rust_worker`。**

产品文档见 `README.md`，架构细节（含实时通道、单视频时间轴、三档节奏）见 `docs/ARCHITECTURE.md`。

## Sub-Projects

| Directory | Tech | Purpose |
|-----------|------|---------|
| `Anti-Course Cheating Plugin/` | Rust (axum) + Vue3 | Main SaaS platform |
| `Vmq-App-3.0/` | Android (Gradle) | Payment monitoring APP |

## Common Commands

### Anti-Course Cheating Plugin (main project)

```bash
cd "Anti-Course Cheating Plugin"

# Backend
cd rust_worker
cargo build --release      # Build the single-binary backend (Rust 1.97+)
cargo run --release        # Run API + SPA hosting + OCR + study daemon on :17017
cargo test                 # Unit tests

# Frontend
cd frontend
npm install
npm run dev                # Dev server (port 5173, proxies /api to :17017)
npm run build              # Type check (vue-tsc) + build to ../static/
```

## Architecture — Anti-Course Cheating Plugin

### Request Flow

1. Vue3 SPA built to `static/`, served by rust_worker SPA fallback
2. `/api/` routes handled by axum routers in `rust_worker/src/`
3. JWT auth + in-memory token blacklist (`auth.rs`)
4. In-memory sliding-window rate limit middleware
5. All non-API/non-static routes return `static/index.html`

### Backend Modules (`rust_worker/src/`)

- **`main.rs`** — axum entry. Registers all routers, CORS, rate-limit, no-cache middleware, SPA fallback. Startup: `ensure_schema`, auto-create admin, init pricing, start task queues, recover running orders
- **`schema.rs`** — Idempotent schema bootstrap: 11 tables + 17 indexes (`CREATE TABLE IF NOT EXISTS`), ypay_account column patches, `ypay_settings` ← `vmq_settings` migration. Runs on every startup via `Db::open`
- **`db.rs`** — SQLite access layer (rusqlite, WAL + busy_timeout). `Db::open` invokes `schema::ensure_schema`
- **`auth.rs`** — JWT create/verify, password hashing, token blacklist (in-memory), view token
- **`api.rs` / `order.rs` / `progress.rs`** — Order lifecycle, pricing, progress query APIs
- **`scan.rs` / `login.rs` / `study.rs` / `queue.rs`** — Course scan, school-platform login (local OCR captcha), study loop (tokio), persistent task queue
- **`exam.rs` / `school_exam.rs`** — Exam answering (school platforms), exam list scraping, submission/heartbeat/cache
- **`llm.rs`** — DeepSeek API client for AI answers
- **`cx_scan.rs` / `cx_study.rs` / `cx_quiz.rs`** — 学习通专用：课程扫描、刷课（enc MD5 签名 + dtoken + 上报循环）、测评/讨论/笔记
- **`pay.rs` / `pay_routes.rs` / `ypay_db.rs` / `ypay_qr.rs`** — 支付：YPay 集成 + HMAC 校验、VMQ 协议、通道分发 + 二维码、订单创建/回调/入队
- **`ocr.rs` / `ocr_ort.rs`** — 验证码识别，进程内 ONNX Runtime 推理（无外部 OCR 服务）

### 任务执行模型（单进程，无子进程 worker）

- 所有任务（扫描/登录/刷课/考试/支付轮询）都是 rust_worker 进程内的 tokio 任务，每任务 ~1-2MB 内存
- 学校任务：登录（本地 OCR 图形码）→ 链式扫描+刷课；学习完成后同进程进考试阶段
- 学习通：`cx_study.rs` 刷课（上报走系统 TLS/HTTP1.1），`cx_quiz.rs` 做测评/讨论/笔记/考试，daily_done 语义保留
- 点选验证码（易盾 dunclick, need_code=2）不支持：遇到直接报错；图形码（need_code=1）走本地 OCR

### Frontend (`frontend/src/`)

Vue3 SPA with Pinia, Vue Router, TypeScript. Views: Home (scan + order + pay), Admin (full admin panel with tabs), Orders, Payment. Dev server proxies `/api` to `:17017`; production build is served by rust_worker itself.

### Key Design Patterns

- **Multi-website support**: `WEBSITES` 静态数据在 Rust 侧（`scan.rs` 平台表常量）. User data isolated per `data/accounts/<username>/`
- **Dual task queues**: `school_queue` (school platforms) and `chaoxing_queue` (学习通) independent, each backed by SQLite task tables
- **Payment**: YPay integration + HMAC verification; VMQ protocol for WeChat/Alipay monitoring; Android APP (`static/ypay-monitor.apk`) for real-time payment detection
- **Realtime**: `progress.rs` 是唯一广播入口；管理后台用 WS（首帧 auth/sub 控制帧），客户端订单页用 SSE（`/api/progress/sse/live?orders=OID:token`，服务端按 view_token 过滤）。两条通道的心跳/鉴权差异见架构文档
- **反检测**：随机 user agent、信号量限并发、请求间隔闸门（platform_client::wait_rate_limit）、三档错峰；任何档位并发不得超过 8（有单测）
- **凭据**：平台密码 AES-256-GCM 加密存 `credentials` 表（`crypto::store`/`load_password`），`orders` 表不落明文

### Configuration

- **`.env`** — Required: `JWT_SECRET_KEY`. See `.env.example`
- Database: SQLite (`data/orders.db`, WAL + busy_timeout); schema auto-created/migrated by `schema.rs` at startup
- Port: `RUST_DAEMON_PORT` (default 17017)
- Default admin: `2910855245` / `woainima123` (auto-created on first startup)

### Data Directory Structure

```
data/
├── orders.db              # SQLite database (all tables, incl. task queues)
├── accounts/<username>/   # Per-user isolated data
│   ├── cookies/           # Platform session cookies (per website)
│   ├── courses/<website>/ # Crawled course JSON
│   └── records/<website>/ # Study records
├── global_config/         # Global config (last selected website)
└── logs/                  # Per-user log files
```

## Coding Conventions

- Rust: 1.97+, `cargo check` + `cargo test` must pass before closing out changes
- Frontend: vue-tsc type check + vite build
- Logging: `tracing` / `log` crates (Rust side)
- HTTP client: reqwest (rustls); ONNX Runtime via `ort` crate for captcha OCR
- Sidecar services (systemd units in deploy/):
  - `rust-study-daemon.service` — the one and only backend service (API + SPA + OCR + study)

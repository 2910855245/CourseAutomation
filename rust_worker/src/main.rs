//! rust-backend — 刷课系统后端（纯 Rust 化，单二进制）
//!
//! 单进程承载：
//! - 刷课 daemon（/submit /submit_cx /submit_full /cancel，tokio task 调度）
//! - HTTP API（/api/*，逐步对齐 Python 版本）
//! - 静态资源 + SPA（gzip/brotli 压缩 + immutable 缓存）
//! - SQLite 访问层（rusqlite 直连，与 Python 迁移期共享 data/*.db）

mod api;
mod auth;
mod crypto;
mod cx_quiz;
mod cx_scan;
mod cx_study;
mod db;
mod exam;
mod guard;
mod llm;
mod login;
mod ocr;
mod ocr_ort;
mod order;
mod pay;
mod pay_routes;
mod platform_client;
mod progress;
mod queue;
mod scan;
mod schema;
mod school_exam;
mod session;
mod speed;
mod study;
mod ypay_db;
mod ypay_qr;

use std::sync::{Arc, OnceLock};

use anyhow::Context;
use axum::body::Body;
use axum::extract::Request;
use axum::http::{header, HeaderValue, StatusCode};
use axum::middleware::{self, Next};
use axum::response::Response;
use axum::routing::{get, post};
use axum::Router;
use dashmap::DashMap;
use tower_http::compression::CompressionLayer;
use tower_http::services::ServeDir;
use tracing_subscriber::EnvFilter;

type TaskMap = Arc<DashMap<String, tokio::task::JoinHandle<()>>>;

#[derive(Clone)]
pub struct AppState {
    pub tasks: TaskMap,
    pub push_url: String,
    pub push_token: String,
    pub db: db::Db,
    pub progress_tx: tokio::sync::broadcast::Sender<progress::Envelope>,
    /// 广播序号（envelope.seq）：前端用它丢弃乱序/重放帧
    pub ws_seq: Arc<std::sync::atomic::AtomicU64>,
}

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.to_string())
}

/// 进度推送令牌 —— **出站与入站必须同一个值**。
///
/// 历史缺陷：出站读 `RUST_DAEMON_PUSH_TOKEN`（systemd unit 里设的就是这个），
/// 入站却校验 `WORKER_TOKEN`（.env.example 里设的是这个）。只设其中一个的结果是
/// 二选一的坏结局：要么所有自推送被 401（进度彻底不更新、前端永远看不到进度），
/// 要么完全不校验（任何人都能 POST 向全体订阅者广播伪造的订单/支付帧）。
///
/// 现在两个键名都接受（并忽略示例里的占位值）；都未配置时随机生成一个进程内令牌，
/// 这样零配置部署下自推送照常可用，而外部无从得知令牌 → 无法伪造广播。
pub(crate) fn worker_token() -> String {
    static TOKEN: OnceLock<String> = OnceLock::new();
    TOKEN
        .get_or_init(|| {
            for key in ["WORKER_TOKEN", "RUST_DAEMON_PUSH_TOKEN"] {
                if let Ok(v) = std::env::var(key) {
                    let v = v.trim().to_string();
                    if !v.is_empty() && v != "change-me-worker-token" {
                        return v;
                    }
                }
            }
            let mut bytes = [0u8; 32];
            rand::fill(&mut bytes);
            let hex: String = bytes.iter().map(|b| format!("{b:02x}")).collect();
            tracing::warn!(
                "未配置 WORKER_TOKEN，已生成进程内临时推送令牌（重启即失效）；\
                 对外部署建议在 .env 显式配置"
            );
            hex
        })
        .clone()
}

/// 启动自检：JWT_SECRET_KEY 一个密钥同时撑起三件事 —— 管理员 JWT 签名、
/// 游客查单 view_token、凭据加密密钥的兜底派生。用缺省值/过短值等于把
/// 后台令牌签发能力公开（任何人可离线自签 admin 令牌或枚举他人订单 token），
/// 所以宁可拒绝启动也不要带病上线。
fn check_secret_key() {
    let key = std::env::var("JWT_SECRET_KEY").unwrap_or_default();
    let key = key.trim();
    if key.len() < 16 || key == "local-dev-secret-key" {
        eprintln!(
            "\n致命错误：JWT_SECRET_KEY 缺失或过短（当前 {} 字符）。\n\
             它同时用于管理员 JWT 签名、游客订单 view_token、以及凭据加密密钥派生，\n\
             使用缺省值等同于公开后台登录令牌。请在 .env 中设置一个随机值后重启：\n\n\
             \x20 JWT_SECRET_KEY=<64 位随机 hex>\n\
             \x20 生成方式：openssl rand -hex 32\n",
            key.len()
        );
        std::process::exit(1);
    }
}

pub(crate) fn rss_mb() -> u64 {
    #[cfg(target_os = "linux")]
    {
        let s = std::fs::read_to_string("/proc/self/status").unwrap_or_default();
        s.lines().find(|l| l.starts_with("VmRSS:"))
            .and_then(|l| l.split_whitespace().nth(1))
            .and_then(|v| v.parse::<u64>().ok())
            .map(|kb| kb / 1024)
            .unwrap_or(0)
    }
    #[cfg(not(target_os = "linux"))]
    { 0 }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let _ = dotenvy::dotenv();
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()))
        .init();

    let port: u16 = env_or("RUST_DAEMON_PORT", "17017").parse().unwrap_or(17017);
    let push_url = env_or("RUST_DAEMON_PUSH_URL", "http://127.0.0.1:17017/api/progress/live/push");
    // 与入站校验同源，详见 worker_token() 的注释
    let push_token = worker_token();
    let db_path = env_or("DB_PATH", "data/orders.db");

    // 启动自检：密钥不到位就不要起服务
    check_secret_key();

    let database = db::Db::open(&db_path)
        .with_context(|| format!("打开数据库失败: {db_path}"))?;
    tracing::info!(db_path, "SQLite 就绪");

    let (progress_tx, _) = tokio::sync::broadcast::channel::<progress::Envelope>(256);
    let state = AppState {
        tasks: Arc::new(DashMap::new()),
        push_url,
        push_token,
        db: database,
        progress_tx,
        ws_seq: Arc::new(std::sync::atomic::AtomicU64::new(1)),
    };

    // Rust 队列调度器（RUST_QUEUE_ENABLED=true 时接管学校任务）
    tokio::spawn(queue::dispatcher_loop(std::sync::Arc::new(state.clone())));

    // 已删除 Python 时代遗留的 daemon 端点：/status /submit /submit_cx
    // /submit_cx_full /submit_full /submit_exam /cancel/{order_id} /ocr。
    // 依据：Rust 版内部调度全部是直调函数（queue.rs、api.rs 调
    // study::run_study / scan::run_scan_and_study），全仓库无任何调用方；且其中
    //   - /submit_exam、/submit_full 的 status_file 直接取自请求体并落盘，
    //     可被任意人用来覆盖任意路径的文件；
    //   - /ocr 在 async handler 里同步跑推理，会阻塞 runtime 线程。
    let app = Router::new()
        .route("/api/progress/live/push", post(progress::push_progress))
        .route("/api/progress/ws/live", get(progress::ws_live))
        .merge(api::router(state.clone()))
        .merge(school_exam::router())
        .merge(pay_routes::router())
        .nest_service("/static", ServeDir::new("static").append_index_html_on_directories(true))
        .fallback(spa_fallback)
        .layer(middleware::from_fn(cache_headers))
        .layer(CompressionLayer::new())
        .layer(middleware::from_fn(trace_request))
        // 限流在 trace 之外（被拦的请求也要留下日志），安全头在最外层
        // （429/404 这类由内层产生的响应同样要带上安全头）。
        .layer(middleware::from_fn_with_state(guard::RateLimiter::from_env(), guard::rate_limit))
        .layer(middleware::from_fn(guard::security_headers))
        .with_state(state);

    let addr = format!("127.0.0.1:{port}");
    tracing::info!(addr, "rust-backend 就绪（API + daemon + 静态服务）");

    let listener = tokio::net::TcpListener::bind(&addr).await
        .with_context(|| format!("绑定 {addr} 失败"))?;
    // 带连接信息：限流中间件需要 socket 对端地址来判断能否采信 X-Forwarded-For
    axum::serve(
        listener,
        app.into_make_service_with_connect_info::<std::net::SocketAddr>(),
    )
    .await?;
    Ok(())
}

/// 请求日志
async fn trace_request(req: Request, next: Next) -> Response {
    let method = req.method().clone();
    let path = req.uri().path().to_string();
    let start = std::time::Instant::now();
    let resp = next.run(req).await;
    let status = resp.status().as_u16();
    if path.starts_with("/api/") {
        tracing::debug!(method = %method, path = %path, status, elapsed_ms = start.elapsed().as_millis(), "request");
    }
    resp
}

/// 构建产物文件名带内容 hash：永久缓存；HTML 保持 no-cache
async fn cache_headers(req: Request, next: Next) -> Response {
    let is_asset = req.uri().path().starts_with("/static/assets/");
    let mut resp = next.run(req).await;
    if is_asset {
        resp.headers_mut().insert(
            header::CACHE_CONTROL,
            HeaderValue::from_static("public, max-age=31536000, immutable"),
        );
    }
    resp
}

/// index.html 内存缓存。
///
/// 每次 SPA 回退（首页、/orders、/admin…任意前端路由）原先都要 `fs::read`，
/// 压测下这条路径的磁盘 I/O 完全没必要 —— 文件只在 `npm run build` 后变化。
/// 进程启动后读一次常驻内存。注意：重新构建前端后需重启后端才能取到新
/// index.html（assets 文件名带 hash，缓存策略不受影响）。
static INDEX_HTML: OnceLock<String> = OnceLock::new();

fn index_html() -> Option<&'static str> {
    INDEX_HTML.get_or_init(|| {
        std::fs::read_to_string("static/index.html").unwrap_or_default()
    });
    INDEX_HTML.get().map(|s| s.as_str()).filter(|s| !s.is_empty())
}

/// SPA 回退：非 API/静态路径返回 index.html（no-cache）。
///
/// `/api/*` 下的未知路径**不再**回退到 index.html：以前它会给前端返回 200 + HTML，
/// 让「调用了不存在的接口」看起来像 200，排查时极具误导性（前端只会得到
/// JSON 解析失败）。这类请求一律 404 JSON，让问题在第一时间暴露。
async fn spa_fallback(req: Request) -> Response {
    if req.uri().path().starts_with("/api/") {
        let mut resp = Response::new(Body::from(
            r#"{"success":false,"message":"接口不存在"}"#,
        ));
        *resp.status_mut() = StatusCode::NOT_FOUND;
        resp.headers_mut().insert(
            header::CONTENT_TYPE,
            HeaderValue::from_static("application/json; charset=utf-8"),
        );
        return resp;
    }
    match index_html() {
        Some(body) => {
            let mut resp = Response::new(Body::from(body));
            *resp.status_mut() = StatusCode::OK;
            resp.headers_mut().insert(
                header::CONTENT_TYPE,
                HeaderValue::from_static("text/html; charset=utf-8"),
            );
            resp.headers_mut().insert(
                header::CACHE_CONTROL,
                HeaderValue::from_static("no-store, no-cache, must-revalidate, max-age=0"),
            );
            resp
        }
        None => {
            let mut resp = Response::new(Body::from("index.html 未找到（请先 npm run build）"));
            *resp.status_mut() = StatusCode::NOT_FOUND;
            resp
        }
    }
}


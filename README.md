# 在线课程自动化平台

Rust + Vue3 全栈在线课程自动化 SaaS 平台，支持多平台视频学习、考试辅助、聚合支付。后端为单个 Rust 二进制（axum），前端构建产物由其直接托管。

## 运营模式

**单人运营**：系统只保留管理员账号（启动自动创建），下单用户为游客（凭查单凭证跟踪订单），支付纯扫码（YPay/VMQ），无注册/余额/钱包体系。

## 默认管理员

首次启动自动创建：

| 用户名 | 密码 |
|--------|------|
| `2910855245` | `woainima123` |

登录入口：浏览器打开 `http://<服务器IP>:17017/#/admin`（登录需输一次图片验证码）。部署后建议在「安全中心」修改密码。

## Linux 部署（直接部署，无需宝塔/Docker）

```bash
# 1. 上传项目到服务器，例如 /opt/anti-course
cd /opt/anti-course

# 2. 构建后端（需要 Rust 1.97+）
cd rust_worker && cargo build --release && cd ..
# 二进制在 target/release/rust_worker（本仓库配置了外置 target，见 rust_worker/.cargo/config.toml）

# 3. 配置
cp .env.example .env
vi .env   # 至少改 SITE_URL 为你的域名/IP；生产环境建议改 JWT_SECRET_KEY

# 4. 构建前端（首次或前端改动后需要）
cd frontend && npm install && npm run build && cd ..

# 5. 启动（API + 前端静态页 + OCR + 刷课全在这一个进程里）
./rust_worker
```

### systemd 常驻（推荐）

```bash
sudo cp deploy/rust-study-daemon.service /etc/systemd/system/
sudo vi /etc/systemd/system/rust-study-daemon.service   # 按实际路径修改 WorkingDirectory/ExecStart
sudo systemctl daemon-reload
sudo systemctl enable --now rust-study-daemon
sudo systemctl status rust-study-daemon
```

### Nginx 反代（可选）

```nginx
server {
    listen 80;
    server_name your.domain.com;

    location / {
        proxy_pass http://127.0.0.1:17017;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## 功能特性

### 多平台支持

| 平台 | 视频学习 | 考试辅助 |
|------|:--------:|:--------:|
| 在线课程测评考试平台 | 支持 | 支持 |
| 劳动课程测评考试平台 | 支持 | 支持 |
| 公益课程平台 | 支持 | 支持 |
| 学习通 | 支持 | 支持 |

### 支付通道

- 支付宝官方支付 / 当面付 / 个人版 / 商家账单
- 微信店员版 / 云端 / 经营码
- Android 收款监控 APP（实时监听通知）

## 架构说明

后端是单个 Rust 进程（axum，:17017）：REST API、前端 SPA 静态托管、OCR 验证码识别（ONNX Runtime）、刷课 tokio 多并发循环（每任务 ~1-2MB 内存）全部进程内完成，不再依赖任何 Python 组件。数据库表结构由 `rust_worker/src/schema.rs` 在启动时幂等创建/迁移（`CREATE TABLE IF NOT EXISTS` + 列级补丁）。

```bash
# 构建（需要 Rust 1.97+）
cd rust_worker && cargo build --release
# Linux 部署：拷贝二进制到服务器后 systemd 常驻
sudo cp deploy/rust-study-daemon.service /etc/systemd/system/ && sudo systemctl enable --now rust-study-daemon
```

## 项目结构

```
├── rust_worker/            # 后端（唯一服务进程）
│   └── src/
│       ├── main.rs         # axum 入口：路由注册、中间件、启动初始化
│       ├── api.rs / auth.rs / order.rs / progress.rs  # 订单/认证/进度 API
│       ├── scan.rs / login.rs / study.rs / queue.rs   # 扫描/登录/刷课/任务队列
│       ├── exam.rs / school_exam.rs / llm.rs          # 考试答题（DeepSeek）
│       ├── cx_scan.rs / cx_study.rs / cx_quiz.rs      # 学习通专用模块
│       ├── pay.rs / pay_routes.rs / ypay_db.rs / ypay_qr.rs  # 支付（YPay/VMQ）
│       ├── ocr.rs / ocr_ort.rs # 验证码识别（ONNX Runtime）
│       ├── db.rs / schema.rs   # SQLite 访问层 + 启动建表/迁移
├── frontend/               # Vue3 前端
│   └── src/views/          # 页面组件
├── static/                 # 前端构建产物（rust_worker 直接托管）
├── deploy/                 # systemd 单元
└── start_local.bat         # 本地一键启动
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `JWT_SECRET_KEY` | JWT 签名密钥 | 必填 |
| `DB_PATH` | SQLite 数据库文件 | `data/orders.db` |
| `RUST_DAEMON_PORT` | 后端监听端口 | `17017` |
| `SITE_URL` | 站点地址（支付回调） | `http://localhost:17017` |
| `DEEPSEEK_API_KEY` | AI 考试答题 | 可选 |

## 技术栈

**后端**: Rust · axum · tokio · rusqlite · reqwest · ort (ONNX Runtime)

**前端**: Vue 3 · TypeScript · Vite · Pinia · Vue Router

**数据库**: SQLite（WAL + busy_timeout）

**部署**: 单二进制 · systemd · Nginx

## License

MIT

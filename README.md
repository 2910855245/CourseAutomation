# 成都文理学院网课平台解决方案

面向成都文理学院（及各高校通用）在线课程平台的自主学习管理工具：登录校内课程平台后，自动生成未完成课程的刷课与考试任务清单，按需选择后统一推进，全程在用户自己的账号下完成。

- **技术栈**：Rust（axum，单二进制）+ Vue 3（TypeScript / Vite）+ SQLite
- **运行形态**：单个进程承载 REST API、前端静态页、验证码识别（进程内 ONNX Runtime）与任务执行
- **支付**：YPay 聚合（微信/支付宝）扫码收款
- **部署**：systemd 常驻 + Nginx 反代，支持 Linux 直接部署

> 本文档为产品与运维说明。代码与接口细节见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 功能

| 模块 | 说明 |
|------|------|
| 课程扫描 | 登录后扫描多平台全部课程，回显视频/考试进度（视频已看 n/N、待刷、考试 n/N 已通过） |
| 任务清单 | 仅展示未完成课程，按 打包计费 自动给出金额，选好即可下单 |
| 三档节奏 | 暴力（全量并行·最快）/ 适中（推荐）/ 保守（一节课接一节课·最稳，免费默认） |
| 考试环节 | 视频刷完后自动处理可作答考试（`exam` / `full` 订单），AI 答题走 DeepSeek |
| 订单跟踪 | 待支付 / 处理中 / 已完成 三态视图；手机端 SSE 长连接实时更新进度 |
| 管理后台 | 数据看板（收入/AI 用量/队列健康）、订单、队列监控、定价、支付对账、公告、安全中心 |
| 营销推广 | 全局免费开关、邀请送刷课卡（有效期可配），身份用服务端 HttpOnly cookie 承载 |

## 默认管理员

首次启动自动创建（部署后请在「安全中心」修改密码）：

| 用户名 | 密码 |
|--------|------|
| `2910855245` | `woainima123` |

登录入口：`http://<服务器IP>:17017/#/admin`（需输入一次图片验证码）。

## 快速开始

```bash
# 1. 构建后端（Rust 1.97+）
#    仓库里的 rust_worker/.cargo/config.toml 把构建目录固定到了 Windows 开发机的
#    ASCII 路径（中文路径下 mingw 链接器找不到 rlib）。Linux 部署时覆盖即可：
cd rust_worker
CARGO_TARGET_DIR=/opt/anti-course/target cargo build --release
cd ..

# 2. 配置（至少改 SITE_URL 与 JWT_SECRET_KEY）
cp .env.example .env && vi .env

# 3. 构建前端
cd frontend && npm install && npm run build && cd ..

# 4. 启动（API + 前端 + OCR + 刷课全在这一进程）
#    必须在仓库根目录启动：进程用相对路径读写 static/ 与 data/
/opt/anti-course/target/release/rust_worker    # 默认 :17017
```

### systemd 常驻

```bash
sudo cp deploy/rust-study-daemon.service /etc/systemd/system/
sudo vi /etc/systemd/system/rust-study-daemon.service   # 按实际路径修改 WorkingDirectory/ExecStart
sudo systemctl daemon-reload
sudo systemctl enable --now rust-study-daemon
```

> `WorkingDirectory` 必须是仓库根目录（相对路径的 `static/`、`data/` 都基于它）；
> 推送令牌用 `WORKER_TOKEN`（旧的 `RUST_DAEMON_PUSH_TOKEN` 仍兼容但不再推荐）。

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
        # SSE 长连接：不要缓冲、放宽空闲超时
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `JWT_SECRET_KEY` | JWT 签名密钥 | 必填 |
| `DB_PATH` | SQLite 数据库文件 | `data/orders.db` |
| `RUST_DAEMON_PORT` | 后端监听端口 | `17017` |
| `SITE_URL` | 站点地址（支付回调） | `http://localhost:17017` |
| `DEEPSEEK_API_KEY` | AI 答题密钥 | 可选 |

## 项目结构

```
├── rust_worker/src/         # 后端（唯一服务进程）
│   ├── main.rs              # axum 入口：路由/中间件/启动初始化
│   ├── api.rs order.rs      # 订单/定价/进度 API
│   ├── scan.rs study.rs queue.rs   # 扫描 / 刷课 / 持久化任务队列
│   ├── exam.rs school_exam.rs llm.rs   # 考试答题（DeepSeek）
│   ├── pay_routes.rs ypay_*.rs   # YPay/VMQ 聚合支付
│   ├── progress.rs          # WS（后台）+ SSE（手机端）实时推送
│   └── ocr.rs ocr_ort.rs    # 验证码识别（ONNX Runtime）
├── frontend/src/            # Vue3 前端（views/api/stores/composables）
├── static/                  # 前端构建产物（rust_worker 托管）
├── deploy/                  # systemd 单元
└── .env.example
```

## 说明

- 本项目仅用于用户管理与推进**自己账号**下的学习进度；请遵守所在平台与学校的课程管理规定。
- 默认管理员口令为部署引导所用，上线前务必修改；`JWT_SECRET_KEY` 缺失会拒绝启动。
- License: MIT

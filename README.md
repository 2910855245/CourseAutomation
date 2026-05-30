# 在线课程自动化平台

FastAPI + Vue3 全栈在线课程自动化 SaaS 平台，支持多平台视频学习、考试辅助、聚合支付、三级代理分销。

## 技术亮点

- **安全** — AES-256-GCM 密码加密（兼容旧 XOR 格式）、JWT + bcrypt、HMAC 支付验证、滑动窗口限流
- **测试** — 112 个后端测试 + 15 个前端测试 + 9 个 E2E 测试
- **工程化** — Ruff + ESLint 双端 lint、GitHub Actions CI、Docker 多阶段构建
- **架构** — router → service → db → infrastructure 四层分层，任务队列 + 子进程模型

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- Redis（可选，不装自动降级内存模式）
- MySQL（可选，默认 SQLite）

### 本地部署

```bash
# 1. 进入项目
cd "Anti-Course Cheating Plugin"

# 2. 安装后端依赖
pip install -r requirements.txt

# 3. 配置 .env（修改 SITE_URL 为你的域名或 IP）
cp .env.example .env   # 或直接编辑 .env

# 4. 构建前端
cd frontend && npm install && npm run build && cd ..

# 5. 启动服务（默认端口 8000）
python run.py

# 6. 浏览器访问 http://localhost:8000
# 首次访问会自动跳转安装向导
```

### 宝塔面板部署（推荐）

1. 上传项目到 `/www/wwwroot/`，解压
2. 宝塔 → 网站 → Python 项目 → 添加：

| 字段 | 值 |
|------|------|
| 项目名称 | 英文名，如 `course_saas` |
| 项目端口 | `8000` |
| Python 环境 | `Python 3.11+` |
| 项目路径 | 项目解压路径 |
| 入口文件 | `run:app` |
| 通讯协议 | `asgi` |
| 启动方式 | `granian` |
| 安装依赖包 | ✅ 勾上 |
| 依赖包路径 | `requirements.txt` |

3. 添加站点 → 域名 → SSL → 反代 `http://127.0.0.1:8000`

### Docker 部署

```bash
docker compose up -d
```

## 安装向导

首次访问自动跳转 `/setup`，五步完成初始化：

1. 环境检测 — 检查 Python 版本、磁盘空间、目录权限
2. 数据库初始化 — 自动建表
3. 创建管理员 — 设置后台登录账号密码
4. 支付配置 — 设置收款监控通信密钥 + 扫码配对监控 APP
5. 完成 — 进入系统

## 功能特性

### 多平台支持

| 平台 | 视频学习 | 考试辅助 |
|------|:--------:|:--------:|
| 在线课程测评考试平台 | ✅ | ✅ |
| 劳动课程测评考试平台 | ✅ | ✅ |
| 公益课程平台 | ✅ | ✅ |
| 学习通 | ✅ | ✅ |

### 支付通道

- 支付宝官方支付 / 当面付 / 个人版 / 商家账单
- 微信店员版 / 云端 / 经营码
- Android 收款监控 APP（实时监听通知）

### 代理体系

三级代理分销，阶梯佣金：

| 等级 | 直推佣金 | 间推佣金 | 二级间推 | 成本折扣 | 升级条件 |
|------|:---:|:---:|:---:|:---:|------|
| 入门代理 | 30% | - | - | 95折 | 无门槛 |
| 高级代理 | 35% | 8% | - | 9折 | 流水¥500+邀3人 |
| 资深代理 | 40% | 10% | 3% | 85折 | 流水¥3000+邀10人 |

## 项目结构

```
├── api/                    # 后端 API 层
│   ├── main.py             # FastAPI 入口
│   ├── config.py           # 全局配置
│   ├── database.py         # SQLAlchemy 模型 + 数据操作
│   ├── models.py           # Pydantic 请求/响应模型
│   ├── auth.py             # JWT 认证 + 黑名单
│   ├── routers/            # API 路由
│   └── services/           # 业务逻辑
├── infrastructure/         # 基础设施层
│   ├── http_session.py     # HTTP 请求封装
│   ├── course_crawler.py   # 课程数据爬取
│   ├── study_reporter.py   # 视频学习上报
│   ├── chaoxing/           # 学习通专用模块
│   └── chaoxing_session.py # rnet 反检测会话
├── services/               # 业务服务层
│   ├── scan_service.py     # 课程扫描
│   ├── ai_service.py       # AI 答题
│   └── study_service.py    # 学习调度
├── frontend/               # Vue3 前端
│   └── src/views/          # 页面组件
├── worker.py               # 课程爬取 Worker
├── study_worker.py         # 视频学习 Worker
├── chaoxing_worker.py      # 学习通 Worker
├── run.py                  # 启动入口
└── requirements.txt        # Python 依赖
```

## 开发指南

```bash
# 后端测试
pytest tests/ -v

# 前端开发
cd frontend && npm run dev    # 开发服务器 (端口 5173)

# 前端测试
cd frontend && npm test       # 单元测试
cd frontend && npx playwright test  # E2E 测试

# 代码检查
python -m ruff check .
cd frontend && npm run lint

# 数据库迁移
alembic upgrade head
alembic revision --autogenerate -m "msg"
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `JWT_SECRET_KEY` | JWT 签名密钥 | 必填 |
| `DATABASE_URL` | 数据库连接 | `sqlite:///data/orders.db` |
| `PASSWORD_ENCRYPTION_KEY` | 密码加密密钥 | 必填 |
| `REDIS_URL` | Redis 连接 | `redis://localhost:6379/0` |
| `SITE_URL` | 站点地址（支付回调） | `http://localhost:8000` |
| `DEEPSEEK_API_KEY` | AI 考试答题 | 可选 |

## 技术栈

**后端**: Python 3.10+ · FastAPI · SQLAlchemy · Pydantic · loguru · rnet · httpx · scrapling · ddddocr

**前端**: Vue 3 · TypeScript · Vite · Pinia · Vue Router

**数据库**: SQLite (默认) · MySQL (可选) · Redis (可选)

**部署**: Docker · Granian (Rust ASGI) · Nginx · 宝塔面板

## License

MIT

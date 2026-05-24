# 网课代刷 SaaS 平台

FastAPI + Vue3 全栈网课代刷系统，支持多平台自动刷视频/考试、聚合支付、三级代理分销。

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
pip install -r requirements-api.txt

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
| 项目名称 | 英文名，如 `anti_course` |
| 项目端口 | `8000` |
| Python 环境 | `Python 3.11+` |
| 项目路径 | 项目解压路径 |
| 入口文件 | `run:app` |
| 通讯协议 | `asgi` |
| 启动方式 | `granian` |
| 安装依赖包 | ✅ 勾上 |
| 依赖包路径 | `requirements.txt` |

3. 如果启动失败，终端执行：`bash fix_bt.sh <项目名>`
4. 添加站点 → 域名 → SSL → 反代 `http://127.0.0.1:8000`

### 命令行部署

```bash
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python run.py
# 或: nohup python run.py > /tmp/app.log 2>&1 &
```

## 安装向导

首次访问自动跳转 `/setup`，五步完成初始化：

1. 环境检测 — 检查 Python 版本、磁盘空间、目录权限
2. 数据库初始化 — 自动建表
3. 创建管理员 — 设置后台登录账号密码
4. 支付配置 — 设置收款监控通信密钥 + 扫码配对监控 APP
5. 完成 — 进入系统

## 支付通道配置

后台 → 支付收款 → 添加通道

- **支付宝官方支付**：需支付宝开放平台 APPID + 密钥（支持普通公钥/证书两种签名模式）
- **支付宝当面付**：需支付宝开放平台 APPID + 密钥，生成收款二维码
- **支付宝个人版/商家账单**：个人收款码免挂方案，需收款监控 APP
- **微信店员版/云端/经营码**：微信收款方案，需收款监控 APP

监控 APP (`static/ypay-monitor.apk`) 安装到安卓手机，扫码配对后自动监听收款通知。

## 代理体系

三级代理分销，阶梯佣金：

| 等级 | 直推佣金 | 间推佣金 | 二级间推 | 成本折扣 | 升级条件 |
|------|:---:|:---:|:---:|:---:|------|
| 入门代理 | 30% | - | - | 95折 | 无门槛 |
| 高级代理 | 35% | 8% | - | 9折 | 流水¥500+邀3人 |
| 资深代理 | 40% | 10% | 3% | 85折 | 流水¥3000+邀10人 |

- 代理注册费/升级费后台可配
- 达到流水+邀请阈值自动升级
- 代理专属推荐码 + 子站独立下单页

## 项目结构

```
├── api/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 全局配置
│   ├── database.py          # SQLAlchemy 模型 + 全部数据操作
│   ├── models.py            # Pydantic 请求/响应模型
│   ├── auth.py              # JWT 认证 + 黑名单
│   ├── utils.py             # 工具函数
│   ├── redis_client.py      # Redis 客户端（自动降级）
│   ├── routers/             # API 路由
│   │   ├── admin.py         # 管理后台（订单/用户/代理/广告/代理/黑名单）
│   │   ├── agents.py        # 代理中心
│   │   ├── orders.py        # 订单管理
│   │   ├── payment.py       # 支付 + 回调处理
│   │   ├── ypay_routes.py   # YPay 支付通道管理
│   │   ├── queue.py         # 任务队列
│   │   ├── setup.py         # 安装向导
│   │   ├── courses.py       # 课程扫描
│   │   ├── scan.py          # 平台检测
│   │   ├── config_admin.py  # 系统配置
│   │   ├── sub_admin.py     # 合伙人管理
│   │   ├── users.py         # 用户管理
│   │   ├── tasks.py         # 任务管理
│   │   ├── pricing.py       # 定价
│   │   ├── crack_admin.py   # 裂变规则管理
│   │   └── progress.py      # 学习进度
│   └── services/
│       ├── task_queue.py    # 持久化任务队列 + 调度器
│       ├── task_manager.py  # 任务状态管理
│       ├── task_runner.py   # 子进程管理
│       ├── ypay_service.py  # YPay 支付服务
│       ├── crack.py         # 佣金计算引擎
│       ├── risk.py          # 风控/限流/黑名单
│       ├── gc_service.py    # 垃圾清理
│       ├── session_pool.py  # 平台会话池
│       └── proxy_config.py  # 代理配置
├── infrastructure/          # 刷课执行层
│   ├── http_session.py      # HTTP 请求封装
│   ├── course_crawler.py    # 课程数据爬取
│   ├── study_reporter.py    # 视频学习上报
│   ├── heartbeat.py         # 心跳保活
│   ├── captcha.py           # 验证码识别
│   ├── anti_test.py         # 考试答题
│   └── dashboard.py         # 终端仪表盘
├── services/                # 业务服务
│   ├── course_service.py    # 课程处理
│   ├── ai_service.py        # AI 答题
│   ├── auth_service.py      # 认证服务
│   ├── study_service.py     # 学习调度
│   └── multi_platform_auth.py # 多平台登录
├── worker.py                # 爬课 Worker (子进程)
├── study_worker.py          # 刷视频 Worker (子进程)
├── run.py                   # 启动入口
├── frontend/                # Vue3 前端
│   └── src/views/
│       ├── Home.vue         # 主页（扫描+下单+支付）
│       ├── Admin.vue        # 管理后台（全部功能）
│       ├── Agent.vue        # 代理中心
│       ├── Orders.vue       # 订单查询
│       ├── Setup.vue        # 安装向导
│       ├── Subsite.vue      # 代理子站
│       ├── SubAdmin.vue     # 合伙人管理
│       └── Payment.vue      # 支付页
├── static/                  # 前端构建产物
│   └── ypay-monitor.apk     # 收款监控 APP
├── data/                    # 数据库文件
├── requirements-api.txt     # Python 依赖
└── .env                     # 环境配置
```

## 管理员后台

浏览器访问 `/#/admin`，功能标签：

- **概览**：订单/用户/代理统计 + 收入趋势
- **订单管理**：搜索、筛选、接单、完成、失败、批量取消、CSV 导出
- **定价设置**：视频单价、考试单价
- **用户管理**：全部用户/合伙人/代理列表，角色调整，余额充值扣费
- **佣金管理**：佣金记录、提现审核
- **任务队列**：实时任务状态、暂停/恢复、最大并发调整
- **支付收款**：支付通道增删改查、通道测试、配置管理
- **代理设置**：隧道代理开关、连接测试、使用教程
- **广告管理**：首页广告位（最多 5 个）
- **安全设置**：修改密码

## 手机 APP 配对

1. 安装 `static/ypay-monitor.apk` 到安卓手机
2. 后台 → 支付收款 → 配置管理 → 生成通信密钥
3. APP 扫描配对二维码完成绑定
4. 手机保持 APP 后台运行，自动监听微信/支付宝收款通知

## 隧道代理

防止服务器 IP 被目标平台封禁：

1. 后台 → 代理设置 → 填入隧道代理地址
2. 购买推荐：芝麻代理、快代理、站大爷（隧道代理 50-100 元/月）
3. 开启后 worker.py 和 study_worker.py 的所有 HTTP 请求走代理出口

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| JWT_SECRET_KEY | change-me | JWT 密钥，生产务必修改 |
| HOST / PORT | 0.0.0.0 / 8000 | 监听地址 |
| DATABASE_URL | sqlite:///data/orders.db | 数据库，支持 MySQL |
| REDIS_URL | redis://localhost:6379/0 | Redis，留空自动降级 |
| SITE_URL | http://localhost:8000 | 站点地址（支付回调用） |

## 开发指南

```bash
# 后端测试（112 个）
python -m pytest tests/ -v

# 前端单元测试（15 个）
cd frontend && npm test

# E2E 测试（9 个，需先启动后端）
cd frontend && npx playwright test

# 代码检查
python -m ruff check .
cd frontend && npm run lint

# Docker 构建
docker compose up -d
```

### CI 流水线

推送到 `main` 分支或创建 PR 时自动运行：
- **backend** — ruff check → pip install → pytest
- **frontend** — npm ci → eslint → vitest → vite build

# 项目架构文档

## 项目概述

Anti-Course Cheating Plugin 是一个在线课程自动化 SaaS 平台，支持视频自动观看、考试自动答题、多用户管理、代理分销系统和聚合支付处理。

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端 | Python 3.9+ / FastAPI | RESTful API 服务 |
| 前端 | Vue 3 / TypeScript / Vite | SPA 单页应用 |
| 数据库 | SQLite (默认) / MySQL | 通过 SQLAlchemy ORM |
| 缓存 | Redis (可选) | 速率限制、JWT 黑名单 |
| 支付 | YPay | 微信/支付宝聚合支付 |

## 目录结构

```
Anti-Course Cheating Plugin/
├── api/                          # 后端 API 层
│   ├── main.py                   # FastAPI 入口，注册路由、中间件
│   ├── auth.py                   # JWT 认证、密码加密
│   ├── database.py               # SQLAlchemy ORM 模型 + 数据库操作
│   ├── models.py                 # Pydantic 数据模型
│   ├── routers/                  # 路由处理器
│   │   ├── admin.py              # 管理员后台 CRUD
│   │   ├── agents.py             # 代理分销系统
│   │   ├── orders.py             # 订单生命周期
│   │   ├── payment.py            # 支付 + 回调
│   │   ├── pricing.py            # 定价系统 (打包/按量)
│   │   ├── courses.py            # 课程扫描
│   │   ├── users.py              # 用户管理
│   │   └── ...
│   └── services/                 # 业务逻辑层
│       ├── task_queue.py         # 持久化任务队列
│       ├── task_runner.py        # 子进程管理
│       ├── ypay_service.py       # YPay 集成
│       ├── crack.py              # 佣金计算
│       └── ...
├── services/                     # 跨切面业务服务
│   ├── ai_service.py             # DeepSeek AI 答题
│   ├── auth_service.py           # 登录认证
│   ├── course_service.py         # 课程处理
│   └── study_service.py          # 学习调度
├── infrastructure/               # 底层爬虫/报告
│   ├── anti_test.py              # AI 自动答题核心
│   ├── course_crawler.py         # 课程数据提取
│   ├── study_reporter.py         # 视频进度上报
│   └── http_session.py           # HTTP 会话管理
├── frontend/                     # Vue3 前端
│   └── src/
│       ├── views/                # 页面组件
│       │   ├── Home.vue          # 首页 (扫描+下单+支付)
│       │   ├── Admin.vue         # 管理员后台
│       │   ├── Agent.vue         # 代理中心
│       │   └── Orders.vue        # 订单列表
│       ├── api/index.ts          # API 接口定义
│       ├── stores/app.ts         # Pinia 状态管理
│       └── router/index.ts       # 路由配置
├── script/                       # 部署脚本
│   ├── deploy.py                 # 主部署脚本
│   └── remote.py                 # 远程服务器操作
├── worker.py                     # 课程爬取 Worker
├── study_worker.py               # 视频学习 Worker
├── run.py                        # 服务启动入口
├── config.py                     # 配置管理
└── run.py                        # 服务启动入口 (granian/uvicorn)
```

## 核心模块说明

### 1. API 层 (`api/`)

#### `main.py` - 应用入口
- 注册所有路由、CORS、速率限制中间件
- 启动时：自动创建管理员、初始化定价配置、启动任务队列、恢复运行中订单

#### `routers/pricing.py` - 定价系统
```python
# 两种定价模式
1. 打包模式 (package): 按视频数分档 + 进度折扣
2. 按量模式 (unit): 视频/作业/考试分别按次计价

# 核心 API
GET  /api/pricing           # 获取当前定价配置
POST /api/pricing/calculate # 计算课程价格 (后端唯一真相源)
POST /api/pricing/recommend # AI 推荐定价方案
POST /api/pricing/apply-package  # 应用打包定价
```

#### `routers/orders.py` - 订单系统
```python
# 订单生命周期
创建 -> 待支付 -> 已支付 -> 接单中 -> 执行中 -> 已完成

# API
POST /api/orders/batch    # 批量创建订单
GET  /api/orders/my       # 用户订单列表
POST /api/orders/{id}/accept  # 接单
```

### 2. Worker 子进程

#### `worker.py` - 课程爬取
- 从目标平台爬取课程结构（视频、章节）
- 写入状态到 `/tmp/task_*/status.json`

#### `study_worker.py` - 视频学习
- 模拟视频观看，定期发送学习报告
- 支持多平台、多账号并发

### 3. 前端 (`frontend/`)

#### 页面流程
```
Home.vue (首页)
  ├── 登录 -> 扫描课程 -> 选择课程 -> 选择套餐 -> 下单 -> 支付
  └── 已登录用户直接进入课程选择

Admin.vue (管理员后台)
  ├── 概览仪表盘
  ├── 用户管理
  ├── 订单管理
  ├── 定价配置 (打包/按量/AI推荐)
  ├── AI 模型配置
  └── YPay 支付配置

Agent.vue (代理中心)
  ├── 登录/注册
  ├── 佣金查看
  └── 推广链接
```

### 4. 定价系统详解

#### 课程类型检测
```python
def _detect_course_type(course) -> str:
    # "video"       - 有视频的课程
    # "exam_only"   - 纯考试 (无视频)
    # "homework_only" - 纯作业 (无视频)
    # "exam_homework" - 考试+作业 (无视频)
```

#### 价格计算逻辑
```python
# 打包模式
if video_total <= 30:   base = price_small      # ¥3
elif video_total <= 80: base = price_medium     # ¥5
else:                   base = price_large      # ¥6

# 进度折扣
if progress <= 25%:   coeff = 1.0
elif progress <= 50%: coeff = 0.7
elif progress <= 75%: coeff = 0.5
else:                 coeff = 0.3

final_price = max(price_minimum, base * coeff)

# 纯考试/纯作业
exam_only_price = ¥5    # 可配置
homework_only_price = ¥3  # 可配置
```

### 5. AI 集成

#### 模型配置
| 用途 | 默认模型 | 配置项 |
|------|----------|--------|
| 期末考试 | deepseek-v4-flash | `deepseek_final_exam_model` |
| 平时作业 | deepseek-chat | `deepseek_homework_model` |
| 定价顾问 | deepseek-v4-pro | `deepseek_pricing_model` |

#### AI 成本
- deepseek-v4-flash: 输入 ¥1/百万tokens，输出 ¥2/百万tokens
- 单门考试成本约 ¥0.01-0.05（极低）

## 运行方式

### 开发环境
```bash
# 后端
pip install -r requirements.txt
python run.py  # 启动在 http://localhost:8000

# 前端
cd frontend
npm install
npm run dev   # 启动在 http://localhost:5173
```

### 生产环境
```bash
# 构建前端
cd frontend && npm run build

# 启动服务
granian --interface asgi --host 0.0.0.0 --port 8000 run:app

# 或使用管理脚本
python manage.py  # 交互式菜单
```

### Worker 启动
```bash
python worker.py        # 课程爬取 Worker
python study_worker.py  # 视频学习 Worker
```

## 数据流

```
用户登录 -> 扫描课程 -> 获取价格(POST /api/pricing/calculate)
    -> 选择课程 -> 创建订单(POST /api/orders/batch)
    -> 支付 -> 接单 -> 入队 -> Worker 执行 -> 完成
```

## 部署架构

```
Nginx (443/80)
    ├── /static/* -> 静态文件
    └── /* -> proxy_pass http://127.0.0.1:8000
                └── Granian (ASGI, Rust)
                    └── FastAPI App
                        ├── SQLite/MySQL
                        └── Redis (可选)
```

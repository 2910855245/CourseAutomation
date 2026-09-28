# 项目架构文档

## 项目概述

Anti-Course Cheating Plugin 是一个在线课程自动化 SaaS 平台，支持视频自动观看、考试自动答题、多用户管理和聚合支付处理。后端为单个 Rust 二进制（axum），无 Python 依赖。

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端 | Rust / axum / tokio | RESTful API + SPA 托管 + 任务执行，单进程 |
| 前端 | Vue 3 / TypeScript / Vite | SPA 单页应用 |
| 数据库 | SQLite | rusqlite，启动时幂等建表（schema.rs） |
| OCR | ONNX Runtime (ort) | 进程内验证码识别 |
| 支付 | YPay | 微信/支付宝聚合支付 |

## 目录结构

```
Anti-Course Cheating Plugin/
├── rust_worker/                    # 后端（唯一服务进程，:17017）
│   └── src/
│       ├── main.rs                 # axum 入口：路由、中间件、启动初始化
│       ├── auth.rs                 # JWT 认证 + 黑名单
│       ├── api.rs / order.rs       # 订单生命周期、定价
│       ├── progress.rs             # 进度查询
│       ├── scan.rs                 # 课程扫描（平台表常量）
│       ├── login.rs                # 学校平台登录（本地 OCR 图形码）
│       ├── study.rs                # 刷课循环（tokio 多并发）
│       ├── queue.rs                # 持久化任务队列
│       ├── exam.rs / school_exam.rs# 考试答题、考试列表抓取
│       ├── llm.rs                  # DeepSeek AI 答题
│       ├── cx_scan.rs / cx_study.rs / cx_quiz.rs  # 学习通专用模块
│       ├── pay.rs / pay_routes.rs  # 支付 + 回调 + 通道分发
│       ├── ypay_db.rs / ypay_qr.rs # YPay/VMQ 数据层 + 二维码
│       ├── ocr.rs / ocr_ort.rs     # 验证码识别（ONNX Runtime）
│       ├── db.rs                   # SQLite 访问层
│       └── schema.rs               # 启动建表/迁移（幂等）
├── frontend/                       # Vue3 前端
│   └── src/
│       ├── views/                  # 页面组件
│       │   ├── Home.vue            # 首页 (扫描+下单+支付)
│       │   ├── Admin.vue           # 管理员后台
│       │   └── Orders.vue          # 订单列表
│       ├── api/index.ts            # API 接口定义
│       ├── stores/app.ts           # Pinia 状态管理
│       └── router/index.ts         # 路由配置
├── static/                         # 前端构建产物（rust_worker 直接托管）
├── deploy/                         # systemd 单元
│   └── rust-study-daemon.service   # 唯一的后端服务单元
├── start_local.bat                 # 本地一键启动
└── .env.example                    # 配置模板
```

## 核心模块说明

### 1. 后端 (`rust_worker/src/`)

#### `main.rs` - 应用入口
- 注册所有路由、CORS、速率限制中间件、SPA fallback
- 启动时：`ensure_schema` 建表/迁移、自动创建管理员、初始化定价配置、启动任务队列、恢复运行中订单

#### `schema.rs` - 数据库引导
- 11 张表 + 17 个索引，全部 `CREATE TABLE IF NOT EXISTS` 幂等
- ypay_account 列级补丁、`ypay_settings` ← `vmq_settings` 数据迁移
- 每次启动经 `Db::open` 执行，可安全重复运行

#### 定价系统
```
两种定价模式
1. 打包模式 (package): 按视频数分档 + 进度折扣
2. 按量模式 (unit): 视频/作业/考试分别按次计价

核心 API
GET  /api/pricing           # 获取当前定价配置
POST /api/pricing/calculate # 计算课程价格 (后端唯一真相源)
POST /api/pricing/recommend # AI 推荐定价方案
POST /api/pricing/apply-package  # 应用打包定价
```

#### 订单系统
```
订单生命周期
创建 -> 待支付 -> 已支付 -> 接单中 -> 执行中 -> 已完成

API
POST /api/orders/batch    # 批量创建订单
GET  /api/orders/my       # 用户订单列表
POST /api/orders/{id}/accept  # 接单
```

### 2. 任务执行（进程内 tokio 任务）

- 扫描/登录/刷课/考试全部在 rust_worker 进程内并发执行，无子进程
- 学校任务：登录（本地 OCR）→ 链式扫描+刷课 → 考试
- 学习通：`cx_study.rs` 刷课（enc MD5 签名 + dtoken + 上报循环），`cx_quiz.rs` 测评/讨论/笔记/考试
- 点选验证码（need_code=2）不支持，直接报错；图形码（need_code=1）走进程内 ONNX OCR

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
```

### 4. 定价系统详解

#### 课程类型检测
```
"video"        - 有视频的课程
"exam_only"    - 纯考试 (无视频)
"homework_only"- 纯作业 (无视频)
"exam_homework"- 考试+作业 (无视频)
```

#### 价格计算逻辑
```
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
cd rust_worker
cargo run --release   # 启动在 http://localhost:17017（含前端静态页）

# 前端
cd frontend
npm install
npm run dev           # 启动在 http://localhost:5173，代理 /api 到 :17017
```

### 生产环境
```bash
# 构建前端
cd frontend && npm run build

# 构建并启动后端（唯一进程）
cd rust_worker && cargo build --release
./rust_worker         # :17017，API + SPA + OCR + 刷课一体
```

## 数据流

```
用户登录 -> 扫描课程 -> 获取价格(POST /api/pricing/calculate)
    -> 选择课程 -> 创建订单(POST /api/orders/batch)
    -> 支付 -> 接单 -> 入队 -> 进程内任务执行 -> 完成
```

## 部署架构

```
Nginx (443/80)
    └── /* -> proxy_pass http://127.0.0.1:17017
                └── rust_worker (axum, 单二进制)
                        ├── static/ (Vue3 SPA)
                        ├── SQLite (data/orders.db)
                        └── ONNX Runtime (验证码 OCR)
```

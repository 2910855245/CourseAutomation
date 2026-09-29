# 项目架构文档

## 项目概述

成都文理学院网课平台解决方案（仓库名 Anti-Course Cheating Plugin）：面向高校在线课程平台的自主学习管理工具，覆盖课程扫描、视频学习调度、考试辅助与聚合支付。后端为单个 Rust 二进制（axum），无 Python 依赖；前端为 Vue 3 SPA，由后端进程直接托管。

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
│       ├── progress.rs             # 实时推送中枢：WS（后台）+ SSE（客户端）
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

#### 营销推广（免费刷 / 邀请 / 刷课卡）
- 身份：访客第一次访问时由服务端下发 `vid`（HttpOnly cookie，一年有效）。
  邀请关系与卡片都挂在 vid 上，**不依赖浏览器 localStorage**；vid 丢失时凭领卡时
  填写的联系方式在后台 `brush_cards.contact` 人工找回。
- 免费：全局开关 `free_mode`，或持有效刷课卡（`card_valid_days` 天）。
  命中后订单 0 元、标记 `payment_channel='free'`、**直接入队**（不走支付与对账），
  档位**强制保守**（不付费只能用串行，见「三档节奏」）。
- 邀请：分享链接形如 `/?ref=<邀请码>`；中间件在链接落地时即记录邀请（不依赖前端上报）。
  `invite_require_order=1`（默认）时，好友下单才算一次有效邀请；每人只计一次、自己邀自己不计。
- 领卡：每满 `invite_threshold` 位有效邀请可领 1 张，可重复领取（`invite_threshold` /
  `card_valid_days` / `card_max_orders` 全部可在后台「营销推广」页改）。
- 页面与接口：客户页 `/#/invite`（邀请页）、首页结算条与公告展示资格；
  `GET /api/invite/me`、`POST /api/invite/claim`、`GET /api/me/benefit`、
  `GET /api/admin/promo/stats`。
- 数据表：`visitors`（访客 + 邀请码）、`invites`（邀请关系与转化）、`brush_cards`（卡）。

#### 公告（支持图片与联系方式）
`announcement_title` / `announcement_image` / `announcement_contact_type` /
`announcement_contact_value` 与正文一起存 system_config。图片支持外链或后台本地
压缩上传（长边 1080、转 jpeg，限 700KB，仅接受 http(s)/data:image）。

#### `schema.rs` - 数据库引导
- 15 张表 + 21 个索引，全部 `CREATE TABLE IF NOT EXISTS` 幂等
- ypay_account 列级补丁、`ypay_settings` ← `vmq_settings` 数据迁移
- `ai_usage`：每次 AI 调用的 tokens/费用/成功与否（后台看板的成本与成功率来源）
- `visitors` / `invites` / `brush_cards`：营销推广（见上）
- 每次启动经 `Db::open` 执行，可安全重复运行

#### 数据看板（`/api/admin/dashboard`）
口径（几个数字必须互相能对上，否则运营会误判）：
- 时间：**本地时间（北京时间）**。所有时间戳由 `queue::now_str()` 统一写入，
  见 `queue::LOCAL_OFFSET_SECS`；此前 Rust 版误用 UTC，日报会与营业日错开 8 小时。
- 收入：`实收` = 已收款（`paid=1` 或已记 `payment_time`）且未取消的订单金额；
  未收款单列 `receivable`；已收款但订单被取消的单列 `refund_due` 并给出待退款提醒。
- 完成率：分母为终态订单（完成+失败+取消），不把"刚下单还没跑"算进分母。
- AI：今日/近 7 天/累计的调用次数、tokens、缓存命中率、成功率与估算费用，按场景拆分。
- 异常信号：队列暂停/调度器停用/排队积压/卡单/超时执行/失败订单/退款待确认/AI 失败率偏高，
  由后端算好返回，前端只做展示（危险级排在前面）。

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
订单生命周期（客户视角只有三态）
创建 -> 待支付 -> 处理中 -> 已完成；失败 / 已取消 单独标出
（内部状态 queued/running/retrying 等不再暴露给客户，只在后台队列页可见）

API
POST /api/orders/batch        # 批量创建订单（价格与档位由后端强制）
GET  /api/orders/{id}         # 单条查单（游客用 view_token）
GET  /api/orders/             # 列表（管理员 Bearer）
POST /api/orders/clear-history
```

### 2. 任务执行（进程内 tokio 任务）

- 扫描/登录/刷课/考试全部在 rust_worker 进程内并发执行，无子进程
- 学校任务：登录（本地 OCR）→ 链式扫描+刷课 → **考试**（`exam`/`full` 订单）
- **考试环节**（`scan::solve_exams`）：视频刷完后按课程拉 `/user/study_record/exam`，
  只处理 is_actionable（未交/继续做题/在做）的考试，逐场交给 `exam::solve_exam` 作答，
  考试之间按所选档位错峰。只要有考试没做成，任务就返回失败交给队列重试
  （视频已完成，重跑只补考试）。总开关 `exam_solve_enabled`（默认开，关掉只刷视频）；
  AI Key 未配置时直接明确报错，不会静默跳过
- 学习通：`cx_study.rs` 刷课（enc MD5 签名 + dtoken + 上报循环），`cx_quiz.rs` 测评/讨论/笔记/考试
- 点选验证码（need_code=2）不支持，直接报错；图形码（need_code=1）走进程内 ONNX OCR
- 取消任务：管理端取消会 abort 真实运行中的 tokio 任务（任务表存 AbortHandle），
  不只是改库状态

#### 单视频时间轴（`study::study_video`）

一个视频要同时满足两个条件才算完成：**studyTime 报满**（`时长 - 已看时长`）与
**墙钟 ≥ 时长 × 2.1**（防平台 beginTime/finalTime 重叠检测）。两段采取的节奏不同：

| 阶段 | 节奏 | 原因 |
|------|------|------|
| `0 → 报满` | 1s 粒度推进，上报间隔随剩余时长自适应放大（1/3/5/10/15/20/30s） | studyTime 需要逐秒逼近目标 |
| `报满 → 2.1×` | 30s 一续报，最后一段按剩余时间**精确睡到终点** | 这段只是撑墙钟；原先每秒重复上报同一 studyTime，一个 45 分钟视频要多发约 3000 次无意义请求，且"1 秒不差"本身就是机器特征 |

`next_tick_secs` 有单测钉住这三条边界（未报满=1s、报满=30s、尾段精确）。
会话许可（`GLOBAL_STUDY_SESSIONS`）在整个视频生命周期内持有，等待期间不发请求。

### 3. 前端 (`frontend/`)

#### 页面流程
```
Home.vue (首页)
  ├── 登录 -> 扫描课程 -> 选择课程 -> 选择套餐 -> 下单 -> 支付
  └── 已登录用户直接进入课程选择

Admin.vue (管理员后台)
  ├── 财务报表（数据看板：KPI/趋势/异常信号/队列健康/AI 用量）
  ├── 订单管理
  ├── 队列监控（全部 / 学校平台 / 学习通）
  ├── 产品定价（打包/按量/AI 推荐）
  ├── 支付收款（YPay 配置与对账）
  ├── 系统通告
  └── 安全中心（DeepSeek Key、模型与能力开关、改密）
```

| 任务类型 | 默认值 | 配置项 |
|------|------|----------|
| 三档节奏 | turbo/balanced/gentle（标识不变） | 下单时选，落库到 `orders.speed_mode` |
| 暴力档 | 全量并行（8），无错峰 | turbo |
| 适中档 | 中等并发（4）+ 适度错峰 | balanced（默认） |
| 保守档 | **完全串行**：课程并发 1、扫描并发 1，课程间 30s 错峰 | gentle |

任何档位的并发上限都不得超过 8（平台重叠检测安全线），有单测兜住。
**免费单（全局免费或刷课卡）由服务端强制改写为保守档** —— 适中/暴力是付费权益，
前端置灰只是提示，真正的闸门在 `order.rs`（客户端传 turbo 也会被覆盖）。

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

对齐 DeepSeek 官方 API（2026-09 版）：对话补全 `POST /chat/completions`，
统一由 `rust_worker/src/llm.rs` 的 `LlmClient` 发出（超时/重试/记账集中一处）。

#### 模型配置
答题/测验/讨论共用同一个模型，键名 `deepseek_model`（默认 `deepseek-flash`），
在「安全中心 → 答题模型」里选。管理端另有 `deepseek_thinking`（思考模式）、
`deepseek_vision_ocr`（验证码视觉兜底）两个开关。

在售模型只有 `deepseek-flash`（V4.1-Flash）与 `deepseek-v4-pro`。
旧的 `deepseek-chat` / `deepseek-reasoner` 已于 2026-07-24 弃用；
老库里存着旧名字时，`llm::resolve_model` 会自动归一化（chat→flash 非思考、
reasoner→flash 思考），不需要人工改配置。

#### 用到的官方能力
- **思考模式**：`thinking:{type:enabled}` + `reasoning_effort`。考试答题首次
  作答置信度 < 0.6 时，用思考模式复核一遍（`exam::review_low_confidence`）。
- **JSON Output**：`response_format:{type:json_object}`，学习通批量答题用它替代正则抓取。
- **图像理解**：验证码在本地 OCR 连续三次识别不出时，用 `deepseek-flash` 看图兜底
  （`llm::recognize_captcha_vision`）。
- **上下文硬盘缓存**：前缀命中部分单价只有未命中的 1/50，因此 system prompt 保持固定前缀。
- **分时计价**：周一至周五 9-12 / 14-18（北京时间）为高峰，其余半价。

#### AI 成本
- deepseek-flash：输入 ¥1/百万tokens（缓存命中 ¥0.02）、输出 ¥4/百万tokens（空闲时段半价）
- 单门考试成本约 ¥0.01-0.05（极低）
- 每次调用后的 tokens 与估算费用写入 `ai_usage` 表，后台看板按
  今日 / 近 7 天 / 累计汇总，并按调用场景拆出成本占比

## 实时通道（进度推送）

`progress.rs` 是唯一广播入口（`broadcast(state, topic, kind, data)`），信封格式：

```json
{"v":1,"topic":"order:ORD-x","type":"order.update","data":{"order_id":"ORD-x","status":"running"},"ts":1759132800123,"seq":12871}
```

同一份广播喂两条通道，按**使用场景**分工，而不是两套机制并存：

| 通道 | 使用方 | 鉴权 | 为什么 |
|------|--------|------|--------|
| `GET /api/progress/ws/live` | 管理后台（桌面端） | 首帧 `auth`（管理员 JWT）/ `sub`（订单 view_token 列表）控制帧，5s 未表态关闭 | 需要双向控制帧；后台常驻桌面，不受手机省电约束 |
| `GET /api/progress/sse/live?orders=OID:token,...` | 客户端订单页（手机端） | 查询串里的订单凭证，逐条比对 `view_token`，无效直接 401 | 只需单向推送：原生 `EventSource` 自带重连（含退避），前端不必实现 ping / 半开检测 / 指数退避 |

服务端约束（两条通道一致）：

- **topic 过滤在服务端做**（隐私，不是性能）：载荷含订单相关文本，客户端过滤等于把别人的订单暴露给 DevTools。
- SSE 的凭证只能走查询串，因此**没有"关闭过滤"的开关**，不会因环境变量配错而全站广播。
- 心跳：WS 30s / SSE 40s（40s 既压住反代 60s 空闲超时，也不至于让手机基带频繁醒来）；
  SSE 另带 `Cache-Control: no-cache` 与 `X-Accel-Buffering: no`，防止反代把帧憋在缓冲区。
- 广播缓冲被冲掉（`Lagged`）时下发 `resync` 帧让前端重拉一次，避免界面静默停在旧状态。

客户端连接生命周期（省电的关键，`Orders.vue`）：**页面可见且还有未跑完的单才维持连接**，
切后台或全部终态立即断开；建连与自动重连成功各补拉一次全量；连续 3 次失败放弃重连
（`EventSource` 默认约 3s 一次且不封顶，对端异常时比重轮询更费电）。

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

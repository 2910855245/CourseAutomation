# 2026-10-16 关键修复：监控 APP 扫码配对/心跳/推送协议对齐（移植 Refine 的 APP 契约）

## 变更内容

- **根因**：本后端此前自造了一套 APP 方言 —— 配对二维码 `{"type":"pair","app":"ypay-monitor",...}`、
  心跳/推送挂在 `/api/ypay/vmq/heart|push`、心跳签名 `MD5(t+key)`。而那台 Vmq 监控 APP 是照
  Vmq/Refine 契约写死的：二维码必须 `t == "vmq-pair"`（否则直接判定"不是配对码"）、接口是
  `/api/ypay/app-heart|app-push|pair-confirm`（且 APP 会把 `/api/` 自动补成 `/pay/api/`）、
  心跳 `sign = MD5(key)`、推送 `sign = MD5(type+price+reallyPrice+key)`。两边对不上 ⇒ 扫码/配对/心跳全废。
- **修法**：新增 `app_compat.rs`，把 APP 侧契约原样补齐，同时挂 `/api/ypay/*` 与 `/pay/api/ypay/*`：
  `app-heart`（GET/POST）、`app-offline`、`app-push`、`app-info`、`pair-confirm`、`pair-status`，
  以及无前缀的旧兼容路径 `/appHeart`、`/appPush`。心跳成功后写 `ypay_last_heart`
  （后台「监控在线」徽标读的就是这个键）。
- **配对二维码**（`ypay_admin.rs::app_qrcode`）改为契约格式
  `{"t":"vmq-pair","v":1,"server":...,"key":...,"site":...}`，并额外回吐 `payload` / `content` 便于排查。

## 验收（对 127.0.0.1 与公网 course.refinely.top 双向验证）

- `sign=MD5(key)`：`/pay/api/ypay/app-heart`（GET 与 POST 表单）→ `{"code":0,"msg":"成功"}`；错签名 → `签名错误`
- `/pay/api/ypay/pair-confirm?key=<key>` → `配对成功`；错 key → `密钥不匹配`
- `pair-status` → `paired:true`；`app-info` → `status:"1"`
- 二维码 payload 实测：`{"key":"<16位>","server":"https://course.refinely.top","site":"...","t":"vmq-pair","v":1}`
- 公网 `https://course.refinely.top/pay/api/ypay/app-heart` → `{"code":0,"msg":"成功"}`

# 2026-10-16 修复：APP 下载二维码提示「不存在」

## 变更内容

- **根因**：`/api/ypay/app-download` 从 `static/ypay-monitor.apk` 读文件下发，但该文件已缺失
  （仓库里也从未有过），接口 404 返回 `{"code":-1,"message":"APK 文件不存在"}`。
  管理端「APP 下载」二维码指向的正是这个地址，于是扫码即显示「不存在」。
- **脆弱点**：`vite.config.ts` 设了 `emptyOutDir: true`，每次 `npm run build` 都会清空 `static/`，
  任何手工放进 static/ 的文件（如 APK）都会被下一次构建冲掉。
- **修法**：APK 改放 `frontend/public/ypay-monitor.apk`（vite 的 publicDir 会在每次构建时
  自动复制进 static/），并从该处补回 `static/ypay-monitor.apk` 让修复立即生效。
  APK 取自 Vmq-App-3.0 的最新构建 app-v3.8.apk。

## 验收

- `curl /api/ypay/app-download` → 200、`application/vnd.android.package-archive`、8,973,702 字节
- 公网 `https://course.refinely.top/api/ypay/app-download` → 200、同大小
- `course.refinely.top` 与 `refinely.top` 均 200

# 2026-10-15 修复：收款码图片上传按钮「点击没反应」

## 变更内容

- **根因**：`YpayTab.vue` 的「上传图片」用 `<input type="file" style="display:none">`
  + `triggerQrUpload()` 里 JS 程序化 `.click()`。这在移动端浏览器（及部分桌面浏览器）会被
  静默拦截 —— 按钮点了没有任何反应，也不报错。后端 `/api/ypay/decode-qr` 实测正常
  （真二维码 PNG 上传返回 `code:0`），故障纯在前端触发方式。
- **修法**：改为 `<label>` 原生触发文件选择（浏览器内建行为，各平台都可靠）；
  file input 由 `display:none` 改为视觉隐藏（clip），保留可点面积。
  随之删除 composable 里的 `qrFileInput` ref 与 `triggerQrUpload()`（不再需要）；
  `onQrFileChange` 改为直接用事件目标清空 input，不再依赖模板 ref。

## 验收

- `npm ci && npm run build`（vite 8 + rolldown）通过；新产物已上线并重启服务
- 线上 `Admin-*.js` 含 `qr-file-input` 标记；旧产物被构建清空（旧 chunk 404）
- `/health` 200、`course.refinely.top` 200、`refinely.top` 200；index.html 引用的 5 个产物全部 200

# 2026-09-29 刷课引擎改视频级调度（并行度不变、总时长显著缩短）

## 变更内容

- **调度粒度：课程级 → 视频级**。原来是"每课程一个任务、课程内部串行"，课程长度极不均时
  （真实账号实测同一批为 1 / 22 / 38 / 41 节）最长那门会独占槽位到最后，整单时长被拖成
  ≈ `2.1 × 最长课程工作量`；现在整单视频进一个并发池，所有槽位一起排空，时长趋近 `总工作量 / 并发数`
- **并发上界不变**：仍是档位决定的会话数（急速 8 / 均衡 4 / 温柔 1），
  平台可见的"beginTime/finalTime 重叠数"没有增加；队列按课程轮转取（A1 B1 C1 A2 B2…）
  避免整段时间集中在一门课
- **保守档语义不变**：1 路会话（一节课接一节课），错峰改在"拿到槽位之后"施加，
  因此仍是"上一节结束 → 停 30s → 下一节"；`is_serial()` 与相关单测照旧
- `SpeedProfile.course_concurrency` 更名 `video_concurrency`（语义从"课程数"变成"会话数"）；
  前端档位文案同步（暴力：8 路并行 / 适中：4 节 + 错峰）
- `platform_client` 请求间隔加测试钩子 `PLATFORM_REQUEST_SPACING_SECS`（默认仍 0.5s）

## 验收

- 新增 **mock 平台 E2E**（不碰真实平台）：起一个只实现上报端点的本地 HTTP 服务，记录每次
  上报时刻，端到端跑 `run_study` 并断言三条契约 —— ① 每个视频跨度仍满足 2.1× 安全比率；
  ② 任意时刻重叠会话数 ≤ 档位并发；③ 课程长度不均时整单耗时显著低于旧调度下界。
  实测：**8 节视频 10.5s 完成（旧调度下界 ≈29s，约 2.8×）**，最大重叠 4 路
- Rust 单测 70 passed、前端 `npm run build`（vue-tsc）通过

# 2026-09-29 删除刷课收尾的"平台进度复核"

## 变更内容

- 删除 `study::verify_platform_progress`（收尾时额外拉 `/user/study_record/video.json` 算账号维度完成率的"复核"）
  及其调用点：该接口不带 courseId，只能给出账号全量完成率，与本单实际选中的课程子集不是一回事，
  既不能当失败判据（代码里自己写着"参考信号"），还每次任务多打一次平台请求、多一条容易误读的 warn 日志
- 完成判据收敛为单点：每个视频由 `study_video` 自己判定（studyTime 报满 + 墙钟 ≥ 2.1×时长），
  订单级看 `failed` 计数 —— 前面每一步都判准了，收尾再做一次外部核查就是纯噪声
- 顺带删掉只为这条日志存在的 `pct` 局部变量

# 2026-09-29 手机端实时通道改 SSE + 商业规则收敛 + 死代码清理

## 变更内容

- **手机端省电**：订单页从「10s 轮询 × N 单」改为 **SSE 长连接**（`GET /api/progress/sse/live?orders=OID:token,...`）——
  逐条比对 `view_token` 才放行 topic（无效 401）、服务端过滤、40s 心跳注释、`no-cache` + `X-Accel-Buffering: no` 防反代缓冲、
  掉帧下发 `resync` 让前端重拉；前端用原生 `EventSource`，**可见且有未跑完的单才维持连接**，
  隐藏/全部终态即断开，连续 3 次失败放弃重连（避免自带重试变成重连风暴）
- **管理后台仍走 WS**：需要 `auth`/`sub` 控制帧，且后台在桌面端，不受手机省电约束（两通道分工见架构文档）
- **窄屏降耗**：≤768px 关闭粘顶栏/固定底栏的实时背景模糊（滚动每帧重算，GPU 常驻开销）
- **商业规则（服务端强制）**：免费单（全局免费/刷课卡）**强制保守档**、价格逐单以后端为准（堵住传 `price=0` 白嫖）、
  刷课卡按笔数扣额度、有效邀请只认已收款订单；`/api/admin/promo/stats` 移入鉴权组
- **算法优化**：单视频"撑墙钟"阶段由每秒空转/重复上报改为 **30s 续报 + 尾段精确睡到终点**
  （一个 45 分钟视频少发约 3000 次同内容请求，1 秒不差的节奏也不像机器），`next_tick_secs` 有单测
- **架构清理**：`api.rs` 五份 orders 列清单收敛为 `ORDER_SELECT` 唯一真源（此前 `vid` 漏选就是拷贝漂移导致）；
  删除 Python 时代遗留的 `status_file`/`cx_plan.json` 只写不读机制（每视频一次磁盘写），连带只写不读的 `Progress`
- **死代码**：删除已下线「风险监控」残留 CSS（Admin.vue / main.css）；`useHomeState` 删除只写不读的 `payOrders`
- **文档**：README 重写为《成都文理学院网课平台解决方案》；删除 `docs/BROWSER_TESTING.md` 与旧设计稿；
  架构文档新增「单视频时间轴」「实时通道」两节

## 验收

- Rust 单测 69 passed、前端单测 16 passed、`cargo build --release` 与 `npm run build`（vue-tsc）通过
- SSE 实测：无效凭证 401、有效凭证 `200 text/event-stream`、真实 `order.update` 帧直达对应订单、40s 心跳到达
- 真账号只读验证：`/api/courses/scan` 两个账号分别 3/3 与 2/3 平台登录成功（失败那个是平台密码不一致，非代码问题）

# 2026-09-29 UI 重构 + WebSocket 实时化 + 技术栈升级

## 变更内容

- **品牌统一**：FUCK → Fuk；主色由墨黑 `#17181b` 改为品牌蓝 `#0071e3`（原先首页主 CTA 一直是黑色）
- **设计系统**：引入 Naive UI（按需自动导入）作为组件层；`src/theme/index.ts` 为品牌色/字体/圆角的单一真源；暗色模式（`[data-theme="dark"]`，index.html 内联脚本首屏防闪，前台与后台顶栏均可切换）
- **零改动桥接**：`store.toast()` 改为「实现可注入」，由 ToastBridge 注入 Naive message；confirm 由 ConfirmBridge 适配 Naive dialog —— 约 100 处 toast、4 处 showConfirm 调用点一行未改
- **WebSocket 重写**：统一信封 `{v,topic,type,data,ts,seq}`；服务端 topic 过滤 + 首帧 `auth`/`sub` 鉴权（`AUTH_WS_REQUIRED` 灰度，默认关）；前端 realtime store 单例（指数退避重连、75s 无帧判半开）；修掉队列任务进度从不广播、Admin 监听死分支、Orders.vue 重复建两条连接三处缺陷
- **前台**：Orders 收到 `order.update` 只重拉该条订单（去抖 300ms），WS 断开时才 60s 兜底轮询；Admin 进度帧 800ms 去抖合并刷新
- **图表**：后台概览换 ECharts（收入折线 + 订单柱、状态分布横条），独立 vendor-echarts 懒加载块
- **Rust 依赖**：rand 0.8→0.10、jsonwebtoken 9→11（显式 rust_crypto provider）、rusqlite 0.32→0.40 + r2d2_sqlite 0.25→0.35（同升）、reqwest 0.12→0.13（需开 form feature）、tower-http 0.6→0.7、scraper 0.20→0.27、md5/base64/bcrypt/aes-gcm/libloading 升级；dashmap 不升（仅有 RC）
- **前端工具链**：vue 3.5 / vite 8 / TS 6 / vue-tsc 3 / pinia 4 / vue-router 5；vite 8 下 manualChunks 改函数式、`__dirname` 改 `import.meta.url`；构建 4.1s → 0.7s
- **修既存 bug**：后台「财务报表」整页空白（访问已删除的 `dash.users`）、`/admin` 登录入口死锁、OrdersTab 表格在 769~859px 撑破整页、支付收款两张空 src 裂图、`pay::test_floating_price` 随机失败

## 验收

- Rust 单测 38 passed、前端单测 16 passed、`cargo build --release` 与 `npm run build`（vue-tsc）通过
- 接口冒烟全 PASS：静态资源、公开 API、JWT 鉴权 API（含无 token 401）、DB 读路径、游客查单、WS 信封 topic 推导
- 浏览器巡检：前台 3 路由 + 后台全部侧栏项，浅/暗各一轮，无 console 错误、无裂图、无横向溢出；全站 WS 连接数 = 1

## 上线前专家审计（四路并行：功能盘点 / 稳定性 / 前端死代码 / 安全）

### 修掉的安全问题

- **推送令牌名对不上**：出站读 `RUST_DAEMON_PUSH_TOKEN`、入站校验 `WORKER_TOKEN`，只设其一的结果是二选一 —— 要么所有进度推送被 401（前端永远看不到进度），要么完全不校验（任何人可向全体 WS 订阅者广播伪造的订单/支付帧）。现在两个键名都认，且未配置时随机生成进程内令牌，零配置也不再可伪造
- **WebSocket 默认全量广播**：任何人连上就能看到所有人的 order_id 与进度文本。`AUTH_WS_REQUIRED` 改为默认开启
- **任意文件写入**：`/submit_exam`、`/submit_full` 的 `status_file` 直接来自请求体并落盘，可覆盖任意路径文件 → 连同 6 个无调用方的 daemon 遗留端点一并删除
- **命令与信息泄露**：`/api/orders/audit-log/{id}` 完全无校验（猜到订单号即可读操作日志）→ 改为与查单同一套鉴权；`/api/jobs/submit`（无鉴权写队列表）删除；`/api/system/status` 移入鉴权组；`/api/*` 未知路径不再回退成 200 + HTML（此前会让「调了不存在的接口」看起来像成功，排查方向被带偏）
- **弱密钥兜底**：`view_token` 的密钥源与管理员 JWT 不统一（缺失时会退化成可离线枚举）→ 统一；新增启动自检，`JWT_SECRET_KEY` 缺失/过短直接拒绝启动

### 修掉的稳定性问题

- **所有出站 HTTP 客户端都没设超时**：平台无响应/TCP 半开时请求永久挂住，占死队列 worker 与扫描并发许可，队列整体停摆且无日志 → 统一 connect 10s / request 45s
- **进程重启后 `running` 任务永不回收**：`claim_next_job` 只挑 pending/retrying，崩溃时留下的 running 行再无人认领，订单永久停在「执行中」→ 调度器启动时回收（幂等）
- **三处按字节切片 panic**：DeepSeek 错误响应预览、API Key 掩码、支付回调响应预览，遇到中文即随机崩溃 → 改为按字符截断

### 补齐的功能（此前后端整段缺失）

- **系统公告**：`GET /api/announcement` + 管理端发布/停用。此前前端「系统通告」页与首页弹窗都调不到接口，公告功能整条链路是断的
- **支付配置**：`/api/ypay/config/get|save|status`。支付通讯密钥存在 `ypay_settings` 表并用于回调签名，但唯一的写入口没迁移过来 —— 等于密钥无法在后台轮换，而这是钱相关能力；同时拒绝把密钥存成空串（那会让签名校验永久失败）

### 删掉的无效功能（点了必然 404）

- **网络代理**页 + 3 个接口：后端无路由，`platform_client` 也不读任何代理配置，整套表单存不了也测不了
- **风险监控**页 + 8 个 `domain-monitor` 接口：一个都不存在，「全面检查」「添加域名」「保存间隔」全部必然失败；平台可用性看队列失败任务的 error_message 即可
- **假的图形验证码**：登录页有验证码输入框和「获取验证码」占位图，但 `admin_login` 明确不校验、`/api/captcha/generate` 也不存在。填了不生效的字段比没有更容易出事
- 顺带：`useSystemConfig` 的 `tierNames`（代理分销残留）等无用导出

### 本轮验收

- `cargo test` 38 passed、`npm test` 16 passed、`cargo build --release` 与 `vue-tsc + vite build` 通过
- 真实服务上跑 34 项回归（默认部署与显式配置 `WORKER_TOKEN` 两种模式各一轮）：旧端点不再响应、`/api` 未知路径 404 JSON、push 无/错令牌 401 而正确令牌 200、已鉴权连接收到广播而伪造凭证的连接业务帧 0 条、公告发布→读取→停用全链路、支付配置读写与空密钥拒绝、audit-log 鉴权边界 —— 全 PASS
- 浏览器实测：**用真实账号密码完成一次后台登录**（验证码字段已移除后登录路径正常）、侧栏两个死页已消失、公告发布后首页弹窗出现且停用后消失、站点 console 错误 0

---

## 历史记录（已失效，仅存档说明）

2026-08 之前的条目描述的是已被替换的 Python / FastAPI 实现（`api/routers`、`services/*.py`、`requirements.txt`、granian 等），
当前仓库已不存在这些文件，唯一后端是 `rust_worker`（Rust + axum）。需要查阅当时的记录请走 git 历史：

```bash
git log --before="2026-08-14" --oneline
```

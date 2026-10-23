# 2026-10-23 「待开课」可补刷：开课后补刷成功即算完成

## 问题

上一条修复把「课程未开课」的订单转成了 `waiting`（待开课），但**没人能推进它**：
- 后台的「重试」按钮只对 `failed` 显示，waiting 的任务点不到
- 后端 `queue_job_retry` 的 SQL 也只匹配 `failed`/`cancelled`
- 于是这些单永远卡在"待开课"，客户既看不到结果、也补不了刷

## 变更内容

- **任务与订单都落 `waiting`**：此前任务落 `failed`、订单落 `waiting`，
  后台列表看到的是红色失败文案。现在统一为 waiting，显示「待开课」标签
- **waiting 可补刷**：后端 retry 的 SQL 纳入 `waiting`；
  前端 waiting 行显示「补刷」按钮（failed 仍是「重试」）
- **补刷不消耗重试额度**：`retry_count` 用 CASE 判断，仅 failed/cancelled 才 +1。
  管理员可能开课后点一次、没刷完过几天再点一次，都不该把额度推到上限后卡死
- **补刷时清空订单旧文案**：上一轮的"尚未开课"说明留着会让订单页显示过期信息；
  同时订单从 waiting 拉回 queued，补刷成功后由 `sync_order_state` 写成 completed
- waiting 是终态，不再提供「取消」（原来同时有「取消」和「补刷」两个按钮，
  语义重复且「取消」会把订单置 cancelled —— 与"等开课补刷"背道而驰）
- 历史数据迁移：5 条因未开课判 failed 的任务改为 waiting

## 验收

- 接口实测：waiting 任务调补刷 → 200，任务 `waiting → retrying`，
  `retry_count` 保持 4 不变，订单 `waiting → queued` 且旧文案清空
- 调度器认领后重新识别为未开课 → 回到 waiting，不判失败、不重试
- 服务器 138 个 Rust 测试全绿；新增单测用真实 DB 验证补刷的 UPDATE 语义
  （waiting 不加计数 / failed、cancelled 各加 1）

# 2026-10-23 后台队列列表显示客户姓名

## 变更内容

后台「队列监控」的任务列表原先只有学号（`251060150507`），人工核对客户很费劲。
现在显示**姓名 + 学号**（姓名在上、学号在下），拿不到姓名时退回只显示学号。

## 姓名的来源与采集

- 平台课程列表页（`/user/index`）的用户资料区本来就带姓名：
  `<div class="name">王国梁 <span style="color:#65d23c">251060150507</span></div>`
  三个学校平台结构一致（2026-10-23 实测）
- **零额外请求**：扫描本来就要拉这个页面，姓名从同一份 HTML 里顺带解析
  （`scan::parse_student_name`），不发第二次请求
- 落库两条路径，互为补充：
  - 下单时前端把扫描拿到的 `student_name` 带上 → `orders.customer_name`
    （该字段早已存在但一直没有写入方）
  - 刷课/手动执行时再次采集兜底（覆盖历史订单与老前端），
    由 scan 层经出参回传给调用方落库 —— scan 层不碰数据库，
    保持既有的分层（见 `scan.rs` 里 DURATION_CACHE 的说明）
- 写入策略：**只在订单还没有姓名时写**，不覆盖已有值
- 列表接口 `/api/queue/jobs` 用 `LEFT JOIN orders` 取姓名，
  队列表不需要加列

## 历史数据回填

61 个历史账号用服务器上已存的会话 cookie 批量取名，
6 个账号取到（更新 14 行订单）。其余 55 个 cookie 已失效，
取不到 —— 下次这些账号再下单时自动补上。

## 验收

- 接口实测 `/api/queue/jobs`：74 条任务中 11 条带姓名，
  截图里的 4 个账号（王国梁 / 陈果 / 陈塬丰 / 张俊秋）全部命中
- 服务器 137 个 Rust 测试全绿；本地 135 个全绿；前端构建通过
- 数据库已备份 `data/orders.db.bak-before-namebackfill-20261023`

# 2026-10-23 修「课程尚未开课」被误判失败（白刷 6000+ 次上报）

## 事故

- 10-21 起公益课程平台（website_id=3）课程 `1021759《服务学习与朋辈实践》`
  的订单连续失败：近 4 天 1438 条错误全部是同一句
  `平台连续拒收上报 6 次（课程还未开始!），这一节平台没记上`
- 根因：**该课程开课时间是 2026-10-26**，平台对整门课下所有节都拒收上报。
  这是学校的硬时间闸，不是我们的错 —— 但系统不认识这个闸，
  于是每节重试满 6 次（45 节 × 6 × 3 轮 ≈ 81 分钟/单）后把订单判失败
- 代价：8 单被误判失败（客户看到"失败"），白扔 6000+ 次注定被拒的上报

## 变更内容

三处配合，缺一不可（只改任一处都还会漏）：

- **扫描侧提前挡（`scan.rs`）**：课程列表页 `.time` 节点本来就有「开课时间」，
  现在解析成 `CourseItem.start_ts`；开课日未到的课程**不入队**，
  一个上报请求都不发。解析不到时间（`start_ts=0`）时按"无闸"处理，不误伤正常课
- **上报侧识别（`study.rs`）**：新增课程级闸 `course_not_started`
  （认「课程还未开始!/课程尚未开始/课程尚未开课」），
  遇到即 bail 终止本门课，不再逐节重试；失败分类新增 `CourseNotStarted`，
  **不计失败**（与章节级时间锁同待遇），并登记课程 id →
  该课程剩余节直接跳过，不再发起请求
- **队列与订单层（`queue.rs`）**：新增 `course_not_started_error`，
  此类错误**不进重试路径**（重试多少次平台都会拒收），
  任务直接终态，订单转 `waiting`（前端显示「待开课」）而非 `failed`；
  附说明「开课后重新提交即可自动补刷」
- 前端：用户端订单页新增「待开课」标签 + 详情里的「待开课说明」，
  该状态不画进度条（它没在刷课）；后台 `waiting` 文案由「等待明天」改为「待开课」

## 验收

- 实机验证：把失败任务 `JOB-B1D32E6320` 重新入队 → **1 秒内**终止，
  日志「尚未开课：《服务学习与朋辈实践》（2026-10-26 开课）」；
  订单 `ORD-D36A5CA1` 转 `waiting`，未判失败
- 旧逻辑同一任务需 81 分钟 × 3 轮
- 服务器 136 个 Rust 测试全绿；本地 134 个全绿；前端构建通过
- 同批另一门正常课程（website_id=1）照常刷课，无回归

## 顺带同步

服务器源码此前领先 git（10-14~10-16 的线上修复未入库），本次一并补回仓库：
上报响应保留原文（504 诊断）、复核空列表重试、登录失败文案去重前缀、
后台「重试」把订单拉回 queued、`app_compat`（APP 端 /api/ypay 契约）

> 服务器无 git 仓库，部署走文件覆盖 + 服务器本机 cargo 构建（非 git pull）

# 2026-10-12 删除公告的「联系方式」附加项

## 变更内容

- 前台已有右下角悬浮「加群」按钮（读 `/api/site/links`），公告弹窗里再挂一份
  「联系方式 + 一键复制」是重复入口，整条链路删掉：
  - 后台「系统通告」页：移除联系方式类型下拉 + 输入框
  - 前台公告弹窗：移除联系方式行与「复制」按钮（`copyAnnouncementContact` 一并删除）
  - 后端 `announcement_get` / `announcement_publish`：不再读写
    `announcement_contact_type` / `announcement_contact_value` 两个配置键
- 公告保留 标题 / 图片 / 正文 / 我知道了；「交流群与赞赏」卡片与悬浮「加群」按钮不受影响
- 顺手清掉库里遗留的这两个配置键（无数据）

## 验收

- 线上 `/api/announcement` 响应不再含 `contact_type` / `contact_value`
- 线上产物核对：`Home-*.js` 已无「联系方式已复制」、`Admin-*.js` 已无联系方式输入项
- 两站体检 200（course.refinely.top / refinely.top）

# 2026-10-12 新增风控「拉黑管理」页：账号黑名单 + IP 黑名单 + IP 限制

## 变更内容

- 后台新增独立页签 **拉黑管理**（`BlacklistTab.vue` + `useBlacklist`），四张卡片：
  账号黑名单 / IP 限制 / IP 黑名单 / 下单来源记录。订单管理页保持原样
  （原先挂在订单行上的「拉黑」按钮与筛选栏的黑名单面板已撤掉，页面回到清爽状态）
- **账号黑名单**（`account_blacklist`，判定只看 username）
  - `school_exam::scan_courses` / `scan_chaoxing`：一进门（扫描）就拦下
  - `order::create_batch_orders`：下单/刷课的权威闸门，返回 `blacklisted: true`
  - 前台弹窗「该账号已被本平台拉黑，无法享用免费刷课」
- **IP 黑名单**（`ip_blacklist`，判定只看 IP）
  - `guard::ip_guard` 中间件：命中即全站 403（含静态页），返回 `ip_blocked: true`
  - 命中集合缓存在进程内 DashMap，启动载入、增删同步，中间件不做库查询
- **IP 限制**（`ip_submissions` + `system_config` 三个键，后台可视化调整）
  - 同一 IP 在窗口内最多提交 N 个**不同**学号（默认开 / 5 个 / 24 小时）
  - 只有不同学号吃额度：同一学号重试、重复提交不会把额度耗光
  - 超限时下单返回 `ip_limited: true`，前台弹窗「当前网络地址提交的账号数量已达上限」
  - 用来治「一台机器替几十个人代刷赚钱」；`ip_records` 按 IP 聚合出
    「几个不同学号 / 提交几次 / 最近一次」，运营照着这个列表一键拉黑
- **修掉一个会让上面两个功能形同虚设的洞**：`guard::client_key` 原先取
  `X-Forwarded-For` 的**第一个**值，而 nginx 用的是 `$proxy_add_x_forwarded_for`
  （"客户端自带的, 真实对端"）—— 客户端自己写在最前面的那段是可控的，
  等于一句 `-H 'X-Forwarded-For: 随便写'` 就能换 IP 绕过黑名单与限制。
  改为取**最后一个**非空值（真实对端），限流一并受益
- 路由全部挂在 api.rs 的管理员鉴权组，匿名访问 401；拉黑/解除动作写 `audit_logs`

## 验收

- 线上实测（脚本内自证 + 自清理）：
  - 账号黑名单：`/api/orders/batch`、`/api/courses/scan`、`/api/courses/scan/chaoxing`
    对拉黑学号均返回 `blacklisted:true` + 文案
  - IP 限制：临时 max=2 时，第 3 个不同学号被拒（`ip_limited:true`），
    已提交过的学号再次提交仍放行；测完恢复默认并清掉测试记录
  - IP 黑名单：`X-Forwarded-For: 10.99.99.99` → 403；
    `X-Forwarded-For: 1.2.3.4, 10.99.99.99` → 仍然 403（伪造前缀无效）；
    未拉黑 IP → 200；非法 IP 字面量被接口拒绝；测完解除
- 前端 `npm run build`（vue-tsc + vite）通过；线上产物核对新页签与新接口路径
- 两站体检 200（course.refinely.top / refinely.top）

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

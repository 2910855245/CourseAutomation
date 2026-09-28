# 蓝白 UI 重构 + WebSocket 实时化 + 技术栈升级

## 实施结果（2026-09-29 收尾）

| 阶段 | 状态 | 说明 |
|---|---|---|
| Phase 0 工具链升级 | ✅ 完成 | vue 3.5.43 / vite 8.3.1 / TS 6.0.3 / vue-tsc 3.3.11 / pinia 4 / vue-router 5；改函数式 manualChunks + `import.meta.url`；构建 4.1s → 0.73s。TS 7.0.2 不可用（删除 `./lib/tsc` 导出，vue-tsc 依赖该路径）→ 落在 6.0.3 |
| Phase 1 设计系统 | ✅ 完成 | 蓝白 `#0071e3` + 暗色模式 + Naive UI provider 链 + toast/confirm 零改动桥接 + `src/theme/index.ts` 单一真源。**偏离**：未引入 `unplugin-auto-import`（全仓库本就显式 import，自动导入只带来隐式全局）；`main.css` 瘦身**未做** —— 手写组件样式仍在被 Admin 的 10 个 tab 使用，须与 Phase 3 的逐个迁移同步删除，先删会造成整片页面失去外观 |
| Phase 2 实时化 | ✅ 完成（不含支付轮询） | 信封 + 服务端 topic 过滤 + 首帧 `auth`/`sub` 鉴权 + `realtime.ts` 单例 + Orders 局部重拉。**偏离**：支付相关 3s 轮询保留 —— YPay 聚合支付没有服务端事件源，无事件可订阅 |
| Phase 3 后台 Naive 化 | ⚠️ 部分 | 已完成：概览两处手搓图表换 ECharts、管理端顶栏主题切换、支付收款裂图、769~859px 表格撑破页面。未做：10 个 tab 的控件逐项换成 Naive 组件、RiskTab 手绘 SVG 仪表盘换 ECharts（现 SVG 环观感已符合设计语言，换 ECharts 属横向改动，收益低） |
| Phase 4 Rust 依赖升级 | ✅ 完成 | 7 个提交逐个升级并验证；`dashmap` 按计划不升（仅有 7.0.0-rc） |
| 计划外 | — | 修掉 5 个既存 bug（财务报表空白、`/admin` 登录死锁、表格撑破页面、裂图、`test_floating_price` 随机失败） |

完整变更与验收见仓库根目录 `CHANGELOG.md` 的 2026-09-29 条目。

---

## 背景与目标

用户要求三件事：

1. **整体美化 UI** —— 参考 GitHub 上同类项目的观感，由我完成设计（用户明确「美化ui你来设计」）。
2. **该用 WebSocket 的地方改用 WebSocket** —— 消除轮询与手动刷新。
3. **把老旧技术升级到最新** —— 前端工具链 + Rust 依赖。

**关于「去 GitHub 搜索」的结论**：WebSearch 两次失效（第一次返回完全不相关的中文政务 PDF，第二次限定 `github.com` 后直接空结果）。经与用户确认，改为由我自行设计，方案锚定在成熟的 Vue3 后台实践（Naive UI + 品牌色主题），并遵循用户一贯偏好：**白底 + 蓝 `#0071e3`、克制动效、界面简洁**。

### 改造前现状（已实测）

| 项 | 现状 |
|---|---|
| 样式 | 约 1.2 万行手写 CSS，**无任何 UI 组件库/图表库**；当前是纯黑白单色（`--c-primary: #17181b`），**仅浅色模式** |
| WebSocket | 只有 1 个广播通道，**订阅端完全无鉴权**；前端监听了后端从未发送的 `job_update`/`order_update` 死分支；`queue.rs` 硬编码 `push_ws: false` → 队列任务进度**从不广播**，管理端只能手动刷新 |
| 轮询 | 4 处 3 秒轮询（支付/队列测试），最长 120 次 ≈ 6 分钟 |
| 已知 bug | `Orders.vue` 在 `onMounted` 里**重复调用两次 `connectWS()`**；`Admin.vue` 使用**非 scoped `<style>`** 泄漏到全站 |
| 技术栈 | vue 3.4 / vite 5 / TS 5.4 / pinia 2；Rust 侧 rand 0.8、jsonwebtoken 9 |

### 目标产物

- 全站白蓝设计系统（含暗色模式），组件统一为 Naive UI，`main.css` 从 ~1049 行压缩到 ≤250 行（仅保留令牌层 + 布局壳）。
- 一套**带鉴权、带 topic 隔离**的 WebSocket 实时层，替代 4 处轮询与 3 处手动刷新。
- 前端工具链与 Rust 依赖升级到最新稳定版，每步可独立回滚。

---

## 用户已确认的决策

1. UI 实现方式：**引入 Naive UI**（替换手写 CSS 组件）。
2. 配色：**回到白蓝 `#0071e3`** + 暗色模式。
3. 覆盖范围：**分期 —— 先前台，后后台**。
4. 技术升级：**安全升级 + Rust 依赖**。

---

## 关键事实（已用 `npm view` / `cargo search` 实测，非推测）

### 前端版本矩阵

| 包 | 当前 | 最新 |
|---|---|---|
| vue | ^3.4.21 | 3.5.43 |
| vue-router | ^4.3.0 | **5.3.1**（4.x 末版 4.6.4） |
| pinia | ^2.1.7 | **4.0.3** |
| vite | ^5.1.6 | **8.3.1** |
| typescript | ^5.4.2 | **7.0.2**（5.x 末版 5.9.3；另有 6.0.3） |
| vue-tsc | ^2.0.6 | 3.3.11（依赖 `@volar/typescript@2.4.28`） |
| @vitejs/plugin-vue | ^5.0.4 | 6.0.9 |
| naive-ui | — | 2.45.3（peer 仅 `vue ^3.0.0`，安全） |
| echarts / vue-echarts | — | 6.1.0 / 8.3.1 |
| unplugin-vue-components / auto-import | — | 32.1.0 / 21.1.0 |

本地环境：node v24.15.0、npm 11.12.1、rustc 1.97.1，满足全部 engines。

> **重要修正**：vue-router@5.3.1 的 `vite` / `pinia` / `@pinia/colada` / `@vue/compiler-sfc` peer **全部标记为 optional**（已查 `peerDependenciesMeta`）。因此**不存在「必须原子升级」的硬约束**，Phase 0 可以拆成可回滚的小步提交。

### Rust 版本（`cargo search --registry crates-io`）

`rand 0.10.3`、`jsonwebtoken 11.1.0`、`rusqlite 0.40.2`、`r2d2_sqlite 0.35.0`、`scraper 0.27.0`、`reqwest 0.13.5`、`tower-http 0.7.1`、`md5 0.8.1`、`aes-gcm 0.11.1`、`bcrypt 0.19.3`、`base64 0.23.1`、`libloading 0.9.0`。
`dashmap` 只有 `7.0.0-rc2` → **不升**（不引入 RC）。

**必须同升的一对**：`r2d2_sqlite@0.35.0` 依赖 `rusqlite ^0.40`（已核实 sparse index 元数据），故 rusqlite 与 r2d2_sqlite 必须同一次提交。

### 破坏性升级的精确调用点（已 grep）

- **rand 0.8 → 0.10**（`thread_rng`→`rng`、`gen`→`random`、`gen_range`→`random_range`、`StdRng::from_entropy`→`from_os_rng`）共 13 处：`api.rs:763,941`、`school_exam.rs:107`、`scan.rs:209,311`、`cx_study.rs:16,261,281`、`exam.rs:123`、`pay.rs:125`、`study.rs:155,297`、`ypay_db.rs:681`。
  ⚠️ `scan.rs:311` 用的是**全限定路径** `rand::Rng::gen_range(...)`，机械替换 `gen_range` 会漏掉。
- **jsonwebtoken 9 → 11**：仅 `auth.rs:10,36,42` 三处。改用显式 `Validation::new(Algorithm::HS256)` 替代 `default()`，把 `validate_exp`/`required_spec_claims` 语义钉死。
- **rusqlite 0.32 → 0.40**：影响面最大（`query_row`/`params!`/`prepare`/`execute`/`transaction` 合计 ~150+ 处，集中在 `api.rs`、`ypay_db.rs`、`queue.rs`）。宏与主要签名稳定，风险在 `Row::get` 索引类型、`transaction()` 的 `&mut` 借用、`rusqlite::Error` 新增变体导致 `match` 非穷尽。

---

## 实施计划（5 个阶段，每阶段结束时应用完整可用）

### Phase 0 — 工具链升级（无功能改动）

**文件**：`frontend/package.json`、`frontend/vite.config.ts`、`frontend/tsconfig*.json`

**步骤**（每个一个 commit，便于单独回滚）：
1. `vue 3.5.43`（minor，安全）。
2. `vite 8.3.1` + `@vitejs/plugin-vue 6.0.9`。
3. `pinia 4.0.3`。
4. `vue-router 5.3.1`（若有 API 破坏则回退 `4.6.4`，功能不受影响）。
5. `vue-tsc 3.3.11` + `typescript`：**先试 7.0.2**；若 `vue-tsc` 与 TS 7 的原生 Compiler API 冲突，回退 **6.0.3**，再不行回退 **5.9.3**（`vue-tsc` peer 为 `typescript >=5.0.0`，5.x 必兼容）。
6. `tsconfig` target `ES2020 → ES2022`。
7. `vite.config.ts` 的 `manualChunks` 改为函数式，先产出 `vendor-vue` 单块。

**验收**：`npm ci && npm run build && npm test`，启动后端点通 5 条路由（`/`、`/orders`、`/admin`、`/payment/:id`、`/orders/:id`）无白屏。

### Phase 1 — 设计系统落地（蓝白 + 暗色 + Naive 骨架）

**文件**：新建 `frontend/src/theme/index.ts`、`frontend/src/components/ToastBridge.vue`；改 `vite.config.ts`、`main.ts`、`App.vue`、`stores/app.ts`、`composables/useConfirm.ts`、`styles/main.css`、`index.html`、`views/Admin.vue`

**严格顺序**（前两步必须先做、单独提交，否则视觉回归无法归因）：
1. **修 `Admin.vue` 非 scoped `<style>` 全局泄漏**：枚举泄漏类名 → 被外部依赖的提升到 `main.css` → 余下加 `scoped`，必要时 `:deep()`。
2. **`--c-primary` 由 `#17181b` 改为 `#0071e3`** —— 全站立即变蓝白（`.btn-primary`、`.tab-btn.active`、`.kpi-*` 等遗留类都引用该变量），此时先跑一遍看回归。
3. 引入 Naive UI：
   - `unplugin-vue-components` + `unplugin-auto-import` 自动导入，`dts` 输出到 `src/types/`（`tsconfig` 的 `include` 已含 `src/**/*.d.ts`），**并把生成的 `components.d.ts` / `auto-imports.d.ts` 提交进 git** —— 因为 `build` 脚本是 `vue-tsc --noEmit && vite build`，首次 clone 时 dts 尚不存在会导致构建失败。
   - `Components({ resolvers: [NaiveUiResolver()], dirs: [] })` —— `dirs: []` 是刻意的：只让 resolver 管 `n-*`，自有组件保持显式 import，避免 1805 行的 `YpayTab` 被隐式注入。
4. Provider 链放 `App.vue`（`useMessage()` 必须在 provider 后代调用，故需 `ToastBridge` 子组件桥接）：
   `n-config-provider → n-loading-bar-provider → n-dialog-provider → n-notification-provider → n-message-provider → ToastBridge + router-view + ConfirmBridge`
   - `:preflight-style-disabled="true"` —— `main.css` 已有自己的全局重置，让 `main.css` 独占，避免叠加闪烁。
5. **toast 零改动桥接**：`stores/app.ts` 保留 `toast(message, type)` 签名，改为「实现可注入」——`setToastImpl(fn)` 由 `ToastBridge` 在 `onMounted` 注入 `message[t](m, {duration: 3500})`，卸载时置空并回退到原 `toasts` 数组。**约 50 个 `store.toast(...)` 调用点一行不改**；`App.vue` 里原 toast Teleport 与 CSS 随之删除。
6. `useConfirm` 内部代理到 `useDialog().warning({...})`；`ConfirmDialog.vue` 暂留，待 Phase 3 末删除。
7. **主题单一真源**：`theme/index.ts` 定义 `brand`（`primary #0071e3`、hover `#1a80e6`、pressed `#005bb8`、suppl `#3d94ea`、faded `rgba(0,113,227,.10)`）+ `GlobalThemeOverrides`（圆角对齐现有 `--radius-*`：`borderRadius 10px == --radius-md`、`borderRadiusSmall 6px`，字体对齐 `--font`）；`main.ts` 启动时把 `brand.*` 反写进 `--c-primary*` 等 CSS 变量，让 Naive 与 `main.css` 共用一份真源。
8. 暗色模式：`n-config-provider :theme="isDark ? darkTheme : null"` + `document.documentElement.dataset.theme` + `main.css` 增加 `[data-theme="dark"]` 覆盖壳层变量；初始值取 `useOsTheme()`，持久化 `localStorage.theme`。**同步升级 `index.html` 的首屏防闪内联脚本**（现为硬编码 `#f7f7f8`），否则暗色下会白闪一下。
9. `main.css` 瘦身：保留令牌层、布局壳、`.page-*` 命名空间下的页面专属样式、`prefers-reduced-motion` 块；删除 `.btn*`/`.field*`/`.card|.panel|.modal-*`/`.table-*`/`.tab-switcher`/`.spinner*`/`.chip|.pill*`（迁移到 Naive 组件）。

**验收**：`npm run build`（`vue-tsc` 必须过）；人工检查首页按钮、订单页表格、模态、toast、确认框全部蓝白；切暗色刷新无白闪；`git diff` 确认 50 处 `store.toast(...)` 未被修改。

### Phase 2 — 前台实时化（WebSocket，后端 + 前端）

**文件**：`rust_worker/src/progress.rs`（重写 `ws_live` + 新增 `broadcast`）、`main.rs`、`queue.rs`、`api.rs`；前端新建 `frontend/src/stores/realtime.ts`，改 `Orders.vue`、`Payment.vue`、`composables/useHomeState.ts`、`composables/usePayments.ts`

**消息封装**（扁平 topic + 前缀通配）：
```json
{"v":1,"topic":"order:ORD-xxx","type":"order.update",
 "data":{"order_id":"ORD-xxx","status":"running","progress":42},
 "ts":1759132800123,"seq":12871}
```
topic：`order:{id}` / `queue` / `dashboard` / `payment:{trade_no}`；type：`order.update`、`job.update`、`queue.stats`、`dashboard.stats`、`payment.success` + 控制帧 `auth`/`sub`/`subscribed`/`error`/`heartbeat`/`pong`。

**子阶段**（保证可回滚）：
- **2a 后端**：envelope + `progress.rs::broadcast(&AppState, topic, type, data)` helper（禁止各模块手搓 JSON）+ 频道载荷由 `String` 改 `Arc<str>`（仅 4 处：`main.rs:60,99`、`progress.rs:37,48`，fan-out 变 O(1)）。`push_progress` 收到裸 JSON 时**包一层 envelope 再广播**，这样 `study.rs:353`、`cx_study.rs:475` 两处既有 HTTP 推送**零改动**即产出合规范消息。
  - **最高性价比的两行**：`queue.rs:179` 的 `push_ws: false` → `true`；`queue.rs:182` 的 `run_scan_and_study(&task, "", "")` → 传 `&state.push_url` / `&state.push_token`（`AppState` 早已持有这两个字段）。`api.rs` 的手动执行同理。
  - 广播点收口：`queue.rs::update_job` 改为唯一扼流点（签名由 `&Db` 改 `&AppState`，UPDATE 成功后发 `job.update` + 对 `job.order_id` 发 `order.update`）；`api.rs::transition_order` / `admin_order_fail` / `order_delete` / `enqueue_order_impl` 各发 `order.update`；支付成功（`vmq_push`、`pay_routes` 的 check）发 `payment.success`。
  - **灰度开关 `AUTH_WS_REQUIRED`，默认关闭**。
- **2b 前端**：`stores/realtime.ts`（Pinia setup store，**模块级单例**，全标签页**仅一条连接**）——`ensure()` 幂等建连、`subscribe(topics, handler)` 返回退订函数、`renewGuestScope(orders)` 提交 `view_token`；重连退避 `min(30s, 500ms·2^n) × (0.5+rand·0.5)`，`online`/`visibilitychange` 立即重连；客户端 25s `ping`，75s 无帧判半开主动重连（当前代码完全没处理 TCP 半开）。
  - `Orders.vue`：删除 L17-33 的 `connectWS`、**修掉 L144/L173 重复连接**，改为 `realtime.subscribe(...)`；回调由「整表重载」升级为**按 order_id 局部 patch**；`onUnmounted` 退订。游客侧把每单 `view_token` 通过 `sub` 帧上报。
  - `Admin.vue`：删除 L86-107 的 `connectAdminWS`，改由 store `ensure()`。
- **2c 打开 `AUTH_WS_REQUIRED=true`，删除轮询**。

**WS 鉴权设计**：**首帧 auth/sub 信封**（不用 query param，因为游客必须做**逐订单**鉴权，一次握手参数表达不了 N 个 `view_token`；首帧机制无论如何都要有，就不必维护两套路径）。
- `{"type":"auth","token":"<admin JWT>"}` → `role=Admin`，`allowed=["*"]`（复用 `auth.rs::verify_token`）。
- `{"type":"sub","orders":[{"order_id":"ORD-x","view_token":"..."}]}` → 逐条校验 `== order::view_token(order_id)`（`order.rs:20`，前端**已持有**）→ `role=Guest`，`allowed={"order:ORD-x",...}`。
- 校验失败**只回 `error` 帧、不关连接**（游客页可能同时持有效+失效订单）；5s 未鉴权则关连接（码 4401）。
- **topic 过滤放在服务端**：理由不是性能而是隐私 —— `study.rs` 推送里含 `message` 文本，若客户端过滤，任何人开 DevTools 就能看到**别人订单**的进度与 order_id；而当前「WS 完全开放」状态下这已是既存缺陷。
- 保留对裸字符串 `"ping"` 的兼容应答（`progress.rs:70`），因为改动窗口期新旧前端会共存。

**轮询删除对照**：

| 现有轮询/手动刷新 | 替换为 | 保留兜底 |
|---|---|---|
| `Payment.vue:116-267` 3s×120 | 订阅 `payment:{tradeNo}` + `order:{id}` | 首帧立即查一次 |
| `Orders.vue:241-267` 3s×120 | 订阅自有 `order:*` | 60s 慢轮询 |
| `useHomeState.ts:477-493` 3s×120 | 同上 | 同上 |
| `usePayments.ts:133-144` 3s×60 | 订阅 `payment:{tradeNo}` | WS 非 open 时保留 3s |
| `useDashboard.ts:16` 手动 | 订阅 `dashboard` | 保留手动刷新按钮 |
| `usePayments.ts:23-26` 手动 | 订阅 `queue` | 同上 |
| `useOrders.ts:21` 手动 | admin 订阅 `order:*` | 同上 |

**验收**：两个浏览器窗口 —— 窗口 A 在 admin 点「执行」，窗口 B 的订单页应在 1s 内**自动**看到状态变化（Phase 2 之前这不可能）；游客页只有 `view_token` 时能收到自己的进度，且 DevTools 里看不到别人的 `order_id`；断网 10s 恢复后自动重建连接；`cargo test`。

### Phase 3 — 后台 Naive 化 + 图表

**文件**：`views/Admin.vue` 与 12 个 admin tab；`vite.config.ts`

1. **先拆 `YpayTab.vue`（1805 行）**为 4 个子组件（配置卡 / 订单表 / 测试面板 / 回调日志），用 `git mv` 保留 blame；**纯拆分、逻辑零改动**，拆完先跑 `npm run build` 确认无行为差异。
2. 再逐个用 `n-tabs`/`n-card`/`n-data-table` 重写：`OverviewTab`（手搓 div 柱状图 → `vue-echarts`）、`RiskTab`（手搓 SVG 环形 → echarts `gauge`）、`QueueTab`、`OrdersTab`、`ProxyTab`、`SecurityTab`、`PricingTab`、`AnnouncementTab`。
3. 删除 `ConfirmDialog.vue`，`main.css` 收尾瘦身。
4. `manualChunks` 拆为 `vendor-vue` / `vendor-naive` / `vendor-echarts`；echarts 走 `echarts/core` + `use([...])` 按需注册（naive-ui 传递依赖含 lodash / date-fns / highlight.js，不拆会让 vendor 块爆炸）。

**验收**：`npm run build`、`npm run lint`；逐 tab 点开比对；`ls -la ../static/assets` 确认无单 chunk 超 ~500KB。

### Phase 4 — Rust 依赖升级（隔离、逐 crate）

顺序（每个 crate 一个 commit，每个都 `cargo build --release` + `cargo test`）：
1. 补丁级（零风险）：`axum 0.8.9`、`tokio 1.53.1`、`tracing-subscriber`、`serde`/`serde_json`、`anyhow`。
2. `reqwest 0.12→0.13.5`、`tower-http 0.6→0.7.1`（major，注意 `main.rs` 的 layer 组合与 feature 名）。
3. `rand 0.8→0.10.3`（13 处，注意 `scan.rs:311` 的全限定调用）。
4. `scraper 0.20→0.27`（需真机跑一次扫描验证选择器）。
5. `rusqlite 0.40.2` + `r2d2_sqlite 0.35.0`（**必须同一次提交**）。
6. `jsonwebtoken 9→11.1.0`（`auth.rs` 3 处，显式 `Validation::new(Algorithm::HS256)`）。
7. 杂项：`md5 0.8.1`、`aes-gcm 0.11.1`、`bcrypt 0.19.3`、`base64 0.23.1`、`libloading 0.9.0`。
8. **不动** `dashmap`（仅 RC）与 `[profile.release]`（`lto=false, codegen-units=16, opt-level=1` 是编译耗时的既定取舍，注释已说明）。

**验收**：端到端 —— 启动二进制 → 提交订单 → 走完扫描/刷课 → 检查 `data/orders.db` 与 WS 推送。

---

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| `Admin.vue`(1734) / `YpayTab.vue`(1805) 单文件过大 | **拆文件与改样式严禁同一 commit**；先纯拆分 + `npm run build` 验证，再改 UI |
| `Admin.vue` 非 scoped 样式全局泄漏 | 作为 Phase 1 **第一步**独立提交；否则无法区分视觉回归来自 Naive 还是泄漏修复 |
| Naive 与既有全局 CSS 冲突 | 已核实 `main.css` 无组件级 `!important`（仅 reduced-motion 块）；用 `:preflight-style-disabled="true"` 让 `main.css` 独占全局重置；遗留页面样式统一加 `.page-*` 前缀 |
| `build` 含 `vue-tsc --noEmit`，组件库类型错误直接构建失败 | 自动导入 dts **提交进 git**；`n-data-table` 的 `columns` 显式泛型 `DataTableColumns<Row>`；每个小步都跑 `npm run build`，不攒到最后 |
| TS 7.0.2 与 `vue-tsc`（`@volar/typescript@2.4.28`）可能不兼容 | 显式降级阶梯 **7.0.2 → 6.0.3 → 5.9.3**，任一可用即止；pinia 4 要求 TS ≥5.6，5.9.3 满足 |
| WS 鉴权改动可能弄坏当前可用的游客订单页 | 三重保护：① `AUTH_WS_REQUIRED` 灰度默认关；② 鉴权失败只回 `error` 不关连接；③ 前端 `realtime.available=false` 时各页自动退回 60s 慢轮询 |
| `rusqlite` 大版本跨 8 个 minor，~150 处调用受影响 | 独立成 Phase 4 的单独 commit，与 UI 改造完全解耦；升级后立即跑 `cargo test` + 端到端 |

---

## 关键文件

- `rust_worker/src/progress.rs` —— WS 中枢重写（鉴权 + topic 过滤 + envelope + `broadcast` helper）
- `rust_worker/src/queue.rs` —— `push_ws` 死开关修复 + `update_job` 作为广播扼流点
- `rust_worker/src/api.rs` —— 订单状态流转广播点
- `frontend/src/stores/realtime.ts`（新建）—— 单例 WS 客户端
- `frontend/src/theme/index.ts`（新建）—— 蓝白主题单一真源
- `frontend/src/components/ToastBridge.vue`（新建）—— toast 桥接，保住 50 处调用点
- `frontend/src/App.vue`、`frontend/src/stores/app.ts`、`frontend/src/styles/main.css`、`frontend/index.html`
- `frontend/src/views/Admin.vue`（非 scoped 泄漏修复）、`frontend/src/views/admin/YpayTab.vue`（拆分）
- `frontend/package.json`、`frontend/vite.config.ts`、`rust_worker/Cargo.toml`

---

## 端到端验收

1. `cd frontend && npm ci && npm run build && npm test` —— `vue-tsc` 零错误。
2. `cd rust_worker && cargo build --release && cargo test` —— 38 个单测保持全绿。
3. 从项目根启动 `D:/dev/rust-target/release/rust_worker.exe`，浏览器打开 `http://127.0.0.1:17017/`。
4. 人工走查：首页扫描下单 → 支付页 → 我的订单 → 后台登录 → 概览/订单/队列/定价/风控各 tab；浅色与暗色各一遍。
5. 实时性验证：A 窗口后台点「执行」，B 窗口订单页 1s 内自动更新状态。
6. 安全验证：未鉴权连接 `/api/progress/ws/live` 收不到任何业务数据；游客用 `view_token` 只能收到自己的 `order:{id}`。

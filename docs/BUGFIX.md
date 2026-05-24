# Bug 修复记录

> 日期: 2026-05-17
> 修复人: Claude Code

---

## 1. 平台2(劳动教育)登录失败 — URL 已失效

**问题**: 扫描时平台2返回"登录失败，请检查账号密码"

**原因**: `config.py` 中配置的 `https://cdcas.rurenkj.com` 已失效，实际被 302 重定向到 `https://cdcas.taiskeji.com`

**修复**: `config.py:78`
```diff
- 2: {"name": "劳动教育平台", "base_url": "https://cdcas.rurenkj.com"},
+ 2: {"name": "劳动教育平台", "base_url": "https://cdcas.taiskeji.com"},
```

---

## 2. 平台3(中嘉鑫盛)登录失败 — URL 已变更 + 缺少 schoolId

**问题**: 扫描时平台3返回"登录失败"

**原因**:
- 旧域名 `https://cdcas.zjxkeji.com` 已变更为 `https://cdcas.chaoxiankeji.com`
- 旧域名登录需要 `schoolId` 参数，原代码未处理

**修复**:
- `config.py:79` — 更新 URL
```diff
- 3: {"name": "中嘉鑫盛", "base_url": "https://cdcas.zjxkeji.com"}
+ 3: {"name": "中嘉鑫盛", "base_url": "https://cdcas.chaoxiankeji.com"}
```
- `services/multi_platform_auth.py` — 新增 schoolId 自动检测与缓存
  - `_extract_school_ids()`: 从登录页提取 schoolId 选项列表
  - `_load_school_id_cache()` / `_save_school_id_cache()`: 持久化缓存到 `data/global_config/school_id_cache.json`
  - `login_single_platform()`: 登录时自动检测 schoolId 并包含在请求中；失败时自动尝试下一个 schoolId；成功后缓存

---

## 3. 视频进度误判 — "未学完"被当成已完成

**问题**: 平台2"实验室安全教育 第二版"实际进度 73.68%，但扫描显示 100% 完成

**原因**: `api/routers/scan.py:131` 对视频完成状态的判定逻辑为 `status != "未学"`，导致平台返回的 **"未学完"**（部分观看）也被计为完成

**修复**: `api/routers/scan.py:129-132`
```diff
- if st and st != "未学":
+ VIDEO_NOT_DONE = {"未学", "未学完", "学习中"}
+ if st and st not in VIDEO_NOT_DONE:
```

---

## 4. 多次下单后旧订单被覆盖

**问题**: 同一账号多次下单后，只有最新一次的订单显示，旧订单全部丢失

**原因**:
- `Home.vue:482-483` — `sessionStorage.setItem('last_order_ids', ...)` 直接**替换**旧 ID，而非追加
- `Orders.vue:68` — 即使用户已登录，游客模式（按 ID 逐个查）仍然优先执行，查到就 `return`，从不调后端列表接口

**修复**:
- `Home.vue:482-485` — 订单 ID 改为**追加**到 sessionStorage
```diff
- const submittedOrderIds = allOrders.map(...).join(',')
- sessionStorage.setItem('last_order_ids', submittedOrderIds)
+ const newIds = allOrders.map(...).join(',')
+ const existingIds = sessionStorage.getItem('last_order_ids') || ''
+ const allIds = existingIds ? existingIds + ',' + newIds : newIds
+ sessionStorage.setItem('last_order_ids', allIds)
```
- `Orders.vue:68` — 游客模式仅在 `isGuest=true` 时才走，登录用户直接调后端列表 API
```diff
- if (guestOrderIds.value.length > 0) {
+ if (isGuest.value && guestOrderIds.value.length > 0) {
```

---

## 5. 后台进度条始终满格

**问题**: 管理后台队列页面，任务的进度条始终显示 100%（满格）

**原因**: 后端存储的 `progress` 已经是 0-100 的百分比值（如 20 即 20%），但前端 `Admin.vue:2167` 又 `* 100`，变为 2000%，CSS 宽度溢出始终满格

**修复**: `Admin.vue:2167`
```diff
- <div class="q-prog-bar" :style="{ width: (j.progress * 100) + '%' }"></div>
+ <div class="q-prog-bar" :style="{ width: j.progress + '%' }"></div>
```

---

## 6. 代理升级后首页横幅不消失

**问题**: 用户升级为 L1 代理后，首页"升级为L1代理"推广横幅仍然显示

**原因**: `detectUserRole()` 仅在 `onMounted` 时调用一次，如果用户在其他标签页升级后切回，不会重新检测

**修复**: `Home.vue`
- 新增 `visibilitychange` 事件监听，页面获得焦点时自动重新检测角色
- "暂不"按钮改为持久化到 `localStorage`，关闭浏览器后也不会再显示

---

## 涉及文件清单

| 文件 | 修改次数 |
|------|---------|
| `config.py` | 2 处 URL 更新 |
| `services/multi_platform_auth.py` | 新增 schoolId 自动检测+缓存 |
| `api/routers/scan.py` | 视频完成判定修复 |
| `frontend/src/views/Home.vue` | sessionStorage 追加、visibility 监听、banner 持久化 |
| `frontend/src/views/Orders.vue` | 游客模式判定修复 |
| `frontend/src/views/Admin.vue` | 进度条百分比修复 |

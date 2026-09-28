<script setup lang="ts">
import { ref, onMounted, onUnmounted, toRef, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { useRealtimeStore } from '@/stores/realtime'
import { usePlatformNames } from '@/composables/usePlatformNames'
import { useAdminStore } from '@/stores/admin'
import { useAuth } from '@/composables/useAuth'
import { useDashboard } from '@/composables/useDashboard'
import { useOrders } from '@/composables/useOrders'
import { usePayments } from '@/composables/usePayments'
import { useSystemConfig } from '@/composables/useSystemConfig'
import { useYpayAdmin } from '@/composables/useYpayAdmin'
import AppTopbar from '@/components/AppTopbar.vue'
import OverviewTab from '@/views/admin/OverviewTab.vue'
import OrdersTab from '@/views/admin/OrdersTab.vue'
import QueueTab from '@/views/admin/QueueTab.vue'
import ProxyTab from '@/views/admin/ProxyTab.vue'
import SecurityTab from '@/views/admin/SecurityTab.vue'
import RiskTab from '@/views/admin/RiskTab.vue'
import PricingTab from '@/views/admin/PricingTab.vue'
import YpayTab from '@/views/admin/YpayTab.vue'
import AnnouncementTab from '@/views/admin/AnnouncementTab.vue'

const store = useAppStore()
const realtime = useRealtimeStore()

// ── Composables ──
const { adminUser, adminPass, loginErr, currentRole, isLoggedIn, pwForm, changingPw, captchaToken, captchaAnswer, captchaImage, captchaLoading, doLogin, logout, changeAdminPassword, loadCaptcha } = useAuth()
const dashboard = useDashboard()
const { allSidebarItems, visibleSidebarGroups, sidebarGroups, sidebarCollapsed, mobileSidebarOpen, loadingDash, dash, dashError, fmtDate, fmtShortDate, fmtMoney, loadDashboard, statusLabel, statusClass, orderStatusLabel, orderStatusClass, maxStatusCount, maxBarRevenue, maxBarOrders, totalPlatformOrders } = dashboard
const orders = useOrders()
const payments = usePayments()
const sysConfig = useSystemConfig()
const ypayAdmin = useYpayAdmin()

// ── Platform names ──
const { load: loadPlatformNames, getName: getPlatformName, platformNames } = usePlatformNames()

// ── Tab switching (orchestrates across composables) ──
type SidebarKey = 'overview' | 'orders' | 'queue' | 'queue_school' | 'queue_chaoxing' | 'pricing' | 'ypay' | 'proxy' | 'announcement' | 'risk' | 'security'
const activeTab = ref<SidebarKey>('overview')
const expandedSidebarItems = ref<string[]>(['queue'])

function toggleSidebarExpand(key: string) {
  const idx = expandedSidebarItems.value.indexOf(key)
  if (idx >= 0) expandedSidebarItems.value.splice(idx, 1)
  else expandedSidebarItems.value.push(key)
}

function switchTab(tab: SidebarKey) {
  activeTab.value = tab
  if (tab === 'overview') dashboard.loadDashboard(currentRole.value)
  if (tab === 'orders') orders.loadOrders()
    // queue 数据由 watch(activeTab) → setQueueFilter 统一加载，此处不重复调用
  if (tab === 'security') { pwForm.old_password = ''; pwForm.new_password = ''; pwForm.confirm_password = ''; if (currentRole.value === 'admin') { sysConfig.loadDeepseekKey(); sysConfig.loadRiskData() } }
  if (tab === 'pricing') sysConfig.loadPricing()
  if (tab === 'ypay') ypayAdmin.loadYpay()
  if (tab === 'proxy') { sysConfig.loadProxySettings(); sysConfig.fetchServerPublicIp() }
}

// ── Lifecycle ──
onMounted(async () => {
  loadPlatformNames()
  if (isLoggedIn.value) {
    if (store.adminToken) {
      currentRole.value = 'admin'
    }
    dashboard.loadDashboard(currentRole.value)
  } else {
    loadCaptcha()
  }
})

// Watch for login state changes (handles login after page load)
watch(isLoggedIn, (loggedIn) => {
  if (loggedIn) {
    realtime.setAdminToken(store.adminToken)
    dashboard.loadDashboard(currentRole.value)
  }
})

// Sync queue filter with sidebar tab
watch(activeTab, (tab) => {
  if (tab === 'queue') payments.setQueueFilter('')
  else if (tab === 'queue_school') payments.setQueueFilter('school')
  else if (tab === 'queue_chaoxing') payments.setQueueFilter('chaoxing')
})

// ── 实时刷新：复用全站唯一的 WS 连接（原先这里另开一条）──
let unsubscribeRealtime: (() => void) | null = null
let refreshTimer: number | null = null

/** 刷课期间每秒可能来好几条进度帧，合并成一次表格刷新 */
function scheduleDataRefresh() {
  if (refreshTimer !== null) return
  refreshTimer = window.setTimeout(() => {
    refreshTimer = null
    if (activeTab.value === 'orders') orders.loadOrders()
    if (activeTab.value === 'queue' || activeTab.value === 'queue_school' || activeTab.value === 'queue_chaoxing') payments.loadQueueData()
  }, 800)
}

onMounted(() => {
  realtime.setAdminToken(store.adminToken)
  unsubscribeRealtime = realtime.subscribe(['*'], (msg) => {
    if (msg.type === 'job.update' || msg.type === 'order.update' || msg.type === 'progress') {
      scheduleDataRefresh()
    }
  })
})

onUnmounted(() => {
  unsubscribeRealtime?.()
  unsubscribeRealtime = null
  if (refreshTimer !== null) { clearTimeout(refreshTimer); refreshTimer = null }
  if (payments._payTestTimer) { clearInterval(payments._payTestTimer); payments._payTestTimer = null }
})

// ── Expose typed state slices to tab components via admin store ──
useAdminStore().init({
  auth: { adminUser, adminPass, loginErr, currentRole, isLoggedIn, pwForm, changingPw, captchaToken, captchaAnswer, captchaImage, captchaLoading, doLogin, logout, changeAdminPassword, loadCaptcha },
  dashboard,
  orders,
  payments,
  sysConfig,
  ypay: ypayAdmin,
  ui: { activeTab, switchTab, platformNames, loadPlatformNames, getPlatformName },
})

</script>

<template>
  <div class="admin-root">
    <!-- Login Screen -->
    <div v-if="!isLoggedIn" class="login-screen">
      <div class="login-split">
      <div class="brand-side">
        <div class="bs-logo">
          <span class="bs-mark">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M13 2L4.5 12.5H11L9.5 22 19 10.5h-6.5L13 2z"/></svg>
          </span>
          <span>Fuk 文理网课</span>
        </div>
        <div class="bs-copy">
          <h2>运营后台</h2>
          <p>订单、队列、支付、风控，一站式管理面板。</p>
        </div>
        <ul class="bs-points">
          <li>实时队列监控与订单全链路追踪</li>
          <li>YPay / VMQ 聚合支付与对账</li>
          <li>网络代理、系统公告与安全中心</li>
        </ul>
        <div class="bs-foot">仅限管理员访问 · 操作全程留痕</div>
      </div>
      <div class="form-side">
      <div class="login-card">
        <form @submit="doLogin">
          <div class="field">
            <label>用户名</label>
            <input v-model="adminUser" placeholder="请输入管理员用户名" autocomplete="username" />
          </div>
          <div class="field">
            <label>密码</label>
            <input v-model="adminPass" type="password" placeholder="请输入密码" autocomplete="current-password" />
          </div>
          <div class="field">
            <label>验证码</label>
            <div class="captcha-row">
              <input v-model="captchaAnswer" placeholder="请输入验证码" autocomplete="off" />
              <img v-if="captchaImage" :src="captchaImage" class="captcha-img" title="点击刷新验证码" @click="loadCaptcha" />
              <div v-else class="captcha-placeholder" @click="loadCaptcha">
                <span v-if="captchaLoading">加载中...</span>
                <span v-else>获取验证码</span>
              </div>
            </div>
          </div>
          <button type="submit" class="btn btn-primary btn-lg btn-block">
登录后台
</button>
          <div v-if="loginErr" class="login-err">
{{ loginErr }}
</div>
        </form>
        <div class="login-back">
          <router-link to="/">
&larr; 返回前台首页
</router-link>
        </div>
      </div>
      </div>
      </div>
    </div>

    <!-- Admin Layout -->
    <div v-else class="admin-layout">
      <!-- Mobile sidebar overlay -->
      <div class="sidebar-overlay" :class="{ show: mobileSidebarOpen }" @click="mobileSidebarOpen = false"></div>

      <!-- Sidebar -->
      <aside class="sidebar" :class="{ collapsed: sidebarCollapsed, 'mobile-open': mobileSidebarOpen }">
        <div class="sidebar-brand">
          <router-link to="/admin" class="sb-logo">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
            </svg>
            <span v-if="!sidebarCollapsed">后台管理</span>
          </router-link>
        </div>

        <nav class="sidebar-nav">
          <template v-for="group in visibleSidebarGroups" :key="group.label">
            <div v-if="!sidebarCollapsed" class="sidebar-group-label">
{{ group.label }}
</div>
            <template v-for="item in group.children" :key="item.key">
              <button
                v-if="!item.children"
                :class="['sidebar-item', { active: activeTab === item.key }]"
                :title="item.label"
                @click="switchTab(item.key as any); mobileSidebarOpen = false"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="sidebar-item-icon">
                  <path :d="item.icon"/>
                </svg>
                <span v-if="!sidebarCollapsed" class="sidebar-item-label">{{ item.label }}</span>
              </button>
              <template v-else>
                <button
                  :class="['sidebar-item', 'sidebar-parent', { active: item.children.some((c: any) => activeTab === c.key) }]"
                  :title="item.label"
                  @click="toggleSidebarExpand(item.key)"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="sidebar-item-icon">
                    <path :d="item.icon"/>
                  </svg>
                  <span v-if="!sidebarCollapsed" class="sidebar-item-label">{{ item.label }}</span>
                  <svg v-if="!sidebarCollapsed" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="sidebar-expand-icon" :class="{ expanded: expandedSidebarItems.includes(item.key) }">
                    <path d="M6 9l6 6 6-6"/>
                  </svg>
                </button>
                <div v-if="expandedSidebarItems.includes(item.key) && !sidebarCollapsed" class="sidebar-sub-items">
                  <button
                    v-for="sub in item.children"
                    :key="sub.key"
                    :class="['sidebar-item', 'sidebar-sub-item', { active: activeTab === sub.key }]"
                    :title="sub.label"
                    @click="switchTab(sub.key as any); mobileSidebarOpen = false"
                  >
                    <span class="sidebar-item-label">{{ sub.label }}</span>
                  </button>
                </div>
              </template>
            </template>
          </template>
        </nav>

        <div class="sidebar-footer">
          <button class="sidebar-item" title="折叠菜单" @click="sidebarCollapsed = !sidebarCollapsed">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path v-if="!sidebarCollapsed" d="M11 19l-7-7 7-7m8 14l-7-7 7-7"/>
              <path v-else d="M13 5l7 7-7 7M5 5l7 7-7 7"/>
            </svg>
          </button>
          <router-link to="/" class="sidebar-item" title="返回前台">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1"/>
            </svg>
            <span v-if="!sidebarCollapsed">返回前台</span>
          </router-link>
          <button class="sidebar-item logout-item" title="退出登录" @click="logout">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>
            </svg>
            <span v-if="!sidebarCollapsed">退出登录</span>
          </button>
        </div>
      </aside>

      <!-- Main Content -->
      <main class="main-content">
        <header class="content-topbar">
          <div style="display:flex;align-items:center;gap:10px">
            <button class="mobile-sidebar-toggle" @click="mobileSidebarOpen = !mobileSidebarOpen">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
            </button>
            <h2>{{ ['queue', 'queue_school', 'queue_chaoxing'].includes(activeTab) ? '队列监控' : allSidebarItems.find(i => i.key === activeTab)?.label }}</h2>
            <span v-if="activeTab === 'queue'" class="topbar-tag">全部</span>
            <span v-else-if="activeTab === 'queue_school'" class="topbar-tag">学校平台</span>
            <span v-else-if="activeTab === 'queue_chaoxing'" class="topbar-tag">学习通</span>
          </div>
          <div class="topbar-right">
            <span class="admin-badge">管理员</span>
            <button v-if="activeTab === 'overview'" class="btn btn-ghost btn-sm" :disabled="loadingDash" @click="loadDashboard(currentRole)">
              <span v-if="loadingDash" class="spinner" style="width:14px;height:14px"></span>
              {{ loadingDash ? '加载中' : '刷新数据' }}
            </button>
          </div>
        </header>

        <div class="content-body">
          <!-- Overview Tab -->
          <OverviewTab v-if="activeTab === 'overview'" />

          <!-- Orders Tab -->
          <OrdersTab v-if="activeTab === 'orders'" />

          <!-- Users Tab -->

          <!-- Queue Tab -->
          <QueueTab v-if="activeTab === 'queue' || activeTab === 'queue_school' || activeTab === 'queue_chaoxing'" />


          <!-- Proxy Tab -->
          <ProxyTab v-if="activeTab === 'proxy'" />


          <!-- Security Tab -->
          <SecurityTab v-if="activeTab === 'security'" />

          <!-- Announcement Tab -->
          <AnnouncementTab v-if="activeTab === 'announcement'" />


          <!-- Risk Monitor Tab -->
          <RiskTab v-if="activeTab === 'risk'" />


          <!-- Pricing Tab -->
          <PricingTab v-if="activeTab === 'pricing'" />

          <YpayTab v-if="activeTab === 'ypay'" />
</div>
      </main>

      <!-- Mobile Bottom Nav -->
      <nav class="mobile-bottom-nav">
        <button :class="['mbn-item', { active: activeTab === 'overview' }]" @click="switchTab('overview')">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1"/></svg>
          <span>首页</span>
        </button>
        <button :class="['mbn-item', { active: activeTab === 'orders' }]" @click="switchTab('orders')">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
          <span>订单</span>
        </button>
        <button :class="['mbn-item', { active: activeTab === 'queue' }]" @click="switchTab('queue')">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 6h16M4 10h16M4 14h16M4 18h16"/></svg>
          <span>队列</span>
        </button>
        <button :class="['mbn-item', { active: activeTab === 'security' || activeTab === 'pricing' || activeTab === 'ypay' || activeTab === 'proxy' }]" @click="mobileSidebarOpen = true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><circle cx="12" cy="12" r="3"/></svg>
          <span>更多</span>
        </button>
      </nav>
    </div>
  </div>
</template>

<style scoped>
/* 原先为非 scoped 全局样式，会泄漏到全站且只在访问 /admin 后才注入
   （导致首页/订单页在进过后台前后外观不一致）。
   被外部依赖的类已上提到 styles/main.css，此处收敛为组件作用域。 */
.admin-root { min-height: 100vh; }

/* Login Screen */
.login-screen {
  min-height: 100vh; display: flex;
  background: var(--c-bg);
}
.login-split {
  flex: 1; display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
}
.brand-side {
  background: #141417; color: #fff;
  padding: 52px 60px;
  display: flex; flex-direction: column;
}
.bs-logo { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 700; letter-spacing: -.01em; }
.bs-mark {
  width: 28px; height: 28px; border-radius: 8px; background: #fff; color: #141417;
  display: inline-flex; align-items: center; justify-content: center;
}
.bs-copy { margin-top: 92px; }
.bs-copy h2 { font-size: 34px; font-weight: 700; letter-spacing: -.025em; line-height: 1.2; }
.bs-copy p { margin-top: 12px; font-size: 14px; line-height: 1.7; color: rgba(255,255,255,.6); max-width: 36ch; }
.bs-points { list-style: none; margin: 36px 0 0; padding: 0; display: flex; flex-direction: column; gap: 14px; }
.bs-points li { display: flex; align-items: center; gap: 12px; font-size: 13.5px; color: rgba(255,255,255,.78); }
.bs-points li::before { content: ''; width: 5px; height: 5px; border-radius: 50%; background: rgba(255,255,255,.35); flex-shrink: 0; }
.bs-foot { margin-top: auto; font-size: 12px; color: rgba(255,255,255,.38); }
.form-side { display: flex; align-items: center; justify-content: center; padding: 40px 24px; }
@media (max-width: 900px) {
  .login-split { grid-template-columns: 1fr; }
  .brand-side { display: none; }
}
.login-card {
  background: var(--c-surface); border: 1px solid var(--c-border-light); border-radius: 20px; padding: 44px 40px;
  width: 420px; max-width: 100%;
  box-shadow: 0 8px 24px rgba(20, 20, 24, .06), 0 24px 56px rgba(20, 20, 24, .08);
}
.login-card h2, .login-card .lc-form-title { font-size: 20px; font-weight: 700; letter-spacing: -.015em; color: var(--c-text); }
.login-desc { text-align: center; font-size: 13px; color: var(--c-text-muted); margin-bottom: 28px; }
.login-back { text-align: center; margin-top: 20px; }
.login-back a { font-size: 13px; color: var(--c-text-muted); text-decoration: none; }
.login-back a:hover { color: var(--c-primary); }

.field { display: flex; flex-direction: column; gap: 5px; margin-bottom: 16px; }
.field label { font-size: 12.5px; font-weight: 600; color: var(--c-text-secondary); }
.field input {
  height: 44px; padding: 0 14px; border: 1.5px solid var(--c-border);
  border-radius: 10px; background: var(--c-surface-2); color: var(--c-text);
  font-size: 14px; outline: none; transition: all .15s;
}
.field input:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-bg); background: var(--c-surface); }
.captcha-row { display: flex; gap: 8px; align-items: stretch; }
.captcha-row input { flex: 1; min-width: 0; height: 44px; padding: 0 14px; border: 1.5px solid var(--c-border); border-radius: 8px; font-size: 14px; outline: none; }
.captcha-img { height: 44px; cursor: pointer; border-radius: 8px; border: 1px solid var(--c-border); flex-shrink: 0; }
.captcha-placeholder {
  height: 44px; padding: 0 16px; display: flex; align-items: center; justify-content: center;
  border: 1px dashed var(--c-border); border-radius: 8px; font-size: 13px; color: var(--c-text-muted);
  cursor: pointer; flex-shrink: 0; white-space: nowrap;
}
.captcha-placeholder:hover { border-color: var(--c-primary); color: var(--c-primary); }
.field input::placeholder { color: var(--c-text-muted); }
.field-hint { font-size: 11px; color: var(--c-text-muted); margin-top: 2px; }
.login-err { font-size: 13px; color: var(--c-danger); text-align: center; margin-top: 12px; }

.btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 9px 20px; border: none; border-radius: 10px; font-weight: 600; font-size: 13.5px; cursor: pointer; transition: all .15s; white-space: nowrap; }
.btn-primary { background: var(--c-primary); color: #fff; box-shadow: var(--shadow-primary); }
.btn-primary:hover { background: var(--c-primary-hover); transform: translateY(-1px); box-shadow: var(--shadow-primary-lg); }
.btn-primary:disabled { opacity: .55; cursor: not-allowed; transform: none; }
.btn-ghost { background: transparent; color: var(--c-text-muted); padding: 6px 12px; }
.btn-ghost:hover { color: var(--c-primary); background: var(--c-primary-bg); }
.btn-lg { padding: 13px 28px; font-size: 15px; }
.btn-block { width: 100%; }
.btn-sm { padding: 5px 10px; font-size: 12px; }
.btn-xs { padding: 4px 10px; font-size: 11.5px; border-radius: 6px; }
.btn-success { background: var(--c-success); color: #fff; }
.btn-success:hover { filter: brightness(1.1); }
.btn-warn { background: var(--c-warning); color: #fff; }
.btn-warn:hover { filter: brightness(1.1); }

/* Layout */
.admin-layout { display: flex; min-height: 100vh; }

/* Mobile sidebar toggle - hidden on desktop */
.mobile-sidebar-toggle { display: none; }

/* Mobile bottom nav - hidden on desktop */
.mobile-bottom-nav { display: none; }

/* Sidebar */
.sidebar {
  width: 220px; flex-shrink: 0; background: var(--c-surface); border-right: 1px solid var(--c-border-light);
  display: flex; flex-direction: column; position: fixed; top: 0; left: 0;
  bottom: 0; z-index: 50; transition: width .2s ease;
  overflow: hidden;
}
.sidebar.collapsed { width: 60px; }

.sidebar-brand {
  padding: 20px 16px; border-bottom: 1px solid rgba(255,255,255,.08);
}
.sb-logo {
  display: flex; align-items: center; gap: 10px; color: var(--c-text);
  text-decoration: none; font-size: 16px; font-weight: 700; white-space: nowrap;
}
.sb-logo svg { color: var(--c-primary); flex-shrink: 0; }
.sb-logo:hover { text-decoration: none; }

.sidebar-nav {
  flex: 1; padding: 12px 8px; display: flex; flex-direction: column; gap: 2px;
  overflow-y: auto; scrollbar-width: thin; scrollbar-color: #d4d4d8 transparent;
}
.sidebar-nav::-webkit-scrollbar { width: 5px; }
.sidebar-nav::-webkit-scrollbar-track { background: transparent; }
.sidebar-nav::-webkit-scrollbar-thumb { background: #d4d4d8; border-radius: 3px; }
.sidebar-nav::-webkit-scrollbar-thumb:hover { background: #bdbdc2; }
.sidebar-group-label {
  font-size: 11px; font-weight: 600; color: var(--c-text-muted); text-transform: uppercase;
  letter-spacing: .5px; padding: 12px 12px 4px; white-space: nowrap;
}
.sidebar-group-label:first-child { padding-top: 4px; }

.sidebar-item {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  border-radius: 8px; background: transparent; border: none;
  color: var(--c-text-muted); font-size: 13.5px; font-weight: 500;
  cursor: pointer; transition: all .15s; width: 100%; text-align: left;
  text-decoration: none; white-space: nowrap;
}
.sidebar-item:hover { background: var(--c-surface-2); color: var(--c-text); text-decoration: none; }
.sidebar-item.active { background: var(--c-primary); color: #fff; box-shadow: none; }
.sidebar-item.active .sidebar-item-icon { color: #fff; }
.sidebar-item-icon { flex-shrink: 0; }

.sidebar-parent { justify-content: space-between; }
.sidebar-expand-icon { flex-shrink: 0; transition: transform .2s; margin-left: auto; }
.sidebar-expand-icon.expanded { transform: rotate(180deg); }
.sidebar-sub-items { display: flex; flex-direction: column; gap: 1px; padding-left: 8px; }
.sidebar-sub-item { padding: 7px 12px 7px 28px; font-size: 13px; }
.sidebar-sub-item.active { background: var(--c-primary-bg); color: var(--c-primary); }
.sidebar-sub-item.active .sidebar-item-icon { color: var(--c-primary); }

.sidebar-footer {
  padding: 8px; border-top: 1px solid rgba(255,255,255,.08);
  display: flex; flex-direction: column; gap: 2px;
}
.logout-item:hover { color: #fca5a5; background: rgba(239,68,68,.1); }

/* Main Content */
.main-content {
  flex: 1; margin-left: 220px; min-height: 100vh;
  display: flex; flex-direction: column; transition: margin-left .2s ease;
}
.sidebar.collapsed ~ .main-content { margin-left: 60px; }

.content-topbar {
  position: sticky; top: 0; z-index: 40; background: var(--c-surface);
  border-bottom: 1px solid var(--c-border);
  padding: 0 28px; height: 56px; display: flex; align-items: center;
  justify-content: space-between;
}
.content-topbar h2 { font-size: 17px; font-weight: 700; color: var(--c-text); }
.topbar-tag { font-size: 11px; font-weight: 600; padding: 2px 10px; border-radius: 12px; background: var(--c-border-light); color: var(--c-text-muted); }
.topbar-tag-school { background: var(--c-success-bg); color: var(--c-success); }
.topbar-tag-chaoxing { background: var(--c-primary-bg); color: var(--c-primary); }
.topbar-right { display: flex; align-items: center; gap: 12px; }
.admin-badge {
  padding: 3px 12px; border-radius: 20px; font-size: 11.5px; font-weight: 600;
  background: var(--c-primary-bg);
  color: var(--c-primary);
}

.content-body { flex: 1; padding: 24px 28px 40px; }

/* KPI Cards */
.overview-content { display: flex; flex-direction: column; gap: 18px; }
.kpi-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }
.kpi-card {
  background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: 12px; padding: 20px 18px; box-shadow: 0 1px 3px rgba(20,20,24,.06);
  display: flex; flex-direction: column; gap: 8px; transition: box-shadow .15s;
}
.kpi-card:hover { box-shadow: 0 4px 16px rgba(20,20,24,.08); }
.kpi-icon {
  width: 38px; height: 38px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
}
.kpi-icon.rev { background: var(--c-danger-bg); color: var(--c-danger); }
.kpi-icon.ord { background: var(--c-primary-bg); color: var(--c-primary); }
.kpi-icon.usr { background: var(--c-success-bg); color: var(--c-success); }
.kpi-icon.agt { background: var(--c-info-bg); color: var(--c-info); }
.kpi-icon.rate { background: var(--c-warning-bg); color: var(--c-warning); }
.kpi-icon.upg { background: var(--c-primary-bg); color: var(--c-primary); }
.kpi-body { display: flex; flex-direction: column; gap: 2px; }
.kpi-val { font-size: 24px; font-weight: 700; color: var(--c-text); line-height: 1.1; }
.kpi-label { font-size: 12px; color: var(--c-text-muted); font-weight: 500; }
.kpi-sub { font-size: 11px; color: var(--c-text-muted); border-top: 1px solid var(--c-border-light); padding-top: 7px; }

/* Panels */
.panel-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.panel {
  background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: 12px; padding: 20px 22px; box-shadow: 0 1px 3px rgba(20,20,24,.06);
}
.panel-wide { grid-column: span 2; }
.panel-wide-sm { grid-column: span 1; }
.panel-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.panel-head h3 { font-size: 14px; font-weight: 700; color: var(--c-text); }
.legend-row { display: flex; gap: 16px; }
.legend { font-size: 11.5px; color: var(--c-text-muted); display: flex; align-items: center; gap: 5px; }
.ldot { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
.ldot-rev { background: var(--c-danger); }
.ldot-ord { background: var(--c-primary); }

.chart-area { display: flex; align-items: flex-end; gap: 10px; height: 160px; padding: 0 4px; }
.bar-group { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; }
.bars { flex: 1; width: 100%; display: flex; align-items: flex-end; gap: 4px; justify-content: center; }
.bar { width: 12px; border-radius: 4px 4px 0 0; min-height: 3px; transition: height .3s; }
.bar-rev { background: var(--c-danger); opacity: .75; }
.bar-ord { background: var(--c-primary); opacity: .75; }
.bar-label { font-size: 10px; color: var(--c-text-muted); margin-top: 6px; }

.status-bars { display: flex; flex-direction: column; gap: 10px; }
.sb-row { display: flex; align-items: center; gap: 10px; }
.sb-label { width: 50px; font-size: 12px; color: var(--c-text-muted); text-align: right; flex-shrink: 0; }
.sb-track { flex: 1; height: 7px; background: var(--c-border-light); border-radius: 4px; overflow: hidden; }
.sb-fill { height: 100%; border-radius: 4px; transition: width .4s; }
.sb-primary { background: var(--c-primary); }
.sb-ok { background: var(--c-success); }
.sb-warn { background: var(--c-warning); }
.sb-bad { background: var(--c-danger); }
.sb-muted { background: var(--c-text-muted); }
.sb-val { width: 36px; font-size: 12px; color: var(--c-text); font-weight: 600; text-align: left; flex-shrink: 0; }

.plat-list { display: flex; flex-direction: column; gap: 10px; }
.plat-item { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.plat-left { display: flex; align-items: center; gap: 8px; min-width: 100px; }
.plat-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.plat-name { font-size: 12.5px; color: var(--c-text); font-weight: 500; white-space: nowrap; }
.plat-right { display: flex; align-items: center; gap: 8px; flex: 1; }
.plat-bar-bg { flex: 1; height: 8px; background: var(--c-border-light); border-radius: 4px; overflow: hidden; max-width: 120px; }
.plat-bar-fill { height: 100%; border-radius: 4px; transition: width .3s; }
.plat-cnt { font-size: 11.5px; color: var(--c-text-muted); white-space: nowrap; min-width: 28px; }
.plat-rev { font-size: 11.5px; color: var(--c-text-muted); white-space: nowrap; }

.type-cards { display: flex; gap: 10px; flex-wrap: wrap; }
.type-card {
  flex: 1; min-width: 60px; background: var(--c-surface-2);
  border-radius: 10px; padding: 16px 14px; text-align: center;
}
.tc-icon { font-size: 13px; font-weight: 600; color: var(--c-primary); margin-bottom: 4px; }
.tc-count { font-size: 20px; font-weight: 700; color: var(--c-text); }
.tc-rev { font-size: 11px; color: var(--c-text-muted); margin-top: 2px; }

.mini-table { font-size: 12.5px; }
.mt-row { display: grid; grid-template-columns: 1fr 1fr .7fr .9fr .9fr 1.2fr; gap: 4px; padding: 8px 0; border-bottom: 1px solid var(--c-border-light); align-items: center; }
.mt-head { font-weight: 600; color: var(--c-text-muted); font-size: 11px; text-transform: uppercase; letter-spacing: .3px; border-bottom: 2px solid var(--c-border); }
.mt-row:last-child { border-bottom: none; }
.mt-uname { font-weight: 600; color: var(--c-text); }
.mt-money { font-weight: 600; }
.mt-date { color: var(--c-text-muted); font-size: 11px; }

.rank-list { display: flex; flex-direction: column; }
.rank-item { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--c-border-light); }
.rank-item:last-child { border-bottom: none; }
.rank-no {
  width: 26px; height: 26px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; background: var(--c-border-light); color: var(--c-text-muted);
}
.rank-no.r1 { background: var(--c-warning-bg); color: var(--c-warning); }
.rank-no.r2 { background: var(--c-border); color: var(--c-text-secondary); }
.rank-no.r3 { background: rgba(251,146,60,.16); color: var(--c-warning); }
.rank-info { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.rank-name { font-size: 13px; font-weight: 600; color: var(--c-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rank-code { font-size: 11px; color: var(--c-text-muted); }
.rank-earn { font-size: 13px; font-weight: 700; color: var(--c-danger); white-space: nowrap; }

/* Agent Sub-tabs */
.agent-subtabs { display: flex; gap: 6px; margin-bottom: 20px; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 10px; padding: 5px; }
.ast { display: flex; align-items: center; gap: 6px; padding: 10px 20px; border: none; background: transparent; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 500; color: var(--c-text-muted); transition: all .2s; white-space: nowrap; }
.ast:hover { background: var(--c-border-light); color: var(--c-text-secondary); }
.ast.active { background: var(--c-primary); color: #fff; box-shadow: var(--shadow-primary); }
.ast.active svg { stroke: #fff; }

/* Agent Stats */
.agent-stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }

.guide-banner {
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 12px;
  margin-bottom: 20px; overflow: hidden; box-shadow: 0 1px 3px rgba(20,20,24,.06);
}
.gb-header {
  display: flex; align-items: center; gap: 8px; padding: 14px 20px;
  background: var(--c-surface-2); border-bottom: 1px solid var(--c-border);
  font-size: 15px; color: var(--c-primary);
}
.gb-body { padding: 18px 20px; }
.gb-section { margin-bottom: 16px; }
.gb-section:last-child { margin-bottom: 0; }
.gb-section h4 { font-size: 14px; font-weight: 700; color: var(--c-text); margin: 0 0 6px; }
.gb-section p { font-size: 13px; color: var(--c-text-muted); margin: 0; line-height: 1.6; }
.gb-section ul { font-size: 13px; color: var(--c-text-muted); margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.gb-rates { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 8px; }
.gb-rate {
  display: flex; align-items: center; gap: 10px; background: var(--c-surface-2);
  border: 1px solid var(--c-border); border-radius: 10px; padding: 12px 16px; flex: 1; min-width: 260px;
}
.gb-rate-tag {
  padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; flex-shrink: 0;
}
.gb-rate-tag.l1 { background: var(--c-primary-bg); color: var(--c-primary); }
.gb-rate-tag.l2 { background: var(--c-success-bg); color: var(--c-success); }
.gb-rate-val { font-size: 22px; font-weight: 800; color: var(--c-text); flex-shrink: 0; }
.gb-rate-desc { font-size: 12px; color: var(--c-text-muted); }
.mini-stat {
  background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: 12px; padding: 18px 22px; text-align: center; box-shadow: 0 1px 3px rgba(20,20,24,.06);
}
.ms-val { font-size: 24px; font-weight: 700; color: var(--c-text); }
.ms-val.ok { color: var(--c-success); }
.ms-val.money { color: var(--c-danger); }
.ms-label { font-size: 12px; color: var(--c-text-muted); margin-top: 4px; }

.section-actions { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; flex-wrap: wrap; gap: 10px; }
.filter-group { display: flex; gap: 6px; }
.filter-bar { width: 100%; overflow: hidden; }
.filter-scroll { display: flex; gap: 6px; overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; padding-bottom: 2px; }
.filter-scroll::-webkit-scrollbar { display: none; }
.filter-divider { width: 1px; height: 24px; background: var(--c-border); flex-shrink: 0; align-self: center; margin: 0 2px; }
.filter-search-row { display: flex; align-items: center; gap: 8px; width: 100%; }
.chip {
  padding: 6px 16px; border: 1px solid var(--c-border); border-radius: 20px;
  background: var(--c-surface); font-size: 12.5px; font-weight: 500;
  color: var(--c-text-muted); cursor: pointer; transition: all .15s;
}
.chip:hover { border-color: var(--c-primary); color: var(--c-primary); }
.chip.active { background: var(--c-primary); color: #fff; border-color: var(--c-primary); }
.total-label { font-size: 13px; color: var(--c-text-muted); }

/* Tables */
.table-wrap {
  background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: 12px; overflow-x: auto; box-shadow: 0 1px 3px rgba(20,20,24,.06);
}
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table thead { background: var(--c-surface-2); }
.data-table th {
  padding: 12px 16px; text-align: left; font-weight: 600; font-size: 11.5px;
  color: var(--c-text-muted); text-transform: uppercase; letter-spacing: .3px;
  border-bottom: 1px solid var(--c-border); white-space: nowrap;
}
.data-table td {
  padding: 12px 16px; border-bottom: 1px solid var(--c-border-light);
  color: var(--c-text); white-space: nowrap;
}
.data-table tbody tr:hover { background: var(--c-surface-2); }
.data-table tbody tr:last-child td { border-bottom: none; }

.user-cell { display: flex; flex-direction: column; gap: 2px; }
.uname { font-weight: 600; font-size: 13px; }
.uid { font-size: 11px; color: var(--c-text-muted); }
.code-tag {
  background: var(--c-border-light); padding: 2px 8px; border-radius: 5px;
  font-size: 11.5px; font-family: 'SF Mono', 'Consolas', monospace; color: var(--c-primary);
}
.money-cell { font-weight: 600; font-variant-numeric: tabular-nums; }
.money-cell.highlight { color: var(--c-danger); }
.date-cell { font-size: 12px; color: var(--c-text-muted); }

.status-tag {
  display: inline-block; padding: 2px 10px; border-radius: 12px;
  font-size: 11.5px; font-weight: 600;
}
.status-tag.ok { background: var(--c-success-bg); color: var(--c-success); }
.status-tag.ok.verified { background: var(--c-success-bg); color: var(--c-success); border: 1.5px solid var(--c-success); }
.status-tag.warn { background: var(--c-warning-bg); color: var(--c-warning); }
.status-tag.bad { background: var(--c-danger-bg); color: var(--c-danger); }
.status-tag.primary { background: var(--c-primary-bg); color: var(--c-primary); }
.status-tag.muted { background: var(--c-border-light); color: var(--c-text-muted); }

.level-tag { display: inline-block; padding: 2px 8px; border-radius: 5px; font-size: 11px; font-weight: 700; }
.level-tag.l1 { background: var(--c-primary-bg); color: var(--c-primary); }
.level-tag.l2 { background: var(--c-info-bg); color: var(--c-info); }
.level-tag.l3 { background: var(--c-primary-bg); color: var(--c-primary); }

.search-input { padding: 6px 12px; border: 1px solid var(--c-border); border-radius: 8px; font-size: 13px; outline: none; width: 160px; transition: border-color .2s; }
.search-input:focus { border-color: var(--c-primary); }

.fee-section { background: var(--c-surface-2); border: 1px solid var(--c-border); border-radius: 10px; padding: 20px; margin-bottom: 16px; }
.fee-toggle-row { display: flex; align-items: center; justify-content: space-between; }
.fee-label { font-size: 14px; font-weight: 600; color: var(--c-text); }
.fee-hint { font-size: 12px; color: var(--c-text-muted); margin-left: 8px; }
.toggle-switch { position: relative; display: inline-block; width: 44px; height: 24px; cursor: pointer; }
.toggle-switch input { opacity: 0; width: 0; height: 0; }
.toggle-slider { position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: var(--c-border); border-radius: 24px; transition: .3s; }
.toggle-slider:before { content: ''; position: absolute; height: 18px; width: 18px; left: 3px; bottom: 3px; background: #ffffff; border-radius: 50%; transition: .3s; }
.toggle-switch input:checked + .toggle-slider { background: var(--c-primary); }
.toggle-switch input:checked + .toggle-slider:before { transform: translateX(20px); }
.fee-input-row { display: flex; align-items: center; gap: 12px; margin-top: 14px; }
.fee-input-label { font-size: 13px; color: var(--c-text-muted); min-width: 160px; }
.fee-input { padding: 6px 12px; border: 1px solid var(--c-border); border-radius: 8px; font-size: 13px; width: 120px; outline: none; }
.fee-input:focus { border-color: var(--c-primary); }

.guide-banner { display: flex; gap: 16px; align-items: flex-start; background: var(--c-gradient-soft); border: 1px solid var(--c-border-light); border-radius: 12px; padding: 20px; margin-bottom: 24px; }
.guide-icon { flex-shrink: 0; width: 48px; height: 48px; background: var(--c-primary); border-radius: 12px; display: flex; align-items: center; justify-content: center; color: #fff; }
.guide-banner h4 { font-size: 15px; font-weight: 700; color: var(--c-text); margin-bottom: 4px; }
.guide-banner p { font-size: 13px; color: var(--c-text-secondary); margin: 0; }
.guide-section { margin-bottom: 24px; }
.guide-section h4 { font-size: 14px; font-weight: 700; color: var(--c-text); margin-bottom: 12px; }
.guide-rate-row { display: flex; gap: 12px; flex-wrap: wrap; }
.guide-rate-card { flex: 1; min-width: 160px; background: var(--c-surface-2); border: 1px solid var(--c-border); border-radius: 10px; padding: 16px; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.grc-badge { display: inline-block; padding: 4px 14px; border-radius: 6px; font-size: 13px; font-weight: 700; }
.grc-badge.l1 { background: var(--c-primary-bg); color: var(--c-primary); }
.grc-badge.l2 { background: var(--c-info-bg); color: var(--c-info); }
.grc-badge.l3 { background: var(--c-primary-bg); color: var(--c-primary); }
.grc-label { font-size: 13px; color: var(--c-text-muted); }
.grc-value { font-size: 14px; font-weight: 600; color: var(--c-text); }
.guide-list { list-style: none; padding: 0; }
.guide-list li { position: relative; padding-left: 18px; margin-bottom: 8px; font-size: 13px; color: var(--c-text-secondary); line-height: 1.6; }
.guide-list li:before { content: ''; position: absolute; left: 0; top: 8px; width: 6px; height: 6px; background: var(--c-primary); border-radius: 50%; }
.guide-list li strong { color: var(--c-text); }

.action-group { display: flex; gap: 4px; }

.empty { text-align: center; padding: 60px; color: var(--c-text-muted); }
.empty p { margin-bottom: 16px; }
.empty-sm { text-align: center; padding: 32px; color: var(--c-text-muted); font-size: 13px; }

.spinner { border: 2px solid var(--c-border); border-top-color: var(--c-primary); border-radius: 50%; animation: spin .65s linear infinite; display: inline-block; }

/* Security */
.security-tab { width: 100%; max-width: 720px; display: flex; flex-direction: column; gap: 20px; }
.proxy-tab { width: 100%; max-width: 720px; display: flex; flex-direction: column; gap: 20px; }
.proxy-toggle-row { display: flex; align-items: center; justify-content: space-between; padding: 6px 0 14px; }
.proxy-toggle-label { font-size: 14px; font-weight: 600; color: var(--c-text-secondary); }
.proxy-actions { display: flex; gap: 10px; margin-top: 16px; }
.proxy-test-result { margin-top: 12px; padding: 10px 14px; border-radius: 8px; font-size: 13px; background: var(--c-danger-bg); color: var(--c-danger); }
.proxy-test-result.ok { background: var(--c-success-bg); color: var(--c-success); }
.proxy-guide { font-size: 13px; line-height: 1.8; color: var(--c-text-secondary); padding-top: 12px; }
.guide-step { margin-bottom: 6px; }
.guide-step code { background: var(--c-surface-3); padding: 1px 6px; border-radius: 4px; font-size: 12px; }
.code-warn { background: var(--c-danger-bg); color: var(--c-danger); }
.guide-details { cursor: pointer; }
.guide-details summary { font-size: 15px; font-weight: 600; color: var(--c-text); outline: none; }
.guide-details summary:hover { color: var(--c-primary); }
.settings-card { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 12px; padding: 28px; box-shadow: 0 1px 3px rgba(20,20,24,.06); }
.settings-card h3 { font-size: 16px; font-weight: 700; margin-bottom: 6px; color: var(--c-text); }
.settings-hint { font-size: 12.5px; color: var(--c-text-muted); margin-bottom: 22px; }
.settings-card .field { margin-bottom: 18px; }
.settings-card .field label { text-align: left; }
.settings-card .field input {
  padding: 10px 14px; border: 1.5px solid var(--c-border); border-radius: 10px;
  background: var(--c-surface-2); color: var(--c-text); font-size: 14px; outline: none;
  transition: border-color .15s; font-family: inherit; width: 100%; box-sizing: border-box;
}
.settings-card .field input:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-bg); background: var(--c-surface); }

/* DeepSeek AI Config */
.ai-section { margin-top: 20px; }
.ai-section:first-child { margin-top: 16px; }
.ai-section-label { font-size: 13px; font-weight: 700; color: var(--c-text-secondary); margin-bottom: 10px; }
.ai-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.ai-key-wrap { display: flex; align-items: center; gap: 8px; }
.ai-key-badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; }
.ai-key-badge.on { background: var(--c-success-bg); color: var(--c-success); }
.ai-key-badge.off { background: var(--c-danger-bg); color: var(--c-danger); }
.ai-key-val { font-size: 13px; font-family: 'SF Mono', Monaco, Consolas, monospace; color: var(--c-text-secondary); }
.ai-key-input-group { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }
.ai-key-input {
  flex: 1; min-width: 0; height: 34px; border: 1.5px solid var(--c-border); border-radius: 8px;
  padding: 0 12px; font-size: 13px; font-family: 'SF Mono', Monaco, Consolas, monospace;
  transition: border-color .15s; background: var(--c-surface);
}
.ai-key-input:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-bg); outline: none; }
.ai-row-bottom { display: flex; align-items: center; gap: 12px; margin-top: 8px; }
.ai-link { font-size: 12px; color: var(--c-primary); text-decoration: none; }
.ai-link:hover { text-decoration: underline; }
.btn-link {
  background: none; border: none; color: var(--c-primary); font-size: 12px; font-weight: 600;
  cursor: pointer; padding: 0; text-decoration: underline;
}
.btn-link:disabled { color: var(--c-text-muted); cursor: not-allowed; }
.ai-status-ok { font-size: 12px; color: var(--c-success); font-weight: 600; }
.ai-status-fail { font-size: 12px; color: var(--c-danger); font-weight: 600; }
.ai-model-grid { display: flex; flex-direction: column; gap: 10px; }
.ai-model-card {
  display: flex; align-items: center; gap: 14px;
  padding: 12px 16px; background: var(--c-surface-2); border: 1.5px solid var(--c-border); border-radius: 10px;
}
.ai-model-head {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; font-weight: 700; color: var(--c-text); min-width: 90px; margin-bottom: 0;
}
.ai-model-select { flex: 1; max-width: 260px; }
.ai-model-foot { display: flex; align-items: center; gap: 10px; }
.ai-model-desc { font-size: 11px; color: var(--c-text-muted); }
.ai-model-head svg { color: var(--c-primary); }
.ai-model-select {
  width: 100%; padding: 8px 10px; border: 1.5px solid var(--c-border); border-radius: 8px;
  font-size: 13px; color: var(--c-text); background: var(--c-surface); outline: none; cursor: pointer;
  transition: border-color .15s;
}
.ai-model-select:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-bg); }

/* QR Code Manager */
.qrcode-quick-area { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.qrcode-quick-card {
  border: 2px solid var(--c-border); border-radius: 14px; overflow: hidden;
  transition: all .25s; cursor: pointer; background: var(--c-surface);
}
.qrcode-quick-card:hover { border-color: var(--c-border); }
.qrcode-quick-card.active { border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-bg); }
.qrcode-quick-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px 0 18px;
}
.qrcode-quick-badge {
  padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 700;
}
.qq-wx { background: var(--c-success-bg); color: var(--c-success); }
.qq-alipay { background: var(--c-primary-bg); color: var(--c-primary); }
.qrcode-quick-status { font-size: 11.5px; color: var(--c-text-muted); font-weight: 500; }
.qrcode-quick-status.qq-none { color: var(--c-warning); }
.qrcode-quick-upload {
  height: 160px; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; margin: 12px; border: 2px dashed var(--c-border); border-radius: 10px;
  transition: all .2s; position: relative; overflow: hidden;
}
.qrcode-quick-card.active .qrcode-quick-upload { border-color: var(--c-primary); background: var(--c-primary-bg); }
.qrcode-quick-upload span { font-size: 13px; font-weight: 500; color: var(--c-text-muted); }
.qrcode-quick-sub { font-size: 11px; color: var(--c-text-muted); }
.qrcode-quick-preview { width: 100%; height: 100%; object-fit: contain; padding: 8px; }
.qrcode-remove-btn {
  position: absolute; top: 6px; right: 6px; width: 22px; height: 22px; border-radius: 50%;
  background: var(--c-danger); color: #fff; border: none; font-size: 13px; font-weight: 700;
  cursor: pointer; display: flex; align-items: center; justify-content: center; line-height: 1;
}
.qrcode-form-inline {
  display: flex; flex-direction: column; gap: 12px;
  padding: 16px 20px; background: var(--c-surface-2); border: 1.5px solid var(--c-border);
  border-radius: 12px; margin-bottom: 16px;
}
.qfi-field { display: flex; flex-direction: column; gap: 6px; }
.qfi-field label { font-size: 12.5px; font-weight: 600; color: var(--c-text-secondary); }
.qfi-hint {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--c-text-muted); line-height: 1.4;
}
.qfi-hint svg { flex-shrink: 0; }
.qfi-submit { align-self: flex-start; }
.qrcode-price-select {
  width: 100%; max-width: 280px; height: 38px; padding: 0 12px;
  border: 1.5px solid var(--c-border); border-radius: 8px; background: var(--c-surface);
  font-size: 13px; color: var(--c-text); outline: none; cursor: pointer; appearance: auto;
}
.qrcode-price-select:focus { border-color: var(--c-primary); }
.custom-price-row { display: flex; align-items: center; margin-top: 6px; }
.custom-price-prefix {
  height: 38px; display: flex; align-items: center; padding: 0 12px;
  background: var(--c-border-light); border: 1.5px solid var(--c-border); border-right: none;
  border-radius: 8px 0 0 8px; font-size: 14px; font-weight: 600; color: var(--c-text-secondary);
}
.custom-price-input {
  width: 200px; height: 38px; padding: 0 12px; border: 1.5px solid var(--c-border);
  border-radius: 0 8px 8px 0; background: var(--c-surface); font-size: 13px; color: var(--c-text); outline: none;
}
.custom-price-input:focus { border-color: var(--c-primary); }
.qrcode-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.qrcode-card {
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 12px; overflow: hidden;
  transition: all .2s;
}
.qrcode-card:hover { border-color: var(--c-border); box-shadow: 0 2px 8px rgba(20,20,24,.06); }
.qrcode-card.qrcode-disabled { opacity: .5; }
.qrcode-card-img-box {
  height: 140px; background: var(--c-surface-2); display: flex; align-items: center; justify-content: center;
  padding: 8px;
}
.qrcode-card-img { max-width: 100%; max-height: 100%; object-fit: contain; }
.qrcode-card-placeholder { display: flex; align-items: center; justify-content: center; opacity: .3; }
.qrcode-card-info { padding: 10px 12px; }
.qrcode-card-tag { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 4px; }
.tag-wx { background: var(--c-success-bg); color: var(--c-success); padding: 1px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; }
.tag-alipay { background: var(--c-primary-bg); color: var(--c-primary); padding: 1px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; }
.tag-universal { background: var(--c-primary-bg); color: var(--c-primary); padding: 1px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; }
.tag-price { background: var(--c-border-light); color: var(--c-text-secondary); padding: 1px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; }
.tag-active { background: var(--c-success-bg); color: var(--c-success); padding: 1px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; }
.tag-inactive { background: var(--c-danger-bg); color: var(--c-danger); padding: 1px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; }
.qrcode-card-id { font-size: 10.5px; color: var(--c-text-muted); font-family: 'SF Mono','Consolas',monospace; }

/* 收款通道管理 */
.channel-section { margin-bottom: 24px; }
.channel-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.channel-title { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; color: var(--c-text); }
.channel-count { font-size: 12px; color: var(--c-text-muted); font-weight: 400; }
.channel-list { display: flex; flex-direction: column; gap: 8px; }
.channel-card { background: var(--c-surface-2); border: 1px solid var(--c-border); border-radius: 10px; padding: 14px 16px; transition: all .15s; }
.channel-card:hover { border-color: var(--c-border); box-shadow: 0 2px 8px rgba(20,20,24,.06); }
.channel-card.disabled { opacity: .5; }
.channel-card-top { display: flex; align-items: center; justify-content: space-between; }
.channel-card-name { font-size: 14px; font-weight: 600; color: var(--c-text); }
.channel-card-actions { display: flex; gap: 4px; }
.btn-icon { background: none; border: none; cursor: pointer; padding: 4px; border-radius: 6px; display: flex; align-items: center; justify-content: center; transition: background .15s; }
.btn-icon:hover { background: var(--c-border); }
.channel-card-meta { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.channel-code-tag { font-size: 11px; background: var(--c-primary-bg); color: var(--c-primary); padding: 2px 8px; border-radius: 4px; font-family: 'SF Mono','Consolas',monospace; }
.channel-status-dot { width: 8px; height: 8px; border-radius: 50%; }
.channel-status-dot.online { background: var(--c-success); box-shadow: 0 0 6px rgba(22,163,74,.4); }
.channel-status-dot.offline { background: var(--c-text-muted); }
.channel-status-text { font-size: 12px; color: var(--c-text-muted); }
.channel-empty { text-align: center; padding: 24px; color: var(--c-text-muted); font-size: 13px; background: var(--c-surface-2); border: 1px dashed var(--c-border); border-radius: 10px; }
.channel-memo { font-size: 11px; color: var(--c-text-muted); margin-left: auto; }
.modal-body select {
  padding: 10px 14px; border: 1.5px solid var(--c-border); border-radius: 10px;
  background: var(--c-surface-2); color: var(--c-text); font-size: 14px; outline: none;
  transition: border-color .15s; font-family: inherit; width: 100%; box-sizing: border-box;
  cursor: pointer;
}
.modal-body select:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-bg); background: var(--c-surface); }
.modal-body textarea {
  padding: 10px 14px; border: 1.5px solid var(--c-border); border-radius: 10px;
  background: var(--c-surface-2); color: var(--c-text); font-size: 14px; outline: none;
  transition: border-color .15s; font-family: inherit; width: 100%; box-sizing: border-box;
  resize: vertical;
}
.modal-body textarea:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-bg); background: var(--c-surface); }
.channel-help-box {
  background: var(--c-primary-bg); border: 1px solid var(--c-primary-ring); border-radius: 10px;
  padding: 14px 16px; margin-bottom: 16px; font-size: 13px; line-height: 1.7; color: var(--c-text-secondary);
}
.channel-help-title { display: flex; align-items: center; gap: 6px; font-weight: 600; font-size: 14px; color: var(--c-primary); margin-bottom: 8px; }
.channel-help-item { margin-bottom: 4px; }
.channel-help-item strong { color: var(--c-text); }
.modal-box { background: var(--c-surface); border-radius: 14px; width: 460px; max-width: 90vw; box-shadow: 0 25px 60px rgba(0,0,0,.2); overflow: hidden; }
.modal-header { display: flex; align-items: center; justify-content: space-between; padding: 20px 24px 0; }
.modal-header h3 { font-size: 17px; font-weight: 700; color: var(--c-text); margin: 0; }
.modal-close { background: none; border: none; font-size: 22px; color: var(--c-text-muted); cursor: pointer; padding: 4px 8px; border-radius: 6px; }
.modal-close:hover { background: var(--c-border-light); color: var(--c-text-muted); }
.modal-body { padding: 20px 24px; }
.modal-body .field { margin-bottom: 16px; }
.modal-body .field label { display: block; font-size: 13px; font-weight: 600; color: var(--c-text-secondary); margin-bottom: 6px; }
.modal-body .field input, .modal-body .field select, .modal-body .field textarea { width: 100%; padding: 8px 12px; border: 1px solid var(--c-border); border-radius: 8px; font-size: 14px; background: var(--c-surface); }
.modal-body .field textarea { resize: vertical; font-family: inherit; }
.modal-body .field input:focus, .modal-body .field select:focus, .modal-body .field textarea:focus { outline: none; border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-bg); }
.field-hint { font-size: 11.5px; color: var(--c-text-muted); margin-top: 4px; display: block; }
.field-divider { border-top: 1px solid var(--c-border); padding-top: 14px; margin-top: 8px; }
.field-divider span { font-size: 13px; font-weight: 600; color: var(--c-text-muted); display: block; }
.field-divider small { font-size: 11.5px; color: var(--c-text-muted); display: block; margin-top: 2px; }
.qr-upload-row { display: flex; gap: 8px; align-items: flex-start; }
.qr-upload-row textarea { flex: 1; }
.btn-upload-qr {
  flex-shrink: 0; height: 38px; padding: 0 14px; border: 1.5px solid var(--c-border); border-radius: 8px;
  background: var(--c-surface-2); color: var(--c-text-secondary); font-size: 12.5px; font-weight: 600;
  cursor: pointer; display: flex; align-items: center; gap: 5px; transition: all .2s; white-space: nowrap;
}
.btn-upload-qr:hover { border-color: var(--c-primary); color: var(--c-primary); background: var(--c-primary-bg); }
.btn-upload-qr:disabled { opacity: .6; cursor: not-allowed; }
.modal-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 0 24px 20px; }

.modal-overlay {
  position: fixed; inset: 0; background: rgba(22,22,26,.42);
  display: flex; align-items: center; justify-content: center; z-index: 200;
}
.modal {
  background: var(--c-surface); border-radius: 14px; padding: 32px;
  width: 400px; max-width: 90vw; box-shadow: 0 25px 60px rgba(0,0,0,.2);
}
.modal h3 { font-size: 17px; font-weight: 700; margin-bottom: 4px; color: var(--c-text); }
.modal-sub { font-size: 13px; color: var(--c-text-muted); margin-bottom: 20px; }
.rate-input-row { display: flex; align-items: center; gap: 12px; }
.rate-input-row input { flex: 1; }
.rate-pct { font-size: 18px; font-weight: 700; color: var(--c-primary); min-width: 48px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 24px; }

/* Queue Panel */
.queue-panel { display: flex; flex-direction: column; gap: 16px; }
.queue-header {
  display: flex; align-items: center; justify-content: space-between;
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 12px;
  padding: 16px 22px; box-shadow: 0 1px 3px rgba(20,20,24,.06);
}
.queue-status-badge { display: flex; align-items: center; gap: 8px; }
.qsb-dot { width: 10px; height: 10px; border-radius: 50%; }
.qsb-dot.qsb-live { background: var(--c-success); box-shadow: 0 0 8px rgba(34,197,94,.4); animation: pulse-dot 1.5s ease-in-out infinite; }
.qsb-dot.qsb-paused { background: var(--c-warning); box-shadow: 0 0 8px rgba(245,158,11,.4); }
.qsb-text { font-size: 13px; font-weight: 600; color: var(--c-text); }
.qsb-queue-tag {
  font-size: 11px; font-weight: 500; color: var(--c-primary); background: var(--c-primary-bg);
  padding: 2px 8px; border-radius: 4px; margin-left: 6px;
}
.queue-actions { display: flex; gap: 8px; }

.queue-kpi-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
.qkpi {
  background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: 12px; padding: 18px; text-align: center; box-shadow: 0 1px 3px rgba(20,20,24,.06);
}
.qkpi-val { font-size: 26px; font-weight: 700; color: var(--c-text); }
.qkpi-val.qkpi-running { color: var(--c-primary); }
.qkpi-val.qkpi-info { color: var(--c-warning); }
.qkpi-val.qkpi-ok { color: var(--c-success); }
.qkpi-val.qkpi-bad { color: var(--c-danger); }
.qkpi-val.qkpi-blue { color: var(--c-info); }
.qkpi-label { font-size: 11.5px; color: var(--c-text-muted); margin-top: 4px; }

.queue-config-row {
  display: flex; align-items: center; gap: 10px;
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 12px;
  padding: 14px 22px; box-shadow: 0 1px 3px rgba(20,20,24,.06);
}
.qcfg-label { font-size: 13px; font-weight: 600; color: var(--c-text-secondary); }
.qcfg-input {
  width: 60px; height: 36px; padding: 0 10px; border: 1.5px solid var(--c-border);
  border-radius: 8px; text-align: center; font-size: 14px; font-weight: 600;
  color: var(--c-text); outline: none;
}
.queue-specs-card {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
  background: var(--c-surface-2); border: 1px solid var(--c-border); border-radius: 12px;
  padding: 14px 22px;
}
.spec-row { display: flex; flex-direction: column; gap: 2px; }
.spec-label { font-size: 11px; color: var(--c-text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.spec-val { font-size: 15px; font-weight: 600; color: var(--c-text-secondary); }
.spec-highlight { color: var(--c-primary); }
.qcfg-input:focus { border-color: var(--c-primary); }

.q-progress { width: 80px; height: 6px; background: var(--c-border-light); border-radius: 3px; overflow: hidden; }
.q-prog-bar { height: 100%; background: var(--c-primary); border-radius: 3px; transition: width .3s; }

.queue-tabs { display: flex; gap: 8px; }
.queue-sub-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.sub-queue-card {
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 12px;
  padding: 14px 18px; box-shadow: 0 1px 3px rgba(20,20,24,.06);
}
.sub-queue-title { font-size: 13px; font-weight: 600; color: var(--c-text); margin-bottom: 8px; }
.sub-queue-row { display: flex; gap: 16px; font-size: 13px; color: var(--c-text-secondary); }
.sub-queue-row .text-red { color: var(--c-danger); }

/* Pricing Tab */
.pricing-tab { width: 100%; max-width: 720px; }
.pricing-section { margin-top: 12px; }
.pricing-mode-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.pricing-rows { display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px; }
.pricing-row {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 16px 18px; background: var(--c-surface-2); border: 1.5px solid var(--c-border);
  border-radius: 10px; transition: border-color .15s;
}
.pricing-row:hover { border-color: var(--c-border); }
.pr-left { display: flex; align-items: center; gap: 12px; }
.pr-icon {
  width: 40px; height: 40px; border-radius: 10px; display: flex;
  align-items: center; justify-content: center; flex-shrink: 0;
}
.pr-icon.video { background: var(--c-primary-bg); color: var(--c-primary); }
.pr-icon.exam { background: var(--c-success-bg); color: var(--c-success); }
.pr-info { display: flex; flex-direction: column; gap: 2px; }
.pr-name { font-size: 14px; font-weight: 600; color: var(--c-text); }
.pr-unit { font-size: 12px; color: var(--c-text-muted); }
.pr-input-wrap { display: flex; align-items: center; }
.pr-prefix {
  font-size: 16px; font-weight: 700; color: var(--c-text);
  background: var(--c-surface); border: 1.5px solid var(--c-border); border-right: none;
  border-radius: 10px 0 0 10px; padding: 0 10px; height: 44px;
  display: flex; align-items: center;
}
.pr-input {
  width: 110px; height: 44px; padding: 0 12px;
  border: 1.5px solid var(--c-border); border-radius: 0 10px 10px 0;
  background: var(--c-surface); color: var(--c-text); font-size: 16px; font-weight: 700;
  outline: none; transition: border-color .15s;
}
.pr-input:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-bg); }

/* 打包定价当前状态 */
.pkg-current-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 12px; }
.pkg-card {
  background: var(--c-surface-2); border: 1.5px solid var(--c-border); border-radius: 10px;
  padding: 16px; text-align: center;
}
.pkg-card-label { font-size: 12px; color: var(--c-text-muted); font-weight: 500; margin-bottom: 6px; }
.pkg-card-price { font-size: 22px; font-weight: 800; color: var(--c-text); }
.pkg-discount-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.pkg-discount-tag {
  padding: 4px 10px; background: var(--c-border-light); border-radius: 6px;
  font-size: 12px; color: var(--c-text-secondary); font-weight: 600;
}
.pricing-section-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;
}
.pricing-section-title { font-size: 13px; font-weight: 600; color: var(--c-text-secondary); }
.pricing-edit-actions { display: flex; gap: 6px; }
.pkg-card-input {
  display: flex; align-items: center; justify-content: center; margin-top: 4px;
}
.pkg-input-prefix {
  font-size: 16px; font-weight: 700; color: var(--c-text);
  background: var(--c-border-light); border: 1.5px solid var(--c-border); border-right: none;
  border-radius: 6px 0 0 6px; padding: 0 8px; height: 36px;
  display: flex; align-items: center;
}
.pkg-card-input input {
  width: 80px; height: 36px; padding: 0 8px;
  border: 1.5px solid var(--c-border); border-radius: 0 6px 6px 0;
  background: var(--c-surface); color: var(--c-text); font-size: 16px; font-weight: 700;
  outline: none; text-align: center;
}
.pkg-card-input input:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-bg); }
.pkg-discount-edit {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 8px; background: var(--c-surface); border: 1.5px solid var(--c-border); border-radius: 6px;
}
.pkg-disc-label { font-size: 11px; color: var(--c-text-muted); font-weight: 600; white-space: nowrap; }
.pkg-discount-edit input {
  width: 56px; height: 28px; padding: 0 4px;
  border: 1px solid var(--c-border); border-radius: 4px;
  background: var(--c-surface); color: var(--c-text); font-size: 13px; font-weight: 600;
  outline: none; text-align: center;
}
.pkg-discount-edit .pkg-input-prefix {
  font-size: 13px; height: 28px; padding: 0 4px;
  border-radius: 4px 0 0 4px;
}
.pkg-discount-edit input:focus { border-color: var(--c-primary); }

/* AI 定价顾问 */
.ai-advisor-card { margin-top: 20px; border: 1.5px solid var(--c-primary-bg); background: var(--c-gradient-soft); }
.ai-advisor-card h3 { color: var(--c-primary); }
.market-input-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }
.market-field { display: flex; flex-direction: column; gap: 6px; }
.market-field label { font-size: 13px; font-weight: 600; color: var(--c-text-secondary); }
.field-required { color: var(--c-danger); }
.field-hint { font-size: 11px; color: var(--c-text-muted); }
.market-textarea {
  width: 100%; padding: 10px 14px; border: 1.5px solid var(--c-border); border-radius: 10px;
  font-size: 13px; color: var(--c-text); background: var(--c-surface); resize: vertical;
  outline: none; transition: border-color .15s; font-family: inherit;
}
.market-textarea:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-bg); }
.btn-ai {
  background: var(--c-primary);
  color: #fff; border: none; border-radius: 10px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.btn-ai:hover { opacity: 0.9; }
.btn-ai:disabled { opacity: 0.5; cursor: not-allowed; }

/* 推荐结果 */
.recommend-result {
  margin-top: 20px; padding: 20px; background: var(--c-surface); border: 1.5px solid var(--c-border);
  border-radius: 14px; animation: fadeInUp .3s ease;
}
@keyframes fadeInUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.recommend-header { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.recommend-ai-badge {
  padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700;
  background: var(--c-danger-bg); color: var(--c-danger);
}
.recommend-ai-badge.ai-ok { background: var(--c-success-bg); color: var(--c-success); }
.strategy-box {
  padding: 14px 16px; background: var(--c-primary-bg); border: 1px solid var(--c-primary-bg);
  border-radius: 10px; margin-bottom: 16px;
}
.strategy-label { font-size: 12px; font-weight: 700; color: var(--c-primary); margin-bottom: 4px; }
.strategy-text { font-size: 13px; color: var(--c-primary); line-height: 1.5; }
.recommend-prices { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 12px; }
.rec-price-card {
  padding: 14px 10px; background: var(--c-surface-2); border: 1.5px solid var(--c-border);
  border-radius: 10px; text-align: center;
}
.rec-price-card.accent { border-color: var(--c-text); background: var(--c-surface-2); }
.rec-price-label { font-size: 11px; color: var(--c-text-muted); font-weight: 600; margin-bottom: 4px; }
.rec-price-value { font-size: 20px; font-weight: 800; color: var(--c-text); }
.rec-price-card.accent .rec-price-value { color: var(--c-text); }
.recommend-discounts { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.rec-disc-item {
  padding: 4px 10px; background: var(--c-border-light); border-radius: 6px;
  font-size: 12px; color: var(--c-text-secondary); font-weight: 600;
}

/* 场景对比表 */
.scenario-table-wrap { margin-top: 8px; }
.scenario-table-label { font-size: 13px; font-weight: 700; color: var(--c-text-secondary); margin-bottom: 8px; }
.scenario-table {
  width: 100%; border-collapse: collapse; font-size: 13px;
}
.scenario-table th {
  padding: 8px 10px; background: var(--c-border-light); color: var(--c-text-secondary); font-weight: 600;
  text-align: left; border-bottom: 1.5px solid var(--c-border);
}
.scenario-table td {
  padding: 8px 10px; border-bottom: 1px solid var(--c-border-light); color: var(--c-text-secondary);
}
.scenario-table tr:hover td { background: var(--c-surface-2); }
.scenario-table .your-price { font-weight: 700; color: var(--c-primary); }
.compare-tag {
  padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700;
}
.compare-low { background: var(--c-success-bg); color: var(--c-success); }
.compare-same { background: var(--c-warning-bg); color: var(--c-warning); }
.btn-success {
  background: var(--c-success);
  color: #fff; border: none; border-radius: 10px; font-weight: 700;
}
.btn-success:hover { opacity: 0.9; }
.btn-success:disabled { opacity: 0.5; cursor: not-allowed; }

/* Payment Admin */
.monitor-summary { background: var(--c-surface-2); border: 1px solid var(--c-border); border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; }
.monitor-summary-row { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.monitor-summary-item { font-size: 13px; color: var(--c-text-muted); }
.text-warn { color: var(--c-warning); }
.text-ok { color: var(--c-success); }
.ypay-tab { width: 100%; }
.ypay-subtabs { display: flex; gap: 4px; margin-bottom: 18px; }
.ypay-subtab {
  padding: 8px 20px; border: 1px solid var(--c-border); border-radius: 8px;
  background: var(--c-surface); color: var(--c-text-muted); font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all .15s;
}
.ypay-subtab:hover { border-color: var(--c-primary); color: var(--c-primary); }
.ypay-subtab.active { background: var(--c-primary); color: #fff; border-color: var(--c-primary); }

.ypay-order-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; flex-wrap: wrap; gap: 8px; }
.ypay-order-filters { display: flex; gap: 4px; }
.ypay-filter-btn {
  padding: 5px 14px; border: 1px solid var(--c-border); border-radius: 8px;
  background: var(--c-surface); color: var(--c-text-muted); font-size: 12.5px; font-weight: 500; cursor: pointer; transition: all 0.15s;
}
.ypay-filter-btn:hover { border-color: var(--c-primary); color: var(--c-primary); }
.ypay-filter-btn.active { background: var(--c-primary); color: #fff; border-color: var(--c-primary); }

.ypay-status-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.ypay-stat-item {
  background: var(--c-surface-2); border: 1px solid var(--c-border);
  border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 6px;
}
.ypay-stat-label { font-size: 11.5px; color: var(--c-text-muted); font-weight: 500; }
.ypay-stat-value { font-size: 15px; font-weight: 700; color: var(--c-text); }
.ypay-stat-value.warn { color: var(--c-warning); }
.ypay-stat-value.success { color: var(--c-success); }
.ypay-stat-badge {
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 14px; border-radius: 14px; font-size: 12px; font-weight: 600;
}
.ypay-stat-badge.online { background: var(--c-success-bg); color: var(--c-success); }
.ypay-stat-badge.offline { background: var(--c-danger-bg); color: var(--c-danger); }
.ypay-stat-badge.key-mismatch { background: var(--c-warning-bg); color: var(--c-warning); gap: 6px; }
.ypay-stat-badge.key-mismatch svg { stroke: var(--c-warning); }
.ypay-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.dot-live { background: var(--c-success); box-shadow: 0 0 6px rgba(34,197,94,.5); animation: pulse-dot 1.5s ease-in-out infinite; }
.dot-dead { background: var(--c-danger); }
@keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }
.ypay-heart-stale { color: var(--c-danger) !important; }

.ypay-key-mismatch-alert {
  display: flex; align-items: flex-start; gap: 12px; margin-top: 14px; padding: 14px 18px;
  background: var(--c-warning-bg); border: 1px solid rgba(251,191,36,.4); border-radius: 12px; color: var(--c-warning);
}
.ypay-key-mismatch-alert svg { flex-shrink: 0; margin-top: 2px; stroke: var(--c-warning); }
.ypay-key-mismatch-text { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; line-height: 1.5; }
.ypay-key-mismatch-text strong { font-size: 13px; color: var(--c-warning); }

.ypay-health-section { margin-top: 16px; padding: 14px 18px; background: var(--c-surface-2); border: 1px solid var(--c-border); border-radius: 12px; }
.ypay-health-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.ypay-health-label { font-size: 13px; font-weight: 600; color: var(--c-text-secondary); }
.ypay-health-rate { font-size: 18px; font-weight: 700; }
.ypay-health-rate.good { color: var(--c-success); }
.ypay-health-rate.warn { color: var(--c-warning); }
.ypay-health-rate.bad { color: var(--c-danger); }
.ypay-health-bar-track { height: 6px; background: var(--c-border); border-radius: 3px; overflow: hidden; }
.ypay-health-bar-fill { height: 100%; border-radius: 3px; transition: width 0.6s ease; }
.ypay-health-bar-fill.good { background: var(--c-success); }
.ypay-health-bar-fill.warn { background: var(--c-warning); }
.ypay-health-bar-fill.bad { background: var(--c-danger); }
.ypay-health-stats { display: flex; gap: 16px; margin-top: 8px; font-size: 12px; color: var(--c-text-muted); }
.ypay-health-ok { color: var(--c-success); }
.ypay-health-fail { color: var(--c-danger); }
.ypay-health-ip { color: var(--c-primary); }

.ypay-actions-row { display: flex; gap: 10px; margin-top: 12px; }
.ypay-test-panel { margin-top: 16px; border: 1px solid var(--c-border); border-radius: 12px; overflow: hidden; }
.ypay-test-summary { padding: 14px 18px; font-size: 13px; font-weight: 600; }
.ypay-test-summary.all-ok { background: var(--c-success-bg); color: var(--c-success); }
.ypay-test-summary.has-issue { background: var(--c-danger-bg); color: var(--c-danger); }
.ypay-test-item { display: flex; align-items: center; gap: 10px; padding: 10px 18px; border-top: 1px solid var(--c-border-light); font-size: 12.5px; }
.ypay-test-item:last-child { border-radius: 0 0 12px 12px; }
.ypay-test-item.ok { background: var(--c-surface); }
.ypay-test-item.fail { background: rgba(220,38,38,.06); }
.ypay-test-icon {
  width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.ypay-test-item.ok .ypay-test-icon { background: var(--c-success-bg); color: var(--c-success); }
.ypay-test-item.fail .ypay-test-icon { background: var(--c-danger-bg); color: var(--c-danger); }
.ypay-test-name { min-width: 90px; font-weight: 600; color: var(--c-text); flex-shrink: 0; }
.ypay-test-msg { color: var(--c-text-muted); }

.channel-test-loading { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 32px; color: var(--c-text-muted); font-size: 14px; }
.channel-test-checks { margin-bottom: 16px; border: 1px solid var(--c-border); border-radius: 12px; overflow: hidden; }
.channel-test-qr { text-align: center; padding: 20px; background: var(--c-surface-2); border: 2px dashed var(--c-border); border-radius: 12px; margin-top: 12px; }
.channel-test-qr-label { font-size: 13px; color: var(--c-text-muted); margin: 0 0 12px; }
.channel-test-qr-img { width: 200px; height: 200px; border-radius: 8px; box-shadow: 0 2px 8px rgba(20,20,24,.09); }
.channel-test-qr-hint { font-size: 12px; color: var(--c-text-muted); margin: 10px 0 0; }
.channel-test-ok { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 16px; background: var(--c-success-bg); border-radius: 12px; color: var(--c-success); font-weight: 600; font-size: 14px; margin-top: 12px; }

.paytest-checks { margin: 16px 0; border: 1px solid var(--c-border); border-radius: 12px; overflow: hidden; }
.paytest-start { margin: 20px 0; text-align: center; }
.paytest-pay-area { margin-top: 20px; }
.paytest-qr-box { display: flex; flex-direction: column; align-items: center; gap: 16px; padding: 32px; background: var(--c-surface-2); border: 2px dashed var(--c-border); border-radius: 16px; }
.paytest-qr-img { width: 220px; height: 220px; border-radius: 8px; box-shadow: 0 2px 12px rgba(20,20,24,.09); }
.paytest-amount { font-size: 16px; color: var(--c-text-secondary); }
.paytest-amount strong { font-size: 20px; color: var(--c-danger); }
.paytest-amount-warn { font-size: 12px; color: var(--c-danger); margin-top: 4px; }
.paytest-status { margin-top: 16px; text-align: center; }
.paytest-waiting { display: flex; align-items: center; justify-content: center; gap: 10px; color: var(--c-text-muted); font-size: 14px; }
.paytest-success { display: flex; align-items: center; justify-content: center; gap: 10px; color: var(--c-success); font-size: 15px; font-weight: 600; padding: 16px; background: var(--c-success-bg); border-radius: 12px; }
.paytest-expired { display: flex; align-items: center; justify-content: center; gap: 10px; color: var(--c-danger); font-size: 14px; padding: 16px; background: var(--c-danger-bg); border-radius: 12px; }

.ypay-state {
  display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11.5px; font-weight: 600;
}
.ypay-state.paid { background: var(--c-success-bg); color: var(--c-success); }
.ypay-state.unpaid { background: var(--c-warning-bg); color: var(--c-warning); }
.ypay-state.closed { background: var(--c-border-light); color: var(--c-text-muted); }

.ypay-settings-layout { display: flex; flex-direction: column; gap: 20px; }
.ypay-qr-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.ypay-qr-card { text-align: center; }
.ypay-qr-img-wrap {
  width: 160px; height: 160px; margin: 16px auto; display: flex;
  align-items: center; justify-content: center; background: var(--c-surface);
  border: 1px solid var(--c-border); border-radius: 10px; overflow: hidden;
}
.ypay-qr-img { width: 140px; height: 140px; object-fit: contain; transition: opacity .3s; }
.qr-loading {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 8px; color: var(--c-text-muted); font-size: 12px; z-index: 1;
}
.qr-spinner {
  width: 28px; height: 28px; border: 3px solid var(--c-border);
  border-top-color: var(--c-primary); border-radius: 50%; animation: qr-spin .8s linear infinite;
}
@keyframes qr-spin { to { transform: rotate(360deg); } }

.hint-text { font-size: 11px; color: var(--c-text-muted); font-weight: 400; }

.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.field-row .field { margin-bottom: 16px; }

.settings-card select {
  height: 44px; padding: 0 14px; border: 1.5px solid var(--c-border);
  border-radius: 10px; background: var(--c-surface-2); color: var(--c-text);
  font-size: 14px; outline: none; width: 100%;
}
.settings-card textarea {
  padding: 10px 14px; border: 1.5px solid var(--c-border); border-radius: 10px;
  background: var(--c-surface-2); color: var(--c-text); font-size: 14px; outline: none;
  width: 100%; resize: vertical; font-family: inherit; box-sizing: border-box;
}
.settings-card textarea:focus, .settings-card select:focus {
  border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-bg); background: var(--c-surface);
}

.mono { font-family: 'SF Mono', 'Consolas', monospace; font-size: 12px; }
.small { font-size: 11.5px; color: var(--c-text-muted); }

.pagination {
  display: flex; align-items: center; justify-content: center; gap: 12px;
  margin-top: 16px; padding: 12px 0;
}
.pagination button {
  padding: 6px 14px; border: 1px solid var(--c-border); border-radius: 8px;
  background: var(--c-surface); color: var(--c-text-muted); font-size: 12px; cursor: pointer;
}
.pagination button:hover:not(:disabled) { border-color: var(--c-primary); color: var(--c-primary); }
.pagination button:disabled { opacity: .4; cursor: not-allowed; }
.pagination span { font-size: 12px; color: var(--c-text-muted); }

.app-config-layout { display: grid; grid-template-columns: 280px 1fr; gap: 24px; align-items: start; }
.app-qrcode-box { text-align: center; }
.app-qrcode-label { font-size: 13px; font-weight: 600; color: var(--c-text-secondary); margin-bottom: 12px; }
.app-qrcode-img { width: 220px; height: 220px; border: 1px solid var(--c-border); border-radius: 12px; padding: 8px; background: var(--c-surface); }
.app-qrcode-hint { font-size: 12px; color: var(--c-text-muted); margin-top: 10px; line-height: 1.6; }
.app-manual-box { display: flex; flex-direction: column; gap: 14px; }
.app-field { display: flex; flex-direction: column; gap: 5px; }
.app-field label { font-size: 12px; font-weight: 600; color: var(--c-text-secondary); }
.app-copy-row { display: flex; align-items: center; gap: 8px; }
.app-code { flex: 1; padding: 9px 14px; background: var(--c-border-light); border: 1px solid var(--c-border); border-radius: 8px; font-size: 12.5px; font-family: 'SF Mono','Consolas',monospace; color: var(--c-text); word-break: break-all; }
.app-copy-btn { flex-shrink: 0; }
.app-steps { margin-top: 6px; padding: 14px 16px; background: var(--c-surface-2); border: 1px solid var(--c-border); border-radius: 10px; }
.app-step-label { font-size: 12px; font-weight: 600; color: var(--c-text-secondary); margin-bottom: 8px; }
.app-step-list { margin: 0; padding-left: 20px; font-size: 12.5px; color: var(--c-text-muted); line-height: 1.9; }

@keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }

@media (max-width: 768px) {
  .kpi-row { grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .kpi-card { padding: 12px 10px; }
  .kpi-val { font-size: 20px; }
  .kpi-label { font-size: 11px; }
  .panel-row { grid-template-columns: 1fr; }
  .panel-wide, .panel-wide-sm { grid-column: span 1; }
  .agent-stats-row { grid-template-columns: repeat(2, 1fr); }
  .chart-area { height: 120px; }
  .mt-row { grid-template-columns: 1fr 1fr 1fr; }

  /* Sidebar: hidden by default, overlay when open */
  .admin-layout { flex-direction: column; }
  .sidebar {
    position: fixed;
    left: 0; top: 0; bottom: 0;
    width: 260px;
    transform: translateX(-100%);
    transition: transform .25s ease;
    z-index: 50;
  }
  .sidebar.mobile-open { transform: translateX(0); }
  .sidebar-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(22,22,26,.42);
    z-index: 45;
  }
  .sidebar-overlay.show { display: block; }
  .sidebar .sidebar-item-label { display: inline; }
  .sidebar .sb-logo span { display: inline; }
  .sidebar.collapsed { width: 260px; transform: translateX(-100%); }

  .main-content { margin-left: 0; width: 100%; }
  .sidebar.collapsed ~ .main-content { margin-left: 0; }

  /* Mobile sidebar toggle button */
  .mobile-sidebar-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px; height: 40px;
    background: var(--c-primary);
    border: none;
    border-radius: 10px;
    cursor: pointer;
    flex-shrink: 0;
    color: #fff;
  }

  .content-topbar { padding: 0 12px; height: 48px; }
  .content-topbar h2 { font-size: 14px; }
  .content-body { padding: 12px 12px 80px; }

  .app-config-layout { grid-template-columns: 1fr; }
  .app-qrcode-img { width: 180px; height: 180px; }
  .qrcode-quick-area { grid-template-columns: 1fr; }
  .qrcode-list { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); }

  .field-row { grid-template-columns: 1fr; }

  .ypay-qr-cards { grid-template-columns: 1fr; }

  .data-table { font-size: 12px; }
  .data-table th, .data-table td { padding: 8px; font-size: 11px; }

  /* Mobile Bottom Nav - removed, sidebar handles navigation */

  .pagination { flex-wrap: wrap; gap: 6px; }
  .pagination button { padding: 5px 10px; font-size: 11px; }

  .channel-test-qr-img { width: 160px; height: 160px; }
  .paytest-qr-img { width: 180px; height: 180px; }

  /* Security - AI config mobile */
  .security-tab { max-width: 100%; }
  .settings-card { padding: 16px; }
  .ai-row { flex-direction: column; align-items: stretch; gap: 8px; }
  .ai-key-wrap { flex-wrap: wrap; }
  .ai-key-input-group { flex-wrap: wrap; }
  .ai-key-input { min-width: 0; width: 100%; }
  .ai-model-grid { grid-template-columns: 1fr; }
  .ai-row-bottom { flex-wrap: wrap; gap: 8px; }

  /* Agent tiers - commission config mobile */
  .tier-commission-config { padding: 14px; }
  .tcc-row { grid-template-columns: 1fr; }
  .tcc-item { padding: 12px 8px; }

  /* YPay key code mobile fix */
  .ypay-key-code { min-width: 0; width: 100%; word-break: break-all; font-size: 12px; padding: 0 8px; height: auto; line-height: 1.6; white-space: normal; }
  .gen-row { flex-direction: column; }
  .gen-row .btn { align-self: flex-start; }

  /* User filter - compact mobile */
  .section-actions { flex-direction: column; align-items: stretch; gap: 8px; }
  .chip { padding: 5px 12px; font-size: 12px; white-space: nowrap; flex-shrink: 0; }
  .search-input { flex: 1; min-width: 0; }

  /* Sub-tabs horizontal scroll */
  .personnel-subtabs { overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
  .personnel-subtabs::-webkit-scrollbar { display: none; }
  .ps-tab { padding: 6px 16px; font-size: 12px; white-space: nowrap; flex-shrink: 0; }
}

.gen-row { display: flex; gap: 8px; align-items: center; }
.ypay-key-code { display: inline-block; height: 40px; line-height: 40px; padding: 0 14px; background: var(--c-border-light); border: 1px solid var(--c-border); border-radius: 8px; font-size: 13px; font-family: 'SF Mono','Consolas',monospace; color: var(--c-primary); min-width: 180px; text-align: center; }

.personnel-tab { width: 100%; }
.personnel-subtabs { display: flex; gap: 4px; margin-bottom: 18px; }
.ps-tab {
  padding: 8px 24px; border: 1px solid var(--c-border); border-radius: 8px;
  background: var(--c-surface); color: var(--c-text-muted); font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all .15s;
}
.ps-tab:hover { border-color: var(--c-primary); color: var(--c-primary); }
.ps-tab.active { background: var(--c-primary); color: #fff; border-color: var(--c-primary); }

.ps-panel { }
.ps-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; flex-wrap: wrap; gap: 8px; }
.ps-header h3 { font-size: 16px; font-weight: 700; color: var(--c-text); }
.ps-desc { font-size: 12.5px; color: var(--c-text-muted); margin-bottom: 16px; }
.ps-loading { text-align: center; padding: 40px; color: var(--c-text-muted); font-size: 13px; }
.ps-empty { text-align: center; padding: 48px; color: var(--c-text-muted); }
.ps-empty-icon { font-size: 40px; display: block; margin-bottom: 8px; }
.ps-empty p { font-size: 13px; }
.ps-table-wrap { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(20,20,24,.06); }

.badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11.5px; font-weight: 600; }
.badge-info { background: var(--c-primary-bg); color: var(--c-primary); }
.badge-success { background: var(--c-success-bg); color: var(--c-success); }
.text-muted { color: var(--c-text-muted); }

.tier-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.tier-card { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(20,20,24,.06); }
.tc-head { display: flex; align-items: center; gap: 10px; padding: 14px 16px; font-size: 13px; font-weight: 700; }
.tc-head.l1 { background: var(--c-surface-3); color: var(--c-text); }
.tc-head.l2 { background: var(--c-surface-3); color: var(--c-text); }
.tc-head.l3 { background: var(--c-surface-3); color: var(--c-text); }
.tc-badge { padding: 2px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; }
.tc-head.l1 .tc-badge { background: var(--c-primary); color: #fff; }
.tc-head.l2 .tc-badge { background: var(--c-info); color: #fff; }
.tc-head.l3 .tc-badge { background: var(--c-success); color: #fff; }
.tc-count { margin-left: auto; font-size: 12px; opacity: .7; }
.tc-body { padding: 8px 0; }
.tc-empty { padding: 24px; text-align: center; font-size: 12px; color: var(--c-text-muted); }
.tc-row { display: flex; align-items: center; gap: 10px; padding: 8px 16px; border-top: 1px solid var(--c-border-light); font-size: 13px; }
.tc-name { flex: 1; font-weight: 500; color: var(--c-text); }
.tc-balance { font-weight: 600; color: var(--c-danger); font-size: 12px; }
.tc-select { padding: 4px 8px; border: 1px solid var(--c-border); border-radius: 6px; font-size: 11px; font-weight: 600; color: var(--c-text-secondary); background: var(--c-surface); cursor: pointer; }
.tc-select:focus { border-color: var(--c-primary); outline: none; }

@media (max-width: 768px) {
  .tier-grid { grid-template-columns: 1fr; }
  .tcc-row { grid-template-columns: 1fr; }
}

.tier-commission-config {
  margin-top: 20px; padding: 20px;
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 12px;
  box-shadow: 0 1px 3px rgba(20,20,24,.06);
}
.tier-commission-config h4 { font-size: 15px; font-weight: 700; margin-bottom: 6px; color: var(--c-text); }
.tcc-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.tcc-item { text-align: center; padding: 16px 10px; background: var(--c-surface-2); border-radius: 10px; border: 1px solid var(--c-border); }
.tcc-badge { display: inline-block; padding: 2px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; margin-bottom: 6px; }
.tcc-badge.l1 { background: var(--c-primary); color: #fff; }
.tcc-badge.l2 { background: var(--c-info); color: #fff; }
.tcc-badge.l3 { background: var(--c-success); color: #fff; }
.tcc-label { display: block; font-size: 12px; color: var(--c-text-muted); margin-bottom: 8px; }
.tcc-input-row { display: flex; align-items: center; justify-content: center; gap: 6px; }
.tcc-input { width: 72px; height: 36px; padding: 0 8px; border: 1px solid var(--c-border); border-radius: 8px; text-align: center; font-size: 14px; font-weight: 700; color: var(--c-text); background: var(--c-surface); }
.tcc-input:focus { border-color: var(--c-primary); outline: none; box-shadow: 0 0 0 3px var(--c-primary-bg); }
.tcc-pct { font-size: 14px; font-weight: 700; color: var(--c-primary); }
.spinner-sm { width: 14px; height: 14px; border: 2px solid #bdbdc2; border-top-color: #fff; border-radius: 50%; animation: spin .6s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Agent Fees - Clean Cards */
.af-settings { max-width: 680px; display: flex; flex-direction: column; gap: 16px; }
.af-page-card { max-width: 100%; }
.af-action-card { padding-top: 8px; }
.af-card-header { display: flex; align-items: center; gap: 14px; margin-bottom: 24px; padding-bottom: 18px; border-bottom: 1px solid var(--c-border); }
.af-card-header-icon { width: 40px; height: 40px; border-radius: 10px; background: var(--c-primary-bg); color: var(--c-primary); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.af-header-desc { font-size: 13px; color: var(--c-text-muted); margin-top: 2px; }
.af-card-new {
  padding: 18px 0;
  border-bottom: 1px solid var(--c-border-light);
}
.af-card-new:last-of-type { border-bottom: none; }
.af-card-row { display: flex; align-items: center; gap: 16px; }
.af-card-icon-circle {
  width: 44px; height: 44px; border-radius: 12px; flex-shrink: 0;
  background: var(--c-primary-bg); color: var(--c-primary);
  display: flex; align-items: center; justify-content: center;
}
.af-card-icon-circle.af-ic-purple { background: var(--c-primary-bg); color: var(--c-primary); }
.af-card-info { flex: 1; min-width: 0; }
.af-card-title { font-size: 15px; font-weight: 600; color: var(--c-text); }
.af-card-desc { font-size: 12.5px; color: var(--c-text-muted); margin-top: 3px; }
.af-card-fee { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.af-fee-label { font-size: 17px; font-weight: 700; color: var(--c-text-muted); }
.af-fee-inp {
  width: 90px; height: 38px; border: 1.5px solid var(--c-border); border-radius: 8px;
  padding: 0 10px; font-size: 15px; font-weight: 600; color: var(--c-text);
  text-align: left; background: var(--c-surface);
}
.af-fee-inp:focus { outline: none; border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-bg); }

.af-card-sub {
  margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--c-border-light);
  display: flex; flex-direction: column; gap: 10px;
}
.af-sub-row { display: flex; align-items: center; justify-content: space-between; padding: 0 0 0 60px; }
.af-sub-info { display: flex; align-items: center; gap: 10px; }
.af-sub-badge {
  width: 30px; height: 30px; border-radius: 7px; display: flex; align-items: center;
  justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0;
}
.af-sub-badge.l1 { background: var(--c-primary-bg); color: var(--c-primary); }
.af-sub-badge.l2 { background: var(--c-primary-bg); color: var(--c-primary); }
.af-sub-badge.l3 { background: var(--c-primary-bg); color: var(--c-primary); }
.af-sub-text { font-size: 13px; color: var(--c-text-muted); }
.af-sub-fee { display: flex; align-items: center; gap: 4px; }


.mt-col { font-size: 12px; color: var(--c-text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.btn-danger { background: var(--c-danger); color: #fff; }
.btn-danger:hover { background: #dc2626; }
.empty-text { text-align: center; padding: 24px; color: var(--c-text-muted); font-size: 13px; }

.ads-tab { width: 100%; }
.ads-help { background: var(--c-surface-2); border: 1px solid var(--c-border); border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; font-size: 13px; color: var(--c-text-muted); line-height: 1.7; }
.ads-help p { margin: 0; }
.ads-help strong { color: var(--c-text-secondary); }
.panel-head-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.panel-head-row h3 { font-size: 16px; font-weight: 700; color: var(--c-text); }
.empty-card { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 48px 20px; background: var(--c-surface); border: 1px dashed var(--c-border); border-radius: 12px; gap: 12px; }
.empty-card p { color: var(--c-text-muted); font-size: 14px; }
.slot-badge { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 8px; background: var(--c-primary-bg); color: var(--c-primary); font-size: 13px; font-weight: 700; }
.ad-name-cell { font-weight: 600; color: var(--c-text); }
.ad-preview-cell { font-size: 12px; color: var(--c-text-muted); max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.status-tag { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all .15s; }
.status-tag.active { background: var(--c-success-bg); color: var(--c-success); }
.status-tag.inactive { background: var(--c-surface-3); color: var(--c-text-muted); }
.status-tag:hover { opacity: .8; }
.row-actions { display: flex; gap: 6px; }
.slot-auto { font-size: 13px; color: var(--c-text-muted); padding: 6px 0; }
.slot-auto strong { color: var(--c-primary); }
.ad-upload-row textarea { width: 100%; }
.ad-upload-actions { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.ad-file-hint { font-size: 12px; color: var(--c-text-muted); }
.modal-wide { max-width: 640px; width: 90vw; }

.qr-thumb { width: 36px; height: 36px; border-radius: 6px; border: 1px solid var(--c-border); cursor: pointer; object-fit: cover; }
.qr-thumb:hover { transform: scale(1.1); }
.qr-modal { background: var(--c-surface); border-radius: 14px; padding: 20px; text-align: center; box-shadow: 0 25px 60px rgba(0,0,0,.15); }
.qr-modal img { max-width: 280px; max-height: 280px; display: block; margin-bottom: 12px; border-radius: 8px; }

/* 风险监控 */
.risk-tab { width: 100%; display: flex; flex-direction: column; gap: 16px; }
.risk-dashboard { display: flex; align-items: center; justify-content: space-between; gap: 32px; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 12px; padding: 24px 28px; box-shadow: 0 1px 3px rgba(20,20,24,.06); }
.risk-gauge-card { display: flex; align-items: center; gap: 24px; flex: 1; }
.risk-gauge { position: relative; width: 120px; height: 120px; flex-shrink: 0; }
.risk-gauge-svg { width: 120px; height: 120px; }
.risk-gauge-fill { transition: stroke-dasharray .8s cubic-bezier(.4,0,.2,1), stroke .3s; }
.risk-gauge-inner { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.risk-gauge-score { font-size: 36px; font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
.risk-gauge-label { font-size: 11px; color: var(--c-text-muted); margin-top: 2px; }
.risk-gauge.level-good .risk-gauge-score { color: var(--c-success); }
.risk-gauge.level-warn .risk-gauge-score { color: var(--c-warning); }
.risk-gauge.level-bad .risk-gauge-score { color: var(--c-danger); }
.risk-gauge-info { display: flex; flex-direction: column; gap: 4px; }
.risk-gauge-title { font-size: 22px; font-weight: 700; }
.risk-gauge-title.level-good { color: var(--c-success); }
.risk-gauge-title.level-warn { color: var(--c-warning); }
.risk-gauge-title.level-bad { color: var(--c-danger); }
.risk-gauge-desc { font-size: 13px; color: var(--c-text-muted); }
.risk-gauge-time { font-size: 12px; color: var(--c-text-muted); margin-top: 4px; }
.risk-actions { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
.health-settings-modal { max-width: 480px; width: 90vw; }
.health-form-group { margin-bottom: 16px; }
.health-form-group label { display: block; font-size: 13px; font-weight: 500; color: var(--text, var(--c-text)); margin-bottom: 6px; }
.health-form-input { padding: 6px 10px; border: 1px solid var(--border, var(--c-border)); border-radius: 6px; background: var(--bg, var(--c-surface)); color: var(--text, var(--c-text)); font-size: 13px; }
.health-form-input:focus { outline: none; border-color: var(--primary, #3b82f6); }
.health-account-list { border: 1px solid var(--border, var(--c-border)); border-radius: 8px; overflow: hidden; }
.health-account-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; font-size: 13px; border-bottom: 1px solid var(--border, var(--c-border)); }
.health-account-item:last-child { border-bottom: none; }
.health-account-item.active { background: color-mix(in srgb, var(--primary, #3b82f6) 8%, transparent); }
.health-account-name { flex: 1; font-weight: 500; }
.health-account-badge { font-size: 11px; color: var(--primary, #3b82f6); background: color-mix(in srgb, var(--primary, #3b82f6) 12%, transparent); padding: 1px 6px; border-radius: 4px; }
.health-account-actions { display: flex; gap: 4px; }
.health-add-row { display: flex; gap: 8px; align-items: center; }
.health-add-row .health-form-input { flex: 1; }
.risk-check-progress { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--primary, #3b82f6); margin-left: 8px; }
.risk-check-spinner { width: 14px; height: 14px; border: 2px solid var(--border, var(--c-border)); border-top-color: var(--primary, #3b82f6); border-radius: 50%; animation: risk-spin 0.8s linear infinite; }
@keyframes risk-spin { to { transform: rotate(360deg); } }
.risk-login-card { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 12px; padding: 16px 18px; margin-top: 12px; }
.risk-login-title { font-size: 14px; font-weight: 600; color: var(--c-text); margin-bottom: 4px; }
.risk-login-desc { font-size: 12px; color: var(--c-text-muted); margin-bottom: 12px; }
.risk-login-form { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.risk-login-select { padding: 7px 12px; border: 1px solid var(--c-border); border-radius: 8px; font-size: 13px; background: var(--c-surface); color: var(--c-text-secondary); min-width: 140px; }
.risk-login-input { padding: 7px 12px; border: 1px solid var(--c-border); border-radius: 8px; font-size: 13px; min-width: 120px; }
.risk-login-input:focus, .risk-login-select:focus { outline: none; border-color: var(--c-primary); box-shadow: 0 0 0 2px var(--c-primary-bg); }
.risk-checks { display: flex; flex-direction: column; gap: 8px; }
.risk-check-item { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 12px; cursor: pointer; transition: border-color .15s, box-shadow .15s; }
.risk-check-item:hover { border-color: var(--c-border); box-shadow: 0 2px 8px rgba(20,20,24,.06); }
.risk-check-main { display: flex; align-items: center; gap: 14px; padding: 16px 18px; }
.risk-check-icon { width: 28px; height: 28px; flex-shrink: 0; }
.risk-check-icon.pass { color: var(--c-success); }
.risk-check-icon.warn { color: var(--c-warning); }
.risk-check-icon.fail { color: var(--c-danger); }
.risk-check-info { flex: 1; min-width: 0; }
.risk-check-name { font-size: 14px; font-weight: 600; color: var(--c-text); }
.risk-check-desc { font-size: 12px; color: var(--c-text-muted); margin-top: 2px; }
.risk-check-status { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 20px; flex-shrink: 0; }
.risk-check-status.pass { background: var(--c-success-bg); color: var(--c-success); }
.risk-check-status.warn { background: var(--c-warning-bg); color: var(--c-warning); }
.risk-check-status.fail { background: var(--c-danger-bg); color: var(--c-danger); }
.risk-check-arrow { width: 18px; height: 18px; color: var(--c-text-muted); flex-shrink: 0; transition: transform .2s; }
.risk-check-arrow.open { transform: rotate(180deg); }
.risk-check-detail { border-top: 1px solid var(--c-border-light); padding: 16px 18px; background: var(--c-surface-2); border-radius: 0 0 12px 12px; }
.risk-health-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.risk-health-card { padding: 12px 14px; border-radius: 8px; border: 1px solid var(--c-border); background: var(--c-surface); }
.risk-health-card.health-ok { border-left: 3px solid #10b981; }
.risk-health-card.health-bad { border-left: 3px solid var(--c-danger); }
.health-name { font-size: 13px; font-weight: 600; color: var(--c-text); }
.health-domain { font-size: 11px; color: var(--c-text-muted); margin-top: 2px; }
.health-status { font-size: 12px; color: var(--c-text-secondary); margin-top: 6px; display: flex; align-items: center; gap: 6px; }
.health-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.health-dot.dot-ok { background: #10b981; }
.health-dot.dot-bad { background: var(--c-danger); }
.empty-sm { padding: 16px; text-align: center; color: var(--c-text-muted); font-size: 13px; }
.data-table-sm { font-size: 12px; }
.data-table-sm th, .data-table-sm td { padding: 8px 10px; }
.risk-interval-row { display: flex; align-items: center; gap: 10px; }
.risk-interval-row label { font-size: 13px; color: var(--c-text-secondary); white-space: nowrap; }
.risk-interval-input { width: 100px; padding: 6px 10px; border: 1px solid var(--c-border); border-radius: 8px; font-size: 13px; }
.risk-interval-hint { font-size: 12px; color: var(--c-text-muted); margin-left: 4px; }

/* 风险监控 - 手机端适配 */
@media (max-width: 768px) {
  .risk-dashboard {
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
    padding: 16px;
  }
  .risk-gauge-card {
    flex-direction: column;
    align-items: center;
    gap: 16px;
  }
  .risk-gauge {
    width: 100px;
    height: 100px;
  }
  .risk-gauge-svg {
    width: 100px;
    height: 100px;
  }
  .risk-gauge-score {
    font-size: 28px;
  }
  .risk-gauge-title {
    font-size: 18px;
    text-align: center;
  }
  .risk-gauge-desc {
    font-size: 12px;
    text-align: center;
  }
  .risk-gauge-time {
    text-align: center;
  }
  .risk-actions {
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
  }
  .risk-check-main {
    padding: 12px 14px;
    gap: 10px;
  }
  .risk-check-icon {
    width: 24px;
    height: 24px;
  }
  .risk-check-name {
    font-size: 13px;
  }
  .risk-check-desc {
    font-size: 11px;
  }
  .risk-check-status {
    font-size: 11px;
    padding: 2px 8px;
  }
  .risk-check-detail {
    padding: 12px 14px;
  }
  .risk-health-grid {
    grid-template-columns: 1fr;
  }
  .risk-interval-row {
    flex-wrap: wrap;
    gap: 8px;
  }
  .risk-interval-hint {
    width: 100%;
    margin-left: 0;
  }
  .risk-login-form {
    flex-direction: column;
    align-items: stretch;
  }
  .risk-login-input {
    min-width: 0;
    width: 100%;
  }
}
</style>

<script setup lang="ts">
// @ts-nocheck
import { ref, onMounted, onUnmounted, toRef, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { usePlatformNames } from '@/composables/usePlatformNames'
import { initAdminState } from '@/views/admin/adminState'
import { useAuth } from '@/composables/useAuth'
import { useDashboard } from '@/composables/useDashboard'
import { useOrders } from '@/composables/useOrders'
import { useUsers } from '@/composables/useUsers'
import { usePayments } from '@/composables/usePayments'
import { useSystemConfig } from '@/composables/useSystemConfig'
import { useYpayAdmin } from '@/composables/useYpayAdmin'
import AppTopbar from '@/components/AppTopbar.vue'
import OverviewTab from '@/views/admin/OverviewTab.vue'
import CommissionsTab from '@/views/admin/CommissionsTab.vue'
import OrdersTab from '@/views/admin/OrdersTab.vue'
import UsersTab from '@/views/admin/UsersTab.vue'
import AgentsTab from '@/views/admin/AgentsTab.vue'
import WithdrawalsTab from '@/views/admin/WithdrawalsTab.vue'
import QueueTab from '@/views/admin/QueueTab.vue'
import ProxyTab from '@/views/admin/ProxyTab.vue'
import SecurityTab from '@/views/admin/SecurityTab.vue'
import RiskTab from '@/views/admin/RiskTab.vue'
import PricingTab from '@/views/admin/PricingTab.vue'
import YpayTab from '@/views/admin/YpayTab.vue'
import AdsTab from '@/views/admin/AdsTab.vue'

const store = useAppStore()

// ── Composables ──
const { adminUser, adminPass, loginErr, currentRole, isLoggedIn, pwForm, changingPw, captchaToken, captchaAnswer, captchaImage, captchaLoading, doLogin, logout, changeAdminPassword, loadCaptcha } = useAuth()
const dashboard = useDashboard()
const { allSidebarItems, visibleSidebarGroups, sidebarGroups, sidebarCollapsed, mobileSidebarOpen, loadingDash, dash, dashError, fmtDate, fmtShortDate, fmtMoney, loadDashboard, statusLabel, statusClass, orderStatusLabel, orderStatusClass, maxStatusCount, maxBarRevenue, maxBarOrders, totalPlatformOrders, maxPartnerStatusCount } = dashboard
const orders = useOrders()
const users = useUsers()
const payments = usePayments()
const sysConfig = useSystemConfig()
const ypayAdmin = useYpayAdmin()

// ── Platform names ──
const { load: loadPlatformNames, getName: getPlatformName, platformNames } = usePlatformNames()

// ── Tab switching (orchestrates across composables) ──
type SidebarKey = 'overview' | 'orders' | 'queue' | 'queue_school' | 'queue_chaoxing' | 'users' | 'agents' | 'commissions' | 'withdrawals' | 'pricing' | 'ypay' | 'ads' | 'proxy' | 'risk' | 'security'
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
  if (tab === 'commissions') users.loadCommissions()
  if (tab === 'users') {
    if (currentRole.value === 'admin') { users.loadUnifiedUsers(); users.loadSubAdmins() }
  }
  if (tab === 'agents') {
    if (currentRole.value === 'admin') { users.loadAgents(); users.loadAgentsByTier(); users.loadTierCommissions(); users.loadAgentFees() }
    else { users.agentSubTab.value = 'agentMgmt'; users.loadAgents() }
  }
  if (tab === 'withdrawals') payments.loadWithdrawals()
  if (tab === 'queue' || tab === 'queue_school' || tab === 'queue_chaoxing') payments.loadQueueData()
  if (tab === 'security') { pwForm.old_password = ''; pwForm.new_password = ''; pwForm.confirm_password = ''; if (currentRole.value === 'admin') { sysConfig.loadDeepseekKey(); sysConfig.loadRiskData() } }
  if (tab === 'pricing') sysConfig.loadPricing()
  if (tab === 'ypay') ypayAdmin.loadYpay()
  if (tab === 'ads') ypayAdmin.loadAds()
  if (tab === 'proxy') { sysConfig.loadProxySettings(); sysConfig.fetchServerPublicIp() }
}

// ── Lifecycle ──
onMounted(async () => {
  loadPlatformNames()
  if (isLoggedIn.value) {
    if (store.adminToken) {
      currentRole.value = 'admin'
    } else if (store.userToken) {
      try {
        const { api } = await import('@/api')
        const r = await api.users.me()
        const role = r?.data?.role
        if (role === 'sub_admin') currentRole.value = 'sub_admin'
        else { store.clearUserToken(); isLoggedIn.value = false; return }
      } catch { store.clearUserToken(); isLoggedIn.value = false; return }
    }
    dashboard.loadDashboard(currentRole.value)
  } else {
    loadCaptcha()
  }
})

// Watch for login state changes (handles login after page load)
watch(isLoggedIn, (loggedIn) => {
  if (loggedIn) {
    dashboard.loadDashboard(currentRole.value)
  }
})

// Sync queue filter with sidebar tab
watch(activeTab, (tab) => {
  if (tab === 'queue') payments.setQueueFilter('')
  else if (tab === 'queue_school') payments.setQueueFilter('school')
  else if (tab === 'queue_chaoxing') payments.setQueueFilter('chaoxing')
})

let autoPollTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  autoPollTimer = setInterval(() => {
    if (!isLoggedIn.value) return
    if (activeTab.value === 'orders') orders.loadOrders()
    if (activeTab.value === 'ypay') ypayAdmin.loadYpay()
    if (activeTab.value === 'queue' || activeTab.value === 'queue_school' || activeTab.value === 'queue_chaoxing') payments.loadQueueData()
  }, 10000)
})

onUnmounted(() => {
  if (autoPollTimer) { clearInterval(autoPollTimer); autoPollTimer = null }
  if (payments._payTestTimer) { clearInterval(payments._payTestTimer); payments._payTestTimer = null }
})

// ── Expose all state to tab components via initAdminState ──
const adminState = initAdminState({
  // Auth
  adminUser, adminPass, loginErr, currentRole, isLoggedIn, pwForm, changingPw, doLogin, logout, changeAdminPassword,
  // Dashboard
  ...dashboard,
  activeTab,
  // Orders
  ...orders,
  // Users
  ...users,
  // Payments (withdrawals, queue, pay test)
  ...payments,
  // System config (deepseek, pricing, proxy, risk/health)
  ...sysConfig,
  // YPay admin (ypay, ads)
  ...ypayAdmin,
  // Tab switching
  switchTab,
  // Platform names
  loadPlatformNames, getPlatformName, platformNames,
})
</script>

<template>
  <div class="admin-root">
    <!-- Login Screen -->
    <div v-if="!isLoggedIn" class="login-screen">
      <div class="login-card">
        <div class="login-brand">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
          </svg>
          <span>后台管理</span>
        </div>
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
            <span v-if="!sidebarCollapsed">{{ currentRole === 'admin' ? '后台管理' : '合伙人后台' }}</span>
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
            <span class="admin-badge">{{ currentRole === 'admin' ? '管理员' : '合伙人' }}</span>
            <button v-if="activeTab === 'overview'" class="btn btn-ghost btn-sm" :disabled="loadingDash" @click="loadDashboard">
              <span v-if="loadingDash" class="spinner" style="width:14px;height:14px"></span>
              {{ loadingDash ? '加载中' : '刷新数据' }}
            </button>
          </div>
        </header>

        <div class="content-body">
          <!-- Overview Tab -->
          <OverviewTab v-if="activeTab === 'overview'" />


          <!-- Commissions Tab -->

          <!-- Commissions Tab -->
          <CommissionsTab v-if="activeTab === 'commissions'" />


          <!-- Orders Tab -->
          <OrdersTab v-if="activeTab === 'orders'" />


          <!-- Users Tab -->
          <UsersTab v-if="activeTab === 'users'" />


          <!-- Agents Tab -->
          <AgentsTab v-if="activeTab === 'agents'" />


          <!-- Withdrawals Tab -->
          <WithdrawalsTab v-if="activeTab === 'withdrawals'" />


          <!-- Queue Tab -->
          <QueueTab v-if="activeTab === 'queue' || activeTab === 'queue_school' || activeTab === 'queue_chaoxing'" />


          <!-- Proxy Tab -->
          <ProxyTab v-if="activeTab === 'proxy'" />


          <!-- Security Tab -->
          <SecurityTab v-if="activeTab === 'security'" />


          <!-- Risk Monitor Tab -->
          <RiskTab v-if="activeTab === 'risk'" />


          <!-- Pricing Tab -->
          <PricingTab v-if="activeTab === 'pricing'" />

          <YpayTab v-if="activeTab === 'ypay'" />


          <AdsTab v-if="activeTab === 'ads'" />
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
        <button :class="['mbn-item', { active: activeTab === 'users' }]" @click="switchTab('users')">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
          <span>用户</span>
        </button>
        <button :class="['mbn-item', { active: activeTab === 'security' || activeTab === 'pricing' || activeTab === 'ypay' || activeTab === 'ads' || activeTab === 'proxy' || activeTab === 'commissions' || activeTab === 'withdrawals' || activeTab === 'agents' }]" @click="mobileSidebarOpen = true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><circle cx="12" cy="12" r="3"/></svg>
          <span>更多</span>
        </button>
      </nav>
    </div>

    <!-- Rate Modal -->
    <div v-if="showRateModal" class="modal-overlay" @click.self="showRateModal = false">
      <div class="modal">
        <h3>调整佣金比例</h3>
        <p v-if="rateTarget" class="modal-sub">
代理: {{ rateTarget.nickname || rateTarget.username }} ({{ rateTarget.referral_code }})
</p>
        <div class="field">
          <label>佣金比例</label>
          <div class="rate-input-row">
            <input v-model.number="newRate" type="number" min="0" max="0.5" step="0.01" />
            <span class="rate-pct">{{ (newRate * 100).toFixed(0) }}%</span>
          </div>
          <p class="field-hint">
范围 0% ~ 50%
</p>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showRateModal = false">
取消
</button>
          <button class="btn btn-primary" @click="saveRate">
确认修改
</button>
        </div>
      </div>
    </div>

    <!-- Topup Modal -->
    <div v-if="showTopupModal" class="modal-overlay" @click.self="showTopupModal = false">
      <div class="modal">
        <h3>{{ toppupMode === 'topup' ? '用户充值' : '用户扣费' }}</h3>
        <p v-if="topupTarget" class="modal-sub">
          用户: {{ topupTarget.nickname || topupTarget.username }} ({{ topupTarget.user_id }})
          当前余额: {{ fmtMoney(topupTarget.balance) }}
        </p>
        <div class="field">
          <label>金额</label>
          <input v-model.number="topupAmount" type="number" min="0" step="0.01" placeholder="请输入金额" />
        </div>
        <div class="field">
          <label>备注</label>
          <input v-model="topupNote" placeholder="可选" />
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showTopupModal = false">
取消
</button>
          <button class="btn btn-primary" :disabled="toppingUp" @click="doTopup">
            {{ toppingUp ? '处理中...' : (toppupMode === 'topup' ? '确认充值' : '确认扣费') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Create SubAdmin Modal -->
    <div v-if="showCreateSubAdmin" class="modal-overlay" @click.self="showCreateSubAdmin = false">
      <div class="modal">
        <h3>添加合伙人</h3>
        <p class="modal-sub">
合伙人可以审批代理、管理订单、查看佣金数据
</p>
        <div class="field">
<label>用户ID</label><input v-model="newSubAdmin.user_id" placeholder="如: subadmin001" />
</div>
        <div class="field">
<label>用户名</label><input v-model="newSubAdmin.username" placeholder="如: 张三" />
</div>
        <div class="field">
<label>密码</label><input v-model="newSubAdmin.password" type="password" placeholder="至少6位" />
</div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showCreateSubAdmin = false; newSubAdmin.user_id=''; newSubAdmin.username=''; newSubAdmin.password=''">
取消
</button>
          <button class="btn btn-primary" :disabled="creatingSubAdmin" @click="doCreateSubAdmin">
{{ creatingSubAdmin ? '创建中...' : '确认创建' }}
</button>
        </div>
      </div>
    </div>

    <!-- QR 大图弹窗 -->
    <div v-if="showQrModal" class="modal-overlay" @click.self="showQrModal = ''">
      <div class="qr-modal">
        <img :src="showQrModal" alt="收款码" />
        <button class="btn btn-ghost btn-sm" @click="showQrModal = ''">
关闭
</button>
      </div>
    </div>
  </div>
</template>

<style>
.admin-root { min-height: 100vh; background: #f1f3f6; }

/* Login Screen */
.login-screen {
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #1e293b 0%, #334155 50%, #1e293b 100%);
  padding: 24px;
}
.login-card {
  background: #fff; border-radius: 16px; padding: 44px 40px;
  width: 400px; max-width: 100%; box-shadow: 0 25px 60px rgba(0,0,0,.3);
}
.login-brand {
  display: flex; align-items: center; justify-content: center; gap: 10px;
  font-size: 22px; font-weight: 700; color: #1e293b; margin-bottom: 4px;
}
.login-brand svg { color: #4f6ef7; }
.login-desc { text-align: center; font-size: 13px; color: #94a3b8; margin-bottom: 28px; }
.login-back { text-align: center; margin-top: 20px; }
.login-back a { font-size: 13px; color: #94a3b8; text-decoration: none; }
.login-back a:hover { color: #4f6ef7; }

.field { display: flex; flex-direction: column; gap: 5px; margin-bottom: 16px; }
.field label { font-size: 12.5px; font-weight: 600; color: #475569; }
.field input {
  height: 44px; padding: 0 14px; border: 1.5px solid #e2e8f0;
  border-radius: 10px; background: #f8fafc; color: #1e293b;
  font-size: 14px; outline: none; transition: all .15s;
}
.field input:focus { border-color: #4f6ef7; box-shadow: 0 0 0 3px rgba(79,110,247,.1); background: #fff; }
.captcha-row { display: flex; gap: 8px; align-items: center; }
.captcha-row input { flex: 1; min-width: 0; }
.captcha-img { height: 44px; cursor: pointer; border-radius: 8px; border: 1px solid #e2e8f0; flex-shrink: 0; }
.captcha-placeholder {
  height: 44px; padding: 0 16px; display: flex; align-items: center; justify-content: center;
  border: 1px dashed #cbd5e1; border-radius: 8px; font-size: 13px; color: #94a3b8;
  cursor: pointer; flex-shrink: 0; white-space: nowrap;
}
.captcha-placeholder:hover { border-color: #4f6ef7; color: #4f6ef7; }
.field input::placeholder { color: #94a3b8; }
.field-hint { font-size: 11px; color: #94a3b8; margin-top: 2px; }
.login-err { font-size: 13px; color: #ef4444; text-align: center; margin-top: 12px; }

.btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 9px 20px; border: none; border-radius: 10px; font-weight: 600; font-size: 13.5px; cursor: pointer; transition: all .15s; white-space: nowrap; }
.btn-primary { background: #4f6ef7; color: #fff; box-shadow: 0 2px 8px rgba(79,110,247,.25); }
.btn-primary:hover { background: #3b5de7; transform: translateY(-1px); }
.btn-primary:disabled { opacity: .55; cursor: not-allowed; transform: none; }
.btn-ghost { background: transparent; color: #64748b; padding: 6px 12px; }
.btn-ghost:hover { color: #4f6ef7; background: #eef1fe; }
.btn-lg { padding: 13px 28px; font-size: 15px; }
.btn-block { width: 100%; }
.btn-sm { padding: 5px 10px; font-size: 12px; }
.btn-xs { padding: 4px 10px; font-size: 11.5px; border-radius: 6px; }
.btn-success { background: #22c55e; color: #fff; }
.btn-success:hover { filter: brightness(1.1); }
.btn-warn { background: #f59e0b; color: #fff; }
.btn-warn:hover { filter: brightness(1.1); }

/* Layout */
.admin-layout { display: flex; min-height: 100vh; }

/* Mobile sidebar toggle - hidden on desktop */
.mobile-sidebar-toggle { display: none; }

/* Mobile bottom nav - hidden on desktop */
.mobile-bottom-nav { display: none; }

/* Sidebar */
.sidebar {
  width: 220px; flex-shrink: 0; background: #1e293b;
  display: flex; flex-direction: column; position: fixed; top: 0; left: 0;
  bottom: 0; z-index: 50; transition: width .2s ease;
  overflow: hidden;
}
.sidebar.collapsed { width: 60px; }

.sidebar-brand {
  padding: 20px 16px; border-bottom: 1px solid rgba(255,255,255,.08);
}
.sb-logo {
  display: flex; align-items: center; gap: 10px; color: #f1f5f9;
  text-decoration: none; font-size: 16px; font-weight: 700; white-space: nowrap;
}
.sb-logo svg { color: #4f6ef7; flex-shrink: 0; }
.sb-logo:hover { text-decoration: none; }

.sidebar-nav {
  flex: 1; padding: 12px 8px; display: flex; flex-direction: column; gap: 2px;
  overflow-y: auto; scrollbar-width: thin; scrollbar-color: rgba(255,255,255,.15) transparent;
}
.sidebar-nav::-webkit-scrollbar { width: 5px; }
.sidebar-nav::-webkit-scrollbar-track { background: transparent; }
.sidebar-nav::-webkit-scrollbar-thumb { background: rgba(255,255,255,.15); border-radius: 3px; }
.sidebar-nav::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,.3); }
.sidebar-group-label {
  font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase;
  letter-spacing: .5px; padding: 12px 12px 4px; white-space: nowrap;
}
.sidebar-group-label:first-child { padding-top: 4px; }

.sidebar-item {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  border-radius: 8px; background: transparent; border: none;
  color: #94a3b8; font-size: 13.5px; font-weight: 500;
  cursor: pointer; transition: all .15s; width: 100%; text-align: left;
  text-decoration: none; white-space: nowrap;
}
.sidebar-item:hover { background: rgba(255,255,255,.06); color: #e2e8f0; text-decoration: none; }
.sidebar-item.active { background: #4f6ef7; color: #fff; }
.sidebar-item.active .sidebar-item-icon { color: #fff; }
.sidebar-item-icon { flex-shrink: 0; }

.sidebar-parent { justify-content: space-between; }
.sidebar-expand-icon { flex-shrink: 0; transition: transform .2s; margin-left: auto; }
.sidebar-expand-icon.expanded { transform: rotate(180deg); }
.sidebar-sub-items { display: flex; flex-direction: column; gap: 1px; padding-left: 8px; }
.sidebar-sub-item { padding: 7px 12px 7px 28px; font-size: 13px; }
.sidebar-sub-item.active { background: rgba(79,110,247,.2); color: #4f6ef7; }
.sidebar-sub-item.active .sidebar-item-icon { color: #4f6ef7; }

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
  position: sticky; top: 0; z-index: 40; background: rgba(255,255,255,.88);
  backdrop-filter: blur(12px); border-bottom: 1px solid #e2e8f0;
  padding: 0 28px; height: 56px; display: flex; align-items: center;
  justify-content: space-between;
}
.content-topbar h2 { font-size: 17px; font-weight: 700; color: #1e293b; }
.topbar-tag { font-size: 11px; font-weight: 600; padding: 2px 10px; border-radius: 12px; background: #f1f5f9; color: #64748b; }
.topbar-tag-school { background: #f0fdf4; color: #22c55e; }
.topbar-tag-chaoxing { background: #eef1fe; color: #4f6ef7; }
.topbar-right { display: flex; align-items: center; gap: 12px; }
.admin-badge {
  padding: 3px 12px; border-radius: 20px; font-size: 11.5px; font-weight: 600;
  background: #fef3c7; color: #d97706;
}

.content-body { flex: 1; padding: 24px 28px 40px; }

/* KPI Cards */
.overview-content { display: flex; flex-direction: column; gap: 18px; }
.kpi-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }
.kpi-card {
  background: #fff; border: 1px solid #e2e8f0;
  border-radius: 12px; padding: 20px 18px; box-shadow: 0 1px 3px rgba(0,0,0,.03);
  display: flex; flex-direction: column; gap: 8px; transition: box-shadow .15s;
}
.kpi-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,.06); }
.kpi-icon {
  width: 38px; height: 38px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
}
.kpi-icon.rev { background: #fef2f2; color: #ef4444; }
.kpi-icon.ord { background: #eef1fe; color: #4f6ef7; }
.kpi-icon.usr { background: #f0fdf4; color: #22c55e; }
.kpi-icon.agt { background: #f0f9ff; color: #0ea5e9; }
.kpi-icon.rate { background: #fffbeb; color: #f59e0b; }
.kpi-icon.upg { background: #faf5ff; color: #a855f7; }
.kpi-body { display: flex; flex-direction: column; gap: 2px; }
.kpi-val { font-size: 24px; font-weight: 700; color: #1e293b; line-height: 1.1; }
.kpi-label { font-size: 12px; color: #94a3b8; font-weight: 500; }
.kpi-sub { font-size: 11px; color: #94a3b8; border-top: 1px solid #f1f5f9; padding-top: 7px; }

/* Panels */
.panel-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.panel {
  background: #fff; border: 1px solid #e2e8f0;
  border-radius: 12px; padding: 20px 22px; box-shadow: 0 1px 3px rgba(0,0,0,.03);
}
.panel-wide { grid-column: span 2; }
.panel-wide-sm { grid-column: span 1; }
.panel-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.panel-head h3 { font-size: 14px; font-weight: 700; color: #1e293b; }
.legend-row { display: flex; gap: 16px; }
.legend { font-size: 11.5px; color: #64748b; display: flex; align-items: center; gap: 5px; }
.ldot { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
.ldot-rev { background: #ef4444; }
.ldot-ord { background: #4f6ef7; }

.chart-area { display: flex; align-items: flex-end; gap: 10px; height: 160px; padding: 0 4px; }
.bar-group { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; }
.bars { flex: 1; width: 100%; display: flex; align-items: flex-end; gap: 4px; justify-content: center; }
.bar { width: 12px; border-radius: 4px 4px 0 0; min-height: 3px; transition: height .3s; }
.bar-rev { background: #ef4444; opacity: .75; }
.bar-ord { background: #4f6ef7; opacity: .75; }
.bar-label { font-size: 10px; color: #94a3b8; margin-top: 6px; }

.status-bars { display: flex; flex-direction: column; gap: 10px; }
.sb-row { display: flex; align-items: center; gap: 10px; }
.sb-label { width: 50px; font-size: 12px; color: #64748b; text-align: right; flex-shrink: 0; }
.sb-track { flex: 1; height: 7px; background: #f1f5f9; border-radius: 4px; overflow: hidden; }
.sb-fill { height: 100%; border-radius: 4px; transition: width .4s; }
.sb-primary { background: #4f6ef7; }
.sb-ok { background: #22c55e; }
.sb-warn { background: #f59e0b; }
.sb-bad { background: #ef4444; }
.sb-muted { background: #94a3b8; }
.sb-val { width: 36px; font-size: 12px; color: #1e293b; font-weight: 600; text-align: left; flex-shrink: 0; }

.plat-list { display: flex; flex-direction: column; gap: 10px; }
.plat-item { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.plat-left { display: flex; align-items: center; gap: 8px; min-width: 100px; }
.plat-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.plat-name { font-size: 12.5px; color: #1e293b; font-weight: 500; white-space: nowrap; }
.plat-right { display: flex; align-items: center; gap: 8px; flex: 1; }
.plat-bar-bg { flex: 1; height: 8px; background: #f1f5f9; border-radius: 4px; overflow: hidden; max-width: 120px; }
.plat-bar-fill { height: 100%; border-radius: 4px; transition: width .3s; }
.plat-cnt { font-size: 11.5px; color: #64748b; white-space: nowrap; min-width: 28px; }
.plat-rev { font-size: 11.5px; color: #94a3b8; white-space: nowrap; }

.type-cards { display: flex; gap: 10px; flex-wrap: wrap; }
.type-card {
  flex: 1; min-width: 60px; background: #f8fafc;
  border-radius: 10px; padding: 16px 14px; text-align: center;
}
.tc-icon { font-size: 13px; font-weight: 600; color: #4f6ef7; margin-bottom: 4px; }
.tc-count { font-size: 20px; font-weight: 700; color: #1e293b; }
.tc-rev { font-size: 11px; color: #94a3b8; margin-top: 2px; }

.mini-table { font-size: 12.5px; }
.mt-row { display: grid; grid-template-columns: 1fr 1fr .7fr .9fr .9fr 1.2fr; gap: 4px; padding: 8px 0; border-bottom: 1px solid #f1f5f9; align-items: center; }
.mt-head { font-weight: 600; color: #94a3b8; font-size: 11px; text-transform: uppercase; letter-spacing: .3px; border-bottom: 2px solid #e2e8f0; }
.mt-row:last-child { border-bottom: none; }
.mt-uname { font-weight: 600; color: #1e293b; }
.mt-money { font-weight: 600; }
.mt-date { color: #94a3b8; font-size: 11px; }

.rank-list { display: flex; flex-direction: column; }
.rank-item { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid #f1f5f9; }
.rank-item:last-child { border-bottom: none; }
.rank-no {
  width: 26px; height: 26px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; background: #f1f5f9; color: #64748b;
}
.rank-no.r1 { background: #fef3c7; color: #d97706; }
.rank-no.r2 { background: #e2e8f0; color: #475569; }
.rank-no.r3 { background: #fed7aa; color: #c2410c; }
.rank-info { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.rank-name { font-size: 13px; font-weight: 600; color: #1e293b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rank-code { font-size: 11px; color: #94a3b8; }
.rank-earn { font-size: 13px; font-weight: 700; color: #ef4444; white-space: nowrap; }

/* Agent Sub-tabs */
.agent-subtabs { display: flex; gap: 6px; margin-bottom: 20px; background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 5px; }
.ast { display: flex; align-items: center; gap: 6px; padding: 10px 20px; border: none; background: transparent; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 500; color: #64748b; transition: all .2s; white-space: nowrap; }
.ast:hover { background: #f1f5f9; color: #334155; }
.ast.active { background: #4f6ef7; color: #fff; box-shadow: 0 2px 8px rgba(79,110,247,.3); }
.ast.active svg { stroke: #fff; }

/* Agent Stats */
.agent-stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }

.guide-banner {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  margin-bottom: 20px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.03);
}
.gb-header {
  display: flex; align-items: center; gap: 8px; padding: 14px 20px;
  background: linear-gradient(135deg, #eef1fe, #f0f4ff); border-bottom: 1px solid #e2e8f0;
  font-size: 15px; color: #4f6ef7;
}
.gb-body { padding: 18px 20px; }
.gb-section { margin-bottom: 16px; }
.gb-section:last-child { margin-bottom: 0; }
.gb-section h4 { font-size: 14px; font-weight: 700; color: #1e293b; margin: 0 0 6px; }
.gb-section p { font-size: 13px; color: #64748b; margin: 0; line-height: 1.6; }
.gb-section ul { font-size: 13px; color: #64748b; margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.gb-rates { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 8px; }
.gb-rate {
  display: flex; align-items: center; gap: 10px; background: #f8fafc;
  border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px 16px; flex: 1; min-width: 260px;
}
.gb-rate-tag {
  padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; flex-shrink: 0;
}
.gb-rate-tag.l1 { background: #eef1fe; color: #4f6ef7; }
.gb-rate-tag.l2 { background: #f0fdf4; color: #22c55e; }
.gb-rate-val { font-size: 22px; font-weight: 800; color: #1e293b; flex-shrink: 0; }
.gb-rate-desc { font-size: 12px; color: #94a3b8; }
.mini-stat {
  background: #fff; border: 1px solid #e2e8f0;
  border-radius: 12px; padding: 18px 22px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,.03);
}
.ms-val { font-size: 24px; font-weight: 700; color: #1e293b; }
.ms-val.ok { color: #22c55e; }
.ms-val.money { color: #ef4444; }
.ms-label { font-size: 12px; color: #94a3b8; margin-top: 4px; }

.section-actions { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; flex-wrap: wrap; gap: 10px; }
.filter-group { display: flex; gap: 6px; }
.filter-bar { width: 100%; overflow: hidden; }
.filter-scroll { display: flex; gap: 6px; overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; padding-bottom: 2px; }
.filter-scroll::-webkit-scrollbar { display: none; }
.filter-divider { width: 1px; height: 24px; background: #e2e8f0; flex-shrink: 0; align-self: center; margin: 0 2px; }
.filter-search-row { display: flex; align-items: center; gap: 8px; width: 100%; }
.chip {
  padding: 6px 16px; border: 1px solid #e2e8f0; border-radius: 20px;
  background: #fff; font-size: 12.5px; font-weight: 500;
  color: #64748b; cursor: pointer; transition: all .15s;
}
.chip:hover { border-color: #4f6ef7; color: #4f6ef7; }
.chip.active { background: #4f6ef7; color: #fff; border-color: #4f6ef7; }
.total-label { font-size: 13px; color: #94a3b8; }

/* Tables */
.table-wrap {
  background: #fff; border: 1px solid #e2e8f0;
  border-radius: 12px; overflow-x: auto; box-shadow: 0 1px 3px rgba(0,0,0,.03);
}
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table thead { background: #f8fafc; }
.data-table th {
  padding: 12px 16px; text-align: left; font-weight: 600; font-size: 11.5px;
  color: #94a3b8; text-transform: uppercase; letter-spacing: .3px;
  border-bottom: 1px solid #e2e8f0; white-space: nowrap;
}
.data-table td {
  padding: 12px 16px; border-bottom: 1px solid #f1f5f9;
  color: #1e293b; white-space: nowrap;
}
.data-table tbody tr:hover { background: #f8fafc; }
.data-table tbody tr:last-child td { border-bottom: none; }

.user-cell { display: flex; flex-direction: column; gap: 2px; }
.uname { font-weight: 600; font-size: 13px; }
.uid { font-size: 11px; color: #94a3b8; }
.code-tag {
  background: #f1f5f9; padding: 2px 8px; border-radius: 5px;
  font-size: 11.5px; font-family: 'SF Mono', 'Consolas', monospace; color: #4f6ef7;
}
.money-cell { font-weight: 600; font-variant-numeric: tabular-nums; }
.money-cell.highlight { color: #ef4444; }
.date-cell { font-size: 12px; color: #94a3b8; }

.status-tag {
  display: inline-block; padding: 2px 10px; border-radius: 12px;
  font-size: 11.5px; font-weight: 600;
}
.status-tag.ok { background: #f0fdf4; color: #22c55e; }
.status-tag.warn { background: #fffbeb; color: #f59e0b; }
.status-tag.bad { background: #fef2f2; color: #ef4444; }
.status-tag.primary { background: #eef1fe; color: #4f6ef7; }
.status-tag.muted { background: #f1f5f9; color: #94a3b8; }

.level-tag { display: inline-block; padding: 2px 8px; border-radius: 5px; font-size: 11px; font-weight: 700; }
.level-tag.l1 { background: #eef1fe; color: #4f6ef7; }
.level-tag.l2 { background: #f0f9ff; color: #0ea5e9; }
.level-tag.l3 { background: #fdf4ff; color: #a855f7; }

.search-input { padding: 6px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; outline: none; width: 160px; transition: border-color .2s; }
.search-input:focus { border-color: #4f6ef7; }

.fee-section { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px; margin-bottom: 16px; }
.fee-toggle-row { display: flex; align-items: center; justify-content: space-between; }
.fee-label { font-size: 14px; font-weight: 600; color: #1e293b; }
.fee-hint { font-size: 12px; color: #94a3b8; margin-left: 8px; }
.toggle-switch { position: relative; display: inline-block; width: 44px; height: 24px; cursor: pointer; }
.toggle-switch input { opacity: 0; width: 0; height: 0; }
.toggle-slider { position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: #cbd5e1; border-radius: 24px; transition: .3s; }
.toggle-slider:before { content: ''; position: absolute; height: 18px; width: 18px; left: 3px; bottom: 3px; background: #fff; border-radius: 50%; transition: .3s; }
.toggle-switch input:checked + .toggle-slider { background: #4f6ef7; }
.toggle-switch input:checked + .toggle-slider:before { transform: translateX(20px); }
.fee-input-row { display: flex; align-items: center; gap: 12px; margin-top: 14px; }
.fee-input-label { font-size: 13px; color: #64748b; min-width: 160px; }
.fee-input { padding: 6px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; width: 120px; outline: none; }
.fee-input:focus { border-color: #4f6ef7; }

.guide-banner { display: flex; gap: 16px; align-items: flex-start; background: linear-gradient(135deg, #eef1fe, #f0f9ff); border: 1px solid #c7d2fe; border-radius: 12px; padding: 20px; margin-bottom: 24px; }
.guide-icon { flex-shrink: 0; width: 48px; height: 48px; background: #4f6ef7; border-radius: 12px; display: flex; align-items: center; justify-content: center; color: #fff; }
.guide-banner h4 { font-size: 15px; font-weight: 700; color: #1e293b; margin-bottom: 4px; }
.guide-banner p { font-size: 13px; color: #475569; margin: 0; }
.guide-section { margin-bottom: 24px; }
.guide-section h4 { font-size: 14px; font-weight: 700; color: #1e293b; margin-bottom: 12px; }
.guide-rate-row { display: flex; gap: 12px; flex-wrap: wrap; }
.guide-rate-card { flex: 1; min-width: 160px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.grc-badge { display: inline-block; padding: 4px 14px; border-radius: 6px; font-size: 13px; font-weight: 700; }
.grc-badge.l1 { background: #eef1fe; color: #4f6ef7; }
.grc-badge.l2 { background: #f0f9ff; color: #0ea5e9; }
.grc-badge.l3 { background: #fdf4ff; color: #a855f7; }
.grc-label { font-size: 13px; color: #64748b; }
.grc-value { font-size: 14px; font-weight: 600; color: #1e293b; }
.guide-list { list-style: none; padding: 0; }
.guide-list li { position: relative; padding-left: 18px; margin-bottom: 8px; font-size: 13px; color: #475569; line-height: 1.6; }
.guide-list li:before { content: ''; position: absolute; left: 0; top: 8px; width: 6px; height: 6px; background: #4f6ef7; border-radius: 50%; }
.guide-list li strong { color: #1e293b; }

.action-group { display: flex; gap: 4px; }

.empty { text-align: center; padding: 60px; color: #94a3b8; }
.empty p { margin-bottom: 16px; }
.empty-sm { text-align: center; padding: 32px; color: #94a3b8; font-size: 13px; }

.spinner { border: 2px solid #e2e8f0; border-top-color: #4f6ef7; border-radius: 50%; animation: spin .65s linear infinite; display: inline-block; }

/* Security */
.security-tab { width: 100%; max-width: 720px; display: flex; flex-direction: column; gap: 20px; }
.proxy-tab { width: 100%; max-width: 720px; display: flex; flex-direction: column; gap: 20px; }
.proxy-toggle-row { display: flex; align-items: center; justify-content: space-between; padding: 6px 0 14px; }
.proxy-toggle-label { font-size: 14px; font-weight: 600; color: #374151; }
.proxy-actions { display: flex; gap: 10px; margin-top: 16px; }
.proxy-test-result { margin-top: 12px; padding: 10px 14px; border-radius: 8px; font-size: 13px; background: #fef2f2; color: #dc2626; }
.proxy-test-result.ok { background: #f0fdf4; color: #16a34a; }
.proxy-guide { font-size: 13px; line-height: 1.8; color: #4b5563; padding-top: 12px; }
.guide-step { margin-bottom: 6px; }
.guide-step code { background: #f3f4f6; padding: 1px 6px; border-radius: 4px; font-size: 12px; }
.code-warn { background: #fef2f2; color: #dc2626; }
.guide-details { cursor: pointer; }
.guide-details summary { font-size: 15px; font-weight: 600; color: #1e293b; outline: none; }
.guide-details summary:hover { color: #4f6ef7; }
.settings-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 28px; box-shadow: 0 1px 3px rgba(0,0,0,.03); }
.settings-card h3 { font-size: 16px; font-weight: 700; margin-bottom: 6px; color: #1e293b; }
.settings-hint { font-size: 12.5px; color: #94a3b8; margin-bottom: 22px; }
.settings-card .field { margin-bottom: 18px; }
.settings-card .field label { text-align: left; }
.settings-card .field input {
  padding: 10px 14px; border: 1.5px solid #e2e8f0; border-radius: 10px;
  background: #f8fafc; color: #1e293b; font-size: 14px; outline: none;
  transition: border-color .15s; font-family: inherit; width: 100%; box-sizing: border-box;
}
.settings-card .field input:focus { border-color: #4f6ef7; box-shadow: 0 0 0 3px rgba(79,110,247,.1); background: #fff; }

/* DeepSeek AI Config */
.ai-section { margin-top: 20px; }
.ai-section:first-child { margin-top: 16px; }
.ai-section-label { font-size: 13px; font-weight: 700; color: #374151; margin-bottom: 10px; }
.ai-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.ai-key-wrap { display: flex; align-items: center; gap: 8px; }
.ai-key-badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; }
.ai-key-badge.on { background: #dcfce7; color: #16a34a; }
.ai-key-badge.off { background: #fee2e2; color: #dc2626; }
.ai-key-val { font-size: 13px; font-family: 'SF Mono', Monaco, Consolas, monospace; color: #475569; }
.ai-key-input-group { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }
.ai-key-input {
  flex: 1; min-width: 0; height: 34px; border: 1.5px solid #e2e8f0; border-radius: 8px;
  padding: 0 12px; font-size: 13px; font-family: 'SF Mono', Monaco, Consolas, monospace;
  transition: border-color .15s; background: #fff;
}
.ai-key-input:focus { border-color: #4f6ef7; box-shadow: 0 0 0 3px rgba(79,110,247,.1); outline: none; }
.ai-row-bottom { display: flex; align-items: center; gap: 12px; margin-top: 8px; }
.ai-link { font-size: 12px; color: #4f6ef7; text-decoration: none; }
.ai-link:hover { text-decoration: underline; }
.btn-link {
  background: none; border: none; color: #4f6ef7; font-size: 12px; font-weight: 600;
  cursor: pointer; padding: 0; text-decoration: underline;
}
.btn-link:disabled { color: #94a3b8; cursor: not-allowed; }
.ai-status-ok { font-size: 12px; color: #16a34a; font-weight: 600; }
.ai-status-fail { font-size: 12px; color: #dc2626; font-weight: 600; }
.ai-model-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
.ai-model-card {
  padding: 14px; background: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 10px;
}
.ai-model-head {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; font-weight: 700; color: #1e293b; margin-bottom: 10px;
}
.ai-model-head svg { color: #4f6ef7; }
.ai-model-select {
  width: 100%; padding: 8px 10px; border: 1.5px solid #e2e8f0; border-radius: 8px;
  font-size: 13px; color: #1e293b; background: #fff; outline: none; cursor: pointer;
  transition: border-color .15s;
}
.ai-model-select:focus { border-color: #4f6ef7; box-shadow: 0 0 0 3px rgba(79,110,247,.1); }
.ai-model-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 6px; }
.ai-model-desc { font-size: 11px; color: #64748b; }

/* QR Code Manager */
.qrcode-quick-area { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.qrcode-quick-card {
  border: 2px solid #e2e8f0; border-radius: 14px; overflow: hidden;
  transition: all .25s; cursor: pointer; background: #fff;
}
.qrcode-quick-card:hover { border-color: #cbd5e1; }
.qrcode-quick-card.active { border-color: #4f6ef7; box-shadow: 0 0 0 3px rgba(79,110,247,.08); }
.qrcode-quick-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px 0 18px;
}
.qrcode-quick-badge {
  padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 700;
}
.qq-wx { background: #dcfce7; color: #16a34a; }
.qq-alipay { background: #dbeafe; color: #2563eb; }
.qrcode-quick-status { font-size: 11.5px; color: #64748b; font-weight: 500; }
.qrcode-quick-status.qq-none { color: #f59e0b; }
.qrcode-quick-upload {
  height: 160px; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; margin: 12px; border: 2px dashed #e2e8f0; border-radius: 10px;
  transition: all .2s; position: relative; overflow: hidden;
}
.qrcode-quick-card.active .qrcode-quick-upload { border-color: #4f6ef7; background: #fafafe; }
.qrcode-quick-upload span { font-size: 13px; font-weight: 500; color: #64748b; }
.qrcode-quick-sub { font-size: 11px; color: #94a3b8; }
.qrcode-quick-preview { width: 100%; height: 100%; object-fit: contain; padding: 8px; }
.qrcode-remove-btn {
  position: absolute; top: 6px; right: 6px; width: 22px; height: 22px; border-radius: 50%;
  background: #ef4444; color: #fff; border: none; font-size: 13px; font-weight: 700;
  cursor: pointer; display: flex; align-items: center; justify-content: center; line-height: 1;
}
.qrcode-form-inline {
  display: flex; flex-direction: column; gap: 12px;
  padding: 16px 20px; background: #f8fafc; border: 1.5px solid #e2e8f0;
  border-radius: 12px; margin-bottom: 16px;
}
.qfi-field { display: flex; flex-direction: column; gap: 6px; }
.qfi-field label { font-size: 12.5px; font-weight: 600; color: #475569; }
.qfi-hint {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: #94a3b8; line-height: 1.4;
}
.qfi-hint svg { flex-shrink: 0; }
.qfi-submit { align-self: flex-start; }
.qrcode-price-select {
  width: 100%; max-width: 280px; height: 38px; padding: 0 12px;
  border: 1.5px solid #e2e8f0; border-radius: 8px; background: #fff;
  font-size: 13px; color: #1e293b; outline: none; cursor: pointer; appearance: auto;
}
.qrcode-price-select:focus { border-color: #4f6ef7; }
.custom-price-row { display: flex; align-items: center; margin-top: 6px; }
.custom-price-prefix {
  height: 38px; display: flex; align-items: center; padding: 0 12px;
  background: #f1f5f9; border: 1.5px solid #e2e8f0; border-right: none;
  border-radius: 8px 0 0 8px; font-size: 14px; font-weight: 600; color: #475569;
}
.custom-price-input {
  width: 200px; height: 38px; padding: 0 12px; border: 1.5px solid #e2e8f0;
  border-radius: 0 8px 8px 0; background: #fff; font-size: 13px; color: #1e293b; outline: none;
}
.custom-price-input:focus { border-color: #4f6ef7; }
.qrcode-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.qrcode-card {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden;
  transition: all .2s;
}
.qrcode-card:hover { border-color: #cbd5e1; box-shadow: 0 2px 8px rgba(0,0,0,.04); }
.qrcode-card.qrcode-disabled { opacity: .5; }
.qrcode-card-img-box {
  height: 140px; background: #f8fafc; display: flex; align-items: center; justify-content: center;
  padding: 8px;
}
.qrcode-card-img { max-width: 100%; max-height: 100%; object-fit: contain; }
.qrcode-card-placeholder { display: flex; align-items: center; justify-content: center; opacity: .3; }
.qrcode-card-info { padding: 10px 12px; }
.qrcode-card-tag { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 4px; }
.tag-wx { background: #dcfce7; color: #16a34a; padding: 1px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; }
.tag-alipay { background: #dbeafe; color: #2563eb; padding: 1px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; }
.tag-universal { background: #fce7f3; color: #db2777; padding: 1px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; }
.tag-price { background: #f1f5f9; color: #475569; padding: 1px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; }
.tag-active { background: #dcfce7; color: #16a34a; padding: 1px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; }
.tag-inactive { background: #fee2e2; color: #ef4444; padding: 1px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; }
.qrcode-card-id { font-size: 10.5px; color: #94a3b8; font-family: 'SF Mono','Consolas',monospace; }

/* 收款通道管理 */
.channel-section { margin-bottom: 24px; }
.channel-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.channel-title { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; color: #1e293b; }
.channel-count { font-size: 12px; color: #94a3b8; font-weight: 400; }
.channel-list { display: flex; flex-direction: column; gap: 8px; }
.channel-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; transition: all .15s; }
.channel-card:hover { border-color: #cbd5e1; box-shadow: 0 2px 8px rgba(0,0,0,.04); }
.channel-card.disabled { opacity: .5; }
.channel-card-top { display: flex; align-items: center; justify-content: space-between; }
.channel-card-name { font-size: 14px; font-weight: 600; color: #1e293b; }
.channel-card-actions { display: flex; gap: 4px; }
.btn-icon { background: none; border: none; cursor: pointer; padding: 4px; border-radius: 6px; display: flex; align-items: center; justify-content: center; transition: background .15s; }
.btn-icon:hover { background: #e2e8f0; }
.channel-card-meta { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.channel-code-tag { font-size: 11px; background: #e0e7ff; color: #4f46e5; padding: 2px 8px; border-radius: 4px; font-family: 'SF Mono','Consolas',monospace; }
.channel-status-dot { width: 8px; height: 8px; border-radius: 50%; }
.channel-status-dot.online { background: #16a34a; box-shadow: 0 0 6px rgba(22,163,74,.4); }
.channel-status-dot.offline { background: #94a3b8; }
.channel-status-text { font-size: 12px; color: #64748b; }
.channel-empty { text-align: center; padding: 24px; color: #94a3b8; font-size: 13px; background: #f8fafc; border: 1px dashed #e2e8f0; border-radius: 10px; }
.channel-memo { font-size: 11px; color: #94a3b8; margin-left: auto; }
.modal-body select {
  padding: 10px 14px; border: 1.5px solid #e2e8f0; border-radius: 10px;
  background: #f8fafc; color: #1e293b; font-size: 14px; outline: none;
  transition: border-color .15s; font-family: inherit; width: 100%; box-sizing: border-box;
  cursor: pointer;
}
.modal-body select:focus { border-color: #4f6ef7; box-shadow: 0 0 0 3px rgba(79,110,247,.1); background: #fff; }
.modal-body textarea {
  padding: 10px 14px; border: 1.5px solid #e2e8f0; border-radius: 10px;
  background: #f8fafc; color: #1e293b; font-size: 14px; outline: none;
  transition: border-color .15s; font-family: inherit; width: 100%; box-sizing: border-box;
  resize: vertical;
}
.modal-body textarea:focus { border-color: #4f6ef7; box-shadow: 0 0 0 3px rgba(79,110,247,.1); background: #fff; }
.channel-help-box {
  background: #f0f4ff; border: 1px solid #d4dcff; border-radius: 10px;
  padding: 14px 16px; margin-bottom: 16px; font-size: 13px; line-height: 1.7; color: #334155;
}
.channel-help-title { display: flex; align-items: center; gap: 6px; font-weight: 600; font-size: 14px; color: #4f6ef7; margin-bottom: 8px; }
.channel-help-item { margin-bottom: 4px; }
.channel-help-item strong { color: #1e293b; }
.modal-box { background: #fff; border-radius: 14px; width: 460px; max-width: 90vw; box-shadow: 0 25px 60px rgba(0,0,0,.2); overflow: hidden; }
.modal-header { display: flex; align-items: center; justify-content: space-between; padding: 20px 24px 0; }
.modal-header h3 { font-size: 17px; font-weight: 700; color: #1e293b; margin: 0; }
.modal-close { background: none; border: none; font-size: 22px; color: #94a3b8; cursor: pointer; padding: 4px 8px; border-radius: 6px; }
.modal-close:hover { background: #f1f5f9; color: #64748b; }
.modal-body { padding: 20px 24px; }
.modal-body .field { margin-bottom: 16px; }
.modal-body .field label { display: block; font-size: 13px; font-weight: 600; color: #374151; margin-bottom: 6px; }
.modal-body .field input, .modal-body .field select, .modal-body .field textarea { width: 100%; padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 14px; background: #fff; }
.modal-body .field textarea { resize: vertical; font-family: inherit; }
.modal-body .field input:focus, .modal-body .field select:focus, .modal-body .field textarea:focus { outline: none; border-color: #4f6ef7; box-shadow: 0 0 0 3px rgba(79,110,247,.1); }
.field-hint { font-size: 11.5px; color: #94a3b8; margin-top: 4px; display: block; }
.field-divider { border-top: 1px solid #e5e7eb; padding-top: 14px; margin-top: 8px; }
.field-divider span { font-size: 13px; font-weight: 600; color: #6b7280; display: block; }
.field-divider small { font-size: 11.5px; color: #9ca3af; display: block; margin-top: 2px; }
.qr-upload-row { display: flex; gap: 8px; align-items: flex-start; }
.qr-upload-row textarea { flex: 1; }
.btn-upload-qr {
  flex-shrink: 0; height: 38px; padding: 0 14px; border: 1.5px solid #e2e8f0; border-radius: 8px;
  background: #f8fafc; color: #475569; font-size: 12.5px; font-weight: 600;
  cursor: pointer; display: flex; align-items: center; gap: 5px; transition: all .2s; white-space: nowrap;
}
.btn-upload-qr:hover { border-color: #4f6ef7; color: #4f6ef7; background: #f0f4ff; }
.btn-upload-qr:disabled { opacity: .6; cursor: not-allowed; }
.modal-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 0 24px 20px; }

.modal-overlay {
  position: fixed; inset: 0; background: rgba(15,23,42,.45);
  display: flex; align-items: center; justify-content: center; z-index: 200;
  backdrop-filter: blur(3px);
}
.modal {
  background: #fff; border-radius: 14px; padding: 32px;
  width: 400px; max-width: 90vw; box-shadow: 0 25px 60px rgba(0,0,0,.2);
}
.modal h3 { font-size: 17px; font-weight: 700; margin-bottom: 4px; color: #1e293b; }
.modal-sub { font-size: 13px; color: #64748b; margin-bottom: 20px; }
.rate-input-row { display: flex; align-items: center; gap: 12px; }
.rate-input-row input { flex: 1; }
.rate-pct { font-size: 18px; font-weight: 700; color: #4f6ef7; min-width: 48px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 24px; }

/* Queue Panel */
.queue-panel { display: flex; flex-direction: column; gap: 16px; }
.queue-header {
  display: flex; align-items: center; justify-content: space-between;
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 16px 22px; box-shadow: 0 1px 3px rgba(0,0,0,.03);
}
.queue-status-badge { display: flex; align-items: center; gap: 8px; }
.qsb-dot { width: 10px; height: 10px; border-radius: 50%; }
.qsb-dot.qsb-live { background: #22c55e; box-shadow: 0 0 8px rgba(34,197,94,.4); animation: pulse-dot 1.5s ease-in-out infinite; }
.qsb-dot.qsb-paused { background: #f59e0b; box-shadow: 0 0 8px rgba(245,158,11,.4); }
.qsb-text { font-size: 13px; font-weight: 600; color: #1e293b; }
.qsb-queue-tag {
  font-size: 11px; font-weight: 500; color: #4f6ef7; background: rgba(79,110,247,.1);
  padding: 2px 8px; border-radius: 4px; margin-left: 6px;
}
.queue-actions { display: flex; gap: 8px; }

.queue-kpi-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
.qkpi {
  background: #fff; border: 1px solid #e2e8f0;
  border-radius: 12px; padding: 18px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,.03);
}
.qkpi-val { font-size: 26px; font-weight: 700; color: #1e293b; }
.qkpi-val.qkpi-running { color: #4f6ef7; }
.qkpi-val.qkpi-info { color: #f59e0b; }
.qkpi-val.qkpi-ok { color: #22c55e; }
.qkpi-val.qkpi-bad { color: #ef4444; }
.qkpi-val.qkpi-blue { color: #0ea5e9; }
.qkpi-label { font-size: 11.5px; color: #94a3b8; margin-top: 4px; }

.queue-config-row {
  display: flex; align-items: center; gap: 10px;
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 14px 22px; box-shadow: 0 1px 3px rgba(0,0,0,.03);
}
.qcfg-label { font-size: 13px; font-weight: 600; color: #475569; }
.qcfg-input {
  width: 60px; height: 36px; padding: 0 10px; border: 1.5px solid #e2e8f0;
  border-radius: 8px; text-align: center; font-size: 14px; font-weight: 600;
  color: #1e293b; outline: none;
}
.queue-specs-card {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 14px 22px;
}
.spec-row { display: flex; flex-direction: column; gap: 2px; }
.spec-label { font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }
.spec-val { font-size: 15px; font-weight: 600; color: #334155; }
.spec-highlight { color: #2563eb; }
.qcfg-input:focus { border-color: #4f6ef7; }

.q-progress { width: 80px; height: 6px; background: #f1f5f9; border-radius: 3px; overflow: hidden; }
.q-prog-bar { height: 100%; background: #4f6ef7; border-radius: 3px; transition: width .3s; }

.queue-tabs { display: flex; gap: 8px; }
.queue-sub-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.sub-queue-card {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,.03);
}
.sub-queue-title { font-size: 13px; font-weight: 600; color: #1e293b; margin-bottom: 8px; }
.sub-queue-row { display: flex; gap: 16px; font-size: 13px; color: #475569; }
.sub-queue-row .text-red { color: #ef4444; }

/* Pricing Tab */
.pricing-tab { width: 100%; max-width: 720px; }
.pricing-section { margin-top: 12px; }
.pricing-mode-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.pricing-rows { display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px; }
.pricing-row {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 16px 18px; background: #f8fafc; border: 1.5px solid #e2e8f0;
  border-radius: 10px; transition: border-color .15s;
}
.pricing-row:hover { border-color: #cbd5e1; }
.pr-left { display: flex; align-items: center; gap: 12px; }
.pr-icon {
  width: 40px; height: 40px; border-radius: 10px; display: flex;
  align-items: center; justify-content: center; flex-shrink: 0;
}
.pr-icon.video { background: #eef1fe; color: #4f6ef7; }
.pr-icon.exam { background: #f0fdf4; color: #22c55e; }
.pr-info { display: flex; flex-direction: column; gap: 2px; }
.pr-name { font-size: 14px; font-weight: 600; color: #1e293b; }
.pr-unit { font-size: 12px; color: #94a3b8; }
.pr-input-wrap { display: flex; align-items: center; }
.pr-prefix {
  font-size: 16px; font-weight: 700; color: #1e293b;
  background: #fff; border: 1.5px solid #e2e8f0; border-right: none;
  border-radius: 10px 0 0 10px; padding: 0 10px; height: 44px;
  display: flex; align-items: center;
}
.pr-input {
  width: 110px; height: 44px; padding: 0 12px;
  border: 1.5px solid #e2e8f0; border-radius: 0 10px 10px 0;
  background: #fff; color: #1e293b; font-size: 16px; font-weight: 700;
  outline: none; transition: border-color .15s;
}
.pr-input:focus { border-color: #4f6ef7; box-shadow: 0 0 0 3px rgba(79,110,247,.1); }

/* 打包定价当前状态 */
.pkg-current-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 12px; }
.pkg-card {
  background: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 10px;
  padding: 16px; text-align: center;
}
.pkg-card-label { font-size: 12px; color: #64748b; font-weight: 500; margin-bottom: 6px; }
.pkg-card-price { font-size: 22px; font-weight: 800; color: #1e293b; }
.pkg-discount-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.pkg-discount-tag {
  padding: 4px 10px; background: #f1f5f9; border-radius: 6px;
  font-size: 12px; color: #475569; font-weight: 600;
}
.pricing-section-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;
}
.pricing-section-title { font-size: 13px; font-weight: 600; color: #374151; }
.pricing-edit-actions { display: flex; gap: 6px; }
.pkg-card-input {
  display: flex; align-items: center; justify-content: center; margin-top: 4px;
}
.pkg-input-prefix {
  font-size: 16px; font-weight: 700; color: #1e293b;
  background: #f1f5f9; border: 1.5px solid #e2e8f0; border-right: none;
  border-radius: 6px 0 0 6px; padding: 0 8px; height: 36px;
  display: flex; align-items: center;
}
.pkg-card-input input {
  width: 80px; height: 36px; padding: 0 8px;
  border: 1.5px solid #e2e8f0; border-radius: 0 6px 6px 0;
  background: #fff; color: #1e293b; font-size: 16px; font-weight: 700;
  outline: none; text-align: center;
}
.pkg-card-input input:focus { border-color: #4f6ef7; box-shadow: 0 0 0 3px rgba(79,110,247,.1); }
.pkg-discount-edit {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 8px; background: #fff; border: 1.5px solid #e2e8f0; border-radius: 6px;
}
.pkg-disc-label { font-size: 11px; color: #64748b; font-weight: 600; white-space: nowrap; }
.pkg-discount-edit input {
  width: 56px; height: 28px; padding: 0 4px;
  border: 1px solid #e2e8f0; border-radius: 4px;
  background: #fff; color: #1e293b; font-size: 13px; font-weight: 600;
  outline: none; text-align: center;
}
.pkg-discount-edit .pkg-input-prefix {
  font-size: 13px; height: 28px; padding: 0 4px;
  border-radius: 4px 0 0 4px;
}
.pkg-discount-edit input:focus { border-color: #4f6ef7; }

/* AI 定价顾问 */
.ai-advisor-card { margin-top: 20px; border: 1.5px solid #e0e7ff; background: linear-gradient(135deg, #fafaff 0%, #fff 100%); }
.ai-advisor-card h3 { color: #3730a3; }
.market-input-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }
.market-field { display: flex; flex-direction: column; gap: 6px; }
.market-field label { font-size: 13px; font-weight: 600; color: #374151; }
.field-required { color: #ef4444; }
.field-hint { font-size: 11px; color: #94a3b8; }
.market-textarea {
  width: 100%; padding: 10px 14px; border: 1.5px solid #e2e8f0; border-radius: 10px;
  font-size: 13px; color: #1e293b; background: #fff; resize: vertical;
  outline: none; transition: border-color .15s; font-family: inherit;
}
.market-textarea:focus { border-color: #4f6ef7; box-shadow: 0 0 0 3px rgba(79,110,247,.1); }
.btn-ai {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: #fff; border: none; border-radius: 10px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.btn-ai:hover { opacity: 0.9; }
.btn-ai:disabled { opacity: 0.5; cursor: not-allowed; }

/* 推荐结果 */
.recommend-result {
  margin-top: 20px; padding: 20px; background: #fff; border: 1.5px solid #e2e8f0;
  border-radius: 14px; animation: fadeInUp .3s ease;
}
@keyframes fadeInUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.recommend-header { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.recommend-ai-badge {
  padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700;
  background: #fef2f2; color: #dc2626;
}
.recommend-ai-badge.ai-ok { background: #f0fdf4; color: #16a34a; }
.strategy-box {
  padding: 14px 16px; background: #eff6ff; border: 1px solid #bfdbfe;
  border-radius: 10px; margin-bottom: 16px;
}
.strategy-label { font-size: 12px; font-weight: 700; color: #1d4ed8; margin-bottom: 4px; }
.strategy-text { font-size: 13px; color: #1e40af; line-height: 1.5; }
.recommend-prices { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 12px; }
.rec-price-card {
  padding: 14px 10px; background: #f8fafc; border: 1.5px solid #e2e8f0;
  border-radius: 10px; text-align: center;
}
.rec-price-card.accent { border-color: #fbbf24; background: #fffbeb; }
.rec-price-label { font-size: 11px; color: #64748b; font-weight: 600; margin-bottom: 4px; }
.rec-price-value { font-size: 20px; font-weight: 800; color: #1e293b; }
.rec-price-card.accent .rec-price-value { color: #d97706; }
.recommend-discounts { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.rec-disc-item {
  padding: 4px 10px; background: #f1f5f9; border-radius: 6px;
  font-size: 12px; color: #475569; font-weight: 600;
}

/* 场景对比表 */
.scenario-table-wrap { margin-top: 8px; }
.scenario-table-label { font-size: 13px; font-weight: 700; color: #374151; margin-bottom: 8px; }
.scenario-table {
  width: 100%; border-collapse: collapse; font-size: 13px;
}
.scenario-table th {
  padding: 8px 10px; background: #f1f5f9; color: #475569; font-weight: 600;
  text-align: left; border-bottom: 1.5px solid #e2e8f0;
}
.scenario-table td {
  padding: 8px 10px; border-bottom: 1px solid #f1f5f9; color: #334155;
}
.scenario-table tr:hover td { background: #f8fafc; }
.scenario-table .your-price { font-weight: 700; color: #4f6ef7; }
.compare-tag {
  padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700;
}
.compare-low { background: #dcfce7; color: #16a34a; }
.compare-same { background: #fef3c7; color: #d97706; }
.btn-success {
  background: linear-gradient(135deg, #059669 0%, #10b981 100%);
  color: #fff; border: none; border-radius: 10px; font-weight: 700;
}
.btn-success:hover { opacity: 0.9; }
.btn-success:disabled { opacity: 0.5; cursor: not-allowed; }

/* Payment Admin */
.monitor-summary { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; }
.monitor-summary-row { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.monitor-summary-item { font-size: 13px; color: #64748b; }
.text-warn { color: #f59e0b; }
.text-ok { color: #16a34a; }
.ypay-tab { width: 100%; }
.ypay-subtabs { display: flex; gap: 4px; margin-bottom: 18px; }
.ypay-subtab {
  padding: 8px 20px; border: 1px solid #e2e8f0; border-radius: 8px;
  background: #fff; color: #64748b; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all .15s;
}
.ypay-subtab:hover { border-color: #4f6ef7; color: #4f6ef7; }
.ypay-subtab.active { background: #4f6ef7; color: #fff; border-color: #4f6ef7; }

.ypay-order-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; flex-wrap: wrap; gap: 8px; }
.ypay-order-filters { display: flex; gap: 4px; }
.ypay-filter-btn {
  padding: 5px 14px; border: 1px solid #e2e8f0; border-radius: 8px;
  background: #fff; color: #64748b; font-size: 12.5px; font-weight: 500; cursor: pointer; transition: all 0.15s;
}
.ypay-filter-btn:hover { border-color: #4f6ef7; color: #4f6ef7; }
.ypay-filter-btn.active { background: #4f6ef7; color: #fff; border-color: #4f6ef7; }

.ypay-status-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.ypay-stat-item {
  background: #f8fafc; border: 1px solid #e2e8f0;
  border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 6px;
}
.ypay-stat-label { font-size: 11.5px; color: #94a3b8; font-weight: 500; }
.ypay-stat-value { font-size: 15px; font-weight: 700; color: #1e293b; }
.ypay-stat-value.warn { color: #f59e0b; }
.ypay-stat-value.success { color: #22c55e; }
.ypay-stat-badge {
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 14px; border-radius: 14px; font-size: 12px; font-weight: 600;
}
.ypay-stat-badge.online { background: #f0fdf4; color: #22c55e; }
.ypay-stat-badge.offline { background: #fef2f2; color: #ef4444; }
.ypay-stat-badge.key-mismatch { background: #fffbeb; color: #d97706; gap: 6px; }
.ypay-stat-badge.key-mismatch svg { stroke: #f59e0b; }
.ypay-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.dot-live { background: #22c55e; box-shadow: 0 0 6px rgba(34,197,94,.5); animation: pulse-dot 1.5s ease-in-out infinite; }
.dot-dead { background: #ef4444; }
@keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }
.ypay-heart-stale { color: #ef4444 !important; }

.ypay-key-mismatch-alert {
  display: flex; align-items: flex-start; gap: 12px; margin-top: 14px; padding: 14px 18px;
  background: #fffbeb; border: 1px solid #fcd34d; border-radius: 12px; color: #92400e;
}
.ypay-key-mismatch-alert svg { flex-shrink: 0; margin-top: 2px; stroke: #f59e0b; }
.ypay-key-mismatch-text { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; line-height: 1.5; }
.ypay-key-mismatch-text strong { font-size: 13px; color: #78350f; }

.ypay-health-section { margin-top: 16px; padding: 14px 18px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; }
.ypay-health-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.ypay-health-label { font-size: 13px; font-weight: 600; color: #334155; }
.ypay-health-rate { font-size: 18px; font-weight: 700; }
.ypay-health-rate.good { color: #22c55e; }
.ypay-health-rate.warn { color: #f59e0b; }
.ypay-health-rate.bad { color: #ef4444; }
.ypay-health-bar-track { height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; }
.ypay-health-bar-fill { height: 100%; border-radius: 3px; transition: width 0.6s ease; }
.ypay-health-bar-fill.good { background: linear-gradient(90deg, #22c55e, #4ade80); }
.ypay-health-bar-fill.warn { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
.ypay-health-bar-fill.bad { background: linear-gradient(90deg, #ef4444, #f87171); }
.ypay-health-stats { display: flex; gap: 16px; margin-top: 8px; font-size: 12px; color: #64748b; }
.ypay-health-ok { color: #22c55e; }
.ypay-health-fail { color: #ef4444; }
.ypay-health-ip { color: #6366f1; }

.ypay-actions-row { display: flex; gap: 10px; margin-top: 12px; }
.ypay-test-panel { margin-top: 16px; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; }
.ypay-test-summary { padding: 14px 18px; font-size: 13px; font-weight: 600; }
.ypay-test-summary.all-ok { background: #f0fdf4; color: #16a34a; }
.ypay-test-summary.has-issue { background: #fef2f2; color: #ef4444; }
.ypay-test-item { display: flex; align-items: center; gap: 10px; padding: 10px 18px; border-top: 1px solid #f1f5f9; font-size: 12.5px; }
.ypay-test-item:last-child { border-radius: 0 0 12px 12px; }
.ypay-test-item.ok { background: #fff; }
.ypay-test-item.fail { background: #fffbfb; }
.ypay-test-icon {
  width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.ypay-test-item.ok .ypay-test-icon { background: #dcfce7; color: #16a34a; }
.ypay-test-item.fail .ypay-test-icon { background: #fee2e2; color: #ef4444; }
.ypay-test-name { min-width: 90px; font-weight: 600; color: #1e293b; flex-shrink: 0; }
.ypay-test-msg { color: #64748b; }

.channel-test-loading { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 32px; color: #64748b; font-size: 14px; }
.channel-test-checks { margin-bottom: 16px; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; }
.channel-test-qr { text-align: center; padding: 20px; background: #f8fafc; border: 2px dashed #e2e8f0; border-radius: 12px; margin-top: 12px; }
.channel-test-qr-label { font-size: 13px; color: #64748b; margin: 0 0 12px; }
.channel-test-qr-img { width: 200px; height: 200px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.channel-test-qr-hint { font-size: 12px; color: #94a3b8; margin: 10px 0 0; }
.channel-test-ok { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 16px; background: #f0fdf4; border-radius: 12px; color: #16a34a; font-weight: 600; font-size: 14px; margin-top: 12px; }

.paytest-checks { margin: 16px 0; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; }
.paytest-start { margin: 20px 0; text-align: center; }
.paytest-pay-area { margin-top: 20px; }
.paytest-qr-box { display: flex; flex-direction: column; align-items: center; gap: 16px; padding: 32px; background: #f8fafc; border: 2px dashed #e2e8f0; border-radius: 16px; }
.paytest-qr-img { width: 220px; height: 220px; border-radius: 8px; box-shadow: 0 2px 12px rgba(0,0,0,.08); }
.paytest-amount { font-size: 16px; color: #334155; }
.paytest-amount strong { font-size: 20px; color: #ef4444; }
.paytest-amount-warn { font-size: 12px; color: #ef4444; margin-top: 4px; }
.paytest-status { margin-top: 16px; text-align: center; }
.paytest-waiting { display: flex; align-items: center; justify-content: center; gap: 10px; color: #64748b; font-size: 14px; }
.paytest-success { display: flex; align-items: center; justify-content: center; gap: 10px; color: #16a34a; font-size: 15px; font-weight: 600; padding: 16px; background: #f0fdf4; border-radius: 12px; }
.paytest-expired { display: flex; align-items: center; justify-content: center; gap: 10px; color: #ef4444; font-size: 14px; padding: 16px; background: #fef2f2; border-radius: 12px; }

.ypay-state {
  display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11.5px; font-weight: 600;
}
.ypay-state.paid { background: #f0fdf4; color: #22c55e; }
.ypay-state.unpaid { background: #fffbeb; color: #f59e0b; }
.ypay-state.closed { background: #f1f5f9; color: #94a3b8; }

.ypay-settings-layout { display: flex; flex-direction: column; gap: 20px; }
.ypay-qr-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.ypay-qr-card { text-align: center; }
.ypay-qr-img-wrap {
  width: 160px; height: 160px; margin: 16px auto; display: flex;
  align-items: center; justify-content: center; background: #fff;
  border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden;
}
.ypay-qr-img { width: 140px; height: 140px; object-fit: contain; transition: opacity .3s; }
.qr-loading {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 8px; color: #9ca3af; font-size: 12px; z-index: 1;
}
.qr-spinner {
  width: 28px; height: 28px; border: 3px solid #e5e7eb;
  border-top-color: #6366f1; border-radius: 50%; animation: qr-spin .8s linear infinite;
}
@keyframes qr-spin { to { transform: rotate(360deg); } }

.hint-text { font-size: 11px; color: #94a3b8; font-weight: 400; }

.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.field-row .field { margin-bottom: 16px; }

.settings-card select {
  height: 44px; padding: 0 14px; border: 1.5px solid #e2e8f0;
  border-radius: 10px; background: #f8fafc; color: #1e293b;
  font-size: 14px; outline: none; width: 100%;
}
.settings-card textarea {
  padding: 10px 14px; border: 1.5px solid #e2e8f0; border-radius: 10px;
  background: #f8fafc; color: #1e293b; font-size: 14px; outline: none;
  width: 100%; resize: vertical; font-family: inherit; box-sizing: border-box;
}
.settings-card textarea:focus, .settings-card select:focus {
  border-color: #4f6ef7; box-shadow: 0 0 0 3px rgba(79,110,247,.1); background: #fff;
}

.mono { font-family: 'SF Mono', 'Consolas', monospace; font-size: 12px; }
.small { font-size: 11.5px; color: #94a3b8; }

.pagination {
  display: flex; align-items: center; justify-content: center; gap: 12px;
  margin-top: 16px; padding: 12px 0;
}
.pagination button {
  padding: 6px 14px; border: 1px solid #e2e8f0; border-radius: 8px;
  background: #fff; color: #64748b; font-size: 12px; cursor: pointer;
}
.pagination button:hover:not(:disabled) { border-color: #4f6ef7; color: #4f6ef7; }
.pagination button:disabled { opacity: .4; cursor: not-allowed; }
.pagination span { font-size: 12px; color: #64748b; }

.app-config-layout { display: grid; grid-template-columns: 280px 1fr; gap: 24px; align-items: start; }
.app-qrcode-box { text-align: center; }
.app-qrcode-label { font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 12px; }
.app-qrcode-img { width: 220px; height: 220px; border: 1px solid #e2e8f0; border-radius: 12px; padding: 8px; background: #fff; }
.app-qrcode-hint { font-size: 12px; color: #94a3b8; margin-top: 10px; line-height: 1.6; }
.app-manual-box { display: flex; flex-direction: column; gap: 14px; }
.app-field { display: flex; flex-direction: column; gap: 5px; }
.app-field label { font-size: 12px; font-weight: 600; color: #475569; }
.app-copy-row { display: flex; align-items: center; gap: 8px; }
.app-code { flex: 1; padding: 9px 14px; background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 12.5px; font-family: 'SF Mono','Consolas',monospace; color: #1e293b; word-break: break-all; }
.app-copy-btn { flex-shrink: 0; }
.app-steps { margin-top: 6px; padding: 14px 16px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; }
.app-step-label { font-size: 12px; font-weight: 600; color: #475569; margin-bottom: 8px; }
.app-step-list { margin: 0; padding-left: 20px; font-size: 12.5px; color: #64748b; line-height: 1.9; }

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
    background: rgba(0,0,0,.4);
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
.ypay-key-code { display: inline-block; height: 40px; line-height: 40px; padding: 0 14px; background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; font-family: 'SF Mono','Consolas',monospace; color: #4f6ef7; min-width: 180px; text-align: center; }

.personnel-tab { width: 100%; }
.personnel-subtabs { display: flex; gap: 4px; margin-bottom: 18px; }
.ps-tab {
  padding: 8px 24px; border: 1px solid #e2e8f0; border-radius: 8px;
  background: #fff; color: #64748b; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all .15s;
}
.ps-tab:hover { border-color: #4f6ef7; color: #4f6ef7; }
.ps-tab.active { background: #4f6ef7; color: #fff; border-color: #4f6ef7; }

.ps-panel { }
.ps-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; flex-wrap: wrap; gap: 8px; }
.ps-header h3 { font-size: 16px; font-weight: 700; color: #1e293b; }
.ps-desc { font-size: 12.5px; color: #94a3b8; margin-bottom: 16px; }
.ps-loading { text-align: center; padding: 40px; color: #94a3b8; font-size: 13px; }
.ps-empty { text-align: center; padding: 48px; color: #94a3b8; }
.ps-empty-icon { font-size: 40px; display: block; margin-bottom: 8px; }
.ps-empty p { font-size: 13px; }
.ps-table-wrap { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.03); }

.badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11.5px; font-weight: 600; }
.badge-info { background: #eef1fe; color: #4f6ef7; }
.badge-success { background: #f0fdf4; color: #22c55e; }
.text-muted { color: #94a3b8; }

.tier-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.tier-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.03); }
.tc-head { display: flex; align-items: center; gap: 10px; padding: 14px 16px; font-size: 13px; font-weight: 700; }
.tc-head.l1 { background: linear-gradient(135deg, #eef1fe, #dbe4fe); color: #3b5de7; }
.tc-head.l2 { background: linear-gradient(135deg, #f0f9ff, #e0f2fe); color: #0284c7; }
.tc-head.l3 { background: linear-gradient(135deg, #f0fdf4, #dcfce7); color: #16a34a; }
.tc-badge { padding: 2px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; }
.tc-head.l1 .tc-badge { background: #4f6ef7; color: #fff; }
.tc-head.l2 .tc-badge { background: #0ea5e9; color: #fff; }
.tc-head.l3 .tc-badge { background: #22c55e; color: #fff; }
.tc-count { margin-left: auto; font-size: 12px; opacity: .7; }
.tc-body { padding: 8px 0; }
.tc-empty { padding: 24px; text-align: center; font-size: 12px; color: #94a3b8; }
.tc-row { display: flex; align-items: center; gap: 10px; padding: 8px 16px; border-top: 1px solid #f1f5f9; font-size: 13px; }
.tc-name { flex: 1; font-weight: 500; color: #1e293b; }
.tc-balance { font-weight: 600; color: #ef4444; font-size: 12px; }
.tc-select { padding: 4px 8px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 11px; font-weight: 600; color: #475569; background: #fff; cursor: pointer; }
.tc-select:focus { border-color: #4f6ef7; outline: none; }

@media (max-width: 768px) {
  .tier-grid { grid-template-columns: 1fr; }
  .tcc-row { grid-template-columns: 1fr; }
}

.tier-commission-config {
  margin-top: 20px; padding: 20px;
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,.03);
}
.tier-commission-config h4 { font-size: 15px; font-weight: 700; margin-bottom: 6px; color: #1e293b; }
.tcc-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.tcc-item { text-align: center; padding: 16px 10px; background: #f8fafc; border-radius: 10px; border: 1px solid #e2e8f0; }
.tcc-badge { display: inline-block; padding: 2px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; margin-bottom: 6px; }
.tcc-badge.l1 { background: #4f6ef7; color: #fff; }
.tcc-badge.l2 { background: #0ea5e9; color: #fff; }
.tcc-badge.l3 { background: #22c55e; color: #fff; }
.tcc-label { display: block; font-size: 12px; color: #64748b; margin-bottom: 8px; }
.tcc-input-row { display: flex; align-items: center; justify-content: center; gap: 6px; }
.tcc-input { width: 72px; height: 36px; padding: 0 8px; border: 1px solid #e2e8f0; border-radius: 8px; text-align: center; font-size: 14px; font-weight: 700; color: #1e293b; background: #fff; }
.tcc-input:focus { border-color: #4f6ef7; outline: none; box-shadow: 0 0 0 3px rgba(79,110,247,.08); }
.tcc-pct { font-size: 14px; font-weight: 700; color: #4f6ef7; }
.spinner-sm { width: 14px; height: 14px; border: 2px solid rgba(255,255,255,.3); border-top-color: #fff; border-radius: 50%; animation: spin .6s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Agent Fees - Clean Cards */
.af-settings { max-width: 680px; display: flex; flex-direction: column; gap: 16px; }
.af-page-card { max-width: 100%; }
.af-action-card { padding-top: 8px; }
.af-card-header { display: flex; align-items: center; gap: 14px; margin-bottom: 24px; padding-bottom: 18px; border-bottom: 1px solid var(--c-border); }
.af-card-header-icon { width: 40px; height: 40px; border-radius: 10px; background: var(--c-primary-bg, #eef1fe); color: var(--c-primary, #4f6ef7); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.af-header-desc { font-size: 13px; color: #94a3b8; margin-top: 2px; }
.af-card-new {
  padding: 18px 0;
  border-bottom: 1px solid #f1f5f9;
}
.af-card-new:last-of-type { border-bottom: none; }
.af-card-row { display: flex; align-items: center; gap: 16px; }
.af-card-icon-circle {
  width: 44px; height: 44px; border-radius: 12px; flex-shrink: 0;
  background: #eff6ff; color: #4f6ef7;
  display: flex; align-items: center; justify-content: center;
}
.af-card-icon-circle.af-ic-purple { background: #f3e8ff; color: #8b5cf6; }
.af-card-info { flex: 1; min-width: 0; }
.af-card-title { font-size: 15px; font-weight: 600; color: #1e293b; }
.af-card-desc { font-size: 12.5px; color: #94a3b8; margin-top: 3px; }
.af-card-fee { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.af-fee-label { font-size: 17px; font-weight: 700; color: #64748b; }
.af-fee-inp {
  width: 90px; height: 38px; border: 1.5px solid #d1d5db; border-radius: 8px;
  padding: 0 10px; font-size: 15px; font-weight: 600; color: #1e293b;
  text-align: left; background: #fff;
}
.af-fee-inp:focus { outline: none; border-color: #4f6ef7; box-shadow: 0 0 0 3px rgba(79,110,247,.1); }

.af-card-sub {
  margin-top: 16px; padding-top: 16px; border-top: 1px solid #f1f5f9;
  display: flex; flex-direction: column; gap: 10px;
}
.af-sub-row { display: flex; align-items: center; justify-content: space-between; padding: 0 0 0 60px; }
.af-sub-info { display: flex; align-items: center; gap: 10px; }
.af-sub-badge {
  width: 30px; height: 30px; border-radius: 7px; display: flex; align-items: center;
  justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0;
}
.af-sub-badge.l1 { background: #dbeafe; color: #2563eb; }
.af-sub-badge.l2 { background: #e0e7ff; color: #4f46e5; }
.af-sub-badge.l3 { background: #f3e8ff; color: #7c3aed; }
.af-sub-text { font-size: 13px; color: #64748b; }
.af-sub-fee { display: flex; align-items: center; gap: 4px; }


.mt-col { font-size: 12px; color: #475569; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.btn-danger { background: #ef4444; color: #fff; }
.btn-danger:hover { background: #dc2626; }
.empty-text { text-align: center; padding: 24px; color: #94a3b8; font-size: 13px; }

.ads-tab { width: 100%; }
.ads-help { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; font-size: 13px; color: #64748b; line-height: 1.7; }
.ads-help p { margin: 0; }
.ads-help strong { color: #475569; }
.panel-head-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.panel-head-row h3 { font-size: 16px; font-weight: 700; color: #1a1a1a; }
.empty-card { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 48px 20px; background: #fff; border: 1px dashed #e0e3e8; border-radius: 12px; gap: 12px; }
.empty-card p { color: #94a3b8; font-size: 14px; }
.slot-badge { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 8px; background: #eef2ff; color: #6366f1; font-size: 13px; font-weight: 700; }
.ad-name-cell { font-weight: 600; color: #1a1a1a; }
.ad-preview-cell { font-size: 12px; color: #94a3b8; max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.status-tag { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all .15s; }
.status-tag.active { background: #ecfdf5; color: #059669; }
.status-tag.inactive { background: #f3f4f6; color: #9ca3af; }
.status-tag:hover { opacity: .8; }
.row-actions { display: flex; gap: 6px; }
.slot-auto { font-size: 13px; color: #6b7280; padding: 6px 0; }
.slot-auto strong { color: #6366f1; }
.ad-upload-row textarea { width: 100%; }
.ad-upload-actions { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.ad-file-hint { font-size: 12px; color: #9ca3af; }
.modal-wide { max-width: 640px; width: 90vw; }

.qr-thumb { width: 36px; height: 36px; border-radius: 6px; border: 1px solid #e2e8f0; cursor: pointer; object-fit: cover; }
.qr-thumb:hover { transform: scale(1.1); }
.qr-modal { background: #fff; border-radius: 14px; padding: 20px; text-align: center; box-shadow: 0 25px 60px rgba(0,0,0,.15); }
.qr-modal img { max-width: 280px; max-height: 280px; display: block; margin-bottom: 12px; border-radius: 8px; }

/* 风险监控 */
.risk-tab { width: 100%; display: flex; flex-direction: column; gap: 16px; }
.risk-dashboard { display: flex; align-items: center; justify-content: space-between; gap: 32px; background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px 28px; box-shadow: 0 1px 3px rgba(0,0,0,.03); }
.risk-gauge-card { display: flex; align-items: center; gap: 24px; flex: 1; }
.risk-gauge { position: relative; width: 120px; height: 120px; flex-shrink: 0; }
.risk-gauge-svg { width: 120px; height: 120px; }
.risk-gauge-fill { transition: stroke-dasharray .8s cubic-bezier(.4,0,.2,1), stroke .3s; }
.risk-gauge-inner { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.risk-gauge-score { font-size: 36px; font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
.risk-gauge-label { font-size: 11px; color: #94a3b8; margin-top: 2px; }
.risk-gauge.level-good .risk-gauge-score { color: #10b981; }
.risk-gauge.level-warn .risk-gauge-score { color: #f59e0b; }
.risk-gauge.level-bad .risk-gauge-score { color: #ef4444; }
.risk-gauge-info { display: flex; flex-direction: column; gap: 4px; }
.risk-gauge-title { font-size: 22px; font-weight: 700; }
.risk-gauge-title.level-good { color: #10b981; }
.risk-gauge-title.level-warn { color: #f59e0b; }
.risk-gauge-title.level-bad { color: #ef4444; }
.risk-gauge-desc { font-size: 13px; color: #64748b; }
.risk-gauge-time { font-size: 12px; color: #94a3b8; margin-top: 4px; }
.risk-actions { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
.health-settings-modal { max-width: 480px; width: 90vw; }
.health-form-group { margin-bottom: 16px; }
.health-form-group label { display: block; font-size: 13px; font-weight: 500; color: var(--text, #1e293b); margin-bottom: 6px; }
.health-form-input { padding: 6px 10px; border: 1px solid var(--border, #e2e8f0); border-radius: 6px; background: var(--bg, #fff); color: var(--text, #1e293b); font-size: 13px; }
.health-form-input:focus { outline: none; border-color: var(--primary, #3b82f6); }
.health-account-list { border: 1px solid var(--border, #e2e8f0); border-radius: 8px; overflow: hidden; }
.health-account-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; font-size: 13px; border-bottom: 1px solid var(--border, #e2e8f0); }
.health-account-item:last-child { border-bottom: none; }
.health-account-item.active { background: color-mix(in srgb, var(--primary, #3b82f6) 8%, transparent); }
.health-account-name { flex: 1; font-weight: 500; }
.health-account-badge { font-size: 11px; color: var(--primary, #3b82f6); background: color-mix(in srgb, var(--primary, #3b82f6) 12%, transparent); padding: 1px 6px; border-radius: 4px; }
.health-account-actions { display: flex; gap: 4px; }
.health-add-row { display: flex; gap: 8px; align-items: center; }
.health-add-row .health-form-input { flex: 1; }
.risk-check-progress { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--primary, #3b82f6); margin-left: 8px; }
.risk-check-spinner { width: 14px; height: 14px; border: 2px solid var(--border, #e2e8f0); border-top-color: var(--primary, #3b82f6); border-radius: 50%; animation: risk-spin 0.8s linear infinite; }
@keyframes risk-spin { to { transform: rotate(360deg); } }
.risk-login-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px 18px; margin-top: 12px; }
.risk-login-title { font-size: 14px; font-weight: 600; color: #1e293b; margin-bottom: 4px; }
.risk-login-desc { font-size: 12px; color: #94a3b8; margin-bottom: 12px; }
.risk-login-form { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.risk-login-select { padding: 7px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; background: #fff; color: #334155; min-width: 140px; }
.risk-login-input { padding: 7px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; min-width: 120px; }
.risk-login-input:focus, .risk-login-select:focus { outline: none; border-color: #4f6ef7; box-shadow: 0 0 0 2px rgba(79,110,247,.15); }
.risk-checks { display: flex; flex-direction: column; gap: 8px; }
.risk-check-item { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; cursor: pointer; transition: border-color .15s, box-shadow .15s; }
.risk-check-item:hover { border-color: #cbd5e1; box-shadow: 0 2px 8px rgba(0,0,0,.04); }
.risk-check-main { display: flex; align-items: center; gap: 14px; padding: 16px 18px; }
.risk-check-icon { width: 28px; height: 28px; flex-shrink: 0; }
.risk-check-icon.pass { color: #10b981; }
.risk-check-icon.warn { color: #f59e0b; }
.risk-check-icon.fail { color: #ef4444; }
.risk-check-info { flex: 1; min-width: 0; }
.risk-check-name { font-size: 14px; font-weight: 600; color: #1e293b; }
.risk-check-desc { font-size: 12px; color: #94a3b8; margin-top: 2px; }
.risk-check-status { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 20px; flex-shrink: 0; }
.risk-check-status.pass { background: #ecfdf5; color: #059669; }
.risk-check-status.warn { background: #fffbeb; color: #d97706; }
.risk-check-status.fail { background: #fef2f2; color: #dc2626; }
.risk-check-arrow { width: 18px; height: 18px; color: #94a3b8; flex-shrink: 0; transition: transform .2s; }
.risk-check-arrow.open { transform: rotate(180deg); }
.risk-check-detail { border-top: 1px solid #f1f5f9; padding: 16px 18px; background: #f8fafc; border-radius: 0 0 12px 12px; }
.risk-health-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.risk-health-card { padding: 12px 14px; border-radius: 8px; border: 1px solid #e2e8f0; background: #fff; }
.risk-health-card.health-ok { border-left: 3px solid #10b981; }
.risk-health-card.health-bad { border-left: 3px solid #ef4444; }
.health-name { font-size: 13px; font-weight: 600; color: #1e293b; }
.health-domain { font-size: 11px; color: #94a3b8; margin-top: 2px; }
.health-status { font-size: 12px; color: #475569; margin-top: 6px; display: flex; align-items: center; gap: 6px; }
.health-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.health-dot.dot-ok { background: #10b981; }
.health-dot.dot-bad { background: #ef4444; }
.empty-sm { padding: 16px; text-align: center; color: #94a3b8; font-size: 13px; }
.data-table-sm { font-size: 12px; }
.data-table-sm th, .data-table-sm td { padding: 8px 10px; }
.risk-interval-row { display: flex; align-items: center; gap: 10px; }
.risk-interval-row label { font-size: 13px; color: #475569; white-space: nowrap; }
.risk-interval-input { width: 100px; padding: 6px 10px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; }
.risk-interval-hint { font-size: 12px; color: #94a3b8; margin-left: 4px; }

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

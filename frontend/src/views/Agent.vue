<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import type { AgentProfile } from '@/api'
import AppTopbar from '@/components/AppTopbar.vue'
import PaymentSuccess from '@/components/PaymentSuccess.vue'
import { useAppStore } from '@/stores/app'
import { useAgentAuth } from '@/composables/useAgentAuth'
import { useAgentDashboard } from '@/composables/useAgentDashboard'
import { useAgentData } from '@/composables/useAgentData'

const store = useAppStore()
const agent = ref<AgentProfile | null>(null)

const dashboard = useAgentDashboard(agent)
const { loadDashboard, activeTab, mySection, dashboard: dashData,
  upgradeInfo, upgradeLoading, upgradeShowPay, upgradeQrImage, upgradeFee,
  upgradeTargetTier, upgradePaying, upgradePaid, showPaySuccess,
  switchTab: switchTabRaw,
  loadUpgradeInfo, doRequestUpgrade, closeUpgradePay, saveUpgradeQr, onPaySuccessDone, checkUpgradePaid,
} = dashboard

const auth = useAgentAuth(agent, loadDashboard)
const { capturedRef, agentStatus, loading, needsAuth, showAuthForm, applying, applyErr,
  authMode, authUsername, authPassword, authNickname, authSubmitting,
  captchaToken, captchaAnswer, captchaImage, captchaLoading,
  regShowPay, regStep, regQrImage, regFee, regPaying, regPaid, showRegPaySuccess,
  checkAgentStatus, loadCaptcha, doAuth, logoutUser,
  closeRegPay, saveRegQr, apply, checkRegPaid, onRegPaySuccessDone,
} = auth

const data = useAgentData(agent, loadDashboard)
const { commissions, commissionsTotal, referrals, referralsTotal,
  withdrawals, withdrawalsTotal, selectedAmount, withdrawing, withdrawRules, childAgents, withdrawPresets,
  orders, ordersTotal, loadingOrders,
  profileForm, pwForm, savingProfile, changingPw, uploadingQr, qrPreview,
  userProfile, savingUserProfile,
  loadCommissions, loadReferrals, loadWithdrawals, loadWithdrawRules, loadOrders,
  doWithdraw, initProfileForm, saveProfile, saveUserProfile,
  triggerQrUpload, handleQrFile, changePassword, copyLink,
} = data

async function switchTab(tab: 'dashboard' | 'orders' | 'commissions' | 'withdrawals' | 'my') {
  await switchTabRaw(tab, {
    loadOrders, loadCommissions, loadWithdrawals, loadWithdrawRules, loadReferrals,
    loadUpgradeInfo, initProfileForm,
    commissionsLoaded: () => commissions.value.length > 0,
    withdrawalsLoaded: () => withdrawals.value.length > 0,
    referralsLoaded: () => referrals.value.length > 0,
  })
}

function doChangePassword() { changePassword(logoutUser) }

onMounted(() => checkAgentStatus())
watch(showAuthForm, (v) => { if (v) loadCaptcha() })
onUnmounted(() => {
  if (auth.regPollInterval.value) { clearTimeout(auth.regPollInterval.value); auth.regPollInterval.value = null }
  if (dashboard.upgradePollInterval.value) { clearTimeout(dashboard.upgradePollInterval.value); dashboard.upgradePollInterval.value = null }
})

const orderStatusLabel: Record<string, string> = { pending: '待处理', accepted: '已接单', running: '执行中', completed: '已完成', failed: '失败', cancelled: '已取消', waiting: '等待明天', paid: '已支付', queued: '排队中', retrying: '重试中', amount_mismatch: '金额异常' }
const orderStatusClass: Record<string, string> = { pending: 'warn', accepted: 'primary', running: 'primary', completed: 'ok', failed: 'bad', cancelled: 'muted', waiting: 'primary', paid: 'ok', queued: 'primary', retrying: 'warn', amount_mismatch: 'bad' }
const fmtDate = (s: string) => s ? s.replace('T', ' ').substring(0, 19) : '-'
const fmtMoney = (n: number) => `¥${(n || 0).toFixed(2)}`
const statusLabel: Record<string, string> = { pending: '待审核', active: '正常', suspended: '已暂停' }
const fullReferralLink = computed(() => window.location.origin + (dashData.referral_link || ''))
const fullSubsiteLink = computed(() => window.location.origin + (dashData.subsite_link || ''))
</script>

<template>
  <div class="page">
    <AppTopbar :show-logout="store.isUserLoggedIn" @logout="logoutUser" />

    <div class="content-wrapper">
      <div v-if="loading" class="loading-area">
        <div class="spinner-lg"></div>
        <p>加载中...</p>
      </div>

      <!-- Unauthenticated — two-stage: hero first, then auth -->
      <div v-else-if="needsAuth" class="apply-center">
        <div class="apply-card">
          <!-- Stage 1: Hero + CTA -->
          <template v-if="!showAuthForm">
            <div class="apply-icon">
              <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="var(--c-primary)" stroke-width="1.2">
                <path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><path d="M20 8v6"/><path d="M23 11h-6"/>
              </svg>
            </div>
            <h2>开启推广赚钱之旅</h2>
            <p>分享专属邀请链接，用户下单即获佣金</p>
            <div class="apply-features">
              <div class="af">
<span class="af-dot"></span>最高15%佣金比例
</div>
              <div class="af">
<span class="af-dot"></span>邀请无上限，收益随时提现
</div>
              <div class="af">
<span class="af-dot"></span>专属子站与推广链接
</div>
            </div>
            <button class="btn btn-primary btn-lg" style="margin-top:8px" @click="showAuthForm = true">
欢迎加入我们
</button>
            <p class="auth-hint">
已有账号？<a href="#" @click.prevent="authMode = 'login'; showAuthForm = true">直接登录</a>
</p>
          </template>

          <!-- Stage 2: Register/Login form only -->
          <div v-else class="auth-section">
            <div class="auth-section-icon">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--c-primary)" stroke-width="1.2">
                <path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/>
              </svg>
            </div>
            <h3>注册 / 登录</h3>
            <div v-if="capturedRef" class="ref-banner">
通过推荐码 <code>{{ capturedRef }}</code> 注册
</div>
            <div class="auth-tabs-compact">
              <button :class="{ active: authMode === 'login' }" @click="authMode = 'login'">
已有账号
</button>
              <button :class="{ active: authMode === 'register' }" @click="authMode = 'register'">
注册账号
</button>
            </div>
            <form class="auth-form-compact" @submit="doAuth">
              <div class="field">
                <input v-model="authUsername" placeholder="用户名" autocomplete="username" />
              </div>
              <div class="field">
                <input v-model="authPassword" type="password" placeholder="密码" autocomplete="current-password" />
              </div>
              <div v-if="authMode === 'register'" class="field">
                <input v-model="authNickname" placeholder="昵称（选填）" />
              </div>
              <div class="captcha-row">
                <input v-model="captchaAnswer" placeholder="请输入验证码" autocomplete="off" />
                <img v-if="captchaImage" :src="captchaImage" class="captcha-img" title="点击刷新验证码" @click="loadCaptcha" />
                <div v-else class="captcha-placeholder" @click="loadCaptcha">
                  <span v-if="captchaLoading">加载中...</span>
                  <span v-else>点击获取验证码</span>
                </div>
              </div>
              <button type="submit" class="btn btn-primary btn-lg btn-block" :disabled="authSubmitting">
                {{ authSubmitting ? '请稍候...' : (authMode === 'register' ? '注册' : '登录') }}
              </button>
            </form>
            <button class="btn btn-ghost btn-sm btn-block" style="margin-top:10px" @click="showAuthForm = false">
返回
</button>
          </div>
        </div>
      </div>

      <!-- Has account, no agent yet -->
      <div v-else-if="agentStatus === 'none'" class="apply-center">
        <div class="apply-card">
          <div v-if="applying" class="apply-loading">
            <div class="spinner-lg"></div>
            <p>正在开通代理...</p>
          </div>
          <template v-else>
            <div class="apply-icon">
              <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="var(--c-primary)" stroke-width="1.2">
                <path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><path d="M20 8v6"/><path d="M23 11h-6"/>
              </svg>
            </div>
            <h2>开启推广赚钱之旅</h2>
            <p>分享专属邀请链接，用户下单即获佣金</p>
            <div class="apply-features">
              <div class="af">
<span class="af-dot"></span>最高15%佣金比例
</div>
              <div class="af">
<span class="af-dot"></span>邀请无上限，收益随时提现
</div>
              <div class="af">
<span class="af-dot"></span>专属子站与推广链接
</div>
            </div>
            <div v-if="applyErr" class="apply-error">
{{ applyErr }}
</div>
            <button class="btn btn-primary btn-lg" :disabled="applying" @click="regStep = 'choose'; regShowPay = true">
升级为L1代理
</button>
          </template>
        </div>
      </div>

      <!-- Pending -->
      <div v-else-if="agentStatus === 'pending'" class="status-center">
        <div class="status-card">
          <div class="status-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#4f6ef7" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/></svg>
          </div>
          <h2>申请已提交</h2>
          <p>管理员正在审核中，通过后即可开始推广赚钱</p>
          <div class="status-code">
推荐码 <code>{{ agent?.referral_code }}</code>
</div>
        </div>
      </div>

      <!-- Suspended -->
      <div v-else-if="agentStatus === 'suspended'" class="status-center">
        <div class="status-card">
          <div class="status-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="1.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          </div>
          <h2>代理账号已暂停</h2>
          <p>请联系管理员了解详情</p>
        </div>
      </div>

      <!-- Active — Dashboard -->
      <div v-else-if="agentStatus === 'active' && agent" class="agent-main">
        <div class="agent-header">
          <div class="ah-left">
            <div class="ah-avatar">
{{ (agent.display_name || store.userInfo?.nickname || store.userInfo?.username || 'U').charAt(0).toUpperCase() }}
</div>
            <div class="ah-info">
              <h1>{{ agent.display_name || store.userInfo?.nickname || store.userInfo?.username }} <span v-if="agent.tier_level" class="ah-tier-badge">L{{ agent.tier_level }}</span></h1>
              <span class="ah-sub">推荐码 {{ agent.referral_code }} · {{ statusLabel[agent.status] }}</span>
            </div>
          </div>
        </div>

        <div class="tabs">
          <button
v-for="t in ([['dashboard','概览'],['orders','我的订单'],['commissions','佣金明细'],['withdrawals','提现中心'],['my','我的']] as const)" :key="t[0]"
            class="tab" :class="{ active: activeTab === t[0] }" @click="switchTab(t[0] as any)"
>
{{ t[1] }}
</button>
        </div>

        <!-- Dashboard -->
        <div v-if="activeTab === 'dashboard'" class="tab-content">
          <!-- How to earn -->
          <div class="card guide-card">
            <h3>如何赚钱</h3>
            <div class="guide-steps">
              <div class="guide-step">
                <div class="gs-num">
1
</div>
                <div class="gs-content">
                  <strong>分享推广链接</strong>
                  <p>把你的专属链接发给好友、微信群、QQ群等</p>
                </div>
              </div>
              <div class="guide-step">
                <div class="gs-num">
2
</div>
                <div class="gs-content">
                  <strong>用户注册下单</strong>
                  <p>通过你的链接注册的用户，每次下单你都有佣金</p>
                </div>
              </div>
              <div class="guide-step">
                <div class="gs-num">
3
</div>
                <div class="gs-content">
                  <strong>佣金自动到账</strong>
                  <p>用户付款后佣金自动入账，可随时提现</p>
                </div>
              </div>
            </div>
            <div class="guide-rate-row">
              <div class="gr-item">
                <span class="gr-label">直推佣金</span>
                <span class="gr-val">20%</span>
              </div>
              <div class="gr-divider"></div>
              <div class="gr-item">
                <span class="gr-label">间推佣金</span>
                <span class="gr-val">5%</span>
              </div>
              <div class="gr-divider"></div>
              <div class="gr-item">
                <span class="gr-label">提现门槛</span>
                <span class="gr-val">¥50</span>
              </div>
            </div>
          </div>

          <!-- Referral link -->
          <div class="card link-card">
            <h3>你的推广链接</h3>
            <p class="link-desc">
把这个链接发给别人，通过此链接注册的用户都算你的邀请
</p>
            <div class="link-row">
              <input class="link-input" :value="fullReferralLink" readonly />
              <button class="btn btn-primary btn-sm" @click="copyLink(dashData.referral_link)">
复制链接
</button>
            </div>
            <div v-if="dashData.subsite_link" class="link-row">
              <input class="link-input" :value="fullSubsiteLink" readonly />
              <button class="btn btn-ghost btn-sm" @click="copyLink(dashData.subsite_link)">
复制子站
</button>
            </div>
            <div class="link-tip">
复制后直接粘贴到微信、QQ发送给好友即可
</div>
          </div>

          <!-- Recent commissions -->
          <div v-if="dashData.recent_commissions.length" class="card">
            <h3>最近佣金记录</h3>
            <div class="mini-table">
              <div v-for="c in dashData.recent_commissions" :key="c.commission_id" class="mt-row">
                <span class="mt-id">{{ c.order_id }}</span>
                <span class="mt-level">L{{ c.level }}</span>
                <span class="mt-rate">{{ (c.commission_rate * 100).toFixed(0) }}%</span>
                <span class="mt-amount">{{ fmtMoney(c.commission_amount) }}</span>
                <span class="mt-date">{{ fmtDate(c.created_at) }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Orders Tab -->
        <div v-if="activeTab === 'orders'" class="tab-content">
          <div class="card">
            <div class="card-header">
              <h3>我的订单</h3>
              <span class="ch-count">共 {{ ordersTotal }} 单</span>
            </div>
            <div v-if="loadingOrders" class="empty">
加载中...
</div>
            <div v-else-if="!orders.length" class="empty">
暂无订单记录
</div>
            <div v-else class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr><th>订单编号</th><th>平台</th><th>类型</th><th>金额</th><th>状态</th><th>时间</th></tr>
                </thead>
                <tbody>
                  <tr v-for="o in orders" :key="o.order_id">
                    <td class="mono">
{{ o.order_id.slice(0, 10) }}...
</td>
                    <td>平台#{{ o.website_id }}</td>
                    <td>{{ o.task_type }}</td>
                    <td class="amount-cell">
{{ fmtMoney(o.price) }}
</td>
                    <td><span :class="['status-tag', orderStatusClass[o.status]]">{{ orderStatusLabel[o.status] || o.status }}</span></td>
                    <td class="date-cell">
{{ fmtDate(o.created_at) }}
</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Commissions -->
        <div v-if="activeTab === 'commissions'" class="tab-content">
          <!-- Commission Rate Explanation -->
          <div class="card rate-card">
            <h3>佣金比例说明</h3>
            <p class="rc-desc">
所有代理统一佣金比例，系统自动结算，无需手动操作
</p>
            <div class="rc-grid">
              <div class="rc-row">
                <div class="rc-level l1">
L1
</div>
                <div class="rc-info">
                  <span class="rc-label">直推佣金</span>
                  <span class="rc-sub">你邀请的用户下单</span>
                </div>
                <div class="rc-rate-col">
                  <span class="rc-rate-val">20%</span>
                  <span class="rc-rate-ex">例 ¥12 → 赚 ¥2.40</span>
                </div>
              </div>
              <div class="rc-row">
                <div class="rc-level l2">
L2
</div>
                <div class="rc-info">
                  <span class="rc-label">间推佣金</span>
                  <span class="rc-sub">下级代理的用户下单</span>
                </div>
                <div class="rc-rate-col">
                  <span class="rc-rate-val">5%</span>
                  <span class="rc-rate-ex">例 ¥12 → 赚 ¥0.60</span>
                </div>
              </div>
              <div class="rc-row">
                <div class="rc-level l3">
L3
</div>
                <div class="rc-info">
                  <span class="rc-label">三级权益</span>
                  <span class="rc-sub">最高等级标识与优先支持</span>
                </div>
                <div class="rc-rate-col">
                  <span class="rc-rate-val muted">—</span>
                  <span class="rc-rate-ex">专属客服 · 优先审核</span>
                </div>
              </div>
            </div>
            <div class="rc-tip">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
              <span>佣金在用户付款后自动到账，多邀多赚，上不封顶</span>
            </div>
          </div>

          <div class="card">
            <div class="card-header">
<h3>佣金明细</h3><span class="ch-count">共 {{ commissionsTotal }} 条</span>
</div>
            <div v-if="!commissions.length" class="empty">
暂无佣金记录
</div>
            <div v-else class="table-wrap">
              <table class="data-table">
                <thead><tr><th>订单</th><th>层级</th><th>佣金率</th><th>订单金额</th><th>佣金</th><th>时间</th></tr></thead>
                <tbody>
                  <tr v-for="c in commissions" :key="c.commission_id">
                    <td class="mono">
{{ c.order_id }}
</td>
                    <td><span class="level-badge" :class="'l'+c.level">L{{ c.level }}</span></td>
                    <td>{{ (c.commission_rate * 100).toFixed(1) }}%</td>
                    <td>{{ fmtMoney(c.order_amount) }}</td>
                    <td class="amount-cell">
{{ fmtMoney(c.commission_amount) }}
</td>
                    <td class="date-cell">
{{ fmtDate(c.created_at) }}
</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Withdrawals -->
        <div v-if="activeTab === 'withdrawals'" class="tab-content">
          <div class="card withdraw-card">
            <div class="wc-balance">
              <span class="wc-bal-label">可提现余额</span>
              <span class="wc-bal-val">{{ fmtMoney(agent.available_balance) }}</span>
            </div>
            <div class="wc-amount-section">
              <span class="wc-amount-label">选择提现金额</span>
              <div class="wc-presets">
                <button
                  v-for="p in withdrawPresets"
                  :key="p"
                  class="wc-preset"
                  :class="{ active: selectedAmount === p }"
                  :disabled="agent.available_balance < p"
                  @click="selectedAmount = p"
                >
¥{{ p }}
</button>
              </div>
            </div>
            <button class="btn btn-primary btn-lg btn-block wc-submit" :disabled="withdrawing || !selectedAmount || (withdrawRules && agent.available_balance < withdrawRules.min_amount)" @click="doWithdraw">
              {{ withdrawing ? '处理中...' : (selectedAmount ? `提现 ¥${selectedAmount.toFixed(2)}` : '请选择金额') }}
            </button>
            <div v-if="withdrawRules" class="wc-rules">
              <span class="wc-rule">最低 ¥{{ withdrawRules.min_amount }}</span>
              <span class="wc-rule">今日已提 {{ withdrawRules.today_count }}次</span>
              <span v-if="withdrawRules.max_daily_count > 0" class="wc-rule" :class="{ 'wc-rule-danger': withdrawRules.today_remaining_count <= 0 }">剩余 {{ withdrawRules.today_remaining_count }}次</span>
              <span v-if="withdrawRules.max_daily_amount > 0" class="wc-rule" :class="{ 'wc-rule-danger': withdrawRules.today_remaining_amount <= 0 }">剩余额度 ¥{{ withdrawRules.today_remaining_amount.toFixed(0) }}</span>
              <span v-if="withdrawRules.fee_rate > 0 || withdrawRules.fee_fixed > 0" class="wc-rule">手续费 {{ withdrawRules.fee_rate > 0 ? (withdrawRules.fee_rate * 100).toFixed(0) + '%' : '¥' + withdrawRules.fee_fixed }}</span>
            </div>
          </div>
          <div class="card">
            <div class="card-header">
<h3>提现记录</h3><span class="ch-count">共 {{ withdrawalsTotal }} 条</span>
</div>
            <div v-if="!withdrawals.length" class="empty">
暂无提现记录
</div>
            <div v-else class="table-wrap">
              <table class="data-table">
                <thead><tr><th>ID</th><th>金额</th><th>方式</th><th>状态</th><th>时间</th></tr></thead>
                <tbody>
                  <tr v-for="w in withdrawals" :key="w.withdrawal_id">
                    <td class="mono">
{{ w.withdrawal_id }}
</td>
                    <td class="amount-cell">
{{ fmtMoney(w.amount) }}
</td>
                    <td>{{ w.method === 'balance' ? '转入余额' : w.method }}</td>
                    <td><span class="status-pill" :class="w.status">{{ w.status === 'completed' ? '已完成' : w.status }}</span></td>
                    <td class="date-cell">
{{ fmtDate(w.created_at) }}
</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- My -->
        <div v-if="activeTab === 'my'" class="tab-content">
          <!-- Sub-tabs -->
          <div class="my-subtabs">
            <button :class="['my-subtab', { active: mySection === 'referrals' }]" @click="mySection = 'referrals'">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>
              邀请管理
            </button>
            <button :class="['my-subtab', { active: mySection === 'upgrade' }]" @click="mySection = 'upgrade'; loadUpgradeInfo()">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
              升级代理
            </button>
            <button :class="['my-subtab', { active: mySection === 'settings' }]" @click="mySection = 'settings'; initProfileForm()">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
              个人设置
            </button>
          </div>

          <!-- Section: Referrals -->
          <div v-if="mySection === 'referrals'">
            <div class="card">
              <div class="card-header">
<h3>邀请用户</h3><span class="ch-count">共 {{ referralsTotal }} 人</span>
</div>
              <div v-if="!referrals.length" class="empty">
暂无邀请用户
</div>
              <div v-else class="table-wrap">
                <table class="data-table">
                  <thead><tr><th>用户</th><th>订单数</th><th>消费总额</th><th>注册时间</th></tr></thead>
                  <tbody>
                    <tr v-for="r in referrals" :key="r.user_id">
                      <td>{{ r.nickname || r.username }}</td>
                      <td>{{ r.order_count }}</td>
                      <td class="amount-cell">
{{ fmtMoney(r.total_spent) }}
</td>
                      <td class="date-cell">
{{ fmtDate(r.created_at) }}
</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- Section: Upgrade -->
          <div v-if="mySection === 'upgrade'" class="upgrade-tab">
            <template v-if="upgradeLoading">
              <div class="upgrade-loading-wrap">
                <div class="spinner-lg"></div>
                <p>加载升级方案...</p>
              </div>
            </template>
            <template v-else-if="!upgradeInfo">
              <div class="upgrade-empty-wrap">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6"/><path d="M9 9l6 6"/></svg>
                <p>无法获取升级信息</p>
              </div>
            </template>
            <template v-else-if="!upgradeInfo.upgradable">
              <div class="upgrade-max-card">
                <div class="umc-icon">
                  <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="1.5"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                </div>
                <h2>已达最高等级</h2>
                <p>当前等级 L{{ upgradeInfo.current_tier }}，无需继续升级</p>
                <div class="umc-badge-row">
                  <div class="umc-tier-badge max">
L{{ upgradeInfo.current_tier }}
</div>
                </div>
                <p class="umc-hint">
通过推广和销售业绩累计，系统会自动评估您的等级
</p>
              </div>
            </template>
            <template v-else>
              <!-- Compact tier progress bar -->
              <div class="tier-progress">
                <div v-for="t in [1,2,3]" :key="t" :class="['tp-step', { done: upgradeInfo.current_tier >= t, current: upgradeInfo.current_tier === t }]">
                  <div class="tp-dot">
                    <svg v-if="upgradeInfo.current_tier >= t" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    <span v-else>{{ t }}</span>
                  </div>
                  <span class="tp-label">L{{ t }}</span>
                  <span class="tp-name">{{ ['初级代理','中级代理','高级代理'][t-1] }}</span>
                </div>
                <div class="tp-line">
<div class="tp-fill" :style="{ width: upgradeInfo.current_tier >= 3 ? '100%' : upgradeInfo.current_tier >= 2 ? '50%' : '0%' }"></div>
</div>
              </div>

              <!-- Tier comparison -->
              <div class="tier-compare">
                <div v-for="t in [1,2,3]" :key="t" :class="['tc-item', { active: upgradeInfo.current_tier === t, reached: upgradeInfo.current_tier >= t }]">
                  <div class="tc-head" :class="'l'+t">
L{{ t }}
</div>
                  <div class="tc-info">
                    <span class="tc-rate-label">{{ t === 1 ? '直推佣金' : t === 2 ? '直推 + 间推' : '最高权限' }}</span>
                    <span class="tc-rate-val">{{ t === 1 ? '20%' : '20%+5%' }}</span>
                  </div>
                  <div class="tc-perks">
                    <span v-if="t >= 1">直推佣金</span>
                    <span v-if="t >= 2">间推佣金</span>
                    <span v-if="t >= 3">专属支持</span>
                  </div>
                  <span v-if="upgradeInfo.current_tier === t" class="tc-current-badge">当前</span>
                </div>
              </div>

              <!-- Upgrade options -->
              <div v-if="!upgradeInfo.upgrade_enabled" class="upgrade-locked-wrap">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
                <h3>付费升级暂未开放</h3>
                <p>请通过推广和销售业绩自然升级，或联系站长开通付费升级</p>
              </div>

              <div v-else class="upgrade-list">
                <div v-for="(opt, idx) in upgradeInfo.options" :key="opt.tier" class="upgrade-row" :class="{ recommended: idx === 0 && upgradeInfo.options.length > 1 }">
                  <div class="ur-left">
                    <span v-if="idx === 0 && upgradeInfo.options.length > 1" class="ur-tag">推荐</span>
                    <div class="ur-tier">
                      <span class="ur-from">L{{ upgradeInfo.current_tier }}</span>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                      <span class="ur-to">L{{ opt.tier }}</span>
                    </div>
                    <span class="ur-desc">升级至 L{{ opt.tier }}，享更高佣金</span>
                  </div>
                  <div class="ur-right">
                    <div class="ur-price">
<span class="ur-currency">&#165;</span><span class="ur-fee">{{ opt.fee }}</span>
</div>
                    <div class="ur-btns">
                      <button class="uoc-pay-btn wechat" :disabled="upgradePaying" @click="doRequestUpgrade(opt.tier, 1)">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M8.691 2.188C3.891 2.188 0 5.476 0 9.53c0 2.212 1.17 4.203 3.002 5.55a.59.59 0 01.213.665l-.39 1.48c-.019.07-.048.141-.048.213 0 .163.13.295.29.295a.326.326 0 00.167-.054l1.903-1.114a.864.864 0 01.717-.098 10.16 10.16 0 002.837.403c.276 0 .543-.027.811-.05-.857-2.578.157-4.972 1.932-6.446 1.703-1.415 3.882-1.98 5.853-1.838-.576-3.583-4.196-6.348-8.596-6.348z"/></svg>
                        微信
                      </button>
                      <button class="uoc-pay-btn alipay" :disabled="upgradePaying" @click="doRequestUpgrade(opt.tier, 2)">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M21.422 15.358c-1.456-.326-3.022-.726-4.694-1.202.586-1.402 1.042-2.954 1.352-4.634h-3.82V7.618h4.564V6.13h-4.564V3.136h-2.594s.042.096.042.276v2.718H7.68v1.488h4.152v1.904H7.916v1.488h7.274a14.6 14.6 0 01-.898 2.47c-1.836-.614-3.882-1.04-5.928-1.04-2.44 0-3.886 1.224-3.886 2.834 0 1.862 1.88 2.964 4.142 2.964 2.478 0 4.524-1.158 6.056-3.056a30.8 30.8 0 003.548 1.432l-.372 1.578s2.726-1.054 3.426-1.354l-.15-.818z"/></svg>
                        支付宝
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </div>

          <!-- Section: Settings -->
          <div v-if="mySection === 'settings'" class="settings-grid">
            <div class="card settings-card">
              <h3>代理资料</h3>
              <div class="field">
                <label>显示名称</label>
                <input v-model="profileForm.display_name" placeholder="被邀请用户看到的名称" />
              </div>
              <div class="field">
                <label>微信收款二维码</label>
                <input id="qr-file-input" type="file" accept="image/*" style="display:none" @change="handleQrFile" />
                <div class="qr-upload-area">
                  <div v-if="qrPreview" class="qr-preview-wrap">
                    <img :src="qrPreview" alt="二维码预览" class="qr-preview-img" />
                    <button class="btn btn-ghost btn-sm" :disabled="uploadingQr" @click="triggerQrUpload">
{{ uploadingQr ? '上传中...' : '更换二维码' }}
</button>
                  </div>
                  <div v-else class="qr-upload-placeholder" @click="triggerQrUpload">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    <span>{{ uploadingQr ? '上传中...' : '点击上传二维码图片' }}</span>
                  </div>
                </div>
              </div>
              <div class="field">
                <label>推荐码（不可改）</label>
                <input :value="agent.referral_code" readonly disabled />
              </div>
              <button class="btn btn-primary" :disabled="savingProfile" @click="saveProfile">
{{ savingProfile ? '保存中...' : '保存' }}
</button>
            </div>

            <div class="card settings-card">
              <h3>修改密码</h3>
              <div class="field">
                <label>原密码</label>
                <input v-model="pwForm.old_password" type="password" placeholder="当前密码" autocomplete="current-password" />
              </div>
              <div class="field">
                <label>新密码</label>
                <input v-model="pwForm.new_password" type="password" placeholder="至少6位" autocomplete="new-password" />
              </div>
              <div class="field">
                <label>确认新密码</label>
                <input v-model="pwForm.confirm_password" type="password" placeholder="再次输入" autocomplete="new-password" />
              </div>
              <button class="btn btn-primary" :disabled="changingPw" @click="doChangePassword">
{{ changingPw ? '处理中...' : '修改密码' }}
</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Agent registration payment modal -->
      <div class="modal-overlay" :class="{ show: regShowPay && !regPaid }" @click.self="closeRegPay">
        <div class="modal-box pay-modal">
          <!-- Step 1: Choose payment method -->
          <template v-if="regStep === 'choose'">
            <h3>升级为L1代理</h3>
            <p style="text-align:center;color:var(--c-text-secondary);font-size:14px;margin:12px 0 20px">
选择支付方式
</p>
            <div class="pay-method-btns">
              <button class="pay-method-btn wechat" :disabled="regPaying" @click="apply(1)">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M8.691 2.188C3.891 2.188 0 5.476 0 9.53c0 2.212 1.17 4.203 3.002 5.55a.59.59 0 01.213.665l-.39 1.48c-.019.07-.048.141-.048.213 0 .163.13.295.29.295a.326.326 0 00.167-.054l1.903-1.114a.864.864 0 01.717-.098 10.16 10.16 0 002.837.403c.276 0 .543-.027.811-.05-.857-2.578.157-4.972 1.932-6.446 1.703-1.415 3.882-1.98 5.853-1.838-.576-3.583-4.196-6.348-8.596-6.348z"/></svg>
                <span>微信支付</span>
              </button>
              <button class="pay-method-btn alipay" :disabled="regPaying" @click="apply(2)">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M21.422 15.358c-1.456-.326-3.022-.726-4.694-1.202.586-1.402 1.042-2.954 1.352-4.634h-3.82V7.618h4.564V6.13h-4.564V3.136h-2.594s.042.096.042.276v2.718H7.68v1.488h4.152v1.904H7.916v1.488h7.274a14.6 14.6 0 01-.898 2.47c-1.836-.614-3.882-1.04-5.928-1.04-2.44 0-3.886 1.224-3.886 2.834 0 1.862 1.88 2.964 4.142 2.964 2.478 0 4.524-1.158 6.056-3.056a30.8 30.8 0 003.548 1.432l-.372 1.578s2.726-1.054 3.426-1.354l-.15-.818z"/></svg>
                <span>支付宝支付</span>
              </button>
            </div>
          </template>

          <!-- Step 2: QR code -->
          <template v-else>
            <h3>扫码支付</h3>
            <div class="modal-amount">
&#165;{{ regFee.toFixed(2) }}
</div>
            <p v-if="regQrImage" class="pay-amount-warn">
请务必支付相同金额，多一分少一分都无法检测到
</p>
            <div class="qr-section">
              <img v-if="regQrImage" :src="regQrImage" alt="支付码" class="pay-qr-img" />
              <div v-else class="pay-qr-placeholder">
生成二维码中...
</div>
            </div>
            <p v-if="regQrImage" class="qr-label">
保存二维码后使用微信/支付宝扫一扫支付
</p>
            <button v-if="regQrImage" class="btn btn-primary btn-block pay-link-btn" style="margin-top:6px" @click="saveRegQr">
保存二维码
</button>
            <button class="btn btn-outline btn-block" style="margin-top:8px" @click="checkRegPaid">
我已付款，点击刷新
</button>
          </template>

          <button class="btn btn-ghost btn-block" style="margin-top:10px" @click="closeRegPay">
关闭
</button>
          <PaymentSuccess :visible="showRegPaySuccess" :amount="regFee" subtitle="代理已开通" @done="onRegPaySuccessDone" />
        </div>
      </div>

      <div class="modal-overlay" :class="{ show: upgradeShowPay && !showPaySuccess }" @click.self="closeUpgradePay">
        <div class="modal-box pay-modal">
          <h3>升级支付</h3>
          <div class="modal-amount">
&#165;{{ upgradeFee.toFixed(2) }}
</div>
          <p v-if="upgradeQrImage && !showPaySuccess" class="pay-amount-warn">
请务必支付相同金额，多一分少一分都无法检测到
</p>
          <div class="qr-section">
            <img v-if="upgradeQrImage" :src="upgradeQrImage" alt="支付码" class="pay-qr-img" />
            <div v-else-if="!upgradePaid" class="pay-qr-placeholder">
生成二维码中...
</div>
            <PaymentSuccess :visible="showPaySuccess" :amount="upgradeFee" subtitle="正在升级..." @done="onPaySuccessDone" />
          </div>
          <p v-if="upgradeQrImage && !showPaySuccess" class="qr-label">
保存二维码后使用微信/支付宝扫一扫支付
</p>
          <button v-if="upgradeQrImage && !showPaySuccess" class="btn btn-primary btn-block pay-link-btn" style="margin-top:6px" @click="saveUpgradeQr">
保存二维码
</button>
          <button v-if="!showPaySuccess" class="btn btn-outline btn-block" style="margin-top:8px" @click="checkUpgradePaid">
我已付款，点击刷新
</button>
          <button class="btn btn-ghost btn-block" style="margin-top:10px" @click="closeUpgradePay">
关闭
</button>
        </div>
      </div>
    </div>

    <footer class="page-footer">
      <span>FUCK 文理网课 · 代理推广中心</span>
    </footer>
  </div>
</template>

<style scoped>
.page { min-height: 100vh; display: flex; flex-direction: column; }
.content-wrapper { flex: 1; max-width: 960px; width: 100%; margin: 0 auto; padding: 0 24px; }

.loading-area { text-align: center; padding: 80px 0; }
.spinner-lg { width: 36px; height: 36px; border: 2.5px solid var(--c-border); border-top-color: var(--c-primary); border-radius: 50%; animation: spin .65s linear infinite; margin: 0 auto 12px; }
.loading-area p { color: var(--c-text-secondary); font-size: 14px; }

.btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 9px 20px; border: none; border-radius: var(--radius-sm); font-weight: 600; font-size: 13.5px; cursor: pointer; transition: all .15s; white-space: nowrap; }
.btn-primary { background: var(--c-primary); color: #fff; box-shadow: 0 2px 8px rgba(79,110,247,.25); }
.btn-primary:hover { background: var(--c-primary-hover); transform: translateY(-1px); }
.btn-primary:disabled { opacity: .55; cursor: not-allowed; transform: none; }
.btn-ghost { background: transparent; color: var(--c-text-secondary); padding: 6px 12px; }
.btn-ghost:hover { color: var(--c-primary); background: var(--c-primary-bg); }
.btn-lg { padding: 12px 28px; font-size: 15px; }
.btn-block { width: 100%; }
.btn-sm { padding: 6px 14px; font-size: 12px; }

/* Auth inside apply card */
.auth-section { margin-top: 0; text-align: center; }
.auth-section-icon { margin-bottom: 8px; }
.auth-section h3 { font-size: 18px; font-weight: 700; margin-bottom: 16px; color: var(--c-text); }
.auth-hint { font-size: 13px; color: var(--c-text-muted); margin-top: 10px; }
.auth-hint a { color: var(--c-primary); font-weight: 500; text-decoration: none; }
.auth-hint a:hover { text-decoration: underline; }
.auth-tabs-compact { display: flex; border-radius: var(--radius-sm); background: var(--c-bg); padding: 3px; margin-bottom: 16px; }
.auth-tabs-compact button {
  flex: 1; padding: 8px 14px; border-radius: var(--radius-sm); border: none;
  background: transparent; font-size: 13px; font-weight: 500; color: var(--c-text-secondary);
  cursor: pointer; transition: all .15s;
}
.auth-tabs-compact button.active { background: #fff; color: var(--c-primary); font-weight: 600; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.auth-form-compact { text-align: left; }
.auth-form-compact .field { margin-bottom: 12px; }
.auth-form-compact input { height: 42px; }
.captcha-row { display: flex; gap: 8px; align-items: stretch; margin-bottom: 12px; }
.captcha-row input { flex: 1; min-width: 0; height: 42px; padding: 0 14px; border: 1px solid var(--c-border); border-radius: var(--radius-sm); background: var(--c-bg); color: var(--c-text); font-size: 14px; outline: none; }
.captcha-row input:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px rgba(79,110,247,.12); background: var(--c-surface); }
.captcha-img { height: 42px; cursor: pointer; border-radius: 6px; border: 1px solid var(--c-border); flex-shrink: 0; }
.captcha-placeholder {
  flex-shrink: 0; height: 42px; padding: 0 12px; display: flex; align-items: center;
  background: var(--c-bg); border: 1px dashed var(--c-border); border-radius: 6px;
  font-size: 12px; color: var(--c-text-muted); cursor: pointer; white-space: nowrap;
}
.btn-block { width: 100%; }
.ref-banner {
  background: var(--c-primary-bg); border: 1px solid rgba(79,110,247,.2);
  border-radius: var(--radius-sm); padding: 10px 14px; margin-bottom: 16px;
  font-size: 12.5px; color: var(--c-primary); text-align: center; font-weight: 500;
}
.ref-banner code { font-family: 'SF Mono', monospace; background: rgba(79,110,247,.1); padding: 1px 6px; border-radius: 3px; font-weight: 700; }

/* Apply / Status Centers */
.apply-center, .status-center { display: flex; justify-content: center; padding: 60px 0; }
.apply-card, .status-card {
  background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: var(--radius-xl); padding: 48px; max-width: 480px; width: 100%;
  text-align: center; box-shadow: var(--shadow);
}
.apply-icon, .status-icon { margin-bottom: 20px; }
.apply-card h2, .status-card h2 { font-size: 22px; font-weight: 700; margin-bottom: 8px; }
.apply-card p, .status-card p { font-size: 14px; color: var(--c-text-secondary); margin-bottom: 24px; }
.apply-features { display: flex; flex-direction: column; gap: 10px; margin-bottom: 28px; }
.af { display: flex; align-items: center; gap: 10px; font-size: 13.5px; color: var(--c-text); justify-content: center; }
.af-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--c-primary); flex-shrink: 0; }
.apply-loading { text-align: center; padding: 30px 0; }
.apply-loading .spinner-lg { margin: 0 auto 16px; }
.apply-loading p { font-size: 14px; color: var(--c-text-secondary); }
.apply-error {
  background: var(--c-danger-bg); border: 1px solid rgba(239,68,68,.2);
  color: var(--c-danger); padding: 10px 16px; border-radius: var(--radius-sm);
  font-size: 13px; margin-bottom: 16px;
}
.apply-pay-btns { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-top: 8px; }
.pay-title { font-size: 18px; font-weight: 700; text-align: center; margin-bottom: 4px; }
.pay-amount { font-size: 36px; font-weight: 800; color: var(--c-primary); margin: 12px 0 4px; text-align: center; }
.pay-desc { text-align: center; color: var(--c-text-secondary); font-size: 13px; margin-bottom: 16px; }
.pay-amount-warn { text-align: center; font-size: 12px; color: #ef4444; margin-bottom: 8px; }
.pay-method-btns { display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; margin-top: 8px; }
.pay-method-btn {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 20px 32px; border: 2px solid #e2e8f0; border-radius: 12px;
  background: #fff; cursor: pointer; transition: all .2s;
  font-size: 14px; font-weight: 600; min-width: 130px;
}
.pay-method-btn:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.1); }
.pay-method-btn:disabled { opacity: .5; cursor: not-allowed; transform: none; }
.pay-method-btn.wechat { color: #07c160; border-color: #07c160; }
.pay-method-btn.wechat:hover:not(:disabled) { background: #f0fdf4; }
.pay-method-btn.alipay { color: #1677ff; border-color: #1677ff; }
.pay-method-btn.alipay:hover:not(:disabled) { background: #f0f7ff; }
.qr-hint { text-align: center; font-size: 13px; color: var(--c-text-secondary); margin-top: 8px; }
.pay-link-btn { text-align: center; display: block; }
.status-code { font-size: 14px; color: var(--c-text-secondary); }
.status-code code { font-family: 'SF Mono', monospace; background: var(--c-bg); padding: 4px 10px; border-radius: 4px; font-size: 13px; color: var(--c-primary); font-weight: 600; }

/* Main */
.agent-main { padding: 24px 0 40px; }
.agent-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }
.ah-left { display: flex; align-items: center; gap: 16px; }
.ah-avatar {
  width: 52px; height: 52px; border-radius: 50%; background: var(--c-primary);
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 20px; font-weight: 700; flex-shrink: 0;
}
.ah-info { display: flex; flex-direction: column; gap: 2px; }
.ah-info h1 { font-size: 20px; font-weight: 700; }
.ah-sub { font-size: 12.5px; color: var(--c-text-muted); }
.ah-tier-badge {
  display: inline-block; font-size: 11px; font-weight: 700; color: #fff;
  background: linear-gradient(135deg, var(--c-primary), #6366f1);
  padding: 1px 8px; border-radius: 10px; vertical-align: middle; margin-left: 6px;
}

.tabs { display: flex; gap: 4px; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--radius); padding: 4px; margin-bottom: 20px; overflow-x: auto; }
.tab { padding: 8px 16px; font-size: 13px; font-weight: 500; color: var(--c-text-secondary); background: none; border: none; border-radius: 8px; cursor: pointer; white-space: nowrap; transition: all .15s; }
.tab:hover { color: var(--c-primary); background: var(--c-primary-bg); }
.tab.active { color: var(--c-primary); background: var(--c-primary-bg); font-weight: 600; box-shadow: var(--shadow-xs); }
.tab-content { animation: fadeIn .25s ease; display: flex; flex-direction: column; gap: 16px; }

.my-subtabs { display: flex; gap: 4px; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--radius); padding: 4px; margin-bottom: 16px; }
.my-subtab { flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px; padding: 10px 12px; font-size: 13px; font-weight: 500; color: var(--c-text-secondary); background: none; border: none; border-radius: 8px; cursor: pointer; transition: all .15s; }
.my-subtab:hover { color: var(--c-primary); background: var(--c-primary-light); }
.my-subtab.active { color: var(--c-primary); background: var(--c-primary-light); font-weight: 600; box-shadow: var(--shadow-xs); }

.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
.stat-card {
  background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: var(--radius); padding: 20px 18px; box-shadow: var(--shadow-xs);
  display: flex; flex-direction: column; gap: 6px;
}
.sc-icon { width: 34px; height: 34px; border-radius: 8px; display: flex; align-items: center; justify-content: center; }
.sc-icon.money { background: #fef2f2; color: #ef4444; }
.sc-icon.ok { background: #f0fdf4; color: #22c55e; }
.sc-icon.out { background: #f0f9ff; color: #0ea5e9; }
.sc-icon.ppl { background: #eef1fe; color: #4f6ef7; }
.sc-label { font-size: 12px; color: var(--c-text-muted); }
.sc-value { font-size: 24px; font-weight: 700; color: var(--c-text); }
.sc-value.success { color: var(--c-success); }
.sc-value.info { color: var(--c-info); }

.card { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--radius); padding: 22px; margin-bottom: 16px; box-shadow: var(--shadow-xs); }
.card h3 { font-size: 15px; font-weight: 600; margin-bottom: 14px; }
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.card-header h3 { margin-bottom: 0; }
.ch-count { font-size: 12px; color: var(--c-text-muted); }

.link-row { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
.link-row:first-child { margin-top: 0; }
.link-input { flex: 1; height: 38px; padding: 0 12px; border: 1px solid var(--c-border); border-radius: var(--radius-sm); background: var(--c-bg); font-size: 13px; color: var(--c-text); }

.guide-card { border-left: 3px solid var(--c-primary); }
.guide-card h3 { color: var(--c-primary); }
.guide-steps { display: flex; flex-direction: column; gap: 16px; }
.guide-step { display: flex; gap: 14px; align-items: flex-start; }
.gs-num {
  width: 28px; height: 28px; border-radius: 50%; background: var(--c-primary); color: #fff;
  display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 700; flex-shrink: 0;
}
.gs-content strong { font-size: 14px; color: var(--c-text); display: block; margin-bottom: 2px; }
.gs-content p { font-size: 13px; color: var(--c-text-secondary); margin: 0; line-height: 1.5; }
.guide-rate-row {
  display: flex; align-items: center; justify-content: center; gap: 0;
  margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--c-border);
}
.gr-item { display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1; }
.gr-label { font-size: 12px; color: var(--c-text-muted); }
.gr-val { font-size: 20px; font-weight: 800; color: var(--c-primary); }
.gr-divider { width: 1px; height: 32px; background: var(--c-border); flex-shrink: 0; }
.link-desc { font-size: 13px; color: var(--c-text-secondary); margin: 0 0 10px; }
.link-tip { font-size: 12px; color: var(--c-text-muted); margin-top: 8px; }

/* Commission Rate Card */
.rate-card h3 { margin-bottom: 4px; }
.rc-desc { font-size: 13px; color: var(--c-text-secondary); margin: 0 0 16px; }
.rc-grid { display: flex; flex-direction: column; gap: 10px; margin-bottom: 14px; }
.rc-row {
  display: flex; align-items: center; gap: 14px; padding: 14px 16px;
  background: var(--c-bg); border-radius: var(--radius); border: 1px solid var(--c-border);
  transition: all .15s;
}
.rc-row:hover { border-color: var(--c-primary); background: rgba(79,110,247,.03); }
.rc-level {
  width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 800; color: #fff; flex-shrink: 0;
}
.rc-level.l1 { background: linear-gradient(135deg, #4f6ef7, #6366f1); }
.rc-level.l2 { background: linear-gradient(135deg, #f59e0b, #f97316); }
.rc-level.l3 { background: linear-gradient(135deg, #8b5cf6, #a855f7); }
.rc-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.rc-label { font-size: 14px; font-weight: 600; color: var(--c-text); }
.rc-sub { font-size: 12px; color: var(--c-text-muted); }
.rc-rate-col { text-align: right; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.rc-rate-val { font-size: 22px; font-weight: 800; color: var(--c-primary); line-height: 1; }
.rc-rate-val.muted { color: var(--c-text-muted); font-size: 18px; }
.rc-rate-ex { font-size: 11px; color: var(--c-text-muted); }
.rc-tip { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--c-text-muted); background: #fffbeb; padding: 10px 14px; border-radius: 8px; border: 1px solid #fef3c7; }
.rc-tip svg { stroke: #f59e0b; flex-shrink: 0; }

.mini-table { display: flex; flex-direction: column; }
.mt-row { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-top: 1px solid #f3f4f6; font-size: 12.5px; }
.mt-row:first-child { border-top: none; }
.mt-id, .mono { font-family: 'SF Mono', monospace; font-size: 11px; color: var(--c-text-muted); }
.mt-level { font-size: 10px; padding: 1px 6px; border-radius: 8px; background: var(--c-info-bg); color: var(--c-info); font-weight: 600; }
.mt-rate { font-size: 11px; color: var(--c-text-muted); }
.mt-amount { font-weight: 600; color: var(--c-primary); margin-left: auto; }
.mt-date { font-size: 11px; color: var(--c-text-muted); }

.table-wrap { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th { text-align: left; padding: 10px 12px; font-size: 11.5px; font-weight: 600; color: var(--c-text-muted); text-transform: uppercase; letter-spacing: .03em; border-bottom: 1px solid var(--c-border); }
.data-table td { padding: 10px 12px; border-bottom: 1px solid #f3f4f6; color: var(--c-text); }
.amount-cell { font-weight: 600; color: var(--c-primary); }
.date-cell { font-size: 12px; color: var(--c-text-muted); }

.level-badge { padding: 1px 6px; border-radius: 8px; font-size: 10px; font-weight: 600; }
.level-badge.l1 { background: var(--c-primary-bg); color: var(--c-primary); }
.level-badge.l2 { background: #f5f3ff; color: #8b5cf6; }

.status-pill { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.status-pill.completed { background: var(--c-success-bg); color: var(--c-success); }
.status-pill.pending { background: var(--c-warning-bg); color: var(--c-warning); }

.status-tag { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11.5px; font-weight: 600; }
.status-tag.ok { background: var(--c-success-bg); color: var(--c-success); }
.status-tag.warn { background: var(--c-warning-bg); color: var(--c-warning); }
.status-tag.bad { background: var(--c-danger-bg); color: var(--c-danger); }
.status-tag.primary { background: var(--c-primary-bg); color: var(--c-primary); }
.status-tag.muted { background: var(--c-bg); color: var(--c-text-muted); }

.empty { text-align: center; padding: 40px; color: var(--c-text-muted); font-size: 13px; }

.withdraw-card { text-align: center; }
.wc-balance { margin-bottom: 20px; }
.wc-bal-label { display: block; font-size: 13px; color: var(--c-text-muted); margin-bottom: 4px; }
.wc-bal-val { font-size: 40px; font-weight: 800; color: var(--c-success); line-height: 1.1; }
.wc-amount-section { margin-bottom: 16px; }
.wc-amount-label { display: block; font-size: 13px; color: var(--c-text-muted); margin-bottom: 10px; }
.wc-presets { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }
.wc-preset {
  height: 44px; min-width: 80px; padding: 0 20px; border: 2px solid var(--c-border);
  border-radius: var(--radius); background: var(--c-surface); color: var(--c-text);
  font-size: 16px; font-weight: 700; cursor: pointer; transition: all .15s;
}
.wc-preset:hover:not(:disabled) { border-color: var(--c-primary); background: var(--c-primary-bg); }
.wc-preset.active { border-color: var(--c-primary); background: var(--c-primary); color: #fff; box-shadow: 0 2px 8px rgba(79,110,247,.3); }
.wc-preset:disabled { opacity: .3; cursor: not-allowed; }
.wc-submit { margin-bottom: 16px; }
.wc-rules { display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; padding-top: 14px; border-top: 1px solid var(--c-border); }
.wc-rule { font-size: 12px; color: var(--c-text-muted); background: var(--c-bg); padding: 4px 10px; border-radius: 6px; }
.wc-rule-danger { color: var(--c-danger); background: rgba(239,68,68,.08); }

.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.settings-card { max-width: 100%; }
.field { display: flex; flex-direction: column; gap: 5px; margin-bottom: 16px; }
.field label { font-size: 13px; font-weight: 500; }
.field input, .field textarea { padding: 10px 14px; border: 1px solid var(--c-border); border-radius: var(--radius-sm); background: var(--c-bg); color: var(--c-text); font-size: 14px; outline: none; transition: border-color .15s; font-family: inherit; }
.field input:focus, .field textarea:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px rgba(79,110,247,.12); background: var(--c-surface); }
.field input:disabled { opacity: .6; }
.field-hint { font-size: 11px; color: var(--c-text-muted); margin-top: 2px; }

.qr-upload-area { margin-top: 4px; }
.qr-preview-wrap { display: flex; flex-direction: column; align-items: center; gap: 12px; }
.qr-preview-img { width: 180px; height: 180px; border-radius: 10px; border: 1px solid var(--c-border); object-fit: contain; background: #fff; }
.qr-upload-placeholder {
  width: 180px; height: 180px; border: 2px dashed var(--c-border); border-radius: 10px;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px;
  cursor: pointer; transition: all .15s; color: var(--c-text-muted); font-size: 13px;
}
.qr-upload-placeholder:hover { border-color: var(--c-primary); color: var(--c-primary); background: var(--c-primary-bg); }

.page-footer { text-align: center; padding: 24px; font-size: 12px; color: var(--c-text-muted); border-top: 1px solid var(--c-border); margin-top: auto; }

@media (max-width: 768px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .stat-card { padding: 14px 12px; }
  .stat-val { font-size: 20px; }
  .stat-label { font-size: 11px; }

  .tabs { gap: 0; overflow-x: auto; -webkit-overflow-scrolling: touch; padding-bottom: 2px; }
  .tab { padding: 6px 12px; font-size: 12px; white-space: nowrap; }

  .rc-row { flex-wrap: wrap; gap: 10px; padding: 10px 12px; }
  .rc-rate-col { text-align: left; flex-direction: row; gap: 6px; align-items: baseline; }
  .rc-rate-val { font-size: 18px; }

  .mini-table { font-size: 12px; }
  .mt-row { gap: 8px; font-size: 11.5px; flex-wrap: wrap; }
  .mt-date { width: 100%; }

  .table-wrap { margin: 0 -12px; padding: 0 12px; }
  .data-table { font-size: 12px; }
  .data-table th, .data-table td { padding: 8px 8px; font-size: 11px; }

  .wc-bal-val { font-size: 32px; }
  .wc-preset { min-width: 64px; padding: 0 14px; font-size: 14px; height: 40px; }
  .wc-rules { gap: 6px; }
  .wc-rule { font-size: 11px; padding: 3px 8px; }

  .tier-compare { grid-template-columns: 1fr; }
  .tc-item { padding: 12px; }

  .tier-progress { padding: 0 8px; }
  .tp-dot { width: 28px; height: 28px; font-size: 11px; }
  .tp-label { font-size: 11px; }
  .tp-name { font-size: 10px; }

  .upgrade-row { flex-direction: column; align-items: flex-start; padding: 14px 16px; }
  .ur-right { width: 100%; justify-content: space-between; }
  .ur-price { font-size: 22px; }

  .settings-grid { grid-template-columns: 1fr; }
  .uoc-actions { flex-direction: column; }
  .uoc-actions .btn { width: 100%; }

  .page-footer { padding: 16px; }
}

/* Upgrade - Card Layout */
.upgrade-tab { gap: 20px; }
.upgrade-loading-wrap { text-align: center; padding: 60px 0; }
.upgrade-loading-wrap p { color: var(--c-text-muted); font-size: 14px; margin-top: 12px; }
.upgrade-empty-wrap { text-align: center; padding: 60px 0; }
.upgrade-empty-wrap p { color: var(--c-text-muted); font-size: 14px; margin-top: 12px; }

.upgrade-max-card {
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--radius-xl);
  padding: 48px 32px; text-align: center; box-shadow: var(--shadow);
}
.umc-icon { margin-bottom: 16px; }
.upgrade-max-card h2 { font-size: 22px; font-weight: 700; color: var(--c-success); margin: 0 0 8px; }
.upgrade-max-card > p { font-size: 14px; color: var(--c-text-secondary); margin: 0; }
.umc-badge-row { display: flex; justify-content: center; margin: 20px 0; }
.umc-tier-badge {
  width: 64px; height: 64px; border-radius: 16px; background: var(--c-primary);
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 24px; font-weight: 800; box-shadow: 0 4px 16px rgba(79,110,247,.3);
}
.umc-tier-badge.max { background: linear-gradient(135deg, #22c55e, #16a34a); box-shadow: 0 4px 16px rgba(34,197,94,.3); }
.umc-hint { font-size: 12px; color: var(--c-text-muted); margin-top: 8px; }

/* Tier Progress Bar */
.tier-progress { position: relative; display: flex; justify-content: space-between; align-items: center; padding: 0 24px; margin-bottom: 20px; }
.tp-line { position: absolute; top: 16px; left: 60px; right: 60px; height: 3px; background: var(--c-border); border-radius: 2px; z-index: 0; }
.tp-fill { height: 100%; background: var(--c-primary); border-radius: 2px; transition: width .4s ease; }
.tp-step { display: flex; flex-direction: column; align-items: center; gap: 6px; z-index: 1; position: relative; }
.tp-dot {
  width: 32px; height: 32px; border-radius: 50%; background: var(--c-surface); border: 2px solid var(--c-border);
  display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; color: var(--c-text-muted);
  transition: all .2s;
}
.tp-step.done .tp-dot { background: var(--c-primary); border-color: var(--c-primary); color: #fff; }
.tp-step.current .tp-dot { box-shadow: 0 0 0 4px rgba(79,110,247,.2); }
.tp-label { font-size: 13px; font-weight: 700; color: var(--c-text-muted); }
.tp-step.done .tp-label { color: var(--c-primary); }
.tp-step.current .tp-label { color: var(--c-primary); }
.tp-name { font-size: 11px; color: var(--c-text-muted); }

/* Tier Comparison */
.tier-compare { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 20px; }
.tc-item {
  background: var(--c-surface); border: 1.5px solid var(--c-border); border-radius: 12px;
  padding: 16px; position: relative; transition: all .2s;
}
.tc-item.active { border-color: var(--c-primary); box-shadow: 0 0 0 2px rgba(79,110,247,.12); }
.tc-item.reached { background: linear-gradient(180deg, rgba(79,110,247,.03) 0%, var(--c-surface) 100%); }
.tc-head {
  display: inline-flex; padding: 3px 10px; border-radius: 6px; font-size: 13px; font-weight: 800; color: #fff;
  margin-bottom: 10px;
}
.tc-head.l1 { background: linear-gradient(135deg, #4f6ef7, #6366f1); }
.tc-head.l2 { background: linear-gradient(135deg, #f59e0b, #f97316); }
.tc-head.l3 { background: linear-gradient(135deg, #8b5cf6, #a855f7); }
.tc-info { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 8px; }
.tc-rate-label { font-size: 12px; color: var(--c-text-muted); }
.tc-rate-val { font-size: 16px; font-weight: 800; color: var(--c-primary); }
.tc-perks { display: flex; flex-wrap: wrap; gap: 4px; }
.tc-perks span { font-size: 11px; color: var(--c-text-secondary); background: var(--c-bg); padding: 2px 8px; border-radius: 6px; }
.tc-item.reached .tc-perks span { background: rgba(79,110,247,.08); color: var(--c-primary); }
.tc-current-badge {
  position: absolute; top: 10px; right: 10px; font-size: 10px; font-weight: 700;
  color: var(--c-primary); background: var(--c-primary-bg); padding: 2px 8px; border-radius: 10px;
}

/* Upgrade List */
.upgrade-list { display: flex; flex-direction: column; gap: 12px; }
.upgrade-row {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  background: var(--c-surface); border: 1.5px solid var(--c-border); border-radius: var(--radius-lg);
  padding: 18px 22px; transition: all .2s; flex-wrap: wrap;
}
.upgrade-row:hover { border-color: var(--c-primary); box-shadow: 0 2px 12px rgba(79,110,247,.1); }
.upgrade-row.recommended { border-color: var(--c-primary); }
.ur-left { display: flex; align-items: center; gap: 14px; flex: 1; min-width: 0; position: relative; }
.ur-tag {
  position: absolute; top: -26px; left: 0; font-size: 10px; font-weight: 700;
  color: #fff; background: linear-gradient(135deg, var(--c-primary), #6366f1);
  padding: 2px 8px; border-radius: 10px;
}
.ur-tier { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.ur-from {
  width: 34px; height: 34px; border-radius: 8px; background: var(--c-bg);
  color: var(--c-text-muted); display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; border: 1px solid var(--c-border);
}
.ur-tier svg { color: var(--c-text-muted); flex-shrink: 0; }
.ur-to {
  width: 34px; height: 34px; border-radius: 8px; background: var(--c-primary);
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 800;
}
.ur-desc { font-size: 13px; color: var(--c-text-secondary); }
.ur-right { display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
.ur-price { display: flex; align-items: baseline; gap: 2px; }
.ur-currency { font-size: 14px; font-weight: 700; color: var(--c-danger); }
.ur-fee { font-size: 28px; font-weight: 800; color: var(--c-danger); line-height: 1; }
.ur-btns { display: flex; gap: 8px; }

.upgrade-locked-wrap {
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--radius);
  padding: 40px 32px; text-align: center; box-shadow: var(--shadow-xs);
}
.upgrade-locked-wrap h3 { font-size: 16px; font-weight: 600; color: var(--c-text); margin: 12px 0 6px; }
.upgrade-locked-wrap p { font-size: 13px; color: var(--c-text-muted); margin: 0; }

.uoc-pay-btn {
  flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  padding: 10px 14px; border: none; border-radius: var(--radius-sm);
  font-size: 13px; font-weight: 600; cursor: pointer; transition: all .15s;
}
.uoc-pay-btn:disabled { opacity: .5; cursor: not-allowed; transform: none; }
.uoc-pay-btn.wechat { background: #07c160; color: #fff; }
.uoc-pay-btn.wechat:hover:not(:disabled) { background: #06ad56; transform: translateY(-1px); }
.uoc-pay-btn.alipay { background: #1677ff; color: #fff; }
.uoc-pay-btn.alipay:hover:not(:disabled) { background: #0f6ae5; transform: translateY(-1px); }

/* Payment Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(15,23,42,.4); backdrop-filter: blur(4px); display: none; align-items: center; justify-content: center; z-index: 500; }
.modal-overlay.show { display: flex; }
.modal-box { background: var(--c-surface); border-radius: 14px; padding: 32px; width: 400px; max-width: 90vw; text-align: center; box-shadow: var(--shadow-lg); }
.modal-box h3 { font-size: 18px; font-weight: 700; }
.modal-amount { font-size: 36px; font-weight: 800; color: var(--c-primary); margin: 12px 0 4px; }
.pay-amount-warn { font-size: 12px; color: #ef4444; margin: 0 0 16px; font-weight: 500; }
.qr-section { margin: 16px 0; }
.pay-qr-img { width: 200px; height: 200px; border-radius: 10px; border: 1px solid var(--c-border); object-fit: contain; }
.pay-qr-placeholder { width: 200px; height: 200px; margin: 0 auto; border-radius: 10px; border: 1px dashed var(--c-border); display: flex; align-items: center; justify-content: center; color: var(--c-text-muted); font-size: 13px; }
.qr-label { font-size: 12px; color: var(--c-text-muted); margin-top: 8px; }
.pay-link-btn { margin-top: 10px; }
.upgrade-paid-box { padding: 30px 0; }
.upgrade-paid-box svg { margin-bottom: 12px; }
.upgrade-paid-box p { font-size: 15px; font-weight: 600; color: #16a34a; }
</style>

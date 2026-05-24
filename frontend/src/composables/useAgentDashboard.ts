import { ref, reactive, type Ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { api, type AgentProfile, type CommissionItem, type ReferralItem, type WithdrawalItem } from '@/api'

export function useAgentDashboard(_agent: Ref<AgentProfile | null>) {
  const store = useAppStore()

  const activeTab = ref<'dashboard' | 'orders' | 'commissions' | 'withdrawals' | 'my'>('dashboard')
  const mySection = ref<'referrals' | 'upgrade' | 'settings'>('referrals')

  const dashboard = reactive({
    earnings: { total_commission_amount: 0, pending_commission_amount: 0, this_month_amount: 0, today_amount: 0 },
    referral_count: 0,
    referral_link: '',
    subsite_link: '',
    recent_commissions: [] as CommissionItem[],
    recent_referrals: [] as ReferralItem[],
    recent_withdrawals: [] as WithdrawalItem[],
  })

  const upgradeInfo = ref<any>(null)
  const upgradeLoading = ref(false)
  const upgradeShowPay = ref(false)
  const upgradeQrImage = ref<string | null>(null)
  const upgradeFee = ref(0)
  const upgradeTargetTier = ref(0)
  const upgradePayId = ref('')
  const upgradePollInterval = ref<any>(null)
  const upgradePaying = ref(false)
  const upgradePaid = ref(false)
  const showPaySuccess = ref(false)

  async function loadDashboard() {
    try {
      const res = await api.agents.dashboard()
      const d = res.data
      Object.assign(dashboard.earnings, d.earnings)
      dashboard.referral_count = d.referral_count
      dashboard.referral_link = d.referral_link
      dashboard.subsite_link = d.subsite_link
      dashboard.recent_commissions = d.recent_commissions || []
      dashboard.recent_referrals = d.recent_referrals || []
      dashboard.recent_withdrawals = d.recent_withdrawals || []
    } catch {}
  }

  async function switchTab(
    tab: typeof activeTab.value,
    callbacks: {
      loadOrders: () => Promise<void>
      loadCommissions: () => Promise<void>
      loadWithdrawals: () => Promise<void>
      loadWithdrawRules: () => Promise<void>
      loadReferrals: () => Promise<void>
      loadUpgradeInfo: () => Promise<void>
      initProfileForm: () => void
      commissionsLoaded: () => boolean
      withdrawalsLoaded: () => boolean
      referralsLoaded: () => boolean
    }
  ) {
    activeTab.value = tab
    if (tab === 'dashboard') await loadDashboard()
    if (tab === 'orders') await callbacks.loadOrders()
    if (tab === 'commissions' && !callbacks.commissionsLoaded()) await callbacks.loadCommissions()
    if (tab === 'withdrawals') { if (!callbacks.withdrawalsLoaded()) await callbacks.loadWithdrawals(); await callbacks.loadWithdrawRules() }
    if (tab === 'my') { if (!callbacks.referralsLoaded()) await callbacks.loadReferrals(); callbacks.loadUpgradeInfo(); callbacks.initProfileForm() }
  }

  async function loadUpgradeInfo() {
    upgradeLoading.value = true
    try {
      const res = await api.agents.upgradeInfo()
      upgradeInfo.value = res.data
    } catch (e: any) { store.toast(e.message || '加载升级信息失败', 'error') }
    finally { upgradeLoading.value = false }
  }

  async function doRequestUpgrade(tier: number, payType: number) {
    upgradePaying.value = true
    try {
      const res = await api.agents.requestUpgrade({ target_tier: tier, pay_type: payType })
      const d = res.data
      upgradeQrImage.value = d.qr_image
      upgradeFee.value = d.fee
      upgradeTargetTier.value = d.target_tier
      upgradePayId.value = d.pay_id
      upgradeShowPay.value = true
      startUpgradePoll()
    } catch (e: any) { store.toast(e.message || '创建支付失败', 'error') }
    finally { upgradePaying.value = false }
  }

  async function checkUpgradePaid() {
    try {
      const r = await api.payment.check(upgradePayId.value, '', '')
      const d = r?.data || r as any
      if (d?.expired) { closeUpgradePay(); store.toast('支付已过期', 'warning'); return true }
      if (d?.paid) {
        if (upgradePollInterval.value) { clearTimeout(upgradePollInterval.value); upgradePollInterval.value = null }
        upgradeQrImage.value = null
        upgradePaid.value = true
        showPaySuccess.value = true
        return true
      }
    } catch {}
    return false
  }

  function startUpgradePoll() {
    if (upgradePollInterval.value) { clearTimeout(upgradePollInterval.value); upgradePollInterval.value = null }
    let failCount = 0; let elapsed = 0; let stopped = false
    const fastMs = 2000; const slowMs = 3000; const fastPhase = 30
    async function tick() {
      if (stopped) return
      elapsed += 1
      try {
        const r = await api.payment.check(upgradePayId.value, '', '')
        failCount = 0
        const d = r?.data || r as any
        if (d?.expired) { stopped = true; closeUpgradePay(); store.toast('支付已过期', 'warning'); return }
        if (d?.paid) {
          stopped = true
          if (upgradePollInterval.value) { clearTimeout(upgradePollInterval.value); upgradePollInterval.value = null }
          upgradeQrImage.value = null
          upgradePaid.value = true
          showPaySuccess.value = true
          return
        }
      } catch {
        failCount++
        if (failCount >= 5) { stopped = true; closeUpgradePay(); store.toast('网络异常，请刷新页面查看结果', 'warning'); return }
      }
      if (!stopped) {
        const delay = elapsed >= fastPhase ? slowMs : fastMs
        upgradePollInterval.value = setTimeout(tick, delay)
      }
    }
    upgradePollInterval.value = setTimeout(tick, fastMs)
  }

  function closeUpgradePay() {
    upgradeShowPay.value = false
    showPaySuccess.value = false
    if (upgradePollInterval.value) { clearTimeout(upgradePollInterval.value); upgradePollInterval.value = null }
  }

  function saveUpgradeQr() {
    const src = upgradeQrImage.value
    if (!src) return
    const a = document.createElement('a')
    a.href = src
    a.download = 'pay-qr.png'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  function onPaySuccessDone() {
    closeUpgradePay()
    store.toast('升级成功！', 'success')
    window.location.reload()
  }

  return {
    activeTab, mySection, dashboard,
    upgradeInfo, upgradeLoading, upgradeShowPay, upgradeQrImage, upgradeFee,
    upgradeTargetTier, upgradePayId, upgradePollInterval, upgradePaying, upgradePaid, showPaySuccess,
    loadDashboard, switchTab,
    loadUpgradeInfo, doRequestUpgrade, checkUpgradePaid, startUpgradePoll,
    closeUpgradePay, saveUpgradeQr, onPaySuccessDone,
  }
}

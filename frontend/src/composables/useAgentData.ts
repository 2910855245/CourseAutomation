import { ref, reactive, type Ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { api, getUserApiToken, type AgentProfile, type CommissionItem, type ReferralItem, type WithdrawalItem, type OrderItem } from '@/api'
import { useConfirmSingleton } from '@/composables/useConfirm'

export function useAgentData(agent: Ref<AgentProfile | null>, loadDashboard: () => Promise<void>) {
  const store = useAppStore()
  const { showConfirm } = useConfirmSingleton()

  const commissions = ref<CommissionItem[]>([])
  const commissionsTotal = ref(0)
  const referrals = ref<ReferralItem[]>([])
  const referralsTotal = ref(0)
  const withdrawals = ref<WithdrawalItem[]>([])
  const withdrawalsTotal = ref(0)
  const withdrawAmount = ref('')
  const selectedAmount = ref(0)
  const withdrawing = ref(false)
  const withdrawRules = ref<any>(null)
  const childAgents = ref<any[]>([])
  const withdrawPresets = ref<number[]>([])

  const orders = ref<OrderItem[]>([])
  const ordersTotal = ref(0)
  const loadingOrders = ref(false)

  const profileForm = reactive({ display_name: '', wechat_qr: '' })
  const pwForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
  const savingProfile = ref(false)
  const changingPw = ref(false)
  const uploadingQr = ref(false)
  const qrPreview = ref('')

  const userProfile = reactive({ nickname: '' })
  const savingUserProfile = ref(false)

  async function loadCommissions() {
    try { const res = await api.agents.commissions({ limit: 100 }); commissions.value = res.data.items; commissionsTotal.value = res.data.total } catch {}
  }

  async function loadReferrals() {
    try { const res = await api.agents.referrals({ limit: 100 }); referrals.value = res.data.items; referralsTotal.value = res.data.total } catch {}
  }

  async function loadWithdrawals() {
    try { const res = await api.agents.withdrawals({ limit: 100 }); withdrawals.value = res.data.items; withdrawalsTotal.value = res.data.total } catch {}
  }

  async function loadWithdrawRules() {
    try { const res = await api.agents.withdrawRules(); withdrawRules.value = res.data; withdrawPresets.value = res.data.presets ? res.data.presets.split(',').map(Number) : [] } catch {}
  }

  async function loadChildren() {
    try { const res = await api.agents.childAgents(); childAgents.value = res?.data || [] } catch {}
  }

  async function loadOrders() {
    loadingOrders.value = true
    try { const res = await api.orders.list({ limit: 50 }); orders.value = res.data.items; ordersTotal.value = res.data.total } catch {}
    finally { loadingOrders.value = false }
  }

  async function doWithdraw() {
    const amount = selectedAmount.value
    if (!amount || amount <= 0) { store.toast('请选择提现金额', 'warning'); return }
    if (!agent.value || amount > agent.value.available_balance) { store.toast('余额不足', 'warning'); return }
    if (withdrawRules.value) {
      if (amount < withdrawRules.value.min_amount) { store.toast(`最低提现 ¥${withdrawRules.value.min_amount}`, 'warning'); return }
      if (withdrawRules.value.today_remaining_count !== null && withdrawRules.value.today_remaining_count <= 0) { store.toast('今日提现次数已用完', 'warning'); return }
      if (withdrawRules.value.today_remaining_amount !== null && amount > withdrawRules.value.today_remaining_amount) { store.toast(`今日剩余可提 ¥${withdrawRules.value.today_remaining_amount.toFixed(0)}`, 'warning'); return }
    }
    const ok = await showConfirm({ title: '确认提现', message: `确定要提现 ¥${amount.toFixed(2)} 吗？`, type: 'info' })
    if (!ok) return
    withdrawing.value = true
    try {
      await api.agents.withdraw(amount)
      store.toast(`提现成功 ¥${amount.toFixed(2)}`, 'success')
      selectedAmount.value = 0
      const res = await api.agents.me()
      agent.value = res.data
      await loadDashboard()
      await loadWithdrawals()
      await loadWithdrawRules()
    } catch (e: any) { store.toast(e?.message || '提现失败，请稍后重试', 'error') }
    finally { withdrawing.value = false }
  }

  function initProfileForm() {
    if (!agent.value) return
    profileForm.display_name = agent.value.display_name || ''
    profileForm.wechat_qr = agent.value.wechat_qr || ''
    qrPreview.value = agent.value.wechat_qr || ''
    userProfile.nickname = ''
    loadUserProfile()
  }

  async function loadUserProfile() {
    try { const r = await api.users.me(); userProfile.nickname = r.data.nickname || '' } catch {}
  }

  async function saveProfile() {
    savingProfile.value = true
    try {
      const res = await api.agents.updateProfile(profileForm)
      agent.value = res.data
      store.toast('代理资料已更新', 'success')
    } catch (e: any) { store.toast(e?.message || '更新失败', 'error') }
    finally { savingProfile.value = false }
  }

  async function saveUserProfile() {
    savingUserProfile.value = true
    try {
      await api.users.updateProfile({ nickname: userProfile.nickname || undefined })
      store.toast('个人资料已更新', 'success')
    } catch (e: any) { store.toast(e?.message || '更新失败', 'error') }
    finally { savingUserProfile.value = false }
  }

  function triggerQrUpload() {
    const input = document.getElementById('qr-file-input') as HTMLInputElement
    input?.click()
  }

  async function handleQrFile(e: Event) {
    const input = e.target as HTMLInputElement
    const file = input.files?.[0]
    if (!file) return
    if (!file.type.startsWith('image/')) { store.toast('请选择图片文件', 'warning'); return }
    if (file.size > 5 * 1024 * 1024) { store.toast('图片大小不能超过5MB', 'warning'); return }

    uploadingQr.value = true
    try {
      const reader = new FileReader()
      reader.onload = async () => {
        try {
          const token = getUserApiToken()
          const r = await fetch('/api/agents/upload-qr-base64', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ image: reader.result }),
          })
          const d = await r.json()
          if (d.code !== 0) { store.toast(d.message || '上传失败', 'error'); return }
          profileForm.wechat_qr = d.data.url
          qrPreview.value = d.data.url
          if (agent.value) agent.value.wechat_qr = d.data.url
          store.toast('二维码上传成功', 'success')
        } catch { store.toast('上传失败', 'error') }
        finally { uploadingQr.value = false }
      }
      reader.onerror = () => { uploadingQr.value = false; store.toast('读取文件失败', 'error') }
      reader.readAsDataURL(file)
    } catch { uploadingQr.value = false }
    input.value = ''
  }

  async function changePassword(logoutFn: () => void) {
    if (!pwForm.old_password || !pwForm.new_password) { store.toast('请填写完整信息', 'warning'); return }
    if (pwForm.new_password.length < 6) { store.toast('新密码至少6位', 'warning'); return }
    if (pwForm.new_password !== pwForm.confirm_password) { store.toast('两次密码不一致', 'warning'); return }
    changingPw.value = true
    try {
      await api.users.changePassword({ old_password: pwForm.old_password, new_password: pwForm.new_password })
      store.toast('密码修改成功，请重新登录', 'success')
      logoutFn()
    } catch (e: any) { store.toast(e?.message || '修改失败', 'error') }
    finally { changingPw.value = false }
  }

  function copyLink(link: string) {
    navigator.clipboard?.writeText(window.location.origin + link)
    store.toast('链接已复制到剪贴板', 'success')
  }

  return {
    commissions, commissionsTotal, referrals, referralsTotal,
    withdrawals, withdrawalsTotal, withdrawAmount, selectedAmount, withdrawing,
    withdrawRules, childAgents, withdrawPresets,
    orders, ordersTotal, loadingOrders,
    profileForm, pwForm, savingProfile, changingPw, uploadingQr, qrPreview,
    userProfile, savingUserProfile,
    loadCommissions, loadReferrals, loadWithdrawals, loadWithdrawRules, loadChildren, loadOrders,
    doWithdraw, initProfileForm, loadUserProfile, saveProfile, saveUserProfile,
    triggerQrUpload, handleQrFile, changePassword, copyLink,
  }
}

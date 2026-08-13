// 用户管理
import { ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api'

export function useUsers() {
  const store = useAppStore()

  // ── Users ──
  const users = ref<any[]>([])
  const usersTotal = ref(0)
  const loadingUsers = ref(false)
  const showTopupModal = ref(false)
  const topupTarget = ref<any>(null)
  const topupAmount = ref(0)
  const topupNote = ref('')
  const toppupMode = ref<'topup' | 'deduct'>('topup')
  const toppingUp = ref(false)

  async function loadUsers() {
    loadingUsers.value = true
    try {
      const r = await api.adminUsers.list({ limit: 100 })
      users.value = r.data.items
      usersTotal.value = r.data.total
    } catch (e: any) { store.toast(e.message || '加载用户失败', 'error') }
    finally { loadingUsers.value = false }
  }

  function openTopup(user: any, mode: 'topup' | 'deduct') {
    topupTarget.value = user
    toppupMode.value = mode
    topupAmount.value = 0
    topupNote.value = ''
    showTopupModal.value = true
  }

  async function doTopup() {
    if (!topupTarget.value || topupAmount.value <= 0) { store.toast('请输入有效金额', 'warning'); return }
    toppingUp.value = true
    try {
      const fn = toppupMode.value === 'topup' ? api.adminUsers.topup : api.adminUsers.deduct
      await fn(topupTarget.value.user_id, topupAmount.value, topupNote.value || undefined)
      store.toast(`${toppupMode.value === 'topup' ? '充值' : '扣费'} ¥${topupAmount.value.toFixed(2)} 成功`, 'success')
      showTopupModal.value = false
      loadUsers()
    } catch (e: any) { store.toast(e.message, 'error') }
    finally { toppingUp.value = false }
  }

  return {
    users, usersTotal, loadingUsers, showTopupModal, topupTarget,
    topupAmount, topupNote, toppupMode, toppingUp,
    loadUsers, openTopup, doTopup,
  }
}

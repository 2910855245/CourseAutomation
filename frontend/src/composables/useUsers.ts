// 用户/代理/佣金/合伙人管理
import { ref, reactive, computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { api, type AgentProfile, type CommissionItem } from '@/api'
import { useConfirmSingleton } from '@/composables/useConfirm'

export function useUsers() {
  const store = useAppStore()
  const { showConfirm } = useConfirmSingleton()

  function getRole(): 'admin' | 'sub_admin' { return store.adminToken ? 'admin' : 'sub_admin' }

  // ── Users ──
  const usersSubTab = ref<'users' | 'subadmins'>('users')
  const users = ref<any[]>([])
  const usersTotal = ref(0)
  const loadingUsers = ref(false)
  const showTopupModal = ref(false)
  const topupTarget = ref<any>(null)
  const topupAmount = ref(0)
  const topupNote = ref('')
  const toppupMode = ref<'topup' | 'deduct'>('topup')
  const toppingUp = ref(false)

  const unifiedUsers = ref<any[]>([])
  const unifiedTotal = ref(0)
  const unifiedStats = ref<any>(null)
  const unifiedRoleFilter = ref('')
  const unifiedAgentFilter = ref('')
  const unifiedSearch = ref('')
  const loadingUnified = ref(false)
  const personnelTab = ref<'subadmins' | 'agents'>('subadmins')

  // ── Agents ──
  const agents = ref<(AgentProfile & { username: string; nickname: string; referral_count: number })[]>([])
  const agentTotal = ref(0)
  const agentStatusFilter = ref('')
  const agentStats = ref<any>(null)
  const loadingAgents = ref(false)
  const agentSubTab = ref<'agentMgmt' | 'tiers' | 'fees' | 'guide'>('agentMgmt')
  const partnerAgentStats = computed(() => {
    const list = agents.value
    return {
      total: list.length,
      active: list.filter((a: any) => a.status === 'active').length,
      pending: list.filter((a: any) => a.status === 'pending').length,
      suspended: list.filter((a: any) => a.status === 'suspended').length,
    }
  })

  // ── Commissions ──
  const commissions = ref<CommissionItem[]>([])
  const commissionTotal = ref(0)
  const loadingCommissions = ref(false)

  // ── Rate modal ──
  const showRateModal = ref(false)
  const rateTarget = ref<any>(null)
  const newRate = ref(0.15)

  // ── Sub-admins ──
  const subAdmins = ref<any[]>([])
  const loadingSubAdmins = ref(false)
  const showCreateSubAdmin = ref(false)
  const newSubAdmin = reactive({ user_id: '', username: '', password: '', nickname: '' })
  const creatingSubAdmin = ref(false)

  // ── Tier management ──
  const agentsByTier = reactive({ l1: [] as any[], l2: [] as any[], l3: [] as any[] })
  const loadingAgentsByTier = ref(false)
  const showTierModal = ref(false)
  const tierTarget = ref<any>(null)
  const newTierLevel = ref(1)
  const tierCommissions = reactive({ tier1: 0.5, tier2: 0.3, tier3: 0.2 })
  const savingTierCommissions = ref(false)

  // ── Agent fees ──
  const agentFees = reactive({
    registration_enabled: false,
    registration_fee: 100,
    upgrade_enabled: false,
    upgrade_l2_fee: 200,
    upgrade_l3_fee: 300,
  })
  const savingAgentFees = ref(false)

  // ── Functions ──

  async function loadAgentStats() {
    try { const r = await api.adminAgents.stats(); agentStats.value = r.data } catch (e: any) { console.error('加载代理统计失败:', e.message) }
  }

  async function loadAgents() {
    loadingAgents.value = true
    try {
      const params: any = { limit: 50, offset: 0 }
      if (agentStatusFilter.value) params.status = agentStatusFilter.value
      if (getRole() === 'admin') {
        const r = await api.adminAgents.list(params)
        agents.value = r.data.items
        agentTotal.value = r.data.total
      } else {
        const r = await api.subAdmin.agents.list(params)
        agents.value = r.data.items
        agentTotal.value = r.data.total
      }
    } catch (e: any) { store.toast(e.message || '加载代理失败', 'error') }
    finally { loadingAgents.value = false }
  }

  async function loadCommissions() {
    loadingCommissions.value = true
    try {
      if (getRole() === 'admin') {
        const r = await api.adminAgents.commissions({ limit: 100 })
        commissions.value = r.data.items
        commissionTotal.value = r.data.total
      } else {
        const r = await api.subAdmin.commissions.list({ limit: 100 })
        commissions.value = r.data.items
        commissionTotal.value = r.data.total
      }
    } catch (e: any) { store.toast(e.message || '加载佣金记录失败', 'error') }
    finally { loadingCommissions.value = false }
  }

  async function approveAgent(id: string) {
    try {
      if (getRole() === 'admin') await api.adminAgents.approve(id)
      else await api.subAdmin.agents.approve(id)
      store.toast('代理已通过', 'success'); loadAgents(); if (getRole() === 'admin') loadAgentStats()
    } catch (e: any) { store.toast(e.message || '操作失败', 'error') }
  }

  async function suspendAgent(id: string) {
    const ok = await showConfirm({ title: '暂停代理', message: '确定要暂停该代理吗？暂停后其子站将无法访问，推荐码将失效。', type: 'warning' })
    if (!ok) return
    try {
      if (getRole() === 'admin') await api.adminAgents.suspend(id)
      else await api.subAdmin.agents.suspend(id)
      store.toast('代理已暂停', 'success'); loadAgents(); if (getRole() === 'admin') loadAgentStats()
    } catch (e: any) { store.toast(e.message || '操作失败', 'error') }
  }

  async function reactivateAgent(id: string) {
    try {
      if (getRole() === 'admin') await api.adminAgents.reactivate(id)
      else await api.subAdmin.agents.reactivate(id)
      store.toast('代理已恢复', 'success'); loadAgents(); if (getRole() === 'admin') loadAgentStats()
    } catch (e: any) { store.toast(e.message || '操作失败', 'error') }
  }

  function openRateModal(agent: any) {
    rateTarget.value = agent; newRate.value = agent.flow_commission_rate; showRateModal.value = true
  }

  async function saveRate() {
    if (!rateTarget.value) return
    try {
      if (getRole() === 'admin') await api.adminAgents.setRate(rateTarget.value.agent_id, newRate.value)
      else await api.subAdmin.agents.setRate(rateTarget.value.agent_id, newRate.value)
      store.toast('佣金比例已更新', 'success'); showRateModal.value = false; loadAgents()
    } catch (e: any) { store.toast(e.message || '操作失败', 'error') }
  }

  async function loadSubAdmins() {
    loadingSubAdmins.value = true
    try { const r = await api.admin.subAdmins.list(); subAdmins.value = r.data?.items || [] } catch (e: any) { store.toast(e.message || '加载合伙人列表失败', 'error') }
    finally { loadingSubAdmins.value = false }
  }

  async function doCreateSubAdmin() {
    if (!newSubAdmin.user_id.trim() || !newSubAdmin.username.trim() || !newSubAdmin.password) { store.toast('请填写完整信息', 'warning'); return }
    if (newSubAdmin.password.length < 6) { store.toast('密码至少6位', 'warning'); return }
    creatingSubAdmin.value = true
    try {
      await api.admin.subAdmins.create({ user_id: newSubAdmin.user_id.trim(), username: newSubAdmin.username.trim(), password: newSubAdmin.password, nickname: newSubAdmin.nickname.trim() })
      store.toast('合伙人创建成功', 'success')
      showCreateSubAdmin.value = false
      newSubAdmin.user_id = ''; newSubAdmin.username = ''; newSubAdmin.password = ''; newSubAdmin.nickname = ''
      loadSubAdmins()
    } catch (e: any) { store.toast(e.message || '创建失败', 'error') }
    finally { creatingSubAdmin.value = false }
  }

  async function doRevokeSubAdmin(userId: string) {
    const ok = await showConfirm({ title: '撤销合伙人', message: '确定撤销该用户的合伙人权限吗？', type: 'warning' })
    if (!ok) return
    try { await api.admin.subAdmins.revoke(userId); store.toast('已撤销合伙人权限', 'success'); loadSubAdmins() } catch (e: any) { store.toast(e.message, 'error') }
  }

  async function loadAgentsByTier() {
    loadingAgentsByTier.value = true
    try {
      let all: any[] = []
      if (getRole() === 'admin') {
        const r = await api.adminAgents.list({ limit: 200 })
        all = r.data?.items || []
      } else {
        const r = await api.subAdmin.agents.list({ limit: 200 })
        all = r.data?.items || []
      }
      agentsByTier.l1 = all.filter((a: any) => a.tier_level === 1)
      agentsByTier.l2 = all.filter((a: any) => a.tier_level === 2)
      agentsByTier.l3 = all.filter((a: any) => a.tier_level >= 3)
    } catch (e: any) { store.toast(e.message || '加载代理层级失败', 'error') }
    finally { loadingAgentsByTier.value = false }
  }

  function openTierModal(agent: any) {
    tierTarget.value = agent; newTierLevel.value = agent.tier_level || 1; showTierModal.value = true
  }

  async function doChangeTier() {
    if (!tierTarget.value) return
    try {
      if (getRole() === 'admin') await api.admin.agents.setTier(tierTarget.value.agent_id, newTierLevel.value)
      else await api.subAdmin.agents.setTier(tierTarget.value.agent_id, newTierLevel.value)
      store.toast(`代理等级已更新为 L${newTierLevel.value}`, 'success')
      showTierModal.value = false; loadAgentsByTier()
    } catch (e: any) { store.toast(e.message, 'error') }
  }

  async function loadTierCommissions() {
    try {
      const r = await api.admin.tierCommissions.get()
      if (r.data) {
        tierCommissions.tier1 = r.data.tier1
        tierCommissions.tier2 = r.data.tier2
        tierCommissions.tier3 = r.data.tier3
      }
    } catch {}
  }

  async function saveTierCommissions() {
    savingTierCommissions.value = true
    try {
      await api.admin.tierCommissions.set({
        tier1: tierCommissions.tier1,
        tier2: tierCommissions.tier2,
        tier3: tierCommissions.tier3,
      })
      store.toast('等级佣金比例已保存', 'success')
    } catch (e: any) { store.toast(e.message, 'error') }
    finally { savingTierCommissions.value = false }
  }

  async function loadAgentFees() {
    try {
      const r = await api.admin.agentFees.get()
      if (r.data) {
        agentFees.registration_enabled = r.data.registration_enabled
        agentFees.registration_fee = r.data.registration_fee
        agentFees.upgrade_enabled = r.data.upgrade_enabled
        agentFees.upgrade_l2_fee = r.data.upgrade_l2_fee
        agentFees.upgrade_l3_fee = r.data.upgrade_l3_fee
      }
    } catch {}
  }

  async function saveAgentFees() {
    savingAgentFees.value = true
    try {
      await api.admin.agentFees.set({
        registration_enabled: agentFees.registration_enabled,
        registration_fee: agentFees.registration_fee,
        upgrade_enabled: agentFees.upgrade_enabled,
        upgrade_l2_fee: agentFees.upgrade_l2_fee,
        upgrade_l3_fee: agentFees.upgrade_l3_fee,
      })
      store.toast('代理付费设置已保存', 'success')
    } catch (e: any) { store.toast(e.message, 'error') }
    finally { savingAgentFees.value = false }
  }

  async function loadUsers() {
    loadingUsers.value = true
    try {
      const r = await api.adminUsers.list({ limit: 100 })
      users.value = r.data.items
      usersTotal.value = r.data.total
    } catch (e: any) { store.toast(e.message || '加载用户失败', 'error') }
    finally { loadingUsers.value = false }
  }

  async function loadUnifiedUsers() {
    loadingUnified.value = true
    try {
      const params: any = { limit: 100 }
      if (unifiedRoleFilter.value) params.role = unifiedRoleFilter.value
      if (unifiedAgentFilter.value) params.agent_status = unifiedAgentFilter.value
      if (unifiedSearch.value) params.search = unifiedSearch.value
      const r = await api.adminUsers.unified(params)
      unifiedUsers.value = r.data.items
      unifiedTotal.value = r.data.total
      unifiedStats.value = r.data.stats
    } catch (e: any) { store.toast(e.message || '加载用户失败', 'error') }
    finally { loadingUnified.value = false }
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

  async function clearCommissionHistory() {
    try { const res = await api.adminAgents.clearCommissions(); store.toast(res.message || '佣金记录已清除', 'success') }
    catch (e: any) { store.toast(e.message, 'error') }
  }

  return {
    usersSubTab, users, usersTotal, loadingUsers, showTopupModal, topupTarget,
    topupAmount, topupNote, toppupMode, toppingUp,
    unifiedUsers, unifiedTotal, unifiedStats, unifiedRoleFilter, unifiedAgentFilter,
    unifiedSearch, loadingUnified, personnelTab,
    agents, agentTotal, agentStatusFilter, agentStats, loadingAgents, agentSubTab, partnerAgentStats,
    commissions, commissionTotal, loadingCommissions,
    showRateModal, rateTarget, newRate,
    subAdmins, loadingSubAdmins, showCreateSubAdmin, newSubAdmin, creatingSubAdmin,
    agentsByTier, loadingAgentsByTier, showTierModal, tierTarget, newTierLevel,
    tierCommissions, savingTierCommissions,
    agentFees, savingAgentFees,
    loadAgentStats, loadAgents, loadCommissions, approveAgent, suspendAgent, reactivateAgent,
    openRateModal, saveRate, loadSubAdmins, doCreateSubAdmin, doRevokeSubAdmin,
    loadAgentsByTier, openTierModal, doChangeTier, loadTierCommissions, saveTierCommissions,
    loadAgentFees, saveAgentFees, loadUsers, loadUnifiedUsers, openTopup, doTopup, clearCommissionHistory,
  }
}

// 风控黑名单：账号黑名单 / IP 黑名单 / IP 限制（后台「拉黑管理」页）
import { ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { api, type BlacklistItem, type IpBlacklistItem, type IpLimitConfig, type IpRecord } from '@/api'
import { useConfirmSingleton } from '@/composables/useConfirm'

export function useBlacklist() {
  const store = useAppStore()
  const { showConfirm } = useConfirmSingleton()

  const accounts = ref<BlacklistItem[]>([])
  const ips = ref<IpBlacklistItem[]>([])
  const ipRecords = ref<IpRecord[]>([])
  const ipLimit = ref<IpLimitConfig>({ enabled: true, max_accounts: 5, window_hours: 24 })
  const loading = ref(false)

  // 表单
  const accountForm = ref({ username: '', reason: '' })
  const ipForm = ref({ ip: '', reason: '' })

  async function loadAll() {
    loading.value = true
    try {
      const [a, i, r, l] = await Promise.all([
        api.adminBlacklist.accounts(),
        api.adminBlacklist.ips(),
        api.adminBlacklist.ipRecords(),
        api.adminBlacklist.ipLimitGet(),
      ])
      accounts.value = a.data.items || []
      ips.value = i.data.items || []
      ipRecords.value = r.data.items || []
      ipLimit.value = l.data
    } catch (e: any) { store.toast(e.message || '加载风控数据失败', 'error') }
    finally { loading.value = false }
  }

  // ── 账号黑名单 ──
  async function addAccount() {
    const username = accountForm.value.username.trim()
    if (!username) { store.toast('请填写要拉黑的学号', 'warning'); return }
    const ok = await showConfirm({
      title: '拉黑账号',
      message: `确定拉黑账号「${username}」吗？\n拉黑后该账号无法扫描课程、也无法提交刷课，再次尝试会弹窗提示"该账号已被本平台拉黑，无法享用免费刷课"。`,
      type: 'danger',
      confirmText: '拉黑',
    })
    if (!ok) return
    try {
      // website_id 只作"拉黑来源平台"的记录：手动拉黑没有上下文，传 0（不限平台）
      const r = await api.adminBlacklist.addAccount({ username, website_id: 0, reason: accountForm.value.reason.trim() })
      store.toast(r.message || '已拉黑该账号', 'success')
      accountForm.value = { username: '', reason: '' }
      await loadAll()
    } catch (e: any) { store.toast(e.message, 'error') }
  }

  async function removeAccount(id: number, username: string) {
    const ok = await showConfirm({
      title: '解除拉黑', message: `确定把「${username}」从黑名单移除吗？移除后该账号可正常刷课。`,
      type: 'warning', confirmText: '解除',
    })
    if (!ok) return
    try { await api.adminBlacklist.removeAccount(id); store.toast('已解除拉黑', 'success'); await loadAll() }
    catch (e: any) { store.toast(e.message, 'error') }
  }

  // ── IP 黑名单 ──
  async function addIp(ip?: string, reason?: string) {
    const target = (ip ?? ipForm.value.ip).trim()
    if (!target) { store.toast('请填写要拉黑的 IP', 'warning'); return }
    const ok = await showConfirm({
      title: '拉黑 IP',
      message: `确定拉黑 IP「${target}」吗？\n该来源将无法访问本站任何页面（含 API 与静态页），返回 403。`,
      type: 'danger', confirmText: '拉黑',
    })
    if (!ok) return
    try {
      const r = await api.adminBlacklist.addIp({ ip: target, reason: (reason ?? ipForm.value.reason).trim() })
      store.toast(r.message || '已拉黑该 IP', 'success')
      ipForm.value = { ip: '', reason: '' }
      await loadAll()
    } catch (e: any) { store.toast(e.message, 'error') }
  }

  async function removeIp(id: number, ip: string) {
    const ok = await showConfirm({
      title: '解除 IP 拉黑', message: `确定解除对「${ip}」的封禁吗？解除后该来源可正常访问。`,
      type: 'warning', confirmText: '解除',
    })
    if (!ok) return
    try { await api.adminBlacklist.removeIp(id); store.toast('已解除该 IP 的拉黑', 'success'); await loadAll() }
    catch (e: any) { store.toast(e.message, 'error') }
  }

  // ── IP 限制 ──
  async function saveIpLimit() {
    const max = Math.min(200, Math.max(1, Math.floor(Number(ipLimit.value.max_accounts) || 1)))
    const hours = Math.min(720, Math.max(1, Math.floor(Number(ipLimit.value.window_hours) || 1)))
    try {
      const r = await api.adminBlacklist.ipLimitSet({ enabled: ipLimit.value.enabled, max_accounts: max, window_hours: hours })
      ipLimit.value = r.data
      store.toast('已保存 IP 限制', 'success')
    } catch (e: any) { store.toast(e.message, 'error') }
  }

  return {
    accounts, ips, ipRecords, ipLimit, loading, accountForm, ipForm,
    loadAll, addAccount, removeAccount, addIp, removeIp, saveIpLimit,
  }
}
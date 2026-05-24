// 概览数据/侧边栏/格式化
import { ref, computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { api, type DashboardStats } from '@/api'

export function useDashboard() {
  const store = useAppStore()

  const dash = ref<DashboardStats | any | null>(null)
  const dashError = ref('')
  const loadingDash = ref(false)
  const sidebarCollapsed = ref(false)
  const mobileSidebarOpen = ref(false)

  async function loadDashboard(currentRole: string) {
    loadingDash.value = true
    dashError.value = ''
    try {
      if (currentRole === 'admin') {
        const r = await api.admin.dashboard()
        dash.value = r.data
      } else {
        const r = await api.subAdmin.stats()
        dash.value = r.data
      }
    } catch (e: any) {
      dashError.value = e?.message || '加载失败，请检查后端服务是否正常运行'
    }
    finally { loadingDash.value = false }
  }

  const statusLabel: Record<string, string> = { pending: '待审核', active: '活跃', suspended: '已暂停' }
  const statusClass: Record<string, string> = { pending: 'warn', active: 'ok', suspended: 'bad' }
  const orderStatusLabel: Record<string, string> = { pending: '待处理', accepted: '已接单', running: '执行中', completed: '已完成', failed: '失败', cancelled: '已取消' }
  const orderStatusClass: Record<string, string> = { pending: 'warn', accepted: 'primary', running: 'primary', completed: 'ok', failed: 'bad', cancelled: 'muted' }

  const maxStatusCount = computed(() => {
    if (!dash.value?.status_distribution?.length) return 1
    return Math.max(...dash.value.status_distribution.map((sd: any) => sd.count), 1)
  })
  const maxBarRevenue = computed(() => {
    if (!dash.value?.recent_7_days) return 1
    return Math.max(...dash.value.recent_7_days.map((d: any) => d.revenue), 1)
  })
  const maxBarOrders = computed(() => {
    if (!dash.value?.recent_7_days) return 1
    return Math.max(...dash.value.recent_7_days.map((d: any) => d.orders), 1)
  })
  const totalPlatformOrders = computed(() => {
    if (!dash.value?.platform_distribution) return 1
    return dash.value.platform_distribution.reduce((s: any, p: any) => s + p.count, 0) || 1
  })
  const maxPartnerStatusCount = computed(() => {
    if (!dash.value?.by_status) return 1
    return Math.max(...Object.values(dash.value.by_status).map((v: any) => v.count), 1)
  })

  const sidebarGroups = [
    {
      label: '经营中心',
      icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1',
      children: [
        { key: 'overview', label: '财务报表', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1' },
        { key: 'orders', label: '订单管理', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01' },
        {
          key: 'queue', label: '队列监控', icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
          children: [
            { key: 'queue', label: '全部队列', icon: 'M4 6h16M4 12h16M4 18h16' },
            { key: 'queue_school', label: '学校平台', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1' },
            { key: 'queue_chaoxing', label: '学习通', icon: 'M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253' },
          ],
        },
        { key: 'users', label: '用户管理', icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z' },
      ],
    },
    {
      label: '代理商',
      icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z',
      children: [
        { key: 'agents', label: '代理管理', icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z' },
        { key: 'commissions', label: '佣金记录', icon: 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
        { key: 'withdrawals', label: '提现管理', icon: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15' },
      ],
    },
    {
      label: '运营配置',
      icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z',
      children: [
        { key: 'pricing', label: '产品定价', icon: 'M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z' },
        { key: 'ypay', label: '支付收款', icon: 'M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z' },
        { key: 'ads', label: '广告管理', icon: 'M19 3H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V5a2 2 0 00-2-2zm-7 14l-5-5 1.41-1.41L12 14.17l4.59-4.58L18 11l-6 6z' },
      ],
    },
    {
      label: '系统',
      icon: 'M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z',
      children: [
        { key: 'proxy', label: '网络代理', icon: 'M3.05 13H1v-2h2.05C3.5 8.83 5.83 6.5 8 6.05V4h2v2.05c2.17.45 4.5 2.78 4.95 4.95H17v2h-2.05c-.45 2.17-2.78 4.5-4.95 4.95V20H8v-2.05C5.83 17.5 3.5 15.17 3.05 13zM12 9a3 3 0 00-3 3 3 3 0 003 3 3 3 0 003-3 3 3 0 00-3-3z' },
        { key: 'risk', label: '风险监控', icon: 'M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
        { key: 'security', label: '安全中心', icon: 'M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z' },
      ],
    },
  ] as const

  type SidebarKey = 'overview' | 'orders' | 'queue' | 'queue_school' | 'queue_chaoxing' | 'users' | 'agents' | 'commissions' | 'withdrawals' | 'pricing' | 'ypay' | 'ads' | 'proxy' | 'risk' | 'security'

  const allSidebarItems: { key: string; label: string; icon: string }[] = sidebarGroups.flatMap((g: any) =>
    g.children.flatMap((item: any) => item.children ? [item, ...item.children] : [item])
  )
  const partnerAllowedTabs: SidebarKey[] = ['overview', 'orders', 'agents', 'commissions', 'withdrawals', 'security']
  const visibleSidebarGroups = computed(() => {
    if ((store.adminToken ? 'admin' : 'sub_admin') === 'admin') return sidebarGroups as any
    return sidebarGroups
      .map(g => ({ ...g, children: (g.children as any).filter((c: any) => partnerAllowedTabs.includes(c.key as SidebarKey)) }))
      .filter(g => g.children.length > 0)
  })

  function fmtDate(s?: string) { if (!s) return '-'; return s.replace('T', ' ').slice(0, 19) }
  function fmtShortDate(s?: string) { if (!s) return '-'; return s.slice(5, 16).replace('T', ' ') }
  function fmtMoney(v: number) { return '¥' + (v || 0).toFixed(2) }

  return {
    dash, dashError, loadingDash, sidebarCollapsed, mobileSidebarOpen,
    statusLabel, statusClass, orderStatusLabel, orderStatusClass,
    maxStatusCount, maxBarRevenue, maxBarOrders, totalPlatformOrders, maxPartnerStatusCount,
    sidebarGroups, allSidebarItems, partnerAllowedTabs, visibleSidebarGroups,
    fmtDate, fmtShortDate, fmtMoney, loadDashboard,
  }
}

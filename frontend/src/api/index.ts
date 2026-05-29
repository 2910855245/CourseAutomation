const API_BASE = ''

let adminToken = ''
export function setAdminApiToken(t: string) { adminToken = t }

let userToken = ''
export function setUserApiToken(t: string) { userToken = t }
export function getUserApiToken() { return userToken }

const FETCH_TIMEOUT_MS = 30000  // 30 秒超时，防止按钮永久卡住

async function request<T = any>(method: string, path: string, body?: any): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const adminOnlyPrefixes = ['/api/admin', '/api/queue', '/api/ypay', '/api/health']
  const userPreferredPrefixes = ['/api/sub-admin']
  if (userPreferredPrefixes.some(p => path.startsWith(p)) && userToken) {
    headers['Authorization'] = `Bearer ${userToken}`
  } else if (adminOnlyPrefixes.some(p => path.startsWith(p)) && adminToken) {
    headers['Authorization'] = `Bearer ${adminToken}`
  } else if (userToken) {
    headers['Authorization'] = `Bearer ${userToken}`
  }
  const opts: RequestInit = { method, headers }
  if (body && method !== 'GET') opts.body = JSON.stringify(body)

  const controller = new AbortController()
  opts.signal = controller.signal
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
  try {
    const res = await fetch(API_BASE + path, opts)
    if (!res.ok) {
      let errMsg = `请求失败 (${res.status})`
      try {
        const errData = await res.json()
        errMsg = errData.detail || errData.message || errMsg
      } catch { }
      throw new Error(errMsg)
    }
    const data = await res.json()
    return data as T
  } catch (e: any) {
    if (e.name === 'AbortError') {
      throw new Error(`请求超时（${FETCH_TIMEOUT_MS / 1000}秒）`)
    }
    throw e
  } finally {
    clearTimeout(timer)
  }
}

function get<T = any>(path: string): Promise<T> { return request<T>('GET', path) }
function post<T = any>(path: string, body?: any): Promise<T> { return request<T>('POST', path, body) }
function put<T = any>(path: string, body?: any): Promise<T> { return request<T>('PUT', path, body) }
function del<T = any>(path: string): Promise<T> { return request<T>('DELETE', path) }

export function buildQuery(params?: Record<string, any>): string {
  if (!params) return ''
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  }
  const qs = q.toString()
  return qs ? '?' + qs : ''
}

export interface ApiResponse<T = any> { success: boolean; message: string; data: T }
export interface PlatformResult { website_id: number; name: string; status: string; error?: string; student_name?: string; school_name?: string; student_code?: string; points_total?: number; points_target?: number; courses: CourseItem[] }
export interface CourseItem { course_id: string; course_name: string; detail_link: string; study_record_url: string; video_total: number; video_completed: number; video_pending: number; video_actionable: number; exam_total: number; exam_done: number; exam_deleted: number; exam_missed: number; exam_actionable: number; exam_pending: number; homework_total: number; homework_done: number; records_loaded: boolean; has_points_system?: boolean; points_total?: number; points_video?: number; points_remaining?: number; days_needed?: number; study_days?: number; total_minutes?: number; work_total?: number; work_pending?: number; work_completed?: number }
export interface OrderItem {
  order_id: string; out_trade_no?: string; ezfpy_trade_no?: string; payment_trade_no?: string;
  payment_channel?: string; payment_time?: string; commission_status?: string;
  user_id: string; username: string; password: string;
  customer_name?: string; customer_contact?: string;
  website_id: number; task_type: string; course_ids: string[];
  video_count: number; price: number; status: string; paid?: boolean;
  progress?: number; task_id?: string; admin_note?: string; exam_count?: number;
  created_at: string; updated_at?: string; accepted_at?: string; started_at?: string; finished_at?: string;
}
export interface DashboardStats {
  users: { total: number; new_today: number; new_week: number }
  orders: { total: number; today: number; week: number; completed: number; pending: number; running: number; failed: number; completion_rate: number }
  revenue: { total: number; today: number; week: number }
  agents: { active: number; pending: number; total_commission: number }
  agent_upgrades?: { count: number; revenue: number; today_count: number; today_revenue: number; week_count: number; week_revenue: number }
  platform_distribution: { website_id: number; count: number; revenue: number }[]
  task_type_distribution: { task_type: string; count: number; revenue: number }[]
  status_distribution: { status: string; count: number }[]
  recent_7_days: { date: string; orders: number; revenue: number }[]
  recent_orders: { order_id: string; username: string; website_id: number; task_type: string; price: number; status: string; created_at: string }[]
  top_agents: { agent_id: string; display_name: string; total_earnings: number; referral_code: string; commission_rate: number }[]
}

export interface SystemStatus { tasks: { running: number; pending: number; completed: number; failed: number; total: number }; queue: { pending: number; running: number; completed: number; failed: number; total: number; active_workers: number }; orders: { total_orders: number; total_revenue: number; by_status: Record<string, { count: number; revenue: number }> } }

export interface AgentProfile {
  agent_id: string; user_id: string; referral_code: string; subdomain_slug: string;
  display_name: string; welcome_text: string; wechat_qr: string;
  flow_commission_rate: number; tier_level: number; parent_agent_id: string | null;
  total_commission: number; available_balance: number; withdrawn_amount: number;
  frozen_balance: number; status: string; created_at: string;
  referral_count?: number; total_commission_amount?: number; pending_commission_amount?: number;
}
export interface CommissionItem { commission_id: string; agent_id: string; order_id: string; referred_user_id: string; order_amount: number; commission_rate: number; commission_amount: number; level: number; status: string; created_at: string }
export interface ReferralItem { user_id: string; username: string; nickname: string; order_count: number; total_spent: number; created_at: string }
export interface WithdrawalItem { withdrawal_id: string; agent_id: string; amount: number; method: string; status: string; created_at: string }
export interface AdItem { id: number; slot: number; name: string; html_content: string; is_active: number; create_time: string }
export interface AdPublicItem { id: number; slot: number; name: string }

export const api = {
  courses: {
    platforms: () => get<ApiResponse<{ id: number; name: string; base_url: string }[]>>('/api/courses/platforms'),
    scan: (d: { username: string; password: string; include_records: boolean }) => post<ApiResponse<{ platforms: PlatformResult[] }>>('/api/courses/scan', d),
    scanChaoxing: (d: { username: string; password: string }) => post<ApiResponse<{ platform: PlatformResult }>>('/api/courses/scan/chaoxing', d),
    relogin: (d: { username: string; password: string; website_id: number; include_records: boolean }) => post<ApiResponse<{ platform: PlatformResult }>>('/api/courses/relogin', d),
  },
  orders: {
    batch: (d: { username: string; password: string; orders: any[]; inviter_code?: string }) => post<ApiResponse<any>>('/api/orders/batch', d),
    pay: () => post<ApiResponse<any>>('/api/orders/pay'),
    list: (params?: { status?: string; page?: number; page_size?: number; limit?: number; search?: string; sort_by?: string; sort_dir?: string }) =>
      get<ApiResponse<{ total: number; items: OrderItem[]; page: number; page_size: number; total_pages: number }>>('/api/orders/' + buildQuery(params)),
    get: (id: string) => get<ApiResponse<OrderItem>>('/api/orders/' + id),
    cancel: (id: string) => del<ApiResponse<any>>('/api/orders/' + id),
    clearHistory: () => post<ApiResponse<any>>('/api/orders/clear-history'),
    exportCsv: (params?: Record<string, any>) => `/api/orders/export-csv` + buildQuery(params),
    auditLog: (id: string) => get<ApiResponse<{ event: string; detail: string; created_at: string }[]>>('/api/orders/audit-log/' + id),
    notifications: () => get<ApiResponse<{ type: string; message: string; time: string; order_id: string }[]>>('/api/orders/notifications'),
    activeCourses: (username: string) => get<ApiResponse<string[]>>('/api/orders/active-courses?username=' + encodeURIComponent(username)),
  },
  payment: {
    create: (d: { order_id: string; pay_type?: number }) =>
      post<ApiResponse<{ mode: string; trade_no: string; out_trade_no: string; order_id: string; pay_url: string; price: number; really_price: number; pay_type: number; qr_image: string | null }>>('/api/payment/create', d),
    batchCreate: (d: { order_ids: string[]; pay_type?: number }) =>
      post<ApiResponse<{ mode: string; batch_id: string; trade_no: string; out_trade_no: string; order_ids: string[]; pay_url: string; total_price: number; really_price: number; pay_type: number; qr_image: string | null }>>('/api/payment/batch-create', d),
    check: (out_trade_no: string, order_id?: string, token?: string) => {
      const params = new URLSearchParams()
      if (order_id) params.set('order_id', order_id)
      if (token) params.set('token', token)
      const q = params.toString() ? '?' + params.toString() : ''
      return get<ApiResponse<{ paid: boolean; order_id?: string; message: string; expired?: boolean }>>('/api/payment/check/' + out_trade_no + q)
    },
    batchCheck: (batch_id: string, out_trade_no?: string, token?: string) => {
      const params = new URLSearchParams()
      if (out_trade_no) params.set('out_trade_no', out_trade_no)
      if (token) params.set('token', token)
      const q = params.toString() ? '?' + params.toString() : ''
      return get<ApiResponse<{ paid: boolean; paid_count?: number; message: string; expired?: boolean }>>('/api/payment/batch-check/' + batch_id + q)
    },
    balancePay: (_order_id: string) => post<ApiResponse<any>>('/api/orders/pay'),
  },
  admin: {
    login: (d: { username: string; password: string; captcha_token?: string; captcha_answer?: string }) => post<ApiResponse<any>>('/api/users/login', d),
    dashboard: () => get<ApiResponse<DashboardStats>>('/api/admin/dashboard'),
    subAdmins: {
      list: () => get<ApiResponse<{ items: any[] }>>('/api/admin/sub-admins'),
      create: (d: { user_id: string; username: string; password: string; nickname?: string }) => post<ApiResponse<any>>('/api/admin/sub-admins/create', d),
      revoke: (userId: string) => post<ApiResponse<any>>('/api/admin/sub-admins/' + userId + '/revoke'),
    },
    agents: {
      setTier: (agentId: string, tierLevel: number) => put<ApiResponse<any>>('/api/admin/agents/' + agentId + '/tier', { tier_level: tierLevel }),
    },
    tierCommissions: {
      get: () => get<ApiResponse<{ tier1: number; tier2: number; tier3: number }>>('/api/admin/tier-commissions'),
      set: (d: { tier1: number; tier2: number; tier3: number }) => put<ApiResponse<any>>('/api/admin/tier-commissions', d),
    },
    agentFees: {
      get: () => get<ApiResponse<{ registration_enabled: boolean; registration_fee: number; upgrade_enabled: boolean; upgrade_l2_fee: number; upgrade_l3_fee: number }>>('/api/admin/agent-fees'),
      set: (d: { registration_enabled: boolean; registration_fee: number; upgrade_enabled: boolean; upgrade_l2_fee: number; upgrade_l3_fee: number }) => put<ApiResponse<any>>('/api/admin/agent-fees', d),
    },
  },
  users: {
    register: (d: { username: string; password: string; nickname?: string; contact?: string; referral_code?: string; captcha_token?: string; captcha_answer?: string }) => post<ApiResponse<any>>('/api/users/register', d),
    login: (d: { username: string; password: string; captcha_token?: string; captcha_answer?: string }) => post<ApiResponse<any>>('/api/users/login', d),
    me: () => get<ApiResponse<any>>('/api/users/me'),
    changePassword: (d: { old_password: string; new_password: string }) => post<ApiResponse<any>>('/api/users/change-password', d),
    updateProfile: (d: { nickname?: string; contact?: string }) => put<ApiResponse<any>>('/api/users/profile', d),
    logout: () => post<ApiResponse<any>>('/api/users/logout'),
  },
  system: {
    status: () => get<SystemStatus>('/api/system/status'),
  },
  agents: {
    apply: (pay_type?: number) => post<ApiResponse<any>>('/api/agents/apply', { pay_type: pay_type ?? 2 }),
    me: () => get<ApiResponse<AgentProfile | null>>('/api/agents/me'),
    profile: () => get<ApiResponse<AgentProfile>>('/api/agents/profile'),
    updateProfile: (d: { display_name?: string; welcome_text?: string; wechat_qr?: string; subdomain_slug?: string }) => put<ApiResponse<AgentProfile>>('/api/agents/profile', d),
    dashboard: () => get<ApiResponse<any>>('/api/agents/dashboard'),
    link: () => get<ApiResponse<{ referral_code: string; referral_link: string; subdomain_slug: string; subsite_link: string }>>('/api/agents/link'),
    referrals: (params?: { limit?: number; offset?: number }) =>
      get<ApiResponse<{ total: number; items: ReferralItem[] }>>('/api/agents/referrals' + buildQuery(params)),
    commissions: (params?: { limit?: number; offset?: number }) =>
      get<ApiResponse<{ total: number; items: CommissionItem[] }>>('/api/agents/commissions' + buildQuery(params)),
    withdrawals: (params?: { limit?: number; offset?: number }) =>
      get<ApiResponse<{ total: number; items: WithdrawalItem[] }>>('/api/agents/withdrawals' + buildQuery(params)),
    withdraw: (amount: number) => post<ApiResponse<any>>('/api/agents/withdraw', { amount }),
    withdrawRules: () => get<ApiResponse<any>>('/api/agents/withdraw-rules'),
    childAgents: () => get<ApiResponse<any[]>>('/api/agents/child-agents'),
    upgradeInfo: () => get<ApiResponse<{ current_tier: number; upgradable: boolean; upgrade_enabled: boolean; options: { tier: number; fee: number; label: string; enabled: boolean }[] }>>('/api/agents/upgrade-info'),
    requestUpgrade: (d: { target_tier: number; pay_type: number }) => post<ApiResponse<{ vmq_order_id: string; pay_id: string; fee: number; target_tier: number; qr_image: string | null; pay_url: string; pay_link: string; submit_url: string; h5_qrurl?: string }>>('/api/agents/request-upgrade', d),
    subsite: (slug: string) => get<ApiResponse<any>>('/api/agents/subsite/' + slug),
  },
  adminAgents: {
    list: (params?: { status?: string; limit?: number; offset?: number }) =>
      get<ApiResponse<{ total: number; items: (AgentProfile & { username: string; nickname: string; referral_count: number })[] }>>('/api/admin/agents/' + buildQuery(params)),
    stats: () => get<ApiResponse<any>>('/api/admin/agents/stats'),
    approve: (id: string) => post<ApiResponse<any>>('/api/admin/agents/' + id + '/approve'),
    suspend: (id: string) => post<ApiResponse<any>>('/api/admin/agents/' + id + '/suspend'),
    reactivate: (id: string) => post<ApiResponse<any>>('/api/admin/agents/' + id + '/reactivate'),
    setRate: (id: string, rate: number) => post<ApiResponse<any>>('/api/admin/agents/' + id + '/rate', { rate }),
    commissions: (params?: { agent_id?: string; limit?: number; offset?: number }) =>
      get<ApiResponse<{ total: number; items: CommissionItem[] }>>('/api/admin/agents/commissions' + buildQuery(params)),
    clearCommissions: () => post<ApiResponse<any>>('/api/admin/agents/commissions/clear'),
  },
  adminOrders: {
    list: (params?: { status?: string; user_id?: string; limit?: number; offset?: number }) =>
      get<ApiResponse<{ total: number; items: OrderItem[] }>>('/api/admin/orders' + buildQuery(params)),
    accept: (id: string) => post<ApiResponse<any>>('/api/admin/orders/' + id + '/accept', {}),
    enqueue: (id: string) => post<ApiResponse<any>>('/api/admin/orders/' + id + '/enqueue', {}),
    execute: (id: string) => post<ApiResponse<any>>('/api/admin/orders/' + id + '/execute'),
    fail: (id: string, note?: string) => post<ApiResponse<any>>('/api/admin/orders/' + id + '/fail', { admin_note: note || '' }),
    complete: (id: string) => post<ApiResponse<any>>('/api/admin/orders/' + id + '/complete'),
  },
  adminUsers: {
    list: (params?: { limit?: number; offset?: number }) =>
      get<ApiResponse<{ total: number; items: any[] }>>('/api/admin/users' + buildQuery(params)),
    unified: (params?: { role?: string; agent_status?: string; search?: string; limit?: number; offset?: number }) =>
      get<ApiResponse<{ total: number; items: any[]; stats: any }>>('/api/admin/users/unified' + buildQuery(params)),
    topup: (userId: string, amount: number, note?: string) =>
      post<ApiResponse<any>>('/api/admin/users/' + userId + '/topup', { amount, note }),
    deduct: (id: string, amount: number, note?: string) =>
      post<ApiResponse<any>>('/api/admin/users/' + id + '/deduct', { amount, note }),
    delete: (id: string) => del<ApiResponse<any>>('/api/admin/users/' + id),
  },
  adminWithdrawals: {
    list: (params?: { status?: string; limit?: number; offset?: number }) =>
      get<ApiResponse<{ total: number; items: any[] }>>('/api/admin/agents/withdrawals' + buildQuery(params)),
    approve: (id: string) => post<ApiResponse<any>>('/api/admin/agents/withdrawals/' + id + '/approve'),
    reject: (id: string) => post<ApiResponse<any>>('/api/admin/agents/withdrawals/' + id + '/reject'),
    withdrawRules: () => get<ApiResponse<any>>('/api/admin/agents/withdraw-rules'),
    setWithdrawRules: (rules: any) => put<ApiResponse<any>>('/api/admin/agents/withdraw-rules', rules),
    clearHistory: () => post<ApiResponse<any>>('/api/admin/agents/withdrawals/clear'),
  },
  queue: {
    stats: (queue?: string) => get<ApiResponse<any>>('/api/queue/stats' + buildQuery({ queue })),
    jobs: (params?: { status?: string; queue?: string }) =>
      get<ApiResponse<any[]>>('/api/queue/jobs' + buildQuery(params)),
    cancel: (id: string) => post<ApiResponse<any>>('/api/queue/jobs/' + id + '/cancel'),
    delete: (id: string) => del<ApiResponse<any>>('/api/queue/jobs/' + id),
    retry: (id: string) => post<ApiResponse<any>>('/api/queue/jobs/' + id + '/retry'),
    clear: () => post<ApiResponse<any>>('/api/queue/clear'),
    pause: (queue?: string) => post<ApiResponse<any>>(queue ? '/api/queue/pause/' + queue : '/api/queue/pause'),
    resume: (queue?: string) => post<ApiResponse<any>>(queue ? '/api/queue/resume/' + queue : '/api/queue/resume'),
    config: (max_workers: number, queue?: string) => post<ApiResponse<any>>('/api/queue/config' + buildQuery({ max_workers, queue })),
    autoConfig: (queue?: string) => post<ApiResponse<any>>('/api/queue/config' + buildQuery({ auto: true, queue })),
    detect: () => get<ApiResponse<any>>('/api/queue/detect'),
  },
  invite: {
    myCode: () => get<ApiResponse<{ invite_code: string; invite_link: string; total_reward: number; invite_count: number }>>('/api/invite/my-code'),
    rank: (period?: string) => get<ApiResponse<{ period: string; items: { user_id: string; nickname: string; invite_count: number; total_reward: number }[] }>>('/api/invite/rank' + (period ? '?period=' + period : '')),
  },
  adminCrack: {
    rules: () => get<ApiResponse<any>>('/api/admin/crack/rules'),
    updateRules: (rules: any) => put<ApiResponse<any>>('/api/admin/crack/rules', rules),
    inviteRewardRate: (rate: number) => post<ApiResponse<any>>('/api/admin/crack/invite-reward-rate', { rate }),
  },
  adminConfig: {
    all: () => get<ApiResponse<Record<string, string>>>('/api/admin/config'),
    set: (key: string, value: string) => post<ApiResponse<any>>('/api/admin/config', { key, value }),
    testDeepseek: (model?: string) => post<ApiResponse<any>>('/api/admin/config/test-deepseek', { model: model || 'deepseek-chat' }),
  },
  adminAds: {
    list: () => get<ApiResponse<AdItem[]>>('/api/admin/ads'),
    create: (d: { slot: number; name: string; html_content: string }) => post<ApiResponse<any>>('/api/admin/ads', d),
    update: (id: number, d: { name?: string; html_content?: string; is_active?: number }) => put<ApiResponse<any>>(`/api/admin/ads/${id}`, d),
    delete: (id: number) => del<ApiResponse<any>>(`/api/admin/ads/${id}`),
  },
  ads: {
    listPublic: () => get<ApiResponse<AdPublicItem[]>>('/api/ads'),
  },
  proxy: {
    get: () => get<ApiResponse<{enabled:boolean;url:string;username:string;password:string}>>('/api/admin/proxy'),
    save: (d: {enabled:boolean;url:string;username:string;password:string}) => post<ApiResponse<any>>('/api/admin/proxy', d),
    test: (d: {enabled:boolean;url:string;username:string;password:string}) => post<ApiResponse<any>>('/api/admin/proxy/test', d),
  },
  adminDomainMonitor: {
    status: () => get<ApiResponse<{ known_domains: Record<string, {name:string;url:string;discovered_at:string;source:string}>; last_check: string; last_change: string; interval: number; school_url: string }>>('/api/admin/domain-monitor/status'),
    check: () => post<ApiResponse<{ checked_at: string; found: any[]; new_domains: any[]; changed_domains: any[]; errors: string[] }>>('/api/admin/domain-monitor/check'),
    add: (d: { domain: string; name: string; url: string }) => post<ApiResponse<any>>('/api/admin/domain-monitor/add', d),
    remove: (domain: string) => post<ApiResponse<any>>('/api/admin/domain-monitor/remove', { domain }),
    setInterval: (interval: number) => post<ApiResponse<any>>('/api/admin/domain-monitor/interval', { interval }),
    jsStatus: () => get<ApiResponse<{ files: {url:string;hash:string}[]; total: number; last_check: string; last_change: string }>>('/api/admin/domain-monitor/js-status'),
    jsCheck: () => post<ApiResponse<{ checked_at: string; changes: any[]; errors: string[]; files_checked: number }>>('/api/admin/domain-monitor/js-check'),
    health: () => get<ApiResponse<{ checked_at: string; platforms: {domain:string;name:string;url:string;reachable:boolean;status_code:number;response_time_ms:number;error:string}[] }>>('/api/admin/domain-monitor/health'),
    alerts: (limit?: number) => get<ApiResponse<{ time:string;type:string;message:string;domain:string }[]>>('/api/admin/domain-monitor/alerts' + (limit ? '?limit=' + limit : '')),
    clearAlerts: () => post<ApiResponse<any>>('/api/admin/domain-monitor/alerts/clear'),
  },
  pricing: {
    get: () => get<ApiResponse<{
      videoUnitPrice: number; examUnitPrice: number; homeworkUnitPrice: number;
      pricingMode: string;
      priceSmall: number; priceMedium: number; priceLarge: number;
      discount25: number; discount50: number; discount75: number;
      priceMinimum: number;
      priceExamOnly: number; priceHomeworkOnly: number;
      priceChaoxing: number;
    }>>('/api/pricing'),
    recommend: (d: { avg_price: number; max_price: number; min_price?: number; my_cost_per_course?: number; extra_info?: string }) =>
      post<ApiResponse<{
        recommended: { priceSmall: number; priceMedium: number; priceLarge: number; discount25: number; discount50: number; discount75: number; priceMinimum: number; priceExamOnly: number; priceHomeworkOnly: number; videoUnitPrice: number; examUnitPrice: number; homeworkUnitPrice: number };
        market: { avg: number; max: number; min: number; your_cost: number };
        analysis: { strategy: string; scenarios: { course: string; videos: number; progress: string; competitor: string; your_price: string; note: string }[]; ai_powered: boolean };
      }>>('/api/pricing/recommend', d),
    applyPackage: (d: Record<string, number>) => post<ApiResponse<any>>('/api/pricing/apply-package', d),
    calculate: (d: { courses: { course_id: string; video_total: number; video_completed: number; exam_total: number; exam_done: number; homework_total: number; homework_done: number }[] }) =>
      post<ApiResponse<{ courses: { course_id: string; type: string; price: number; label: string }[]; total: number; pricing_mode: string }>>('/api/pricing/calculate', d),
  },
  subAdmin: {
    stats: () => get<ApiResponse<any>>('/api/sub-admin/stats'),
    orders: {
      list: (params?: { status?: string; limit?: number; offset?: number }) =>
        get<ApiResponse<{ total: number; items: any[] }>>('/api/sub-admin/orders' + buildQuery(params)),
      accept: (id: string) => post<ApiResponse<any>>('/api/sub-admin/orders/' + id + '/accept'),
      complete: (id: string) => post<ApiResponse<any>>('/api/sub-admin/orders/' + id + '/complete'),
      fail: (id: string, note?: string) => post<ApiResponse<any>>('/api/sub-admin/orders/' + id + '/fail?admin_note=' + (note || '')),
    },
    agents: {
      list: (params?: { status?: string; limit?: number; offset?: number }) =>
        get<ApiResponse<{ total: number; items: any[] }>>('/api/sub-admin/agents' + buildQuery(params)),
      approve: (id: string) => post<ApiResponse<any>>('/api/sub-admin/agents/' + id + '/approve'),
      suspend: (id: string) => post<ApiResponse<any>>('/api/sub-admin/agents/' + id + '/suspend'),
      reactivate: (id: string) => post<ApiResponse<any>>('/api/sub-admin/agents/' + id + '/reactivate'),
      setTier: (id: string, tierLevel: number) => put<ApiResponse<any>>('/api/sub-admin/agents/' + id + '/tier', { tier_level: tierLevel }),
      setRate: (id: string, commissionRate: number) => put<ApiResponse<any>>('/api/sub-admin/agents/' + id + '/commission-rate', { commission_rate: commissionRate }),
      updateInfo: (id: string, d: { display_name?: string; contact?: string; welcome_text?: string }) => put<ApiResponse<any>>('/api/sub-admin/agents/' + id + '/info', d),
    },
    agentFees: {
      get: () => get<ApiResponse<any>>('/api/sub-admin/agent-fees'),
      set: (d: any) => put<ApiResponse<any>>('/api/sub-admin/agent-fees', d),
    },
    commissions: {
      list: (params?: { agent_id?: string; limit?: number; offset?: number }) =>
        get<ApiResponse<{ total: number; items: any[] }>>('/api/sub-admin/commissions' + buildQuery(params)),
    },
    withdrawals: {
      list: (params?: { status?: string; limit?: number; offset?: number }) =>
        get<ApiResponse<{ total: number; items: any[] }>>('/api/sub-admin/withdrawals' + buildQuery(params)),
      approve: (id: string) => post<ApiResponse<any>>('/api/sub-admin/withdrawals/' + id + '/approve'),
      reject: (id: string) => post<ApiResponse<any>>('/api/sub-admin/withdrawals/' + id + '/reject'),
    },
  },
  ypay: {
    regenerateKey: () => post<ApiResponse<{ key: string }>>('/api/ypay/regenerate-key'),
    clearOrders: () => post<ApiResponse<any>>('/api/ypay/clear-orders'),
    accounts: {
      list: () => get<ApiResponse<any[]>>('/api/ypay/accounts'),
      create: (d: any) => post<ApiResponse<any>>('/api/ypay/accounts', d),
      update: (id: number, d: any) => put<ApiResponse<any>>(`/api/ypay/accounts/${id}`, d),
      delete: (id: number) => del<ApiResponse<any>>(`/api/ypay/accounts/${id}`),
    },
    channelTest: (id: number) => post<ApiResponse<any>>(`/api/ypay/channel-test/${id}`),
    config: {
      get: () => get<ApiResponse<any>>('/api/ypay/config/get'),
      save: (d: any) => post<ApiResponse<any>>('/api/ypay/config/save', d),
    },
    status: () => get<ApiResponse<any>>('/api/ypay/status'),
    appQrcode: () => get<ApiResponse<any>>('/api/ypay/app-qrcode'),
    orders: {
      list: (params?: { page?: number; limit?: number; status?: number | null }) =>
        get<ApiResponse<{ items: any[]; total: number }>>('/api/ypay/orders' + buildQuery(params as any)),
    },
    closeExpired: () => post<ApiResponse<any>>('/api/ypay/close-expired'),
    payTest: {
      create: (id: number) => post<ApiResponse<any>>(`/api/ypay/pay-test/create/${id}`),
      check: (batchId: string, params?: Record<string, string>) =>
        get<ApiResponse<any>>(`/api/ypay/pay-test/check/${batchId}` + buildQuery(params)),
    },
    diagnose: () => get<ApiResponse<any>>('/api/ypay/diagnose'),
    resetConnection: () => post<ApiResponse<any>>('/api/ypay/reset-connection'),
    decodeQr: async (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      const res = await fetch('/api/ypay/decode-qr', { method: 'POST', body: fd })
      return res.json()
    },
  },
  setup: {
    status: () => get<ApiResponse<{ done: boolean }>>('/api/setup/status'),
    check: () => get<ApiResponse<{ all_ok: boolean; checks: { category: string; items: { name: string; status: string; msg: string; ok: boolean }[] }[]; setup_done: boolean }>>('/api/setup/check'),
    initDb: () => post<ApiResponse<{ success: boolean; message: string }>>('/api/setup/init-db'),
    saveConfig: (d: { site_url?: string; jwt_secret?: string; db_url?: string; redis_url?: string }) => post<ApiResponse<{ success: boolean; message: string }>>('/api/setup/save-config', d),
    createAdmin: (d: { username: string; password: string }) => post<ApiResponse<{ success: boolean; message: string }>>('/api/setup/create-admin', d),
    saveYpay: (d: { ypay_key?: string }) => post<ApiResponse<{ success: boolean; message: string }>>('/api/setup/save-ypay', d),
    saveVmq: (d: { vmq_key?: string }) => post<ApiResponse<{ success: boolean; message: string }>>('/api/setup/save-vmq', d),
    finish: () => post<ApiResponse<{ success: boolean; message: string }>>('/api/setup/finish'),
    testDb: (d: { user: string; password: string; database: string }) => post<ApiResponse<{ success: boolean; message: string; db_url?: string }>>('/api/setup/test-db', d),
    saveDb: (d: { user: string; password: string; database: string }) => post<ApiResponse<{ success: boolean; message: string }>>('/api/setup/save-db', d),
  },
  app: {
    info: () => get<ApiResponse<{ app_name: string; version: string; apk_exists: boolean; apk_size_mb: number; download_url: string }>>('/api/app/info'),
    pairQrcode: () => get<ApiResponse<{ pair_data: string; qr_image: string | null; download_url: string; host: string; port: number }>>('/api/app/pair-qrcode'),
    pairStatus: () => get<ApiResponse<{ paired: boolean }>>('/api/app/pair-status'),
    downloadUrl: () => '/api/app/download',
  },
  captcha: {
    generate: () => get<ApiResponse<{ token: string; image: string }>>('/api/captcha/generate'),
  },
  announcement: {
    get: () => get<ApiResponse<{ id: number; content: string; active: boolean }>>('/api/announcement'),
    set: (content: string) => post<ApiResponse<{ id: number }>>('/api/admin/announcement', { content }),
    disable: () => post<ApiResponse<any>>('/api/admin/announcement/disable'),
  },
  healthMonitor: {
    summary: () => get<ApiResponse<{ status: string; check_time: string; website: string; checks: Record<string, { status: string; message: string }> }>>('/api/health/summary'),
    check: (websiteId: number) => post<ApiResponse<{ website_id: number; website_name: string; check_time: string; checks: Record<string, { status: string; message: string; [k: string]: any }>; overall: string }>>(`/api/health/check/${websiteId}`),
    checkAll: () => post<ApiResponse<Record<number, any>>>('/api/health/check/all'),
    getInterval: () => get<ApiResponse<{ interval: number }>>('/api/health/interval'),
    setInterval: (interval: number) => put<ApiResponse<{ interval: number }>>('/api/health/interval', { interval }),
    getAccount: () => get<ApiResponse<{ accounts: { username: string; password: string; active: boolean }[] }>>('/api/health/account'),
    setAccount: (username: string, password: string, website_type: string = 'school') => put<ApiResponse>('/api/health/account', { username, password, website_type }),
    setAccounts: (accounts: { username: string; password: string; active: boolean }[]) => put<ApiResponse>('/api/health/accounts', { accounts }),
  },
}

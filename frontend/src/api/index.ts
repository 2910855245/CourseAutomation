const API_BASE = ''

let adminToken = ''
export function setAdminApiToken(t: string) { adminToken = t }


const FETCH_TIMEOUT_MS = 30000  // 30 秒超时，防止按钮永久卡住

// 邀请落地：分享链接是 /?ref=<邀请码>，但路由是 hash 模式，后端中间件只看得到
// API 请求（前端地址栏的 query 它看不到）。所以由落地后的第一个 API 请求代转一次，
// 之后清空，避免后续每个请求都重复上报。
const refCode = (() => {
  try {
    const v = new URLSearchParams(location.search).get('ref') || ''
    return /^[A-Za-z0-9]{4,32}$/.test(v) ? v : ''
  } catch { return '' }
})()
let refPending = !!refCode

function withRef(path: string): string {
  if (!refPending) return path
  return path + (path.includes('?') ? '&' : '?') + 'ref=' + encodeURIComponent(refCode)
}

async function request<T = any>(method: string, path: string, body?: any): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const adminOnlyPrefixes = ['/api/admin', '/api/queue', '/api/ypay', '/api/health']
  if (adminOnlyPrefixes.some(p => path.startsWith(p)) && adminToken) {
    headers['Authorization'] = `Bearer ${adminToken}`
  } else if (adminToken) {
    headers['Authorization'] = `Bearer ${adminToken}`
  }
  const opts: RequestInit = { method, headers }
  if (body && method !== 'GET') opts.body = JSON.stringify(body)

  const controller = new AbortController()
  opts.signal = controller.signal
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
  try {
    const res = await fetch(API_BASE + withRef(path), opts)
    // 请求已到过服务端（后端在中间件里就先记账，与 handler 成败无关），不必再带
    refPending = false
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
export interface CourseItem { course_id: string; course_name: string; detail_link: string; study_record_url: string; video_total: number; video_completed: number; video_pending: number; video_actionable: number; exam_total: number; exam_done: number; exam_deleted: number; exam_missed: number; exam_actionable: number; exam_pending: number; homework_total: number; homework_done: number; records_loaded: boolean; has_points_system?: boolean; points_total?: number; points_video?: number; points_remaining?: number; days_needed?: number; study_days?: number; total_minutes?: number; work_total?: number; work_pending?: number; work_completed?: number; /** 学习通：课程是否不在有效学习时间内（过期后平台关闭一切学习入口） */ course_ended?: boolean; begin_date?: string; end_date?: string }
export interface OrderItem {
  order_id: string; out_trade_no?: string; ezfpy_trade_no?: string; payment_trade_no?: string;
  payment_channel?: string; payment_time?: string; paid_processed?: string;
  user_id: string; username: string; password: string;
  customer_name?: string; customer_contact?: string;
  website_id: number; task_type: string; course_ids: string[];
  video_count: number; price: number; status: string; paid?: boolean;
  progress?: number; task_id?: string; admin_note?: string; exam_count?: number;
  /** 队列当前步骤（如"已刷 12/40 节"），由查单接口从队列任务注入 */
  current_step_name?: string;
  /** 刷课节奏档位：turbo 暴力 / gentle 保守（balanced 已下线，仅历史订单存在） */
  speed_mode?: string;
  created_at: string; updated_at?: string; accepted_at?: string; started_at?: string; finished_at?: string;
}
export interface DashboardAlert {
  level: 'info' | 'warn' | 'danger'
  title: string
  detail: string
}
export interface DashboardStats {
  orders: {
    total: number; today: number; yesterday: number; week: number
    completed: number; pending: number; running: number; failed: number
    cancelled: number; paid: number
    completion_rate: number; avg_delivery_hours: number
    stuck: number; long_running: number
    /** 今日环比昨日（昨日为 0 时后端返回 null，避免除零） */
    today_change: number | null
    today_diff: number
  }
  revenue: {
    total: number; today: number; yesterday: number; week: number
    receivable: number; refund_due: number; avg_order: number
    today_change: number | null; today_diff: number
  }
  queue: {
    enabled: boolean; paused: boolean
    /** 双通道分开：付费池与免费额度上限不同，占用率各自算 */
    paid: { active_workers: number; max_workers: number }
    free: { active_workers: number; max_workers: number }
    pending: number; retrying: number; running: number
    waiting: number; failed: number; completed: number
    backlog_minutes: number
  }
  ai: {
    today: {
      calls: number; ok: number; prompt_tokens: number; completion_tokens: number
      cache_hit_tokens: number; cost: number; cache_hit_rate: number; success_rate: number
    }
    total: { calls: number; ok: number; prompt_tokens: number; completion_tokens: number; cache_hit_tokens: number; cost: number }
    by_scene: { scene: string; calls: number; cost: number }[]
  }
  alerts: DashboardAlert[]
  platform_distribution: { website_id: number; count: number; revenue: number }[]
  task_type_distribution: { task_type: string; count: number; revenue: number }[]
  status_distribution: { status: string; count: number }[]
  recent_7_days: { date: string; orders: number; revenue: number; failed: number; ai_calls: number; ai_cost: number }[]
  recent_orders: { order_id: string; username: string; website_id: number; task_type: string; price: number; status: string; created_at: string; paid: boolean }[]
}

/** 域名监控快照（只含 3 个教学平台；首页其余链接不入库） */
export interface DomainMonitorData {
  platforms: { website_id: number; name: string; host: string; base_url: string; is_primary: boolean; is_alias: boolean; reachable: number }[]
  last_check: number
  last_status: string
  interval_hours: number
  monitor_url: string
}


export const api = {
  // 营销推广：免费待遇 / 邀请 / 刷课卡（身份由服务端 cookie 承载，前端不传标识）
  me: {
    benefit: () => get<ApiResponse<any>>('/api/me/benefit'),
  },
  invite: {
    me: () => get<ApiResponse<any>>('/api/invite/me'),
    claim: (contact: string) => post<ApiResponse<any>>('/api/invite/claim', { contact }),
  },
  // 学期卡：建单只拿到 order_id，收款复用 /api/payment/batch-create（同一单号）
  pass: {
    create: () => post<ApiResponse<{ order_id: string; price: number; days: number }>>('/api/promo/pass/create'),
  },
  adminPromo: {
    stats: () => get<ApiResponse<any>>('/api/admin/promo/stats'),
  },
  // 域名监控：平台域名/名称由学校首页自动抓取纠正，域名一换即时生效
  adminDomain: {
    get: () => get<ApiResponse<DomainMonitorData>>('/api/admin/domain-monitor'),
    check: () => post<ApiResponse<any>>('/api/admin/domain-monitor/check'),
    setInterval: (hours: number) => post<ApiResponse<{ interval_hours: number }>>('/api/admin/domain-monitor/interval', { hours }),
  },
  courses: {
    platforms: () => get<ApiResponse<{ id: number; name: string; base_url: string }[]>>('/api/courses/platforms'),
    scan: (d: { username: string; password: string; include_records: boolean }) => post<ApiResponse<{ platforms: PlatformResult[] }>>('/api/courses/scan', d),
    scanChaoxing: (d: { username: string; password: string }) => post<ApiResponse<{ platform: PlatformResult }>>('/api/courses/scan/chaoxing', d),
    relogin: (d: { username: string; password: string; website_id: number; include_records: boolean }) => post<ApiResponse<{ platform: PlatformResult }>>('/api/courses/relogin', d),
  },
  orders: {
    // 后端逐单分流：free_order_ids 是 0 元、已直接开跑的（只剩视频要刷）；
    // payable_order_ids 是要付款才能跑的（含未完成的考试/作业）
    batch: (d: { username: string; password: string; orders: any[] }) =>
      post<ApiResponse<{
        orders: any[]; free_order_ids: string[]; payable_order_ids: string[]
        total_price: number; paid: boolean; free: boolean; free_reason: string
      }>>('/api/orders/batch', d),
    get: (id: string, token?: string) => get<ApiResponse<OrderItem>>('/api/orders/' + id + (token ? '?token=' + encodeURIComponent(token) : '')),
    cancel: (id: string, token?: string) => del<ApiResponse<any>>('/api/orders/' + id + (token ? '?token=' + encodeURIComponent(token) : '')),
    clearHistory: () => post<ApiResponse<any>>('/api/orders/clear-history'),
    activeCourses: (username: string) => get<ApiResponse<string[]>>('/api/orders/active-courses?username=' + encodeURIComponent(username)),
  },
  payment: {
    batchCreate: (d: { order_ids: string[]; pay_type?: number }) =>
      post<ApiResponse<{ mode: string; batch_id: string; trade_no: string; out_trade_no: string; order_ids: string[]; pay_url: string; total_price: number; really_price: number; pay_type: number; qr_image: string | null }>>('/api/payment/batch-create', d),
    batchCheck: (batch_id: string, out_trade_no?: string, token?: string) => {
      const params = new URLSearchParams()
      if (out_trade_no) params.set('out_trade_no', out_trade_no)
      if (token) params.set('token', token)
      const q = params.toString() ? '?' + params.toString() : ''
      return get<ApiResponse<{ paid: boolean; paid_count?: number; message: string; expired?: boolean }>>('/api/payment/batch-check/' + batch_id + q)
    },
  },
  admin: {
    login: (d: { username: string; password: string }) => post<ApiResponse<any>>('/api/admin/login', d),
    dashboard: () => get<ApiResponse<DashboardStats>>('/api/admin/dashboard'),
    changePassword: (d: { old_password: string; new_password: string }) => post<ApiResponse<any>>('/api/admin/change-password', d),
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
    freeConfig: (free_max_workers: number) => post<ApiResponse<any>>('/api/queue/config' + buildQuery({ free_max_workers })),
    autoConfig: (queue?: string) => post<ApiResponse<any>>('/api/queue/config' + buildQuery({ auto: true, queue })),
    detect: () => get<ApiResponse<any>>('/api/queue/detect'),
  },
  adminConfig: {
    all: () => get<ApiResponse<Record<string, string>>>('/api/admin/config'),
    set: (key: string, value: string) => post<ApiResponse<any>>('/api/admin/config', { key, value }),
    testDeepseek: (model?: string) => post<ApiResponse<any>>('/api/admin/config/test-deepseek', { model: model || 'deepseek-flash' }),
  },
  // 运行日志：默认读内存环形缓冲（实时、最快），source='db' 回看持久层
  adminLogs: {
    list: (params?: { category?: string; level?: string; order_id?: string; before?: number; limit?: number; source?: string }) =>
      get<ApiResponse<{ items: any[]; source: string; stats?: any }>>('/api/admin/logs' + buildQuery(params)),
    stats: () => get<ApiResponse<any>>('/api/admin/logs/stats'),
    clear: () => post<ApiResponse<any>>('/api/admin/logs/clear'),
  },
  // 说明：proxy（3 个）与 adminDomainMonitor（8 个）两段已删除 ——
  // 后端从未注册这些路由，对应的两个后台页面（网络代理 / 风险监控）
  // 已一并移除，避免留下「点了必然 404」的死接口定义。
  pricing: {
    // 刷视频免费后只剩三档收费（视频打包价/进度折扣已下线）
    get: () => get<ApiResponse<{
      priceExamOnly: number; priceHomeworkOnly: number;
      priceChaoxing: number;
    }>>('/api/pricing'),
    applyPackage: (d: Record<string, number>) => post<ApiResponse<any>>('/api/pricing/apply-package', d),
    // username：服务端据此回查自己扫描时留下的快照（定价事实只认快照，
    // 客户端传的明细仅作老调用兜底）；website_id 让服务端知道该查哪个平台的快照
    calculate: (d: { username?: string; courses: { course_id: string; website_id?: number; video_total: number; video_completed: number; exam_total: number; exam_done: number; homework_total: number; homework_done: number }[] }) =>
      post<ApiResponse<{ courses: { course_id: string; type: string; price: number; label: string }[]; total: number; pricing_mode: string }>>('/api/pricing/calculate', d),
  },
  ypay: {
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
    // resetConnection 已删除：服务端不保存 APP 会话状态，
    // 该接口只能返回"无可重置"，按钮已从「支付收款」页移除
    decodeQr: async (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      const res = await fetch('/api/ypay/decode-qr', { method: 'POST', body: fd })
      return res.json()
    },
  },
  // 说明：captcha 段已删除 —— 后端从无 /api/captcha/generate，
  // 且 admin_login 明确不校验验证码；登录表单里的验证码字段属假交互。
  announcement: {
    get: () => get<ApiResponse<{
      id: number; content: string; active: boolean
      title?: string; image?: string; contact_type?: string; contact_value?: string
    }>>('/api/announcement'),
    set: (content: string, extra?: { title?: string; image?: string; contact_type?: string; contact_value?: string }) =>
      post<ApiResponse<{ id: number }>>('/api/admin/announcement', { content, ...(extra || {}) }),
    disable: () => post<ApiResponse<any>>('/api/admin/announcement/disable'),
  },
}

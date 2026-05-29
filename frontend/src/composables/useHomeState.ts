// Home.vue 完整状态管理：扫描、课程选择、定价、支付、角色检测
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { api, type PlatformResult, type CourseItem } from '@/api'

export function useHomeState() {
  const store = useAppStore()
  const route = useRoute()

  // ── Role detection ──
  const userRole = ref<'admin' | 'sub_admin' | 'agent' | null>(null)
  const isPrivileged = computed(() => !!userRole.value)
  const isRegularUser = ref(false)
  const UPGRADE_BANNER_KEY = 'hide_upgrade_banner'
  const showUpgradeBanner = ref(localStorage.getItem(UPGRADE_BANNER_KEY) !== '1')
  function dismissUpgradeBanner() {
    showUpgradeBanner.value = false
    localStorage.setItem(UPGRADE_BANNER_KEY, '1')
  }

  async function detectUserRole() {
    // 管理员在后台登录后，adminToken 已存入 localStorage
    // store 初始化时会自动 setAdminApiToken，所以 api.users.me() 会带上 admin token
    if (store.isAdminLoggedIn) {
      userRole.value = 'admin'
      return
    }
    if (store.isUserLoggedIn) {
      try {
        const r = await api.users.me()
        const role = r?.data?.role
        if (role === 'admin') { userRole.value = 'admin'; return }
        if (role === 'sub_admin') { userRole.value = 'sub_admin'; return }
        if (r?.data?.agent) { userRole.value = 'agent'; return }
        isRegularUser.value = true
      } catch {}
    }
  }

  function handleVisibilityChange() {
    if (document.visibilityState === 'visible') detectUserRole()
  }

  // ── Session persistence ──
  const LS_KEY = 'course_platform_remember'

  interface SavedData { username: string; password?: string; scanData: PlatformResult[]; scanDone: boolean; checkedIds: string[]; pkgIdx: number; ts: number }

  function loadSaved(): SavedData | null {
    try {
      const raw = localStorage.getItem(LS_KEY)
      if (!raw) return null
      const data = JSON.parse(raw) as SavedData
      if (!data || typeof data !== 'object') { localStorage.removeItem(LS_KEY); return null }
      if (!data.username || !data.ts) { localStorage.removeItem(LS_KEY); return null }
      if (Date.now() - data.ts > 7 * 24 * 3600 * 1000) { localStorage.removeItem(LS_KEY); return null }
      if (!Array.isArray(data.scanData)) { data.scanData = []; data.scanDone = false }
      return data
    } catch { localStorage.removeItem(LS_KEY); return null }
  }

  function saveSession() {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify({
        username: username.value.trim(), password: password.value, scanData: scanData.value, scanDone: scanDone.value,
        checkedIds: [...checkedCourseIds.value], ts: Date.now(),
      }))
    } catch {}
  }

  function clearSaved() {
    localStorage.removeItem(LS_KEY); savedData.value = null
    scanData.value = []; scanDone.value = false; checkedCourseIds.value = new Set()
    password.value = ''
  }

  // ── Scan state ──
  const savedData = ref<SavedData | null>(loadSaved())
  const username = ref(savedData.value?.username || '')
  const password = ref(savedData.value?.password || '')
  const scanning = ref(false)
  const activeTab = ref<'school' | 'chaoxing'>('school')
  const chaoxingUsername = ref('')
  const chaoxingPassword = ref('')
  const rescanning = ref(false)
  const scanDone = ref(savedData.value?.scanDone || false)
  const allDone = ref(false)
  const isLeaving = ref(false)
  const scanData = ref<PlatformResult[]>(savedData.value?.scanData || [])
  const countdown = ref(3)
  const loginError = ref<'all' | 'partial' | null>(null)
  const failedPlatforms = ref<{ website_id: number; name: string; error: string }[]>([])
  const reloginDialog = ref<{ visible: boolean; website_id: number; name: string }>({ visible: false, website_id: 0, name: '' })
  const reloginPassword = ref('')
  const reloginLoading = ref(false)
  const loginErrorCountdown = ref(3)
  let loginErrorTimer: any = null
  let countdownTimer: any = null

  const packagePricing = ref({
    priceSmall: 3, priceMedium: 5, priceLarge: 6,
    discount25: 0.7, discount50: 0.5, discount75: 0.3, priceMinimum: 2,
    priceExamOnly: 5, priceHomeworkOnly: 3, priceChaoxing: 8,
  })

  async function loadPackagePricing() {
    try {
      const res = await api.pricing.get()
      const d = res.data as any
      if (d) {
        packagePricing.value = {
          priceSmall: d.priceSmall ?? 3,
          priceMedium: d.priceMedium ?? 5,
          priceLarge: d.priceLarge ?? 6,
          discount25: d.discount25 ?? 0.7,
          discount50: d.discount50 ?? 0.5,
          discount75: d.discount75 ?? 0.3,
          priceMinimum: d.priceMinimum ?? 2,
          priceExamOnly: d.priceExamOnly ?? 5,
          priceHomeworkOnly: d.priceHomeworkOnly ?? 3,
          priceChaoxing: d.priceChaoxing ?? 8,
        }
      }
    } catch {}
  }
  loadPackagePricing()

  const submittedCourseIds = ref(new Set<string>())
  const allInProgress = ref(false)
  const pendingOrderedCourseIds = ref<string[]>([])
  const checkedCourseIds = ref(new Set<string>(savedData.value?.checkedIds || []))

  function isCourseDone(c: CourseItem): boolean {
    // 学习通：积分达标 且 无待完成作业
    if (c.has_points_system !== undefined) {
      const pointsOk = !c.has_points_system || ((c.points_remaining ?? 0) <= 0)
      const workOk = (c.work_pending ?? 0) <= 0
      return pointsOk && workOk
    }
    // 学校平台：视频完成 且 考试完成
    return c.video_pending === 0 && (c.exam_total === 0 || c.exam_done >= c.exam_total)
  }

  function isCourseDoneOrSubmitted(c: CourseItem): boolean {
    return isCourseDone(c) || submittedCourseIds.value.has(c.course_id)
  }

  const visiblePlatforms = computed(() => scanData.value.filter(p => p.courses.length > 0 && p.courses.some(c => !isCourseDoneOrSubmitted(c))))

  function togglePlatform(wid: number, checked: boolean) {
    const platform = scanData.value.find(p => p.website_id === wid)
    if (!platform) return
    for (const c of platform.courses) {
      if (checked && !isCourseDoneOrSubmitted(c)) checkedCourseIds.value.add(c.course_id)
      else checkedCourseIds.value.delete(c.course_id)
    }
    saveSession(); fetchBackendPrices()
  }

  function toggleCourse(cid: string) {
    if (checkedCourseIds.value.has(cid)) checkedCourseIds.value.delete(cid)
    else checkedCourseIds.value.add(cid)
    saveSession(); fetchBackendPrices()
  }

  function isPlatformAllChecked(platform: PlatformResult): boolean {
    const pendings = platform.courses.filter(c => !isCourseDoneOrSubmitted(c))
    return pendings.length > 0 && pendings.every(c => checkedCourseIds.value.has(c.course_id))
  }

  // ── Pricing ──
  function calcCoursePrice(c: { video_total: number; video_completed: number; exam_total?: number; exam_done?: number }): number {
    const pkg = packagePricing.value
    if (c.video_total <= 0) {
      if ((c.exam_total ?? 0) > 0) return pkg.priceExamOnly || 5
      return 0
    }
    let base: number
    if (c.video_total <= 30) base = pkg.priceSmall
    else if (c.video_total <= 80) base = pkg.priceMedium
    else base = pkg.priceLarge
    const progress = c.video_completed / c.video_total * 100
    let coeff: number
    if (progress <= 25) coeff = 1.0
    else if (progress <= 50) coeff = pkg.discount25
    else if (progress <= 75) coeff = pkg.discount50
    else coeff = pkg.discount75
    return Math.max(pkg.priceMinimum, Math.round(base * coeff * 100) / 100)
  }

  const backendPrices = ref<Record<string, { price: number; type: string; label: string }>>({})
  const loadingPrices = ref(false)

  async function fetchBackendPrices() {
    const courses: { course_id: string; video_total: number; video_completed: number; exam_total: number; exam_done: number; exam_actionable: number; homework_total: number; homework_done: number }[] = []
    for (const p of scanData.value) {
      for (const c of p.courses) {
        if (checkedCourseIds.value.has(c.course_id)) {
          courses.push({
            course_id: c.course_id, video_total: c.video_total, video_completed: c.video_completed,
            exam_total: c.exam_total, exam_done: c.exam_done, exam_actionable: c.exam_actionable ?? 0,
            homework_total: c.homework_total || 0, homework_done: c.homework_done || 0,
          })
        }
      }
    }
    if (courses.length === 0) return
    loadingPrices.value = true
    try {
      const res = await api.pricing.calculate({ courses })
      if (res.data?.courses) {
        const map: Record<string, { price: number; type: string; label: string }> = {}
        for (const item of res.data.courses) map[item.course_id] = { price: item.price, type: item.type, label: item.label }
        backendPrices.value = map
      }
    } catch {} finally { loadingPrices.value = false }
  }

  const summary = computed(() => {
    let courses = 0, videos = 0, exams = 0, totalPrice = 0
    const courseBreakdown: { name: string; videos: number; completed: number; price: number }[] = []
    for (const p of scanData.value) {
      for (const c of p.courses) {
        if (checkedCourseIds.value.has(c.course_id)) {
          courses++; videos += c.video_pending
          const ePending = Math.max(0, c.exam_total - c.exam_done)
          if (ePending > 0) exams += ePending
          const bp = backendPrices.value[c.course_id]
          const price = bp ? bp.price : 0
          totalPrice += price
          courseBreakdown.push({ name: c.course_name, videos: c.video_total, completed: c.video_completed, price })
        }
      }
    }
    return { courses, videos, exams, total: totalPrice, breakdown: courseBreakdown }
  })

  const scenario = computed(() => {
    const { videos, exams } = summary.value
    if (videos === 0 && exams > 0) return 'onlyExams' as const
    if (videos > 0 && exams === 0) return 'onlyVideos' as const
    if (videos > 0 && exams > 0) return 'both' as const
    return 'none' as const
  })

  const currentPrices = computed(() => {
    const pkg = packagePricing.value
    return { priceSmall: pkg.priceSmall, priceMedium: pkg.priceMedium, priceLarge: pkg.priceLarge, discount25: pkg.discount25, discount50: pkg.discount50, discount75: pkg.discount75, priceMinimum: pkg.priceMinimum, priceChaoxing: pkg.priceChaoxing }
  })

  const studentName = computed(() => {
    for (const p of scanData.value) { if (p.student_name) return p.student_name }
    return ''
  })

  const chaoxingInfo = computed(() => {
    const p = scanData.value.find(p => p.website_id === 4)
    if (!p || p.status !== 'ok') return null
    return {
      name: p.student_name || '',
      school: p.school_name || '',
      studentCode: p.student_code || '',
      pointsTotal: p.points_total || 0,
      pointsTarget: p.points_target || 200,
      courseCount: p.courses?.length || 0,
      pendingCount: p.courses?.filter(c => !isCourseDoneOrSubmitted(c)).length || 0,
      workPending: p.courses?.reduce((s, c) => s + (c.work_pending || 0), 0) || 0,
    }
  })

  const chaoxingServiceType = computed(() => {
    const p = scanData.value.find(p => p.website_id === 4)
    if (!p || p.status !== 'ok') return null
    const hasPoints = p.courses.some(c => (c.points_remaining ?? 0) > 0)
    const hasWork = p.courses.some(c => (c.work_pending ?? 0) > 0)
    if (hasPoints && hasWork) return 'both'
    if (hasWork) return 'work'
    if (hasPoints) return 'points'
    return 'done'
  })

  // ── Scan logic ──
  async function startScan() {
    if (!username.value.trim() || !password.value.trim()) { store.toast('请输入学号和密码', 'warning'); return }
    if (countdownTimer) clearInterval(countdownTimer)
    if (loginErrorTimer) { clearInterval(loginErrorTimer); loginErrorTimer = null }
    scanning.value = true; submitSuccess.value = false; allDone.value = false
    loginError.value = null; failedPlatforms.value = []; countdown.value = 3; loginErrorCountdown.value = 3
    try {
      const res = await api.courses.scan({ username: username.value.trim(), password: password.value.trim(), include_records: true })
      scanData.value = res.data.platforms
      const okPlatforms = scanData.value.filter(p => p.status === 'ok')
      const failed = scanData.value.filter(p => p.status !== 'ok')
      if (okPlatforms.length === 0) {
        loginError.value = 'all'
        failedPlatforms.value = failed.map(p => ({ website_id: p.website_id, name: p.name, error: p.error || '登录失败' }))
        loginErrorCountdown.value = 3
        loginErrorTimer = setInterval(() => { loginErrorCountdown.value--; if (loginErrorCountdown.value <= 0) { clearInterval(loginErrorTimer); loginErrorTimer = null; resetScan() } }, 1000)
        return
      }
      if (failed.length > 0) {
        failedPlatforms.value = failed.map(p => ({ website_id: p.website_id, name: p.name, error: p.error || '登录失败' }))
        const failMsg = failed.map(p => `${p.name}: ${p.error || '登录失败'}`).join('\n')
        store.toast(`以下平台登录失败，已自动跳过：\n${failMsg}`, 'warning')
        setTimeout(() => { resetScan() }, 2000)
        return
      }
      const pendingCount = scanData.value.reduce((sum, p) => sum + p.courses.filter(c => !isCourseDone(c)).length, 0)
      if (pendingCount === 0) {
        allDone.value = true
        countdownTimer = setInterval(() => { countdown.value--; if (countdown.value <= 0) { clearInterval(countdownTimer); resetScan() } }, 1000)
        return
      }
      scanDone.value = true; saveSession()
      try { const r = await api.orders.activeCourses(username.value.trim()); const activeIds: string[] = r?.data || []; for (const cid of activeIds) submittedCourseIds.value.add(cid) } catch {}
      const total = scanData.value.reduce((s, p) => s + p.courses.length, 0)
      store.toast(`扫描完成：${okPlatforms.length} 个平台成功，共 ${total} 门课程`, 'success')
      await fetchBackendPrices()
    } catch (e: any) { store.toast('扫描失败：' + (e?.message || '网络错误'), 'error') }
    finally { scanning.value = false; rescanning.value = false }
  }

  async function startChaoxingScan() {
    if (!chaoxingUsername.value.trim()) { store.toast('请输入学习通账号', 'warning'); return }
    if (!chaoxingPassword.value.trim()) { store.toast('请输入学习通密码', 'warning'); return }
    if (countdownTimer) clearInterval(countdownTimer)
    scanning.value = true; submitSuccess.value = false; allDone.value = false
    loginError.value = null; failedPlatforms.value = []
    try {
      const res = await api.courses.scanChaoxing({ username: chaoxingUsername.value.trim(), password: chaoxingPassword.value.trim() })
      const platform = res.data.platform
      scanData.value = [platform]
      if (platform.status !== 'ok') {
        loginError.value = 'all'
        failedPlatforms.value = [{ website_id: 4, name: '学习通', error: platform.error || '登录失败' }]
        loginErrorCountdown.value = 3
        loginErrorTimer = setInterval(() => { loginErrorCountdown.value--; if (loginErrorCountdown.value <= 0) { clearInterval(loginErrorTimer); loginErrorTimer = null; resetScan() } }, 1000)
        return
      }
      const pendingCount = platform.courses.filter(c => !isCourseDone(c)).length
      if (pendingCount === 0) {
        allDone.value = true
        countdownTimer = setInterval(() => { countdown.value--; if (countdown.value <= 0) { clearInterval(countdownTimer); resetScan() } }, 1000)
        return
      }
      scanDone.value = true
      store.toast(`学习通扫描完成，共 ${platform.courses.length} 门课程`, 'success')
    } catch (e: any) { store.toast('扫描失败：' + (e?.message || '网络错误'), 'error') }
    finally { scanning.value = false; rescanning.value = false }
  }

  function resetScan() {
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
    if (loginErrorTimer) { clearInterval(loginErrorTimer); loginErrorTimer = null }
    if (payPollTimer.value) { clearInterval(payPollTimer.value); payPollTimer.value = null }
    localStorage.removeItem(LS_KEY); savedData.value = null
    scanDone.value = false; allDone.value = false; allInProgress.value = false; scanData.value = []
    checkedCourseIds.value = new Set(); submittedCourseIds.value = new Set(); pendingOrderedCourseIds.value = []
    loginError.value = null; failedPlatforms.value = []; submitSuccess.value = false
    rescanning.value = false; scanning.value = false; paying.value = false
    password.value = ''
    countdown.value = 3; loginErrorCountdown.value = 3
    showPayModal.value = false; payTimedOut.value = false; payQrCode.value = ''
    payOrders.value = []; payQrCodes.value = {}; payBatchIds.value = {}; payBatchOutTradeNos.value = {}
    payBatchId.value = ''; payBatchOutTradeNo.value = ''
  }

  function rescan() {
    if (!username.value.trim() || !password.value.trim()) { store.toast('请先输入学号和密码', 'warning'); return }
    checkedCourseIds.value = new Set(); submittedCourseIds.value = new Set(); allInProgress.value = false
    rescanning.value = true; startScan().catch(() => { rescanning.value = false })
  }

  function openReloginDialog(website_id: number, name: string) { reloginDialog.value = { visible: true, website_id, name }; reloginPassword.value = '' }
  function closeReloginDialog() { reloginDialog.value = { visible: false, website_id: 0, name: '' }; reloginPassword.value = '' }

  async function submitRelogin() {
    if (!reloginPassword.value.trim()) { store.toast('请输入密码', 'warning'); return }
    reloginLoading.value = true
    try {
      const res = await api.courses.relogin({ username: username.value.trim(), password: reloginPassword.value.trim(), website_id: reloginDialog.value.website_id, include_records: true })
      const platform = res.data.platform
      if (platform.status === 'ok') {
        const idx = scanData.value.findIndex(p => p.website_id === platform.website_id)
        if (idx >= 0) scanData.value[idx] = platform; else scanData.value.push(platform)
        failedPlatforms.value = failedPlatforms.value.filter(fp => fp.website_id !== platform.website_id)
        if (failedPlatforms.value.length === 0) loginError.value = null
        store.toast(`${platform.name} 登录成功，已更新数据`, 'success'); closeReloginDialog(); saveSession()
      } else { store.toast(platform.error || '登录失败，请检查密码', 'error') }
    } catch (e: any) { store.toast(e?.message || '操作失败', 'error') }
    finally { reloginLoading.value = false }
  }

  // ── Payment state ──
  const paying = ref(false)
  const showPayModal = ref(false)
  const payTotal = ref(0)
  const submitSuccess = ref(false)
  const payError = ref('')
  const payQrCode = ref('')
  const payPollTimer = ref<ReturnType<typeof setInterval> | null>(null)
  const selectedPayMethod = ref('ypay_wxpay')
  const payOrders = ref<any[]>([])
  const payQrCodes = ref<Record<string, string>>({})
  const payReallyPrices = ref<Record<string, number>>({})
  const payBatchIds = ref<Record<string, string>>({})
  const payBatchOutTradeNos = ref<Record<string, string>>({})
  const payBatchId = ref('')
  const payBatchOutTradeNo = ref('')
  const showPaySuccess = ref(false)
  const footerAds = ref<{ id: number; slot: number; name: string }[]>([])
  const paySuccessAmount = ref(0)
  const payTimedOut = ref(false)

  // ── Payment logic ──
  function handleOrderSuccess(orderedCourseIds: string[]) {
    for (const cid of orderedCourseIds) { submittedCourseIds.value.add(cid); checkedCourseIds.value.delete(cid) }
    let remaining = 0
    for (const p of scanData.value) { for (const c of p.courses) { if (!isCourseDoneOrSubmitted(c)) remaining++ } }
    if (remaining === 0) { allInProgress.value = true; store.toast('所有课程已下单，任务正在进行中！', 'success') }
    else { for (const p of scanData.value) { for (const c of p.courses) { if (!isCourseDoneOrSubmitted(c)) checkedCourseIds.value.add(c.course_id) } }; store.toast(`下单成功！还有 ${remaining} 门课程未处理，已自动选中`, 'info') }
    saveSession()
  }

  function goToOrders() { window.location.href = '/#/orders' }

  async function submitAndPay() {
    if (summary.value.courses === 0) { store.toast('请至少选择一门课程', 'warning'); return }
    // 学习通用账号密码，学校平台用学号密码
    const isChaoxing = activeTab.value === 'chaoxing'
    if (isChaoxing && !chaoxingPassword.value.trim()) { store.toast('请输入学习通密码', 'warning'); return }
    if (!isChaoxing && !password.value.trim()) { store.toast('请输入密码后再提交', 'warning'); return }
    paying.value = true; payError.value = ''
    try {
      await fetchBackendPrices()
      try { const r = await api.orders.activeCourses(username.value.trim()); const activeIds: string[] = r?.data || []; for (const cid of activeIds) { checkedCourseIds.value.delete(cid); submittedCourseIds.value.add(cid) } } catch {}
      if (checkedCourseIds.value.size === 0) { store.toast('所选课程均已有进行中的订单，无需重复提交', 'info'); paying.value = false; return }
      const grouped: Record<number, { ids: string[]; v: number; e: number; details: { video_total: number; video_completed: number; exam_total: number; exam_done: number }[] }> = {}
      for (const plat of scanData.value) {
        for (const c of plat.courses) {
          if (checkedCourseIds.value.has(c.course_id)) {
            if (!grouped[plat.website_id]) grouped[plat.website_id] = { ids: [], v: 0, e: 0, details: [] }
            grouped[plat.website_id].ids.push(c.course_id); grouped[plat.website_id].v += c.video_pending
            grouped[plat.website_id].e += Math.max(0, c.exam_total - c.exam_done)
            grouped[plat.website_id].details.push({ video_total: c.video_total, video_completed: c.video_completed, exam_total: c.exam_total, exam_done: c.exam_done })
          }
        }
      }
      const free = isPrivileged.value
      const orders = Object.entries(grouped).map(([w, g]) => {
        const wid = parseInt(w)
        let taskType: string
        let price: number
        const hasVideo = g.v > 0; const hasExam = g.e > 0
        if (wid === 4) {
          taskType = 'chaoxing_points'
          price = free ? 0 : (packagePricing.value.priceChaoxing || 8)
        } else {
          taskType = 'video'; if (hasVideo && hasExam) taskType = 'full'; else if (hasExam) taskType = 'exam'
          const backendTotal = g.ids.reduce((s, id) => s + (backendPrices.value[id]?.price || 0), 0)
          price = backendTotal
          price = free ? 0 : parseFloat(price.toFixed(2))
        }
        return { website_id: wid, task_type: taskType, course_ids: g.ids, video_count: g.v, exam_count: g.e, price, course_details: g.details }
      })
      payTotal.value = orders.reduce((s, o) => s + o.price, 0)
      const orderUsername = isChaoxing ? chaoxingUsername.value.trim() : username.value.trim()
      const orderPassword = isChaoxing ? chaoxingPassword.value.trim() : password.value.trim()
      const batchRes = await api.orders.batch({ username: orderUsername, password: orderPassword, orders, inviter_code: (route.query.ref as string) || '' })
      submitSuccess.value = true
      const allOrders = (batchRes?.data?.orders) || []; payOrders.value = allOrders
      const newIds = allOrders.map((o: any) => o.order_id).join(',')
      const existingIds = sessionStorage.getItem('last_order_ids') || ''
      const allIds = existingIds ? existingIds + ',' + newIds : newIds
      sessionStorage.setItem('last_order_ids', allIds); localStorage.setItem('last_order_ids', allIds)
      const orderedCourseIds = Object.values(grouped).flatMap(g => g.ids)
      if (!allOrders.length) { store.toast('订单创建成功，但未返回订单信息', 'warning'); paying.value = false; return }
      if (free) { handleOrderSuccess(orderedCourseIds); paying.value = false; return }
      pendingOrderedCourseIds.value = orderedCourseIds
      const methods = [{ key: 'ypay_wxpay', pay_type: 1 }, { key: 'ypay_alipay', pay_type: 2 }]
      const qrCodes: Record<string, string> = {}; const batchIds: Record<string, string> = {}; const batchOutTradeNos: Record<string, string> = {}; const reallyPrices: Record<string, number> = {}
      const orderIds = allOrders.map((o: any) => o.order_id)
      for (const m of methods) {
        try { const payRes = await api.payment.batchCreate({ order_ids: orderIds, pay_type: m.pay_type }); const pd = (payRes?.data || {}) as any; batchIds[m.key] = pd.batch_id || ''; batchOutTradeNos[m.key] = pd.out_trade_no || ''; if (pd.qr_image) qrCodes[m.key] = pd.qr_image; if (pd.really_price) reallyPrices[m.key] = pd.really_price } catch {}
      }
      payQrCodes.value = qrCodes; payReallyPrices.value = reallyPrices; payBatchIds.value = batchIds; payBatchOutTradeNos.value = batchOutTradeNos
      payQrCode.value = qrCodes[selectedPayMethod.value] || ''; payBatchId.value = batchIds[selectedPayMethod.value] || ''; payBatchOutTradeNo.value = batchOutTradeNos[selectedPayMethod.value] || ''
      payTotal.value = reallyPrices[selectedPayMethod.value] || payTotal.value; showPayModal.value = true
      startPollPayment()
    } catch (e: any) { store.toast('提交失败：' + (e?.message || '网络错误'), 'error') }
    finally { paying.value = false }
  }

  function startPollPayment() {
    if (payPollTimer.value) { clearTimeout(payPollTimer.value); payPollTimer.value = null }
    if (!payBatchId.value) return
    let pollCount = 0; let stopped = false; const maxPolls = 120
    async function tick() {
      if (stopped) return
      try {
        pollCount++
        const r = await api.payment.batchCheck(payBatchId.value, payBatchOutTradeNo.value) as any
        if (r?.expired) { stopped = true; payPollTimer.value = null; payTimedOut.value = true; store.toast('订单已过期，请重新下单', 'warning'); return }
        if (pollCount >= maxPolls) { stopped = true; payPollTimer.value = null; payTimedOut.value = true; store.toast('支付超时，订单已提交，请到订单页查询', 'warning'); return }
        if (r?.paid) { stopped = true; payPollTimer.value = null; paySuccessAmount.value = payTotal.value; showPaySuccess.value = true; return }
      } catch {}
      if (!stopped) payPollTimer.value = setTimeout(tick, 3000)
    }
    payPollTimer.value = setTimeout(tick, 3000)
  }

  function onPaySuccessDone() {
    showPaySuccess.value = false; closePay(); handleOrderSuccess(pendingOrderedCourseIds.value); pendingOrderedCourseIds.value = []
    setTimeout(() => { window.location.href = '/#/orders' }, 300)
  }

  function closePay() {
    showPayModal.value = false; showPaySuccess.value = false; payTimedOut.value = false; payError.value = ''
    payQrCode.value = ''; payOrders.value = []; payQrCodes.value = {}; payBatchIds.value = {}; payBatchOutTradeNos.value = {}
    payBatchId.value = ''; payBatchOutTradeNo.value = ''
    if (payPollTimer.value) { clearInterval(payPollTimer.value); payPollTimer.value = null }
  }

  function savePayQr() {
    const src = payQrCode.value; if (!src) return
    const a = document.createElement('a'); a.href = src; a.download = 'pay-qr.png'; document.body.appendChild(a); a.click(); document.body.removeChild(a)
  }

  function switchPayMethod(method: string) {
    if (selectedPayMethod.value === method) return
    selectedPayMethod.value = method; payQrCode.value = payQrCodes.value[method] || ''
    payBatchId.value = payBatchIds.value[method] || ''; payBatchOutTradeNo.value = payBatchOutTradeNos.value[method] || ''
    if (payReallyPrices.value[method]) payTotal.value = payReallyPrices.value[method]
    if (payPollTimer.value) clearInterval(payPollTimer.value); startPollPayment()
  }

  // ── Danmaku / Earn button ──
  const painTexts = ['化好妆了网课还没刷完', '兄弟们上号啊我还在刷课', '网课谁发明的能不能取消', '这视频怎么还要答题啊', '出去玩还要挂着刷课', '室友都在打游戏就我在刷', '又占我周末时间', '作业比专业课还多', '又要挂科了救救我吧', '周末本该出去拍照的', '室友都去KTV了就我留宿', '网课进度条怎么不动啊', '五排就差我一个了', '考前才知道有网课要刷', '早八人还要刷到凌晨三点', '社团活动全被网课耽误了', '一学期的课两周刷完', '求求了给个脚本吧']
  const danmakuList = painTexts.map((text, idx) => ({ text, x: `${3 + idx * 5}%`, delay: `${idx * 2}s`, dur: `${14 + (idx % 3) * 3}s` }))

  const EARN_BTN_LS = 'earn_btn_y'
  const earnBtnY = ref<number>((() => { const v = localStorage.getItem(EARN_BTN_LS); return v ? parseInt(v) : Math.round(window.innerHeight * 0.5 - 25) })())
  let earnDragging = false; let earnStartY = 0; let earnStartClientY = 0
  function clampEarnY(y: number) { return Math.max(10, Math.min(window.innerHeight - 60, y)) }
  function earnPointerDown(e: PointerEvent) { earnDragging = false; earnStartY = earnBtnY.value; earnStartClientY = e.clientY; document.addEventListener('pointermove', earnPointerMove); document.addEventListener('pointerup', earnPointerUp) }
  function earnPointerMove(e: PointerEvent) { const dy = e.clientY - earnStartClientY; if (Math.abs(dy) > 5) earnDragging = true; earnBtnY.value = clampEarnY(earnStartY + dy) }
  function earnPointerUp() { document.removeEventListener('pointermove', earnPointerMove); document.removeEventListener('pointerup', earnPointerUp); localStorage.setItem(EARN_BTN_LS, String(Math.round(earnBtnY.value))) }
  function earnClick(e: MouseEvent) { if (earnDragging) { e.preventDefault(); e.stopPropagation() } }

  // ── Utilities ──
  const pct = (c: CourseItem) => { const total = c.video_total; if (total === 0) return 0; return Math.round(c.video_completed / total * 100) }
  const pctClass = (c: CourseItem) => { const p = pct(c); if (p >= 100) return 'done'; if (p < 50) return 'low'; return '' }

  // ── Announcement ──
  const ANNOUNCEMENT_LS_KEY = 'dismissed_announcement_id'
  const showAnnouncement = ref(false)
  const announcementContent = ref('')
  const announcementId = ref(0)

  async function checkAnnouncement() {
    try {
      const res = await api.announcement.get()
      if (!res?.data?.active || !res.data.content) return
      const serverId = res.data.id
      const dismissedId = parseInt(localStorage.getItem(ANNOUNCEMENT_LS_KEY) || '0', 10)
      if (serverId > dismissedId) {
        announcementId.value = serverId
        announcementContent.value = res.data.content
        showAnnouncement.value = true
      }
    } catch {}
  }

  function dismissAnnouncement() {
    showAnnouncement.value = false
    localStorage.setItem(ANNOUNCEMENT_LS_KEY, String(announcementId.value))
  }

  return {
    // Role
    userRole, isPrivileged, isRegularUser, showUpgradeBanner, dismissUpgradeBanner, detectUserRole, handleVisibilityChange,
    // Scan
    username, password, scanning, rescanning, scanDone, allDone, isLeaving, scanData, countdown,
    activeTab, chaoxingUsername, chaoxingPassword, startChaoxingScan,
    loginError, failedPlatforms, reloginDialog, reloginPassword, reloginLoading, loginErrorCountdown,
    packagePricing, submittedCourseIds, allInProgress, pendingOrderedCourseIds, checkedCourseIds,
    savedData, loadingPrices, backendPrices,
    isCourseDone, isCourseDoneOrSubmitted, visiblePlatforms, togglePlatform, toggleCourse, isPlatformAllChecked,
    summary, scenario, currentPrices, studentName, chaoxingInfo, chaoxingServiceType,
    startScan, resetScan, rescan, openReloginDialog, closeReloginDialog, submitRelogin,
    calcCoursePrice, fetchBackendPrices, saveSession, clearSaved,
    // Payment
    paying, showPayModal, payTotal, submitSuccess, payError, payQrCode, payPollTimer,
    selectedPayMethod, payOrders, payQrCodes, payReallyPrices, payBatchIds, payBatchOutTradeNos,
    payBatchId, payBatchOutTradeNo, showPaySuccess, footerAds, paySuccessAmount, payTimedOut,
    handleOrderSuccess, goToOrders, submitAndPay, startPollPayment, onPaySuccessDone, closePay, savePayQr, switchPayMethod,
    // UI
    danmakuList, earnBtnY, earnPointerDown, earnClick, pct, pctClass,
    // Announcement
    showAnnouncement, announcementContent, announcementId, checkAnnouncement, dismissAnnouncement,
    // LS_KEY for template
    LS_KEY,
  }
}

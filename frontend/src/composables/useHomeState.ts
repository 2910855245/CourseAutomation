// Home.vue 完整状态管理：扫描、课程选择、定价、支付、角色检测
import { ref, computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { api, type PlatformResult, type CourseItem } from '@/api'

export function useHomeState() {
  const store = useAppStore()

  // ── Role detection ──
  const userRole = ref<'admin' | null>(null)
  const isPrivileged = computed(() => !!userRole.value)
  const isRegularUser = ref(false)

  function detectUserRole() {
    // 管理员徽章：仅检查 admin token（用户体系已删除）
    userRole.value = store.isAdminLoggedIn ? 'admin' : null
  }

  function handleVisibilityChange() {
    if (document.visibilityState === 'visible') detectUserRole()
  }

  // ── Session persistence ──
  const LS_KEY = 'course_platform_remember'

  // 本地只记「学号」，**不记密码，也不记扫描结果**。
  //
  // 两点原因：
  //  1. 平台账号是学员本人的校园账号，明文写进 localStorage 等于任何一个 XSS
  //     或本地翻看都能直接拿到；密码改为每次会话由用户输入，只留在内存里。
  //  2. 扫描结果依赖平台实时状态，且下单/扫描这两步本来就必须有密码 ——
  //     只恢复「结果」而不恢复密码，用户会卡在一个没有密码输入框的结果页上
  //     无法提交。所以恢复出来的会话一律回到登录页，重新扫描即可。
  interface SavedData { username: string; ts: number }

  const SESSION_TTL_MS = 7 * 24 * 3600 * 1000

  function loadSaved(): SavedData | null {
    try {
      const raw = localStorage.getItem(LS_KEY)
      if (!raw) return null
      const data = JSON.parse(raw) as Partial<SavedData> & Record<string, unknown>
      if (!data || typeof data !== 'object') { localStorage.removeItem(LS_KEY); return null }
      if (!data.username || !data.ts) { localStorage.removeItem(LS_KEY); return null }
      if (Date.now() - (data.ts as number) > SESSION_TTL_MS) { localStorage.removeItem(LS_KEY); return null }
      // 旧版本把密码 + 扫描结果一起存了：读到就即刻瘦身回写，
      // 别让历史残留的明文密码继续躺在浏览器里。
      const slim: SavedData = { username: data.username as string, ts: data.ts as number }
      if (raw !== JSON.stringify(slim)) {
        try { localStorage.setItem(LS_KEY, JSON.stringify(slim)) } catch { }
      }
      return slim
    } catch { localStorage.removeItem(LS_KEY); return null }
  }

  function saveSession() {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify({ username: username.value.trim(), ts: Date.now() }))
    } catch { }
  }

  function clearSaved() {
    localStorage.removeItem(LS_KEY); savedData.value = null
    scanData.value = []; scanDone.value = false; checkedCourseIds.value = new Set()
    password.value = ''
  }

  // ── Scan state ──
  const savedData = ref<SavedData | null>(loadSaved())
  const username = ref(savedData.value?.username || '')
  // 密码不落盘：每次会话需要时由用户重新输入（见 SavedData 注释）
  const password = ref('')
  const scanning = ref(false)
  const activeTab = ref<'school' | 'chaoxing'>('school')
  const chaoxingUsername = ref('')
  const chaoxingPassword = ref('')
  const rescanning = ref(false)
  // 扫描结果不落盘：恢复会话只带回学号，扫描结果一律重新拉取（见 SavedData 注释）
  const scanDone = ref(false)
  const allDone = ref(false)
  const isLeaving = ref(false)
  const scanData = ref<PlatformResult[]>([])
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
    } catch { }
  }
  loadPackagePricing()

  // ── 刷课节奏档位（暴力 / 适中 / 保守）──
  // 与后端 speed.rs 的 SpeedMode 一一对应（turbo/balanced/gentle 是落库标识）；
  // 默认适中；保守档是"一节课接一节课"的串行档，免费刷默认走它
  const SPEED_LS_KEY = 'course_speed_mode'
  type SpeedMode = 'turbo' | 'balanced' | 'gentle'
  const hasSavedSpeed = (['turbo', 'balanced', 'gentle'] as const)
    .includes(localStorage.getItem(SPEED_LS_KEY) as SpeedMode)
  const speedMode = ref<SpeedMode>(
    hasSavedSpeed ? (localStorage.getItem(SPEED_LS_KEY) as SpeedMode) : 'balanced'
  )
  function setSpeedMode(mode: SpeedMode) {
    speedMode.value = mode
    try { localStorage.setItem(SPEED_LS_KEY, mode) } catch { }
  }

  // ── 免费待遇（全局免费开关 / 刷课卡）──
  // 由后端按访客身份判定，前端只负责展示与跳过支付；判定结果以后端返回为准
  const benefit = ref<{ free: boolean; reason: string; speed_mode?: string }>({ free: false, reason: '' })
  const inviteInfo = ref<{ code: string; threshold: number; invited_valid: number; can_claim: number; enabled: boolean }>(
    { code: '', threshold: 3, invited_valid: 0, can_claim: 0, enabled: true }
  )
  const myCard = ref<{ code: string; expires_at: string; days_left: number } | null>(null)

  async function loadBenefit() {
    try {
      const r = await api.me.benefit()
      const d = (r?.data || {}) as any
      benefit.value = d.benefit || { free: false, reason: '' }
      if (d.invite) inviteInfo.value = { ...inviteInfo.value, ...d.invite }
      myCard.value = d.card || null
      // 免费用户默认走保守档（没手动选过档位时才覆盖）
      if (benefit.value.free && !hasSavedSpeed) speedMode.value = 'gentle'
    } catch { /* 营销是附加功能，失败不打扰用户 */ }
  }

  const submittedCourseIds = ref(new Set<string>())
  const allInProgress = ref(false)
  const pendingOrderedCourseIds = ref<string[]>([])
  const checkedCourseIds = ref(new Set<string>())

  function isCourseDone(c: CourseItem): boolean {
    // 学习通：积分达标 且 无待完成作业 且 无待完成视频
    if (c.has_points_system !== undefined) {
      const pointsOk = !c.has_points_system || ((c.points_remaining ?? 0) <= 0)
      const workOk = (c.work_pending ?? 0) <= 0
      const videoOk = (c.video_pending ?? 0) <= 0
      return pointsOk && workOk && videoOk
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
    } catch { } finally { loadingPrices.value = false }
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
        // 不再 resetScan，继续显示成功平台的课程列表
      }
      const pendingCount = scanData.value.reduce((sum, p) => sum + p.courses.filter(c => !isCourseDone(c)).length, 0)
      if (pendingCount === 0) {
        allDone.value = true
        countdownTimer = setInterval(() => { countdown.value--; if (countdown.value <= 0) { clearInterval(countdownTimer); resetScan() } }, 1000)
        return
      }
      scanDone.value = true; saveSession()
      try { const r = await api.orders.activeCourses(username.value.trim()); const activeIds: string[] = r?.data || []; for (const cid of activeIds) submittedCourseIds.value.add(cid) } catch { }
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
  const paySuccessAmount = ref(0)
  const payTimedOut = ref(false)

  // 支付会话状态机。
  //
  // 把「通道已收款」和「业务已入账」分开，是因为二者真会不一致：
  // 通道单由回调写成已付，业务单的 paid/paid_processed 可能滞后。若只有
  // paid/未付 两态，就会出现「钱收了、界面说成功、实际上任务没派发」，用户
  // 关掉页面后无人跟进。uncredited 就是承接这个中间态的。
  type PayPhase = 'idle' | 'pending' | 'paid' | 'uncredited' | 'expired'
  const payPhase = ref<PayPhase>('idle')
  const payRemaining = ref(0)          // 剩余支付秒数（弹窗里显示倒计时）
  const payRechecking = ref(false)     // 「重新检查」进行中

  const PAY_TIMEOUT_SEC = 300
  const POLL_INTERVAL_MS = 3000
  // 连续这么多次「已付但未入账」才定态为 uncredited（避免正常入账延迟误报）
  const UNCREDITED_HIT_LIMIT = 8

  let payCountdownTimer: ReturnType<typeof setInterval> | null = null
  let payPollBusy = false
  let payUncreditedHits = 0

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
      try { const r = await api.orders.activeCourses(username.value.trim()); const activeIds: string[] = r?.data || []; for (const cid of activeIds) { checkedCourseIds.value.delete(cid); submittedCourseIds.value.add(cid) } } catch { }
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
      const free = isPrivileged.value || benefit.value.free
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
        return { website_id: wid, task_type: taskType, course_ids: g.ids, video_count: g.v, exam_count: g.e, price, course_details: g.details, speed_mode: speedMode.value }
      })
      payTotal.value = orders.reduce((s, o) => s + o.price, 0)
      const orderUsername = isChaoxing ? chaoxingUsername.value.trim() : username.value.trim()
      const orderPassword = isChaoxing ? chaoxingPassword.value.trim() : password.value.trim()
      const batchRes = await api.orders.batch({ username: orderUsername, password: orderPassword, orders })
      submitSuccess.value = true
      const allOrders = (batchRes?.data?.orders) || []; payOrders.value = allOrders
      const newIds = allOrders.map((o: any) => o.order_id).join(',')
      const existingIds = sessionStorage.getItem('last_order_ids') || ''
      const allIds = existingIds ? existingIds + ',' + newIds : newIds
      sessionStorage.setItem('last_order_ids', allIds); localStorage.setItem('last_order_ids', allIds)
      // 游客查单凭证：order_id -> view_token 映射
      const tokenPairs = allOrders.map((o: any) => `${o.order_id}:${o.view_token || ''}`)
      const existingPairs = sessionStorage.getItem('last_order_tokens') || ''
      const allPairs = existingPairs ? existingPairs + ',' + tokenPairs.join(',') : tokenPairs.join(',')
      sessionStorage.setItem('last_order_tokens', allPairs); localStorage.setItem('last_order_tokens', allPairs)
      const orderedCourseIds = Object.values(grouped).flatMap(g => g.ids)
      if (!allOrders.length) { store.toast('订单创建成功，但未返回订单信息', 'warning'); paying.value = false; return }
      // 免费单以后端判定为准（它已经 0 元并直接进队列），前端不该再弹支付
      if (free || batchRes?.data?.free === true) {
        if (batchRes?.data?.free === true) { await loadBenefit() }
        handleOrderSuccess(orderedCourseIds); paying.value = false; return
      }
      pendingOrderedCourseIds.value = orderedCourseIds
      const methods = [{ key: 'ypay_wxpay', pay_type: 1 }, { key: 'ypay_alipay', pay_type: 2 }]
      const qrCodes: Record<string, string> = {}; const batchIds: Record<string, string> = {}; const batchOutTradeNos: Record<string, string> = {}; const reallyPrices: Record<string, number> = {}
      const orderIds = allOrders.map((o: any) => o.order_id)
      for (const m of methods) {
        try { const payRes = await api.payment.batchCreate({ order_ids: orderIds, pay_type: m.pay_type }); const pd = (payRes?.data || {}) as any; batchIds[m.key] = pd.batch_id || ''; batchOutTradeNos[m.key] = pd.out_trade_no || ''; if (pd.qr_image) qrCodes[m.key] = pd.qr_image; if (pd.really_price) reallyPrices[m.key] = pd.really_price } catch { }
      }
      payQrCodes.value = qrCodes; payReallyPrices.value = reallyPrices; payBatchIds.value = batchIds; payBatchOutTradeNos.value = batchOutTradeNos
      payQrCode.value = qrCodes[selectedPayMethod.value] || ''; payBatchId.value = batchIds[selectedPayMethod.value] || ''; payBatchOutTradeNo.value = batchOutTradeNos[selectedPayMethod.value] || ''
      payTotal.value = reallyPrices[selectedPayMethod.value] || payTotal.value; showPayModal.value = true
      startPollPayment()
    } catch (e: any) { store.toast('提交失败：' + (e?.message || '网络错误'), 'error') }
    finally { paying.value = false }
  }

  /// 停止支付会话（清掉轮询与倒计时，避免定时器泄漏）
  function stopPaySession() {
    if (payPollTimer.value) { clearTimeout(payPollTimer.value); payPollTimer.value = null }
    if (payCountdownTimer) { clearInterval(payCountdownTimer); payCountdownTimer = null }
    payPollBusy = false
  }

  /** 进入支付会话：立刻查一次，然后按固定间隔轮询；同时跑 300s 倒计时 */
  function startPollPayment() {
    stopPaySession()
    if (!payBatchId.value) return
    payPhase.value = 'pending'
    payRemaining.value = PAY_TIMEOUT_SEC
    payUncreditedHits = 0

    payCountdownTimer = setInterval(() => {
      if (payPhase.value !== 'pending') return
      payRemaining.value--
      if (payRemaining.value <= 0) {
        // 倒计时归零：本地即可判定过期，不必再等服务端确认
        payPhase.value = 'expired'
        payTimedOut.value = true
        stopPaySession()
      }
    }, 1000)

    schedulePayTick(0)
  }

  function schedulePayTick(delay: number) {
    payPollTimer.value = setTimeout(payTick, delay)
  }

  async function payTick() {
    if (payPhase.value !== 'pending') return
    // in-flight 闸：弱网下上一次请求还没回来就跳过本轮，避免请求叠加
    if (payPollBusy) { schedulePayTick(POLL_INTERVAL_MS); return }
    // 页面在后台时不查（省电，也避免移动端被浏览器节流后堆积）；回前台会立即补查
    if (document.visibilityState === 'hidden') { schedulePayTick(POLL_INTERVAL_MS); return }

    payPollBusy = true
    try {
      await checkPaymentOnce()
    } catch { /* 网络抖动不中断轮询，等下一轮 */ }
    finally { payPollBusy = false }

    if (payPhase.value === 'pending') schedulePayTick(POLL_INTERVAL_MS)
  }

  /** 查一次支付状态并按结果推进状态机（轮询与「重新检查」共用） */
  async function checkPaymentOnce() {
    const r = await api.payment.batchCheck(payBatchId.value, payBatchOutTradeNo.value) as any
    if (r?.expired) { payPhase.value = 'expired'; payTimedOut.value = true; stopPaySession(); return }
    if (!r?.paid) return

    // 已付款：再看业务是否真的入账
    if (r.credited === false) {
      payUncreditedHits++
      if (payUncreditedHits >= UNCREDITED_HIT_LIMIT) {
        payPhase.value = 'uncredited'
        stopPaySession()
      }
      return
    }
    payPhase.value = 'paid'
    paySuccessAmount.value = payTotal.value
    showPaySuccess.value = true
    stopPaySession()
  }

  /** uncredited 态的「重新检查」：给入账留出时间后手动再查一次 */
  async function recheckPayment() {
    if (payRechecking.value) return
    payRechecking.value = true
    payUncreditedHits = 0
    try {
      await checkPaymentOnce()
      if (payPhase.value === 'uncredited') {
        // 仍未入账：恢复轮询再等一会儿（后台对账也在跑，可能马上就补上）
        payPhase.value = 'pending'
        if (payRemaining.value <= 0) payRemaining.value = 60
        startPollPayment()
        store.toast('仍在入账中，已为你继续查询', 'info')
      }
    } catch { store.toast('查询失败，请稍后重试', 'error') }
    finally { payRechecking.value = false }
  }

  /** 过期后重新发起支付：复用原订单重新下单，不必重新选课 */
  async function retryPayment() {
    closePay()
    store.toast('请重新提交订单以生成新的支付二维码', 'info')
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

  // ── Utilities ──
  const pct = (c: CourseItem) => { const total = c.video_total; if (total === 0) return 0; return Math.round(c.video_completed / total * 100) }
  const pctClass = (c: CourseItem) => { const p = pct(c); if (p >= 100) return 'done'; if (p < 50) return 'low'; return '' }

  // ── Announcement ──
  const ANNOUNCEMENT_LS_KEY = 'dismissed_announcement_id'
  const showAnnouncement = ref(false)
  const announcementContent = ref('')
  const announcementTitle = ref('')
  const announcementImage = ref('')
  const announcementContactType = ref('')
  const announcementContactValue = ref('')
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
        announcementTitle.value = (res.data as any).title || ''
        announcementImage.value = (res.data as any).image || ''
        announcementContactType.value = (res.data as any).contact_type || ''
        announcementContactValue.value = (res.data as any).contact_value || ''
        showAnnouncement.value = true
      }
    } catch { }
  }

  /** 复制联系方式（公告里挂微信/QQ 时用） */
  async function copyAnnouncementContact() {
    const v = announcementContactValue.value
    if (!v) return
    try { await navigator.clipboard.writeText(v); store.toast('联系方式已复制', 'success') }
    catch { store.toast('复制失败，请手动选择', 'warning') }
  }

  function dismissAnnouncement() {
    showAnnouncement.value = false
    localStorage.setItem(ANNOUNCEMENT_LS_KEY, String(announcementId.value))
  }

  return {
    // Role
    userRole, isPrivileged, isRegularUser, detectUserRole, handleVisibilityChange,
    // Scan
    username, password, scanning, rescanning, scanDone, allDone, isLeaving, scanData, countdown,
    activeTab, chaoxingUsername, chaoxingPassword, startChaoxingScan,
    loginError, failedPlatforms, reloginDialog, reloginPassword, reloginLoading, loginErrorCountdown,
    packagePricing, submittedCourseIds, allInProgress, pendingOrderedCourseIds, checkedCourseIds,
    savedData, loadingPrices, backendPrices,
    // Speed mode
    speedMode, setSpeedMode,
    // 营销：免费待遇 / 邀请 / 刷课卡
    benefit, inviteInfo, myCard, loadBenefit,
    isCourseDone, isCourseDoneOrSubmitted, visiblePlatforms, togglePlatform, toggleCourse, isPlatformAllChecked,
    summary, scenario, currentPrices, studentName, chaoxingInfo, chaoxingServiceType,
    startScan, resetScan, rescan, openReloginDialog, closeReloginDialog, submitRelogin,
    calcCoursePrice, fetchBackendPrices, saveSession, clearSaved,
    // Payment
    paying, showPayModal, payTotal, submitSuccess, payError, payQrCode, payPollTimer,
    selectedPayMethod, payOrders, payQrCodes, payReallyPrices, payBatchIds, payBatchOutTradeNos,
    payBatchId, payBatchOutTradeNo, showPaySuccess, paySuccessAmount, payTimedOut,
    handleOrderSuccess, goToOrders, submitAndPay, startPollPayment, onPaySuccessDone, closePay, savePayQr, switchPayMethod,
    // UI
    pct, pctClass,
    // Announcement
    showAnnouncement, announcementContent, announcementTitle, announcementImage,
    announcementContactType, announcementContactValue, copyAnnouncementContact,
    announcementId, checkAnnouncement, dismissAnnouncement,
    // LS_KEY for template
    LS_KEY,
  }
}

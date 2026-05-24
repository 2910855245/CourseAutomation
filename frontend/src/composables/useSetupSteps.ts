import { ref, watch, type Ref, type Reactive } from 'vue'
import { api } from '@/api'

export function useSetupSteps(
  ctx: {
    currentStep: Ref<number>
    loading: Ref<boolean>
    error: Ref<string>
    success: Ref<string>
    completedSteps: Reactive<Set<number>>
    markDone: (n: number) => void
    nextStep: () => void
    debouncedSave: () => void
    setExtraSave: (fn: () => Record<string, any>) => void
    clearDraft: () => void
  }
) {
  const envChecks = ref<any[]>([])
  const envAllOk = ref(false)
  const envChecking = ref(false)

  const dbUser = ref('')
  const dbPassword = ref('')
  const dbName = ref('')
  const dbTesting = ref(false)
  const dbTested = ref(false)
  const dbSaved = ref(false)

  const adminUser = ref('admin')
  const adminPass = ref('')
  const adminPassConfirm = ref('')
  const adminCreated = ref(false)

  const ypayKey = ref('')
  const ypaySaved = ref(false)

  const videoPrice = ref('0.10')
  const examPrice = ref('0.15')
  const pricingSaved = ref(false)

  const appQrImage = ref('')
  const appDownloadUrl = ref('')
  const appPairData = ref('')
  const appLoading = ref(false)
  const appPaired = ref(false)
  const appPairPollTimer = ref<ReturnType<typeof setInterval> | null>(null)

  const aiKey = ref('')
  const aiKeySaved = ref(false)
  const aiKeyShow = ref(false)
  const aiKeySaving = ref(false)

  // Register extra save data for draft persistence
  ctx.setExtraSave(() => ({
    dbUser: dbUser.value,
    dbPassword: dbPassword.value,
    dbName: dbName.value,
    dbTested: dbTested.value,
    dbSaved: dbSaved.value,
    adminUser: adminUser.value,
    adminPass: adminPass.value,
    adminPassConfirm: adminPassConfirm.value,
    adminCreated: adminCreated.value,
    ypayKey: ypayKey.value,
    ypaySaved: ypaySaved.value,
    videoPrice: videoPrice.value,
    examPrice: examPrice.value,
    pricingSaved: pricingSaved.value,
    appPaired: appPaired.value,
    aiKey: aiKey.value,
    aiKeySaved: aiKeySaved.value,
  }))

  function restoreStepsDraft(d: any) {
    dbUser.value = d.dbUser ?? ''
    dbPassword.value = d.dbPassword ?? ''
    dbName.value = d.dbName ?? ''
    dbTested.value = d.dbTested ?? false
    dbSaved.value = d.dbSaved ?? false
    adminUser.value = d.adminUser ?? 'admin'
    adminPass.value = d.adminPass ?? ''
    adminPassConfirm.value = d.adminPassConfirm ?? ''
    adminCreated.value = d.adminCreated ?? false
    ypayKey.value = d.ypayKey ?? ''
    ypaySaved.value = d.ypaySaved ?? false
    videoPrice.value = d.videoPrice ?? '0.10'
    examPrice.value = d.examPrice ?? '0.15'
    pricingSaved.value = d.pricingSaved ?? false
    appPaired.value = d.appPaired ?? false
    aiKey.value = d.aiKey ?? ''
    aiKeySaved.value = d.aiKeySaved ?? false
  }

  // Auto-save on step fields change
  watch(
    [ctx.currentStep, dbUser, dbPassword, dbName, dbTested, dbSaved, adminUser, adminPass, adminPassConfirm, adminCreated, ypayKey, ypaySaved, videoPrice, examPrice, pricingSaved, appPaired, aiKey, aiKeySaved],
    ctx.debouncedSave,
  )

  // Step 5 auto-load
  watch(ctx.currentStep, async (v) => {
    if (v === 5) {
      if (!ypaySaved.value && ypayKey.value.trim()) {
        try { await api.setup.saveYpay({ ypay_key: ypayKey.value.trim() }); ypaySaved.value = true } catch {}
      }
      if (!appQrImage.value) { await loadAppPairQr() }
      if (!appPaired.value) { startPairPoll() }
    } else {
      stopPairPoll()
    }
  })

  async function runEnvCheck() {
    envChecking.value = true
    ctx.error.value = ''
    try {
      const r = await api.setup.check()
      envChecks.value = r.data?.checks || []
      envAllOk.value = r.data?.all_ok || false
    } catch (e: any) {
      ctx.error.value = e.message || '环境检测失败'
    } finally { envChecking.value = false }
  }

  async function initDatabase() {
    ctx.loading.value = true
    ctx.error.value = ''
    try {
      const r = await api.setup.initDb()
      ctx.success.value = r.data?.message || '数据库初始化成功！'
      ctx.nextStep()
    } catch (e: any) {
      ctx.error.value = e.message || '数据库初始化失败'
    } finally { ctx.loading.value = false }
  }

  function friendlyDbError(raw: string) {
    const msg = raw || ''
    if (/Access denied/i.test(msg)) return '数据库登录失败，请核对数据库用户名和密码'
    if (/Unknown database/i.test(msg)) return '数据库不存在，请在宝塔面板先创建数据库'
    if (/Can't connect/i.test(msg) || /Connection refused/i.test(msg)) return '无法连接数据库，请检查数据库服务是否已启动'
    if (/Host .* is not allowed/i.test(msg)) return '数据库不允许该主机连接，请检查数据库访问权限'
    if (msg.includes('(1045')) return '数据库登录失败，请核对数据库用户名和密码'
    if (msg.includes('(1049')) return '数据库不存在，请在宝塔面板先创建数据库'
    if (msg.includes('(2003')) return '无法连接数据库，请检查数据库服务是否已启动'
    return msg || '数据库连接失败，请检查配置'
  }

  async function testDbConnection() {
    dbTesting.value = true
    ctx.error.value = ''
    ctx.success.value = ''
    try {
      const r = await api.setup.testDb({
        user: dbUser.value.trim(),
        password: dbPassword.value,
        database: dbName.value.trim(),
      })
      if (r.data?.success) {
        dbTested.value = true
        ctx.success.value = r.data?.message || 'MySQL 连接成功！'
      } else {
        ctx.error.value = friendlyDbError(r.message || '连接失败')
      }
    } catch (e: any) {
      ctx.error.value = friendlyDbError(e.message || '连接失败，请检查 MySQL 配置')
    } finally { dbTesting.value = false }
  }

  async function testAndSaveDb() {
    await testDbConnection()
    if (dbTested.value) {
      await saveDbConfig()
    }
  }

  async function saveDbConfig() {
    if (!dbTested.value) { ctx.error.value = '请先测试数据库连接'; return }
    ctx.loading.value = true
    ctx.error.value = ''
    try {
      const r = await api.setup.saveDb({
        user: dbUser.value.trim(),
        password: dbPassword.value,
        database: dbName.value.trim(),
      })
      dbSaved.value = true
      ctx.markDone(3)
      ctx.success.value = r.data?.message || '数据库配置已保存！'
      await initDatabase()
    } catch (e: any) {
      ctx.error.value = e.message || '保存失败'
    } finally { ctx.loading.value = false }
  }

  async function createAdmin() {
    if (!adminUser.value.trim()) { ctx.error.value = '请输入管理员用户名'; return }
    if (!adminPass.value) { ctx.error.value = '请输入管理员密码'; return }
    if (adminPass.value.length < 6) { ctx.error.value = '密码至少 6 位'; return }
    if (adminPass.value !== adminPassConfirm.value) { ctx.error.value = '两次密码不一致'; return }
    ctx.loading.value = true
    ctx.error.value = ''
    try {
      const r = await api.setup.createAdmin({ username: adminUser.value.trim(), password: adminPass.value })
      adminCreated.value = true
      ctx.markDone(4)

      try {
        const loginRes = await api.admin.login({ username: adminUser.value.trim(), password: adminPass.value })
        const token = loginRes?.data?.token
        if (token) {
          localStorage.setItem('admin_token', token)
          const { setAdminApiToken } = await import('@/api')
          setAdminApiToken(token)
        }
      } catch { }

      ctx.success.value = r.data?.message || '管理员账号创建成功！'
      ctx.nextStep()
    } catch (e: any) {
      ctx.error.value = e.message || '创建失败'
    } finally { ctx.loading.value = false }
  }

  async function saveYpay() {
    if (!ypayKey.value.trim()) { ctx.error.value = '请输入通信密钥'; return }
    ctx.loading.value = true
    ctx.error.value = ''
    try {
      const r = await api.setup.saveYpay({ ypay_key: ypayKey.value.trim() })
      ypaySaved.value = true
      ctx.markDone(5)
      ctx.success.value = r.data?.message || '支付配置已保存！'
      ctx.nextStep()
    } catch (e: any) {
      ctx.error.value = e.message || '保存失败'
    } finally { ctx.loading.value = false }
  }

  async function savePricing() {
    const vp = parseFloat(videoPrice.value)
    const ep = parseFloat(examPrice.value)
    if (isNaN(vp) || vp <= 0) { ctx.error.value = '视频单价必须大于 0'; return }
    if (isNaN(ep) || ep <= 0) { ctx.error.value = '考试单价必须大于 0'; return }
    ctx.loading.value = true
    ctx.error.value = ''
    try {
      await api.adminConfig.set('video_unit_price', vp.toFixed(2))
      await api.adminConfig.set('exam_unit_price', ep.toFixed(2))
      pricingSaved.value = true
      ctx.markDone(6)
      ctx.success.value = '定价设置成功！'
      ctx.nextStep()
    } catch (e: any) {
      ctx.error.value = e.message || '保存失败'
    } finally { ctx.loading.value = false }
  }

  async function saveAiKey() {
    if (!aiKey.value.trim()) { ctx.error.value = '请输入 DeepSeek API Key'; return }
    aiKeySaving.value = true
    ctx.error.value = ''
    try {
      await api.adminConfig.set('deepseek_api_key', aiKey.value.trim())
      aiKeySaved.value = true
      ctx.markDone(7)
      ctx.success.value = 'AI 答题配置成功！'
      ctx.nextStep()
    } catch (e: any) {
      ctx.error.value = e.message || '保存失败'
    } finally { aiKeySaving.value = false }
  }

  function skipAiKey() {
    aiKeySaved.value = false
    ctx.markDone(7)
    ctx.nextStep()
  }

  async function loadAppPairQr() {
    appLoading.value = true
    ctx.error.value = ''
    try {
      const r = await api.app.pairQrcode()
      const d = r.data || {} as any
      appQrImage.value = d.qr_image || ''
      appDownloadUrl.value = d.download_url || ''
      appPairData.value = d.pair_data || ''
    } catch (e: any) {
      ctx.error.value = e.message || '获取配对二维码失败'
    } finally { appLoading.value = false }
  }

  function startPairPoll() {
    if (appPairPollTimer.value) return
    let count = 0
    appPairPollTimer.value = setInterval(async () => {
      count++
      if (count > 60) { stopPairPoll(); return }
      if (appPaired.value) { stopPairPoll(); return }
      try {
        const r = await api.app.pairStatus()
        if (r?.data?.paired) {
          appPaired.value = true
          stopPairPoll()
        }
      } catch {}
    }, 3000)
  }

  function stopPairPoll() {
    if (appPairPollTimer.value) { clearInterval(appPairPollTimer.value); appPairPollTimer.value = null }
  }

  async function finishSetup() {
    ctx.loading.value = true
    ctx.error.value = ''
    try {
      if (!pricingSaved.value) {
        await api.adminConfig.set('video_unit_price', parseFloat(videoPrice.value).toFixed(2))
        await api.adminConfig.set('exam_unit_price', parseFloat(examPrice.value).toFixed(2))
      }
      if (!ypaySaved.value && ypayKey.value.trim()) {
        await api.setup.saveYpay({ ypay_key: ypayKey.value.trim() })
      }
      if (!aiKeySaved.value && aiKey.value.trim()) {
        await api.adminConfig.set('deepseek_api_key', aiKey.value.trim())
      }
      await api.setup.finish()
      ctx.completedSteps.add(8)
      ctx.clearDraft()
      ctx.success.value = '安装完成！正在跳转...'
      setTimeout(() => { window.location.href = '/' }, 1500)
    } catch (e: any) {
      ctx.error.value = e.message || '安装失败'
    } finally { ctx.loading.value = false }
  }

  function generateYpayKey() {
    const arr = new Uint8Array(16)
    crypto.getRandomValues(arr)
    return Array.from(arr).map(b => b.toString(16).padStart(2, '0')).join('')
  }

  function cleanup() {
    stopPairPoll()
  }

  return {
    envChecks, envAllOk, envChecking,
    dbUser, dbPassword, dbName, dbTesting, dbTested, dbSaved,
    adminUser, adminPass, adminPassConfirm, adminCreated,
    ypayKey, ypaySaved,
    videoPrice, examPrice, pricingSaved,
    appQrImage, appDownloadUrl, appPairData, appLoading, appPaired, appPairPollTimer,
    aiKey, aiKeySaved, aiKeyShow, aiKeySaving,
    restoreStepsDraft,
    runEnvCheck, testDbConnection, testAndSaveDb, saveDbConfig, initDatabase,
    createAdmin, saveYpay, savePricing, saveAiKey, skipAiKey,
    loadAppPairQr, startPairPoll, stopPairPoll,
    finishSetup, generateYpayKey, cleanup,
  }
}

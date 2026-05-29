// 系统配置：DeepSeek/AI、定价、代理、风控/健康
import { ref, reactive, computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api'
import { useConfirmSingleton } from '@/composables/useConfirm'

export function useSystemConfig() {
  const store = useAppStore()
  const { showConfirm } = useConfirmSingleton()

  // ── DeepSeek / AI ──
  const deepseekApiKey = ref('')
  const deepseekKeyMasked = ref('')
  const savingDeepseekKey = ref(false)
  const showDeepseekKey = ref(false)
  const testingDeepseek = ref(false)
  const deepseekTestResult = ref<any>(null)
  const examModel = ref('deepseek-chat')
  const finalExamModel = ref('deepseek-v4-flash')
  const homeworkModel = ref('deepseek-chat')
  const pricingModel = ref('deepseek-v4-pro')
  const chaoxingModel = ref('deepseek-chat')
  const savingModels = ref(false)
  const testingModel = ref('')
  const DEEPSEEK_MODELS = [
    { value: 'deepseek-chat', label: 'deepseek-chat (v4-flash)', desc: '答题推荐，快速便宜' },
    { value: 'deepseek-v4-flash', label: 'deepseek-v4-flash', desc: '非思考模式，速度快' },
    { value: 'deepseek-v4-pro', label: 'deepseek-v4-pro', desc: '深度推理，适合分析' },
    { value: 'deepseek-reasoner', label: 'deepseek-reasoner', desc: '思考模式，最强推理' },
  ]

  async function loadDeepseekKey() {
    try {
      const r = await api.adminConfig.all()
      const configs = r.data || {}
      const key = configs.deepseek_api_key || ''
      deepseekKeyMasked.value = key ? key.slice(0, 6) + '****' + key.slice(-4) : ''
      deepseekApiKey.value = ''
      showDeepseekKey.value = false
      if (configs.deepseek_exam_model) examModel.value = configs.deepseek_exam_model
      if (configs.deepseek_final_exam_model) finalExamModel.value = configs.deepseek_final_exam_model
      if (configs.deepseek_homework_model) homeworkModel.value = configs.deepseek_homework_model
      if (configs.deepseek_chaoxing_model) chaoxingModel.value = configs.deepseek_chaoxing_model
      if (configs.deepseek_pricing_model) pricingModel.value = configs.deepseek_pricing_model
    } catch {}
  }

  async function saveDeepseekKey() {
    if (!deepseekApiKey.value.trim()) { store.toast('请输入 API Key', 'warning'); return }
    savingDeepseekKey.value = true
    try {
      await api.adminConfig.set('deepseek_api_key', deepseekApiKey.value.trim())
      store.toast('DeepSeek API Key 已保存', 'success')
      loadDeepseekKey()
    } catch (e: any) { store.toast(e?.message || '保存失败', 'error') }
    finally { savingDeepseekKey.value = false }
  }

  async function clearDeepseekKey() {
    savingDeepseekKey.value = true
    try {
      await api.adminConfig.set('deepseek_api_key', '')
      store.toast('API Key 已清除', 'success')
      loadDeepseekKey()
    } catch (e: any) { store.toast(e?.message || '操作失败', 'error') }
    finally { savingDeepseekKey.value = false }
  }

  async function testDeepseekApi() {
    testingDeepseek.value = true
    deepseekTestResult.value = null
    try {
      const r = await api.adminConfig.testDeepseek()
      deepseekTestResult.value = r.data
      if (r.data?.api_ok) {
        store.toast('DeepSeek API 检测通过', 'success')
      } else {
        store.toast(r.data?.error || '检测失败', 'error')
      }
    } catch (e: any) {
      deepseekTestResult.value = { openai_module: false, api_key: '', api_ok: false, error: e?.message || '检测请求失败' }
      store.toast('检测失败', 'error')
    } finally { testingDeepseek.value = false }
  }

  async function saveModels() {
    savingModels.value = true
    try {
      await api.adminConfig.set('deepseek_exam_model', examModel.value)
      await api.adminConfig.set('deepseek_final_exam_model', finalExamModel.value)
      await api.adminConfig.set('deepseek_homework_model', homeworkModel.value)
      await api.adminConfig.set('deepseek_pricing_model', pricingModel.value)
      await api.adminConfig.set('deepseek_chaoxing_model', chaoxingModel.value)
      store.toast('模型配置已保存', 'success')
    } catch (e: any) { store.toast(e?.message || '保存失败', 'error') }
    finally { savingModels.value = false }
  }

  async function testModelApi(model: string) {
    testingModel.value = model
    try {
      const r = await api.adminConfig.testDeepseek(model)
      if (r.data?.api_ok) {
        store.toast(`${model} 测试通过 (${r.data.latency_ms}ms)`, 'success')
      } else {
        store.toast(`${model} 测试失败: ${r.data?.error || '未知错误'}`, 'error')
      }
    } catch (e: any) {
      store.toast(`${model} 测试失败: ${e?.message || '网络错误'}`, 'error')
    } finally { testingModel.value = '' }
  }

  // ── Pricing ──
  const marketForm = reactive({ avgPrice: 5, maxPrice: 6, minPrice: 0, myCost: 0.5, extraInfo: '' })
  const recommending = ref(false)
  const recommendResult = ref<any>(null)
  const applyingPackage = ref(false)
  const packagePricing = reactive({
    priceSmall: 3, priceMedium: 5, priceLarge: 6,
    discount25: 0.7, discount50: 0.5, discount75: 0.3, priceMinimum: 2,
    priceExamOnly: 5, priceHomeworkOnly: 3, priceChaoxing: 8,
  })
  const editingPricing = ref(false)
  const savingPricing = ref(false)
  const editPricing = reactive({
    priceSmall: 3, priceMedium: 5, priceLarge: 6,
    discount25: 0.7, discount50: 0.5, discount75: 0.3, priceMinimum: 2,
    priceExamOnly: 5, priceHomeworkOnly: 3, priceChaoxing: 8,
  })

  async function loadPricing() {
    try {
      const res = await api.pricing.get()
      const d = res.data || {} as any
      packagePricing.priceSmall = d.priceSmall || 3
      packagePricing.priceMedium = d.priceMedium || 5
      packagePricing.priceLarge = d.priceLarge || 6
      packagePricing.discount25 = d.discount25 || 0.7
      packagePricing.discount50 = d.discount50 || 0.5
      packagePricing.discount75 = d.discount75 || 0.3
      packagePricing.priceMinimum = d.priceMinimum || 2
      packagePricing.priceExamOnly = d.priceExamOnly || 5
      packagePricing.priceHomeworkOnly = d.priceHomeworkOnly || 3
      packagePricing.priceChaoxing = d.priceChaoxing || 8
      Object.assign(editPricing, { ...packagePricing })
    } catch (e: any) {
      store.toast('加载定价配置失败: ' + (e?.message || '网络错误'), 'error')
    }
  }

  async function getRecommendation() {
    if (marketForm.avgPrice <= 0 || marketForm.maxPrice <= 0) {
      store.toast('请填写市场平均价和最高价', 'warning')
      return
    }
    recommending.value = true
    recommendResult.value = null
    try {
      const res = await api.pricing.recommend({
        avg_price: marketForm.avgPrice,
        max_price: marketForm.maxPrice,
        min_price: marketForm.minPrice || undefined,
        my_cost_per_course: marketForm.myCost,
        extra_info: marketForm.extraInfo || undefined,
      })
      recommendResult.value = res.data
      const r = res.data.recommended
      packagePricing.priceSmall = r.priceSmall
      packagePricing.priceMedium = r.priceMedium
      packagePricing.priceLarge = r.priceLarge
      packagePricing.discount25 = r.discount25
      packagePricing.discount50 = r.discount50
      packagePricing.discount75 = r.discount75
      packagePricing.priceMinimum = r.priceMinimum
      packagePricing.priceExamOnly = r.priceExamOnly || 5
      packagePricing.priceHomeworkOnly = r.priceHomeworkOnly || 3
      Object.assign(editPricing, { ...packagePricing })
      store.toast('AI 推荐方案已生成', 'success')
    } catch (e: any) {
      store.toast('推荐失败: ' + (e?.message || '网络错误'), 'error')
    } finally {
      recommending.value = false
    }
  }

  async function applyPackagePricing() {
    applyingPackage.value = true
    try {
      await api.pricing.applyPackage({ ...packagePricing })
      store.toast('打包定价方案已应用', 'success')
    } catch (e: any) {
      store.toast('应用失败: ' + (e?.message || '网络错误'), 'error')
    } finally {
      applyingPackage.value = false
    }
  }

  function cancelEditPricing() {
    editingPricing.value = false
  }

  async function savePricingConfig() {
    savingPricing.value = true
    try {
      await api.pricing.applyPackage({ ...editPricing })
      Object.assign(packagePricing, editPricing)
      editingPricing.value = false
      store.toast('定价配置已保存', 'success')
    } catch (e: any) {
      store.toast('保存失败: ' + (e?.message || '网络错误'), 'error')
    } finally {
      savingPricing.value = false
    }
  }

  // ── Proxy ──
  const proxyForm = reactive({ enabled: false, url: '', username: '', password: '' })
  const proxySaving = ref(false)
  const proxyTesting = ref(false)
  const proxyTestResult = ref('')
  const proxyTestOk = ref(false)
  const serverPublicIp = ref('')

  async function loadProxySettings() {
    try { const r = await api.proxy.get(); if (r.data) Object.assign(proxyForm, r.data) } catch {}
  }

  async function saveProxy() {
    proxySaving.value = true
    try {
      const r = await api.proxy.save({ ...proxyForm })
      if (r.success) store.toast('代理设置已保存', 'success')
      else store.toast(r.message || '保存失败', 'error')
    } catch { store.toast('保存失败', 'error') }
    finally { proxySaving.value = false }
  }

  async function testProxy() {
    if (!proxyForm.url.trim()) { store.toast('请先输入代理地址', 'warning'); return }
    proxyTesting.value = true; proxyTestResult.value = ''
    try {
      const r = await api.proxy.test({ ...proxyForm })
      proxyTestOk.value = r.success
      proxyTestResult.value = r.message + (r.data?.exit_ip ? ' — 出口IP: ' + r.data.exit_ip : '')
    } catch { proxyTestResult.value = '测试请求失败'; proxyTestOk.value = false }
    finally { proxyTesting.value = false }
  }

  async function fetchServerPublicIp() {
    try {
      const r = await fetch('https://myip.ipip.net')
      const t = await r.text()
      serverPublicIp.value = t.trim().split(' ').pop() || t.trim()
    } catch {}
  }

  // ── Risk / Health ──
  const riskDomainStatus = ref<any>(null)
  const riskJsStatus = ref<any>(null)
  const riskHealth = ref<any>(null)
  const riskAlerts = ref<any[]>([])
  const loadingRisk = ref(false)
  const riskChecking = ref(false)
  const riskIntervalInput = ref(3600)
  const showAddDomainModal = ref(false)
  const addDomainForm = reactive({ domain: '', name: '', url: '' })
  const healthSummary = ref<any>(null)
  const loadingHealth = ref(false)
  const healthChecking = ref(false)
  const riskCheckStep = ref('')
  const healthIntervalInput = ref(3600)
  const healthIntervalSaving = ref(false)
  const healthAccountInput = ref('')
  const healthPasswordInput = ref('')
  const healthAccountSaving = ref(false)
  const healthChaoxingAccountInput = ref('')
  const healthChaoxingPasswordInput = ref('')
  const healthChaoxingSaving = ref(false)
  const healthSchoolSaved = ref(false)
  const healthChaoxingSaved = ref(false)
  const healthSchoolSwitched = ref(false)
  const healthChaoxingSwitched = ref(false)
  const showHealthSettings = ref(false)
  const riskLoginForm = reactive({ username: '', password: '' })
  const riskLoginLoading = ref(false)
  const riskNeedLogin = ref(false)
  const riskChecks = ref<any[]>([])

  const riskScore = computed(() => {
    const checks = riskChecks.value
    if (!checks.length) return 0
    const passCount = checks.filter(c => c.status === 'pass').length
    return Math.round((passCount / checks.length) * 100)
  })
  const riskScoreColor = computed(() => {
    const s = riskScore.value
    if (s >= 80) return '#10b981'
    if (s >= 50) return '#f59e0b'
    return '#ef4444'
  })
  const riskScoreLevel = computed(() => {
    const s = riskScore.value
    if (s >= 80) return 'level-good'
    if (s >= 50) return 'level-warn'
    return 'level-bad'
  })
  const riskScoreText = computed(() => {
    const s = riskScore.value
    if (s >= 80) return '系统安全'
    if (s >= 50) return '存在风险'
    return '安全告警'
  })
  const riskScoreDesc = computed(() => {
    const s = riskScore.value
    const failCount = riskChecks.value.filter(c => c.status === 'fail').length
    const warnCount = riskChecks.value.filter(c => c.status === 'warn').length
    if (s >= 80) return '所有安全检查项正常运行'
    if (s >= 50) return `${warnCount} 项警告, ${failCount} 项异常，请关注`
    return `${failCount} 项异常，建议立即处理`
  })
  const riskScoreDash = computed(() => {
    const circumference = 2 * Math.PI * 52
    const filled = (riskScore.value / 100) * circumference
    return `${filled} ${circumference}`
  })

  function buildRiskChecks() {
    const checks: any[] = []
    const platforms = riskHealth.value?.platforms || []
    const allUp = platforms.length > 0 && platforms.every((p: any) => p.reachable)
    const someUp = platforms.some((p: any) => p.reachable)
    checks.push({ id: 'platform', name: '平台可达性', expanded: false, desc: allUp ? `${platforms.length} 个平台全部正常` : someUp ? `部分平台不可达` : '所有平台不可达', status: allUp ? 'pass' : someUp ? 'warn' : 'fail' })

    const domainCount = riskDomainStatus.value?.known_domains ? Object.keys(riskDomainStatus.value.known_domains).length : 0
    checks.push({ id: 'domain', name: '域名监控', expanded: false, desc: `正在监控 ${domainCount} 个域名`, status: domainCount > 0 ? 'pass' : 'warn' })

    const jsFiles = riskJsStatus.value?.files?.length || 0
    const jsChecked = !!riskJsStatus.value?.last_check
    const jsChanged = riskJsStatus.value?.last_change && (Date.now() - new Date(riskJsStatus.value.last_change).getTime()) < 86400000
    checks.push({ id: 'js', name: 'JS 反作弊监控', expanded: false, desc: jsChanged ? '检测到近期 JS 变更' : jsChecked ? `监控 ${jsFiles} 个文件，无变更` : '尚未执行过检查', status: jsChanged ? 'warn' : 'pass' })

    const alertCount = riskAlerts.value?.length || 0
    checks.push({ id: 'alerts', name: '安全告警', expanded: false, desc: alertCount > 0 ? `${alertCount} 条未处理告警` : '无告警', status: alertCount === 0 ? 'pass' : alertCount < 5 ? 'warn' : 'fail' })

    const interval = riskIntervalInput.value || 3600
    checks.push({ id: 'interval', name: '自动检查', expanded: false, desc: `每 ${Math.floor(interval / 60)} 分钟自动检查一次`, status: interval >= 300 ? 'pass' : 'warn' })

    const hChecks = healthSummary.value?.checks || {}
    const hNameMap: Record<string, string> = { auth: '登录态', courses: '课程列表', study_report: '学习上报', exam_api: '考试接口' }
    for (const key of ['auth', 'courses', 'study_report', 'exam_api']) {
      const val = hChecks[key]
      if (val) {
        const st = val.status === 'healthy' ? 'pass' : val.status === 'warning' ? 'warn' : 'fail'
        checks.push({ id: `health_${key}`, name: hNameMap[key] || key, expanded: false, desc: val.message || '', status: st })
      } else {
        checks.push({ id: `health_${key}`, name: hNameMap[key] || key, expanded: false, desc: '未检测，点击"全面检查"执行', status: 'unknown' })
      }
    }
    riskChecks.value = checks
  }

  async function loadRiskData() {
    loadingRisk.value = true
    try {
      const [ds, js, health, alerts, hSummary] = await Promise.all([
        api.adminDomainMonitor.status(), api.adminDomainMonitor.jsStatus(),
        api.adminDomainMonitor.health(), api.adminDomainMonitor.alerts(30),
        api.healthMonitor.summary().catch(() => ({ data: null })),
      ])
      riskDomainStatus.value = ds.data; riskJsStatus.value = js.data
      riskHealth.value = health.data; riskAlerts.value = alerts.data || []
      riskIntervalInput.value = ds.data?.interval || 3600
      healthSummary.value = hSummary.data
      buildRiskChecks(); loadHealthInterval(); loadHealthAccount()
    } catch (e: any) { store.toast(e.message || '加载风险数据失败', 'error') }
    finally { loadingRisk.value = false }
  }

  async function runDomainCheck() {
    riskChecking.value = true
    try {
      const res = await api.adminDomainMonitor.check()
      if (res.data?.new_domains?.length || res.data?.changed_domains?.length) {
        store.toast(`检测到变更: ${res.data.new_domains?.length || 0}个新域名, ${res.data.changed_domains?.length || 0}个变更`, 'warning')
      } else { store.toast('域名检查完成，无变更', 'success') }
      loadRiskData()
    } catch (e: any) { store.toast(e.message, 'error') }
    finally { riskChecking.value = false }
  }

  async function runJsCheck() {
    riskChecking.value = true
    try {
      const res = await api.adminDomainMonitor.jsCheck()
      if (res.data?.changes?.length) { store.toast(`检测到 ${res.data.changes.length} 个JS文件变更`, 'warning') }
      else { store.toast(`JS检查完成，共检查 ${res.data?.files_checked || 0} 个文件，无变更`, 'success') }
      loadRiskData()
    } catch (e: any) { store.toast(e.message, 'error') }
    finally { riskChecking.value = false }
  }

  async function saveRiskInterval() {
    try { await api.adminDomainMonitor.setInterval(riskIntervalInput.value); store.toast('检查间隔已保存', 'success') }
    catch (e: any) { store.toast(e.message, 'error') }
  }

  async function runHealthCheck(websiteId?: number) {
    healthChecking.value = true
    try {
      if (websiteId !== undefined) await api.healthMonitor.check(websiteId)
      else await api.healthMonitor.checkAll()
      const [hSummary, healthRes] = await Promise.all([
        api.healthMonitor.summary().catch(() => ({ data: null })),
        api.adminDomainMonitor.health().catch(() => ({ data: null })),
      ])
      healthSummary.value = hSummary.data
      if (healthRes.data) riskHealth.value = healthRes.data
    } catch (e: any) { throw e }
    finally { healthChecking.value = false }
  }

  async function saveHealthInterval() {
    healthIntervalSaving.value = true
    try { await api.healthMonitor.setInterval(healthIntervalInput.value); store.toast(`检查间隔已设为 ${healthIntervalInput.value} 秒`, 'success') }
    catch (e: any) { store.toast(e?.message || '保存失败', 'error') }
    finally { healthIntervalSaving.value = false }
  }

  async function loadHealthInterval() {
    try { const res = await api.healthMonitor.getInterval(); if (res.data?.interval) healthIntervalInput.value = res.data.interval } catch {}
  }

  async function saveHealthAccount(websiteType: string = 'school') {
    const isChaoxing = websiteType === 'chaoxing'
    const username = isChaoxing ? healthChaoxingAccountInput.value.trim() : healthAccountInput.value.trim()
    const password = isChaoxing ? healthChaoxingPasswordInput.value : healthPasswordInput.value
    if (!username || !password) { store.toast('请输入检测账号和密码', 'error'); return }
    if (isChaoxing) healthChaoxingSaving.value = true
    else healthAccountSaving.value = true
    try {
      // 检测是否是切换账号（之前已有保存的账号）
      const prevSaved = isChaoxing ? healthChaoxingSaved.value : healthSchoolSaved.value
      await api.healthMonitor.setAccount(username, password, websiteType)
      if (isChaoxing) {
        healthChaoxingSaved.value = true
        healthChaoxingSwitched.value = prevSaved
      } else {
        healthSchoolSaved.value = true
        healthSchoolSwitched.value = prevSaved
      }
      store.toast(prevSaved ? '检测账号已切换' : '检测账号已保存', 'success')
      await loadHealthAccount()
    } catch (e: any) { store.toast(e?.message || '保存失败', 'error') }
    finally {
      if (isChaoxing) healthChaoxingSaving.value = false
      else healthAccountSaving.value = false
    }
  }

  async function loadHealthAccount() {
    try {
      const res = await api.healthMonitor.getAccount()
      const accounts = res.data?.accounts || []
      const school = accounts.find((a: any) => (a.website_type || 'school') === 'school' && a.active) || accounts.find((a: any) => (a.website_type || 'school') === 'school')
      const chaoxing = accounts.find((a: any) => a.website_type === 'chaoxing' && a.active) || accounts.find((a: any) => a.website_type === 'chaoxing')
      if (school) { healthAccountInput.value = school.username; healthPasswordInput.value = school.password; healthSchoolSaved.value = true }
      if (chaoxing) { healthChaoxingAccountInput.value = chaoxing.username; healthChaoxingPasswordInput.value = chaoxing.password; healthChaoxingSaved.value = true }
    } catch {}
  }

  async function runFullRiskCheck() {
    riskChecking.value = true; riskNeedLogin.value = false
    try {
      riskCheckStep.value = '域名监控'
      const dsRes = await api.adminDomainMonitor.check()
      if (dsRes.data?.new_domains?.length || dsRes.data?.changed_domains?.length) {
        store.toast(`检测到变更: ${dsRes.data.new_domains?.length || 0}个新域名, ${dsRes.data.changed_domains?.length || 0}个变更`, 'warning')
      }
      riskCheckStep.value = 'JS 反作弊'
      const jsRes = await api.adminDomainMonitor.jsCheck()
      if (jsRes.data?.changes?.length) { store.toast(`检测到 ${jsRes.data.changes.length} 个JS文件变更`, 'warning') }
      riskCheckStep.value = '平台登录态'
      try { await runHealthCheck() } catch (e: any) {
        if (e?.message?.includes('会话') || e?.message?.includes('登录') || e?.response?.status === 400) riskNeedLogin.value = true
      }
      riskCheckStep.value = '刷新数据'
      await loadRiskData()
      if (riskNeedLogin.value) { store.toast('需要先登录平台账号才能执行健康检查', 'warning') }
      else { store.toast('全面检查完成', 'success') }
    } catch { store.toast('检查失败', 'error') }
    finally { setTimeout(() => { riskChecking.value = false; riskCheckStep.value = '' }, 800) }
  }

  async function riskLoginAndCheck() {
    if (!riskLoginForm.username.trim() || !riskLoginForm.password.trim()) { store.toast('请输入账号密码', 'warning'); return }
    riskLoginLoading.value = true
    try {
      const res = await api.courses.scan({ username: riskLoginForm.username.trim(), password: riskLoginForm.password.trim(), include_records: false })
      const platforms = res.data.platforms || []
      const okCount = platforms.filter((p: any) => p.status === 'ok').length
      if (okCount > 0) {
        store.toast(`登录成功 (${okCount}/${platforms.length} 个平台)`, 'success')
        riskLoginForm.username = ''; riskLoginForm.password = ''; riskNeedLogin.value = false
        await runHealthCheck(); buildRiskChecks(); store.toast('全面检查完成', 'success')
      } else { store.toast('所有平台登录失败，请检查账号密码', 'error') }
    } catch (e: any) { store.toast(e?.message || '登录失败', 'error') }
    finally { riskLoginLoading.value = false }
  }

  async function addDomain() {
    if (!addDomainForm.domain || !addDomainForm.name) { store.toast('请填写域名和名称', 'error'); return }
    if (!addDomainForm.url) addDomainForm.url = `https://${addDomainForm.domain}`
    try {
      await api.adminDomainMonitor.add(addDomainForm)
      showAddDomainModal.value = false
      addDomainForm.domain = ''; addDomainForm.name = ''; addDomainForm.url = ''
      loadRiskData(); store.toast('域名已添加', 'success')
    } catch (e: any) { store.toast(e.message, 'error') }
  }

  async function removeDomain(domain: string) {
    const ok = await showConfirm({ title: '移除域名', message: `确定要移除域名 ${domain} 吗？`, type: 'warning' })
    if (!ok) return
    try { await api.adminDomainMonitor.remove(domain); loadRiskData(); store.toast('域名已移除', 'success') }
    catch (e: any) { store.toast(e.message, 'error') }
  }

  async function clearRiskAlerts() {
    try { await api.adminDomainMonitor.clearAlerts(); riskAlerts.value = []; store.toast('告警历史已清除', 'success') }
    catch (e: any) { store.toast(e.message, 'error') }
  }

  const platformColors: string[] = ['#4f6ef7','#22c55e','#f59e0b','#ef4444','#8b5cf6','#0ea5e9']
  const taskTypeNames: Record<string, string> = { video: '视频', exam: '考试', full: '全包', chaoxing_points: '学习通积分', both: '视频+考试' }
  const tierNames: Record<string, string> = { '1': '入门代理', '2': '高级代理', '3': '合伙人' }

  return {
    // DeepSeek
    deepseekApiKey, deepseekKeyMasked, savingDeepseekKey, showDeepseekKey, testingDeepseek,
    deepseekTestResult, examModel, finalExamModel, homeworkModel, pricingModel, chaoxingModel, savingModels,
    testingModel, DEEPSEEK_MODELS,
    loadDeepseekKey, saveDeepseekKey, clearDeepseekKey, testDeepseekApi, saveModels, testModelApi,
    // Pricing
    marketForm, recommending, recommendResult, applyingPackage, packagePricing,
    editingPricing, savingPricing, editPricing,
    loadPricing, getRecommendation, applyPackagePricing, cancelEditPricing, savePricingConfig,
    // Proxy
    proxyForm, proxySaving, proxyTesting, proxyTestResult, proxyTestOk, serverPublicIp,
    loadProxySettings, saveProxy, testProxy, fetchServerPublicIp,
    // Risk / Health
    riskDomainStatus, riskJsStatus, riskHealth, riskAlerts, loadingRisk, riskChecking,
    riskIntervalInput, showAddDomainModal, addDomainForm, healthSummary, loadingHealth,
    healthChecking, riskCheckStep, healthIntervalInput, healthIntervalSaving,
    healthAccountInput, healthPasswordInput, healthAccountSaving, healthChaoxingAccountInput, healthChaoxingPasswordInput, healthChaoxingSaving, healthSchoolSaved, healthChaoxingSaved, healthSchoolSwitched, healthChaoxingSwitched, showHealthSettings,
    riskLoginForm, riskLoginLoading, riskNeedLogin, riskChecks,
    riskScore, riskScoreColor, riskScoreLevel, riskScoreText, riskScoreDesc, riskScoreDash,
    buildRiskChecks, loadRiskData, runDomainCheck, runJsCheck, saveRiskInterval,
    runHealthCheck, saveHealthInterval, loadHealthInterval, saveHealthAccount, loadHealthAccount,
    runFullRiskCheck, riskLoginAndCheck, addDomain, removeDomain, clearRiskAlerts,
    // Constants
    platformColors, taskTypeNames, tierNames,
  }
}

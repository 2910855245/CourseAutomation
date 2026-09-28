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
  const riskHealth = ref<any>(null)
  const riskAlerts = ref<any[]>([])
  const loadingRisk = ref(false)
  const riskChecking = ref(false)
  const riskIntervalInput = ref(3600)
  const showAddDomainModal = ref(false)
  const addDomainForm = reactive({ domain: '', name: '', url: '' })
  const riskCheckStep = ref('')
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

    const alertCount = riskAlerts.value?.length || 0
    checks.push({ id: 'alerts', name: '安全告警', expanded: false, desc: alertCount > 0 ? `${alertCount} 条未处理告警` : '无告警', status: alertCount === 0 ? 'pass' : alertCount < 5 ? 'warn' : 'fail' })

    const interval = riskIntervalInput.value || 3600
    checks.push({ id: 'interval', name: '自动检查', expanded: false, desc: `每 ${Math.floor(interval / 60)} 分钟自动检查一次`, status: interval >= 300 ? 'pass' : 'warn' })

    riskChecks.value = checks
  }

  async function loadRiskData() {
    loadingRisk.value = true
    try {
      const [ds, health, alerts] = await Promise.all([
        api.adminDomainMonitor.status(),
        api.adminDomainMonitor.health(), api.adminDomainMonitor.alerts(30),
      ])
      riskDomainStatus.value = ds.data
      riskHealth.value = health.data; riskAlerts.value = alerts.data || []
      riskIntervalInput.value = ds.data?.interval || 3600
      buildRiskChecks()
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

  async function saveRiskInterval() {
    try { await api.adminDomainMonitor.setInterval(riskIntervalInput.value); store.toast('检查间隔已保存', 'success') }
    catch (e: any) { store.toast(e.message, 'error') }
  }

  async function runFullRiskCheck() {
    riskChecking.value = true
    try {
      riskCheckStep.value = '域名监控'
      const dsRes = await api.adminDomainMonitor.check()
      if (dsRes.data?.new_domains?.length || dsRes.data?.changed_domains?.length) {
        store.toast(`检测到变更: ${dsRes.data.new_domains?.length || 0}个新域名, ${dsRes.data.changed_domains?.length || 0}个变更`, 'warning')
      }
      riskCheckStep.value = '刷新数据'
      await loadRiskData()
      store.toast('全面检查完成', 'success')
    } catch { store.toast('检查失败', 'error') }
    finally { setTimeout(() => { riskChecking.value = false; riskCheckStep.value = '' }, 800) }
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
    applyingPackage, packagePricing,
    editingPricing, savingPricing, editPricing,
    loadPricing, applyPackagePricing, cancelEditPricing, savePricingConfig,
    // Proxy
    proxyForm, proxySaving, proxyTesting, proxyTestResult, proxyTestOk, serverPublicIp,
    loadProxySettings, saveProxy, testProxy, fetchServerPublicIp,
    // Risk
    riskDomainStatus, riskHealth, riskAlerts, loadingRisk, riskChecking,
    riskIntervalInput, showAddDomainModal, addDomainForm, riskCheckStep,
    riskChecks,
    riskScore, riskScoreColor, riskScoreLevel, riskScoreText, riskScoreDesc, riskScoreDash,
    buildRiskChecks, loadRiskData, runDomainCheck, saveRiskInterval,
    runFullRiskCheck, addDomain, removeDomain, clearRiskAlerts,
    // Constants
    platformColors, taskTypeNames, tierNames,
  }
}

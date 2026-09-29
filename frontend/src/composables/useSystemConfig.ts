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
  const examModel = ref('deepseek-flash')
  const finalExamModel = ref('deepseek-flash')
  const homeworkModel = ref('deepseek-flash')
  const pricingModel = ref('deepseek-v4-pro')
  const chaoxingModel = ref('deepseek-flash')
  const savingModels = ref(false)
  const testingModel = ref('')
  // 当前在售模型（deepseek-chat / deepseek-reasoner 已于 2026-07-24 弃用；
  // 老配置里的旧名字后端会自动归一化，这里只提供在售选项）
  const DEEPSEEK_MODELS = [
    { value: 'deepseek-flash', label: 'deepseek-flash', desc: 'V4.1-Flash，答题/测验首选，快且便宜' },
    { value: 'deepseek-v4-pro', label: 'deepseek-v4-pro', desc: 'V4-Pro，复杂推理与分析' },
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
      const t = configs.deepseek_thinking
      thinkingMode.value = t === '1' || t === 'true' ? 'on' : t === '0' || t === 'false' ? 'off' : 'auto'
      // 未配置时默认开启（与后端默认值一致）
      visionOcr.value = configs.deepseek_vision_ocr !== '0'
    } catch { }
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

  // ── AI 能力开关（对齐 DeepSeek 官方能力：思考模式 / 图像理解兜底）──
  // thinkingMode: 'auto' 不写配置（由模型名语义决定）/ 'on' / 'off'
  const thinkingMode = ref<'auto' | 'on' | 'off'>('auto')
  const visionOcr = ref(true)
  const savingAiOptions = ref(false)

  async function saveAiOptions() {
    savingAiOptions.value = true
    try {
      // auto 用空串表示"未配置"，后端 configured_thinking() 会把空串当作 None
      const thinkingVal = thinkingMode.value === 'on' ? '1' : thinkingMode.value === 'off' ? '0' : ''
      await api.adminConfig.set('deepseek_thinking', thinkingVal)
      await api.adminConfig.set('deepseek_vision_ocr', visionOcr.value ? '1' : '0')
      store.toast('AI 能力开关已保存', 'success')
    } catch (e: any) { store.toast(e?.message || '保存失败', 'error') }
    finally { savingAiOptions.value = false }
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

  // 说明：网络代理整块已删除。后端 rust_worker 从无 /api/admin/proxy 路由，
  // 也没有任何出站请求读取代理配置（platform_client 只做 TLS/UA/限速），
  // 所以原「网络代理」页是一整套无效交互，已连同侧栏入口一并移除。
  // 若日后确实要接代理，应在 platform_client::build_client_with_ua 里统一
  // 接 reqwest::Proxy，而不是先摆一个存不了也用不上的表单。

  // 说明：风险 / 健康检查整块已删除 —— 它依赖的 8 个
  // /api/admin/domain-monitor/* 接口后端一个都没有，页面上的
  // 「全面检查」「刷新」「添加域名」「保存间隔」点了必然失败。
  // 平台是否可用，看「队列监控」里失败任务的 error_message 即可。
  const platformColors: string[] = ['#4f6ef7', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#0ea5e9']
  const taskTypeNames: Record<string, string> = { video: '视频', exam: '考试', full: '全包', chaoxing_points: '学习通积分', both: '视频+考试' }


  return {
    // DeepSeek
    deepseekApiKey, deepseekKeyMasked, savingDeepseekKey, showDeepseekKey, testingDeepseek,
    deepseekTestResult, examModel, finalExamModel, homeworkModel, pricingModel, chaoxingModel, savingModels,
    testingModel, DEEPSEEK_MODELS,
    loadDeepseekKey, saveDeepseekKey, clearDeepseekKey, testDeepseekApi, saveModels, testModelApi,
    // AI 能力开关
    thinkingMode, visionOcr, savingAiOptions, saveAiOptions,
    // Pricing
    applyingPackage, packagePricing,
    editingPricing, savingPricing, editPricing,
    loadPricing, applyPackagePricing, cancelEditPricing, savePricingConfig,

    // Constants
    platformColors, taskTypeNames,
  }
}

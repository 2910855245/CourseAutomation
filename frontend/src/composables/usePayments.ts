// 支付核心：任务队列、支付测试
import { ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api'

export function usePayments() {
  const store = useAppStore()

  // ── Queue ──
  const queueStats = ref<any>(null)
  const queueJobs = ref<any[]>([])
  const queueStatusFilter = ref('')
  const queueFilter = ref<'' | 'school' | 'chaoxing'>('')
  const loadingQueue = ref(false)
  const queuePausing = ref(false)
  const maxWorkersInput = ref(0)
  const serverSpecs = ref<any>(null)

  async function loadQueueData() {
    loadingQueue.value = true
    try {
      const q = queueFilter.value || undefined
      const [sr, jr] = await Promise.all([
        api.queue.stats(q),
        api.queue.jobs({ ...(queueStatusFilter.value ? { status: queueStatusFilter.value } : {}), queue: q }),
      ])
      queueStats.value = sr.data
      queueJobs.value = jr.data
      maxWorkersInput.value = sr.data.max_workers || 1
      detectServerSpecs()
    } catch (e: any) { store.toast(e.message || '加载队列数据失败', 'error') }
    finally { loadingQueue.value = false }
  }

  function setQueueFilter(f: '' | 'school' | 'chaoxing') {
    queueFilter.value = f
    loadQueueData()
  }

  async function pauseQueue(target?: string) {
    queuePausing.value = true
    try { await api.queue.pause(target || queueFilter.value || undefined); loadQueueData(); store.toast('队列已暂停', 'success') }
    catch (e: any) { store.toast(e.message, 'error') }
    finally { queuePausing.value = false }
  }

  async function resumeQueue(target?: string) {
    queuePausing.value = true
    try { await api.queue.resume(target || queueFilter.value || undefined); loadQueueData(); store.toast('队列已恢复', 'success') }
    catch (e: any) { store.toast(e.message, 'error') }
    finally { queuePausing.value = false }
  }

  async function setMaxWorkers() {
    try { await api.queue.config(maxWorkersInput.value, undefined); loadQueueData(); store.toast('并发数已更新', 'success') }
    catch (e: any) { store.toast(e.message, 'error') }
  }

  async function detectServerSpecs() {
    try {
      const res = await api.queue.detect()
      serverSpecs.value = res.data
    } catch (e: any) { store.toast(e.message || '检测失败', 'error') }
  }

  async function applyAutoConcurrency() {
    try {
      await api.queue.autoConfig()
      await loadQueueData()
      await detectServerSpecs()
      store.toast('已自动应用推荐并发数', 'success')
    } catch (e: any) { store.toast(e.message, 'error') }
  }

  async function cancelQueueJob(id: string) {
    try { await api.queue.cancel(id); loadQueueData(); store.toast('任务已取消', 'success') }
    catch (e: any) { store.toast(e.message, 'error') }
  }

  async function deleteQueueJob(id: string) {
    try { await api.queue.delete(id); loadQueueData(); store.toast('任务已删除', 'success') }
    catch (e: any) { store.toast(e.message, 'error') }
  }

  async function retryQueueJob(id: string) {
    try { await api.queue.retry(id); loadQueueData(); store.toast('任务已重试', 'success') }
    catch (e: any) { store.toast(e.message, 'error') }
  }

  async function clearQueueHistory() {
    try { const res = await api.queue.clear(); loadQueueData(); store.toast(res.message || '历史记录已清除', 'success') }
    catch (e: any) { store.toast(e.message, 'error') }
  }

  // ── Pay test ──
  const payTestChecks = ref<Array<{name: string; ok: boolean; msg: string}>>([])
  const payTestLoading = ref(false)
  const payTestStarted = ref(false)
  const payTestQrImage = ref('')
  const payTestReallyPrice = ref(0.01)
  const payTestPolling = ref(false)
  const payTestPaid = ref(false)
  const payTestExpired = ref(false)
  const showPayTest = ref(false)
  const payTestChannelName = ref('')
  let payTestBatchId = ''
  let payTestTradeNo = ''
  const payTestAccountId = ref(0)
  let payTestTimer: ReturnType<typeof setInterval> | null = null

  async function startChannelPayTest(acc: any) {
    if (!acc) return
    payTestAccountId.value = acc.id; payTestChannelName.value = acc.name
    showPayTest.value = true; payTestLoading.value = true
    payTestChecks.value = []; payTestStarted.value = false
    payTestQrImage.value = ''; payTestPaid.value = false; payTestExpired.value = false
    try {
      const r = await api.ypay.payTest.create(acc.id)
      if (r.success && r.data?.qr_image) {
        payTestStarted.value = true; payTestQrImage.value = r.data.qr_image
        payTestReallyPrice.value = r.data.really_price || 0.01
        payTestBatchId = r.data.batch_id; payTestTradeNo = r.data.trade_no
        payTestPolling.value = true; startPayTestPolling()
      } else {
        payTestChecks.value = [{ name: '创建', ok: false, msg: r.message || '创建测试订单失败' }]
      }
    } catch {
      payTestChecks.value = [{ name: '网络', ok: false, msg: '无法连接服务器' }]
    }
    finally { payTestLoading.value = false }
  }

  function startPayTestPolling() {
    if (payTestTimer) clearInterval(payTestTimer)
    let count = 0
    payTestTimer = setInterval(async () => {
      count++
      if (count > 60) { stopPayTestPolling(); payTestExpired.value = true; return }
      try {
        const r = await api.ypay.payTest.check(payTestBatchId, { out_trade_no: payTestBatchId, trade_no: payTestTradeNo })
        if (r.data?.paid) { stopPayTestPolling(); payTestPaid.value = true; payTestPolling.value = false }
      } catch {}
    }, 3000)
  }

  function stopPayTestPolling() {
    if (payTestTimer) { clearInterval(payTestTimer); payTestTimer = null }
    payTestPolling.value = false
  }

  function closePayTest() {
    stopPayTestPolling(); showPayTest.value = false; payTestChecks.value = []
    payTestStarted.value = false; payTestQrImage.value = ''
    payTestPaid.value = false; payTestExpired.value = false
  }

  return {
    // Queue
    queueStats, queueJobs, queueStatusFilter, queueFilter, loadingQueue, queuePausing, maxWorkersInput, serverSpecs,
    loadQueueData, setQueueFilter, pauseQueue, resumeQueue, setMaxWorkers, detectServerSpecs, applyAutoConcurrency,
    cancelQueueJob, deleteQueueJob, retryQueueJob, clearQueueHistory,
    // Pay test
    payTestChecks, payTestLoading, payTestStarted, payTestQrImage, payTestReallyPrice,
    payTestPolling, payTestPaid, payTestExpired, showPayTest, payTestChannelName,
    startChannelPayTest, startPayTestPolling, stopPayTestPolling, closePayTest,
    _payTestTimer: payTestTimer,
    payTestAccountId,
  }
}

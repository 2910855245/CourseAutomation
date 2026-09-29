<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { api, type OrderItem } from '@/api'
import { usePlatformNames } from '@/composables/usePlatformNames'
import AppTopbar from '@/components/AppTopbar.vue'
import { useConfirmSingleton } from '@/composables/useConfirm'

const route = useRoute()
const store = useAppStore()
const { showConfirm } = useConfirmSingleton()
const { load: loadPlatformNames, getName: getPlatformName } = usePlatformNames()

const orders = ref<OrderItem[]>([])
const loading = ref(false)
const statusFilter = ref('')
const detailOrder = ref<OrderItem | null>(null)

const taskTypeNames: Record<string, string> = { video: '视频', exam: '考试', full: '全包', chaoxing_points: '学习通积分' }

// 本页只查"本机下过的单"：后端没有按用户列订单的接口，
// 订单号 + view_token 存在 localStorage/sessionStorage 里（下单时由首页写入）。
const orderIds = ref<string[]>([])
const orderTokens: Record<string, string> = {}

function loadStoredIds() {
  const raw = sessionStorage.getItem('last_order_tokens') || localStorage.getItem('last_order_tokens') || ''
  for (const pair of raw.split(',')) {
    const [oid, tok] = pair.split(':')
    if (oid && tok) orderTokens[oid] = tok
  }
}

// ── 客户只看三种状态：待支付 / 处理中 / 已完成（失败与取消单独标出）──
type Group = 'todo' | 'running' | 'done' | 'failed'
function group(o: OrderItem): Group {
  if (o.status === 'completed') return 'done'
  if (o.status === 'failed' || o.status === 'cancelled') return 'failed'
  if (!o.paid) return 'todo'
  return 'running'
}
function tagLabel(o: OrderItem) {
  const g = group(o)
  if (g === 'done') return '已完成'
  if (g === 'failed') return o.status === 'cancelled' ? '已取消' : '失败'
  if (g === 'todo') return '待支付'
  return '处理中'
}
function tagClass(o: OrderItem) {
  const g = group(o)
  if (g === 'done') return 'ok'
  if (g === 'failed') return o.status === 'cancelled' ? 'muted' : 'bad'
  if (g === 'todo') return 'warn'
  return 'primary'
}
/** 进度条只在真的在跑的时候出现 */
function showProgress(o: OrderItem) { return group(o) === 'running' && pct(o) > 0 }
function pct(o: OrderItem) { return o.progress != null ? o.progress : 0 }

const filters: { key: string; label: string }[] = [
  { key: '', label: '全部' },
  { key: 'active', label: '处理中' },
  { key: 'done', label: '已完成' },
  { key: 'failed', label: '失败' },
]
const shown = computed(() => orders.value.filter(o => {
  if (!statusFilter.value) return true
  const g = group(o)
  if (statusFilter.value === 'active') return g === 'todo' || g === 'running'
  return g === statusFilter.value
}))
const hasPending = computed(() => orders.value.some(o => {
  const g = group(o)
  return g === 'todo' || g === 'running'
}))

let inFlight = false
async function load() {
  // 手动刷新与 10s 轮询可能撞在一起，后到的旧响应会覆盖新数据 → 只放行一个请求
  if (inFlight) return
  inFlight = true
  loading.value = true
  try {
    // 游客只能逐单查：并发发出，N 单不再串成 N 个 RTT
    const results = await Promise.all(orderIds.value.map(oid =>
      api.orders.get(oid, orderTokens[oid]).then(
        r => (r?.data as OrderItem) || null,
        () => null,   // 单条查不到就跳过（可能是别人的单或已清理）
      )
    ))
    orders.value = results.filter((o): o is OrderItem => !!o)
  } finally {
    loading.value = false
    inFlight = false
  }
}

// ── 实时更新：SSE 长连接（替代 10s 轮询）──
//
// 手机端最在意的是耗电：轮询是「每 10 秒 × N 单」的固定唤醒，而 SSE 只在
// 服务端真的有变化时推一帧，空闲时链路完全静默（服务端每 40s 一个保活注释）。
// 连接只在「页面可见 + 还有没跑完的单」时维持，其余时间一律断开：
// 后台挂着的连接、以及全部订单已终态后的连接，都只是耗电没有收益。
let es: EventSource | null = null
let streamFails = 0

const TERMINAL = ['completed', 'failed', 'cancelled']

function closeStream() {
  if (es) { es.close(); es = null }
}

function openStream() {
  if (es || orderIds.value.length === 0) return
  const spec = orderIds.value.map(id => `${id}:${orderTokens[id] || ''}`).join(',')
  es = new EventSource('/api/progress/sse/live?orders=' + encodeURIComponent(spec))
  // 首次建连与浏览器自动重连都会触发 onopen：都补拉一次，
  // 把断线/切后台期间错过的状态变化补齐
  es.onopen = () => { streamFails = 0; load() }
  es.onmessage = (ev) => {
    let msg: any
    try { msg = JSON.parse(ev.data) } catch { return }
    patchOrder(msg)
  }
  // 服务端广播缓冲被冲掉时会发 resync：整页重拉一次
  es.addEventListener('resync', () => { load() })
  es.onerror = () => {
    // EventSource 自带重连，但默认约 3 秒一次且不封顶：对端持续异常时会变成
    // 比轮询更费电的重连风暴，连续失败 3 次就放弃（下次切前台再重试）
    streamFails++
    if (streamFails >= 3 || es?.readyState === EventSource.CLOSED) closeStream()
  }
}

/** 把推送帧就地打进列表（引用不改，详情抽屉共享同一对象） */
function patchOrder(msg: any) {
  const d = msg?.data
  const oid = d?.order_id
  if (!oid) return
  const target = orders.value.find(o => o.order_id === oid)
  if (!target) { load(); return }
  if (d.status) target.status = d.status
  if (d.progress != null) target.progress = d.progress
  // 终态补一次拉取：拿 finished_at 等收尾字段
  if (TERMINAL.includes(d.status)) load()
}

/** 可见 + 有未跑完的单，才维持长连接 */
function syncStream() {
  if (document.hidden || !hasPending.value) closeStream()
  else openStream()
}

// 首屏拉一次全量，随后交给 SSE 推送；轮询只在 SSE 连不上时才有一点点意义，
// 所以这里不再保留定时器
onMounted(async () => {
  loadPlatformNames()
  const routeId = (route.params.id as string) || ''
  const urlIds = (route.query.ids as string) || ''
  const storedIds = sessionStorage.getItem('last_order_ids') || localStorage.getItem('last_order_ids') || ''
  const idsStr = routeId || urlIds || storedIds
  if (idsStr) orderIds.value = idsStr.split(',').filter(Boolean)
  loadStoredIds()
  await load()
  syncStream()
  document.addEventListener('visibilitychange', syncStream)

  if (routeId) {
    const target = orders.value.find(o => o.order_id === routeId)
    if (target) detailOrder.value = target
  }
})

watch(hasPending, syncStream)

onUnmounted(() => {
  closeStream()
  document.removeEventListener('visibilitychange', syncStream)
})

function copyId(id: string) {
  navigator.clipboard?.writeText(id).then(
    () => store.toast('订单号已复制', 'success'),
    () => store.toast('复制失败，请手动选择', 'warning'),
  )
}

async function cancel(id: string) {
  const ok = await showConfirm({ title: '取消订单', message: '确认取消该订单吗？取消后不可恢复。', type: 'warning' })
  if (!ok) return
  try {
    await api.orders.cancel(id, orderTokens[id])
    store.toast('订单已取消', 'success')
    load()
  } catch (e: any) { store.toast(e.message, 'error') }
}
/** 后端只允许非终态、非执行中的订单取消 */
function canCancel(o: OrderItem) {
  return !['completed', 'failed', 'running', 'cancelled'].includes(o.status)
}

async function clearHistory() {
  const ok = await showConfirm({ title: '清空历史', message: '确认清空所有已完成/失败/已取消的订单？此操作不可撤销。', type: 'danger' })
  if (!ok) return
  try {
    await api.orders.clearHistory()
    orderIds.value = []
    sessionStorage.removeItem('last_order_ids')
    localStorage.removeItem('last_order_ids')
    sessionStorage.removeItem('last_order_tokens')
    localStorage.removeItem('last_order_tokens')
    orders.value = []
    store.toast('历史订单已清空', 'success')
  } catch (e: any) { store.toast(e.message, 'error') }
}

// ── 支付（与首页同一套：弹窗 + 微信/支付宝 + 二维码 + 轮询到账）──
const showPayModal = ref(false)
const payQrCode = ref('')
const payTotal = ref(0)
const payBatchId = ref('')
const payBatchOutTradeNo = ref('')
const payMethod = ref<'ypay_wxpay' | 'ypay_alipay'>('ypay_wxpay')
const payPollTimer = ref<number | null>(null)
const payTimedOut = ref(false)
const payingOrderIds = ref<string[]>([])

async function repay(orderIds2: string[]) {
  payingOrderIds.value = orderIds2
  // 先开弹窗再请求：创建失败时由 createPay 关掉弹窗并给出提示，
  // 否则会停在"生成中…"且没有轮询的空壳弹窗里
  showPayModal.value = true
  await createPay('ypay_wxpay')
}

async function createPay(method: 'ypay_wxpay' | 'ypay_alipay') {
  payMethod.value = method
  payQrCode.value = ''
  payTimedOut.value = false
  try {
    const payRes = await api.payment.batchCreate({
      order_ids: payingOrderIds.value,
      pay_type: method === 'ypay_wxpay' ? 1 : 2,
    })
    const pd = (payRes?.data || {}) as any
    payBatchId.value = pd.batch_id || ''
    payBatchOutTradeNo.value = pd.out_trade_no || ''
    payQrCode.value = pd.qr_image || ''
    payTotal.value = pd.really_price || 0
    startPayPoll()
  } catch (e: any) {
    store.toast('创建支付失败：' + (e?.message || '网络错误'), 'error')
    showPayModal.value = false
  }
}

function startPayPoll() {
  if (payPollTimer.value) { clearTimeout(payPollTimer.value); payPollTimer.value = null }
  if (!payBatchId.value) return
  let pollCount = 0
  async function tick() {
    pollCount++
    try {
      const r = await api.payment.batchCheck(payBatchId.value, payBatchOutTradeNo.value) as any
      if (r?.paid) {
        if (payPollTimer.value) { clearTimeout(payPollTimer.value); payPollTimer.value = null }
        store.toast('支付成功！', 'success')
        showPayModal.value = false
        load()
        return
      }
      if (r?.expired || pollCount >= 120) {
        payTimedOut.value = true
        if (payPollTimer.value) { clearTimeout(payPollTimer.value); payPollTimer.value = null }
        return
      }
    } catch { /* 单次失败继续轮询 */ }
    payPollTimer.value = window.setTimeout(tick, 3000)
  }
  payPollTimer.value = window.setTimeout(tick, 3000)
}

function closePayModal() {
  showPayModal.value = false
  if (payPollTimer.value) { clearTimeout(payPollTimer.value); payPollTimer.value = null }
}

function savePayQr() {
  const src = payQrCode.value
  if (!src) return
  const a = document.createElement('a')
  a.href = src
  a.download = 'pay-qr.png'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

const fmtDate = (s?: string) => s ? s.replace('T', ' ').substring(0, 16) : '-'
const fmtMoney = (n: number) => `¥${(n || 0).toFixed(2)}`
</script>

<template>
  <div class="page">
    <AppTopbar :show-role-badge="true" />

    <div class="content-wrapper">
      <header class="page-head anim-rise">
        <h1 class="ph-title">我的订单</h1>
        <div class="ph-actions">
          <button class="btn btn-ghost btn-sm" :disabled="loading" @click="load">
            {{ loading ? '刷新中' : '刷新' }}
          </button>
          <button
            v-if="orders.some(o => group(o) === 'done' || group(o) === 'failed')"
            class="btn btn-ghost btn-sm"
            @click="clearHistory"
          >
            清空历史
          </button>
        </div>
      </header>

      <div v-if="orders.length" class="filter-row anim-rise">
        <div class="filter-bar">
          <button
            v-for="f in filters"
            :key="f.key"
            :class="['chip', { active: statusFilter === f.key }]"
            @click="statusFilter = f.key"
          >
            {{ f.label }}
          </button>
        </div>
        <span class="result-count"><span class="mono">{{ shown.length }}</span> 条</span>
      </div>

      <div v-if="!orders.length && !loading" class="empty anim-rise">
        <div class="empty-icon">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
        </div>
        <p class="empty-title">暂无订单</p>
        <router-link to="/" class="btn btn-primary">去下单</router-link>
      </div>

      <div v-else class="order-list">
        <article
          v-for="(o, i) in shown"
          :key="o.order_id"
          class="order-card anim-rise"
          :style="{ animationDelay: Math.min(i, 8) * 40 + 'ms' }"
          @click="detailOrder = o"
        >
          <header class="oc-head">
            <button
              class="oc-id code-tag mono"
              type="button"
              title="点击复制订单号"
              @click.stop="copyId(o.order_id)"
            >
              {{ o.order_id }}
            </button>
            <span :class="['status-tag', tagClass(o)]">{{ tagLabel(o) }}</span>
          </header>

          <div class="oc-meta">
            <span>{{ getPlatformName(o.website_id) }}</span>
            <span class="oc-sep">·</span>
            <span>{{ taskTypeNames[o.task_type] || o.task_type }}</span>
            <span class="oc-sep">·</span>
            <span class="mono">{{ fmtMoney(o.price) }}</span>
            <span class="oc-sep">·</span>
            <span class="mono">{{ fmtDate(o.created_at) }}</span>
          </div>

          <div v-if="showProgress(o)" class="oc-progress">
            <div class="ocp-bar">
              <div class="ocp-fill" :style="{ width: pct(o) + '%' }" />
            </div>
            <span class="ocp-pct mono">{{ pct(o) }}%</span>
          </div>

          <footer
            v-if="!o.paid || canCancel(o)"
            class="oc-actions"
            @click.stop
          >
            <button v-if="!o.paid" class="btn btn-primary btn-xs" @click="repay([o.order_id])">
              去支付
            </button>
            <button v-if="canCancel(o)" class="btn btn-ghost btn-xs" @click="cancel(o.order_id)">
              取消订单
            </button>
          </footer>
        </article>
      </div>
    </div>

    <footer class="page-footer">
      <span>Fuk 文理网课</span>
    </footer>

    <!-- 订单详情 -->
    <div v-if="detailOrder" class="modal-overlay show" @click.self="detailOrder = null">
      <div class="modal-box detail-modal">
        <div class="modal-header">
          <span>订单详情</span>
          <button class="modal-close" aria-label="关闭" @click="detailOrder = null">&times;</button>
        </div>
        <div class="modal-body">
          <div class="dm-row">
            <span class="dm-label">状态</span>
            <span class="dm-value">
              <span :class="['status-tag', tagClass(detailOrder)]">{{ tagLabel(detailOrder) }}</span>
            </span>
          </div>
          <div class="dm-row">
            <span class="dm-label">订单号</span>
            <span class="dm-value mono">{{ detailOrder.order_id }}</span>
          </div>
          <div class="dm-row">
            <span class="dm-label">学号</span>
            <span class="dm-value">{{ detailOrder.username }}</span>
          </div>
          <div class="dm-row">
            <span class="dm-label">平台 / 类型</span>
            <span class="dm-value">{{ getPlatformName(detailOrder.website_id) }} · {{ taskTypeNames[detailOrder.task_type] || detailOrder.task_type }}</span>
          </div>
          <div class="dm-row">
            <span class="dm-label">课程数量</span>
            <span class="dm-value"><span class="mono">{{ detailOrder.course_ids?.length || 0 }}</span> 门</span>
          </div>
          <div class="dm-row">
            <span class="dm-label">金额</span>
            <span class="dm-value money mono">{{ fmtMoney(detailOrder.price) }}</span>
          </div>
          <div class="dm-row">
            <span class="dm-label">下单时间</span>
            <span class="dm-value mono">{{ fmtDate(detailOrder.created_at) }}</span>
          </div>
          <div v-if="detailOrder.status === 'failed' && detailOrder.admin_note" class="dm-row">
            <span class="dm-label">失败原因</span>
            <span class="dm-value err">{{ detailOrder.admin_note }}</span>
          </div>
          <div v-if="showProgress(detailOrder)" class="dm-progress">
            <div class="ocp-bar">
              <div class="ocp-fill" :style="{ width: pct(detailOrder) + '%' }" />
            </div>
            <span class="ocp-pct mono">{{ pct(detailOrder) }}%</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 支付弹窗 -->
    <div v-if="showPayModal" class="modal-overlay show" @click.self="closePayModal">
      <div class="modal-box pay-modal">
        <div class="modal-header">
          <span>{{ payTimedOut ? '支付超时' : '扫码支付' }}</span>
          <button class="modal-close" aria-label="关闭" @click="closePayModal">&times;</button>
        </div>
        <div class="modal-body">
          <template v-if="payTimedOut">
            <p class="pm-desc">支付查询已超时，请点「刷新」查看支付状态。</p>
            <button class="btn btn-primary btn-block" @click="repay(payingOrderIds)">重新支付</button>
          </template>
          <template v-else>
            <p class="pm-warn">请支付相同金额，否则无法自动到账</p>
            <p class="pm-amount mono">{{ fmtMoney(payTotal) }}</p>
            <div class="pay-method-tabs">
              <button :class="['pm-tab', { active: payMethod === 'ypay_wxpay' }]" @click="createPay('ypay_wxpay')">
                微信
              </button>
              <button :class="['pm-tab', { active: payMethod === 'ypay_alipay' }]" @click="createPay('ypay_alipay')">
                支付宝
              </button>
            </div>
            <div class="pm-qr">
              <img v-if="payQrCode" :src="payQrCode" alt="支付二维码" class="pm-qr-img" />
              <div v-else class="pm-qr-placeholder">生成中…</div>
            </div>
            <p class="pm-hint">保存二维码后使用{{ payMethod === 'ypay_wxpay' ? '微信' : '支付宝' }}扫一扫支付</p>
          </template>
        </div>
        <div v-if="!payTimedOut" class="modal-footer col">
          <button v-if="payQrCode" class="btn btn-primary btn-block" @click="savePayQr">保存二维码</button>
          <button class="btn btn-ghost btn-block" @click="closePayModal">取消支付</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 结构约定：编号/金额/时间一律等宽数字；层次靠 1px 发丝描边。 */
.page { min-height: 100vh; display: flex; flex-direction: column; }

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: var(--space-5);
}
.ph-title {
  font-size: var(--fs-title);
  font-weight: 700;
  letter-spacing: var(--tracking-title);
  color: var(--c-text);
}
.ph-actions { display: flex; align-items: center; gap: 8px; }

.filter-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: var(--space-4);
  flex-wrap: wrap;
}
.result-count { font-size: 12.5px; color: var(--c-text-muted); }

.order-list { display: flex; flex-direction: column; gap: 12px; }

.order-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: 16px 18px;
  cursor: pointer;
  transition: border-color .2s ease, box-shadow .25s cubic-bezier(.32, .72, .35, 1), transform .25s cubic-bezier(.32, .72, .35, 1);
}
.order-card:hover {
  border-color: var(--c-border-strong);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.oc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.oc-id {
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  font-size: 13px;
  text-align: left;
}
.oc-id:hover { color: var(--c-primary); }

.oc-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12.5px;
  color: var(--c-text-secondary);
}
.oc-sep { color: var(--c-text-muted); }

.oc-progress {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}
.ocp-bar {
  flex: 1;
  height: 6px;
  background: var(--c-bg);
  border-radius: 999px;
  overflow: hidden;
}
.ocp-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--c-primary);
  transition: width .4s cubic-bezier(.32, .72, .35, 1);
}
.ocp-pct { font-size: 11.5px; color: var(--c-text-muted); min-width: 34px; text-align: right; }

.oc-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

/* ==================== 详情 ==================== */
.detail-modal { max-width: 460px; width: 100%; }
.dm-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  padding: 9px 0;
  border-bottom: 1px solid var(--c-border-light);
  font-size: 13px;
}
.dm-row:last-child { border-bottom: none; }
.dm-label { color: var(--c-text-muted); flex-shrink: 0; }
.dm-value { color: var(--c-text); text-align: right; word-break: break-all; }
.dm-value.err { color: var(--c-danger); }
.dm-progress { display: flex; align-items: center; gap: 10px; margin-top: 12px; }

/* ==================== 支付 ==================== */
.pay-modal { max-width: 380px; width: 100%; }
.pm-warn { font-size: 12px; color: var(--c-warning); text-align: center; margin-bottom: 6px; }
.pm-desc { font-size: 13px; color: var(--c-text-secondary); text-align: center; margin-bottom: 16px; }
.pm-amount {
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.02em;
  text-align: center;
  color: var(--c-text);
  margin-bottom: 14px;
}
.pay-method-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}
.pm-tab {
  flex: 1;
  padding: 9px 0;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  background: var(--c-surface);
  color: var(--c-text-secondary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color .2s ease, color .2s ease, background .2s ease;
}
.pm-tab.active {
  border-color: transparent;
  background: var(--c-primary-bg);
  color: var(--c-primary);
}
.pm-qr {
  display: flex;
  align-items: center;
  justify-content: center;
  /* 二维码固定白底，暗色模式下才扫得出来 */
  background: #fff;
  border-radius: 14px;
  padding: 14px;
  min-height: 208px;
}
.pm-qr-img { width: 200px; height: 200px; display: block; }
.pm-qr-placeholder { font-size: 13px; color: var(--c-text-muted); }
.pm-hint { font-size: 12px; color: var(--c-text-muted); text-align: center; margin-top: 12px; }
.modal-footer.col { flex-direction: column; gap: 8px; }

.page-footer {
  margin-top: auto;
  padding: var(--space-6) var(--space-5);
  text-align: center;
  font-size: 12px;
  color: var(--c-text-muted);
}

@media (max-width: 560px) {
  .page-head { align-items: flex-start; }
  .oc-meta { font-size: 12px; }
  .pm-amount { font-size: 26px; }
}
</style>
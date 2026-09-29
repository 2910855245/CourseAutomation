<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useRealtimeStore } from '@/stores/realtime'
import { api, type OrderItem } from '@/api'
import { usePlatformNames } from '@/composables/usePlatformNames'
import AppTopbar from '@/components/AppTopbar.vue'
import { useConfirmSingleton } from '@/composables/useConfirm'

const route = useRoute()
const store = useAppStore()
const { showConfirm } = useConfirmSingleton()


const orders = ref<OrderItem[]>([])
const changedIds = ref(new Set<string>())
const realtime = useRealtimeStore()

// 实时推进：收到 order.update 只重拉这一条订单（原先是一条消息整表重载）。
// 同一条订单在短时间内可能连续来多帧，按 order_id 合并到一次请求。
const refreshTimers = new Map<string, number>()
let unsubscribeRealtime: (() => void) | null = null
let fallbackTimer: number | null = null

function scheduleRefresh(orderId: string) {
  if (!orderId) { load(); return }
  const pending = refreshTimers.get(orderId)
  if (pending !== undefined) clearTimeout(pending)
  refreshTimers.set(orderId, window.setTimeout(() => {
    refreshTimers.delete(orderId)
    refreshOne(orderId)
  }, 300))
}

async function refreshOne(orderId: string) {
  const idx = orders.value.findIndex(o => o.order_id === orderId)
  if (idx < 0) return
  try {
    const res = await api.orders.get(orderId, guestOrderTokens[orderId])
    const item = res?.data
    if (!item) return
    const old = orders.value[idx]
    if (old && (old.status !== item.status || old.progress !== item.progress)) {
      const next = new Set(changedIds.value)
      next.add(orderId)
      changedIds.value = next
    }
    orders.value[idx] = item
  } catch {
    // 单条刷新失败不打断页面：下一次事件或兜底轮询会补上
  }
}

/** 游客把逐单 view_token 交给服务端做 topic 白名单（服务端过滤，非客户端） */
function syncRealtimeScope() {
  realtime.renewGuestScope(
    orders.value
      .map(o => ({ order_id: o.order_id, view_token: guestOrderTokens[o.order_id] || '' }))
      .filter(o => o.view_token),
  )
}

const statusFilter = ref('')
const searchQuery = ref('')
const currentPage = ref(1)
const totalPages = ref(1)
const totalOrders = ref(0)
const pageSize = 50
const detailOrder = ref<OrderItem | null>(null)
const auditLogs = ref<{ event: string; detail: string; created_at: string }[]>([])
const taskTypeNames: Record<string, string> = { video: '视频', exam: '考试', full: '全包', chaoxing_points: '学习通积分' }
// 刷课节奏档位（历史订单无该字段 → 回退均衡）
const speedModeNames: Record<string, string> = { turbo: '急速', balanced: '均衡', gentle: '温柔' }
const speedModeLabel = (m?: string) => speedModeNames[m || 'balanced'] || '均衡'
const guestOrderIds = ref<string[]>([])
const guestOrderTokens: Record<string, string> = {}

function loadGuestTokens() {
  const raw = sessionStorage.getItem('last_order_tokens') || localStorage.getItem('last_order_tokens') || ''
  for (const pair of raw.split(',')) {
    const [oid, tok] = pair.split(':')
    if (oid && tok) guestOrderTokens[oid] = tok
  }
}

// 支付相关
const showPayModal = ref(false)
const payQrCode = ref('')
const payTotal = ref(0)
const payBatchId = ref('')
const payBatchOutTradeNo = ref('')
const payMethod = ref<'ypay_wxpay' | 'ypay_alipay'>('ypay_wxpay')
const payPollTimer = ref<number | null>(null)
const payTimedOut = ref(false)
const payingOrderIds = ref<string[]>([])

const { load: loadPlatformNames, getName: getPlatformName } = usePlatformNames()

const statusLabels: Record<string, string> = {
  pending: '待处理', accepted: '已接单', running: '执行中',
  completed: '已完成', failed: '失败', cancelled: '已取消',
  queued: '排队中', retrying: '重试中', paid: '已支付',
  waiting: '等待明天',
}
const activeStatuses = ['pending', 'accepted', 'queued', 'running', 'retrying', 'paid', 'waiting']

const filteredOrders = computed(() => orders.value)
const activeCount = computed(() => orders.value.filter(o => activeStatuses.includes(o.status)).length)
const doneCount = computed(() => orders.value.filter(o => o.status === 'completed').length)

function statusLabel(s: string) { return statusLabels[s] || s }

function onSearch() {
  currentPage.value = 1
  load()
}

function goPage(p: number) {
  currentPage.value = p
  load()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function load() {
  try {
    // 用 sessionStorage 的订单 ID 逐个查询（view token 鉴权）
    if (guestOrderIds.value.length > 0) {
      const items: OrderItem[] = []
      for (const oid of guestOrderIds.value) {
        try {
          const r = await api.orders.get(oid, guestOrderTokens[oid])
          if (r?.data) items.push(r.data as OrderItem)
        } catch { /* skip */ }
      }
      if (items.length > 0) {
        orders.value = items
        totalOrders.value = items.length
        return
      }
    }
    if (guestOrderIds.value.length === 0) {
      orders.value = []
      totalOrders.value = 0
      return
    }
    // 登录用户：调后端列表接口，显示所有订单
    const params: any = { page: currentPage.value, page_size: pageSize }
    if (statusFilter.value) params.status = statusFilter.value
    if (searchQuery.value) params.search = searchQuery.value
    const res = await api.orders.list(params)
    const items: OrderItem[] = res?.data?.items || []
    totalPages.value = (res?.data as any)?.total_pages || 1
    totalOrders.value = res?.data?.total || 0
    const oldMap = new Map(orders.value.map(o => [o.order_id, o]))
    const newIds = new Set<string>()
    for (const item of items) {
      const old = oldMap.get(item.order_id)
      if (old && (old.status !== item.status || old.progress !== item.progress)) {
        newIds.add(item.order_id)
      }
    }
    changedIds.value = newIds
    orders.value = items
  } catch (e: any) {
    // If auth fails and we have guest IDs, retry as guest
    if (guestOrderIds.value.length > 0) {
            load()
      return
    }
    store.toast(e?.message || '加载订单失败', 'error')
  }
}

onMounted(async () => {
  try {
    loadPlatformNames()
    const hasToken = !!localStorage.getItem('user_token')
    const routeId = route.params.id as string || ''

    if (hasToken) {
          } else if (routeId) {
      guestOrderIds.value = [routeId]
          } else {
      const urlIds = (route.query.ids as string) || ''
      const storedIds = sessionStorage.getItem('last_order_ids') || localStorage.getItem('last_order_ids') || ''
      const idsStr = urlIds || storedIds
      if (idsStr) {
        guestOrderIds.value = idsStr.split(',').filter(Boolean)
      }
          }

    loadGuestTokens()
    await load()

    // 如果URL带订单ID，自动打开该订单详情
    if (routeId && orders.value.length > 0) {
      const target = orders.value.find(o => o.order_id === routeId)
      if (target) showDetail(target)
    }
  } catch (e) {
    console.error('Orders init error:', e)
  }

  // 复用全站唯一的 WS 连接（原先这里重复建了第二条）
  realtime.setAdminToken(localStorage.getItem('admin_token') || '')
  syncRealtimeScope()
  unsubscribeRealtime = realtime.subscribe(['order:', 'dashboard'], (msg) => {
    if (msg.type === 'order.update') {
      scheduleRefresh(msg.data?.order_id || '')
    } else if (msg.type === 'progress') {
      scheduleRefresh(msg.data?.order_id || '')
    }
  })

  // 兜底：WS 断开期间才慢轮询（连接正常时完全不发请求）
  fallbackTimer = window.setInterval(() => {
    if (!realtime.connected) load()
  }, 60_000)
})

onUnmounted(() => {
  unsubscribeRealtime?.()
  unsubscribeRealtime = null
  if (fallbackTimer !== null) { clearInterval(fallbackTimer); fallbackTimer = null }
  for (const t of refreshTimers.values()) clearTimeout(t)
  refreshTimers.clear()
  // 连接是全站共享的，这里不关闭
})

async function cancel(id: string) {
  const ok = await showConfirm({ title: '取消订单', message: '确认取消该订单吗？取消后不可恢复。', type: 'warning' })
  if (!ok) return
  try {
    await api.orders.cancel(id, guestOrderTokens[id])
    store.toast('订单已取消', 'success')
    load()
  } catch (e: any) { store.toast(e.message, 'error') }
}

async function clearHistory() {
  const ok = await showConfirm({ title: '清空历史', message: '确认清空所有已完成/失败/已取消的订单？此操作不可撤销。', type: 'danger' })
  if (!ok) return
  try {
    await api.orders.clearHistory()
    guestOrderIds.value = []
    sessionStorage.removeItem('last_order_ids')
    localStorage.removeItem('last_order_ids')
    sessionStorage.removeItem('last_order_tokens')
    localStorage.removeItem('last_order_tokens')
    orders.value = []
    totalOrders.value = 0
    store.toast('历史订单已清空', 'success')
  } catch (e: any) { store.toast(e.message, 'error') }
}

async function repay(orderIds: string[]) {
  payingOrderIds.value = orderIds
  payMethod.value = 'ypay_wxpay'
  payQrCode.value = ''
  payTotal.value = 0
  payBatchId.value = ''
  payBatchOutTradeNo.value = ''
  payTimedOut.value = false
  showPayModal.value = true
  try {
    const payRes = await api.payment.batchCreate({ order_ids: orderIds, pay_type: 1 })
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

function switchPayMethod(method: 'ypay_wxpay' | 'ypay_alipay') {
  if (payMethod.value === method) return
  payMethod.value = method
  const payType = method === 'ypay_wxpay' ? 1 : 2
  payQrCode.value = ''
  api.payment.batchCreate({ order_ids: payingOrderIds.value, pay_type: payType }).then(r => {
    const pd = (r?.data || {}) as any
    payBatchId.value = pd.batch_id || ''
    payBatchOutTradeNo.value = pd.out_trade_no || ''
    payQrCode.value = pd.qr_image || ''
    payTotal.value = pd.really_price || payTotal.value
    startPayPoll()
  }).catch(() => { store.toast('切换支付方式失败', 'error') })
}

function startPayPoll() {
  if (payPollTimer.value) { clearTimeout(payPollTimer.value); payPollTimer.value = null }
  if (!payBatchId.value) return
  let pollCount = 0
  const maxPolls = 120
  async function tick() {
    pollCount++
    try {
      const r = await api.payment.batchCheck(payBatchId.value, payBatchOutTradeNo.value) as any
      if (r?.expired || pollCount >= maxPolls) {
        payTimedOut.value = true
        if (payPollTimer.value) { clearTimeout(payPollTimer.value); payPollTimer.value = null }
        store.toast('支付超时，请到订单页查看状态', 'warning')
        return
      }
      if (r?.paid) {
        if (payPollTimer.value) { clearTimeout(payPollTimer.value); payPollTimer.value = null }
        store.toast('支付成功！', 'success')
        showPayModal.value = false
        load()
        return
      }
    } catch {}
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

function pct(o: OrderItem) { return o.progress != null ? o.progress : 0 }

const fmtTime = (s: string) => s ? s.replace('T', ' ').substring(0, 19) : '-'
const fmtDate = (s: string) => s ? s.replace('T', ' ').substring(0, 19) : '-'
const fmtMoney = (n: number) => `¥${(n || 0).toFixed(2)}`
const statusClass: Record<string, string> = { pending: 'warn', accepted: 'primary', queued: 'primary', running: 'primary', completed: 'ok', failed: 'bad', cancelled: 'muted', waiting: 'warn' }


function showDetail(o: OrderItem) {
  detailOrder.value = o
  auditLogs.value = []
  api.orders.auditLog(o.order_id, guestOrderTokens[o.order_id]).then((r: any) => {
    auditLogs.value = r?.data || []
  }).catch(() => {})
}
function closeDetail() { detailOrder.value = null }
</script>

<template>
  <div class="page">
    <AppTopbar :show-role-badge="true" />

    <div class="content-wrapper">
      <!-- 页头：只留一个标题 + 真实连接状态（不再叠「订单中心/我的订单」两层同名标题） -->
      <header class="page-head anim-rise">
        <div class="ph-row">
          <h1 class="ph-title">我的订单</h1>
          <span class="ph-live" :class="{ off: !realtime.connected }">
            <span class="live-dot"></span>
            {{ realtime.connected ? '实时同步' : '连接已断开' }}
          </span>
        </div>
      </header>

      <!-- 概览 -->
      <div v-if="orders.length" class="stat-row anim-rise">
        <div class="stat">
          <span class="stat-val mono">{{ orders.length }}</span>
          <span class="stat-label">全部订单</span>
        </div>
        <div class="stat">
          <span class="stat-val mono">{{ activeCount }}</span>
          <span class="stat-label">进行中</span>
        </div>
        <div class="stat">
          <span class="stat-val mono">{{ doneCount }}</span>
          <span class="stat-label">已完成</span>
        </div>
      </div>

      <!-- 搜索 -->
      <div v-if="orders.length || searchQuery" class="search-bar anim-rise">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索订单号…"
          class="search-input"
          @keyup.enter="onSearch"
        />
        <button class="btn btn-primary" @click="onSearch">搜索</button>
      </div>

      <!-- 筛选 + 结果计数 + 清空历史：左右对称 -->
      <div v-if="orders.length || statusFilter" class="section-actions filter-section anim-rise">
        <div class="filter-bar">
          <button :class="['chip', { active: statusFilter === '' }]" @click="statusFilter = ''; load()">
            全部
          </button>
          <button :class="['chip', { active: statusFilter === 'pending' }]" @click="statusFilter = 'pending'; load()">
            待处理
          </button>
          <button :class="['chip', { active: statusFilter === 'running' }]" @click="statusFilter = 'running'; load()">
            执行中
          </button>
          <button :class="['chip', { active: statusFilter === 'completed' }]" @click="statusFilter = 'completed'; load()">
            已完成
          </button>
          <button :class="['chip', { active: statusFilter === 'failed' }]" @click="statusFilter = 'failed'; load()">
            失败
          </button>
          <button :class="['chip', { active: statusFilter === 'waiting' }]" @click="statusFilter = 'waiting'; load()">
            等待明天
          </button>
        </div>
        <div class="filter-right">
          <span class="result-count"><span class="mono">{{ totalOrders }}</span> 条结果</span>
          <button v-if="orders.length" class="btn btn-ghost btn-sm" @click="clearHistory">清空历史</button>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="!orders.length" class="empty anim-rise">
        <div class="empty-icon">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
        </div>
        <p class="empty-title">暂无订单</p>
        <p class="empty-sub">提交任务后可在此查看进度</p>
        <router-link to="/" class="btn btn-primary">去下单</router-link>
      </div>

      <!-- 订单列表：三段式卡片 -->
      <div v-else class="order-list">
        <article
          v-for="(o, i) in filteredOrders"
          :key="o.order_id"
          class="order-card anim-rise"
          :class="{
            'is-completed': o.status === 'completed',
            'is-failed': o.status === 'failed',
            'is-cancelled': o.status === 'cancelled',
          }"
          :style="{ animationDelay: Math.min(i, 8) * 45 + 'ms' }"
          @click="showDetail(o)"
        >
          <!-- 顶部：订单号 + 状态 -->
          <header class="oc-head">
            <div class="oc-head-left">
              <span class="oc-id code-tag mono">{{ o.order_id }}</span>
              <span v-if="changedIds.has(o.order_id)" class="badge">已更新</span>
            </div>
            <span class="status-tag" :class="statusClass[o.status] || 'primary'">{{ statusLabel(o.status) }}</span>
          </header>

          <!-- 中部：字段组 -->
          <div class="oc-fields">
            <div class="oc-field">
              <span class="ocf-l">平台</span>
              <span class="ocf-v">{{ getPlatformName(o.website_id) }}</span>
            </div>
            <div class="oc-field">
              <span class="ocf-l">类型</span>
              <span class="ocf-v">{{ taskTypeNames[o.task_type] || o.task_type }}</span>
            </div>
            <div v-if="o.website_id !== 4" class="oc-field">
              <span class="ocf-l">节奏</span>
              <span class="ocf-v">{{ speedModeLabel(o.speed_mode) }}</span>
            </div>
            <div class="oc-field">
              <span class="ocf-l">金额</span>
              <span class="ocf-v amount mono">¥{{ o.price.toFixed(2) }}</span>
            </div>
          </div>

          <!-- 进行中：进度条 -->
          <div v-if="activeStatuses.includes(o.status) && pct(o) > 0" class="oc-progress">
            <div class="ocp-bar">
              <div class="ocp-fill" :style="{ width: pct(o) + '%' }"></div>
            </div>
            <span class="ocp-pct mono">{{ pct(o) }}%</span>
          </div>

          <!-- 底部：时间 + 待处理操作 -->
          <footer class="oc-foot">
            <div class="oc-times">
              <span class="oct"><em>创建</em><span class="mono">{{ fmtTime(o.created_at) }}</span></span>
              <span class="oct"><em>更新</em><span class="mono">{{ fmtTime(o.updated_at || '') }}</span></span>
            </div>
            <div v-if="o.status === 'pending'" class="oc-actions">
              <button v-if="!o.paid" type="button" class="btn btn-primary btn-xs" @click.stop="repay([o.order_id])">去支付</button>
              <button type="button" class="btn btn-ghost btn-xs" @click.stop="cancel(o.order_id)">取消</button>
            </div>
          </footer>
        </article>
      </div>

      <div v-if="totalPages > 1" class="pagination">
        <button :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">
          上一页
        </button>
        <span v-for="p in totalPages" :key="p">
          <button :class="{ active: p === currentPage }" @click="goPage(p)">{{ p }}</button>
        </span>
        <button :disabled="currentPage >= totalPages" @click="goPage(currentPage + 1)">
          下一页
        </button>
        <span class="pg-info">共 <span class="mono">{{ totalOrders }}</span> 条</span>
      </div>
    </div>

    <footer class="page-footer">
      <span>Fuk 文理网课</span>
    </footer>

    <div v-if="detailOrder" class="modal-overlay show" @click.self="closeDetail">
      <div class="modal-box detail-modal">
        <div class="modal-header">
          <span>订单详情</span>
          <button class="modal-close" aria-label="关闭" @click="closeDetail">&times;</button>
        </div>
        <div class="modal-body">
          <div class="dm-grid">
            <div class="dm-row">
              <span class="dm-label">订单编号</span>
              <span class="dm-value mono">{{ detailOrder.order_id }}</span>
            </div>
            <div class="dm-row">
              <span class="dm-label">学号</span>
              <span class="dm-value">{{ detailOrder.username }}</span>
            </div>
            <div class="dm-row">
              <span class="dm-label">平台</span>
              <span class="dm-value">{{ getPlatformName(detailOrder.website_id) }}</span>
            </div>
            <div class="dm-row">
              <span class="dm-label">任务类型</span>
              <span class="dm-value">{{ taskTypeNames[detailOrder.task_type] || detailOrder.task_type }}</span>
            </div>
            <div v-if="detailOrder.website_id !== 4" class="dm-row">
              <span class="dm-label">刷课节奏</span>
              <span class="dm-value">{{ speedModeLabel(detailOrder.speed_mode) }}</span>
            </div>
            <div class="dm-row">
              <span class="dm-label">课程数量</span>
              <span class="dm-value"><span class="mono">{{ detailOrder.course_ids?.length || 0 }}</span> 门</span>
            </div>
            <div class="dm-row">
              <span class="dm-label">视频数量</span>
              <span class="dm-value"><span class="mono">{{ detailOrder.video_count }}</span> 个</span>
            </div>
            <div class="dm-row">
              <span class="dm-label">订单金额</span>
              <span class="dm-value money mono">{{ fmtMoney(detailOrder.price) }}</span>
            </div>
            <div class="dm-row">
              <span class="dm-label">支付状态</span>
              <span class="dm-value">
                <span class="status-tag" :class="detailOrder.paid ? 'ok' : 'warn'">{{ detailOrder.paid ? '已支付' : '未支付' }}</span>
              </span>
            </div>
            <div class="dm-row">
              <span class="dm-label">当前状态</span>
              <span class="dm-value">
                <span class="status-tag" :class="statusClass[detailOrder.status] || 'muted'">{{ statusLabel(detailOrder.status) }}</span>
              </span>
            </div>
            <div class="dm-row">
              <span class="dm-label">创建时间</span>
              <span class="dm-value mono">{{ fmtDate(detailOrder.created_at) }}</span>
            </div>
            <div v-if="detailOrder.accepted_at" class="dm-row">
              <span class="dm-label">接单时间</span>
              <span class="dm-value mono">{{ fmtDate(detailOrder.accepted_at) }}</span>
            </div>
            <div v-if="detailOrder.started_at" class="dm-row">
              <span class="dm-label">开始时间</span>
              <span class="dm-value mono">{{ fmtDate(detailOrder.started_at) }}</span>
            </div>
            <div v-if="detailOrder.updated_at" class="dm-row">
              <span class="dm-label">更新时间</span>
              <span class="dm-value mono">{{ fmtDate(detailOrder.updated_at) }}</span>
            </div>
            <div v-if="detailOrder.finished_at" class="dm-row">
              <span class="dm-label">完成时间</span>
              <span class="dm-value mono">{{ fmtDate(detailOrder.finished_at) }}</span>
            </div>
            <div v-if="detailOrder.status === 'failed' && detailOrder.admin_note" class="dm-row">
              <span class="dm-label">失败原因</span>
              <span class="dm-value err">{{ detailOrder.admin_note }}</span>
            </div>
          </div>

          <!-- 审计日志：竖向时间线 -->
          <div v-if="auditLogs.length" class="dm-audit">
            <span class="eyebrow">操作日志</span>
            <div class="timeline">
              <div v-for="log in auditLogs" :key="log.created_at" class="tl-item">
                <span class="tl-dot"></span>
                <div class="tl-main">
                  <div class="tl-top">
                    <span class="tl-event">{{ log.event }}</span>
                    <span class="tl-time mono">{{ fmtDate(log.created_at) }}</span>
                  </div>
                  <p v-if="log.detail" class="tl-detail">{{ log.detail }}</p>
                </div>
              </div>
            </div>
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
            <p class="pm-desc">支付查询已超时，请到订单页查看支付状态。</p>
          </template>
          <template v-else>
            <p class="pm-warn">请支付相同金额，否则无法自动到账</p>
            <p class="pm-amount mono">¥{{ payTotal.toFixed(2) }}</p>
            <div class="pay-method-tabs">
              <button :class="['pm-tab', { active: payMethod === 'ypay_wxpay' }]" @click="switchPayMethod('ypay_wxpay')">
                微信
              </button>
              <button :class="['pm-tab', { active: payMethod === 'ypay_alipay' }]" @click="switchPayMethod('ypay_alipay')">
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
        <div class="modal-footer col">
          <template v-if="payTimedOut">
            <button class="btn btn-primary btn-block" @click="closePayModal">关闭</button>
          </template>
          <template v-else>
            <button v-if="payQrCode" class="btn btn-primary btn-block" @click="savePayQr">保存二维码</button>
            <button class="btn btn-ghost btn-block" @click="closePayModal">取消支付</button>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ============================================================
   Paper & Signal — 订单页
   约定：编号 / 金额 / 百分比 / 时间一律等宽数字；
   结构靠 1px 发丝描边，阴影只表达"浮起"
   ============================================================ */

.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.content-wrapper {
  flex: 1;
  max-width: 900px;
  padding-top: var(--space-10);
  padding-bottom: var(--space-12);
}

/* ==================== 页头 ==================== */
.page-head { margin-bottom: var(--space-5); }

.ph-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-top: var(--space-3);
}

.ph-title {
  font-size: var(--fs-h);
  font-weight: 700;
  letter-spacing: var(--tracking-title);
}

.ph-live {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
}
/* 断线时给出明确告警，而不是继续显示一句「实时更新」骗自己 */
.ph-live.off { color: var(--c-warning); }

.live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--c-success);
  animation: pulse-dot 2.2s var(--ease) infinite;
}
.ph-live.off .live-dot { background: var(--c-warning); animation: none; }

/* ==================== 概览 ==================== */
.stat-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-4) var(--space-5);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs), var(--hairline-top);
}

.stat-val {
  font-size: var(--fs-h);
  font-weight: 700;
  letter-spacing: -.02em;
  line-height: 1.15;
}

.stat-label {
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
}

/* ==================== 搜索 ==================== */
.search-bar {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.search-bar .search-input { flex: 1; max-width: none; }

/* ==================== 筛选 ==================== */
.filter-section { margin-bottom: var(--space-5); }

.filter-right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.result-count {
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
  white-space: nowrap;
}

/* ==================== 订单卡片 ==================== */
.order-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.order-card {
  padding: var(--space-5);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs), var(--hairline-top);
  cursor: pointer;
  transition: transform var(--t) var(--ease), box-shadow var(--t) var(--ease),
              border-color var(--t) var(--ease);
}

.order-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md), var(--hairline-top);
  border-color: var(--c-border-strong);
}

.order-card.is-completed { border-left: 2px solid var(--c-success); }
.order-card.is-failed { border-left: 2px solid var(--c-danger); }
.order-card.is-cancelled { opacity: .6; }

.oc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.oc-head-left {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  flex-wrap: wrap;
}

.oc-id { font-size: var(--fs-xs); }

.oc-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
  gap: var(--space-3) var(--space-4);
}

.oc-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.ocf-l {
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
}

.ocf-v {
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--c-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ocf-v.amount {
  font-size: var(--fs-lg);
  font-weight: 700;
  letter-spacing: -.02em;
}

.oc-progress {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.ocp-bar {
  flex: 1;
  height: 5px;
  border-radius: var(--radius-pill);
  background: var(--c-surface-3);
  overflow: hidden;
}

.ocp-fill {
  height: 100%;
  border-radius: var(--radius-pill);
  background: var(--c-primary);
  transition: width var(--t-slow) var(--ease-out);
}

.ocp-pct {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--c-primary);
  min-width: 40px;
  text-align: right;
}

.oc-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-top: var(--space-4);
  padding-top: var(--space-3);
  border-top: 1px solid var(--c-border-light);
}

.oc-times {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
}

.oct { display: inline-flex; align-items: center; gap: 6px; }
.oct em { font-style: normal; opacity: .8; }

.oc-actions {
  display: flex;
  gap: var(--space-2);
  margin-left: auto;
}

/* ==================== 分页 ==================== */
.pg-info {
  margin-left: var(--space-2);
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
}

.pg-info .mono { color: var(--c-text-secondary); }

/* ==================== 详情弹窗 ==================== */
.detail-modal { max-width: 520px; }

.dm-grid { display: flex; flex-direction: column; }

/* 字段行：label 左 / value 右 的两列对齐网格 */
.dm-row {
  display: grid;
  grid-template-columns: 92px 1fr;
  gap: var(--space-3);
  align-items: baseline;
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--c-border-light);
}

.dm-row:last-child { border-bottom: none; }

.dm-label {
  font-size: var(--fs-sm);
  color: var(--c-text-muted);
}

.dm-value {
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--c-text);
  text-align: right;
  word-break: break-all;
}

.dm-value.money { color: var(--c-primary); font-weight: 700; }
.dm-value.err { color: var(--c-danger); }

/* 审计日志：竖向时间线 */
.dm-audit {
  margin-top: var(--space-5);
  padding-top: var(--space-4);
  border-top: 1px solid var(--c-border);
}

.timeline {
  position: relative;
  margin-top: var(--space-4);
  padding-left: var(--space-5);
}

.timeline::before {
  content: '';
  position: absolute;
  left: 4px;
  top: 4px;
  bottom: 4px;
  width: 1px;
  background: var(--c-border);
}

.tl-item {
  position: relative;
  padding-bottom: var(--space-4);
}

.tl-item:last-child { padding-bottom: 0; }

.tl-dot {
  position: absolute;
  left: -19px;
  top: 5px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--c-primary);
  box-shadow: 0 0 0 3px var(--c-primary-bg);
}

.tl-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tl-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.tl-event {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--c-text);
}

.tl-time {
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
}

.tl-detail {
  font-size: var(--fs-xs);
  color: var(--c-text-secondary);
  line-height: 1.6;
}

/* ==================== 支付弹窗 ==================== */
.pay-modal { max-width: 400px; }
.pm-desc { font-size: var(--fs-sm); color: var(--c-text-secondary); line-height: 1.7; }

.pm-warn {
  font-size: var(--fs-xs);
  color: var(--c-warning);
  text-align: center;
}

.pm-amount {
  font-size: 34px;
  font-weight: 800;
  letter-spacing: -.02em;
  color: var(--c-text);
  text-align: center;
  margin: var(--space-2) 0 var(--space-4);
}

.pay-method-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3px;
  padding: 3px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-border-light);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
}

.pm-tab {
  padding: 8px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--c-text-secondary);
  font-family: inherit;
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease);
}

.pm-tab.active {
  background: var(--c-surface);
  color: var(--c-text);
  box-shadow: var(--shadow-xs);
}

.pm-qr { display: flex; justify-content: center; margin-bottom: var(--space-3); }

/* 二维码需固定白底以保证暗色下可扫描 */
.pm-qr-img {
  width: 190px;
  height: 190px;
  padding: 8px;
  background: #fff;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
}

.pm-qr-placeholder {
  width: 190px;
  height: 190px;
  display: grid;
  place-content: center;
  border: 1px dashed var(--c-border);
  border-radius: var(--radius-md);
  color: var(--c-text-muted);
  font-size: var(--fs-sm);
}

.pm-hint {
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
  text-align: center;
}

.modal-footer.col { flex-direction: column; gap: var(--space-2); }

/* ==================== 页脚 ==================== */
.page-footer {
  padding: var(--space-8) var(--space-6) var(--space-6);
  text-align: center;
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
}

/* ==================== 响应式 ==================== */
@media (max-width: 768px) {
  .content-wrapper { padding-top: var(--space-6); padding-bottom: var(--space-10); }
  .ph-title { font-size: var(--fs-title); }

  .stat-row { gap: var(--space-2); }
  .stat { padding: var(--space-3); }
  .stat-val { font-size: var(--fs-title); }

  .search-bar { flex-wrap: wrap; }

  .filter-right { width: 100%; justify-content: space-between; }

  .order-card { padding: var(--space-4); }
  /* 字段组：窄屏改单列紧凑排布 */
  .oc-fields { grid-template-columns: 1fr; gap: 6px; }
  .oc-field { flex-direction: row; align-items: baseline; justify-content: space-between; gap: var(--space-3); }
  .ocf-v.amount { font-size: var(--fs-md); }

  .oc-foot { align-items: flex-start; }
  .oc-actions { margin-left: 0; }

  .dm-row { grid-template-columns: 80px 1fr; }
  .detail-modal, .pay-modal { max-width: 100%; }
}
</style>

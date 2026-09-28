<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { api, type OrderItem } from '@/api'
import { usePlatformNames } from '@/composables/usePlatformNames'
import AppTopbar from '@/components/AppTopbar.vue'
import { useConfirmSingleton } from '@/composables/useConfirm'

const route = useRoute()
const store = useAppStore()
const { showConfirm } = useConfirmSingleton()


const orders = ref<OrderItem[]>([])
let changedIds = new Set<string>()
let ws: WebSocket | null = null

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  try {
    ws = new WebSocket(`${proto}//${location.host}/api/progress/ws/live`)
    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data)
        if (d.type === 'progress' || d.type === 'job_update' || d.type === 'order_update') {
          load()
        }
      } catch {}
    }
    ws.onclose = () => { setTimeout(connectWS, 5000) }
  } catch {}
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
    changedIds = newIds
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
    connectWS()
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

  connectWS()
})
onUnmounted(() => { if (ws) { ws.close(); ws = null } })

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
  api.orders.auditLog(o.order_id).then((r: any) => {
    auditLogs.value = r?.data || []
  }).catch(() => {})
}
function closeDetail() { detailOrder.value = null }
</script>

<template>
  <div class="page">
    <AppTopbar :show-role-badge="true" />

    <div class="content-wrapper">
      <div class="page-header">
        <div class="ph-left">
          <h1>我的订单</h1>
          <div class="ph-sub">
            <span class="live-dot"></span>
            <span>订单状态实时更新</span>
          </div>
        </div>
        <button v-if="orders.length" class="btn-clear-history" @click="clearHistory">
          清空历史
        </button>
      </div>

      <div v-if="orders.length" class="order-stats">
        <div class="os-item"><b>{{ orders.length }}</b><span>全部订单</span></div>
        <div class="os-divider"></div>
        <div class="os-item"><b>{{ activeCount }}</b><span>进行中</span></div>
        <div class="os-divider"></div>
        <div class="os-item"><b>{{ doneCount }}</b><span>已完成</span></div>
      </div>

      <div v-if="orders.length || searchQuery" class="search-bar">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索订单号…"
          class="search-input"
          @keyup.enter="onSearch"
        />
        <button class="btn btn-primary" @click="onSearch">
          搜索
        </button>
      </div>

      <div v-if="orders.length || statusFilter" class="filter-bar">
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

      <div v-if="!orders.length" class="empty">
        <div class="empty-icon">
          <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
          </svg>
        </div>
        <p class="empty-title">暂无订单</p>
        <p class="empty-sub">提交任务后，可在这里查看进度</p>
        <router-link to="/" class="btn btn-primary">
          去下单
        </router-link>
      </div>

      <div v-else class="order-list">
        <div
          v-for="(o, i) in filteredOrders"
          :key="o.order_id"
          class="order-card"
          :class="{
            completed: o.status === 'completed',
            failed: o.status === 'failed',
            cancelled: o.status === 'cancelled',
          }"
          :style="{ animationDelay: Math.min(i, 8) * 45 + 'ms' }"
          @click="showDetail(o)"
        >
          <div class="oc-top">
            <div class="oc-left">
              <span class="oc-id">{{ o.order_id }}</span>
              <span class="oc-status" :class="o.status">{{ statusLabel(o.status) }}</span>
              <span v-if="changedIds.has(o.order_id)" class="oc-changed">已更新</span>
            </div>
            <div v-if="o.status === 'pending'" class="oc-actions">
              <a
                v-if="!o.paid"
                class="oc-link pay-link"
                @click.stop="repay([o.order_id])"
              >去支付</a>
              <a
                class="oc-link cancel-link"
                @click.stop="cancel(o.order_id)"
              >取消</a>
            </div>
          </div>
          <div class="oc-info">
            <div class="oci">
              <span class="oci-l">平台</span>
              <span class="oci-v">{{ getPlatformName(o.website_id) }}</span>
            </div>
            <div class="oci">
              <span class="oci-l">类型</span>
              <span class="oci-v">{{ taskTypeNames[o.task_type] || o.task_type }}</span>
            </div>
            <div class="oci">
              <span class="oci-l">金额</span>
              <span class="oci-v price">¥{{ o.price.toFixed(2) }}</span>
            </div>
            <div class="oci">
              <span class="oci-l">创建</span>
              <span class="oci-v">{{ fmtTime(o.created_at) }}</span>
            </div>
            <div class="oci">
              <span class="oci-l">更新</span>
              <span class="oci-v">{{ fmtTime(o.updated_at || '') }}</span>
            </div>
          </div>
          <div v-if="activeStatuses.includes(o.status) && pct(o) > 0" class="oc-progress">
            <div class="ocp-bar">
              <div class="ocp-fill" :style="{ width: pct(o) + '%' }"></div>
            </div>
            <span class="ocp-pct">{{ pct(o) }}%</span>
          </div>
        </div>
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
        <span class="pg-info">共 {{ totalOrders }} 条</span>
      </div>
    </div>

    <footer class="page-footer">
      <span>Fuk 文理网课</span>
    </footer>

    <div v-if="detailOrder" class="modal-overlay" @click.self="closeDetail">
      <div class="detail-modal">
        <div class="dm-header">
          <h2>订单详情</h2>
          <button class="dm-close" @click="closeDetail">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="dm-body">
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
          <div class="dm-row">
            <span class="dm-label">课程数量</span>
            <span class="dm-value">{{ detailOrder.course_ids?.length || 0 }} 门</span>
          </div>
          <div class="dm-row">
            <span class="dm-label">视频数量</span>
            <span class="dm-value">{{ detailOrder.video_count }} 个</span>
          </div>
          <div class="dm-row">
            <span class="dm-label">订单金额</span>
            <span class="dm-value money">{{ fmtMoney(detailOrder.price) }}</span>
          </div>
          <div class="dm-row">
            <span class="dm-label">支付状态</span>
            <span class="dm-value">
              <span :class="['status-tag', detailOrder.paid ? 'ok' : 'warn']">{{ detailOrder.paid ? '已支付' : '未支付' }}</span>
            </span>
          </div>
          <div class="dm-row">
            <span class="dm-label">当前状态</span>
            <span class="dm-value">
              <span :class="['status-tag', statusClass[detailOrder.status]]">{{ statusLabel(detailOrder.status) }}</span>
            </span>
          </div>
          <div class="dm-row">
            <span class="dm-label">创建时间</span>
            <span class="dm-value">{{ fmtDate(detailOrder.created_at) }}</span>
          </div>
          <div v-if="detailOrder.accepted_at" class="dm-row">
            <span class="dm-label">接单时间</span>
            <span class="dm-value">{{ fmtDate(detailOrder.accepted_at) }}</span>
          </div>
          <div v-if="detailOrder.started_at" class="dm-row">
            <span class="dm-label">开始时间</span>
            <span class="dm-value">{{ fmtDate(detailOrder.started_at) }}</span>
          </div>
          <div v-if="detailOrder.updated_at" class="dm-row">
            <span class="dm-label">更新时间</span>
            <span class="dm-value">{{ fmtDate(detailOrder.updated_at) }}</span>
          </div>
          <div v-if="detailOrder.finished_at" class="dm-row">
            <span class="dm-label">完成时间</span>
            <span class="dm-value">{{ fmtDate(detailOrder.finished_at) }}</span>
          </div>
          <div v-if="detailOrder.status === 'failed' && detailOrder.admin_note" class="dm-row">
            <span class="dm-label">失败原因</span>
            <span class="dm-value" style="color: var(--c-danger);">{{ detailOrder.admin_note }}</span>
          </div>
        </div>
        <div v-if="auditLogs.length" class="dm-audit">
          <h3>操作日志</h3>
          <div v-for="log in auditLogs" :key="log.created_at" class="audit-item">
            <span class="audit-time">{{ fmtDate(log.created_at) }}</span>
            <span class="audit-event">{{ log.event }}</span>
            <span v-if="log.detail" class="audit-detail">{{ log.detail }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 支付弹窗 -->
    <div v-if="showPayModal" class="modal-overlay" @click.self="closePayModal">
      <div class="pay-modal">
        <template v-if="payTimedOut">
          <h3 class="pm-title">支付超时</h3>
          <p class="pm-desc">支付查询已超时，请到订单页查看支付状态。</p>
          <button class="btn btn-primary btn-block" @click="closePayModal">
            关闭
          </button>
        </template>
        <template v-else>
          <h3 class="pm-title">扫码支付</h3>
          <p class="pm-warn">请支付相同金额，否则无法自动到账</p>
          <p class="pm-amount">¥{{ payTotal.toFixed(2) }}</p>
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
            <div v-else class="pm-qr-placeholder">
              生成中…
            </div>
          </div>
          <p class="pm-hint">
            保存二维码后使用{{ payMethod === 'ypay_wxpay' ? '微信' : '支付宝' }}扫一扫支付
          </p>
          <button v-if="payQrCode" class="btn btn-primary btn-block pm-save" :class="{ wechat: payMethod === 'ypay_wxpay' }" @click="savePayQr">
            保存二维码
          </button>
          <button class="btn btn-ghost btn-block pm-cancel" @click="closePayModal">
            取消支付
          </button>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { min-height: 100vh; display: flex; flex-direction: column; }

.content-wrapper { flex: 1; max-width: 860px; width: 100%; margin: 0 auto; padding: 0 24px; }

.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 44px 0 26px;
  animation: fadeUp .32s cubic-bezier(.32, .72, .35, 1) both;
}
.order-stats {
  display: flex;
  align-items: center;
  gap: 28px;
  padding: 20px 24px;
  background: var(--c-surface);
  border: 1px solid var(--c-border-light);
  border-radius: 14px;
  margin-bottom: 20px;
  animation: fadeUp .32s cubic-bezier(.32, .72, .35, 1) .05s both;
}
.os-item b {
  display: block;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -.02em;
  font-variant-numeric: tabular-nums;
  color: var(--c-text);
  line-height: 1.3;
}
.os-item span { font-size: 12px; color: var(--c-text-muted); }
.os-divider { width: 1px; height: 32px; background: var(--c-border-light); }
.page-header h1 {
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -.02em;
  color: var(--c-text);
}
.ph-sub { display: flex; align-items: center; gap: 7px; margin-top: 8px; font-size: 12.5px; color: var(--c-text-secondary); }
.live-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--c-text); box-shadow: 0 0 0 3px rgba(21, 128, 61, .18); animation: live-pulse 2.4s ease infinite; }
@keyframes live-pulse {
  0%, 100% { box-shadow: 0 0 0 3px rgba(21, 128, 61, .18); }
  50% { box-shadow: 0 0 0 5px rgba(21, 128, 61, .08); }
}
.btn-clear-history { background: none; border: none; font-size: 12.5px; color: var(--c-text-muted); cursor: pointer; padding: 2px 8px; border-radius: 6px; margin-left: 6px; transition: color .2s, background .2s; }
.btn-clear-history:hover { color: var(--c-danger); background: rgba(220, 38, 38, .08); }

.btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 9px 20px; border: none; border-radius: 11px; font-weight: 600; font-size: 13.5px; cursor: pointer; white-space: nowrap; transition: transform .22s cubic-bezier(.32, .72, .35, 1), box-shadow .22s, background .22s, color .22s; }
.btn:active { transform: scale(.97); }
.btn-primary { background: var(--c-gradient); color: #fff; box-shadow: 0 2px 10px rgba(16, 16, 20, .16); }
.btn-primary:hover { filter: brightness(1.12); box-shadow: 0 4px 16px rgba(16, 16, 20, .2); transform: translateY(-1px); }
.btn-primary:active { transform: scale(.97); box-shadow: 0 1px 4px rgba(20, 20, 24, .2); }
.btn-ghost { background: transparent; color: var(--c-text-secondary); }
.btn-ghost:hover { color: var(--c-primary); background: rgba(20, 20, 24, .08); }
.btn-block { width: 100%; }

.search-bar { display: flex; gap: 10px; margin-bottom: 12px; animation: fadeUp .32s cubic-bezier(.32, .72, .35, 1) .05s both; }
.search-input { flex: 1; height: 42px; padding: 0 14px; border: 1px solid var(--c-border); border-radius: 10px; background: var(--c-surface); color: var(--c-text); font-size: 14px; outline: none; transition: border-color .22s, box-shadow .22s; }
.search-input:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px rgba(20, 20, 24, .12); }
.search-input::placeholder { color: var(--c-text-muted); }

.filter-bar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; animation: fadeUp .32s cubic-bezier(.32, .72, .35, 1) .1s both; }
.chip { padding: 6px 14px; border-radius: 999px; background: var(--c-surface); border: 1px solid var(--c-border); font-size: 12.5px; cursor: pointer; color: var(--c-text-secondary); font-weight: 500; transition: all .22s cubic-bezier(.32, .72, .35, 1); }
.chip:hover { border-color: var(--c-primary); color: var(--c-primary); transform: translateY(-1px); }
.chip:active { transform: scale(.97); }
.chip.active { background: var(--c-primary); color: #fff; border-color: var(--c-primary); box-shadow: none; }

.empty { text-align: center; padding: 80px 20px; animation: fadeUp .32s cubic-bezier(.32, .72, .35, 1) both; }
.empty-icon { display: flex; justify-content: center; color: var(--c-text-muted); margin-bottom: 14px; }
.empty-title { font-size: 16px; font-weight: 700; color: var(--c-text); margin-bottom: 4px; }
.empty-sub { font-size: 13px; color: var(--c-text-secondary); margin-bottom: 20px; }

.order-list { display: flex; flex-direction: column; }
.order-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border-light);
  border-radius: 16px;
  cursor: pointer;
  padding: 18px 22px;
  margin-bottom: 12px;
  box-shadow: 0 1px 2px rgba(20,20,24,.06);
  animation: fadeUp .32s cubic-bezier(.32, .72, .35, 1) both;
  transition: transform .25s cubic-bezier(.32, .72, .35, 1), box-shadow .25s, border-color .25s;
}
.order-card:hover { transform: translateY(-2px); box-shadow: 0 12px 32px rgba(20, 20, 24, .1); border-color: rgba(20, 20, 24, .35); }
.order-card.completed { border-color: rgba(20, 20, 24, .35); }
.order-card.failed { border-color: rgba(220, 38, 38, .35); }
.order-card.cancelled { opacity: .55; }

.oc-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
.oc-left { display: flex; align-items: center; gap: 8px; min-width: 0; flex-wrap: wrap; }
.oc-id { font-family: 'SF Mono', 'Cascadia Code', monospace; font-size: 11px; color: var(--c-text-secondary); background: var(--c-surface-3); padding: 3px 9px; border-radius: 6px; }
.oc-status { font-size: 11.5px; font-weight: 600; padding: 3px 10px; border-radius: 999px; }
.oc-status.pending { background: var(--c-surface-3); color: var(--c-text-secondary); }
.oc-status.accepted { background: rgba(20, 20, 24, .1); color: var(--c-primary); }
.oc-status.running { background: rgba(20, 20, 24, .1); color: var(--c-primary); }
.oc-status.paid { background: rgba(20, 20, 24, .1); color: var(--c-primary); }
.oc-status.retrying { background: var(--c-surface-3); color: var(--c-text-secondary); }
.oc-status.queued { background: var(--c-surface-3); color: var(--c-text-secondary); }
.oc-status.completed { background: var(--c-text); color: #fff; }
.oc-status.failed { background: rgba(220, 38, 38, .1); color: var(--c-danger); }
.oc-status.cancelled { background: var(--c-surface-3); color: var(--c-text-muted); }
.oc-status.waiting { background: var(--c-surface-3); color: var(--c-text-secondary); }
.oc-changed { font-size: 10.5px; font-weight: 600; color: var(--c-primary); background: rgba(20, 20, 24, .1); padding: 2px 8px; border-radius: 999px; }

.oc-actions { display: flex; gap: 12px; align-items: center; flex-shrink: 0; }
.oc-link { font-size: 12.5px; cursor: pointer; text-decoration: none; white-space: nowrap; transition: opacity .2s; }
.oc-link:hover { text-decoration: underline; }
.pay-link { color: var(--c-primary); font-weight: 600; }
.cancel-link { color: var(--c-text-muted); }

.oc-info { display: grid; grid-template-columns: repeat(auto-fit, minmax(84px, 1fr)); gap: 8px; }
.oci { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.oci-l { font-size: 10.5px; color: var(--c-text-muted); }
.oci-v { font-size: 12.5px; font-weight: 500; color: var(--c-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.oci-v.price { color: var(--c-text); font-weight: 700; }

.oc-progress { display: flex; align-items: center; gap: 10px; margin-top: 12px; }
.ocp-bar { flex: 1; height: 6px; background: var(--c-surface-3); border-radius: 999px; overflow: hidden; }
.ocp-fill { height: 100%; border-radius: 999px; background: var(--c-text); transition: width .35s cubic-bezier(.32, .72, .35, 1); }
.ocp-pct { font-size: 13px; font-weight: 700; color: var(--c-primary); min-width: 42px; text-align: right; }

.pagination { display: flex; justify-content: center; align-items: center; gap: 6px; padding: 22px 0; flex-wrap: wrap; }
.pagination button { padding: 7px 13px; border: 1px solid var(--c-border); border-radius: 9px; background: var(--c-surface); cursor: pointer; font-size: 13px; color: var(--c-text); transition: all .2s cubic-bezier(.32, .72, .35, 1); }
.pagination button:hover:not(:disabled):not(.active) { border-color: var(--c-primary); color: var(--c-primary); }
.pagination button:active:not(:disabled) { transform: scale(.96); }
.pagination button.active { background: var(--c-primary); color: #fff; border-color: var(--c-primary); }
.pagination button:disabled { opacity: .4; cursor: default; }
.pg-info { font-size: 12px; color: var(--c-text-muted); margin-left: 12px; }

.page-footer { text-align: center; padding: 24px; font-size: 12px; color: var(--c-text-muted); border-top: 1px solid var(--c-border-light); margin-top: 20px; }

.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(22,22,26,.42);
  display: flex; align-items: center; justify-content: center; z-index: 500;
  padding: 20px;
  animation: overlay-in .2s ease;
}
@keyframes overlay-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes fadeUp { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }

.detail-modal {
  background: var(--c-surface); border: 1px solid var(--c-border-light); border-radius: 18px;
  padding: 26px 28px; max-width: 500px; width: 100%;
  box-shadow: 0 24px 64px rgba(20, 20, 24, .12), 0 8px 24px rgba(20, 20, 24, .09); max-height: 85vh; overflow-y: auto;
  animation: modal-in .28s cubic-bezier(.32, .72, .35, 1) both;
}
@keyframes modal-in { from { opacity: 0; transform: translateY(14px) scale(.97); } to { opacity: 1; transform: translateY(0) scale(1); } }
.dm-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.dm-header h2 { font-size: 18px; font-weight: 700; letter-spacing: -.015em; color: var(--c-text); }
.dm-close { background: var(--c-surface-3); border: none; cursor: pointer; color: var(--c-text-secondary); width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; transition: background .2s, color .2s, transform .2s; }
.dm-close:hover { background: var(--c-border-light); color: var(--c-text); }
.dm-close:active { transform: scale(.92); }
.dm-body { display: flex; flex-direction: column; }
.dm-row { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 9px 0; border-bottom: 1px solid var(--c-surface-3); }
.dm-row:last-child { border-bottom: none; }
.dm-label { font-size: 13px; color: var(--c-text-muted); flex-shrink: 0; }
.dm-value { font-size: 13px; font-weight: 500; color: var(--c-text); text-align: right; word-break: break-all; }
.dm-value.money { color: var(--c-primary); font-weight: 700; }
.dm-value.mono { font-family: 'SF Mono', 'Cascadia Code', monospace; font-size: 12px; }
.status-tag { font-size: 11.5px; font-weight: 600; padding: 3px 10px; border-radius: 999px; }
.status-tag.ok { background: var(--c-text); color: #fff; }
.status-tag.warn { background: var(--c-surface-3); color: var(--c-text-secondary); }
.status-tag.primary { background: rgba(20, 20, 24, .1); color: var(--c-primary); }
.status-tag.bad { background: rgba(220, 38, 38, .1); color: var(--c-danger); }
.status-tag.muted { background: var(--c-surface-3); color: var(--c-text-muted); }

.dm-audit { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--c-border-light); }
.dm-audit h3 { font-size: 14px; font-weight: 700; color: var(--c-text); margin-bottom: 10px; }
.audit-item { display: flex; gap: 8px; padding: 6px 0; font-size: 12px; border-bottom: 1px solid var(--c-surface-3); }
.audit-item:last-child { border-bottom: none; }
.audit-time { color: var(--c-text-muted); min-width: 140px; flex-shrink: 0; }
.audit-event { color: var(--c-primary); font-weight: 500; }
.audit-detail { color: var(--c-text-secondary); flex: 1; }

.pay-modal {
  width: 400px; max-width: 92vw; background: var(--c-surface);
  border: 1px solid var(--c-border-light); border-radius: 18px; padding: 30px 26px; text-align: center;
  box-shadow: 0 24px 64px rgba(20, 20, 24, .12), 0 8px 24px rgba(20, 20, 24, .09);
  animation: modal-in .28s cubic-bezier(.32, .72, .35, 1) both;
}
.pm-title { font-size: 18px; font-weight: 700; letter-spacing: -.015em; color: var(--c-text); margin-bottom: 6px; }
.pm-desc { font-size: 14px; color: var(--c-text-secondary); margin: 12px 0 22px; }
.pm-warn { font-size: 12px; color: var(--c-warning); font-weight: 600; margin: 4px 0; }
.pm-amount {
  font-size: 34px;
  font-weight: 800;
  letter-spacing: -.02em;
  font-variant-numeric: tabular-nums;
  color: var(--c-text);
  margin: 10px 0 16px;
}
.pay-method-tabs { display: flex; gap: 0; margin-bottom: 18px; background: var(--c-surface-3); border-radius: 11px; padding: 3px; }
.pm-tab { flex: 1; padding: 8px 0; border: none; background: transparent; border-radius: 8px; font-size: 13px; font-weight: 600; color: var(--c-text-secondary); cursor: pointer; transition: all .22s cubic-bezier(.32, .72, .35, 1); }
.pm-tab.active { background: var(--c-surface); color: var(--c-text); box-shadow: 0 1px 3px rgba(16, 16, 20, .12); }
.pm-tab:hover:not(.active) { color: var(--c-text); }
.pm-qr { display: flex; justify-content: center; margin-bottom: 14px; }
.pm-qr-img { width: 200px; height: 200px; border-radius: 14px; border: 1px solid rgba(255, 255, 255, .1); padding: 8px; background: #fff; box-shadow: 0 0 0 6px rgba(16, 16, 20, .04), 0 12px 32px rgba(20, 20, 24, .09); }
.pm-qr-placeholder { width: 200px; height: 200px; display: flex; align-items: center; justify-content: center; background: var(--c-surface-3); border-radius: 12px; color: var(--c-text-muted); font-size: 13px; }
.pm-hint { font-size: 12px; color: var(--c-text-secondary); margin-bottom: 14px; }
.pm-save.wechat { background: #07c160; box-shadow: 0 2px 10px rgba(7, 193, 96, .22); }
.pm-save.wechat:hover { background: #06ad56; box-shadow: 0 5px 16px rgba(7, 193, 96, .28); }
.pm-cancel { margin-top: 10px; }

@media (max-width: 768px) {
  .content-wrapper { padding: 0 14px; }
  .page-header { padding: 26px 0 16px; }
  .page-header h1 { font-size: 22px; }
  .order-stats { gap: 20px; padding: 16px 18px; }

  .search-bar { flex-wrap: wrap; }
  .search-input { font-size: 13px; height: 40px; }

  .filter-bar { gap: 6px; }
  .chip { padding: 5px 11px; font-size: 11.5px; }

  .order-card { padding: 14px 16px; margin-bottom: 10px; border-radius: 14px; }
  .oc-info { grid-template-columns: repeat(3, 1fr); gap: 6px; }

  .pagination { gap: 4px; padding: 16px 0; }
  .pagination button { padding: 6px 10px; font-size: 12px; }
  .pg-info { width: 100%; text-align: center; margin: 6px 0 0; }

  .detail-modal { padding: 20px; max-height: 90vh; }
  .audit-item { flex-wrap: wrap; gap: 4px; }
  .audit-time { min-width: auto; }
  .audit-detail { width: 100%; }
}
</style>

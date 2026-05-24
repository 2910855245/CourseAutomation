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
let interval: number
const statusFilter = ref('')
const searchQuery = ref('')
const currentPage = ref(1)
const totalPages = ref(1)
const totalOrders = ref(0)
const pageSize = 50
const detailOrder = ref<OrderItem | null>(null)
const auditLogs = ref<{ event: string; detail: string; created_at: string }[]>([])
const taskTypeNames: Record<string, string> = { video: '视频', exam: '考试', full: '全包' }
const countdown = ref(15)
const isGuest = ref(false)
const guestOrderIds = ref<string[]>([])

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
    // 仅游客模式：用sessionStorage的ID逐个查询
    if (isGuest.value && guestOrderIds.value.length > 0) {
      const items: OrderItem[] = []
      for (const oid of guestOrderIds.value) {
        try {
          const r = await api.orders.get(oid)
          if (r?.data) items.push(r.data as OrderItem)
        } catch { /* skip */ }
      }
      if (items.length > 0) {
        orders.value = items
        totalOrders.value = items.length
        return
      }
    }
    // 游客无ID：显示空
    if (isGuest.value && guestOrderIds.value.length === 0) {
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
      isGuest.value = true
      load()
      return
    }
    store.toast(e?.message || '加载订单失败', 'error')
  }
}

function startAutoRefresh() {
  interval = window.setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) { load(); countdown.value = 15 }
  }, 1000)
}

onMounted(async () => {
  try {
    loadPlatformNames()
    const hasToken = !!localStorage.getItem('user_token')
    const routeId = route.params.id as string || ''

    if (hasToken) {
      isGuest.value = false
    } else if (routeId) {
      guestOrderIds.value = [routeId]
      isGuest.value = true
    } else {
      const urlIds = (route.query.ids as string) || ''
      const storedIds = sessionStorage.getItem('last_order_ids') || localStorage.getItem('last_order_ids') || ''
      const idsStr = urlIds || storedIds
      if (idsStr) {
        guestOrderIds.value = idsStr.split(',').filter(Boolean)
      }
      isGuest.value = true
    }

    await load()

    // 如果URL带订单ID，自动打开该订单详情
    if (routeId && orders.value.length > 0) {
      const target = orders.value.find(o => o.order_id === routeId)
      if (target) showDetail(target)
    }
  } catch (e) {
    console.error('Orders init error:', e)
  }

  startAutoRefresh()
})
onUnmounted(() => { if (interval) clearInterval(interval) })

function refresh() { load(); countdown.value = 15 }

async function cancel(id: string) {
  const ok = await showConfirm({ title: '取消订单', message: '确认取消该订单吗？取消后不可恢复。', type: 'warning' })
  if (!ok) return
  try {
    await api.orders.cancel(id)
    store.toast('订单已取消', 'success')
    load()
  } catch (e: any) { store.toast(e.message, 'error') }
}

async function clearHistory() {
  const ok = await showConfirm({ title: '清空历史', message: '确认清空所有已完成/失败/已取消的订单？此操作不可撤销。', type: 'danger' })
  if (!ok) return
  try {
    await api.orders.clearHistory()
    store.toast('历史订单已清空', 'success')
    load()
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

const hasActive = () => orders.value.some(o => activeStatuses.includes(o.status))
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
        <h1>我的订单</h1>
      </div>

      <div class="toolbar">
        <span v-if="hasActive()" class="timer">自动刷新：{{ countdown }}秒</span>
        <span v-else-if="orders.length" class="timer done">全部完成 ✓</span>
        <div class="toolbar-actions">
          <button class="btn btn-ghost" @click="refresh">
刷新
</button>
          <button v-if="orders.length" class="btn btn-ghost btn-clear-history" @click="clearHistory">
清空
</button>
        </div>
      </div>

      <div v-if="orders.length || searchQuery" class="search-bar">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索用户名/订单号…"
          class="search-input"
          @keyup.enter="onSearch"
        />
        <button class="btn btn-primary-sm" @click="onSearch">
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
      </div>

      <div v-if="!orders.length" class="empty">
        <div class="empty-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
          </svg>
        </div>
        <p>暂无订单</p>
        <router-link to="/" class="btn btn-primary">
去下单
</router-link>
      </div>

      <div v-else class="order-list">
        <div
          v-for="o in filteredOrders"
          :key="o.order_id"
          class="order-card"
          :class="{
            completed: o.status === 'completed',
            failed: o.status === 'failed',
            cancelled: o.status === 'cancelled',
          }"
          @click="showDetail(o)"
        >
          <div class="oc-top">
            <div class="oc-left">
              <span class="oc-id">{{ o.order_id }}</span>
              <span class="oc-status" :class="o.status">{{ statusLabel(o.status) }}</span>
              <span v-if="changedIds.has(o.order_id)" class="oc-changed">已更新</span>
            </div>
            <div v-if="o.status === 'pending'" class="oc-actions">
              <button
                v-if="!o.paid"
                class="btn btn-primary-sm"
                @click.stop="repay([o.order_id])"
              >
去支付
</button>
              <button
                class="btn btn-danger-sm"
                @click.stop="cancel(o.order_id)"
              >
取消
</button>
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
          <div v-if="activeStatuses.includes(o.status)" class="oc-progress">
            <div class="ocp-bar">
              <div class="ocp-fill" :style="{ width: pct(o) + '%' }"></div>
            </div>
            <span class="ocp-pct">{{ pct(o) }}%</span>
          </div>
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

    <footer class="page-footer">
      <span>FUCK 文理网课 · 让网课不再成为负担</span>
    </footer>

    <div v-if="detailOrder" class="modal-overlay show" @click.self="closeDetail">
      <div class="detail-modal fade-in-enter-active">
        <div class="dm-header">
          <h2>订单详情</h2>
          <button class="dm-close" @click="closeDetail">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
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
    <div v-if="showPayModal" class="modal-overlay show" @click.self="closePayModal">
      <div class="pay-modal">
        <div v-if="payTimedOut" style="text-align:center">
          <h3>支付超时</h3>
          <p style="font-size:14px;color:var(--c-text-secondary);margin:16px 0 24px">
支付查询已超时，请到订单页查看支付状态。
</p>
          <button class="btn btn-primary btn-block" @click="closePayModal">
关闭
</button>
        </div>
        <div v-else style="text-align:center">
          <h3>扫码支付</h3>
          <p style="font-size:13px;color:var(--c-warning);margin:8px 0">
请务必支付相同金额，多一分少一分都无法检测到
</p>
          <p style="font-size:24px;font-weight:800;color:var(--c-primary);margin:12px 0">
¥{{ payTotal.toFixed(2) }}
</p>
          <div class="pay-method-tabs" style="display:flex;gap:8px;justify-content:center;margin-bottom:16px">
            <button :class="['pm-tab', { active: payMethod === 'ypay_wxpay' }]" style="padding:6px 16px;border-radius:20px;font-size:13px;font-weight:600;border:1.5px solid var(--c-border);background:transparent;cursor:pointer" @click="switchPayMethod('ypay_wxpay')">
微信
</button>
            <button :class="['pm-tab', { active: payMethod === 'ypay_alipay' }]" style="padding:6px 16px;border-radius:20px;font-size:13px;font-weight:600;border:1.5px solid var(--c-border);background:transparent;cursor:pointer" @click="switchPayMethod('ypay_alipay')">
支付宝
</button>
          </div>
          <div style="margin:16px 0">
            <img v-if="payQrCode" :src="payQrCode" alt="支付二维码" style="width:200px;height:200px;border-radius:8px" />
            <div v-else style="width:200px;height:200px;display:flex;align-items:center;justify-content:center;background:var(--c-bg);border-radius:8px;margin:0 auto;color:var(--c-text-muted)">
生成中...
</div>
          </div>
          <p style="font-size:12px;color:var(--c-text-secondary);margin-bottom:12px">
保存二维码后使用{{ payMethod === 'ypay_wxpay' ? '微信' : '支付宝' }}扫一扫支付
</p>
          <button v-if="payQrCode" class="btn btn-primary btn-block" style="margin-top:8px" :style="payMethod === 'ypay_wxpay' ? 'background:#07c160' : ''" @click="savePayQr">
保存二维码
</button>
          <button class="btn btn-ghost btn-block" style="margin-top:10px" @click="closePayModal">
取消支付
</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { min-height: 100vh; display: flex; flex-direction: column; }

.content-wrapper { flex: 1; max-width: 840px; width: 100%; margin: 0 auto; padding: 0 24px; }
.page-header { text-align: center; padding: 36px 0 8px; }
.page-header h1 { font-size: 24px; font-weight: 700; margin-bottom: 4px; }
.page-header p { font-size: 13px; color: var(--c-text-secondary); }

.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 0; margin-bottom: 12px;
}
.timer { font-size: 12.5px; color: var(--c-text-muted); }
.timer.done { color: var(--c-success); font-weight: 600; }
.toolbar-actions { display: flex; gap: 8px; align-items: center; }
.btn-clear-history { color: #94a3b8; font-size: 12px; }
.btn-clear-history:hover { color: var(--c-danger); background: var(--c-danger-bg); }

.btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 9px 20px; border: none; border-radius: var(--radius-sm); font-weight: 600; font-size: 13.5px; cursor: pointer; transition: all .15s; white-space: nowrap; }
.btn-primary { background: var(--c-primary); color: #fff; box-shadow: 0 2px 8px rgba(79,110,247,.25); }
.btn-primary:hover { background: var(--c-primary-hover); transform: translateY(-1px); }
.btn-ghost { background: transparent; color: var(--c-text-secondary); padding: 6px 12px; }
.btn-ghost:hover { color: var(--c-primary); background: var(--c-primary-bg); }
.btn-danger-sm { background: var(--c-danger-bg); color: var(--c-danger); border: 1px solid rgba(239,68,68,.2); padding: 5px 12px; font-size: 12px; }
.btn-danger-sm:hover { background: var(--c-danger); color: #fff; }
.btn-primary-sm { background: var(--c-primary); color: #fff; padding: 7px 16px; font-size: 13px; font-weight: 600; border-radius: var(--radius-sm); }
.btn-primary-sm:hover { background: var(--c-primary-hover); }

.empty { text-align: center; padding: 60px 20px; }
.empty-icon { color: var(--c-text-muted); margin-bottom: 12px; }
.empty p { color: var(--c-text-secondary); margin-bottom: 16px; font-size: 14px; }

.order-list { display: flex; flex-direction: column; gap: 0; }
.order-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-lg);
  cursor: pointer; padding: 18px 22px; margin-bottom: 12px;
  box-shadow: var(--shadow-xs); transition: border-color .3s;
}
.order-card.completed { border-color: var(--c-success); background: var(--c-success-bg); }
.order-card.failed { border-color: var(--c-danger); background: var(--c-danger-bg); }
.order-card.cancelled { opacity: .6; }

.oc-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.oc-left { display: flex; align-items: center; gap: 10px; }
.oc-id { font-family: 'SF Mono', 'Cascadia Code', monospace; font-size: 11px; color: var(--c-text-muted); background: var(--c-bg); padding: 2px 8px; border-radius: 3px; }
.oc-status { font-size: 11.5px; font-weight: 600; padding: 2px 8px; border-radius: 12px; }
.oc-status.pending { background: #fef3c7; color: #d97706; }
.oc-status.accepted { background: var(--c-info-bg); color: var(--c-info); }
.oc-status.running { background: var(--c-primary-bg); color: var(--c-primary); }
.oc-status.paid { background: var(--c-info-bg); color: var(--c-info); }
.oc-status.retrying { background: #fef3c7; color: #d97706; }
.oc-status.queued { background: #fef3c7; color: #d97706; }
.oc-status.completed { background: var(--c-success-bg); color: var(--c-success); }
.oc-status.failed { background: var(--c-danger-bg); color: var(--c-danger); }
.oc-status.cancelled { background: #f3f4f6; color: var(--c-text-muted); }
.oc-status.waiting { background: #fef3c7; color: #d97706; }

.oc-changed {
  font-size: 10.5px; font-weight: 600; color: var(--c-info);
  background: var(--c-info-bg); padding: 1px 7px; border-radius: 8px;
}

.oc-actions { display: flex; gap: 6px; }
.pay-modal {
  width: 400px; max-width: 92vw; background: var(--c-surface);
  border-radius: var(--radius-lg); padding: 28px 24px;
  box-shadow: 0 20px 60px rgba(0,0,0,.2);
}
.pm-tab {
  padding: 6px 18px; border-radius: 20px; font-size: 13px; font-weight: 600;
  border: 1.5px solid var(--c-border); background: transparent; cursor: pointer;
  transition: all .15s;
}
.pm-tab.active { background: var(--c-primary); color: #fff; border-color: var(--c-primary); }
.btn-block { width: 100%; }

.oc-info { display: grid; grid-template-columns: repeat(auto-fit, minmax(80px, 1fr)); gap: 8px; margin-bottom: 10px; }
.oci { display: flex; flex-direction: column; }
.oci-l { font-size: 10.5px; color: var(--c-text-muted); }
.oci-v { font-size: 12.5px; font-weight: 500; color: var(--c-text); }
.oci-v.price { color: var(--c-danger); font-weight: 700; }

.filter-bar { display: flex; gap: 6px; margin-bottom: 14px; flex-wrap: wrap; }
.chip { padding: 5px 12px; border-radius: 16px; background: var(--c-bg); border: 1px solid var(--c-border); font-size: 12px; cursor: pointer; color: var(--c-text-secondary); font-weight: 500; transition: all .15s; }
.chip:hover { border-color: var(--c-primary); color: var(--c-primary); }
.chip.active { background: var(--c-primary); color: #fff; border-color: var(--c-primary); }

.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(15,23,42,.45); backdrop-filter: blur(4px);
  display: none; align-items: center; justify-content: center; z-index: 500;
  padding: 20px;
}
.modal-overlay.show { display: flex; }

.fade-in-enter-active {
  animation: fadeInUp 0.3s ease-out;
}
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.detail-modal {
  background: var(--c-surface); border-radius: var(--radius-xl);
  padding: 28px 32px; max-width: 500px; width: 90%;
  box-shadow: 0 20px 60px rgba(0,0,0,.15); max-height: 85vh; overflow-y: auto;
}
.dm-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.dm-header h2 { font-size: 18px; font-weight: 700; }
.dm-close { background: none; border: none; cursor: pointer; color: var(--c-text-muted); padding: 4px; border-radius: 6px; }
.dm-close:hover { background: var(--c-bg); color: var(--c-text); }
.dm-body { display: flex; flex-direction: column; gap: 12px; }
.dm-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #f3f4f6; }
.dm-row:last-child { border-bottom: none; }
.dm-label { font-size: 13px; color: var(--c-text-muted); }
.dm-value { font-size: 13px; font-weight: 500; color: var(--c-text); }
.dm-value.money { color: var(--c-primary); font-weight: 700; }
.dm-value.mono { font-family: 'SF Mono', monospace; font-size: 12px; }

.oc-progress { display: flex; align-items: center; gap: 10px; }
.ocp-bar { flex: 1; height: 7px; background: #f1f5f9; border-radius: 4px; overflow: hidden; }
.ocp-fill { height: 100%; border-radius: 4px; background: var(--c-primary); transition: width .4s ease; }
.ocp-pct { font-size: 14px; font-weight: 700; color: var(--c-primary); min-width: 44px; text-align: right; }

.page-footer { text-align: center; padding: 24px; font-size: 12px; color: var(--c-text-muted); border-top: 1px solid var(--c-border); margin-top: 20px; }

.search-bar { display: flex; gap: 8px; margin-bottom: 12px; }
.search-input { flex: 1; padding: 8px 12px; border: 1px solid var(--c-border); border-radius: 8px; font-size: 14px; outline: none; }
.search-input:focus { border-color: var(--c-primary); }

.pagination { display: flex; justify-content: center; align-items: center; gap: 4px; padding: 20px 0; }
.pagination button { padding: 6px 12px; border: 1px solid var(--c-border); border-radius: 6px; background: #fff; cursor: pointer; font-size: 13px; }
.pagination button.active { background: var(--c-primary); color: #fff; border-color: var(--c-primary); }
.pagination button:disabled { opacity: .4; cursor: default; }
.pg-info { font-size: 12px; color: var(--c-text-muted); margin-left: 12px; }

.dm-audit { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--c-border); }
.dm-audit h3 { font-size: 14px; font-weight: 600; margin-bottom: 10px; }
.audit-item { display: flex; gap: 8px; padding: 6px 0; font-size: 12px; border-bottom: 1px solid #f3f4f6; }
.audit-time { color: var(--c-text-muted); min-width: 140px; }
.audit-event { color: var(--c-primary); font-weight: 500; }
.audit-detail { color: var(--c-text-secondary); flex: 1; }

@media (max-width: 768px) {
  .content-wrapper { padding: 0 12px; }
  .page-header { padding: 24px 0 8px; }
  .page-header h1 { font-size: 20px; }

  .toolbar {
    gap: 8px;
    padding: 10px 0;
  }
  .timer { font-size: 11px; }
  .toolbar-actions { gap: 4px; }
  .toolbar-actions .btn { font-size: 11px; padding: 5px 8px; }
  .btn-clear-history { font-size: 11px; }

  .search-bar { flex-wrap: wrap; }
  .search-input { font-size: 13px; padding: 8px 10px; }

  .filter-bar { gap: 4px; }
  .chip { padding: 4px 10px; font-size: 11px; }

  .order-card { padding: 14px 16px; margin-bottom: 10px; }
  .oc-top { flex-wrap: wrap; gap: 6px; }
  .oc-left { gap: 6px; flex-wrap: wrap; }
  .oc-id { font-size: 10px; }
  .oc-status { font-size: 10.5px; padding: 2px 6px; }

  .oc-info { grid-template-columns: repeat(3, 1fr); gap: 6px; }
  .oci-l { font-size: 10px; }
  .oci-v { font-size: 11.5px; }

  .oc-progress { gap: 8px; }
  .ocp-bar { height: 6px; }
  .ocp-pct { font-size: 12px; min-width: 36px; }

  .pagination { gap: 2px; padding: 16px 0; flex-wrap: wrap; }
  .pagination button { padding: 5px 10px; font-size: 12px; }
  .pg-info { font-size: 11px; margin-left: 8px; width: 100%; text-align: center; margin-top: 4px; }

  .detail-modal { width: 94vw; padding: 20px; max-height: 90vh; }
  .dm-header h2 { font-size: 16px; }
  .dm-row { padding: 6px 0; }
  .dm-label { font-size: 12px; }
  .dm-value { font-size: 12px; }
  .dm-value.mono { font-size: 11px; }

  .audit-item { flex-wrap: wrap; gap: 4px; }
  .audit-time { min-width: auto; font-size: 11px; }
  .audit-event { font-size: 11px; }
  .audit-detail { font-size: 11px; width: 100%; }

  .oc-actions { display: flex; gap: 6px; }
  .pay-modal { width: 92vw; max-width: 380px; background: var(--c-surface); border-radius: var(--radius-lg); padding: 24px 20px; box-shadow: var(--shadow-lg); }
  .pm-tab.active { background: var(--c-primary); color: #fff; border-color: var(--c-primary); }
  .btn-block { width: 100%; }
}
</style>

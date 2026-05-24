<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { api, type PlatformResult, type CourseItem } from '@/api'
import { isMobile } from '@/utils/mobile'
import PaymentSuccess from '@/components/PaymentSuccess.vue'

const store = useAppStore()

const route = useRoute()
const router = useRouter()
const slug = ref((route.params.slug as string) || '')
const loading = ref(true)
const notFound = ref(false)

const agentData = ref<any>(null)

onMounted(async () => {
  if (!slug.value) { notFound.value = true; loading.value = false; return }
  try {
    const r = await api.agents.subsite(slug.value)
    if (!r.data) { notFound.value = true; loading.value = false; return }
    agentData.value = r.data
  } catch { notFound.value = true }
  finally {
    loading.value = false
    if (agentData.value) loadPricing()
  }
})

const pricing = ref({ videoUnitPrice: 0.10, examUnitPrice: 0.15 })
async function loadPricing() { try { const r = await api.pricing.get(); if (r?.data) pricing.value = { videoUnitPrice: r.data.videoUnitPrice ?? 0.10, examUnitPrice: r.data.examUnitPrice ?? 0.15 } } catch {} }

const username = ref('')
const password = ref('')
const scanning = ref(false)
const scanDone = ref(false)
const scanData = ref<PlatformResult[]>([])
const checkedCourseIds = ref(new Set<string>())

const visiblePlatforms = computed(() => scanData.value.filter(p => p.courses.length > 0 && p.courses.some(c => !isCourseDone(c))))

function isCourseDone(c: CourseItem): boolean { return c.video_pending === 0 && (c.exam_total === 0 || c.exam_done >= c.exam_total) }
function togglePlatform(wid: number, checked: boolean) {
  const p = scanData.value.find(p => p.website_id === wid)
  if (!p) return
  for (const c of p.courses) { if (checked && !isCourseDone(c)) checkedCourseIds.value.add(c.course_id); else checkedCourseIds.value.delete(c.course_id) }
}
function toggleCourse(cid: string) { if (checkedCourseIds.value.has(cid)) checkedCourseIds.value.delete(cid); else checkedCourseIds.value.add(cid) }
function isPlatformAllChecked(p: PlatformResult): boolean { const pd = p.courses.filter(c => !isCourseDone(c)); return pd.length > 0 && pd.every(c => checkedCourseIds.value.has(c.course_id)) }

const summary = computed(() => {
  let courses = 0, videos = 0, exams = 0
  for (const p of scanData.value) for (const c of p.courses) if (checkedCourseIds.value.has(c.course_id)) { courses++; videos += c.video_pending; exams += Math.max(0, c.exam_total - c.exam_done) }
  const vp = videos > 0 ? pricing.value.videoUnitPrice : 0; const ep = exams > 0 ? pricing.value.examUnitPrice : 0
  return { courses, videos, exams, total: parseFloat((videos * vp + exams * ep).toFixed(2)) }
})

const studentName = computed(() => { for (const p of scanData.value) if (p.student_name) return p.student_name; return '' })

async function startScan() {
  if (!username.value.trim() || !password.value.trim()) return
  scanning.value = true; scanDone.value = false
  try {
    const res = await api.courses.scan({ username: username.value.trim(), password: password.value.trim(), include_records: true })
    scanData.value = res.data.platforms; scanDone.value = true
  } catch {}
  finally { scanning.value = false }
}

function pct(c: CourseItem) { return c.video_total > 0 ? Math.round(c.video_completed / c.video_total * 100) : 0 }

const paying = ref(false)
const showPayModal = ref(false)
const showPaySuccess = ref(false)
const payTotal = ref(0)
const payQrCode = ref('')
const payGatewayUrl = ref('')
const payPollTimer = ref<any>(null)
const selectedPayMethod = ref('ypay_wxpay')
const payQrCodes = ref<Record<string, string>>({})
const payGatewayUrls = ref<Record<string, string>>({})
const payH5Urls = ref<Record<string, string>>({})
const mobileRedirecting = ref(false)
const payOutTradeNos = ref<string[]>([])
const payOutTradeNosByMethod = ref<Record<string, string[]>>({})
const payCheckTokens = ref<string[]>([])
const payCheckTokensByMethod = ref<Record<string, string[]>>({})
const payCurrentOrderIds = ref<string[]>([])
const payOrderIdsByMethod = ref<Record<string, string[]>>({})

async function submitAndPay() {
  if (summary.value.courses === 0) return
  paying.value = true
  try {
    const grouped: Record<number, { ids: string[]; v: number; e: number }> = {}
    for (const p of scanData.value) for (const c of p.courses) if (checkedCourseIds.value.has(c.course_id)) {
      if (!grouped[p.website_id]) grouped[p.website_id] = { ids: [], v: 0, e: 0 }
      grouped[p.website_id].ids.push(c.course_id); grouped[p.website_id].v += c.video_pending; grouped[p.website_id].e += Math.max(0, c.exam_total - c.exam_done)
    }
    const orders = Object.entries(grouped).map(([w, g]) => {
      const vp = g.v > 0 ? pricing.value.videoUnitPrice : 0; const ep = g.e > 0 ? pricing.value.examUnitPrice : 0
      const t = g.v > 0 && g.e > 0 ? 'full' : g.v > 0 ? 'video' : 'exam'
      return { website_id: parseInt(w), task_type: t, course_ids: g.ids, video_count: g.v, exam_count: g.e, price: parseFloat((g.v * vp + g.e * ep).toFixed(2)) }
    })
    payTotal.value = orders.reduce((s, o) => s + o.price, 0)
    const batchRes = await api.orders.batch({ username: username.value.trim(), password: password.value.trim(), orders, inviter_code: agentData.value?.referral_code || '' })
    const allOrders = (batchRes?.data?.orders) || []
    if (!allOrders.length) { paying.value = false; return }

    const methods = ['ypay_wxpay', 'ypay_alipay']
    const qrCodes: Record<string, string> = {}; const gwUrls: Record<string, string> = {}; const h5Urls: Record<string, string> = {}
    const otns: Record<string, string[]> = {}; const oids: Record<string, string[]> = {}
    const ctkns: Record<string, string[]> = {}

    for (const method of methods) {
      otns[method] = []; oids[method] = []; ctkns[method] = []
      for (const o of allOrders) {
        try {
          const r = await api.payment.create({ order_id: o.order_id, pay_type: method === 'ypay_wxpay' ? 1 : 2 })
          const d = (r?.data || {}) as any
          otns[method].push(d.out_trade_no || ''); oids[method].push(o.order_id); ctkns[method].push(d.check_token || '')
          if (!qrCodes[method] && d.qr_image) { qrCodes[method] = d.qr_image; gwUrls[method] = d.submit_url || '' }
          if (d.h5_qrurl) { h5Urls[method] = d.h5_qrurl }
        } catch (e: any) {
          if (!qrCodes[method]) { store.toast('创建支付失败：' + (e?.message || '网络错误'), 'error') }
        }
      }
    }
    const hasAnyQr = Object.values(qrCodes).some(q => !!q)
    if (!hasAnyQr) { paying.value = false; return }
    payQrCodes.value = qrCodes; payGatewayUrls.value = gwUrls; payH5Urls.value = h5Urls
    payOutTradeNosByMethod.value = otns; payOrderIdsByMethod.value = oids; payCheckTokensByMethod.value = ctkns
    selectedPayMethod.value = 'ypay_wxpay'
    payQrCode.value = qrCodes['ypay_wxpay'] || qrCodes['ypay_alipay'] || ''
    payGatewayUrl.value = gwUrls['ypay_wxpay'] || gwUrls['ypay_alipay'] || ''
    payOutTradeNos.value = otns['ypay_wxpay'] || otns['ypay_alipay'] || []
    payCurrentOrderIds.value = oids['ypay_wxpay'] || oids['ypay_alipay'] || []
    payCheckTokens.value = ctkns['ypay_wxpay'] || ctkns['ypay_alipay'] || []
    showPayModal.value = true; startPollPayment()
    if (isMobile()) {
      const h5Url = h5Urls[selectedPayMethod.value]
      if (h5Url) { mobileRedirecting.value = true; window.location.href = h5Url }
    }
  } catch {}
  finally { paying.value = false }
}

function startPollPayment() {
  if (payPollTimer.value) { clearTimeout(payPollTimer.value); payPollTimer.value = null }
  let stopped = false
  async function tick() {
    if (stopped) return
    try {
      if (payOutTradeNos.value.length === 0) return
      let allPaid = true
      let allExpired = true
      for (let i = 0; i < payOutTradeNos.value.length; i++) {
        const r = await api.payment.check(payOutTradeNos.value[i], payCurrentOrderIds.value[i] || '', payCheckTokens.value[i] || '') as any
        if (!r?.expired) allExpired = false
        if (!r || !r.paid) { allPaid = false }
      }
      if (allExpired) { stopped = true; closePay(); return }
      if (allPaid) { stopped = true; showPaySuccess.value = true; return }
    } catch {}
    if (!stopped) payPollTimer.value = setTimeout(tick, 3000)
  }
  payPollTimer.value = setTimeout(tick, 3000)
}
onBeforeUnmount(() => { if (payPollTimer.value) { clearTimeout(payPollTimer.value); payPollTimer.value = null } })
function onPaySuccessDone() {
  showPaySuccess.value = false
  closePay()
  router.push('/')
}
function closePay() { showPayModal.value = false; showPaySuccess.value = false; mobileRedirecting.value = false; if (payPollTimer.value) { clearTimeout(payPollTimer.value); payPollTimer.value = null } }
function switchPayMethod(m: string) {
  selectedPayMethod.value = m
  payQrCode.value = payQrCodes.value[m] || ''; payGatewayUrl.value = payGatewayUrls.value[m] || ''
  payOutTradeNos.value = payOutTradeNosByMethod.value[m] || []
  payCurrentOrderIds.value = payOrderIdsByMethod.value[m] || []
  payCheckTokens.value = payCheckTokensByMethod.value[m] || []
  if (payPollTimer.value) { clearTimeout(payPollTimer.value); payPollTimer.value = null }; startPollPayment()
}

const fmtMoney = (n: number) => '¥' + (n || 0).toFixed(2)
</script>

<template>
  <div class="landing">
    <template v-if="loading">
      <div class="ldg-center">
<div class="spinner-lg"></div><p>加载中...</p>
</div>
    </template>
    <template v-else-if="notFound">
      <div class="ldg-center">
        <div class="nf-icon">
<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><path d="M8 11h6"/></svg>
</div>
        <h2>页面未找到</h2><p>该代理子站不存在或已下架</p><router-link to="/" class="btn btn-primary">
返回首页
</router-link>
      </div>
    </template>
    <template v-else>
      <header class="ldg-hero">
<div class="ldg-hero-bg"></div><div class="ldg-hero-content">
<div class="ldg-avatar">
{{ (agentData.display_name || slug).charAt(0).toUpperCase() }}
</div><h1>{{ agentData.display_name || slug }}</h1><p>{{ agentData.welcome_text || '欢迎使用网课代刷服务，三大平台一键完成' }}</p>
</div>
</header>

      <section class="ldg-main-content">
        <div class="ldg-features">
          <div class="ldg-feature-card">
<div class="ldg-fc-icon">
<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--c-primary)" stroke-width="1.5"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
</div><h3>全网网课</h3><p>自动发现学校关联的所有课程平台</p>
</div>
          <div class="ldg-feature-card">
<div class="ldg-fc-icon">
<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--c-warning)" stroke-width="1.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
</div><h3>快速完成</h3><p>智能刷课引擎，自动完成视频和考试</p>
</div>
          <div class="ldg-feature-card">
<div class="ldg-fc-icon">
<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--c-success)" stroke-width="1.5"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
</div><h3>安全可靠</h3><p>模拟真实学习行为，确保账号安全</p>
</div>
        </div>

        <div v-if="!scanDone" class="sub-order-form">
          <h3>开始下单</h3>
          <p class="form-hint">
输入学号密码，系统自动检测三大平台课程进度
</p>
          <div class="field">
<label>学号</label><input v-model="username" placeholder="请输入学号" :disabled="scanning" @keyup.enter="startScan" />
</div>
          <div class="field">
<label>密码</label><input v-model="password" type="password" placeholder="请输入平台密码" :disabled="scanning" @keyup.enter="startScan" />
</div>
          <button class="btn btn-primary btn-lg btn-block" :disabled="scanning" @click="startScan">
            <template v-if="!scanning">
开始检测课程
</template>
            <template v-else>
<span class="spinner-inline"></span>检测中...
</template>
          </button>
        </div>

        <div v-if="scanDone" class="results">
          <div v-if="studentName" class="results-topbar">
            <div class="rt-student">
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg><span>{{ studentName }}</span>
</div>
            <span class="rt-pill ok">{{ visiblePlatforms.filter(p => p.status === 'ok').length }} 平台成功</span>
            <span class="rt-pill pending">{{ visiblePlatforms.reduce((s,p) => s + p.courses.filter(c => !isCourseDone(c)).length, 0) }} 门未完成</span>
          </div>

          <div v-for="p in visiblePlatforms" :key="p.website_id" class="platform-block">
            <div class="pb-header">
              <label class="pb-check"><input type="checkbox" :checked="isPlatformAllChecked(p)" :indeterminate="!isPlatformAllChecked(p) && p.courses.some(c => !isCourseDone(c) && checkedCourseIds.has(c.course_id))" @change="togglePlatform(p.website_id, ($event.target as HTMLInputElement).checked)" /></label>
              <span class="pb-badge" :class="p.status === 'ok' ? 'ok' : 'fail'">{{ p.name }}</span>
              <span class="pb-count">{{ p.courses.length }} 门（{{ p.courses.filter(c => !isCourseDone(c)).length }} 门未完成）</span>
            </div>
            <div class="course-list">
              <div v-for="c in p.courses" :key="c.course_id" class="course-row" :class="{ done: isCourseDone(c) }">
                <label class="cr-check"><input type="checkbox" :checked="checkedCourseIds.has(c.course_id)" :disabled="isCourseDone(c)" @change="toggleCourse(c.course_id)" /></label>
                <span class="cr-name">{{ c.course_name }}</span>
                <div class="cr-meta">
                  <div class="cr-bar">
<div class="cr-bar-fill" :class="pct(c) >= 100 ? 'done' : pct(c) < 50 ? 'low' : ''" :style="{ width: pct(c) + '%' }"></div>
</div>
                  <span class="cr-pct">{{ pct(c) }}%</span>
                  <span class="cr-pill" :class="c.video_pending > 0 ? 'warn' : 'ok'">{{ c.video_pending }} 剩余</span>
                </div>
              </div>
            </div>
          </div>

          <div class="summary-bar">
            <div class="sb-left">
<span class="sb-item">已选 <strong>{{ summary.courses }}</strong> 门 · <strong>{{ summary.videos }}</strong> 视频 <span v-if="summary.exams > 0">· <strong>{{ summary.exams }}</strong> 考试</span></span>
</div>
            <div class="sb-right">
<span class="sb-price">¥{{ summary.total.toFixed(2) }}</span><button class="btn btn-primary btn-lg" :disabled="paying || summary.courses === 0" @click="submitAndPay">
<template v-if="!paying">
提交并支付
</template><template v-else>
<span class="spinner-inline"></span>提交中
</template>
</button>
</div>
          </div>
        </div>
      </section>

      <footer class="ldg-footer">
<span>FUCK 文理网课 · 代理: {{ agentData.display_name || slug }}</span>
</footer>

      <div class="modal-overlay" :class="{ show: showPayModal && !showPaySuccess }" @click.self="closePay">
        <div class="modal-box pay-modal">
          <h3>扫码支付</h3><div class="modal-amount">
¥{{ payTotal.toFixed(2) }}
</div>
          <div class="pay-method-tabs">
            <button :class="['pm-tab', { active: selectedPayMethod === 'ypay_wxpay' }]" @click="switchPayMethod('ypay_wxpay')">
微信
</button>
            <button :class="['pm-tab', { active: selectedPayMethod === 'ypay_alipay' }]" @click="switchPayMethod('ypay_alipay')">
支付宝
</button>
          </div>
          <div v-if="mobileRedirecting" class="mobile-redirect-box">
            <div class="spinner-sm"></div>
            <p>正在跳转到支付APP...</p>
            <a v-if="payH5Urls[selectedPayMethod]" :href="payH5Urls[selectedPayMethod]" class="btn btn-primary btn-block">手动打开</a>
            <button class="btn btn-ghost btn-block" @click="mobileRedirecting = false">
返回二维码
</button>
          </div>
          <template v-else>
            <div class="qr-section">
              <img v-if="payQrCode" :src="payQrCode" alt="支付码" class="pay-qr-img" />
              <div v-else class="pay-qr-placeholder">
生成二维码中...
</div>
              <p class="qr-label">
使用{{ selectedPayMethod === 'ypay_alipay' ? '支付宝' : '微信' }}扫码支付
</p>
            </div>
            <a v-if="payH5Urls[selectedPayMethod]" :href="payH5Urls[selectedPayMethod]" class="btn btn-primary btn-block pay-link-btn">打开支付APP</a>
            <a v-else-if="payGatewayUrl" :href="payGatewayUrl" target="_blank" class="btn btn-outline btn-block pay-link-btn">在浏览器中打开支付页面</a>
          </template>
          <button class="btn btn-ghost btn-block" style="margin-top:10px" @click="closePay">
取消支付
</button>
        </div>
      </div>

      <PaymentSuccess :visible="showPaySuccess" subtitle="订单已提交" @done="onPaySuccessDone" />
    </template>
  </div>
</template>

<style scoped>
.landing { min-height: 100vh; display: flex; flex-direction: column; background: #f7f8fa; }
.ldg-center { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px; text-align: center; }
.spinner-lg { width: 36px; height: 36px; border: 2.5px solid var(--c-border); border-top-color: var(--c-primary); border-radius: 50%; animation: spin .65s linear infinite; margin-bottom: 16px; }
.spinner-inline { width: 14px; height: 14px; border: 2px solid rgba(255,255,255,.3); border-top-color: #fff; border-radius: 50%; animation: spin .65s linear infinite; display: inline-block; }
.nf-icon { margin-bottom: 16px; }
.ldg-center h2 { font-size: 22px; font-weight: 700; margin-bottom: 8px; }
.ldg-center p { color: var(--c-text-muted); margin-bottom: 20px; }

.btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 9px 20px; border: none; border-radius: 10px; font-weight: 600; font-size: 13.5px; cursor: pointer; transition: all .15s; white-space: nowrap; text-decoration: none; }
.btn-primary { background: var(--c-primary); color: #fff; box-shadow: 0 2px 8px rgba(79,110,247,.25); }
.btn-primary:hover:not(:disabled) { background: var(--c-primary-hover); transform: translateY(-1px); }
.btn-primary:disabled { opacity: .55; cursor: not-allowed; transform: none; }
.btn-ghost { background: transparent; color: var(--c-text-secondary); }
.btn-ghost:hover { background: var(--c-primary-bg); color: var(--c-primary); }
.btn-lg { padding: 14px 36px; font-size: 16px; }
.btn-block { width: 100%; }
.btn-outline { background: transparent; border: 1px solid var(--c-border); color: var(--c-text-secondary); }
.btn-outline:hover { border-color: var(--c-primary); color: var(--c-primary); }

.ldg-hero { position: relative; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 56px 24px 48px; text-align: center; color: #fff; overflow: hidden; }
.ldg-hero-bg { position: absolute; inset: 0; opacity: .06; background: repeating-linear-gradient(45deg,transparent,transparent 40px,rgba(255,255,255,.3) 40px,rgba(255,255,255,.3) 80px); }
.ldg-hero-content { position: relative; z-index: 1; }
.ldg-avatar { width: 64px; height: 64px; border-radius: 50%; background: rgba(255,255,255,.25); display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: 700; margin: 0 auto 12px; border: 3px solid rgba(255,255,255,.4); }
.ldg-hero h1 { font-size: 24px; font-weight: 700; margin-bottom: 6px; }
.ldg-hero p { font-size: 13.5px; opacity: .85; }

.ldg-main-content { max-width: 880px; width: 100%; margin: -24px auto 0; padding: 0 20px; position: relative; z-index: 2; }
.ldg-features { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 24px; }
.ldg-feature-card { background: var(--c-surface); border-radius: 12px; padding: 22px 16px; text-align: center; box-shadow: var(--shadow-md); }
.ldg-fc-icon { margin-bottom: 10px; display: flex; justify-content: center; }
.ldg-feature-card h3 { font-size: 15px; font-weight: 700; margin-bottom: 4px; }
.ldg-feature-card p { font-size: 12px; color: var(--c-text-secondary); }

.sub-order-form { background: var(--c-surface); border-radius: 12px; padding: 28px 24px; box-shadow: var(--shadow); margin-bottom: 20px; }
.sub-order-form h3 { font-size: 17px; font-weight: 700; margin-bottom: 4px; }
.form-hint { font-size: 12.5px; color: var(--c-text-muted); margin-bottom: 20px; }
.field { display: flex; flex-direction: column; gap: 5px; margin-bottom: 16px; }
.field label { font-size: 13px; font-weight: 500; }
.field input { height: 42px; padding: 0 14px; border: 1px solid var(--c-border); border-radius: 8px; background: var(--c-bg); font-size: 14px; outline: none; }
.field input:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px rgba(79,110,247,.1); background: var(--c-surface); }

.results { padding: 16px 0 32px; }
.results-topbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; }
.rt-student { display: flex; align-items: center; gap: 6px; font-weight: 600; color: var(--c-primary); padding: 4px 12px; background: var(--c-primary-bg); border-radius: 20px; }
.rt-pill { padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
.rt-pill.ok { background: var(--c-success-bg); color: var(--c-success); }
.rt-pill.pending { background: var(--c-warning-bg); color: var(--c-warning); }

.platform-block { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 10px; padding: 16px 18px; margin-bottom: 12px; }
.pb-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.pb-check input { cursor: pointer; }
.pb-badge { padding: 3px 10px; border-radius: 20px; font-size: 11.5px; font-weight: 600; }
.pb-badge.ok { background: var(--c-success-bg); color: var(--c-success); }
.pb-badge.fail { background: var(--c-danger-bg); color: var(--c-danger); }
.pb-count { font-size: 12px; color: var(--c-text-muted); margin-left: auto; }

.course-row { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-top: 1px solid #f3f4f6; }
.course-row.done { opacity: .5; }
.cr-check input { cursor: pointer; }
.cr-name { flex: 1; font-size: 13px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cr-meta { display: flex; align-items: center; gap: 8px; }
.cr-bar { width: 60px; height: 5px; background: #f1f5f9; border-radius: 3px; overflow: hidden; }
.cr-bar-fill { height: 100%; border-radius: 3px; background: var(--c-primary); }
.cr-bar-fill.done { background: var(--c-success); }
.cr-bar-fill.low { background: var(--c-warning); }
.cr-pct { font-size: 10px; color: var(--c-text-muted); min-width: 28px; }
.cr-pill { padding: 1px 6px; border-radius: 10px; font-size: 10px; font-weight: 600; }
.cr-pill.warn { background: var(--c-warning-bg); color: var(--c-warning); }
.cr-pill.ok { background: var(--c-success-bg); color: var(--c-success); }

.summary-bar { position: sticky; bottom: 0; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 10px; padding: 14px 20px; display: flex; align-items: center; justify-content: space-between; box-shadow: var(--shadow-md); margin-bottom: 20px; }
.sb-left { font-size: 13px; color: var(--c-text-secondary); }
.sb-left strong { color: var(--c-primary); }
.sb-right { display: flex; align-items: center; gap: 16px; }
.sb-price { font-size: 22px; font-weight: 800; color: var(--c-danger); }

.ldg-footer { text-align: center; padding: 28px; font-size: 12px; color: var(--c-text-muted); }

.modal-overlay { position: fixed; inset: 0; background: rgba(15,23,42,.4); backdrop-filter: blur(4px); display: none; align-items: center; justify-content: center; z-index: 500; }
.modal-overlay.show { display: flex; }
.modal-box { background: var(--c-surface); border-radius: 14px; padding: 32px; width: 400px; max-width: 90vw; text-align: center; box-shadow: var(--shadow-lg); }
.modal-box h3 { font-size: 18px; font-weight: 700; }
.modal-amount { font-size: 36px; font-weight: 800; color: var(--c-primary); margin: 12px 0 16px; }
.pay-method-tabs { display: flex; background: var(--c-bg); border-radius: 8px; padding: 3px; margin-bottom: 16px; }
.pm-tab { flex: 1; padding: 7px 0; border: none; background: transparent; border-radius: 6px; font-size: 13px; font-weight: 600; color: var(--c-text-secondary); cursor: pointer; }
.pm-tab.active { background: #fff; color: var(--c-text); box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.qr-section { margin: 12px 0; }
.pay-qr-img { width: 180px; height: 180px; border-radius: 10px; border: 2px solid var(--c-border); background: #fff; padding: 6px; }
.pay-qr-placeholder { width: 180px; height: 180px; margin: 0 auto; display: flex; align-items: center; justify-content: center; background: var(--c-bg); border-radius: 10px; border: 2px dashed var(--c-border); font-size: 13px; color: var(--c-text-muted); }
.qr-label { font-size: 12px; color: var(--c-text-muted); margin-top: 8px; }
.pay-link-btn { text-decoration: none; justify-content: center; display: flex; align-items: center; gap: 6px; }

@media (max-width: 640px) {
  .ldg-features { grid-template-columns: 1fr; }
  .ldg-hero { padding: 36px 16px 32px; }
  .ldg-hero h1 { font-size: 20px; }
  .ldg-main-content { padding: 0 12px; }
  .summary-bar { flex-direction: column; gap: 10px; }
  .sb-right { width: 100%; justify-content: center; }
}
</style>
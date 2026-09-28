<template>
  <div class="pay-page">
    <div class="pay-card">
      <template v-if="loading">
        <div class="pay-spinner"></div>
        <p class="pay-hint">
          正在加载订单信息…
        </p>
      </template>

      <template v-else-if="error">
        <div class="pay-icon-fail">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="1.8">
            <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
          </svg>
        </div>
        <h2 class="pay-title">
          无法加载订单
        </h2>
        <p class="pay-error-text">
          {{ error }}
        </p>
      </template>

      <template v-else-if="expired">
        <div class="pay-icon-fail">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--c-warning)" stroke-width="1.8">
            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
          </svg>
        </div>
        <h2 class="pay-title">
          订单已过期
        </h2>
        <p class="pay-hint">
          请返回重新下单
        </p>
      </template>

      <template v-else>
        <div v-if="mobileRedirecting" class="mobile-redirect-box">
          <div class="pay-spinner"></div>
          <p class="pay-hint">
            正在跳转到支付 App…
          </p>
          <a v-if="h5Url" :href="h5Url" class="pay-btn-back">手动打开支付 App</a>
          <button class="pay-btn-back pay-btn-muted" @click="mobileRedirecting = false">
            返回二维码
          </button>
        </div>
        <template v-else>
          <h2 class="pay-title">
            扫码支付
          </h2>
          <div class="pay-amount">
            ¥{{ reallyPrice.toFixed(2) }}
          </div>
          <p class="pay-amount-warn">
            请支付相同金额，否则无法自动到账
          </p>

          <!-- 二维码展示区 -->
          <div class="qr-box">
            <img v-if="qrContentType === 'image_url' && qrImage" :src="qrImage" alt="收款码" class="qr-img" />
            <img v-else-if="qrImage" :src="qrImage" alt="支付二维码" class="qr-img" />
            <div v-else class="pay-spinner"></div>
          </div>

          <p class="pay-hint">
            {{ payHint }}
          </p>
          <p v-if="channelName" class="pay-channel">
            支付通道：{{ channelName }}
          </p>

          <a v-if="h5Url && qrContentType !== 'wxpay'" :href="h5Url" class="pay-btn-back">打开支付 App</a>
          <button v-if="isMobile() && qrImage && qrContentType === 'wxpay'" class="pay-btn-back pay-btn-wechat" @click="saveQr">
            保存二维码到相册
          </button>

          <div v-if="remaining > 0" class="pay-countdown">
            剩余支付时间 {{ formatTime(remaining) }}
          </div>
        </template>
      </template>
    </div>
    <PaymentSuccess :visible="showPaySuccess" :amount="reallyPrice" @done="onPaySuccessDone" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PaymentSuccess from '@/components/PaymentSuccess.vue'
import { isMobile } from '@/utils/mobile'

const route = useRoute()
const router = useRouter()

const returnTo = (route.query.return_to as string) || ''

const loading = ref(true)
const error = ref('')
const paid = ref(false)
const showPaySuccess = ref(false)
const expired = ref(false)
const qrImage = ref('')
const reallyPrice = ref(0)
const payType = ref(1)
const qrContentType = ref('')
const channelName = ref('')
const remaining = ref(0)
const redirectCountdown = ref(0)
const h5Url = ref('')
const mobileRedirecting = ref(false)

let pollTimer: ReturnType<typeof setInterval> | null = null
let countdownTimer: ReturnType<typeof setInterval> | null = null
let redirectTimer: ReturnType<typeof setInterval> | null = null
let currentTradeNo = ''
let checking = false

// 手机端跳转支付APP后返回时，立即检查支付状态
function onVisibilityChange() {
  if (document.visibilityState === 'visible' && currentTradeNo && !paid.value && !checking) {
    checkOnce(currentTradeNo)
  }
}

async function checkOnce(tradeNo: string) {
  if (checking) return
  checking = true
  try {
    const r = await fetch(`/api/ypay/check/${tradeNo}`)
    const d = await r.json()
    if (d.paid) {
      stopPoll()
      paid.value = true
      reallyPrice.value = d.really_price || reallyPrice.value
      startRedirectCountdown()
    }
  } catch { /* ignore */ }
  finally { checking = false }
}

const payHint = computed(() => {
  // 根据 qr_content_type 提示用户用什么APP扫码
  const typeHints: Record<string, string> = {
    'wxpay': '请使用微信扫描上方二维码完成支付',
    'alipay': '请使用支付宝扫描上方二维码完成支付',
    'image_url': '请使用对应APP扫描上方收款码完成支付',
  }
  if (qrContentType.value && typeHints[qrContentType.value]) {
    return typeHints[qrContentType.value]
  }
  // 根据 pay_type 兜底
  const typePayHints: Record<number, string> = {
    1: '请使用微信扫描上方二维码完成支付',
    2: '请使用支付宝扫描上方二维码完成支付',
    3: '请扫码完成支付',
  }
  return typePayHints[payType.value] || '请扫描上方二维码完成支付'
})

function formatTime(sec: number) {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function saveQr() {
  const src = qrImage.value
  if (!src) return
  const a = document.createElement('a')
  a.href = src
  a.download = 'pay-qr.png'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

async function loadOrder() {
  const tradeNo = route.params.id as string
  currentTradeNo = tradeNo
  if (!tradeNo) {
    error.value = '订单号无效'
    loading.value = false
    return
  }
  try {
    const r = await fetch(`/api/ypay/order/${tradeNo}`)
    const d = await r.json()
    if (d.code !== 0 || !d.data) {
      error.value = d.message || '订单不存在或已过期'
      loading.value = false
      return
    }
    if (d.data.status === 1) {
      paid.value = true
      reallyPrice.value = d.data.truemoney || 0
      loading.value = false
      startRedirectCountdown()
      return
    }
    const timeout = d.data.timeout_seconds || 300
    qrImage.value = d.data.qr_image || ''
    reallyPrice.value = d.data.truemoney || d.data.money || 0
    payType.value = d.data.pay_type || 1
    qrContentType.value = d.data.qr_content_type || ''
    channelName.value = d.data.channel_name || ''
    h5Url.value = d.data.h5_qrurl || ''
    remaining.value = timeout
    loading.value = false
    if (isMobile() && h5Url.value && qrContentType.value !== 'wxpay') {
      mobileRedirecting.value = true
      window.location.href = h5Url.value
    }
    startPoll(tradeNo)
  } catch {
    error.value = '网络错误，请刷新重试'
    loading.value = false
  }
}

function startRedirectCountdown() {
  showPaySuccess.value = true
}
function onPaySuccessDone() {
  showPaySuccess.value = false
  router.push('/')
}

function startPoll(tradeNo: string) {
  let count = 0
  let stopped = false
  async function tick() {
    if (stopped) return
    count++
    if (count > 120) {
      stopped = true; stopPoll(); expired.value = true; return
    }
    if (remaining.value > 0) remaining.value--
    try {
      const r = await fetch(`/api/ypay/check/${tradeNo}`)
      const d = await r.json()
      if (d.remaining !== undefined) remaining.value = d.remaining
      if (d.paid) {
        stopped = true; stopPoll(); paid.value = true
        reallyPrice.value = d.really_price || reallyPrice.value
        startRedirectCountdown(); return
      }
      if (d.expired || (d.remaining !== undefined && d.remaining <= 0)) {
        stopped = true; stopPoll(); expired.value = true; return
      }
    } catch { /* ignore */ }
    if (!stopped) {
      if (remaining.value <= 0) { stopped = true; stopPoll(); expired.value = true; return }
      pollTimer = setTimeout(tick, 3000)
    }
  }
  pollTimer = setTimeout(tick, 3000)
}

function stopPoll() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null }
  if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
  if (redirectTimer) { clearInterval(redirectTimer); redirectTimer = null }
}

onMounted(() => {
  loadOrder()
  document.addEventListener('visibilitychange', onVisibilityChange)
})
onUnmounted(() => {
  stopPoll()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.pay-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  position: relative;
}
.pay-card {
  position: relative;
  background: var(--c-surface);
  border: 1px solid var(--c-border-light);
  border-radius: 20px;
  padding: 44px 36px;
  max-width: 400px;
  width: 100%;
  text-align: center;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(20,20,24,.07), 0 28px 72px rgba(20, 20, 24, .12);
  animation: pay-rise .32s cubic-bezier(.32, .72, .35, 1) both;
}
@keyframes pay-rise {
  from { opacity: 0; transform: translateY(16px) scale(.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.pay-title {
  font-size: 21px;
  font-weight: 700;
  letter-spacing: -.015em;
  color: var(--c-text);
  margin: 0 0 6px;
}
.pay-amount {
  font-size: 40px;
  font-weight: 800;
  letter-spacing: -.02em;
  font-variant-numeric: tabular-nums;
  color: var(--c-text);
  margin: 14px 0 4px;
}
.pay-amount-warn {
  font-size: 12px;
  color: var(--c-warning);
  margin: 0 0 22px;
  font-weight: 600;
}

.qr-box {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 220px;
  margin: 0 auto 18px;
}
.qr-img {
  width: 220px;
  height: 220px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, .1);
  background: #fff;
  padding: 8px;
  object-fit: contain;
  box-shadow: 0 0 0 6px rgba(16, 16, 20, .04), 0 12px 32px rgba(20, 20, 24, .09);
}

.pay-hint {
  font-size: 14px;
  color: var(--c-text-secondary);
  margin: 0 0 6px;
  line-height: 1.55;
}
.pay-channel {
  font-size: 12px;
  color: var(--c-text-muted);
  margin: 0 0 8px;
}
.pay-countdown {
  display: inline-block;
  font-size: 12.5px;
  color: var(--c-warning);
  font-weight: 600;
  margin-top: 14px;
  padding: 4px 14px;
  background: var(--c-warning-bg);
  border-radius: 999px;
}
.pay-error-text {
  font-size: 14px;
  color: var(--c-danger);
  margin: 10px 0 0;
  line-height: 1.5;
}
.pay-icon-fail {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
  animation: pay-pop .35s cubic-bezier(.32, .72, .35, 1) both;
}
@keyframes pay-pop {
  from { opacity: 0; transform: scale(.72); }
  to { opacity: 1; transform: scale(1); }
}

.pay-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--c-border);
  border-top-color: var(--c-primary);
  border-radius: 50%;
  animation: spin .7s linear infinite;
  margin: 0 auto 16px;
}

.pay-btn-back {
  display: block;
  margin: 14px auto 0;
  max-width: 220px;
  width: 100%;
  padding: 11px 24px;
  background: var(--c-gradient);
  color: #fff;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  text-align: center;
  box-shadow: var(--shadow-primary);
  transition: transform .22s cubic-bezier(.32, .72, .35, 1), box-shadow .22s, background .22s;
}
.pay-btn-back:hover {
  filter: brightness(1.12);
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(16, 16, 20, .2);
}
.pay-btn-back:active {
  transform: scale(.97);
  box-shadow: 0 1px 4px rgba(20, 20, 24, .2);
}
.pay-btn-wechat {
  background: #07c160;
  box-shadow: 0 2px 10px rgba(7, 193, 96, .22);
}
.pay-btn-wechat:hover {
  background: #06ad56;
  box-shadow: 0 5px 16px rgba(7, 193, 96, .28);
}
.pay-btn-muted {
  background: var(--c-text-secondary);
  box-shadow: none;
  margin-top: 8px;
}
.pay-btn-muted:hover {
  background: var(--c-surface-3);
  box-shadow: 0 4px 12px rgba(0, 0, 0, .14);
}

.mobile-redirect-box {
  text-align: center;
  padding: 8px 0;
}
.mobile-redirect-box .pay-hint {
  margin-bottom: 4px;
}

@media (max-width: 480px) {
  .pay-card { padding: 32px 20px; }
  .pay-amount { font-size: 34px; }
  .qr-img { width: 240px; height: 240px; }
  .qr-box { min-height: 240px; }
}
@keyframes spin { to { transform: rotate(360deg) } }
</style>

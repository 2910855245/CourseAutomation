<template>
  <div class="pay-page">
    <div class="pay-card">
      <template v-if="loading">
        <div class="pay-spinner"></div>
        <p class="pay-hint">
加载订单信息...
</p>
      </template>

      <template v-else-if="error">
        <div class="pay-icon-fail">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2">
            <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
          </svg>
        </div>
        <p class="pay-error-text">
{{ error }}
</p>
      </template>

      <template v-else-if="expired">
        <div class="pay-icon-fail">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2">
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
正在跳转到支付APP...
</p>
          <a v-if="h5Url" :href="h5Url" class="pay-btn-back">手动打开支付APP</a>
          <button class="pay-btn-back" style="background:#6b7280;margin-top:8px" @click="mobileRedirecting = false">
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
请务必支付相同金额，多一分少一分都无法检测到
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
通道：{{ channelName }}
</p>

          <a v-if="h5Url && qrContentType !== 'wxpay'" :href="h5Url" class="pay-btn-back" style="display:block;text-align:center;margin:12px auto 0;max-width:200px">打开支付APP</a>
          <button v-if="isMobile() && qrImage && qrContentType === 'wxpay'" class="pay-btn-back" style="display:block;margin:12px auto 0;max-width:200px;background:#07c160" @click="saveQr">
保存二维码到相册
</button>

          <div v-if="remaining > 0" class="pay-countdown">
            剩余支付时间：{{ formatTime(remaining) }}
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
  background: #f5f5f7;
  padding: 20px;
}
.pay-card {
  background: #fff;
  border-radius: 16px;
  padding: 40px 32px;
  max-width: 380px;
  width: 100%;
  text-align: center;
  box-shadow: 0 2px 12px rgba(0,0,0,0.08);
}
.pay-title {
  font-size: 20px;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0 0 8px;
}
.pay-amount {
  font-size: 36px;
  font-weight: 800;
  color: #1a1a1a;
  margin: 16px 0 4px;
}
.pay-amount-warn {
  font-size: 12px;
  color: #ef4444;
  margin: 0 0 20px;
  font-weight: 500;
}
.qr-box {
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 20px;
}
.qr-img {
  width: 220px;
  height: 220px;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  object-fit: contain;
}
.pay-hint {
  font-size: 14px;
  color: #6b7280;
  margin: 0 0 8px;
  line-height: 1.5;
}
.pay-channel {
  font-size: 12px;
  color: #9ca3af;
  margin: 0 0 8px;
}
.pay-countdown {
  font-size: 13px;
  color: #f59e0b;
  font-weight: 600;
  margin-top: 12px;
}
.pay-error-text {
  font-size: 15px;
  color: #ef4444;
  margin: 16px 0 0;
}
.pay-icon-fail {
  margin-bottom: 16px;
}
.pay-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid #e5e7eb;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 16px;
}
.pay-redirect {
  font-size: 13px;
  color: #6b7280;
  margin-top: 12px;
}
.pay-btn-back {
  margin-top: 16px;
  padding: 10px 24px;
  background: #4f6ef7;
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}
.pay-btn-back:active { background: #3b5de7; }

@media (max-width: 420px) {
  .pay-card { padding: 28px 20px; }
  .pay-amount { font-size: 42px; }
  .qr-img { width: 260px; height: 260px; }
}
@keyframes spin { to { transform: rotate(360deg) } }
@keyframes circle-draw { to { stroke-dashoffset: 0 } }
@keyframes check-draw { to { stroke-dashoffset: 0 } }
@keyframes fade-in { to { opacity: 1 } }
</style>

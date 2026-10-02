<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api'
import AppTopbar from '@/components/AppTopbar.vue'

const store = useAppStore()
const loading = ref(true)
const loadError = ref('')
const data = ref<any>(null)
// 手机号（选填）：领卡与买学期卡都带上它。它 = 换设备后唯一的自助找回凭据，
// 所以这里只收手机号，不收自由文本联系方式（自由文本查不出、也认不了人）。
const phone = ref(localStorage.getItem('promo_phone') || '')
function savePhone() {
  try { localStorage.setItem('promo_phone', phone.value.trim()) } catch { }
}
const claiming = ref(false)
const copied = ref(false)

// 自助找回：手机号 + 卡号（或后 4 位 / 订单号）
const restoreOpen = ref(false)
const restorePhone = ref(phone.value)
const restoreSecret = ref('')
const restoring = ref(false)

async function doRestore() {
  if (restoring.value) return
  restoring.value = true
  try {
    const r = await api.promo.restore(restorePhone.value.trim(), restoreSecret.value.trim())
    data.value = r.data?.overview || data.value
    phone.value = restorePhone.value.trim(); savePhone()
    const n = r.data?.result?.cards ?? 0
    store.toast(n > 0 ? `已找回 ${n} 张卡，邀请进度也一并恢复` : '已找回', 'success')
    restoreOpen.value = false
    restoreSecret.value = ''
  } catch (e: any) {
    store.toast(e?.message || '找回失败，请核对手机号与卡号', 'error')
  } finally { restoring.value = false }
}

const link = computed(() => {
  const code = data.value?.code || ''
  if (!code) return ''
  return `${location.origin}/?ref=${code}`
})

const progress = computed(() => {
  const d = data.value
  if (!d) return { done: 0, need: 1, pct: 0 }
  const need = Math.max(1, d.threshold || 1)
  // 进度条语义 = "距下一张卡的推进度"：
  //   - 手上已经有可领的卡 → 满格（此前直接取模，邀请 6 人时会显示 0/3，看起来像 bug）
  //   - 否则 → 本轮已积累人数（取模才是"距下一张还差几个"的正确口径）
  if ((d.can_claim || 0) > 0) return { done: need, need, pct: 100 }
  const done = (d.invited_valid || 0) % need
  return { done, need, pct: Math.round((done / need) * 100) }
})

/** 当前持有的有效卡（有效期最长的第一张） */
const activeCard = computed(() => (data.value?.cards || []).find((c: any) => c.valid) || null)

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const r = await api.invite.me()
    data.value = r.data
  } catch (e: any) {
    // 页面主体全靠这份数据，失败必须给出可见的错误态，不能白屏
    loadError.value = e?.message || '加载失败，请稍后重试'
    store.toast(loadError.value, 'error')
  } finally { loading.value = false }
}

async function copyLink() {
  const text = link.value
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    store.toast('邀请链接已复制', 'success')
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    store.toast('复制失败，请手动选择链接', 'warning')
  }
}

async function claim() {
  if (!data.value?.can_claim) return
  claiming.value = true
  try {
    const r = await api.invite.claim(phone.value)
    data.value = r.data?.overview || data.value
    savePhone()
    store.toast(`领取成功：${r.data?.card?.code || '免单卡'}`, 'success')
  } catch (e: any) {
    store.toast(e?.message || '领取失败', 'error')
  } finally { claiming.value = false }
}

// ── 学期卡（付费）────────────────────────────────────────────────────────
// 收款复用订单页那套 /api/payment/batch-create（传单个 order_id），
// 好处是入账/发卡全走后端已有的三条收款路径，前端不用自己实现对账。
const passPaying = ref(false)
const passOpen = ref(false)
const passPaid = ref(false)
const passMethod = ref<'wx' | 'ali'>('wx')
const passAmount = ref(0)
const passQrs = ref<Record<string, string>>({})
const passBatchIds = ref<Record<string, string>>({})
const passOutTradeNos = ref<Record<string, string>>({})
let passTimer: ReturnType<typeof setInterval> | null = null

const passInfo = computed(() =>
  data.value?.pass || { enabled: false, price: 19.9, days: 180, exam_price: 5 })
/** 跑几门考试的花费才超过学期卡（价格都由后台配，不能写死数字） */
const passBreakEven = computed(() => {
  const exam = passInfo.value.exam_price || 5
  if (exam <= 0) return 1
  return Math.max(1, Math.floor((passInfo.value.price || 0) / exam) + 1)
})
const hasPass = computed(() => data.value?.has_pass === true)
const passCard = computed(() =>
  (data.value?.cards || []).find((c: any) => c.kind === 'pass' && c.valid) || null)
const passExpire = computed(() => (passCard.value?.expires_at || '').slice(0, 10))
const passQr = computed(() => passQrs.value[passMethod.value] || '')
const passBatchId = computed(() => passBatchIds.value[passMethod.value] || '')
const passOutTradeNo = computed(() => passOutTradeNos.value[passMethod.value] || '')

function stopPassPoll() {
  if (passTimer) { clearInterval(passTimer); passTimer = null }
}

function closePass() {
  stopPassPoll()
  passOpen.value = false
  passPaid.value = false
  passQrs.value = {}
  passBatchIds.value = {}
  passOutTradeNos.value = {}
}

function startPassPoll() {
  stopPassPoll()
  passTimer = setInterval(async () => {
    if (!passBatchId.value) return
    try {
      const r = await api.payment.batchCheck(passBatchId.value, passOutTradeNo.value)
      if (r?.data?.paid) {
        stopPassPoll()
        passPaid.value = true
        store.toast('学期卡已开通', 'success')
        await load()
      }
    } catch { /* 网络抖动：下一拍继续，不打断用户 */ }
  }, 3000)
}

async function buyPass() {
  if (passPaying.value || hasPass.value) return
  passPaying.value = true
  passPaid.value = false
  try {
    const r = await api.pass.create(phone.value)
    savePhone()
    const orderId = r.data?.order_id
    if (!orderId) throw new Error('建单失败，请稍后重试')
    passAmount.value = r.data?.price ?? passInfo.value.price
    // 一次性把微信/支付宝两个通道都建好，用户在本页就能换支付方式
    const qrs: Record<string, string> = {}
    const batchIds: Record<string, string> = {}
    const outTradeNos: Record<string, string> = {}
    for (const m of [{ key: 'wx', pay_type: 1 }, { key: 'ali', pay_type: 2 }]) {
      try {
        const p = await api.payment.batchCreate({ order_ids: [orderId], pay_type: m.pay_type })
        const pd: any = p?.data || {}
        if (pd.qr_image) qrs[m.key] = pd.qr_image
        if (pd.batch_id) batchIds[m.key] = pd.batch_id
        if (pd.out_trade_no) outTradeNos[m.key] = pd.out_trade_no
        if (pd.really_price) passAmount.value = pd.really_price
      } catch { /* 单个通道失败不影响另一个 */ }
    }
    if (!qrs.wx && !qrs.ali) throw new Error('收款通道暂不可用，请稍后重试')
    passQrs.value = qrs; passBatchIds.value = batchIds; passOutTradeNos.value = outTradeNos
    if (!qrs[passMethod.value]) passMethod.value = qrs.wx ? 'wx' : 'ali'
    passOpen.value = true
    startPassPoll()
  } catch (e: any) {
    store.toast(e?.message || '下单失败，请稍后重试', 'error')
  } finally { passPaying.value = false }
}

onMounted(load)
onBeforeUnmount(stopPassPoll)
</script>

<template>
  <div class="page">
    <AppTopbar :show-role-badge="true" />

    <div class="content-wrapper">
      <!-- 头图区：营销主视觉 -->
      <section class="hero anim-rise">
        <span class="eyebrow">邀请有礼</span>
        <h1 class="hero-title">邀请好友，得优先通道</h1>
        <p class="hero-sub">
          每成功邀请 <strong class="mono">{{ data?.threshold || 3 }}</strong> 位好友下单，
          即可领取 <strong class="mono">{{ data?.valid_days || 30 }}</strong> 天<strong>免单卡</strong> ——
          <strong>答题 / 考试免单</strong>（刷视频本来就免费），下单还能<strong>优先排队</strong>，不用等免费队列。
        </p>

        <div v-if="data?.free_mode" class="hero-banner">
          <span class="hb-dot" />
          限时活动进行中：当前<b>全场免费</b>（含考试 / 作业），免单卡可留到活动结束后继续免单
        </div>
      </section>

      <div v-if="loading" class="loading">加载中…</div>

      <div v-else-if="loadError" class="error-card">
        <p class="error-text">{{ loadError }}</p>
        <button class="btn btn-primary" @click="load">重试</button>
      </div>

      <template v-else-if="data">
        <!-- 学期卡（付费） -->
        <section class="card pass-card anim-rise">
          <div class="card-head">
            <h3>学期卡</h3>
            <span v-if="hasPass" class="status-tag ok">生效中</span>
          </div>

          <template v-if="hasPass">
            <p class="pass-own">
              答题 / 考试<b>全免单</b>、<b>暴力档</b>提速、下单<b>优先排队</b>均已生效
              <template v-if="passExpire">，有效期至 <b class="mono">{{ passExpire }}</b></template>。
            </p>
          </template>

          <template v-else-if="passInfo.enabled">
            <div class="pass-price">
              <span class="cur">¥</span><span class="num mono">{{ passInfo.price }}</span>
              <span class="unit">/ 整学期 {{ passInfo.days }} 天</span>
            </div>
            <ul class="pass-benefits">
              <li>整学期答题 / 考试<b>全免单</b>，不限门数</li>
              <li>解锁<b>暴力档</b>提速，比免费队列快得多</li>
              <li>下单<b>优先排队</b>，永远排在免费单前面</li>
            </ul>
            <button class="btn btn-primary pass-btn" :disabled="passPaying" @click="buyPass">
              {{ passPaying ? '处理中…' : `立即开通 ¥${passInfo.price}` }}
            </button>
            <p class="tip">
              按门付费是单门考试 ¥{{ passInfo.exam_price || 5 }}，跑 {{ passBreakEven }} 门就超过学期卡；
              一门一付还是整学期，你自己算。
            </p>
          </template>

          <p v-else class="tip">学期卡暂未开售，可先靠邀请领免单卡。</p>

          <!-- 收款面板（复用 batch-create / batch-check 通道） -->
          <div v-if="passOpen" class="pay-box">
            <template v-if="passPaid">
              <p class="pay-done">支付成功，学期卡已开通</p>
              <button class="btn pay-ghost" @click="closePass">知道了</button>
            </template>
            <template v-else>
              <div class="pay-methods">
                <button class="pm" :class="{ on: passMethod === 'wx' }" @click="passMethod = 'wx'">微信支付</button>
                <button class="pm" :class="{ on: passMethod === 'ali' }" @click="passMethod = 'ali'">支付宝</button>
              </div>
              <div class="pay-qr">
                <img v-if="passQr" :src="passQr" alt="支付二维码">
                <div v-else class="pay-qr-empty">该通道暂不可用，换个支付方式试试</div>
              </div>
              <p class="pay-amount mono">应付 ¥{{ passAmount }}</p>
              <p class="tip">扫码支付，付完本页会自动刷新，无需手动确认。</p>
              <button class="btn pay-ghost" @click="closePass">关闭</button>
            </template>
          </div>
        </section>

        <!-- 邀请链接 -->
        <section class="card anim-rise">
          <div class="card-head">
            <h3>我的专属邀请链接</h3>
            <span v-if="activeCard" class="status-tag ok">优先通道生效中</span>
          </div>
          <div class="link-row">
            <input class="link-input mono" :value="link" readonly @focus="(e: any) => e.target.select()">
            <button class="btn btn-primary" @click="copyLink">
              {{ copied ? '已复制' : '复制链接' }}
            </button>
          </div>
          <p class="tip">
            好友打开链接后完成一次下单即计入进度；同一好友只算一次，自己邀请自己不计。
          </p>
        </section>

        <!-- 进度 -->
        <section class="card anim-rise">
          <div class="card-head">
            <h3>邀请进度</h3>
            <span class="muted">
              有效邀请 <b class="mono">{{ data.invited_valid }}</b> 人
              <template v-if="data.invited_total > data.invited_valid">
                · 待转化 <b class="mono">{{ data.invited_total - data.invited_valid }}</b> 人
              </template>
            </span>
          </div>

          <div class="prog">
            <div class="prog-bar">
              <div class="prog-fill" :style="{ width: progress.pct + '%' }" />
            </div>
            <span class="prog-num mono">{{ progress.done }} / {{ progress.need }}</span>
          </div>

          <div class="claim-row">
            <div class="claim-info">
              <div class="claim-title">
                <template v-if="data.can_claim > 0">
                  可领取 <b class="mono">{{ data.can_claim }}</b> 张免单卡
                </template>
                <template v-else>
                  再邀请 <b class="mono">{{ data.need_more || progress.need - progress.done }}</b> 位好友下单即可领卡
                </template>
              </div>
              <div class="claim-sub">每张卡自领取起 {{ data.valid_days }} 天有效，可叠加领取</div>
            </div>
            <div class="claim-actions">
              <input
                v-model="phone"
                class="contact-input contact-value"
                inputmode="numeric"
                placeholder="手机号（选填，换设备找回用）"
                :disabled="!data.can_claim"
              >
              <button
                class="btn btn-primary"
                :disabled="claiming || !data.can_claim"
                @click="claim"
              >
                {{ claiming ? '领取中…' : data.can_claim > 0 ? '立即领取' : '暂不可领' }}
              </button>
            </div>
          </div>
        </section>

        <!-- 我的卡 -->
        <section v-if="data.cards?.length" class="card anim-rise">
          <div class="card-head">
            <h3>我的卡券</h3>
            <span class="muted">共 <b class="mono">{{ data.cards.length }}</b> 张</span>
          </div>
          <div class="card-grid">
            <div v-for="c in data.cards" :key="c.code" class="ticket" :class="{ expired: !c.valid }">
              <div class="ticket-top">
                <span class="ticket-code mono">{{ c.code }}</span>
                <span class="status-tag" :class="c.valid ? 'ok' : 'muted'">{{ c.valid ? '生效中' : '已过期' }}</span>
              </div>
              <div class="ticket-body">
                <span class="ticket-label">{{ c.kind === 'pass' ? '学期卡' : '免单卡' }}</span>
                <span class="ticket-days mono">{{ c.valid ? `剩 ${c.days_left} 天` : '—' }}</span>
              </div>
              <div class="ticket-foot">
                <span>有效期至 {{ (c.expires_at || '').slice(0, 10) }}</span>
                <span v-if="c.used_orders">已用 {{ c.used_orders }} 单</span>
              </div>
            </div>
          </div>
        </section>

        <!-- 换设备找回：卡与邀请进度都绑在当前浏览器上，清了就没了 -->
        <section class="card anim-rise">
          <div class="card-head">
            <h3>换设备了？找回我的卡</h3>
            <button class="btn btn-xs pay-ghost" @click="restoreOpen = !restoreOpen">
              {{ restoreOpen ? '收起' : '去认领' }}
            </button>
          </div>
          <p class="tip">
            卡和邀请进度都绑在<strong>当前浏览器</strong>上。清了缓存 / 换了手机后，用
            买卡或领卡时留的<strong>手机号</strong>，加上<strong>卡号（后 4 位即可）或订单号</strong>，
            就能把卡和邀请进度认领回来。
          </p>
          <div v-if="restoreOpen" class="restore-form">
            <input v-model="restorePhone" class="contact-input" inputmode="numeric" placeholder="手机号">
            <input v-model="restoreSecret" class="contact-input" placeholder="卡号 / 后 4 位 / 订单号">
            <button class="btn btn-primary" :disabled="restoring" @click="doRestore">
              {{ restoring ? '找回中…' : '找回' }}
            </button>
          </div>
        </section>

        <!-- 规则 -->
        <section class="card anim-rise">
          <div class="card-head">
            <h3>活动规则</h3>
          </div>
          <ol class="rules">
            <li>分享链接给好友，好友<b>通过链接进入并完成一次下单</b>记为 1 位有效邀请。</li>
            <li>每满 {{ data.threshold }} 位有效邀请，可领取 1 张 {{ data.valid_days }} 天<b>免单卡</b>，可重复领取。</li>
            <li><b>免单卡</b>的权益是<b>答题 / 考试免单</b>（刷视频本来就免费）+ 优先排队，额度内可重复使用。</li>
            <li>持卡下单<b>优先排队</b>：排在所有普通免费单之前，不用等免费队列。</li>
            <li>免费单（含免单卡）走<b>免费队列</b>且只能用<b>保守档</b>；<b>学期卡</b>与按门课付费的单解锁<b>暴力档</b>，走独立通道，永远不排在免费队列后面。</li>
            <li><b>学期卡</b>：付费开通，整学期（{{ passInfo.days }} 天）内答题/考试全免单、不限门数，并解锁暴力档与优先排队。</li>
            <li>卡片与当前浏览器身份绑定；领卡时填了联系方式的，换设备 / 清缓存后联系客服可找回。</li>
            <li>同一好友仅计一次；需通过你的链接进入并完成下单才计入，自己邀请自己不计。</li>
          </ol>
        </section>
      </template>
    </div>

    <footer class="page-footer">
      <span>Fuk 文理网课</span>
    </footer>
  </div>
</template>

<style scoped>
.page { min-height: 100vh; display: flex; flex-direction: column; }

/* ==================== 主视觉 ==================== */
.hero {
  padding: var(--space-8) 0 var(--space-6);
  text-align: center;
}
.hero-title {
  font-size: clamp(28px, 4vw, 40px);
  font-weight: 700;
  letter-spacing: var(--tracking-title);
  color: var(--c-text);
  margin: var(--space-3) 0 var(--space-3);
}
.hero-sub {
  font-size: 14px;
  line-height: 1.9;
  color: var(--c-text-secondary);
  max-width: 560px;
  margin: 0 auto;
}
.hero-sub strong { color: var(--c-primary); font-weight: 700; }
.hero-banner {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: var(--space-5);
  padding: 8px 16px;
  border-radius: 999px;
  background: var(--c-success-bg);
  color: var(--c-success);
  font-size: 12.5px;
  font-weight: 600;
}
.hero-banner b { font-weight: 700; }
.hb-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: currentColor;
  animation: pulse 1.6s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: .35; transform: scale(.8); }
}

.loading { text-align: center; padding: 60px; color: var(--c-text-muted); }

/* 加载失败：主体数据取不到时的出口，避免整页空白 */
.error-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 48px 22px;
  text-align: center;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 16px;
}
.error-text { font-size: 13.5px; color: var(--c-text-secondary); }

/* ==================== 卡片 ==================== */
.card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 16px;
  padding: 22px;
  box-shadow: var(--shadow-xs);
  margin-bottom: 16px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.card-head h3 {
  font-size: 15px;
  font-weight: 700;
  color: var(--c-text);
  letter-spacing: -0.01em;
}
.muted { font-size: 12.5px; color: var(--c-text-muted); }
.muted b { color: var(--c-text); }

/* ==================== 邀请链接 ==================== */
.link-row { display: flex; gap: 10px; flex-wrap: wrap; }
.link-input {
  flex: 1;
  min-width: 220px;
  height: 42px;
  padding: 0 14px;
  border: 1.5px solid var(--c-border);
  border-radius: 10px;
  background: var(--c-bg);
  color: var(--c-text);
  font-size: 13px;
  outline: none;
}
.link-input:focus { border-color: var(--c-primary); background: var(--c-surface); }
.tip { font-size: 12px; color: var(--c-text-muted); margin-top: 10px; line-height: 1.7; }

/* ==================== 进度 ==================== */
.prog { display: flex; align-items: center; gap: 12px; }
.prog-bar {
  flex: 1;
  height: 10px;
  border-radius: 999px;
  background: var(--c-bg);
  overflow: hidden;
}
.prog-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--c-primary), var(--c-info));
  transition: width .5s cubic-bezier(.32, .72, .35, 1);
}
.prog-num { font-size: 12.5px; color: var(--c-text-secondary); min-width: 52px; text-align: right; }

.claim-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--c-border);
  flex-wrap: wrap;
}
.claim-title { font-size: 13.5px; font-weight: 600; color: var(--c-text); }
.claim-title b { color: var(--c-primary); }
.claim-sub { font-size: 12px; color: var(--c-text-muted); margin-top: 3px; }
.claim-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.contact-input {
  height: 38px;
  padding: 0 12px;
  border: 1.5px solid var(--c-border);
  border-radius: 10px;
  background: var(--c-surface);
  color: var(--c-text);
  font-size: 13px;
  outline: none;
}
.contact-input:focus { border-color: var(--c-primary); }
.contact-value { width: 200px; }

/* 找回表单：手机号 + 卡号/订单号 + 按钮 */
.restore-form {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
}
.restore-form .contact-input { flex: 1; min-width: 180px; }

/* ==================== 票券 ==================== */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.ticket {
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: 14px 16px;
  background: linear-gradient(135deg, var(--c-primary-bg), var(--c-surface));
  transition: transform .25s cubic-bezier(.32, .72, .35, 1), box-shadow .25s cubic-bezier(.32, .72, .35, 1);
}
.ticket:hover { transform: translateY(-2px); box-shadow: var(--shadow-sm); }
.ticket.expired { background: var(--c-surface); opacity: .7; }
.ticket-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.ticket-code { font-size: 12.5px; font-weight: 700; color: var(--c-text); letter-spacing: .04em; }
.ticket-body {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin: 12px 0 8px;
}
.ticket-label { font-size: 14px; font-weight: 700; color: var(--c-primary); }
.ticket-days { font-size: 12.5px; color: var(--c-text-secondary); }
.ticket-foot {
  display: flex;
  justify-content: space-between;
  font-size: 11.5px;
  color: var(--c-text-muted);
}

/* ==================== 学期卡 ==================== */
.pass-card { background: linear-gradient(150deg, var(--c-primary-bg), var(--c-surface) 62%); }
.pass-own { font-size: 13.5px; line-height: 1.9; color: var(--c-text-secondary); }
.pass-own b { color: var(--c-primary); font-weight: 700; }
.pass-price { display: flex; align-items: baseline; gap: 6px; }
.pass-price .cur { font-size: 16px; font-weight: 700; color: var(--c-primary); }
.pass-price .num { font-size: 34px; font-weight: 700; letter-spacing: -0.02em; color: var(--c-primary); }
.pass-price .unit { font-size: 12.5px; color: var(--c-text-muted); }
.pass-benefits {
  margin: 14px 0 16px;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 7px;
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--c-text-secondary);
}
.pass-benefits b { color: var(--c-text); }
.pass-btn { width: 100%; height: 46px; font-size: 14.5px; font-weight: 700; }

/* 收款面板 */
.pay-box {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--c-border);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.pay-methods { display: flex; gap: 8px; }
.pm {
  height: 34px;
  padding: 0 16px;
  border: 1.5px solid var(--c-border);
  border-radius: 999px;
  background: var(--c-surface);
  color: var(--c-text-secondary);
  font-size: 12.5px;
  cursor: pointer;
  transition: all .2s ease;
}
.pm.on { border-color: var(--c-primary); background: var(--c-primary-bg); color: var(--c-primary); font-weight: 700; }
.pay-qr {
  width: 200px; height: 200px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--c-border);
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
}
.pay-qr img { width: 100%; height: 100%; object-fit: contain; }
.pay-qr-empty { font-size: 12px; color: var(--c-text-muted); text-align: center; padding: 0 16px; line-height: 1.7; }
.pay-amount { font-size: 15px; font-weight: 700; color: var(--c-text); }
.pay-done { font-size: 14px; font-weight: 700; color: var(--c-success); }
.pay-ghost {
  height: 36px;
  padding: 0 18px;
  border: 1.5px solid var(--c-border);
  border-radius: 10px;
  background: var(--c-surface);
  color: var(--c-text-secondary);
  font-size: 13px;
  cursor: pointer;
}
.pay-ghost:hover { border-color: var(--c-primary); color: var(--c-primary); }
.pay-box .tip { margin: 0; text-align: center; }

/* ==================== 规则 ==================== */
.rules {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 12.5px;
  line-height: 1.8;
  color: var(--c-text-secondary);
}
.rules b { color: var(--c-text); }

.page-footer {
  margin-top: auto;
  padding: var(--space-6) var(--space-5);
  text-align: center;
  font-size: 12px;
  color: var(--c-text-muted);
}

@media (max-width: 560px) {
  .claim-actions { width: 100%; }
  .contact-value { flex: 1; width: auto; }
}
</style>
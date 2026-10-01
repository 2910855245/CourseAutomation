<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api'
import AppTopbar from '@/components/AppTopbar.vue'

const store = useAppStore()
const loading = ref(true)
const loadError = ref('')
const data = ref<any>(null)
// 领取时留联系方式：类型 + 号码，拼成"微信：abc"存库（便于人工找回）
const saved = (localStorage.getItem('invite_contact') || '').split('：')
const contactType = ref(saved.length > 1 ? saved[0] : '')
const contactValue = ref(saved.length > 1 ? saved[1] : (localStorage.getItem('invite_contact') || ''))
const contact = computed(() =>
  contactValue.value.trim() ? `${contactType.value || '其他'}：${contactValue.value.trim()}` : '')
const claiming = ref(false)
const copied = ref(false)

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

const contactTypes = ['微信', 'QQ', '手机', '其他']

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
    const r = await api.invite.claim(contact.value)
    data.value = r.data?.overview || data.value
    if (contact.value) localStorage.setItem('invite_contact', contact.value)
    store.toast(`领取成功：${r.data?.card?.code || '刷课卡'}`, 'success')
  } catch (e: any) {
    store.toast(e?.message || '领取失败', 'error')
  } finally { claiming.value = false }
}

onMounted(load)
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
          即可领取 <strong class="mono">{{ data?.valid_days || 30 }}</strong> 天刷课卡 ——
          答题/考试<strong>免单</strong>，下单还能<strong>优先排队</strong>，不用等免费队列。
        </p>

        <div v-if="data?.free_mode" class="hero-banner">
          <span class="hb-dot" />
          限时活动进行中：当前<b>全场免费</b>，刷课卡可留到活动结束后继续免单
        </div>
      </section>

      <div v-if="loading" class="loading">加载中…</div>

      <div v-else-if="loadError" class="error-card">
        <p class="error-text">{{ loadError }}</p>
        <button class="btn btn-primary" @click="load">重试</button>
      </div>

      <template v-else-if="data">
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
                  可领取 <b class="mono">{{ data.can_claim }}</b> 张刷课卡
                </template>
                <template v-else>
                  再邀请 <b class="mono">{{ data.need_more || progress.need - progress.done }}</b> 位好友下单即可领卡
                </template>
              </div>
              <div class="claim-sub">每张卡自领取起 {{ data.valid_days }} 天有效，可叠加领取</div>
            </div>
            <div class="claim-actions">
              <select v-model="contactType" class="contact-input" :disabled="!data.can_claim">
                <option value="">联系方式</option>
                <option v-for="t in contactTypes" :key="t" :value="t">{{ t }}</option>
              </select>
              <input
                v-model="contactValue"
                class="contact-input contact-value"
                placeholder="选填：微信 / 手机号"
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
            <h3>我的刷课卡</h3>
            <span class="muted">共 <b class="mono">{{ data.cards.length }}</b> 张</span>
          </div>
          <div class="card-grid">
            <div v-for="c in data.cards" :key="c.code" class="ticket" :class="{ expired: !c.valid }">
              <div class="ticket-top">
                <span class="ticket-code mono">{{ c.code }}</span>
                <span class="status-tag" :class="c.valid ? 'ok' : 'muted'">{{ c.valid ? '生效中' : '已过期' }}</span>
              </div>
              <div class="ticket-body">
                <span class="ticket-label">刷课卡</span>
                <span class="ticket-days mono">{{ c.valid ? `剩 ${c.days_left} 天` : '—' }}</span>
              </div>
              <div class="ticket-foot">
                <span>有效期至 {{ (c.expires_at || '').slice(0, 10) }}</span>
                <span v-if="c.used_orders">已用 {{ c.used_orders }} 单</span>
              </div>
            </div>
          </div>
        </section>

        <!-- 规则 -->
        <section class="card anim-rise">
          <div class="card-head">
            <h3>活动规则</h3>
          </div>
          <ol class="rules">
            <li>分享链接给好友，好友<b>通过链接进入并完成一次下单</b>记为 1 位有效邀请。</li>
            <li>每满 {{ data.threshold }} 位有效邀请，可领取 1 张 {{ data.valid_days }} 天刷课卡，可重复领取。</li>
            <li>持卡期间<b>答题 / 考试免单</b>（刷视频本来就免费），额度内可重复使用。</li>
            <li>持卡下单<b>优先排队</b>：排在所有普通免费单之前，不用等免费队列。</li>
            <li>免费单（含持卡）走<b>免费队列</b>且只能用<b>保守档</b>；想用暴力档提速，需按门课付费 —— 付费订单走独立通道，永远不排在免费队列后面。</li>
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
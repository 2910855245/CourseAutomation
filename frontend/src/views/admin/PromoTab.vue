<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '@/api'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const loading = ref(true)
const saving = ref(false)
const stats = ref<any>(null)

// 表单（与 system_config 的键一一对应）
const freeMode = ref(false)
const inviteEnabled = ref(true)
const threshold = ref(3)
const requireOrder = ref(true)
const validDays = ref(30)
const maxOrders = ref(0)
// 学期卡（付费虚拟商品）
const passEnabled = ref(true)
const passPrice = ref(19.9)
const passDays = ref(180)

const CONFIG_KEYS = {
  free_mode: 'free_mode',
  invite_enabled: 'invite_enabled',
  threshold: 'invite_threshold',
  require_order: 'invite_require_order',
  valid_days: 'card_valid_days',
  max_orders: 'card_max_orders',
  pass_enabled: 'pass_enabled',
  pass_price: 'pass_price',
  pass_days: 'pass_days',
}

async function load() {
  loading.value = true
  try {
    const r = await api.adminPromo.stats()
    const d = r.data || {}
    stats.value = d
    const c = d.config || {}
    freeMode.value = !!c.free_mode
    inviteEnabled.value = c.invite_enabled !== false
    threshold.value = c.threshold ?? 3
    requireOrder.value = c.require_order !== false
    validDays.value = c.valid_days ?? 30
    maxOrders.value = c.max_orders ?? 0
    passEnabled.value = c.pass_enabled !== false
    passPrice.value = c.pass_price ?? 19.9
    passDays.value = c.pass_days ?? 180
  } catch (e: any) {
    store.toast(e?.message || '加载推广数据失败', 'error')
  } finally { loading.value = false }
}

async function save() {
  saving.value = true
  try {
    const pairs: [string, string][] = [
      [CONFIG_KEYS.free_mode, freeMode.value ? '1' : '0'],
      [CONFIG_KEYS.invite_enabled, inviteEnabled.value ? '1' : '0'],
      [CONFIG_KEYS.threshold, String(Math.max(1, Math.min(1000, Math.floor(threshold.value || 1))))],
      [CONFIG_KEYS.require_order, requireOrder.value ? '1' : '0'],
      [CONFIG_KEYS.valid_days, String(Math.max(1, Math.min(3650, Math.floor(validDays.value || 1))))],
      [CONFIG_KEYS.max_orders, String(Math.max(0, Math.floor(maxOrders.value || 0)))],
      [CONFIG_KEYS.pass_enabled, passEnabled.value ? '1' : '0'],
      [CONFIG_KEYS.pass_price, String(Math.max(0, Math.round((passPrice.value || 0) * 100) / 100))],
      [CONFIG_KEYS.pass_days, String(Math.max(1, Math.min(3650, Math.floor(passDays.value || 1))))],
    ]
    for (const [k, v] of pairs) await api.adminConfig.set(k, v)
    store.toast('推广配置已保存', 'success')
    load()
  } catch (e: any) {
    store.toast(e?.message || '保存失败', 'error')
  } finally { saving.value = false }
}

onMounted(load)
</script>

<template>
  <div class="promo-tab">
    <div v-if="loading" class="loading">加载中…</div>

    <template v-else>
      <!-- 数据概览 -->
      <div class="kpi-row">
        <div class="kpi">
          <div class="kpi-val mono">{{ stats?.visitors ?? 0 }}</div>
          <div class="kpi-label">累计访客</div>
          <div class="kpi-sub">今日 +{{ stats?.visitors_today ?? 0 }}</div>
        </div>
        <div class="kpi">
          <div class="kpi-val mono">{{ stats?.invites_valid ?? 0 }}</div>
          <div class="kpi-label">有效邀请</div>
          <div class="kpi-sub">共 {{ stats?.invites ?? 0 }} 次邀请</div>
        </div>
        <div class="kpi">
          <div class="kpi-val mono">{{ ((stats?.conversion ?? 0) * 100).toFixed(0) }}%</div>
          <div class="kpi-label">邀请转化率</div>
          <div class="kpi-sub">好友下单占比</div>
        </div>
        <div class="kpi">
          <div class="kpi-val mono">{{ stats?.cards_active ?? 0 }}</div>
          <div class="kpi-label">生效中的卡</div>
          <div class="kpi-sub">累计发出 {{ stats?.cards ?? 0 }} 张</div>
        </div>
        <div class="kpi">
          <div class="kpi-val mono">{{ stats?.pass_cards_active ?? 0 }}</div>
          <div class="kpi-label">生效中学期卡</div>
          <div class="kpi-sub">累计售出 {{ stats?.pass_cards ?? 0 }} 张</div>
        </div>
        <div class="kpi">
          <div class="kpi-val mono">{{ stats?.free_video_orders ?? 0 }}</div>
          <div class="kpi-label">纯视频免费单</div>
          <div class="kpi-sub">今日 {{ stats?.free_video_orders_today ?? 0 }} 单 · 天然免费</div>
        </div>
        <div class="kpi">
          <div class="kpi-val mono">{{ stats?.free_card_orders ?? 0 }}</div>
          <div class="kpi-label">卡 / 学期卡免单</div>
          <div class="kpi-sub">今日 {{ stats?.free_card_orders_today ?? 0 }} 单 · 卡的真实用量</div>
        </div>
      </div>

      <!-- 开关与参数 -->
      <div class="settings-card">
        <h3>营销配置</h3>
        <p class="settings-hint">
          <b>刷视频对所有人永久免费</b>（纯视频单本来就 0 元，直接进队列），
          平台收入来自答题 / 考试。所以下面「全场免费」开关管的是<b>考试 / 作业要不要也免费</b>。
        </p>

        <div class="opt-row">
          <div class="opt-main">
            <div class="opt-title">全场免费（含考试 / 作业）</div>
            <div class="opt-desc">
              刷视频本来就免费，这个开关只决定<b>考试 / 作业是否也变 0 元</b>。
              开着时所有新单 0 元直接进队列（活动期用），关闭后恢复按收费标准收费。
              免费单一律走保守档。
            </div>
          </div>
          <select v-model="freeMode" class="opt-input" :class="{ on: freeMode }">
            <option :value="true">开启</option>
            <option :value="false">关闭</option>
          </select>
        </div>

        <div class="opt-row">
          <div class="opt-main">
            <div class="opt-title">邀请活动</div>
            <div class="opt-desc">
              好友通过邀请链接进来即记录；每满设定人数可领 1 张<b>免单卡</b>（权益＝答题/考试免单 + 优先排队）。
              关闭后邀请页不再发卡，已发出的仍在有效期内可用。
            </div>
          </div>
          <select v-model="inviteEnabled" class="opt-input" :class="{ on: inviteEnabled }">
            <option :value="true">开启</option>
            <option :value="false">关闭</option>
          </select>
        </div>

        <div class="opt-row">
          <div class="opt-main">
            <div class="opt-title">有效邀请判定</div>
            <div class="opt-desc">"好友下单才算"更能防刷量；"打开链接就算"拉新更快但容易被刷。</div>
          </div>
          <select v-model="requireOrder" class="opt-input" :class="{ on: requireOrder }">
            <option :value="true">好友下单才算</option>
            <option :value="false">打开链接就算</option>
          </select>
        </div>

        <div class="grid-row">
          <div class="field">
            <label>每邀请几人可领 1 张卡</label>
            <input v-model.number="threshold" type="number" min="1" max="1000" class="opt-input full">
          </div>
          <div class="field">
            <label>免单卡有效期（天）</label>
            <input v-model.number="validDays" type="number" min="1" max="3650" class="opt-input full">
          </div>
          <div class="field">
            <label>一张卡可用订单数（0=不限）</label>
            <input v-model.number="maxOrders" type="number" min="0" class="opt-input full">
          </div>
        </div>

        <div class="opt-row">
          <div class="opt-main">
            <div class="opt-title">学期卡售卖</div>
            <div class="opt-desc">
              付费虚拟商品：整学期答题/考试免单、不限门数，并解锁暴力档与优先排队。
              改价后立即生效，无需重启。
            </div>
          </div>
          <select v-model="passEnabled" class="opt-input" :class="{ on: passEnabled }">
            <option :value="true">开售</option>
            <option :value="false">停售</option>
          </select>
        </div>

        <div class="grid-row">
          <div class="field">
            <label>学期卡价格（元）</label>
            <input v-model.number="passPrice" type="number" min="0" step="0.1" class="opt-input full">
          </div>
          <div class="field">
            <label>学期卡有效期（天）</label>
            <input v-model.number="passDays" type="number" min="1" max="3650" class="opt-input full">
          </div>
        </div>

        <p class="settings-hint">
          免费通道的并发额度（同时放几个免费单在跑）在「队列监控」页配置，与付费额度并排。
        </p>

        <button class="btn btn-primary" :disabled="saving" @click="save">
          {{ saving ? '保存中…' : '保存配置' }}
        </button>
      </div>

      <!-- 邀请排行 -->
      <div class="settings-card">
        <h3>邀请排行</h3>
        <p class="settings-hint">
          按有效邀请数排序，可在库里按邀请码反查邀请人（visitors.ref_code）。
        </p>
        <div v-if="stats?.top_inviters?.length" class="rank">
          <div v-for="(t, i) in stats.top_inviters" :key="t.code" class="rank-row">
            <span class="rank-no mono">{{ Number(i) + 1 }}</span>
            <span class="rank-code mono">{{ t.code }}</span>
            <span class="rank-num">邀请 <b class="mono">{{ t.invited }}</b> 人</span>
            <span class="rank-num ok">有效 <b class="mono">{{ t.converted }}</b> 人</span>
          </div>
        </div>
        <div v-else class="empty-sm">还没有邀请记录</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.promo-tab { display: flex; flex-direction: column; gap: 18px; width: 100%; }
.loading { text-align: center; padding: 60px; color: var(--c-text-muted); }

.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}
.kpi {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: 16px;
  box-shadow: var(--shadow-xs);
}
.kpi-val {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--c-text);
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.kpi-label { font-size: 12.5px; color: var(--c-text-secondary); margin-top: 4px; font-weight: 500; }
.kpi-sub { font-size: 11.5px; color: var(--c-text-muted); margin-top: 6px; }

.settings-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 16px;
  padding: 24px 26px;
  box-shadow: var(--shadow-xs);
}
.settings-card h3 {
  font-size: 16px;
  font-weight: 700;
  color: var(--c-text);
  margin-bottom: 4px;
}
.settings-hint { font-size: 12.5px; color: var(--c-text-secondary); margin-bottom: 18px; line-height: 1.6; }

.opt-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid var(--c-border-light);
}
.opt-title { font-size: 13.5px; font-weight: 600; color: var(--c-text); }
.opt-desc { font-size: 12px; color: var(--c-text-muted); margin-top: 3px; line-height: 1.6; }
.opt-main { min-width: 0; }

.opt-input {
  /* main.css 里有一条 `select { width: 100% }`：不写死宽度的话，下拉框会吞掉
     整行，把左侧文案列挤成 0 宽（一个字一行）。这里显式覆盖回按内容宽度。 */
  width: auto;
  min-width: 132px;
  height: 38px;
  padding: 0 12px;
  border: 1.5px solid var(--c-border);
  border-radius: 10px;
  background: var(--c-surface);
  color: var(--c-text);
  font-size: 13px;
  font-weight: 600;
  outline: none;
  flex-shrink: 0;
  transition: border-color .2s ease, color .2s ease;
}
.opt-input:focus { border-color: var(--c-primary); }
.opt-input.on { color: var(--c-success); border-color: var(--c-success); }
.opt-input.full { width: 100%; }

.grid-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 14px;
  margin: 18px 0;
}
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: 12.5px; font-weight: 600; color: var(--c-text-secondary); }

.rank { display: flex; flex-direction: column; }
.rank-row {
  display: grid;
  grid-template-columns: 32px 1fr auto auto;
  gap: 12px;
  align-items: center;
  padding: 10px 6px;
  border-bottom: 1px solid var(--c-border-light);
  font-size: 13px;
}
.rank-row:last-child { border-bottom: none; }
.rank-no { color: var(--c-text-muted); font-weight: 700; }
.rank-code { color: var(--c-text); font-weight: 600; letter-spacing: .04em; }
.rank-num { color: var(--c-text-secondary); font-size: 12.5px; }
.rank-num.ok { color: var(--c-success); }
.empty-sm { text-align: center; padding: 28px; color: var(--c-text-muted); font-size: 13px; }

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px 20px;
  border: none;
  border-radius: 10px;
  font-weight: 600;
  font-size: 13.5px;
  cursor: pointer;
  transition: transform .2s cubic-bezier(.32, .72, .35, 1), background .2s ease, opacity .2s ease;
}
.btn:hover:not(:disabled) { transform: translateY(-1px); }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-primary { background: var(--c-primary); color: #fff; }
.btn-primary:hover:not(:disabled) { background: var(--c-primary-hover); }

@media (max-width: 768px) {
  .opt-row { flex-direction: column; align-items: stretch; gap: 8px; }
  .opt-input { width: 100%; }
}
</style>
<script setup lang="ts">
// 域名监控：学校首页定时抓取 → 平台域名/名称自动纠正（域名一换即时生效）
import { computed, onMounted, ref } from 'vue'
import { api, type DomainMonitorData } from '@/api'
import { usePlatformNames } from '@/composables/usePlatformNames'

const data = ref<DomainMonitorData | null>(null)
const loading = ref(false)
const checking = ref(false)
const errMsg = ref('')
const okMsg = ref('')
const intervalInput = ref(72)
const lastResult = ref<any>(null)

const { reset: resetPlatformNames } = usePlatformNames()

async function load() {
  loading.value = true
  try {
    const r = await api.adminDomain.get()
    if (r.success && r.data) {
      data.value = r.data
      intervalInput.value = r.data.interval_hours
    }
    errMsg.value = ''
  } catch (e: any) {
    errMsg.value = e?.message || '加载失败，请检查后端服务'
  } finally {
    loading.value = false
  }
}

async function checkNow() {
  checking.value = true
  okMsg.value = ''
  errMsg.value = ''
  lastResult.value = null
  try {
    const r = await api.adminDomain.check()
    if (r.success) {
      lastResult.value = r.data
      okMsg.value = r.message || '检测完成'
    } else {
      errMsg.value = r.message || '检测失败'
    }
    // 显示名可能刚被首页文案纠正，清一次缓存让其它页面也用上新名字
    resetPlatformNames()
    await load()
  } catch (e: any) {
    errMsg.value = e?.message || '检测失败'
  } finally {
    checking.value = false
  }
}

async function applyInterval() {
  const h = Math.min(720, Math.max(1, Number(intervalInput.value) || 72))
  intervalInput.value = h
  try {
    const r = await api.adminDomain.setInterval(h)
    if (r.success) { okMsg.value = r.message; errMsg.value = '' } else { errMsg.value = r.message }
    await load()
  } catch (e: any) {
    errMsg.value = e?.message || '保存失败'
  }
}

const platforms = computed(() => data.value?.platforms || [])
const statusOk = computed(() => (data.value?.last_status || '').startsWith('ok'))

function reachText(v: number) {
  return v === 1 ? '可达' : v === 0 ? '不可达' : '未探测'
}
function reachClass(v: number) {
  return v === 1 ? 'dm-ok' : v === 0 ? 'dm-bad' : 'dm-muted'
}
function fmtTs(ms?: number) {
  if (!ms) return '从未检测'
  const d = new Date(ms)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function changeText(c: any) {
  const what = c.kind === 'name' ? '名称更正' : '主域切换'
  return `平台 ${c.website_id} ${what}：${c.old || '（无）'} → ${c.new}`
}

onMounted(load)
</script>

<template>
  <div class="dm-panel">
    <!-- 状态条 -->
    <div class="dm-header">
      <div class="dm-status">
        <span
          class="dm-dot"
          :class="statusOk ? 'dm-dot-live' : 'dm-dot-bad'"
        />
        <span class="dm-status-text">
          上次检测：{{ fmtTs(data?.last_check) }}
        </span>
        <span
          v-if="data?.last_status"
          class="dm-status-sub"
        >{{ data.last_status }}</span>
      </div>
      <div class="dm-actions">
        <button
          class="btn btn-primary btn-sm"
          :disabled="checking"
          @click="checkNow"
        >
          {{ checking ? '检测中…' : '立即检测' }}
        </button>
        <button
          class="btn btn-ghost btn-sm"
          :disabled="loading"
          @click="load"
        >
          {{ loading ? '刷新中' : '刷新' }}
        </button>
      </div>
    </div>

    <!-- 检测间隔 + 首页地址 -->
    <div class="dm-config-row">
      <label class="dm-label">检测间隔</label>
      <input
        v-model.number="intervalInput"
        type="number"
        min="1"
        max="720"
        class="dm-input"
      >
      <span class="dm-unit">小时</span>
      <button
        class="btn btn-primary btn-sm"
        @click="applyInterval"
      >
        应用
      </button>
      <span class="dm-src">监控页：{{ data?.monitor_url || 'https://www.cdcas.edu.cn/' }}</span>
    </div>

    <div
      v-if="errMsg"
      class="dm-alert dm-alert-bad"
    >
      {{ errMsg }}
    </div>
    <div
      v-if="okMsg"
      class="dm-alert dm-alert-ok"
    >
      {{ okMsg }}
    </div>

    <!-- 本次检测结果 -->
    <div
      v-if="lastResult"
      class="dm-result"
    >
      <div class="dm-result-line">
        解析 {{ (lastResult.detected || []).length }} 条平台链接
        <template v-if="lastResult.redirect">
          · 首页跳转 {{ lastResult.redirect }}
        </template>
      </div>
      <ul
        v-if="(lastResult.changes || []).length"
        class="dm-result-list"
      >
        <li
          v-for="(c, i) in lastResult.changes"
          :key="i"
        >
          {{ changeText(c) }}
        </li>
      </ul>
      <div
        v-else
        class="dm-result-line dm-muted"
      >
        域名与名称均无变化
      </div>
      <ul
        v-if="(lastResult.errors || []).length"
        class="dm-result-list dm-result-err"
      >
        <li
          v-for="(t, i) in lastResult.errors"
          :key="i"
        >
          {{ t }}
        </li>
      </ul>
    </div>

    <!-- 平台域名 -->
    <div
      v-if="platforms.length"
      class="table-wrap"
    >
      <table>
        <thead>
          <tr>
            <th>平台</th>
            <th>名称</th>
            <th>域名</th>
            <th>角色</th>
            <th>可达</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="p in platforms"
            :key="p.website_id + p.host"
          >
            <td class="mono">
              #{{ p.website_id }}
            </td>
            <td>{{ p.name }}</td>
            <td>
              <a
                class="dm-link mono"
                :href="p.base_url"
                target="_blank"
                rel="noopener"
              >{{ p.host }}</a>
            </td>
            <td>
              <span
                class="dm-tag"
                :class="p.is_primary ? 'dm-tag-primary' : 'dm-tag-alias'"
              >{{ p.is_primary ? '主域' : '备用' }}</span>
            </td>
            <td>
              <span
                class="dm-tag"
                :class="reachClass(p.reachable)"
              >{{ reachText(p.reachable) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div
      v-else-if="!loading"
      class="empty"
    >
      <p>暂无平台域名，点「立即检测」从学校首页抓取</p>
    </div>
  </div>
</template>

<style scoped>
.dm-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  animation: dm-in .35s cubic-bezier(.32, .72, .35, 1) both;
}
@keyframes dm-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.dm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: 12px 18px;
  box-shadow: var(--shadow-xs);
}
.dm-status { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.dm-dot { width: 9px; height: 9px; border-radius: 50%; }
.dm-dot-live { background: var(--c-success); animation: dm-pulse 1.8s ease-in-out infinite; }
.dm-dot-bad { background: var(--c-danger); }
@keyframes dm-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, .35); }
  50% { box-shadow: 0 0 0 5px rgba(34, 197, 94, 0); }
}
.dm-status-text { font-size: 13px; font-weight: 600; color: var(--c-text); }
.dm-status-sub { font-size: 12px; color: var(--c-text-muted); }
.dm-actions { display: flex; gap: 8px; flex-wrap: wrap; }

.dm-config-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: 12px 18px;
  box-shadow: var(--shadow-xs);
}
.dm-label { font-size: 13px; font-weight: 600; color: var(--c-text-secondary); }
.dm-unit { font-size: 13px; color: var(--c-text-muted); }
.dm-input {
  width: 76px;
  padding: 7px 10px;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  font-size: 13px;
  background: var(--c-bg);
  color: var(--c-text);
  outline: none;
  transition: border-color .2s ease, box-shadow .2s ease, background .2s ease;
}
.dm-input:focus {
  border-color: var(--c-primary);
  background: var(--c-surface);
  box-shadow: 0 0 0 3px rgba(0, 113, 227, .12);
}
.dm-src { font-size: 12px; color: var(--c-text-muted); margin-left: auto; }

.dm-alert {
  border-radius: 12px;
  padding: 10px 14px;
  font-size: 13px;
  border: 1px solid transparent;
}
.dm-alert-bad { background: rgba(239, 68, 68, .08); color: var(--c-danger); border-color: rgba(239, 68, 68, .22); }
.dm-alert-ok { background: rgba(34, 197, 94, .08); color: var(--c-success); border-color: rgba(34, 197, 94, .22); }

.dm-result {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: 12px 18px;
  font-size: 13px;
  color: var(--c-text-secondary);
  box-shadow: var(--shadow-xs);
}
.dm-result-line { line-height: 1.7; }
.dm-result-list { margin: 6px 0 0; padding-left: 18px; }
.dm-result-list li { line-height: 1.8; }
.dm-result-err { color: var(--c-danger); }

.table-wrap {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: var(--shadow-xs);
}
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  text-align: left;
  font-weight: 600;
  color: var(--c-text-muted);
  background: var(--c-bg);
  padding: 11px 14px;
  white-space: nowrap;
}
td {
  padding: 12px 14px;
  border-top: 1px solid var(--c-border);
  color: var(--c-text);
  vertical-align: middle;
}
.dm-link { color: var(--c-primary); text-decoration: none; }
.dm-link:hover { text-decoration: underline; }
.dm-muted { color: var(--c-text-muted); }

.dm-tag {
  display: inline-block;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.dm-tag-primary { background: rgba(0, 113, 227, .1); color: var(--c-primary); }
.dm-tag-alias { background: var(--c-bg); color: var(--c-text-muted); }
.dm-ok { background: rgba(34, 197, 94, .1); color: var(--c-success); }
.dm-bad { background: rgba(239, 68, 68, .1); color: var(--c-danger); }
.dm-muted.dm-tag, .dm-tag.dm-muted { background: var(--c-bg); color: var(--c-text-muted); }

@media (max-width: 768px) {
  .dm-src { margin-left: 0; flex-basis: 100%; }
  .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
}
</style>
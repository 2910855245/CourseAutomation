<script setup lang="ts">
/**
 * 运行日志面板 —— 实时看刷课引擎在干什么（尤其是 studyTime 上报记录）。
 *
 * 数据有两条来源，各有分工：
 * - **实时**：WebSocket `logs` topic 推送（复用 progress 的同一条广播通道，
 *   服务端只向已鉴权连接广播，因此本页无需额外鉴权）。
 * - **历史**：`GET /api/admin/logs`（默认读服务端内存环形缓冲，`source=db`
 *   读 SQLite 持久层，可回看重启前的记录）。
 *
 * 两端的"垃圾回收"是各自独立的：服务端按 TTL + 条数双阈值裁剪（见 logs.rs），
 * 本页只在前端保留最近 MAX_ROWS 条，避免长时间开着页面把 DOM 撑爆。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '@/api'
import { useRealtimeStore } from '@/stores/realtime'

const realtime = useRealtimeStore()

interface LogEntry {
  seq: number
  ts: number
  level: string
  category: string
  order_id?: string
  node_id?: string
  message: string
  detail?: any
}

/** 前端保留上限（前端侧的 GC：超出即丢最旧） */
const MAX_ROWS = 1000
const PAGE_LIMIT = 500

const logs = ref<LogEntry[]>([])
const paused = ref(false)
const autoScroll = ref(true)
const loading = ref(false)
const stats = ref<any>(null)
const expanded = ref<Record<number, boolean>>({})

const filterCategory = ref('report')  // 默认只看上报：这是最常回看的一类
const filterLevel = ref('')
const filterOrder = ref('')
const source = ref<'mem' | 'db'>('mem')

const scrollBox = ref<HTMLElement | null>(null)

const CATEGORIES: { v: string; t: string }[] = [
  { v: '', t: '全部' },
  { v: 'report', t: '上报' },
  { v: 'login', t: '登录' },
  { v: 'order', t: '订单' },
  { v: 'queue', t: '队列' },
  { v: 'exam', t: '考试' },
  { v: 'scan', t: '扫描' },
  { v: 'domain', t: '域名' },
  { v: 'system', t: '系统' },
]
const LEVELS = ['', 'INFO', 'WARN', 'ERROR']

const CAT_LABEL: Record<string, string> = {
  report: '上报', login: '登录', order: '订单', queue: '队列',
  exam: '考试', scan: '扫描', system: '系统', domain: '域名',
}

const connText = computed(() => (realtime.connected ? '实时已连接' : '实时未连接'))

function levelClass(lv: string) {
  const l = (lv || '').toUpperCase()
  if (l === 'ERROR') return 'lg-error'
  if (l === 'WARN') return 'lg-warn'
  if (l === 'DEBUG') return 'lg-debug'
  return 'lg-info'
}

function fmtTime(ts: number) {
  const d = new Date(ts)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function matchesFilter(e: LogEntry) {
  if (filterCategory.value && e.category !== filterCategory.value) return false
  if (filterLevel.value && e.level !== filterLevel.value) return false
  if (filterOrder.value && !(e.order_id || '').includes(filterOrder.value)) return false
  return true
}

function atBottom() {
  const el = scrollBox.value
  if (!el) return
  // +80px 容差：几乎到底就继续跟随，避免必须精确贴底才自动滚动
  el.scrollTop = el.scrollHeight - el.clientHeight - 80
}

function pushLive(e: LogEntry) {
  // 历史模式下不混入实时帧：两种来源的 seq 语义不同，混在一起会乱序
  if (paused.value || source.value !== 'mem' || !matchesFilter(e)) return
  const arr = logs.value
  arr.push(e)
  if (arr.length > MAX_ROWS) arr.splice(0, arr.length - MAX_ROWS)
  if (autoScroll.value) {
    // 等 DOM 更新完再滚，否则滚的是旧高度
    requestAnimationFrame(atBottom)
  }
}

async function load() {
  loading.value = true
  try {
    const r = await api.adminLogs.list({
      category: filterCategory.value,
      level: filterLevel.value,
      order_id: filterOrder.value,
      limit: PAGE_LIMIT,
      source: source.value,
    })
    const items: LogEntry[] = (r.data?.items || []).slice().reverse() // 后端按新→旧返回
    logs.value = items.slice(-MAX_ROWS)
    if (source.value === 'mem' && r.data?.stats) stats.value = r.data.stats
    await refreshStats()
    if (autoScroll.value) requestAnimationFrame(atBottom)
  } catch (e: any) {
    logs.value = []
    window.alert(e?.message || '加载日志失败')
  } finally {
    loading.value = false
  }
}

async function refreshStats() {
  try {
    const r = await api.adminLogs.stats()
    stats.value = r.data
  } catch { /* 统计失败不影响看日志 */ }
}

async function clearMem() {
  if (!window.confirm('清空服务端「内存日志缓冲」？（持久层由 GC 按 TTL/条数自动裁剪）')) return
  try {
    await api.adminLogs.clear()
    logs.value = []
    await refreshStats()
  } catch (e: any) {
    window.alert(e?.message || '清空失败')
  }
}

function setSource(s: 'mem' | 'db') {
  if (source.value === s) return
  source.value = s
  load()
}

function toggleDetail(i: number) {
  expanded.value[i] = !expanded.value[i]
}

let unsubscribe: (() => void) | null = null

onMounted(() => {
  load()
  unsubscribe = realtime.subscribe(['logs'], (msg) => {
    if (msg.type !== 'log') return
    const data = msg.data
    // 广播帧的 data 是 LogEntry 本体（见 logs.rs emit 的 envelope）
    if (data && typeof data.message === 'string') pushLive(data as LogEntry)
    else if (data && typeof data.data === 'object') pushLive(data.data as LogEntry)
  })
})

onBeforeUnmount(() => {
  unsubscribe?.()
  unsubscribe = null
})
</script>

<template>
  <div class="logs-panel">
    <!-- 顶部：状态 + 操作 -->
    <div class="logs-header">
      <div class="logs-status">
        <span
          class="ls-dot"
          :class="realtime.connected ? 'ls-on' : 'ls-off'"
        />
        <span class="ls-text">{{ connText }}</span>
        <span
          v-if="paused"
          class="ls-paused"
        >已暂停接收</span>
      </div>
      <div class="logs-actions">
        <button
          class="btn btn-ghost btn-sm"
          @click="paused = !paused"
        >
          {{ paused ? '继续' : '暂停' }}
        </button>
        <label
          class="ls-check"
          title="新日志到达时自动滚到底部"
        >
          <input
            v-model="autoScroll"
            type="checkbox"
          > 自动滚动
        </label>
        <button
          class="btn btn-ghost btn-sm"
          :disabled="loading"
          @click="load"
        >
          {{ loading ? '刷新中' : '刷新' }}
        </button>
        <button
          class="btn btn-ghost btn-sm"
          @click="clearMem"
        >
          清空内存
        </button>
      </div>
    </div>

    <!-- GC / 容量统计 -->
    <div
      v-if="stats"
      class="logs-stats"
    >
      <span class="stat-pill">内存 {{ stats.mem_count }}/{{ stats.mem_max }}</span>
      <span class="stat-pill">累计 {{ stats.total }}</span>
      <span class="stat-pill">已淘汰 {{ stats.evicted }}</span>
      <span
        class="stat-pill"
        :class="{ 'stat-warn': stats.dropped > 0 }"
      >落库丢弃 {{ stats.dropped }}</span>
      <span
        v-if="stats.db_rows !== undefined"
        class="stat-pill"
      >持久层 {{ stats.db_rows }}/{{ stats.db_max_rows }}</span>
      <span class="stat-pill stat-muted">GC：内存 {{ stats.mem_ttl_hours }}h · 库 {{ stats.db_ttl_days }}d</span>
    </div>

    <!-- 筛选 -->
    <div class="logs-filters">
      <div class="lf-chips">
        <button
          v-for="c in CATEGORIES"
          :key="c.v"
          class="lf-chip"
          :class="{ 'lf-chip-on': filterCategory === c.v }"
          @click="filterCategory = c.v; load()"
        >
          {{ c.t }}
        </button>
      </div>
      <select
        v-model="filterLevel"
        class="lf-select"
        @change="load()"
      >
        <option
          v-for="lv in LEVELS"
          :key="lv"
          :value="lv"
        >
          {{ lv || '全部级别' }}
        </option>
      </select>
      <input
        v-model.trim="filterOrder"
        class="lf-input"
        placeholder="订单号"
        @keyup.enter="load()"
      >
      <div class="lf-source">
        <button
          class="lf-chip"
          :class="{ 'lf-chip-on': source === 'mem' }"
          @click="setSource('mem')"
        >
          内存
        </button>
        <button
          class="lf-chip"
          :class="{ 'lf-chip-on': source === 'db' }"
          @click="setSource('db')"
        >
          持久层
        </button>
      </div>
    </div>

    <!-- 日志列表 -->
    <div
      ref="scrollBox"
      class="logs-list"
    >
      <div
        v-if="!logs.length"
        class="logs-empty"
      >
        {{ loading ? '加载中…' : '暂无日志' }}
      </div>
      <div
        v-for="(e, i) in logs"
        :key="`${e.ts}-${e.seq}-${i}`"
        class="log-row"
        :class="levelClass(e.level)"
        @click="toggleDetail(i)"
      >
        <span class="lr-time">{{ fmtTime(e.ts) }}</span>
        <span
          class="lr-level"
          :class="levelClass(e.level)"
        >{{ e.level }}</span>
        <span class="lr-cat">{{ CAT_LABEL[e.category] || e.category }}</span>
        <span
          v-if="e.order_id"
          class="lr-order"
          :title="e.order_id"
        >{{ e.order_id }}</span>
        <span class="lr-msg">{{ e.message }}</span>
        <pre
          v-if="expanded[i] && e.detail"
          class="lr-detail"
        >{{ JSON.stringify(e.detail, null, 2) }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.logs-panel { display: flex; flex-direction: column; gap: 12px; min-height: 0; }

.logs-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; flex-wrap: wrap;
}
.logs-status { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--c-text-secondary); }
.ls-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--c-text-muted); }
.ls-dot.ls-on { background: var(--c-success); box-shadow: 0 0 0 3px var(--c-success-bg); }
.ls-dot.ls-off { background: var(--c-danger); box-shadow: 0 0 0 3px var(--c-danger-bg); }
.ls-paused { color: var(--c-warning); background: var(--c-warning-bg); padding: 1px 8px; border-radius: 999px; font-size: 12px; }
.logs-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ls-check { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; color: var(--c-text-secondary); cursor: pointer; }

.logs-stats { display: flex; gap: 8px; flex-wrap: wrap; }
.stat-pill {
  font-size: 12px; padding: 3px 10px; border-radius: 999px;
  background: var(--c-bg-soft); color: var(--c-text-secondary);
  border: 1px solid var(--c-border-light);
}
.stat-pill.stat-muted { color: var(--c-text-muted); }
.stat-pill.stat-warn { color: var(--c-danger); background: var(--c-danger-bg); border-color: transparent; }

.logs-filters { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.lf-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.lf-chip {
  font-size: 13px; padding: 4px 12px; border-radius: 999px; cursor: pointer;
  background: var(--c-surface); color: var(--c-text-secondary);
  border: 1px solid var(--c-border); transition: all .15s;
}
.lf-chip:hover { border-color: var(--c-primary); color: var(--c-primary); }
.lf-chip-on { background: var(--c-primary-bg); color: var(--c-primary); border-color: var(--c-primary-ring); font-weight: 600; }
.lf-select, .lf-input {
  height: 30px; padding: 0 10px; font-size: 13px; border-radius: 8px;
  background: var(--c-surface); color: var(--c-text);
  border: 1px solid var(--c-border); outline: none;
}
.lf-input { width: 160px; }
.lf-select:focus, .lf-input:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px var(--c-primary-ring); }
.lf-source { display: flex; gap: 6px; }

.logs-list {
  flex: 1; min-height: 320px; max-height: calc(100vh - 340px); overflow-y: auto;
  background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: 14px; padding: 6px 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.logs-empty { padding: 40px; text-align: center; color: var(--c-text-muted); font-size: 13px; }
.log-row {
  display: grid; grid-template-columns: 64px 52px 40px auto 1fr;
  align-items: baseline; gap: 8px;
  padding: 4px 12px; font-size: 12.5px; line-height: 1.6;
  border-left: 2px solid transparent; cursor: pointer;
}
.log-row:hover { background: var(--c-bg-soft); }
.log-row.lg-error { border-left-color: var(--c-danger); background: var(--c-danger-bg); }
.log-row.lg-warn { border-left-color: var(--c-warning); }
.lr-time { color: var(--c-text-muted); }
.lr-level { font-weight: 700; font-size: 11px; }
.lg-info .lr-level, .lr-level.lg-info { color: var(--c-info); }
.lg-warn .lr-level, .lr-level.lg-warn { color: var(--c-warning); }
.lg-error .lr-level, .lr-level.lg-error { color: var(--c-danger); }
.lg-debug .lr-level, .lr-level.lg-debug { color: var(--c-text-muted); }
.lr-cat {
  font-size: 11px; text-align: center; border-radius: 6px;
  background: var(--c-bg-soft); color: var(--c-text-secondary); padding: 1px 0;
}
.lr-order { color: var(--c-primary); }
.lr-msg { color: var(--c-text); word-break: break-word; }
.lr-detail {
  grid-column: 1 / -1; margin: 4px 0 4px 0; padding: 8px 10px;
  background: var(--c-bg-soft); border-radius: 8px;
  font-size: 12px; color: var(--c-text-secondary); white-space: pre-wrap; word-break: break-all;
}
</style>
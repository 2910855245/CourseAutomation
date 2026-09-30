<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { useAdminStore } from '@/stores/admin'
import { useAppStore } from '@/stores/app'
import { chartPalette } from '@/theme/charts'

const appStore = useAppStore()
const adminStore = useAdminStore()
const { currentRole } = adminStore.state().auth
const { getPlatformName } = adminStore.state().ui
const { dash, dashError, fmtMoney, fmtShortDate, loadDashboard, loadingDash, orderStatusClass, orderStatusLabel, totalPlatformOrders } = adminStore.state().dashboard
const { platformColors, taskTypeNames } = adminStore.state().sysConfig

// v-for 的索引在 dash 为宽松类型时不被推断为 number，这里统一收敛为数字下标
const platColor = (i: unknown): string => platformColors[Number(i)] || '#6b7280'

const palette = computed(() => chartPalette(appStore.isDark))

function tooltipStyle(p: ReturnType<typeof chartPalette>) {
  return {
    trigger: 'axis' as const,
    backgroundColor: p.tooltipBg,
    borderColor: p.tooltipBorder,
    textStyle: { color: p.text, fontSize: 12 },
  }
}

/** 环比徽标：昨日为 0 时后端给 null，此时不显示（而不是显示 +100%） */
function changeText(v: number | null | undefined): string {
  if (v === null || v === undefined) return ''
  const pct = v * 100
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(0)}%`
}
function changeClass(v: number | null | undefined): string {
  if (!v) return 'flat'
  return v > 0 ? 'up' : 'down'
}

/** 大数字缩写：1234 → 1.2k，避免 KPI 卡片被超长数字撑破 */
function compact(n: number | undefined): string {
  const v = n || 0
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M'
  if (v >= 10_000) return (v / 1000).toFixed(1) + 'k'
  return String(v)
}

const alertCount = computed(() => (dash.value?.alerts || []).length)
/** 危险级信号排在前面，运营一眼先看到需要立刻处理的 */
const sortedAlerts = computed(() =>
  [...(dash.value?.alerts || [])].sort((a: any, b: any) => {
    const rank: Record<string, number> = { danger: 0, warn: 1, info: 2 }
    return (rank[a.level] ?? 3) - (rank[b.level] ?? 3)
  }),
)

/** 通道占用率：分子分母必须来自同一通道（付费池与免费额度上限不同，混算会虚高） */
function lanePct(active: number | undefined, max: number | undefined): number {
  if (!max) return 0
  return Math.min(100, Math.round(((active || 0) / max) * 100))
}

/** 近 7 天：收入折线（左轴）+ 订单柱（右轴），图例由面板头部 HTML 承担 */
const trendOption = computed(() => {
  const p = palette.value
  const days = (dash.value?.recent_7_days || []) as { date: string; orders: number; revenue: number; failed: number }[]
  return {
    grid: { left: 4, right: 4, top: 16, bottom: 0, containLabel: true },
    tooltip: tooltipStyle(p),
    legend: { show: false },
    xAxis: {
      type: 'category',
      data: days.map(d => d.date),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: p.split } },
      axisLabel: { color: p.axis, fontSize: 11 },
    },
    yAxis: [
      {
        type: 'value',
        splitLine: { lineStyle: { color: p.split } },
        axisLabel: { color: p.axis, fontSize: 11 },
      },
      {
        type: 'value',
        splitLine: { show: false },
        axisLabel: { color: p.axis, fontSize: 11 },
      },
    ],
    series: [
      {
        name: '收入',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        data: days.map(d => d.revenue),
        itemStyle: { color: p.primary },
        lineStyle: { width: 2.5, color: p.primary },
        areaStyle: { color: p.primary, opacity: 0.10 },
      },
      {
        name: '订单',
        type: 'bar',
        yAxisIndex: 1,
        barWidth: 12,
        data: days.map(d => d.orders),
        itemStyle: { color: p.info, opacity: 0.75, borderRadius: [4, 4, 0, 0] },
      },
    ],
  }
})

/** 订单状态分布：横向条形，颜色沿用状态语义（ok/bad/warn/primary/muted） */
const statusOption = computed(() => {
  const p = palette.value
  const colorOf: Record<string, string> = {
    ok: p.success, bad: p.danger, warn: p.warning, primary: p.primary, muted: p.axis,
  }
  const rows = ((dash.value?.status_distribution || []) as { status: string; count: number }[])
    .map(sd => ({
      label: orderStatusLabel[sd.status] || sd.status,
      count: sd.count,
      color: colorOf[orderStatusClass[sd.status] || 'primary'] || p.primary,
    }))
  return {
    grid: { left: 4, right: 16, top: 8, bottom: 0, containLabel: true },
    tooltip: tooltipStyle(p),
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: p.split } },
      axisLabel: { color: p.axis, fontSize: 11 },
    },
    yAxis: {
      type: 'category',
      data: rows.map(r => r.label),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: p.axis, fontSize: 12 },
    },
    series: [{
      type: 'bar',
      barWidth: 10,
      data: rows.map(r => ({ value: r.count, itemStyle: { color: r.color, borderRadius: [0, 5, 5, 0] } })),
    }],
  }
})

/** 状态条数不固定，高度跟着行数走，避免出现大片留白或挤压 */
const statusChartHeight = computed(() =>
  `${Math.max(120, ((dash.value?.status_distribution?.length || 0) * 30) + 24)}px`,
)

/** 场景名 → 中文（AI 用量按场景拆分时展示） */
const sceneNames: Record<string, string> = {
  exam: '考试答题', quiz: '测验答题', discussion: '讨论生成',
  captcha_vision: '验证码兜底', selftest: '连通测试',
}
</script>

<template>
  <div>
    <div
      v-if="dash"
      class="overview-content"
    >
      <!-- 异常信号：只有真有事时才出现，避免常驻噪声 -->
      <div
        v-if="alertCount"
        class="alert-strip"
      >
        <div
          v-for="(a, i) in sortedAlerts"
          :key="i"
          :class="['alert-item', a.level]"
        >
          <span class="alert-dot" />
          <span class="alert-title">{{ a.title }}</span>
          <span class="alert-detail">{{ a.detail }}</span>
        </div>
      </div>

      <div class="kpi-row">
        <div class="kpi-card">
          <div class="kpi-icon rev">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><line
              x1="12"
              y1="1"
              x2="12"
              y2="23"
            /><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ fmtMoney(dash.revenue.today) }}
            </div>
            <div class="kpi-label">
              今日实收
            </div>
          </div>
          <div class="kpi-sub">
            <span :class="['chg', changeClass(dash.revenue.today_change)]">
              {{ changeText(dash.revenue.today_change) || '环比昨日 —' }}
            </span>
            <span>本周 {{ fmtMoney(dash.revenue.week) }}</span>
            <span>累计 {{ fmtMoney(dash.revenue.total) }}</span>
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-icon ord">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" /><line
              x1="16"
              y1="13"
              x2="8"
              y2="13"
            /><line
              x1="16"
              y1="17"
              x2="8"
              y2="17"
            /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ dash.orders.today }}
            </div>
            <div class="kpi-label">
              今日订单
            </div>
          </div>
          <div class="kpi-sub">
            <span :class="['chg', changeClass(dash.orders.today_change)]">
              {{ changeText(dash.orders.today_change) || '环比昨日 —' }}
            </span>
            <span>本周 {{ dash.orders.week }} 单</span>
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-icon rate">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ (dash.orders.completion_rate * 100).toFixed(1) }}%
            </div>
            <div class="kpi-label">
              完成率
            </div>
          </div>
          <div class="kpi-sub">
            <span>已完成 {{ dash.orders.completed }}</span>
            <span v-if="dash.orders.avg_delivery_hours > 0">均 {{ dash.orders.avg_delivery_hours }}h</span>
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-icon agt">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><circle
              cx="12"
              cy="12"
              r="10"
            /><line
              x1="12"
              y1="8"
              x2="12"
              y2="12"
            /><line
              x1="12"
              y1="16"
              x2="12.01"
              y2="16"
            /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ dash.orders.pending }}
            </div>
            <div class="kpi-label">
              待处理
            </div>
          </div>
          <div class="kpi-sub">
            <span>执行中 {{ dash.orders.running }}</span>
            <span
              v-if="dash.orders.stuck || dash.orders.long_running"
              class="chg down"
            >卡单 {{ dash.orders.stuck + dash.orders.long_running }}</span>
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-icon ai">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><rect
              x="4"
              y="4"
              width="16"
              height="16"
              rx="3"
            /><path d="M9 9h6v6H9z" /><path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2" /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ fmtMoney(dash.ai.today.cost) }}
            </div>
            <div class="kpi-label">
              AI 今日成本
            </div>
          </div>
          <div class="kpi-sub">
            <span>{{ dash.ai.today.calls }} 次调用</span>
            <span v-if="dash.ai.today.calls">命中 {{ (dash.ai.today.cache_hit_rate * 100).toFixed(0) }}%</span>
          </div>
        </div>

        <div
          v-if="dash.orders.failed || dash.revenue.receivable > 0"
          class="kpi-card"
        >
          <div
            class="kpi-icon"
            :class="dash.orders.failed ? 'ord' : 'rate'"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ dash.orders.failed }}
            </div>
            <div class="kpi-label">
              失败订单
            </div>
          </div>
          <div class="kpi-sub">
            <span>待收款 {{ fmtMoney(dash.revenue.receivable) }}</span>
          </div>
        </div>
      </div>

      <div class="panel-row">
        <div class="panel panel-wide">
          <div class="panel-head">
            <h3>近7天收入与订单趋势</h3>
            <div class="legend-row">
              <span class="legend"><b class="ldot ldot-rev" />收入</span>
              <span class="legend"><b class="ldot ldot-ord" />订单</span>
            </div>
          </div>
          <v-chart
            class="chart"
            :option="trendOption"
            autoresize
          />
        </div>
      </div>

      <div class="panel-row">
        <div class="panel">
          <div class="panel-head">
            <h3>队列健康</h3>
            <span :class="['status-tag', dash.queue.paused ? 'bad' : dash.queue.enabled ? 'ok' : 'warn']">
              {{ dash.queue.paused ? '已暂停' : dash.queue.enabled ? '运行中' : '调度器停用' }}
            </span>
          </div>
          <div class="q-lanes">
            <div class="q-lane">
              <div class="q-workers-head">
                <span>付费通道</span>
                <span class="mono">{{ dash.queue.paid?.active_workers || 0 }} / {{ dash.queue.paid?.max_workers || '—' }}</span>
              </div>
              <div class="q-bar-bg">
                <div
                  class="q-bar-fill"
                  :style="{ width: lanePct(dash.queue.paid?.active_workers, dash.queue.paid?.max_workers) + '%' }"
                />
              </div>
            </div>
            <div class="q-lane">
              <div class="q-workers-head">
                <span>免费通道</span>
                <span class="mono">{{ dash.queue.free?.active_workers || 0 }} / {{ dash.queue.free?.max_workers || '—' }}</span>
              </div>
              <div class="q-bar-bg">
                <div
                  class="q-bar-fill free"
                  :style="{ width: lanePct(dash.queue.free?.active_workers, dash.queue.free?.max_workers) + '%' }"
                />
              </div>
            </div>
          </div>
          <div class="q-grid">
            <div class="q-cell">
              <div class="q-val mono">{{ dash.queue.pending + dash.queue.retrying }}</div>
              <div class="q-label">排队中</div>
            </div>
            <div class="q-cell">
              <div class="q-val mono">{{ dash.queue.running }}</div>
              <div class="q-label">执行中</div>
            </div>
            <div class="q-cell">
              <div class="q-val mono">{{ dash.queue.completed }}</div>
              <div class="q-label">已完成</div>
            </div>
            <div class="q-cell">
              <div
                class="q-val mono"
                :class="{ bad: dash.queue.failed > 0 }"
              >
                {{ dash.queue.failed }}
              </div>
              <div class="q-label">失败</div>
            </div>
          </div>
          <div
            v-if="dash.queue.backlog_minutes > 0"
            class="q-foot"
          >
            最早排队任务已等待 {{ dash.queue.backlog_minutes }} 分钟
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h3>AI 用量</h3>
            <span class="panel-note">近7天 {{ fmtMoney((dash.recent_7_days || []).reduce((s: number, d: any) => s + (d.ai_cost || 0), 0)) }}</span>
          </div>
          <div class="ai-total">
            <div class="ai-total-main">
              <div class="ai-total-val mono">
                {{ compact(dash.ai.total.prompt_tokens + dash.ai.total.completion_tokens) }}
              </div>
              <div class="ai-total-label">
                累计 tokens
              </div>
            </div>
            <div class="ai-total-side">
              <div>累计调用 <b class="mono">{{ compact(dash.ai.total.calls) }}</b></div>
              <div>累计成本 <b class="mono">{{ fmtMoney(dash.ai.total.cost) }}</b></div>
              <div v-if="dash.ai.today.calls">
                今日成功率 <b class="mono">{{ (dash.ai.today.success_rate * 100).toFixed(0) }}%</b>
              </div>
            </div>
          </div>
          <div
            v-if="dash.ai.by_scene.length"
            class="ai-scenes"
          >
            <div
              v-for="s in dash.ai.by_scene"
              :key="s.scene"
              class="ai-scene"
            >
              <span class="ai-scene-name">{{ sceneNames[s.scene] || s.scene }}</span>
              <span class="ai-scene-calls mono">{{ s.calls }} 次</span>
              <span class="ai-scene-cost mono">{{ fmtMoney(s.cost) }}</span>
            </div>
          </div>
          <div
            v-else
            class="empty-sm"
          >
            暂无 AI 调用记录
          </div>
        </div>
      </div>

      <div class="panel-row">
        <div class="panel panel-wide">
          <div class="panel-head">
            <h3>订单状态分布</h3>
          </div>
          <v-chart
            class="chart-slim"
            :style="{ height: statusChartHeight }"
            :option="statusOption"
            autoresize
          />
        </div>
      </div>

      <div class="panel-row">
        <div class="panel">
          <div class="panel-head">
            <h3>平台分布</h3>
          </div>
          <div
            v-if="dash.platform_distribution.length"
            class="plat-list"
          >
            <div
              v-for="(p, i) in dash.platform_distribution"
              :key="p.website_id"
              class="plat-item"
            >
              <div class="plat-left">
                <span
                  class="plat-dot"
                  :style="{ background: platColor(i) }"
                />
                <span class="plat-name">{{ getPlatformName(p.website_id) }}</span>
              </div>
              <div class="plat-right">
                <div class="plat-bar-bg">
                  <div
                    class="plat-bar-fill"
                    :style="{ width: (p.count / totalPlatformOrders * 100) + '%', background: platColor(i) }"
                  />
                </div>
                <span class="plat-cnt mono">{{ p.count }}单</span>
                <span class="plat-rev mono">{{ fmtMoney(p.revenue) }}</span>
              </div>
            </div>
          </div>
          <div
            v-else
            class="empty-sm"
          >
            暂无数据
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h3>任务类型分布</h3>
          </div>
          <div
            v-if="dash.task_type_distribution.length"
            class="type-cards"
          >
            <div
              v-for="td in dash.task_type_distribution"
              :key="td.task_type"
              class="type-card"
            >
              <div class="tc-icon">
                {{ taskTypeNames[td.task_type] || td.task_type }}
              </div>
              <div class="tc-count mono">
                {{ td.count }}单
              </div>
              <div class="tc-rev mono">
                {{ fmtMoney(td.revenue) }}
              </div>
            </div>
          </div>
          <div
            v-else
            class="empty-sm"
          >
            暂无数据
          </div>
        </div>
      </div>

      <div class="panel-row">
        <div class="panel panel-wide-sm">
          <div class="panel-head">
            <h3>最近订单</h3>
          </div>
          <div
            v-if="dash.recent_orders.length"
            class="mini-table"
          >
            <div class="mt-row mt-head">
              <span class="mt-col">用户</span><span class="mt-col">平台</span><span class="mt-col">类型</span>
              <span class="mt-col">金额</span><span class="mt-col">状态</span><span class="mt-col">时间</span>
            </div>
            <div
              v-for="o in dash.recent_orders"
              :key="o.order_id"
              class="mt-row"
            >
              <span class="mt-col mt-uname">{{ o.username }}</span>
              <span class="mt-col">{{ getPlatformName(o.website_id) }}</span>
              <span class="mt-col">{{ taskTypeNames[o.task_type] || o.task_type }}</span>
              <span class="mt-col mt-money">
                {{ fmtMoney(o.price) }}
                <span
                  v-if="!o.paid"
                  class="mt-unpaid"
                >未收</span>
              </span>
              <span class="mt-col"><span :class="['status-tag', orderStatusClass[o.status]]">{{ orderStatusLabel[o.status] || o.status }}</span></span>
              <span class="mt-col mt-date">{{ fmtShortDate(o.created_at) }}</span>
            </div>
          </div>
          <div
            v-else
            class="empty-sm"
          >
            暂无订单
          </div>
        </div>
      </div>
    </div>
    <div
      v-else-if="dashError"
      class="empty"
    >
      <p class="empty-err-title">
        数据加载失败
      </p>
      <p class="empty-err-msg">
        {{ dashError }}
      </p>
      <button
        class="btn btn-primary btn-sm"
        @click="() => loadDashboard(currentRole)"
      >
        重试
      </button>
    </div>
    <div
      v-else-if="!loadingDash"
      class="empty"
    >
      <p>点击刷新加载数据</p>
    </div>
  </div>
</template>

<style scoped>
.overview-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ==================== 异常信号 ==================== */
.alert-strip {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.alert-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  border-radius: 12px;
  font-size: 12.5px;
  line-height: 1.5;
  animation: ov-in .35s cubic-bezier(.32, .72, .35, 1) both;
}
.alert-item.danger { background: var(--c-danger-bg); color: var(--c-danger); }
.alert-item.warn { background: var(--c-warning-bg); color: var(--c-warning); }
.alert-item.info { background: var(--c-bg); color: var(--c-text-secondary); }
.alert-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}
.alert-title { font-weight: 700; flex-shrink: 0; }
.alert-detail {
  color: var(--c-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ==================== KPI 卡片 ==================== */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
}
.kpi-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 16px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  box-shadow: var(--shadow-xs);
  transition: transform .25s cubic-bezier(.32, .72, .35, 1), box-shadow .25s cubic-bezier(.32, .72, .35, 1);
  animation: ov-in .35s cubic-bezier(.32, .72, .35, 1) both;
}
.kpi-card:nth-child(2) { animation-delay: .04s; }
.kpi-card:nth-child(3) { animation-delay: .08s; }
.kpi-card:nth-child(4) { animation-delay: .12s; }
.kpi-card:nth-child(5) { animation-delay: .16s; }
.kpi-card:nth-child(6) { animation-delay: .20s; }
.kpi-card:nth-child(7) { animation-delay: .24s; }
.kpi-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}
@keyframes ov-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
.kpi-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.kpi-icon.rev { background: var(--c-danger-bg); color: var(--c-danger); }
.kpi-icon.ord { background: var(--c-primary-bg); color: var(--c-primary); }
.kpi-icon.rate { background: var(--c-warning-bg); color: var(--c-warning); }
.kpi-icon.agt { background: var(--c-info-bg); color: var(--c-info); }
.kpi-icon.ai { background: var(--c-success-bg); color: var(--c-success); }
.kpi-body { display: flex; flex-direction: column; gap: 3px; }
.kpi-val {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--c-text);
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.kpi-label { font-size: 12.5px; color: var(--c-text-secondary); font-weight: 500; }
.kpi-sub {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 4px 8px;
  font-size: 11.5px;
  color: var(--c-text-muted);
  border-top: 1px solid var(--c-border);
  padding-top: 8px;
}
/* 环比徽标：涨/跌/持平用同一个色族，不抢主数字的注意力 */
.chg { font-weight: 600; }
.chg.up { color: var(--c-success); }
.chg.down { color: var(--c-danger); }
.chg.flat { color: var(--c-text-muted); }

/* ==================== 面板 ==================== */
.panel-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.panel {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 16px;
  padding: 22px;
  box-shadow: var(--shadow-xs);
  animation: ov-in .35s cubic-bezier(.32, .72, .35, 1) .1s both;
  transition: box-shadow .25s cubic-bezier(.32, .72, .35, 1);
}
.panel:hover { box-shadow: var(--shadow-sm); }
.panel-wide { grid-column: span 2; }
.panel-wide-sm { grid-column: span 1; }
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}
.panel-head h3 {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--c-text);
}
.panel-note { font-size: 11.5px; color: var(--c-text-muted); }
.legend-row { display: flex; gap: 14px; }
.legend {
  font-size: 11.5px;
  color: var(--c-text-secondary);
  display: flex;
  align-items: center;
  gap: 6px;
}
.ldot { width: 8px; height: 8px; border-radius: 3px; display: inline-block; }
.ldot-rev { background: var(--c-primary); }
.ldot-ord { background: var(--c-info); }

/* ==================== 图表（ECharts） ==================== */
.chart {
  width: 100%;
  height: 200px;
}
.chart-slim { width: 100%; }

/* ==================== 队列健康 ==================== */
.q-lanes { display: flex; flex-direction: column; gap: 14px; margin-bottom: 18px; }
.q-lane { display: flex; flex-direction: column; gap: 6px; }
.q-workers-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--c-text-secondary);
}
.mono { font-variant-numeric: tabular-nums; }
.q-bar-bg {
  height: 8px;
  background: var(--c-bg);
  border-radius: 999px;
  overflow: hidden;
}
.q-bar-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--c-primary);
  transition: width .4s cubic-bezier(.32, .72, .35, 1);
}
.q-bar-fill.free { background: var(--c-success); }
.q-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.q-cell {
  background: var(--c-bg);
  border-radius: 12px;
  padding: 12px;
  text-align: center;
}
.q-val {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--c-text);
  line-height: 1.2;
}
.q-val.bad { color: var(--c-danger); }
.q-label { font-size: 11.5px; color: var(--c-text-muted); margin-top: 2px; }
.q-foot {
  margin-top: 14px;
  font-size: 12px;
  color: var(--c-warning);
}

/* ==================== AI 用量 ==================== */
.ai-total {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--c-border);
}
.ai-total-val {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--c-text);
  line-height: 1.1;
}
.ai-total-label { font-size: 12px; color: var(--c-text-secondary); margin-top: 2px; }
.ai-total-side {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--c-text-secondary);
  text-align: right;
}
.ai-total-side b { color: var(--c-text); }
.ai-scenes {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 12px;
}
.ai-scene {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 12px;
  align-items: center;
  padding: 8px 6px;
  border-radius: 8px;
  font-size: 12.5px;
  transition: background .2s ease;
}
.ai-scene:hover { background: var(--c-bg); }
.ai-scene-name { color: var(--c-text); }
.ai-scene-calls { color: var(--c-text-muted); font-size: 11.5px; }
.ai-scene-cost { color: var(--c-text-secondary); font-size: 11.5px; min-width: 62px; text-align: right; }

/* ==================== 平台分布 ==================== */
.plat-list { display: flex; flex-direction: column; gap: 12px; }
.plat-item { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.plat-left { display: flex; align-items: center; gap: 8px; min-width: 100px; }
.plat-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.plat-name { font-size: 12.5px; color: var(--c-text); font-weight: 500; white-space: nowrap; }
.plat-right { display: flex; align-items: center; gap: 10px; flex: 1; }
.plat-bar-bg {
  flex: 1;
  height: 6px;
  background: var(--c-bg);
  border-radius: 999px;
  overflow: hidden;
  max-width: 130px;
}
.plat-bar-fill { height: 100%; border-radius: 999px; transition: width .35s cubic-bezier(.32, .72, .35, 1); }
.plat-cnt { font-size: 11.5px; color: var(--c-text-secondary); white-space: nowrap; min-width: 30px; font-variant-numeric: tabular-nums; }
.plat-rev { font-size: 11.5px; color: var(--c-text-muted); white-space: nowrap; font-variant-numeric: tabular-nums; }

/* ==================== 任务类型卡片 ==================== */
.type-cards { display: flex; gap: 10px; flex-wrap: wrap; }
.type-card {
  flex: 1;
  min-width: 120px;
  border: 1px solid var(--c-border);
  border-radius: 12px;
  padding: 14px 16px;
  transition: transform .25s cubic-bezier(.32, .72, .35, 1), box-shadow .25s cubic-bezier(.32, .72, .35, 1);
}
.type-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}
.tc-icon { font-size: 13px; font-weight: 600; color: var(--c-primary); margin-bottom: 4px; }
.tc-count { font-size: 22px; font-weight: 700; letter-spacing: -0.02em; color: var(--c-text); font-variant-numeric: tabular-nums; }
.tc-rev { font-size: 11.5px; color: var(--c-text-muted); margin-top: 2px; }

/* ==================== 最近订单（极简表格） ==================== */
.mini-table { display: flex; flex-direction: column; }
.mt-row {
  display: grid;
  grid-template-columns: 1fr 1fr .7fr .9fr .9fr 1.2fr;
  gap: 6px;
  padding: 10px 6px;
  border-bottom: 1px solid var(--c-border);
  align-items: center;
  font-size: 13px;
  border-radius: 8px;
  transition: background .2s ease;
}
.mt-row:not(.mt-head):hover { background: var(--c-bg); }
.mt-row:last-child { border-bottom: none; }
.mt-head {
  font-size: 11px;
  font-weight: 600;
  color: var(--c-text-muted);
  text-transform: uppercase;
  letter-spacing: .05em;
  border-bottom: 1px solid var(--c-border);
}
.mt-uname { font-weight: 600; color: var(--c-text); }
.mt-money { font-weight: 600; font-variant-numeric: tabular-nums; }
.mt-unpaid {
  margin-left: 6px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--c-warning);
}
.mt-date { color: var(--c-text-muted); font-size: 11.5px; }

/* ==================== 状态标签 ==================== */
.status-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.7;
  white-space: nowrap;
}
.status-tag.ok { background: var(--c-success-bg); color: var(--c-success); }
.status-tag.ok.verified { border: 1.5px solid var(--c-success); }
.status-tag.warn { background: var(--c-warning-bg); color: var(--c-warning); }
.status-tag.bad { background: var(--c-danger-bg); color: var(--c-danger); }
.status-tag.primary { background: var(--c-primary-bg); color: var(--c-primary); }
.status-tag.muted { background: var(--c-bg); color: var(--c-text-muted); }

/* ==================== 空状态 / 按钮 ==================== */
.empty { text-align: center; padding: 60px 20px; color: var(--c-text-muted); }
.empty p { margin-bottom: 16px; }
.empty-sm { text-align: center; padding: 32px; color: var(--c-text-muted); font-size: 13px; }
.empty-err-title { color: var(--c-danger); font-weight: 600; margin-bottom: 4px; }
.empty-err-msg { color: var(--c-text-muted); font-size: 12px; margin-bottom: 16px; }

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 10px;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  transition: transform .2s cubic-bezier(.32, .72, .35, 1), background .2s ease, box-shadow .2s ease, opacity .2s ease;
}
.btn:hover:not(:disabled) { transform: translateY(-1px); }
.btn:active:not(:disabled) { transform: scale(.97); }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-primary { background: var(--c-primary); color: #fff; box-shadow: var(--shadow-xs); }
.btn-primary:hover:not(:disabled) { background: var(--c-primary-hover); }
.btn-sm { padding: 6px 12px; font-size: 12px; }

/* ==================== 响应式 ==================== */
@media (max-width: 1024px) {
  .kpi-row { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 768px) {
  .kpi-row { grid-template-columns: repeat(2, 1fr); gap: 10px; }
  .kpi-card { padding: 14px; border-radius: 14px; }
  .kpi-val { font-size: 22px; }
  .panel-row { grid-template-columns: 1fr; }
  .panel-wide, .panel-wide-sm { grid-column: span 1; }
  .panel { padding: 18px; }
  .chart { height: 170px; }
  .q-grid { grid-template-columns: repeat(2, 1fr); }
  .alert-detail { white-space: normal; }
}
@media (max-width: 480px) {
  .kpi-row { gap: 8px; }
  .kpi-card { padding: 12px; gap: 8px; }
  .kpi-icon { width: 30px; height: 30px; border-radius: 8px; }
  .kpi-val { font-size: 19px; }
  .kpi-label { font-size: 11px; }
  .kpi-sub { font-size: 10.5px; }
  .panel { padding: 14px; border-radius: 14px; }
  .mini-table { overflow-x: auto; }
  .mt-row { min-width: 560px; }
}
</style>
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

/** 近 7 天：收入折线（左轴）+ 订单柱（右轴），图例由面板头部 HTML 承担 */
const trendOption = computed(() => {
  const p = palette.value
  const days = (dash.value?.recent_7_days || []) as { date: string; orders: number; revenue: number }[]
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
</script>

<template>
  <div>
    <div
      v-if="dash"
      class="overview-content"
    >
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
              今日收入
            </div>
          </div>
          <div class="kpi-sub">
            本周 {{ fmtMoney(dash.revenue.week) }}
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
            本周 {{ dash.orders.week }} 单
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
            累计 {{ dash.orders.completed }}/{{ dash.orders.total }}
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon agt">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ dash.orders.pending || 0 }}
            </div>
            <div class="kpi-label">
              待处理订单
            </div>
          </div>
          <div class="kpi-sub">
            执行中 {{ dash.orders.running || 0 }} 单
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon rev">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16"/></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ fmtMoney(dash.revenue.total) }}
            </div>
            <div class="kpi-label">
              累计收入
            </div>
          </div>
          <div class="kpi-sub">
            本周 {{ fmtMoney(dash.revenue.week) }}
          </div>
        </div>
        <div v-if="(dash.orders.failed || 0) > 0" class="kpi-card">
          <div class="kpi-icon ord">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
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
            今日 {{ dash.orders.today || 0 }} 单
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
        <div class="panel panel-wide">
          <div class="panel-head">
            <h3>订单状态分布</h3>
          </div>
          <v-chart
            class="chart"
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
                <span class="plat-cnt">{{ p.count }}单</span>
                <span class="plat-rev">{{ fmtMoney(p.revenue) }}</span>
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
              <div class="tc-count">
                {{ td.count }}单
              </div>
              <div class="tc-rev">
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
              <span class="mt-col mt-money">{{ fmtMoney(o.price) }}</span>
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
  font-size: 11.5px;
  color: var(--c-text-muted);
  border-top: 1px solid var(--c-border);
  padding-top: 8px;
}

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

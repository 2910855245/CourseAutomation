<script setup lang="ts">
import { useAdminStore } from '@/stores/admin'
const { currentRole } = useAdminStore().state().auth
const { getPlatformName } = useAdminStore().state().ui
const { dash, dashError, fmtMoney, fmtShortDate, loadDashboard, loadingDash, maxBarOrders, maxBarRevenue, maxStatusCount, orderStatusClass, orderStatusLabel, totalPlatformOrders } = useAdminStore().state().dashboard
const { orders } = useAdminStore().state().orders
const { platformColors, taskTypeNames } = useAdminStore().state().sysConfig
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
          <div class="kpi-icon usr">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" /><circle
              cx="12"
              cy="7"
              r="4"
            /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ dash.users.total }}
            </div>
            <div class="kpi-label">
              总用户数
            </div>
          </div>
          <div class="kpi-sub">
            今日新增 {{ dash.users.new_today }}
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
              {{ dash.orders.completion_rate }}%
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
          <div class="chart-area">
            <div
              v-for="day in dash.recent_7_days"
              :key="day.date"
              class="bar-group"
            >
              <div class="bars">
                <div
                  class="bar bar-rev"
                  :style="{ height: (day.revenue / maxBarRevenue * 100) + '%' }"
                  :title="'收入 ' + fmtMoney(day.revenue)"
                />
                <div
                  class="bar bar-ord"
                  :style="{ height: (day.orders / maxBarOrders * 100) + '%' }"
                  :title="'订单 ' + day.orders"
                />
              </div>
              <div class="bar-label">
                {{ day.date }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel-row">
        <div class="panel panel-wide">
          <div class="panel-head">
            <h3>订单状态分布</h3>
          </div>
          <div class="status-bars">
            <div
              v-for="sd in dash.status_distribution"
              :key="sd.status"
              class="sb-row"
            >
              <div class="sb-label">
                {{ orderStatusLabel[sd.status] || sd.status }}
              </div>
              <div class="sb-track">
                <div
                  class="sb-fill"
                  :class="'sb-' + (orderStatusClass[sd.status] || 'primary')"
                  :style="{ width: maxStatusCount > 0 ? (sd.count / maxStatusCount * 100) + '%' : '0%' }"
                />
              </div>
              <div class="sb-val">
                {{ sd.count }}
              </div>
            </div>
          </div>
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
                  :style="{ background: platformColors[i] || '#6b7280' }"
                />
                <span class="plat-name">{{ getPlatformName(p.website_id) }}</span>
              </div>
              <div class="plat-right">
                <div class="plat-bar-bg">
                  <div
                    class="plat-bar-fill"
                    :style="{ width: (p.count / totalPlatformOrders * 100) + '%', background: platformColors[i] || '#6b7280' }"
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
      <p style="color:#ef4444;font-weight:600;margin-bottom:4px">
        数据加载失败
      </p>
      <p style="color:#94a3b8;font-size:12px;margin-bottom:16px">
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
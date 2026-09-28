<script setup lang="ts">
import { useAdminStore } from '@/stores/admin'
const { currentRole } = useAdminStore().state().auth
const { getPlatformName } = useAdminStore().state().ui
const { fmtDate, fmtMoney, orderStatusClass, orderStatusLabel } = useAdminStore().state().dashboard
const { acceptOrder, clearOrderHistory, completeOrder, enqueueOrder, executeOrder, failOrder, loadOrders, loadingOrders, orders, ordersStatusFilter, ordersTotal } = useAdminStore().state().orders
const { taskTypeNames } = useAdminStore().state().sysConfig
</script>

<template>
  <div class="orders-tab">
    <div class="section-actions">
      <div class="filter-group">
        <button
          :class="['chip', { active: ordersStatusFilter === '' }]"
          @click="ordersStatusFilter = ''; loadOrders()"
        >
          全部
        </button>
        <button
          :class="['chip', { active: ordersStatusFilter === 'pending' }]"
          @click="ordersStatusFilter = 'pending'; loadOrders()"
        >
          待处理
        </button>
        <button
          :class="['chip', { active: ordersStatusFilter === 'running' }]"
          @click="ordersStatusFilter = 'running'; loadOrders()"
        >
          执行中
        </button>
        <button
          :class="['chip', { active: ordersStatusFilter === 'completed' }]"
          @click="ordersStatusFilter = 'completed'; loadOrders()"
        >
          已完成
        </button>
        <button
          :class="['chip', { active: ordersStatusFilter === 'failed' }]"
          @click="ordersStatusFilter = 'failed'; loadOrders()"
        >
          失败
        </button>
      </div>
      <span class="total-label">共 {{ ordersTotal }} 单</span>
      <button
        class="btn btn-ghost"
        :disabled="loadingOrders"
        @click="loadOrders"
      >
        <span
          v-if="loadingOrders"
          class="spinner"
          style="width:14px;height:14px"
        />
        {{ loadingOrders ? '加载中' : '刷新' }}
      </button>
      <button
        v-if="currentRole === 'admin'"
        class="btn btn-ghost btn-sm danger-text"
        @click="clearOrderHistory"
      >
        清除历史
      </button>
    </div>

    <div
      v-if="orders.length > 0"
      class="table-wrap"
    >
      <table class="data-table">
        <thead>
          <tr>
            <th>订单编号</th><th>用户</th><th>平台</th><th>类型</th><th>金额</th><th>支付</th><th>状态</th><th>创建时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="o in orders"
            :key="o.order_id"
          >
            <td><code class="code-tag">{{ o.order_id.slice(0, 10) }}...</code></td>
            <td>
              <div class="user-cell">
                <span class="uname">{{ o.customer_name || o.username }}</span>
                <span class="uid">{{ o.customer_contact || o.user_id?.slice(0, 8) || '-' }}</span>
              </div>
            </td>
            <td>{{ getPlatformName(o.website_id) }}</td>
            <td>{{ taskTypeNames[o.task_type] || o.task_type }}</td>
            <td class="money-cell">
              {{ fmtMoney(o.price) }}
            </td>
            <td><span :class="['status-tag', o.paid ? 'ok' : 'warn']">{{ o.paid ? '已支付' : '未支付' }}</span></td>
            <td><span :class="['status-tag', orderStatusClass[o.status]]">{{ orderStatusLabel[o.status] || o.status }}</span></td>
            <td class="date-cell">
              {{ fmtDate(o.created_at) }}
            </td>
            <td>
              <div class="action-group">
                <button
                  v-if="o.status === 'pending' || o.status === 'cancelled'"
                  class="btn btn-xs btn-success"
                  @click="acceptOrder(o.order_id)"
                >
                  接单
                </button>
                <button
                  v-if="(o.status === 'pending' || o.status === 'accepted' || o.status === 'cancelled') && currentRole === 'admin'"
                  class="btn btn-xs btn-primary"
                  @click="executeOrder(o.order_id)"
                >
                  执行
                </button>
                <button
                  v-if="(o.status === 'pending' || o.status === 'accepted') && currentRole === 'admin'"
                  class="btn btn-xs btn-primary"
                  @click="enqueueOrder(o.order_id)"
                >
                  入队
                </button>
                <button
                  v-if="o.status === 'cancelled' && currentRole === 'admin'"
                  class="btn btn-xs btn-warn"
                  @click="enqueueOrder(o.order_id)"
                >
                  重新入队
                </button>
                <button
                  v-if="o.status === 'running'"
                  class="btn btn-xs btn-success"
                  @click="completeOrder(o.order_id)"
                >
                  完成
                </button>
                <button
                  v-if="o.status !== 'completed' && o.status !== 'cancelled'"
                  class="btn btn-xs btn-danger"
                  @click="failOrder(o.order_id)"
                >
                  失败
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div
      v-else-if="!loadingOrders"
      class="empty"
    >
      <p>暂无订单数据</p>
    </div>
  </div>
</template>

<style scoped>
.orders-tab {
  display: flex;
  flex-direction: column;
  animation: od-in .35s cubic-bezier(.32, .72, .35, 1) both;
}
@keyframes od-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ==================== 筛选区 ==================== */
.section-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}
.filter-group { display: flex; gap: 6px; flex-wrap: wrap; }
.chip {
  padding: 6px 14px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  background: var(--c-surface);
  color: var(--c-text-secondary);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all .2s cubic-bezier(.32, .72, .35, 1);
}
.chip:hover { border-color: var(--c-primary); color: var(--c-primary); }
.chip:active { transform: scale(.97); }
.chip.active {
  background: var(--c-primary);
  color: #fff;
  border-color: var(--c-primary);
  box-shadow: var(--shadow-xs);
}
.total-label { font-size: 12.5px; color: var(--c-text-muted); margin-left: auto; }
.danger-text { color: var(--c-danger); }

/* ==================== 表格 ==================== */
.table-wrap {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  /* 9 列表格在 769~859px 这个区间会挤爆容器：横向滚动必须常开，
     原先只在 ≤768px 生效，导致中等宽度下内容被 overflow:hidden 裁掉 */
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  box-shadow: var(--shadow-xs);
}
.data-table { width: 100%; min-width: 860px; border-collapse: collapse; font-size: 13px; }
.data-table th {
  text-align: left;
  padding: 11px 16px;
  font-size: 11px;
  font-weight: 600;
  color: var(--c-text-muted);
  text-transform: uppercase;
  letter-spacing: .05em;
  border-bottom: 1px solid var(--c-border);
  white-space: nowrap;
}
.data-table td {
  padding: 12px 16px;
  border-bottom: 1px solid var(--c-border);
  color: var(--c-text);
  vertical-align: middle;
}
.data-table tbody tr { transition: background .2s ease; }
.data-table tbody tr:hover { background: var(--c-bg); }
.data-table tbody tr:last-child td { border-bottom: none; }

.user-cell { display: flex; flex-direction: column; gap: 1px; }
.uname { font-weight: 600; color: var(--c-text); }
.uid { font-size: 11px; color: var(--c-text-muted); }
.money-cell { font-weight: 600; font-variant-numeric: tabular-nums; }
.date-cell { font-size: 12px; color: var(--c-text-muted); white-space: nowrap; }
.code-tag {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  background: var(--c-bg);
  padding: 2px 7px;
  border-radius: 6px;
  color: var(--c-text-secondary);
}

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
.status-tag.warn { background: var(--c-warning-bg); color: var(--c-warning); }
.status-tag.bad { background: var(--c-danger-bg); color: var(--c-danger); }
.status-tag.primary { background: var(--c-primary-bg); color: var(--c-primary); }
.status-tag.muted { background: var(--c-bg); color: var(--c-text-muted); }

/* ==================== 操作区 ==================== */
.action-group { display: flex; gap: 6px; flex-wrap: wrap; }

/* ==================== 按钮 ==================== */
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
.btn-primary { background: var(--c-primary); color: #fff; }
.btn-primary:hover:not(:disabled) { background: var(--c-primary-hover); }
.btn-success { background: var(--c-success); color: #fff; }
.btn-warn { background: var(--c-warning); color: #fff; }
.btn-danger { background: var(--c-danger); color: #fff; }
.btn-ghost { background: transparent; color: var(--c-text-secondary); }
.btn-ghost:hover:not(:disabled) { color: var(--c-primary); background: var(--c-primary-bg); transform: none; }
.btn-sm { padding: 6px 12px; font-size: 12px; }
.btn-xs { padding: 4px 10px; font-size: 11.5px; border-radius: 8px; }

/* ==================== 空状态 ==================== */
.empty { text-align: center; padding: 60px 20px; color: var(--c-text-muted); }
.empty p { margin-bottom: 16px; }

/* ==================== 响应式 ==================== */
@media (max-width: 768px) {
  .data-table th, .data-table td { padding: 9px 12px; font-size: 12px; }
  .total-label { margin-left: 0; }
}
@media (max-width: 480px) {
  .chip { padding: 5px 11px; font-size: 11.5px; }
  .section-actions { gap: 8px; }
}
</style>

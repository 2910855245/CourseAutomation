<script setup lang="ts">
import { computed } from 'vue'
import { useAdminStore } from '@/stores/admin'
const { fmtDate } = useAdminStore().state().dashboard
const { applyAutoConcurrency, cancelQueueJob, clearQueueHistory, deleteQueueJob, detectServerSpecs, loadQueueData, loadingQueue, maxWorkersInput, pauseQueue, queueFilter, queueJobs, queuePausing, queueStats, queueStatusFilter, resumeQueue, retryQueueJob, serverSpecs, setMaxWorkers } = useAdminStore().state().payments

// 调度器开关的真实状态：接口未返回该字段时按"启用"处理（兼容旧后端）
const schedulerOff = computed(() => queueStats.value?.scheduler_enabled === false)
</script>

<template>
  <div>
    <div
      v-if="queueStats"
      class="queue-panel"
    >
      <!-- 共用区域：状态 + 控制（始终操作全部队列） -->
      <div class="queue-header">
        <div class="queue-status-badge">
          <span
            class="qsb-dot"
            :class="queueStats.paused ? 'qsb-paused' : (schedulerOff ? 'qsb-off' : 'qsb-live')"
          />
          <span class="qsb-text">
            {{ schedulerOff ? '调度器已停用' : (queueStats.paused ? '全部已暂停' : '运行中') }}
          </span>
        </div>
        <div
          v-if="schedulerOff"
          class="queue-off-hint"
        >
          后端以 RUST_QUEUE_ENABLED=false 启动，任何入队任务都不会被执行
        </div>
        <div class="queue-actions">
          <button
            v-if="!queueStats.paused"
            class="btn btn-warn btn-sm"
            :disabled="queuePausing"
            @click="pauseQueue('')"
          >
            {{ queuePausing ? '...' : '暂停全部' }}
          </button>
          <button
            v-if="queueStats.paused"
            class="btn btn-success btn-sm"
            :disabled="queuePausing"
            @click="resumeQueue('')"
          >
            {{ queuePausing ? '...' : '恢复全部' }}
          </button>
          <button
            class="btn btn-ghost btn-sm"
            :disabled="loadingQueue"
            @click="loadQueueData"
          >
            {{ loadingQueue ? '刷新中' : '刷新' }}
          </button>
        </div>
      </div>

      <div class="queue-config-row">
        <label class="qcfg-label">最大并发数</label>
        <input
          v-model.number="maxWorkersInput"
          type="number"
          min="1"
          max="64"
          class="qcfg-input"
        >
        <button
          class="btn btn-primary btn-sm"
          @click="setMaxWorkers"
        >
          应用
        </button>
        <button
          class="btn btn-ghost btn-sm"
          title="根据服务器配置自动设置"
          @click="applyAutoConcurrency"
        >
          智能检测
        </button>
        <button
          class="btn btn-ghost btn-sm"
          title="查看服务器配置"
          @click="detectServerSpecs"
        >
          服务器配置
        </button>
      </div>

      <div
        v-if="serverSpecs"
        class="queue-specs-card"
      >
        <div class="spec-row">
          <span class="spec-label">CPU</span><span class="spec-val">{{ serverSpecs.cpu_count }} 核</span>
        </div>
        <div class="spec-row">
          <span class="spec-label">内存</span><span class="spec-val">{{ serverSpecs.total_mem_gb }} GB</span>
        </div>
        <div class="spec-row">
          <span class="spec-label">推荐并发</span><span class="spec-val spec-highlight">{{ serverSpecs.recommended_workers }} 个任务</span>
        </div>
        <div class="spec-row">
          <span class="spec-label">当前设置</span><span class="spec-val">{{ serverSpecs.current_workers }} 个任务</span>
        </div>
      </div>


      <!-- KPI -->
      <div class="queue-kpi-row">
        <div class="qkpi">
          <div class="qkpi-val">
            {{ queueStats.pending ?? queueStats.queue?.pending ?? 0 }}
          </div>
          <div class="qkpi-label">
            待处理
          </div>
        </div>
        <div class="qkpi">
          <div class="qkpi-val qkpi-running">
            {{ queueStats.running ?? queueStats.queue?.running ?? 0 }}
          </div>
          <div class="qkpi-label">
            执行中
          </div>
        </div>
        <div
          v-if="(queueStats.waiting ?? 0) > 0"
          class="qkpi"
        >
          <div class="qkpi-val qkpi-info">
            {{ queueStats.waiting }}
          </div>
          <div class="qkpi-label">
            等待明天
          </div>
        </div>
        <div class="qkpi">
          <div class="qkpi-val qkpi-ok">
            {{ queueStats.completed ?? queueStats.queue?.completed ?? 0 }}
          </div>
          <div class="qkpi-label">
            已完成
          </div>
        </div>
        <div class="qkpi">
          <div class="qkpi-val qkpi-bad">
            {{ queueStats.failed ?? queueStats.queue?.failed ?? 0 }}
          </div>
          <div class="qkpi-label">
            失败
          </div>
        </div>
        <div class="qkpi">
          <div class="qkpi-val qkpi-blue">
            {{ queueStats.active_workers || 0 }}<span class="qkpi-sub">/{{ queueStats.max_workers || '-' }}</span>
          </div>
          <div class="qkpi-label">
            工作线程（在跑/上限）
          </div>
        </div>
        <div
          v-if="queueStats.global_study_sessions"
          class="qkpi"
        >
          <div class="qkpi-val qkpi-blue">
            {{ queueStats.global_study_sessions }}
          </div>
          <div
            class="qkpi-label"
            title="进程内同时在刷的视频会话数上限，调大工作线程不会突破它"
          >
            全局会话上限
          </div>
        </div>
      </div>

      <!-- 状态筛选 + 清除 -->
      <div class="section-actions">
        <div class="filter-group">
          <button
            :class="['chip', { active: queueStatusFilter === '' }]"
            @click="queueStatusFilter = ''; loadQueueData()"
          >
            全部
          </button>
          <button
            :class="['chip', { active: queueStatusFilter === 'pending' }]"
            @click="queueStatusFilter = 'pending'; loadQueueData()"
          >
            待处理
          </button>
          <button
            :class="['chip', { active: queueStatusFilter === 'running' }]"
            @click="queueStatusFilter = 'running'; loadQueueData()"
          >
            执行中
          </button>
          <button
            :class="['chip', { active: queueStatusFilter === 'completed' }]"
            @click="queueStatusFilter = 'completed'; loadQueueData()"
          >
            已完成
          </button>
          <button
            :class="['chip', { active: queueStatusFilter === 'failed' }]"
            @click="queueStatusFilter = 'failed'; loadQueueData()"
          >
            失败
          </button>
        </div>
        <button
          class="btn btn-ghost btn-sm danger-text"
          style="margin-left:auto;"
          @click="clearQueueHistory"
        >
          清除历史
        </button>
      </div>

      <!-- 任务列表 -->
      <div
        v-if="queueJobs.length > 0"
        class="table-wrap"
      >
        <table class="data-table">
          <thead>
            <tr>
              <th>任务ID</th><th>用户</th><th>订单编号</th><th v-if="queueFilter === ''">
                队列
              </th><th>状态</th><th>进度</th><th>创建时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="j in queueJobs"
              :key="j.job_id"
            >
              <td><code class="code-tag">{{ j.job_id?.slice(0, 10) }}...</code></td>
              <td>{{ j.username || '-' }}</td>
              <td>
                <code
                  v-if="j.order_id"
                  class="code-tag"
                >{{ j.order_id?.slice(0, 10) }}...</code><span v-else>-</span>
              </td>
              <td v-if="queueFilter === ''">
                <span :class="['status-tag', j.queue === 'chaoxing' ? 'primary' : 'ok']">
                  {{ j.queue === 'chaoxing' ? '学习通' : '学校平台' }}
                </span>
              </td>
              <td>
                <span
                  :class="['status-tag',
                           j.status === 'completed' && j.verified ? 'ok verified' :
                           j.status === 'completed' ? 'ok' :
                           j.status === 'running' ? 'primary' :
                           j.status === 'failed' ? 'bad' :
                           j.status === 'cancelled' ? 'muted' :
                           j.status === 'waiting' ? 'warn' :
                           j.status === 'retrying' ? 'primary' :
                           j.status === 'pending' ? 'warn' : 'muted'
                  ]"
                >
                  {{ j.status === 'completed' ? '已完成' : j.status === 'running' ? '执行中' : j.status === 'failed' ? (j.error_message || '失败') : j.status === 'cancelled' ? '已取消' : j.status === 'waiting' ? '等待明天' : j.status === 'retrying' ? '重试中' : j.status === 'pending' ? '待处理' : j.status }}
                </span>
              </td>
              <td>
                <div
                  v-if="j.progress !== undefined"
                  class="q-progress"
                >
                  <div
                    class="q-prog-bar"
                    :style="{ width: j.progress + '%' }"
                  />
                </div>
                <span v-else>-</span>
              </td>
              <td class="date-cell">
                {{ fmtDate(j.created_at) }}
              </td>
              <td>
                <div class="action-cell">
                  <span class="action-slot">
                    <button
                      v-if="j.status === 'pending' || j.status === 'running' || j.status === 'waiting'"
                      class="btn btn-xs btn-danger"
                      @click="cancelQueueJob(j.job_id)"
                    >
                      取消
                    </button>
                    <button
                      v-if="j.status === 'failed'"
                      class="btn btn-xs btn-primary"
                      @click="retryQueueJob(j.job_id)"
                    >
                      重试
                    </button>
                  </span>
                  <button
                    v-if="j.status !== 'running'"
                    class="del-btn"
                    title="删除"
                    @click="deleteQueueJob(j.job_id)"
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/></svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        v-else-if="!loadingQueue"
        class="empty"
      >
        <p>暂无任务</p>
      </div>
    </div>
    <div
      v-else-if="!loadingQueue"
      class="empty"
    >
      <p>点击刷新加载队列数据</p>
    </div>
  </div>
</template>

<style scoped>
.queue-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  animation: q-in .35s cubic-bezier(.32, .72, .35, 1) both;
}
@keyframes q-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ==================== 顶部状态条 ==================== */
.queue-header {
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
.queue-status-badge { display: flex; align-items: center; gap: 8px; }
.qsb-dot { width: 9px; height: 9px; border-radius: 50%; }
.qsb-dot.qsb-live { background: var(--c-success); animation: qsb-pulse 1.8s ease-in-out infinite; }
.qsb-dot.qsb-paused { background: var(--c-warning); }
.qsb-dot.qsb-off { background: var(--c-danger); }
.queue-off-hint { font-size: 12px; color: var(--c-danger); flex-basis: 100%; }
.qkpi-sub { font-size: 14px; font-weight: 600; color: var(--c-text-muted); margin-left: 2px; }
@keyframes qsb-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, .35); }
  50% { box-shadow: 0 0 0 5px rgba(34, 197, 94, 0); }
}
.qsb-text { font-size: 13px; font-weight: 600; color: var(--c-text); }
.queue-actions { display: flex; gap: 8px; flex-wrap: wrap; }

/* ==================== 并发配置 ==================== */
.queue-config-row {
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
.qcfg-label { font-size: 13px; font-weight: 600; color: var(--c-text-secondary); }
.qcfg-input {
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
.qcfg-input:focus {
  border-color: var(--c-primary);
  background: var(--c-surface);
  box-shadow: 0 0 0 3px rgba(0, 113, 227, .12);
}

/* ==================== 服务器配置卡片 ==================== */
.queue-specs-card {
  display: flex;
  gap: 32px;
  flex-wrap: wrap;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: 16px 20px;
  box-shadow: var(--shadow-xs);
  animation: q-in .3s cubic-bezier(.32, .72, .35, 1) both;
}
.spec-row { display: flex; flex-direction: column; gap: 2px; }
.spec-label {
  font-size: 10.5px;
  color: var(--c-text-muted);
  text-transform: uppercase;
  letter-spacing: .05em;
  font-weight: 600;
}
.spec-val { font-size: 15px; font-weight: 600; color: var(--c-text); font-variant-numeric: tabular-nums; }
.spec-highlight { color: var(--c-primary); }

/* ==================== KPI ==================== */
.queue-kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 12px;
}
.qkpi {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: 16px 18px;
  box-shadow: var(--shadow-xs);
  transition: transform .25s cubic-bezier(.32, .72, .35, 1), box-shadow .25s cubic-bezier(.32, .72, .35, 1);
}
.qkpi:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}
.qkpi-val {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--c-text);
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.qkpi-val.qkpi-running { color: var(--c-primary); }
.qkpi-val.qkpi-info { color: var(--c-warning); }
.qkpi-val.qkpi-ok { color: var(--c-success); }
.qkpi-val.qkpi-bad { color: var(--c-danger); }
.qkpi-val.qkpi-blue { color: var(--c-info); }
.qkpi-label { font-size: 11.5px; color: var(--c-text-secondary); margin-top: 4px; font-weight: 500; }

/* ==================== 筛选区 ==================== */
.section-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
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
.danger-text { color: var(--c-danger); }

/* ==================== 表格 ==================== */
.table-wrap {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: var(--shadow-xs);
}
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
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
.status-tag.ok.verified { border: 1.5px solid var(--c-success); }
.status-tag.warn { background: var(--c-warning-bg); color: var(--c-warning); }
.status-tag.bad { background: var(--c-danger-bg); color: var(--c-danger); }
.status-tag.primary { background: var(--c-primary-bg); color: var(--c-primary); }
.status-tag.muted { background: var(--c-bg); color: var(--c-text-muted); }

/* ==================== 进度条 ==================== */
.q-progress {
  width: 84px;
  height: 6px;
  background: var(--c-bg);
  border-radius: 999px;
  overflow: hidden;
}
.q-prog-bar {
  height: 100%;
  background: var(--c-primary);
  border-radius: 999px;
  transition: width .35s cubic-bezier(.32, .72, .35, 1);
}

/* ==================== 操作区 ==================== */
.action-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.action-slot {
  display: inline-flex;
  min-width: 32px;
}
.del-btn {
  margin-left: auto;
  color: var(--c-text-muted);
  cursor: pointer;
  padding: 5px;
  border: none;
  background: none;
  line-height: 1;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  transition: color .2s ease, background .2s ease;
}
.del-btn:hover {
  color: var(--c-danger);
  background: var(--c-danger-bg);
}

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
@media (max-width: 1024px) {
  .queue-kpi-row { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 768px) {
  .queue-kpi-row { grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .qkpi { padding: 12px 14px; }
  .qkpi-val { font-size: 22px; }
  .queue-header, .queue-config-row { padding: 12px 14px; }
  .queue-specs-card { gap: 20px; padding: 14px 16px; }
  .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .data-table { min-width: 760px; }
  .data-table th, .data-table td { padding: 9px 12px; font-size: 12px; }
}
@media (max-width: 480px) {
  .queue-kpi-row { grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .qkpi { padding: 10px 12px; border-radius: 12px; }
  .qkpi-val { font-size: 19px; }
  .queue-header { flex-direction: column; align-items: flex-start; }
  .chip { padding: 5px 11px; font-size: 11.5px; }
}
</style>

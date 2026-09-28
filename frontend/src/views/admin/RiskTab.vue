<script setup lang="ts">
import { useAdminStore } from '@/stores/admin'
const { fmtDate } = useAdminStore().state().dashboard
const { loadRiskData, loadingRisk, removeDomain, riskAlerts, riskCheckStep, riskChecking, riskChecks, riskDomainStatus, riskHealth, riskIntervalInput, riskScore, riskScoreColor, riskScoreDash, riskScoreDesc, riskScoreLevel, riskScoreText, runFullRiskCheck, saveRiskInterval } = useAdminStore().state().sysConfig
</script>

<template>
  <div class="risk-tab">
    <div class="risk-dashboard">
      <div class="risk-gauge-card">
        <div
          class="risk-gauge"
          :class="riskScoreLevel"
        >
          <svg
            viewBox="0 0 120 120"
            class="risk-gauge-svg"
          >
            <circle
              cx="60"
              cy="60"
              r="52"
              fill="none"
              stroke="#e2e8f0"
              stroke-width="8"
            />
            <circle
              cx="60"
              cy="60"
              r="52"
              fill="none"
              :stroke="riskScoreColor"
              stroke-width="8"
              stroke-linecap="round"
              :stroke-dasharray="riskScoreDash"
              stroke-dashoffset="0"
              transform="rotate(-90 60 60)"
              class="risk-gauge-fill"
            />
          </svg>
          <div class="risk-gauge-inner">
            <div class="risk-gauge-score">
              {{ riskScore }}
            </div>
            <div class="risk-gauge-label">
              健康度
            </div>
          </div>
        </div>
        <div class="risk-gauge-info">
          <div
            class="risk-gauge-title"
            :class="riskScoreLevel"
          >
            {{ riskScoreText }}
          </div>
          <div class="risk-gauge-desc">
            {{ riskScoreDesc }}
          </div>
          <div
            v-if="riskDomainStatus?.last_check"
            class="risk-gauge-time"
          >
            上次检查: {{ fmtDate(riskDomainStatus.last_check) }}
          </div>
        </div>
      </div>
      <div class="risk-actions">
        <button
          class="btn btn-primary"
          :disabled="riskChecking"
          @click="runFullRiskCheck"
        >
          {{ riskChecking ? '检查中...' : '全面检查' }}
        </button>
        <button
          class="btn btn-ghost btn-sm"
          :disabled="loadingRisk"
          @click="loadRiskData"
        >
          {{ loadingRisk ? '刷新中' : '刷新' }}
        </button>
        <span
          v-if="riskChecking && riskCheckStep"
          class="risk-check-progress"
        >
          <span class="risk-check-spinner" />
          正在检查: {{ riskCheckStep }}
        </span>
      </div>
    </div>

    <div
      v-if="loadingRisk && !riskDomainStatus"
      class="empty"
    >
      <p>加载中...</p>
    </div>

    <template v-else>
      <div class="risk-checks">
        <div
          v-for="check in riskChecks"
          :key="check.id"
          class="risk-check-item"
          @click="check.expanded = !check.expanded"
        >
          <div class="risk-check-main">
            <div
              class="risk-check-icon"
              :class="check.status"
            >
              <svg
                v-if="check.status === 'pass'"
                viewBox="0 0 20 20"
                fill="currentColor"
              ><path
                fill-rule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                clip-rule="evenodd"
              /></svg>
              <svg
                v-else-if="check.status === 'warn'"
                viewBox="0 0 20 20"
                fill="currentColor"
              ><path
                fill-rule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                clip-rule="evenodd"
              /></svg>
              <svg
                v-else-if="check.status === 'unknown'"
                viewBox="0 0 20 20"
                fill="currentColor"
              ><path
                fill-rule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z"
                clip-rule="evenodd"
              /></svg>
              <svg
                v-else
                viewBox="0 0 20 20"
                fill="currentColor"
              ><path
                fill-rule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293-1.293a1 1 0 001.414-1.414L11.414 10l1.293 1.293a1 1 0 010-1.414-1.414L10 8.586 8.707 7.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                clip-rule="evenodd"
              /></svg>
            </div>
            <div class="risk-check-info">
              <div class="risk-check-name">
                {{ check.name }}
              </div>
              <div class="risk-check-desc">
                {{ check.desc }}
              </div>
            </div>
            <div
              class="risk-check-status"
              :class="check.status"
            >
              {{ check.status === 'pass' ? '正常' : check.status === 'warn' ? '警告' : check.status === 'unknown' ? '未检测' : '异常' }}
            </div>
            <svg
              class="risk-check-arrow"
              :class="{ open: check.expanded }"
              viewBox="0 0 20 20"
              fill="currentColor"
            ><path
              fill-rule="evenodd"
              d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
              clip-rule="evenodd"
            /></svg>
          </div>
          <div
            v-if="check.expanded"
            class="risk-check-detail"
            @click.stop
          >
            <slot :name="check.id">
              <div v-if="check.id === 'platform'">
                <div
                  v-if="riskHealth?.platforms?.length"
                  class="risk-health-grid"
                >
                  <div
                    v-for="p in riskHealth.platforms"
                    :key="p.domain"
                    class="risk-health-card"
                    :class="p.reachable ? 'health-ok' : 'health-bad'"
                  >
                    <div class="health-name">
                      {{ p.name }}
                    </div>
                    <div class="health-domain">
                      {{ p.domain }}
                    </div>
                    <div class="health-status">
                      <span :class="['health-dot', p.reachable ? 'dot-ok' : 'dot-bad']" />
                      {{ p.reachable ? `可达 (${p.response_time_ms}ms)` : (p.error || '不可达') }}
                    </div>
                  </div>
                </div>
                <div
                  v-else
                  class="empty-sm"
                >
                  暂无平台数据
                </div>
              </div>
              <div v-else-if="check.id === 'domain'">
                <div
                  v-if="riskDomainStatus?.known_domains && Object.keys(riskDomainStatus.known_domains).length"
                  class="table-wrap"
                >
                  <table class="data-table data-table-sm">
                    <thead><tr><th>域名</th><th>名称</th><th>来源</th><th>操作</th></tr></thead>
                    <tbody>
                      <tr
                        v-for="(info, domain) in riskDomainStatus.known_domains"
                        :key="domain"
                      >
                        <td><code class="code-tag">{{ domain }}</code></td>
                        <td>{{ info.name }}</td>
                        <td><span :class="['status-tag', info.source === 'auto' ? 'primary' : info.source === 'config' ? 'ok' : 'ok']">{{ info.source === 'auto' ? '自动' : info.source === 'config' ? '预设' : '手动' }}</span></td>
                        <td>
                          <button
                            class="btn btn-xs btn-danger"
                            @click.stop="removeDomain(String(domain))"
                          >
                            移除
                          </button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div
                  v-else
                  class="empty-sm"
                >
                  暂无监控域名
                </div>
              </div>
              <div v-else-if="check.id === 'alerts'">
                <div
                  v-if="riskAlerts.length"
                  class="table-wrap"
                >
                  <table class="data-table data-table-sm">
                    <thead><tr><th>时间</th><th>类型</th><th>详情</th></tr></thead>
                    <tbody>
                      <tr
                        v-for="(a, i) in riskAlerts.slice(0, 10)"
                        :key="i"
                      >
                        <td class="date-cell">
                          {{ fmtDate(a.time) }}
                        </td>
                        <td><span :class="['status-tag', a.type === 'new_domain' ? 'warn' : 'primary']">{{ a.type === 'new_domain' ? '新域名' : a.type }}</span></td>
                        <td>{{ a.message }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div
                  v-else
                  class="empty-sm"
                >
                  暂无告警
                </div>
              </div>
              <div v-else-if="check.id === 'interval'">
                <div class="risk-interval-row">
                  <label>自动检查间隔</label>
                  <input
                    v-model.number="riskIntervalInput"
                    type="number"
                    min="300"
                    step="60"
                    class="risk-interval-input"
                  >
                  <span>秒</span>
                  <button
                    class="btn btn-primary btn-sm"
                    @click.stop="saveRiskInterval"
                  >
                    保存
                  </button>
                  <span class="risk-interval-hint">最小 300 秒（当前: {{ Math.floor(riskIntervalInput / 60) }} 分钟）</span>
                </div>
              </div>
            </slot>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.risk-tab {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.risk-tab > * {
  animation: risk-in .35s cubic-bezier(.32, .72, .35, 1) both;
}

.risk-tab > *:nth-child(2) { animation-delay: .07s; }
.risk-tab > *:nth-child(3) { animation-delay: .14s; }

@keyframes risk-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.btn {
  transition: all .2s cubic-bezier(.32, .72, .35, 1);
}

.btn:active:not(:disabled) {
  transform: scale(.97);
}

/* 仪表盘 */
.risk-dashboard {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 16px;
  padding: 24px 28px;
  box-shadow: var(--shadow-xs);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 24px;
}

.risk-gauge-card {
  display: flex;
  align-items: center;
  gap: 20px;
  flex: 1;
  min-width: 260px;
}

.risk-gauge {
  position: relative;
  width: 120px;
  height: 120px;
  flex-shrink: 0;
}

.risk-gauge-svg {
  width: 100%;
  height: 100%;
  display: block;
}

.risk-gauge-fill {
  transition: stroke-dasharray .6s cubic-bezier(.32, .72, .35, 1), stroke .4s ease;
}

.risk-gauge-inner {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.risk-gauge-score {
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--c-text);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}

.risk-gauge-label {
  font-size: 11.5px;
  color: var(--c-text-muted);
  margin-top: 2px;
}

.risk-gauge-title {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.risk-gauge-title.good { color: var(--c-success); }
.risk-gauge-title.warn { color: var(--c-warning, #ff9500); }
.risk-gauge-title.bad { color: var(--c-danger); }

.risk-gauge-desc {
  font-size: 13px;
  color: var(--c-text-secondary);
  margin-top: 6px;
  line-height: 1.6;
}

.risk-gauge-time {
  font-size: 12px;
  color: var(--c-text-muted);
  margin-top: 8px;
}

.risk-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.risk-check-progress {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--c-text-secondary);
}

.risk-check-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--c-border);
  border-top-color: var(--c-primary);
  border-radius: 50%;
  animation: risk-spin .7s linear infinite;
}

@keyframes risk-spin {
  to { transform: rotate(360deg); }
}

/* 检查项列表 */
.risk-checks {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.risk-checks > .risk-check-item:nth-child(2) { animation-delay: .04s; }
.risk-checks > .risk-check-item:nth-child(3) { animation-delay: .08s; }
.risk-checks > .risk-check-item:nth-child(4) { animation-delay: .12s; }
.risk-checks > .risk-check-item:nth-child(5) { animation-delay: .16s; }

.risk-check-item {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  animation: risk-in .35s cubic-bezier(.32, .72, .35, 1) both;
  transition: transform .25s cubic-bezier(.32, .72, .35, 1), box-shadow .25s cubic-bezier(.32, .72, .35, 1), border-color .2s ease;
}

.risk-check-item:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.risk-check-main {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 18px;
}

.risk-check-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.risk-check-icon svg {
  width: 18px;
  height: 18px;
}

.risk-check-icon.pass { background: var(--c-success-bg); color: var(--c-success); }
.risk-check-icon.warn { background: rgba(255, 149, 0, .12); color: var(--c-warning, #ff9500); }
.risk-check-icon.fail { background: var(--c-danger-bg); color: var(--c-danger); }
.risk-check-icon.unknown { background: var(--c-bg); color: var(--c-text-muted); }

.risk-check-info {
  flex: 1;
  min-width: 0;
}

.risk-check-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--c-text);
}

.risk-check-desc {
  font-size: 12.5px;
  color: var(--c-text-muted);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.risk-check-status {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 11px;
  border-radius: 999px;
  flex-shrink: 0;
}

.risk-check-status.pass { background: var(--c-success-bg); color: var(--c-success); }
.risk-check-status.warn { background: rgba(255, 149, 0, .12); color: var(--c-warning, #ff9500); }
.risk-check-status.fail { background: var(--c-danger-bg); color: var(--c-danger); }
.risk-check-status.unknown { background: var(--c-bg); color: var(--c-text-muted); }

.risk-check-arrow {
  width: 16px;
  height: 16px;
  color: var(--c-text-muted);
  flex-shrink: 0;
  transition: transform .25s cubic-bezier(.32, .72, .35, 1);
}

.risk-check-arrow.open {
  transform: rotate(180deg);
}

.risk-check-detail {
  padding: 4px 18px 18px;
  cursor: default;
  animation: risk-in .25s cubic-bezier(.32, .72, .35, 1) both;
}

/* 平台健康度 */
.risk-health-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.risk-health-card {
  background: var(--c-bg);
  border-radius: 12px;
  padding: 12px 14px;
  border-left: 3px solid transparent;
  transition: transform .2s cubic-bezier(.32, .72, .35, 1);
}

.risk-health-card:hover {
  transform: translateY(-1px);
}

.risk-health-card.health-ok { border-left-color: var(--c-success); }
.risk-health-card.health-bad { border-left-color: var(--c-danger); }

.health-name {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--c-text);
}

.health-domain {
  font-size: 12px;
  color: var(--c-text-muted);
  font-family: var(--font-mono, 'SF Mono', Menlo, monospace);
  margin-top: 2px;
}

.health-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--c-text-secondary);
  margin-top: 8px;
}

.health-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.health-dot.dot-ok { background: var(--c-success); }
.health-dot.dot-bad { background: var(--c-danger); }

/* 间隔设置 */
.risk-interval-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 13.5px;
  color: var(--c-text);
}

.risk-interval-input {
  width: 110px;
}

.risk-interval-hint {
  font-size: 12px;
  color: var(--c-text-muted);
}

.empty {
  padding: 40px 0;
  text-align: center;
  color: var(--c-text-muted);
  font-size: 14px;
}

.empty-sm {
  padding: 18px 0;
  text-align: center;
  color: var(--c-text-muted);
  font-size: 13px;
}

@media (max-width: 768px) {
  .risk-dashboard {
    padding: 18px;
    gap: 16px;
  }

  .risk-gauge {
    width: 100px;
    height: 100px;
  }

  .risk-gauge-score {
    font-size: 24px;
  }

  .risk-gauge-card {
    min-width: 0;
    width: 100%;
  }

  .risk-check-desc {
    white-space: normal;
  }
}
</style>

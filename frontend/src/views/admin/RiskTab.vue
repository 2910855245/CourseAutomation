<script setup lang="ts">
import { useAdminStore } from '@/stores/admin'
const { fmtDate } = useAdminStore().state().dashboard
const { loadRiskData, loadingRisk, removeDomain, riskAlerts, riskCheckStep, riskChecking, riskChecks, riskDomainStatus, riskHealth, riskIntervalInput, riskJsStatus, riskScore, riskScoreColor, riskScoreDash, riskScoreDesc, riskScoreLevel, riskScoreText, runFullRiskCheck, saveRiskInterval } = useAdminStore().state().sysConfig
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
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
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
              <div v-else-if="check.id === 'js'">
                <div
                  v-if="riskJsStatus?.files?.length"
                  class="table-wrap"
                >
                  <table class="data-table data-table-sm">
                    <thead><tr><th>文件地址</th><th>Hash</th></tr></thead>
                    <tbody>
                      <tr
                        v-for="(f, i) in riskJsStatus.files"
                        :key="i"
                      >
                        <td>
                          <code
                            class="code-tag"
                            style="font-size:11px;word-break:break-all;"
                          >{{ f.url }}</code>
                        </td>
                        <td><code class="code-tag">{{ f.hash }}</code></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div
                  v-else
                  class="empty-sm"
                >
                  暂无监控文件
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
                        <td><span :class="['status-tag', a.type === 'new_domain' ? 'warn' : a.type === 'js_change' ? 'bad' : 'primary']">{{ a.type === 'new_domain' ? '新域名' : a.type === 'js_change' ? 'JS变更' : a.type }}</span></td>
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
<script setup lang="ts">
// @ts-nocheck
import { useAdminState } from './adminState'

const { DEEPSEEK_MODELS, acceptOrder, accountForm, accounts, active, activeTab, adFileInput, adFileUploading, adForm, adImgInput, addDomain, addDomainForm, adminPass, adminState, adminUser, adsList, agentFees, agentStats, agentStatusFilter, agentSubTab, agentTotal, agents, agentsByTier, alertCount, aliAccounts, all, allSidebarItems, allUp, applyAutoConcurrency, applyPackagePricing, applyingPackage, approveAgent, approveWithdrawal, base64, body, buildRiskChecks, cancelEditPricing, cancelQueueJob, captchaAnswer, captchaImage, captchaLoading, captchaToken, cfg, changeAdminPassword, changingPw, channelCodeHelp, channelCodeLabels, channelTestAccount, channelTestAllOk, channelTestChecks, channelTestLoading, channelTestQrImage, chars, checks, circumference, clearCommissionHistory, clearDeepseekKey, clearOrderHistory, clearQueueHistory, clearRiskAlerts, clearWithdrawalHistory, clearYpayOrderHistory, closeAccountModal, closeExpiredYpayOrders, closePayTest, codeLabel, commissionTotal, commissions, completeOrder, configs, count, creatingSubAdmin, currentRole, d, dash, dashError, deepseekApiKey, deepseekKeyMasked, deepseekTestResult, defaultCodes, deleteAccount, deleteAd, detectServerSpecs, doChangeTier, doCreateSubAdmin, doRevokeSubAdmin, doTopup, domainCount, downloadQrImage, downloadQrLoading, dsRes, editPricing, editingAccount, editingAd, editingPricing, end, enqueueOrder, examModel, executeOrder, failCount, failOrder, fd, file, filled, finalExamModel, fmtDate, fmtHeartbeat, fmtMoney, fmtShortDate, fn, genRandomStr, getPlatformName, getRecommendation, hChecks, hNameMap, hOrder, healthAccountInput, healthAccountSaving, healthChecking, healthIntervalInput, healthIntervalSaving, healthPasswordInput, healthSummary, homeworkModel, html, imgTag, interval, isLoggedIn, jsChanged, jsChecked, jsFiles, jsRes, key, list, loadAccounts, loadAds, loadAgentFees, loadAgentStats, loadAgents, loadAgentsByTier, loadCommissions, loadDashboard, loadDeepseekKey, loadHealthAccount, loadHealthInterval, loadOrders, loadPairQr, loadPlatformNames, loadPricing, loadProxySettings, loadQueueData, loadRiskData, loadSubAdmins, loadTierCommissions, loadUnifiedUsers, loadUsers, loadWithdrawals, loadYpay, loadYpayOrders, loadingAccounts, loadingAds, loadingAgents, loadingAgentsByTier, loadingCommissions, loadingDash, loadingHealth, loadingOrders, loadingQueue, loadingRisk, loadingSubAdmins, loadingUnified, loadingUsers, loadingWithdrawals, loadingYpayOrders, loginErr, marketForm, maxBarOrders, maxBarRevenue, maxPartnerStatusCount, maxStatusCount, maxWorkersInput, mobileSidebarOpen, needAppid, needQrUrl, needRemark, newRate, newStatus, newSubAdmin, newTierLevel, nextSlot, ok, okCount, onAdFileChange, onAdImgChange, onQrFileChange, openAddAccount, openCreateAd, openEditAccount, openEditAd, openRateModal, openTierModal, openTopup, orderStatusClass, orderStatusLabel, orders, ordersStatusFilter, ordersTotal, packagePricing, pairQrImage, pairQrLoading, pairQrTs, params, partnerAgentStats, partnerAllowedTabs, passCount, pauseQueue, payTestAccountId, payTestBatchId, payTestChannelName, payTestChecks, payTestExpired, payTestLoading, payTestPaid, payTestPolling, payTestQrImage, payTestReallyPrice, payTestStarted, payTestTimer, payTestTradeNo, payTypeLabels, personnelTab, platformColors, platformNames, platforms, pricingModel, proxyForm, proxySaving, proxyTestOk, proxyTestResult, proxyTesting, pwForm, qrFileInput, qrUploading, queueJobs, queuePausing, queueStats, queueStatusFilter, r, rateTarget, reactivateAgent, reader, recommendResult, recommending, regenerateYpayKey, rejectWithdrawal, relImgs, removeDomain, res, resetAccountForm, resetYpayConnection, resumeQueue, retryQueueJob, riskAlerts, riskCheckStep, riskChecking, riskChecks, riskDomainStatus, riskHealth, riskIntervalInput, riskJsStatus, riskLoginAndCheck, riskLoginForm, riskLoginLoading, riskNeedLogin, riskScore, riskScoreColor, riskScoreDash, riskScoreDesc, riskScoreLevel, riskScoreText, role, runDomainCheck, runFullRiskCheck, runHealthCheck, runJsCheck, runYpayTest, s, saveAccount, saveAd, saveAgentFees, saveDeepseekKey, saveHealthAccount, saveHealthInterval, saveModels, savePricingConfig, saveProxy, saveRate, saveRiskInterval, saveTierCommissions, saveYpayKeyOnly, saveYpaySettings, savingAccount, savingAd, savingAgentFees, savingDeepseekKey, savingModels, savingPricing, savingTierCommissions, serverPublicIp, serverSpecs, setMaxWorkers, showAccountModal, showAdModal, showAddDomainModal, showCertFields, showChannelTest, showCreateSubAdmin, showDeepseekKey, showHealthSettings, showPayTest, showQrModal, showRateModal, showTierModal, showTopupModal, sidebarCollapsed, sidebarGroups, someUp, st, start, startChannelPayTest, startPayTestPolling, statusClass, statusLabel, stopPayTestPolling, subAdmins, suspendAgent, switchTab, t, ta, taskTypeNames, testChannel, testDeepseekApi, testModelApi, testProxy, testingDeepseek, testingModel, tierCommissions, tierNames, tierTarget, toggleAccount, toggleAdActive, toppingUp, toppupMode, topupAmount, topupNote, topupTarget, totalPlatformOrders, triggerAdFileUpload, triggerAdImgUpload, triggerQrUpload, typeLabels, unifiedAgentFilter, unifiedRoleFilter, unifiedSearch, unifiedStats, unifiedTotal, unifiedUsers, usedSlots, users, usersSubTab, usersTotal, val, visibleSidebarGroups, warnCount, withdrawalStatusFilter, withdrawals, withdrawalsTotal, wxAccounts, ypayAccounts, ypayForm, ypayLoaded, ypayOrderFilters, ypayOrderStatusFilter, ypayOrders, ypayOrdersPage, ypayOrdersTotal, ypaySaving, ypayStateLabels, ypayStatus, ypayTab, ypayTestResult, ypayTesting } = useAdminState()
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
        <button
          class="btn btn-ghost btn-sm"
          @click="showHealthSettings = true"
        >
          设置
        </button>
        <span
          v-if="riskChecking && riskCheckStep"
          class="risk-check-progress"
        >
          <span class="risk-check-spinner" />
          正在检查: {{ riskCheckStep }}
        </span>
      </div>

      <!-- 健康检查设置弹窗 -->
      <div
        v-if="showHealthSettings"
        class="modal-overlay"
        @click.self="showHealthSettings = false"
      >
        <div class="modal-box health-settings-modal">
          <div class="modal-header">
            <h3>健康检查设置</h3>
            <button
              class="modal-close"
              @click="showHealthSettings = false"
            >
              &times;
            </button>
          </div>
          <div class="modal-body">
            <div class="health-form-group">
              <label>检查间隔（秒）</label>
              <div style="display:flex;align-items:center;gap:8px;">
                <input
                  v-model.number="healthIntervalInput"
                  type="number"
                  min="300"
                  max="86400"
                  step="60"
                  class="health-form-input"
                  style="width:100px;"
                >
                <span style="font-size:12px;color:var(--text-secondary);">范围 300-86400</span>
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="healthIntervalSaving"
                  @click="saveHealthInterval"
                >
                  {{ healthIntervalSaving ? '保存中' : '保存' }}
                </button>
              </div>
            </div>

            <div class="health-form-group">
              <label>检测账号</label>
              <div class="health-add-row">
                <input
                  v-model="healthAccountInput"
                  type="text"
                  placeholder="学号"
                  class="health-form-input"
                >
                <input
                  v-model="healthPasswordInput"
                  type="password"
                  placeholder="密码"
                  class="health-form-input"
                >
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button
              class="btn btn-ghost btn-sm"
              @click="showHealthSettings = false"
            >
              取消
            </button>
            <button
              class="btn btn-primary btn-sm"
              :disabled="healthAccountSaving"
              @click="saveHealthAccount"
            >
              {{ healthAccountSaving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="riskNeedLogin"
      class="risk-login-card"
    >
      <div class="risk-login-title">
        需要登录测试账号
      </div>
      <div class="risk-login-desc">
        健康检查需要平台会话，请输入一个学生账号登录所有平台
      </div>
      <div class="risk-login-form">
        <input
          v-model="riskLoginForm.username"
          type="text"
          placeholder="学号/账号"
          class="risk-login-input"
          @keyup.enter="riskLoginAndCheck"
        >
        <input
          v-model="riskLoginForm.password"
          type="password"
          placeholder="密码"
          class="risk-login-input"
          @keyup.enter="riskLoginAndCheck"
        >
        <button
          class="btn btn-primary btn-sm"
          :disabled="riskLoginLoading"
          @click="riskLoginAndCheck"
        >
          {{ riskLoginLoading ? '登录并检查中...' : '登录并检查' }}
        </button>
        <button
          class="btn btn-ghost btn-sm"
          @click="riskNeedLogin = false"
        >
          取消
        </button>
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
              <div v-else-if="check.id.startsWith('health_')">
                <div
                  v-if="healthSummary?.platform_checks && Object.keys(healthSummary.platform_checks).length"
                  class="table-wrap"
                >
                  <table class="data-table data-table-sm">
                    <thead><tr><th>平台</th><th>检测账号</th><th>状态</th><th>详情</th></tr></thead>
                    <tbody>
                      <tr
                        v-for="(pc, wid) in healthSummary.platform_checks"
                        :key="wid"
                      >
                        <td>{{ pc.name || '平台' + wid }}</td>
                        <td style="font-size:12px;">
                          {{ pc.username || '-' }}
                        </td>
                        <td>
                          <span
                            v-if="pc.error && !Object.keys(pc.checks).length"
                            class="status-tag bad"
                          >登录失败</span>
                          <span
                            v-else
                            :class="['status-tag',
                                     (pc.checks[check.id.replace('health_', '')]?.status === 'healthy') ? 'ok' :
                                     (pc.checks[check.id.replace('health_', '')]?.status === 'warning') ? 'warn' :
                                     (pc.checks[check.id.replace('health_', '')]?.status === 'failed') ? 'bad' : 'unknown']"
                          >
                            {{ pc.checks[check.id.replace('health_', '')]?.status === 'healthy' ? '正常' :
                              pc.checks[check.id.replace('health_', '')]?.status === 'warning' ? '警告' :
                              pc.checks[check.id.replace('health_', '')]?.status === 'failed' ? '异常' : '未检测' }}
                          </span>
                        </td>
                        <td style="font-size:12px;">
                          {{ pc.error && !Object.keys(pc.checks).length ? pc.error : (pc.checks[check.id.replace('health_', '')]?.message || '-') }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div
                  v-else
                  style="font-size:13px;color:var(--text-secondary);padding:8px 0;"
                >
                  {{ check.desc || '无详细信息' }}
                </div>
              </div>
            </slot>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
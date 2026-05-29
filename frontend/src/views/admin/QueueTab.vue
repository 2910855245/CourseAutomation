<script setup lang="ts">
// @ts-nocheck
import { useAdminState } from './adminState'

const { DEEPSEEK_MODELS, acceptOrder, accountForm, accounts, active, activeTab, adFileInput, adFileUploading, adForm, adImgInput, addDomain, addDomainForm, adminPass, adminState, adminUser, adsList, agentFees, agentStats, agentStatusFilter, agentSubTab, agentTotal, agents, agentsByTier, alertCount, aliAccounts, all, allSidebarItems, allUp, applyAutoConcurrency, applyPackagePricing, applyingPackage, approveAgent, approveWithdrawal, base64, body, buildRiskChecks, cancelEditPricing, cancelQueueJob, deleteQueueJob, captchaAnswer, captchaImage, captchaLoading, captchaToken, cfg, changeAdminPassword, changingPw, channelCodeHelp, channelCodeLabels, channelTestAccount, channelTestAllOk, channelTestChecks, channelTestLoading, channelTestQrImage, chars, checks, circumference, clearCommissionHistory, clearDeepseekKey, clearOrderHistory, clearQueueHistory, clearRiskAlerts, clearWithdrawalHistory, clearYpayOrderHistory, closeAccountModal, closeExpiredYpayOrders, closePayTest, codeLabel, commissionTotal, commissions, completeOrder, configs, count, creatingSubAdmin, currentRole, d, dash, dashError, deepseekApiKey, deepseekKeyMasked, deepseekTestResult, defaultCodes, deleteAccount, deleteAd, detectServerSpecs, doChangeTier, doCreateSubAdmin, doRevokeSubAdmin, doTopup, domainCount, downloadQrImage, downloadQrLoading, dsRes, editPricing, editingAccount, editingAd, editingPricing, end, enqueueOrder, examModel, executeOrder, failCount, failOrder, fd, file, filled, finalExamModel, fmtDate, fmtHeartbeat, fmtMoney, fmtShortDate, fn, genRandomStr, getPlatformName, getRecommendation, hChecks, hNameMap, hOrder, healthAccountInput, healthAccountSaving, healthChecking, healthIntervalInput, healthIntervalSaving, healthPasswordInput, healthSummary, homeworkModel, html, imgTag, interval, isLoggedIn, jsChanged, jsChecked, jsFiles, jsRes, key, list, loadAccounts, loadAds, loadAgentFees, loadAgentStats, loadAgents, loadAgentsByTier, loadCommissions, loadDashboard, loadDeepseekKey, loadHealthAccount, loadHealthInterval, loadOrders, loadPairQr, loadPlatformNames, loadPricing, loadProxySettings, loadQueueData, loadRiskData, loadSubAdmins, loadTierCommissions, loadUnifiedUsers, loadUsers, loadWithdrawals, loadYpay, loadYpayOrders, loadingAccounts, loadingAds, loadingAgents, loadingAgentsByTier, loadingCommissions, loadingDash, loadingHealth, loadingOrders, loadingQueue, loadingRisk, loadingSubAdmins, loadingUnified, loadingUsers, loadingWithdrawals, loadingYpayOrders, loginErr, marketForm, maxBarOrders, maxBarRevenue, maxPartnerStatusCount, maxStatusCount, maxWorkersInput, mobileSidebarOpen, needAppid, needQrUrl, needRemark, newRate, newStatus, newSubAdmin, newTierLevel, nextSlot, ok, okCount, onAdFileChange, onAdImgChange, onQrFileChange, openAddAccount, openCreateAd, openEditAccount, openEditAd, openRateModal, openTierModal, openTopup, orderStatusClass, orderStatusLabel, orders, ordersStatusFilter, ordersTotal, packagePricing, pairQrImage, pairQrLoading, pairQrTs, params, partnerAgentStats, partnerAllowedTabs, passCount, pauseQueue, payTestAccountId, payTestBatchId, payTestChannelName, payTestChecks, payTestExpired, payTestLoading, payTestPaid, payTestPolling, payTestQrImage, payTestReallyPrice, payTestStarted, payTestTimer, payTestTradeNo, payTypeLabels, personnelTab, platformColors, platformNames, platforms, pricingModel, proxyForm, proxySaving, proxyTestOk, proxyTestResult, proxyTesting, pwForm, qrFileInput, qrUploading, queueFilter, queueJobs, queuePausing, queueStats, queueStatusFilter, r, rateTarget, reactivateAgent, reader, recommendResult, recommending, regenerateYpayKey, rejectWithdrawal, relImgs, removeDomain, res, resetAccountForm, resetYpayConnection, resumeQueue, retryQueueJob, riskAlerts, riskCheckStep, riskChecking, riskChecks, riskDomainStatus, riskHealth, riskIntervalInput, riskJsStatus, riskLoginAndCheck, riskLoginForm, riskLoginLoading, riskNeedLogin, riskScore, riskScoreColor, riskScoreDash, riskScoreDesc, riskScoreLevel, riskScoreText, role, runDomainCheck, runFullRiskCheck, runHealthCheck, runJsCheck, runYpayTest, s, saveAccount, saveAd, saveAgentFees, saveDeepseekKey, saveHealthAccount, saveHealthInterval, saveModels, savePricingConfig, saveProxy, saveRate, saveRiskInterval, saveTierCommissions, saveYpayKeyOnly, saveYpaySettings, savingAccount, savingAd, savingAgentFees, savingDeepseekKey, savingModels, savingPricing, savingTierCommissions, serverPublicIp, serverSpecs, setMaxWorkers, setQueueFilter, showAccountModal, showAdModal, showAddDomainModal, showCertFields, showChannelTest, showCreateSubAdmin, showDeepseekKey, showHealthSettings, showPayTest, showQrModal, showRateModal, showTierModal, showTopupModal, sidebarCollapsed, sidebarGroups, someUp, st, start, startChannelPayTest, startPayTestPolling, statusClass, statusLabel, stopPayTestPolling, subAdmins, suspendAgent, switchTab, t, ta, taskTypeNames, testChannel, testDeepseekApi, testModelApi, testProxy, testingDeepseek, testingModel, tierCommissions, tierNames, tierTarget, toggleAccount, toggleAdActive, toppingUp, toppupMode, topupAmount, topupNote, topupTarget, totalPlatformOrders, triggerAdFileUpload, triggerAdImgUpload, triggerQrUpload, typeLabels, unifiedAgentFilter, unifiedRoleFilter, unifiedSearch, unifiedStats, unifiedTotal, unifiedUsers, usedSlots, users, usersSubTab, usersTotal, val, visibleSidebarGroups, warnCount, withdrawalStatusFilter, withdrawals, withdrawalsTotal, wxAccounts, ypayAccounts, ypayForm, ypayLoaded, ypayOrderFilters, ypayOrderStatusFilter, ypayOrders, ypayOrdersPage, ypayOrdersTotal, ypaySaving, ypayStateLabels, ypayStatus, ypayTab, ypayTestResult, ypayTesting } = useAdminState()
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
            :class="queueStats.paused ? 'qsb-paused' : 'qsb-live'"
          />
          <span class="qsb-text">{{ queueStats.paused ? '全部已暂停' : '运行中' }}</span>
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
          max="20"
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
            {{ queueStats.active_workers || 0 }}
          </div>
          <div class="qkpi-label">
            工作线程
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
          class="btn btn-ghost btn-sm"
          style="margin-left:auto; color:#ef4444;"
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
              <th>任务ID</th><th>用户</th><th>订单编号</th><th v-if="queueFilter === ''">队列</th><th>状态</th><th>进度</th><th>创建时间</th><th>操作</th>
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
                    X
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
.action-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}
.action-slot {
  display: inline-flex;
  min-width: 32px;
}
.del-btn {
  margin-left: auto;
  color: #ccc;
  font-size: 11px;
  cursor: pointer;
  padding: 0 4px;
  border: none;
  background: none;
  line-height: 1;
}
.del-btn:hover {
  color: #ef4444;
}
</style>


<script setup lang="ts">
// @ts-nocheck
import { useAdminState } from './adminState'

const { DEEPSEEK_MODELS, acceptOrder, accountForm, accounts, active, activeTab, adFileInput, adFileUploading, adForm, adImgInput, addDomain, addDomainForm, adminPass, adminState, adminUser, adsList, agentFees, agentStats, agentStatusFilter, agentSubTab, agentTotal, agents, agentsByTier, alertCount, aliAccounts, all, allSidebarItems, allUp, applyAutoConcurrency, applyPackagePricing, applyingPackage, approveAgent, approveWithdrawal, base64, body, buildRiskChecks, cancelEditPricing, cancelQueueJob, captchaAnswer, captchaImage, captchaLoading, captchaToken, cfg, changeAdminPassword, changingPw, channelCodeHelp, channelCodeLabels, channelTestAccount, channelTestAllOk, channelTestChecks, channelTestLoading, channelTestQrImage, chars, checks, circumference, clearCommissionHistory, clearDeepseekKey, clearOrderHistory, clearQueueHistory, clearRiskAlerts, clearWithdrawalHistory, clearYpayOrderHistory, closeAccountModal, closeExpiredYpayOrders, closePayTest, codeLabel, commissionTotal, commissions, completeOrder, configs, count, creatingSubAdmin, currentRole, d, dash, dashError, deepseekApiKey, deepseekKeyMasked, deepseekTestResult, defaultCodes, deleteAccount, deleteAd, detectServerSpecs, doChangeTier, doCreateSubAdmin, doRevokeSubAdmin, doTopup, domainCount, downloadQrImage, downloadQrLoading, dsRes, editPricing, editingAccount, editingAd, editingPricing, end, enqueueOrder, examModel, executeOrder, failCount, failOrder, fd, file, filled, finalExamModel, fmtDate, fmtHeartbeat, fmtMoney, fmtShortDate, fn, genRandomStr, getPlatformName, getRecommendation, hChecks, hNameMap, hOrder, healthAccountInput, healthAccountSaving, healthChecking, healthIntervalInput, healthIntervalSaving, healthPasswordInput, healthSummary, homeworkModel, html, imgTag, interval, isLoggedIn, jsChanged, jsChecked, jsFiles, jsRes, key, list, loadAccounts, loadAds, loadAgentFees, loadAgentStats, loadAgents, loadAgentsByTier, loadCommissions, loadDashboard, loadDeepseekKey, loadHealthAccount, loadHealthInterval, loadOrders, loadPairQr, loadPlatformNames, loadPricing, loadProxySettings, loadQueueData, loadRiskData, loadSubAdmins, loadTierCommissions, loadUnifiedUsers, loadUsers, loadWithdrawals, loadYpay, loadYpayOrders, loadingAccounts, loadingAds, loadingAgents, loadingAgentsByTier, loadingCommissions, loadingDash, loadingHealth, loadingOrders, loadingQueue, loadingRisk, loadingSubAdmins, loadingUnified, loadingUsers, loadingWithdrawals, loadingYpayOrders, loginErr, marketForm, maxBarOrders, maxBarRevenue, maxPartnerStatusCount, maxStatusCount, maxWorkersInput, mobileSidebarOpen, needAppid, needQrUrl, needRemark, newRate, newStatus, newSubAdmin, newTierLevel, nextSlot, ok, okCount, onAdFileChange, onAdImgChange, onQrFileChange, openAddAccount, openCreateAd, openEditAccount, openEditAd, openRateModal, openTierModal, openTopup, orderStatusClass, orderStatusLabel, orders, ordersStatusFilter, ordersTotal, packagePricing, pairQrImage, pairQrLoading, pairQrTs, params, partnerAgentStats, partnerAllowedTabs, passCount, pauseQueue, payTestAccountId, payTestBatchId, payTestChannelName, payTestChecks, payTestExpired, payTestLoading, payTestPaid, payTestPolling, payTestQrImage, payTestReallyPrice, payTestStarted, payTestTimer, payTestTradeNo, payTypeLabels, personnelTab, platformColors, platformNames, platforms, pricingModel, proxyForm, proxySaving, proxyTestOk, proxyTestResult, proxyTesting, pwForm, qrFileInput, qrUploading, queueJobs, queuePausing, queueStats, queueStatusFilter, r, rateTarget, reactivateAgent, reader, recommendResult, recommending, regenerateYpayKey, rejectWithdrawal, relImgs, removeDomain, res, resetAccountForm, resetYpayConnection, resumeQueue, retryQueueJob, riskAlerts, riskCheckStep, riskChecking, riskChecks, riskDomainStatus, riskHealth, riskIntervalInput, riskJsStatus, riskLoginAndCheck, riskLoginForm, riskLoginLoading, riskNeedLogin, riskScore, riskScoreColor, riskScoreDash, riskScoreDesc, riskScoreLevel, riskScoreText, role, runDomainCheck, runFullRiskCheck, runHealthCheck, runJsCheck, runYpayTest, s, saveAccount, saveAd, saveAgentFees, saveDeepseekKey, saveHealthAccount, saveHealthInterval, saveModels, savePricingConfig, saveProxy, saveRate, saveRiskInterval, saveTierCommissions, saveYpayKeyOnly, saveYpaySettings, savingAccount, savingAd, savingAgentFees, savingDeepseekKey, savingModels, savingPricing, savingTierCommissions, serverPublicIp, serverSpecs, setMaxWorkers, showAccountModal, showAdModal, showAddDomainModal, showCertFields, showChannelTest, showCreateSubAdmin, showDeepseekKey, showHealthSettings, showPayTest, showQrModal, showRateModal, showTierModal, showTopupModal, sidebarCollapsed, sidebarGroups, someUp, st, start, startChannelPayTest, startPayTestPolling, statusClass, statusLabel, stopPayTestPolling, subAdmins, suspendAgent, switchTab, t, ta, taskTypeNames, testChannel, testDeepseekApi, testModelApi, testProxy, testingDeepseek, testingModel, tierCommissions, tierNames, tierTarget, toggleAccount, toggleAdActive, toppingUp, toppupMode, topupAmount, topupNote, topupTarget, totalPlatformOrders, triggerAdFileUpload, triggerAdImgUpload, triggerQrUpload, typeLabels, unifiedAgentFilter, unifiedRoleFilter, unifiedSearch, unifiedStats, unifiedTotal, unifiedUsers, usedSlots, users, usersSubTab, usersTotal, val, visibleSidebarGroups, warnCount, withdrawalStatusFilter, withdrawals, withdrawalsTotal, wxAccounts, ypayAccounts, ypayForm, ypayLoaded, ypayOrderFilters, ypayOrderStatusFilter, ypayOrders, ypayOrdersPage, ypayOrdersTotal, ypaySaving, ypayStateLabels, ypayStatus, ypayTab, ypayTestResult, ypayTesting } = useAdminState()
</script>

<template>
  <div>
    <div class="section-actions">
      <div class="filter-group">
        <button
          :class="['chip', { active: withdrawalStatusFilter === '' }]"
          @click="withdrawalStatusFilter = ''; loadWithdrawals()"
        >
          全部
        </button>
        <button
          :class="['chip', { active: withdrawalStatusFilter === 'pending' }]"
          @click="withdrawalStatusFilter = 'pending'; loadWithdrawals()"
        >
          待审核
        </button>
        <button
          :class="['chip', { active: withdrawalStatusFilter === 'completed' }]"
          @click="withdrawalStatusFilter = 'completed'; loadWithdrawals()"
        >
          已完成
        </button>
        <button
          :class="['chip', { active: withdrawalStatusFilter === 'rejected' }]"
          @click="withdrawalStatusFilter = 'rejected'; loadWithdrawals()"
        >
          已拒绝
        </button>
      </div>
      <span class="total-label">共 {{ withdrawalsTotal }} 条</span>
      <button
        class="btn btn-ghost"
        :disabled="loadingWithdrawals"
        @click="loadWithdrawals"
      >
        刷新
      </button>
      <button
        class="btn btn-ghost btn-sm"
        style="color:#ef4444;"
        @click="clearWithdrawalHistory"
      >
        清除历史
      </button>
    </div>

    <div
      v-if="withdrawals.length > 0"
      class="table-wrap"
    >
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th><th>代理</th><th>金额</th><th>收款码</th><th>状态</th><th>申请时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="w in withdrawals"
            :key="w.withdrawal_id"
          >
            <td><code class="code-tag">{{ w.withdrawal_id.slice(0,12) }}</code></td>
            <td>{{ w.agent_display_name || w.agent_id?.slice(0, 8) }}</td>
            <td class="money-cell">
              {{ fmtMoney(w.amount) }}
            </td>
            <td>
              <img
                v-if="w.wechat_qr"
                :src="w.wechat_qr"
                class="qr-thumb"
                title="点击查看大图"
                @click="showQrModal = w.wechat_qr"
              >
              <span
                v-else
                style="color:#94a3b8;font-size:12px"
              >未上传</span>
            </td>
            <td>
              <span :class="['status-tag', w.status === 'completed' ? 'ok' : w.status === 'rejected' ? 'bad' : w.status === 'pending' ? 'warn' : 'muted']">
                {{ w.status === 'completed' ? '已完成' : w.status === 'rejected' ? '已拒绝' : w.status === 'pending' ? '待审核' : w.status }}
              </span>
            </td>
            <td>{{ w.admin_note || '-' }}</td>
            <td class="date-cell">
              {{ fmtDate(w.created_at) }}
            </td>
            <td>
              <div
                v-if="w.status === 'pending'"
                class="action-group"
              >
                <button
                  class="btn btn-xs btn-success"
                  @click="approveWithdrawal(w.withdrawal_id)"
                >
                  通过
                </button>
                <button
                  class="btn btn-xs btn-danger"
                  @click="rejectWithdrawal(w.withdrawal_id)"
                >
                  拒绝
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div
      v-else-if="!loadingWithdrawals"
      class="empty"
    >
      <p>暂无提现记录</p>
    </div>
  </div>
</template>
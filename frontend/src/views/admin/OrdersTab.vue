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
        class="btn btn-ghost btn-sm"
        style="color:#ef4444;"
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
                  v-if="o.status === 'pending'"
                  class="btn btn-xs btn-success"
                  @click="acceptOrder(o.order_id)"
                >
                  接单
                </button>
                <button
                  v-if="(o.status === 'pending' || o.status === 'accepted') && currentRole === 'admin'"
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
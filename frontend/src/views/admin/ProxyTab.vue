<script setup lang="ts">
// @ts-nocheck
import { useAdminState } from './adminState'

const { DEEPSEEK_MODELS, acceptOrder, accountForm, accounts, active, activeTab, adFileInput, adFileUploading, adForm, adImgInput, addDomain, addDomainForm, adminPass, adminState, adminUser, adsList, agentFees, agentStats, agentStatusFilter, agentSubTab, agentTotal, agents, agentsByTier, alertCount, aliAccounts, all, allSidebarItems, allUp, applyAutoConcurrency, applyPackagePricing, applyingPackage, approveAgent, approveWithdrawal, base64, body, buildRiskChecks, cancelEditPricing, cancelQueueJob, captchaAnswer, captchaImage, captchaLoading, captchaToken, cfg, changeAdminPassword, changingPw, channelCodeHelp, channelCodeLabels, channelTestAccount, channelTestAllOk, channelTestChecks, channelTestLoading, channelTestQrImage, chars, checks, circumference, clearCommissionHistory, clearDeepseekKey, clearOrderHistory, clearQueueHistory, clearRiskAlerts, clearWithdrawalHistory, clearYpayOrderHistory, closeAccountModal, closeExpiredYpayOrders, closePayTest, codeLabel, commissionTotal, commissions, completeOrder, configs, count, creatingSubAdmin, currentRole, d, dash, dashError, deepseekApiKey, deepseekKeyMasked, deepseekTestResult, defaultCodes, deleteAccount, deleteAd, detectServerSpecs, doChangeTier, doCreateSubAdmin, doRevokeSubAdmin, doTopup, domainCount, downloadQrImage, downloadQrLoading, dsRes, editPricing, editingAccount, editingAd, editingPricing, end, enqueueOrder, examModel, executeOrder, failCount, failOrder, fd, file, filled, finalExamModel, fmtDate, fmtHeartbeat, fmtMoney, fmtShortDate, fn, genRandomStr, getPlatformName, getRecommendation, hChecks, hNameMap, hOrder, healthAccountInput, healthAccountSaving, healthChecking, healthIntervalInput, healthIntervalSaving, healthPasswordInput, healthSummary, homeworkModel, html, imgTag, interval, isLoggedIn, jsChanged, jsChecked, jsFiles, jsRes, key, list, loadAccounts, loadAds, loadAgentFees, loadAgentStats, loadAgents, loadAgentsByTier, loadCommissions, loadDashboard, loadDeepseekKey, loadHealthAccount, loadHealthInterval, loadOrders, loadPairQr, loadPlatformNames, loadPricing, loadProxySettings, loadQueueData, loadRiskData, loadSubAdmins, loadTierCommissions, loadUnifiedUsers, loadUsers, loadWithdrawals, loadYpay, loadYpayOrders, loadingAccounts, loadingAds, loadingAgents, loadingAgentsByTier, loadingCommissions, loadingDash, loadingHealth, loadingOrders, loadingQueue, loadingRisk, loadingSubAdmins, loadingUnified, loadingUsers, loadingWithdrawals, loadingYpayOrders, loginErr, marketForm, maxBarOrders, maxBarRevenue, maxPartnerStatusCount, maxStatusCount, maxWorkersInput, mobileSidebarOpen, needAppid, needQrUrl, needRemark, newRate, newStatus, newSubAdmin, newTierLevel, nextSlot, ok, okCount, onAdFileChange, onAdImgChange, onQrFileChange, openAddAccount, openCreateAd, openEditAccount, openEditAd, openRateModal, openTierModal, openTopup, orderStatusClass, orderStatusLabel, orders, ordersStatusFilter, ordersTotal, packagePricing, pairQrImage, pairQrLoading, pairQrTs, params, partnerAgentStats, partnerAllowedTabs, passCount, pauseQueue, payTestAccountId, payTestBatchId, payTestChannelName, payTestChecks, payTestExpired, payTestLoading, payTestPaid, payTestPolling, payTestQrImage, payTestReallyPrice, payTestStarted, payTestTimer, payTestTradeNo, payTypeLabels, personnelTab, platformColors, platformNames, platforms, pricingModel, proxyForm, proxySaving, proxyTestOk, proxyTestResult, proxyTesting, pwForm, qrFileInput, qrUploading, queueJobs, queuePausing, queueStats, queueStatusFilter, r, rateTarget, reactivateAgent, reader, recommendResult, recommending, regenerateYpayKey, rejectWithdrawal, relImgs, removeDomain, res, resetAccountForm, resetYpayConnection, resumeQueue, retryQueueJob, riskAlerts, riskCheckStep, riskChecking, riskChecks, riskDomainStatus, riskHealth, riskIntervalInput, riskJsStatus, riskLoginAndCheck, riskLoginForm, riskLoginLoading, riskNeedLogin, riskScore, riskScoreColor, riskScoreDash, riskScoreDesc, riskScoreLevel, riskScoreText, role, runDomainCheck, runFullRiskCheck, runHealthCheck, runJsCheck, runYpayTest, s, saveAccount, saveAd, saveAgentFees, saveDeepseekKey, saveHealthAccount, saveHealthInterval, saveModels, savePricingConfig, saveProxy, saveRate, saveRiskInterval, saveTierCommissions, saveYpayKeyOnly, saveYpaySettings, savingAccount, savingAd, savingAgentFees, savingDeepseekKey, savingModels, savingPricing, savingTierCommissions, serverPublicIp, serverSpecs, setMaxWorkers, showAccountModal, showAdModal, showAddDomainModal, showCertFields, showChannelTest, showCreateSubAdmin, showDeepseekKey, showHealthSettings, showPayTest, showQrModal, showRateModal, showTierModal, showTopupModal, sidebarCollapsed, sidebarGroups, someUp, st, start, startChannelPayTest, startPayTestPolling, statusClass, statusLabel, stopPayTestPolling, subAdmins, suspendAgent, switchTab, t, ta, taskTypeNames, testChannel, testDeepseekApi, testModelApi, testProxy, testingDeepseek, testingModel, tierCommissions, tierNames, tierTarget, toggleAccount, toggleAdActive, toppingUp, toppupMode, topupAmount, topupNote, topupTarget, totalPlatformOrders, triggerAdFileUpload, triggerAdImgUpload, triggerQrUpload, typeLabels, unifiedAgentFilter, unifiedRoleFilter, unifiedSearch, unifiedStats, unifiedTotal, unifiedUsers, usedSlots, users, usersSubTab, usersTotal, val, visibleSidebarGroups, warnCount, withdrawalStatusFilter, withdrawals, withdrawalsTotal, wxAccounts, ypayAccounts, ypayForm, ypayLoaded, ypayOrderFilters, ypayOrderStatusFilter, ypayOrders, ypayOrdersPage, ypayOrdersTotal, ypaySaving, ypayStateLabels, ypayStatus, ypayTab, ypayTestResult, ypayTesting } = useAdminState()
</script>

<template>
  <div class="proxy-tab">
    <div class="settings-card">
      <h3>隧道代理</h3>
      <p class="settings-hint">
        所有刷课请求走代理出口，防止服务器 IP 被目标平台封禁
      </p>

      <div class="proxy-toggle-row">
        <span class="proxy-toggle-label">启用代理</span>
        <label class="toggle-switch">
          <input
            v-model="proxyForm.enabled"
            type="checkbox"
          >
          <span class="toggle-slider" />
        </label>
      </div>

      <div class="field">
        <label>代理地址</label>
        <input
          v-model="proxyForm.url"
          type="text"
          placeholder="http://隧道地址:端口"
          :disabled="!proxyForm.enabled"
        >
      </div>
      <div class="field-row">
        <div class="field">
          <label>用户名（选填）</label>
          <input
            v-model="proxyForm.username"
            type="text"
            placeholder="代理认证用户名"
            :disabled="!proxyForm.enabled"
          >
        </div>
        <div class="field">
          <label>密码（选填）</label>
          <input
            v-model="proxyForm.password"
            type="password"
            placeholder="代理认证密码"
            :disabled="!proxyForm.enabled"
          >
        </div>
      </div>
      <div class="proxy-actions">
        <button
          class="btn btn-ghost"
          :disabled="proxyTesting || !proxyForm.enabled"
          @click="testProxy"
        >
          {{ proxyTesting ? '测试中...' : '测试连接' }}
        </button>
        <button
          class="btn btn-primary"
          :disabled="proxySaving"
          @click="saveProxy"
        >
          {{ proxySaving ? '保存中...' : '保存设置' }}
        </button>
      </div>
      <div
        v-if="proxyTestResult"
        class="proxy-test-result"
        :class="{ ok: proxyTestOk }"
      >
        {{ proxyTestResult }}
      </div>
    </div>

    <div class="settings-card">
      <details class="guide-details">
        <summary>使用教程</summary>
        <div class="proxy-guide">
          <div class="guide-step">
            <strong>1.</strong> 搜索"隧道代理"购买，推荐：芝麻代理、快代理、站大爷，月付 50-100 元。
          </div>
          <div class="guide-step">
            <strong>2.</strong> 获取代理地址，格式如 <code>http://user:pass@tunnel.provider.com:8888</code>，拆分填入上方。
          </div>
          <div class="guide-step">
            <strong>3.</strong> 在代理后台将服务器 IP <code class="code-warn">{{ serverPublicIp || '...' }}</code> 加白名单。
          </div>
          <div class="guide-step">
            <strong>4.</strong> 点击"测试连接"验证代理可用。
          </div>
          <div class="guide-step">
            <strong>5.</strong> 打开开关并保存，之后 worker 所有请求自动走代理。
          </div>
        </div>
      </details>
    </div>
  </div>
</template>
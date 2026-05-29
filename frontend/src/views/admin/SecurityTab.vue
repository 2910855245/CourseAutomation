<script setup lang="ts">
// @ts-nocheck
import { useAdminState } from './adminState'

const { DEEPSEEK_MODELS, acceptOrder, accountForm, accounts, active, activeTab, adFileInput, adFileUploading, adForm, adImgInput, addDomain, addDomainForm, adminPass, adminState, adminUser, adsList, agentFees, agentStats, agentStatusFilter, agentSubTab, agentTotal, agents, agentsByTier, alertCount, aliAccounts, all, allSidebarItems, allUp, applyAutoConcurrency, applyPackagePricing, applyingPackage, approveAgent, approveWithdrawal, base64, body, buildRiskChecks, cancelEditPricing, cancelQueueJob, captchaAnswer, captchaImage, captchaLoading, captchaToken, cfg, changeAdminPassword, changingPw, chaoxingModel, channelCodeHelp, channelCodeLabels, channelTestAccount, channelTestAllOk, channelTestChecks, channelTestLoading, channelTestQrImage, chars, checks, circumference, clearCommissionHistory, clearDeepseekKey, clearOrderHistory, clearQueueHistory, clearRiskAlerts, clearWithdrawalHistory, clearYpayOrderHistory, closeAccountModal, closeExpiredYpayOrders, closePayTest, codeLabel, commissionTotal, commissions, completeOrder, configs, count, creatingSubAdmin, currentRole, d, dash, dashError, deepseekApiKey, deepseekKeyMasked, deepseekTestResult, defaultCodes, deleteAccount, deleteAd, detectServerSpecs, doChangeTier, doCreateSubAdmin, doRevokeSubAdmin, doTopup, domainCount, downloadQrImage, downloadQrLoading, dsRes, editPricing, editingAccount, editingAd, editingPricing, end, enqueueOrder, examModel, executeOrder, failCount, failOrder, fd, file, filled, finalExamModel, fmtDate, fmtHeartbeat, fmtMoney, fmtShortDate, fn, genRandomStr, getPlatformName, getRecommendation, hChecks, hNameMap, hOrder, healthAccountInput, healthAccountSaving, healthChecking, healthIntervalInput, healthIntervalSaving, healthPasswordInput, healthSummary, homeworkModel, html, imgTag, interval, isLoggedIn, jsChanged, jsChecked, jsFiles, jsRes, key, list, loadAccounts, loadAds, loadAgentFees, loadAgentStats, loadAgents, loadAgentsByTier, loadCommissions, loadDashboard, loadDeepseekKey, loadHealthAccount, loadHealthInterval, loadOrders, loadPairQr, loadPlatformNames, loadPricing, loadProxySettings, loadQueueData, loadRiskData, loadSubAdmins, loadTierCommissions, loadUnifiedUsers, loadUsers, loadWithdrawals, loadYpay, loadYpayOrders, loadingAccounts, loadingAds, loadingAgents, loadingAgentsByTier, loadingCommissions, loadingDash, loadingHealth, loadingOrders, loadingQueue, loadingRisk, loadingSubAdmins, loadingUnified, loadingUsers, loadingWithdrawals, loadingYpayOrders, loginErr, marketForm, maxBarOrders, maxBarRevenue, maxPartnerStatusCount, maxStatusCount, maxWorkersInput, mobileSidebarOpen, needAppid, needQrUrl, needRemark, newRate, newStatus, newSubAdmin, newTierLevel, nextSlot, ok, okCount, onAdFileChange, onAdImgChange, onQrFileChange, openAddAccount, openCreateAd, openEditAccount, openEditAd, openRateModal, openTierModal, openTopup, orderStatusClass, orderStatusLabel, orders, ordersStatusFilter, ordersTotal, packagePricing, pairQrImage, pairQrLoading, pairQrTs, params, partnerAgentStats, partnerAllowedTabs, passCount, pauseQueue, payTestAccountId, payTestBatchId, payTestChannelName, payTestChecks, payTestExpired, payTestLoading, payTestPaid, payTestPolling, payTestQrImage, payTestReallyPrice, payTestStarted, payTestTimer, payTestTradeNo, payTypeLabels, personnelTab, platformColors, platformNames, platforms, pricingModel, proxyForm, proxySaving, proxyTestOk, proxyTestResult, proxyTesting, pwForm, qrFileInput, qrUploading, queueJobs, queuePausing, queueStats, queueStatusFilter, r, rateTarget, reactivateAgent, reader, recommendResult, recommending, regenerateYpayKey, rejectWithdrawal, relImgs, removeDomain, res, resetAccountForm, resetYpayConnection, resumeQueue, retryQueueJob, riskAlerts, riskCheckStep, riskChecking, riskChecks, riskDomainStatus, riskHealth, riskIntervalInput, riskJsStatus, riskLoginAndCheck, riskLoginForm, riskLoginLoading, riskNeedLogin, riskScore, riskScoreColor, riskScoreDash, riskScoreDesc, riskScoreLevel, riskScoreText, role, runDomainCheck, runFullRiskCheck, runHealthCheck, runJsCheck, runYpayTest, s, saveAccount, saveAd, saveAgentFees, saveDeepseekKey, saveHealthAccount, saveHealthInterval, saveModels, savePricingConfig, saveProxy, saveRate, saveRiskInterval, saveTierCommissions, saveYpayKeyOnly, saveYpaySettings, savingAccount, savingAd, savingAgentFees, savingDeepseekKey, savingModels, savingPricing, savingTierCommissions, serverPublicIp, serverSpecs, setMaxWorkers, showAccountModal, showAdModal, showAddDomainModal, showCertFields, showChannelTest, showCreateSubAdmin, showDeepseekKey, showHealthSettings, showPayTest, showQrModal, showRateModal, showTierModal, showTopupModal, sidebarCollapsed, sidebarGroups, someUp, st, start, startChannelPayTest, startPayTestPolling, statusClass, statusLabel, stopPayTestPolling, subAdmins, suspendAgent, switchTab, t, ta, taskTypeNames, testChannel, testDeepseekApi, testModelApi, testProxy, testingDeepseek, testingModel, tierCommissions, tierNames, tierTarget, toggleAccount, toggleAdActive, toppingUp, toppupMode, topupAmount, topupNote, topupTarget, totalPlatformOrders, triggerAdFileUpload, triggerAdImgUpload, triggerQrUpload, typeLabels, unifiedAgentFilter, unifiedRoleFilter, unifiedSearch, unifiedStats, unifiedTotal, unifiedUsers, usedSlots, users, usersSubTab, usersTotal, val, visibleSidebarGroups, warnCount, withdrawalStatusFilter, withdrawals, withdrawalsTotal, wxAccounts, ypayAccounts, ypayForm, ypayLoaded, ypayOrderFilters, ypayOrderStatusFilter, ypayOrders, ypayOrdersPage, ypayOrdersTotal, ypaySaving, ypayStateLabels, ypayStatus, ypayTab, ypayTestResult, ypayTesting } = useAdminState()
</script>

<template>
  <div class="security-tab">
    <div
      v-if="currentRole === 'admin'"
      class="settings-card"
    >
      <h3>DeepSeek AI 配置</h3>

      <!-- API Key -->
      <div class="ai-section">
        <div class="ai-section-label">
          API Key
        </div>
        <div class="ai-row">
          <div class="ai-key-wrap">
            <span
              v-if="deepseekKeyMasked"
              class="ai-key-badge on"
            >已配置</span>
            <span
              v-else
              class="ai-key-badge off"
            >未配置</span>
            <span class="ai-key-val">{{ deepseekKeyMasked || 'sk-****' }}</span>
          </div>
          <div class="ai-key-input-group">
            <input
              v-model="deepseekApiKey"
              :type="showDeepseekKey ? 'text' : 'password'"
              placeholder="输入新 Key 覆盖..."
              autocomplete="off"
              class="ai-key-input"
            >
            <button
              class="btn btn-ghost btn-xs"
              type="button"
              @click="showDeepseekKey = !showDeepseekKey"
            >
              {{ showDeepseekKey ? '隐藏' : '显示' }}
            </button>
            <button
              class="btn btn-primary btn-sm"
              :disabled="savingDeepseekKey"
              @click="saveDeepseekKey"
            >
              {{ savingDeepseekKey ? '...' : '保存' }}
            </button>
            <button
              v-if="deepseekKeyMasked"
              class="btn btn-ghost btn-sm"
              :disabled="savingDeepseekKey"
              @click="clearDeepseekKey"
            >
              清除
            </button>
          </div>
        </div>
        <div class="ai-row-bottom">
          <a
            class="ai-link"
            href="https://platform.deepseek.com/"
            target="_blank"
            rel="noopener"
          >获取 Key</a>
          <button
            class="btn-link"
            :disabled="testingDeepseek"
            @click="testDeepseekApi"
          >
            {{ testingDeepseek ? '检测中...' : '一键检查' }}
          </button>
          <span
            v-if="deepseekTestResult"
            :class="deepseekTestResult.api_ok ? 'ai-status-ok' : 'ai-status-fail'"
          >
            {{ deepseekTestResult.api_ok ? `连通 (${deepseekTestResult.latency_ms}ms)` : deepseekTestResult.error || '连接失败' }}
          </span>
        </div>
      </div>

      <!-- 模型分配 -->
      <div class="ai-section">
        <div class="ai-section-label">
          模型分配
        </div>
        <div class="ai-model-grid">
          <div class="ai-model-card">
            <div class="ai-model-head">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              ><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" /></svg>
              期末考试
            </div>
            <select
              v-model="finalExamModel"
              class="ai-model-select"
            >
              <option
                v-for="m in DEEPSEEK_MODELS"
                :key="m.value"
                :value="m.value"
              >
                {{ m.label }}
              </option>
            </select>
            <div class="ai-model-foot">
              <span class="ai-model-desc">{{ DEEPSEEK_MODELS.find(m => m.value === finalExamModel)?.desc }}</span>
              <button
                class="btn-link"
                :disabled="testingModel === finalExamModel"
                @click="testModelApi(finalExamModel)"
              >
                {{ testingModel === finalExamModel ? '...' : '测试' }}
              </button>
            </div>
          </div>
          <div class="ai-model-card">
            <div class="ai-model-head">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              ><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" /></svg>
              平时作业
            </div>
            <select
              v-model="homeworkModel"
              class="ai-model-select"
            >
              <option
                v-for="m in DEEPSEEK_MODELS"
                :key="m.value"
                :value="m.value"
              >
                {{ m.label }}
              </option>
            </select>
            <div class="ai-model-foot">
              <span class="ai-model-desc">{{ DEEPSEEK_MODELS.find(m => m.value === homeworkModel)?.desc }}</span>
              <button
                class="btn-link"
                :disabled="testingModel === homeworkModel"
                @click="testModelApi(homeworkModel)"
              >
                {{ testingModel === homeworkModel ? '...' : '测试' }}
              </button>
            </div>
          </div>
          <div class="ai-model-card">
            <div class="ai-model-head">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 10.5V6a2 2 0 00-2-2H4a2 2 0 00-2 2v12a2 2 0 002 2h7"/><path d="M22 10.5L12 16l-3-1.7"/><path d="M12 16v5"/><path d="M22 10.5V12"/></svg>
              学习通
            </div>
            <select v-model="chaoxingModel" class="ai-model-select">
              <option v-for="m in DEEPSEEK_MODELS" :key="m.value" :value="m.value">{{ m.label }}</option>
            </select>
            <div class="ai-model-foot">
              <span class="ai-model-desc">{{ DEEPSEEK_MODELS.find(m => m.value === chaoxingModel)?.desc }}</span>
              <button class="btn-link" :disabled="testingModel === chaoxingModel" @click="testModelApi(chaoxingModel)">{{ testingModel === chaoxingModel ? '...' : '测试' }}</button>
            </div>
          </div>
          <div class="ai-model-card">
            <div class="ai-model-head">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              ><path d="M12 2a5 5 0 015 5v3H7V7a5 5 0 015-5z" /><rect
                x="3"
                y="10"
                width="18"
                height="12"
                rx="2"
              /><circle
                cx="12"
                cy="16"
                r="2"
              /></svg>
              定价顾问
            </div>
            <select
              v-model="pricingModel"
              class="ai-model-select"
            >
              <option
                v-for="m in DEEPSEEK_MODELS"
                :key="m.value"
                :value="m.value"
              >
                {{ m.label }}
              </option>
            </select>
            <div class="ai-model-foot">
              <span class="ai-model-desc">{{ DEEPSEEK_MODELS.find(m => m.value === pricingModel)?.desc }}</span>
              <button
                class="btn-link"
                :disabled="testingModel === pricingModel"
                @click="testModelApi(pricingModel)"
              >
                {{ testingModel === pricingModel ? '...' : '测试' }}
              </button>
            </div>
          </div>
        </div>
        <button
          class="btn btn-primary btn-sm"
          :disabled="savingModels"
          style="margin-top:12px"
          @click="saveModels"
        >
          {{ savingModels ? '保存中...' : '保存模型' }}
        </button>
      </div>
    </div>

    <div class="settings-card">
      <h3>修改管理员密码</h3>
      <p class="settings-hint">
        修改后需要重新登录
      </p>
      <div class="field">
        <label>原密码</label>
        <input
          v-model="pwForm.old_password"
          type="password"
          placeholder="输入当前密码"
          autocomplete="current-password"
        >
      </div>
      <div class="field">
        <label>新密码</label>
        <input
          v-model="pwForm.new_password"
          type="password"
          placeholder="至少6位"
          autocomplete="new-password"
        >
      </div>
      <div class="field">
        <label>确认新密码</label>
        <input
          v-model="pwForm.confirm_password"
          type="password"
          placeholder="再次输入新密码"
          autocomplete="new-password"
        >
      </div>
      <button
        class="btn btn-primary"
        :disabled="changingPw"
        @click="changeAdminPassword"
      >
        {{ changingPw ? '处理中...' : '修改密码' }}
      </button>
    </div>
  </div>
</template>
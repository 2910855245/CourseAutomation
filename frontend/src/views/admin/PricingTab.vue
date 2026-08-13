<script setup lang="ts">
// @ts-nocheck
import { useAdminState } from './adminState'

const { DEEPSEEK_MODELS, acceptOrder, accountForm, accounts, active, activeTab, adFileInput, adFileUploading, adForm, adImgInput, addDomain, addDomainForm, adminPass, adminState, adminUser, adsList, agentFees, agentStats, agentStatusFilter, agentSubTab, agentTotal, agents, agentsByTier, alertCount, aliAccounts, all, allSidebarItems, allUp, applyAutoConcurrency, applyPackagePricing, applyingPackage, approveAgent, approveWithdrawal, base64, body, buildRiskChecks, cancelEditPricing, cancelQueueJob, captchaAnswer, captchaImage, captchaLoading, captchaToken, cfg, changeAdminPassword, changingPw, channelCodeHelp, channelCodeLabels, channelTestAccount, channelTestAllOk, channelTestChecks, channelTestLoading, channelTestQrImage, chars, checks, circumference, clearCommissionHistory, clearDeepseekKey, clearOrderHistory, clearQueueHistory, clearRiskAlerts, clearWithdrawalHistory, clearYpayOrderHistory, closeAccountModal, closeExpiredYpayOrders, closePayTest, codeLabel, commissionTotal, commissions, completeOrder, configs, count, creatingSubAdmin, currentRole, d, dash, dashError, deepseekApiKey, deepseekKeyMasked, deepseekTestResult, defaultCodes, deleteAccount, deleteAd, detectServerSpecs, doChangeTier, doCreateSubAdmin, doRevokeSubAdmin, doTopup, domainCount, downloadQrImage, downloadQrLoading, dsRes, editPricing, editingAccount, editingAd, editingPricing, end, enqueueOrder, examModel, executeOrder, failCount, failOrder, fd, file, filled, finalExamModel, fmtDate, fmtHeartbeat, fmtMoney, fmtShortDate, fn, genRandomStr, getPlatformName, getRecommendation, hChecks, hNameMap, hOrder, healthAccountInput, healthAccountSaving, healthChecking, healthIntervalInput, healthIntervalSaving, healthPasswordInput, healthSummary, homeworkModel, html, imgTag, interval, isLoggedIn, jsChanged, jsChecked, jsFiles, jsRes, key, list, loadAccounts, loadAds, loadAgentFees, loadAgentStats, loadAgents, loadAgentsByTier, loadCommissions, loadDashboard, loadDeepseekKey, loadHealthAccount, loadHealthInterval, loadOrders, loadPairQr, loadPlatformNames, loadPricing, loadProxySettings, loadQueueData, loadRiskData, loadSubAdmins, loadTierCommissions, loadUnifiedUsers, loadUsers, loadWithdrawals, loadYpay, loadYpayOrders, loadingAccounts, loadingAds, loadingAgents, loadingAgentsByTier, loadingCommissions, loadingDash, loadingHealth, loadingOrders, loadingQueue, loadingRisk, loadingSubAdmins, loadingUnified, loadingUsers, loadingWithdrawals, loadingYpayOrders, loginErr, marketForm, maxBarOrders, maxBarRevenue, maxPartnerStatusCount, maxStatusCount, maxWorkersInput, mobileSidebarOpen, needAppid, needQrUrl, needRemark, newRate, newStatus, newSubAdmin, newTierLevel, nextSlot, ok, okCount, onAdFileChange, onAdImgChange, onQrFileChange, openAddAccount, openCreateAd, openEditAccount, openEditAd, openRateModal, openTierModal, openTopup, orderStatusClass, orderStatusLabel, orders, ordersStatusFilter, ordersTotal, packagePricing, pairQrImage, pairQrLoading, pairQrTs, params, partnerAgentStats, partnerAllowedTabs, passCount, pauseQueue, payTestAccountId, payTestBatchId, payTestChannelName, payTestChecks, payTestExpired, payTestLoading, payTestPaid, payTestPolling, payTestQrImage, payTestReallyPrice, payTestStarted, payTestTimer, payTestTradeNo, payTypeLabels, personnelTab, platformColors, platformNames, platforms, pricingModel, proxyForm, proxySaving, proxyTestOk, proxyTestResult, proxyTesting, pwForm, qrFileInput, qrUploading, queueJobs, queuePausing, queueStats, queueStatusFilter, r, rateTarget, reactivateAgent, reader, recommendResult, recommending, regenerateYpayKey, rejectWithdrawal, relImgs, removeDomain, res, resetAccountForm, resetYpayConnection, resumeQueue, retryQueueJob, riskAlerts, riskCheckStep, riskChecking, riskChecks, riskDomainStatus, riskHealth, riskIntervalInput, riskJsStatus, riskLoginAndCheck, riskLoginForm, riskLoginLoading, riskNeedLogin, riskScore, riskScoreColor, riskScoreDash, riskScoreDesc, riskScoreLevel, riskScoreText, role, runDomainCheck, runFullRiskCheck, runHealthCheck, runJsCheck, runYpayTest, s, saveAccount, saveAd, saveAgentFees, saveDeepseekKey, saveHealthAccount, saveHealthInterval, saveModels, savePricingConfig, saveProxy, saveRate, saveRiskInterval, saveTierCommissions, saveYpayKeyOnly, saveYpaySettings, savingAccount, savingAd, savingAgentFees, savingDeepseekKey, savingModels, savingPricing, savingTierCommissions, serverPublicIp, serverSpecs, setMaxWorkers, showAccountModal, showAdModal, showAddDomainModal, showCertFields, showChannelTest, showCreateSubAdmin, showDeepseekKey, showHealthSettings, showPayTest, showQrModal, showRateModal, showTierModal, showTopupModal, sidebarCollapsed, sidebarGroups, someUp, st, start, startChannelPayTest, startPayTestPolling, statusClass, statusLabel, stopPayTestPolling, subAdmins, suspendAgent, switchTab, t, ta, taskTypeNames, testChannel, testDeepseekApi, testModelApi, testProxy, testingDeepseek, testingModel, tierCommissions, tierNames, tierTarget, toggleAccount, toggleAdActive, toppingUp, toppupMode, topupAmount, topupNote, topupTarget, totalPlatformOrders, triggerAdFileUpload, triggerAdImgUpload, triggerQrUpload, typeLabels, unifiedAgentFilter, unifiedRoleFilter, unifiedSearch, unifiedStats, unifiedTotal, unifiedUsers, usedSlots, users, usersSubTab, usersTotal, val, visibleSidebarGroups, warnCount, withdrawalStatusFilter, withdrawals, withdrawalsTotal, wxAccounts, ypayAccounts, ypayForm, ypayLoaded, ypayOrderFilters, ypayOrderStatusFilter, ypayOrders, ypayOrdersPage, ypayOrdersTotal, ypaySaving, ypayStateLabels, ypayStatus, ypayTab, ypayTestResult, ypayTesting } = useAdminState()
</script>

<template>
  <div class="pricing-tab">
    <!-- AI 定价顾问 -->
    <div class="settings-card ai-advisor-card">
      <div class="pricing-mode-header">
        <h3>
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            style="vertical-align: -3px; margin-right: 6px;"
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
          定价配置
        </h3>
      </div>

      <!-- 当前生效定价 -->
      <div
        class="pricing-section"
        style="margin-bottom:20px"
      >
        <div class="pricing-section-header">
          <span class="pricing-section-title">当前定价方案</span>
          <button
            v-if="!editingPricing"
            class="btn btn-xs btn-ghost"
            @click="editingPricing = true"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
            编辑
          </button>
          <div
            v-else
            class="pricing-edit-actions"
          >
            <button
              class="btn btn-xs btn-ghost"
              @click="cancelEditPricing"
            >
              取消
            </button>
            <button
              class="btn btn-xs btn-primary"
              :disabled="savingPricing"
              @click="savePricingConfig"
            >
              {{ savingPricing ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
        <div class="pkg-current-grid">
          <div class="pkg-card">
            <div class="pkg-card-label">
              小课 (≤30视频)
            </div>
            <div
              v-if="!editingPricing"
              class="pkg-card-price"
            >
              ¥{{ packagePricing.priceSmall }}
            </div>
            <div
              v-else
              class="pkg-card-input"
            >
              <span class="pkg-input-prefix">¥</span><input
                v-model.number="editPricing.priceSmall"
                type="number"
                min="0"
                step="0.5"
              >
            </div>
          </div>
          <div class="pkg-card">
            <div class="pkg-card-label">
              中课 (31-80视频)
            </div>
            <div
              v-if="!editingPricing"
              class="pkg-card-price"
            >
              ¥{{ packagePricing.priceMedium }}
            </div>
            <div
              v-else
              class="pkg-card-input"
            >
              <span class="pkg-input-prefix">¥</span><input
                v-model.number="editPricing.priceMedium"
                type="number"
                min="0"
                step="0.5"
              >
            </div>
          </div>
          <div class="pkg-card">
            <div class="pkg-card-label">
              大课 (>80视频)
            </div>
            <div
              v-if="!editingPricing"
              class="pkg-card-price"
            >
              ¥{{ packagePricing.priceLarge }}
            </div>
            <div
              v-else
              class="pkg-card-input"
            >
              <span class="pkg-input-prefix">¥</span><input
                v-model.number="editPricing.priceLarge"
                type="number"
                min="0"
                step="0.5"
              >
            </div>
          </div>
          <div class="pkg-card">
            <div class="pkg-card-label">
              纯考试
            </div>
            <div
              v-if="!editingPricing"
              class="pkg-card-price"
            >
              ¥{{ packagePricing.priceExamOnly }}
            </div>
            <div
              v-else
              class="pkg-card-input"
            >
              <span class="pkg-input-prefix">¥</span><input
                v-model.number="editPricing.priceExamOnly"
                type="number"
                min="0"
                step="0.5"
              >
            </div>
          </div>
          <div class="pkg-card">
            <div class="pkg-card-label">
              纯作业
            </div>
            <div
              v-if="!editingPricing"
              class="pkg-card-price"
            >
              ¥{{ packagePricing.priceHomeworkOnly }}
            </div>
            <div
              v-else
              class="pkg-card-input"
            >
              <span class="pkg-input-prefix">¥</span><input
                v-model.number="editPricing.priceHomeworkOnly"
                type="number"
                min="0"
                step="0.5"
              >
            </div>
          </div>
          <div class="pkg-card">
            <div class="pkg-card-label">
              学习通（积分+作业）
            </div>
            <div
              v-if="!editingPricing"
              class="pkg-card-price"
            >
              ¥{{ packagePricing.priceChaoxing }}
            </div>
            <div
              v-else
              class="pkg-card-input"
            >
              <span class="pkg-input-prefix">¥</span><input
                v-model.number="editPricing.priceChaoxing"
                type="number"
                min="0"
                step="0.5"
              >
            </div>
          </div>
        </div>
        <div class="pkg-discount-row">
          <span
            v-if="!editingPricing"
            class="pkg-discount-tag"
          >25-50%进度: ×{{ packagePricing.discount25 }}</span>
          <span
            v-if="!editingPricing"
            class="pkg-discount-tag"
          >50-75%进度: ×{{ packagePricing.discount50 }}</span>
          <span
            v-if="!editingPricing"
            class="pkg-discount-tag"
          >>75%进度: ×{{ packagePricing.discount75 }}</span>
          <span
            v-if="!editingPricing"
            class="pkg-discount-tag"
          >最低: ¥{{ packagePricing.priceMinimum }}</span>
          <template v-else>
            <span class="pkg-discount-edit"><span class="pkg-disc-label">25-50%:</span><input
              v-model.number="editPricing.discount25"
              type="number"
              min="0"
              max="1"
              step="0.05"
            ></span>
            <span class="pkg-discount-edit"><span class="pkg-disc-label">50-75%:</span><input
              v-model.number="editPricing.discount50"
              type="number"
              min="0"
              max="1"
              step="0.05"
            ></span>
            <span class="pkg-discount-edit"><span class="pkg-disc-label">>75%:</span><input
              v-model.number="editPricing.discount75"
              type="number"
              min="0"
              max="1"
              step="0.05"
            ></span>
            <span class="pkg-discount-edit"><span class="pkg-disc-label">最低:</span><span class="pkg-input-prefix">¥</span><input
              v-model.number="editPricing.priceMinimum"
              type="number"
              min="0"
              step="0.5"
            ></span>
          </template>
        </div>
      </div>

        <!-- 一键应用 -->
        <button
          class="btn btn-success btn-lg btn-block"
          :disabled="applyingPackage"
          style="margin-top: 16px;"
          @click="applyPackagePricing"
        >
          {{ applyingPackage ? '应用中...' : '一键应用此方案' }}
        </button>
    </div>
  </div>
</template>
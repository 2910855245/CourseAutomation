<script setup lang="ts">
// @ts-nocheck
import { useAdminState } from './adminState'

const { DEEPSEEK_MODELS, acceptOrder, accountForm, accounts, active, activeTab, adFileInput, adFileUploading, adForm, adImgInput, addDomain, addDomainForm, adminPass, adminState, adminUser, adsList, agentFees, agentStats, agentStatusFilter, agentSubTab, agentTotal, agents, agentsByTier, alertCount, aliAccounts, all, allSidebarItems, allUp, applyAutoConcurrency, applyPackagePricing, applyingPackage, approveAgent, approveWithdrawal, base64, body, buildRiskChecks, cancelEditPricing, cancelQueueJob, captchaAnswer, captchaImage, captchaLoading, captchaToken, cfg, changeAdminPassword, changingPw, channelCodeHelp, channelCodeLabels, channelTestAccount, channelTestAllOk, channelTestChecks, channelTestLoading, channelTestQrImage, chars, checks, circumference, clearCommissionHistory, clearDeepseekKey, clearOrderHistory, clearQueueHistory, clearRiskAlerts, clearWithdrawalHistory, clearYpayOrderHistory, closeAccountModal, closeExpiredYpayOrders, closePayTest, codeLabel, commissionTotal, commissions, completeOrder, configs, count, creatingSubAdmin, currentRole, d, dash, dashError, deepseekApiKey, deepseekKeyMasked, deepseekTestResult, defaultCodes, deleteAccount, deleteAd, detectServerSpecs, doChangeTier, doCreateSubAdmin, doRevokeSubAdmin, doTopup, domainCount, downloadQrImage, downloadQrLoading, dsRes, editPricing, editingAccount, editingAd, editingPricing, end, enqueueOrder, examModel, executeOrder, failCount, failOrder, fd, file, filled, finalExamModel, fmtDate, fmtHeartbeat, fmtMoney, fmtShortDate, fn, genRandomStr, getPlatformName, getRecommendation, hChecks, hNameMap, hOrder, healthAccountInput, healthAccountSaving, healthChecking, healthIntervalInput, healthIntervalSaving, healthPasswordInput, healthSummary, homeworkModel, html, imgTag, interval, isLoggedIn, jsChanged, jsChecked, jsFiles, jsRes, key, list, loadAccounts, loadAds, loadAgentFees, loadAgentStats, loadAgents, loadAgentsByTier, loadCommissions, loadDashboard, loadDeepseekKey, loadHealthAccount, loadHealthInterval, loadOrders, loadPairQr, loadPlatformNames, loadPricing, loadProxySettings, loadQueueData, loadRiskData, loadSubAdmins, loadTierCommissions, loadUnifiedUsers, loadUsers, loadWithdrawals, loadYpay, loadYpayOrders, loadingAccounts, loadingAds, loadingAgents, loadingAgentsByTier, loadingCommissions, loadingDash, loadingHealth, loadingOrders, loadingQueue, loadingRisk, loadingSubAdmins, loadingUnified, loadingUsers, loadingWithdrawals, loadingYpayOrders, loginErr, marketForm, maxBarOrders, maxBarRevenue, maxPartnerStatusCount, maxStatusCount, maxWorkersInput, mobileSidebarOpen, needAppid, needQrUrl, needRemark, newRate, newStatus, newSubAdmin, newTierLevel, nextSlot, ok, okCount, onAdFileChange, onAdImgChange, onQrFileChange, openAddAccount, openCreateAd, openEditAccount, openEditAd, openRateModal, openTierModal, openTopup, orderStatusClass, orderStatusLabel, orders, ordersStatusFilter, ordersTotal, packagePricing, pairQrImage, pairQrLoading, pairQrTs, params, partnerAgentStats, partnerAllowedTabs, passCount, pauseQueue, payTestAccountId, payTestBatchId, payTestChannelName, payTestChecks, payTestExpired, payTestLoading, payTestPaid, payTestPolling, payTestQrImage, payTestReallyPrice, payTestStarted, payTestTimer, payTestTradeNo, payTypeLabels, personnelTab, platformColors, platformNames, platforms, pricingModel, proxyForm, proxySaving, proxyTestOk, proxyTestResult, proxyTesting, pwForm, qrFileInput, qrUploading, queueJobs, queuePausing, queueStats, queueStatusFilter, r, rateTarget, reactivateAgent, reader, recommendResult, recommending, regenerateYpayKey, rejectWithdrawal, relImgs, removeDomain, res, resetAccountForm, resetYpayConnection, resumeQueue, retryQueueJob, riskAlerts, riskCheckStep, riskChecking, riskChecks, riskDomainStatus, riskHealth, riskIntervalInput, riskJsStatus, riskLoginAndCheck, riskLoginForm, riskLoginLoading, riskNeedLogin, riskScore, riskScoreColor, riskScoreDash, riskScoreDesc, riskScoreLevel, riskScoreText, role, runDomainCheck, runFullRiskCheck, runHealthCheck, runJsCheck, runYpayTest, s, saveAccount, saveAd, saveAgentFees, saveDeepseekKey, saveHealthAccount, saveHealthInterval, saveModels, savePricingConfig, saveProxy, saveRate, saveRiskInterval, saveTierCommissions, saveYpayKeyOnly, saveYpaySettings, savingAccount, savingAd, savingAgentFees, savingDeepseekKey, savingModels, savingPricing, savingTierCommissions, serverPublicIp, serverSpecs, setMaxWorkers, showAccountModal, showAdModal, showAddDomainModal, showCertFields, showChannelTest, showCreateSubAdmin, showDeepseekKey, showHealthSettings, showPayTest, showQrModal, showRateModal, showTierModal, showTopupModal, sidebarCollapsed, sidebarGroups, someUp, st, start, startChannelPayTest, startPayTestPolling, statusClass, statusLabel, stopPayTestPolling, subAdmins, suspendAgent, switchTab, t, ta, taskTypeNames, testChannel, testDeepseekApi, testModelApi, testProxy, testingDeepseek, testingModel, tierCommissions, tierNames, tierTarget, toggleAccount, toggleAdActive, toppingUp, toppupMode, topupAmount, topupNote, topupTarget, totalPlatformOrders, triggerAdFileUpload, triggerAdImgUpload, triggerQrUpload, typeLabels, unifiedAgentFilter, unifiedRoleFilter, unifiedSearch, unifiedStats, unifiedTotal, unifiedUsers, usedSlots, users, usersSubTab, usersTotal, val, visibleSidebarGroups, warnCount, withdrawalStatusFilter, withdrawals, withdrawalsTotal, wxAccounts, ypayAccounts, ypayForm, ypayLoaded, ypayOrderFilters, ypayOrderStatusFilter, ypayOrders, ypayOrdersPage, ypayOrdersTotal, ypaySaving, ypayStateLabels, ypayStatus, ypayTab, ypayTestResult, ypayTesting } = useAdminState()
</script>

<template>
  <div class="ads-tab">
    <div class="panel-head-row">
      <h3>广告管理</h3>
      <button
        class="btn btn-primary btn-sm"
        :disabled="adsList.length >= 5"
        @click="openCreateAd"
      >
        + 添加广告
      </button>
    </div>
    <div class="ads-help">
      <p>最多 5 个广告位，显示在首页底部，点击名称跳转到对应 HTML 页面。</p>
      <p><strong>图片说明：</strong>HTML 中的外部图片 URL（https://...）可直接使用；本地图片请用编辑器中的「插入图片」按钮上传，会自动转为 base64 内联存储（单张不超过 2MB）。</p>
    </div>

    <div
      v-if="loadingAds"
      class="loading-row"
    >
      <div class="spinner-sm" /><span>加载中...</span>
    </div>

    <div
      v-else-if="adsList.length === 0"
      class="empty-card"
    >
      <svg
        width="40"
        height="40"
        viewBox="0 0 24 24"
        fill="none"
        stroke="#cbd5e1"
        stroke-width="1.5"
      ><rect
        x="3"
        y="3"
        width="18"
        height="18"
        rx="2"
      /><line
        x1="3"
        y1="9"
        x2="21"
        y2="9"
      /><line
        x1="9"
        y1="3"
        x2="9"
        y2="21"
      /></svg>
      <p>暂无广告</p>
      <button
        class="btn btn-primary btn-sm"
        @click="openCreateAd"
      >
        添加第一个广告
      </button>
    </div>

    <div
      v-else
      class="table-wrap"
    >
      <table class="data-table">
        <thead>
          <tr>
            <th style="width:60px">
              位置
            </th>
            <th>广告名称</th>
            <th>HTML 预览</th>
            <th style="width:80px">
              状态
            </th>
            <th style="width:180px">
              操作
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="ad in adsList"
            :key="ad.id"
          >
            <td><span class="slot-badge">{{ ad.slot }}</span></td>
            <td class="ad-name-cell">
              {{ ad.name }}
            </td>
            <td class="ad-preview-cell">
              {{ ad.html_content.replace(/<[^>]*>/g, '').substring(0, 60) }}{{ ad.html_content.length > 60 ? '...' : '' }}
            </td>
            <td>
              <span
                :class="['status-tag', ad.is_active ? 'active' : 'inactive']"
                @click="toggleAdActive(ad)"
              >
                {{ ad.is_active ? '展示中' : '已隐藏' }}
              </span>
            </td>
            <td>
              <div class="row-actions">
                <button
                  class="btn btn-xs btn-ghost"
                  @click="openEditAd(ad)"
                >
                  编辑
                </button>
                <button
                  class="btn btn-xs btn-ghost btn-danger"
                  @click="deleteAd(ad)"
                >
                  删除
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 广告编辑弹窗 -->
    <div
      v-if="showAdModal"
      class="modal-overlay"
      @click.self="showAdModal = false"
    >
      <div class="modal modal-wide">
        <h3>{{ editingAd ? '编辑广告' : '添加广告' }}</h3>
        <div
          v-if="!editingAd"
          class="field"
        >
          <label>广告位编号</label>
          <div class="slot-auto">
            自动分配为 <strong>位置 {{ adForm.slot }}</strong>
          </div>
        </div>
        <div class="field">
          <label>广告名称（显示在首页底部的链接文字）</label>
          <input
            v-model="adForm.name"
            type="text"
            placeholder="例如：代理推广"
          >
        </div>
        <div class="field">
          <label>HTML 内容</label>
          <div class="ad-upload-row">
            <textarea
              v-model="adForm.html_content"
              rows="10"
              class="ad-html-textarea"
              placeholder="粘贴完整的 HTML 代码，或上传 HTML 文件..."
            />
          </div>
          <div class="ad-upload-actions">
            <input
              ref="adFileInput"
              type="file"
              accept=".html,.htm"
              style="display:none"
              @change="onAdFileChange"
            >
            <input
              ref="adImgInput"
              type="file"
              accept="image/*"
              style="display:none"
              @change="onAdImgChange"
            >
            <button
              class="btn btn-sm btn-outline"
              :disabled="adFileUploading"
              @click="triggerAdFileUpload"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              ><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line
                x1="12"
                y1="3"
                x2="12"
                y2="15"
              /></svg>
              <span>上传 HTML</span>
            </button>
            <button
              class="btn btn-sm btn-outline"
              :disabled="adFileUploading"
              @click="triggerAdImgUpload"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              ><rect
                x="3"
                y="3"
                width="18"
                height="18"
                rx="2"
              /><circle
                cx="8.5"
                cy="8.5"
                r="1.5"
              /><polyline points="21 15 16 10 5 21" /></svg>
              <span>插入图片</span>
            </button>
            <span class="ad-file-hint">图片自动转为内联 base64，不超过 2MB</span>
          </div>
        </div>
        <div class="modal-actions">
          <button
            class="btn btn-ghost"
            @click="showAdModal = false"
          >
            取消
          </button>
          <button
            class="btn btn-primary"
            :disabled="savingAd"
            @click="saveAd"
          >
            {{ savingAd ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
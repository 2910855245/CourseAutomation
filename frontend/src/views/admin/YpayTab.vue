<script setup lang="ts">
// @ts-nocheck
import { useAdminState } from './adminState'

const { DEEPSEEK_MODELS, acceptOrder, accountForm, accounts, active, activeTab, adFileInput, adFileUploading, adForm, adImgInput, addDomain, addDomainForm, adminPass, adminState, adminUser, adsList, agentFees, agentStats, agentStatusFilter, agentSubTab, agentTotal, agents, agentsByTier, alertCount, aliAccounts, all, allSidebarItems, allUp, applyAutoConcurrency, applyPackagePricing, applyingPackage, approveAgent, approveWithdrawal, base64, body, buildRiskChecks, cancelEditPricing, cancelQueueJob, captchaAnswer, captchaImage, captchaLoading, captchaToken, cfg, changeAdminPassword, changingPw, channelCodeHelp, channelCodeLabels, channelTestAccount, channelTestAllOk, channelTestChecks, channelTestLoading, channelTestQrImage, chars, checks, circumference, clearCommissionHistory, clearDeepseekKey, clearOrderHistory, clearQueueHistory, clearRiskAlerts, clearWithdrawalHistory, clearYpayOrderHistory, closeAccountModal, closeExpiredYpayOrders, closePayTest, codeLabel, commissionTotal, commissions, completeOrder, configs, count, creatingSubAdmin, currentRole, d, dash, dashError, deepseekApiKey, deepseekKeyMasked, deepseekTestResult, defaultCodes, deleteAccount, deleteAd, detectServerSpecs, doChangeTier, doCreateSubAdmin, doRevokeSubAdmin, doTopup, domainCount, downloadQrImage, downloadQrLoading, dsRes, editPricing, editingAccount, editingAd, editingPricing, end, enqueueOrder, examModel, executeOrder, failCount, failOrder, fd, file, filled, finalExamModel, fmtDate, fmtHeartbeat, fmtMoney, fmtShortDate, fn, genRandomStr, getPlatformName, getRecommendation, hChecks, hNameMap, hOrder, healthAccountInput, healthAccountSaving, healthChecking, healthIntervalInput, healthIntervalSaving, healthPasswordInput, healthSummary, homeworkModel, html, imgTag, interval, isLoggedIn, jsChanged, jsChecked, jsFiles, jsRes, key, list, loadAccounts, loadAds, loadAgentFees, loadAgentStats, loadAgents, loadAgentsByTier, loadCommissions, loadDashboard, loadDeepseekKey, loadHealthAccount, loadHealthInterval, loadOrders, loadPairQr, loadPlatformNames, loadPricing, loadProxySettings, loadQueueData, loadRiskData, loadSubAdmins, loadTierCommissions, loadUnifiedUsers, loadUsers, loadWithdrawals, loadYpay, loadYpayOrders, loadingAccounts, loadingAds, loadingAgents, loadingAgentsByTier, loadingCommissions, loadingDash, loadingHealth, loadingOrders, loadingQueue, loadingRisk, loadingSubAdmins, loadingUnified, loadingUsers, loadingWithdrawals, loadingYpayOrders, loginErr, marketForm, maxBarOrders, maxBarRevenue, maxPartnerStatusCount, maxStatusCount, maxWorkersInput, mobileSidebarOpen, needAppid, needQrUrl, needRemark, newRate, newStatus, newSubAdmin, newTierLevel, nextSlot, ok, okCount, onAdFileChange, onAdImgChange, onQrFileChange, openAddAccount, openCreateAd, openEditAccount, openEditAd, openRateModal, openTierModal, openTopup, orderStatusClass, orderStatusLabel, orders, ordersStatusFilter, ordersTotal, packagePricing, pairQrImage, pairQrLoading, pairQrTs, params, partnerAgentStats, partnerAllowedTabs, passCount, pauseQueue, payTestAccountId, payTestBatchId, payTestChannelName, payTestChecks, payTestExpired, payTestLoading, payTestPaid, payTestPolling, payTestQrImage, payTestReallyPrice, payTestStarted, payTestTimer, payTestTradeNo, payTypeLabels, personnelTab, platformColors, platformNames, platforms, pricingModel, proxyForm, proxySaving, proxyTestOk, proxyTestResult, proxyTesting, pwForm, qrFileInput, qrUploading, queueJobs, queuePausing, queueStats, queueStatusFilter, r, rateTarget, reactivateAgent, reader, recommendResult, recommending, regenerateYpayKey, rejectWithdrawal, relImgs, removeDomain, res, resetAccountForm, resetYpayConnection, resumeQueue, retryQueueJob, riskAlerts, riskCheckStep, riskChecking, riskChecks, riskDomainStatus, riskHealth, riskIntervalInput, riskJsStatus, riskLoginAndCheck, riskLoginForm, riskLoginLoading, riskNeedLogin, riskScore, riskScoreColor, riskScoreDash, riskScoreDesc, riskScoreLevel, riskScoreText, role, runDomainCheck, runFullRiskCheck, runHealthCheck, runJsCheck, runYpayTest, s, saveAccount, saveAd, saveAgentFees, saveDeepseekKey, saveHealthAccount, saveHealthInterval, saveModels, savePricingConfig, saveProxy, saveRate, saveRiskInterval, saveTierCommissions, saveYpayKeyOnly, saveYpaySettings, savingAccount, savingAd, savingAgentFees, savingDeepseekKey, savingModels, savingPricing, savingTierCommissions, serverPublicIp, serverSpecs, setMaxWorkers, showAccountModal, showAdModal, showAddDomainModal, showCertFields, showChannelTest, showCreateSubAdmin, showDeepseekKey, showHealthSettings, showPayTest, showQrModal, showRateModal, showTierModal, showTopupModal, sidebarCollapsed, sidebarGroups, someUp, st, start, startChannelPayTest, startPayTestPolling, statusClass, statusLabel, stopPayTestPolling, subAdmins, suspendAgent, switchTab, t, ta, taskTypeNames, testChannel, testDeepseekApi, testModelApi, testProxy, testingDeepseek, testingModel, tierCommissions, tierNames, tierTarget, toggleAccount, toggleAdActive, toppingUp, toppupMode, topupAmount, topupNote, topupTarget, totalPlatformOrders, triggerAdFileUpload, triggerAdImgUpload, triggerQrUpload, typeLabels, unifiedAgentFilter, unifiedRoleFilter, unifiedSearch, unifiedStats, unifiedTotal, unifiedUsers, usedSlots, users, usersSubTab, usersTotal, val, visibleSidebarGroups, warnCount, withdrawalStatusFilter, withdrawals, withdrawalsTotal, wxAccounts, ypayAccounts, ypayForm, ypayLoaded, ypayOrderFilters, ypayOrderStatusFilter, ypayOrders, ypayOrdersPage, ypayOrdersTotal, ypaySaving, ypayStateLabels, ypayStatus, ypayTab, ypayTestResult, ypayTesting } = useAdminState()
</script>

<template>
  <div class="ypay-tab">
    <div class="ypay-subtabs">
      <button
        :class="['ypay-subtab', { active: ypayTab === 'settings' }]"
        @click="ypayTab = 'settings'"
      >
        基本配置
      </button>
      <button
        :class="['ypay-subtab', { active: ypayTab === 'orders' }]"
        @click="ypayTab = 'orders'"
      >
        支付订单
      </button>
      <button
        :class="['ypay-subtab', { active: ypayTab === 'qrcodes' }]"
        @click="ypayTab = 'qrcodes'"
      >
        收款通道
      </button>
    </div>

    <div
      v-if="ypayTab === 'settings'"
      class="ypay-settings-layout"
    >
      <div class="settings-card">
        <h3>基本配置</h3>
        <p class="settings-hint">
          通讯密钥由系统自动生成，保存配置后打开APP扫码即可自动配对
        </p>
        <div class="field">
          <label>通讯密钥</label>
          <div class="gen-row">
            <code class="ypay-key-code">{{ ypayForm.key || '未设置' }}</code>
            <button
              class="btn btn-xs btn-ghost"
              @click="regenerateYpayKey"
            >
              重新生成
            </button>
          </div>
        </div>
        <div class="field-row">
          <div class="field">
            <label>未支付关闭 (分钟)</label>
            <input
              v-model="ypayForm.close_time"
              type="number"
              min="1"
            >
          </div>
          <div class="field">
            <label>支付超时 (秒)</label>
            <input
              v-model="ypayForm.pay_timeout"
              type="number"
              min="30"
            >
          </div>
        </div>
        <button
          class="btn btn-primary"
          :disabled="ypaySaving"
          @click="saveYpaySettings"
        >
          {{ ypaySaving ? '保存中...' : '保存配置' }}
        </button>
      </div>
      <div class="ypay-qr-cards">
        <div class="settings-card ypay-qr-card">
          <h3>APP 扫码配对</h3>
          <p class="settings-hint">
            打开手机APP扫描二维码，自动完成服务器连接
          </p>
          <div class="ypay-qr-img-wrap">
            <div
              v-if="pairQrLoading"
              class="qr-loading"
            >
              <div class="qr-spinner" />
            </div>
            <img
              :src="pairQrImage"
              class="ypay-qr-img"
              alt="APP扫码配对"
              :style="{ opacity: pairQrLoading ? 0 : 1 }"
            >
          </div>
          <button
            class="btn btn-ghost btn-sm btn-block"
            @click="regenerateYpayKey()"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" /></svg>
            刷新二维码
          </button>
        </div>
        <div class="settings-card ypay-qr-card">
          <h3>下载收款APP</h3>
          <p class="settings-hint">
            支持 Android 7.0+，安装后扫码配对即可使用
          </p>
          <div class="ypay-qr-img-wrap">
            <div
              v-if="downloadQrLoading"
              class="qr-loading"
            >
              <div class="qr-spinner" />
            </div>
            <img
              :src="downloadQrImage"
              class="ypay-qr-img"
              alt="APP下载"
              :style="{ opacity: downloadQrLoading ? 0 : 1 }"
            >
          </div>
          <a
            href="/api/ypay/app-download"
            target="_blank"
            class="btn btn-ghost btn-sm btn-block"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line
              x1="12"
              y1="15"
              x2="12"
              y2="3"
            /></svg>
            直接下载 APK
          </a>
        </div>
      </div>
    </div>

    <div
      v-if="ypayTab === 'orders'"
      class="settings-card"
    >
      <h3>支付订单</h3>
      <!-- 监控状态摘要 -->
      <div
        v-if="ypayStatus"
        class="monitor-summary"
      >
        <div class="monitor-summary-row">
          <span :class="['ypay-stat-badge', ypayStatus.monitor_status === 'key_mismatch' ? 'key-mismatch' : (ypayStatus.is_online ? 'online' : 'offline')]">
            <span
              v-if="ypayStatus.monitor_status !== 'key_mismatch'"
              class="ypay-dot"
              :class="ypayStatus.is_online ? 'dot-live' : 'dot-dead'"
            />
            {{ ypayStatus.monitor_status === 'key_mismatch' ? '密钥不匹配' : (ypayStatus.is_online ? '监控在线' : '监控离线') }}
          </span>
          <span class="monitor-summary-item">心跳: {{ fmtHeartbeat(ypayStatus.seconds_ago, ypayStatus.monitor_last_heart) }}</span>
          <span class="monitor-summary-item">总 {{ ypayStatus.orders_total }} | 待支付 <b class="text-warn">{{ ypayStatus.orders_unpaid }}</b> | 已支付 <b class="text-ok">{{ ypayStatus.orders_paid }}</b></span>
          <button
            class="btn btn-xs btn-ghost"
            @click="loadYpay"
          >
            刷新
          </button>
        </div>
        <div
          v-if="ypayStatus && ypayStatus.monitor_status === 'key_mismatch'"
          class="ypay-key-mismatch-alert"
          style="margin-top:8px"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          ><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /><line
            x1="12"
            y1="9"
            x2="12"
            y2="13"
          /><line
            x1="12"
            y1="17"
            x2="12.01"
            y2="17"
          /></svg>
          <span>APP密钥不匹配，请重新扫码配对</span>
          <button
            class="btn btn-xs btn-warn"
            @click="resetYpayConnection"
          >
            重置
          </button>
        </div>
      </div>
      <div class="ypay-order-toolbar">
        <div class="ypay-order-filters">
          <button
            v-for="f in ypayOrderFilters"
            :key="f.label"
            :class="['ypay-filter-btn', { active: ypayOrderStatusFilter === f.value }]"
            @click="ypayOrderStatusFilter = f.value; ypayOrdersPage = 1; loadYpayOrders()"
          >
            {{ f.label }}
          </button>
        </div>
        <button
          class="btn btn-xs btn-ghost"
          @click="closeExpiredYpayOrders"
        >
          关闭过期订单
        </button>
        <button
          class="btn btn-xs btn-ghost"
          style="color:#ef4444;"
          @click="clearYpayOrderHistory"
        >
          清除历史
        </button>
      </div>
      <div
        v-if="ypayOrders.length"
        style="overflow-x:auto"
      >
        <table class="data-table">
          <thead><tr><th>订单号</th><th>外部订单号</th><th>支付方式</th><th>金额</th><th>实付金额</th><th>状态</th><th>创建时间</th></tr></thead>
          <tbody>
            <tr
              v-for="o in ypayOrders"
              :key="o.id"
            >
              <td class="mono">
                {{ o.trade_no }}
              </td>
              <td class="mono">
                {{ o.out_trade_no || '-' }}
              </td>
              <td>{{ payTypeLabels[o.pay_type] || o.pay_type }}</td>
              <td>¥{{ (o.money || 0).toFixed(2) }}</td>
              <td>¥{{ o.truemoney ? o.truemoney.toFixed(2) : '0.00' }}</td>
              <td><span :class="['ypay-state', o.status === 1 ? 'paid' : o.status === -1 ? 'closed' : 'unpaid']">{{ ypayStateLabels[String(o.status)] || o.status }}</span></td>
              <td class="mono small">
                {{ o.create_time?.slice(0, 19) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p
        v-else
        class="empty-text"
      >
        暂无支付订单
      </p>
      <div
        v-if="ypayOrdersTotal > 20"
        class="pagination"
      >
        <button
          :disabled="ypayOrdersPage <= 1"
          @click="ypayOrdersPage--; loadYpayOrders()"
        >
          上一页
        </button>
        <span>{{ ypayOrdersPage }} / {{ Math.ceil(ypayOrdersTotal / 20) }}</span>
        <button
          :disabled="ypayOrdersPage >= Math.ceil(ypayOrdersTotal / 20)"
          @click="ypayOrdersPage++; loadYpayOrders()"
        >
          下一页
        </button>
      </div>
    </div>

    <div
      v-if="ypayTab === 'qrcodes'"
      class="settings-card"
    >
      <h3>收款通道管理</h3>
      <p class="settings-hint">
        配置微信和支付宝收款通道，添加后用户下单即可扫码支付
      </p>

      <!-- 微信通道 -->
      <div class="channel-section">
        <div class="channel-header">
          <div class="channel-title">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="#16a34a"
            ><path d="M8.691 2.188C3.891 2.188 0 5.476 0 9.53c0 2.212 1.17 4.203 3.002 5.55a.59.59 0 01.213.665l-.39 1.48c-.019.07-.048.141-.048.213 0 .163.13.295.29.295a.326.326 0 00.167-.054l1.903-1.114a.864.864 0 01.717-.098 10.16 10.16 0 002.837.403c.276 0 .543-.027.811-.05-.857-2.578.157-4.972 1.932-6.446 1.703-1.415 3.882-1.98 5.853-1.838-.576-3.583-4.196-6.348-8.596-6.348zM5.785 5.991c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 01-1.162 1.178A1.17 1.17 0 014.623 7.17c0-.651.52-1.18 1.162-1.18zm5.813 0c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 01-1.162 1.178 1.17 1.17 0 01-1.162-1.178c0-.651.52-1.18 1.162-1.18zm5.34 2.867c-1.797-.052-3.746.512-5.28 1.786-1.72 1.428-2.687 3.72-1.78 6.22.942 2.453 3.666 4.229 6.884 4.229.826 0 1.622-.12 2.361-.336a.722.722 0 01.598.082l1.584.926a.272.272 0 00.14.047c.134 0 .24-.108.24-.243 0-.06-.023-.12-.038-.177l-.327-1.233a.582.582 0 01-.023-.156.49.49 0 01.201-.398C23.024 18.48 24 16.82 24 14.98c0-3.21-2.931-5.837-7.062-6.122zm-2.18 2.769c.535 0 .969.44.969.982a.976.976 0 01-.969.983.976.976 0 01-.969-.983c0-.542.434-.982.97-.982zm4.844 0c.535 0 .969.44.969.982a.976.976 0 01-.969.983.976.976 0 01-.969-.983c0-.542.434-.982.969-.982z" /></svg>
            <span>微信收款通道</span>
            <span class="channel-count">{{ wxAccounts.length }} 条</span>
          </div>
          <button
            class="btn btn-xs btn-primary"
            @click="openAddAccount('wxpay')"
          >
            + 添加微信通道
          </button>
        </div>
        <div
          v-if="wxAccounts.length"
          class="channel-list"
        >
          <div
            v-for="acc in wxAccounts"
            :key="acc.id"
            :class="['channel-card', { disabled: acc.is_status !== 1 }]"
          >
            <div class="channel-card-top">
              <div class="channel-card-name">
                {{ acc.name }}
                <span class="channel-code-tag">{{ codeLabel(acc.code) }}</span>
              </div>
              <div class="channel-card-actions">
                <button
                  class="btn-icon"
                  title="支付测试"
                  @click="startChannelPayTest(acc)"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#16a34a"
                    stroke-width="2"
                  ><path d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" /></svg>
                </button>
                <button
                  class="btn-icon"
                  title="测试通道"
                  @click="testChannel(acc)"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#f59e0b"
                    stroke-width="2"
                  ><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z" /></svg>
                </button>
                <button
                  class="btn-icon"
                  :title="acc.is_status === 1 ? '点击停用' : '点击启用'"
                  @click="toggleAccount(acc)"
                >
                  <svg
                    v-if="acc.is_status === 1"
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#16a34a"
                    stroke-width="2"
                  ><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
                  <svg
                    v-else
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#94a3b8"
                    stroke-width="2"
                  ><circle
                    cx="12"
                    cy="12"
                    r="10"
                  /><line
                    x1="4.93"
                    y1="4.93"
                    x2="19.07"
                    y2="19.07"
                  /></svg>
                </button>
                <button
                  class="btn-icon"
                  title="编辑"
                  @click="openEditAccount(acc)"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#6366f1"
                    stroke-width="2"
                  ><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                </button>
                <button
                  class="btn-icon"
                  title="删除"
                  @click="deleteAccount(acc)"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#ef4444"
                    stroke-width="2"
                  ><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></svg>
                </button>
              </div>
            </div>
            <div class="channel-card-meta">
              <span :class="['channel-status-dot', acc.status === 1 ? 'online' : 'offline']" />
              <span class="channel-status-text">{{ acc.status === 1 ? '在线' : '离线' }}</span>
              <span
                v-if="acc.memo"
                class="channel-memo"
              >{{ acc.memo }}</span>
            </div>
          </div>
        </div>
        <div
          v-else
          class="channel-empty"
        >
          暂无微信通道，点击上方按钮添加
        </div>
      </div>

      <!-- 支付宝通道 -->
      <div class="channel-section">
        <div class="channel-header">
          <div class="channel-title">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="#2563eb"
            ><path d="M21.422 15.358c-1.428-.648-3.36-1.44-5.28-2.088.72-1.44 1.248-3.048 1.56-4.536h-4.32V7.02h5.04V5.754h-5.04V3.126H11.82v2.628H6.78v1.266h5.04v1.714H7.62v1.266h9.84c-.252 1.08-.636 2.16-1.14 3.132-1.632-.72-3.504-1.38-5.16-1.812-3.336-.876-5.88.36-6.12 2.856-.24 2.496 1.872 4.44 5.208 4.44 2.16 0 4.2-.96 5.76-2.64 1.92.84 3.48 1.56 4.68 2.1 1.44.66 2.64 1.08 3.36 1.08v-1.26c-.72 0-1.68-.24-3.48-.828zM9.66 16.314c-2.496.096-3.96-1.08-3.84-2.568.12-1.488 1.8-2.28 3.72-2.28 1.2 0 2.4.24 3.48.648-.96 1.44-2.16 2.64-3.36 3.204v.996z" /></svg>
            <span>支付宝收款通道</span>
            <span class="channel-count">{{ aliAccounts.length }} 条</span>
          </div>
          <button
            class="btn btn-xs btn-primary"
            @click="openAddAccount('alipay')"
          >
            + 添加支付宝通道
          </button>
        </div>
        <div
          v-if="aliAccounts.length"
          class="channel-list"
        >
          <div
            v-for="acc in aliAccounts"
            :key="acc.id"
            :class="['channel-card', { disabled: acc.is_status !== 1 }]"
          >
            <div class="channel-card-top">
              <div class="channel-card-name">
                {{ acc.name }}
                <span class="channel-code-tag">{{ codeLabel(acc.code) }}</span>
              </div>
              <div class="channel-card-actions">
                <button
                  class="btn-icon"
                  title="支付测试"
                  @click="startChannelPayTest(acc)"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#16a34a"
                    stroke-width="2"
                  ><path d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" /></svg>
                </button>
                <button
                  class="btn-icon"
                  title="测试通道"
                  @click="testChannel(acc)"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#f59e0b"
                    stroke-width="2"
                  ><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z" /></svg>
                </button>
                <button
                  class="btn-icon"
                  :title="acc.is_status === 1 ? '点击停用' : '点击启用'"
                  @click="toggleAccount(acc)"
                >
                  <svg
                    v-if="acc.is_status === 1"
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#16a34a"
                    stroke-width="2"
                  ><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
                  <svg
                    v-else
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#94a3b8"
                    stroke-width="2"
                  ><circle
                    cx="12"
                    cy="12"
                    r="10"
                  /><line
                    x1="4.93"
                    y1="4.93"
                    x2="19.07"
                    y2="19.07"
                  /></svg>
                </button>
                <button
                  class="btn-icon"
                  title="编辑"
                  @click="openEditAccount(acc)"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#6366f1"
                    stroke-width="2"
                  ><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                </button>
                <button
                  class="btn-icon"
                  title="删除"
                  @click="deleteAccount(acc)"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#ef4444"
                    stroke-width="2"
                  ><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></svg>
                </button>
              </div>
            </div>
            <div class="channel-card-meta">
              <span :class="['channel-status-dot', acc.status === 1 ? 'online' : 'offline']" />
              <span class="channel-status-text">{{ acc.status === 1 ? '在线' : '离线' }}</span>
              <span
                v-if="acc.memo"
                class="channel-memo"
              >{{ acc.memo }}</span>
            </div>
          </div>
        </div>
        <div
          v-else
          class="channel-empty"
        >
          暂无支付宝通道，点击上方按钮添加
        </div>
      </div>

      <!-- 添加/编辑通道弹窗 -->
      <div
        v-if="showAccountModal"
        class="modal-overlay"
        @click.self="closeAccountModal"
      >
        <div
          class="modal-box"
          style="max-width:560px"
        >
          <div class="modal-header">
            <h3>{{ editingAccount ? '编辑通道' : '添加' + typeLabels[accountForm.type] + '通道' }}</h3>
            <button
              class="modal-close"
              @click="closeAccountModal"
            >
              &times;
            </button>
          </div>
          <div class="modal-body">
            <!-- 通道类型选择 -->
            <div class="field">
              <label>通道类型</label>
              <select v-model="accountForm.code">
                <optgroup
                  v-if="accountForm.type === 'wxpay'"
                  label="微信免挂"
                >
                  <option value="wxpay_dy">
                    微信店员版
                  </option>
                </optgroup>
                <optgroup
                  v-if="accountForm.type === 'wxpay'"
                  label="微信软件"
                >
                  <option value="wxpay_software">
                    微信软件版
                  </option>
                </optgroup>
                <optgroup
                  v-if="accountForm.type === 'wxpay'"
                  label="微信其他"
                >
                  <option value="wxpay_skd">
                    微信收款单
                  </option>
                  <option value="wxpay_cloudzs">
                    微信赞赏码
                  </option>
                </optgroup>
                <optgroup
                  v-if="accountForm.type === 'wxpay'"
                  label="第三方聚合"
                >
                  <option value="dougong_wxpay">
                    汇付斗拱-微信
                  </option>
                  <option value="lkl_wxpay">
                    拉卡拉-微信
                  </option>
                  <option value="lebrush_wxpay">
                    乐刷-微信
                  </option>
                </optgroup>
                <optgroup
                  v-if="accountForm.type === 'alipay'"
                  label="支付宝官方"
                >
                  <option value="alipay_dmf">
                    支付宝当面付
                  </option>
                  <option value="alipay_official">
                    支付宝官方支付
                  </option>
                </optgroup>
                <optgroup
                  v-if="accountForm.type === 'alipay'"
                  label="第三方聚合"
                >
                  <option value="dougong_alipay">
                    汇付斗拱-支付宝
                  </option>
                  <option value="lkl_alipay">
                    拉卡拉-支付宝
                  </option>
                  <option value="lebrush_alipay">
                    乐刷-支付宝
                  </option>
                </optgroup>
              </select>
            </div>

            <!-- 通道帮助说明 -->
            <div
              v-if="channelCodeHelp[accountForm.code]"
              class="channel-help-box"
            >
              <div class="channel-help-title">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#4f6ef7"
                  stroke-width="2"
                ><circle
                  cx="12"
                  cy="12"
                  r="10"
                /><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" /><line
                  x1="12"
                  y1="17"
                  x2="12.01"
                  y2="17"
                /></svg>
                <span>{{ channelCodeLabels[accountForm.code] }} 使用说明</span>
              </div>
              <div class="channel-help-item">
                <strong>简介：</strong>{{ channelCodeHelp[accountForm.code].desc }}
              </div>
              <div class="channel-help-item">
                <strong>原理：</strong>{{ channelCodeHelp[accountForm.code].how }}
              </div>
              <div class="channel-help-item">
                <strong>需要准备：</strong>{{ channelCodeHelp[accountForm.code].need }}
              </div>
              <div class="channel-help-item">
                <strong>提示：</strong>{{ channelCodeHelp[accountForm.code].tip }}
              </div>
            </div>

            <div class="field">
              <label>通道名称</label>
              <input
                v-model="accountForm.name"
                type="text"
                :placeholder="'例如：我的' + typeLabels[accountForm.type] + '收款'"
              >
            </div>

            <!-- 收款码内容: 微信通道 + 支付宝聚合通道(斗拱/乐刷) -->
            <div
              v-if="accountForm.type === 'wxpay' || ['dougong_alipay','lebrush_alipay'].includes(accountForm.code)"
              class="field"
            >
              <label>收款码内容</label>
              <div class="qr-upload-row">
                <textarea
                  v-model="accountForm.qr_url"
                  rows="3"
                  :placeholder="accountForm.type === 'wxpay' ? '粘贴 wxp:// 链接或上传收款码图片' : '粘贴收款码链接或内容'"
                />
                <input
                  ref="qrFileInput"
                  type="file"
                  accept="image/*"
                  style="display:none"
                  @change="onQrFileChange"
                >
                <button
                  class="btn btn-sm btn-upload-qr"
                  :disabled="qrUploading"
                  @click="triggerQrUpload"
                >
                  <svg
                    v-if="!qrUploading"
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
                  <span v-if="qrUploading">解码中...</span>
                  <span v-else>上传图片</span>
                </button>
              </div>
            </div>

            <!-- 拉卡拉 Authorization 令牌 -->
            <div
              v-if="accountForm.code.startsWith('lkl_')"
              class="field"
            >
              <label>Authorization 令牌</label>
              <textarea
                v-model="accountForm.remark"
                rows="2"
                placeholder="拉卡拉钱包平台的 Authorization 令牌"
              />
            </div>

            <!-- 微信店员版 cookie -->
            <div
              v-if="accountForm.code === 'wxpay_dy'"
              class="field"
            >
              <label>Cookie</label>
              <textarea
                v-model="accountForm.cookie"
                rows="2"
                placeholder="店员版Cookie"
              />
            </div>

            <!-- 支付宝官方通道: APPID + 密钥 (仅 alipay_dmf / alipay_official) -->
            <template v-if="['alipay_dmf','alipay_official'].includes(accountForm.code)">
              <div class="field">
                <label>应用 APPID</label>
                <input
                  v-model="accountForm.alipay_appid"
                  type="text"
                  placeholder="支付宝开放平台APPID"
                >
              </div>
              <div class="field">
                <label>支付宝公钥</label>
                <textarea
                  v-model="accountForm.alipay_public_key"
                  rows="2"
                  placeholder="支付宝公钥"
                />
              </div>
              <div class="field">
                <label>应用私钥</label>
                <textarea
                  v-model="accountForm.alipay_private_key"
                  rows="2"
                  placeholder="应用私钥"
                />
              </div>
            </template>

            <!-- 证书模式字段（仅 alipay_official，默认折叠） -->
            <template v-if="accountForm.code === 'alipay_official'">
              <div
                class="field-divider"
                style="cursor:pointer"
                @click="showCertFields = !showCertFields"
              >
                <span>证书模式（可选）{{ showCertFields ? '▾' : '▸' }}</span>
                <small>如支付宝应用配置为证书模式，请填写以下证书内容（PEM格式文本）</small>
              </div>
              <template v-if="showCertFields">
                <div class="field">
                  <label>应用公钥证书</label>
                  <textarea
                    v-model="accountForm.app_public_cert"
                    rows="2"
                    placeholder="appCertPublicKey.crt 的内容"
                  />
                </div>
                <div class="field">
                  <label>支付宝公钥证书</label>
                  <textarea
                    v-model="accountForm.alipay_public_cert"
                    rows="2"
                    placeholder="alipayCertPublicKey_RSA2.crt 的内容"
                  />
                </div>
                <div class="field">
                  <label>支付宝根证书</label>
                  <textarea
                    v-model="accountForm.alipay_root_cert"
                    rows="2"
                    placeholder="alipayRootCert.crt 的内容"
                  />
                </div>
              </template>
            </template>
          </div>
          <div class="modal-footer">
            <button
              class="btn btn-ghost"
              @click="closeAccountModal"
            >
              取消
            </button>
            <button
              class="btn btn-primary"
              :disabled="savingAccount"
              @click="saveAccount"
            >
              {{ savingAccount ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 通道测试弹窗 -->
    <div
      v-if="showChannelTest"
      class="modal-overlay"
      @click.self="showChannelTest = false"
    >
      <div
        class="modal-box"
        style="max-width:460px"
      >
        <div class="modal-header">
          <h3>通道测试 - {{ channelTestAccount?.name }}</h3>
          <button
            class="modal-close"
            @click="showChannelTest = false"
          >
            &times;
          </button>
        </div>
        <div class="modal-body">
          <div
            v-if="channelTestLoading"
            class="channel-test-loading"
          >
            <div class="spinner-sm" />
            <span>正在检测通道配置...</span>
          </div>
          <template v-else>
            <div class="channel-test-checks">
              <div
                v-for="c in channelTestChecks"
                :key="c.name"
                :class="['ypay-test-item', c.ok ? 'ok' : 'fail']"
              >
                <span
                  v-if="c.ok"
                  class="ypay-test-icon"
                ><svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="3"
                ><polyline points="20 6 9 17 4 12" /></svg></span>
                <span
                  v-else
                  class="ypay-test-icon fail-icon"
                ><svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="3"
                ><line
                  x1="18"
                  y1="6"
                  x2="6"
                  y2="18"
                /><line
                  x1="6"
                  y1="6"
                  x2="18"
                  y2="18"
                /></svg></span>
                <span class="ypay-test-name">{{ c.name }}</span>
                <span class="ypay-test-msg">{{ c.msg }}</span>
              </div>
            </div>
            <div
              v-if="channelTestQrImage"
              class="channel-test-qr"
            >
              <p class="channel-test-qr-label">
                测试二维码（¥0.01）
              </p>
              <img
                :src="channelTestQrImage"
                class="channel-test-qr-img"
              >
              <p class="channel-test-qr-hint">
                使用对应支付APP扫码测试
              </p>
            </div>
            <div
              v-if="channelTestAllOk && !channelTestQrImage"
              class="channel-test-ok"
            >
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#16a34a"
                stroke-width="2"
              ><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
              <span>配置检查通过</span>
            </div>
          </template>
        </div>
        <div class="modal-footer">
          <button
            class="btn btn-ghost"
            @click="showChannelTest = false"
          >
            关闭
          </button>
          <button
            class="btn btn-primary"
            @click="testChannel(channelTestAccount)"
          >
            重新测试
          </button>
        </div>
      </div>
    </div>

    <!-- 按通道支付测试弹窗 -->
    <div
      v-if="showPayTest"
      class="modal-overlay"
      @click.self="closePayTest"
    >
      <div
        class="modal-box"
        style="max-width:460px"
      >
        <div class="modal-header">
          <h3>支付测试 - {{ payTestChannelName }}</h3>
          <button
            class="modal-close"
            @click="closePayTest"
          >
            &times;
          </button>
        </div>
        <div class="modal-body">
          <div
            v-if="payTestLoading"
            class="channel-test-loading"
          >
            <div class="spinner-sm" />
            <span>正在创建测试订单...</span>
          </div>
          <template v-else>
            <div
              v-if="payTestChecks.length"
              class="paytest-checks"
            >
              <div
                v-for="c in payTestChecks"
                :key="c.name"
                :class="['ypay-test-item', c.ok ? 'ok' : 'fail']"
              >
                <span
                  v-if="c.ok"
                  class="ypay-test-icon"
                ><svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="3"
                ><polyline points="20 6 9 17 4 12" /></svg></span>
                <span
                  v-else
                  class="ypay-test-icon fail-icon"
                ><svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="3"
                ><line
                  x1="18"
                  y1="6"
                  x2="6"
                  y2="18"
                /><line
                  x1="6"
                  y1="6"
                  x2="18"
                  y2="18"
                /></svg></span>
                <span class="ypay-test-name">{{ c.name }}</span>
                <span class="ypay-test-msg">{{ c.msg }}</span>
              </div>
            </div>
            <div
              v-if="payTestQrImage"
              class="paytest-pay-area"
            >
              <div class="paytest-qr-box">
                <img
                  :src="payTestQrImage"
                  class="paytest-qr-img"
                >
                <div class="paytest-amount">
                  请扫码支付 <strong>¥{{ payTestReallyPrice }}</strong>
                </div>
                <div class="paytest-amount-warn">
                  请务必支付相同金额，多一分少一分都无法检测到
                </div>
              </div>
              <div class="paytest-status">
                <div
                  v-if="payTestPolling"
                  class="paytest-waiting"
                >
                  <span class="spinner-sm" />
                  <span>等待支付... (每3秒自动检测)</span>
                </div>
                <div
                  v-if="payTestPaid"
                  class="paytest-success"
                >
                  <svg
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#16a34a"
                    stroke-width="2"
                  ><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
                  <span>支付成功！通道工作正常</span>
                </div>
                <div
                  v-if="payTestExpired"
                  class="paytest-expired"
                >
                  <svg
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#ef4444"
                    stroke-width="2"
                  ><circle
                    cx="12"
                    cy="12"
                    r="10"
                  /><line
                    x1="15"
                    y1="9"
                    x2="9"
                    y2="15"
                  /><line
                    x1="9"
                    y1="9"
                    x2="15"
                    y2="15"
                  /></svg>
                  <span>测试订单已过期</span>
                </div>
              </div>
            </div>
          </template>
        </div>
        <div class="modal-footer">
          <button
            class="btn btn-ghost"
            @click="closePayTest"
          >
            {{ payTestPaid || payTestExpired ? '关闭' : '取消' }}
          </button>
          <button
            v-if="payTestPaid || payTestExpired || payTestChecks.length"
            class="btn btn-primary"
            @click="startChannelPayTest({ id: payTestAccountId, name: payTestChannelName })"
          >
            重新测试
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
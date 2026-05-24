<script setup lang="ts">
// @ts-nocheck
import { useAdminState } from './adminState'

const { DEEPSEEK_MODELS, acceptOrder, accountForm, accounts, active, activeTab, adFileInput, adFileUploading, adForm, adImgInput, addDomain, addDomainForm, adminPass, adminState, adminUser, adsList, agentFees, agentStats, agentStatusFilter, agentSubTab, agentTotal, agents, agentsByTier, alertCount, aliAccounts, all, allSidebarItems, allUp, applyAutoConcurrency, applyPackagePricing, applyingPackage, approveAgent, approveWithdrawal, base64, body, buildRiskChecks, cancelEditPricing, cancelQueueJob, captchaAnswer, captchaImage, captchaLoading, captchaToken, cfg, changeAdminPassword, changingPw, channelCodeHelp, channelCodeLabels, channelTestAccount, channelTestAllOk, channelTestChecks, channelTestLoading, channelTestQrImage, chars, checks, circumference, clearCommissionHistory, clearDeepseekKey, clearOrderHistory, clearQueueHistory, clearRiskAlerts, clearWithdrawalHistory, clearYpayOrderHistory, closeAccountModal, closeExpiredYpayOrders, closePayTest, codeLabel, commissionTotal, commissions, completeOrder, configs, count, creatingSubAdmin, currentRole, d, dash, dashError, deepseekApiKey, deepseekKeyMasked, deepseekTestResult, defaultCodes, deleteAccount, deleteAd, detectServerSpecs, doChangeTier, doCreateSubAdmin, doRevokeSubAdmin, doTopup, domainCount, downloadQrImage, downloadQrLoading, dsRes, editPricing, editingAccount, editingAd, editingPricing, end, enqueueOrder, examModel, executeOrder, failCount, failOrder, fd, file, filled, finalExamModel, fmtDate, fmtHeartbeat, fmtMoney, fmtShortDate, fn, genRandomStr, getPlatformName, getRecommendation, hChecks, hNameMap, hOrder, healthAccountInput, healthAccountSaving, healthChecking, healthIntervalInput, healthIntervalSaving, healthPasswordInput, healthSummary, homeworkModel, html, imgTag, interval, isLoggedIn, jsChanged, jsChecked, jsFiles, jsRes, key, list, loadAccounts, loadAds, loadAgentFees, loadAgentStats, loadAgents, loadAgentsByTier, loadCommissions, loadDashboard, loadDeepseekKey, loadHealthAccount, loadHealthInterval, loadOrders, loadPairQr, loadPlatformNames, loadPricing, loadProxySettings, loadQueueData, loadRiskData, loadSubAdmins, loadTierCommissions, loadUnifiedUsers, loadUsers, loadWithdrawals, loadYpay, loadYpayOrders, loadingAccounts, loadingAds, loadingAgents, loadingAgentsByTier, loadingCommissions, loadingDash, loadingHealth, loadingOrders, loadingQueue, loadingRisk, loadingSubAdmins, loadingUnified, loadingUsers, loadingWithdrawals, loadingYpayOrders, loginErr, marketForm, maxBarOrders, maxBarRevenue, maxPartnerStatusCount, maxStatusCount, maxWorkersInput, mobileSidebarOpen, needAppid, needQrUrl, needRemark, newRate, newStatus, newSubAdmin, newTierLevel, nextSlot, ok, okCount, onAdFileChange, onAdImgChange, onQrFileChange, openAddAccount, openCreateAd, openEditAccount, openEditAd, openRateModal, openTierModal, openTopup, orderStatusClass, orderStatusLabel, orders, ordersStatusFilter, ordersTotal, packagePricing, pairQrImage, pairQrLoading, pairQrTs, params, partnerAgentStats, partnerAllowedTabs, passCount, pauseQueue, payTestAccountId, payTestBatchId, payTestChannelName, payTestChecks, payTestExpired, payTestLoading, payTestPaid, payTestPolling, payTestQrImage, payTestReallyPrice, payTestStarted, payTestTimer, payTestTradeNo, payTypeLabels, personnelTab, platformColors, platformNames, platforms, pricingModel, proxyForm, proxySaving, proxyTestOk, proxyTestResult, proxyTesting, pwForm, qrFileInput, qrUploading, queueJobs, queuePausing, queueStats, queueStatusFilter, r, rateTarget, reactivateAgent, reader, recommendResult, recommending, regenerateYpayKey, rejectWithdrawal, relImgs, removeDomain, res, resetAccountForm, resetYpayConnection, resumeQueue, retryQueueJob, riskAlerts, riskCheckStep, riskChecking, riskChecks, riskDomainStatus, riskHealth, riskIntervalInput, riskJsStatus, riskLoginAndCheck, riskLoginForm, riskLoginLoading, riskNeedLogin, riskScore, riskScoreColor, riskScoreDash, riskScoreDesc, riskScoreLevel, riskScoreText, role, runDomainCheck, runFullRiskCheck, runHealthCheck, runJsCheck, runYpayTest, s, saveAccount, saveAd, saveAgentFees, saveDeepseekKey, saveHealthAccount, saveHealthInterval, saveModels, savePricingConfig, saveProxy, saveRate, saveRiskInterval, saveTierCommissions, saveYpayKeyOnly, saveYpaySettings, savingAccount, savingAd, savingAgentFees, savingDeepseekKey, savingModels, savingPricing, savingTierCommissions, serverPublicIp, serverSpecs, setMaxWorkers, showAccountModal, showAdModal, showAddDomainModal, showCertFields, showChannelTest, showCreateSubAdmin, showDeepseekKey, showHealthSettings, showPayTest, showQrModal, showRateModal, showTierModal, showTopupModal, sidebarCollapsed, sidebarGroups, someUp, st, start, startChannelPayTest, startPayTestPolling, statusClass, statusLabel, stopPayTestPolling, subAdmins, suspendAgent, switchTab, t, ta, taskTypeNames, testChannel, testDeepseekApi, testModelApi, testProxy, testingDeepseek, testingModel, tierCommissions, tierNames, tierTarget, toggleAccount, toggleAdActive, toppingUp, toppupMode, topupAmount, topupNote, topupTarget, totalPlatformOrders, triggerAdFileUpload, triggerAdImgUpload, triggerQrUpload, typeLabels, unifiedAgentFilter, unifiedRoleFilter, unifiedSearch, unifiedStats, unifiedTotal, unifiedUsers, usedSlots, users, usersSubTab, usersTotal, val, visibleSidebarGroups, warnCount, withdrawalStatusFilter, withdrawals, withdrawalsTotal, wxAccounts, ypayAccounts, ypayForm, ypayLoaded, ypayOrderFilters, ypayOrderStatusFilter, ypayOrders, ypayOrdersPage, ypayOrdersTotal, ypaySaving, ypayStateLabels, ypayStatus, ypayTab, ypayTestResult, ypayTesting } = useAdminState()
</script>

<template>
  <div>
    <div class="agent-subtabs">
      <button
        v-if="currentRole === 'sub_admin'"
        :class="['ast', { active: agentSubTab === 'agentMgmt' }]"
        @click="agentSubTab = 'agentMgmt'"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        ><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle
          cx="9"
          cy="7"
          r="4"
        /></svg>
        代理管理
      </button>
      <button
        :class="['ast', { active: agentSubTab === 'tiers' }]"
        @click="agentSubTab = 'tiers'"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        ><polyline points="23 6 13.5 15.5 8.5 10.5 1 18" /><polyline points="17 6 23 6 23 12" /></svg>
        代理层级
      </button>
      <button
        v-if="currentRole === 'admin'"
        :class="['ast', { active: agentSubTab === 'fees' }]"
        @click="agentSubTab = 'fees'"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        ><path d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8V7m0 10v1m9-5a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        收费设置
      </button>
      <button
        v-if="currentRole === 'admin'"
        :class="['ast', { active: agentSubTab === 'guide' }]"
        @click="agentSubTab = 'guide'"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        ><circle
          cx="12"
          cy="12"
          r="10"
        /><path d="M12 16v-4" /><path d="M12 8h.01" /></svg>
        系统说明
      </button>
    </div>

    <!-- Sub-tab: Partner Agent Management -->
    <div v-if="agentSubTab === 'agentMgmt'">
      <div class="agent-stats-row">
        <div class="mini-stat">
          <div class="ms-val">
            {{ partnerAgentStats.total }}
          </div><div class="ms-label">
            总代理数
          </div>
        </div>
        <div class="mini-stat">
          <div class="ms-val ok">
            {{ partnerAgentStats.active }}
          </div><div class="ms-label">
            活跃
          </div>
        </div>
        <div class="mini-stat">
          <div class="ms-val money">
            {{ partnerAgentStats.pending }}
          </div><div class="ms-label">
            待审核
          </div>
        </div>
        <div class="mini-stat">
          <div
            class="ms-val"
            style="color:#ef4444"
          >
            {{ partnerAgentStats.suspended }}
          </div><div class="ms-label">
            已暂停
          </div>
        </div>
      </div>
      <div class="section-actions">
        <div class="filter-group">
          <button
            :class="['chip', { active: agentStatusFilter === '' }]"
            @click="agentStatusFilter = ''; loadAgents()"
          >
            全部
          </button>
          <button
            :class="['chip', { active: agentStatusFilter === 'pending' }]"
            @click="agentStatusFilter = 'pending'; loadAgents()"
          >
            待审核
          </button>
          <button
            :class="['chip', { active: agentStatusFilter === 'active' }]"
            @click="agentStatusFilter = 'active'; loadAgents()"
          >
            活跃
          </button>
          <button
            :class="['chip', { active: agentStatusFilter === 'suspended' }]"
            @click="agentStatusFilter = 'suspended'; loadAgents()"
          >
            已暂停
          </button>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <button
            class="btn btn-ghost"
            :disabled="loadingAgents"
            @click="loadAgents"
          >
            <span
              v-if="loadingAgents"
              class="spinner"
              style="width:14px;height:14px"
            />
            {{ loadingAgents ? '加载中' : '刷新' }}
          </button>
        </div>
      </div>
      <div
        v-if="agents.length > 0"
        class="table-wrap"
      >
        <table class="data-table">
          <thead>
            <tr>
              <th>用户名</th><th>等级</th><th>佣金比例</th><th>代理余额</th><th>邀请人数</th><th>状态</th><th>注册时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="a in agents"
              :key="a.agent_id"
            >
              <td>
                <div class="user-cell">
                  <span class="uname">{{ a.nickname || a.username || a.display_name || a.agent_id }}</span>
                  <span class="uid">{{ a.username || a.agent_id }}</span>
                </div>
              </td>
              <td>
                <span
                  class="level-tag"
                  :class="'l' + (a.tier_level || 1)"
                >L{{ a.tier_level || 1 }}</span>
              </td>
              <td>{{ ((a.flow_commission_rate || 0) * 100).toFixed(0) }}%</td>
              <td class="money-cell">
                {{ fmtMoney(a.available_balance || 0) }}
              </td>
              <td>{{ a.referral_count || 0 }}</td>
              <td><span :class="['status-tag', statusClass[a.status]]">{{ statusLabel[a.status] || a.status }}</span></td>
              <td class="date-cell">
                {{ fmtDate(a.created_at) }}
              </td>
              <td>
                <div class="action-group">
                  <button
                    v-if="a.status === 'pending'"
                    class="btn btn-xs btn-success"
                    @click="approveAgent(a.agent_id)"
                  >
                    审核
                  </button>
                  <button
                    v-if="a.status === 'active'"
                    class="btn btn-xs btn-warn"
                    @click="suspendAgent(a.agent_id)"
                  >
                    暂停
                  </button>
                  <button
                    v-if="a.status === 'suspended'"
                    class="btn btn-xs btn-primary"
                    @click="reactivateAgent(a.agent_id)"
                  >
                    恢复
                  </button>
                  <button
                    class="btn btn-xs btn-ghost"
                    @click="openRateModal(a)"
                  >
                    调比例
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        v-else-if="!loadingAgents"
        class="empty"
      >
        <p>暂无代理数据</p>
      </div>
    </div>

    <!-- Sub-tab: Agent Tiers -->
    <div v-if="agentSubTab === 'tiers'">
      <div class="ps-panel">
        <div class="ps-header">
          <h3>代理层级总览</h3>
          <button
            class="btn btn-sm btn-ghost"
            :disabled="loadingAgentsByTier"
            @click="loadAgentsByTier"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" /></svg>
            刷新
          </button>
        </div>
        <p class="ps-desc">
          一级代理佣金最高，下级代理佣金递减。调整等级会影响代理的分成比例。
        </p>
        <div
          v-if="loadingAgentsByTier"
          class="ps-loading"
        >
          加载中...
        </div>
        <div v-else>
          <div class="tier-grid">
            <div class="tier-card">
              <div class="tc-head l1">
                <span class="tc-badge">L1</span><span>一级代理</span><span class="tc-count">{{ agentsByTier.l1.length }} 人</span>
              </div>
              <div class="tc-body">
                <div
                  v-if="!agentsByTier.l1.length"
                  class="tc-empty"
                >
                  暂无一级代理
                </div>
                <div
                  v-for="a in agentsByTier.l1"
                  :key="a.agent_id"
                  class="tc-row"
                >
                  <span class="tc-name">{{ a.display_name || a.agent_id }}</span>
                  <span class="tc-balance">¥{{ (a.total_commission || 0).toFixed(2) }}</span>
                  <div class="tc-actions">
                    <select
                      v-model="a._newTier"
                      class="tc-select"
                      @change="newTierLevel = parseInt(($event.target as HTMLSelectElement).value); tierTarget = a; doChangeTier()"
                    >
                      <option :value="1">
                        L1
                      </option>
                      <option :value="2">
                        L2
                      </option>
                      <option :value="3">
                        L3
                      </option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
            <div class="tier-card">
              <div class="tc-head l2">
                <span class="tc-badge">L2</span><span>二级代理</span><span class="tc-count">{{ agentsByTier.l2.length }} 人</span>
              </div>
              <div class="tc-body">
                <div
                  v-if="!agentsByTier.l2.length"
                  class="tc-empty"
                >
                  暂无二级代理
                </div>
                <div
                  v-for="a in agentsByTier.l2"
                  :key="a.agent_id"
                  class="tc-row"
                >
                  <span class="tc-name">{{ a.display_name || a.agent_id }}</span>
                  <span class="tc-balance">¥{{ (a.total_commission || 0).toFixed(2) }}</span>
                  <div class="tc-actions">
                    <select
                      v-model="a._newTier"
                      class="tc-select"
                      @change="newTierLevel = parseInt(($event.target as HTMLSelectElement).value); tierTarget = a; doChangeTier()"
                    >
                      <option :value="1">
                        L1
                      </option>
                      <option :value="2">
                        L2
                      </option>
                      <option :value="3">
                        L3
                      </option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
            <div class="tier-card">
              <div class="tc-head l3">
                <span class="tc-badge">L3</span><span>三级代理</span><span class="tc-count">{{ agentsByTier.l3.length }} 人</span>
              </div>
              <div class="tc-body">
                <div
                  v-if="!agentsByTier.l3.length"
                  class="tc-empty"
                >
                  暂无三级代理
                </div>
                <div
                  v-for="a in agentsByTier.l3"
                  :key="a.agent_id"
                  class="tc-row"
                >
                  <span class="tc-name">{{ a.display_name || a.agent_id }}</span>
                  <span class="tc-balance">¥{{ (a.total_commission || 0).toFixed(2) }}</span>
                  <div class="tc-actions">
                    <select
                      v-model="a._newTier"
                      class="tc-select"
                      @change="newTierLevel = parseInt(($event.target as HTMLSelectElement).value); tierTarget = a; doChangeTier()"
                    >
                      <option :value="1">
                        L1
                      </option>
                      <option :value="2">
                        L2
                      </option>
                      <option :value="3">
                        L3
                      </option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div
            v-if="currentRole === 'admin'"
            class="tier-commission-config"
          >
            <h4>代理等级佣金比例</h4>
            <p
              class="ps-desc"
              style="margin-bottom:12px"
            >
              各等级代理从订单中获得的佣金分成比例（总和不超过50%）
            </p>
            <div class="tcc-row">
              <div class="tcc-item">
                <span class="tcc-badge l1">L1</span>
                <span class="tcc-label">一级代理</span>
                <div class="tcc-input-row">
                  <input
                    v-model.number="tierCommissions.tier1"
                    type="number"
                    min="0"
                    max="0.5"
                    step="0.01"
                    class="tcc-input"
                  >
                  <span class="tcc-pct">{{ (tierCommissions.tier1 * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <div class="tcc-item">
                <span class="tcc-badge l2">L2</span>
                <span class="tcc-label">二级代理</span>
                <div class="tcc-input-row">
                  <input
                    v-model.number="tierCommissions.tier2"
                    type="number"
                    min="0"
                    max="0.5"
                    step="0.01"
                    class="tcc-input"
                  >
                  <span class="tcc-pct">{{ (tierCommissions.tier2 * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <div class="tcc-item">
                <span class="tcc-badge l3">L3</span>
                <span class="tcc-label">三级代理</span>
                <div class="tcc-input-row">
                  <input
                    v-model.number="tierCommissions.tier3"
                    type="number"
                    min="0"
                    max="0.5"
                    step="0.01"
                    class="tcc-input"
                  >
                  <span class="tcc-pct">{{ (tierCommissions.tier3 * 100).toFixed(0) }}%</span>
                </div>
              </div>
            </div>
            <button
              class="btn btn-primary"
              :disabled="savingTierCommissions"
              style="margin-top:16px"
              @click="saveTierCommissions"
            >
              <template v-if="!savingTierCommissions">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                ><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z" /><polyline points="17 21 17 13 7 13 7 21" /><polyline points="7 3 7 8 15 8" /></svg>
                保存比例
              </template>
              <template v-else>
                <span class="spinner-sm" /> 保存中
              </template>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Sub-tab: Fee Settings -->
    <div v-if="agentSubTab === 'fees'">
      <div class="ps-panel">
        <div class="ps-header">
          <h3>代理收费设置</h3>
        </div>
        <p class="ps-desc">
          开启后，新用户注册为普通用户，需付费升级为L1代理；关闭后，新用户注册即成为L1代理。
        </p>

        <div class="fee-section">
          <div class="fee-toggle-row">
            <label class="fee-label">付费升级代理</label>
            <span class="fee-hint">开启后注册为普通用户，需付费升级为L1代理</span>
            <label class="toggle-switch">
              <input
                v-model="agentFees.registration_enabled"
                type="checkbox"
              >
              <span class="toggle-slider" />
            </label>
          </div>
          <div
            v-if="agentFees.registration_enabled"
            class="fee-input-row"
          >
            <span class="fee-input-label">注册费用 (元)</span>
            <input
              v-model.number="agentFees.registration_fee"
              type="number"
              min="0"
              step="1"
              class="fee-input"
            >
          </div>
        </div>

        <div class="fee-section">
          <div class="fee-toggle-row">
            <label class="fee-label">代理升级收费</label>
            <label class="toggle-switch">
              <input
                v-model="agentFees.upgrade_enabled"
                type="checkbox"
              >
              <span class="toggle-slider" />
            </label>
          </div>
          <template v-if="agentFees.upgrade_enabled">
            <div class="fee-input-row">
              <span class="fee-input-label">L1 → L2 升级费用 (元)</span>
              <input
                v-model.number="agentFees.upgrade_l2_fee"
                type="number"
                min="0"
                step="1"
                class="fee-input"
              >
            </div>
            <div class="fee-input-row">
              <span class="fee-input-label">L2 → L3 升级费用 (元)</span>
              <input
                v-model.number="agentFees.upgrade_l3_fee"
                type="number"
                min="0"
                step="1"
                class="fee-input"
              >
            </div>
          </template>
        </div>

        <button
          class="btn btn-primary"
          :disabled="savingAgentFees"
          style="margin-top:16px"
          @click="saveAgentFees"
        >
          <template v-if="!savingAgentFees">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z" /><polyline points="17 21 17 13 7 13 7 21" /><polyline points="7 3 7 8 15 8" /></svg>
            保存设置
          </template>
          <template v-else>
            <span class="spinner-sm" /> 保存中
          </template>
        </button>
      </div>
    </div>

    <!-- Sub-tab: System Guide -->
    <div v-if="agentSubTab === 'guide'">
      <div class="ps-panel">
        <div class="ps-header">
          <h3>系统说明</h3>
        </div>
        <div class="guide-banner">
          <div class="guide-icon">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><circle
              cx="12"
              cy="12"
              r="10"
            /><path d="M12 16v-4" /><path d="M12 8h.01" /></svg>
          </div>
          <div>
            <h4>代理佣金系统说明</h4>
            <p>本系统采用二级推荐分佣模式，代理通过推荐码发展下级代理，从下级代理的订单中获得佣金分成。</p>
          </div>
        </div>

        <div class="guide-section">
          <h4>佣金比例</h4>
          <div class="guide-rate-row">
            <div class="guide-rate-card">
              <span class="grc-badge l1">L1</span>
              <span class="grc-label">一级代理</span>
              <span class="grc-value">订单金额的 50%</span>
            </div>
            <div class="guide-rate-card">
              <span class="grc-badge l2">L2</span>
              <span class="grc-label">二级代理</span>
              <span class="grc-value">订单金额的 30%</span>
            </div>
            <div class="guide-rate-card">
              <span class="grc-badge l3">L3</span>
              <span class="grc-label">三级代理</span>
              <span class="grc-value">订单金额的 20%</span>
            </div>
          </div>
        </div>

        <div class="guide-section">
          <h4>代理等级</h4>
          <ul class="guide-list">
            <li><strong>L1 (一级代理)</strong>：默认等级，注册即获得。享受基础佣金比例。</li>
            <li><strong>L2 (二级代理)</strong>：可通过付费升级或达到业绩要求免费升级。享受更高佣金比例，可发展下级代理。</li>
            <li><strong>L3 (三级代理)</strong>：最高等级，享受最高佣金比例和专属权益。</li>
          </ul>
        </div>

        <div class="guide-section">
          <h4>提现规则</h4>
          <ul class="guide-list">
            <li>佣金自动累计到代理余额，可随时申请提现</li>
            <li>提现申请由管理员审核，审核通过后转入用户余额</li>
            <li>最低提现金额为 ¥1.00</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>
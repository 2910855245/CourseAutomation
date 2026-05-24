<script setup lang="ts">
// @ts-nocheck
import { useAdminState } from './adminState'

const { DEEPSEEK_MODELS, acceptOrder, accountForm, accounts, active, activeTab, adFileInput, adFileUploading, adForm, adImgInput, addDomain, addDomainForm, adminPass, adminState, adminUser, adsList, agentFees, agentStats, agentStatusFilter, agentSubTab, agentTotal, agents, agentsByTier, alertCount, aliAccounts, all, allSidebarItems, allUp, applyAutoConcurrency, applyPackagePricing, applyingPackage, approveAgent, approveWithdrawal, base64, body, buildRiskChecks, cancelEditPricing, cancelQueueJob, captchaAnswer, captchaImage, captchaLoading, captchaToken, cfg, changeAdminPassword, changingPw, channelCodeHelp, channelCodeLabels, channelTestAccount, channelTestAllOk, channelTestChecks, channelTestLoading, channelTestQrImage, chars, checks, circumference, clearCommissionHistory, clearDeepseekKey, clearOrderHistory, clearQueueHistory, clearRiskAlerts, clearWithdrawalHistory, clearYpayOrderHistory, closeAccountModal, closeExpiredYpayOrders, closePayTest, codeLabel, commissionTotal, commissions, completeOrder, configs, count, creatingSubAdmin, currentRole, d, dash, dashError, deepseekApiKey, deepseekKeyMasked, deepseekTestResult, defaultCodes, deleteAccount, deleteAd, detectServerSpecs, doChangeTier, doCreateSubAdmin, doRevokeSubAdmin, doTopup, domainCount, downloadQrImage, downloadQrLoading, dsRes, editPricing, editingAccount, editingAd, editingPricing, end, enqueueOrder, examModel, executeOrder, failCount, failOrder, fd, file, filled, finalExamModel, fmtDate, fmtHeartbeat, fmtMoney, fmtShortDate, fn, genRandomStr, getPlatformName, getRecommendation, hChecks, hNameMap, hOrder, healthAccountInput, healthAccountSaving, healthChecking, healthIntervalInput, healthIntervalSaving, healthPasswordInput, healthSummary, homeworkModel, html, imgTag, interval, isLoggedIn, jsChanged, jsChecked, jsFiles, jsRes, key, list, loadAccounts, loadAds, loadAgentFees, loadAgentStats, loadAgents, loadAgentsByTier, loadCommissions, loadDashboard, loadDeepseekKey, loadHealthAccount, loadHealthInterval, loadOrders, loadPairQr, loadPlatformNames, loadPricing, loadProxySettings, loadQueueData, loadRiskData, loadSubAdmins, loadTierCommissions, loadUnifiedUsers, loadUsers, loadWithdrawals, loadYpay, loadYpayOrders, loadingAccounts, loadingAds, loadingAgents, loadingAgentsByTier, loadingCommissions, loadingDash, loadingHealth, loadingOrders, loadingQueue, loadingRisk, loadingSubAdmins, loadingUnified, loadingUsers, loadingWithdrawals, loadingYpayOrders, loginErr, marketForm, maxBarOrders, maxBarRevenue, maxPartnerStatusCount, maxStatusCount, maxWorkersInput, mobileSidebarOpen, needAppid, needQrUrl, needRemark, newRate, newStatus, newSubAdmin, newTierLevel, nextSlot, ok, okCount, onAdFileChange, onAdImgChange, onQrFileChange, openAddAccount, openCreateAd, openEditAccount, openEditAd, openRateModal, openTierModal, openTopup, orderStatusClass, orderStatusLabel, orders, ordersStatusFilter, ordersTotal, packagePricing, pairQrImage, pairQrLoading, pairQrTs, params, partnerAgentStats, partnerAllowedTabs, passCount, pauseQueue, payTestAccountId, payTestBatchId, payTestChannelName, payTestChecks, payTestExpired, payTestLoading, payTestPaid, payTestPolling, payTestQrImage, payTestReallyPrice, payTestStarted, payTestTimer, payTestTradeNo, payTypeLabels, personnelTab, platformColors, platformNames, platforms, pricingModel, proxyForm, proxySaving, proxyTestOk, proxyTestResult, proxyTesting, pwForm, qrFileInput, qrUploading, queueJobs, queuePausing, queueStats, queueStatusFilter, r, rateTarget, reactivateAgent, reader, recommendResult, recommending, regenerateYpayKey, rejectWithdrawal, relImgs, removeDomain, res, resetAccountForm, resetYpayConnection, resumeQueue, retryQueueJob, riskAlerts, riskCheckStep, riskChecking, riskChecks, riskDomainStatus, riskHealth, riskIntervalInput, riskJsStatus, riskLoginAndCheck, riskLoginForm, riskLoginLoading, riskNeedLogin, riskScore, riskScoreColor, riskScoreDash, riskScoreDesc, riskScoreLevel, riskScoreText, role, runDomainCheck, runFullRiskCheck, runHealthCheck, runJsCheck, runYpayTest, s, saveAccount, saveAd, saveAgentFees, saveDeepseekKey, saveHealthAccount, saveHealthInterval, saveModels, savePricingConfig, saveProxy, saveRate, saveRiskInterval, saveTierCommissions, saveYpayKeyOnly, saveYpaySettings, savingAccount, savingAd, savingAgentFees, savingDeepseekKey, savingModels, savingPricing, savingTierCommissions, serverPublicIp, serverSpecs, setMaxWorkers, showAccountModal, showAdModal, showAddDomainModal, showCertFields, showChannelTest, showCreateSubAdmin, showDeepseekKey, showHealthSettings, showPayTest, showQrModal, showRateModal, showTierModal, showTopupModal, sidebarCollapsed, sidebarGroups, someUp, st, start, startChannelPayTest, startPayTestPolling, statusClass, statusLabel, stopPayTestPolling, subAdmins, suspendAgent, switchTab, t, ta, taskTypeNames, testChannel, testDeepseekApi, testModelApi, testProxy, testingDeepseek, testingModel, tierCommissions, tierNames, tierTarget, toggleAccount, toggleAdActive, toppingUp, toppupMode, topupAmount, topupNote, topupTarget, totalPlatformOrders, triggerAdFileUpload, triggerAdImgUpload, triggerQrUpload, typeLabels, unifiedAgentFilter, unifiedRoleFilter, unifiedSearch, unifiedStats, unifiedTotal, unifiedUsers, usedSlots, users, usersSubTab, usersTotal, val, visibleSidebarGroups, warnCount, withdrawalStatusFilter, withdrawals, withdrawalsTotal, wxAccounts, ypayAccounts, ypayForm, ypayLoaded, ypayOrderFilters, ypayOrderStatusFilter, ypayOrders, ypayOrdersPage, ypayOrdersTotal, ypaySaving, ypayStateLabels, ypayStatus, ypayTab, ypayTestResult, ypayTesting } = useAdminState()
</script>

<template>
  <div>
    <div class="agent-subtabs">
      <button
        v-if="currentRole === 'admin'"
        :class="['ast', { active: usersSubTab === 'users' }]"
        @click="usersSubTab = 'users'"
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
        全部用户
      </button>
      <button
        v-if="currentRole === 'admin'"
        :class="['ast', { active: usersSubTab === 'subadmins' }]"
        @click="usersSubTab = 'subadmins'"
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
        /><path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" /></svg>
        合伙人
      </button>
    </div>

    <!-- Sub-tab: All Users (unified) -->
    <div v-if="usersSubTab === 'users'">
      <div
        v-if="unifiedStats"
        class="agent-stats-row"
      >
        <div class="mini-stat">
          <div class="ms-val">
            {{ unifiedStats.total_users || 0 }}
          </div><div class="ms-label">
            总用户数
          </div>
        </div>
        <div class="mini-stat">
          <div class="ms-val ok">
            {{ unifiedStats.total_agents || 0 }}
          </div><div class="ms-label">
            总代理数
          </div>
        </div>
        <div class="mini-stat">
          <div class="ms-val money">
            {{ unifiedStats.active_agents || 0 }}
          </div><div class="ms-label">
            活跃代理
          </div>
        </div>
        <div class="mini-stat">
          <div class="ms-val">
            {{ unifiedStats.pending_agents || 0 }}
          </div><div class="ms-label">
            待审核代理
          </div>
        </div>
      </div>
      <div class="section-actions">
        <div class="filter-bar">
          <div class="filter-scroll">
            <button
              :class="['chip', { active: unifiedRoleFilter === '' }]"
              @click="unifiedRoleFilter = ''; loadUnifiedUsers()"
            >
              全部
            </button>
            <button
              :class="['chip', { active: unifiedRoleFilter === 'sub_admin' }]"
              @click="unifiedRoleFilter = 'sub_admin'; loadUnifiedUsers()"
            >
              合伙人
            </button>
            <button
              :class="['chip', { active: unifiedRoleFilter === 'agent' }]"
              @click="unifiedRoleFilter = 'agent'; loadUnifiedUsers()"
            >
              代理
            </button>
            <button
              :class="['chip', { active: unifiedRoleFilter === 'customer' }]"
              @click="unifiedRoleFilter = 'customer'; loadUnifiedUsers()"
            >
              普通用户
            </button>
            <template v-if="unifiedRoleFilter === 'agent' || unifiedRoleFilter === 'sub_admin' || unifiedRoleFilter === ''">
              <span class="filter-divider" />
              <button
                :class="['chip', { active: unifiedAgentFilter === '' }]"
                @click="unifiedAgentFilter = ''; loadUnifiedUsers()"
              >
                全部状态
              </button>
              <button
                :class="['chip', { active: unifiedAgentFilter === 'pending' }]"
                @click="unifiedAgentFilter = 'pending'; loadUnifiedUsers()"
              >
                待审核
              </button>
              <button
                :class="['chip', { active: unifiedAgentFilter === 'active' }]"
                @click="unifiedAgentFilter = 'active'; loadUnifiedUsers()"
              >
                活跃
              </button>
              <button
                :class="['chip', { active: unifiedAgentFilter === 'suspended' }]"
                @click="unifiedAgentFilter = 'suspended'; loadUnifiedUsers()"
              >
                已暂停
              </button>
            </template>
          </div>
        </div>
        <div class="filter-search-row">
          <input
            v-model="unifiedSearch"
            placeholder="搜索用户名/昵称"
            class="search-input"
            @keyup.enter="loadUnifiedUsers"
          >
          <button
            class="btn btn-ghost"
            :disabled="loadingUnified"
            @click="loadUnifiedUsers"
          >
            <span
              v-if="loadingUnified"
              class="spinner"
              style="width:14px;height:14px"
            />
            {{ loadingUnified ? '加载中' : '刷新' }}
          </button>
        </div>
      </div>
      <div
        v-if="unifiedUsers.length > 0"
        class="table-wrap"
      >
        <table class="data-table">
          <thead>
            <tr>
              <th>用户名</th><th>角色/等级</th><th>佣金比例</th><th>用户余额</th><th>代理余额</th><th>订单数</th><th>邀请人数</th><th>状态</th><th>注册时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="u in unifiedUsers"
              :key="u.user_id"
            >
              <td>
                <div class="user-cell">
                  <span class="uname">{{ u.nickname || u.username }}</span>
                  <span class="uid">{{ u.username }}</span>
                </div>
              </td>
              <td>
                <span
                  v-if="u.role === 'admin'"
                  class="status-tag bad"
                >管理员</span>
                <span
                  v-else-if="u.role === 'sub_admin'"
                  class="status-tag primary"
                >合伙人</span>
                <template v-else-if="u.agent">
                  <span class="status-tag primary">代理</span>
                  <span
                    class="level-tag"
                    :class="'l' + u.agent.tier_level"
                    style="margin-left:4px"
                  >L{{ u.agent.tier_level }}</span>
                </template>
                <span
                  v-else
                  class="status-tag muted"
                >用户</span>
              </td>
              <td>{{ u.agent ? (u.agent.flow_commission_rate * 100).toFixed(0) + '%' : '-' }}</td>
              <td class="money-cell">
                {{ fmtMoney(u.balance) }}
              </td>
              <td class="money-cell">
                {{ u.agent ? fmtMoney(u.agent.available_balance) : '-' }}
              </td>
              <td>{{ u.order_count || 0 }}</td>
              <td>{{ u.referral_count || 0 }}</td>
              <td>
                <span
                  v-if="u.agent"
                  :class="['status-tag', statusClass[u.agent.status]]"
                >{{ statusLabel[u.agent.status] || u.agent.status }}</span>
                <span
                  v-else
                  class="status-tag ok"
                >正常</span>
              </td>
              <td class="date-cell">
                {{ fmtDate(u.created_at) }}
              </td>
              <td>
                <div class="action-group">
                  <button
                    class="btn btn-xs btn-success"
                    @click="openTopup(u, 'topup')"
                  >
                    充值
                  </button>
                  <button
                    class="btn btn-xs btn-warn"
                    @click="openTopup(u, 'deduct')"
                  >
                    扣费
                  </button>
                  <template v-if="u.agent">
                    <button
                      v-if="u.agent.status === 'pending'"
                      class="btn btn-xs btn-success"
                      @click="approveAgent(u.agent.agent_id)"
                    >
                      审核
                    </button>
                    <button
                      v-if="u.agent.status === 'active'"
                      class="btn btn-xs btn-warn"
                      @click="suspendAgent(u.agent.agent_id)"
                    >
                      暂停
                    </button>
                    <button
                      v-if="u.agent.status === 'suspended'"
                      class="btn btn-xs btn-primary"
                      @click="reactivateAgent(u.agent.agent_id)"
                    >
                      恢复
                    </button>
                    <button
                      class="btn btn-xs btn-ghost"
                      @click="openRateModal(u.agent)"
                    >
                      调比例
                    </button>
                  </template>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        v-else-if="!loadingUnified"
        class="empty"
      >
        <p>暂无用户数据</p>
      </div>
    </div>

    <!-- Sub-tab: Sub-admins -->
    <div v-if="usersSubTab === 'subadmins'">
      <div class="ps-panel">
        <div class="ps-header">
          <h3>合伙人列表</h3>
          <button
            class="btn btn-sm btn-primary"
            @click="showCreateSubAdmin = true"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><line
              x1="12"
              y1="5"
              x2="12"
              y2="19"
            /><line
              x1="5"
              y1="12"
              x2="19"
              y2="12"
            /></svg>
            添加合伙人
          </button>
        </div>
        <p class="ps-desc">
          合伙人拥有代理审核、订单管理、佣金查看等权限，但不能管理系统配置和人员管理。
        </p>
        <div
          v-if="loadingSubAdmins"
          class="ps-loading"
        >
          加载中...
        </div>
        <div
          v-else-if="!subAdmins.length"
          class="ps-empty"
        >
          <span class="ps-empty-icon">
            <svg
              width="40"
              height="40"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#94a3b8"
              stroke-width="1.5"
            ><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle
              cx="9"
              cy="7"
              r="4"
            /><path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" /></svg>
          </span>
          <p>暂无合伙人，点击上方按钮添加</p>
        </div>
        <div
          v-else
          class="ps-table-wrap"
        >
          <table class="data-table">
            <thead><tr><th>用户名</th><th>用户ID</th><th>角色</th><th>注册时间</th><th>关联代理</th><th>操作</th></tr></thead>
            <tbody>
              <tr
                v-for="s in subAdmins"
                :key="s.user_id"
              >
                <td><strong>{{ s.username }}</strong></td>
                <td><code>{{ s.user_id }}</code></td>
                <td><span class="badge badge-info">合伙人</span></td>
                <td>{{ fmtShortDate(s.created_at) }}</td>
                <td>
                  <template v-if="s.agent">
                    <span class="badge badge-success">L{{ s.agent.tier_level }}</span>
                    <span style="font-size:12px;color:#64748b;margin-left:4px">推荐码: {{ s.agent.referral_code }}</span>
                  </template>
                  <span
                    v-else
                    class="text-muted"
                    style="font-size:12px"
                  >-</span>
                </td>
                <td>
                  <button
                    class="btn btn-xs btn-ghost"
                    style="color:var(--c-danger)"
                    @click="doRevokeSubAdmin(s.user_id)"
                  >
                    撤销权限
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
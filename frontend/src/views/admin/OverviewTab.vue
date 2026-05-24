<script setup lang="ts">
// @ts-nocheck
import { useAdminState } from './adminState'

const { DEEPSEEK_MODELS, acceptOrder, accountForm, accounts, active, activeTab, adFileInput, adFileUploading, adForm, adImgInput, addDomain, addDomainForm, adminPass, adminState, adminUser, adsList, agentFees, agentStats, agentStatusFilter, agentSubTab, agentTotal, agents, agentsByTier, alertCount, aliAccounts, all, allSidebarItems, allUp, applyAutoConcurrency, applyPackagePricing, applyingPackage, approveAgent, approveWithdrawal, base64, body, buildRiskChecks, cancelEditPricing, cancelQueueJob, captchaAnswer, captchaImage, captchaLoading, captchaToken, cfg, changeAdminPassword, changingPw, channelCodeHelp, channelCodeLabels, channelTestAccount, channelTestAllOk, channelTestChecks, channelTestLoading, channelTestQrImage, chars, checks, circumference, clearCommissionHistory, clearDeepseekKey, clearOrderHistory, clearQueueHistory, clearRiskAlerts, clearWithdrawalHistory, clearYpayOrderHistory, closeAccountModal, closeExpiredYpayOrders, closePayTest, codeLabel, commissionTotal, commissions, completeOrder, configs, count, creatingSubAdmin, currentRole, d, dash, dashError, deepseekApiKey, deepseekKeyMasked, deepseekTestResult, defaultCodes, deleteAccount, deleteAd, detectServerSpecs, doChangeTier, doCreateSubAdmin, doRevokeSubAdmin, doTopup, domainCount, downloadQrImage, downloadQrLoading, dsRes, editPricing, editingAccount, editingAd, editingPricing, end, enqueueOrder, examModel, executeOrder, failCount, failOrder, fd, file, filled, finalExamModel, fmtDate, fmtHeartbeat, fmtMoney, fmtShortDate, fn, genRandomStr, getPlatformName, getRecommendation, hChecks, hNameMap, hOrder, healthAccountInput, healthAccountSaving, healthChecking, healthIntervalInput, healthIntervalSaving, healthPasswordInput, healthSummary, homeworkModel, html, imgTag, interval, isLoggedIn, jsChanged, jsChecked, jsFiles, jsRes, key, list, loadAccounts, loadAds, loadAgentFees, loadAgentStats, loadAgents, loadAgentsByTier, loadCommissions, loadDashboard, loadDeepseekKey, loadHealthAccount, loadHealthInterval, loadOrders, loadPairQr, loadPlatformNames, loadPricing, loadProxySettings, loadQueueData, loadRiskData, loadSubAdmins, loadTierCommissions, loadUnifiedUsers, loadUsers, loadWithdrawals, loadYpay, loadYpayOrders, loadingAccounts, loadingAds, loadingAgents, loadingAgentsByTier, loadingCommissions, loadingDash, loadingHealth, loadingOrders, loadingQueue, loadingRisk, loadingSubAdmins, loadingUnified, loadingUsers, loadingWithdrawals, loadingYpayOrders, loginErr, marketForm, maxBarOrders, maxBarRevenue, maxPartnerStatusCount, maxStatusCount, maxWorkersInput, mobileSidebarOpen, needAppid, needQrUrl, needRemark, newRate, newStatus, newSubAdmin, newTierLevel, nextSlot, ok, okCount, onAdFileChange, onAdImgChange, onQrFileChange, openAddAccount, openCreateAd, openEditAccount, openEditAd, openRateModal, openTierModal, openTopup, orderStatusClass, orderStatusLabel, orders, ordersStatusFilter, ordersTotal, packagePricing, pairQrImage, pairQrLoading, pairQrTs, params, partnerAgentStats, partnerAllowedTabs, passCount, pauseQueue, payTestAccountId, payTestBatchId, payTestChannelName, payTestChecks, payTestExpired, payTestLoading, payTestPaid, payTestPolling, payTestQrImage, payTestReallyPrice, payTestStarted, payTestTimer, payTestTradeNo, payTypeLabels, personnelTab, platformColors, platformNames, platforms, pricingModel, proxyForm, proxySaving, proxyTestOk, proxyTestResult, proxyTesting, pwForm, qrFileInput, qrUploading, queueJobs, queuePausing, queueStats, queueStatusFilter, r, rateTarget, reactivateAgent, reader, recommendResult, recommending, regenerateYpayKey, rejectWithdrawal, relImgs, removeDomain, res, resetAccountForm, resetYpayConnection, resumeQueue, retryQueueJob, riskAlerts, riskCheckStep, riskChecking, riskChecks, riskDomainStatus, riskHealth, riskIntervalInput, riskJsStatus, riskLoginAndCheck, riskLoginForm, riskLoginLoading, riskNeedLogin, riskScore, riskScoreColor, riskScoreDash, riskScoreDesc, riskScoreLevel, riskScoreText, role, runDomainCheck, runFullRiskCheck, runHealthCheck, runJsCheck, runYpayTest, s, saveAccount, saveAd, saveAgentFees, saveDeepseekKey, saveHealthAccount, saveHealthInterval, saveModels, savePricingConfig, saveProxy, saveRate, saveRiskInterval, saveTierCommissions, saveYpayKeyOnly, saveYpaySettings, savingAccount, savingAd, savingAgentFees, savingDeepseekKey, savingModels, savingPricing, savingTierCommissions, serverPublicIp, serverSpecs, setMaxWorkers, showAccountModal, showAdModal, showAddDomainModal, showCertFields, showChannelTest, showCreateSubAdmin, showDeepseekKey, showHealthSettings, showPayTest, showQrModal, showRateModal, showTierModal, showTopupModal, sidebarCollapsed, sidebarGroups, someUp, st, start, startChannelPayTest, startPayTestPolling, statusClass, statusLabel, stopPayTestPolling, subAdmins, suspendAgent, switchTab, t, ta, taskTypeNames, testChannel, testDeepseekApi, testModelApi, testProxy, testingDeepseek, testingModel, tierCommissions, tierNames, tierTarget, toggleAccount, toggleAdActive, toppingUp, toppupMode, topupAmount, topupNote, topupTarget, totalPlatformOrders, triggerAdFileUpload, triggerAdImgUpload, triggerQrUpload, typeLabels, unifiedAgentFilter, unifiedRoleFilter, unifiedSearch, unifiedStats, unifiedTotal, unifiedUsers, usedSlots, users, usersSubTab, usersTotal, val, visibleSidebarGroups, warnCount, withdrawalStatusFilter, withdrawals, withdrawalsTotal, wxAccounts, ypayAccounts, ypayForm, ypayLoaded, ypayOrderFilters, ypayOrderStatusFilter, ypayOrders, ypayOrdersPage, ypayOrdersTotal, ypaySaving, ypayStateLabels, ypayStatus, ypayTab, ypayTestResult, ypayTesting } = useAdminState()
</script>

<template>
  <div>
    <!-- Partner financial report -->
    <div
      v-if="dash && currentRole === 'sub_admin'"
      class="overview-content"
    >
      <div class="kpi-row">
        <div class="kpi-card">
          <div class="kpi-icon rev">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><line
              x1="12"
              y1="1"
              x2="12"
              y2="23"
            /><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ fmtMoney(dash.total_revenue || 0) }}
            </div>
            <div class="kpi-label">
              总收入
            </div>
          </div>
          <div class="kpi-sub">
            订单 {{ fmtMoney(dash.total_revenue - (dash.agent_upgrades?.revenue || 0)) }}
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon ord">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ dash.total_orders || 0 }}
            </div>
            <div class="kpi-label">
              总订单
            </div>
          </div>
          <div class="kpi-sub">
            完成率 {{ dash.total_orders > 0 ? ((dash.by_status?.completed?.count || 0) / dash.total_orders * 100).toFixed(1) : 0 }}%
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon usr">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><polyline points="20 6 9 17 4 12" /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ fmtMoney(dash.by_status?.completed?.revenue || 0) }}
            </div>
            <div class="kpi-label">
              完成收入
            </div>
          </div>
          <div class="kpi-sub">
            {{ dash.by_status?.completed?.count || 0 }} 单
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon agt">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 22 12 18.56 5.82 22 7 14.14l-5-4.87 6.91-1.01z" /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ fmtMoney(dash.agent_upgrades?.revenue || 0) }}
            </div>
            <div class="kpi-label">
              代理升级收入
            </div>
          </div>
          <div class="kpi-sub">
            {{ dash.agent_upgrades?.count || 0 }} 笔
          </div>
        </div>
      </div>

      <div class="panel-row">
        <div class="panel panel-wide">
          <div class="panel-head">
            <h3>收入明细</h3>
          </div>
          <div class="table-wrap">
            <table
              class="data-table"
              style="font-size:13px"
            >
              <thead><tr><th>项目</th><th>订单数</th><th>金额</th><th>占比</th></tr></thead>
              <tbody>
                <tr
                  v-for="(v, k) in dash.by_status"
                  :key="k"
                >
                  <td><span :class="['status-tag', orderStatusClass[k]]">{{ orderStatusLabel[k] || k }}</span></td>
                  <td>{{ v.count }}</td>
                  <td class="money-cell">
                    {{ fmtMoney(v.revenue) }}
                  </td>
                  <td>{{ dash.total_revenue > 0 ? (v.revenue / dash.total_revenue * 100).toFixed(1) : 0 }}%</td>
                </tr>
                <tr v-if="dash.agent_upgrades?.revenue">
                  <td><span class="status-tag primary">代理升级</span></td>
                  <td>{{ dash.agent_upgrades.count || 0 }}</td>
                  <td class="money-cell">
                    {{ fmtMoney(dash.agent_upgrades.revenue) }}
                  </td>
                  <td>{{ dash.total_revenue > 0 ? (dash.agent_upgrades.revenue / dash.total_revenue * 100).toFixed(1) : 0 }}%</td>
                </tr>
              </tbody>
              <tfoot>
                <tr style="font-weight:600">
                  <td>合计</td>
                  <td>{{ dash.total_orders }}</td>
                  <td class="money-cell">
                    {{ fmtMoney(dash.total_revenue) }}
                  </td>
                  <td>100%</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      </div>

      <div class="panel-row">
        <div class="panel panel-wide">
          <div class="panel-head">
            <h3>订单状态分布</h3>
          </div>
          <div class="status-bars">
            <div
              v-for="(v, k) in dash.by_status"
              :key="k"
              class="sb-row"
            >
              <div class="sb-label">
                {{ orderStatusLabel[k] || k }}
              </div>
              <div class="sb-track">
                <div
                  class="sb-fill"
                  :class="'sb-' + (orderStatusClass[k] || 'primary')"
                  :style="{ width: maxPartnerStatusCount > 0 ? (v.count / maxPartnerStatusCount * 100) + '%' : '0%' }"
                />
              </div>
              <div class="sb-val">
                {{ v.count }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <!-- Admin full overview -->
    <div
      v-else-if="dash"
      class="overview-content"
    >
      <div class="kpi-row">
        <div class="kpi-card">
          <div class="kpi-icon rev">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><line
              x1="12"
              y1="1"
              x2="12"
              y2="23"
            /><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ fmtMoney(dash.revenue.today) }}
            </div>
            <div class="kpi-label">
              今日收入
            </div>
          </div>
          <div class="kpi-sub">
            本周 {{ fmtMoney(dash.revenue.week) }}
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon ord">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" /><line
              x1="16"
              y1="13"
              x2="8"
              y2="13"
            /><line
              x1="16"
              y1="17"
              x2="8"
              y2="17"
            /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ dash.orders.today }}
            </div>
            <div class="kpi-label">
              今日订单
            </div>
          </div>
          <div class="kpi-sub">
            本周 {{ dash.orders.week }} 单
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon usr">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" /><circle
              cx="12"
              cy="7"
              r="4"
            /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ dash.users.total }}
            </div>
            <div class="kpi-label">
              总用户数
            </div>
          </div>
          <div class="kpi-sub">
            今日新增 {{ dash.users.new_today }}
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon agt">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle
              cx="9"
              cy="7"
              r="4"
            /><path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ dash.agents.active }}
            </div>
            <div class="kpi-label">
              活跃代理
            </div>
          </div>
          <div class="kpi-sub">
            待审核 {{ dash.agents.pending }}
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon usr">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle
              cx="8.5"
              cy="7"
              r="4"
            /><line
              x1="20"
              y1="8"
              x2="20"
              y2="14"
            /><line
              x1="23"
              y1="11"
              x2="17"
              y2="11"
            /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ dash.agents.total || 0 }}
            </div>
            <div class="kpi-label">
              代理总数
            </div>
          </div>
          <div class="kpi-sub">
            今日 +{{ dash.agents.new_today || 0 }} · 本周 +{{ dash.agents.new_week || 0 }}
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon rate">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ dash.orders.completion_rate }}%
            </div>
            <div class="kpi-label">
              完成率
            </div>
          </div>
          <div class="kpi-sub">
            累计 {{ dash.orders.completed }}/{{ dash.orders.total }}
          </div>
        </div>
        <div
          v-if="dash.agent_upgrades"
          class="kpi-card"
        >
          <div class="kpi-icon upg">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 22 12 18.56 5.82 22 7 14.14l-5-4.87 6.91-1.01z" /></svg>
          </div>
          <div class="kpi-body">
            <div class="kpi-val">
              {{ fmtMoney(dash.agent_upgrades.today_revenue) }}
            </div>
            <div class="kpi-label">
              代理升级收入
            </div>
          </div>
          <div class="kpi-sub">
            今日 {{ dash.agent_upgrades.today_count }} 笔 · 本周 {{ fmtMoney(dash.agent_upgrades.week_revenue) }}
          </div>
        </div>
      </div>

      <div class="panel-row">
        <div class="panel panel-wide">
          <div class="panel-head">
            <h3>近7天收入与订单趋势</h3>
            <div class="legend-row">
              <span class="legend"><b class="ldot ldot-rev" />收入</span>
              <span class="legend"><b class="ldot ldot-ord" />订单</span>
            </div>
          </div>
          <div class="chart-area">
            <div
              v-for="day in dash.recent_7_days"
              :key="day.date"
              class="bar-group"
            >
              <div class="bars">
                <div
                  class="bar bar-rev"
                  :style="{ height: (day.revenue / maxBarRevenue * 100) + '%' }"
                  :title="'收入 ' + fmtMoney(day.revenue)"
                />
                <div
                  class="bar bar-ord"
                  :style="{ height: (day.orders / maxBarOrders * 100) + '%' }"
                  :title="'订单 ' + day.orders"
                />
              </div>
              <div class="bar-label">
                {{ day.date }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel-row">
        <div class="panel panel-wide">
          <div class="panel-head">
            <h3>订单状态分布</h3>
          </div>
          <div class="status-bars">
            <div
              v-for="sd in dash.status_distribution"
              :key="sd.status"
              class="sb-row"
            >
              <div class="sb-label">
                {{ orderStatusLabel[sd.status] || sd.status }}
              </div>
              <div class="sb-track">
                <div
                  class="sb-fill"
                  :class="'sb-' + (orderStatusClass[sd.status] || 'primary')"
                  :style="{ width: maxStatusCount > 0 ? (sd.count / maxStatusCount * 100) + '%' : '0%' }"
                />
              </div>
              <div class="sb-val">
                {{ sd.count }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel-row">
        <div class="panel">
          <div class="panel-head">
            <h3>平台分布</h3>
          </div>
          <div
            v-if="dash.platform_distribution.length"
            class="plat-list"
          >
            <div
              v-for="(p, i) in dash.platform_distribution"
              :key="p.website_id"
              class="plat-item"
            >
              <div class="plat-left">
                <span
                  class="plat-dot"
                  :style="{ background: platformColors[i] || '#6b7280' }"
                />
                <span class="plat-name">{{ getPlatformName(p.website_id) }}</span>
              </div>
              <div class="plat-right">
                <div class="plat-bar-bg">
                  <div
                    class="plat-bar-fill"
                    :style="{ width: (p.count / totalPlatformOrders * 100) + '%', background: platformColors[i] || '#6b7280' }"
                  />
                </div>
                <span class="plat-cnt">{{ p.count }}单</span>
                <span class="plat-rev">{{ fmtMoney(p.revenue) }}</span>
              </div>
            </div>
          </div>
          <div
            v-else
            class="empty-sm"
          >
            暂无数据
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h3>任务类型分布</h3>
          </div>
          <div
            v-if="dash.task_type_distribution.length"
            class="type-cards"
          >
            <div
              v-for="td in dash.task_type_distribution"
              :key="td.task_type"
              class="type-card"
            >
              <div class="tc-icon">
                {{ taskTypeNames[td.task_type] || td.task_type }}
              </div>
              <div class="tc-count">
                {{ td.count }}单
              </div>
              <div class="tc-rev">
                {{ fmtMoney(td.revenue) }}
              </div>
            </div>
          </div>
          <div
            v-else
            class="empty-sm"
          >
            暂无数据
          </div>
        </div>
      </div>

      <div class="panel-row">
        <div class="panel">
          <div class="panel-head">
            <h3>代理层级分布</h3>
          </div>
          <div
            v-if="dash.agents.by_tier && Object.keys(dash.agents.by_tier).length"
            class="plat-list"
          >
            <div
              v-for="(cnt, tier) in dash.agents.by_tier"
              :key="tier"
              class="plat-item"
            >
              <div class="plat-left">
                <span
                  class="plat-dot"
                  :style="{ background: ['#6366f1','#8b5cf6','#a855f7','#d946ef'][Number(tier)-1] || '#6b7280' }"
                />
                <span class="plat-name">{{ tierNames[tier] || 'L' + tier }}</span>
              </div>
              <div class="plat-right">
                <div class="plat-bar-bg">
                  <div
                    class="plat-bar-fill"
                    :style="{ width: (cnt / dash.agents.active * 100) + '%', background: ['#6366f1','#8b5cf6','#a855f7','#d946ef'][Number(tier)-1] || '#6b7280' }"
                  />
                </div>
                <span class="plat-cnt">{{ cnt }}人</span>
              </div>
            </div>
          </div>
          <div
            v-else
            class="empty-sm"
          >
            暂无代理
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h3>代理统计概览</h3>
          </div>
          <div class="type-cards">
            <div class="type-card">
              <div class="tc-icon">
                活跃
              </div>
              <div class="tc-count">
                {{ dash.agents.active }}人
              </div>
            </div>
            <div class="type-card">
              <div class="tc-icon">
                待审
              </div>
              <div class="tc-count">
                {{ dash.agents.pending }}人
              </div>
            </div>
            <div class="type-card">
              <div class="tc-icon">
                拒绝
              </div>
              <div class="tc-count">
                {{ dash.agents.rejected || 0 }}人
              </div>
            </div>
            <div class="type-card">
              <div class="tc-icon">
                佣金
              </div>
              <div class="tc-rev">
                {{ fmtMoney(dash.agents.total_commission) }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel-row">
        <div class="panel panel-wide-sm">
          <div class="panel-head">
            <h3>最近订单</h3>
          </div>
          <div
            v-if="dash.recent_orders.length"
            class="mini-table"
          >
            <div class="mt-row mt-head">
              <span class="mt-col">用户</span><span class="mt-col">平台</span><span class="mt-col">类型</span>
              <span class="mt-col">金额</span><span class="mt-col">状态</span><span class="mt-col">时间</span>
            </div>
            <div
              v-for="o in dash.recent_orders"
              :key="o.order_id"
              class="mt-row"
            >
              <span class="mt-col mt-uname">{{ o.username }}</span>
              <span class="mt-col">{{ getPlatformName(o.website_id) }}</span>
              <span class="mt-col">{{ taskTypeNames[o.task_type] || o.task_type }}</span>
              <span class="mt-col mt-money">{{ fmtMoney(o.price) }}</span>
              <span class="mt-col"><span :class="['status-tag', orderStatusClass[o.status]]">{{ orderStatusLabel[o.status] || o.status }}</span></span>
              <span class="mt-col mt-date">{{ fmtShortDate(o.created_at) }}</span>
            </div>
          </div>
          <div
            v-else
            class="empty-sm"
          >
            暂无订单
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h3>代理排行榜</h3>
          </div>
          <div
            v-if="dash.top_agents.length"
            class="rank-list"
          >
            <div
              v-for="(a, i) in dash.top_agents"
              :key="a.agent_id"
              class="rank-item"
            >
              <span
                class="rank-no"
                :class="'r' + (i + 1)"
              >{{ i + 1 }}</span>
              <div class="rank-info">
                <span class="rank-name">{{ a.display_name || a.referral_code }}</span>
                <span class="rank-code">{{ a.referral_code }}</span>
              </div>
              <span class="rank-earn">{{ fmtMoney(a.total_earnings) }}</span>
            </div>
          </div>
          <div
            v-else
            class="empty-sm"
          >
            暂无代理
          </div>
        </div>
      </div>
    </div>
    <div
      v-else-if="dashError"
      class="empty"
    >
      <p style="color:#ef4444;font-weight:600;margin-bottom:4px">
        数据加载失败
      </p>
      <p style="color:#94a3b8;font-size:12px;margin-bottom:16px">
        {{ dashError }}
      </p>
      <button
        class="btn btn-primary btn-sm"
        @click="loadDashboard"
      >
        重试
      </button>
    </div>
    <div
      v-else-if="!loadingDash"
      class="empty"
    >
      <p>点击刷新加载数据</p>
    </div>
  </div>
</template>
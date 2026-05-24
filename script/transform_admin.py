"""Transform Admin.vue to use tab components with provide/inject."""
import re

ADMIN_VUE = r"C:\Users\win\Desktop\刷课平台js逆向\Anti-Course Cheating Plugin\frontend\src\views\Admin.vue"

with open(ADMIN_VUE, encoding="utf-8") as f:
    content = f.read()

# Step 1: Add imports
imports = """import { provideAdminState } from '@/views/admin/adminState'
import OverviewTab from '@/views/admin/OverviewTab.vue'
import CommissionsTab from '@/views/admin/CommissionsTab.vue'
import OrdersTab from '@/views/admin/OrdersTab.vue'
import UsersTab from '@/views/admin/UsersTab.vue'
import AgentsTab from '@/views/admin/AgentsTab.vue'
import WithdrawalsTab from '@/views/admin/WithdrawalsTab.vue'
import QueueTab from '@/views/admin/QueueTab.vue'
import ProxyTab from '@/views/admin/ProxyTab.vue'
import SecurityTab from '@/views/admin/SecurityTab.vue'
import RiskTab from '@/views/admin/RiskTab.vue'
import PricingTab from '@/views/admin/PricingTab.vue'
import YpayTab from '@/views/admin/YpayTab.vue'
import AdsTab from '@/views/admin/AdsTab.vue'
"""

# Add after AppTopbar import
content = content.replace(
    "import AppTopbar from '@/components/AppTopbar.vue'\n",
    "import AppTopbar from '@/components/AppTopbar.vue'\n" + imports
)

# Step 2: Add provideAdminState() call after all the ref/function declarations
# Find a good insertion point — after the last handler function definition
# We'll insert it before the onMounted call
provide_call = """
// Provide state to tab components
provideAdminState({
  currentRole, isLoggedIn,
  dash, dashError, loadingDash,
  maxBarRevenue, maxBarOrders, maxStatusCount, maxPartnerStatusCount,
  totalPlatformOrders, platformColors, tierNames,
  orderStatusLabel, orderStatusClass, taskTypeNames,
  orders, ordersTotal, ordersStatusFilter, loadingOrders,
  users, usersTotal, loadingUsers, usersSubTab,
  unifiedUsers, unifiedTotal, unifiedStats, unifiedRoleFilter,
  unifiedAgentFilter, unifiedSearch, loadingUnified,
  showTopupModal, topupTarget, topupAmount, topupNote, toppupMode, toppingUp,
  subAdmins, loadingSubAdmins, showCreateSubAdmin, newSubAdmin,
  statusClass, statusLabel,
  agents, agentTotal, agentStatusFilter, agentStats, loadingAgents,
  partnerAgentStats, agentSubTab, showTierModal, tierForm, agentTiers,
  commissions, commissionTotal, loadingCommissions,
  showRateModal, rateTarget, newRate,
  withdrawals, withdrawalsTotal, withdrawalStatusFilter, loadingWithdrawals, showQrModal,
  queueJobs, queueStats, loadingQueue,
  proxyForm, proxySaving, proxyTesting, proxyTestResult, proxyTestOk, serverPublicIp,
  secConfig, secSaving, pwForm, changingPw, loginLogs, loadingLoginLogs,
  riskConfig, riskSaving, riskStats, blacklist, loadingBlacklist,
  showAddBlackModal, newBlackItem, riskLogs, loadingRiskLogs,
  pricing, pricingSaving, showAddPriceModal, editingPrice, priceForm,
  ypaySettings, ypayAccounts, ypayOrders, ypayTmpPrices, ypaySaving,
  showYpayModal, editingYpayAccount, ypayForm, showYpayOrderModal, ypayOrderForm,
  showPairModal, pairCode, pairStatus, pairPolling, ypayEditingTmpPriceId,
  adsList, loadingAds, showAdModal, editingAd, adForm, savingAd, adFileUploading,
  sidebarCollapsed, mobileSidebarOpen, activeTab,
  loadDashboard, loadOrders, clearOrderHistory,
  acceptOrder, executeOrder, enqueueOrder, completeOrder, failOrder,
  loadUnifiedUsers, loadSubAdmins, createSubAdmin, deleteSubAdmin,
  openTopup, doTopup, approveAgent, suspendAgent, reactivateAgent,
  openRateModal, loadAgents, saveTier, deleteTier, loadAgentTiers, openCreateTier,
  loadCommissions, clearCommissionHistory,
  loadWithdrawals, approveWithdrawal, rejectWithdrawal, showQr, clearWithdrawalHistory,
  loadQueue, cancelQueueJob, retryQueueJob, clearQueueHistory,
  testProxy, saveProxy,
  saveSecConfig, changePw, loadLoginLogs,
  saveRiskConfig, loadBlacklist, addBlackItem, removeBlackItem,
  loadRiskLogs, clearRiskLogs,
  savePricing, addPriceRule, editPriceRule, deletePriceRule, savePriceRule,
  saveYpaySettings, loadYpayAccounts, addYpayAccount, editYpayAccount,
  deleteYpayAccount, saveYpayAccount, loadYpayOrders, createYpayOrder,
  deleteYpayOrder, loadYpayTmpPrices, addYpayTmpPrice, deleteYpayTmpPrice,
  startPairing, stopPairing,
  openCreateAd, openEditAd, saveAd, toggleAdActive, deleteAd,
  triggerAdFileUpload, triggerAdImgUpload, onAdFileChange, onAdImgChange,
  switchTab,
  fmtMoney, fmtDate, fmtShortDate, getPlatformName,
})

"""

# Insert before onMounted
content = content.replace(
    "\nonMounted(() => {",
    "\n" + provide_call + "onMounted(() => {"
)

# Step 3: Replace tab blocks with component tags
tab_replacements = [
    ("overview", "OverviewTab"),
    ("commissions", "CommissionsTab"),
    ("orders", "OrdersTab"),
    ("users", "UsersTab"),
    ("agents", "AgentsTab"),
    ("withdrawals", "WithdrawalsTab"),
    ("queue", "QueueTab"),
    ("proxy", "ProxyTab"),
    ("security", "SecurityTab"),
    ("risk", "RiskTab"),
    ("pricing", "PricingTab"),
    ("ypay", "YpayTab"),
    ("ads", "AdsTab"),
]

for tab_key, component_name in tab_replacements:
    # Find the start of the block
    if tab_key in ("proxy", "security", "risk", "pricing", "ypay", "ads"):
        pattern = rf'(\s*)<div v-if="activeTab === \'{tab_key}\'" class="{tab_key}-tab">'
    else:
        pattern = rf'(\s*)<div v-if="activeTab === \'{tab_key}\'">'

    match = re.search(pattern, content)
    if not match:
        print(f"  WARNING: Could not find {tab_key} tab block")
        continue

    start_pos = match.start()
    indent = match.group(1)

    # Find the end by counting div nesting
    search_from = match.end()
    nesting = 1
    pos = search_from

    while nesting > 0 and pos < len(content):
        next_open = content.find('<div', pos)
        next_close = content.find('</div>', pos)

        if next_close == -1:
            break

        if next_open != -1 and next_open < next_close:
            tag_end = content.find('>', next_open)
            if tag_end > 0 and content[tag_end - 1] == '/':
                pos = tag_end + 1
                continue
            nesting += 1
            pos = next_open + 4
        else:
            nesting -= 1
            if nesting == 0:
                end_pos = next_close + len('</div>')
                break
            pos = next_close + 6

    if nesting != 0:
        print(f"  WARNING: Could not find end of {tab_key} tab block")
        continue

    old_block = content[start_pos:end_pos]
    new_tag = f'{indent}<{component_name} v-if="activeTab === \'{tab_key}\'" />\n'
    content = content[:start_pos] + new_tag + content[end_pos:]
    print(f"  Replaced {tab_key} ({len(old_block)} chars)")

with open(ADMIN_VUE, "w", encoding="utf-8") as f:
    f.write(content)

lines = content.splitlines()
print(f"\nFinal: {len(lines)} lines")
print("Done!")

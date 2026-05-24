"""Fix s. prefix in generated tab components.

For each component, read the template from the raw file, apply s. prefix to all
known identifiers, then write back the component.
"""
import os
import re

ADMIN_DIR = r"C:\Users\win\Desktop\刷课平台js逆向\Anti-Course Cheating Plugin\frontend\src\views\admin"

# All identifiers that need s. prefix
IDS = {
    # Data
    "dash", "dashError", "loadingDash", "currentRole", "isLoggedIn",
    "orders", "ordersTotal", "ordersStatusFilter", "loadingOrders",
    "users", "usersTotal", "loadingUsers", "usersSubTab",
    "unifiedUsers", "unifiedTotal", "unifiedStats", "unifiedRoleFilter",
    "unifiedAgentFilter", "unifiedSearch", "loadingUnified",
    "showTopupModal", "topupTarget", "topupAmount", "topupNote", "toppupMode", "toppingUp",
    "subAdmins", "loadingSubAdmins", "showCreateSubAdmin", "newSubAdmin",
    "agents", "agentTotal", "agentStatusFilter", "agentStats", "loadingAgents",
    "partnerAgentStats", "agentSubTab", "showTierModal", "tierForm", "agentTiers",
    "commissions", "commissionTotal", "loadingCommissions",
    "showRateModal", "rateTarget", "newRate",
    "withdrawals", "withdrawalsTotal", "withdrawalStatusFilter", "loadingWithdrawals", "showQrModal",
    "queueJobs", "queueStats", "loadingQueue",
    "proxyForm", "proxySaving", "proxyTesting", "proxyTestResult", "proxyTestOk", "serverPublicIp",
    "secConfig", "secSaving", "pwForm", "changingPw", "loginLogs", "loadingLoginLogs",
    "riskConfig", "riskSaving", "riskStats", "blacklist", "loadingBlacklist",
    "showAddBlackModal", "newBlackItem", "riskLogs", "loadingRiskLogs",
    "pricing", "pricingSaving", "showAddPriceModal", "editingPrice", "priceForm",
    "ypaySettings", "ypayAccounts", "ypayOrders", "ypayTmpPrices", "ypaySaving",
    "showYpayModal", "editingYpayAccount", "ypayForm", "showYpayOrderModal", "ypayOrderForm",
    "showPairModal", "pairCode", "pairStatus", "pairPolling", "ypayEditingTmpPriceId",
    "adsList", "loadingAds", "showAdModal", "editingAd", "adForm", "savingAd", "adFileUploading",
    "sidebarCollapsed", "mobileSidebarOpen", "activeTab",
    "statusClass", "statusLabel", "orderStatusLabel", "orderStatusClass",
    "taskTypeNames", "tierNames", "platformColors",
    "maxBarRevenue", "maxBarOrders", "maxStatusCount", "maxPartnerStatusCount",
    "totalPlatformOrders",
    # Handlers
    "loadDashboard", "loadOrders", "clearOrderHistory",
    "acceptOrder", "executeOrder", "enqueueOrder", "completeOrder", "failOrder",
    "loadUnifiedUsers", "loadSubAdmins", "createSubAdmin", "deleteSubAdmin",
    "openTopup", "doTopup", "approveAgent", "suspendAgent", "reactivateAgent",
    "openRateModal", "loadAgents", "saveTier", "deleteTier", "loadAgentTiers", "openCreateTier",
    "loadCommissions", "clearCommissionHistory",
    "loadWithdrawals", "approveWithdrawal", "rejectWithdrawal", "showQr", "clearWithdrawalHistory",
    "loadQueue", "cancelQueueJob", "retryQueueJob", "clearQueueHistory",
    "testProxy", "saveProxy",
    "saveSecConfig", "changePw", "loadLoginLogs",
    "saveRiskConfig", "loadBlacklist", "addBlackItem", "removeBlackItem",
    "loadRiskLogs", "clearRiskLogs",
    "savePricing", "addPriceRule", "editPriceRule", "deletePriceRule", "savePriceRule",
    "saveYpaySettings", "loadYpayAccounts", "addYpayAccount", "editYpayAccount",
    "deleteYpayAccount", "saveYpayAccount", "loadYpayOrders", "createYpayOrder",
    "deleteYpayOrder", "loadYpayTmpPrices", "addYpayTmpPrice", "deleteYpayTmpPrice",
    "startPairing", "stopPairing",
    "openCreateAd", "openEditAd", "saveAd", "toggleAdActive", "deleteAd",
    "triggerAdFileUpload", "triggerAdImgUpload", "onAdFileChange", "onAdImgChange",
    "switchTab",
    "fmtMoney", "fmtDate", "fmtShortDate", "getPlatformName",
}

# Sort by length descending to match longer names first
IDS_SORTED = sorted(IDS, key=len, reverse=True)

# Build regex that matches these as whole words
_pattern = re.compile(r'(?<![.\w])(' + '|'.join(re.escape(i) for i in IDS_SORTED) + r')(?!\w)')


def process_template(template: str) -> str:
    """Add s. prefix to all known identifiers in template."""
    # Split template into segments: Vue expressions {{ }}, v-bind :attr, @event, and plain HTML
    # We only want to modify Vue expressions and directive values, not plain HTML attributes

    result = []
    i = 0
    while i < len(template):
        # Check for {{ expression }}
        if template[i:i+2] == '{{':
            end = template.find('}}', i)
            if end == -1:
                result.append(template[i:])
                break
            expr = template[i+2:end]
            expr = _pattern.sub(r's.\1', expr)
            result.append('{{' + expr + '}}')
            i = end + 2
        # Check for ="..."  (Vue directive value)
        elif template[i] == '"' and i > 0 and template[i-1] == '=':
            # Find the matching closing quote
            # But be careful about nested quotes
            j = i + 1
            depth = 0
            while j < len(template):
                if template[j] == '"' and depth == 0:
                    break
                elif template[j] == "'":
                    # Skip single-quoted string inside
                    k = template.find("'", j + 1)
                    if k == -1:
                        j = len(template)
                    else:
                        j = k + 1
                    continue
                j += 1
            if j < len(template):
                attr_val = template[i+1:j]
                # Only process if it looks like a Vue expression (not just a plain string)
                if any(c in attr_val for c in '=(){}[]!&|?:'):
                    attr_val = _pattern.sub(r's.\1', attr_val)
                result.append('"' + attr_val + '"')
                i = j + 1
            else:
                result.append(template[i])
                i += 1
        else:
            result.append(template[i])
            i += 1

    return ''.join(result)


TABS = [
    "overview", "commissions", "orders", "users", "agents",
    "withdrawals", "queue", "proxy", "security", "risk",
    "pricing", "ypay", "ads",
]


def build_component(tab_key: str):
    name = tab_key[0].upper() + tab_key[1:] + "Tab"
    raw_file = os.path.join(ADMIN_DIR, f"{name}_raw.txt")

    with open(raw_file, encoding="utf-8") as f:
        template = f.read()

    # Strip v-if wrapper
    lines = template.split("\n")
    if lines and "v-if=\"activeTab ===" in lines[0]:
        lines[0] = re.sub(r'\s*v-if="activeTab === \'[^\']+\'"', '', lines[0])
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() == "</div>":
                lines.pop(i)
                break
    template = "\n".join(lines)

    # Apply s. prefix
    template = process_template(template)

    script = """<script setup lang="ts">
import { useAdminState } from './adminState'

const s = useAdminState()
</script>"""

    component = script + "\n\n" + template

    out_file = os.path.join(ADMIN_DIR, f"{name}.vue")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(component)
    print(f"  {name}.vue")


print("Generating tab components with s. prefix...")
for tab in TABS:
    build_component(tab)
print("Done!")

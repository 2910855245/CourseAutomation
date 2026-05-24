"""Generate Vue tab components from extracted raw template blocks."""
import re, os

ADMIN_DIR = r"C:\Users\win\Desktop\刷课平台js逆向\Anti-Course Cheating Plugin\frontend\src\views\admin"

# Tab definitions: (tab_key, component_name, extra_classes_on_div)
TABS = [
    "overview", "commissions", "orders", "users", "agents",
    "withdrawals", "queue", "proxy", "security", "risk",
    "pricing", "ypay", "ads"
]

# Known function/variable mappings per tab (from reading the script section)
# Format: tab_name -> { 'props': [...], 'emits': [...], 'funcs': [...] }
TAB_DEPS = {
    "overview": {
        "props": ["dash", "currentRole", "loadingDash", "dashError",
                  "maxBarRevenue", "maxBarOrders", "maxStatusCount",
                  "maxPartnerStatusCount", "totalPlatformOrders",
                  "platformColors", "tierNames", "orderStatusLabel",
                  "orderStatusClass", "taskTypeNames"],
        "funcs": ["fmtMoney", "fmtShortDate", "getPlatformName", "loadDashboard"],
    },
    "commissions": {
        "props": ["commissions", "commissionTotal", "loadingCommissions"],
        "funcs": ["fmtMoney", "fmtDate", "loadCommissions", "clearCommissionHistory"],
    },
    "orders": {
        "props": ["orders", "ordersTotal", "ordersStatusFilter", "loadingOrders", "currentRole",
                  "orderStatusLabel", "orderStatusClass", "taskTypeNames"],
        "funcs": ["fmtMoney", "fmtDate", "getPlatformName", "loadOrders", "clearOrderHistory",
                  "acceptOrder", "executeOrder", "enqueueOrder", "completeOrder", "failOrder"],
    },
    "users": {
        "props": ["currentRole", "usersSubTab", "unifiedUsers", "unifiedStats",
                  "unifiedRoleFilter", "unifiedAgentFilter", "unifiedSearch", "loadingUnified",
                  "subAdmins", "loadingSubAdmins", "showCreateSubAdmin", "newSubAdmin",
                  "statusClass", "statusLabel", "showTopupModal", "topupTarget",
                  "topupAmount", "topupNote", "toppupMode", "toppingUp"],
        "funcs": ["fmtMoney", "fmtDate", "loadUnifiedUsers", "loadSubAdmins",
                  "createSubAdmin", "deleteSubAdmin", "openTopup", "doTopup",
                  "approveAgent", "suspendAgent", "reactivateAgent", "openRateModal"],
    },
    "agents": {
        "props": ["agents", "agentTotal", "agentStatusFilter", "agentStats",
                  "loadingAgents", "currentRole", "partnerAgentStats",
                  "agentSubTab", "showTierModal", "tierForm", "agentTiers",
                  "statusClass", "statusLabel"],
        "funcs": ["fmtMoney", "fmtDate", "loadAgents", "approveAgent", "suspendAgent",
                  "reactivateAgent", "openRateModal", "saveTier", "deleteTier",
                  "loadAgentTiers", "openCreateTier"],
    },
    "withdrawals": {
        "props": ["withdrawals", "withdrawalsTotal", "withdrawalStatusFilter",
                  "loadingWithdrawals", "showQrModal"],
        "funcs": ["fmtMoney", "fmtDate", "loadWithdrawals", "approveWithdrawal",
                  "rejectWithdrawal", "showQr"],
    },
    "queue": {
        "props": ["queueJobs", "queueStats", "loadingQueue", "currentRole"],
        "funcs": ["fmtDate", "loadQueue", "cancelQueueJob", "retryQueueJob", "clearQueueHistory"],
    },
    "proxy": {
        "props": ["proxyConfig", "proxyTesting", "proxyTestResult", "proxySaving"],
        "funcs": ["testProxy", "saveProxy", "clearProxy"],
    },
    "security": {
        "props": ["secConfig", "secSaving", "pwForm", "changingPw", "currentRole",
                  "loginLogs", "loadingLoginLogs"],
        "funcs": ["saveSecConfig", "changePw", "loadLoginLogs"],
    },
    "risk": {
        "props": ["riskConfig", "riskSaving", "riskStats", "blacklist",
                  "loadingBlacklist", "showAddBlackModal", "newBlackItem",
                  "riskLogs", "loadingRiskLogs"],
        "funcs": ["saveRiskConfig", "loadBlacklist", "addBlackItem", "removeBlackItem",
                  "loadRiskLogs", "clearRiskLogs"],
    },
    "pricing": {
        "props": ["pricing", "pricingSaving", "showAddPriceModal", "editingPrice",
                  "priceForm", "currentRole"],
        "funcs": ["savePricing", "addPriceRule", "editPriceRule", "deletePriceRule",
                  "savePriceRule"],
    },
    "ypay": {
        "props": ["ypaySettings", "ypayAccounts", "ypayOrders", "ypayTmpPrices",
                  "ypaySaving", "showYpayModal", "editingYpayAccount", "ypayForm",
                  "showYpayOrderModal", "ypayOrderForm", "currentRole",
                  "showPairModal", "pairCode", "pairStatus", "pairPolling"],
        "funcs": ["saveYpaySettings", "loadYpayAccounts", "addYpayAccount",
                  "editYpayAccount", "deleteYpayAccount", "saveYpayAccount",
                  "loadYpayOrders", "createYpayOrder", "deleteYpayOrder",
                  "loadYpayTmpPrices", "addYpayTmpPrice", "deleteYpayTmpPrice",
                  "startPairing", "stopPairing"],
    },
    "ads": {
        "props": ["adsList", "loadingAds", "showAdModal", "editingAd",
                  "adForm", "savingAd", "adFileUploading"],
        "funcs": ["openCreateAd", "openEditAd", "saveAd", "toggleAdActive",
                  "deleteAd", "triggerAdFileUpload", "triggerAdImgUpload",
                  "onAdFileChange", "onAdImgChange"],
    },
}

def make_component(tab_key):
    name = tab_key[0].upper() + tab_key[1:] + "Tab"
    raw_file = os.path.join(ADMIN_DIR, f"{name}_raw.txt")

    with open(raw_file, "r", encoding="utf-8") as f:
        template_block = f.read()

    deps = TAB_DEPS.get(tab_key, {"props": [], "funcs": []})

    # Build props interface
    props_fields = []
    for p in deps["props"]:
        # Guess type from name
        if p.startswith("loading") or p.startswith("show") or p.startswith("changing") or p.startswith("saving") or p.startswith("topping") or p.startswith("curing"):
            props_fields.append(f"  {p}: boolean")
        elif p.endswith("List") or p.endswith("s") or p.endswith("Logs") or p.endswith("Jobs") or p.endswith("Tiers") or p.endswith("Accounts") or p.endswith("Orders") or p.endswith("Prices") or p.endswith("Blacklist"):
            props_fields.append(f"  {p}: any[]")
        elif p.endswith("Total") or p.endswith("Count") or p.endswith("Rate"):
            props_fields.append(f"  {p}: number")
        elif p.endswith("Form") or p.endswith("Config") or p.endswith("Form"):
            props_fields.append(f"  {p}: any")
        else:
            props_fields.append(f"  {p}: any")

    props_ts = "\n".join(props_fields)

    # Build emits
    emit_entries = []
    # For filter changes, emit update events
    for p in deps["props"]:
        if p.endswith("Filter") or p.endswith("SubTab") or p.endswith("Tab"):
            emit_entries.append(f"  'update:{p}': [val: any]")
        elif p.startswith("show"):
            emit_entries.append(f"  'update:{p}': [val: boolean]")

    # For functions, emit events
    for fn in deps["funcs"]:
        # Some functions take arguments
        if fn in ("acceptOrder", "executeOrder", "enqueueOrder", "completeOrder", "failOrder",
                  "approveAgent", "suspendAgent", "reactivateAgent", "deleteSubAdmin",
                  "approveWithdrawal", "rejectWithdrawal", "showQr",
                  "cancelQueueJob", "retryQueueJob",
                  "openTopup", "openRateModal", "openEditAd", "toggleAdActive", "deleteAd",
                  "editPriceRule", "deletePriceRule", "editYpayAccount", "deleteYpayAccount",
                  "deleteYpayOrder", "deleteYpayTmpPrice", "addBlackItem", "removeBlackItem"):
            emit_entries.append(f"  {fn}: [...args: any[]]")
        elif fn.startswith("load") or fn.startswith("clear") or fn.startswith("save") or fn.startswith("test"):
            emit_entries.append(f"  {fn}: []")
        elif fn.startswith("on") or fn.startswith("trigger"):
            emit_entries.append(f"  {fn}: [e?: any]")
        elif fn.startswith("open"):
            emit_entries.append(f"  {fn}: [...args: any[]]")
        else:
            emit_entries.append(f"  {fn}: [...args: any[]]")

    emits_ts = "\n".join(emit_entries)

    # Build template replacements: replace function calls with emit()
    # We need to replace things like:
    #   @click="loadOrders()" -> @click="emit('loadOrders')"
    #   @click="acceptOrder(o.order_id)" -> @click="emit('acceptOrder', o.order_id)"
    #   :disabled="loadingOrders" -> :disabled="loadingOrders"  (props, keep as is)

    # For the template, we keep all prop references as-is since they come from props
    # We replace function calls in event handlers

    # Generate the component
    component = f"""<script setup lang="ts">
defineProps<{{
{props_ts}
}>()

const emit = defineEmits<{{
{emits_ts}
}>()
</script>

{template_block}
"""

    out_file = os.path.join(ADMIN_DIR, f"{name}.vue")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(component)
    print(f"Created: {name}.vue ({len(template_block.splitlines())} template lines)")

for tab in TABS:
    make_component(tab)

print("\nDone! Now you need to manually adjust the emit calls in each component.")

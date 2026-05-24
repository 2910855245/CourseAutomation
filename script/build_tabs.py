"""Build Vue tab components with proper emit() calls."""
import os
import re

ADMIN_DIR = r"C:\Users\win\Desktop\刷课平台js逆向\Anti-Course Cheating Plugin\frontend\src\views\admin"

# All functions that are called in templates (extracted from script section analysis)
# These need to be replaced: funcName(args) -> emit('funcName', args)
TAB_FUNCS = {
    "overview": ["loadDashboard", "fmtMoney", "fmtShortDate", "getPlatformName"],
    "commissions": ["loadCommissions", "clearCommissionHistory", "fmtMoney", "fmtDate"],
    "orders": ["loadOrders", "clearOrderHistory", "fmtMoney", "fmtDate", "getPlatformName",
               "acceptOrder", "executeOrder", "enqueueOrder", "completeOrder", "failOrder"],
    "users": ["loadUnifiedUsers", "loadSubAdmins", "createSubAdmin", "deleteSubAdmin",
              "openTopup", "doTopup", "approveAgent", "suspendAgent", "reactivateAgent",
              "openRateModal", "fmtMoney", "fmtDate"],
    "agents": ["loadAgents", "approveAgent", "suspendAgent", "reactivateAgent",
               "openRateModal", "saveTier", "deleteTier", "loadAgentTiers", "openCreateTier",
               "fmtMoney", "fmtDate"],
    "withdrawals": ["loadWithdrawals", "approveWithdrawal", "rejectWithdrawal", "showQr",
                     "fmtMoney", "fmtDate"],
    "queue": ["loadQueue", "cancelQueueJob", "retryQueueJob", "clearQueueHistory", "fmtDate"],
    "proxy": ["testProxy", "saveProxy", "clearProxy"],
    "security": ["saveSecConfig", "changePw", "loadLoginLogs", "fmtDate"],
    "risk": ["saveRiskConfig", "loadBlacklist", "addBlackItem", "removeBlackItem",
             "loadRiskLogs", "clearRiskLogs", "fmtDate"],
    "pricing": ["savePricing", "addPriceRule", "editPriceRule", "deletePriceRule", "savePriceRule",
                "fmtMoney"],
    "ypay": ["saveYpaySettings", "loadYpayAccounts", "addYpayAccount", "editYpayAccount",
             "deleteYpayAccount", "saveYpayAccount", "loadYpayOrders", "createYpayOrder",
             "deleteYpayOrder", "loadYpayTmpPrices", "addYpayTmpPrice", "deleteYpayTmpPrice",
             "startPairing", "stopPairing", "fmtMoney", "fmtDate"],
    "ads": ["openCreateAd", "openEditAd", "saveAd", "toggleAdActive", "deleteAd",
            "triggerAdFileUpload", "triggerAdImgUpload", "onAdFileChange", "onAdImgChange"],
}

def replace_func_calls(template: str, funcs: list[str]) -> str:
    """Replace function calls in template with emit() calls.

    Patterns:
      @click="funcName"           -> @click="emit('funcName')"
      @click="funcName()"         -> @click="emit('funcName')"
      @click="funcName(a, b)"     -> @click="emit('funcName', a, b)"
      @change="funcName($event)"  -> @change="emit('funcName', $event)"
      :disabled="funcName"        -> keep (not an event handler, shouldn't happen)
    """
    for func in funcs:
        # Pattern 1: @event="funcName(args)" or @event="funcName"
        # Match @something="funcName(...)" or @something="funcName"
        def replace_handler(m):
            prefix = m.group(1)  # @event="
            fname = m.group(2)
            rest = m.group(3)    # everything after function name until closing quote
            if rest and rest.strip():
                # Has arguments: funcName(a, b) -> emit('funcName', a, b)
                # Remove outer parens
                args = rest.strip()
                if args.startswith('(') and args.endswith(')'):
                    args = args[1:-1].strip()
                if args:
                    return f"{prefix}emit('{fname}', {args})"
                else:
                    return f"{prefix}emit('{fname}')"
            else:
                # No args: funcName or funcName() -> emit('funcName')
                return f"{prefix}emit('{fname}')"

        # This regex matches: (@event=")funcName( optional_args )?(")
        # We need to be careful not to match inside :attr="..." that aren't events
        pattern = r'(@\w+=")' + re.escape(func) + r'(\([^)]*\)|\s*)(?=")'
        template = re.sub(pattern, replace_handler, template)

        # Also handle @click.prevent="funcName(...)"
        pattern2 = r'(@\w+(?:\.\w+)*=")' + re.escape(func) + r'(\([^)]*\)|\s*)(?=")'
        template = re.sub(pattern2, replace_handler, template)

    return template


def build_component(tab_key: str):
    name = tab_key[0].upper() + tab_key[1:] + "Tab"
    raw_file = os.path.join(ADMIN_DIR, f"{name}_raw.txt")

    with open(raw_file, encoding="utf-8") as f:
        template = f.read()

    funcs = TAB_FUNCS.get(tab_key, [])
    template = replace_func_calls(template, funcs)

    # Add emit import to script
    script = """<script setup lang="ts">
const emit = defineEmits<{
"""
    # Add emit type declarations
    for func in funcs:
        script += f"  {func}: [...args: any[]]\n"
    script += "}>()\n</script>\n"

    component = script + "\n" + template

    out_file = os.path.join(ADMIN_DIR, f"{name}.vue")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(component)
    print(f"Created: {name}.vue")


for tab in TAB_FUNCS:
    build_component(tab)

print("\nDone! Components created. Now update Admin.vue to import and use them.")

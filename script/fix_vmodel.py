"""Fix v-model and prop assignments in generated tab components."""
import os
import re

ADMIN_DIR = r"C:\Users\win\Desktop\刷课平台js逆向\Anti-Course Cheating Plugin\frontend\src\views\admin"

# Map of component -> props that need v-model -> emit conversion
VMOODEL_PROPS = {
    "OrdersTab": ["ordersStatusFilter"],
    "UsersTab": ["usersSubTab", "unifiedRoleFilter", "unifiedAgentFilter", "unifiedSearch",
                 "showCreateSubAdmin", "showTopupModal", "topupTarget", "topupAmount",
                 "topupNote", "toppupMode"],
    "AgentsTab": ["agentStatusFilter", "agentSubTab"],
    "WithdrawalsTab": ["withdrawalStatusFilter"],
    "AdsTab": ["showAdModal"],
    "PricingTab": ["showAddPriceModal"],
    "YpayTab": ["showYpayModal", "showYpayOrderModal", "showPairModal"],
}

# Also handle v-model="prop.field" patterns (these are OK since object mutation is fine)
# But v-model="primitiveProp" needs conversion

def fix_file(name: str, vmodel_props: list):
    filepath = os.path.join(ADMIN_DIR, f"{name}.vue")
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    changed = False
    for prop in vmodel_props:
        # Pattern 1: @click="propName = 'value'" -> @click="emit('update:propName', 'value')"
        # This is tricky because it's inside an event handler with possible other statements

        # Pattern 2: v-model="propName" -> :modelValue="propName" @update:modelValue="emit('update:propName', $event)"
        old_vmodel = f'v-model="{prop}"'
        new_vmodel = f':modelValue="{prop}" @update:modelValue="emit(\'update:{prop}\', $event)"'
        if old_vmodel in content:
            content = content.replace(old_vmodel, new_vmodel)
            changed = True

        # Pattern 3: In @click handlers, replace "propName = 'value'" with "emit('update:propName', 'value')"
        # Match patterns like: @click="propName = 'someValue'; funcCall()"
        # or: @click="propName = ''"
        # or: @click="propName = value"

        # Simple assignment in handler: @click="prop = 'value'"
        content = re.sub(
            rf'(@\w+(?:\.\w+)*=")({re.escape(prop)}) = (\'[^\']*\')(;?\s*")',
            rf"\1emit('update:{prop}', \3)\4",
            content
        )

        # Assignment with other value types: @click="prop = value"
        content = re.sub(
            rf'(@\w+(?:\.\w+)*=")({re.escape(prop)}) = ([^;"]+)(;?\s*")',
            rf"\1emit('update:{prop}', \3)\4",
            content
        )

        # v-if="prop === 'value'" patterns should stay as-is (reading is fine)

    if changed:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  Fixed: {name}.vue")
    else:
        print(f"  No changes: {name}.vue")


print("Fixing v-model assignments...")
for name, props in VMOODEL_PROPS.items():
    fix_file(name, props)
print("Done!")

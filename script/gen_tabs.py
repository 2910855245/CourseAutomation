"""Generate Vue tab components using useAdminState() with destructuring.

Extracts ALL variable/function names from Admin.vue and destructures them
in every tab component. Vue 3 auto-unwraps refs in templates.
"""
import os
import re

ADMIN_DIR = r"C:\Users\win\Desktop\刷课平台js逆向\Anti-Course Cheating Plugin\frontend\src\views\admin"
ADMIN_VUE = r"C:\Users\win\Desktop\刷课平台js逆向\Anti-Course Cheating Plugin\frontend\src\views\Admin.vue"

TABS = [
    "overview", "commissions", "orders", "users", "agents",
    "withdrawals", "queue", "proxy", "security", "risk",
    "pricing", "ypay", "ads",
]

# Extract ALL variable/function names from Admin.vue
with open(ADMIN_VUE, encoding="utf-8") as f:
    admin_content = f.read()

ref_names = set(re.findall(r'const\s+(\w+)\s*(?::\s*[^=]+)?\s*=', admin_content))
let_names = set(re.findall(r'^\s*let\s+(\w+)\s*(?::\s*[^=]+)?\s*=', admin_content, re.MULTILINE))
func_names = set(re.findall(r'(?:async\s+)?function\s+(\w+)', admin_content))
# Also extract destructured names: const { a, b: c } = ...
destructured = set()
for m in re.finditer(r'const\s*\{([^}]+)\}\s*=', admin_content):
    for part in m.group(1).split(','):
        part = part.strip()
        if ':' in part:
            destructured.add(part.split(':')[1].strip())  # alias
        elif part:
            destructured.add(part)
ALL_IDS = ref_names | let_names | func_names | destructured

# Remove non-template identifiers
EXCLUDE = {'store', 'showConfirm', 'loadCaptcha', 'doLogin', 'logout',
           'fetchServerPublicIp', 'autoPollTimer'}
ALL_IDS -= EXCLUDE

ALL_VARS = sorted(ALL_IDS)
DESTRUCTURE = ", ".join(ALL_VARS)
print(f"Found {len(ALL_VARS)} state identifiers")


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

    script = f"""<script setup lang="ts">
// @ts-nocheck
import {{ useAdminState }} from './adminState'

const {{ {DESTRUCTURE} }} = useAdminState()
</script>"""

    component = script + "\n\n<template>\n" + template + "\n</div>\n</template>"

    out_file = os.path.join(ADMIN_DIR, f"{name}.vue")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(component)
    print(f"  {name}.vue")


print("Generating tab components...")
for tab in TABS:
    build_component(tab)
print("Done!")

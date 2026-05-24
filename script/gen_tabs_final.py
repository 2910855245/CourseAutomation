"""Generate Vue tab components with s. prefix for all state references.

This script reads the raw template blocks, adds s. prefix to ALL camelCase
identifiers that could be state variables or functions from Admin.vue,
then writes the component files.
"""
import os
import re

ADMIN_DIR = r"C:\Users\win\Desktop\刷课平台js逆向\Anti-Course Cheating Plugin\frontend\src\views\admin"
ADMIN_VUE = r"C:\Users\win\Desktop\刷课平台js逆向\Anti-Course Cheating Plugin\frontend\src\views\Admin.vue"

# Read Admin.vue to extract all variable/function names
with open(ADMIN_VUE, encoding="utf-8") as f:
    admin_content = f.read()

# Extract all const xxx = ref/reactive/computed and function names
ref_names = set(re.findall(r'const\s+(\w+)\s*=\s*(?:ref|reactive|computed)', admin_content))
func_names = set(re.findall(r'(?:async\s+)?function\s+(\w+)', admin_content))

# Combine and filter out common non-state identifiers
ALL_IDS = ref_names | func_names

# Remove identifiers that are clearly not template-accessible state
EXCLUDE = {
    'store', 'showConfirm', 'loadCaptcha', 'doLogin', 'logout',
    'fetchServerPublicIp', 'detectServerSpecs',
}

ALL_IDS -= EXCLUDE

# Sort by length descending for matching priority
ALL_IDS_SORTED = sorted(ALL_IDS, key=len, reverse=True)

# Build regex pattern
_id_pattern = re.compile(r'(?<![.\w"/\'])(\b(?:' + '|'.join(re.escape(i) for i in ALL_IDS_SORTED) + r')\b)')


def prefix_template(template: str) -> str:
    """Add s. prefix to state identifiers in Vue template expressions."""
    result = []
    i = 0
    length = len(template)

    while i < length:
        # Skip HTML comments
        if template[i:i+4] == '<!--':
            end = template.find('-->', i)
            if end == -1:
                result.append(template[i:])
                break
            result.append(template[i:end+3])
            i = end + 3
            continue

        # Handle {{ expression }}
        if template[i:i+2] == '{{':
            end = template.find('}}', i + 2)
            if end == -1:
                result.append(template[i:])
                break
            expr = template[i+2:end]
            expr = _id_pattern.sub(r's.\1', expr)
            result.append('{{' + expr + '}}')
            i = end + 2
            continue

        # Handle Vue directives: ="...", @click="...", :attr="...", v-if="..."
        # We need to process the value inside quotes
        if template[i] == '=' and i + 1 < length and template[i+1] == '"':
            result.append('="')
            i += 2
            # Find matching closing quote (handle nested quotes)
            depth = 0
            val_start = i
            while i < length:
                if template[i] == '"' and depth == 0:
                    break
                elif template[i] == "'":
                    # Skip single-quoted string
                    j = template.find("'", i + 1)
                    if j == -1:
                        i = length
                    else:
                        i = j + 1
                    continue
                i += 1
            if i < length:
                attr_val = template[val_start:i]
                attr_val = _id_pattern.sub(r's.\1', attr_val)
                result.append(attr_val)
                result.append('"')
                i += 1
            continue

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
    template = prefix_template(template)

    script = """<script setup lang="ts">
import { useAdminState } from './adminState'

const s = useAdminState()
</script>"""

    component = script + "\n\n" + template

    out_file = os.path.join(ADMIN_DIR, f"{name}.vue")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(component)
    print(f"  {name}.vue")


print(f"Found {len(ALL_IDS)} state identifiers")
print("Generating tab components with s. prefix...")
for tab in TABS:
    build_component(tab)
print("Done!")

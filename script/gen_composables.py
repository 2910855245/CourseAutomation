"""Extract composables from Admin.vue script section.

Reads Admin.vue, groups refs/functions by domain, and generates
composable files that return their state + functions.
"""
import os
import re

ADMIN_VUE = r"C:\Users\win\Desktop\刷课平台js逆向\Anti-Course Cheating Plugin\frontend\src\views\Admin.vue"
COMPOSABLES_DIR = r"C:\Users\win\Desktop\刷课平台js逆向\Anti-Course Cheating Plugin\frontend\src\composables"

with open(ADMIN_VUE, encoding="utf-8") as f:
    content = f.read()

# Extract script section
script_match = re.search(r'<script setup lang="ts">\s*\n(.*?)\n</script>', content, re.DOTALL)
if not script_match:
    print("ERROR: Could not find script section")
    exit(1)
script = script_match.group(1)

# ── Define composable groups ──
# Each group: (name, description, ref_names, function_names, computed_names)
# We'll extract by line ranges for precision

COMPOSABLES = {
    "useAuth": {
        "desc": "登录/登出/验证码/密码修改",
        "imports": [
            "import { ref, reactive } from 'vue'",
            "import { useAppStore } from '@/stores/app'",
            "import { api } from '@/api'",
        ],
        "lines": (26, 47),  # ref declarations
        "extra_lines": [(257, 291), (331, 342)],  # doLogin, logout, changeAdminPassword
        "extra_refs": [],  # refs defined elsewhere but needed
        "init_lines": [(49, 50)],  # activeTab ref needed for logout
    },
    "useDashboard": {
        "desc": "概览数据/侧边栏/格式化",
        "imports": [
            "import { ref, computed } from 'vue'",
            "import { useAppStore } from '@/stores/app'",
            "import { api, type DashboardStats } from '@/api'",
        ],
        "lines": (87, 92),  # dash, dashError, loadingDash, sidebarCollapsed, mobileSidebarOpen
        "extra_lines": [(293, 329), (1147, 1171), (1213, 1226)],
        "extra_refs": [],
    },
    "useOrders": {
        "desc": "订单管理",
        "imports": [
            "import { ref } from 'vue'",
            "import { useAppStore } from '@/stores/app'",
            "import { api, type OrderItem } from '@/api'",
            "import { useConfirmSingleton } from '@/composables/useConfirm'",
        ],
        "lines": (93, 97),
        "extra_lines": [(597, 644), (792, 795)],
        "extra_refs": [],
    },
    "useUsers": {
        "desc": "用户/代理/佣金/合伙人管理",
        "imports": [
            "import { ref, reactive, computed } from 'vue'",
            "import { useAppStore } from '@/stores/app'",
            "import { api, type AgentProfile, type CommissionItem } from '@/api'",
            "import { useConfirmSingleton } from '@/composables/useConfirm'",
        ],
        "lines": (50, 136),  # usersSubTab through agentFees
        "extra_lines": [
            (420, 595),  # loadAgentStats through saveAgentFees
            (646, 690),  # loadUsers through doTopup
            (797, 800),  # clearCommissionHistory
        ],
        "extra_refs": [],
    },
    "usePayments": {
        "desc": "支付/提现/YPay/代理/安全/风险/定价/广告/队列",
        "imports": [
            "import { ref, reactive, computed } from 'vue'",
            "import { useAppStore } from '@/stores/app'",
            "import { api } from '@/api'",
            "import { useConfirmSingleton } from '@/composables/useConfirm'",
        ],
        "lines": (108, 113),  # withdrawals
        "extra_lines": [
            (137, 216),  # deepseek, queue, pricing, ads, risk, health refs
            (344, 418),  # deepseek functions
            (692, 790),  # withdrawals, queue functions
            (802, 1145),  # risk, health, domain functions
            (1228, 1354),  # pricing functions
            (1356, 2008),  # ypay, ads, proxy, pay test functions
        ],
        "extra_refs": [],
    },
}


def extract_lines(text: str, start: int, end: int) -> str:
    """Extract lines from script (1-indexed)."""
    lines = text.split('\n')
    return '\n'.join(lines[start-1:end])


# Extract all variable/function declarations to build the full list
# for initAdminState() call
all_ids = set()
for m in re.finditer(r'const\s+(\w+)\s*(?::\s*[^=]+)?\s*=', script):
    all_ids.add(m.group(1))
for m in re.finditer(r'^\s*let\s+(\w+)\s*(?::\s*[^=]+)?\s*=', script, re.MULTILINE):
    all_ids.add(m.group(1))
for m in re.finditer(r'(?:async\s+)?function\s+(\w+)', script):
    all_ids.add(m.group(1))
# Destructured
for m in re.finditer(r'const\s*\{([^}]+)\}\s*=', script):
    for part in m.group(1).split(','):
        part = part.strip()
        if ':' in part:
            all_ids.add(part.split(':')[1].strip())
        elif part:
            all_ids.add(part)

print(f"Total identifiers found: {len(all_ids)}")


def build_composable(name: str, config: dict) -> str:
    """Build a composable file content."""
    lines = []

    # Header
    lines.append(f"// {config['desc']}")
    lines.append("// Auto-generated from Admin.vue — do not edit manually")
    lines.append("")

    # Imports
    for imp in config["imports"]:
        lines.append(imp)
    lines.append("")

    lines.append(f"export function {name}() {{")
    lines.append("  const store = useAppStore()")
    lines.append("  const { showConfirm } = useConfirmSingleton()")
    lines.append("")

    # Extract ref declarations
    ref_block = extract_lines(script, *config["lines"])
    for line in ref_block.split('\n'):
        line = line.strip()
        if line:
            lines.append(f"  {line}")
    lines.append("")

    # Extract function bodies
    for start, end in config["extra_lines"]:
        func_block = extract_lines(script, start, end)
        for line in func_block.split('\n'):
            # Re-indent to 2 spaces
            stripped = line.lstrip()
            if stripped:
                lines.append(f"  {stripped}")
            else:
                lines.append("")
        lines.append("")

    # Build return statement - collect all refs and functions defined in this composable
    return_ids = set()
    full_text = '\n'.join(lines)
    for m in re.finditer(r'const\s+(\w+)\s*(?::\s*[^=]+)?\s*=', full_text):
        return_ids.add(m.group(1))
    for m in re.finditer(r'(?:async\s+)?function\s+(\w+)', full_text):
        return_ids.add(m.group(1))
    for m in re.finditer(r'let\s+(\w+)\s*(?::\s*[^=]+)?\s*=', full_text):
        return_ids.add(m.group(1))
    # Destructured
    for m in re.finditer(r'const\s*\{([^}]+)\}\s*=', full_text):
        for part in m.group(1).split(','):
            part = part.strip()
            if ':' in part:
                return_ids.add(part.split(':')[1].strip())
            elif part:
                return_ids.add(part)

    # Remove internal-only names
    return_ids -= {'store', 'showConfirm'}

    sorted_ids = sorted(return_ids)
    lines.append("  return {")
    for rid in sorted_ids:
        lines.append(f"    {rid},")
    lines.append("  }")
    lines.append("}")

    return '\n'.join(lines)


# Generate composable files
for name, config in COMPOSABLES.items():
    content_out = build_composable(name, config)
    out_path = os.path.join(COMPOSABLES_DIR, f"{name}.ts")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content_out)
    print(f"  Generated {name}.ts")

print("\nDone! Now update Admin.vue to import and use composables.")

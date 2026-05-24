"""Extract tab components from Admin.vue"""
import os
import re

ADMIN_VUE = r"C:\Users\win\Desktop\刷课平台js逆向\Anti-Course Cheating Plugin\frontend\src\views\Admin.vue"
OUT_DIR = r"C:\Users\win\Desktop\刷课平台js逆向\Anti-Course Cheating Plugin\frontend\src\views\admin"

with open(ADMIN_VUE, encoding="utf-8") as f:
    lines = f.readlines()

# Find template section start (0-indexed)
template_start = None
for i, line in enumerate(lines):
    if line.strip() == "<template>":
        template_start = i
        break

# Find each tab's v-if block in the template
tab_pattern = re.compile(r"v-if=\"activeTab === '(\w+)'\"")
tabs = []
for i, line in enumerate(lines):
    m = tab_pattern.search(line)
    if m and i > template_start and '<div' in line:
        tab_name = m.group(1)
        tabs.append((tab_name, i))

print(f"Found {len(tabs)} tabs:")
for name, line_no in tabs:
    print(f"  {name}: line {line_no + 1}")

# For each tab, extract the full block (match div nesting)
for idx, (tab_name, start_line) in enumerate(tabs):
    # Find the matching closing </div> by counting nesting
    nesting = 0
    end_line = start_line
    for j in range(start_line, len(lines)):
        line = lines[j]
        # Count opening <div tags (not self-closing)
        opens = len(re.findall(r'<div[\s>]', line))
        closes = len(re.findall(r'</div>', line))
        nesting += opens - closes
        if nesting == 0:
            end_line = j + 1  # inclusive end
            break

    # Extract lines from <div v-if="activeTab === 'xxx'"> to matching </div>
    block = lines[start_line:end_line]

    # Remove trailing blank lines
    while block and block[-1].strip() == "":
        block.pop()

    # Convert to PascalCase component name
    component_name = tab_name[0].upper() + tab_name[1:] + "Tab"

    print(f"\n=== {component_name} ({tab_name}) ===")
    print(f"  Lines: {start_line+1}-{end_line} ({len(block)} lines)")

    # Save the raw template block for inspection
    out_file = os.path.join(OUT_DIR, f"{component_name}_raw.txt")
    with open(out_file, "w", encoding="utf-8") as f:
        f.writelines(block)
    print(f"  Saved: {out_file}")

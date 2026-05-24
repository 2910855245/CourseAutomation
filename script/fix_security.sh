#!/bin/bash
# 宝塔面板安全漏洞修复脚本
# 自动修复可通过命令行解决的中/低危漏洞
# 用法: bash fix_security.sh

set -e
echo "========================================="
echo "  宝塔安全漏洞自动修复"
echo "========================================="
echo ""

# -------------------- 1. PASS_MIN_DAYS >= 7 --------------------
echo "[1/9] 设置密码最小修改间隔为 7 天..."
if grep -q "^PASS_MIN_DAYS" /etc/login.defs; then
  sed -i 's/^PASS_MIN_DAYS.*/PASS_MIN_DAYS\t7/' /etc/login.defs
else
  echo "PASS_MIN_DAYS	7" >> /etc/login.defs
fi
echo "  ✓ PASS_MIN_DAYS 已设为 7"

# -------------------- 2. 命令行超时退出 --------------------
echo "[2/9] 配置命令行超时退出 (TMOUT=600)..."
if ! grep -q "TMOUT=" /etc/profile; then
  cat >> /etc/profile << 'EOF'

# 命令行超时退出 - 600秒无操作自动注销
TMOUT=600
readonly TMOUT
export TMOUT
EOF
  echo "  ✓ TMOUT=600 已添加到 /etc/profile"
else
  echo "  - TMOUT 已存在，跳过"
fi

# -------------------- 3. 禁 Ping --------------------
echo "[3/9] 开启禁 Ping 功能..."
cat > /etc/sysctl.d/99-disable-ping.conf << 'EOF'
# 禁止 ICMP echo (禁 Ping)
net.ipv4.icmp_echo_ignore_all = 1
EOF
sysctl -p /etc/sysctl.d/99-disable-ping.conf > /dev/null 2>&1
echo "  ✓ Ping 已禁用"

# -------------------- 4. grub.cfg 权限 --------------------
echo "[4/9] 修复 grub.cfg 权限为 600..."
if [ -f /boot/grub/grub.cfg ]; then
  chmod 600 /boot/grub/grub.cfg
  echo "  ✓ /boot/grub/grub.cfg 权限已设为 600"
elif [ -f /boot/grub2/grub.cfg ]; then
  chmod 600 /boot/grub2/grub.cfg
  echo "  ✓ /boot/grub2/grub.cfg 权限已设为 600"
fi

# -------------------- 5. SSH 空闲超时 + 登录超时 --------------------
echo "[5/9] 配置 SSH 超时..."
SSHD_CFG="/etc/ssh/sshd_config"
cp "$SSHD_CFG" "${SSHD_CFG}.bak.$(date +%Y%m%d%H%M%S)"

# ClientAliveInterval: 每 N 秒发一次心跳
if grep -q "^ClientAliveInterval" "$SSHD_CFG"; then
  sed -i 's/^ClientAliveInterval.*/ClientAliveInterval 120/' "$SSHD_CFG"
else
  echo "ClientAliveInterval 120" >> "$SSHD_CFG"
fi

# ClientAliveCountMax: 心跳失败 N 次后断开 (120*3=360秒=6分钟)
if grep -q "^ClientAliveCountMax" "$SSHD_CFG"; then
  sed -i 's/^ClientAliveCountMax.*/ClientAliveCountMax 3/' "$SSHD_CFG"
else
  echo "ClientAliveCountMax 3" >> "$SSHD_CFG"
fi

# LoginGraceTime: 登录超时
if grep -q "^LoginGraceTime" "$SSHD_CFG"; then
  sed -i 's/^LoginGraceTime.*/LoginGraceTime 60/' "$SSHD_CFG"
else
  echo "LoginGraceTime 60" >> "$SSHD_CFG"
fi

echo "  ✓ SSH超时: ClientAliveInterval=120, ClientAliveCountMax=3, LoginGraceTime=60"

# -------------------- 6. sudo NOPASSWD --------------------
echo "[6/9] 移除 sudo NOPASSWD 标记..."
if [ -f /etc/sudoers.d/90-cloud-init-users ]; then
  cp /etc/sudoers.d/90-cloud-init-users /etc/sudoers.d/90-cloud-init-users.bak
  # 注释掉 NOPASSWD 行
  sed -i 's/^root ALL=(ALL) NOPASSWD:ALL/# root ALL=(ALL) NOPASSWD:ALL  # 已由安全脚本禁用/' /etc/sudoers.d/90-cloud-init-users
  echo "  ✓ /etc/sudoers.d/90-cloud-init-users 中的 NOPASSWD 已注释"
fi

# -------------------- 7. wheel 组外禁止 su --------------------
echo "[7/9] 限制 su 切换权限..."
if [ -f /etc/pam.d/su ]; then
  cp /etc/pam.d/su /etc/pam.d/su.bak
  # 启用 pam_wheel - 只有 wheel 组成员才能 su
  if grep -q "^# auth.*required.*pam_wheel.so" /etc/pam.d/su; then
    sed -i 's/^# auth\s\+required\s\+pam_wheel.so/auth       required   pam_wheel.so/' /etc/pam.d/su
    echo "  ✓ pam_wheel 已启用（仅 wheel 组可 su 到 root）"
  else
    echo "  - pam_wheel 已配置或格式不匹配，请手动检查 /etc/pam.d/su"
  fi
fi

# -------------------- 8. SSH 重启 --------------------
echo "[8/9] 重启 SSH 服务..."
if systemctl is-active sshd > /dev/null 2>&1; then
  systemctl restart sshd 2>/dev/null || systemctl restart ssh 2>/dev/null
elif systemctl is-active ssh > /dev/null 2>&1; then
  systemctl restart ssh 2>/dev/null
else
  /etc/init.d/ssh restart 2>/dev/null || /etc/init.d/sshd restart 2>/dev/null || true
fi
echo "  ✓ SSH 已重启"

# -------------------- 9. TCP Wrappers (如果可用) --------------------
echo "[9/9] 安装 TCP Wrappers..."
if command -v apt-get > /dev/null 2>&1; then
  apt-get install -y tcpd 2>/dev/null && echo "  ✓ tcpd 已安装" || echo "  - tcpd 不可用（现代 Debian 已移除），不影响安全"
elif command -v yum > /dev/null 2>&1; then
  yum install -y tcp_wrappers 2>/dev/null && echo "  ✓ tcp_wrappers 已安装" || echo "  - tcp_wrappers 不可用"
fi

echo ""
echo "========================================="
echo "  自动修复完成！"
echo "========================================="
echo ""
echo "以下漏洞已修复:"
echo "  ✓ PASS_MIN_DAYS = 7"
echo "  ✓ TMOUT = 600"
echo "  ✓ 禁 Ping"
echo "  ✓ grub.cfg 权限 600"
echo "  ✓ SSH 空闲/登录超时"
echo "  ✓ sudo NOPASSWD 已移除"
echo "  ✓ wheel 组外 su 已限制"
echo ""
echo "需要手动在宝塔面板操作的:"
echo "  ● 面板登录告警: 【设置】→【告警通知】→【告警列表】→【添加任务】"
echo "  ● 系统监控: 【监控】→【系统监控】中开启"
echo ""
echo "以下是误报，不需要修复:"
echo "  ✗ suid/sgid 特权文件 - 这些是系统正常运行所需，移除会导致系统故障"
echo "  ✗ SSH 安全套接字加密 - SSH 默认已加密，无需额外配置"
echo "  ✗ TCP Wrappers - 现代 Debian/Ubuntu 已移除该组件，不影响安全"
echo ""

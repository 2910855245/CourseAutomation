<script setup lang="ts">
// @ts-nocheck
import { ref, reactive } from 'vue'
import { useAdminState } from './adminState'
import { useAppStore } from '@/stores/app'
import { useConfirmSingleton } from '@/composables/useConfirm'
import { api } from '@/api'

const store = useAppStore()
const { showConfirm } = useConfirmSingleton()
const { currentRole, usersSubTab, unifiedUsers, unifiedTotal, unifiedStats, unifiedRoleFilter, unifiedAgentFilter, unifiedSearch, loadingUnified, loadUnifiedUsers, subAdmins, loadingSubAdmins, loadSubAdmins, doRevokeSubAdmin, fmtMoney, fmtDate, fmtShortDate, statusClass, statusLabel, openTopup, openRateModal, approveAgent, suspendAgent, reactivateAgent } = useAdminState()

// Local modal state — avoids cross-component reactivity issues with initAdminState
const showCreateModal = ref(false)
const newSubAdmin = reactive({ user_id: '', username: '', password: '' })
const creatingSubAdmin = ref(false)

async function doCreateSubAdmin() {
  if (!newSubAdmin.user_id.trim() || !newSubAdmin.username.trim() || !newSubAdmin.password) {
    store.toast('请填写完整信息', 'warning')
    return
  }
  if (newSubAdmin.password.length < 6) {
    store.toast('密码至少6位', 'warning')
    return
  }
  if (!/[a-zA-Z]/.test(newSubAdmin.password) || !/\d/.test(newSubAdmin.password)) {
    store.toast('密码需同时包含字母和数字', 'warning')
    return
  }
  creatingSubAdmin.value = true
  try {
    await api.admin.subAdmins.create({
      user_id: newSubAdmin.user_id.trim(),
      username: newSubAdmin.username.trim(),
      password: newSubAdmin.password,
      nickname: newSubAdmin.username.trim(),
    })
    store.toast('合伙人创建成功', 'success')
    showCreateModal.value = false
    newSubAdmin.user_id = ''
    newSubAdmin.username = ''
    newSubAdmin.password = ''
    loadSubAdmins()
  } catch (e: any) {
    store.toast(e.message || '创建失败', 'error')
  } finally {
    creatingSubAdmin.value = false
  }
}

async function deleteUser(u: any) {
  const label = u.nickname || u.username || u.user_id
  const ok = await showConfirm({ title: '删除用户', message: `确定删除用户「${label}」吗？`, type: 'warning' })
  if (!ok) return
  try {
    await api.adminUsers.delete(u.user_id)
    store.toast(`用户 ${label} 已删除`, 'success')
    loadUnifiedUsers()
  } catch (e: any) {
    store.toast(e.message || '删除失败', 'error')
  }
}
</script>

<template>
  <div>
    <div class="agent-subtabs">
      <button
        v-if="currentRole === 'admin'"
        :class="['ast', { active: usersSubTab === 'users' }]"
        @click="usersSubTab = 'users'"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        ><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle
          cx="9"
          cy="7"
          r="4"
        /></svg>
        全部用户
      </button>
      <button
        v-if="currentRole === 'admin'"
        :class="['ast', { active: usersSubTab === 'subadmins' }]"
        @click="usersSubTab = 'subadmins'"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        ><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle
          cx="9"
          cy="7"
          r="4"
        /><path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" /></svg>
        合伙人
      </button>
    </div>

    <!-- Sub-tab: All Users (unified) -->
    <div v-if="usersSubTab === 'users'">
      <div
        v-if="unifiedStats"
        class="agent-stats-row"
      >
        <div class="mini-stat">
          <div class="ms-val">
            {{ unifiedStats.total_users || 0 }}
          </div><div class="ms-label">
            总用户数
          </div>
        </div>
        <div class="mini-stat">
          <div class="ms-val ok">
            {{ unifiedStats.total_agents || 0 }}
          </div><div class="ms-label">
            总代理数
          </div>
        </div>
        <div class="mini-stat">
          <div class="ms-val money">
            {{ unifiedStats.active_agents || 0 }}
          </div><div class="ms-label">
            活跃代理
          </div>
        </div>
        <div class="mini-stat">
          <div class="ms-val">
            {{ unifiedStats.pending_agents || 0 }}
          </div><div class="ms-label">
            待审核代理
          </div>
        </div>
      </div>
      <div class="section-actions">
        <div class="filter-bar">
          <div class="filter-scroll">
            <button
              :class="['chip', { active: unifiedRoleFilter === '' }]"
              @click="unifiedRoleFilter = ''; loadUnifiedUsers()"
            >
              全部
            </button>
            <button
              :class="['chip', { active: unifiedRoleFilter === 'sub_admin' }]"
              @click="unifiedRoleFilter = 'sub_admin'; loadUnifiedUsers()"
            >
              合伙人
            </button>
            <button
              :class="['chip', { active: unifiedRoleFilter === 'agent' }]"
              @click="unifiedRoleFilter = 'agent'; loadUnifiedUsers()"
            >
              代理
            </button>
            <button
              :class="['chip', { active: unifiedRoleFilter === 'customer' }]"
              @click="unifiedRoleFilter = 'customer'; loadUnifiedUsers()"
            >
              普通用户
            </button>
            <template v-if="unifiedRoleFilter === 'agent' || unifiedRoleFilter === 'sub_admin' || unifiedRoleFilter === ''">
              <span class="filter-divider" />
              <button
                :class="['chip', { active: unifiedAgentFilter === '' }]"
                @click="unifiedAgentFilter = ''; loadUnifiedUsers()"
              >
                全部状态
              </button>
              <button
                :class="['chip', { active: unifiedAgentFilter === 'pending' }]"
                @click="unifiedAgentFilter = 'pending'; loadUnifiedUsers()"
              >
                待审核
              </button>
              <button
                :class="['chip', { active: unifiedAgentFilter === 'active' }]"
                @click="unifiedAgentFilter = 'active'; loadUnifiedUsers()"
              >
                活跃
              </button>
              <button
                :class="['chip', { active: unifiedAgentFilter === 'suspended' }]"
                @click="unifiedAgentFilter = 'suspended'; loadUnifiedUsers()"
              >
                已暂停
              </button>
            </template>
          </div>
        </div>
        <div class="filter-search-row">
          <input
            v-model="unifiedSearch"
            placeholder="搜索用户名/昵称"
            class="search-input"
            @keyup.enter="loadUnifiedUsers"
          >
          <button
            class="btn btn-ghost"
            :disabled="loadingUnified"
            @click="loadUnifiedUsers"
          >
            <span
              v-if="loadingUnified"
              class="spinner"
              style="width:14px;height:14px"
            />
            {{ loadingUnified ? '加载中' : '刷新' }}
          </button>
        </div>
      </div>
      <div
        v-if="unifiedUsers.length > 0"
        class="table-wrap"
      >
        <table class="data-table">
          <thead>
            <tr>
              <th>用户名</th><th>角色/等级</th><th>佣金比例</th><th>用户余额</th><th>代理余额</th><th>订单数</th><th>邀请人数</th><th>状态</th><th>注册时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="u in unifiedUsers"
              :key="u.user_id"
            >
              <td>
                <div class="user-cell">
                  <span class="uname">{{ u.nickname || u.username }}</span>
                  <span class="uid">{{ u.username }}</span>
                </div>
              </td>
              <td>
                <span
                  v-if="u.role === 'admin'"
                  class="status-tag bad"
                >管理员</span>
                <span
                  v-else-if="u.role === 'sub_admin'"
                  class="status-tag primary"
                >合伙人</span>
                <template v-else-if="u.agent">
                  <span class="status-tag primary">代理</span>
                  <span
                    class="level-tag"
                    :class="'l' + u.agent.tier_level"
                    style="margin-left:4px"
                  >L{{ u.agent.tier_level }}</span>
                </template>
                <span
                  v-else
                  class="status-tag muted"
                >用户</span>
              </td>
              <td>{{ u.agent ? (u.agent.flow_commission_rate * 100).toFixed(0) + '%' : '-' }}</td>
              <td class="money-cell">
                {{ fmtMoney(u.balance) }}
              </td>
              <td class="money-cell">
                {{ u.agent ? fmtMoney(u.agent.available_balance) : '-' }}
              </td>
              <td>{{ u.order_count || 0 }}</td>
              <td>{{ u.referral_count || 0 }}</td>
              <td>
                <span
                  v-if="u.agent"
                  :class="['status-tag', statusClass[u.agent.status]]"
                >{{ statusLabel[u.agent.status] || u.agent.status }}</span>
                <span
                  v-else
                  class="status-tag ok"
                >正常</span>
              </td>
              <td class="date-cell">
                {{ fmtDate(u.created_at) }}
              </td>
              <td>
                <div
                  v-if="u.role !== 'admin'"
                  class="action-cell"
                >
                  <span class="action-slot">
                    <button
                      class="btn btn-xs btn-success"
                      @click="openTopup(u, 'topup')"
                    >
                      充值
                    </button>
                    <button
                      class="btn btn-xs btn-warn"
                      @click="openTopup(u, 'deduct')"
                    >
                      扣费
                    </button>
                    <template v-if="u.agent">
                      <button
                        v-if="u.agent.status === 'pending'"
                        class="btn btn-xs btn-success"
                        @click="approveAgent(u.agent.agent_id)"
                      >
                        审核
                      </button>
                      <button
                        v-if="u.agent.status === 'active'"
                        class="btn btn-xs btn-warn"
                        @click="suspendAgent(u.agent.agent_id)"
                      >
                        暂停
                      </button>
                      <button
                        v-if="u.agent.status === 'suspended'"
                        class="btn btn-xs btn-primary"
                        @click="reactivateAgent(u.agent.agent_id)"
                      >
                        恢复
                      </button>
                      <button
                        class="btn btn-xs btn-ghost"
                        @click="openRateModal(u.agent)"
                      >
                        调比例
                      </button>
                    </template>
                  </span>
                  <button
                    class="del-btn"
                    title="删除用户"
                    @click="deleteUser(u)"
                  >
                    X
                  </button>
                </div>
                <span
                  v-else
                  class="status-tag muted"
                >-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        v-else-if="!loadingUnified"
        class="empty"
      >
        <p>暂无用户数据</p>
      </div>
    </div>

    <!-- Sub-tab: Sub-admins -->
    <div v-if="usersSubTab === 'subadmins'">
      <div class="ps-panel">
        <div class="ps-header">
          <h3>合伙人列表</h3>
          <button
            class="btn btn-sm btn-primary"
            @click="showCreateModal = true"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><line
              x1="12"
              y1="5"
              x2="12"
              y2="19"
            /><line
              x1="5"
              y1="12"
              x2="19"
              y2="12"
            /></svg>
            添加合伙人
          </button>
        </div>
        <p class="ps-desc">
          合伙人拥有代理审核、订单管理、佣金查看等权限，但不能管理系统配置和人员管理。
        </p>
        <div
          v-if="loadingSubAdmins"
          class="ps-loading"
        >
          加载中...
        </div>
        <div
          v-else-if="!subAdmins.length"
          class="ps-empty"
        >
          <span class="ps-empty-icon">
            <svg
              width="40"
              height="40"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#94a3b8"
              stroke-width="1.5"
            ><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle
              cx="9"
              cy="7"
              r="4"
            /><path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" /></svg>
          </span>
          <p>暂无合伙人，点击上方按钮添加</p>
        </div>
        <div
          v-else
          class="ps-table-wrap"
        >
          <table class="data-table">
            <thead><tr><th>用户名</th><th>用户ID</th><th>角色</th><th>注册时间</th><th>关联代理</th><th>操作</th></tr></thead>
            <tbody>
              <tr
                v-for="s in subAdmins"
                :key="s.user_id"
              >
                <td><strong>{{ s.username }}</strong></td>
                <td><code>{{ s.user_id }}</code></td>
                <td><span class="badge badge-info">合伙人</span></td>
                <td>{{ fmtShortDate(s.created_at) }}</td>
                <td>
                  <template v-if="s.agent">
                    <span class="badge badge-success">L{{ s.agent.tier_level }}</span>
                    <span style="font-size:12px;color:#64748b;margin-left:4px">推荐码: {{ s.agent.referral_code }}</span>
                  </template>
                  <span
                    v-else
                    class="text-muted"
                    style="font-size:12px"
                  >-</span>
                </td>
                <td>
                  <button
                    class="btn btn-xs btn-ghost"
                    style="color:var(--c-danger)"
                    @click="doRevokeSubAdmin(s.user_id)"
                  >
                    撤销权限
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Create SubAdmin Modal (local) -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal">
        <h3>添加合伙人</h3>
        <p class="modal-sub">合伙人可以审批代理、管理订单、查看佣金数据</p>
        <div class="field">
          <label>用户ID</label>
          <input v-model="newSubAdmin.user_id" placeholder="如: subadmin001" />
        </div>
        <div class="field">
          <label>用户名</label>
          <input v-model="newSubAdmin.username" placeholder="如: 张三" />
        </div>
        <div class="field">
          <label>密码</label>
          <input v-model="newSubAdmin.password" type="password" placeholder="至少6位，包含字母和数字" />
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showCreateModal = false; newSubAdmin.user_id=''; newSubAdmin.username=''; newSubAdmin.password=''">取消</button>
          <button class="btn btn-primary" :disabled="creatingSubAdmin" @click="doCreateSubAdmin">
            {{ creatingSubAdmin ? '创建中...' : '确认创建' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.action-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}
.action-slot {
  display: inline-flex;
  min-width: 32px;
}
.del-btn {
  margin-left: auto;
  color: #ccc;
  font-size: 11px;
  cursor: pointer;
  padding: 0 4px;
  border: none;
  background: none;
  line-height: 1;
}
.del-btn:hover {
  color: #ef4444;
}
</style>
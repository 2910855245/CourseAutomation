<script setup lang="ts">
import { ref } from 'vue'
import { useAdminStore } from '@/stores/admin'
import { useAppStore } from '@/stores/app'
import { useConfirmSingleton } from '@/composables/useConfirm'
import { api } from '@/api'

const store = useAppStore()
const { showConfirm } = useConfirmSingleton()
const { fmtDate, fmtMoney } = useAdminStore().state().dashboard
const { loadUsers, loadingUsers, openTopup, users, usersTotal } = useAdminStore().state().users

async function deleteUser(u: any) {
  const label = u.nickname || u.username || u.user_id
  const ok = await showConfirm({ title: '删除用户', message: `确定删除用户「${label}」吗？`, type: 'warning' })
  if (!ok) return
  try {
    await api.adminUsers.delete(u.user_id)
    store.toast(`用户 ${label} 已删除`, 'success')
    loadUsers()
  } catch (e: any) {
    store.toast(e.message || '删除失败', 'error')
  }
}
</script>

<template>
  <div>
    <div class="section-actions">
      <div class="filter-search-row">
        <button
          class="btn btn-ghost"
          :disabled="loadingUsers"
          @click="loadUsers"
        >
          <span
            v-if="loadingUsers"
            class="spinner"
            style="width:14px;height:14px"
          />
          {{ loadingUsers ? '加载中' : '刷新' }}
        </button>
        <span class="text-muted" style="font-size:12px">共 {{ usersTotal }} 个用户</span>
      </div>
    </div>
    <div
      v-if="users.length > 0"
      class="table-wrap"
    >
      <table class="data-table">
        <thead>
          <tr>
            <th>用户名</th><th>角色</th><th>用户余额</th><th>订单数</th><th>消费总额</th><th>注册时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="u in users"
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
                v-else
                class="status-tag muted"
              >用户</span>
            </td>
            <td class="money-cell">
              {{ fmtMoney(u.balance) }}
            </td>
            <td>{{ u.order_count || 0 }}</td>
            <td class="money-cell">
              {{ fmtMoney(u.total_spent) }}
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
      v-else-if="!loadingUsers"
      class="empty"
    >
      <p>暂无用户数据</p>
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

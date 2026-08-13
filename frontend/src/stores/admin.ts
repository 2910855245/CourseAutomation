/**
 * Admin 后台状态 store — Admin.vue 与 10 个 tab 组件的显式类型共享点。
 *
 * 替代旧的 adminState.ts 透传（Record<string, any>）：
 * - 切片类型 = 对应 composable 的 ReturnType，编译器保证 tab 取用不越界；
 * - shallowRef + markRaw 保持原始 refs 的响应性（不 reactive 包裹避免 unwrap 丢响应）。
 */

import { markRaw, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { useAuth } from '@/composables/useAuth'
import { useDashboard } from '@/composables/useDashboard'
import { useOrders } from '@/composables/useOrders'
import { useUsers } from '@/composables/useUsers'
import { usePayments } from '@/composables/usePayments'
import { useSystemConfig } from '@/composables/useSystemConfig'
import { useYpayAdmin } from '@/composables/useYpayAdmin'

export interface AdminUiSlice {
  activeTab: ReturnType<typeof useDashboard> extends never ? never : any // 占位，实际在 Admin.vue 构造
}

export interface AdminStateContainer {
  auth: ReturnType<typeof useAuth>
  dashboard: ReturnType<typeof useDashboard>
  orders: ReturnType<typeof useOrders>
  users: ReturnType<typeof useUsers>
  payments: ReturnType<typeof usePayments>
  sysConfig: ReturnType<typeof useSystemConfig>
  ypay: ReturnType<typeof useYpayAdmin>
  ui: {
    activeTab: any
    switchTab: (tab: any) => void
    platformNames: any
    loadPlatformNames: () => Promise<void>
    getPlatformName: (id: number) => string
  }
}

export const useAdminStore = defineStore('admin', () => {
  const container = shallowRef<AdminStateContainer | null>(null)

  function init(c: AdminStateContainer) {
    container.value = markRaw(c)
  }

  function state(): AdminStateContainer {
    if (!container.value) {
      throw new Error('useAdminStore().state() called before init()')
    }
    return container.value
  }

  return { container, init, state }
})

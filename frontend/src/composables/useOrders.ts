// 订单管理
import { ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { api, type OrderItem } from '@/api'
import { useConfirmSingleton } from '@/composables/useConfirm'

export function useOrders() {
  const store = useAppStore()
  const { showConfirm } = useConfirmSingleton()

  function getRole(): 'admin' | 'sub_admin' { return store.adminToken ? 'admin' : 'sub_admin' }

  const orders = ref<OrderItem[]>([])
  const ordersTotal = ref(0)
  const ordersStatusFilter = ref('')
  const loadingOrders = ref(false)

  async function loadOrders() {
    loadingOrders.value = true
    try {
      const params: any = { limit: 50, offset: 0 }
      if (ordersStatusFilter.value) params.status = ordersStatusFilter.value
      if (getRole() === 'admin') {
        const r = await api.adminOrders.list(params)
        orders.value = r.data.items; ordersTotal.value = r.data.total
      } else {
        const r = await api.subAdmin.orders.list(params)
        orders.value = r.data.items; ordersTotal.value = r.data.total
      }
    } catch (e: any) { store.toast(e.message || '加载订单失败', 'error') }
    finally { loadingOrders.value = false }
  }

  async function acceptOrder(id: string) {
    try {
      if (getRole() === 'admin') await api.adminOrders.accept(id)
      else await api.subAdmin.orders.accept(id)
      store.toast('订单已接单', 'success'); loadOrders()
    } catch (e: any) { store.toast(e.message, 'error') }
  }

  async function enqueueOrder(id: string) {
    try { await api.adminOrders.enqueue(id); store.toast('订单已入队', 'success'); loadOrders() } catch (e: any) { store.toast(e.message, 'error') }
  }

  async function failOrder(id: string) {
    const ok = await showConfirm({ title: '标记失败', message: '确定将该订单标记为失败吗？此操作不可撤销。', type: 'danger' })
    if (!ok) return
    try {
      if (getRole() === 'admin') await api.adminOrders.fail(id, '管理员手动标记失败')
      else await api.subAdmin.orders.fail(id, '手动标记失败')
      store.toast('订单已标记失败', 'success'); loadOrders()
    } catch (e: any) { store.toast(e.message, 'error') }
  }

  async function executeOrder(id: string) {
    try { await api.adminOrders.execute(id); store.toast('订单执行中', 'success'); loadOrders() } catch (e: any) { store.toast(e.message, 'error') }
  }

  async function completeOrder(id: string) {
    try {
      if (getRole() === 'admin') await api.adminOrders.complete(id)
      else await api.subAdmin.orders.complete(id)
      store.toast('订单已完成', 'success'); loadOrders()
    } catch (e: any) { store.toast(e.message, 'error') }
  }

  async function clearOrderHistory() {
    try { const res = await api.orders.clearHistory(); loadOrders(); store.toast(res.message || '历史记录已清除', 'success') }
    catch (e: any) { store.toast(e.message, 'error') }
  }

  return {
    orders, ordersTotal, ordersStatusFilter, loadingOrders,
    loadOrders, acceptOrder, enqueueOrder, failOrder, executeOrder, completeOrder, clearOrderHistory,
  }
}

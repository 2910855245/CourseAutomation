import { ref } from 'vue'
import { useAppStore } from '../stores/app'

export function useApiCall<T = any>(fn: () => Promise<T>) {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const data = ref<T | null>(null)

  async function execute() {
    loading.value = true
    error.value = null
    try {
      data.value = await fn()
      return data.value
    } catch (e: any) {
      error.value = e.message || '请求失败'
      const store = useAppStore()
      store.toast(error.value!, 'error')
      throw e
    } finally {
      loading.value = false
    }
  }

  return { loading, error, data, execute }
}

export function buildQuery(params?: Record<string, any>): string {
  if (!params) return ''
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  }
  const qs = q.toString()
  return qs ? '?' + qs : ''
}

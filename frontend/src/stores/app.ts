import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { setAdminApiToken } from '@/api'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

/**
 * toast 的实际渲染由外部注入（见 components/ToastBridge.vue → Naive UI message），
 * 这样 ~50 处 `store.toast(...)` 调用点无需改动，也不会把 Naive 的实例
 * 泄漏到 store / composable 这类非组件上下文里。
 */
export type ToastImpl = (message: string, type: ToastType) => void

export type ThemeMode = 'light' | 'dark'

export const useAppStore = defineStore('app', () => {
  // ── Toast ──
  let toastImpl: ToastImpl | null = null

  function setToastImpl(fn: ToastImpl | null) {
    toastImpl = fn
  }

  function toast(message: string, type: ToastType = 'success') {
    if (toastImpl) toastImpl(message, type)
    else console.warn(`[toast:${type}] ${message}`)
  }

  // ── 主题（浅色 / 暗色）──
  // 初始值直接取 index.html 内联脚本算好的 data-theme（它在样式表加载前执行，
  // 保证首屏不闪），这里不再重复一遍「localStorage 还是系统偏好」的判定逻辑。
  const themeMode = ref<ThemeMode>(
    (document.documentElement.dataset.theme as ThemeMode) || 'light',
  )
  const isDark = computed(() => themeMode.value === 'dark')

  function setThemeMode(mode: ThemeMode) {
    themeMode.value = mode
    document.documentElement.dataset.theme = mode
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.setAttribute('content', mode === 'dark' ? '#111114' : '#f7f7f8')
    try {
      localStorage.setItem('theme', mode)
    } catch {
      // 隐私模式等场景下 localStorage 不可用，主题仅本次会话生效
    }
  }

  function toggleTheme() {
    setThemeMode(isDark.value ? 'light' : 'dark')
  }

  // ── 管理员令牌 ──
  const adminToken = ref(localStorage.getItem('admin_token') || '')
  const isAdminLoggedIn = ref(!!adminToken.value)

  function setAdminToken(token: string) {
    adminToken.value = token
    localStorage.setItem('admin_token', token)
    setAdminApiToken(token)
    isAdminLoggedIn.value = true
  }

  function clearAdminToken() {
    adminToken.value = ''
    localStorage.removeItem('admin_token')
    setAdminApiToken('')
    isAdminLoggedIn.value = false
  }

  if (adminToken.value) setAdminApiToken(adminToken.value)

  return {
    toast, setToastImpl,
    themeMode, isDark, setThemeMode, toggleTheme,
    adminToken, setAdminToken, clearAdminToken, isAdminLoggedIn,
  }
})

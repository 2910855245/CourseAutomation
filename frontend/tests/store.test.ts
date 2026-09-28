import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAppStore } from '@/stores/app'

// Mock localStorage
const store: Record<string, string> = {}
vi.stubGlobal('localStorage', {
  getItem: (k: string) => store[k] || null,
  setItem: (k: string, v: string) => { store[k] = v },
  removeItem: (k: string) => { delete store[k] },
})

// Mock api module
vi.mock('@/api', () => ({
  setAdminApiToken: vi.fn(),
}))

describe('useAppStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    Object.keys(store).forEach(k => delete store[k])
    delete document.documentElement.dataset.theme
  })

  it('初始状态无 token', () => {
    const s = useAppStore()
    expect(s.adminToken).toBe('')
    expect(s.isAdminLoggedIn).toBe(false)
  })

  it('setAdminToken 设置 token', () => {
    const s = useAppStore()
    s.setAdminToken('test-token')
    expect(s.adminToken).toBe('test-token')
    expect(s.isAdminLoggedIn).toBe(true)
    expect(store['admin_token']).toBe('test-token')
  })

  it('clearAdminToken 清除 token', () => {
    const s = useAppStore()
    s.setAdminToken('tok')
    s.clearAdminToken()
    expect(s.adminToken).toBe('')
    expect(s.isAdminLoggedIn).toBe(false)
    expect(store['admin_token']).toBeUndefined()
  })

  it('toast 转发给注入的实现（Naive message 由 ToastBridge 注入）', () => {
    const s = useAppStore()
    const seen: Array<[string, string]> = []
    s.setToastImpl((message, type) => seen.push([message, type]))

    s.toast('成功', 'success')
    s.toast('失败', 'error')
    s.toast('纯文本') // 缺省 type

    expect(seen).toEqual([
      ['成功', 'success'],
      ['失败', 'error'],
      ['纯文本', 'success'],
    ])
  })

  it('未注入实现时 toast 降级为 console.warn 而不抛错', () => {
    const s = useAppStore()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => { })
    s.toast('提示', 'info')
    expect(warn).toHaveBeenCalledWith('[toast:info] 提示')
    warn.mockRestore()
  })

  it('themeMode 默认浅色且可切换', () => {
    const s = useAppStore()
    expect(s.themeMode).toBe('light')
    expect(s.isDark).toBe(false)

    s.toggleTheme()
    expect(s.isDark).toBe(true)
    expect(store['theme']).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')

    s.toggleTheme()
    expect(s.isDark).toBe(false)
    expect(store['theme']).toBe('light')
  })
})

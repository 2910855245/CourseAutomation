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
  setUserApiToken: vi.fn(),
}))

describe('useAppStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    Object.keys(store).forEach(k => delete store[k])
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

  it('setUserToken 设置用户 token', () => {
    const s = useAppStore()
    s.setUserToken('user-tok', { username: 'test' })
    expect(s.userToken).toBe('user-tok')
    expect(s.isUserLoggedIn).toBe(true)
    expect(s.userInfo).toEqual({ username: 'test' })
  })

  it('toast 添加并自动移除', async () => {
    vi.useFakeTimers()
    const s = useAppStore()
    s.toast('成功', 'success')
    expect(s.toasts).toHaveLength(1)
    expect(s.toasts[0].message).toBe('成功')

    vi.advanceTimersByTime(3500)
    expect(s.toasts).toHaveLength(0)
    vi.useRealTimers()
  })
})

import { describe, it, expect } from 'vitest'
import { buildQuery } from '@/composables/useApi'
import { usePlatformNames } from '@/composables/usePlatformNames'

describe('buildQuery', () => {
  it('无参数返回空字符串', () => {
    expect(buildQuery()).toBe('')
    expect(buildQuery(undefined)).toBe('')
  })

  it('正常参数拼接', () => {
    const q = buildQuery({ status: 'pending', limit: 10 })
    expect(q).toContain('status=pending')
    expect(q).toContain('limit=10')
    expect(q.startsWith('?')).toBe(true)
  })

  it('过滤空值', () => {
    const q = buildQuery({ a: '1', b: '', c: null, d: undefined })
    expect(q).toBe('?a=1')
  })

  it('数字转字符串', () => {
    expect(buildQuery({ page: 0 })).toBe('?page=0')
    expect(buildQuery({ count: 99 })).toBe('?count=99')
  })

  it('特殊字符编码', () => {
    const q = buildQuery({ name: '张三' })
    expect(q).toContain(encodeURIComponent('张三'))
  })
})

describe('usePlatformNames', () => {
  it('未加载时返回默认名', () => {
    const { getName } = usePlatformNames()
    expect(getName(999)).toBe('平台999')
  })
})

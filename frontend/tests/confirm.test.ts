import { describe, it, expect } from 'vitest'
import { useConfirm } from '@/composables/useConfirm'

describe('useConfirm', () => {
  it('confirm 返回 true', async () => {
    const { showConfirm, confirm } = useConfirm()
    const p = showConfirm('确认删除？')
    confirm()
    expect(await p).toBe(true)
  })

  it('cancel 返回 false', async () => {
    const { showConfirm, cancel } = useConfirm()
    const p = showConfirm('确认删除？')
    cancel()
    expect(await p).toBe(false)
  })

  it('字符串参数设置 message', async () => {
    const { showConfirm, confirmOptions, confirm } = useConfirm()
    const p = showConfirm('测试消息')
    expect(confirmOptions.value.message).toBe('测试消息')
    confirm()
    await p
  })

  it('对象参数设置选项', async () => {
    const { showConfirm, confirmOptions, cancel } = useConfirm()
    const p = showConfirm({ title: '标题', message: '内容', type: 'danger' })
    expect(confirmOptions.value.title).toBe('标题')
    expect(confirmOptions.value.type).toBe('danger')
    cancel()
    await p
  })
})

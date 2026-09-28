import { describe, it, expect, afterEach } from 'vitest'
import { useConfirm, useConfirmSingleton, setConfirmImpl, type ConfirmOptions } from '@/composables/useConfirm'

// 真实弹窗由 ConfirmBridge.vue 注入 Naive UI dialog；此处注入假实现，
// 只验证 useConfirm 这层的参数归一化与 Promise 语义。
describe('useConfirm', () => {
  afterEach(() => setConfirmImpl(null))

  it('字符串参数归一化为 message，返回 true', async () => {
    const captured: ConfirmOptions[] = []
    setConfirmImpl((opts) => { captured.push(opts); return Promise.resolve(true) })

    const { showConfirm } = useConfirm()
    expect(await showConfirm('确认删除？')).toBe(true)
    expect(captured[0]).toEqual({ message: '确认删除？' })
  })

  it('对象参数原样透传，返回 false', async () => {
    const captured: ConfirmOptions[] = []
    setConfirmImpl((opts) => { captured.push(opts); return Promise.resolve(false) })

    const { showConfirm } = useConfirm()
    const opts: ConfirmOptions = { title: '标题', message: '内容', type: 'danger' }
    expect(await showConfirm(opts)).toBe(false)
    expect(captured[0]).toEqual(opts)
  })

  it('未注入实现时保守返回 false（不执行危险操作）', async () => {
    const { showConfirm } = useConfirm()
    expect(await showConfirm('确认删除？')).toBe(false)
  })

  it('useConfirmSingleton 复用同一实例', () => {
    expect(useConfirmSingleton().showConfirm).toBe(useConfirmSingleton().showConfirm)
  })
})

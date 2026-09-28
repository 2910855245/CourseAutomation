export interface ConfirmOptions {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  type?: 'danger' | 'warning' | 'info'
}

type ConfirmImpl = (opts: ConfirmOptions) => Promise<boolean>

// 实际的弹窗由 components/ConfirmBridge.vue 在挂载时注入（Naive UI dialog）。
// 未注入时（单测、极早期调用）保守地返回 false —— 即「不执行」，
// 对删除类操作来说是安全的降级方向。
let impl: ConfirmImpl | null = null

export function setConfirmImpl(fn: ConfirmImpl | null) {
  impl = fn
}

export function useConfirm() {
  function showConfirm(opts: ConfirmOptions | string): Promise<boolean> {
    const normalized: ConfirmOptions = typeof opts === 'string' ? { message: opts } : opts
    return impl ? impl(normalized) : Promise.resolve(false)
  }

  return { showConfirm }
}

let singleton: ReturnType<typeof useConfirm> | null = null

export function useConfirmSingleton() {
  if (!singleton) singleton = useConfirm()
  return singleton
}

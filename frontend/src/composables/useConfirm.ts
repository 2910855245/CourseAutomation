export interface ConfirmOptions {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  type?: 'danger' | 'warning' | 'info'
}

type ConfirmImpl = (opts: ConfirmOptions) => Promise<boolean>
type AlertImpl = (opts: ConfirmOptions) => Promise<void>

// 实际的弹窗由 components/ConfirmBridge.vue 在挂载时注入（Naive UI dialog）。
// 未注入时（单测、极早期调用）保守地返回 false —— 即「不执行」，
// 对删除类操作来说是安全的降级方向。
let impl: ConfirmImpl | null = null
// 单按钮提示弹窗（业务拒绝类：黑名单、功能未开放等）
let alertImpl: AlertImpl | null = null

export function setConfirmImpl(fn: ConfirmImpl | null) {
  impl = fn
}

export function setAlertImpl(fn: AlertImpl | null) {
  alertImpl = fn
}

export function useConfirm() {
  function showConfirm(opts: ConfirmOptions | string): Promise<boolean> {
    const normalized: ConfirmOptions = typeof opts === 'string' ? { message: opts } : opts
    return impl ? impl(normalized) : Promise.resolve(false)
  }

  /** 只有「我知道了」一个按钮的提示弹窗（用于必须让用户看到的拒绝类提示） */
  function showAlert(opts: ConfirmOptions | string): Promise<void> {
    const normalized: ConfirmOptions = typeof opts === 'string' ? { message: opts } : opts
    return alertImpl ? alertImpl(normalized) : Promise.resolve()
  }

  return { showConfirm, showAlert }
}

let singleton: ReturnType<typeof useConfirm> | null = null

export function useConfirmSingleton() {
  if (!singleton) singleton = useConfirm()
  return singleton
}

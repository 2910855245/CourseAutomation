import { ref } from 'vue'

interface ConfirmOptions {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  type?: 'danger' | 'warning' | 'info'
}

const visible = ref(false)
const options = ref<ConfirmOptions>({ message: '' })
let resolveFn: ((val: boolean) => void) | null = null

export function useConfirm() {
  function confirm(opts: ConfirmOptions | string): Promise<boolean> {
    return new Promise((resolve) => {
      if (resolveFn) {
        resolveFn(false)
      }
      resolveFn = resolve
      if (typeof opts === 'string') {
        options.value = { message: opts }
      } else {
        options.value = opts
      }
      visible.value = true
    })
  }

  function handleConfirm() {
    visible.value = false
    resolveFn?.(true)
    resolveFn = null
  }

  function handleCancel() {
    visible.value = false
    resolveFn?.(false)
    resolveFn = null
  }

  return {
    confirmVisible: visible,
    confirmOptions: options,
    confirm: handleConfirm,
    cancel: handleCancel,
    showConfirm: confirm,
  }
}

let singleton: ReturnType<typeof useConfirm> | null = null

export function useConfirmSingleton() {
  if (!singleton) singleton = useConfirm()
  return singleton
}
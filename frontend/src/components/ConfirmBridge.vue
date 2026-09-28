<script setup lang="ts">
/**
 * 把 Naive UI 的 dialog 适配成 useConfirm 的 Promise<boolean> 语义。
 *
 * 替换了原先自绘的 ConfirmDialog.vue：组件库自带主题与暗色适配，
 * 不必再为模态框单独维护一套 CSS。
 */
import { onUnmounted } from 'vue'
import { useDialog } from 'naive-ui'
import { setConfirmImpl, type ConfirmOptions } from '@/composables/useConfirm'

const dialog = useDialog()

function show(opts: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    // onClose / onMaskClick 与 onPositiveClick 可能先后触发，只认第一次结果
    let settled = false
    const done = (value: boolean) => {
      if (settled) return
      settled = true
      resolve(value)
    }

    const open = opts.type === 'danger'
      ? dialog.error
      : opts.type === 'info'
        ? dialog.info
        : dialog.warning

    open({
      title: opts.title || '确认操作',
      content: opts.message,
      positiveText: opts.confirmText || '确定',
      negativeText: opts.cancelText || '取消',
      onPositiveClick: () => done(true),
      onNegativeClick: () => done(false),
      onMaskClick: () => done(false),
      onClose: () => done(false),
    })
  })
}

setConfirmImpl(show)
onUnmounted(() => setConfirmImpl(null))
</script>

<template>
  <span style="display: none" />
</template>

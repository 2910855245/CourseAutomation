<script setup lang="ts">
/**
 * 把 Naive UI 的 message 实例注入到 app store。
 *
 * 注入放在 setup 期而不是 onMounted：App.vue 渲染 provider 链时本组件先于
 * router-view 内的页面组件执行，因此页面在 setup 阶段调用 store.toast 也已可用。
 */
import { onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import { useAppStore } from '@/stores/app'

const message = useMessage()
const store = useAppStore()

const options = { duration: 3500 }

store.setToastImpl((msg, type) => {
  if (type === 'error') message.error(msg, options)
  else if (type === 'warning') message.warning(msg, options)
  else if (type === 'info') message.info(msg, options)
  else message.success(msg, options)
})

onUnmounted(() => store.setToastImpl(null))
</script>

<template>
  <span style="display: none" />
</template>

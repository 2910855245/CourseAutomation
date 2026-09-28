<script setup lang="ts">
/**
 * 应用外壳：Naive UI provider 链 + 全局桥接组件。
 *
 * 顺序有要求：useMessage()/useDialog() 必须在对应 provider 的后代中调用，
 * 所以 ToastBridge / ConfirmBridge 只能放在 provider 内部。
 * preflight-style-disabled：main.css 已有自己的全局重置，避免两套重置叠加。
 */
import {
  NConfigProvider,
  NLoadingBarProvider,
  NDialogProvider,
  NNotificationProvider,
  NMessageProvider,
  darkTheme,
  zhCN,
  dateZhCN,
} from 'naive-ui'
import ToastBridge from '@/components/ToastBridge.vue'
import ConfirmBridge from '@/components/ConfirmBridge.vue'
import { lightThemeOverrides, darkThemeOverrides } from '@/theme'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
</script>

<template>
  <n-config-provider
    :theme="store.isDark ? darkTheme : null"
    :theme-overrides="store.isDark ? darkThemeOverrides : lightThemeOverrides"
    :locale="zhCN"
    :date-locale="dateZhCN"
    :preflight-style-disabled="true"
  >
    <n-loading-bar-provider>
      <n-dialog-provider>
        <n-notification-provider>
          <n-message-provider>
            <ToastBridge />
            <ConfirmBridge />
            <div class="app-root">
              <router-view v-slot="{ Component }">
                <component :is="Component" />
              </router-view>
            </div>
          </n-message-provider>
        </n-notification-provider>
      </n-dialog-provider>
    </n-loading-bar-provider>
  </n-config-provider>
</template>

<style scoped>
.app-root {
  min-height: 100vh;
}
</style>

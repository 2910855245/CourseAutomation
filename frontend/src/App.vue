<script setup lang="ts">
import { useAppStore } from '@/stores/app'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const store = useAppStore()
const route = useRoute()
const transitionName = ref('page-fade')

watch(() => route.path, (_to, from) => {
  transitionName.value = from ? 'page-slide' : 'page-fade'
})
</script>

<template>
  <div class="app-root">
    <router-view v-slot="{ Component }">
      <component :is="Component" />
    </router-view>
  </div>
  <ConfirmDialog />
  <Teleport to="body">
    <div
      v-if="store.toasts.length"
      class="toast-container"
    >
      <div
        v-for="t in store.toasts"
        :key="t.id"
        class="toast"
        :class="t.type"
      >
        <span class="toast-icon">
          <svg
            v-if="t.type === 'success'"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
          ><path d="M20 6L9 17l-5-5" /></svg>
          <svg
            v-else-if="t.type === 'error'"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
          ><circle
            cx="12"
            cy="12"
            r="10"
          /><line
            x1="15"
            y1="9"
            x2="9"
            y2="15"
          /><line
            x1="9"
            y1="9"
            x2="15"
            y2="15"
          /></svg>
          <svg
            v-else-if="t.type === 'warning'"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          ><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /><line
            x1="12"
            y1="9"
            x2="12"
            y2="13"
          /><line
            x1="12"
            y1="17"
            x2="12.01"
            y2="17"
          /></svg>
          <svg
            v-else
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          ><circle
            cx="12"
            cy="12"
            r="10"
          /><line
            x1="12"
            y1="16"
            x2="12"
            y2="12"
          /><line
            x1="12"
            y1="8"
            x2="12.01"
            y2="8"
          /></svg>
        </span>
        <span class="toast-msg">{{ t.message }}</span>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity .3s cubic-bezier(.32,.72,.35,1), transform .3s cubic-bezier(.32,.72,.35,1);
}
.page-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.page-slide-enter-active,
.page-slide-leave-active {
  transition: opacity .35s cubic-bezier(.32,.72,.35,1), transform .35s cubic-bezier(.32,.72,.35,1);
}
.page-slide-enter-from {
  opacity: 0;
  transform: translateX(24px);
}
.page-slide-leave-to {
  opacity: 0;
  transform: translateX(-24px);
}

.app-root {
  min-height: 100vh;
}

.toast-container {
  position: fixed;
  top: 20px;
  right: 24px;
  z-index: 10000;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  color: var(--c-text);
  background: var(--c-surface);
  border: 1px solid var(--c-border-light);
  box-shadow: var(--shadow-md);
  animation: toastIn .3s cubic-bezier(.32,.72,.35,1) both;
  pointer-events: auto;
  max-width: 360px;
}

.toast-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
}

.toast-icon svg {
  width: 12px;
  height: 12px;
}

.toast.success .toast-icon { background: var(--c-success); color: #fff; }
.toast.error .toast-icon { background: var(--c-danger); color: #fff; }
.toast.warning .toast-icon { background: var(--c-warning); color: #fff; }
.toast.info .toast-icon { background: var(--c-info); color: #fff; }

.toast-msg {
  line-height: 1.4;
}

@keyframes toastIn {
  from {
    opacity: 0;
    transform: translateX(16px) scale(.97);
  }
  to {
    opacity: 1;
    transform: translateX(0) scale(1);
  }
}

@media (max-width: 768px) {
  .toast-container {
    top: 12px;
    right: 12px;
    left: 12px;
    align-items: center;
  }

  .toast {
    max-width: 100%;
    width: 100%;
  }
}
</style>

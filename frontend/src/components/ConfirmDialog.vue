<script setup lang="ts">
import { useConfirmSingleton } from '@/composables/useConfirm'

const { confirmVisible, confirmOptions, confirm, cancel } = useConfirmSingleton()
</script>

<template>
  <Teleport to="body">
    <div
      v-if="confirmVisible"
      class="confirm-overlay"
      @click.self="cancel"
    >
      <div class="confirm-dialog">
        <div
          class="confirm-icon"
          :class="confirmOptions.type || 'warning'"
        >
          <svg
            v-if="confirmOptions.type === 'danger'"
            width="28"
            height="28"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
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
            v-else-if="confirmOptions.type === 'warning'"
            width="28"
            height="28"
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
            width="28"
            height="28"
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
        </div>
        <h3>{{ confirmOptions.title || '确认操作' }}</h3>
        <p>{{ confirmOptions.message }}</p>
        <div class="confirm-actions">
          <button
            class="btn btn-ghost"
            @click="cancel"
          >
            {{ confirmOptions.cancelText || '取消' }}
          </button>
          <button
            :class="['btn', confirmOptions.type === 'danger' ? 'btn-danger' : 'btn-primary']"
            @click="confirm"
          >
            {{ confirmOptions.confirmText || '确认' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.confirm-overlay {
  position: fixed; inset: 0; background: rgba(15,23,42,.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000; backdrop-filter: blur(3px);
  animation: fadeIn .2s ease;
}
.confirm-dialog {
  background: #fff; border-radius: 14px; padding: 32px 28px;
  width: 380px; max-width: 90vw; text-align: center;
  box-shadow: 0 25px 60px rgba(0,0,0,.2);
  animation: scaleIn .2s ease;
}
.confirm-icon {
  width: 56px; height: 56px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  margin: 0 auto 16px;
}
.confirm-icon.danger { background: #fef2f2; color: #ef4444; }
.confirm-icon.warning { background: #fffbeb; color: #f59e0b; }
.confirm-icon.info { background: #eef1fe; color: #4f6ef7; }
.confirm-dialog h3 { font-size: 17px; font-weight: 700; margin-bottom: 8px; color: #1e293b; }
.confirm-dialog p { font-size: 13.5px; color: #64748b; line-height: 1.5; margin-bottom: 24px; }
.confirm-actions { display: flex; justify-content: center; gap: 10px; }
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  padding: 9px 20px; border: none; border-radius: 10px; font-weight: 600;
  font-size: 13.5px; cursor: pointer; transition: all .15s;
}
.btn-primary { background: #4f6ef7; color: #fff; }
.btn-primary:hover { background: #3b5de7; }
.btn-danger { background: #ef4444; color: #fff; }
.btn-danger:hover { background: #dc2626; }
.btn-ghost { background: transparent; color: #64748b; }
.btn-ghost:hover { background: #f1f5f9; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes scaleIn { from { opacity: 0; transform: scale(.9); } to { opacity: 1; transform: scale(1); } }
</style>
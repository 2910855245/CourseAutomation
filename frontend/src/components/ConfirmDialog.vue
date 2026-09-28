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
  position: fixed; inset: 0; background: rgba(22, 22, 26, .42);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
  animation: fadeIn .2s cubic-bezier(.32,.72,.35,1);
}
.confirm-dialog {
  background: var(--c-surface); border: 1px solid var(--c-border-light); border-radius: 18px; padding: 32px 28px;
  width: 380px; max-width: 90vw; text-align: center;
  box-shadow: 0 8px 24px rgba(20,20,24,.09), 0 32px 80px rgba(20,20,24,.14);
  animation: scaleIn .3s cubic-bezier(.32,.72,.35,1);
}
.confirm-icon {
  width: 56px; height: 56px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  margin: 0 auto 16px;
}
.confirm-icon.danger { background: var(--c-danger-bg); color: var(--c-danger); }
.confirm-icon.warning { background: var(--c-warning-bg); color: var(--c-warning); }
.confirm-icon.info { background: var(--c-primary-bg); color: var(--c-primary); }
.confirm-dialog h3 {
  font-size: 17px; font-weight: 700; letter-spacing: -0.01em;
  margin-bottom: 8px; color: var(--c-text);
}
.confirm-dialog p {
  font-size: 13.5px; color: var(--c-text-secondary);
  line-height: 1.55; margin-bottom: 24px;
}
.confirm-actions { display: flex; justify-content: center; gap: 10px; }
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  padding: 9px 20px; border: none; border-radius: 10px; font-weight: 600;
  font-size: 13.5px; cursor: pointer;
  transition: background-color .2s cubic-bezier(.32,.72,.35,1),
              color .2s cubic-bezier(.32,.72,.35,1),
              transform .2s cubic-bezier(.32,.72,.35,1);
}
.btn:active { transform: scale(.97); }
.btn-primary { background: var(--c-primary); color: #fff; }
.btn-primary:hover { background: var(--c-primary-hover); }
.btn-danger { background: var(--c-danger); color: #fff; }
.btn-danger:hover { background: var(--c-danger-hover); }
.btn-ghost { background: transparent; color: var(--c-text-secondary); }
.btn-ghost:hover { background: var(--c-bg); color: var(--c-text); }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes scaleIn {
  from { opacity: 0; transform: scale(.92) translateY(8px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}
</style>
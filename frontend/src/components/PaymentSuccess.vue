<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  visible: boolean
  amount?: number
  subtitle?: string
  duration?: number
}>(), {
  amount: 0,
  subtitle: '',
  duration: 2500,
})

const emit = defineEmits<{ done: [] }>()

const show = ref(false)
const exiting = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

watch(() => props.visible, (v) => {
  if (v) {
    show.value = true
    exiting.value = false
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      exiting.value = true
      setTimeout(() => {
        show.value = false
        exiting.value = false
        emit('done')
      }, 350)
    }, props.duration)
  } else {
    show.value = false
    exiting.value = false
    if (timer) { clearTimeout(timer); timer = null }
  }
}, { immediate: true })

onUnmounted(() => { if (timer) clearTimeout(timer) })
</script>

<template>
  <Teleport to="body">
    <div v-if="show" :class="['ps-overlay', { 'ps-exiting': exiting }]">
      <div :class="['ps-card', { 'ps-exiting': exiting }]">
        <svg class="ps-icon" viewBox="0 0 52 52">
          <circle class="ps-circle" cx="26" cy="26" r="24" fill="none" stroke="#16a34a" stroke-width="2.5"/>
          <path class="ps-check" fill="none" stroke="#16a34a" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" d="M14 27l8 8 16-16"/>
        </svg>
        <h2 class="ps-title">
支付成功
</h2>
        <p v-if="amount != null" class="ps-amount">
&yen;{{ amount.toFixed(2) }}
</p>
        <p v-if="subtitle" class="ps-subtitle">
{{ subtitle }}
</p>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ps-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  animation: overlayIn 0.25s ease-out both;
}
.ps-overlay.ps-exiting {
  animation: overlayOut 0.35s ease-in both;
}

.ps-card {
  background: #fff;
  border-radius: 20px;
  padding: 40px 48px 36px;
  text-align: center;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  animation: cardIn 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) both;
  animation-delay: 0.1s;
  min-width: 240px;
}
.ps-card.ps-exiting {
  animation: cardOut 0.3s ease-in both;
}

.ps-icon {
  width: 72px;
  height: 72px;
  display: block;
  margin: 0 auto 16px;
}

.ps-circle {
  stroke-dasharray: 151;
  stroke-dashoffset: 151;
  animation: circleDraw 0.5s ease-out 0.2s both;
}

.ps-check {
  stroke-dasharray: 48;
  stroke-dashoffset: 48;
  animation: checkDraw 0.35s ease-out 0.6s both;
}

.ps-title {
  font-size: 20px;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0 0 8px;
  opacity: 0;
  animation: textIn 0.3s ease-out 0.85s both;
}

.ps-amount {
  font-size: 28px;
  font-weight: 700;
  color: #16a34a;
  margin: 0 0 6px;
  opacity: 0;
  animation: textIn 0.3s ease-out 0.95s both;
  font-variant-numeric: tabular-nums;
}

.ps-subtitle {
  font-size: 14px;
  color: #666;
  margin: 0;
  opacity: 0;
  animation: textIn 0.3s ease-out 1.05s both;
}

@keyframes overlayIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes overlayOut {
  from { opacity: 1; }
  to { opacity: 0; }
}
@keyframes cardIn {
  from { opacity: 0; transform: scale(0.5); }
  to { opacity: 1; transform: scale(1); }
}
@keyframes cardOut {
  from { opacity: 1; transform: scale(1); }
  to { opacity: 0; transform: scale(0.8); }
}
@keyframes circleDraw {
  to { stroke-dashoffset: 0; }
}
@keyframes checkDraw {
  to { stroke-dashoffset: 0; }
}
@keyframes textIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>

<script setup lang="ts">
/**
 * 全站悬浮「加群」入口：右下角常驻按钮，点开显示 QQ 群号（一键复制）与微信群二维码。
 *
 * 内容来自 /api/site/links（后台「系统通告」页配置）：
 *   - 两个渠道都没配置 → 整个组件不渲染（功能未启用，不占屏幕）
 *   - 拉取失败静默降级（悬浮入口的问题不该打扰正在下单的用户）
 * 后台路由（/admin）由 App.vue 侧判断不挂载本组件。
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '@/api'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const loaded = ref(false)
const open = ref(false)
const qqGroup = ref('')
const wechatQr = ref('')

const hasAny = computed(() => !!qqGroup.value || !!wechatQr.value)

onMounted(async () => {
  try {
    const r = await api.site.links()
    qqGroup.value = r?.data?.qq_group || ''
    wechatQr.value = r?.data?.wechat_qr || ''
  } catch { /* 静默降级：不显示入口 */ }
  finally { loaded.value = true }
})

async function copyQq() {
  const text = qqGroup.value.trim()
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    store.toast('QQ 群号已复制', 'success')
  } catch {
    store.toast('复制失败，请手动输入群号', 'warning')
  }
}
</script>

<template>
  <div
    v-if="loaded && hasAny"
    class="fc-root"
  >
    <Transition name="fc-pop">
      <div
        v-if="open"
        class="fc-panel"
      >
        <div class="fc-head">
          <span class="fc-title">加入交流群</span>
          <button
            class="fc-close"
            aria-label="关闭"
            @click="open = false"
          >
            &times;
          </button>
        </div>
        <div
          v-if="qqGroup"
          class="fc-section"
        >
          <div class="fc-label">
            QQ 群
          </div>
          <div class="fc-qq-row">
            <span class="fc-qq mono">{{ qqGroup }}</span>
            <button
              class="fc-copy"
              @click="copyQq"
            >
              复制
            </button>
          </div>
        </div>
        <div
          v-if="wechatQr"
          class="fc-section"
        >
          <div class="fc-label">
            微信群
          </div>
          <img
            :src="wechatQr"
            class="fc-qr"
            alt="微信群二维码"
          >
          <p class="fc-tip">
            长按二维码识别，或截图后用微信扫一扫
          </p>
        </div>
      </div>
    </Transition>
    <button
      class="fc-fab"
      :class="{ 'is-open': open }"
      aria-label="加入交流群"
      @click="open = !open"
    >
      <svg
        width="17"
        height="17"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.8"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
        <circle
          cx="9"
          cy="7"
          r="4"
        />
        <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
        <path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
      <span>加群</span>
    </button>
  </div>
</template>

<style scoped>
.fc-root {
  position: fixed;
  right: 22px;
  bottom: 22px;
  z-index: 90;
}

/* 悬浮按钮：胶囊形，主色底；hover 仅上浮 2px，不做花哨效果 */
.fc-fab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border: none;
  border-radius: 999px;
  background: var(--c-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow-primary-lg);
  transition: transform .25s cubic-bezier(.32, .72, .35, 1), box-shadow .25s ease;
}
.fc-fab:hover { transform: translateY(-2px); }
.fc-fab:active { transform: scale(.96); }
.fc-fab.is-open { box-shadow: var(--shadow-primary); }

/* 弹层：挂在按钮上方，右对齐 */
.fc-panel {
  position: absolute;
  right: 0;
  bottom: 54px;
  width: 242px;
  padding: 16px;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  box-shadow: var(--shadow-md);
}
.fc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.fc-title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--c-text);
}
.fc-close {
  border: none;
  background: none;
  padding: 0 2px;
  font-size: 18px;
  line-height: 1;
  color: var(--c-text-muted);
  cursor: pointer;
  transition: color .2s ease;
}
.fc-close:hover { color: var(--c-text); }

.fc-section + .fc-section { margin-top: 14px; }
.fc-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--c-text-secondary);
  margin-bottom: 6px;
}
.fc-qq-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--c-bg);
}
.fc-qq { font-size: 13.5px; color: var(--c-text); }
.fc-copy {
  border: none;
  background: none;
  color: var(--c-primary);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;
}
.fc-qr {
  width: 100%;
  display: block;
  border-radius: 10px;
  border: 1px solid var(--c-border-light);
}
.fc-tip {
  margin-top: 6px;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--c-text-muted);
  text-align: center;
}

.fc-pop-enter-active { transition: opacity .22s ease, transform .22s cubic-bezier(.32, .72, .35, 1); }
.fc-pop-leave-active { transition: opacity .16s ease, transform .16s ease; }
.fc-pop-enter-from,
.fc-pop-leave-to { opacity: 0; transform: translateY(8px) scale(.97); }

@media (max-width: 640px) {
  .fc-root { right: 14px; bottom: 14px; }
}
</style>
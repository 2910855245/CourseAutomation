<script setup lang="ts">
/**
 * 赞赏支持页：展示后台配置的赞赏码（图片）+ 一段文案。
 *
 * 数据来自 /api/site/links（公开接口，与悬浮「加群」按钮同一份数据：
 * site_donate_qr / site_donate_note）。未配置 → 显示"尚未开通"空态。
 *
 * 注意：赞赏码是静态收款码（扫码转账），与订单支付**无关**——转账不会
 * 自动入账到任何订单，也不影响刷课进度。页面上不承诺任何"付款权益"。
 */
import { onMounted, ref } from 'vue'
import { api } from '@/api'
import { useAppStore } from '@/stores/app'
import AppTopbar from '@/components/AppTopbar.vue'

const store = useAppStore()
const loading = ref(true)
const qr = ref('')
const note = ref('')

const DEFAULT_NOTE = '如果这个站点帮你省下了时间，欢迎请作者喝杯奶茶。'

onMounted(async () => {
  try {
    const r = await api.site.links()
    qr.value = r?.data?.donate_qr || ''
    note.value = r?.data?.donate_note || ''
  } catch {
    store.toast('加载失败，请稍后再试', 'error')
  } finally { loading.value = false }
})

function saveQr() {
  if (!qr.value) return
  // data URL（后台本地上传）可以直接触发下载；外链图跨域时 download 会被
  // 浏览器忽略，只能提示长按/右键保存
  if (qr.value.startsWith('data:')) {
    const a = document.createElement('a')
    a.href = qr.value
    a.download = '赞赏码.png'
    a.click()
  } else {
    store.toast('请长按图片保存，或右键另存为', 'info')
  }
}
</script>

<template>
  <div class="page">
    <AppTopbar title="Fuk 文理网课" />
    <main class="main">
      <section class="hero">
        <span class="eyebrow">赞赏支持</span>
        <h1 class="title">
          请作者喝杯奶茶
        </h1>
        <p class="sub">
          你的支持是这个站点持续更新与维护的动力。
        </p>
      </section>

      <div
        v-if="loading"
        class="card center"
      >
        <span class="muted">加载中…</span>
      </div>

      <div
        v-else-if="!qr"
        class="card center"
      >
        <p class="empty-title">
          赞赏通道尚未开通
        </p>
        <p class="empty-sub">
          感谢你的心意 —— 使用本站服务就是最大的支持。
        </p>
      </div>

      <div
        v-else
        class="card"
      >
        <p class="note">
          {{ note || DEFAULT_NOTE }}
        </p>
        <div class="qr-wrap">
          <img
            :src="qr"
            alt="赞赏码"
            class="qr-img"
          >
        </div>
        <p class="hint">
          使用微信扫一扫，或长按图片识别
        </p>
        <button
          class="btn btn-primary btn-block"
          @click="saveQr"
        >
          保存赞赏码
        </button>
      </div>
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.main {
  flex: 1;
  width: 100%;
  max-width: 480px;
  margin: 0 auto;
  padding: var(--space-6);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.hero { text-align: center; padding-top: var(--space-5); }
.eyebrow {
  display: inline-block;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--c-primary);
  margin-bottom: 8px;
}
.title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: var(--tracking-title);
  color: var(--c-text);
  margin-bottom: 8px;
}
.sub {
  font-size: 13.5px;
  color: var(--c-text-secondary);
  line-height: 1.6;
}

.card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 16px;
  padding: 26px 24px;
  box-shadow: var(--shadow-xs);
  text-align: center;
  animation: dn-in .35s cubic-bezier(.32, .72, .35, 1) both;
}
@keyframes dn-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
.center { display: flex; flex-direction: column; gap: 6px; align-items: center; }
.muted { color: var(--c-text-muted); font-size: 13.5px; }
.empty-title { font-size: 15px; font-weight: 600; color: var(--c-text); }
.empty-sub { font-size: 12.5px; color: var(--c-text-secondary); }

.note {
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--c-text-secondary);
  margin-bottom: 18px;
}

.qr-wrap {
  display: flex;
  justify-content: center;
  padding: 14px;
  border-radius: 14px;
  background: var(--c-bg);
  border: 1px solid var(--c-border-light);
  margin-bottom: 12px;
}
.qr-img {
  width: 232px;
  max-width: 100%;
  display: block;
  border-radius: 8px;
  background: #fff;
}
.hint {
  font-size: 12px;
  color: var(--c-text-muted);
  margin-bottom: 16px;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 11px 20px;
  border: none;
  border-radius: 10px;
  font-weight: 600;
  font-size: 13.5px;
  cursor: pointer;
  transition: transform .2s cubic-bezier(.32, .72, .35, 1), background .2s ease, box-shadow .2s ease;
}
.btn:hover { transform: translateY(-1px); }
.btn:active { transform: scale(.97); }
.btn-primary {
  background: var(--c-primary);
  color: #fff;
  box-shadow: var(--shadow-xs);
}
.btn-primary:hover { background: var(--c-primary-hover); }
.btn-block { width: 100%; }

@media (max-width: 640px) {
  .main { padding: var(--space-5) var(--space-4); }
}
</style>
<script setup lang="ts">
import { useAdminStore } from '@/stores/admin'
const { proxyForm, proxySaving, proxyTestOk, proxyTestResult, proxyTesting, saveProxy, serverPublicIp, testProxy } = useAdminStore().state().sysConfig
</script>

<template>
  <div class="proxy-tab">
    <div class="settings-card">
      <h3>隧道代理</h3>
      <p class="settings-hint">
        所有刷课请求走代理出口，防止服务器 IP 被目标平台封禁
      </p>

      <div class="proxy-toggle-row">
        <span class="proxy-toggle-label">启用代理</span>
        <label class="toggle-switch">
          <input
            v-model="proxyForm.enabled"
            type="checkbox"
          >
          <span class="toggle-slider" />
        </label>
      </div>

      <div class="field">
        <label>代理地址</label>
        <input
          v-model="proxyForm.url"
          type="text"
          placeholder="http://隧道地址:端口"
          :disabled="!proxyForm.enabled"
        >
      </div>
      <div class="field-row">
        <div class="field">
          <label>用户名（选填）</label>
          <input
            v-model="proxyForm.username"
            type="text"
            placeholder="代理认证用户名"
            :disabled="!proxyForm.enabled"
          >
        </div>
        <div class="field">
          <label>密码（选填）</label>
          <input
            v-model="proxyForm.password"
            type="password"
            placeholder="代理认证密码"
            :disabled="!proxyForm.enabled"
          >
        </div>
      </div>
      <div class="proxy-actions">
        <button
          class="btn btn-ghost"
          :disabled="proxyTesting || !proxyForm.enabled"
          @click="testProxy"
        >
          {{ proxyTesting ? '测试中...' : '测试连接' }}
        </button>
        <button
          class="btn btn-primary"
          :disabled="proxySaving"
          @click="saveProxy"
        >
          {{ proxySaving ? '保存中...' : '保存设置' }}
        </button>
      </div>
      <div
        v-if="proxyTestResult"
        class="proxy-test-result"
        :class="{ ok: proxyTestOk }"
      >
        {{ proxyTestResult }}
      </div>
    </div>

    <div class="settings-card">
      <details class="guide-details">
        <summary>使用教程</summary>
        <div class="proxy-guide">
          <div class="guide-step">
            <strong>1.</strong> 搜索"隧道代理"购买，推荐：芝麻代理、快代理、站大爷，月付 50-100 元。
          </div>
          <div class="guide-step">
            <strong>2.</strong> 获取代理地址，格式如 <code>http://user:pass@tunnel.provider.com:8888</code>，拆分填入上方。
          </div>
          <div class="guide-step">
            <strong>3.</strong> 在代理后台将服务器 IP <code class="code-warn">{{ serverPublicIp || '...' }}</code> 加白名单。
          </div>
          <div class="guide-step">
            <strong>4.</strong> 点击"测试连接"验证代理可用。
          </div>
          <div class="guide-step">
            <strong>5.</strong> 打开开关并保存，之后 worker 所有请求自动走代理。
          </div>
        </div>
      </details>
    </div>
  </div>
</template>

<style scoped>
.proxy-tab {
  width: 100%;
  max-width: 720px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.proxy-tab > * {
  animation: proxy-in .35s cubic-bezier(.32, .72, .35, 1) both;
}

.proxy-tab > *:nth-child(2) {
  animation-delay: .07s;
}

@keyframes proxy-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.settings-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 16px;
  padding: 26px 28px;
  box-shadow: var(--shadow-xs);
}

.settings-card h3 {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--c-text);
  margin-bottom: 6px;
}

.settings-hint {
  font-size: 12.5px;
  color: var(--c-text-muted);
  margin-bottom: 22px;
}

.btn {
  transition: all .2s cubic-bezier(.32, .72, .35, 1);
}

.btn:active:not(:disabled) {
  transform: scale(.97);
}

.proxy-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: var(--c-bg);
  border-radius: 12px;
  margin-bottom: 20px;
}

.proxy-toggle-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--c-text);
}

.field input:disabled {
  opacity: .5;
  cursor: not-allowed;
}

.proxy-actions {
  display: flex;
  gap: 10px;
  margin-top: 4px;
}

.proxy-test-result {
  margin-top: 14px;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 13px;
  background: var(--c-danger-bg);
  color: var(--c-danger);
  animation: proxy-in .25s cubic-bezier(.32, .72, .35, 1) both;
}

.proxy-test-result.ok {
  background: var(--c-success-bg);
  color: var(--c-success);
}

.guide-details summary {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--c-text);
  outline: none;
  cursor: pointer;
  transition: color .2s ease;
}

.guide-details summary:hover {
  color: var(--c-primary);
}

.proxy-guide {
  font-size: 13px;
  line-height: 1.9;
  color: var(--c-text-secondary);
  padding-top: 14px;
}

.guide-step {
  margin-bottom: 6px;
}

.guide-step code {
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  padding: 1px 6px;
  border-radius: 6px;
  font-size: 12px;
}

.code-warn {
  background: var(--c-danger-bg);
  color: var(--c-danger);
  border-color: transparent;
}

@media (max-width: 768px) {
  .proxy-tab {
    max-width: 100%;
  }

  .settings-card {
    padding: 18px;
  }

  .proxy-actions {
    flex-direction: column;
  }

  .proxy-actions .btn {
    width: 100%;
  }
}
</style>

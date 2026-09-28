<script setup lang="ts">
import { useAdminStore } from '@/stores/admin'
const { changeAdminPassword, changingPw, currentRole, pwForm } = useAdminStore().state().auth
const { DEEPSEEK_MODELS, chaoxingModel, clearDeepseekKey, deepseekApiKey, deepseekKeyMasked, deepseekTestResult, finalExamModel, homeworkModel, pricingModel, saveDeepseekKey, saveModels, savingDeepseekKey, savingModels, showDeepseekKey, testDeepseekApi, testModelApi, testingDeepseek, testingModel } = useAdminStore().state().sysConfig
</script>

<template>
  <div class="security-tab">
    <div
      v-if="currentRole === 'admin'"
      class="settings-card"
    >
      <h3>DeepSeek AI 配置</h3>

      <!-- API Key -->
      <div class="ai-section">
        <div class="ai-section-label">
          API Key
        </div>
        <div class="ai-row">
          <div class="ai-key-wrap">
            <span
              v-if="deepseekKeyMasked"
              class="ai-key-badge on"
            >已配置</span>
            <span
              v-else
              class="ai-key-badge off"
            >未配置</span>
            <span class="ai-key-val">{{ deepseekKeyMasked || 'sk-****' }}</span>
          </div>
          <div class="ai-key-input-group">
            <input
              v-model="deepseekApiKey"
              :type="showDeepseekKey ? 'text' : 'password'"
              placeholder="输入新 Key 覆盖..."
              autocomplete="off"
              class="ai-key-input"
            >
            <button
              class="btn btn-ghost btn-xs"
              type="button"
              @click="showDeepseekKey = !showDeepseekKey"
            >
              {{ showDeepseekKey ? '隐藏' : '显示' }}
            </button>
            <button
              class="btn btn-primary btn-sm"
              :disabled="savingDeepseekKey"
              @click="saveDeepseekKey"
            >
              {{ savingDeepseekKey ? '...' : '保存' }}
            </button>
            <button
              v-if="deepseekKeyMasked"
              class="btn btn-ghost btn-sm"
              :disabled="savingDeepseekKey"
              @click="clearDeepseekKey"
            >
              清除
            </button>
          </div>
        </div>
        <div class="ai-row-bottom">
          <a
            class="ai-link"
            href="https://platform.deepseek.com/"
            target="_blank"
            rel="noopener"
          >获取 Key</a>
          <button
            class="btn-link"
            :disabled="testingDeepseek"
            @click="testDeepseekApi"
          >
            {{ testingDeepseek ? '检测中...' : '一键检查' }}
          </button>
          <span
            v-if="deepseekTestResult"
            :class="deepseekTestResult.api_ok ? 'ai-status-ok' : 'ai-status-fail'"
          >
            {{ deepseekTestResult.api_ok ? `连通 (${deepseekTestResult.latency_ms}ms)` : deepseekTestResult.error || '连接失败' }}
          </span>
        </div>
      </div>

      <!-- 模型分配 -->
      <div class="ai-section">
        <div class="ai-section-label">
          模型分配
        </div>
        <div class="ai-model-grid">
          <div class="ai-model-card">
            <div class="ai-model-head">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              ><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" /></svg>
              期末考试
            </div>
            <select
              v-model="finalExamModel"
              class="ai-model-select"
            >
              <option
                v-for="m in DEEPSEEK_MODELS"
                :key="m.value"
                :value="m.value"
              >
                {{ m.label }}
              </option>
            </select>
            <div class="ai-model-foot">
              <span class="ai-model-desc">{{ DEEPSEEK_MODELS.find(m => m.value === finalExamModel)?.desc }}</span>
              <button
                class="btn-link"
                :disabled="testingModel === finalExamModel"
                @click="testModelApi(finalExamModel)"
              >
                {{ testingModel === finalExamModel ? '...' : '测试' }}
              </button>
            </div>
          </div>
          <div class="ai-model-card">
            <div class="ai-model-head">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              ><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" /></svg>
              平时作业
            </div>
            <select
              v-model="homeworkModel"
              class="ai-model-select"
            >
              <option
                v-for="m in DEEPSEEK_MODELS"
                :key="m.value"
                :value="m.value"
              >
                {{ m.label }}
              </option>
            </select>
            <div class="ai-model-foot">
              <span class="ai-model-desc">{{ DEEPSEEK_MODELS.find(m => m.value === homeworkModel)?.desc }}</span>
              <button
                class="btn-link"
                :disabled="testingModel === homeworkModel"
                @click="testModelApi(homeworkModel)"
              >
                {{ testingModel === homeworkModel ? '...' : '测试' }}
              </button>
            </div>
          </div>
          <div class="ai-model-card">
            <div class="ai-model-head">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 10.5V6a2 2 0 00-2-2H4a2 2 0 00-2 2v12a2 2 0 002 2h7"/><path d="M22 10.5L12 16l-3-1.7"/><path d="M12 16v5"/><path d="M22 10.5V12"/></svg>
              学习通
            </div>
            <select v-model="chaoxingModel" class="ai-model-select">
              <option v-for="m in DEEPSEEK_MODELS" :key="m.value" :value="m.value">
{{ m.label }}
</option>
            </select>
            <div class="ai-model-foot">
              <span class="ai-model-desc">{{ DEEPSEEK_MODELS.find(m => m.value === chaoxingModel)?.desc }}</span>
              <button class="btn-link" :disabled="testingModel === chaoxingModel" @click="testModelApi(chaoxingModel)">
{{ testingModel === chaoxingModel ? '...' : '测试' }}
</button>
            </div>
          </div>
          <div class="ai-model-card">
            <div class="ai-model-head">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              ><path d="M12 2a5 5 0 015 5v3H7V7a5 5 0 015-5z" /><rect
                x="3"
                y="10"
                width="18"
                height="12"
                rx="2"
              /><circle
                cx="12"
                cy="16"
                r="2"
              /></svg>
              定价顾问
            </div>
            <select
              v-model="pricingModel"
              class="ai-model-select"
            >
              <option
                v-for="m in DEEPSEEK_MODELS"
                :key="m.value"
                :value="m.value"
              >
                {{ m.label }}
              </option>
            </select>
            <div class="ai-model-foot">
              <span class="ai-model-desc">{{ DEEPSEEK_MODELS.find(m => m.value === pricingModel)?.desc }}</span>
              <button
                class="btn-link"
                :disabled="testingModel === pricingModel"
                @click="testModelApi(pricingModel)"
              >
                {{ testingModel === pricingModel ? '...' : '测试' }}
              </button>
            </div>
          </div>
        </div>
        <button
          class="btn btn-primary btn-sm"
          :disabled="savingModels"
          style="margin-top:12px"
          @click="saveModels"
        >
          {{ savingModels ? '保存中...' : '保存模型' }}
        </button>
      </div>
    </div>

    <div class="settings-card">
      <h3>修改管理员密码</h3>
      <p class="settings-hint">
        修改后需要重新登录
      </p>
      <div class="field">
        <label>原密码</label>
        <input
          v-model="pwForm.old_password"
          type="password"
          placeholder="输入当前密码"
          autocomplete="current-password"
        >
      </div>
      <div class="field">
        <label>新密码</label>
        <input
          v-model="pwForm.new_password"
          type="password"
          placeholder="至少6位"
          autocomplete="new-password"
        >
      </div>
      <div class="field">
        <label>确认新密码</label>
        <input
          v-model="pwForm.confirm_password"
          type="password"
          placeholder="再次输入新密码"
          autocomplete="new-password"
        >
      </div>
      <button
        class="btn btn-primary"
        :disabled="changingPw"
        @click="changeAdminPassword"
      >
        {{ changingPw ? '处理中...' : '修改密码' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.security-tab {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.security-tab > * {
  animation: security-in .35s cubic-bezier(.32, .72, .35, 1) both;
}

.security-tab > *:nth-child(2) { animation-delay: .07s; }
.security-tab > *:nth-child(3) { animation-delay: .14s; }

@keyframes security-in {
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
  margin-bottom: 18px;
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

.btn-link {
  transition: color .2s ease, opacity .2s ease;
}

.ai-section + .ai-section {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid var(--c-border);
}

.ai-section-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--c-text-muted);
  letter-spacing: .02em;
  margin-bottom: 10px;
}

.ai-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: var(--c-bg);
  border-radius: 12px;
}

.ai-key-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ai-key-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 9px;
  border-radius: 999px;
}

.ai-key-badge.on {
  background: var(--c-success-bg);
  color: var(--c-success);
}

.ai-key-badge.off {
  background: var(--c-danger-bg);
  color: var(--c-danger);
}

.ai-key-val {
  font-family: var(--font-mono, 'SF Mono', Menlo, monospace);
  font-size: 12.5px;
  color: var(--c-text-secondary);
}

.ai-key-input-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 240px;
}

.ai-key-input {
  flex: 1;
  min-width: 0;
}

.ai-row-bottom {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 12px;
  font-size: 13px;
}

.ai-link {
  color: var(--c-primary);
  text-decoration: none;
  transition: color .2s ease;
}

.ai-link:hover {
  color: var(--c-primary-hover, var(--c-primary));
  text-decoration: underline;
}

.ai-status-ok {
  color: var(--c-success);
  font-weight: 600;
}

.ai-status-fail {
  color: var(--c-danger);
}

.ai-model-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.ai-model-card {
  flex: 1 1 200px;
  min-width: 180px;
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: 14px 16px;
  transition: transform .25s cubic-bezier(.32, .72, .35, 1), box-shadow .25s cubic-bezier(.32, .72, .35, 1), border-color .2s ease;
}

.ai-model-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
  border-color: transparent;
}

.ai-model-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 700;
  color: var(--c-text);
  margin-bottom: 10px;
}

.ai-model-head svg {
  color: var(--c-primary);
  flex-shrink: 0;
}

.ai-model-select {
  width: 100%;
}

.ai-model-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
}

.ai-model-desc {
  font-size: 12px;
  color: var(--c-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 768px) {
  .settings-card {
    padding: 18px;
  }

  .ai-model-grid {
    flex-direction: column;
  }

  .ai-model-card {
    flex: none;
    width: 100%;
  }

  .ai-row-bottom {
    flex-wrap: wrap;
    gap: 8px 14px;
  }
}
</style>

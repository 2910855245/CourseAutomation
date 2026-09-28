<script setup lang="ts">
import { useAdminStore } from '@/stores/admin'
const { applyPackagePricing, applyingPackage, cancelEditPricing, editPricing, editingPricing, packagePricing, savePricingConfig, savingPricing } = useAdminStore().state().sysConfig
</script>

<template>
  <div class="pricing-tab">
    <!-- AI 定价顾问 -->
    <div class="settings-card ai-advisor-card">
      <div class="pricing-mode-header">
        <h3>
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            style="vertical-align: -3px; margin-right: 6px;"
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
          定价配置
        </h3>
      </div>

      <!-- 当前生效定价 -->
      <div
        class="pricing-section"
        style="margin-bottom:20px"
      >
        <div class="pricing-section-header">
          <span class="pricing-section-title">当前定价方案</span>
          <button
            v-if="!editingPricing"
            class="btn btn-xs btn-ghost"
            @click="editingPricing = true"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            ><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
            编辑
          </button>
          <div
            v-else
            class="pricing-edit-actions"
          >
            <button
              class="btn btn-xs btn-ghost"
              @click="cancelEditPricing"
            >
              取消
            </button>
            <button
              class="btn btn-xs btn-primary"
              :disabled="savingPricing"
              @click="savePricingConfig"
            >
              {{ savingPricing ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
        <div class="pkg-current-grid">
          <div class="pkg-card">
            <div class="pkg-card-label">
              小课 (≤30视频)
            </div>
            <div
              v-if="!editingPricing"
              class="pkg-card-price"
            >
              ¥{{ packagePricing.priceSmall }}
            </div>
            <div
              v-else
              class="pkg-card-input"
            >
              <span class="pkg-input-prefix">¥</span><input
                v-model.number="editPricing.priceSmall"
                type="number"
                min="0"
                step="0.5"
              >
            </div>
          </div>
          <div class="pkg-card">
            <div class="pkg-card-label">
              中课 (31-80视频)
            </div>
            <div
              v-if="!editingPricing"
              class="pkg-card-price"
            >
              ¥{{ packagePricing.priceMedium }}
            </div>
            <div
              v-else
              class="pkg-card-input"
            >
              <span class="pkg-input-prefix">¥</span><input
                v-model.number="editPricing.priceMedium"
                type="number"
                min="0"
                step="0.5"
              >
            </div>
          </div>
          <div class="pkg-card">
            <div class="pkg-card-label">
              大课 (>80视频)
            </div>
            <div
              v-if="!editingPricing"
              class="pkg-card-price"
            >
              ¥{{ packagePricing.priceLarge }}
            </div>
            <div
              v-else
              class="pkg-card-input"
            >
              <span class="pkg-input-prefix">¥</span><input
                v-model.number="editPricing.priceLarge"
                type="number"
                min="0"
                step="0.5"
              >
            </div>
          </div>
          <div class="pkg-card">
            <div class="pkg-card-label">
              纯考试
            </div>
            <div
              v-if="!editingPricing"
              class="pkg-card-price"
            >
              ¥{{ packagePricing.priceExamOnly }}
            </div>
            <div
              v-else
              class="pkg-card-input"
            >
              <span class="pkg-input-prefix">¥</span><input
                v-model.number="editPricing.priceExamOnly"
                type="number"
                min="0"
                step="0.5"
              >
            </div>
          </div>
          <div class="pkg-card">
            <div class="pkg-card-label">
              纯作业
            </div>
            <div
              v-if="!editingPricing"
              class="pkg-card-price"
            >
              ¥{{ packagePricing.priceHomeworkOnly }}
            </div>
            <div
              v-else
              class="pkg-card-input"
            >
              <span class="pkg-input-prefix">¥</span><input
                v-model.number="editPricing.priceHomeworkOnly"
                type="number"
                min="0"
                step="0.5"
              >
            </div>
          </div>
          <div class="pkg-card">
            <div class="pkg-card-label">
              学习通（积分+作业）
            </div>
            <div
              v-if="!editingPricing"
              class="pkg-card-price"
            >
              ¥{{ packagePricing.priceChaoxing }}
            </div>
            <div
              v-else
              class="pkg-card-input"
            >
              <span class="pkg-input-prefix">¥</span><input
                v-model.number="editPricing.priceChaoxing"
                type="number"
                min="0"
                step="0.5"
              >
            </div>
          </div>
        </div>
        <div class="pkg-discount-row">
          <span
            v-if="!editingPricing"
            class="pkg-discount-tag"
          >25-50%进度: ×{{ packagePricing.discount25 }}</span>
          <span
            v-if="!editingPricing"
            class="pkg-discount-tag"
          >50-75%进度: ×{{ packagePricing.discount50 }}</span>
          <span
            v-if="!editingPricing"
            class="pkg-discount-tag"
          >>75%进度: ×{{ packagePricing.discount75 }}</span>
          <span
            v-if="!editingPricing"
            class="pkg-discount-tag"
          >最低: ¥{{ packagePricing.priceMinimum }}</span>
          <template v-else>
            <span class="pkg-discount-edit"><span class="pkg-disc-label">25-50%:</span><input
              v-model.number="editPricing.discount25"
              type="number"
              min="0"
              max="1"
              step="0.05"
            ></span>
            <span class="pkg-discount-edit"><span class="pkg-disc-label">50-75%:</span><input
              v-model.number="editPricing.discount50"
              type="number"
              min="0"
              max="1"
              step="0.05"
            ></span>
            <span class="pkg-discount-edit"><span class="pkg-disc-label">>75%:</span><input
              v-model.number="editPricing.discount75"
              type="number"
              min="0"
              max="1"
              step="0.05"
            ></span>
            <span class="pkg-discount-edit"><span class="pkg-disc-label">最低:</span><span class="pkg-input-prefix">¥</span><input
              v-model.number="editPricing.priceMinimum"
              type="number"
              min="0"
              step="0.5"
            ></span>
          </template>
        </div>
      </div>

        <!-- 一键应用 -->
        <button
          class="btn btn-success btn-lg btn-block"
          :disabled="applyingPackage"
          style="margin-top: 16px;"
          @click="applyPackagePricing"
        >
          {{ applyingPackage ? '应用中...' : '一键应用此方案' }}
        </button>
    </div>
  </div>
</template>

<style scoped>
.pricing-tab {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.pricing-tab > * {
  animation: pricing-in .35s cubic-bezier(.32, .72, .35, 1) both;
}

@keyframes pricing-in {
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

.btn {
  transition: all .2s cubic-bezier(.32, .72, .35, 1);
}

.btn:active:not(:disabled) {
  transform: scale(.97);
}

.pricing-mode-header h3 {
  display: flex;
  align-items: center;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--c-text);
  margin-bottom: 20px;
}

.pricing-mode-header svg {
  color: var(--c-primary);
}

.pricing-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 14px;
}

.pricing-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--c-text-muted);
  letter-spacing: .02em;
}

.pricing-edit-actions {
  display: flex;
  gap: 8px;
}

.pkg-current-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.pkg-current-grid .pkg-card {
  animation: pricing-in .35s cubic-bezier(.32, .72, .35, 1) both;
}

.pkg-current-grid .pkg-card:nth-child(2) { animation-delay: .04s; }
.pkg-current-grid .pkg-card:nth-child(3) { animation-delay: .08s; }
.pkg-current-grid .pkg-card:nth-child(4) { animation-delay: .12s; }
.pkg-current-grid .pkg-card:nth-child(5) { animation-delay: .16s; }
.pkg-current-grid .pkg-card:nth-child(6) { animation-delay: .20s; }

.pkg-card {
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: 16px 18px;
  transition: transform .25s cubic-bezier(.32, .72, .35, 1), box-shadow .25s cubic-bezier(.32, .72, .35, 1), border-color .2s ease;
}

.pkg-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
  border-color: transparent;
}

.pkg-card-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--c-text-muted);
  margin-bottom: 6px;
}

.pkg-card-price {
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--c-text);
  font-variant-numeric: tabular-nums;
}

.pkg-card-input {
  display: flex;
  align-items: center;
  gap: 4px;
}

.pkg-input-prefix {
  font-size: 14px;
  font-weight: 600;
  color: var(--c-text-muted);
}

.pkg-card-input input,
.pkg-discount-edit input {
  width: 90px;
  padding: 6px 10px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  background: var(--c-surface);
  color: var(--c-text);
  font-size: 14px;
  font-weight: 600;
  outline: none;
  transition: border-color .2s ease, box-shadow .2s ease;
}

.pkg-card-input input:focus,
.pkg-discount-edit input:focus {
  border-color: var(--c-primary);
  box-shadow: 0 0 0 3px var(--c-primary-soft, rgba(0, 113, 227, .12));
}

.pkg-discount-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.pkg-discount-tag {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--c-text-secondary);
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  padding: 5px 12px;
  border-radius: 999px;
}

.pkg-discount-edit {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  padding: 5px 12px;
  border-radius: 10px;
}

.pkg-disc-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--c-text-muted);
}

.pkg-discount-edit input {
  width: 70px;
}

@media (max-width: 768px) {
  .settings-card {
    padding: 18px;
  }

  .pkg-current-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .pkg-card-price {
    font-size: 20px;
  }
}

@media (max-width: 480px) {
  .pkg-card {
    padding: 12px 14px;
  }

  .pkg-card-price {
    font-size: 18px;
  }
}
</style>

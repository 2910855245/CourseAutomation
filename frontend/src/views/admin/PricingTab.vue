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
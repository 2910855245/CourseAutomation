<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useSetupWizard } from '@/composables/useSetupWizard'
import { useSetupSteps } from '@/composables/useSetupSteps'

const wizard = useSetupWizard()
const { totalSteps, currentStep, loading, error, success, completedSteps, maxReachedStep, steps,
  goStep, nextStep, prevStep, markDone, setExtraSave, debouncedSave, restoreDraft, clearDraft, cleanup: cleanupWizard,
} = wizard

const stepsCtrl = useSetupSteps({
  currentStep, loading, error, success, completedSteps, markDone, nextStep, debouncedSave, setExtraSave, clearDraft,
})
const {
  envChecks, envAllOk, envChecking,
  dbUser, dbPassword, dbName, dbTesting, dbTested, dbSaved,
  adminUser, adminPass, adminPassConfirm, adminCreated,
  ypayKey, ypaySaved,
  videoPrice, examPrice, pricingSaved,
  appQrImage, appDownloadUrl, appPairData, appLoading, appPaired,
  aiKey, aiKeySaved, aiKeyShow, aiKeySaving,
  restoreStepsDraft,
  runEnvCheck, testDbConnection, testAndSaveDb, saveDbConfig, initDatabase,
  createAdmin, saveYpay, savePricing, saveAiKey, skipAiKey,
  loadAppPairQr, finishSetup, generateYpayKey, cleanup: cleanupSteps,
} = stepsCtrl

const welcomeFeatures = [
  { icon: 'platform', title: '多平台自动发现', desc: '自动检测学校关联的所有课程平台' },
  { icon: 'engine', title: '智能刷课引擎', desc: '自动完成视频 + 考试，AI 答题' },
  { icon: 'pay', title: '自建支付系统', desc: '微信/支付宝扫码，YPay-App监控实时到账' },
  { icon: 'agent', title: '代理分销系统', desc: '多级代理、自动佣金结算' },
  { icon: 'chart', title: '数据仪表盘', desc: '营收、订单、代理数据一目了然' },
  { icon: 'server', title: '独立子站', desc: '每个代理拥有专属下单页面' },
]

const guides = [
  { title: '登录管理后台', desc: '用管理员账号登录后台查看数据' },
  { title: '风险监控', desc: '查看平台健康、加密参数变化、接口状态' },
  { title: '配置完整参数', desc: '设置佣金比例、提现规则、代理配置' },
  { title: '开始接单', desc: '输入学号密码检测课程提交订单' },
]

function doRestoreDraft() {
  const d = restoreDraft()
  if (d) restoreStepsDraft(d)
}

onMounted(async () => {
  const params = new URLSearchParams(window.location.search)
  if (params.has('reset')) {
    localStorage.removeItem('setup_draft')
    window.history.replaceState({}, '', window.location.pathname)
  }
  const savedToken = localStorage.getItem('admin_token')
  if (savedToken) {
    const { setAdminApiToken } = await import('@/api')
    setAdminApiToken(savedToken)
  }
  doRestoreDraft()
  runEnvCheck()
  if (!ypayKey.value) ypayKey.value = generateYpayKey()
})

onUnmounted(() => {
  cleanupSteps()
  cleanupWizard()
})
</script>

<template>
  <div class="setup-root">
    <div class="setup-bg">
      <div class="bg-orb bg-orb-1" />
      <div class="bg-orb bg-orb-2" />
      <div class="bg-orb bg-orb-3" />
      <div
        v-for="i in 10"
        :key="i"
        class="bg-particle"
        :style="{ '--i': i }"
      />
    </div>

    <div class="setup-card">
      <div class="card-header">
        <div class="card-header-row">
          <div class="card-brand">
            <span class="brand-badge">v6.0</span>
            <span class="brand-title">安装向导</span>
          </div>
          <div class="card-meta">
            <span class="meta-step">{{ currentStep }} / {{ totalSteps }}</span>
            <span class="meta-label">{{ steps[currentStep - 1]?.title }}</span>
          </div>
        </div>
        <div class="card-track">
          <div
            class="card-fill"
            :style="{ width: ((currentStep - 1) / (totalSteps - 1) * 100) + '%' }"
          />
        </div>
      </div>

      <div class="card-body">
        <div
          :key="currentStep"
          class="step-anim-wrap"
        >
          <div
            v-if="currentStep === 1"
            class="step-panel"
          >
            <div class="welcome-hero">
              <div class="welcome-logo">
                <div class="logo-ring" />
                <div class="logo-ring logo-ring-2" />
                <div class="logo-core">
                  <svg
                    width="34"
                    height="34"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" /></svg>
                </div>
              </div>
              <h1 class="welcome-title">
                在线课程自动化平台
              </h1>
              <p class="welcome-desc">
                智能高效 · 一站搞定
              </p>
            </div>

            <div class="feature-list">
              <div
                v-for="(f, idx) in welcomeFeatures"
                :key="idx"
                class="feature-row"
                :style="{ '--delay': idx * 0.06 + 0.1 + 's' }"
              >
                <div class="fr-icon">
                  <svg
                    v-if="f.icon === 'platform'"
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><rect
                    x="2"
                    y="3"
                    width="20"
                    height="14"
                    rx="2"
                  /><line
                    x1="8"
                    y1="21"
                    x2="16"
                    y2="21"
                  /><line
                    x1="12"
                    y1="17"
                    x2="12"
                    y2="21"
                  /></svg>
                  <svg
                    v-else-if="f.icon === 'engine'"
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><path d="M12 2a4 4 0 0 1 4 4c0 1.95-1.4 3.58-3.25 3.93" /><path d="M8.56 9.8A4 4 0 1 1 15.4 12" /><circle
                    cx="12"
                    cy="12"
                    r="1"
                  /><path d="M12 16v4" /><path d="M8 20h8" /></svg>
                  <svg
                    v-else-if="f.icon === 'pay'"
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><rect
                    x="1"
                    y="4"
                    width="22"
                    height="16"
                    rx="2"
                  /><line
                    x1="1"
                    y1="10"
                    x2="23"
                    y2="10"
                  /></svg>
                  <svg
                    v-else-if="f.icon === 'agent'"
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle
                    cx="9"
                    cy="7"
                    r="4"
                  /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></svg>
                  <svg
                    v-else-if="f.icon === 'chart'"
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><line
                    x1="18"
                    y1="20"
                    x2="18"
                    y2="10"
                  /><line
                    x1="12"
                    y1="20"
                    x2="12"
                    y2="4"
                  /><line
                    x1="6"
                    y1="20"
                    x2="6"
                    y2="14"
                  /></svg>
                  <svg
                    v-else-if="f.icon === 'server'"
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><rect
                    x="2"
                    y="2"
                    width="20"
                    height="8"
                    rx="2"
                  /><rect
                    x="2"
                    y="14"
                    width="20"
                    height="8"
                    rx="2"
                  /><line
                    x1="6"
                    y1="6"
                    x2="6.01"
                    y2="6"
                  /><line
                    x1="6"
                    y1="18"
                    x2="6.01"
                    y2="18"
                  /></svg>
                </div>
                <div class="fr-content">
                  <strong>{{ f.title }}</strong>
                  <span>{{ f.desc }}</span>
                </div>
              </div>
            </div>

            <button
              class="btn-primary btn-xl btn-full"
              @click="markDone(1); nextStep()"
            >
              开始安装
            </button>
          </div>

          <div
            v-if="currentStep === 2"
            class="step-panel"
          >
            <div class="step-head">
              <h2>系统环境检测</h2>
              <p>自动检查运行环境是否满足要求</p>
            </div>
            <div
              v-if="envChecking"
              class="loading-state"
            >
              <div class="spinner" />
              <span>正在检测环境...</span>
            </div>
            <div
              v-else
              class="env-results"
            >
              <div
                v-for="cat in envChecks"
                :key="cat.category"
                class="env-category"
              >
                <h4>{{ cat.category }}</h4>
                <div
                  v-for="item in cat.items"
                  :key="item.name"
                  :class="['env-row', item.status]"
                >
                  <span
                    class="env-icon"
                    :class="item.status"
                  >
                    <svg
                      v-if="item.status === 'ok'"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2.5"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    ><path d="M5 12l5 5L20 7" /></svg>
                    <svg
                      v-else-if="item.status === 'warn'"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2.5"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    ><path d="M12 9v4" /><circle
                      cx="12"
                      cy="17"
                      r="0.5"
                    /></svg>
                    <svg
                      v-else
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2.5"
                      stroke-linecap="round"
                      stroke-linejoin="round"
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
                  </span>
                  <span class="env-name">{{ item.name }}</span>
                  <span class="env-msg">{{ item.msg }}</span>
                </div>
              </div>
            </div>
            <div
              v-if="error"
              class="msg-error"
            >
              {{ error }}
            </div>
            <div class="step-actions">
              <button
                class="btn-ghost"
                :disabled="envChecking"
                @click="runEnvCheck"
              >
                重新检测
              </button>
              <button
                class="btn-primary btn-lg"
                @click="markDone(2); nextStep()"
              >
                下一步
              </button>
            </div>
          </div>

          <div
            v-if="currentStep === 3"
            class="step-panel"
          >
            <div class="step-head">
              <h2>配置 MySQL 数据库</h2>
              <p>连接宝塔面板创建的 MySQL 数据库</p>
            </div>
            <div class="form-stack">
              <div class="form-grid-2">
                <div class="form-group">
                  <label>数据库用户名</label>
                  <input
                    v-model="dbUser"
                    class="form-input"
                    placeholder="root"
                  >
                </div>
                <div class="form-group">
                  <label>数据库密码</label>
                  <input
                    v-model="dbPassword"
                    type="password"
                    class="form-input"
                    placeholder="请输入密码"
                  >
                </div>
              </div>
              <div class="form-group">
                <label>数据库名</label>
                <input
                  v-model="dbName"
                  class="form-input"
                  placeholder="anticheat"
                >
                <span class="form-hint">在宝塔面板「数据库」中创建的数据库名</span>
              </div>
            </div>
            <div
              v-if="error"
              class="msg-error"
            >
              {{ error }}
            </div>
            <div
              v-if="success"
              class="msg-success"
            >
              {{ success }}
            </div>
            <div class="step-actions">
              <button
                class="btn-ghost"
                @click="prevStep()"
              >
                上一步
              </button>
              <button
                v-if="completedSteps.has(3)"
                class="btn-primary btn-lg"
                @click="nextStep()"
              >
                下一步
              </button>
              <button
                v-else
                class="btn-primary btn-lg"
                :disabled="loading"
                @click="testAndSaveDb"
              >
                <template v-if="!loading">
                  保存并继续
                </template>
                <template v-else>
                  <span class="btn-spinner" /> 连接中
                </template>
              </button>
            </div>
          </div>

          <div
            v-if="currentStep === 4"
            class="step-panel"
          >
            <div class="step-head">
              <h2>创建管理员账号</h2>
              <p>此账号用于登录管理后台</p>
            </div>
            <div class="form-stack">
              <div class="form-group">
                <label>用户名</label>
                <input
                  v-model="adminUser"
                  class="form-input"
                  placeholder="admin"
                >
              </div>
              <div class="form-grid-2">
                <div class="form-group">
                  <label>密码</label>
                  <input
                    v-model="adminPass"
                    type="password"
                    class="form-input"
                    placeholder="请输入密码"
                  >
                </div>
                <div class="form-group">
                  <label>确认密码</label>
                  <input
                    v-model="adminPassConfirm"
                    type="password"
                    class="form-input"
                    placeholder="再次输入"
                    @keyup.enter="createAdmin"
                  >
                </div>
              </div>
            </div>
            <div
              v-if="error"
              class="msg-error"
            >
              {{ error }}
            </div>
            <div
              v-if="success"
              class="msg-success"
            >
              {{ success }}
            </div>
            <div class="step-actions">
              <button
                class="btn-ghost"
                @click="prevStep()"
              >
                上一步
              </button>
              <button
                v-if="completedSteps.has(4)"
                class="btn-primary btn-lg"
                @click="nextStep()"
              >
                下一步
              </button>
              <button
                v-else
                class="btn-primary btn-lg"
                :disabled="loading"
                @click="createAdmin"
              >
                <template v-if="!loading">
                  创建并继续
                </template>
                <template v-else>
                  <span class="btn-spinner" /> 创建中
                </template>
              </button>
            </div>
          </div>

          <div
            v-if="currentStep === 5"
            class="step-panel"
          >
            <div class="step-head">
              <h2>配置支付系统</h2>
              <p>YPay自建支付 — 安装手机 APP 监控收款，扫码自动配对</p>
            </div>

            <div class="ypay-setup-cards">
              <div class="ypay-setup-card">
                <div class="ypay-setup-card-hd">
                  <span class="ypay-setup-badge">APP 下载</span>
                </div>
                <div class="qr-frame">
                  <img
                    :src="'/api/app/download-qr'"
                    alt="扫码下载APP"
                  >
                </div>
                <a
                  href="/api/app/download"
                  class="dl-link"
                >电脑下载 APK</a>
              </div>

              <div class="ypay-setup-card">
                <div class="ypay-setup-card-hd">
                  <span class="ypay-setup-badge">扫码配对</span>
                </div>
                <div
                  v-if="appQrImage"
                  class="qr-frame"
                >
                  <img
                    :src="appQrImage"
                    alt="配对二维码"
                  >
                </div>
                <div
                  v-else-if="appLoading"
                  class="qr-loading"
                >
                  <div class="spinner-sm" />
                  <span>正在生成配对码…</span>
                </div>
                <div
                  v-else
                  class="qr-empty"
                >
                  <span>配对码生成失败</span>
                  <button
                    class="btn-ghost btn-sm"
                    @click="loadAppPairQr"
                  >
                    重试
                  </button>
                </div>
                <p class="tut-note-small">
                  打开YPay-App → 扫码配对 → 扫描此二维码
                </p>
                <div
                  v-if="appPaired"
                  class="pair-status-ok"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#22c55e"
                    stroke-width="2.5"
                  ><path d="M5 12l5 5L20 7" /></svg>
                  APP已连接
                </div>
                <div
                  v-else-if="appQrImage"
                  class="pair-status-wait"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#f59e0b"
                    stroke-width="2.5"
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
                  等待APP扫码连接...（3秒检测一次）
                </div>
              </div>

              <div class="ypay-setup-card">
                <div class="ypay-setup-card-hd">
                  <span class="ypay-setup-badge">APP 设置</span>
                </div>
                <div class="tut-checklist">
                  <div class="tut-check">
                    <span class="tc-icon">✓</span>授予通知监听权限
                  </div>
                  <div class="tut-check">
                    <span class="tc-icon">✓</span>开启后台保活服务
                  </div>
                  <div class="tut-check">
                    <span class="tc-icon">✓</span>保持 APP 后台运行
                  </div>
                </div>
                <p class="tut-note">
                  APP 需保持后台运行才能自动监控到账
                </p>
              </div>
            </div>

            <div
              class="form-section"
              style="margin-top:16px;"
            >
              <div class="form-group">
                <label>通信密钥 <span style="color:#6b7280;font-size:12px;">（自动生成，不可修改）</span></label>
                <input
                  :value="ypayKey"
                  class="form-input"
                  readonly
                  style="background:#f8f9fa;cursor:default;"
                >
              </div>
              <p
                class="tut-note-small"
                style="margin-top:4px;"
              >
                <svg
                  style="display:inline;vertical-align:middle;margin-right:4px;"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#f59e0b"
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
                收款二维码可在安装完成后到 <b>管理后台 → YPay支付</b> 中添加
              </p>
            </div>

            <div
              v-if="success"
              class="msg-success"
            >
              {{ success }}
            </div>
            <div
              v-if="error"
              class="msg-error"
            >
              {{ error }}
            </div>
            <div class="step-actions">
              <button
                class="btn-ghost"
                @click="prevStep()"
              >
                上一步
              </button>
              <button
                v-if="completedSteps.has(5)"
                class="btn-primary btn-lg"
                @click="nextStep()"
              >
                下一步
              </button>
              <div
                v-else
                class="action-group"
              >
                <button
                  class="btn-ghost"
                  @click="markDone(5); nextStep()"
                >
                  暂不配置
                </button>
                <button
                  class="btn-primary btn-lg"
                  :disabled="loading"
                  @click="saveYpay"
                >
                  <template v-if="!loading">
                    保存并继续
                  </template>
                  <template v-else>
                    <span class="btn-spinner" /> 保存中
                  </template>
                </button>
              </div>
            </div>
          </div>

          <div
            v-if="currentStep === 6"
            class="step-panel"
          >
            <div class="step-head">
              <h2>设置收费标准</h2>
              <p>设定视频和考试单价，后续可调整</p>
            </div>
            <div class="pricing-grid">
              <div class="pricing-card">
                <h3>视频单价</h3>
                <p>每完成一个视频</p>
                <div class="price-input">
                  <span class="price-sym">¥</span><input
                    v-model="videoPrice"
                    type="number"
                    step="0.01"
                    min="0.01"
                  >
                </div>
                <span class="price-hint">50个视频 × ¥0.10 = ¥5.00</span>
              </div>
              <div class="pricing-card">
                <h3>考试单价</h3>
                <p>每完成一个考试</p>
                <div class="price-input">
                  <span class="price-sym">¥</span><input
                    v-model="examPrice"
                    type="number"
                    step="0.01"
                    min="0.01"
                  >
                </div>
                <span class="price-hint">3个考试 × ¥0.15 = ¥0.45</span>
              </div>
            </div>
            <div
              v-if="error"
              class="msg-error"
            >
              {{ error }}
            </div>
            <div class="step-actions">
              <button
                class="btn-ghost"
                @click="prevStep()"
              >
                上一步
              </button>
              <button
                v-if="completedSteps.has(6)"
                class="btn-primary btn-lg"
                @click="nextStep()"
              >
                下一步
              </button>
              <button
                v-else
                class="btn-primary btn-lg"
                :disabled="loading"
                @click="savePricing"
              >
                <template v-if="!loading">
                  保存并继续
                </template>
                <template v-else>
                  <span class="btn-spinner" /> 保存中
                </template>
              </button>
            </div>
          </div>

          <div
            v-if="currentStep === 7"
            class="step-panel"
          >
            <div class="step-head">
              <h2>AI 答题配置</h2>
              <p>配置 DeepSeek API Key，AI 将自动完成考试答题（可跳过）</p>
            </div>
            <div
              class="pricing-grid"
              style="max-width:480px;margin:0 auto"
            >
              <div
                class="pricing-card"
                style="grid-column:1/-1"
              >
                <h3>DeepSeek API Key</h3>
                <p>用于 AI 自动答题，需要 DeepSeek 账号</p>
                <div style="display:flex;gap:8px;margin-top:12px">
                  <input
                    v-model="aiKey"
                    :type="aiKeyShow ? 'text' : 'password'"
                    placeholder="sk-..."
                    style="flex:1;height:44px;border:1px solid #e2e8f0;border-radius:8px;padding:0 14px;font-family:monospace;font-size:13px"
                  >
                  <button
                    class="btn-ghost"
                    style="min-width:56px"
                    type="button"
                    @click="aiKeyShow = !aiKeyShow"
                  >
                    {{ aiKeyShow ? '隐藏' : '显示' }}
                  </button>
                </div>
                <p style="font-size:12px;color:#94a3b8;margin-top:10px">
                  获取：<a
                    href="https://platform.deepseek.com/"
                    target="_blank"
                    rel="noopener"
                    style="color:#4f6ef7;text-decoration:none"
                  >platform.deepseek.com</a>
                  &nbsp;·&nbsp; 不配置则考试需手动完成
                </p>
              </div>
            </div>
            <div
              v-if="error"
              class="msg-error"
            >
              {{ error }}
            </div>
            <div class="step-actions">
              <button
                class="btn-ghost"
                @click="prevStep()"
              >
                上一步
              </button>
              <div style="display:flex;gap:10px">
                <button
                  class="btn-ghost"
                  @click="skipAiKey"
                >
                  跳过
                </button>
                <button
                  v-if="completedSteps.has(7)"
                  class="btn-primary btn-lg"
                  @click="nextStep()"
                >
                  下一步
                </button>
                <button
                  v-else
                  class="btn-primary btn-lg"
                  :disabled="aiKeySaving"
                  @click="saveAiKey"
                >
                  <template v-if="!aiKeySaving">
                    保存并继续
                  </template>
                  <template v-else>
                    <span class="btn-spinner" /> 保存中
                  </template>
                </button>
              </div>
            </div>
          </div>

          <div
            v-if="currentStep === 8"
            class="step-panel"
          >
            <div class="step-hero">
              <div class="finish-checkmark">
                <svg
                  width="48"
                  height="48"
                  viewBox="0 0 48 48"
                  fill="none"
                ><circle
                  cx="24"
                  cy="24"
                  r="22"
                  stroke="url(#cg)"
                  stroke-width="3"
                /><path
                  d="M14 24l7 7 13-13"
                  stroke="url(#cg)"
                  stroke-width="3"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                /><defs><linearGradient
                  id="cg"
                  x1="0"
                  y1="0"
                  x2="48"
                  y2="48"
                ><stop stop-color="#4f6ef7" /><stop
                  offset="1"
                  stop-color="#22c55e"
                /></linearGradient></defs></svg>
              </div>
              <h1><span class="gradient-text">安装完成</span></h1>
              <p class="hero-sub">
                平台已就绪，以下是快速入门指南
              </p>
            </div>

            <div class="finish-checklist">
              <div
                class="ck-item"
                :class="{ ok: envAllOk }"
              >
                <span
                  class="ck-icon"
                  :class="envAllOk ? 'ok' : 'warn'"
                >
                  <svg
                    v-if="envAllOk"
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><path d="M5 12l5 5L20 7" /></svg>
                  <svg
                    v-else
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><path d="M12 9v4" /><circle
                    cx="12"
                    cy="17"
                    r="0.5"
                  /></svg>
                </span><span>系统环境检测</span>
              </div>
              <div class="ck-item ok">
                <span class="ck-icon ok"><svg
                  width="15"
                  height="15"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                ><path d="M5 12l5 5L20 7" /></svg></span><span>数据库初始化</span>
              </div>
              <div
                class="ck-item"
                :class="{ ok: adminCreated || adminPass }"
              >
                <span
                  class="ck-icon"
                  :class="adminCreated || adminPass ? 'ok' : 'warn'"
                >
                  <svg
                    v-if="adminCreated || adminPass"
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><path d="M5 12l5 5L20 7" /></svg>
                  <svg
                    v-else
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><path d="M12 9v4" /><circle
                    cx="12"
                    cy="17"
                    r="0.5"
                  /></svg>
                </span><span>管理员 : <code>{{ adminUser || 'admin' }}</code></span>
              </div>
              <div
                class="ck-item"
                :class="{ ok: ypaySaved || ypayKey }"
              >
                <span
                  class="ck-icon"
                  :class="ypaySaved || ypayKey ? 'ok' : 'warn'"
                >
                  <svg
                    v-if="ypaySaved || ypayKey"
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><path d="M5 12l5 5L20 7" /></svg>
                  <svg
                    v-else
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><path d="M12 9v4" /><circle
                    cx="12"
                    cy="17"
                    r="0.5"
                  /></svg>
                </span><span>YPay {{ ypaySaved ? '已配置' : '未配置' }}</span>
              </div>
              <div
                class="ck-item"
                :class="{ ok: pricingSaved }"
              >
                <span
                  class="ck-icon"
                  :class="pricingSaved ? 'ok' : 'warn'"
                >
                  <svg
                    v-if="pricingSaved"
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><path d="M5 12l5 5L20 7" /></svg>
                  <svg
                    v-else
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><path d="M12 9v4" /><circle
                    cx="12"
                    cy="17"
                    r="0.5"
                  /></svg>
                </span><span>定价 视频¥{{ videoPrice }} / 考试¥{{ examPrice }}</span>
              </div>
              <div
                class="ck-item"
                :class="{ ok: aiKeySaved }"
              >
                <span
                  class="ck-icon"
                  :class="aiKeySaved ? 'ok' : 'warn'"
                >
                  <svg
                    v-if="aiKeySaved"
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><path d="M5 12l5 5L20 7" /></svg>
                  <svg
                    v-else
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><path d="M12 9v4" /><circle
                    cx="12"
                    cy="17"
                    r="0.5"
                  /></svg>
                </span><span>AI 答题 {{ aiKeySaved ? '已配置' : '未配置' }}</span>
              </div>
              <div class="ck-item ok">
                <span class="ck-icon ok"><svg
                  width="15"
                  height="15"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                ><path d="M5 12l5 5L20 7" /></svg></span><span>平台健康监控 · Scrapling 自适应爬虫 · 代理轮换</span>
              </div>
            </div>

            <div class="guide-section">
              <h3>下一步做什么？</h3>
              <div class="guide-grid">
                <div
                  v-for="(g, idx) in guides"
                  :key="idx"
                  class="guide-card"
                  :style="{ '--delay': idx * 0.08 + 's' }"
                >
                  <span class="gc-icon">
                    <svg
                      v-if="idx === 0"
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    ><rect
                      x="2"
                      y="3"
                      width="20"
                      height="14"
                      rx="2"
                    /><line
                      x1="8"
                      y1="21"
                      x2="16"
                      y2="21"
                    /><line
                      x1="12"
                      y1="17"
                      x2="12"
                      y2="21"
                    /></svg>
                    <svg
                      v-else-if="idx === 1"
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    ><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle
                      cx="9"
                      cy="7"
                      r="4"
                    /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></svg>
                    <svg
                      v-else
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    ><line
                      x1="18"
                      y1="20"
                      x2="18"
                      y2="10"
                    /><line
                      x1="12"
                      y1="20"
                      x2="12"
                      y2="4"
                    /><line
                      x1="6"
                      y1="20"
                      x2="6"
                      y2="14"
                    /></svg>
                  </span>
                  <strong>{{ g.title }}</strong>
                  <p>{{ g.desc }}</p>
                </div>
              </div>
            </div>

            <div
              v-if="error"
              class="msg-error"
            >
              {{ error }}
            </div>
            <div class="step-actions">
              <button
                class="btn-ghost"
                @click="prevStep()"
              >
                上一步
              </button>
              <button
                class="btn-primary btn-xl"
                :disabled="loading"
                @click="finishSetup"
              >
                <template v-if="!loading">
                  完成安装，进入系统
                </template>
                <template v-else>
                  <span class="btn-spinner" /> 完成中
                </template>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="card-footer">
        <div class="stepper">
          <template
            v-for="s in steps"
            :key="s.num"
          >
            <div
              :class="['stepper-node', { active: currentStep === s.num, done: completedSteps.has(s.num), clickable: s.num <= maxReachedStep && s.num !== currentStep }]"
              :title="s.title"
              @click="s.num <= maxReachedStep && s.num !== currentStep ? goStep(s.num) : null"
            >
              <span class="stepper-dot">
                <svg
                  v-if="completedSteps.has(s.num)"
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="3"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                ><path d="M5 12l5 5L20 7" /></svg>
                <span v-else>{{ s.num }}</span>
              </span>
            </div>
            <div
              v-if="s.num < totalSteps"
              :class="['stepper-line', { filled: s.num < currentStep }]"
            />
          </template>
        </div>
      </div>
    </div>

    <p class="page-bottom-hint">
      © 2025 在线课程自动化平台 · 安装完成后此页面将自动禁用
    </p>
  </div>
</template>

<style scoped>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

.setup-root {
  position: relative;
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif;
  background: var(--c-bg);
  overflow: hidden;
}

/* ── Background Orbs & Particles ── */
.setup-bg {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

.bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.18;
}

.bg-orb-1 {
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, #4f6ef7, transparent 70%);
  top: -120px;
  right: -80px;
  animation: orbDrift1 18s ease-in-out infinite;
}

.bg-orb-2 {
  width: 400px;
  height: 400px;
  background: radial-gradient(circle, #8b5cf6, transparent 70%);
  bottom: -100px;
  left: -60px;
  animation: orbDrift2 22s ease-in-out infinite;
}

.bg-orb-3 {
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, #ec4899, transparent 70%);
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  animation: orbDrift3 15s ease-in-out infinite;
}

@keyframes orbDrift1 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(-40px, 30px) scale(1.08); }
  66% { transform: translate(20px, -20px) scale(0.95); }
}

@keyframes orbDrift2 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -25px) scale(1.05); }
  66% { transform: translate(-20px, 15px) scale(0.97); }
}

@keyframes orbDrift3 {
  0%, 100% { transform: translate(-50%, -50%) scale(1); }
  50% { transform: translate(-50%, -50%) scale(1.15); }
}

.bg-particle {
  position: absolute;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--c-primary);
  opacity: 0;
  animation: particleFloat 7s ease-in-out infinite;
  animation-delay: calc(var(--i) * 0.6s);
}

.bg-particle:nth-child(odd) { background: #8b5cf6; }
.bg-particle:nth-child(4) { left: 10%; top: 25%; }
.bg-particle:nth-child(5) { left: 20%; top: 60%; width: 4px; height: 4px; }
.bg-particle:nth-child(6) { left: 35%; top: 35%; width: 7px; height: 7px; }
.bg-particle:nth-child(7) { left: 50%; top: 75%; }
.bg-particle:nth-child(8) { left: 65%; top: 20%; width: 4px; height: 4px; }
.bg-particle:nth-child(9) { left: 80%; top: 55%; width: 6px; height: 6px; }
.bg-particle:nth-child(10) { left: 90%; top: 40%; }
.bg-particle:nth-child(11) { left: 75%; top: 80%; width: 3px; height: 3px; }
.bg-particle:nth-child(12) { left: 45%; top: 15%; width: 5px; height: 5px; }
.bg-particle:nth-child(13) { left: 28%; top: 85%; }

@keyframes particleFloat {
  0%, 100% { opacity: 0; transform: translateY(0) scale(0.5); }
  15% { opacity: 0.5; }
  50% { opacity: 0.25; transform: translateY(-35px) scale(1); }
  85% { opacity: 0.45; }
}

/* ── Card ── */
.setup-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 560px;
  max-height: calc(100vh - 64px);
  display: flex;
  flex-direction: column;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 20px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.06), 0 1px 3px rgba(0, 0, 0, 0.04);
  animation: cardEnter 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) backwards;
  overflow: hidden;
}

@keyframes cardEnter {
  from { opacity: 0; transform: translateY(30px) scale(0.95); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

/* ── Card Header ── */
.card-header {
  flex-shrink: 0;
  padding: 16px 24px 0;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.card-brand {
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand-badge {
  padding: 2px 8px;
  background: linear-gradient(135deg, var(--c-primary-bg), #f3e8ff);
  color: var(--c-primary);
  border-radius: 20px;
  font-size: 11px;
  font-weight: 700;
}

.brand-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--c-text);
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.meta-step {
  font-size: 12px;
  font-weight: 700;
  color: var(--c-primary);
  background: var(--c-primary-bg);
  padding: 2px 10px;
  border-radius: 12px;
}

.meta-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--c-text-secondary);
}

.card-track {
  height: 3px;
  background: var(--c-border);
  border-radius: 3px;
  overflow: hidden;
}

.card-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--c-primary), #8b5cf6, #ec4899);
  background-size: 200% 100%;
  animation: progressShimmer 2s ease-in-out infinite;
  transition: width 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
  border-radius: 3px;
}

@keyframes progressShimmer {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

/* ── Card Body ── */
.card-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 28px;
  min-height: 0;
  scrollbar-width: thin;
  scrollbar-color: var(--c-border) transparent;
}

.card-body::-webkit-scrollbar { width: 4px; }
.card-body::-webkit-scrollbar-thumb { background: var(--c-border); border-radius: 4px; }
.card-body::-webkit-scrollbar-track { background: transparent; }

/* ── Card Footer ── */
.card-footer {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 12px 24px 16px;
  border-top: 1px solid var(--c-border);
  background: var(--c-surface);
}

.footer-steps {
  display: flex;
  gap: 6px;
}

.footer-hint {
  font-size: 10px;
  color: var(--c-text-muted);
  margin: 0;
}

.page-bottom-hint {
  position: fixed;
  bottom: 16px;
  left: 0;
  width: 100%;
  text-align: center;
  font-size: 11px;
  color: var(--c-text-muted);
  margin: 0;
  z-index: 1;
  pointer-events: none;
}

/* ── Step Panel ── */
.step-anim-wrap {
  animation: stepSpringIn 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) backwards;
}

@keyframes stepSpringIn {
  from { opacity: 0; transform: translateY(16px) scale(0.97); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.step-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ── Welcome Hero ── */
.welcome-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 0 8px;
}

.welcome-logo {
  position: relative;
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 18px;
}

.logo-core {
  width: 64px;
  height: 64px;
  border-radius: 20px;
  background: var(--c-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  position: relative;
  z-index: 2;
  box-shadow: 0 8px 24px rgba(79, 110, 247, 0.3);
  animation: logoFloat 4s ease-in-out infinite;
}

@keyframes logoFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}

.logo-ring {
  position: absolute;
  width: 80px;
  height: 80px;
  border-radius: 24px;
  border: 2px solid rgba(79, 110, 247, 0.15);
  animation: ringPulse 3s ease-in-out infinite;
}

.logo-ring-2 {
  width: 96px;
  height: 96px;
  border-radius: 28px;
  border-color: rgba(79, 110, 247, 0.08);
  animation-delay: 0.5s;
}

@keyframes ringPulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.06); opacity: 0.6; }
}

.welcome-title {
  font-size: 28px;
  font-weight: 800;
  color: var(--c-text);
  letter-spacing: -0.5px;
  margin-bottom: 4px;
  animation: fadeInUp 0.5s ease 0.15s backwards;
}

.welcome-desc {
  font-size: 14px;
  color: var(--c-text-secondary);
  animation: fadeInUp 0.5s ease 0.25s backwards;
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ── Feature List ── */
.feature-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.feature-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  border-radius: var(--radius);
  animation: featureRowIn 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) backwards;
  animation-delay: var(--delay);
  transition: background 0.2s;
}

.feature-row:hover {
  background: rgba(79, 110, 247, 0.04);
}

@keyframes featureRowIn {
  from { opacity: 0; transform: translateX(-12px); }
  to { opacity: 1; transform: translateX(0); }
}

.fr-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(79, 110, 247, 0.08);
  color: var(--c-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.feature-row:hover .fr-icon {
  transform: scale(1.1);
}

.fr-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.fr-content strong {
  font-size: 14px;
  font-weight: 700;
  color: var(--c-text);
}

.fr-content span {
  font-size: 12px;
  color: var(--c-text-muted);
}

/* ── Finish ── */
.finish-checkmark {
  margin-bottom: 16px;
  animation: scaleIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) 0.1s backwards;
}

@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.5); }
  to { opacity: 1; transform: scale(1); }
}

/* ── Step Head ── */
.step-head {
  text-align: center;
  padding: 4px 0;
}

.step-head h2 {
  font-size: 24px;
  font-weight: 800;
  color: var(--c-text);
  margin-bottom: 6px;
  letter-spacing: -0.3px;
}

.step-head p {
  font-size: 14px;
  color: var(--c-text-secondary);
}

/* ── Buttons ── */
.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px 24px;
  background: linear-gradient(135deg, #4f6ef7, #6366f1);
  color: #fff;
  border: none;
  border-radius: var(--radius);
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  box-shadow: 0 2px 12px rgba(79, 110, 247, 0.25);
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  white-space: nowrap;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px) scale(1.03);
  box-shadow: 0 6px 24px rgba(79, 110, 247, 0.35);
}

.btn-primary:active:not(:disabled) {
  transform: translateY(0) scale(0.98);
  box-shadow: 0 1px 4px rgba(79, 110, 247, 0.2);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.btn-xl {
  padding: 14px 32px;
  font-size: 15px;
  border-radius: var(--radius-lg);
}

.btn-lg {
  padding: 11px 26px;
  font-size: 14px;
  border-radius: var(--radius-lg);
}

.btn-full {
  width: 100%;
}

.btn-ghost {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px 18px;
  background: transparent;
  color: var(--c-text-secondary);
  border: none;
  border-radius: var(--radius);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.btn-ghost:hover:not(:disabled) {
  color: var(--c-primary);
  background: var(--c-primary-bg);
}

.btn-ghost:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-sm {
  padding: 5px 12px;
  font-size: 11px;
}

.btn-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  display: inline-block;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* ── Step Actions ── */
.step-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--c-border);
}

.action-group {
  display: flex;
  gap: 8px;
}

/* ── Forms ── */
.form-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 13px;
  font-weight: 600;
  color: var(--c-text-secondary);
}

.form-input {
  width: 100%;
  height: 44px;
  padding: 0 14px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  background: var(--c-bg);
  color: var(--c-text);
  font-size: 13px;
  outline: none;
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.form-input:focus {
  border-color: var(--c-primary);
  box-shadow: 0 0 0 3px rgba(79, 110, 247, 0.1);
  background: var(--c-surface);
  transform: scale(1.01);
}

.form-input::placeholder {
  color: var(--c-text-muted);
  opacity: 0.5;
}

.form-input.mono {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
}

.form-hint {
  font-size: 11px;
  color: var(--c-text-muted);
  margin-top: 2px;
}

/* ── Messages ── */
.msg-error {
  padding: 10px 14px;
  background: var(--c-danger-bg);
  color: var(--c-danger);
  border: 1px solid rgba(239, 68, 68, 0.15);
  border-radius: var(--radius-sm);
  font-size: 12px;
  animation: shakeIn 0.4s cubic-bezier(0.36, 0.07, 0.19, 0.97);
}

.msg-success {
  padding: 10px 14px;
  background: var(--c-success-bg);
  color: var(--c-success);
  border: 1px solid rgba(34, 197, 94, 0.15);
  border-radius: var(--radius-sm);
  font-size: 12px;
  animation: fadeInUp 0.3s ease;
}

@keyframes shakeIn {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-6px); }
  40% { transform: translateX(5px); }
  60% { transform: translateX(-3px); }
  80% { transform: translateX(2px); }
}

/* ── Loading State ── */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 0;
}

.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--c-border);
  border-top-color: var(--c-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-state span {
  font-size: 13px;
  color: var(--c-text-muted);
}

/* ── Env Check ── */
.env-results {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.env-category h4 {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--c-text-muted);
  margin-bottom: 6px;
  font-weight: 700;
}

.env-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  animation: fadeInUp 0.3s ease backwards;
}

.env-row.ok { background: var(--c-success-bg); color: var(--c-success); }
.env-row.warn { background: var(--c-warning-bg); color: var(--c-warning); }
.env-row.error { background: var(--c-danger-bg); color: var(--c-danger); }

.env-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.env-icon.ok { color: var(--c-success); }
.env-icon.warn { color: var(--c-warning); }
.env-icon.fail { color: var(--c-error); }

.env-name {
  color: var(--c-text-secondary);
  min-width: 80px;
  font-weight: 500;
}

.env-msg {
  color: var(--c-text-muted);
  font-size: 11px;
  flex: 1;
  word-break: break-all;
}

/* ── YPay Layout ── */
.ypay-layout {
  display: flex;
  gap: 28px;
  align-items: flex-start;
}

.ypay-qr {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.qr-frame {
  background: #fff;
  border-radius: var(--radius);
  padding: 10px;
  border: 1px solid var(--c-border);
  box-shadow: var(--shadow-sm);
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.qr-frame:hover {
  transform: scale(1.05);
}

.qr-frame img {
  width: 120px;
  height: 120px;
  display: block;
}

.qr-label {
  font-size: 11px;
  color: var(--c-text-muted);
}

.qr-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px;
  border: 1px dashed var(--c-border);
  border-radius: var(--radius);
  text-align: center;
}

.qr-empty span {
  font-size: 12px;
  color: var(--c-text-secondary);
}

.ypay-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.info-card {
  padding: 14px 16px;
  background: var(--c-info-bg, rgba(59, 130, 246, 0.08));
  border: 1px solid rgba(59, 130, 246, 0.12);
  border-radius: var(--radius);
}

.info-card strong {
  display: block;
  font-size: 13px;
  color: var(--c-text);
  margin-bottom: 8px;
  font-weight: 700;
}

.info-card ol {
  margin: 0;
  padding-left: 18px;
}

.info-card li {
  font-size: 12px;
  color: var(--c-text-secondary);
  margin-bottom: 4px;
  line-height: 1.5;
}

.dl-link {
  margin-top: 8px;
  font-size: 12px;
  color: var(--c-primary);
  text-decoration: none;
  font-weight: 600;
  transition: color 0.2s;
}

.dl-link:hover {
  color: #3b5bdb;
}

/* ── Pricing ── */
.pricing-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.pricing-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-lg);
  padding: 24px 20px;
  text-align: center;
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.pricing-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-md);
}

.pricing-card h3 {
  font-size: 16px;
  color: var(--c-text);
  margin-bottom: 4px;
  font-weight: 700;
}

.pricing-card > p {
  font-size: 12px;
  color: var(--c-text-muted);
  margin-bottom: 16px;
}

.price-input {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.price-sym {
  font-size: 18px;
  font-weight: 700;
  color: var(--c-text-muted);
}

.price-input input {
  width: 100px;
  text-align: center;
  font-size: 22px;
  font-weight: 800;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  background: var(--c-bg);
  color: var(--c-text);
  padding: 8px;
  outline: none;
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.price-input input:focus {
  border-color: var(--c-primary);
  box-shadow: 0 0 0 3px rgba(79, 110, 247, 0.1);
  transform: scale(1.04);
}

.price-hint {
  display: block;
  margin-top: 10px;
  font-size: 11px;
  color: var(--c-text-muted);
}

/* ── App Steps ── */
.app-steps {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.app-step {
  display: flex;
  gap: 14px;
  padding: 18px;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-lg);
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  animation: cardSpringIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) backwards;
  animation-delay: calc(var(--delay, 0s));
}

.app-step:nth-child(1) { animation-delay: 0s; }
.app-step:nth-child(2) { animation-delay: 0.08s; }
.app-step:nth-child(3) { animation-delay: 0.16s; }

.app-step:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.as-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(79, 110, 247, 0.08);
  color: var(--c-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.as-body {
  flex: 1;
  min-width: 0;
}

.as-body strong {
  display: block;
  font-size: 14px;
  font-weight: 700;
  color: var(--c-text);
  margin-bottom: 10px;
}

.as-tips {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
}

.as-tip {
  padding: 8px 12px;
  background: var(--c-bg);
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--c-text-secondary);
}

.as-note {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--c-success-bg);
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--c-success);
  font-weight: 600;
}

/* ── VMQ Setup Cards ── */
.ypay-setup-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}
.ypay-setup-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-lg);
  padding: 16px;
  text-align: center;
}
.ypay-setup-card-hd {
  margin-bottom: 14px;
}
.ypay-setup-badge {
  display: inline-block;
  padding: 4px 16px;
  border-radius: 14px;
  background: #eef2ff;
  color: #4f6ef7;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.03em;
}
.qr-frame {
  display: inline-block;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 6px;
  background: #fff;
}
.qr-frame img { width: 180px; height: 180px; display: block; border-radius: 6px; }
.dl-link { display: block; margin-top: 10px; font-size: 13px; color: #4f6ef7; font-weight: 500; }
.tut-note-small { font-size: 11px; color: #94a3b8; margin-top: 10px; }
.pair-status-ok { margin-top: 8px; font-size: 12px; color: #22c55e; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 4px; }
.pair-status-wait { margin-top: 8px; font-size: 12px; color: #f59e0b; font-weight: 500; display: flex; align-items: center; justify-content: center; gap: 4px; }
.qr-loading, .qr-empty { height: 190px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: #94a3b8; font-size: 13px; }

/* ── Tutorial Steps ── */
.tut-steps {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.tut-step {
  display: flex;
  gap: 14px;
  padding: 18px 20px;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-lg);
  transition: border-color 0.2s;
}

.tut-step:hover {
  border-color: var(--c-primary);
}

.tut-num {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--c-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.tut-body {
  flex: 1;
  min-width: 0;
}

.tut-body > strong {
  display: block;
  font-size: 15px;
  font-weight: 700;
  color: var(--c-text);
  margin-bottom: 4px;
  letter-spacing: 0.02em;
}

.tut-desc {
  font-size: 13px;
  color: var(--c-text-secondary);
  margin: 0 0 14px;
  line-height: 1.5;
}

.tut-body .qr-frame {
  width: 140px;
  height: 140px;
  margin-bottom: 8px;
}

.tut-body .dl-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--c-primary);
  text-decoration: none;
  font-weight: 600;
}

.tut-body .dl-link:hover {
  text-decoration: underline;
}

.tut-checklist {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 4px;
}

.tut-check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--c-text);
  line-height: 1.4;
}

.tc-icon {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--c-success-bg);
  color: var(--c-success);
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.tut-note {
  margin: 10px 0 0;
  font-size: 11px;
  color: var(--c-text-muted);
  line-height: 1.4;
}

.qr-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 20px;
  color: var(--c-text-muted);
  font-size: 13px;
}

.spinner-sm {
  width: 18px;
  height: 18px;
  border: 2px solid var(--c-border);
  border-top-color: var(--c-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* ── Finish ── */
.finish-checklist {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 16px;
  background: var(--c-surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--c-border);
}

.ck-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--c-text-muted);
  transition: color 0.2s;
}

.ck-item.ok {
  color: var(--c-text);
}

.ck-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.ck-icon.ok { color: var(--c-success); }
.ck-icon.warn { color: var(--c-warning); }

.ck-item code {
  background: var(--c-primary-bg);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--c-primary);
  font-weight: 600;
}

.guide-section h3 {
  font-size: 15px;
  color: var(--c-text);
  margin-bottom: 12px;
  font-weight: 700;
}

.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.guide-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: 16px;
  animation: cardSpringIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) backwards;
  animation-delay: var(--delay);
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s;
}

.guide-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-md);
}

.gc-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background: rgba(79, 110, 247, 0.08);
  color: var(--c-primary);
  margin-bottom: 8px;
}

.guide-card strong {
  display: block;
  font-size: 13px;
  color: var(--c-text);
  margin-bottom: 4px;
  font-weight: 700;
}

.guide-card p {
  font-size: 12px;
  color: var(--c-text-muted);
  line-height: 1.5;
  margin: 0;
}

/* ── Stepper ── */
.stepper {
  display: flex;
  align-items: center;
  gap: 0;
}

.stepper-node {
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: default;
  transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.stepper-node.clickable {
  cursor: pointer;
}

.stepper-dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid rgba(79, 110, 247, 0.3);
  background: rgba(79, 110, 247, 0.05);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: var(--c-primary);
  transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
  position: relative;
}

.stepper-node.clickable:hover .stepper-dot {
  border-color: var(--c-primary);
  color: var(--c-primary);
  transform: scale(1.12);
}

.stepper-node.active .stepper-dot {
  width: 32px;
  height: 32px;
  background: var(--c-primary);
  border-color: var(--c-primary);
  color: #fff;
  font-size: 12px;
  box-shadow: 0 0 0 4px rgba(79, 110, 247, 0.15), 0 2px 8px rgba(79, 110, 247, 0.25);
  animation: dotPulse 2s ease-in-out infinite;
}

@keyframes dotPulse {
  0%, 100% { box-shadow: 0 0 0 4px rgba(79, 110, 247, 0.15), 0 2px 8px rgba(79, 110, 247, 0.25); }
  50% { box-shadow: 0 0 0 8px rgba(79, 110, 247, 0.08), 0 2px 8px rgba(79, 110, 247, 0.25); }
}

.stepper-node.done .stepper-dot {
  background: var(--c-primary);
  border-color: var(--c-primary);
  color: #fff;
}

.stepper-node.done:hover .stepper-dot {
  transform: scale(1.12);
  box-shadow: 0 0 0 4px rgba(79, 110, 247, 0.15);
}

.stepper-line {
  width: 20px;
  height: 2px;
  background: rgba(79, 110, 247, 0.2);
  border-radius: 2px;
  transition: background 0.4s ease;
  flex-shrink: 0;
}

.stepper-line.filled {
  background: var(--c-primary);
}

/* ── Mobile ── */
@media (max-width: 640px) {
  .setup-card { max-width: 100%; max-height: 100vh; border-radius: 0; margin: 0; }
  .card-body { padding: 16px; }
  .welcome-title { font-size: 24px; }
  .form-grid-2 { grid-template-columns: 1fr; }
  .pricing-grid { grid-template-columns: 1fr; }
  .ypay-layout { flex-direction: column; align-items: center; }
  .guide-grid { grid-template-columns: 1fr; }
  .step-actions { flex-direction: column; gap: 8px; }
  .action-group { width: 100%; }
  .action-group .btn-ghost { flex: 1; }
  .btn-xl, .btn-lg { width: 100%; }
  .stepper-line { width: 10px; }
  .stepper-dot { width: 24px; height: 24px; font-size: 10px; }
  .stepper-node.active .stepper-dot { width: 28px; height: 28px; }
  .meta-label { display: none; }
}
</style>

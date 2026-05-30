<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { api, type CourseItem } from '@/api'
import { usePlatformNames } from '@/composables/usePlatformNames'
import { useHomeState } from '@/composables/useHomeState'
import AppTopbar from '@/components/AppTopbar.vue'
import PaymentSuccess from '@/components/PaymentSuccess.vue'

const store = useAppStore()
const { load: loadPlatformNames, getName: getPlatformName } = usePlatformNames()

const {
  userRole, isPrivileged, isRegularUser, showUpgradeBanner, dismissUpgradeBanner, detectUserRole, handleVisibilityChange,
  username, password, scanning, rescanning, scanDone, allDone, isLeaving, scanData, countdown,
  activeTab, chaoxingUsername, chaoxingPassword, startChaoxingScan,
  loginError, failedPlatforms, reloginDialog, reloginPassword, reloginLoading, loginErrorCountdown,
  packagePricing, submittedCourseIds, allInProgress, pendingOrderedCourseIds, checkedCourseIds,
  loadingPrices, backendPrices,
  isCourseDone, isCourseDoneOrSubmitted, visiblePlatforms, togglePlatform, toggleCourse, isPlatformAllChecked,
  summary, scenario, currentPrices, studentName, chaoxingInfo, chaoxingServiceType,
  startScan, resetScan, rescan, openReloginDialog, closeReloginDialog, submitRelogin,
  calcCoursePrice, fetchBackendPrices, saveSession,
  paying, showPayModal, payTotal, submitSuccess, payError, payQrCode, payPollTimer,
  selectedPayMethod, payOrders, payQrCodes, payReallyPrices, payBatchIds, payBatchOutTradeNos,
  payBatchId, payBatchOutTradeNo, showPaySuccess, footerAds, paySuccessAmount, payTimedOut,
  handleOrderSuccess, goToOrders, submitAndPay, onPaySuccessDone, closePay, savePayQr, switchPayMethod,
  danmakuList, earnBtnY, earnPointerDown, earnClick, pct, pctClass, LS_KEY,
  showAnnouncement, announcementContent, checkAnnouncement, dismissAnnouncement,
} = useHomeState()

// 所有任务进行中时，3秒后自动跳转订单页
const autoRedirectCountdown = ref(3)
let autoRedirectTimer: ReturnType<typeof setInterval> | null = null

watch(allInProgress, (val) => {
  if (val) {
    autoRedirectCountdown.value = 3
    autoRedirectTimer = setInterval(() => {
      autoRedirectCountdown.value--
      if (autoRedirectCountdown.value <= 0) {
        if (autoRedirectTimer) { clearInterval(autoRedirectTimer); autoRedirectTimer = null }
        goToOrders()
      }
    }, 1000)
  } else {
    if (autoRedirectTimer) { clearInterval(autoRedirectTimer); autoRedirectTimer = null }
  }
})

onBeforeUnmount(() => {
  if (autoRedirectTimer) { clearInterval(autoRedirectTimer); autoRedirectTimer = null }
  if (payPollTimer.value) { clearTimeout(payPollTimer.value); payPollTimer.value = null }
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})

onMounted(async () => {
  detectUserRole()
  document.addEventListener('visibilitychange', handleVisibilityChange)
  loadPlatformNames()
  checkAnnouncement()
  try {
    const res = await api.pricing.get()
    if (res.data) {
      packagePricing.value = {
        priceSmall: res.data.priceSmall ?? 3, priceMedium: res.data.priceMedium ?? 5, priceLarge: res.data.priceLarge ?? 6,
        discount25: res.data.discount25 ?? 0.7, discount50: res.data.discount50 ?? 0.5, discount75: res.data.discount75 ?? 0.3,
        priceMinimum: res.data.priceMinimum ?? 2, priceExamOnly: res.data.priceExamOnly ?? 5, priceHomeworkOnly: res.data.priceHomeworkOnly ?? 3,
        priceChaoxing: res.data.priceChaoxing ?? 8,
      }
    }
  } catch {}
  try { const adRes = await api.ads.listPublic(); if (adRes.data) footerAds.value = adRes.data } catch {}
  if (scanDone.value && username.value.trim()) {
    try { const r = await api.orders.activeCourses(username.value.trim()); const activeIds: string[] = r?.data || []; for (const cid of activeIds) submittedCourseIds.value.add(cid) } catch {}
  }
})
</script>

<template>
  <div class="page">
    <AppTopbar title="FUCK 文理网课" :show-role-badge="true" />

    <div class="content-wrapper">
      <div v-if="isRegularUser && showUpgradeBanner" class="upgrade-banner">
        <div class="upgrade-banner-body">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
          <span>升级为<strong>L1代理</strong>，开启推广赚钱之旅，最高享15%佣金</span>
        </div>
        <div class="upgrade-banner-actions">
          <router-link to="/agent" class="btn btn-primary btn-sm">
立即升级
</router-link>
          <button class="btn btn-ghost btn-sm" @click="dismissUpgradeBanner">
暂不
</button>
        </div>
      </div>
      <div v-if="allDone" class="all-done-wrapper">
        <div :class="['done-card', isLeaving ? 'fade-out-leave-active' : 'fade-in-enter-active']">
          <div class="done-icon">
            <svg width="72" height="72" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="11" stroke="var(--c-success)" stroke-width="2" fill="var(--c-success-bg)"/>
              <path d="M7 13l3 3 7-7" stroke="var(--c-success)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <h1>任务已完成</h1>
          <p>所有课程均已 100% 完成</p>
          <div class="countdown">
{{ countdown }} 秒后返回登录页面
</div>
        </div>
      </div>

      <div v-else-if="allInProgress" class="all-done-wrapper">
        <div :class="['done-card', 'inprogress-card', isLeaving ? 'fade-out-leave-active' : 'fade-in-enter-active']">
          <div class="done-icon inprogress-icon">
            <svg width="72" height="72" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="11" stroke="var(--c-primary)" stroke-width="2" fill="var(--c-primary-bg)"/>
              <path d="M12 6v6l4 2" stroke="var(--c-primary)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <h1>所有任务正在进行中</h1>
          <p>所有课程已提交下单，系统正在自动刷课处理中，请耐心等待</p>
          <p style="margin-top:12px;font-size:14px;color:var(--c-text-secondary)">{{ autoRedirectCountdown }}秒后自动跳转到订单页面...</p>
        </div>
      </div>

      <div v-else-if="loginError === 'all'" class="all-done-wrapper">
        <div :class="['done-card', 'error-card', isLeaving ? 'fade-out-leave-active' : 'fade-in-enter-active']">
          <div class="done-icon error-icon">
            <svg width="72" height="72" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="11" stroke="var(--c-danger)" stroke-width="2" fill="var(--c-danger-bg)"/>
              <path d="M15 9l-6 6M9 9l6 6" stroke="var(--c-danger)" stroke-width="2.5" stroke-linecap="round"/>
            </svg>
          </div>
          <h1>登录失败</h1>
          <p v-if="activeTab === 'chaoxing'">学习通登录失败，请检查账号密码是否正确</p>
          <p v-else>所有平台均登录失败，请检查学号密码是否正确</p>
          <div class="countdown error-countdown">
{{ loginErrorCountdown }} 秒后自动返回
</div>
        </div>
      </div>

      <template v-else>
        <div v-if="!scanDone" class="landing-center">
          <h1 class="lc-title">
一键躺平，网课全搞定
</h1>
          <p class="lc-subtitle">
全平台秒杀 · 顶级AI大模型满分答题 · 7×24自动挂机
</p>

          <div class="lc-pills">
            <span class="pill pill-accent">99.2% 通过率</span>
            <span class="pill pill-accent">5000+ 学生信赖</span>
            <span class="pill pill-accent">秒级响应</span>
          </div>

          <div class="login-card" style="margin-top: 32px;">
            <div class="tab-switcher">
              <button :class="['tab-btn', { active: activeTab === 'school' }]" @click="activeTab = 'school'">
                学校平台
              </button>
              <button :class="['tab-btn', { active: activeTab === 'chaoxing' }]" @click="activeTab = 'chaoxing'">
                学习通
              </button>
            </div>

            <template v-if="activeTab === 'school'">
              <div class="lc-header">
                <h2>平台登录</h2>
                <p>输入学号密码，系统将自动检测三大平台</p>
              </div>
              <div class="field">
                <label>学号</label>
                <input v-model="username" placeholder="请输入学号" :disabled="scanning" />
              </div>
              <div class="field">
                <label>密码</label>
                <input v-model="password" type="password" placeholder="请输入平台密码" :disabled="scanning" @keyup.enter="startScan" />
              </div>
              <button class="btn btn-primary btn-lg btn-block" :disabled="scanning" @click="startScan">
                <span v-if="!scanning">登录</span>
                <span v-else class="btn-loading">
                  <span class="spinner"></span>
                  扫描中...
                </span>
              </button>
            </template>

            <template v-if="activeTab === 'chaoxing'">
              <div class="lc-header">
                <h2>学习通</h2>
                <p>输入学习通账号密码，自动扫描课程和积分状态</p>
              </div>
              <div class="field">
                <label>账号</label>
                <input v-model="chaoxingUsername" placeholder="请输入手机号" :disabled="scanning" />
              </div>
              <div class="field">
                <label>密码</label>
                <input v-model="chaoxingPassword" type="password" placeholder="请输入密码" :disabled="scanning" @keyup.enter="startChaoxingScan" />
              </div>
              <button class="btn btn-primary btn-lg btn-block" :disabled="scanning" @click="startChaoxingScan">
                <span v-if="!scanning">登录</span>
                <span v-else class="btn-loading">
                  <span class="spinner"></span>
                  扫描中...
                </span>
              </button>
            </template>
          </div>
        </div>

        <div v-if="scanDone" class="results">
        <div v-if="rescanning" class="rescan-overlay">
          <span class="spinner-lg"></span>
          <p>正在刷新数据...</p>
        </div>
        <div v-if="submittedCourseIds.size > 0" class="submitted-banner">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
          </svg>
          <span>已成功提交 <strong>{{ submittedCourseIds.size }}</strong> 门课程，任务处理中</span>
        </div>
        <div class="results-topbar">
          <div v-if="studentName" class="rt-student">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            <span>{{ studentName }}</span>
          </div>
          <!-- 学习通专用信息 -->
          <div v-if="activeTab === 'chaoxing' && chaoxingInfo" class="rt-info">
            <span v-if="chaoxingInfo.school" class="rt-pill ok">{{ chaoxingInfo.school }}</span>
            <span v-if="chaoxingInfo.workPending > 0" class="rt-pill warn">{{ chaoxingInfo.workPending }} 个待完成作业</span>
            <span class="rt-pill pending">{{ chaoxingInfo.pendingCount }} 门待处理</span>
          </div>
          <!-- 学校平台信息 -->
          <div v-else class="rt-info">
            <span class="rt-pill ok">{{ visiblePlatforms.filter(p => p.status === 'ok').length }} 个平台登录成功</span>
            <span class="rt-pill total">{{ visiblePlatforms.reduce((s,p) => s + p.courses.length, 0) }} 门课程</span>
            <span class="rt-pill pending">{{ visiblePlatforms.reduce((s,p) => s + p.courses.filter(c => !isCourseDoneOrSubmitted(c)).length, 0) }} 门待处理</span>
          </div>
          <div class="rt-actions">
            <button class="btn btn-ghost" @click="rescan">
重新扫描
</button>
            <button class="btn btn-outline btn-back-home" @click="resetScan">
返回主页
</button>
          </div>
        </div>

        <!-- ========== onlyVideos ========== -->
        <template v-if="activeTab !== 'chaoxing'">
        <div v-if="scenario === 'onlyVideos'" class="plan-select">
          <div class="scenario-banner video-banner">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            <div class="sb-body">
              <strong>仅剩视频未完成</strong>
              <span>所选课程考试已全部通过，只需刷视频。</span>
            </div>
          </div>
          <div class="plan-card single active">
            <div class="plan-card-top">
<span class="plan-tag tag-green">推荐</span>
</div>
            <div class="plan-icon" style="color:#4f6ef7">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="23 7 16 12 7 7 11 3 23 3 23 7"/><polygon points="12 7 5 12 1 9 1 13 5 16 12 13"/><polygon points="12 13 5 16 1 13 1 17 5 20 12 17"/><polygon points="22 10 17 13 17 17 22 20 23 16"/><polygon points="23 4 19 6 19 10 23 8"/></svg>
            </div>
            <div class="plan-name">
视频刷课
</div>
            <div class="plan-desc">
仅刷视频课程
</div>
            <div class="plan-short-desc">
所选课程考试已完成，仅需刷视频
</div>
          </div>
        </div>

        <!-- ========== onlyExams ========== -->
        <div v-if="scenario === 'onlyExams'" class="plan-select">
          <div class="scenario-banner exam-banner">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <div class="sb-body">
              <strong>仅剩考试未完成</strong>
              <span>所选课程视频已全部刷完，仅需处理考试。</span>
            </div>
          </div>
          <div class="plan-card single active">
            <div class="plan-card-top">
<span class="plan-tag tag-green">推荐</span>
</div>
            <div class="plan-icon" style="color:#22c55e">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
            </div>
            <div class="plan-name">
考试答题
</div>
            <div class="plan-desc">
AI智能答题考试
</div>
            <div class="plan-short-desc">
所选课程视频已完成，仅需答题
</div>
          </div>
        </div>

        <!-- ========== both ========== -->
        <div v-if="scenario === 'both'" class="plan-select">
          <div class="scenario-banner both-banner">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            <div class="sb-body">
              <strong>视频和考试均有未完成</strong>
              <span>需要同时处理视频和考试，按基础单价计费。</span>
            </div>
          </div>
          <div class="plan-card single active">
            <div class="plan-card-top">
<span class="plan-tag tag-blue">标准计费</span>
</div>
            <div class="plan-icon" style="color:#4f6ef7">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            </div>
            <div class="plan-name">
视频 + 考试
</div>
            <div class="plan-desc">
视频刷课 + 考试答题
</div>
            <div class="plan-short-desc">
视频和考试打包计费
</div>
          </div>
        </div>
        </template>

        <div v-for="p in visiblePlatforms" :key="p.website_id" class="platform-block">
          <div class="pb-header">
            <label class="pb-check">
              <input
                type="checkbox"
                :checked="isPlatformAllChecked(p)"
                :indeterminate="!isPlatformAllChecked(p) && p.courses.some(c => !isCourseDoneOrSubmitted(c) && checkedCourseIds.has(c.course_id))"
                @change="togglePlatform(p.website_id, ($event.target as HTMLInputElement).checked)"
              />
            </label>
            <span class="pb-badge" :class="p.status === 'ok' ? 'ok' : 'fail'">{{ p.name }}</span>
            <span class="pb-count">{{ p.courses.filter(c => !isCourseDoneOrSubmitted(c)).length }} 门待处理</span>
          </div>
          <div class="course-list">
            <div
              v-for="c in p.courses.filter(c => !submittedCourseIds.has(c.course_id))"
              :key="c.course_id"
              class="course-row"
              :class="{ done: isCourseDone(c) }"
            >
              <label class="cr-check">
                <input
                  type="checkbox"
                  :checked="checkedCourseIds.has(c.course_id)"
                  :disabled="isCourseDone(c)"
                  @change="toggleCourse(c.course_id)"
                />
              </label>
              <span class="cr-name">{{ c.course_name }}</span>
              <div class="cr-meta">
                <template v-if="p.website_id === 4">
                  <span v-if="c.has_points_system" class="cr-pill exam">{{ c.points_total ?? 0 }}/{{ chaoxingInfo?.pointsTarget ?? 200 }} 积分</span>
                  <span v-if="(c.points_remaining ?? 0) > 0" class="cr-pill warn">还需 {{ c.days_needed ?? 4 }} 天</span>
                  <span v-else-if="c.has_points_system" class="cr-pill ok">积分达标</span>
                  <span v-if="(c.work_pending ?? 0) > 0" class="cr-pill warn">{{ c.work_pending }} 个待完成作业</span>
                  <span v-else-if="(c.work_total ?? 0) > 0" class="cr-pill ok">作业已完成</span>
                </template>
                <template v-else>
                  <div class="cr-bar">
                    <div class="cr-bar-fill" :class="pctClass(c)" :style="{ width: pct(c) + '%' }"></div>
                  </div>
                  <span class="cr-pct">{{ pct(c) }}%</span>
                  <span class="cr-pill" :class="c.video_pending > 0 ? 'warn' : 'ok'">{{ c.video_pending }} 剩余</span>
                  <span v-if="c.records_loaded" class="cr-pill exam">{{ c.exam_done }}/{{ c.exam_total }} 已通过</span>
                  <span v-if="c.exam_deleted > 0" class="cr-pill deleted">{{ c.exam_deleted }} 已删除</span>
                </template>
              </div>
            </div>
          </div>
        </div>

        <div class="summary-bar">
          <template v-if="activeTab === 'chaoxing'">
            <div class="sb-left">
              <span v-if="chaoxingServiceType === 'points'" class="sb-item">刷积分服务</span>
              <span v-else-if="chaoxingServiceType === 'work'" class="sb-item">作业代做服务</span>
              <span v-else-if="chaoxingServiceType === 'both'" class="sb-item">刷积分 + 作业代做</span>
              <span v-else class="sb-item">全部完成</span>
              <span class="sb-item">已选 <strong>{{ summary.courses }}</strong> 门课程</span>
            </div>
            <div class="sb-right">
              <template v-if="isPrivileged">
                <button class="btn btn-primary btn-lg" :disabled="paying || summary.courses === 0" @click="submitAndPay">
                  <span v-if="!paying">加入队列</span>
                  <span v-else class="btn-loading"><span class="spinner"></span>提交中</span>
                </button>
              </template>
              <template v-else>
                <span class="sb-price">¥{{ summary.total.toFixed(2) }}</span>
                <button class="btn btn-primary btn-lg" :disabled="paying || summary.courses === 0" @click="submitAndPay">
                  <span v-if="!paying">提交并支付</span>
                  <span v-else class="btn-loading"><span class="spinner"></span>提交中</span>
                </button>
              </template>
            </div>
          </template>
          <template v-else>
            <div class="sb-left">
              <span class="sb-item">已选 <strong>{{ summary.courses }}</strong> 门课程</span>
              <span class="sb-item"><strong>{{ summary.videos }}</strong> 个视频</span>
              <span v-if="summary.exams > 0" class="sb-item"><strong>{{ summary.exams }}</strong> 场考试</span>
            </div>
            <div class="sb-right">
              <template v-if="isPrivileged">
                <button class="btn btn-primary btn-lg" :disabled="paying || summary.courses === 0" @click="submitAndPay">
                  <span v-if="!paying">加入队列</span>
                  <span v-else class="btn-loading"><span class="spinner"></span>提交中</span>
                </button>
              </template>
              <template v-else>
                <div class="sb-detail">
                  <template v-if="summary.breakdown.length > 0">
                    <span v-for="(b, i) in summary.breakdown.slice(0, 3)" :key="i" class="sb-detail-item">
                      {{ b.name.length > 10 ? b.name.slice(0, 10) + '...' : b.name }} ({{ b.videos }}节) ¥{{ b.price.toFixed(2) }}
                    </span>
                    <span v-if="summary.breakdown.length > 3" class="sb-detail-item">...共 {{ summary.breakdown.length }} 门课</span>
                  </template>
                  <span class="sb-price">¥{{ summary.total.toFixed(2) }}</span>
                </div>
                <button class="btn btn-primary btn-lg" :disabled="paying || summary.courses === 0" @click="submitAndPay">
                  <span v-if="!paying">提交并支付</span>
                  <span v-else class="btn-loading"><span class="spinner"></span>提交中</span>
                </button>
              </template>
            </div>
          </template>
        </div>
      </div>
      </template>
    </div>

    <div class="modal-overlay" :class="{ show: showPayModal && !showPaySuccess }" @click.self="closePay">
      <div class="modal-box pay-modal">
        <template v-if="payTimedOut">
          <h3>订单已提交</h3>
          <p style="font-size:14px;color:var(--c-text-secondary);margin:16px 0 24px">
支付查询已超时，但订单已创建成功。请到订单页查看支付状态。
</p>
          <button class="btn btn-primary btn-block" @click="goToOrders(); closePay()">
查看订单
</button>
        </template>
        <template v-else>
        <h3>确认支付</h3>
        <div class="modal-amount">
¥{{ payTotal.toFixed(2) }}
</div>
        <p class="pay-amount-warn">
请务必支付相同金额，多一分少一分都无法检测到
</p>
        <div v-if="payError" class="pay-error">
{{ payError }}
</div>

        <div class="pay-method-tabs">
          <button :class="['pm-tab', { active: selectedPayMethod === 'ypay_wxpay' }]" @click="switchPayMethod('ypay_wxpay')">
微信
</button>
          <button :class="['pm-tab', { active: selectedPayMethod === 'ypay_alipay' }]" @click="switchPayMethod('ypay_alipay')">
支付宝
</button>
        </div>

        <!-- QR code section -->
        <div class="qr-section">
          <img v-if="payQrCode" :src="payQrCode" alt="支付二维码" class="pay-qr-img" />
          <div v-else class="pay-qr-placeholder">
生成二维码中...
</div>
          <p class="qr-label">
保存二维码后使用{{ { ypay_alipay: '支付宝', ypay_wxpay: '微信' }[selectedPayMethod] || '扫码' }}扫一扫支付
</p>
        </div>
        <button v-if="payQrCode" class="btn btn-primary btn-block pay-link-btn" style="margin-top:8px" :style="selectedPayMethod === 'ypay_wxpay' ? 'background:#07c160' : ''" @click="savePayQr">
保存二维码
</button>

        <button class="btn btn-ghost btn-block" style="margin-top:10px" @click="closePay">
取消支付
</button>
        </template>
      </div>
    </div>

    <PaymentSuccess :visible="showPaySuccess" :amount="paySuccessAmount" subtitle="订单已提交" @done="onPaySuccessDone" />

    <!-- 系统公告弹窗 -->
    <Teleport to="body">
      <div v-if="showAnnouncement" class="announcement-overlay" @click.self="dismissAnnouncement">
        <div class="announcement-box">
          <div class="announcement-header">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>
            <h3>系统公告</h3>
          </div>
          <div class="announcement-body" v-html="announcementContent"></div>
          <button class="btn btn-primary btn-block announcement-confirm" @click="dismissAnnouncement">
我知道了
</button>
        </div>
      </div>
    </Teleport>

    <footer class="page-footer" :class="{ 'hide-on-mobile-results': scanDone }">
      <div class="footer-divider-wrap">
        <div class="footer-divider"></div>
        <div class="danmaku-layer">
          <span v-for="(d, i) in danmakuList" :key="i" class="danmaku-item" :style="{ '--x': d.x, '--delay': d.delay, '--dur': d.dur }">{{ d.text }}</span>
        </div>
      </div>
      <div v-if="footerAds.length" class="footer-ads">
        <a v-for="ad in footerAds" :key="ad.id" :href="'/api/ads/' + ad.id + '/page'" target="_blank" class="footer-ad-link">{{ ad.name }}</a>
      </div>
      <div v-else class="footer-brand">
        <span>FUCK<strong>文理网课</strong> · 专业解决你的需求</span>
      </div>
    </footer>

    <router-link
      to="/agent"
      class="float-earn-btn"
      :style="{ top: earnBtnY + 'px' }"
      @pointerdown="earnPointerDown"
      @click="earnClick"
    >
      <span class="feb-text">我也要赚钱</span>
    </router-link>
  </div>

  <!-- 重新输入密码弹窗 -->
  <Teleport to="body">
    <div v-if="reloginDialog.visible" class="relogin-overlay" @click.self="closeReloginDialog">
      <div class="relogin-box">
        <div class="relogin-header">
          <h3>重新输入密码</h3>
          <span class="relogin-sub">{{ reloginDialog.name }}</span>
          <button class="relogin-close" @click="closeReloginDialog">
&times;
</button>
        </div>
        <div class="relogin-body">
          <label class="relogin-label">请输入该平台的正确密码</label>
          <input
            v-model="reloginPassword"
            type="password"
            class="relogin-input"
            placeholder="输入密码"
            autofocus
            @keydown.enter="submitRelogin"
          />
        </div>
        <div class="relogin-footer">
          <button class="btn btn-ghost" @click="closeReloginDialog">
取消
</button>
          <button class="btn btn-primary" :disabled="reloginLoading" @click="submitRelogin">
            <span v-if="reloginLoading" class="spinner" style="width:14px;height:14px"></span>
            {{ reloginLoading ? '登录中...' : '确认登录' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}


.upgrade-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 12px;
  background: linear-gradient(135deg, var(--c-primary-bg, #eef2ff) 0%, var(--c-primary-bg-sub, #f5f3ff) 100%);
  border: 1px solid var(--c-primary, #4f6ef7);
  border-radius: 10px;
  flex-wrap: wrap;
}
.upgrade-banner-body {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--c-primary, #4f6ef7);
  font-size: 14px;
}
.upgrade-banner-body strong {
  color: var(--c-primary, #4f6ef7);
}
.upgrade-banner-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.content-wrapper {
  flex: 1;
  width: 100%;
  margin: 0 auto;
  padding: 0 24px;
}

.landing-center {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 80px 24px 0;
  position: relative;
}

.lc-title {
  font-size: 32px;
  font-weight: 800;
  letter-spacing: -1px;
  margin-bottom: 6px;
  position: relative;
  z-index: 1;
  background: linear-gradient(135deg, var(--c-primary) 0%, #8b5cf6 50%, #ec4899 100%);
  background-size: 200% 200%;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: gradientShift 4s ease-in-out infinite;
}
@keyframes gradientShift {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

.lc-subtitle {
  font-size: 14px;
  color: var(--c-text-muted);
  margin-bottom: 12px;
  position: relative;
  z-index: 1;
  animation: fadeInUp 0.8s ease 0.15s backwards;
}

.lc-pills {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-bottom: 28px;
  position: relative;
  z-index: 1;
  animation: fadeInUp 0.7s ease 0.25s backwards;
}

.pill {
  display: inline-block;
  padding: 5px 14px;
  font-size: 12px;
  font-weight: 500;
  color: var(--c-text-muted);
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  border-radius: 20px;
  white-space: nowrap;
  transition: border-color .2s, color .2s;
}

.pill:hover {
  border-color: var(--c-primary);
  color: var(--c-primary);
}

.pill-accent {
  color: var(--c-primary);
  background: var(--c-primary-bg);
  border-color: transparent;
  font-weight: 600;
}

.danmaku-layer {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: 0;
}

.danmaku-item {
  position: absolute;
  left: var(--x);
  bottom: -40px;
  font-size: 16px;
  font-weight: 700;
  color: rgba(79,110,247,0.18);
  opacity: 0;
  white-space: nowrap;
  letter-spacing: 1px;
  animation: danmakuFloatUp var(--dur) ease-in-out infinite;
  animation-delay: var(--delay);
}

.login-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-lg);
  padding: 32px 40px;
  width: 100%;
  max-width: 500px;
  box-shadow: var(--shadow);
  position: relative;
  z-index: 1;
  animation: fadeInUp 0.6s ease 0.4s backwards;
}
.lc-header {
  text-align: center;
  margin-bottom: 28px;
}

.tab-switcher {
  display: flex;
  gap: 0;
  margin-bottom: 24px;
  background: var(--c-bg);
  border-radius: var(--radius);
  padding: 3px;
}
.tab-btn {
  flex: 1;
  padding: 10px 0;
  border: none;
  background: transparent;
  border-radius: 7px;
  font-size: 14px;
  font-weight: 600;
  color: var(--c-text-secondary);
  cursor: pointer;
  transition: all .2s;
}
.tab-btn.active {
  background: var(--c-surface);
  color: var(--c-text);
  box-shadow: 0 1px 3px rgba(0,0,0,.08);
}
.tab-btn:hover:not(.active) { color: var(--c-text); }

.lc-header h2 { font-size: 20px; font-weight: 700; margin-bottom: 6px; color: var(--c-text); }
.lc-header p { font-size: 13px; color: var(--c-text-muted); }

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 18px;
  text-align: left;
}
.field label {
  font-size: 14px;
  font-weight: 500;
  color: var(--c-text-secondary);
}
.field input {
  height: 48px;
  padding: 0 14px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  background: var(--c-bg);
  color: var(--c-text);
  font-size: 14px;
  outline: none;
  transition: border-color .15s, box-shadow .15s;
}
.field input:focus {
  border-color: var(--c-primary);
  box-shadow: 0 0 0 3px rgba(79,110,247,.12);
  background: var(--c-surface);
}
.field input::placeholder { color: var(--c-text-muted); }

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px 20px;
  border: none;
  border-radius: var(--radius-sm);
  font-weight: 600;
  font-size: 13.5px;
  cursor: pointer;
  transition: all .15s;
  white-space: nowrap;
}
.btn-primary {
  background: var(--c-primary);
  color: #fff;
  box-shadow: 0 2px 8px rgba(79,110,247,.25);
}
.btn-primary:hover { background: var(--c-primary-hover); box-shadow: 0 4px 14px rgba(79,110,247,.3); transform: translateY(-1px); }
.btn-primary:disabled { opacity: .55; cursor: not-allowed; transform: none; }
.btn-ghost {
  background: transparent;
  color: var(--c-text-secondary);
  padding: 6px 12px;
}
.btn-ghost:hover { color: var(--c-primary); background: var(--c-primary-bg); }
.btn-lg { padding: 12px 28px; font-size: 15px; }
.btn-block { width: 100%; }
.btn-loading { display: flex; align-items: center; gap: 8px; }

.spinner, .spinner-lg {
  border: 2.5px solid var(--c-border);
  border-top-color: var(--c-primary);
  border-radius: 50%;
  animation: spin .65s linear infinite;
}
.spinner { width: 16px; height: 16px; }
.spinner-lg { width: 36px; height: 36px; margin: 0 auto 12px; }
.btn-primary .spinner { border-color: rgba(255,255,255,.3); border-top-color: #fff; }

.all-done-wrapper {
  min-height: calc(100vh - var(--topbar-h) - 64px);
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 40px 20px;
}
.done-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-xl);
  padding: 48px 40px;
  text-align: center;
  max-width: 460px;
  width: 100%;
  box-shadow: var(--shadow);
}
.fade-in-enter-active {
  animation: fadeInUp 0.5s ease;
}
.fade-out-leave-active {
  animation: fadeOutDown 0.4s ease forwards;
}
.done-icon {
  margin-bottom: 20px;
  animation: scaleIn 0.6s ease-out 0.1s backwards;
}
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@keyframes fadeOutDown {
  from {
    opacity: 1;
    transform: translateY(0);
  }
  to {
    opacity: 0;
    transform: translateY(20px);
  }
}
@keyframes scaleIn {
  from {
    opacity: 0;
    transform: scale(0.7);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
.done-card h1 {
  font-size: 26px;
  font-weight: 700;
  color: var(--c-text);
  margin-bottom: 8px;
}
.done-card p {
  font-size: 14px;
  color: var(--c-text-secondary);
  margin-bottom: 24px;
}
.countdown {
  font-size: 15px;
  font-weight: 600;
  color: var(--c-primary);
  margin-bottom: 24px;
}

.error-card .countdown.error-countdown {
  color: var(--c-danger);
}

.error-icon {
  margin-bottom: 20px;
  animation: scaleIn 0.6s ease-out 0.1s backwards;
}

.btn-danger {
  background: var(--c-danger);
  color: #fff;
  box-shadow: 0 2px 8px rgba(239,68,68,.25);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px 20px;
  border: none;
  border-radius: var(--radius-sm);
  font-weight: 600;
  font-size: 13.5px;
  cursor: pointer;
  transition: all .15s;
}
.btn-danger:hover { background: #dc2626; box-shadow: 0 4px 14px rgba(239,68,68,.3); transform: translateY(-1px); }
.btn-danger:disabled { opacity: .55; cursor: not-allowed; transform: none; }

.failed-list {
  text-align: left;
  margin: 12px auto 20px;
  max-width: 320px;
}
.failed-item {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid rgba(239,68,68,.15);
  font-size: 13px;
}
.fl-name { font-weight: 600; color: var(--c-text); }
.fl-error { color: var(--c-danger); font-size: 12px; }

.partial-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 12px 18px;
  background: var(--c-warning-bg);
  border: 1px solid rgba(245,158,11,.3);
  border-radius: var(--radius);
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--c-warning);
  font-weight: 500;
}
.pw-tag {
  padding: 2px 10px;
  background: rgba(245,158,11,.15);
  border-radius: 12px;
  font-size: 11.5px;
  color: #b45309;
  font-weight: 600;
}
.pw-tag-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.btn-relogin {
  padding: 2px 10px;
  font-size: 11.5px;
  font-weight: 600;
  border-radius: 12px;
  border: 1px solid rgba(234, 179, 8, .6);
  background: rgba(234, 179, 8, .15);
  color: #a16207;
  cursor: pointer;
  transition: all .15s;
  white-space: nowrap;
}
.btn-relogin:hover {
  background: rgba(234, 179, 8, .3);
  border-color: #eab308;
}

/* 重新输入密码弹窗 */
.relogin-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0,0,0,.45);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn .15s ease;
}
.relogin-box {
  background: #fff;
  border-radius: 14px;
  width: 380px;
  max-width: 92vw;
  box-shadow: 0 20px 60px rgba(0,0,0,.2);
  overflow: hidden;
  animation: slideUp .2s ease;
}
.relogin-header {
  padding: 20px 24px 0;
  position: relative;
}
.relogin-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
}
.relogin-sub {
  display: block;
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
}
.relogin-close {
  position: absolute;
  top: 16px;
  right: 16px;
  background: none;
  border: none;
  font-size: 22px;
  color: #94a3b8;
  cursor: pointer;
  line-height: 1;
  padding: 0;
}
.relogin-close:hover { color: #475569; }
.relogin-body {
  padding: 16px 24px;
}
.relogin-label {
  display: block;
  font-size: 13px;
  color: #64748b;
  margin-bottom: 8px;
}
.relogin-input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  transition: border-color .15s;
  box-sizing: border-box;
}
.relogin-input:focus {
  border-color: #4f6ef7;
  box-shadow: 0 0 0 3px rgba(79,110,247,.12);
}
.relogin-footer {
  padding: 12px 24px 20px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes slideUp {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

.submitted-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 18px;
  background: var(--c-primary-bg);
  border: 1px solid rgba(79,110,247,.3);
  border-radius: var(--radius);
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--c-primary);
  font-weight: 500;
}
.submitted-banner strong {
  font-weight: 700;
}

.inprogress-card h1 {
  color: var(--c-primary);
}
.inprogress-icon {
  margin-bottom: 20px;
  animation: scaleIn 0.6s ease-out 0.1s backwards;
}

.results {
  padding: 24px 0 40px;
  position: relative;
  animation: fadeInUp 0.4s ease;
}
.rescan-overlay {
  position: absolute;
  inset: 0;
  background: rgba(255,255,255,.82);
  backdrop-filter: blur(4px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 10;
  border-radius: var(--radius);
  gap: 12px;
}
.rescan-overlay p {
  font-size: 14px;
  color: var(--c-text-secondary);
  font-weight: 500;
}

.results-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 20px;
  padding: 14px 18px;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
}
.rt-student {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--c-primary);
  padding: 4px 14px;
  background: var(--c-primary-bg);
  border-radius: 20px;
  white-space: nowrap;
}
.rt-student svg { color: var(--c-primary); flex-shrink: 0; }
.rt-info { display: flex; gap: 8px; flex-wrap: wrap; flex: 1; }
.rt-actions { display: flex; gap: 10px; align-items: center; flex-shrink: 0; }
.btn-outline {
  background: transparent;
  border: 1px solid var(--c-border);
  color: var(--c-text-secondary);
}
.btn-outline:hover { border-color: var(--c-primary); color: var(--c-primary); background: var(--c-primary-bg); }
.btn-back-home { font-size: 12.5px; padding: 6px 14px; }
.rt-pill {
  padding: 3px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}
.rt-pill.ok { background: var(--c-success-bg); color: var(--c-success); }
.rt-pill.total { background: var(--c-info-bg); color: var(--c-info); }
.rt-pill.pending { background: var(--c-warning-bg); color: var(--c-warning); }

.plan-select { margin-bottom: 24px; }
.plan-select h3 {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--c-text);
}
.plan-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}
.plan-card {
  background: var(--c-surface);
  border: 1.5px solid var(--c-border);
  border-radius: var(--radius);
  padding: 22px 16px;
  text-align: center;
  cursor: pointer;
  transition: all .2s;
  position: relative;
}
.plan-card:hover { border-color: var(--c-primary); box-shadow: var(--shadow); }
.plan-card.active {
  border-color: var(--c-primary);
  background: var(--c-primary-bg);
  box-shadow: 0 0 0 1px var(--c-primary);
}
.plan-badge {
  position: absolute;
  top: -10px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--c-primary);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 12px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.plan-badge.muted { background: #6b7280; }
.plan-badge.premium { background: #8b5cf6; }
.plan-icon {
  margin-bottom: 10px;
  display: flex;
  justify-content: center;
}
.plan-highlight {
  margin-top: 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--c-primary);
  background: var(--c-primary-bg);
  padding: 2px 8px;
  border-radius: 8px;
  display: inline-block;
}
.plan-name { font-size: 15px; font-weight: 700; color: var(--c-text); margin-bottom: 2px; }
.plan-desc { font-size: 12.5px; color: var(--c-text-secondary); font-weight: 600; margin-bottom: 12px; }
.plan-price-row {
  display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 10px;
}
.ppr-item {
  display: flex; flex-direction: column; align-items: center; min-width: 56px;
}
.ppr-label { font-size: 10px; color: var(--c-text-muted); font-weight: 500; text-transform: uppercase; }
.ppr-price { font-size: 20px; font-weight: 800; color: var(--c-primary); line-height: 1.2; }
.ppr-price.dimmed { color: var(--c-text-muted); opacity: 0.4; }
.ppr-price.na { color: var(--c-text-muted); font-size: 14px; font-weight: 600; }
.ppr-sub { font-size: 9.5px; color: var(--c-text-muted); margin-top: 1px; }
.ppr-sub.na { color: var(--c-text-muted); opacity: 0.5; }
.ppr-divider { width: 1px; height: 28px; background: #e2e8f0; flex-shrink: 0; }
.plan-short-desc { font-size: 11px; color: var(--c-text-muted); margin-bottom: 4px; line-height: 1.4; }
.plan-extra {
  margin-top: 6px; padding: 6px 12px; border-radius: 8px;
  background: #f3e8ff; color: #7c3aed; font-size: 11px; font-weight: 600;
  display: flex; align-items: center; gap: 5px; justify-content: center;
}

/* Plan tags */
.plan-card-top { height: 22px; display: flex; align-items: center; justify-content: center; margin-bottom: 4px; }
.plan-tag {
  padding: 3px 10px; border-radius: 10px; font-size: 10.5px; font-weight: 700;
}
.tag-danger { background: #fef2f2; color: #dc2626; }
.tag-green { background: #f0fdf4; color: #16a34a; }
.tag-purple { background: #f3e8ff; color: #7c3aed; }
.tag-blue { background: #eef1fe; color: #4f6ef7; }

/* Scenario banners */
.scenario-banner {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 14px 18px; border-radius: 12px; margin-bottom: 18px;
}
.scenario-banner svg { flex-shrink: 0; margin-top: 1px; }
.sb-body { display: flex; flex-direction: column; gap: 3px; }
.sb-body strong { font-size: 13px; font-weight: 700; }
.sb-body span { font-size: 12.5px; line-height: 1.5; }
.sb-body strong strong { color: inherit; }
.exam-banner { background: #fffbeb; color: #92400e; border: 1px solid #fcd34d; }
.video-banner { background: #f0fdf4; color: #166534; border: 1px solid #86efac; }
.both-banner { background: #eef1fe; color: #3730a3; border: 1px solid #a5b4fc; }

/* Unsuitable & recommended & best-value cards */
.plan-card.unsuitable {
  opacity: 0.4; cursor: not-allowed;
  border-color: #e2e8f0; background: #f1f5f9;
}
.plan-card.unsuitable:hover { border-color: #e2e8f0; transform: none; }
.plan-card.recommended {
  border-color: #22c55e; background: #f0fdf4;
}
.plan-card.best-value {
  border-color: #8b5cf6; background: #faf5ff;
}
.plan-card.best-value::before {
  content: ''; position: absolute; top: -1px; left: -1px; right: -1px; bottom: -1px;
  border-radius: 14px; background: linear-gradient(135deg, #8b5cf6, #4f6ef7);
  z-index: -1; opacity: 0.12;
}
.plan-price { font-size: 26px; font-weight: 800; color: var(--c-primary); }
.plan-card.single { max-width: 340px; margin: 0 auto; cursor: default; }

.platform-block {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: 18px 20px;
  margin-bottom: 14px;
}
.pb-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.pb-check input { cursor: pointer; }
.pb-badge {
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 11.5px;
  font-weight: 600;
}
.pb-badge.ok { background: var(--c-success-bg); color: var(--c-success); }
.pb-badge.fail { background: var(--c-danger-bg); color: var(--c-danger); }
.pb-name { font-weight: 500; font-size: 13px; color: var(--c-text); }
.pb-count { font-size: 12px; color: var(--c-text-muted); margin-left: auto; }

.course-list { display: flex; flex-direction: column; }
.course-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-top: 1px solid #f3f4f6;
}
.course-row.done { opacity: .5; }
.cr-check input { cursor: pointer; }
.cr-name {
  flex: 1;
  font-size: 13.5px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cr-meta { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.cr-bar {
  width: 70px;
  height: 5px;
  background: #f1f5f9;
  border-radius: 3px;
  overflow: hidden;
}
.cr-bar-fill { height: 100%; border-radius: 3px; background: var(--c-primary); transition: width .3s; }
.cr-bar-fill.done { background: var(--c-success); }
.cr-bar-fill.low { background: var(--c-warning); }
.cr-pct { font-size: 11px; color: var(--c-text-muted); min-width: 34px; text-align: right; }
.cr-pill {
  padding: 1.5px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}
.cr-pill.warn { background: var(--c-warning-bg); color: var(--c-warning); }
.cr-pill.ok { background: var(--c-success-bg); color: var(--c-success); }
.cr-pill.exam { background: var(--c-info-bg); color: var(--c-info); font-size: 10px; }
.cr-pill.deleted { background: #f3f4f6; color: #9ca3af; font-size: 10px; text-decoration: line-through; }

.summary-bar {
  position: sticky;
  bottom: 0;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: 16px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: var(--shadow-md);
  margin-bottom: 24px;
}
.sb-left { display: flex; gap: 20px; }
.sb-item { font-size: 13px; color: var(--c-text-secondary); }
.sb-item strong { color: var(--c-primary); }
.sb-right { display: flex; align-items: center; gap: 18px; }
.sb-detail {
  display: flex; flex-direction: column; align-items: flex-end; gap: 4px;
}
.sb-detail-item { font-size: 11.5px; color: var(--c-text-muted); white-space: nowrap; }
.sb-price { font-size: 24px; font-weight: 800; color: var(--c-danger); }

.done-bar {
  justify-content: center;
  gap: 16px;
  color: var(--c-success);
  font-weight: 500;
}
.done-icon {
  width: 26px; height: 26px;
  border-radius: 50%;
  background: var(--c-success);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15,23,42,.4);
  backdrop-filter: blur(4px);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 500;
}
.modal-overlay.show { display: flex; }
.modal-box {
  background: var(--c-surface);
  border-radius: var(--radius-xl);
  padding: 32px;
  width: 400px;
  text-align: center;
  box-shadow: var(--shadow-lg);
  animation: fadeIn .3s ease;
}
.modal-box h3 { font-size: 18px; font-weight: 700; margin-bottom: 4px; }
.modal-amount { font-size: 40px; font-weight: 800; color: var(--c-primary); margin: 16px 0 4px; }
.pay-amount-warn { text-align: center; font-size: 12px; color: #ef4444; margin: 0 0 16px; font-weight: 500; }

.pay-error {
  background: var(--c-danger-bg); color: var(--c-danger);
  border-radius: var(--radius-sm); padding: 10px 14px;
  font-size: 12.5px; margin-bottom: 16px; text-align: left;
}

.pay-method-tabs {
  display: flex; gap: 0; margin-bottom: 20px;
  background: var(--c-bg); border-radius: var(--radius); padding: 3px;
}
.pm-tab {
  flex: 1; padding: 8px 0; border: none; background: transparent;
  border-radius: 7px; font-size: 13px; font-weight: 600;
  color: var(--c-text-secondary); cursor: pointer; transition: all .2s;
}
.pm-tab.active { background: #fff; color: var(--c-text); box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.pm-tab:hover:not(.active) { color: var(--c-text); }

.qr-section { margin: 16px 0; }
.pay-qr-img {
  width: 200px; height: 200px; border-radius: var(--radius);
  border: 2px solid var(--c-border); background: #fff; padding: 8px;
}
.pay-qr-placeholder {
  width: 200px; height: 200px; margin: 0 auto;
  display: flex; align-items: center; justify-content: center;
  background: var(--c-bg); border-radius: var(--radius); border: 2px dashed var(--c-border);
  font-size: 13px; color: var(--c-text-muted);
}
.qr-label { font-size: 12px; color: var(--c-text-muted); margin-top: 10px; }

.pay-link-btn {
  text-decoration: none; justify-content: center; display: flex;
  align-items: center; gap: 6px;
}


.page-footer {
  text-align: center;
  padding: 0 24px 12px;
  margin-top: 20px;
}
.footer-divider-wrap {
  position: relative;
  height: 1px;
  overflow: visible;
}
.footer-divider {
  height: 1px;
  background: var(--c-border);
}
.footer-divider-wrap .danmaku-layer {
  position: absolute;
  top: -400px;
  left: 0;
  right: 0;
  height: 400px;
  overflow: hidden;
  pointer-events: none;
  z-index: 0;
}
.footer-divider-wrap .danmaku-item {
  bottom: 0;
  top: auto;
  animation: danmakuFloatUp var(--dur) ease-in-out infinite;
  animation-delay: var(--delay);
}
@keyframes danmakuFloatUp {
  0% {
    opacity: 0;
    transform: translateY(0);
  }
  10% {
    opacity: 1;
  }
  90% {
    opacity: 1;
  }
  100% {
    opacity: 0;
    transform: translateY(-350px);
  }
}
.footer-ads {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 10px 0 0;
  flex-wrap: wrap;
}
.footer-ad-link {
  font-size: 12px;
  color: var(--c-text-muted);
  text-decoration: none;
  padding: 3px 12px;
  border-radius: 20px;
  background: var(--c-bg);
  transition: all .15s;
}
.footer-ad-link:hover { color: var(--c-primary); background: var(--c-primary-bg); text-decoration: none; }
.footer-brand {
  padding: 10px 0 0;
  font-size: 12px;
  color: var(--c-text-muted);
  letter-spacing: 0.5px;
}
.footer-brand strong {
  font-weight: 700;
}

.float-earn-btn {
  position: fixed; right: 0;
  z-index: 200; background: var(--c-primary); color: #fff;
  padding: 12px 10px; border-radius: 10px 0 0 10px; text-decoration: none !important;
  font-size: 12px; font-weight: 600; display: flex; flex-direction: column;
  align-items: center; gap: 4px; box-shadow: -2px 2px 12px rgba(79,110,247,.35);
  transition: background .2s, box-shadow .2s; writing-mode: horizontal-tb;
  cursor: grab; user-select: none; -webkit-user-select: none;
  touch-action: none;
}
.float-earn-btn:hover {
  padding-right: 14px; background: var(--c-primary-hover);
  text-decoration: none; box-shadow: -4px 4px 20px rgba(79,110,247,.45);
}
.float-earn-btn:active { cursor: grabbing; }
.feb-text { white-space: nowrap; letter-spacing: 1px; }

@media (max-width: 768px) {
  .plan-grid { grid-template-columns: 1fr; }
  .summary-bar { flex-direction: column; gap: 12px; }
  .sb-left, .sb-right { width: 100%; justify-content: center; }
  .danmaku-layer { display: none; }

  .content-wrapper { padding: 0 12px; }

  .landing-center {
    padding: 24px 12px 0;
    justify-content: center;
    gap: 0;
  }
  .lc-title { font-size: 24px; margin-bottom: 8px; }
  .lc-subtitle { font-size: 12px; margin-bottom: 14px; }
  .lc-pills { gap: 6px; margin-bottom: 18px; }
  .pill { padding: 3px 10px; font-size: 11px; }
  .login-card { max-width: 100%; padding: 20px 16px; margin-top: 20px; }
  .login-card .field { margin-bottom: 14px; }
  .login-card .btn-lg { padding: 12px 20px; font-size: 15px; }

  .upgrade-banner {
    flex-direction: column;
    align-items: flex-start;
    padding: 10px 12px;
  }
  .upgrade-banner-actions { width: 100%; justify-content: flex-end; }

  /* 结果页：顶栏固定 + 底栏固定 + 列表滚动 */
  .results {
    display: flex;
    flex-direction: column;
    padding: 12px 0 140px;
    position: relative;
    min-height: 100vh;
  }
  .results-topbar {
    flex-shrink: 0;
    flex-wrap: wrap;
    gap: 8px;
    padding: 10px 12px;
    margin-bottom: 6px;
  }
  .rt-student { font-size: 12px; padding: 3px 10px; }
  .rt-actions { width: 100%; justify-content: center; }
  .rt-info { flex-wrap: wrap; gap: 4px; }
  .rt-pill { font-size: 11px; padding: 2px 8px; }
  .partial-warning, .submitted-banner {
    flex-shrink: 0;
    font-size: 12px;
    padding: 8px 12px;
  }
  .plan-select {
    margin-bottom: 6px;
  }
  .plan-card.single { max-width: 100%; margin: 0; }
  .plan-card { padding: 14px 12px; }
  .ppr-price { font-size: 18px; }
  .scenario-banner { padding: 10px 14px; gap: 10px; font-size: 12px; margin-bottom: 6px; }

  .platform-block {
    padding: 12px 14px;
    margin-bottom: 6px;
  }
  .pb-header { gap: 8px; margin-bottom: 8px; }
  .pb-count { font-size: 11px; }
  .course-row {
    padding: 8px 0;
    gap: 8px;
    flex-wrap: wrap;
  }
  .cr-name { font-size: 13px; flex: 1 1 100%; order: -1; }
  .cr-check { order: 0; }
  .cr-meta { gap: 4px; flex-wrap: wrap; flex: 1; }
  .cr-bar { width: 40px; }
  .cr-pct { font-size: 10px; min-width: 28px; }
  .cr-pill { font-size: 10px; padding: 1px 6px; }

  .summary-bar {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    flex-direction: column;
    gap: 10px;
    padding: 12px 16px;
    border-radius: 0;
    border: none;
    border-top: 1px solid var(--c-border);
    background: var(--c-surface);
    box-shadow: 0 -4px 16px rgba(0,0,0,.08);
    z-index: 50;
    margin-bottom: 0;
  }
  .sb-left { gap: 12px; }
  .sb-item { font-size: 12px; }
  .sb-right { flex-direction: column; align-items: center; gap: 8px; width: 100%; }
  .sb-detail { flex-direction: row; flex-wrap: wrap; gap: 6px; justify-content: center; }
  .sb-detail-item { font-size: 11px; }
  .sb-price { font-size: 20px; }
  .sb-right .btn-lg { width: 100%; }

  .results .plan-select,
  .results .platform-block {
    margin-bottom: 6px;
  }

  .page-footer { padding: 12px 16px 16px; margin-top: 0; }
  .page-footer.hide-on-mobile-results { display: none; }

  /* 支付弹窗 */
  .modal-box.pay-modal {
    width: 92vw;
    max-width: none;
    padding: 24px 20px;
    border-radius: var(--radius-lg);
  }
  .modal-amount { font-size: 32px; }
  .pay-qr-img { width: 180px; height: 180px; }
  .pay-qr-placeholder { width: 180px; height: 180px; }

  .float-earn-btn {
    padding: 8px 8px;
    font-size: 11px;
  }

  /* Done/error cards */
  .done-card { padding: 32px 20px; }
  .done-card h1 { font-size: 22px; }
  .all-done-wrapper { padding: 24px 16px; min-height: auto; }

  /* Relogin dialog */
  .relogin-box { width: 90vw; }
  .relogin-header { padding: 16px 18px 0; }
  .relogin-body { padding: 12px 18px; }
  .relogin-footer { padding: 10px 18px 16px; }
}

/* 系统公告弹窗 */
.announcement-overlay {
  position: fixed;
  inset: 0;
  z-index: 9998;
  background: rgba(0,0,0,.45);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn .15s ease;
}
.announcement-box {
  background: #fff;
  border-radius: 16px;
  width: 420px;
  max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0,0,0,.2);
  overflow: hidden;
  animation: slideUp .2s ease;
}
.announcement-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 24px 24px 0;
  color: var(--c-primary, #4f6ef7);
}
.announcement-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--c-text, #1e293b);
}
.announcement-header svg {
  flex-shrink: 0;
  color: var(--c-primary, #4f6ef7);
}
.announcement-body {
  padding: 16px 24px 24px;
  font-size: 14px;
  color: var(--c-text-secondary, #475569);
  line-height: 1.7;
  max-height: 50vh;
  overflow-y: auto;
  word-break: break-word;
}
.announcement-confirm {
  margin: 0 24px 24px;
  width: calc(100% - 48px);
}

@media (max-width: 768px) {
  .announcement-box { width: 92vw; }
  .announcement-header { padding: 18px 18px 0; }
  .announcement-body { padding: 12px 18px 18px; }
  .announcement-confirm { margin: 0 18px 18px; width: calc(100% - 36px); }
}
</style>

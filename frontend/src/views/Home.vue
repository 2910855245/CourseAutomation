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
  userRole, isPrivileged, isRegularUser, detectUserRole, handleVisibilityChange,
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
  payBatchId, payBatchOutTradeNo, showPaySuccess, paySuccessAmount, payTimedOut,
  handleOrderSuccess, goToOrders, submitAndPay, onPaySuccessDone, closePay, savePayQr, switchPayMethod,
  pct, pctClass, LS_KEY,
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
  if (scanDone.value && username.value.trim()) {
    try { const r = await api.orders.activeCourses(username.value.trim()); const activeIds: string[] = r?.data || []; for (const cid of activeIds) submittedCourseIds.value.add(cid) } catch {}
  }
})
</script>

<template>
  <div class="page">
    <AppTopbar title="Fuk 文理网课" :show-role-badge="true" />

    <div class="content-wrapper">
      <div v-if="allDone" class="all-done-wrapper">
        <div :class="['done-card', isLeaving ? 'fade-out-leave-active' : 'fade-in-enter-active']">
          <div class="done-icon">
            <svg width="72" height="72" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="11" stroke="#17181b" stroke-width="2" fill="rgba(20,20,24,.05)"/>
              <path d="M7 13l3 3 7-7" stroke="#17181b" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <h1>任务已完成</h1>
          <p>所有课程均已 100% 完成</p>
          <div class="countdown">{{ countdown }} 秒后返回登录页</div>
        </div>
      </div>

      <div v-else-if="allInProgress" class="all-done-wrapper">
        <div :class="['done-card', 'inprogress-card', isLeaving ? 'fade-out-leave-active' : 'fade-in-enter-active']">
          <div class="done-icon inprogress-icon">
            <svg width="72" height="72" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="11" stroke="#17181b" stroke-width="2" fill="rgba(20,20,24,.05)"/>
              <path d="M12 6v6l4 2" stroke="#17181b" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <h1>所有任务正在进行中</h1>
          <p>所有课程已提交下单，系统正在自动刷课处理中，请耐心等待</p>
          <div class="countdown">{{ autoRedirectCountdown }} 秒后自动跳转到订单页面</div>
        </div>
      </div>

      <div v-else-if="loginError === 'all'" class="all-done-wrapper">
        <div :class="['done-card', 'error-card', isLeaving ? 'fade-out-leave-active' : 'fade-in-enter-active']">
          <div class="done-icon error-icon">
            <svg width="72" height="72" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="11" stroke="#dc2626" stroke-width="2" fill="rgba(220,38,38,.06)"/>
              <path d="M15 9l-6 6M9 9l6 6" stroke="#dc2626" stroke-width="2.5" stroke-linecap="round"/>
            </svg>
          </div>
          <h1>登录失败</h1>
          <p v-if="activeTab === 'chaoxing'">学习通登录失败，请检查账号密码是否正确</p>
          <p v-else>所有平台均登录失败，请检查学号密码是否正确</p>
          <div class="countdown error-countdown">{{ loginErrorCountdown }} 秒后自动返回</div>
        </div>
      </div>

      <template v-else>
        <div v-if="!scanDone" class="landing">
          <div class="login-head">
            <h1>登录平台账号</h1>
            <p>输入账号密码，系统自动扫描未完成课程并生成任务。</p>
          </div>

          <div class="login-card">
            <div class="tab-switcher minimal">
              <button :class="['tab-btn', { active: activeTab === 'school' }]" @click="activeTab = 'school'">
                学校平台
              </button>
              <button :class="['tab-btn', { active: activeTab === 'chaoxing' }]" @click="activeTab = 'chaoxing'">
                学习通
              </button>
            </div>

            <template v-if="activeTab === 'school'">
              <div class="field minimal">
                <label>学号</label>
                <input v-model="username" placeholder="请输入学号" :disabled="scanning" />
              </div>
              <div class="field minimal">
                <label>密码</label>
                <input v-model="password" type="password" placeholder="请输入平台密码" :disabled="scanning" @keyup.enter="startScan" />
              </div>
              <button class="btn btn-primary btn-block" :disabled="scanning" @click="startScan">
                <span v-if="!scanning">登录</span>
                <span v-else class="btn-loading">
                  <span class="spinner"></span>
                  扫描中...
                </span>
              </button>
            </template>

            <template v-if="activeTab === 'chaoxing'">
              <div class="field minimal">
                <label>账号</label>
                <input v-model="chaoxingUsername" placeholder="请输入手机号" :disabled="scanning" />
              </div>
              <div class="field minimal">
                <label>密码</label>
                <input v-model="chaoxingPassword" type="password" placeholder="请输入密码" :disabled="scanning" @keyup.enter="startChaoxingScan" />
              </div>
              <button class="btn btn-primary btn-block" :disabled="scanning" @click="startChaoxingScan">
                <span v-if="!scanning">登录</span>
                <span v-else class="btn-loading">
                  <span class="spinner"></span>
                  扫描中...
                </span>
              </button>
            </template>
          </div>

          <p class="login-foot">支持粟湾、劳动教育、中嘉鑫盛、学习通等平台。</p>
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
        <div class="results-head">
          <div class="rh-left">
            <h2 class="rh-title">选择需要代刷的课程</h2>
            <div class="rh-meta">
              <span v-if="studentName" class="rh-student">{{ studentName }}</span>
              <template v-if="activeTab === 'chaoxing' && chaoxingInfo">
                <span v-if="chaoxingInfo.school" class="rh-meta-item">{{ chaoxingInfo.school }}</span>
                <span v-if="chaoxingInfo.workPending > 0" class="rh-meta-item">{{ chaoxingInfo.workPending }} 个待完成作业</span>
                <span class="rh-meta-item">{{ chaoxingInfo.pendingCount }} 门待处理</span>
              </template>
              <template v-else>
                <span class="rh-meta-item">{{ visiblePlatforms.filter(p => p.status === 'ok').length }} 个平台已登录</span>
                <span class="rh-meta-item">{{ visiblePlatforms.reduce((s,p) => s + p.courses.length, 0) }} 门课程</span>
                <span class="rh-meta-item">{{ visiblePlatforms.reduce((s,p) => s + p.courses.filter(c => !isCourseDoneOrSubmitted(c)).length, 0) }} 门待处理</span>
              </template>
            </div>
          </div>
          <div class="rt-actions">
            <button class="btn btn-ghost" @click="rescan">重新扫描</button>
            <button class="btn btn-outline btn-back-home" @click="resetScan">返回主页</button>
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
            <div class="plan-card-top"><span class="plan-tag tag-green">推荐</span></div>
            <div class="plan-icon" style="color:#17181b">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="23 7 16 12 7 7 11 3 23 3 23 7"/><polygon points="12 7 5 12 1 9 1 13 5 16 12 13"/><polygon points="12 13 5 16 1 13 1 17 5 20 12 17"/><polygon points="22 10 17 13 17 17 22 20 23 16"/><polygon points="23 4 19 6 19 10 23 8"/></svg>
            </div>
            <div class="plan-name">视频刷课</div>
            <div class="plan-desc">仅刷视频课程</div>
            <div class="plan-short-desc">所选课程考试已完成，仅需刷视频</div>
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
            <div class="plan-card-top"><span class="plan-tag tag-green">推荐</span></div>
            <div class="plan-icon" style="color:#17181b">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
            </div>
            <div class="plan-name">考试答题</div>
            <div class="plan-desc">AI智能答题考试</div>
            <div class="plan-short-desc">所选课程视频已完成，仅需答题</div>
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
            <div class="plan-card-top"><span class="plan-tag tag-blue">标准计费</span></div>
            <div class="plan-icon" style="color:#17181b">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            </div>
            <div class="plan-name">视频 + 考试</div>
            <div class="plan-desc">视频刷课 + 考试答题</div>
            <div class="plan-short-desc">视频和考试打包计费</div>
          </div>
        </div>
        </template>

        <div
          v-for="(p, pi) in visiblePlatforms"
          :key="p.website_id"
          class="platform-block"
          :style="{ animationDelay: Math.min(pi, 8) * 60 + 'ms' }"
        >
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
          <p class="pm-timeout-note">支付查询已超时，但订单已创建成功。请到订单页查看支付状态。</p>
          <button class="btn btn-primary btn-block" @click="goToOrders(); closePay()">查看订单</button>
        </template>
        <template v-else>
        <h3>确认支付</h3>
        <div class="modal-amount">¥{{ payTotal.toFixed(2) }}</div>
        <p class="pay-amount-warn">请务必支付相同金额，多一分少一分都无法检测到</p>
        <div v-if="payError" class="pay-error">{{ payError }}</div>

        <div class="pay-method-tabs">
          <button :class="['pm-tab', { active: selectedPayMethod === 'ypay_wxpay' }]" @click="switchPayMethod('ypay_wxpay')">微信</button>
          <button :class="['pm-tab', { active: selectedPayMethod === 'ypay_alipay' }]" @click="switchPayMethod('ypay_alipay')">支付宝</button>
        </div>

        <!-- QR code section -->
        <div class="qr-section">
          <img v-if="payQrCode" :src="payQrCode" alt="支付二维码" class="pay-qr-img" />
          <div v-else class="pay-qr-placeholder">生成二维码中...</div>
          <p class="qr-label">保存二维码后使用{{ { ypay_alipay: '支付宝', ypay_wxpay: '微信' }[selectedPayMethod] || '扫码' }}扫一扫支付</p>
        </div>
        <button
          v-if="payQrCode"
          class="btn btn-primary btn-block pay-save-btn"
          :class="{ wechat: selectedPayMethod === 'ypay_wxpay' }"
          @click="savePayQr"
        >保存二维码</button>

        <button class="btn btn-ghost btn-block pay-cancel-btn" @click="closePay">取消支付</button>
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
          <div class="announcement-body">{{ announcementContent }}</div>
          <button class="btn btn-primary btn-block announcement-confirm" @click="dismissAnnouncement">我知道了</button>
        </div>
      </div>
    </Teleport>

    <footer class="page-footer" :class="{ 'hide-on-mobile-results': scanDone }">
      <div class="footer-brand">Fuk 文理网课</div>
    </footer>
  </div>

  <!-- 重新输入密码弹窗 -->
  <Teleport to="body">
    <div v-if="reloginDialog.visible" class="relogin-overlay" @click.self="closeReloginDialog">
      <div class="relogin-box">
        <div class="relogin-header">
          <h3>重新输入密码</h3>
          <span class="relogin-sub">{{ reloginDialog.name }}</span>
          <button class="relogin-close" @click="closeReloginDialog">&times;</button>
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
          <button class="btn btn-ghost" @click="closeReloginDialog">取消</button>
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
/* ============================================================
   Aurora Glass · 深色高级质感 / 极光渐变 / 玻璃拟态
   ============================================================ */
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.content-wrapper {
  flex: 1;
  width: 100%;
  margin: 0 auto;
  padding: 0 24px;
}

/* ---------- 全屏状态卡（完成 / 进行中 / 失败） ---------- */
.all-done-wrapper {
  min-height: calc(100vh - 56px - 64px);
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 40px 20px;
}
.done-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border-light);
  border-radius: 20px;
  padding: 48px 40px;
  text-align: center;
  max-width: 460px;
  width: 100%;
  box-shadow: 0 2px 8px rgba(20,20,24,.07), 0 24px 64px rgba(20,20,24,.12);
}
.fade-in-enter-active {
  animation: fadeInUp .5s cubic-bezier(.32,.72,.35,1);
}
.fade-out-leave-active {
  animation: fadeOutDown .4s cubic-bezier(.32,.72,.35,1) forwards;
}
.done-icon {
  margin-bottom: 20px;
  animation: scaleIn .6s cubic-bezier(.32,.72,.35,1) .1s backwards;
}
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes fadeOutDown {
  from { opacity: 1; transform: translateY(0); }
  to { opacity: 0; transform: translateY(20px); }
}
@keyframes scaleIn {
  from { opacity: 0; transform: scale(.7); }
  to { opacity: 1; transform: scale(1); }
}
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes slideUp {
  from { opacity: 0; transform: translateY(14px) scale(.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.done-card h1 {
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -.01em;
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
}
.error-card .countdown.error-countdown { color: var(--c-danger); }
.inprogress-card h1 { color: var(--c-primary); }

/* ---------- 落地页 ---------- */
.landing {
  width: 100%;
  max-width: 420px;
  margin: 0 auto;
  padding: 56px 20px 72px;
}
.login-head {
  margin-bottom: 28px;
}
.login-head h1 {
  font-size: 22px;
  font-weight: 600;
  color: var(--c-text);
  margin-bottom: 6px;
}
.login-head p {
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--c-text-secondary);
}
.login-foot {
  margin-top: 18px;
  font-size: 12px;
  color: var(--c-text-muted);
  text-align: center;
}

/* ---------- 登录卡片 ---------- */
.login-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 8px;
  padding: 24px;
}

.tab-switcher.minimal {
  display: flex;
  gap: 0;
  margin-bottom: 22px;
  border-bottom: 1px solid var(--c-border-light);
  background: transparent;
  padding: 0;
  border-radius: 0;
}
.tab-switcher.minimal .tab-btn {
  flex: 1;
  padding: 10px 0 12px;
  border: none;
  background: transparent;
  border-radius: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--c-text-secondary);
  cursor: pointer;
  position: relative;
  transition: color .2s ease;
}
.tab-switcher.minimal .tab-btn:hover:not(.active) { color: var(--c-text); }
.tab-switcher.minimal .tab-btn.active {
  color: var(--c-text);
  background: transparent;
  box-shadow: none;
}
.tab-switcher.minimal .tab-btn.active::after {
  content: '';
  position: absolute; left: 0; right: 0; bottom: -1px;
  height: 1.5px;
  background: var(--c-text);
}

.field.minimal {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 16px;
}
.field.minimal label {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--c-text-secondary);
}
.field.minimal input {
  height: 42px;
  padding: 0 12px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-surface);
  color: var(--c-text);
  font-size: 14px;
  outline: none;
  transition: border-color .15s ease, background-color .15s ease;
}
.field.minimal input:hover { border-color: #bdbdc2; }
.field.minimal input:focus {
  border-color: var(--c-text);
  background: var(--c-surface);
}
.field.minimal input::placeholder { color: var(--c-text-muted); }
.field.minimal input:disabled { background: var(--c-surface-2); color: var(--c-text-muted); cursor: not-allowed; }

/* ---------- 按钮 ---------- */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px 18px;
  border: none;
  border-radius: 6px;
  font-weight: 500;
  font-size: 13.5px;
  cursor: pointer;
  transition: background-color .15s ease, opacity .15s ease;
  white-space: nowrap;
}
.btn-primary {
  background: var(--c-text);
  color: #fff;
}
.btn-primary:hover:not(:disabled) { background: #000; }
.btn-primary:active:not(:disabled) { background: #2e2f34; }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.btn-ghost {
  background: transparent;
  color: var(--c-text-secondary);
  padding: 8px 14px;
}
.btn-ghost:hover { color: var(--c-text); background: var(--c-surface-2); }
.btn-outline {
  background: transparent;
  border: 1px solid var(--c-border);
  color: var(--c-text-secondary);
}
.btn-outline:hover {
  border-color: var(--c-text);
  color: var(--c-text);
  background: transparent;
}
.btn-lg { padding: 11px 24px; font-size: 14px; border-radius: 6px; }
.btn-block { width: 100%; }
.btn-loading { display: flex; align-items: center; gap: 8px; }

.spinner, .spinner-lg {
  border: 2px solid var(--c-border);
  border-top-color: var(--c-primary);
  border-radius: 50%;
  animation: spin .65s linear infinite;
}
.spinner { width: 15px; height: 15px; }
.spinner-lg { width: 36px; height: 36px; margin: 0 auto 12px; }
.btn-primary .spinner { border-color: rgba(255,255,255,.25); border-top-color: #fff; }

/* ---------- 结果区 ---------- */
.results {
  padding: 24px 0 40px;
  position: relative;
  animation: fadeInUp .4s cubic-bezier(.32,.72,.35,1);
}
.rescan-overlay {
  position: absolute;
  inset: 0;
  background: rgba(255,255,255,.88);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 10;
  border-radius: 14px;
  gap: 12px;
}
.rescan-overlay p {
  font-size: 14px;
  color: var(--c-text-secondary);
  font-weight: 500;
}

.submitted-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 18px;
  background: var(--c-primary-bg);
  border: 1px solid rgba(20,20,24,.25);
  border-radius: 12px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--c-primary);
  font-weight: 500;
  animation: fadeInUp .4s cubic-bezier(.32,.72,.35,1) backwards;
}
.submitted-banner strong { font-weight: 700; }

.results-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 24px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--c-border-light);
}
.rh-title {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -.015em;
  color: var(--c-text);
}
.rh-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--c-text-secondary);
}
.rh-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 14px;
}
.rh-meta-item + .rh-meta-item::before {
  content: '·';
  color: var(--c-text-muted);
  margin-right: 14px;
}
.rh-student {
  display: inline-flex;
  align-items: center;
  padding: 3px 12px;
  background: var(--c-primary);
  color: #fff;
  border-radius: 980px;
  font-size: 12px;
  font-weight: 600;
}
.rt-actions { display: flex; gap: 10px; align-items: center; flex-shrink: 0; }
.btn-back-home { font-size: 12.5px; padding: 6px 14px; }
.rt-pill {
  padding: 3px 12px;
  border-radius: 980px;
  font-size: 12px;
  font-weight: 600;
}
.rt-pill.ok { background: var(--c-surface-3); color: var(--c-text); }
.rt-pill.total { background: var(--c-surface-3); color: var(--c-text); }
.rt-pill.pending { background: var(--c-surface-3); color: var(--c-text-secondary); }

/* ---------- 场景横幅 & 套餐卡 ---------- */
.plan-select { margin-bottom: 24px; }
.scenario-banner {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 18px;
  border-radius: 14px;
  margin-bottom: 18px;
}
.scenario-banner svg { flex-shrink: 0; margin-top: 1px; }
.sb-body { display: flex; flex-direction: column; gap: 3px; }
.sb-body strong { font-size: 13px; font-weight: 700; }
.sb-body span { font-size: 12.5px; line-height: 1.5; }
.video-banner { background: var(--c-surface-2); color: var(--c-text); border: 1px solid var(--c-border-light); }
.exam-banner { background: var(--c-surface-2); color: var(--c-text); border: 1px solid var(--c-border-light); }
.both-banner { background: var(--c-surface-2); color: var(--c-text); border: 1px solid var(--c-border-light); }

.plan-card {
  background: var(--c-surface);
  border: 1.5px solid var(--c-border-light);
  border-radius: 14px;
  padding: 22px 16px;
  text-align: center;
  transition: all .25s cubic-bezier(.32,.72,.35,1);
  position: relative;
  box-shadow: 0 1px 2px rgba(20,20,24,.06);
  animation: fadeInUp .45s cubic-bezier(.32,.72,.35,1) backwards;
}
.plan-card.single {
  max-width: 340px;
  margin: 0 auto;
  cursor: default;
}
.plan-card.single.active {
  border-color: var(--c-primary);
  box-shadow: 0 0 0 3px rgba(20,20,24,.1), 0 4px 16px rgba(20,20,24,.08);
}
.plan-card-top {
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 4px;
}
.plan-tag {
  padding: 3px 10px;
  border-radius: 980px;
  font-size: 10.5px;
  font-weight: 700;
}
.tag-green { background: var(--c-primary); color: #fff; }
.tag-blue { background: var(--c-primary); color: #fff; }
.plan-icon {
  margin-bottom: 10px;
  display: flex;
  justify-content: center;
}
.plan-name { font-size: 15px; font-weight: 700; color: var(--c-text); margin-bottom: 2px; }
.plan-desc { font-size: 12.5px; color: var(--c-text-secondary); font-weight: 600; margin-bottom: 10px; }
.plan-short-desc { font-size: 11px; color: var(--c-text-muted); line-height: 1.4; }

/* ---------- 平台块 & 课程行 ---------- */
.platform-block {
  background: var(--c-surface);
  border: 1px solid var(--c-border-light);
  border-radius: 14px;
  padding: 18px 20px;
  margin-bottom: 14px;
  box-shadow: 0 1px 2px rgba(20,20,24,.06);
  transition: box-shadow .25s cubic-bezier(.32,.72,.35,1);
  animation: fadeInUp .45s cubic-bezier(.32,.72,.35,1) backwards;
}
.platform-block:hover {
  box-shadow: 0 4px 16px rgba(20,20,24,.08);
}
.pb-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.pb-check input { cursor: pointer; accent-color: var(--c-primary); width: 16px; height: 16px; }
.pb-badge {
  padding: 3px 10px;
  border-radius: 980px;
  font-size: 11.5px;
  font-weight: 600;
}
.pb-badge.ok { background: var(--c-success-bg); color: var(--c-success); }
.pb-badge.fail { background: var(--c-danger-bg); color: var(--c-danger); }
.pb-count { font-size: 12px; color: var(--c-text-muted); margin-left: auto; }

.course-list { display: flex; flex-direction: column; }
.course-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-top: 1px solid var(--c-surface-3);
  transition: opacity .2s;
}
.course-row.done { opacity: .5; }
.cr-check input { cursor: pointer; accent-color: var(--c-primary); width: 16px; height: 16px; }
.cr-check input:disabled { cursor: not-allowed; }
.cr-name {
  flex: 1;
  font-size: 13.5px;
  color: var(--c-text);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cr-meta { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.cr-bar {
  width: 70px;
  height: 5px;
  background: var(--c-surface-3);
  border-radius: 3px;
  overflow: hidden;
}
.cr-bar-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--c-primary);
  transition: width .3s cubic-bezier(.32,.72,.35,1);
}
.cr-bar-fill.done { background: var(--c-text); }
.cr-bar-fill.low { background: #b6b6bc; }
.cr-pct { font-size: 11px; color: var(--c-text-muted); min-width: 34px; text-align: right; }
.cr-pill {
  padding: 2px 8px;
  border-radius: 980px;
  font-size: 11px;
  font-weight: 600;
}
.cr-pill.warn { background: var(--c-surface-3); color: var(--c-text-secondary); }
.cr-pill.ok { background: var(--c-surface-3); color: var(--c-text); }
.cr-pill.exam { background: var(--c-surface-3); color: var(--c-text); font-size: 10px; }
.cr-pill.deleted { background: var(--c-surface-3); color: var(--c-text-muted); font-size: 10px; text-decoration: line-through; }

/* ---------- 底部汇总栏 ---------- */
.summary-bar {
  position: sticky;
  bottom: 12px;
  background: var(--c-surface);
  border: 1px solid var(--c-border-light);
  border: 1px solid var(--c-border-light);
  border-radius: 16px;
  padding: 16px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 8px 24px rgba(20,20,24,.1), 0 24px 64px rgba(20,20,24,.12), inset 0 1px 0 rgba(16,16,20,.03);
  margin-bottom: 24px;
  animation: fadeInUp .5s cubic-bezier(.32,.72,.35,1) backwards;
}
.sb-left { display: flex; gap: 20px; flex-wrap: wrap; }
.sb-item { font-size: 13px; color: var(--c-text-secondary); }
.sb-item strong { color: var(--c-text); }
.sb-right { display: flex; align-items: center; gap: 18px; }
.sb-detail { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
.sb-detail-item { font-size: 11.5px; color: var(--c-text-muted); white-space: nowrap; }
.sb-price {
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -.01em;
  font-variant-numeric: tabular-nums;
  color: var(--c-text);
}

/* ---------- 支付弹窗 ---------- */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(22,22,26,.42);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 500;
}
.modal-overlay.show {
  display: flex;
  animation: fadeIn .2s ease;
}
.modal-box {
  background: var(--c-surface);
  border: 1px solid var(--c-border-light);
  border-radius: 20px;
  padding: 32px;
  width: 400px;
  max-width: calc(100vw - 48px);
  text-align: center;
  box-shadow: 0 8px 20px rgba(20,20,24,.09), 0 32px 80px rgba(20,20,24,.14);
  animation: slideUp .25s cubic-bezier(.32,.72,.35,1);
}
.modal-box h3 {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -.01em;
  color: var(--c-text);
  margin-bottom: 4px;
}
.pm-timeout-note {
  font-size: 14px;
  color: var(--c-text-secondary);
  margin: 16px 0 24px;
}
.modal-amount {
  font-size: 42px;
  font-weight: 800;
  letter-spacing: -.02em;
  font-variant-numeric: tabular-nums;
  background: var(--c-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  margin: 16px 0 4px;
}
.pay-amount-warn {
  text-align: center;
  font-size: 12px;
  color: var(--c-danger);
  margin: 0 0 16px;
  font-weight: 500;
}
.pay-error {
  background: var(--c-danger-bg);
  color: var(--c-danger);
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 12.5px;
  margin-bottom: 16px;
  text-align: left;
}
.pay-method-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 20px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-border-light);
  border-radius: 12px;
  padding: 3px;
}
.pm-tab {
  flex: 1;
  padding: 8px 0;
  border: none;
  background: transparent;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--c-text-secondary);
  cursor: pointer;
  transition: all .2s cubic-bezier(.32,.72,.35,1);
}
.pm-tab.active {
  background: var(--c-surface);
  color: var(--c-text);
  box-shadow: 0 1px 3px rgba(16, 16, 20, .12);
}
.pm-tab:hover:not(.active) { color: var(--c-text); }

.qr-section { margin: 16px 0; }
.pay-qr-img {
  width: 200px;
  height: 200px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, .1);
  background: #fff;
  padding: 8px;
  box-shadow: 0 0 0 6px rgba(16, 16, 20, .04), 0 12px 32px rgba(20,20,24,.09);
}
.pay-qr-placeholder {
  width: 200px;
  height: 200px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-surface-3);
  border-radius: 12px;
  border: 2px dashed var(--c-border);
  font-size: 13px;
  color: var(--c-text-muted);
}
.qr-label { font-size: 12px; color: var(--c-text-muted); margin-top: 10px; }

.pay-save-btn { margin-top: 8px; }
.pay-save-btn.wechat {
  background: #07c160;
  box-shadow: 0 2px 8px rgba(7,193,96,.25);
}
.pay-save-btn.wechat:hover:not(:disabled) {
  background: #06ad56;
  box-shadow: 0 4px 14px rgba(7,193,96,.3);
}
.pay-cancel-btn { margin-top: 10px; }

/* ---------- 页脚 ---------- */
.page-footer {
  text-align: center;
  padding: 0 20px 24px;
  margin-top: auto;
}
.footer-brand {
  font-size: 12px;
  color: var(--c-text-muted);
}

/* ---------- 重新输入密码弹窗 ---------- */
.relogin-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(22,22,26,.42);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn .2s ease;
}
.relogin-box {
  background: var(--c-surface);
  border: 1px solid var(--c-border-light);
  border-radius: 18px;
  width: 380px;
  max-width: 92vw;
  box-shadow: 0 8px 20px rgba(20,20,24,.09), 0 32px 80px rgba(20,20,24,.14);
  overflow: hidden;
  animation: slideUp .25s cubic-bezier(.32,.72,.35,1);
}
.relogin-header {
  padding: 20px 24px 0;
  position: relative;
}
.relogin-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -.01em;
  color: var(--c-text);
}
.relogin-sub {
  display: block;
  font-size: 12px;
  color: var(--c-text-muted);
  margin-top: 4px;
}
.relogin-close {
  position: absolute;
  top: 16px;
  right: 16px;
  background: none;
  border: none;
  font-size: 22px;
  color: var(--c-text-muted);
  cursor: pointer;
  line-height: 1;
  padding: 0;
  transition: color .2s;
}
.relogin-close:hover { color: var(--c-text); }
.relogin-body { padding: 16px 24px; }
.relogin-label {
  display: block;
  font-size: 13px;
  color: var(--c-text-secondary);
  margin-bottom: 8px;
}
.relogin-input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--c-border);
  border-radius: 12px;
  font-size: 14px;
  color: var(--c-text);
  background: var(--c-surface-2);
  outline: none;
  transition: border-color .2s cubic-bezier(.32,.72,.35,1), box-shadow .2s cubic-bezier(.32,.72,.35,1);
  box-sizing: border-box;
}
.relogin-input:focus {
  border-color: var(--c-primary);
  box-shadow: 0 0 0 4px rgba(20,20,24,.12);
}
.relogin-footer {
  padding: 12px 24px 20px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

/* ---------- 系统公告弹窗 ---------- */
.announcement-overlay {
  position: fixed;
  inset: 0;
  z-index: 9998;
  background: rgba(22,22,26,.42);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn .2s ease;
}
.announcement-box {
  background: var(--c-surface);
  border: 1px solid var(--c-border-light);
  border-radius: 18px;
  width: 420px;
  max-width: 90vw;
  box-shadow: 0 8px 20px rgba(20,20,24,.09), 0 32px 80px rgba(20,20,24,.14);
  overflow: hidden;
  animation: slideUp .25s cubic-bezier(.32,.72,.35,1);
}
.announcement-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 24px 24px 0;
  color: var(--c-primary);
}
.announcement-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -.01em;
  color: var(--c-text);
}
.announcement-header svg { flex-shrink: 0; }
.announcement-body {
  padding: 16px 24px 24px;
  white-space: pre-line;
  font-size: 14px;
  color: var(--c-text-secondary);
  line-height: 1.7;
  max-height: 50vh;
  overflow-y: auto;
  word-break: break-word;
}
.announcement-confirm {
  margin: 0 24px 24px;
  width: calc(100% - 48px);
}

/* ---------- 响应式 ---------- */
@media (max-width: 768px) {
  .summary-bar { flex-direction: column; gap: 12px; }
  .sb-left, .sb-right { width: 100%; justify-content: center; }
  .login-card { padding: 22px; }
  .announcement-box { width: 92vw; }
  .announcement-header { padding: 18px 18px 0; }
  .announcement-body { padding: 12px 18px 18px; }
  .announcement-confirm { margin: 0 18px 18px; width: calc(100% - 36px); }
  .hide-on-mobile-results { display: none; }
}
@media (max-width: 480px) {
  .content-wrapper { padding: 0 16px; }
  .landing { padding-top: 40px; }
  .login-head h1 { font-size: 20px; }
  .done-card { padding: 36px 24px; }
  .cr-bar { display: none; }
  .modal-box { padding: 26px 20px; }
}
</style>

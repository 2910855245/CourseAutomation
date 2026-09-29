<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { type CourseItem } from '@/api'
import { usePlatformNames } from '@/composables/usePlatformNames'
import { useHomeState } from '@/composables/useHomeState'
import AppTopbar from '@/components/AppTopbar.vue'
import PaymentSuccess from '@/components/PaymentSuccess.vue'

const store = useAppStore()
const { load: loadPlatformNames, getName: getPlatformName } = usePlatformNames()

const {
  userRole, isPrivileged, detectUserRole, handleVisibilityChange,
  username, password, scanning, rescanning, scanDone, allDone, isLeaving, scanData, countdown,
  activeTab, chaoxingUsername, chaoxingPassword, startChaoxingScan,
  loginError, failedPlatforms, reloginDialog, reloginPassword, reloginLoading, loginErrorCountdown,
  submittedCourseIds, allInProgress, pendingOrderedCourseIds, checkedCourseIds,
  loadingPrices, backendPrices, speedMode, setSpeedMode,
  isCourseDone, isCourseDoneOrSubmitted, visiblePlatforms, togglePlatform, toggleCourse, isPlatformAllChecked,
  summary, scenario, studentName, chaoxingInfo,
  startScan, resetScan, rescan, openReloginDialog, closeReloginDialog, submitRelogin,
  fetchBackendPrices, saveSession,
  paying, showPayModal, payTotal, submitSuccess, payError, payQrCode, payPollTimer,
  selectedPayMethod,
  payBatchId, payBatchOutTradeNo, showPaySuccess, paySuccessAmount, payTimedOut,
  payPhase, payRemaining, payRechecking, recheckPayment, retryPayment,
  handleOrderSuccess, goToOrders, submitAndPay, onPaySuccessDone, closePay, savePayQr, switchPayMethod,
  pct, pctClass, LS_KEY,
  showAnnouncement, announcementContent, announcementTitle, announcementImage,
  announcementContactType, announcementContactValue, copyAnnouncementContact,
  checkAnnouncement, dismissAnnouncement,
  benefit, inviteInfo, myCard, loadBenefit,
} = useHomeState()

// 刷课节奏三档（与后端 speed.rs 的 SpeedMode 对应）
// "并发"指同时在推进的视频会话数（平台按 beginTime/finalTime 重叠数判定）
const speedOptions = [
  { key: 'turbo' as const, name: '暴力', sub: '8 路并行 · 最快' },
  { key: 'balanced' as const, name: '适中', sub: '推荐 · 兼顾安全' },
  { key: 'gentle' as const, name: '保守', sub: '一节课一节课 · 最稳' },
]
const speedModeDesc = computed(() => ({
  turbo: '整单最多 8 节同时推进，整体完成最快，风控风险最高。',
  balanced: '4 节同时推进 + 启动错峰，完成时间与账号安全的平衡点。',
  gentle: '完全串行：一节课刷完再刷下一节，课程间自动拉长间隔，最接近真人。',
}[speedMode.value]))

// 付费权益：不付费（全局免费活动 / 刷课卡）只能跑保守档，适中与暴力锁定
function isSpeedLocked(key: string) {
  return benefit.value.free && key !== 'gentle'
}
function pickSpeed(key: 'turbo' | 'balanced' | 'gentle') {
  if (isSpeedLocked(key)) {
    store.toast('免费刷只能使用保守档，付费下单可解锁适中 / 暴力档', 'warning')
    return
  }
  setSpeedMode(key)
}

// 场景说明（原来铺三张静态卡片，改成一条紧凑提示，减少视觉噪声）
const SCENARIO_NOTES: Record<string, { tag: string; text: string }> = {
  onlyVideos: { tag: '仅视频', text: '所选课程考试已通过，只需刷视频。' },
  onlyExams: { tag: '仅考试', text: '所选课程视频已刷完，只需处理考试。' },
  both: { tag: '视频 + 考试', text: '视频与考试均有未完成，按基础单价打包计费。' },
}
const scenarioNote = computed(() => SCENARIO_NOTES[scenario.value] ?? null)

// 全屏状态屏（完成 / 进行中 / 失败）的色调
const stateTone = computed(() => {
  if (allDone.value) return 'tone-ok'
  if (allInProgress.value) return 'tone-live'
  return 'tone-bad'
})

// 已选课程的价格（后端逐课定价回显）
const coursePrice = (c: CourseItem) => backendPrices.value[c.course_id]?.price ?? 0

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

// 支付倒计时展示：m:ss
const fmtCountdown = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

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
  loadBenefit()
  // 定价由 useHomeState 的 loadPackagePricing 在 setup 期统一加载，
  // 这里不再重复请求（此前首屏会对 /api/pricing 打两次）
})
</script>

<template>
  <div class="page">
    <AppTopbar title="Fuk 文理网课" :show-role-badge="true" />

    <main class="content-wrapper">
      <!-- ==================== 全屏状态屏 ==================== -->
      <section
        v-if="allDone || allInProgress || loginError === 'all'"
        class="state-screen"
      >
        <div :class="['state-card', stateTone, isLeaving ? 'is-leaving' : 'anim-rise']">
          <div class="state-mark">
            <svg v-if="allDone" width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 6L9 17l-5-5" />
            </svg>
            <svg v-else-if="allInProgress" width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" />
            </svg>
            <svg v-else width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </div>

          <span class="eyebrow">
            {{ allDone ? '全部完成' : allInProgress ? '处理中' : '登录未通过' }}
          </span>
          <h1 class="state-title">
            {{ allDone ? '所有课程已完成' : allInProgress ? '任务正在进行中' : '平台登录失败' }}
          </h1>
          <p class="state-desc">
            <template v-if="allDone">扫描到的所有课程均已 100% 完成，无需下单。</template>
            <template v-else-if="allInProgress">所有课程已提交，系统正在自动处理，进度可在订单页实时查看。</template>
            <template v-else-if="activeTab === 'chaoxing'">学习通登录失败，请检查账号与密码是否正确。</template>
            <template v-else>所有平台均登录失败，请检查学号与密码是否正确。</template>
          </p>

          <div class="state-countdown">
            <span class="mono">{{ allDone ? countdown : allInProgress ? autoRedirectCountdown : loginErrorCountdown }}</span>
            秒后{{ allInProgress ? '自动跳转到订单页' : '返回登录页' }}
          </div>

          <div v-if="failedPlatforms.length > 0" class="state-fails">
            <div v-for="fp in failedPlatforms" :key="fp.website_id" class="state-fail-item">
              <span class="sf-name">{{ fp.name }}</span>
              <span class="sf-err">{{ fp.error }}</span>
              <button class="btn btn-ghost btn-xs" @click="openReloginDialog(fp.website_id, fp.name)">重新登录</button>
            </div>
          </div>
        </div>
      </section>

      <template v-else>
        <!-- ==================== 阶段一 · 登录 ==================== -->
        <section v-if="!scanDone" class="login-stage">
          <div class="login-stack">
            <header class="hero">
              <span class="hero-eyebrow">课程进度自动化</span>
              <h1 class="hero-title">登录平台账号</h1>
              <p class="hero-sub">系统自动扫描各平台未完成课程，并生成可直接提交的任务。</p>
            </header>

            <div class="login-card">
              <div class="seg">
                <button :class="['seg-btn', { active: activeTab === 'school' }]" @click="activeTab = 'school'">
                  学校平台
                </button>
                <button :class="['seg-btn', { active: activeTab === 'chaoxing' }]" @click="activeTab = 'chaoxing'">
                  学习通
                </button>
              </div>

              <form class="login-form" @submit.prevent>
                <template v-if="activeTab === 'school'">
                  <div class="field">
                    <label class="field-label">学号</label>
                    <input v-model="username" placeholder="请输入学号" :disabled="scanning" autocomplete="username" />
                  </div>
                  <div class="field">
                    <label class="field-label">密码</label>
                    <input v-model="password" type="password" placeholder="请输入平台密码" :disabled="scanning" autocomplete="current-password" @keyup.enter="startScan" />
                  </div>
                </template>
                <template v-else>
                  <div class="field">
                    <label class="field-label">手机号</label>
                    <input v-model="chaoxingUsername" placeholder="请输入手机号" :disabled="scanning" autocomplete="username" />
                  </div>
                  <div class="field">
                    <label class="field-label">密码</label>
                    <input v-model="chaoxingPassword" type="password" placeholder="请输入密码" :disabled="scanning" autocomplete="current-password" @keyup.enter="startChaoxingScan" />
                  </div>
                </template>

                <button
                  class="login-cta"
                  :disabled="scanning"
                  @click="activeTab === 'chaoxing' ? startChaoxingScan() : startScan()"
                >
                  <span v-if="!scanning">登录并扫描</span>
                  <span v-else class="login-cta-loading"><span class="spinner"></span>扫描中…</span>
                </button>
              </form>

              <p class="login-foot">支持粟湾、劳动教育、中嘉鑫盛、学习通等平台</p>
            </div>

            <ul class="assure-row">
              <li>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20 6L9 17l-5-5" /></svg>
                自动扫描未完成课程
              </li>
              <li>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></svg>
                处理进度实时同步
              </li>
              <li>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 3l8 4v5c0 4.4-3 8.4-8 9.5-5-1.1-8-5.1-8-9.5V7z" /></svg>
                凭据加密存储
              </li>
            </ul>
          </div>
        </section>

        <!-- ==================== 阶段二 · 选课下单 ==================== -->
        <section v-else class="results">
          <div v-if="rescanning" class="rescan-overlay">
            <span class="spinner-lg"></span>
            <p>正在刷新数据…</p>
          </div>

          <!-- 页头 -->
          <header class="results-head">
            <div class="rh-left">
              <span class="eyebrow">扫描结果</span>
              <h1 class="rh-title">选择需要处理的课程</h1>
              <div class="rh-meta">
                <span v-if="studentName" class="rh-student">{{ studentName }}</span>
                <template v-if="activeTab === 'chaoxing' && chaoxingInfo">
                  <span v-if="chaoxingInfo.school" class="rh-meta-item">{{ chaoxingInfo.school }}</span>
                  <span v-if="chaoxingInfo.workPending > 0" class="rh-meta-item">{{ chaoxingInfo.workPending }} 个待完成作业</span>
                  <span class="rh-meta-item">{{ chaoxingInfo.pendingCount }} 门待处理</span>
                </template>
                <template v-else>
                  <span class="rh-meta-item">{{ visiblePlatforms.filter(p => p.status === 'ok').length }} 个平台已登录</span>
                  <span class="rh-meta-item">{{ visiblePlatforms.reduce((s, p) => s + p.courses.length, 0) }} 门课程</span>
                  <span class="rh-meta-item">{{ visiblePlatforms.reduce((s, p) => s + p.courses.filter(c => !isCourseDoneOrSubmitted(c)).length, 0) }} 门待处理</span>
                </template>
              </div>
            </div>
            <div class="rt-actions">
              <button class="btn btn-ghost" @click="rescan">重新扫描</button>
              <button class="btn btn-outline" @click="resetScan">返回主页</button>
            </div>
          </header>

          <div v-if="submittedCourseIds.size > 0" class="submitted-banner">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></svg>
            <span>已提交 <strong class="mono">{{ submittedCourseIds.size }}</strong> 门课程，任务处理中</span>
          </div>

          <!-- 场景提示：一条紧凑说明，替代原来的三张静态卡片 -->
          <div v-if="scenarioNote" class="scenario-strip">
            <span class="ss-tag">{{ scenarioNote.tag }}</span>
            <span class="ss-text">{{ scenarioNote.text }}</span>
          </div>

          <!-- 平台 + 课程 -->
          <div
            v-for="(p, pi) in visiblePlatforms"
            :key="p.website_id"
            class="platform-block"
            :style="{ animationDelay: Math.min(pi, 8) * 55 + 'ms' }"
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
              <span class="pb-name">{{ p.name }}</span>
              <span class="pb-badge" :class="p.status === 'ok' ? 'ok' : 'fail'">
                {{ p.status === 'ok' ? '已登录' : '未登录' }}
              </span>
              <span class="pb-count mono">{{ p.courses.filter(c => !isCourseDoneOrSubmitted(c)).length }} 门待处理</span>
            </div>

            <div class="course-list">
              <div
                v-for="c in p.courses.filter(x => !submittedCourseIds.has(x.course_id))"
                :key="c.course_id"
                class="course-row"
                :class="{ 'is-done': isCourseDone(c), 'is-checked': checkedCourseIds.has(c.course_id) }"
              >
                <label class="cr-check">
                  <input
                    type="checkbox"
                    :checked="checkedCourseIds.has(c.course_id)"
                    :disabled="isCourseDone(c)"
                    @change="toggleCourse(c.course_id)"
                  />
                </label>

                <div class="cr-main">
                  <div class="cr-top">
                    <span class="cr-name">{{ c.course_name }}</span>
                    <template v-if="p.website_id === 4">
                      <span v-if="c.has_points_system" class="cr-pill">{{ c.points_total ?? 0 }}/{{ chaoxingInfo?.pointsTarget ?? 200 }} 积分</span>
                      <span v-if="(c.points_remaining ?? 0) > 0" class="cr-pill warn">还需 {{ c.days_needed ?? 4 }} 天</span>
                      <span v-else-if="c.has_points_system" class="cr-pill ok">积分达标</span>
                      <span v-if="(c.work_pending ?? 0) > 0" class="cr-pill warn">{{ c.work_pending }} 个待完成作业</span>
                      <span v-else-if="(c.work_total ?? 0) > 0" class="cr-pill ok">作业已完成</span>
                    </template>
                    <template v-else>
                      <span class="cr-pill" :class="c.video_pending > 0 ? 'warn' : 'ok'">{{ c.video_pending }} 剩余</span>
                      <span v-if="c.records_loaded && c.exam_total > 0" class="cr-pill">{{ c.exam_done }}/{{ c.exam_total }} 已通过</span>
                      <span v-if="c.exam_deleted > 0" class="cr-pill deleted">{{ c.exam_deleted }} 已删除</span>
                    </template>
                  </div>

                  <!-- 进度条：数据用等宽数字，读起来像仪表 -->
                  <div v-if="p.website_id !== 4" class="cr-meter">
                    <div class="cr-meter-track">
                      <div class="cr-meter-fill" :class="pctClass(c)" :style="{ width: pct(c) + '%' }"></div>
                    </div>
                    <span class="cr-pct mono">{{ pct(c) }}%</span>
                  </div>
                </div>

                <div class="cr-side">
                  <span v-if="coursePrice(c) > 0" class="cr-price mono">¥{{ coursePrice(c).toFixed(2) }}</span>
                  <span v-else-if="loadingPrices" class="cr-done-tag">计价中…</span>
                  <span v-else-if="isCourseDone(c)" class="cr-done-tag">已完成</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 刷课节奏 -->
          <div class="speed-picker">
            <div class="sp-head">
              <span class="eyebrow">刷课节奏</span>
              <span class="sp-desc">{{ speedModeDesc }}</span>
            </div>
            <div class="sp-opts">
              <button
                v-for="opt in speedOptions"
                :key="opt.key"
                type="button"
                class="sp-opt"
                :class="{ active: speedMode === opt.key, locked: isSpeedLocked(opt.key) }"
                :title="isSpeedLocked(opt.key) ? '付费订单可用' : ''"
                @click="pickSpeed(opt.key)"
              >
                <span class="sp-opt-name">
                  {{ opt.name }}
                  <svg
                    v-if="isSpeedLocked(opt.key)"
                    class="sp-lock"
                    width="11"
                    height="11"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.4"
                  ><rect
                    x="4"
                    y="10"
                    width="16"
                    height="11"
                    rx="2"
                  /><path d="M8 10V7a4 4 0 018 0v3" /></svg>
                </span>
                <span class="sp-opt-sub">{{ isSpeedLocked(opt.key) ? '付费可用' : opt.sub }}</span>
              </button>
            </div>
            <p v-if="benefit.free && speedMode === 'gentle'" class="sp-free">
              {{ benefit.reason === 'card' ? '刷课卡' : '限时免费' }}只能使用保守档（一节课接一节课）。
              想要更快？付费下单即可解锁适中 / 暴力档。
            </p>
            <p v-else-if="speedMode === 'turbo'" class="sp-warn">
              暴力档并发最高（已控制在平台检测安全线内），建议仅在需要当天见效时使用。
            </p>
          </div>

          <!-- 结算条 -->
          <div class="checkout">
            <div class="co-info">
              <div class="co-stats">
                <span class="co-stat"><b class="mono">{{ summary.courses }}</b> 门课程</span>
                <span class="co-sep">·</span>
                <span class="co-stat"><b class="mono">{{ summary.videos }}</b> 个视频</span>
                <template v-if="summary.exams > 0">
                  <span class="co-sep">·</span>
                  <span class="co-stat"><b class="mono">{{ summary.exams }}</b> 场考试</span>
                </template>
              </div>
              <div v-if="!(isPrivileged || benefit.free) && summary.breakdown.length > 0" class="co-breakdown">
                <span v-for="(b, i) in summary.breakdown.slice(0, 3)" :key="i" class="co-bd-item">
                  {{ b.name.length > 10 ? b.name.slice(0, 10) + '…' : b.name }} <span class="mono">{{ b.videos }}</span>节 <span class="mono">¥{{ b.price.toFixed(2) }}</span>
                </span>
                <span v-if="summary.breakdown.length > 3" class="co-bd-item">…共 <span class="mono">{{ summary.breakdown.length }}</span> 门课</span>
              </div>
            </div>

            <div class="co-action">
              <div v-if="isPrivileged || benefit.free" class="co-total">
                <span class="co-total-label">合计</span>
                <span class="co-total-val free">
                  <span class="free-tag">{{ benefit.reason === 'card' ? '刷课卡免单' : '限时免费' }}</span>
                  <span class="mono">¥0.00</span>
                </span>
              </div>
              <div v-else class="co-total">
                <span class="co-total-label">合计</span>
                <span class="co-total-val mono">¥{{ summary.total.toFixed(2) }}</span>
              </div>
              <button
                class="btn btn-primary btn-lg"
                :disabled="paying || summary.courses === 0"
                @click="submitAndPay"
              >
                <span v-if="!paying">{{ (isPrivileged || benefit.free) ? '免费提交' : '提交并支付' }}</span>
                <span v-else class="btn-loading"><span class="spinner"></span>提交中</span>
              </button>
            </div>
          </div>

          <!-- 营销位：免费资格与邀请进度 -->
          <div v-if="benefit.free || inviteInfo.can_claim > 0 || myCard" class="promo-strip">
            <template v-if="myCard">
              <span class="ps-tag ok">刷课卡生效中</span>
              <span class="ps-text">有效期还剩 <b class="mono">{{ myCard.days_left }}</b> 天，期间下单不花钱</span>
            </template>
            <template v-else-if="benefit.reason === 'global'">
              <span class="ps-tag ok">限时免费</span>
              <span class="ps-text">活动期间全场 0 元，直接提交即可</span>
            </template>
            <template v-else>
              <span class="ps-tag warn">可领卡</span>
              <span class="ps-text">你有 <b class="mono">{{ inviteInfo.can_claim }}</b> 张刷课卡待领取</span>
            </template>
            <router-link to="/invite" class="ps-link">
              {{ myCard || benefit.reason === 'global' ? '邀请好友得更多' : '立即领取' }} →
            </router-link>
          </div>
        </section>
      </template>
    </main>

    <footer class="page-footer" :class="{ 'hide-on-mobile-results': scanDone }">
      <div class="footer-brand">Fuk 文理网课</div>
    </footer>
  </div>

  <!-- ==================== 支付弹窗 ==================== -->
  <div class="modal-overlay" :class="{ show: showPayModal && !showPaySuccess }" @click.self="closePay">
    <div class="modal-box pay-modal">
      <template v-if="payTimedOut">
        <div class="modal-header"><span>{{ payPhase === 'uncredited' ? '已支付' : '支付超时' }}</span></div>
        <div class="modal-body">
          <template v-if="payPhase === 'uncredited'">
            <p class="pm-note">
              已收到你的付款，正在等待人工/自动对账入账。入账后会自动开始刷课，无需重复支付。
            </p>
          </template>
          <template v-else>
            <p class="pm-note">支付查询已超时，但订单已创建成功。可重新发起支付，或到订单页查看状态。</p>
          </template>
        </div>
        <div class="modal-footer col">
          <button
            v-if="payPhase === 'uncredited'"
            class="btn btn-primary btn-block"
            :disabled="payRechecking"
            @click="recheckPayment"
          >
            {{ payRechecking ? '查询中…' : '重新检查到账' }}
          </button>
          <button v-else class="btn btn-primary btn-block" @click="goToOrders(); closePay()">重新支付</button>
          <button class="btn btn-ghost btn-block" @click="goToOrders(); closePay()">查看订单</button>
        </div>
      </template>

      <template v-else>
        <div class="modal-header">
          <span>确认支付</span>
          <span v-if="payRemaining > 0" class="pm-countdown mono">剩余 {{ fmtCountdown(payRemaining) }}</span>
          <button class="modal-close" @click="closePay">&times;</button>
        </div>
        <div class="modal-body">
          <div class="pay-hero">
            <span class="eyebrow">应付金额</span>
            <div class="modal-amount mono">¥{{ payTotal.toFixed(2) }}</div>
            <p class="pay-warn">请务必支付相同金额，多一分少一分都无法检测到</p>
          </div>

          <div v-if="payError" class="pay-error">{{ payError }}</div>

          <div class="pay-methods">
            <button :class="['pm-tab', { active: selectedPayMethod === 'ypay_wxpay' }]" @click="switchPayMethod('ypay_wxpay')">微信</button>
            <button :class="['pm-tab', { active: selectedPayMethod === 'ypay_alipay' }]" @click="switchPayMethod('ypay_alipay')">支付宝</button>
          </div>

          <div class="qr-section">
            <img v-if="payQrCode" :src="payQrCode" alt="支付二维码" class="pay-qr-img" />
            <div v-else class="pay-qr-placeholder">
              <span class="spinner"></span>
              生成二维码中…
            </div>
            <p class="qr-label">保存二维码后使用{{ { ypay_alipay: '支付宝', ypay_wxpay: '微信' }[selectedPayMethod] || '扫码' }}扫一扫支付</p>
          </div>
        </div>
        <div class="modal-footer col">
          <button v-if="payQrCode" class="btn btn-primary btn-block" @click="savePayQr">保存二维码</button>
          <button class="btn btn-ghost btn-block" @click="closePay">取消支付</button>
        </div>
      </template>
    </div>
  </div>

  <PaymentSuccess :visible="showPaySuccess" :amount="paySuccessAmount" subtitle="订单已提交" @done="onPaySuccessDone" />

  <!-- ==================== 系统公告 ==================== -->
  <Teleport to="body">
    <div v-if="showAnnouncement" class="announcement-overlay" @click.self="dismissAnnouncement">
      <div class="announcement-box">
        <div class="announcement-header">
          <span class="eyebrow">系统公告</span>
          <h3 v-if="announcementTitle" class="announcement-title">{{ announcementTitle }}</h3>
        </div>
        <img
          v-if="announcementImage"
          :src="announcementImage"
          alt="公告图片"
          class="announcement-image"
        >
        <div class="announcement-body">{{ announcementContent }}</div>
        <div v-if="announcementContactValue" class="announcement-contact">
          <span class="ac-label">{{ announcementContactType || '联系方式' }}</span>
          <span class="ac-value mono">{{ announcementContactValue }}</span>
          <button class="btn btn-ghost btn-xs" @click="copyAnnouncementContact">复制</button>
        </div>
        <div class="announcement-foot">
          <button class="btn btn-primary btn-block" @click="dismissAnnouncement">我知道了</button>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- ==================== 重新输入密码 ==================== -->
  <Teleport to="body">
    <div v-if="reloginDialog.visible" class="relogin-overlay" @click.self="closeReloginDialog">
      <div class="relogin-box">
        <div class="relogin-head">
          <span class="eyebrow">重新登录</span>
          <h3 class="relogin-title">{{ reloginDialog.name }}</h3>
          <p class="relogin-sub">该平台登录失败，请输入正确密码重试。</p>
        </div>
        <div class="relogin-body">
          <input
            v-model="reloginPassword"
            type="password"
            placeholder="输入密码"
            autocomplete="current-password"
            @keydown.enter="submitRelogin"
          />
        </div>
        <div class="relogin-foot">
          <button class="btn btn-ghost" @click="closeReloginDialog">取消</button>
          <button class="btn btn-primary" :disabled="reloginLoading" @click="submitRelogin">
            <span v-if="reloginLoading" class="spinner"></span>
            {{ reloginLoading ? '登录中…' : '确认登录' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* ============================================================
   Paper & Signal — 下单页
   结构：登录（hero + 单一卡片） → 选课（平台分组 + 结算条）
   细节约定：编号/金额/百分比一律等宽数字；层次靠发丝描边而非阴影
   ============================================================ */

.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.content-wrapper {
  flex: 1;
  max-width: 960px;
  padding-top: var(--space-10);
  padding-bottom: var(--space-16);
}

/* ==================== 全屏状态屏 ==================== */
.state-screen {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 62vh;
  padding: var(--space-8) 0;
}

.state-card {
  width: 100%;
  max-width: 460px;
  padding: var(--space-10) var(--space-8);
  text-align: center;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-md), var(--hairline-top);
}
.state-card.is-leaving { opacity: 0; transform: translateY(-8px); transition: all var(--t-slow) var(--ease); }

.state-mark {
  width: 68px;
  height: 68px;
  margin: 0 auto var(--space-5);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 1px solid currentColor;
}
.state-card.tone-ok .state-mark { color: var(--c-success); background: var(--c-success-bg); }
.state-card.tone-live .state-mark { color: var(--c-primary); background: var(--c-primary-bg); }
.state-card.tone-bad .state-mark { color: var(--c-danger); background: var(--c-danger-bg); }

.state-card .eyebrow { margin-bottom: var(--space-3); }
.state-title {
  font-size: var(--fs-h);
  letter-spacing: var(--tracking-title);
  margin-bottom: var(--space-2);
}
.state-desc {
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
  line-height: 1.7;
  max-width: 34ch;
  margin: 0 auto;
}
.state-countdown {
  margin-top: var(--space-6);
  font-size: var(--fs-sm);
  color: var(--c-text-muted);
}
.state-countdown .mono { font-size: var(--fs-md); font-weight: 700; color: var(--c-text); }

.state-fails {
  margin-top: var(--space-6);
  padding-top: var(--space-5);
  border-top: 1px solid var(--c-border-light);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  text-align: left;
}
.state-fail-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--fs-sm);
}
.sf-name { font-weight: 600; }
.sf-err { flex: 1; color: var(--c-text-muted); font-size: var(--fs-xs); }

/* ==================== 阶段一 · 登录 ====================
   目标是"高级大气"：整屏留白 + 大字号标题 + 悬浮玻璃卡 + 渐变主按钮。
   氛围只用平滑径向光晕（**不使用任何点阵/纹理**，避免像素风观感）。 */
.login-stage {
  position: relative;
  z-index: 1;
  min-height: calc(100vh - var(--topbar-h) - 104px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-8) 0;
}

/* 三层平滑光晕：顶部主光 + 右上辅光 + 左下补光 */
.login-stage::before {
  content: '';
  position: fixed;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  background:
    radial-gradient(820px 540px at 50% -14%, rgba(0, 113, 227, .17), transparent 62%),
    radial-gradient(680px 480px at 92% 2%, rgba(92, 170, 255, .13), transparent 64%),
    radial-gradient(760px 560px at 4% 102%, rgba(0, 113, 227, .07), transparent 66%);
}
[data-theme="dark"] .login-stage::before {
  background:
    radial-gradient(820px 540px at 50% -14%, rgba(76, 157, 240, .24), transparent 62%),
    radial-gradient(680px 480px at 92% 2%, rgba(76, 157, 240, .15), transparent 64%),
    radial-gradient(760px 560px at 4% 102%, rgba(76, 157, 240, .10), transparent 66%);
}

.login-stack {
  width: 100%;
  max-width: 440px;
  margin: 0 auto;
}

/* ---------- 标题区 ---------- */
.hero { text-align: center; margin-bottom: var(--space-8); }
.hero-eyebrow {
  display: inline-block;
  margin-bottom: var(--space-5);
  padding: 5px 14px;
  border-radius: var(--radius-pill);
  background: var(--c-primary-bg);
  color: var(--c-primary);
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: .07em;
}
.hero-title {
  font-size: clamp(30px, 4.4vw, 44px);
  font-weight: 700;
  letter-spacing: -.032em;
  line-height: 1.1;
  margin-bottom: var(--space-4);
}
.hero-sub {
  font-size: var(--fs-md);
  line-height: 1.72;
  color: var(--c-text-secondary);
  max-width: 30ch;
  margin: 0 auto;
}

/* ---------- 悬浮玻璃卡 ---------- */
.login-card {
  padding: var(--space-7);
  border-radius: 26px;
  border: 1px solid var(--c-border);
  background: color-mix(in srgb, var(--c-surface) 86%, transparent);
  backdrop-filter: blur(22px) saturate(165%);
  -webkit-backdrop-filter: blur(22px) saturate(165%);
  box-shadow: var(--shadow-lg), var(--hairline-top);
  animation: rise .55s var(--ease-out) both;
  animation-delay: .06s;
}

/* ---------- 平台切换 ---------- */
.seg {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3px;
  padding: 3px;
  border-radius: 15px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-border-light);
}
.seg-btn {
  padding: 11px;
  border: none;
  border-radius: 12px;
  background: transparent;
  color: var(--c-text-secondary);
  font-family: inherit;
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--t) var(--ease), color var(--t) var(--ease),
              box-shadow var(--t) var(--ease);
}
.seg-btn:hover { color: var(--c-text); }
.seg-btn.active {
  background: var(--c-surface);
  color: var(--c-text);
  box-shadow: var(--shadow-sm);
}

/* ---------- 表单 ---------- */
.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin-top: var(--space-6);
}
.field-label {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--c-text-secondary);
}
.login-form input {
  height: 50px;
  padding: 0 16px;
  border-radius: 14px;
  border: 1px solid transparent;
  background: var(--c-surface-2);
  font-size: var(--fs-md);
  transition: background var(--t) var(--ease), border-color var(--t) var(--ease),
              box-shadow var(--t) var(--ease);
}
.login-form input:hover:not(:disabled) { background: var(--c-surface-3); }
.login-form input:focus {
  background: var(--c-surface);
  border-color: var(--c-primary);
  box-shadow: 0 0 0 4px var(--c-primary-ring);
}

/* 主按钮：渐变 + 光晕，是整页唯一的强视觉锚点 */
.login-cta {
  height: 52px;
  margin-top: var(--space-3);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: none;
  border-radius: 14px;
  background: var(--c-gradient);
  color: #fff;
  font-family: inherit;
  font-size: var(--fs-md);
  font-weight: 600;
  letter-spacing: .01em;
  cursor: pointer;
  box-shadow: var(--shadow-primary-lg);
  transition: transform var(--t) var(--ease), box-shadow var(--t) var(--ease),
              filter var(--t) var(--ease);
}
.login-cta:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.06);
  box-shadow: 0 14px 34px -8px rgba(0, 113, 227, .48);
}
.login-cta:active:not(:disabled) { transform: translateY(0) scale(.99); }
.login-cta:disabled { opacity: .55; cursor: not-allowed; box-shadow: none; }
.login-cta-loading { display: inline-flex; align-items: center; gap: 8px; }
.login-cta .spinner { border-color: rgba(255, 255, 255, .35); border-top-color: #fff; }

.login-foot {
  margin-top: var(--space-5);
  padding-top: var(--space-5);
  border-top: 1px solid var(--c-border-light);
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
  text-align: center;
}

/* ---------- 信任说明 ---------- */
.assure-row {
  list-style: none;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-6);
  flex-wrap: wrap;
  margin-top: var(--space-8);
}
.assure-row li {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
}
.assure-row svg { flex: 0 0 auto; opacity: .8; }

/* ==================== 阶段二 · 页头 ==================== */
.results { position: relative; }

.rescan-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  background: color-mix(in srgb, var(--c-bg) 78%, transparent);
  backdrop-filter: blur(3px);
  border-radius: var(--radius-lg);
  color: var(--c-text-secondary);
  font-size: var(--fs-sm);
}

.results-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-5);
  flex-wrap: wrap;
  margin-bottom: var(--space-6);
}
.rh-title {
  font-size: var(--fs-h);
  letter-spacing: var(--tracking-title);
  margin: var(--space-3) 0 var(--space-2);
}
.rh-meta { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
.rh-student { font-size: var(--fs-md); font-weight: 600; }
.rh-meta-item {
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
  padding-left: var(--space-3);
  border-left: 1px solid var(--c-border);
}
.rt-actions { display: flex; gap: var(--space-2); }

.submitted-banner {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 11px 16px;
  margin-bottom: var(--space-5);
  border-radius: var(--radius-md);
  background: var(--c-primary-soft);
  border: 1px solid var(--c-primary-ring);
  color: var(--c-primary);
  font-size: var(--fs-sm);
}

.scenario-strip {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 11px 16px;
  margin-bottom: var(--space-5);
  border-radius: var(--radius-md);
  background: var(--c-surface-2);
  border: 1px solid var(--c-border-light);
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
}
.ss-tag {
  flex: 0 0 auto;
  padding: 2px 9px;
  border-radius: var(--radius-pill);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--c-text);
}

/* ==================== 平台分组 ==================== */
.platform-block {
  margin-bottom: var(--space-5);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs), var(--hairline-top);
  overflow: hidden;
  animation: rise .45s var(--ease-out) both;
}

.pb-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 13px var(--space-5);
  background: var(--c-surface-2);
  border-bottom: 1px solid var(--c-border);
}
.pb-name { font-size: var(--fs-base); font-weight: 600; }
.pb-badge {
  padding: 2px 9px;
  border-radius: var(--radius-pill);
  font-size: var(--fs-xs);
  font-weight: 600;
}
.pb-badge.ok { background: var(--c-success-bg); color: var(--c-success); }
.pb-badge.fail { background: var(--c-danger-bg); color: var(--c-danger); }
.pb-count { margin-left: auto; font-size: var(--fs-xs); color: var(--c-text-muted); }

/* 自定义勾选：统一两处复选框观感 */
.pb-check input,
.cr-check input {
  appearance: none;
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  border: 1.5px solid var(--c-border-strong);
  border-radius: 5px;
  background: var(--c-surface);
  cursor: pointer;
  display: grid;
  place-content: center;
  transition: border-color var(--t-fast) var(--ease), background var(--t-fast) var(--ease);
  flex: 0 0 auto;
}
.pb-check input::after,
.cr-check input::after {
  content: '';
  width: 10px;
  height: 10px;
  transform: scale(0);
  transition: transform var(--t-fast) var(--ease-spring);
  background: #fff;
  clip-path: polygon(14% 44%, 0 65%, 40% 100%, 100% 16%, 85% 0, 39% 68%);
}
.pb-check input:hover:not(:disabled),
.cr-check input:hover:not(:disabled) { border-color: var(--c-primary); }
.pb-check input:checked,
.cr-check input:checked { background: var(--c-primary); border-color: var(--c-primary); }
.pb-check input:checked::after,
.cr-check input:checked::after { transform: scale(1); }
.pb-check input:indeterminate,
.cr-check input:indeterminate { background: var(--c-primary); border-color: var(--c-primary); }
.pb-check input:indeterminate::after,
.cr-check input:indeterminate::after {
  transform: scale(1);
  clip-path: none;
  width: 9px;
  height: 2px;
  border-radius: 1px;
}
.pb-check input:disabled,
.cr-check input:disabled { opacity: .4; cursor: not-allowed; }

/* ==================== 课程行 ==================== */
.course-list { display: flex; flex-direction: column; }
.course-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: 13px var(--space-5);
  border-bottom: 1px solid var(--c-border-light);
  transition: background var(--t-fast) var(--ease);
}
.course-row:last-child { border-bottom: none; }
.course-row:hover { background: var(--c-surface-2); }
.course-row.is-checked { background: var(--c-primary-soft); }
.course-row.is-done { opacity: .55; }

.cr-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.cr-top { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.cr-name {
  font-size: var(--fs-base);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 46ch;
}
.cr-pill {
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  background: var(--c-surface-3);
  color: var(--c-text-secondary);
  font-size: var(--fs-xs);
  font-weight: 600;
  white-space: nowrap;
}
.cr-pill.warn { background: var(--c-warning-bg); color: var(--c-warning); }
.cr-pill.ok { background: var(--c-success-bg); color: var(--c-success); }
.cr-pill.deleted { text-decoration: line-through; opacity: .7; }

.cr-meter { display: flex; align-items: center; gap: 10px; }
.cr-meter-track {
  flex: 1;
  max-width: 320px;
  height: 4px;
  border-radius: var(--radius-pill);
  background: var(--c-surface-3);
  overflow: hidden;
}
.cr-meter-fill {
  height: 100%;
  border-radius: var(--radius-pill);
  background: var(--c-primary);
  transition: width var(--t-slow) var(--ease-out);
}
.cr-meter-fill.done { background: var(--c-success); }
.cr-meter-fill.low { background: var(--c-warning); }
.cr-pct { font-size: var(--fs-xs); color: var(--c-text-muted); min-width: 34px; }

.cr-side { flex: 0 0 auto; text-align: right; min-width: 62px; }
.cr-price { font-size: var(--fs-base); font-weight: 600; }
.cr-done-tag { font-size: var(--fs-xs); color: var(--c-text-muted); }

/* ==================== 刷课节奏 ==================== */
.speed-picker {
  margin: var(--space-6) 0 var(--space-5);
  padding: var(--space-5);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs), var(--hairline-top);
}
.sp-head {
  display: flex;
  align-items: baseline;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-bottom: var(--space-4);
}
.sp-desc { font-size: var(--fs-sm); color: var(--c-text-muted); }
.sp-opts { display: flex; gap: var(--space-2); flex-wrap: wrap; }
.sp-opt {
  flex: 1 1 0;
  min-width: 140px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 11px 16px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  background: var(--c-surface);
  font-family: inherit;
  cursor: pointer;
  text-align: left;
  transition: border-color var(--t-fast) var(--ease), background var(--t-fast) var(--ease),
              transform var(--t-fast) var(--ease);
}
.sp-opt:hover { border-color: var(--c-primary); transform: translateY(-1px); }
.sp-opt.active {
  border-color: var(--c-primary);
  background: var(--c-primary-soft);
  box-shadow: inset 0 0 0 1px var(--c-primary);
}
/* 付费档位在免费待遇下置灰：不是禁用而是"要解锁"，所以保留可点击（点了给出提示） */
.sp-opt.locked {
  opacity: .55;
  cursor: not-allowed;
  background: var(--c-bg);
}
.sp-opt.locked:hover { border-color: var(--c-border); transform: none; }
.sp-opt.locked .sp-opt-sub { color: var(--c-warning); }
.sp-lock { margin-left: 4px; vertical-align: -1px; opacity: .8; }
.sp-opt-name { font-size: var(--fs-base); font-weight: 700; }
.sp-opt.active .sp-opt-name { color: var(--c-primary); }
.sp-opt-sub { font-size: var(--fs-xs); color: var(--c-text-muted); }
.sp-warn {
  margin-top: var(--space-3);
  padding: 9px 13px;
  border-radius: var(--radius-sm);
  background: var(--c-warning-bg);
  color: var(--c-warning);
  font-size: var(--fs-xs);
  line-height: 1.6;
}

/* ==================== 结算条 ==================== */
.checkout {
  position: sticky;
  bottom: var(--space-4);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-5);
  flex-wrap: wrap;
  padding: var(--space-5);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-md), var(--hairline-top);
}
.co-info { min-width: 0; }
.co-stats { display: flex; align-items: baseline; gap: var(--space-2); flex-wrap: wrap; font-size: var(--fs-sm); color: var(--c-text-secondary); }
.co-stat b { font-size: var(--fs-md); color: var(--c-text); }
.co-sep { color: var(--c-text-muted); }
.co-breakdown {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-top: 5px;
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
}
.co-action { display: flex; align-items: center; gap: var(--space-5); margin-left: auto; }
.co-total { display: flex; flex-direction: column; align-items: flex-end; }
.co-total-label { font-size: var(--fs-xs); color: var(--c-text-muted); }
.co-total-val {
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -.02em;
  line-height: 1.15;
}

/* ==================== 支付弹窗 ==================== */
.pay-modal { max-width: 420px; }
.pay-hero { text-align: center; margin-bottom: var(--space-5); }
.pay-hero .modal-amount { margin: var(--space-2) 0 6px; }
.pay-warn {
  font-size: var(--fs-xs);
  color: var(--c-warning);
  line-height: 1.6;
}
/* 支付倒计时：贴在标题栏右侧、关闭按钮左边 */
.pm-countdown {
  margin-left: auto;
  margin-right: var(--space-3);
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--c-text-muted);
}
.pm-note { font-size: var(--fs-sm); color: var(--c-text-secondary); line-height: 1.7; }

.pay-error {
  padding: 10px 13px;
  margin-bottom: var(--space-4);
  border-radius: var(--radius-sm);
  background: var(--c-danger-bg);
  color: var(--c-danger);
  font-size: var(--fs-xs);
}

.pay-methods {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
  padding: 3px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-border-light);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-5);
}
.pm-tab {
  padding: 9px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--c-text-secondary);
  font-family: inherit;
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease);
}
.pm-tab.active { background: var(--c-surface); color: var(--c-text); box-shadow: var(--shadow-xs); }

.qr-section { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); }
.pay-qr-img {
  width: 200px;
  height: 200px;
  object-fit: contain;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  background: #fff;
  padding: 6px;
}
.pay-qr-placeholder {
  width: 200px;
  height: 200px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  border: 1px dashed var(--c-border);
  border-radius: var(--radius-md);
  color: var(--c-text-muted);
  font-size: var(--fs-sm);
}
.qr-label { font-size: var(--fs-xs); color: var(--c-text-muted); }
.modal-footer.col { flex-direction: column; gap: var(--space-2); }

/* ==================== 公告 ==================== */
.announcement-overlay,
.relogin-overlay {
  position: fixed;
  inset: 0;
  z-index: 300;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-5);
  background: rgba(16, 14, 10, .45);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}
.announcement-box,
.relogin-box {
  width: 100%;
  max-width: 460px;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  animation: modal-in var(--t-slow) var(--ease-out) both;
  overflow: hidden;
}
.announcement-header {
  padding: var(--space-5) var(--space-6) var(--space-3);
  border-bottom: 1px solid var(--c-border-light);
}
.announcement-body {
  padding: var(--space-5) var(--space-6);
  font-size: var(--fs-base);
  line-height: 1.75;
  color: var(--c-text-secondary);
  white-space: pre-wrap;
  max-height: 52vh;
  overflow-y: auto;
}
.announcement-foot { padding: 0 var(--space-6) var(--space-6); }

.announcement-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  letter-spacing: var(--tracking-title);
  margin-top: var(--space-2);
  color: var(--c-text);
}
.announcement-image {
  display: block;
  width: calc(100% - var(--space-6) * 2);
  margin: 0 var(--space-6) var(--space-4);
  border-radius: 12px;
  border: 1px solid var(--c-border);
}
.announcement-contact {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 var(--space-6) var(--space-4);
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--c-bg);
  font-size: 12.5px;
}
.ac-label { color: var(--c-text-muted); flex-shrink: 0; }
.ac-value { color: var(--c-text); font-weight: 600; flex: 1; word-break: break-all; }

/* ==================== 营销提示位 ==================== */
.promo-strip {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 12px;
  padding: 12px 16px;
  border-radius: 12px;
  background: var(--c-primary-bg);
  font-size: 12.5px;
}
.ps-tag {
  padding: 2px 9px;
  border-radius: 999px;
  font-weight: 700;
  font-size: 11px;
  flex-shrink: 0;
  background: var(--c-surface);
}
.ps-tag.ok { color: var(--c-success); }
.ps-tag.warn { color: var(--c-warning); }
.ps-text { color: var(--c-text-secondary); flex: 1; min-width: 140px; }
.ps-text b { color: var(--c-text); }
.ps-link {
  color: var(--c-primary);
  font-weight: 600;
  white-space: nowrap;
  text-decoration: none;
}
.ps-link:hover { text-decoration: underline; }

.sp-free {
  font-size: 12px;
  color: var(--c-success);
  line-height: 1.7;
  margin-top: 10px;
}

.co-total-val.free {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--c-success);
}
.free-tag {
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--c-success-bg);
  color: var(--c-success);
  font-size: 11px;
  font-weight: 700;
}

/* ==================== 重新登录 ==================== */
.relogin-head { padding: var(--space-6) var(--space-6) 0; }
.relogin-title { font-size: var(--fs-lg); letter-spacing: var(--tracking-title); margin: var(--space-2) 0 4px; }
.relogin-sub { font-size: var(--fs-sm); color: var(--c-text-muted); }
.relogin-body { padding: var(--space-5) var(--space-6); }
.relogin-foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  padding: 0 var(--space-6) var(--space-6);
}

/* ==================== 页脚 ==================== */
.page-footer {
  padding: var(--space-8) var(--space-6) var(--space-6);
  text-align: center;
  font-size: var(--fs-xs);
  color: var(--c-text-muted);
}

/* ==================== 响应式 ==================== */
@media (max-width: 768px) {
  .content-wrapper { padding-top: var(--space-6); padding-bottom: var(--space-12); }
  .results-head { align-items: flex-start; }
  .rh-title { font-size: var(--fs-title); }
  .cr-name { max-width: 100%; white-space: normal; }
  .course-row { padding: 12px var(--space-4); gap: var(--space-3); }
  .pb-header { padding: 11px var(--space-4); }
  .checkout {
    position: static;
    flex-direction: column;
    align-items: stretch;
    gap: var(--space-4);
  }
  .co-action { margin-left: 0; justify-content: space-between; width: 100%; }
  .co-action .btn { flex: 1; }
  .cr-meter-track { max-width: none; }
  .hide-on-mobile-results { display: none; }
}

@media (max-width: 480px) {
  /* 窄屏上三个档位横排会挤成两行且文字换行，改成竖排整行点击区 */
  .sp-opts { flex-direction: column; }
  .sp-opt { width: 100%; }
}
</style>
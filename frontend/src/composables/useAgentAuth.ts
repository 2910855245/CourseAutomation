import { ref, type Ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { api, type AgentProfile } from '@/api'

export function useAgentAuth(agent: Ref<AgentProfile | null>, loadDashboard: () => Promise<void>) {
  const route = useRoute()
  const store = useAppStore()

  const capturedRef = ref((route.query.ref as string) || '')
  const agentStatus = ref<'none' | 'pending' | 'active' | 'suspended'>('none')
  const loading = ref(true)
  const needsAuth = ref(false)
  const showAuthForm = ref(false)
  const applying = ref(false)
  const applyErr = ref('')

  const authMode = ref<'login' | 'register'>('login')
  const authUsername = ref('')
  const authPassword = ref('')
  const authNickname = ref('')
  const authSubmitting = ref(false)
  const captchaToken = ref('')
  const captchaAnswer = ref('')
  const captchaImage = ref('')
  const captchaLoading = ref(false)

  // Reg payment modal
  const regShowPay = ref(false)
  const regStep = ref<'choose' | 'qr'>('choose')
  const regQrImage = ref<string | null>(null)
  const regFee = ref(0)
  const regPayId = ref('')
  const regPollInterval = ref<any>(null)
  const regPaying = ref(false)
  const regPaid = ref(false)
  const showRegPaySuccess = ref(false)
  const regChannelName = ref('')
  const regPayType = ref(2)

  async function checkAgentStatus() {
    try {
      const res = await api.agents.me()
      if (!res.data) {
        agentStatus.value = 'none'
      } else {
        agent.value = res.data
        agentStatus.value = res.data.status as any
        if (agentStatus.value === 'active') await loadDashboard()
      }
      needsAuth.value = false
    } catch {
      agentStatus.value = 'none'
      needsAuth.value = true
    }
    finally { loading.value = false }
  }

  async function loadCaptcha() {
    captchaLoading.value = true
    try {
      const r = await api.captcha.generate()
      captchaToken.value = r.data.token
      captchaImage.value = r.data.image
      captchaAnswer.value = ''
    } catch { captchaImage.value = '' }
    finally { captchaLoading.value = false }
  }

  async function doAuth(e: Event) {
    e.preventDefault()
    if (!authUsername.value || !authPassword.value) { store.toast('请填写用户名和密码', 'warning'); return }
    if (!captchaAnswer.value.trim()) { store.toast('请填写验证码答案', 'warning'); return }
    authSubmitting.value = true
    try {
      if (authMode.value === 'register') {
        const r = await api.users.register({
          username: authUsername.value,
          password: authPassword.value,
          nickname: authNickname.value || undefined,
          referral_code: capturedRef.value || undefined,
          captcha_token: captchaToken.value,
          captcha_answer: captchaAnswer.value.trim(),
        })
        store.setUserToken(r.data.token, r.data)
        if (r.data.agent) {
          agent.value = r.data.agent
          agentStatus.value = r.data.agent.status as any
          await loadDashboard()
          store.toast('注册成功，代理已开通！', 'success')
        } else {
          store.toast('注册成功！', 'success')
        }
        needsAuth.value = false
      } else {
        const r = await api.users.login({
          username: authUsername.value, password: authPassword.value,
          captcha_token: captchaToken.value,
          captcha_answer: captchaAnswer.value.trim(),
        })
        store.setUserToken(r.data.token, r.data)
        store.toast('登录成功', 'success')
        needsAuth.value = false
        await checkAgentStatus()
      }
    } catch (e: any) {
      store.toast(e?.message || '操作失败', 'error')
      if (e?.message?.includes('验证码')) loadCaptcha()
    }
    finally { authSubmitting.value = false }
  }

  function logoutUser() {
    store.clearUserToken()
    agent.value = null
    agentStatus.value = 'none'
    needsAuth.value = true
  }

  function closeRegPay() {
    regShowPay.value = false
    showRegPaySuccess.value = false
    if (regPollInterval.value) { clearTimeout(regPollInterval.value); regPollInterval.value = null }
  }

  function saveRegQr() {
    const src = regQrImage.value
    if (!src) return
    const a = document.createElement('a')
    a.href = src
    a.download = 'pay-qr.png'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  async function apply(payType: number = 2) {
    applying.value = true
    applyErr.value = ''
    try {
      const res = await api.agents.apply(payType)
      const d = res.data
      if (d.need_pay) {
        regQrImage.value = d.qr_image
        regFee.value = d.fee
        regPayId.value = d.pay_id
        regPayType.value = payType
        regStep.value = 'qr'
        startRegPoll()
      } else {
        agent.value = d
        agentStatus.value = d.status as any
        store.toast(res.message, 'success')
        if (agentStatus.value === 'active') await loadDashboard()
      }
    } catch (e: any) {
      applyErr.value = e.message || '申请失败，请稍后重试'
      store.toast(e.message, 'error')
      await checkAgentStatus()
    }
    finally { applying.value = false }
  }

  async function checkRegPaid() {
    try {
      const r = await api.payment.check(regPayId.value, '', '')
      const d = r?.data || r as any
      if (d?.expired) { closeRegPay(); store.toast('支付已过期', 'warning'); return true }
      if (d?.paid) {
        if (regPollInterval.value) { clearTimeout(regPollInterval.value); regPollInterval.value = null }
        regQrImage.value = null
        showRegPaySuccess.value = true
        return true
      }
    } catch {}
    return false
  }

  function onRegPaySuccessDone() {
    showRegPaySuccess.value = false
    regShowPay.value = false
    window.location.reload()
  }

  function startRegPoll() {
    if (regPollInterval.value) { clearTimeout(regPollInterval.value); regPollInterval.value = null }
    let failCount = 0; let elapsed = 0; let stopped = false
    const fastMs = 2000; const slowMs = 3000; const fastPhase = 30
    async function tick() {
      if (stopped) return
      elapsed += 1
      try {
        const r = await api.payment.check(regPayId.value, '', '')
        failCount = 0
        const d = r?.data || r as any
        if (d?.expired) { stopped = true; closeRegPay(); store.toast('支付已过期', 'warning'); return }
        if (d?.paid) {
          stopped = true
          if (regPollInterval.value) { clearTimeout(regPollInterval.value); regPollInterval.value = null }
          regQrImage.value = null
          showRegPaySuccess.value = true
          return
        }
      } catch {
        failCount++
        if (failCount >= 5) { stopped = true; closeRegPay(); store.toast('网络异常，请刷新页面查看结果', 'warning'); return }
      }
      if (!stopped) {
        const delay = elapsed >= fastPhase ? slowMs : fastMs
        regPollInterval.value = setTimeout(tick, delay)
      }
    }
    regPollInterval.value = setTimeout(tick, fastMs)
  }

  return {
    capturedRef, agentStatus, loading, needsAuth, showAuthForm, applying, applyErr,
    authMode, authUsername, authPassword, authNickname, authSubmitting,
    captchaToken, captchaAnswer, captchaImage, captchaLoading,
    regShowPay, regStep, regQrImage, regFee, regPayId, regPollInterval,
    regPaying, regPaid, showRegPaySuccess, regChannelName, regPayType,
    checkAgentStatus, loadCaptcha, doAuth, logoutUser,
    closeRegPay, saveRegQr, apply, checkRegPaid, onRegPaySuccessDone, startRegPoll,
  }
}

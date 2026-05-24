// 登录/登出/密码修改
import { ref, reactive } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api'

export function useAuth() {
  const store = useAppStore()

  const adminUser = ref('')
  const adminPass = ref('')
  const loginErr = ref('')
  const currentRole = ref<'admin' | 'sub_admin'>(store.adminToken ? 'admin' : 'sub_admin')
  const isLoggedIn = ref(!!store.adminToken || !!store.userToken)
  const pwForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
  const changingPw = ref(false)

  const captchaToken = ref('')
  const captchaAnswer = ref('')
  const captchaImage = ref('')
  const captchaLoading = ref(false)

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

  async function doLogin(e: Event) {
    e.preventDefault()
    loginErr.value = ''
    try {
      const r = await api.admin.login({
        username: adminUser.value,
        password: adminPass.value,
        captcha_token: captchaToken.value,
        captcha_answer: captchaAnswer.value.trim(),
      })
      const role = r.data?.role
      if (role === 'admin') {
        store.setAdminToken(r.data.token)
        currentRole.value = 'admin'
      } else if (role === 'sub_admin') {
        store.setUserToken(r.data.token, r.data)
        currentRole.value = 'sub_admin'
      } else {
        loginErr.value = '需要管理员或合伙人账号'; return
      }
      isLoggedIn.value = true
    } catch (err: any) {
      loginErr.value = err?.message || '登录失败，请稍后重试'
      if (err?.message?.includes('验证码')) loadCaptcha()
    }
  }

  function logout() {
    if (currentRole.value === 'admin') store.clearAdminToken()
    else store.clearUserToken()
    isLoggedIn.value = false
  }

  async function changeAdminPassword() {
    if (!pwForm.old_password || !pwForm.new_password) { store.toast('请填写完整信息', 'warning'); return }
    if (pwForm.new_password.length < 6) { store.toast('新密码至少6位', 'warning'); return }
    if (pwForm.new_password !== pwForm.confirm_password) { store.toast('两次密码不一致', 'warning'); return }
    changingPw.value = true
    try {
      await api.users.changePassword({ old_password: pwForm.old_password, new_password: pwForm.new_password })
      store.toast('密码修改成功，请重新登录', 'success')
      logout()
    } catch (e: any) { store.toast(e?.message || '操作失败', 'error') }
    finally { changingPw.value = false }
  }

  return {
    adminUser, adminPass, loginErr,
    currentRole, isLoggedIn, pwForm, changingPw,
    captchaToken, captchaAnswer, captchaImage, captchaLoading,
    doLogin, logout, changeAdminPassword, loadCaptcha,
  }
}

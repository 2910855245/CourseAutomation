// 登录/登出/密码修改
import { ref, reactive } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api'

export function useAuth() {
  const store = useAppStore()

  const adminUser = ref('')
  const adminPass = ref('')
  const loginErr = ref('')
  const currentRole = ref<'admin'>('admin')
  const isLoggedIn = ref(!!store.adminToken)
  const pwForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
  const changingPw = ref(false)

  // 说明：登录表单原先带图形验证码，但后端 admin_login 明确不做校验
  // （Rust 迁移后没有实现验证码签发），前端还调用了并不存在的
  // /api/captcha/generate —— 表现为「获取验证码」占位图 + 一个填了也没用的输入框。
  // 该假交互已整体移除：填了不生效的字段比没有更容易出事。
  async function doLogin(e: Event) {
    e.preventDefault()
    loginErr.value = ''
    try {
      const r = await api.admin.login({
        username: adminUser.value,
        password: adminPass.value,
      })
      store.setAdminToken(r.data.token)
      currentRole.value = 'admin'
      isLoggedIn.value = true
    } catch (err: any) {
      loginErr.value = err?.message || '登录失败，请稍后重试'
    }
  }

  function logout() {
    store.clearAdminToken()
    isLoggedIn.value = false
  }

  async function changeAdminPassword() {
    if (!pwForm.old_password || !pwForm.new_password) { store.toast('请填写完整信息', 'warning'); return }
    if (pwForm.new_password.length < 6) { store.toast('新密码至少6位', 'warning'); return }
    if (pwForm.new_password !== pwForm.confirm_password) { store.toast('两次密码不一致', 'warning'); return }
    changingPw.value = true
    try {
      await api.admin.changePassword({ old_password: pwForm.old_password, new_password: pwForm.new_password })
      store.toast('密码修改成功，请重新登录', 'success')
      logout()
    } catch (e: any) { store.toast(e?.message || '操作失败', 'error') }
    finally { changingPw.value = false }
  }

  return {
    adminUser, adminPass, loginErr,
    currentRole, isLoggedIn, pwForm, changingPw,
    doLogin, logout, changeAdminPassword,
  }
}

import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { setAdminApiToken, setUserApiToken } from '@/api'

export const useAppStore = defineStore('app', () => {
  const toasts = reactive<Array<{ id: number; message: string; type: string }>>([])
  let nextId = 0

  function toast(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'success') {
    const id = nextId++
    toasts.push({ id, message, type })
    setTimeout(() => {
      const idx = toasts.findIndex(t => t.id === id)
      if (idx > -1) toasts.splice(idx, 1)
    }, 3500)
  }

  const adminToken = ref(localStorage.getItem('admin_token') || '')
  const isAdminLoggedIn = ref(!!adminToken.value)

  function setAdminToken(token: string) {
    adminToken.value = token
    localStorage.setItem('admin_token', token)
    setAdminApiToken(token)
    isAdminLoggedIn.value = true
  }

  function clearAdminToken() {
    adminToken.value = ''
    localStorage.removeItem('admin_token')
    setAdminApiToken('')
    isAdminLoggedIn.value = false
  }

  const userToken = ref(localStorage.getItem('user_token') || '')
  const isUserLoggedIn = ref(!!userToken.value)
  const userInfo = ref<any>(null)

  function setUserToken(token: string, info?: any) {
    userToken.value = token
    localStorage.setItem('user_token', token)
    setUserApiToken(token)
    isUserLoggedIn.value = true
    if (info) userInfo.value = info
  }

  function clearUserToken() {
    userToken.value = ''
    localStorage.removeItem('user_token')
    setUserApiToken('')
    isUserLoggedIn.value = false
    userInfo.value = null
  }

  if (adminToken.value) setAdminApiToken(adminToken.value)
  if (userToken.value) setUserApiToken(userToken.value)

  return {
    toasts, toast,
    adminToken, setAdminToken, clearAdminToken, isAdminLoggedIn,
    userToken, setUserToken, clearUserToken, isUserLoggedIn, userInfo,
  }
})

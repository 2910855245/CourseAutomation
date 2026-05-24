import { createRouter, createWebHashHistory } from 'vue-router'
import { api } from '@/api'

let setupChecked = false
let setupDoneFromApi = false

async function checkSetupDone(): Promise<boolean> {
  if (setupChecked) return setupDoneFromApi
  try {
    const r = await fetch('/api/setup/status')
    const d = await r.json()
    setupDoneFromApi = !!(d.data && d.data.done)
  } catch {
    setupDoneFromApi = false
  }
  setupChecked = true
  return setupDoneFromApi
}

const SITE_NAME = 'Anti-Course'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/Home.vue'),
      meta: { title: '首页' },
    },
    {
      path: '/orders',
      name: 'orders',
      component: () => import('@/views/Orders.vue'),
      meta: { title: '订单查询' },
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/Admin.vue'),
      meta: { requiresAdmin: true, title: '后台管理' },
    },
    {
      path: '/agent',
      name: 'agent',
      component: () => import('@/views/Agent.vue'),
      meta: { title: '代理中心' },
    },
    {
      path: '/subsite/:slug',
      name: 'subsite',
      component: () => import('@/views/Subsite.vue'),
      meta: { title: '分站' },
    },
    {
      path: '/sub-admin',
      redirect: '/admin',
    },
    {
      path: '/setup',
      name: 'setup',
      component: () => import('@/views/Setup.vue'),
      meta: { title: '安装向导' },
    },
    {
      path: '/payment/:id',
      name: 'payment',
      component: () => import('@/views/Payment.vue'),
      meta: { title: '支付' },
    },
    {
      path: '/orders/:id',
      name: 'orderDetail',
      component: () => import('@/views/Orders.vue'),
      meta: { title: '订单详情' },
    },
  ],
})

router.afterEach((to) => {
  const page = to.meta?.title as string | undefined
  document.title = page ? `${page} · ${SITE_NAME}` : SITE_NAME
})

router.beforeEach(async (to, _from, next) => {
  if (to.name === 'setup' || to.name === 'payment' || to.name === 'orders' || to.name === 'orderDetail' || to.name === 'admin' || to.name === 'agent') {
    next()
    return
  }
  const done = await checkSetupDone()
  if (!done) {
    next({ name: 'setup' })
  } else {
    if (to.meta.requiresAuth) {
      const token = localStorage.getItem('user_token')
      if (!token) { next({ name: 'home' }); return }
    }
    if (to.meta.requiresAdmin) {
      const adminToken = localStorage.getItem('admin_token')
      const userToken = localStorage.getItem('user_token')
      if (adminToken) {
        // 管理员直接通过
      } else if (userToken) {
        // 检查是否为合伙人
        try {
          const r = await api.users.me()
          const role = (r as any)?.data?.role
          if (role !== 'sub_admin' && role !== 'agent') { next({ name: 'home' }); return }
        } catch { next({ name: 'home' }); return }
      } else {
        next({ name: 'home' }); return
      }
    }
    next()
  }
})

export default router

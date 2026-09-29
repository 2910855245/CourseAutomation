import { createRouter, createWebHashHistory } from 'vue-router'

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
      path: '/invite',
      name: 'invite',
      component: () => import('@/views/Invite.vue'),
      meta: { title: '邀请有礼' },
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/Admin.vue'),
      meta: { title: '后台管理' },
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
  if (to.meta.requiresAuth) {
    const token = localStorage.getItem('user_token')
    if (!token) { next({ name: 'home' }); return }
  }
  // /admin 不再在此拦截：Admin.vue 自身按 adminToken 决定「登录表单 / 后台布局」，
  // 若守卫在无 token 时重定向到首页，登录表单将永远无法到达（死锁）。
  next()
})

export default router

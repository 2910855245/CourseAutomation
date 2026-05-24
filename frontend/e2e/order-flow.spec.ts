import { test, expect } from '@playwright/test'

test('创建订单接口需要参数', async ({ request }) => {
  const res = await request.post('/api/orders/', {
    data: {},
  })
  // 缺少必要参数应返回 422
  expect(res.status()).toBe(422)
})

test('未登录查询订单返回 401', async ({ request }) => {
  const res = await request.get('/api/orders/')
  expect(res.status()).toBe(401)
})

test('平台列表接口返回数据', async ({ request }) => {
  const res = await request.get('/api/courses/platforms')
  expect(res.ok()).toBeTruthy()
  const data = await res.json()
  expect(data.success).toBe(true)
})

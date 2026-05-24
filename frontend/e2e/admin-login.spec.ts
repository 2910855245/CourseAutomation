import { test, expect } from '@playwright/test'

test('管理后台页面可访问', async ({ request }) => {
  const res = await request.get('/')
  expect(res.ok()).toBeTruthy()
  const html = await res.text()
  // SPA 页面包含 Vue 应用挂载点
  expect(html).toContain('id="app"')
})

test('验证码接口可用', async ({ request }) => {
  const res = await request.get('/api/captcha/generate')
  expect(res.ok()).toBeTruthy()
  const data = await res.json()
  expect(data.success).toBe(true)
  expect(data.data).toHaveProperty('token')
  expect(data.data).toHaveProperty('image')
})

test('未登录访问管理接口返回 401', async ({ request }) => {
  const res = await request.get('/api/admin/stats')
  expect(res.status()).toBe(401)
})

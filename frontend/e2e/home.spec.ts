import { test, expect } from '@playwright/test'

test('首页可访问', async ({ request }) => {
  const res = await request.get('/')
  expect(res.ok()).toBeTruthy()
  const html = await res.text()
  expect(html).toContain('html')
})

test('定价接口返回正常', async ({ request }) => {
  const res = await request.get('/api/pricing')
  expect(res.ok()).toBeTruthy()
  const data = await res.json()
  expect(data.code).toBe(0)
  expect(data.data).toHaveProperty('priceSmall')
})

test('系统信息接口返回版本', async ({ request }) => {
  const res = await request.get('/api/info')
  expect(res.ok()).toBeTruthy()
  const data = await res.json()
  expect(data).toHaveProperty('version')
})

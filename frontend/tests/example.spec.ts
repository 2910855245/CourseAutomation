import { test, expect } from '@playwright/test';

test('首页加载测试', async ({ page }) => {
  await page.goto('https://shuakecdcas.top');
  await expect(page).toHaveTitle(/刷课|课程/);
});

test('API 定价接口测试', async ({ request }) => {
  const response = await request.get('https://shuakecdcas.top/api/pricing');
  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  expect(data.code).toBe(0);
  expect(data.data).toHaveProperty('priceSmall');
  expect(data.data).toHaveProperty('priceExamOnly');
});

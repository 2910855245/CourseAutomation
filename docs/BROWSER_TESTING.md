# 浏览器自动化测试指南

## 概述

本文档介绍如何使用浏览器自动化工具测试 Anti-Course Cheating Plugin 平台的功能。

## 推荐工具

| 工具 | 适用场景 | 安装 |
|------|----------|------|
| Playwright | 现代 Web 测试，支持多浏览器 | `npm install -D @playwright/test` |
| Puppeteer | Chrome/Edge 自动化 | `npm install puppeteer` |
| Selenium | 跨浏览器兼容测试 | `pip install selenium` |

## Playwright 测试示例

### 安装

```bash
cd frontend
npm install -D @playwright/test
npx playwright install
```

### 测试配置

创建 `frontend/playwright.config.ts`:

```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  use: {
    baseURL: 'https://shuakecdcas.top',
    headless: false,  // 设为 false 可以看到浏览器操作
    viewport: { width: 1280, height: 720 },
    screenshot: 'on',
    video: 'on',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'mobile-chrome', use: { ...devices['Pixel 5'] } },
  ],
});
```

### 测试用例

#### 1. 首页加载测试

创建 `frontend/tests/home.spec.ts`:

```typescript
import { test, expect } from '@playwright/test';

test.describe('首页测试', () => {
  test('页面正常加载', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/刷课/);
    await expect(page.locator('text=登录')).toBeVisible();
  });

  test('定价信息显示', async ({ page }) => {
    await page.goto('/');
    // 检查定价区域
    await expect(page.locator('.pricing-section')).toBeVisible();
  });
});
```

#### 2. 用户登录测试

```typescript
test.describe('用户登录', () => {
  test('正常登录流程', async ({ page }) => {
    await page.goto('/');
    
    // 输入用户名密码
    await page.fill('input[placeholder="用户名"]', 'testuser');
    await page.fill('input[placeholder="密码"]', 'password123');
    
    // 点击登录
    await page.click('button:has-text("登录")');
    
    // 验证登录成功
    await expect(page.locator('text=扫描课程')).toBeVisible({ timeout: 10000 });
  });

  test('登录失败提示', async ({ page }) => {
    await page.goto('/');
    
    await page.fill('input[placeholder="用户名"]', 'wrong');
    await page.fill('input[placeholder="密码"]', 'wrong');
    await page.click('button:has-text("登录")');
    
    // 验证错误提示
    await expect(page.locator('.error-message')).toBeVisible();
  });
});
```

#### 3. 课程扫描测试

```typescript
test.describe('课程扫描', () => {
  test('扫描并显示课程列表', async ({ page }) => {
    // 先登录
    await page.goto('/');
    await page.fill('input[placeholder="用户名"]', 'testuser');
    await page.fill('input[placeholder="密码"]', 'password123');
    await page.click('button:has-text("登录")');
    
    // 等待扫描按钮出现
    await expect(page.locator('text=扫描课程')).toBeVisible({ timeout: 10000 });
    
    // 点击扫描
    await page.click('button:has-text("扫描课程")');
    
    // 等待扫描完成
    await expect(page.locator('.course-list')).toBeVisible({ timeout: 30000 });
    
    // 验证课程数量
    const courses = page.locator('.course-item');
    await expect(courses).toHaveCount.greaterThan(0);
  });
});
```

#### 4. 定价系统测试

```typescript
test.describe('定价系统', () => {
  test('后端价格计算API', async ({ request }) => {
    const response = await request.post('/api/pricing/calculate', {
      data: {
        courses: [
          {
            course_id: 'test1',
            video_total: 20,
            video_completed: 0,
            exam_total: 0,
            exam_done: 0,
            homework_total: 0,
            homework_done: 0,
          },
        ],
      },
    });
    
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.code).toBe(0);
    expect(data.data.courses[0].price).toBe(3.0);  // 小课价格
  });

  test('纯考试课程定价', async ({ request }) => {
    const response = await request.post('/api/pricing/calculate', {
      data: {
        courses: [
          {
            course_id: 'exam1',
            video_total: 0,
            video_completed: 0,
            exam_total: 1,
            exam_done: 0,
            homework_total: 0,
            homework_done: 0,
          },
        ],
      },
    });
    
    const data = await response.json();
    expect(data.data.courses[0].type).toBe('exam_only');
    expect(data.data.courses[0].price).toBe(5.0);  // 纯考试价格
  });
});
```

#### 5. 管理员后台测试

```typescript
test.describe('管理员后台', () => {
  test.beforeEach(async ({ page }) => {
    // 登录管理员
    await page.goto('/admin');
    await page.fill('input[placeholder="用户名"]', 'admin');
    await page.fill('input[placeholder="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await expect(page.locator('text=概览')).toBeVisible({ timeout: 10000 });
  });

  test('定价配置页面', async ({ page }) => {
    // 导航到定价页面
    await page.click('text=定价配置');
    
    // 验证定价卡片显示
    await expect(page.locator('text=小课')).toBeVisible();
    await expect(page.locator('text=纯考试')).toBeVisible();
    await expect(page.locator('text=纯作业')).toBeVisible();
  });

  test('编辑定价配置', async ({ page }) => {
    await page.click('text=定价配置');
    
    // 点击编辑按钮
    await page.click('button:has-text("编辑")');
    
    // 修改小课价格
    const smallPriceInput = page.locator('input[v-model="editPricing.priceSmall"]');
    await smallPriceInput.fill('4');
    
    // 保存
    await page.click('button:has-text("保存")');
    
    // 验证保存成功提示
    await expect(page.locator('text=已保存')).toBeVisible();
  });
});
```

#### 6. 移动端测试

```typescript
test.describe('移动端适配', () => {
  test.use({ viewport: { width: 375, height: 812 } });  // iPhone 13

  test('移动端首页布局', async ({ page }) => {
    await page.goto('/');
    
    // 验证移动端元素
    await expect(page.locator('.mobile-nav')).toBeVisible();
    
    // 验证没有水平滚动
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const clientWidth = await page.evaluate(() => document.body.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
  });
});
```

## API 测试

### 使用 curl 测试

```bash
# 获取定价配置
curl https://shuakecdcas.top/api/pricing

# 计算课程价格
curl -X POST https://shuakecdcas.top/api/pricing/calculate \
  -H "Content-Type: application/json" \
  -d '{
    "courses": [
      {"course_id": "1", "video_total": 50, "video_completed": 0, "exam_total": 0, "exam_done": 0, "homework_total": 0, "homework_done": 0}
    ]
  }'

# AI 推荐定价
curl -X POST https://shuakecdcas.top/api/pricing/recommend \
  -H "Content-Type: application/json" \
  -d '{"avg_price": 5, "max_price": 6}'
```

### 使用 Playwright 测试 API

```typescript
test('API 响应时间测试', async ({ request }) => {
  const start = Date.now();
  const response = await request.get('/api/pricing');
  const duration = Date.now() - start;
  
  expect(response.ok()).toBeTruthy();
  expect(duration).toBeLessThan(1000);  // 响应时间 < 1秒
});
```

## 测试数据准备

### 创建测试用户

```typescript
test.beforeAll(async ({ request }) => {
  // 通过 API 创建测试用户
  await request.post('/api/admin/users', {
    data: {
      username: 'testuser',
      password: 'password123',
      role: 'user',
    },
  });
});
```

### Mock 课程数据

```typescript
test('模拟课程扫描', async ({ page }) => {
  // 拦截 API 请求
  await page.route('/api/courses/scan', async (route) => {
    await route.fulfill({
      status: 200,
      body: JSON.stringify({
        code: 0,
        data: {
          courses: [
            { course_id: '1', course_name: '测试课程', video_total: 50 },
          ],
        },
      }),
    });
  });
  
  await page.goto('/');
  await page.click('button:has-text("扫描课程")');
  await expect(page.locator('text=测试课程')).toBeVisible();
});
```

## 运行测试

```bash
# 运行所有测试
npx playwright test

# 运行特定测试文件
npx playwright test tests/home.spec.ts

# 运行带 UI 的测试
npx playwright test --ui

# 生成测试报告
npx playwright show-report
```

## 持续集成

### GitHub Actions 配置

创建 `.github/workflows/test.yml`:

```yaml
name: E2E Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: 18
      - run: cd frontend && npm ci
      - run: cd frontend && npx playwright install --with-deps
      - run: cd frontend && npx playwright test
      - uses: actions/upload-artifact@v3
        if: failure()
        with:
          name: playwright-report
          path: frontend/playwright-report/
```

## 调试技巧

### 录制测试脚本

```bash
# 打开 Playwright Inspector
npx playwright codegen https://shuakecdcas.top
```

### 截图对比

```typescript
test('视觉回归测试', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveScreenshot('homepage.png', {
    maxDiffPixels: 100,
  });
});
```

### 调试失败测试

```typescript
test('调试测试', async ({ page }) => {
  await page.goto('/');
  
  // 添加调试断点
  await page.pause();
  
  // 或者在失败时自动暂停
  page.on('pageerror', () => page.pause());
});
```

## 常见问题

### 1. 元素找不到

```typescript
// 等待元素出现
await page.waitForSelector('.course-list', { timeout: 10000 });

// 或者使用 locator 的等待
await expect(page.locator('.course-list')).toBeVisible({ timeout: 10000 });
```

### 2. 跨域问题

```typescript
// 在配置中设置
export default defineConfig({
  use: {
    extraHTTPHeaders: {
      'Origin': 'https://shuakecdcas.top',
    },
  },
});
```

### 3. 移动端测试

```typescript
import { devices } from '@playwright/test';

test.use({
  ...devices['iPhone 13'],
});
```

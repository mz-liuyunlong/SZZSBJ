import { expect, test, type Page } from '@playwright/test';

test.use({ channel: process.env.PLAYWRIGHT_CHANNEL });

async function prepare(page: Page) {
  await page.addInitScript(() => localStorage.setItem('szzsbj_auth_token', 'synthetic-keyword-layout'));
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith('/api/')) return route.fallback();
    const data = url.pathname === '/api/auth/me'
      ? { id: 16, username: 'layout-fixture', display_name: '布局测试', is_super_admin: true,
          role_keys: [], role_names: [], permissions: ['*'] }
      : { items: [], total: 0 };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      success: true, data, error: null, meta: {}, request_id: 'synthetic-layout',
    }) });
  });
}

test('keyword launch keeps the original four-step layout and embedded rules', async ({ page }) => {
  await prepare(page);
  await page.goto('/#/ai-center/keyword-launch');
  await expect(page.locator('.kw-v2-page')).toBeVisible();
  await expect(page.locator('.kw-v2-page')).toHaveCSS('display', 'flex');
  await expect(page.locator('.kw-v2-setup')).toHaveCSS('display', 'grid');
  await expect(page.getByRole('heading', { name: '新品关键词投放' })).toBeVisible();
  await expect(page.getByText('选择 SKU', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '规则配置' }).click();
  await expect(page.getByRole('heading', { name: '规则配置' })).toBeVisible();
  await expect(page).toHaveURL(/\/#\/ai-center\/keyword-launch$/);
  await expect(page.getByRole('button', { name: '返回关键词投放' })).toBeVisible();
  await page.goto('/#/ai-center/keyword-launch/rules');
  await expect(page.getByText('页面不存在')).toBeVisible();
});

test('keyword library keeps the original report layout', async ({ page }) => {
  await prepare(page);
  await page.goto('/#/ads/keyword-library');
  await expect(page.locator('.kw-v2-library')).toBeVisible();
  await expect(page.locator('.kw-v2-library')).toHaveCSS('display', 'flex');
  await expect(page.getByText('当前 SKU（唯一商品维度）')).toBeVisible();
  await expect(page.getByText('关键词词库 · 后端持久化')).toHaveCount(0);
});

import { expect, test } from '@playwright/test';

const topLevelMenus = [
  '工作台',
  '产品',
  '销售',
  '广告',
  '售后',
  '仓库',
  '财务',
  '运营',
  '采购',
  'AI中心',
  '数据中心',
  '统计',
  '设置',
];

test.describe('本项目 navigation shell', () => {
  test('renders top-level navigation menus', async ({ page }) => {
    await page.goto('/');

    for (const menu of topLevelMenus) {
      await expect(page.getByText(menu, { exact: true })).toBeVisible();
    }
  });

  test('opens a placeholder page from the navigation', async ({ page }) => {
    await page.goto('/');
    await page.getByText('销售', { exact: true }).click();
    await page.getByText('每日销售', { exact: true }).click();

    await expect(page.getByRole('heading', { name: /每日销售/ })).toBeVisible();
    await expect(page.getByText(/building|建设中|Coming Soon/i)).toBeVisible();
  });
});

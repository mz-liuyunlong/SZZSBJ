import { expect, test } from '@playwright/test';

test.describe('API documentation entry', () => {
  test('API docs entry is available for authorized UI state', async ({ page }) => {
    await page.goto('/');
    await page.getByText('数据中心', { exact: true }).click();
    await expect(page.getByText('API文档', { exact: true })).toBeVisible();
  });
});

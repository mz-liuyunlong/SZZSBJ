import { expect, test } from '@playwright/test';

test.describe('Page help link', () => {
  test('opens SOP help in a new tab', async ({ context, page }) => {
    await page.goto('/sales/daily-sales');

    const helpButton = page.getByRole('button', { name: /帮助|Help|\?/ });
    await expect(helpButton).toBeVisible();

    const [newPage] = await Promise.all([
      context.waitForEvent('page'),
      helpButton.click(),
    ]);

    await newPage.waitForLoadState('domcontentloaded');
    await expect(newPage).toHaveURL(/\/help\//);
  });
});

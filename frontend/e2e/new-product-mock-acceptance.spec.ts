/** Isolated visual acceptance for both new-product mock pages; never writes production data. */
import { expect, test, type Page } from "@playwright/test";

async function prepare(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem("szzsbj_auth_token", "synthetic-new-product-visual");
  });
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.fallback();
    const data = path === "/api/auth/me"
      ? {
        id: 17,
        username: "new-product-visual",
        display_name: "新品视觉验收",
        is_super_admin: true,
        role_keys: [],
        role_names: [],
        permissions: ["*"],
      }
      : { items: [], total: 0 };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true, data, error: null, meta: {}, request_id: "new-product-visual",
      }),
    });
  });
}

for (const mode of [
  {
    name: "新品表现",
    path: "/products/new-product-analysis",
    board: "新品表现看板",
    table: "新品表现明细",
  },
  {
    name: "打品跟踪",
    path: "/products/launch-tracking",
    board: "打品跟踪看板",
    table: "打品跟踪明细",
  },
]) {
  test(`${mode.name} retains independent list and dashboard mock views`, async ({ page }, info) => {
    await prepare(page);
    const writes: string[] = [];
    const runtimeErrors: string[] = [];
    page.on("pageerror", error => runtimeErrors.push(error.message));
    page.on("request", request => {
      const url = new URL(request.url());
      if (url.pathname.startsWith("/api/") && request.method() !== "GET") {
        writes.push(`${request.method()} ${url.pathname}`);
      }
    });
    await page.goto(`/#${mode.path}`);
    await expect(page.getByRole("heading", { name: mode.name, exact: true })).toBeVisible();
    await expect(page.locator(".npd-page .ant-pro-table").first()).toBeVisible();
    await expect(page.getByText(mode.table, { exact: true })).toBeVisible();
    await page.screenshot({
      path: info.outputPath(`${mode.name}-list.png`),
      fullPage: true,
      animations: "disabled",
    });

    await page.getByRole("tab", { name: mode.board }).click();
    await expect(page.locator(".npd-board")).toBeVisible();
    await expect(page.locator(".npd-board canvas").first()).toBeVisible();
    await page.screenshot({
      path: info.outputPath(`${mode.name}-dashboard.png`),
      fullPage: true,
      animations: "disabled",
    });
    expect(runtimeErrors).toEqual([]);
    expect(writes).toEqual([]);
  });
}

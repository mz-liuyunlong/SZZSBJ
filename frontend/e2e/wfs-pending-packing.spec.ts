/** Browser acceptance with synthetic API responses; never writes business data. */
import { expect, test } from "@playwright/test";
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL ?? "msedge", viewport: { width: 1600, height: 1000 } });
test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => console.log("PAGE_ERROR", error.message));
});
test("a failed backend read shows an error rather than sample orders", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-wfs-test"));
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.fallback();
    const auth = path === "/api/auth/me";
    await route.fulfill({ status: auth ? 200 : 503, contentType: "application/json", body: JSON.stringify({
      success: auth, data: auth ? { id: 16, username: "wfs-fixture", is_super_admin: true, permissions: ["*"], role_keys: [], role_names: [] } : null,
      error: auth ? null : { code: "UNAVAILABLE" }, meta: {}, request_id: "synthetic-error",
    }) });
  });
  await page.goto("/#/pmc/wfs/pending-packing");
  await expect(page.getByText(/待发货服务请求失败/)).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("数据加载失败，请重试")).toBeVisible();
});

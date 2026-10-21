/** Warehouse UI contracts: empty/error are explicit and read actions remain real GETs. */
import { expect, test } from "@playwright/test";
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL });
async function prepare(page: import("@playwright/test").Page, error = false) {
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-warehouse-contract"));
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.fallback();
    if (error && path.endsWith("/packing-warehouse/orders")) return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ success: false, data: null, error: { code: "INTERNAL_ERROR" }, meta: {}, request_id: "synthetic-error" }) });
    const data = path === "/api/auth/me" ? { id: 15, username: "warehouse-contract", display_name: "仓库契约", is_super_admin: false, role_keys: [], role_names: [], permissions: ["page:pmc:domestic-warehouse-board:view"] }
      : path.endsWith("/filter-options") ? { stores: [], owners: [] }
      : path.endsWith("/packing-warehouse/orders/summary") ? { todo: 0, packed: 0 } : { items: [], total: 0 };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, data, error: null, meta: { publication_ids: [], data_status: "not_published", freshness_at: null }, request_id: "synthetic-contract" }) });
  });
  await page.goto("/#/pmc/domestic/packing-warehouse");
}
test("warehouse shows real empty state and sends only read requests for filters", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => { if (new URL(request.url()).pathname.includes("/packing-warehouse/")) requests.push(request.method()); });
  await prepare(page);
  await expect(page.getByText("当前条件下暂无已审批打包单", { exact: true })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "打包单店铺", exact: true })).toBeEnabled();
  await page.getByRole("textbox", { name: "搜索仓库打包单" }).fill("IB-FIXTURE");
  await page.getByRole("textbox", { name: "搜索仓库打包单" }).press("Enter");
  await expect(page.locator(".domestic-packing .ant-pagination")).toBeVisible();
  expect(requests.length).toBeGreaterThan(0);
  expect(requests.every((method) => method === "GET")).toBe(true);
});
test("warehouse service error is actionable rather than silent empty", async ({ page }) => {
  await prepare(page, true);
  await expect(page.getByText(/仓库打包服务请求失败/)).toBeVisible({ timeout: 20000 });
  await expect(page.getByRole("button", { name: /^重\s*试$/ })).toBeVisible();
});

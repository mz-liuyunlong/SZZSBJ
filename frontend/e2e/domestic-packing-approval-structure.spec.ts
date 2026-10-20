/** UI contracts with explicit synthetic fixtures; live DB acceptance is separate. */
import { expect, test } from "@playwright/test";
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL });
const envelope = (data: unknown) => JSON.stringify({ success: true, data, error: null, meta: { publication_ids: [], data_status: "not_published", freshness_at: null }, request_id: "packing-contract-test" });
test("read-only role sees candidate and blocked reason without write controls", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-ui-test"));
  await page.route("**/api/**", async (route) => {
    const p = new URL(route.request().url()).pathname;
    if (!p.startsWith("/api/")) return route.fallback();
    const data = p === "/api/auth/me" ? { id: 16, username: "packing-ui-test", display_name: "UI测试", is_super_admin: false, role_keys: [], role_names: [], permissions: ["page:pmc:domestic-warehouse-board:view"] }
      : p.endsWith("/pending/summary") ? { pending: 1, overdue: 1, blocked: 1, approved: 0, rejected: 0 }
      : p.endsWith("/filter-options") ? { stores: [], owners: [] }
      : p.endsWith("/packing-approval/pending") ? { total: 1, items: [{ id: "fixture", candidate_version: "a".repeat(64), source_account_ref: "fixture", warehouse_id: "16168", publication_id: "fixture", board_id: "fixture", inbound_order_sn: "IB-FIXTURE", sku: "FIXTURE-SKU", store_id: null, store_name: null, item_id: null, gtin: null, msku: null, purchase_order_sns: [], arrival_purchased: null, arrival_received: null, arrival_pending: null, arrival_status: "unknown", candidate_created_on: "2026-10-19", overdue: true, stock_balance: 1, available_quantity: null, default_quantity: null, can_approve: false, blocked_reasons: ["STORE_UNKNOWN"] }] }
      : { items: [], total: 0 };
    await route.fulfill({ status: 200, contentType: "application/json", body: envelope(data) });
  });
  await page.goto("/#/pmc/domestic-warehouse-board"); await page.getByRole("tab", { name: "打包单审批", exact: true }).click();
  await expect(page.getByText("FIXTURE-SKU", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /^通\s*过$/ }).first()).toBeDisabled();
  await expect(page.getByRole("button", { name: /^驳\s*回$/ }).first()).toBeDisabled();
  await expect(page.getByRole("button", { name: "手工添加打包单", exact: true })).toBeDisabled();
});
test("list errors are actionable and never shown as empty success", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-ui-test"));
  await page.route("**/api/**", async (route) => {
    const p = new URL(route.request().url()).pathname;
    if (!p.startsWith("/api/")) return route.fallback();
    if (p.endsWith("/packing-approval/pending")) return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ success: false, data: null, error: { code: "INTERNAL_ERROR" }, meta: null, request_id: "failure" }) });
    const data = p === "/api/auth/me" ? { id: 16, username: "packing-ui-test", display_name: "UI测试", is_super_admin: false, role_keys: [], role_names: [], permissions: ["page:pmc:domestic-warehouse-board:view"] } : p.endsWith("/filter-options") ? { stores: [], owners: [] } : { items: [], total: 0 };
    await route.fulfill({ status: 200, contentType: "application/json", body: envelope(data) });
  });
  await page.goto("/#/pmc/domestic-warehouse-board"); await page.getByRole("tab", { name: "打包单审批", exact: true }).click();
  await expect(page.getByText(/打包审批服务请求失败/)).toBeVisible({ timeout: 20000 });
  await expect(page.getByRole("button", { name: /^重\s*试$/ })).toBeVisible();
});

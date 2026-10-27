/** Synthetic reads only: multi-ItemID display must not duplicate the purchase row. */
import { expect, test } from "@playwright/test";

test.use({ channel: process.env.PLAYWRIGHT_CHANNEL, viewport: { width: 1600, height: 1000 } });

test("purchase board displays both verified remark identities on one quantity row", async ({ page }) => {
  test.setTimeout(90_000);
  page.on("pageerror", (error) => console.log("PAGE_ERROR", error.message));
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-item-identities"));
  const writes: string[] = [];
  const identities = [
    { item_id: "11111111111", msku: "SKU-A", gtin: "00012345678905", fulfillment_type: "1" },
    { item_id: "22222222222", msku: "SKU-B", gtin: "00012345678906", fulfillment_type: "1" },
  ];
  const row = {
    purchase_order_sn: "PO-SYNTHETIC", order_item_id: "L1", plan_sn: "P1", plan_sns: ["P1"],
    draft_no: null, order_status: 1, sku: "SKU-TEST", product_name: "合成测试产品",
    stage: { stage_code: "S3", stage_start: null, threshold_days: null, due_date: null,
      overdue_days: 0, overdue_kind: null, alert_due_since: null, stage_start_estimated: false },
    store: { id: "S1", name: "测试店铺", attributed: true }, owner: { uid: null, name: null },
    item_id: { item_id: null, source: "from_plan_remark", source_ref: "P1", matched_at: null,
      match_status: "matched", msku: null, gtin: null, fulfillment_type: null, wfs_not_ready: false, identities },
    quantity_total: 100, quantity_allocated: 100, quantity_received: 0, remaining_quantity: 100,
    progress_ratio: "0", order_date: "2026-10-27", order_create_date: "2026-10-27",
    plan_create_date: null, arrival_date: null, arrival_receipt_order_sn: null,
    purchase_cycle_days: null, approval_cycle_days: null,
    sku_cycle: { value_days: null, source: null, sample_count: null, unstable: false },
    unit_price: null, amount_allocated: null, amount_total: null, currency_code: null,
    calculated_at: "2026-10-27T00:00:00Z",
  };
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    // Vite modules under /src/api/ are JavaScript, not backend API responses.
    if (!path.startsWith("/api/")) return route.fallback();
    if (request.method() !== "GET") writes.push(request.url());
    const data = path === "/api/auth/me"
      ? { id: 16, username: "fixture", display_name: "测试用户", is_super_admin: true,
        role_keys: [], role_names: [], permissions: ["*"] }
      : path === "/api/pmc/purchase/board" ? { items: [row], total: 1 }
      : path.endsWith("/summary") ? { awaiting_arrival_orders: 1, arrival_overdue_orders: 0,
        purchase_overdue_orders: 0, purchase_overdue_plans: 0, average_purchase_cycle_days_90d: null,
        median_purchase_cycle_days_90d: null, purchase_cycle_sample_orders_90d: 0,
        month_purchase_amount: [], unstable_sku_count: 0, itemid_pending_lines: 0,
        wfs_not_ready_lines: 0, unattributed_store_lines: 0, as_of: "2026-10-27" }
      : { items: [], total: 0 };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      success: true, data, error: null, meta: { freshness_at: "2026-10-27T00:00:00Z", rule_version: 1 },
      request_id: "synthetic-item-identities",
    }) });
  });
  await page.goto("/#/pmc/purchase-board", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("多 listing（2）", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("link", { name: /11111111111/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /22222222222/ })).toBeVisible();
  await expect(page.getByText("归属冲突", { exact: true })).toHaveCount(0);
  await expect(page.getByText("共 1 条明细", { exact: true })).toBeVisible();
  expect(writes).toEqual([]);
});

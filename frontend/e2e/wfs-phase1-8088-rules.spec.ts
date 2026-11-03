/** WFS phase 1 (8088 rules) browser acceptance with synthetic API responses; never writes business data. */
import { expect, test, type Page } from "@playwright/test";

test.use({ channel: process.env.PLAYWRIGHT_CHANNEL ?? "msedge", viewport: { width: 1600, height: 1000 } });

const envelope = (data: unknown) => ({ success: true, data, error: null, meta: {}, request_id: "synthetic-wfs-phase1" });
const me = { id: 16, username: "wfs-fixture", is_super_admin: true, permissions: ["*"], role_keys: [], role_names: [] };
const freshness = {
  publication_id: "p1", source_observed_at: new Date(Date.now() - 2 * 36e5).toISOString(),
  published_at: new Date().toISOString(), coverage_start: "2026-07-01", coverage_end: "2026-11-02", stale: false,
};
const boardRow = {
  id: "lx:p1:1", source: "lingxing", shipment_id: "9000001WFB", inbound_order_id: "PMC-9000001WFB",
  store_id: "s1", store_name: "测试店", status: 2, status_name: "RECEIVING_IN_PROGRESS", status_label: "收货中",
  cargo_sync_status: "已申报", lingxing_sync_status: "SYNCED", business_test: false, its: false, pk: "PK-E2E-1",
  sku: "TSKU", product_name: "测试商品", item_id: "1", gtin: "0001", msku: "TSKU-1U", sku_count: 1,
  declared_units: 40, shipped_units: 40, received_units: 30, damaged_units: 0, logistics_code: "LAX2T",
  shipping_codes: ["SP-E2E-1"], shipping_status: "已发货", warehouse_id: "1", actual_delivery_date: "2026-10-01",
  arrival_date: null, expected_arrival_date: "2026-09-28", logistics_numbers: ["ZY-E2E-1"],
  created_at: "2026-09-01T00:00:00Z", updated_at: null, to_await_at: null, to_receive_at: null, to_closed_at: null,
  to_cancelled_at: null, operation_id: null, ticket_id: null, ticket_number: null, order_id: null, label_state: null,
  creation_state: null, ticket_state: null,
  owners: ["测试负责人"], region: "美西", its_inferred: false, baseline_units: 40, baseline_from: "SP", diff_units: -10,
  boxes: 4, eta: "2026-10-01", eta_source: "real", eta_source_label: "沃尔玛签收", eta_passed_days: 32,
  sellable_date: "2026-10-03", sellable_real: true, arrival_bucket: "arrived", shipped_out: true,
  walmart_signed_date: "2026-10-01", walmart_first_receipt: "2026-10-03", d0: "2026-10-01", d0_real: true,
  days_since_d0: 32, external: false, age_days: 63, exception_types: ["收货长期未完成", "签收后长期未收货"],
};
const pendingRow = (overdue: boolean) => ({
  order: { id: "00000000-0000-4000-8000-000000000001", source_account_ref: "fixture", version: 1,
    pk: "PK-E2E-OVERDUE", sku: "TEST-SKU", store_id: "s1", store_name: "测试店", item_id: "123456",
    gtin: "00000000000001", product_name: "测试商品", approved_quantity: 10, customs_value: false,
    box_set: { id: "box", version: 1, total_qty: 10, completed_at: "2026-10-28T00:00:00Z", completed_by: "仓库",
      lines: [{ id: "00000000-0000-4000-8000-000000000002", line_no: 1, boxes: 2, units_per_box: 5 }] } },
  total_boxes: 2, occupied_boxes: 0, available_boxes: 2, available_units: 10, business_test: false,
  occupied_line_ids: [], available_line_ids: ["00000000-0000-4000-8000-000000000002"], blocked_reasons: [],
  can_edit: true, packed_days: overdue ? 6 : 1, overdue,
});

/** Serves the synthetic API and records every request so filter wiring can be asserted. */
async function serve(page: Page): Promise<URL[]> {
  const seen: URL[] = [];
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-wfs-test"));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith("/api/")) return route.fallback();
    seen.push(url);
    const p = url.pathname;
    const onlyOverdue = url.searchParams.get("only_overdue") === "true";
    const data =
      p === "/api/auth/me" ? me
      : p.endsWith("/shipment-board/shipments") ? { items: [boardRow], total: 1, data_asof: freshness.source_observed_at, freshness }
      : p.endsWith("/shipment-board/products") ? { items: [], total: 0, data_asof: freshness.source_observed_at, freshness }
      : p.endsWith("/shipment-board/summary") ? { total: 1, by_status: { "2": 1 }, pending_lingxing_sync: 0, test: 0, received_short: 0,
          by_arrival_bucket: { arrived: 1 }, with_exceptions: 1, external: 0, rule_version: "WFS-RULES-20261010", freshness }
      : p.endsWith("/shipment-board/filter-options") ? { stores: [{ value: "s1", label: "测试店" }], owners: ["测试负责人"], regions: ["美西"],
          arrival_buckets: [{ value: "arrived", label: "已到仓" }] }
      : p.endsWith("/pending-packing/orders") ? { items: [pendingRow(true), ...(onlyOverdue ? [] : [{ ...pendingRow(false), order: { ...pendingRow(false).order, id: "00000000-0000-4000-8000-000000000003", pk: "PK-E2E-FRESH" } }])], total: onlyOverdue ? 1 : 2 }
      : p.endsWith("/pending-packing/summary") ? { completed: 2, ready: 2, test: 0, waiting: 0, no_box: 0, filled_not_done: 0,
          available_boxes: 4, available_units: 20, overdue: 1, overdue_days: 3 }
      : p.endsWith("/pending-packing/filter-options") ? { stores: [{ value: "s1", label: "测试店" }] }
      : p.endsWith("/pending-packing/capabilities") ? { creation_enabled: false, preview_enabled: false, reason: "synthetic" }
      : null;
    if (data === null) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ success: false, data: null, error: { code: "NOT_FOUND" }, meta: {}, request_id: "x" }) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope(data)) });
  });
  return seen;
}

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => console.log("PAGE_ERROR", error.message));
});

test("shipment board shows 8088 columns, exception count and filters by exceptions", async ({ page }) => {
  const seen = await serve(page);
  await page.goto("/#/pmc/wfs/board");
  await expect(page.getByRole("columnheader", { name: "Shipment ID" })).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole("columnheader", { name: "产品负责人" })).toBeVisible();
  const row = page.getByRole("row").filter({ hasText: "9000001WFB" });
  await expect(row.getByText("测试负责人")).toBeVisible();
  await expect(row.locator(".ant-tag-error").getByText("2", { exact: true })).toBeVisible();
  await expect(page.getByText("外部创建·待关联")).toBeVisible();
  await page.getByText("有异常", { exact: true }).click();
  await expect.poll(() => seen.some((u) => u.pathname.endsWith("/shipments") && u.searchParams.get("only_exceptions") === "true")).toBe(true);
});

test("pending packing marks orders packed 3+ days without a shipment and filters to them", async ({ page }) => {
  const seen = await serve(page);
  await page.goto("/#/pmc/wfs/pending-packing");
  await expect(page.getByText("打包完成 6 天未建货件")).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole("row").filter({ hasText: "PK-E2E-FRESH" }).getByText(/天未建货件/)).toHaveCount(0);
  await page.getByText("打包完成满 3 天未建货件").click();
  await expect.poll(() => seen.some((u) => u.pathname.endsWith("/orders") && u.searchParams.get("only_overdue") === "true")).toBe(true);
  await expect(page.getByText("PK-E2E-FRESH")).toHaveCount(0);
});

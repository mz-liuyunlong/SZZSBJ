/** Browser acceptance with synthetic API responses; never writes business data. */
import { expect, test } from "@playwright/test";
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL ?? "msedge", viewport: { width: 1600, height: 1000 } });
test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => console.log("PAGE_ERROR", error.message));
});
const prefix = "/api/pmc/wfs/pending-packing";
const lineId = "00000000-0000-4000-8000-000000000002";
const orderId = "00000000-0000-4000-8000-000000000001";
const row = {
  order: { id: orderId, source_account_ref: "fixture", version: 1, pk: "PK-BROWSER-TEST", sku: "TEST-SKU", product_name: "本地验收商品",
    store_id: "fixture-store", store_name: "测试店", item_id: "123456", gtin: "00000000000001", msku: "TEST-MSKU", approved_quantity: 10, customs_value: false,
    box_set: { id: "box", version: 1, total_qty: 10, completed_at: "2026-10-23T00:00:00Z", completed_by: "仓库",
      lines: [{ id: lineId, line_no: 1, boxes: 2, units_per_box: 5 }] } },
  business_test: true, occupied_line_ids: [] as string[], available_line_ids: [lineId], blocked_reasons: [], can_edit: true,
};
test("choose physical boxes, persist pending draft and refresh occupancy", async ({ page }, info) => {
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-wfs-test"));
  let submitted: Record<string, unknown> | undefined;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.fallback();
    let data: unknown = { items: [], total: 0 };
    if (path === "/api/auth/me") data = { id: 16, username: "wfs-fixture", display_name: "本地验收", is_super_admin: true, permissions: ["*"], role_keys: [], role_names: [] };
    if (path === prefix + "/orders") data = { items: [{ ...row, occupied_line_ids: submitted ? [lineId] : [], available_line_ids: submitted ? [] : [lineId], can_edit: !submitted }], total: 1 };
    if (path === prefix + "/summary") data = { completed: 1, ready: submitted ? 0 : 1, test: 1, waiting: 0, no_box: 0, filled_not_done: 0, available_boxes: submitted ? 0 : 2, available_units: submitted ? 0 : 10 };
    if (path === prefix + "/filter-options") data = { stores: [{ value: "fixture-store", label: "测试店" }] };
    if (path === prefix + "/drafts") { submitted = route.request().postDataJSON(); data = { drafts: [{ id: "draft", number: "WS-BROWSER-TEST", status: "pending", store_id: "fixture-store", business_test: true, actor_uid: "fixture", created_at: "2026-10-23T00:00:00Z", payload: { items: [] } }] }; }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, data, error: null, meta: {}, request_id: "synthetic-wfs" }) });
  });
  await page.goto("/#/pmc/wfs/pending-packing");
  await expect(page.getByRole("checkbox", { name: "选择PK-BROWSER-TEST" })).toBeVisible({ timeout: 30000 });
  await page.getByRole("checkbox", { name: "选择PK-BROWSER-TEST" }).check();
  await page.getByRole("button", { name: /生成货件草稿/ }).click();
  await page.getByLabel("退货街道地址").fill("Test street");
  await page.getByLabel("城市", { exact: true }).fill("Katy");
  await page.getByLabel("州代码").fill("TX");
  await page.getByLabel("邮编").fill("77449");
  await page.getByRole("button", { name: "保存为待审批草稿" }).click();
  await expect(page.getByText(/WS-BROWSER-TEST/)).toBeVisible();
  expect(submitted?.selections).toEqual([{ order_id: orderId, expected_version: 1, expected_box_version: 1, box_line_ids: [lineId] }]);
  await page.getByRole("button", { name: "知道了", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "货件草稿已保存" })).toBeHidden();
  await expect(page.getByRole("checkbox", { name: "选择PK-BROWSER-TEST" })).toBeDisabled();
  await page.screenshot({ path: info.outputPath("pending-packing.png"), fullPage: true });
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

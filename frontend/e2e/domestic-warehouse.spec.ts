/** Browser acceptance uses synthetic receipts and intercepts every backend request. */
import { expect, test } from "@playwright/test";
// CI uses Playwright Chromium; local acceptance can use an installed browser channel.
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL });
const makeBatch = (index: number) => ({
  id: `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`,
  source_account_ref: "synthetic-account", receipt_order_sn: `RCPT-${index}`, line_ordinal: 0,
  purchase_order_sn: `PO-${index}`, source_warehouse_id: "W1", sku: `TEST-SKU-${index}`,
  received_qty: index === 1 ? 0 : 100, receive_time: "2026-10-01 10:00:00",
  received_business_date: index === 2 ? null : "2026-10-01", days_in_warehouse: index === 2 ? null : 18,
  arrival_date_status: index === 2 ? "unknown" : "known", mapping_status: index === 2 ? "unresolved" : "matched",
  links: index === 2 ? [] : [{ id: `link-${index}`, batch_order_sn: `IB-${index}`, batch_no: `B-${index}`,
    store_id: "S1", mapped_qty: 100, mapping_status: "matched", mapping_method: "explicit" }],
});
const envelope = (data: unknown, meta: unknown = {}) => JSON.stringify({
  success: true, data, error: null, meta, request_id: "synthetic-domestic-request",
});
test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => console.error("Domestic browser error:", error.message));
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-domestic-session"));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    // Vite also serves /src/api/*.ts modules; intercept backend URLs only.
    if (!url.pathname.startsWith("/api/")) return route.fallback();
    let data: unknown = {};
    if (url.pathname === "/api/auth/me") {
      data = { id: 9, username: "domestic-test", display_name: "页面验收", is_super_admin: false,
        role_keys: [], role_names: [], permissions: ["page:pmc:domestic-warehouse-board:view", "pmc:domestic-batch:read"] };
    } else if (url.pathname.endsWith("/filter-options")) {
      data = { stores: [{ value: "S1", label: "深圳一店" }, { value: "S2", label: "非沃尔玛店铺" }],
        owners: [{ value: "001", label: "当前负责人甲" }, { value: "002", label: "当前负责人乙" }] };
    } else if (url.pathname.endsWith("/batches/summary")) {
      data = { receipt_batch_count: 51, received_qty: 5000, warehouse_count: 1, matched_batch_count: 50,
        unresolved_batch_count: 1, missing_arrival_date_count: 1, as_of: "2026-10-19" };
    } else if (url.pathname.endsWith("/trace")) {
      data = { batch: makeBatch(1), outbound: { status: "unknown", reason: "source_not_published", events: [] } };
    } else if (url.pathname.endsWith("/batches")) {
      const filtered = Boolean(url.searchParams.get("search") || url.searchParams.get("sku"));
      const first = url.searchParams.get("page") === "2" ? 51 : 1;
      data = { items: filtered ? [] : Array.from({ length: first === 51 ? 1 : 50 }, (_, i) => makeBatch(first + i)),
        total: filtered ? 0 : 51 };
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: envelope(data, {
      source: "new_system_postgresql", source_objects: ["dwd_domestic_receipt_batch"],
      freshness_at: "2026-10-19T00:00:00Z",
    }) });
  });
});

test("loads named store and current owner choices, confirms stable IDs and resets pagination", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/#/pmc/domestic-warehouse-board");
  await expect(page.getByText("RCPT-1", { exact: true })).toBeVisible();
  await page.locator(".ant-pagination-next").click();
  await expect(page.getByText("RCPT-51", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "店铺", exact: true }).click();
  await page.getByRole("checkbox", { name: "店铺选项：S1", exact: true }).click();
  await page.getByRole("checkbox", { name: "店铺选项：S2", exact: true }).click();
  const storeQuery = page.waitForRequest((r) => r.url().includes("/batches?") && new URL(r.url()).searchParams.getAll("store_id").length === 2);
  await page.getByRole("button", { name: "确定", exact: true }).click();
  expect(new URL((await storeQuery).url()).searchParams.get("page")).toBe("1");
  await page.getByRole("combobox", { name: "负责人", exact: true }).click();
  await page.getByRole("combobox", { name: "负责人", exact: true }).fill("当前负责人");
  await page.getByRole("checkbox", { name: "负责人选项：001", exact: true }).click();
  await page.getByRole("checkbox", { name: "负责人选项：002", exact: true }).click();
  await page.screenshot({ path: process.env.TEMP + "/szzsbj-domestic-owner-options.png", animations: "disabled" });
  const ownerQuery = page.waitForRequest((r) => r.url().includes("/batches?") && new URL(r.url()).searchParams.getAll("owner_uid").length === 2);
  const summaryQuery = page.waitForRequest((r) => r.url().includes("/batches/summary?") && new URL(r.url()).searchParams.getAll("owner_uid").length === 2);
  await page.getByRole("button", { name: "确定", exact: true }).click();
  const params = new URL((await ownerQuery).url()).searchParams;
  expect(params.getAll("owner_uid")).toEqual(["001", "002"]);
  expect(params.getAll("store_id")).toEqual(["S1", "S2"]);
  expect(new URL((await summaryQuery).url()).searchParams.getAll("owner_uid")).toEqual(["001", "002"]);
  const reset = page.waitForRequest((r) => r.url().includes("/batches?") && !new URL(r.url()).searchParams.has("owner_uid") && !new URL(r.url()).searchParams.has("store_id"));
  await page.getByRole("button", { name: /重\s*置/ }).click();
  await reset;
});

test("shows option errors and retries without hiding the receipt list", async ({ page }) => {
  let failOptions = true;
  await page.route("**/api/pmc/domestic/filter-options", async (route) => {
    if (!failOptions) return route.fallback();
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({
      success: false, data: null, error: { code: "SERVICE_UNAVAILABLE" }, meta: {}, request_id: "options-test",
    }) });
  });
  await page.goto("/#/pmc/domestic-warehouse-board");
  await expect(page.getByText("店铺与负责人选项加载失败", { exact: true })).toBeVisible();
  await expect(page.getByText("RCPT-1", { exact: true })).toBeVisible();
  failOptions = false;
  await page.getByRole("button", { name: "重试选项", exact: true }).click();
  await expect(page.getByText("店铺与负责人选项加载失败", { exact: true })).toHaveCount(0);
  await page.getByRole("combobox", { name: "店铺", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: "店铺选项：S1", exact: true })).toBeVisible();
});
test("receipt dates, committed search, reset, paging, filters, column settings and help", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/#/pmc/domestic-warehouse-board");
  await expect(page.getByRole("heading", { name: "国内仓看板", exact: true })).toBeVisible();
  await expect(page.getByText("RCPT-1", { exact: true })).toBeVisible();
  await expect(page.getByText("待核实", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "平均在仓天数：—" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "打包单审批" })).toHaveAttribute("aria-disabled", "true");
  await page.screenshot({ path: process.env.TEMP + "/szzsbj-domestic-initial.png", animations: "disabled" });
  const next = page.waitForRequest((r) => new URL(r.url()).searchParams.get("page") === "2");
  await page.locator(".ant-pagination-next").click();
  await next;
  await expect(page.getByText("RCPT-51", { exact: true })).toBeVisible();
  const input = page.getByRole("textbox", { name: "搜索国内仓批次" });
  await input.fill("not-found");
  await expect(page.getByText("RCPT-51", { exact: true })).toBeVisible();
  const searched = page.waitForRequest((r) => r.url().includes("/batches?") && new URL(r.url()).searchParams.get("sku") === "not-found");
  await input.press("Enter");
  const request = await searched;
  expect(new URL(request.url()).searchParams.get("page")).toBe("1");
  await expect(page.getByText("暂无收货批次")).toBeVisible();
  await page.getByRole("button", { name: /重\s*置/ }).click();
  await expect(page.getByText("RCPT-1", { exact: true })).toBeVisible();
  await expect(input).toHaveValue("");
  await page.getByRole("button", { name: "隐藏统计", exact: true }).click();
  await expect(page.getByRole("region", { name: "国内仓统计" })).toHaveCount(0);
  await page.getByRole("button", { name: "显示统计", exact: true }).click();
  await page.getByRole("button", { name: "更多筛选", exact: true }).click();
  await page.getByRole("textbox", { name: "仓库 ID", exact: true }).fill("W1\nW2");
  const filtered = page.waitForRequest((r) => r.url().includes("/batches?") && new URL(r.url()).searchParams.getAll("warehouse_id").length === 2);
  await page.getByRole("button", { name: "应用筛选" }).click();
  await filtered;
  await page.getByRole("button", { name: "列配置", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "详情", exact: true }).first().click();
  await expect(page.getByText("出库追溯尚未接入")).toBeVisible();
  await page.keyboard.press("Escape");
  const help = page.getByRole("link", { name: "？帮助" });
  await expect(help).toHaveAttribute("target", "_blank");
  const popupEvent = page.waitForEvent("popup");
  await help.click();
  const popup = await popupEvent;
  await expect(popup.getByRole("heading", { name: "国内仓看板使用说明" })).toBeVisible();
  await popup.close();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect(page.getByText("RCPT-1", { exact: true })).toBeVisible();
  await expect(page.locator(".ant-drawer-mask")).toHaveCount(0);
  await page.screenshot({ path: process.env.TEMP + "/szzsbj-domestic-board.png", fullPage: true, animations: "disabled" });
});
test("reports forbidden data and can retry an unavailable source", async ({ page }) => {
  await page.route("**/api/pmc/domestic/**", (route) => route.fulfill({ status: 403, contentType: "application/json",
    body: JSON.stringify({ success: false, data: null, error: { code: "FORBIDDEN" }, meta: null, request_id: "synthetic-forbidden" }) }));
  await page.goto("/#/pmc/domestic-warehouse-board");
  await expect(page.getByRole("alert").filter({ hasText: "没有国内仓批次的查看权限" })).toBeVisible();
  await expect(page.getByText("RCPT-1", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^重\s*试$/ })).toBeVisible();
});

test("keeps a narrow viewport contained and submits mapping and sort filters", async ({ page }) => {
  await page.setViewportSize({ width: 800, height: 1000 });
  await page.goto("/#/pmc/domestic-warehouse-board");
  await expect(page.getByText("RCPT-1", { exact: true })).toBeVisible();
  const filtered = page.waitForRequest((r) => r.url().includes("/batches?") && new URL(r.url()).searchParams.get("mapping_status") === "unresolved");
  await page.getByRole("button", { name: "库存批次待关联：1 条" }).click();
  await filtered;
  const sorted = page.waitForRequest((r) => r.url().includes("/batches?") && new URL(r.url()).searchParams.get("sort") === "qty_desc");
  await page.getByRole("button", { name: "更多筛选", exact: true }).click();
  await page.getByRole("combobox", { name: "排序", exact: true }).focus();
  await page.getByRole("combobox", { name: "排序", exact: true }).press("ArrowDown");
  await page.getByText("实收数量：多到少", { exact: true }).click();
  await sorted;
  await page.keyboard.press("Escape");
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("uses screenshot status options and typed batch search without silently ignoring unsupported filters", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/#/pmc/domestic-warehouse-board");
  await expect(page.getByText("RCPT-1", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "状态", exact: true }).focus();
  await page.getByRole("combobox", { name: "状态", exact: true }).press("ArrowDown");
  for (const label of ["在库", "待打包（领星打包单）", "已打包待发", "超时未发", "已发出", "非发货出库"]) {
    await expect(page.getByText(label, { exact: true }).last()).toBeAttached();
  }
  let submittedBusinessStatus = false;
  page.on("request", (request) => {
    if (new URL(request.url()).searchParams.has("business_status")) submittedBusinessStatus = true;
  });
  await page.getByText("非发货出库", { exact: true }).click();
  await expect(page.getByText("业务状态筛选尚未接入", { exact: true })).toBeVisible();
  await expect(page.getByText("RCPT-1", { exact: true })).toHaveCount(0);
  expect(submittedBusinessStatus).toBe(false);
  await page.getByRole("button", { name: "清除状态", exact: true }).click();
  await expect(page.getByText("RCPT-1", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "批量搜索国内仓批次" }).click();
  await page.getByRole("textbox", { name: "批量搜索国内仓批次内容" }).fill("SKU-A\nSKU-B\nSKU-A");
  const batchRequest = page.waitForRequest((r) => r.url().includes("/batches?") && new URL(r.url()).searchParams.getAll("sku").length === 2);
  await page.getByRole("button", { name: /^搜\s*索$/ }).last().click();
  expect(new URL((await batchRequest).url()).searchParams.getAll("sku")).toEqual(["SKU-A", "SKU-B"]);
  await expect(page.getByRole("button", { name: "导出国内仓批次" })).toBeDisabled();
  await page.getByRole("button", { name: /重\s*置/ }).click();
  await expect(page.getByRole("textbox", { name: "搜索国内仓批次" })).toHaveValue("");
  await expect(page.getByText("RCPT-1", { exact: true })).toBeVisible();
  await page.screenshot({ path: process.env.TEMP + "/szzsbj-domestic-search.png", animations: "disabled" });
});

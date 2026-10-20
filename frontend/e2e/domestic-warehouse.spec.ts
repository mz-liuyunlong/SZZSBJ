/** Synthetic API and files; all backend traffic is intercepted. */
import { expect, test } from "@playwright/test";
import { makeInbound, previewRow } from "./fixtures/domesticInbound";
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL });
const meta = { source: "new_system_postgresql", source_objects: ["mart_domestic_inbound_batch_board"], freshness_at: "2026-10-20T02:00:00Z",
  data_status: "ready", publication_ids: ["synthetic-publication"], coverage_start: "2026-10-01", coverage_end: "2026-10-21", as_of: "2026-10-20" };
const envelope = (data: unknown, metadata: unknown = meta) => JSON.stringify({ success: true, data, error: null, meta: metadata, request_id: "synthetic-inbound-test" });
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-inbound-session"));
  await page.route("**/api/**", async (route) => {
    const u = new URL(route.request().url());
    if (!u.pathname.startsWith("/api/")) return route.fallback();
    let data: unknown;
    if (u.pathname === "/api/auth/me") data = { id: 9, username: "inbound-test", display_name: "合成验收", is_super_admin: false, role_keys: [], role_names: [], permissions: ["page:pmc:domestic-warehouse-board:view", "pmc:domestic-batch:read"] };
    else if (u.pathname === "/api/pmc/domestic/inbound-batches/filter-options") data = {
      stores: [{value: "001", label: "惠州店"}, {value: "002", label: "第二店铺"}],
      owners: [{value: "0001", label: "产品负责人甲"}, {value: "0002", label: "产品负责人乙"}],
      statuses: [ ["in_stock", "在库"], ["approved", "待打包（领星打包单已建）"], ["packed", "已打包待发"],
        ["overdue", "超时未发"], ["shipped", "已发出"], ["other_out", "非发货出库"]
      ].map(([value, label]) => ({value, label, disabled: true, reason: "状态事实待接入"})), owner_basis: "current_product_owner",
    };
    else if (u.pathname === "/api/pmc/domestic/inbound-batches/summary") data = { board_row_count: 51, inbound_order_count: 51, sku_count: 51, balance_qty: 2000,
      unknown_inventory_row_count: 0, total_inbound_qty: 5100, unknown_inbound_qty_count: 0, missing_arrival_date_count: 0, as_of: "2026-10-20" };
    else if (u.pathname.endsWith("/trace")) data = { batch: makeInbound(), inbound_events: previewRow().inbound_events, outbound_status: "unknown", outbound_reason: "source_not_published" };
    else if (u.pathname === "/api/pmc/domestic/inbound-batches") {
      const first = u.searchParams.get("page") === "2" ? 51 : 1;
      data = { items: Array.from({ length: first === 51 ? 1 : 50 }, (_, i) => makeInbound(i + first)), total: 51 };
    } else return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ success: false, data: null, error: { code: "UNEXPECTED_ENDPOINT" }, meta: {}, request_id: "test" }) });
    return route.fulfill({ status: 200, contentType: "application/json", body: envelope(data) });
  });
});

test("uses inbound list, stable pagination, precise batch search, trace and help", async ({ page }) => {
  const oldRequests: string[] = [];
  page.on("request", (r) => { if (/\/api\/pmc\/domestic\/(batches|filter-options)/.test(r.url())) oldRequests.push(r.url()); });
  await page.setViewportSize({ width: 1920, height: 1080 }); await page.goto("/#/pmc/domestic-warehouse-board");
  await expect(page.getByText("IB-1", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "已知入库总量：5,100 件" })).toBeVisible();
  await page.locator(".ant-pagination-next").click(); await expect(page.getByText("IB-51", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "搜索类型", exact: true }).focus();
  await page.getByRole("combobox", { name: "搜索类型", exact: true }).press("ArrowDown"); await page.getByText("入库单号", { exact: true }).last().click();
  await page.getByRole("button", { name: "批量搜索国内仓批次" }).click();
  await page.getByRole("textbox", { name: "批量搜索国内仓批次内容" }).fill("IB-1\nIB-2\nIB-1");
  const requested = page.waitForRequest((r) => r.url().includes("/inbound-batches?") && new URL(r.url()).searchParams.getAll("inbound_order_sn").length === 2);
  await page.getByRole("button", { name: /^搜\s*索$/ }).last().click();
  const q = new URL((await requested).url()).searchParams; expect(q.getAll("inbound_order_sn")).toEqual(["IB-1", "IB-2"]); expect(q.get("page")).toBe("1");
  await page.getByRole("button", { name: "核对详情" }).first().click();
  await expect(page.getByText("入库流水证据", { exact: true })).toBeVisible(); await expect(page.getByText("123456789012345678", { exact: true })).toBeVisible();
  await expect(page.getByText("未知（无分摊证据）", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).last().click();
  await expect(page.getByRole("combobox", { name: "负责人", exact: true })).toBeEnabled();
  const popup = page.waitForEvent("popup"); await page.getByRole("link", { name: "？帮助", exact: true }).click();
  await expect((await popup).getByRole("heading", { name: "国内仓看板使用说明", exact: true })).toBeVisible();
  expect(oldRequests).toEqual([]);
});


test("loads real option contract, commits IDs to list and summary and resets pagination", async ({ page }) => {
  await page.setViewportSize({width:1920,height:1080});
  const requests: URL[] = [];
  page.on("request", (request) => { if (request.url().includes("/inbound-batches")) requests.push(new URL(request.url())); });
  await page.goto("/#/pmc/domestic-warehouse-board");
  await expect(page.getByText("IB-1", { exact: true })).toBeVisible();
  await page.locator(".ant-pagination-next").click();
  await expect(page.getByText("IB-51", { exact: true })).toBeVisible();
  for (const [field, labels] of [["店铺", ["惠州店"]], ["负责人", ["产品负责人甲", "产品负责人乙"]]] as const) {
    const input = page.getByRole("combobox", { name: field, exact: true });
    await input.focus(); await input.press("ArrowDown");
    for (const label of labels) await page.getByText(label, { exact: true }).last().click();
    await page.getByRole("button", { name: "确定", exact: true }).click();
    await expect(page.getByText("IB-1", { exact: true })).toBeVisible();
  }
  await expect.poll(() => requests.some((url) => url.pathname.endsWith("/summary") && url.searchParams.getAll("owner_uid").length === 2)).toBe(true);
  for (const ending of ["/inbound-batches", "/summary"]) {
    const url = requests.filter((r) => r.pathname.endsWith(ending) && r.searchParams.has("owner_uid")).at(-1)!;
    expect(url.searchParams.getAll("owner_uid")).toEqual(["0001", "0002"]);
    expect(url.searchParams.getAll("store_id")).toEqual(["001"]);
    if (ending === "/inbound-batches") expect(url.searchParams.get("page")).toBe("1");
  }
  const status = page.getByRole("combobox", { name: "业务状态", exact: true });
  await status.click();
  await expect(page.getByText("非发货出库", {exact:true}).last()).toBeVisible();
  await expect(page.locator(".ant-select-item-option-disabled")).toHaveCount(6);
  if (process.env.DOMESTIC_FILTER_SCREENSHOT) await page.screenshot({ path: process.env.DOMESTIC_FILTER_SCREENSHOT, animations: "disabled" });
  await status.press("Escape");
  await page.getByRole("button", { name: /重\s*置/ }).click();
  await expect.poll(() => requests.filter((u) => u.pathname.endsWith("/inbound-batches")).at(-1)?.searchParams.has("owner_uid")).toBe(false);
  await expect(page.getByText("全部负责人", { exact: true })).toBeVisible();
});

test("option failures are visible and independently retryable", async ({ page }) => {
  let fail = true;
  await page.route("**/api/pmc/domestic/inbound-batches/filter-options**", async (route) => {
    if (!fail) return route.fallback();
    return route.fulfill({status: 500, contentType: "application/json", body: JSON.stringify({success:false, data:null, error:{code:"INTERNAL_ERROR"}, meta:{}, request_id:"test"})});
  });
  await page.goto("/#/pmc/domestic-warehouse-board");
  await expect(page.getByText("筛选选项加载失败", {exact:true})).toBeVisible();
  await expect(page.getByText("IB-1", {exact:true})).toBeVisible();
  fail = false;
  await page.getByRole("button", {name:"重试筛选选项",exact:true}).click();
  await expect(page.getByText("筛选选项加载失败", {exact:true})).toHaveCount(0);
  const owner = page.getByRole("combobox", {name:"负责人",exact:true});
  await owner.focus(); await owner.press("ArrowDown");
  await expect(page.getByText("产品负责人甲", {exact:true})).toBeVisible();
});

test("distinguishes missing publication, proven empty publication and service failure", async ({ page }) => {
  let state = "missing";
  await page.route("**/api/pmc/domestic/inbound-batches**", async (route) => {
    if (route.request().url().includes("/filter-options")) return route.fallback();
    if (state === "error") return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ success: false, data: null, error: { code: "INTERNAL_ERROR" }, meta: {}, request_id: "safe-test" }) });
    const data = new URL(route.request().url()).pathname.endsWith("summary")
      ? { board_row_count: 0, inbound_order_count: 0, sku_count: 0, balance_qty: 0, unknown_inventory_row_count: 0, total_inbound_qty: 0, unknown_inbound_qty_count: 0, missing_arrival_date_count: 0, as_of: "2026-10-20" }
      : { items: [], total: 0 };
    return route.fulfill({ status: 200, contentType: "application/json", body: envelope(data, { ...meta, data_status: state === "missing" ? "not_published" : "ready", publication_ids: state === "missing" ? [] : meta.publication_ids }) });
  });
  await page.goto("/#/pmc/domestic-warehouse-board"); await expect(page.getByText("尚未发布入库数据", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "已知入库总量：—" })).toBeVisible();
  state = "empty"; await page.reload();
  await expect(page.getByText("暂无入库批次", { exact: true })).toBeVisible(); await expect(page.getByRole("button", { name: "已知入库总量：0 件" })).toBeVisible();
  state = "error"; await page.reload();
  await expect(page.getByText(/入库数据服务暂不可用/)).toBeVisible(); await expect(page.getByRole("button", { name: "已知入库总量：—" })).toBeVisible();
});

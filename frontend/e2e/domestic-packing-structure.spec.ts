/** Structure-only acceptance: no packing orders, sample mode or simulated business writes. */
import { expect, test } from "@playwright/test";
import { join } from "node:path";
import { tmpdir } from "node:os";

test.use({ channel: process.env.PLAYWRIGHT_CHANNEL });

const envelope = (data: unknown) => JSON.stringify({
  success: true, data, error: null, meta: { freshness_at: null }, request_id: "packing-structure-test",
});

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("szzsbj_auth_token", "synthetic-structure-session");
    sessionStorage.setItem("szzsbj:page-state:domestic-board:packing-structure-test:tab", JSON.stringify("packing"));
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.fallback();
    const data = path === "/api/auth/me"
      ? { id: 15, username: "packing-structure-test", display_name: "页面结构验收", is_super_admin: false,
        role_keys: [], role_names: [], permissions: ["page:pmc:domestic-warehouse-board:view", "pmc:domestic-batch:read"] }
      : path.endsWith("/filter-options") ? { stores: [], owners: [] }
      : path.endsWith("/batches/summary")
        ? { receipt_batch_count: 0, received_qty: 0, warehouse_count: 0, matched_batch_count: 0,
          unresolved_batch_count: 0, missing_arrival_date_count: 0, as_of: "2026-10-19" }
        : { items: [], total: 0 };
    await route.fulfill({ status: 200, contentType: "application/json", body: envelope(data) });
  });
});

test("shows screenshot columns and unavailable actions without data or packing requests", async ({ page }) => {
  const businessRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/pmc/")) businessRequests.push(request.url());
  });
  await page.setViewportSize({ width: 1920, height: 1000 });
  await page.goto("/#/pmc/domestic-warehouse-board");
  await expect(page.getByRole("tab", { name: "打包单（仓库）", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("alert")).toContainText("打包单服务待接入");
  await expect(page.getByText("打包单查询服务尚未接入，暂不展示业务数据")).toBeVisible();
  for (const title of ["审批日期", "打包单", "到仓日期", "入库单号", "采购单号", "SKU", "店铺", "ItemID", "GTIN", "产品标签", "操作"]) {
    await expect(page.getByRole("columnheader", { name: new RegExp(title) }).first()).toBeAttached();
  }
  for (const name of ["标签 PDF", "填装箱", "打包完成"]) {
    await expect(page.getByRole("button", { name, exact: true })).toBeDisabled();
  }
  await expect(page.getByRole("combobox", { name: "打包单店铺", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: /示例|预览/ })).toHaveCount(0);
  expect(businessRequests).toEqual([]);
  await expect(page.locator(".domestic-packing .ant-pagination")).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: join(tmpdir(), "szzsbj-domestic-packing-structure.png"), animations: "disabled" });
});

test("keeps UI filter and pagination state, resets filters, and preserves the batch tab", async ({ page }) => {
  const requests: { path: string; method: string }[] = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/api/pmc/")) requests.push({ path, method: request.method() });
  });
  await page.goto("/#/pmc/domestic-warehouse-board");
  await expect(page.getByRole("search", { name: "仓库打包单筛选" })).toBeVisible();
  const input = page.getByRole("textbox", { name: "搜索仓库打包单" });
  await input.fill("filter-only");
  await input.press("Enter");
  const status = page.getByRole("combobox", { name: "打包状态", exact: true });
  await status.focus();
  await status.press("ArrowDown");
  await page.getByText("已打包待发", { exact: true }).click();
  await expect(page.locator(".domestic-packing__toolbar .ant-select-selection-item").filter({ hasText: "已打包待发" })).toBeVisible();
  await page.locator(".ant-pagination-options-size-changer .ant-select-selector").click();
  await page.getByText(/100\s*(条\/页|\/ page)/, { exact: true }).click();
  await expect(page.locator(".ant-pagination-options-size-changer")).toContainText("100");
  expect(requests).toEqual([]);
  await page.getByRole("button", { name: "重置打包单筛选" }).click();
  await expect(input).toHaveValue("");
  await expect(page.locator(".domestic-packing__toolbar .ant-select-selection-item").filter({ hasText: "待打包" })).toBeVisible();
  await page.getByRole("tab", { name: "批次看板", exact: true }).click();
  await expect(page.getByRole("search", { name: "国内仓看板筛选" })).toBeVisible();
  await expect(page.getByText("暂无收货批次", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "打包单（仓库）", exact: true }).click();
  await expect(page.locator(".ant-pagination-options-size-changer")).toContainText("100");
  expect(requests.every((request) => request.method === "GET" && /\/(batches(\/summary)?|filter-options)$/.test(request.path))).toBe(true);
});

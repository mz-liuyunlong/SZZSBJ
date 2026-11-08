import { expect, test, type Page } from "@playwright/test";
import { DEFAULT_RULES } from "../src/pages/products/clearance/clearanceModel";

/**
 * Browser contract for the real clearance APIs using transport-level fixtures.
 * Intercept every /api/ request; never contact local or production databases.
 * Do not resurrect the old DEMO-row/localStorage write workflow.
 */
const item = {
  source_account_ref: "TEST2601",
  store_id: "store-1",
  item_id: "100101",
  listing_id: "test-listing-101",
  title: "Test Walmart Listing",
  product_name: "测试 WFS 清货商品",
  local_name: "测试 WFS 清货商品",
  sku: "TEST-SKU-101",
  msku: "TEST-MSKU-101",
  store_name: "测试店铺",
  owner: "测试运营",
  owner_name: "测试运营",
  picture_url: null,
  available: 300,
  price_amount: "15.99",
  risk: "medium",
  reasons: ["预计售罄时间超过中风险阈值"],
  signals: [],
  data_gaps: [],
  rule_version: 1,
  metrics: {
    listing_days: 80,
    sales_7d: 20, sales_14d: 45, sales_30d: 100,
    profit_7d_usd: 31.98, profit_14d_usd: 88, profit_30d_usd: 223.86,
    purchase_unit_cost_usd: 8,
    unit_inventory_cost_usd: 9,
    capital_at_cost_usd: 2700,
    sellout_days: 90,
    rating: 4.5, review_count: 33, returns_30d: 1,
  },
};

const retired = new Set([
  "mediumAge", "agedLotDays", "agedLotMin", "feeAgeDays", "feeWarningDays",
  "agedRatioPercent", "enableAged", "enableAverageAge", "enableNearFee",
  "enableAgedRatio",
]);
type RuleConfig = Record<string, number | boolean>;
type RulePayload = { expected_version: number; config: RuleConfig; reason: string };
type ApplyPayload = {
  source_account_ref: string; store_id: string; item_id: string;
  qty: number; reason: string; methods: string[]; note: string;
  planned_completion_date?: string;
};

function initialConfig(): RuleConfig {
  return {
    ...Object.fromEntries(Object.entries(DEFAULT_RULES).filter(([key]) => !retired.has(key))),
    coverageLookback: 30,
    newProductProtectionDays: 60,
    minBaselineSales7: 10,
    minSalesDropUnits7: 5,
    minReturns30: 5,
    minReturnSales30: 30,
    minReviewCount: 10,
  };
}

async function prepare(page: Page, initialVersion = 1) {
  const writes: string[] = [];
  const savedRules: RulePayload[] = [];
  const applications: Array<Record<string, unknown>> = [];
  const history: Array<Record<string, unknown>> = [];
  let version = initialVersion;
  let config = initialConfig();

  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-clearance-e2e"));
  await page.route("**/api/**", async route => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (!pathname.startsWith("/api/")) return route.fallback();
    const method = request.method();
    if (method !== "GET") writes.push(method + " " + pathname);
    let data: unknown = { items: [], total: 0 };

    if (pathname === "/api/auth/me") {
      data = {
        id: 16, username: "clearance-e2e", display_name: "清货测试",
        is_super_admin: true, role_keys: [], role_names: [], permissions: ["*"],
      };
    } else if (pathname === "/api/clearance/filter-options") {
      data = {
        stores: [{ value: "TEST2601::store-1", label: "测试店铺", source_account_ref: "TEST2601" }],
        owners: [{ value: "测试运营", label: "测试运营" }],
        risks: [{ value: "medium", label: "中风险" }],
      };
    } else if (pathname === "/api/clearance/listings") {
      data = {
        items: [item], page: 1, page_size: 50, has_more: false,
        total: 1, total_scope: "all_wfs_stock_eligible",
        rule_version: version, risk_model_ready: true,
      };
    } else if (pathname === "/api/clearance/listing") {
      data = item;
    } else if (pathname === "/api/clearance/lifecycle-overrides") {
      data = { items: [] };
    } else if (pathname === "/api/clearance/rules" && method === "GET") {
      data = {
        version, persisted: version > 0,
        config: { ...config }, catalog: [], can_edit: true,
      };
    } else if (pathname === "/api/clearance/rules" && method === "PUT") {
      const payload = request.postDataJSON() as RulePayload;
      if (payload.expected_version !== version) {
        await route.fulfill({
          status: 409, contentType: "application/json",
          body: JSON.stringify({
            success: false, data: null, error: { code: "CLEARANCE_RULE_VERSION_CONFLICT" },
            meta: null, request_id: "mock-conflict",
          }),
        });
        return;
      }
      savedRules.push(payload);
      config = { ...payload.config };
      version += 1;
      history.unshift({
        version, changed_by: "clearance-e2e", changed_at: "2026-11-08T00:00:00Z",
        change_reason: payload.reason,
      });
      data = { version, recalculation: "not_dispatched" };
    } else if (pathname === "/api/clearance/rules/history") {
      data = { items: [...history], page: 1, page_size: 20 };
    } else if (pathname === "/api/clearance/applications" && method === "POST") {
      const payload = request.postDataJSON() as ApplyPayload;
      const id = "mock-clearance-application-001";
      applications.push({
        id,
        source_account_ref: payload.source_account_ref,
        store_id: payload.store_id,
        item_id: payload.item_id,
        applicant_ref: "clearance-e2e",
        status: "pending",
        title: item.product_name,
        local_sku: item.sku,
        msku: item.msku,
        store_name: item.store_name,
        owner_ref: item.owner_name,
        requested_qty: payload.qty,
        approved_qty: null,
        sold_qty: 0,
        reason: payload.reason,
        note: payload.note,
        methods_json: payload.methods,
        risk_at_submission: "medium",
        current_risk: "medium",
        rule_version: version,
        version: 1,
        submitted_at: "2026-11-08T10:00:00Z",
        approved_at: null,
        approved_date_la: null,
        planned_completion_date: payload.planned_completion_date ?? null,
        finished_at: null,
        finish_reason: null,
      });
      data = { id, approval_id: "mock-approval-001", status: "pending" };
    } else if (pathname === "/api/clearance/applications") {
      data = { items: [...applications], total: applications.length, page: 1, page_size: 100 };
    } else if (pathname.startsWith("/api/clearance/applications/")) {
      const id = pathname.slice("/api/clearance/applications/".length);
      data = { application: applications.find(app => app.id === id), current: item, events: [] };
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true, data, error: null, meta: {}, request_id: "mock-clearance-e2e",
      }),
    });
  });

  return {
    writes, savedRules, applications,
    get version() { return version; },
    get config() { return config; },
  };
}

test("clearance renders the real Listing API model in the existing native table", async ({ page }) => {
  const mock = await prepare(page);
  await page.goto("/#/products/clearance-center");
  await expect(page.getByRole("heading", { name: "WFS 清货中心" })).toBeVisible();
  await expect(page.locator("iframe")).toHaveCount(0);
  await expect(page.locator(".clearance-main-card .ant-pro-table")).toHaveCount(1);
  await expect(page.locator(".clearance-main-card .ant-table-thead th.ant-table-cell-fix-left")).toHaveCount(2);
  await expect(page.locator(".clearance-period-segmented .ant-segmented-item-selected")).toContainText("30天");

  const listing = page.locator(".clearance-main-card .ant-table-row").filter({ hasText: item.sku });
  await expect(listing).toContainText(item.item_id);
  await expect(listing).toContainText("$223.86");
  await page.locator(".clearance-period-segmented").getByText("7天", { exact: true }).click();
  await expect(listing).toContainText("$31.98");

  await page.getByRole("button", { name: "规则配置" }).click();
  await expect(page.locator(".clearance-rules-drawer")).toBeVisible();
  await expect(page.getByText("自动识别条件", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "保存并应用" })).toBeDisabled();
  await page.keyboard.press("Escape");
  await page.getByRole("tab", { name: /清货管理/ }).click();
  await expect(page.getByRole("region", { name: "清货管理表格" })).toContainText("暂无符合条件的清货申请");
  expect(mock.writes).toEqual([]);
});

test("manual single-Item WFS application submits only through the scoped real API", async ({ page }) => {
  const mock = await prepare(page);
  await page.goto("/#/products/clearance-center");
  await expect(page.locator(".clearance-main-card .ant-table-row").filter({ hasText: item.sku })).toBeVisible();

  await page.locator(".clearance-toolbar").getByRole("button", { name: "申请 SKU" }).click();
  const chooser = page.getByRole("dialog", { name: /主动申请\s*SKU/ });
  await expect(chooser).toBeVisible();
  const row = chooser.locator(".clearance-wizard-table .ant-table-row").filter({ hasText: item.sku });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "选择商品" }).click();
  await chooser.getByRole("button", { name: "下一步", exact: true }).click();

  await expect(chooser.locator(".clearance-wizard-existing-form")).toBeVisible();
  const reason = chooser.locator(".ant-form-item").filter({ hasText: "清货原因" }).locator(".ant-select");
  await reason.click();
  await page.locator(".ant-select-dropdown:visible .ant-select-item-option:not(.ant-select-item-option-disabled)").first().click();
  await chooser.getByRole("checkbox", { name: "广告清货" }).check();
  await chooser.getByRole("textbox", { name: "申请说明" }).fill("真实 API 合同测试，不连接实际后端或业务数据库");

  await chooser.getByRole("button", { name: "提交申请" }).click();
  await expect.poll(() => mock.applications.length).toBe(1);
  await expect(chooser).toHaveCount(0);
  expect(mock.applications[0].source_account_ref).toBe(item.source_account_ref);
  expect(mock.applications[0].store_id).toBe(item.store_id);
  expect(mock.applications[0].item_id).toBe(item.item_id);
  expect(mock.applications[0].methods_json).toEqual(["广告清货"]);
  expect(mock.writes).toEqual(["POST /api/clearance/applications"]);

  await page.getByRole("tab", { name: /清货管理/ }).click();
  await expect(page.getByRole("region", { name: "清货管理表格" })).toContainText(item.sku);
  await expect(page.getByRole("region", { name: "清货管理表格" })).toContainText("待审批");
});

test("rules first-save through PUT, preserve hidden fields, and survive page reload", async ({ page }) => {
  const mock = await prepare(page, 0);
  await page.goto("/#/products/clearance-center");
  await expect(page.getByRole("heading", { name: "WFS 清货中心" })).toBeVisible();
  await page.getByRole("button", { name: "规则配置" }).click();
  const drawer = page.locator(".clearance-rules-drawer");
  await expect(drawer).toBeVisible();
  const coverage = drawer.locator(".clearance-explain-fields .clearance-explain-field").first().locator("input");
  await expect(coverage).toHaveValue("180");
  const save = drawer.getByRole("button", { name: "保存并应用" });
  await expect(save).toBeEnabled();

  await coverage.fill("200");
  await coverage.press("Tab");
  await save.click();
  await expect.poll(() => mock.savedRules.length).toBe(1);
  expect(mock.savedRules[0].expected_version).toBe(0);
  expect(mock.savedRules[0].config.highCoverage).toBe(200);
  expect(mock.savedRules[0].config.newProductProtectionDays).toBe(60);
  expect(mock.savedRules[0].config.coverageLookback).toBe(30);
  expect(mock.savedRules[0].config.enableRepeatBacklog).toBe(false);
  for (const key of retired) expect(key in mock.savedRules[0].config).toBe(false);
  expect(mock.writes).toEqual(["PUT /api/clearance/rules"]);
  await expect.poll(() => mock.version).toBe(1);

  await page.reload();
  await expect(page.getByRole("heading", { name: "WFS 清货中心" })).toBeVisible();
  await page.getByRole("button", { name: "规则配置" }).click();
  const refreshed = page.locator(".clearance-rules-drawer");
  await expect(refreshed.locator(".clearance-explain-fields .clearance-explain-field").first().locator("input")).toHaveValue("200");
  await expect(refreshed.getByRole("button", { name: "保存并应用" })).toBeDisabled();
  expect(mock.config.highCoverage).toBe(200);
  expect(mock.writes).toEqual(["PUT /api/clearance/rules"]);
});

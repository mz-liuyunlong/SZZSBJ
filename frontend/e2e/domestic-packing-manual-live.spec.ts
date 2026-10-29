/** Synthetic local DB acceptance: all writes live in a rollback-only transaction. */
import { expect, test } from "@playwright/test";
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL });
test.skip(process.env.PACKING_LIVE_E2E !== "1", "requires isolated local fixture bridge");
test("manual source selection and submission leave edit without row approve or reject", async ({ page }, testInfo) => {
  page.on("pageerror", (error) => console.log("PAGE_ERROR", error.message));
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-local-test"));
  await page.route("**/api/**", async (route) => {
    const u = new URL(route.request().url());
    if (!u.pathname.startsWith("/api/")) return route.fallback();
    if (u.pathname.includes("/packing-approval/")) {
      const response = await route.fetch({ url: "http://127.0.0.1:8012" + u.pathname + u.search });
      return route.fulfill({ response });
    }
    const data = u.pathname === "/api/auth/me" ? { id: 16, username: "fixture", display_name: "本地验收", is_super_admin: false, role_keys: [], role_names: [], permissions: ["page:pmc:domestic-warehouse-board:view", ...["approve", "reject", "manual-create"].map((k) => "action:pmc:domestic-warehouse-board:packing-" + k)] }
      : u.pathname.endsWith("/filter-options") ? { stores: [], owners: [] } : { items: [], total: 0 };
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, data, error: null, meta: { publication_ids: [], data_status: "not_published", freshness_at: null }, request_id: "fixture" }) });
  });
  await page.goto("/#/pmc/domestic-warehouse-board");
  await page.getByRole("tab", { name: "打包单审批", exact: true }).click();
  await expect(page.getByRole("button", { name: "系统打包单", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "手工添加打包单", exact: true }).click();
  const modal = page.getByRole("dialog", { name: "手工添加打包单", exact: true });
  await expect(modal.getByRole("combobox", { name: "目标店铺 / ItemID" })).toBeDisabled();
  await modal.getByRole("combobox", { name: "入库单 × SKU" }).click();
  await page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option").first().click();
  await expect(modal.getByRole("combobox", { name: "目标店铺 / ItemID" })).toBeEnabled();
  await modal.getByRole("combobox", { name: "目标店铺 / ItemID" }).click();
  await page.locator('.ant-select-item-option[title="fixture-store / 100000"]').click();
  await expect(modal.locator(".domestic-approval__customs-select")).toContainText("报关");
  await modal.getByRole("spinbutton", { name: "备货数量" }).fill("2");
  await modal.getByRole("textbox", { name: "添加原因（必填）" }).fill("本地手工分批验收");
  const submitted = page.waitForResponse((r) => r.url().endsWith("/packing-approval/manual") && r.request().method() === "POST");
  await modal.getByRole("button", { name: "提交审批", exact: true }).click();
  const response = await submitted;
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(result.data.status).toBe("pending");
  await expect(modal).not.toBeVisible();
  const row = page.locator(`tr[data-row-key="${result.data.id}"]`);
  await expect(row).toContainText("手工待审批");
  await row.getByRole("combobox", { name: /^是否报关 / }).focus();
  await row.getByRole("combobox", { name: /^是否报关 / }).press("ArrowDown");
  await expect(page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option')).toHaveCount(2);
  await page.locator('.ant-select-item-option[title="不报关"]').click();
  await expect(row).toContainText("人工");
  await page.screenshot({ path: testInfo.outputPath("customs-actions.png"), fullPage: true });
  await expect(row.getByRole("button", { name: /修\s*改/ })).toBeVisible();
  await expect(row.getByRole("button", { name: "审批通过", exact: true })).toHaveCount(0);
  await expect(row.getByRole("button", { name: "驳回", exact: true })).toHaveCount(0);
});

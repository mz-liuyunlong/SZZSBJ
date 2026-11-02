/** Local navigation acceptance; mocked reads only, no database or write requests. */
import { expect, test, type Page } from "@playwright/test";
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL, viewport: { width: 1440, height: 1000 } });
async function setup(page: Page, legacy = false) {
  await page.addInitScript((old) => {
    localStorage.setItem("szzsbj_auth_token", "synthetic-pmc-navigation");
    if (old) sessionStorage.setItem("tab_workspace", JSON.stringify({ version: 1,
      openPaths: ["/pmc/domestic-warehouse-board", "/pmc/wfs"], activePath: "/pmc/domestic-warehouse-board" }));
  }, legacy);
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.fallback();
    const data = path === "/api/auth/me" ? { id: 16, username: "nav-fixture", display_name: "导航本地验收", is_super_admin: true, role_keys: [], role_names: [], permissions: ["*"] }
      : path.endsWith("/filter-options") ? { stores: [], owners: [] }
      : path.endsWith("/packing-warehouse/orders/summary") ? { todo: 0, packed: 0 }
      : path.endsWith("/packing-approval/summary") ? { pending: 0, overdue: 0, blocked: 0, approved: 0 }
      : { items: [], total: 0 };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, data, error: null,
      meta: { publication_ids: [], data_status: "not_published", freshness_at: null }, request_id: "synthetic-pmc-nav" }) });
  });
}
test("PMC has expanded groups and three independent pages without internal tabs", async ({ page }, info) => {
  await setup(page);
  const writes: string[] = [];
  page.on("request", (r) => { if (new URL(r.url()).pathname.startsWith("/api/pmc/") && r.method() !== "GET") writes.push(r.url()); });
  await page.goto("/#/pmc/domestic/batches");
  await expect(page.getByRole("heading", { name: "批次看板", exact: true })).toBeVisible();
  await page.getByRole("menuitem", { name: "PMC", exact: true }).click();
  const menu = page.getByRole("menu", { name: "PMC二级导航" });
  await expect(menu.getByRole("menuitem", { name: "批次看板", exact: true })).toBeVisible();
  await expect(menu.getByRole("menuitem", { name: /系统货件/ })).toHaveCount(0);
  await expect(menu.getByRole("menuitem", { name: "待发货打包单", exact: true })).toBeVisible();
  await expect(menu).not.toContainText("28");
  await expect(menu).not.toContainText("国内仓看板");
  const before = page.url();
  await menu.getByText("国内仓", { exact: true }).click();
  expect(page.url()).toBe(before);
  await expect(menu.getByRole("menuitem", { name: "批次看板", exact: true })).toBeVisible();
  await expect(menu.locator(".ant-menu-submenu")).toHaveCount(0);
  await expect(menu.locator(".ant-menu-item-group-title")).toHaveText(["国内仓", "WFS"]);
  await menu.getByRole("menuitem", { name: "打包单审批", exact: true }).click();
  await expect(page).toHaveURL(/#\/pmc\/domestic\/packing-approval$/);
  await expect(page.getByRole("heading", { name: "打包单审批", exact: true })).toBeVisible();
  await expect(page.locator(".domestic-board .ant-tabs")).toHaveCount(0);
  await page.getByRole("menuitem", { name: "PMC", exact: true }).click();
  await menu.getByRole("menuitem", { name: "打包单（仓库）", exact: true }).click();
  await expect(page).toHaveURL(/#\/pmc\/domestic\/packing-warehouse$/);
  await expect(page.getByRole("button", { name: "刷新仓库列表", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "批次看板", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "打包单审批", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "打包单（仓库）", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "国内仓看板", exact: true })).toHaveCount(0);
  await page.getByRole("tab", { name: "批次看板", exact: true }).click();
  await page.getByRole("menuitem", { name: "PMC", exact: true }).click();
  await page.screenshot({ path: info.outputPath("pmc-navigation.png"), fullPage: true, animations: "disabled" });
  expect(writes).toEqual([]);
});
test("legacy domestic URL redirects and removed container tabs are discarded", async ({ page }) => {
  await setup(page, true);
  await page.goto("/#/pmc/domestic-warehouse-board");
  await expect(page).toHaveURL(/#\/pmc\/domestic\/batches$/);
  await expect(page.getByRole("heading", { name: "批次看板", exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("tab_workspace"))).not.toContain("domestic-warehouse-board");
  await expect(page.getByRole("tab", { name: "国内仓看板", exact: true })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "WFS", exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "批次看板", exact: true })).toBeVisible();
});

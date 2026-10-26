/** Explicit local-only acceptance: real HTTP and PostgreSQL; synthetic test principal.
 * Row approve and reject stay hidden; this check confirms the list and the edit action.
 */
import { expect, test } from "@playwright/test";
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL });
test.skip(process.env.PACKING_LIVE_E2E !== "1", "requires short-lived local verification bridge");
test("real local list keeps edit and hides row approve and reject", async ({ page }) => {
  await page.addInitScript(() => { localStorage.setItem("szzsbj_auth_token", "packing-e2e-synthetic-session"); });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith("/api/")) return route.fallback();
    if (url.pathname.startsWith("/api/pmc/domestic/packing-approval")) {
      const reply = await route.fetch({ url: `http://127.0.0.1:8012${url.pathname}${url.search}` });
      return route.fulfill({ response: reply });
    }
    const data = url.pathname === "/api/auth/me" ? { id: 16, username: "packing-e2e-verification", display_name: "本地联调验证", is_super_admin: false, role_keys: [], role_names: [], permissions: ["page:pmc:domestic-warehouse-board:view", "action:pmc:domestic-warehouse-board:packing-approve", "action:pmc:domestic-warehouse-board:packing-reject"] }
      : url.pathname.endsWith("/filter-options") ? { stores: [], owners: [] } : { items: [], total: 0 };
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, data, error: null, meta: { publication_ids: [], data_status: "not_published", freshness_at: null }, request_id: "packing-ui-verification" }) });
  });
  await page.goto("/#/pmc/domestic-warehouse-board");
  await page.getByRole("tab", { name: "打包单审批", exact: true }).click();
  await expect(page.getByText("待审批打包单", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "审批通过", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "驳回", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /修\s*改/ }).first()).toBeVisible();
});

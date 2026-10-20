/** Explicit local-only acceptance: real HTTP and PostgreSQL; synthetic test principal.
 * Persists one approval and one rejection as clearly marked local test records.
 */
import { expect, test } from "@playwright/test";
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL });
test.skip(process.env.PACKING_LIVE_E2E !== "1", "requires short-lived local verification bridge");
test("real local list, approve, reject and audit trail", async ({ page }) => {
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
  await expect(page.getByText("本地打包审批已接通")).toBeVisible();
  const approve = page.getByRole("button", { name: /^通\s*过$/ }).filter({ visible: true });
  await expect(approve.first()).toBeAttached();
  // Read the first eligible row from the actual rendered page, never a fixture SKU.
  const ready = page.locator("tr[data-row-key]").filter({ has: page.locator("button:not([disabled])", { hasText: /^通\s*过$/ }) }).first();
  await expect(ready).toBeVisible();
  await ready.getByRole("button", { name: /^通\s*过$/ }).click();
  const modal = page.getByRole("dialog", { name: "审批通过并生成打包单" });
  await expect(modal).toBeVisible();
  await modal.getByRole("spinbutton").fill("1");
  const posted = page.waitForResponse((r) => r.url().includes("/packing-approval/pending/") && r.url().endsWith("/approve") && r.request().method() === "POST");
  await modal.getByRole("button", { name: /^确\s*定$/ }).click();
  const approved = await posted; expect(approved.status()).toBe(200);
  const result = await approved.json(); expect(result.data.is_test).toBe(true); expect(result.data.pk).toMatch(/^PK\d{6}-\d{3}$/);
  await expect(modal).not.toBeVisible();
  await expect(page.getByText(`已生成本地打包单 ${result.data.pk}`)).toBeVisible();
  await page.getByRole("button", { name: /^驳\s*回$/ }).first().click();
  const rejectModal = page.getByRole("dialog", { name: "驳回打包单" });
  await rejectModal.getByRole("textbox", { name: "驳回原因" }).fill("本地页面联调验证：保留审计，不操作领星");
  const rejected = page.waitForResponse((r) => r.url().endsWith("/reject") && r.request().method() === "POST");
  await rejectModal.getByRole("button", { name: /^确\s*定$/ }).click(); expect((await rejected).status()).toBe(200);
  await expect(rejectModal).not.toBeVisible();
  await page.getByRole("button", { name: "审批记录", exact: true }).click();
  const history = page.getByRole("dialog", { name: "打包审批记录（本地验证）" });
  await expect(history.getByText(result.data.pk, { exact: true })).toBeVisible();
  await history.getByRole("button", { name: "查看审计", exact: true }).first().click();
  const audit = page.getByRole("dialog", { name: "审批审计", exact: true });
  await expect(audit).toBeVisible(); await expect(audit.getByText("来源版本", { exact: true })).toBeVisible();
  await page.screenshot({ path: process.env.PACKING_SCREENSHOT_PATH ?? "C:/Users/treas/.codex/visualizations/2026/10/20/01a156e4-1334-79a0-822c-3db2278b8749/packing-approval-20261020/approval-live.png", fullPage: true });
});

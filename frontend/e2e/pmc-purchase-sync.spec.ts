/** Synthetic task-center acceptance. Every API request is intercepted. */
import { expect, test } from "@playwright/test";
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL });

test("one purchase entry supports three-hour configuration and manual execution", async ({ page }, testInfo) => {
  const keys = ["pmcPurchaseBoardSync", "purchasePlanList", "purchaseOrderList", "purchaseReceiptOrderList", "walmartListingList"];
  const configs = keys.map((key) => ({ id: key, interface_id: key, source_account_ref: "fixture",
    is_enabled: true, schedule_enabled: key === "pmcPurchaseBoardSync",
    schedule_cron: key === "pmcPurchaseBoardSync" ? "0 */3 * * *" : null,
    max_pages: 1000, max_attempts: 3, page_size: 500, batch_size: null,
    next_run_at: null, updated_at: "2026-10-27T00:00:00Z" }));
  const writes: Array<{ path: string; body: Record<string, unknown> }> = [];
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-sync-test"));
  await page.route("**/api/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (!path.startsWith("/api/")) return route.fallback();
    if (req.method() === "POST" || req.method() === "PATCH") {
      writes.push({ path, body: req.postDataJSON() as Record<string, unknown> });
    }
    const data = path === "/api/auth/me" ? { id: 1, username: "fixture", display_name: "测试",
      is_super_admin: true, role_keys: [], role_names: [], permissions: ["integrations:read", "integrations:update", "integrations:execute", "page:data-center:task-center:view"] }
      : path === "/api/integrations/interfaces" ? { items: keys.map((key) => ({ id: key,
        interface_key: key, display_name: key, provider: "lingxing", request_kind: "offset_page", outbound_enabled: true })) }
      : path === "/api/integrations/sync-configs" ? { items: configs }
      : path.endsWith("/run") ? { run_id: "queued", status: "queued", trigger_type: "manual" }
      : req.method() === "PATCH" ? configs[0]
      : { items: [], total: 0 };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      success: true, data, error: null, meta: {}, request_id: "synthetic-sync",
    }) });
  });
  await page.goto("/#/data-center/task-center");
  const row = page.getByRole("row").filter({ hasText: "采购看板同步" });
  await expect(row).toHaveCount(1);
  await expect(page.getByRole("row").filter({ hasText: "采购计划同步" })).toHaveCount(0);
  await expect(page.getByRole("row").filter({ hasText: "Listing 管理同步" })).toHaveCount(1);
  await expect(row).toContainText("每 3 小时");
  await page.screenshot({ path: testInfo.outputPath("purchase-sync.png"), fullPage: true });
  await row.getByRole("button", { name: "配置", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "配置同步任务" });
  await expect(drawer.getByText("每 3 小时", { exact: true })).toBeVisible();
  await drawer.getByRole("button", { name: /保存/ }).click();
  await page.getByRole("button", { name: "确认保存", exact: true }).click();
  await expect.poll(() => writes.find((write) => !write.path.endsWith("/run"))?.body.schedule_cron).toBe("0 */3 * * *");
  await row.getByRole("button", { name: "立即同步", exact: true }).click();
  await page.getByRole("button", { name: "确认执行", exact: true }).click();
  await expect.poll(() => writes.some((write) => write.path.endsWith("/pmcPurchaseBoardSync/run"))).toBe(true);
  const envelope = (data: unknown) => JSON.stringify({ success: true, data, error: null, meta: {}, request_id: "synthetic-failed-run" });
  await page.route("**/api/integrations/sync-runs?**", (route) => route.fulfill({
    status: 200, contentType: "application/json", body: envelope({ items: [{
      id: "failed", config_id: "pmcPurchaseBoardSync", interface_id: "pmcPurchaseBoardSync",
      provider: "lingxing", interface_key: "pmcPurchaseBoardSync", source_account_ref: "fixture",
      trigger_type: "schedule", status: "failed", request_id: "synthetic-failed-run",
      queued_at: "2026-10-27T00:00:00Z", started_at: "2026-10-27T00:00:00Z", finished_at: "2026-10-27T00:01:00Z",
      created_at: "2026-10-27T00:00:00Z", work_items_total: 5, work_items_succeeded: 4,
      work_items_failed: 1, records_seen: 10, records_written: 10, error_code: "SYNC_PURCHASE_PIPELINE_FAILED",
    }] }),
  }));
  await page.route("**/api/integrations/sync-runs/failed/work-items?**", (route) => route.fulfill({
    status: 200, contentType: "application/json", body: envelope({ items: [{
      id: "stage5", run_id: "failed", ordinal: 5, request_kind: "offset_page", status: "failed",
      attempt_count: 1, request_safe_params: { stage: "refresh_dws" }, response_count: null,
      error_code: "SYNC_PURCHASE_STAGE_FAILED", error_message: "采购同步阶段失败",
      started_at: "2026-10-27T00:00:00Z", finished_at: "2026-10-27T00:01:00Z", created_at: "2026-10-27T00:00:00Z",
    }] }),
  }));
  await page.reload();
  await row.getByRole("button", { name: "日志", exact: true }).click();
  await expect(page.getByText("完整流程", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "详情", exact: true }).click();
  await page.getByRole("tab", { name: "执行批次", exact: true }).click();
  await expect(page.getByRole("cell", { name: "看板刷新", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "SYNC_PURCHASE_STAGE_FAILED", exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("purchase-sync-failure.png"), fullPage: true });
  await page.goto("/help/purchase-sync.html");
  await expect(page.getByRole("heading", { name: "任务中心：采购看板同步" })).toBeVisible();
});

/** Synthetic contract acceptance: no provider or real database requests. */
import { expect, test } from "@playwright/test";
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL });

test("shows WFS blocked advice and independent batch filter", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-approval"));
  const seen: string[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (!path.startsWith("/api/")) return route.fallback();
    let data: unknown = { items: [], total: 0 };
    if (path === "/api/auth/me") data = { id: 16, username: "fixture", display_name: "测试",
      is_super_admin: false, role_keys: [], role_names: [], permissions: ["page:pmc:domestic-warehouse-board:view"] };
    else if (path.endsWith("/pending/summary")) data = { pending: 1, overdue: 0, blocked: 1, approved: 0, rejected: 0 };
    else if (path.endsWith("/filter-options")) data = { stores: [], owners: [] };
    else if (path.endsWith("/packing-approval/pending")) {
      seen.push(url.searchParams.get("split_arrival") ?? "");
      data = { total: 1, items: [{ id: "fixture", candidate_version: "a".repeat(64), source_account_ref: "fixture",
        warehouse_id: "16168", publication_id: "fixture", board_id: "fixture", inbound_order_sn: "IB-FIXTURE",
        sku: "SKU-FIXTURE", store_id: "S1", item_id: "11111111111", gtin: "00000000000000", msku: "M1",
        purchase_order_sns: ["PO1"], arrival_purchased: 100, arrival_received: 60, arrival_pending: 40,
        arrival_status: "partial", split_arrival: true, arrival_batch_count: 2, arrival_batch_index: 2,
        stock_balance: 60, available_quantity: 60, default_quantity: 30, can_approve: false,
        blocked_reasons: ["WFS_NOT_CONVERTED"], quantity_suggestion: { rule: "plan_ratio",
          plan_weights: { "11111111111": 50 }, box_pcs: 10, tail_quantity: 0, notes: [], source_refs: [] } }] };
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      success: true, data, error: null, meta: {}, request_id: "allocation-fixture",
    }) });
  });
  await page.goto("/#/pmc/domestic/packing-approval");
  await expect(page.getByText("100 / 60 / 40", { exact: true })).toBeVisible();
  await expect(page.getByText("第 2 批 / 2 批", { exact: true })).toBeVisible();
  await expect(page.getByText("30 / 60", { exact: true })).toBeVisible();
  await page.getByText("待补资料", { exact: true }).hover();
  await expect(page.getByRole("tooltip")).toContainText("尚未完成 WFS 转换");
  await page.getByTitle("分批到货（全部）", { exact: true }).click();
  await page.getByText("已观测分批", { exact: true }).last().click();
  await expect.poll(() => seen.at(-1)).toBe("yes");
});

test("modify saves a draft through PUT and survives refresh without approval", async ({ page }) => {
  const id = "11111111-1111-4111-8111-111111111111";
  const candidate = {
    id, candidate_version: "a".repeat(64), source_account_ref: "fixture", warehouse_id: "16168",
    publication_id: id, board_id: id, inbound_order_sn: "IB-SYN-DRAFT", sku: "SYN-SKU",
    store_id: "S1", store_name: "测试店铺", item_id: "11111111111", gtin: "00000000000000",
    msku: "SYN-MSKU", purchase_order_sns: [], arrival_purchased: 100,
    available_quantity: 100, stock_balance: 100, default_quantity: 60,
    can_approve: true, blocked_reasons: [], origin: "automatic",
  };
  let saved = false;
  const writes: { method: string; path: string; body: Record<string, unknown> }[] = [];
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-draft-test"));
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (!path.startsWith("/api/")) return route.fallback();
    let data: unknown = { items: [], total: 0 };
    if (["PUT", "POST", "PATCH", "DELETE"].includes(request.method())) {
      writes.push({ method: request.method(), path, body: request.postDataJSON() });
    }
    if (path === "/api/auth/me") data = {
      id: 16, username: "fixture", display_name: "测试", is_super_admin: false,
      role_keys: [], role_names: [], permissions: ["page:pmc:domestic-warehouse-board:view",
        "action:pmc:domestic-warehouse-board:packing-approve"],
    };
    else if (path.endsWith("/pending/summary")) data = { pending: 1, overdue: 0, blocked: 0, approved: 0, rejected: 0 };
    else if (path.endsWith("/filter-options")) data = { stores: [], owners: [] };
    else if (path.endsWith("/edit-options")) data = {
      candidate, cross_store_proof_available: false,
      listings: [{ store_id: "S1", store_name: "测试店铺", item_id: candidate.item_id,
        gtin: candidate.gtin, msku: candidate.msku, listing_version: "b".repeat(64), cross_store: false }],
    };
    else if (path.endsWith(`/pending/${id}/draft`) && request.method() === "PUT") {
      saved = true;
      data = { candidate_id: id, edit_draft_pending: true,
        snapshot: { ...candidate, default_quantity: 25, edit_draft_pending: true } };
    }
    else if (path.endsWith("/packing-approval/pending")) data = {
      total: 1, items: [{ ...candidate, default_quantity: saved ? 25 : 60, edit_draft_pending: saved }],
    };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      success: true, data, error: null, meta: {}, request_id: "synthetic-draft-test",
    }) });
  });
  await page.goto("/#/pmc/domestic/packing-approval");
  await page.getByRole("button", { name: /^修\s*改$/ }).click();
  const dialog = page.getByRole("dialog", { name: "修改打包单", exact: true });
  await expect(dialog.getByRole("spinbutton")).toHaveValue("60");
  await dialog.getByRole("spinbutton").fill("25");
  await expect(dialog.getByText("测试店铺 / 11111111111", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: /^保\s*存$/ }).click();
  await expect(page.getByText("已修改未审批", { exact: true })).toBeVisible();
  expect(writes).toEqual([{ method: "PUT",
    path: `/api/pmc/domestic/packing-approval/pending/${id}/draft`,
    body: expect.objectContaining({ qty: 25, candidate_version: candidate.candidate_version }),
  }]);
  await page.reload();
  await expect(page.getByText("已修改未审批", { exact: true })).toBeVisible();
  await expect(page.getByText("25 / 100", { exact: true })).toBeVisible();
  expect(writes).toHaveLength(1);
});

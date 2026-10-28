/** Browser contract with synthetic API state; PostgreSQL transactions are tested separately. */
import { expect, test } from "@playwright/test";
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL });

test("list hides decisions, saves edits and reads existing approval audit", async ({ page }) => {
  const base = { candidate_version: "a".repeat(64), source_account_ref: "fixture",
    warehouse_id: "16168", publication_id: "pub", board_id: "board", inbound_order_sn: "IB-SYN",
    sku: "SYN-SKU", store_id: "S1", store_name: "测试店铺", item_id: "11111111111",
    gtin: "00000000000000", msku: "SYN-MSKU", purchase_order_sns: [], arrival_purchased: 100,
    available_quantity: 100, default_quantity: 60, can_approve: true, blocked_reasons: [] };
  const pending = [{ ...base, id: "candidate-a", edit_draft_pending: false },
    { ...base, id: "candidate-b", edit_draft_pending: false }];
  // Historical decisions remain readable; this page no longer exposes decision actions.
  const orders = [
    { id: "approved-order", pk: "PK261028-001", status: "approved", qty: 25 },
    { id: "rejected-order", pk: null, status: "rejected", qty: null },
  ].map(order => ({ ...order, snapshot: base, source_snapshot: base,
    actor_uid: "synthetic-user", created_at: "2026-10-28T00:00:00Z",
    customs_value: false, customs_src: "default", is_test: true, version: 1 }));
  const writes: { method: string; path: string; body: Record<string, unknown> }[] = [];
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-contract"));
  await page.route("**/api/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (!path.startsWith("/api/")) return route.fallback();
    let data: unknown = { items: [], total: 0 };
    const envelope = (value: unknown) => JSON.stringify({ success: true, data: value, error: null, meta: {}, request_id: "synthetic-contract" });
    if (["PUT", "POST"].includes(request.method())) {
      writes.push({ method: request.method(), path, body: request.postDataJSON() });
    }
    if (path === "/api/auth/me") data = { id: 16, username: "synthetic-user", display_name: "测试用户",
      is_super_admin: false, role_keys: [], role_names: [], permissions: ["page:pmc:domestic-warehouse-board:view",
        "action:pmc:domestic-warehouse-board:packing-approve", "action:pmc:domestic-warehouse-board:packing-reject"] };
    else if (path.endsWith("/filter-options")) data = { stores: [], owners: [] };
    else if (path.endsWith("/pending/summary")) data = { pending: pending.length, approved: orders.filter(o => o.status === "approved").length, rejected: orders.filter(o => o.status === "rejected").length, blocked: 0, overdue: 0 };
    else if (path.endsWith("/edit-options")) data = { cross_store_proof_available: false,
      listings: [{ store_id: "S1", store_name: "测试店铺", item_id: base.item_id, gtin: base.gtin,
        msku: base.msku, listing_version: "b".repeat(64), cross_store: false }] };
    else if (path.endsWith("/draft") && request.method() === "PUT") {
      const row = pending.find(row => path.includes(row.id))!;
      row.default_quantity = request.postDataJSON().qty;
      row.edit_draft_pending = true;
      data = { candidate_id: row.id, edit_draft_pending: true, snapshot: row };
    }
    else if (path.endsWith("/events")) data = { items: [{ id: "evt", event_kind: "approve", actor_uid: "synthetic-user", occurred_at: "2026-10-28T00:00:00Z" }] };
    else if (path.endsWith("/packing-approval/orders")) data = { items: orders, total: orders.length };
    else if (path.endsWith("/packing-approval/pending")) data = { items: pending, total: pending.length };
    await route.fulfill({ status: 200, contentType: "application/json", body: envelope(data) });
  });
  await page.goto("/#/pmc/domestic/packing-approval");
  await expect(page.getByRole("button", { name: /^修\s*改$/ }).first()).toBeEnabled();
  await expect(page.getByRole("button", { name: "审批通过", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^驳\s*回$/ })).toHaveCount(0);
  await page.getByRole("button", { name: /^修\s*改$/ }).first().click();
  const edit = page.getByRole("dialog", { name: "修改打包单", exact: true });
  await expect(edit.getByText("测试店铺 / 11111111111", { exact: true })).toBeVisible();
  await edit.getByRole("spinbutton").fill("25");
  await edit.getByRole("button", { name: /^保\s*存$/ }).click();
  await expect(page.getByText("已修改未审批", { exact: true })).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0].method).toBe("PUT");
  await page.getByRole("button", { name: "审批记录", exact: true }).click();
  const history = page.getByRole("dialog", { name: "打包审批记录（本地验证）" });
  await expect(history.getByText("PK261028-001", { exact: true })).toBeVisible();
  await expect(history.getByText("已驳回", { exact: true })).toBeVisible();
  await history.getByRole("row").filter({ hasText: "PK261028-001" }).getByRole("button", { name: "查看审计" }).click();
  const audit = page.getByRole("dialog", { name: "审批审计", exact: true });
  await expect(audit.getByRole("cell", { name: "approve", exact: true })).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0].path).toMatch(/\/draft$/);
});

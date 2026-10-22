/** The real modal is covered by Playwright; these tests verify its HTTP boundary. */
import { expect, test, vi } from "vitest";
import { backendRequest } from "@/api/backendApi";
import { decidePacking, getPackingEditOptions, type ApprovalCandidate } from "./packingApprovalApi";
vi.mock("@/api/backendApi", () => ({ backendRequest: vi.fn().mockResolvedValue({ success: true, data: {}, error: null, meta: {}, request_id: "test" }), BackendRequestError: class extends Error {} }));
test("identity options keep source account and candidate scope in the request", async () => {
  await getPackingEditOptions({ id: "candidate-a", source_account_ref: "source-account" } as ApprovalCandidate);
  expect(backendRequest).toHaveBeenLastCalledWith("/api/pmc/domestic/packing-approval/pending/candidate-a/edit-options?source_account_ref=source-account", { signal: undefined });
});
test("edited target identities preserve string IDs and never replace the source SKU", async () => {
  await decidePacking("candidate-a", "approve", { source_account_ref: "source-account", warehouse_id: "16168", candidate_version: "a".repeat(64), idempotency_key: "operation", qty: 2, customs: "default", target_store_id: "001", target_item_id: "000123456789", listing_version: "b".repeat(64), edit_reason: "业务去向调整" });
  const [url, options] = vi.mocked(backendRequest).mock.calls.at(-1)!;
  expect(url).toBe("/api/pmc/domestic/packing-approval/pending/candidate-a/approve");
  const body = JSON.parse(String(options?.body));
  expect(body.target_store_id).toBe("001");
  expect(body.target_item_id).toBe("000123456789");
  expect(body.customs).toBe("default");
  expect(body.sku).toBeUndefined();
  expect(body.gtin).toBeUndefined();
  expect(body.msku).toBeUndefined();
});

import { beforeEach, describe, expect, it, vi } from "vitest";
import { backendRequest } from "@/api/backendApi";
import {
  decideNewProductPurchase,
  getNewProductWorkflows,
  getIndependentNewProductPlans,
  getNewProductAccounts,
  verifyNewProductDates,
  requestNewProductPurchase,
  saveMarketScore,
} from "./newProductApi";

vi.mock("@/api/backendApi", () => ({ backendRequest: vi.fn() }));

const skuId = "00000000-0000-0000-0000-000000000123";

describe("new product server API identity and optimistic lock", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(backendRequest).mockResolvedValue({
      success: true,
      data: { items: [], page: 2, total: 0 },
      error: null,
      meta: {},
      request_id: "test-request",
    });
  });

  it("loads account choices only from the scoped server endpoint", async () => {
    const accounts = await getNewProductAccounts();
    expect(accounts).toEqual([]);
    expect(backendRequest).toHaveBeenCalledWith("/api/new-products/source-accounts");
  });

  it("queries independent plans only within the selected account", async () => {
    await getIndependentNewProductPlans("account-a", 3);
    expect(backendRequest).toHaveBeenCalledWith(
      "/api/new-products/purchase-plans?source_account_ref=account-a&page=3",
    );
  });

  it("refuses independent plan queries without an account", async () => {
    await expect(getIndependentNewProductPlans("")).rejects.toThrow("需要先选择真实数据账户");
    expect(backendRequest).not.toHaveBeenCalled();
  });

  it("requires a selected account before requesting live data", async () => {
    await expect(getNewProductWorkflows("")).rejects.toThrow("需要先选择真实数据账户");
    expect(backendRequest).not.toHaveBeenCalled();
  });

  it("encodes source account and page in server read", async () => {
    await getNewProductWorkflows("store & co", 2);
    expect(backendRequest).toHaveBeenCalledWith(
      "/api/new-products/workflows?source_account_ref=store+%26+co&page=2",
    );
  });

  it("cannot write with a fabricated SKU identity", async () => {
    await expect(saveMarketScore("wrong", 0, 8, "品类审核通过")).rejects.toThrow("无效的 SKU 身份");
    expect(backendRequest).not.toHaveBeenCalled();
  });

  it("always submits optimistic row version for business changes", async () => {
    await requestNewProductPurchase(skuId, 4, 250, "近期测试数据符合采购条件");
    expect(backendRequest).toHaveBeenCalledWith(
      `/api/new-products/workflows/${skuId}/purchase-request`,
      { method: "POST", body: JSON.stringify({
        expected_version: 4, quantity: 250, reason: "近期测试数据符合采购条件",
      }) },
    );
  });

  it("sends verified launch dates with optimistic version and evidence", async () => {
    await verifyNewProductDates(skuId, 3, "2026-08-10", "2026-08-12", "到仓与前台可售已核对");
    expect(backendRequest).toHaveBeenCalledWith(
      "/api/new-products/workflows/" + skuId + "/verified-dates",
      {
        method: "POST",
        body: JSON.stringify({
          expected_version: 3,
          arrival_date: "2026-08-10",
          sellable_date: "2026-08-12",
          evidence: "到仓与前台可售已核对",
        }),
      },
    );
  });

  it("labels approvals as drafts rather than actual purchase execution", async () => {
    await decideNewProductPurchase(skuId, 2, "approved_draft", "同意业务草稿继续复核");
    expect(backendRequest).toHaveBeenCalledWith(
      `/api/new-products/workflows/${skuId}/purchase-decision`,
      { method: "POST", body: JSON.stringify({
        expected_version: 2, decision: "approved_draft", note: "同意业务草稿继续复核",
      }) },
    );
  });
});

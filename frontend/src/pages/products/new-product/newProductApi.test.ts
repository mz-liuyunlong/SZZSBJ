import { beforeEach, describe, expect, it, vi } from "vitest";
import { backendRequest } from "@/api/backendApi";
import {
  decideNewProductPurchase,
  getNewProductWorkflows,
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

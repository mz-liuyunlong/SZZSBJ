import { afterEach, describe, expect, it, vi } from "vitest";
import { backendRequest, BackendRequestError } from "@/api/backendApi";
import { ReviewRequestKey, postReview, reviewSignature } from "@/pages/finance/order-review/orderReviewApi";

vi.mock("@/api/backendApi", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/api/backendApi")>()), backendRequest: vi.fn() }));

const headerKey = (call: number) => {
  const init = vi.mocked(backendRequest).mock.calls[call][1] as { headers: Record<string, string> };
  return init.headers["Idempotency-Key"];
};

/** 和页面一样：取编号 → 提交 → 成功才换编号 */
const submit = async (keys: ReviewRequestKey, ids: string[], comment?: string) => {
  const key = keys.take(reviewSignature(ids, "first", "pass", comment));
  const result = await postReview(ids, "first", "pass", comment, false, key);
  keys.done();
  return result;
};

describe("批量审核请求编号", () => {
  afterEach(() => vi.mocked(backendRequest).mockReset());

  it("第一次失败或超时后再点，两次请求的编号相同", async () => {
    let n = 0;
    const keys = new ReviewRequestKey(() => `key-${++n}`);
    vi.mocked(backendRequest)
      .mockRejectedValueOnce(new BackendRequestError(0, "NETWORK_ERROR"))
      .mockResolvedValueOnce({ data: { succeeded: 2, failed: 0, items: [] } } as never);
    await expect(submit(keys, ["r2", "r1"])).rejects.toBeInstanceOf(BackendRequestError);
    await submit(keys, ["r1", "r2"]);
    expect(vi.mocked(backendRequest)).toHaveBeenCalledTimes(2);
    expect(headerKey(0)).toBe("key-1");
    expect(headerKey(1)).toBe("key-1");
  });

  it("改了选中行或意见就换编号；成功后再提交也换编号", async () => {
    let n = 0;
    const keys = new ReviewRequestKey(() => `key-${++n}`);
    vi.mocked(backendRequest)
      .mockRejectedValueOnce(new BackendRequestError(0, "NETWORK_ERROR"))
      .mockResolvedValue({ data: { succeeded: 1, failed: 0, items: [] } } as never);
    await expect(submit(keys, ["r1"])).rejects.toBeInstanceOf(BackendRequestError);
    await submit(keys, ["r1", "r3"]);
    await submit(keys, ["r1", "r3"]);
    await submit(keys, ["r1", "r3"], "备注");
    expect([0, 1, 2, 3].map(headerKey)).toEqual(["key-1", "key-2", "key-3", "key-4"]);
  });

  it("请求体不带编号，编号只放在请求头", async () => {
    vi.mocked(backendRequest).mockResolvedValue({ data: { succeeded: 1, failed: 0, items: [] } } as never);
    await postReview(["r1"], "final", "reject", " 退回原因 ", true, "fixed-key");
    const [url, init] = vi.mocked(backendRequest).mock.calls[0] as [string, { body: string; headers: Record<string, string> }];
    expect(url).toBe("/api/finance/order-review/review");
    expect(init.headers["Idempotency-Key"]).toBe("fixed-key");
    expect(JSON.parse(init.body)).toEqual({
      review_ids: ["r1"], stage: "final", decision: "reject", comment: " 退回原因 ", confirm_token: "CONFIRM_BATCH_REVIEW",
    });
  });
});

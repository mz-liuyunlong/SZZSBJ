import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backendRequest } from "@/api/backendApi";
import { queryClient } from "@/api/queryClient";
import {
  getCachedNewProductDetail, invalidateNewProductDetail, newProductDetailQueryKey,
  newProductDetailQueryOptions, prefetchNewProductDetail, type Identity,
} from "./newProductBusinessApi";

vi.mock("@/api/backendApi", () => ({backendRequest:vi.fn(),backendDownload:vi.fn()}));
const identity: Identity = {source_account_ref:"account-a",store_id:"store-1",item_id:"20911472667"};

describe("NP_DETAIL_CACHE_V4_REFRESH_GUARD", () => {
  beforeEach(() => {queryClient.clear();vi.resetAllMocks();});
  afterEach(() => {queryClient.clear();});

  it("isolates account, store and item IDs", () => {
    expect(newProductDetailQueryKey(identity)).not.toEqual(newProductDetailQueryKey({
      ...identity,source_account_ref:"account-b",
    }));
    expect(newProductDetailQueryKey(identity)).not.toEqual(newProductDetailQueryKey({
      ...identity,store_id:"store-2",
    }));
    expect(newProductDetailQueryKey(identity)).not.toEqual(newProductDetailQueryKey({
      ...identity,item_id:"other-item",
    }));
  });

  it("shares prefetch, initial detail and subsequent tab reads", async () => {
    vi.mocked(backendRequest).mockResolvedValue({data:{proof:"original"}} as never);
    expect(newProductDetailQueryOptions(identity).staleTime).toBe(300_000);
    expect(newProductDetailQueryOptions(identity).gcTime).toBe(1_800_000);
    await Promise.all([prefetchNewProductDetail(identity), getCachedNewProductDetail(identity)]);
    await getCachedNewProductDetail(identity);
    expect(backendRequest).toHaveBeenCalledTimes(1);
  });

  it("refetches after explicit invalidation", async () => {
    let times = 0;
    vi.mocked(backendRequest).mockImplementation(async () => ({data:{times:++times}} as never));
    await getCachedNewProductDetail(identity);
    await invalidateNewProductDetail(identity);
    await getCachedNewProductDetail(identity);
    expect(backendRequest).toHaveBeenCalledTimes(2);
  });

  it("clears cached data with the existing logout cache clear", async () => {
    vi.mocked(backendRequest).mockResolvedValue({data:{proof:"valid"}} as never);
    await getCachedNewProductDetail(identity);
    queryClient.clear();
    await getCachedNewProductDetail(identity);
    expect(backendRequest).toHaveBeenCalledTimes(2);
  });
});

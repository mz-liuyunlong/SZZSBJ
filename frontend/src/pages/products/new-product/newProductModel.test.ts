import { describe, expect, it } from "vitest";
import { completedScore, defaultConfig, evaluatedTrack, useNewProductStore } from "./newProductModel";
import { mockProducts } from "./newProductMockData";

describe("new product rules with mock fixtures", () => {
  it("does not score without a submitted competition assessment", () => {
    expect(completedScore(mockProducts[0],defaultConfig)).toBeNull();
  });
  it("assigns the computed grade and bounded purchase suggestion", () => {
    const p=mockProducts.find(x=>x.id==="YC00872")!;
    const result=completedScore(p,defaultConfig);
    expect(result?.grade).toBe("A");
    expect(result?.suggested).toBeGreaterThanOrEqual(result?.rule?.qtyMin??0);
    expect(result?.suggested).toBeLessThanOrEqual(result?.rule?.qtyMax??0);
  });
  it("keeps score correction pending before a leader approves it", () => {
    const store=useNewProductStore.getState();
    store.resetMockData();
    store.submitCorrection("YC00806","ads",9,"测试规则同步不完整");
    expect(useNewProductStore.getState().products.find(p=>p.id==="YC00806")?.overrides.ads).toBeUndefined();
    const correction=useNewProductStore.getState().corrections[0];
    useNewProductStore.getState().decideCorrection(correction.id,"approved","已复核",true);
    expect(useNewProductStore.getState().products.find(p=>p.id==="YC00806")?.overrides.ads).toBe(9);
    useNewProductStore.getState().resetMockData();
  });
  it("requires justification when operator changes suggested quantity", () => {
    const store=useNewProductStore.getState();
    store.resetMockData();
    expect(()=>store.applyPurchase("YC00806",450,"")).toThrow();
    store.applyPurchase("YC00806",450,"市场销售增长明显");
    expect(useNewProductStore.getState().products.find(p=>p.id==="YC00806")?.approval).toBe("pending");
    useNewProductStore.getState().resetMockData();
  });
  it("never treats unsellable products as completed launch evaluations", () => {
    expect(evaluatedTrack(mockProducts[1],defaultConfig)).toBe("未开始");
  });
});

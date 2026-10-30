import { describe, expect, it } from "vitest";
import { completedScore, defaultConfig, demoProducts, evaluatedTrack, useNewProductDemoStore } from "./newProductDemoModel";

describe("new product demo rules", () => {
  it("does not score without a submitted competition assessment", () => {
    expect(completedScore(demoProducts[0],defaultConfig)).toBeNull();
  });
  it("assigns the computed grade and bounded purchase suggestion", () => {
    const p=demoProducts.find(x=>x.id==="YC00872")!;
    const result=completedScore(p,defaultConfig);
    expect(result?.grade).toBe("A");
    expect(result?.suggested).toBeGreaterThanOrEqual(result?.rule?.qtyMin??0);
    expect(result?.suggested).toBeLessThanOrEqual(result?.rule?.qtyMax??0);
  });
  it("keeps score correction pending before a leader approves it", () => {
    const store=useNewProductDemoStore.getState();
    store.resetDemo();
    store.submitCorrection("YC00806","ads",9,"测试规则同步不完整");
    expect(useNewProductDemoStore.getState().products.find(p=>p.id==="YC00806")?.overrides.ads).toBeUndefined();
    useNewProductDemoStore.getState().setDemoRole("leader");
    const correction=useNewProductDemoStore.getState().corrections[0];
    useNewProductDemoStore.getState().decideCorrection(correction.id,"approved","已复核");
    expect(useNewProductDemoStore.getState().products.find(p=>p.id==="YC00806")?.overrides.ads).toBe(9);
    useNewProductDemoStore.getState().resetDemo();
  });
  it("requires justification when operator changes suggested quantity", () => {
    const store=useNewProductDemoStore.getState();
    store.resetDemo();
    expect(()=>store.applyPurchase("YC00806",450,"")).toThrow();
    store.applyPurchase("YC00806",450,"市场销售增长明显");
    expect(useNewProductDemoStore.getState().products.find(p=>p.id==="YC00806")?.approval).toBe("pending");
    useNewProductDemoStore.getState().resetDemo();
  });
  it("never treats unsellable products as completed launch evaluations", () => {
    expect(evaluatedTrack(demoProducts[1],defaultConfig)).toBe("未开始");
  });
});

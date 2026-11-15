import { describe, expect, it } from "vitest";
import { resolveNewProductFlow, hasNewProductScoreDetails } from "./newProductFlowState";
import type { NewProductListing } from "./newProductBusinessApi";
import type { Product } from "./nativeData";

const row = (): NewProductListing => ({
  listing: {
    id: "1", source_account_ref: "a", store_id: "s", item_id: "123", msku: null,
    local_sku: "sku", title: "x", local_name: "x", store_name: null,
    owner_name: null, picture_url: null, wfs_available_quantity: "0",
    product_tags: [], first_wfs_available_date_la: "2026-11-01",
  },
  facts: {first_wfs_available_date_la: "2026-11-01", market_score: null},
  evaluation: {rule_version: 1, total: null, grade: null,
    dimensions: {market: null, speed: "6", ad: null, profit: null, trust: null},
    missing: [], ad_excluded: false, observation_state: "automatic_partial"},
  tracking_decision: null, tracking_reason: null, market_reason: null, market_version: 0,
  suggested_qty: null, purchase_status: null, purchase_id: null,
  system_recommendation: {value:"",reasons: []},
});

describe("PR337 real workflow and WFS gating", () => {
  it("only creates a market-scoring action when real automatic evidence exists", () => {
    const r = row();
    expect(resolveNewProductFlow(r,r.evaluation)).toBe("待市场评分");
    r.evaluation.dimensions.speed = null;
    expect(resolveNewProductFlow(r,r.evaluation)).toBe("数据待评估");
  });
  it("missing first-stock day distinguishes awaiting WFS from inconsistent current stock", () => {
    const r = row();
    r.listing.first_wfs_available_date_la = null;
    r.facts.first_wfs_available_date_la = null;
    r.facts.data_status = "awaiting_wfs";
    expect(resolveNewProductFlow(r,r.evaluation)).toBe("待首次可售");
    r.listing.wfs_available_quantity = "5";
    expect(resolveNewProductFlow(r,r.evaluation)).toBe("可售时间待核实");
  });
  it("final states outrank reviews, tracking, purchase and missing WFS", () => {
    const r = row();
    r.tracking_decision = "打品失败";
    r.tracking_review_status = "submitted";
    r.purchase_status = "approved";
    r.listing.first_wfs_available_date_la = null;
    expect(resolveNewProductFlow(r,r.evaluation)).toBe("打品失败");
    r.tracking_decision = null;
    expect(resolveNewProductFlow(r,r.evaluation)).toBe("结果审核中");
  });
  it("purchase statuses are sourced from approval data, never the grade", () => {
    const r = row();
    r.purchase_status = "submitted";
    expect(resolveNewProductFlow(r,r.evaluation)).toBe("采购审核中");
    r.purchase_status = "approved";
    expect(resolveNewProductFlow(r,r.evaluation)).toBe("采购已通过");
    r.purchase_status = "rejected";
    expect(resolveNewProductFlow(r,r.evaluation)).toBe("采购已驳回");
  });
  it("a verified zero is viewable but missing first-WFS is not", () => {
    const r = row();
    const product = {backend: {
      firstWfsDate:"2026-11-01", evaluation:{total:null,grade:null,
      dimensions:{market:null,speed:"0",ad:null,profit:null,trust:null}}},
      tracking:"未判定", status:"数据待评估"} as unknown as Product;
    expect(hasNewProductScoreDetails(product)).toBe(true);
    (product.backend as NonNullable<Product["backend"]>).firstWfsDate = null;
    expect(hasNewProductScoreDetails(product)).toBe(false);
    r.tracking_decision = "打品成功";
    expect(resolveNewProductFlow(r,r.evaluation)).toBe("打品成功");
  });
});

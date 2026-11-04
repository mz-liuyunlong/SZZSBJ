import { describe, expect, it } from "vitest";
import { CLEARANCE_PRODUCTS, DEFAULT_RULES, businessSignals, evaluateProduct, suggestedClearanceQty, suggestedClearanceFloorPrice, validateRules } from "./clearanceModel";
import { CLEARANCE_RULE_GROUPS, CLEARANCE_RULE_SPECS } from "./clearanceRuleCatalog";

describe("WFS 清货扩展规则", () => {
 it("所有规则都有明确说明，并按五组展示", () => {
  const keys=CLEARANCE_RULE_SPECS.map(x=>x.key);
  expect(keys.length).toBe(new Set(keys).size);
  expect(CLEARANCE_RULE_GROUPS).toHaveLength(5);
  for(const rule of CLEARANCE_RULE_SPECS){
   expect(rule.label.length).toBeGreaterThan(2);
   expect(rule.help.length).toBeGreaterThan(12);
   expect(rule.example?.length).toBeGreaterThan(12);
   expect(rule.adjust?.length).toBeGreaterThan(8);
   expect(rule.effect?.length).toBeGreaterThan(8);
   expect(rule.key in DEFAULT_RULES).toBe(true);
  }
 });
 it("扩展默认值有效，缺失外部数据时不将其当零", () => {
  expect(validateRules(DEFAULT_RULES)).toBe("");
  const product=CLEARANCE_PRODUCTS[0];
  const original=evaluateProduct(product,DEFAULT_RULES);
  const rule={...DEFAULT_RULES,enableLastSale:true,enableActiveDays:true,enableAdConversion:true,enableNetSales:true};
  const after=evaluateProduct(product,rule);
  expect(after.level).toBe(original.level);
  expect(businessSignals(product,rule)).not.toContain("广告点击足够但订单转化率低");
  expect(suggestedClearanceFloorPrice(product,{...rule,enableFloorPrice:true})).toBeNull();
 });
 it("只有真实批次进入收费预警窗口时才标记", () => {
  const p={...CLEARANCE_PRODUCTS[9],avail:100,age:30,ageLots:[{ageDays:345,qty:10}],listingDays:200};
  const base={...DEFAULT_RULES,enableCoverage:false,enableAged:false,enableAverageAge:false,enableAssisted:false,enableZero:false,enableNearFee:false};
  expect(evaluateProduct(p,base).level).toBe("low");
  expect(evaluateProduct(p,{...base,enableNearFee:true,feeAgeDays:365,feeWarningDays:30}).level).toBe("medium");
 });
 it("建议清货量严格限制在0至可售范围，且不会修改原库存", () => {
  const product=CLEARANCE_PRODUCTS[0];
  const initial=product.avail;
  const qty=suggestedClearanceQty(product,DEFAULT_RULES);
  expect(qty).not.toBeNull();
  expect(qty!).toBeGreaterThanOrEqual(0);
  expect(qty!).toBeLessThanOrEqual(product.avail);
  expect(product.avail).toBe(initial);
 });
 it("单件最低价只有完整费用参数才计算", () => {
  const p={...CLEARANCE_PRODUCTS[0],cost:8,referralRate:0.15,fulfillmentFeePerUnit:3};
  expect(suggestedClearanceFloorPrice(p,{...DEFAULT_RULES,enableFloorPrice:true,allowedClearanceLoss:0})).toBe(12.95);
 });
});

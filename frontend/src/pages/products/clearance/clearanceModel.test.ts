import { describe, expect, it } from "vitest";
import {
 CLEARANCE_PRODUCTS, DEFAULT_RULES, activeTaskFor, chinaToday, coverage,
 evaluateProduct, findProduct, seedTasks, taskProgress, taskIsComplete, nextClearanceTaskId, chinaNow, toCsv, validateRules,
} from "./clearanceModel";

describe("WFS clearance native mock domain",()=>{
 it("preserves all 14 existing mock products and approval examples",()=>{
  expect(CLEARANCE_PRODUCTS).toHaveLength(14);
  expect(seedTasks()).toHaveLength(6);
  expect(findProduct("WFS-110")?.sku).toBe("DEMO-SKU-110");
 });
 it("uses WFS available stock and 30-day demand for coverage",()=>{
  const p=findProduct("WFS-101")!;
  expect(coverage(p)).toBe(Math.ceil(860/(14/30)));
  expect(coverage({...p,per:{...p.per,30:{...p.per[30],units:0}}})).toBeNull();
 });
 it("keeps high risk threshold and excludes products without WFS stock",()=>{
  const p=findProduct("WFS-101")!;
  expect(evaluateProduct(p,DEFAULT_RULES).level).toBe("high");
  expect(evaluateProduct({...p,avail:0},DEFAULT_RULES).auto).toBe(false);
 });
 it("business signals cannot qualify a SKU alone",()=>{
  const base=findProduct("WFS-110")!;
  const p={...base,avail:1,per:{...base.per,7:{...base.per[7],profit:-30},14:{...base.per[14],profit:-20,units:10}}};
  expect(evaluateProduct(p,DEFAULT_RULES).auto).toBe(false);
 });
 it("blocks threshold inversions and invalid dates",()=>{
  expect(validateRules(DEFAULT_RULES)).toBe("");
  expect(validateRules({...DEFAULT_RULES,mediumCoverage:180})).not.toBe("");
  expect(chinaToday()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
 });
 it("completes only at 100 percent and keeps active task lookup",()=>{
  const tasks=seedTasks(),t=tasks.find(x=>x.status==="running")!;
  expect(taskProgress(t)).toBeLessThan(100);
  expect(activeTaskFor(tasks,t.lines[0].id)?.id).toBe(t.id);
 });
 it("does not display or authorize premature completion",()=>{
  const task=seedTasks().find(t=>t.status==="running")!;
  task.lines=[{id:"WFS-108",qty:300,sold:299,removed:0,disposed:0}];
  expect(taskProgress(task)).toBe(99);
  expect(taskIsComplete(task)).toBe(false);
  task.lines[0].sold=300;
  expect(taskProgress(task)).toBe(100);
  expect(taskIsComplete(task)).toBe(true);
 });
 it("uses current China business time and noncolliding mock task IDs",()=>{
  expect(chinaNow(new Date("2026-10-31T04:05:00Z"))).toBe("2026-10-31 12:05");
  expect(nextClearanceTaskId(seedTasks(),"2026-10-31 12:05")).toBe("CH-1031-001");
 });
 it("exports UTF-8 BOM CSV and protects spreadsheet formula cells",()=>{
  const csv=toCsv(["SKU","Value"],[["=HYPERLINK(\"https://invalid\")","ok"]]);
  expect(csv.startsWith("\ufeff")).toBe(true);
  expect(csv).toContain("'=HYPERLINK");
 });
});

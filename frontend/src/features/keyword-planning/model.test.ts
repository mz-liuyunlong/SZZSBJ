/* KEYWORD_SKU_INITIAL_PREFETCH_20261022 */
import {describe,expect,it} from 'vitest';
import {analyzeKeyword,initialRules,normalizeTerm,parseAsins,ruleErrors,selectPlan} from './model';
import type {MarketKeyword,SkuDefinition} from './types';
// Test-only fixtures; production store starts empty and has no demo SKUs.
const fixtureSkus:SkuDefinition[]=[
 {id:'fixture-drawer',sku:'TEST-DRAWER',name:'Drawer',material:'plastic',uses:['drawer organizer'],storeIds:[],hasLibrary:false},
 {id:'fixture-office',sku:'TEST-OFFICE',name:'Office',material:'plastic',uses:['office organizer'],storeIds:[],hasLibrary:false},
];
const word:MarketKeyword={id:'drawer organizer',term:'drawer organizer',normalized:'drawer organizer',originalTranslation:'抽屉收纳用品',translation:'抽屉收纳用品',translationSource:'file',monthlySearches:1000,monthlyPurchases:25,marketPurchaseRate:.025,amazonPpc:.5,bidRange:'$0.40-$0.65',trafficType:'自然搜索词',relatedAsins:['B000000001','B000000002','B000000003'],sponsoredCompetitors:15,listingCount:600,root:'drawer organizer',source:'excel',sourceRow:2};
describe('keyword planning model',()=>{
 it('normalizes case/spacing and ASINs safely',()=>{expect(normalizeTerm('  Drawer   Organizer  ')).toBe('drawer organizer');expect(parseAsins('B012345678\nB012345678\nINVALID\nB012345679')).toEqual({valid:['B012345678','B012345679'],invalid:['INVALID']})});
 it('checks rules and preserves SKU-specific scores',()=>{expect(ruleErrors(initialRules)).toEqual([]);const risk=analyzeKeyword({...word,id:'bamboo drawer organizer',term:'bamboo drawer organizer',normalized:'bamboo drawer organizer'},fixtureSkus[0],initialRules);expect(risk.grade).toBe('不投放');const baseline=analyzeKeyword(word,fixtureSkus[0],initialRules);const other=analyzeKeyword(word,fixtureSkus[1],initialRules);expect(baseline.skuId).not.toBe(other.skuId)});
 it('does not require unapproved ad execution values for internal analysis rules',()=>{
  expect(ruleErrors({...initialRules,bid:{exact:0,broad:0,auto:0,dailyBudget:0,startDate:''}})).toEqual([]);
 });
 it('enforces Exact/Broad caps on recommendations',()=>{const plan=selectPlan(Array.from({length:30},(_,i)=>({...analyzeKeyword(word,fixtureSkus[0],initialRules),keywordId:String(i),grade:'P0' as const,score:99-i})),initialRules);expect(plan.filter(x=>x.exact).length).toBeLessThanOrEqual(initialRules.limits.exact);expect(plan.filter(x=>x.broad).length).toBeLessThanOrEqual(initialRules.limits.broad)});
});

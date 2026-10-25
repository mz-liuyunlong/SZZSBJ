import type { Grade, MarketKeyword, RuleConfig, SkuDefinition, SkuKeyword } from './types';

export const normalizeTerm = (value:string) => value.trim().toLowerCase().replace(/\s+/g,' ');
export const makeTermId = (term:string) => normalizeTerm(term);
export const isAsin = (value:string) => /^[A-Z0-9]{10}$/.test(value.trim().toUpperCase());
export function parseAsins(value:string):{valid:string[];invalid:string[]} {
  const values=[...new Set(value.toUpperCase().split(/[\s,，;；]+/).map(x=>x.trim()).filter(Boolean))];
  return {valid:values.filter(isAsin),invalid:values.filter(x=>!isAsin(x))};
}
export const percentText = (value:number|null) => value==null?'—':(value*100).toFixed(1)+'%';
export const dollarText = (value:number|null) => value==null?'—':'$'+value.toFixed(2);
export const countText = (value:number|null) => value==null?'—':value.toLocaleString('en-US');
export const initialRules: RuleConfig = {
  version:1,
  weights:{match:30,intent:20,coverage:20,root:15,market:15},
  thresholds:{p0:85,p1:75,p2:60},
  limits:{exact:20,broad:20,roots:5,p0:5,p1:10,p2:30},
  asin:{min:3,recommend:3,max:5,titleWeight:2,featuresWeight:1},
  riskWords:'bamboo replacement parts\nrefill only\nspare parts',
  bid:{exact:0.35,broad:0.25,auto:0.20,dailyBudget:10,startDate:new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())},
  naming:{manual:'{SKU}-Manual-{OWNER}',auto:'{SKU}-Auto-{OWNER}'},
  listing:{features:5,titleMax:180,description:true},
  export:{sheetNames:'01_最终投放总表\n02_词根与Broad拓展\n03_风险词\n04_模拟广告方案\n05_Listing建议',columnNames:'关键词,中文翻译,SKU,潜力分,等级,Exact,Broad,运营建议'},
};
export function ruleErrors(rule:RuleConfig):string[]{
  const e:string[]=[];const weight=Object.values(rule.weights).reduce((a,b)=>a+b,0);
  if(weight!==100)e.push(`评分权重合计必须为 100，当前 ${weight}`);
  if(rule.weights.coverage!==20)e.push('竞品 ASIN 覆盖权重尚无可执行评分口径，当前只能保持 20');
  if(!(rule.thresholds.p0>rule.thresholds.p1&&rule.thresholds.p1>rule.thresholds.p2&&rule.thresholds.p2>=0&&rule.thresholds.p0<=100))e.push('P0 / P1 / P2 分级阈值必须由高到低且在 0–100 之间');
  if(Object.values(rule.limits).some(v=>!Number.isInteger(v)||v<0))e.push('所有名额必须是非负整数');
  if(rule.limits.p0+rule.limits.p1>rule.limits.exact)e.push('P0 + P1 计划名额不得超过 Exact 最大数量');
  if(rule.asin.min<1||rule.asin.recommend<rule.asin.min||rule.asin.max<rule.asin.recommend)e.push('ASIN 数量顺序不合法');
  if(Object.values({exact:rule.bid.exact,broad:rule.bid.broad,auto:rule.bid.auto,dailyBudget:rule.bid.dailyBudget}).some(v=>!Number.isFinite(v)||v<0))e.push('Bid / Budget 不得为负数');
  if((rule.bid.startDate||rule.bid.exact>0||rule.bid.broad>0||rule.bid.auto>0||rule.bid.dailyBudget>0)
    &&(!/^\d{4}-\d{2}-\d{2}$/.test(rule.bid.startDate??'')||Number.isNaN(Date.parse(rule.bid.startDate??''))))e.push('请在出价预算规则中设置有效的美国开始日期');
  if(rule.listing.features<1||rule.listing.features>15)e.push('Key Features 条数应在 1–15');
  return e;
}
const hasRisk = (text:string,rules:RuleConfig) => rules.riskWords.split(/[\n,，]+/).map(normalizeTerm).some(w=>w&&text.includes(w));
/** Display-only deterministic scoring. No Amazon listing has been fetched and no Walmart actual performance is used. */
export function analyzeKeyword(k:MarketKeyword,sku:SkuDefinition,rules:RuleConfig):SkuKeyword {
  const term=k.normalized;
  const words=sku.uses.map(normalizeTerm).filter(Boolean);
  const matched=words.filter(w=>term.includes(w)||w.split(' ').some(token=>token.length>4&&term.includes(token)));
  const risk=hasRisk(term,rules)||(sku.material.toLowerCase()==='plastic'&&term.includes('bamboo'));
  const match=matched.length>=2?1:matched.length===1?0.82:0.35;
  const intent=/\b(for|holder|organizer|storage|bin|tray|set|rack)\b/.test(term)?0.85:0.55;
  const coverage=Math.min(1,k.relatedAsins.length/Math.max(rules.asin.min,1));
  const root=words.some(w=>term.includes(w))?0.9:0.48;
  const market=k.monthlySearches==null?0.35:Math.min(1,Math.log10(1+k.monthlySearches)/5);
  const w=rules.weights;const score=Math.min(100,Math.max(0,Math.round((w.match*match+w.intent*intent+w.coverage*coverage+w.root*root+w.market*market)-(risk?45:0))));
  const brand=/\b(oxo|rubbermaid|madesmart|ikea)\b/i.test(term);
  const grade:Grade=risk?'不投放':brand?'品牌等级':score>=rules.thresholds.p0?'P0':score>=rules.thresholds.p1?'P1':score>=rules.thresholds.p2?'P2':score>=Math.max(0,rules.thresholds.p2-15)?'候选复查':'复查';
  const exact=grade==='P0'||grade==='P1';const broad=grade==='P0'||grade==='P1'||grade==='P2';
  const reason=risk?'商品材质或风险规则冲突，请人工复核':brand?'检测到竞品品牌表达，需品牌隔离':matched.length?'商品用途有匹配；仍需验证 Listing 承接':'商品相关性证据偏弱，建议人工复核';
  return {skuId:sku.id,keywordId:k.id,grade,score,reason,exact,broad,status:risk||brand?'风险复查':exact||broad?'已计划':'待测试',analysisVersion:`RULE-v${rules.version}`};
}
/** Plan limits are deterministic demo limits. Hard-risk and brand terms never enter pools. */
export function selectPlan(rows:SkuKeyword[],rules:RuleConfig){
  const rank:Record<Grade,number>={P0:0,P1:1,P2:2,'品牌等级':9,'候选复查':6,'复查':7,'不投放':10};
  const sorted=[...rows].sort((a,b)=>rank[a.grade]-rank[b.grade]||(b.score??0)-(a.score??0));
  let exact=0,broad=0,roots=0,tails=0,p0=0,p1=0,p2=0;
  const normalized=sorted.map(row=>{
    const r={...row,exact:false,broad:false};
    if(row.grade==='P0'){if(p0++>=rules.limits.p0)r.grade='P1';}
    if(r.grade==='P1'){if(p1++>=rules.limits.p1)r.grade='P2';}
    if(r.grade==='P2'){if(p2++>=rules.limits.p2)r.grade='候选复查';}
    return r;
  });
  for(const r of normalized){
    if(!['P0','P1','P2'].includes(r.grade))continue;
    if(exact<rules.limits.exact){r.exact=true;exact++;}
    // Without lexical source phrases, keywordId token count is an approximate broad grouping.
    const words=r.keywordId.trim().split(/\s+/).filter(Boolean);
    if(broad<rules.limits.broad){
      if(words.length<=2&&roots<rules.limits.roots){r.broad=true;roots++;broad++;}
      else if(words.length>=3&&tails<Math.max(0,rules.limits.broad-rules.limits.roots)){r.broad=true;tails++;broad++;}
    }
  }
  return normalized;
}

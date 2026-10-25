import type {MarketKeyword,RuleConfig,SkuDefinition,SkuKeyword,Grade} from './types';
/** Facts were explicitly confirmed by the operator; walmart is verified scrape text only. */
export type DecisionContext = {
  facts:{itemType:string;brand:string;material:string;color:string;pack:string;structure:string;use:string;forbidden:string};
  walmart:{title:string;description:string;attributes:string}|null;
};
const norm=(s:string)=>s.toLowerCase().normalize('NFKC').replace(/[^a-z0-9]+/g,' ').trim().replace(/\s+/g,' ');
const singular=(s:string)=>s.split(' ').map(w=>w.endsWith('ies')&&w.length>4?w.slice(0,-3)+'y':w.endsWith('sses')?w:w.endsWith('s')&&!w.endsWith('ss')&&w.length>3?w.slice(0,-1):w).join(' ');
const words=(s:string)=>singular(norm(s)).split(' ').filter(Boolean);
const stop=new Set(['for','with','and','or','the','a','an','of','in','on','to','by','at','set','pack']);
const mainWords=(s:string)=>words(s).filter(w=>!stop.has(w));
const has=(text:string,phrase:string)=>!!phrase&&(' '+singular(norm(text))+' ').includes(' '+singular(norm(phrase))+' ');
const round=(n:number)=>Math.min(100,Math.max(0,Math.round(n)));
const percentile=(values:number[],v:number|null):number|null=>{
 if(v==null||!values.length)return null;
 return values.filter(x=>x<=v).length/values.length;
};
const demand=(rank:number|null)=>rank==null?2:rank>=.8?5:rank>=.4?3:1;
const purchase=(rank:number|null)=>rank==null?2:rank>=.8?5:rank>=.4?3:1;
const coveragePoints:Record<string,number>={
 '标题已埋词':20,'标题意思已覆盖':18,'详情/属性已埋词':16,
 '场景/用途能接住':14,'用户确认能接住':13,'页面没埋但可优化':10,
 '页面埋得弱，先验证':8,'页面看不出来':4,'页面不建议埋':0
};
const rank:Record<Grade,number>={P0:0,P1:1,P2:2,'品牌等级':9,'候选复查':6,'复查':7,'不投放':10};
type Decision=SkuKeyword & {keywordType:string;pageCoverage:string;coreRoot:string;qualityNote:string;nonSelectionReason:string};
function assess(k:MarketKeyword,sku:SkuDefinition,r:RuleConfig,c:DecisionContext,volumes:number[],purchases:number[],medianPpc:number):Decision{
 const f=c.facts,term=norm(k.term),tokens=mainWords(term);
 const item=mainWords(f.itemType).join(' ');
 const itemParts=mainWords(f.itemType);
 const productMatch=itemParts.length>0&&itemParts.every(w=>words(term).includes(w));
 const exactProduct=!!item&&singular(term)===item;
 const correctMaterial=!!norm(f.material)&&has(term,f.material);
 const uses=f.use.split(/[,，、;；\n]+/).map(x=>x.trim()).filter(Boolean);
 const extra=tokens.filter(w=>!itemParts.includes(w));
 const useMatch=uses.some(x=>has(x,term)||has(term,x)||(productMatch&&extra.some(w=>mainWords(x).includes(w))));
 const materialWords=words(f.material);
 const otherMaterial=['wood','wooden','plastic','bamboo','glass','metal','silicone','ceramic','cork','leather','steel','cotton'].some(m=>words(term).includes(m)&&!materialWords.includes(m)&&!words(f.structure).includes(m));
 const riskTerms=[r.riskWords,f.forbidden].flatMap(x=>x.split(/[\n,，、;；]+/)).map(norm).filter(w=>w&&w!=='none'&&w!=='no'&&w!=='无');
 const explicitRisk=riskTerms.find(w=>has(term,w));
 const brand=norm(f.brand);
 const brandTerm=!!brand&&has(term,brand);
 const page=c.walmart;
 let coverage='页面看不出来';
 if(explicitRisk)coverage='页面不建议埋';
 else if(page){
   const title=norm(page.title),details=norm(page.description+' '+page.attributes);
   if(has(title,term))coverage='标题已埋词';
   else if(tokens.length>=2&&tokens.every(w=>words(title).includes(w)))coverage='标题意思已覆盖';
   else if(has(details,term))coverage='详情/属性已埋词';
   else if(useMatch)coverage='用户确认能接住';
   else if(productMatch)coverage='页面没埋但可优化';
 }else if(useMatch)coverage='用户确认能接住';
 let kind='人工确认词';
 if(explicitRisk)kind=/(replacement|spare parts|accessor)/.test(term)?'配件/替换词':'人工确认词';
 else if(brandTerm)kind='品牌/竞品词';
 else if(productMatch&&correctMaterial)kind='核心材质长尾词';
 else if(exactProduct)kind='核心本体词';
 else if(productMatch&&/(\bpack\b|\bset\b|\b[0-9]+\b)/.test(term))kind='核心规格/数量词';
 else if(productMatch&&useMatch)kind='核心场景长尾词';
 else if(productMatch)kind='精准长尾词';
 else if(useMatch)kind='次级场景词';
 else if(otherMaterial)kind='人工确认词';
 const root=productMatch&&item?item:(useMatch&&tokens.length===1?tokens[0]:'');
 let quality='该词与当前商品的对应关系待确认';
 if(explicitRisk)quality=`命中已确认禁止方向：${explicitRisk}`;
 else if(brandTerm)quality='涉及已确认品牌，不自动进入普通投放';
 else if(otherMaterial)quality='包含不同材质描述，需核对商品结构';
 else if(exactProduct)quality='核心产品词，买家寻找的就是本品';
 else if(correctMaterial&&productMatch)quality='材质与商品一致，买家目标较明确';
 else if(productMatch&&useMatch)quality='产品和用途匹配，可验证场景转化';
 else if(productMatch)quality='包含本品名称，需确认附加词是否准确';
 else if(useMatch)quality='使用场景有依据，但不是直接产品词';
 else if(!page)quality='缺少 Walmart 页面证据，需人工复核';
 const hard=!!explicitRisk;
 const match=hard?0:exactProduct?30:productMatch&&correctMaterial?24:productMatch&&useMatch?22:productMatch?26:useMatch?18:5;
 const intent=hard?0:exactProduct?20:productMatch&&tokens.length>1?18:productMatch?16:useMatch?12:8;
 const rootScore=hard?0:exactProduct?15:productMatch?12:useMatch?7:3;
 const searchScores=volumes, buyScores=purchases;
 const data=demand(percentile(searchScores,k.monthlySearches))+purchase(percentile(buyScores,k.monthlyPurchases))+
   (k.amazonPpc==null?1:k.amazonPpc<=medianPpc*1.5?3:1)+0;
 const penalty=coverage==='页面看不出来'?-8:coverage==='页面埋得弱，先验证'?-5:!productMatch&&!useMatch?-10:0;
 const score=round(match+intent+(coveragePoints[coverage]??4)+rootScore+data+penalty);
 let grade:Grade=hard?'不投放':brandTerm?'品牌等级':(!productMatch&&!useMatch)||otherMaterial?'候选复查':
   score>=r.thresholds.p0?'P0':score>=r.thresholds.p1?'P1':score>=r.thresholds.p2?'P2':'候选复查';
 if(coverage==='页面不建议埋')grade='不投放';
 return {skuId:sku.id,keywordId:k.id,keywordType:kind,pageCoverage:coverage,coreRoot:root,
  qualityNote:quality,nonSelectionReason:'',grade,score,reason:quality,exact:false,broad:false,
  status:hard?'风险复查':'待测试',analysisVersion:`RULE-v${r.version}`};
}
/** One deterministic pass: all displayed judgments and upload admissions reuse these same stored rows. */
export function selectFactPlan(keywords:MarketKeyword[],sku:SkuDefinition,r:RuleConfig,ctx:DecisionContext):SkuKeyword[]{
 const vs=keywords.flatMap(k=>k.monthlySearches==null?[]:[k.monthlySearches]).sort((a,b)=>a-b);
 const bs=keywords.flatMap(k=>k.monthlyPurchases==null?[]:[k.monthlyPurchases]).sort((a,b)=>a-b);
 const pp=keywords.flatMap(k=>k.amazonPpc==null?[]:[k.amazonPpc]).sort((a,b)=>a-b);
 const medianPpc=pp.length?pp[Math.floor(pp.length/2)]:0;
 const rows=keywords.map(k=>assess(k,sku,r,ctx,vs,bs,medianPpc));
 const sorted=[...rows].sort((a,b)=>rank[a.grade]-rank[b.grade]||(b.score??0)-(a.keywordId<b.keywordId?-1:1));
 const counts={P0:0,P1:0,P2:0};
 for(const row of sorted){
   if(row.grade==='P0'&&++counts.P0>r.limits.p0)row.grade='P1';
   if(row.grade==='P1'&&++counts.P1>r.limits.p1)row.grade='P2';
   if(row.grade==='P2'&&++counts.P2>r.limits.p2)row.grade='候选复查';
 }
 let exact=0,broad=0,rootCount=0,tailCount=0;
 const broadRoots=new Set<string>();
 for(const row of sorted){
  const eligible=['P0','P1','P2'].includes(row.grade);
  if(eligible&&exact<Math.min(20,r.limits.exact)){row.exact=true;exact++;}
  // Broad selection: no unverified or generic terms, cap 5 distinct roots / 15 safe long tails.
  const broadEligible=eligible&&row.coreRoot&&row.pageCoverage!=='页面看不出来'&&row.pageCoverage!=='页面不建议埋';
  if(broadEligible&&broad<Math.min(20,r.limits.broad)){
   const isRoot=row.keywordId===row.coreRoot||singular(norm(row.keywordId))===row.coreRoot;
   if(isRoot&&rootCount<Math.min(5,r.limits.roots)&&!broadRoots.has(row.coreRoot)){
      row.broad=true;broadRoots.add(row.coreRoot);rootCount++;broad++;
   }else if(!isRoot&&tailCount<15){row.broad=true;tailCount++;broad++;}
  }
  if(!row.exact){
    row.nonSelectionReason=row.grade==='品牌等级'?'品牌/竞品词，需用户决定':
      row.grade==='不投放'?'触发明确的风险或禁止方向':
      row.grade==='候选复查'||row.grade==='复查'?'商品关联或页面依据待确认':
      row.grade==='P2'?'P2排序未进入Exact前20':'未进入本轮Exact上限';
  }
  row.status=row.grade==='不投放'?'风险复查':row.exact||row.broad?'已计划':'待测试';
 }
 return rows;
}

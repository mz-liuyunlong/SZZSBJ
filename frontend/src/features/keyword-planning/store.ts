/* KEYWORD_PRODUCT_LISTING_API_LOCAL_20261022 */
/* REAL_EXCEL_EMPTY_BASELINE_20261022 */
import {create} from 'zustand';
import {analyzeKeyword, initialRules, makeTermId, normalizeTerm, selectPlan} from './model';
import {selectFactPlan,type DecisionContext} from './keywordDecision';
import type {AdRecord, KeywordAnalysis, MarketKeyword, RuleConfig, RuleHistory, SkuDefinition, SkuKeyword, SourceWorkbook, MatchType} from './types';
import type {KeywordLibraryItem,KeywordResult,KeywordRun} from '@/api/keywordPlanningV11Api';
/** Empty, user-supplied data baseline: never synthesize product, keyword or ad records. */
const emptyKeyword=(term:string,meaning=''):MarketKeyword=>({
 id:makeTermId(term),term,normalized:normalizeTerm(term),
 originalTranslation:meaning||null,translation:meaning||null,
 translationSource:meaning?'manual':'missing',
 monthlySearches:null,monthlyPurchases:null,marketPurchaseRate:null,
 amazonPpc:null,bidRange:null,trafficType:null,relatedAsins:[],
 sponsoredCompetitors:null,listingCount:null,root:normalizeTerm(term).split(' ').slice(0,2).join(' '),
 source:'manual',sourceRow:0
});
export interface KeywordStore{
  skus:SkuDefinition[];keywords:Record<string,MarketKeyword>;entries:SkuKeyword[];ads:AdRecord[];analyses:KeywordAnalysis[];
  staged:SourceWorkbook|null;rules:RuleConfig;draft:RuleConfig|null;history:RuleHistory[];listing:Record<string,{title:string;features:string;description:string}>;
  upsertProductSku:(product:SkuDefinition)=>void;
  installServerRun:(skuId:string,run:KeywordRun,results:KeywordResult[])=>void;
  installServerLibrary:(skuId:string,items:KeywordLibraryItem[])=>void;
  setStaged:(value:SourceWorkbook|null)=>void;importSupplement:(skuId:string,book:SourceWorkbook)=>number;analyze:(skuId:string,context?:DecisionContext)=>number;getSkuTerms:(skuId:string)=>SkuKeyword[];
  updateTranslation:(wordId:string,value:string)=>void;addWord:(skuId:string,term:string,meaning:string)=>boolean;
  addManual:(payload:{skuId:string|null;term:string;store:string;match:MatchType;bid:number;campaign:string;note?:string})=>void;
  assignManual:(id:string,skuId:string)=>void;
  startDraft:()=>void;changeDraft:(rule:RuleConfig)=>void;publishDraft:(reason:string)=>string|null;resetDraft:()=>void;rollback:(version:number)=>void;
  saveListing:(skuId:string,value:{title:string;features:string;description:string})=>void;
}
export const useKeywordStore=create<KeywordStore>((set,get)=>({
  skus:[],keywords:{},entries:[],ads:[],analyses:[],staged:null,rules:initialRules,draft:null,history:[{version:1,at:'初始规则',reason:'规则基线',rule:structuredClone(initialRules)}],listing:{},
  upsertProductSku:(product)=>set(state=>{
    const current=state.skus.find(s=>s.id===product.id);
    const next={...product,hasLibrary:current?.hasLibrary??false};
    return {skus:current?state.skus.map(s=>s.id===product.id?next:s):[next,...state.skus]};
  }),
  installServerRun:(skuId,run,results)=>set(state=>{
    const words={...state.keywords};
    const current:SkuKeyword[]=results.map(row=>{
      const prior=words[row.term_id];
      words[row.term_id]={
        id:row.term_id,term:row.keyword,normalized:normalizeTerm(row.keyword),
        originalTranslation:prior?.originalTranslation??null,
        translation:prior?.translation??null,translationSource:prior?.translationSource??'missing',
        monthlySearches:null,monthlyPurchases:null,marketPurchaseRate:null,
        amazonPpc:null,bidRange:null,trafficType:null,relatedAsins:[],
        sponsoredCompetitors:null,listingCount:null,root:row.core_root??'',
        source:'excel',sourceRow:row.rank_index??0,
      };
      const grade=(['P0','P1','P2','品牌等级','候选复查','不投放'].includes(row.allocation_grade??'')
        ?row.allocation_grade:'复查') as SkuKeyword['grade'];
      return {skuId,keywordId:row.term_id,keywordType:row.primary_type??undefined,
        pageCoverage:row.page_coverage??undefined,coreRoot:row.core_root??undefined,
        qualityNote:row.quality_note??undefined,
        suggestedBid:row.suggested_optimization_bid==null?null:String(row.suggested_optimization_bid),
        nonSelectionReason:row.exact_reason||row.broad_reason||row.risk_reasons.join('；'),
        grade,score:row.score,reason:row.risk_reasons.join('；')||row.exact_reason||'后端规则分析',
        exact:row.exact_selected,broad:row.broad_selected,
        status:row.decision_status==='ready'?'已计划':'风险复查',
        analysisVersion:run.rule_version_id};
    });
    const history=state.analyses.filter(item=>item.skuId!==skuId||item.runId!==run.run_id);
    return {keywords:words,entries:[...state.entries.filter(item=>item.skuId!==skuId),...current],
      skus:state.skus.map(item=>item.id===skuId?{...item,hasLibrary:true}:item),
      analyses:[...history,{skuId,sourceFile:'已保存来源',version:0,at:run.created_at,
        rows:results.length,runId:run.run_id,ruleVersionId:run.rule_version_id}]};
  }),
  installServerLibrary:(skuId,items)=>set(state=>{
    const words={...state.keywords};
    const existing=state.entries.filter(entry=>entry.skuId===skuId);
    const entries=items.map(item=>{
      const prior=words[item.term_id];
      words[item.term_id]={...emptyKeyword(item.keyword,item.translation??''),
        id:item.term_id,source:item.source_kinds.includes('operator_manual')?'manual':'excel',
        root:prior?.root??'',translation:item.translation,originalTranslation:prior?.originalTranslation??item.translation,
        translationSource:item.translation?'manual':'missing'};
      const fromRun=existing.find(entry=>entry.keywordId===item.term_id);
      if(fromRun)return fromRun;
      const grade=(['P0','P1','P2','品牌等级','候选复查','不投放'].includes(item.latest_grade??'')
        ?item.latest_grade:'复查') as SkuKeyword['grade'];
      return {skuId,keywordId:item.term_id,grade,score:item.latest_score,
        reason:'已保存词库，尚待分析',exact:false,broad:false,
        status:'待测试' as const,analysisVersion:'未分析'};
    });
    return {keywords:words,entries:[...state.entries.filter(entry=>entry.skuId!==skuId),...entries],
      skus:state.skus.map(item=>item.id===skuId?{...item,hasLibrary:true}:item)};
  }),
  setStaged:(staged)=>set({staged}),
  importSupplement:(skuId,book)=>{const existing=get().entries;const kw={...get().keywords};let added=0;const next=[...existing];for(const word of book.keywords){if(!kw[word.id])kw[word.id]=word;else{const previous=kw[word.id];kw[word.id]={...word,translation:previous.translation||word.translation,translationSource:previous.translationSource==='manual'?'manual':word.translationSource};}if(!next.some(x=>x.skuId===skuId&&x.keywordId===word.id)){next.push({skuId,keywordId:word.id,grade:'复查',score:null,reason:'新增 Excel 补词，尚未重新分析',exact:false,broad:false,status:'待测试',analysisVersion:'待分析'});added++}}set({keywords:kw,entries:next});return added},
  getSkuTerms:(skuId)=>get().entries.filter(e=>e.skuId===skuId),
  analyze:(skuId,context)=>{const {staged,skus,rules}=get();const sku=skus.find(s=>s.id===skuId);if(!staged||!sku)return 0;
    const scored=context?selectFactPlan(staged.keywords,sku,rules,context):selectPlan(staged.keywords.map(k=>analyzeKeyword(k,sku,rules)),rules);
    const old=get().entries.filter(x=>x.skuId!==skuId);
    const merged={...get().keywords};for(const k of staged.keywords){const prev=merged[k.id];merged[k.id]=prev?{...k,translation:prev.translation??k.translation,translationSource:prev.translationSource==='manual'?'manual':k.translationSource}:k;}
    set({keywords:merged,entries:[...old,...scored],skus:skus.map(s=>s.id===skuId?{...s,hasLibrary:true}:s),analyses:[...get().analyses,{skuId,sourceFile:staged.fileName,version:rules.version,at:new Date().toISOString(),rows:scored.length}],staged:null});return scored.length;
  },
  updateTranslation:(wordId,translation)=>set(s=>({keywords:{...s.keywords,[wordId]:{...s.keywords[wordId],translation:translation.trim()||null,translationSource:translation.trim()?'manual':'missing'}}})),
  addWord:(skuId,term,meaning)=>{
    const id=makeTermId(term);if(!id||!get().skus.some(s=>s.id===skuId))return false;
    if(get().entries.some(e=>e.skuId===skuId&&e.keywordId===id))return false;
    const prev=get().keywords[id];const keyword:MarketKeyword=prev||emptyKeyword(term,meaning);
    set(state=>({keywords:{...state.keywords,[id]:keyword},entries:[...state.entries,{skuId,keywordId:id,grade:'复查',score:null,reason:'人工新增关键词，待分析与事实核对',exact:false,broad:false,status:'待测试',analysisVersion:'未分析'}],skus:state.skus.map(s=>s.id===skuId?{...s,hasLibrary:true}:s)}));
    return true;
  },
  addManual:({skuId,term,store,match,bid,campaign})=>{const normalized=normalizeTerm(term);if(!normalized)return;const id=makeTermId(term);const item=get().keywords[id]||emptyKeyword(term);const kw={...get().keywords,[id]:item};const adId=`manual:${skuId||'unknown'}:${store}:${id}:${match}:${campaign}`;
    const prev=get().ads.filter(a=>a.id!==adId);const record:AdRecord={id:adId,skuId,keywordId:id,term,store,campaign,adGroup:'手动补录',match,bid,status:'启用',source:'manual',impressions:null,clicks:null,spend:null,orders:null,sales:null};const entries=get().entries;
    set({keywords:kw,ads:[...prev,record],entries:skuId&&!entries.some(x=>x.skuId===skuId&&x.keywordId===id)?[...entries,{skuId,keywordId:id,grade:'复查',score:null,reason:'运营后台新增：尚未做关键词分析',exact:false,broad:false,status:'待测试',analysisVersion:'人工补录'}]:entries});
  },
  assignManual:(id,skuId)=>set(s=>({ads:s.ads.map(x=>x.id===id?{...x,skuId}:x),entries:s.entries.some(x=>x.skuId===skuId&&x.keywordId===s.ads.find(a=>a.id===id)?.keywordId)?s.entries:[...s.entries,{skuId,keywordId:s.ads.find(a=>a.id===id)?.keywordId||'',grade:'复查',score:null,reason:'待认领后补词',exact:false,broad:false,status:'待测试',analysisVersion:'人工归属'}]})),
  startDraft:()=>set(s=>({draft:structuredClone(s.rules)})),changeDraft:(draft)=>set({draft}),resetDraft:()=>set({draft:null}),
  publishDraft:(reason)=>{const draft=get().draft;if(!draft)return '没有可发布的草稿';const rules={...structuredClone(draft),version:get().rules.version+1};set(s=>({rules,draft:null,history:[...s.history,{version:rules.version,at:new Date().toISOString(),reason,rule:structuredClone(rules)}]}));return null},
  rollback:(version)=>{const h=get().history.find(x=>x.version===version);if(h)set(s=>({draft:{...structuredClone(h.rule),version:s.rules.version}}))},
  saveListing:(skuId,listing)=>set(s=>({listing:{...s.listing,[skuId]:listing}})),
}));

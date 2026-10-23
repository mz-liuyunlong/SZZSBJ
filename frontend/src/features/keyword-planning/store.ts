import {create} from 'zustand';
import {analyzeKeyword, initialRules, makeTermId, normalizeTerm, selectPlan} from './model';
import type {AdRecord, KeywordAnalysis, MarketKeyword, RuleConfig, RuleHistory, SkuDefinition, SkuKeyword, SourceWorkbook, MatchType} from './types';
export const DEMO_SKUS:SkuDefinition[]=[
  {id:'demo-product-1',sku:'MOCK-ORG-001',name:'演示塑料抽屉收纳盒',material:'plastic',uses:['drawer organizer','organizer tray','plastic storage'],storeIds:['演示店铺A','演示店铺B'],hasLibrary:true},
  {id:'demo-product-2',sku:'MOCK-OFF-002',name:'演示办公桌面收纳盒',material:'plastic',uses:['desk organizer','office organizer','drawer organizer'],storeIds:['演示店铺B'],hasLibrary:true},
  {id:'demo-product-3',sku:'MOCK-NEW-003',name:'演示新品食品储物盒',material:'plastic',uses:['pantry organizers','storage','kitchen organizer'],storeIds:['演示店铺C'],hasLibrary:false},
];
const seedTerms=[
 ['drawer organizer','抽屉收纳用品',14000,290,0.52],
 ['clear drawer organizer','透明抽屉收纳盒',9200,130,0.46],
 ['plastic organizer trays','塑料收纳托盘',6000,110,0.41],
 ['desk organizer','桌面收纳用品',8800,210,0.50],
 ['office drawer organizer','办公抽屉收纳用品',3900,51,0.42],
 ['kitchen organization','厨房收纳整理',101315,688,0.51],
 ['pantry organizers and storage','食品储藏区收纳与储物',284852,8004,0.81],
 ['bamboo drawer organizer','竹制抽屉收纳盒',2000,50,0.60],
];
const mk=(x:(string|number)[]):MarketKeyword=>({id:makeTermId(String(x[0])),term:String(x[0]),normalized:normalizeTerm(String(x[0])),originalTranslation:String(x[1]),translation:String(x[1]),translationSource:'mock',monthlySearches:Number(x[2]),monthlyPurchases:Number(x[3]),marketPurchaseRate:Number(x[3])/Number(x[2]),amazonPpc:Number(x[4]),bidRange:null,trafficType:'演示参考数据',relatedAsins:['B000000001','B000000002','B000000003'],sponsoredCompetitors:null,listingCount:null,root:normalizeTerm(String(x[0])).split(' ').slice(0,2).join(' '),source:'sample',sourceRow:0});
const keywords:Record<string,MarketKeyword>=Object.fromEntries(seedTerms.map(x=>{const k=mk(x);return[k.id,k]}));
const initialEntries:SkuKeyword[]=[
 ...['drawer organizer','clear drawer organizer','plastic organizer trays','bamboo drawer organizer'].map(term=>analyzeKeyword(keywords[makeTermId(term)],DEMO_SKUS[0],initialRules)),
 ...['drawer organizer','desk organizer','office drawer organizer'].map(term=>analyzeKeyword(keywords[makeTermId(term)],DEMO_SKUS[1],initialRules)),
];
const demoAds:AdRecord[]=[
 {id:'mock-ad-1',skuId:DEMO_SKUS[0].id,keywordId:makeTermId('drawer organizer'),term:'drawer organizer',store:'演示店铺A',campaign:'MOCK-ORG-001-Manual',adGroup:'AG-01',match:'Exact',bid:0.39,status:'启用',source:'mock_only',impressions:8400,clicks:210,spend:81.90,orders:18,sales:350},
 {id:'mock-ad-2',skuId:DEMO_SKUS[1].id,keywordId:makeTermId('drawer organizer'),term:'drawer organizer',store:'演示店铺B',campaign:'MOCK-OFF-002-Manual',adGroup:'AG-02',match:'Broad',bid:0.31,status:'启用',source:'mock_only',impressions:5200,clicks:140,spend:43.4,orders:5,sales:88},
 {id:'mock-ad-3',skuId:DEMO_SKUS[0].id,keywordId:makeTermId('clear drawer organizer'),term:'clear drawer organizer',store:'演示店铺A',campaign:'MOCK-ORG-001-Manual',adGroup:'AG-01',match:'Exact',bid:0.35,status:'暂停',source:'mock_only',impressions:4700,clicks:65,spend:22.75,orders:1,sales:20},
 {id:'mock-ad-4',skuId:null,keywordId:makeTermId('unmapped storage box'),term:'unmapped storage box',store:'演示店铺C',campaign:'Demo-Unassigned',adGroup:'AG-Unknown',match:'Broad',bid:0.30,status:'启用',source:'mock_only',impressions:500,clicks:8,spend:2.40,orders:0,sales:0},
];
const MOCK_TRANSLATIONS:Record<string,string>={
 'pantry organizers and storage':'食品储藏区收纳与储物','kitchen organization':'厨房收纳整理','drawer organizer':'抽屉收纳用品','cabinet organizer':'橱柜收纳用品','pantry organizers':'食品储藏室收纳用品','desk organizer':'桌面收纳用品','storage containers':'储物容器','clear storage bins':'透明储物盒','organizer':'收纳用品','storage bins':'储物盒','drawer storage':'抽屉储物','plastic organizer':'塑料收纳用品',
};
export interface KeywordStore{
  skus:SkuDefinition[];keywords:Record<string,MarketKeyword>;entries:SkuKeyword[];ads:AdRecord[];analyses:KeywordAnalysis[];
  staged:SourceWorkbook|null;rules:RuleConfig;draft:RuleConfig|null;history:RuleHistory[];listing:Record<string,{title:string;features:string;description:string}>;
  setStaged:(value:SourceWorkbook|null)=>void;importSupplement:(skuId:string,book:SourceWorkbook)=>number;analyze:(skuId:string)=>number;getSkuTerms:(skuId:string)=>SkuKeyword[];
  updateTranslation:(wordId:string,value:string)=>void;mockTranslate:()=>number;
  addManual:(payload:{skuId:string|null;term:string;store:string;match:MatchType;bid:number;campaign:string;note?:string})=>void;
  assignManual:(id:string,skuId:string)=>void;
  startDraft:()=>void;changeDraft:(rule:RuleConfig)=>void;publishDraft:(reason:string)=>string|null;resetDraft:()=>void;rollback:(version:number)=>void;
  saveListing:(skuId:string,value:{title:string;features:string;description:string})=>void;
}
export const useKeywordStore=create<KeywordStore>((set,get)=>({
  skus:DEMO_SKUS,keywords,entries:initialEntries,ads:demoAds,analyses:[],staged:null,rules:initialRules,draft:null,history:[{version:1,at:'初始演示版本',reason:'初始规则',rule:structuredClone(initialRules)}],listing:{},
  setStaged:(staged)=>set({staged}),
  importSupplement:(skuId,book)=>{const existing=get().entries;const kw={...get().keywords};let added=0;const next=[...existing];for(const word of book.keywords){if(!kw[word.id])kw[word.id]=word;else if(kw[word.id].source==='sample')kw[word.id]={...word,translation:kw[word.id].translation||word.translation};if(!next.some(x=>x.skuId===skuId&&x.keywordId===word.id)){next.push({skuId,keywordId:word.id,grade:'复查',score:null,reason:'新增 Excel 补词，尚未重新分析',exact:false,broad:false,status:'待测试',analysisVersion:'待分析'});added++}}set({keywords:kw,entries:next});return added},
  getSkuTerms:(skuId)=>get().entries.filter(e=>e.skuId===skuId),
  analyze:(skuId)=>{const {staged,skus,rules}=get();const sku=skus.find(s=>s.id===skuId);if(!staged||!sku)return 0;
    const scored=selectPlan(staged.keywords.map(k=>analyzeKeyword(k,sku,rules)),rules);
    const old=get().entries.filter(x=>x.skuId!==skuId);
    const merged={...get().keywords};for(const k of staged.keywords){const prev=merged[k.id];merged[k.id]=prev?{...k,translation:prev.translation??k.translation,translationSource:prev.translationSource==='manual'?'manual':k.translationSource}:k;}
    set({keywords:merged,entries:[...old,...scored],skus:skus.map(s=>s.id===skuId?{...s,hasLibrary:true}:s),analyses:[...get().analyses,{skuId,sourceFile:staged.fileName,version:rules.version,at:new Date().toISOString(),rows:scored.length}],staged:null});return scored.length;
  },
  updateTranslation:(wordId,translation)=>set(s=>({keywords:{...s.keywords,[wordId]:{...s.keywords[wordId],translation:translation.trim()||null,translationSource:translation.trim()?'manual':'missing'}}})),
  mockTranslate:()=>{const keys=get().keywords;let changed=0;const next={...keys};for(const k of Object.values(keys))if(!k.translation&&MOCK_TRANSLATIONS[k.normalized]){next[k.id]={...k,translation:MOCK_TRANSLATIONS[k.normalized],translationSource:'mock'};changed++}set({keywords:next});return changed},
  addManual:({skuId,term,store,match,bid,campaign})=>{const normalized=normalizeTerm(term);if(!normalized)return;const id=makeTermId(term);const item=get().keywords[id]||{...mk([term,'',0,0,0]),originalTranslation:null,translation:null,translationSource:'missing' as const,monthlySearches:null,monthlyPurchases:null,marketPurchaseRate:null,amazonPpc:null,relatedAsins:[],source:'manual' as const};const kw={...get().keywords,[id]:item};const adId=`manual:${skuId||'unknown'}:${store}:${id}:${match}:${campaign}`;
    const prev=get().ads.filter(a=>a.id!==adId);const record:AdRecord={id:adId,skuId,keywordId:id,term,store,campaign,adGroup:'手动补录',match,bid,status:'启用',source:'manual',impressions:null,clicks:null,spend:null,orders:null,sales:null};const entries=get().entries;
    set({keywords:kw,ads:[...prev,record],entries:skuId&&!entries.some(x=>x.skuId===skuId&&x.keywordId===id)?[...entries,{skuId,keywordId:id,grade:'复查',score:null,reason:'运营后台新增：尚未做关键词分析',exact:false,broad:false,status:'待测试',analysisVersion:'人工补录'}]:entries});
  },
  assignManual:(id,skuId)=>set(s=>({ads:s.ads.map(x=>x.id===id?{...x,skuId}:x),entries:s.entries.some(x=>x.skuId===skuId&&x.keywordId===s.ads.find(a=>a.id===id)?.keywordId)?s.entries:[...s.entries,{skuId,keywordId:s.ads.find(a=>a.id===id)?.keywordId||'',grade:'复查',score:null,reason:'待认领后补词',exact:false,broad:false,status:'待测试',analysisVersion:'人工归属'}]})),
  startDraft:()=>set(s=>({draft:structuredClone(s.rules)})),changeDraft:(draft)=>set({draft}),resetDraft:()=>set({draft:null}),
  publishDraft:(reason)=>{const draft=get().draft;if(!draft)return '没有可发布的草稿';const rules={...structuredClone(draft),version:get().rules.version+1};set(s=>({rules,draft:null,history:[...s.history,{version:rules.version,at:new Date().toISOString(),reason,rule:structuredClone(rules)}]}));return null},
  rollback:(version)=>{const h=get().history.find(x=>x.version===version);if(h)set(s=>({draft:{...structuredClone(h.rule),version:s.rules.version}}))},
  saveListing:(skuId,listing)=>set(s=>({listing:{...s.listing,[skuId]:listing}})),
}));
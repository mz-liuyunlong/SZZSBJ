/** Mock-only keyword planning contracts. Never interpret these as approved backend API types. */
export type KeywordSource = 'excel' | 'sample' | 'manual' | 'mock_ad';
export type TranslationSource = 'file' | 'mock' | 'manual' | 'missing';
export type MatchType = 'Exact' | 'Broad';
export type Grade = 'P0' | 'P1' | 'P2' | '复查' | '不投放';
export interface MarketKeyword {
  id: string;
  term: string;
  normalized: string;
  originalTranslation: string | null;
  translation: string | null;
  translationSource: TranslationSource;
  monthlySearches: number | null;
  monthlyPurchases: number | null;
  marketPurchaseRate: number | null;
  amazonPpc: number | null;
  bidRange: string | null;
  trafficType: string | null;
  relatedAsins: string[];
  sponsoredCompetitors: number | null;
  listingCount: number | null;
  root: string;
  source: KeywordSource;
  sourceRow: number;
}
export interface SourceWorkbook { fileName: string; sheets: string[]; keywords: MarketKeyword[]; roots: Array<{term:string;count:number}>; asins: string[]; importedAt: string; warnings: string[]; }
export interface SkuDefinition { id:string; sku:string; name:string; material:string; uses:string[]; storeIds:string[]; hasLibrary:boolean; }
export interface SkuKeyword { skuId:string; keywordId:string; grade:Grade; score:number | null; reason:string; exact:boolean; broad:boolean; status:'待测试'|'已计划'|'风险复查'|'已暂停'; analysisVersion:string; }
export interface AdRecord { id:string; skuId:string|null; keywordId:string; term:string; store:string; campaign:string; adGroup:string; match:MatchType; bid:number; status:'启用'|'暂停'; source:'mock_only'|'manual'; clicks:number|null; spend:number|null; orders:number|null; sales:number|null; impressions:number|null; }
export interface RuleConfig {
  version:number;
  weights:{match:number;intent:number;coverage:number;root:number;market:number};
  thresholds:{p0:number;p1:number;p2:number};
  limits:{exact:number;broad:number;roots:number;p0:number;p1:number;p2:number};
  asin:{min:number;recommend:number;max:number;titleWeight:number;featuresWeight:number};
  riskWords:string;
  bid:{exact:number;broad:number;auto:number;dailyBudget:number};
  naming:{manual:string;auto:string};
  listing:{features:number;titleMax:number;description:boolean};
  export:{sheetNames:string;columnNames:string};
}
export interface RuleHistory { version:number; at:string; reason:string; rule:RuleConfig; }
export interface KeywordAnalysis {skuId:string; sourceFile:string; version:number; at:string; rows:number;}
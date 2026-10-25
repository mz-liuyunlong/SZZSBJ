/* KEYWORD_SKU_INITIAL_PREFETCH_20261022 */
/** Reuses existing read-only Product Management and Walmart Listing endpoints.
 * No separate API, no browser-side direct marketplace request, no automatic fuzzy binding.
 */
import {getProductManagementSku,listProductManagementSkus} from '@/pages/products/productManagementApi';
import {fetchListingManagementRows} from '@/pages/products/listingManagementApi';
import type {ProductManagementRow} from '@/pages/products/productManagementTypes';
import type {ListingManagementRow} from '@/pages/products/listingManagementData';

export type MatchMethod = 'sku_exact' | 'msku_exact' | 'msku_candidate';
export type ListingCandidate = {listing:ListingManagementRow;match:MatchMethod;label:string};
export const canonicalSku=(value:string|null|undefined)=>String(value||'').trim().toUpperCase();
const compact=(value:string|null|undefined)=>canonicalSku(value).replace(/[^A-Z0-9]/g,'');

/** Preload the first page from the canonical Product Management API.
 * Keep this bounded (100 rows); searches outside the first page go server-side.
 */
export async function preloadProductSkuOptions():Promise<ProductManagementRow[]> {
  const response=await listProductManagementSkus({searchType:'sku',keyword:''},1,100);
  return response.rows.filter(row=>Boolean(row.id&&row.sku));
}

export async function searchProductsBySku(raw:string):Promise<ProductManagementRow[]> {
  const query=raw.trim();
  if(query.length<2)return [];
  const response=await listProductManagementSkus({searchType:'sku',keyword:query},1,30);
  const q=canonicalSku(query);
  // The product source determines canonical SKU. Never synthesize one from an MSKU.
  return response.rows.filter(r=>r.id&&r.sku&&canonicalSku(r.sku).includes(q))
    .sort((a,b)=>Number(canonicalSku(b.sku)===q)-Number(canonicalSku(a.sku)===q))
    .slice(0,30);
}

export async function getProductFacts(row:ProductManagementRow):Promise<ProductManagementRow>{
  return getProductManagementSku(row);
}

function rankListing(row:ListingManagementRow,sku:string):ListingCandidate|null {
  const base=canonicalSku(sku),condensed=compact(sku);
  if(base&&canonicalSku(row.sku)===base){return {listing:row,match:'sku_exact',label:'SKU 精确匹配'};}
  if(condensed&&compact(row.msku)===condensed){return {listing:row,match:'msku_exact',label:'MSKU 精确匹配 · 需人工确认'};}
  const msku=compact(row.msku);
  if(condensed.length>=3&&msku.includes(condensed)){
    return {listing:row,match:'msku_candidate',label:'MSKU 包含 SKU · 需人工确认'};
  }
  return null;
}

/** Search both canonical SKU and potentially decorated MSKU, do not treat fuzzy as ownership. */
export async function searchListingsForSku(sku:string):Promise<{candidates:ListingCandidate[];warnings:string[]}> {
  const q=sku.trim();if(!q)return {candidates:[],warnings:[]};
  const warnings:string[]=[];
  const requests=[
    {searchType:'sku' as const,keyword:q,page:1,pageSize:50},
    {searchType:'msku' as const,keyword:q,page:1,pageSize:50},
  ];
  const responses=await Promise.allSettled(requests.map(args=>fetchListingManagementRows(args)));
  const all:ListingManagementRow[]=[];
  responses.forEach((result,index)=>{
    if(result.status==='fulfilled'){
      all.push(...result.value.rows);
      if(result.value.meta.total>50)warnings.push(`${index===0?'SKU':'MSKU'} 查询超过50条，仅展示第一页候选；请缩小条件再确认`);
    }else warnings.push(`${index===0?'SKU':'MSKU'} 查询失败；无法确认是否有匹配的 Listing`);
  });
  if(responses.every(x=>x.status==='rejected'))throw new Error('Listing 接口暂不可用，请检查登录权限或网络；可人工输入 Item ID');
  const unique=new Map<string,ListingCandidate>();
  for(const row of all){const result=rankListing(row,q);if(!result||!row.productId||row.productId==='-')continue;
    const key=`${row.id}:${row.productId}`;
    const existing=unique.get(key);
    if(!existing||result.match==='sku_exact')unique.set(key,result);
  }
  const order:Record<MatchMethod,number>={sku_exact:0,msku_exact:1,msku_candidate:2};
  return {candidates:[...unique.values()].sort((a,b)=>order[a.match]-order[b.match]||a.listing.store.localeCompare(b.listing.store)),warnings};
}

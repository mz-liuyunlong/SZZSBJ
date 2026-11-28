import { backendRequest } from "@/api/backendApi";
import { emptyListing as emptyBaseListing, type ListingProgress as BaseListing, type SkuProgressRow as BaseRow } from "./skuProgressModel";
import type { ReportFilterOption } from "@/shared/report-filters";

const base = "/api/new-products/sku-progress";
export const SKU_PROGRESS_SOURCE_TAG = "小批量测品";
export type Facet = "store"|"owner"|"developer"|"listing"|"plan"|"site"|"strike"|"ad"|"proc"|"ship"|"progress";
export type Filters = Partial<Record<Facet,string[]>>;
export type Card = "all"|"active"|"done"|"paused"|"terminated";
export type Sort = {key:"date"|"product"|"name"|"dev"|"progress"|"listing";order:"asc"|"desc"};
export type Criteria = {filters:Filters;keyword:string;searchField:string;card:Card;dateRange:[string,string]|null};
export type Summary = {total:number;in_progress:number;completed:number;paused:number;terminated:number;listed:number;unlisted:number;listing_count:number};
export type FacetResult = {facets:Record<Facet,ReportFilterOption[]>;date_range:{min:string|null;max:string|null};unknown_sources:string[]};
export type ListingProgress = BaseListing & {storeId:string;candidate:boolean;ad:string;site:string;purchasePlan:string;purchaseProgress:string;shipping:string};
export type ProgressCode = "in_progress"|"paused"|"terminated"|"completed";
export type SkuProgressRow = Omit<BaseRow,"ls"|"purchasePlan"|"independentSite"> & {account:string;skuId:string;ls:ListingProgress[];purchasePlan:string;independentSite:string;developmentDate:string;purchaseProgress:string;shipping:string;progress:string;remark:string;progressCode:ProgressCode;reasonType:string;progressVersion:number;canEditProgress:boolean};
type BackendListing = {store_id:string;store_name:string|null;item_id:string;msku:string|null;owner_ref:string|null;owner_display?:string|null;launch_date_cn:string|null;strike_price:string|null;strike_currency:string|null;sale_price:string|null;sale_currency:string|null;strike_effect:string|null;ad_enabled:boolean|null;site_label:string;purchase_candidate:boolean;plan_label?:string|null;proc_label?:string|null;domestic_shipping_status?:string|null};
type BackendRow = {source_account_ref:string;sku_identity_id:string;sku:string;product_name:string|null;main_image_url:string|null;developer_name:string|null;developer_uid:string|null;development_date:string|null;listing_status:"listed"|"unlisted"|"unknown";progress_status:string;remark:string|null;reason_type?:string|null;progress_version?:number;can_edit_progress?:boolean;plan_label:string;proc_label:string;site_label?:string;domestic_shipping_status:string|null;listings:BackendListing[];independent_site_submissions:Array<{target_scope:string;submission_status:string}>};
type BackendPage = {items:BackendRow[];total:number;listing_count:number;page:number;page_size:number};
const text=(s:string|null|undefined)=>s?.trim()??"";
const progressLabels:Record<string,string>={in_progress:"推进中",completed:"已完成",paused:"暂停推进",terminated:"终止推进"};
function money(amount:string|null,currency:string|null){return amount!=null&&currency&&/^\d+(?:\.\d+)?$/.test(String(amount))?`${currency==="USD"?"$":currency==="CNY"?"¥":`${currency} `}${amount}`:"";}
export function toProgressRow(row:BackendRow):SkuProgressRow {
  const ls:ListingProgress[]=row.listings.map(l=>({key:JSON.stringify([row.source_account_ref,l.store_id,l.item_id]),id:l.item_id,msku:text(l.msku),store:text(l.store_name)||l.store_id,storeId:l.store_id,owner:text(l.owner_display)||text(l.owner_ref),listing:"已上架",date:text(l.launch_date_cn),strike:money(l.strike_price,l.strike_currency),effect:l.strike_effect==="effective"?"已生效":l.strike_effect==="ineffective"?"未生效":"",price:money(l.sale_price,l.sale_currency),ad:l.ad_enabled===true?"已开启":l.ad_enabled===false?"未开启":"待确认",site:l.site_label,candidate:l.purchase_candidate===true,purchasePlan:l.plan_label??"待确认",purchaseProgress:l.proc_label??"待确认",shipping:l.domestic_shipping_status??"待确认"}));
  const skuSite=row.independent_site_submissions.find(s=>s.target_scope==="sku");
  return {key:JSON.stringify([row.source_account_ref,row.sku_identity_id]),account:row.source_account_ref,skuId:row.sku_identity_id,sku:row.sku,name:text(row.product_name),dev:text(row.developer_name)||text(row.developer_uid),owner:"",image:text(row.main_image_url),previewImage:text(row.main_image_url),ls,unmatchedListingStatus:row.listing_status==="unlisted"?"未上架":"",purchasePlan:row.plan_label,independentSite:skuSite?.submission_status==="submitted"?"已提交":"未提交",developmentDate:text(row.development_date),purchaseProgress:row.proc_label,shipping:row.domestic_shipping_status??"待确认",progress:progressLabels[row.progress_status]??"待确认",remark:text(row.remark),progressCode:(Object.prototype.hasOwnProperty.call(progressLabels,row.progress_status)?row.progress_status:"in_progress") as ProgressCode,reasonType:text(row.reason_type),progressVersion:row.progress_version??0,canEditProgress:row.can_edit_progress===true&&Object.prototype.hasOwnProperty.call(progressLabels,row.progress_status)};
}
export const emptyListing=(row:SkuProgressRow):ListingProgress=>({...emptyBaseListing(row.unmatchedListingStatus),storeId:"",candidate:false,ad:"待确认",site:row.independentSite,purchasePlan:row.unmatchedListingStatus==="未上架"&&row.purchasePlan==="未提交"?"未提交":"待确认",purchaseProgress:"待确认",shipping:"待确认"});
export function criteriaParams(c:Criteria):URLSearchParams {
  const p=new URLSearchParams({keyword:c.keyword.trim(),search_field:c.searchField,card:c.card});
  if(c.dateRange){p.set("start",c.dateRange[0]);p.set("end",c.dateRange[1]);}
  for(const key of Object.keys(c.filters).sort() as Facet[]){for(const value of [...new Set(c.filters[key]??[])].sort()){p.append(key,value);}}
  return p;
}
export async function loadSkuProgress(c:Criteria,page:number,pageSize:number,sort:Sort,signal?:AbortSignal){
  const p=criteriaParams(c);p.set("page",String(page));p.set("page_size",String(pageSize));p.set("sort_by",sort.key);p.set("sort_order",sort.order);
  const {data}=await backendRequest<BackendPage>(`${base}/list?${p}`,{signal});
  if(!Array.isArray(data.items)||!Number.isSafeInteger(data.total)||data.total<0||data.page!==page||data.page_size!==pageSize||data.items.length>pageSize)throw new Error("SKU进度分页返回异常");
  return {...data,rows:data.items.map(toProgressRow)};
}
export async function loadProgressSummary(c:Criteria,signal?:AbortSignal){return (await backendRequest<Summary>(`${base}/summary?${criteriaParams({...c,card:"all"})}`,{signal})).data;}
export async function loadProgressFacets(c:Criteria,signal?:AbortSignal){return (await backendRequest<FacetResult>(`${base}/facets?${criteriaParams(c)}`,{signal})).data;}
export async function submitSkuPurchase(row:SkuProgressRow,listing:ListingProgress){
  if(!listing.candidate||!row.ls.some(l=>l.key===listing.key&&l.storeId===listing.storeId&&l.id===listing.id&&l.candidate))throw new Error("当前商品不符合采购条件");
  const {data}=await backendRequest<{submission_status:string;quantity:number;lingxing_plan_sn:string|null}>(`${base}/purchase`,{method:"POST",body:JSON.stringify({source_account_ref:row.account,sku_identity_id:row.skuId,store_id:listing.storeId,item_id:listing.id,quantity:20})});
  if(data.submission_status!=="submitted"||data.quantity!==20||!data.lingxing_plan_sn)throw new Error("采购结果未确认，请核实领星记录，禁止重复提交");
  return data;
}

export async function saveSkuProgress(row:SkuProgressRow,status:ProgressCode,reason:string|undefined,remark:string){
  if(!row.canEditProgress)throw new Error("当前环境或账号不可保存");
  const {data}=await backendRequest<{progress_status:ProgressCode;version:number}>(`${base}/manual`,{method:"PUT",body:JSON.stringify({source_account_ref:row.account,sku_identity_id:row.skuId,version:row.progressVersion,progress_status:status,reason_type:reason||null,remark:remark.trim()})});
  if(data.progress_status!==status||!Number.isSafeInteger(data.version)||data.version<=row.progressVersion)throw new Error("保存回执异常，请刷新核对");
  return data;
}
export type BatchPurchaseTarget={row:SkuProgressRow;listing:ListingProgress};
export const batchPurchaseKey=({row,listing}:BatchPurchaseTarget)=>JSON.stringify([row.key,listing.key]);
export type BatchPurchaseResult={key:string;sku:string;ok:boolean;detail:string};
export async function submitSkuPurchaseBatch(items:BatchPurchaseTarget[],onResult:(result:BatchPurchaseResult)=>void,shouldContinue:()=>boolean=()=>true){
  if(!items.length||items.length>100||new Set(items.map(batchPurchaseKey)).size!==items.length)throw new Error("批量采购必须选择1至100个不同Listing");
  for(const item of items){
    if(!shouldContinue())break;
    let result:BatchPurchaseResult;
    try{const receipt=await submitSkuPurchase(item.row,item.listing);result={key:batchPurchaseKey(item),sku:item.row.sku,ok:true,detail:receipt.lingxing_plan_sn!};}
    catch(e){result={key:batchPurchaseKey(item),sku:item.row.sku,ok:false,detail:e instanceof Error?e.message:"结果未确认，请核对领星"};}
    onResult(result);
  }
}

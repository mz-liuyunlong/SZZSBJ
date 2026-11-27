/** One page read: real list + category counts + preloaded purchase read model.
 * Demo rows remain local and never enter any decision or server cache record.
 */
import {backendRequest} from '@/api/backendApi';
import {readAuthToken} from '@/pages/auth/authSession';
import {getFilteredDemoItems} from './approvalDemoData';
import type {ApprovalFilters, ApprovalItem, ApprovalMeta} from './approvalTypes';
import type {ApprovalBusinessKey} from './approvalBusiness';

type Counts = Partial<Record<ApprovalBusinessKey,number>>;
type ReadPage = {data:{items:ApprovalItem[];business_counts:Counts};meta:ApprovalMeta};

export function appendWorkbenchDemos(result:ReadPage, filters:ApprovalFilters):ReadPage {
  const demos = getFilteredDemoItems(filters).filter(r => r.approval_type !== 'clearance_request' && r.approval_type !== 'purchase_exception');
  const allDemos = getFilteredDemoItems({...filters,approval_type:undefined}).filter(r => r.approval_type !== 'clearance_request' && r.approval_type !== 'purchase_exception');
  const offset = (filters.page-1)*filters.page_size;
  const start = Math.max(0,offset-result.meta.total);
  const capacity = Math.max(0,filters.page_size-result.data.items.length);
  return {data:{items:[...result.data.items,...demos.slice(start,start+capacity)],business_counts:{...result.data.business_counts,all:(result.data.business_counts.all??0)+allDemos.length}},meta:{...result.meta,total:result.meta.total+demos.length}};
}

// Reuse a complete category from the All page without changing its source order.
// A partial All page is reusable only when the category count proves completeness.
const categoryCountKeys: Record<string, ApprovalBusinessKey> = {
  purchase_exception:'purchase', new_product_evaluation_review:'newProduct',
  wfs_case_abandon:'wfs', clearance_request:'clearance',
};
export function projectWorkbenchCategory(all:ReadPage, filters:ApprovalFilters):ReadPage|undefined {
  const type=filters.approval_type;
  if (!type || all.meta.page!==1) return undefined;
  const countKey=categoryCountKeys[type];
  // Finance is not included in the All endpoint. Never infer its rows.
  if (!countKey) return undefined;
  const matched=all.data.items.filter(row=>row.approval_type===type ||
    (type==='purchase_exception' && row.approval_type==='new_product_purchase'));
  const expected=all.data.business_counts[countKey];
  if (typeof expected!=='number' || expected!==matched.length) return undefined;
  const start=(filters.page-1)*filters.page_size;
  return {data:{items:matched.slice(start,start+filters.page_size),business_counts:all.data.business_counts},
    meta:{page:filters.page,page_size:filters.page_size,total:expected}};
}

function paramsFor(filters:ApprovalFilters) {
  const params=new URLSearchParams({tab:filters.tab,view:filters.view??'all',page:String(filters.page),page_size:String(filters.page_size)});
  if(filters.approval_type) params.set('approval_type',filters.approval_type);
  if(filters.risk_level) params.set('risk_level',filters.risk_level);
  if(filters.keyword?.trim()) params.set('keyword',filters.keyword.trim());
  return params.toString();
}

// One reader per mounted workbench. Refresh, approval mutation, auth or scope
// change invalidates its data and in-flight generation; never persist in storage.
export function createWorkbenchReader() {
  let scope:string|undefined;
  let generation=0;
  let expiresAt=0;
  let all:ReadPage|undefined;
  const pages=new Map<string,ReadPage>();
  const pending=new Map<string,Promise<ReadPage>>();
  return function fetchWorkbenchRead(filters:ApprovalFilters,reloadToken:number):Promise<ReadPage> {
    const token=readAuthToken();
    const signature=JSON.stringify([token,filters.tab,filters.view??'all',filters.risk_level??'',filters.keyword?.trim()??'',reloadToken]);
    if(signature!==scope || (expiresAt!==0 && Date.now()>=expiresAt)) {
      scope=signature;generation++;expiresAt=0;all=undefined;pages.clear();pending.clear();
    }
    const key=paramsFor(filters);
    const cached=pages.get(key);
    if(cached) return Promise.resolve(cached);
    const projected=all && projectWorkbenchCategory(all,filters);
    if(projected) return Promise.resolve(projected);
    const existing=pending.get(key);
    if(existing) return existing;
    const epoch=generation;
    // A quick click during the All request can wait for that same response.
    const allPending=filters.approval_type ? [...pending.entries()].find(([p])=>{
      const q=new URLSearchParams(p);return !q.has('approval_type') && q.get('page')==='1';
    })?.[1] : undefined;
    const request=(async()=>{
      if(allPending) {
        const loaded=await allPending;
        if(epoch!==generation) throw new Error('WORKBENCH_SCOPE_CHANGED');
        const projected=projectWorkbenchCategory(loaded,filters);
        if(projected) return projected;
      }
      const result=await backendRequest<ReadPage['data'],ApprovalMeta>(`/api/approvals/workbench/read?${key}`);
      const page=appendWorkbenchDemos(result,filters);
      if(epoch===generation && readAuthToken()===token) {
        if(expiresAt===0) expiresAt=Date.now()+120_000;
        pages.set(key,page);
        if(!filters.approval_type && filters.page===1) all=page;
      }
      return page;
    })();
    pending.set(key,request);
    const cleanup=()=>{if(pending.get(key)===request) pending.delete(key);};
    void request.then(cleanup,cleanup);
    return request;
  };
}

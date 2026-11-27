import {describe,expect,it,vi} from 'vitest';
vi.mock('./approvalDemoData',()=>({getFilteredDemoItems:()=>[]}));
import {appendWorkbenchDemos, createWorkbenchReader, projectWorkbenchCategory} from './workbenchReadApi';
import {backendRequest} from '@/api/backendApi';
vi.mock('@/api/backendApi',()=>({backendRequest:vi.fn()}));
vi.mock('@/pages/auth/authSession',()=>({readAuthToken:()=> 'test-user-token'}));
import type {ApprovalItem} from './approvalTypes';
import parent from './components/ApprovalBusinessDetailDrawer.tsx?raw';
import model from './purchaseApprovalReadModel.ts?raw';
import page from './ApprovalWorkspacePage.tsx?raw';

describe('unified workbench',()=>{
  it('keeps the exact preloaded row and the server total',()=>{
    const row={id:'p',version:7} as ApprovalItem;
    const result=appendWorkbenchDemos({data:{items:[row],business_counts:{all:1,purchase:1}},meta:{page:1,page_size:50,total:1}},{tab:'pending',page:1,page_size:50});
    expect(result.data.items[0]).toBe(row);
    expect(result.meta.total).toBe(1);
  });
  it('uses one page request and disables detail reads for cached purchases',()=>{
    expect(page).toContain('fetchWorkbenchRead(filters,reloadToken)');
    expect(page).not.toContain('fetchWorkbenchList(');
    expect(page).not.toContain('enrichVisiblePurchaseRows(');
    expect(parent).toContain('|| preloadedRead) return;');
    expect(model).toContain('!preloaded && Boolean(identity');
  });
});

const f={tab:'pending',view:'mine',page:1,page_size:50} as const;
const row=(id:string,type:string)=>({id,approval_type:type,version:1} as ApprovalItem);
const full={data:{items:[row('p','new_product_purchase'),row('w','wfs_case_abandon')],business_counts:{all:2,purchase:1,wfs:1,clearance:0}},meta:{page:1,page_size:50,total:2}};
describe('workbench V2 category cache',()=>{
  it('projects purchase and zero-count categories from All',()=>{
    expect(projectWorkbenchCategory(full,{...f,approval_type:'purchase_exception'})?.data.items).toEqual([full.data.items[0]]);
    expect(projectWorkbenchCategory(full,{...f,approval_type:'clearance_request'})?.meta.total).toBe(0);
    expect(projectWorkbenchCategory(full,{...f,approval_type:'finance_exception'})).toBeUndefined();
  });
  it('does not infer incomplete categories',()=>{
    const partial={...full,data:{...full.data,business_counts:{...full.data.business_counts,purchase:2}}};
    expect(projectWorkbenchCategory(partial,{...f,approval_type:'purchase_exception'})).toBeUndefined();
  });
  it('loads All once, reuses categories, and refreshes on new generation',async()=>{
    const mock=vi.mocked(backendRequest);mock.mockReset();mock.mockResolvedValue({...full,success:true,error:null,request_id:"test"});
    const read=createWorkbenchReader();
    await Promise.all([read(f,0),read(f,0)]);
    await read({...f,approval_type:'purchase_exception'},0);
    await read(f,0);
    expect(mock).toHaveBeenCalledTimes(1);
    await read(f,1);
    expect(mock).toHaveBeenCalledTimes(2);
  });
});

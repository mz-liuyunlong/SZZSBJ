import { beforeEach, describe, expect, it, vi } from "vitest";
import { criteriaParams, emptyListing, loadProgressFacets, loadProgressSummary, loadSkuProgress, submitSkuPurchase, submitSkuPurchaseBatch, saveSkuProgress, toProgressRow, type Criteria } from "./skuProgressApi";
const request=vi.hoisted(()=>vi.fn());
vi.mock("@/api/backendApi",()=>({backendRequest:request}));
const criteria:Criteria={filters:{store:['["A", "S1"]','["A", "S2"]','["A", "S1"]'],ad:["已开启","待确认"]},keyword:" SKU1 ",searchField:"sku",card:"active",dateRange:["2026-01-01","2026-02-01"]};
const listing={store_id:"S1",store_name:"CN2601",item_id:"12345678901",msku:"SKU1-US",owner_ref:"负责人",launch_date_cn:"2026-01-15",strike_price:"18.99",strike_currency:"USD",sale_price:"9.99",sale_currency:"USD",strike_effect:"effective",ad_enabled:true,site_label:"已提交",purchase_candidate:true};
const row:Parameters<typeof toProgressRow>[0]={source_account_ref:"A",sku_identity_id:"11111111-1111-1111-1111-111111111111",sku:"SKU1",product_name:"商品",main_image_url:"",developer_name:"开发",developer_uid:"D1",development_date:"2026-01-01",listing_status:"listed",progress_status:"in_progress",remark:"备注",plan_label:"未提交",proc_label:"待确认",domestic_shipping_status:null,listings:[listing,{...listing,store_id:"S2",item_id:"22345678901",ad_enabled:null,purchase_candidate:false}],independent_site_submissions:[]};
describe("SKU progress live API",()=>{
  beforeEach(()=>request.mockReset());
  it("deduplicates multi-select values and sends real dates and search type",()=>{
    const p=criteriaParams(criteria);expect(p.getAll("store")).toHaveLength(2);expect(p.get("start")).toBe("2026-01-01");expect(p.get("keyword")).toBe("SKU1");expect(p.get("search_field")).toBe("sku");
  });
  it("loads only one server page without splitting a SKU group",async()=>{
    request.mockResolvedValue({data:{items:[row],total:1000,listing_count:1300,page:2,page_size:20}});
    const result=await loadSkuProgress(criteria,2,20,{key:"date",order:"desc"});expect(request).toHaveBeenCalledTimes(1);expect(request.mock.calls[0][0]).toContain("page=2");expect(result.total).toBe(1000);expect(result.rows[0].ls).toHaveLength(2);expect(result.rows[0].ls[1].ad).toBe("待确认");
  });
  it("summary and facets are independent of page and preserve card semantics",async()=>{
    request.mockResolvedValue({data:{}});await loadProgressSummary(criteria);await loadProgressFacets(criteria);expect(request.mock.calls[0][0]).toContain("/summary?");expect(request.mock.calls[0][0]).toContain("card=all");expect(request.mock.calls[1][0]).toContain("/facets?");expect(request.mock.calls.every(c=>!String(c[0]).includes("page="))).toBe(true);
  });
  it("distinguishes unlisted, unknown and missing shipping evidence",()=>{
    expect(emptyListing(toProgressRow({...row,listings:[],listing_status:"unlisted"})).listing).toBe("未上架");expect(emptyListing(toProgressRow({...row,listings:[],listing_status:"unknown"})).listing).toBe("");expect(toProgressRow(row).shipping).toBe("待确认");
  });
  it("sends fixed twenty and exact scoped identity",async()=>{
    request.mockResolvedValue({data:{submission_status:"submitted",quantity:20,lingxing_plan_sn:"PLAN-1"}});const r=toProgressRow(row);await submitSkuPurchase(r,r.ls[0]);expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({source_account_ref:"A",sku_identity_id:row.sku_identity_id,store_id:"S1",item_id:listing.item_id,quantity:20});
  });
  it("does not post blocked listings",async()=>{const r=toProgressRow(row);await expect(submitSkuPurchase(r,r.ls[1])).rejects.toThrow();expect(request).not.toHaveBeenCalled();});
  it("rejects uncertain purchase receipt",async()=>{request.mockResolvedValue({data:{submission_status:"unknown",quantity:20,lingxing_plan_sn:null}});const r=toProgressRow(row);await expect(submitSkuPurchase(r,r.ls[0])).rejects.toThrow();});
  it("preserves manual status, reason, version and note",async()=>{
    const r=toProgressRow({...row,progress_status:"paused",reason_type:"其他原因",progress_version:3,can_edit_progress:true});
    expect(r.progressCode).toBe("paused");expect(r.reasonType).toBe("其他原因");expect(r.remark).toBe("备注");
    request.mockResolvedValue({data:{progress_status:"in_progress",version:4}});await saveSkuProgress(r,"in_progress",undefined,"  恢复说明  ");
    expect(JSON.parse(request.mock.calls[0][1].body)).toMatchObject({version:3,progress_status:"in_progress",reason_type:null,remark:"恢复说明"});
  });
  it("does not save in the read-only environment",async()=>{await expect(saveSkuProgress(toProgressRow(row),"completed",undefined,"note")).rejects.toThrow();expect(request).not.toHaveBeenCalled();});
  it("batch submits distinct SKUs sequentially and reports each result",async()=>{
    const first=toProgressRow(row),second=toProgressRow({...row,sku_identity_id:"other",sku:"SKU2"});
    request.mockRejectedValueOnce(new Error("unknown")).mockResolvedValueOnce({data:{submission_status:"submitted",quantity:20,lingxing_plan_sn:"P2"}});
    const results:unknown[]=[];await submitSkuPurchaseBatch([{row:first,listing:first.ls[0]},{row:second,listing:second.ls[0]}],r=>results.push(r));
    expect(results).toEqual([expect.objectContaining({ok:false,sku:"SKU1"}),expect.objectContaining({ok:true,sku:"SKU2",detail:"P2"})]);expect(request).toHaveBeenCalledTimes(2);
  });
  it("duplicate batch SKU never posts",async()=>{const r=toProgressRow(row);await expect(submitSkuPurchaseBatch([{row:r,listing:r.ls[0]},{row:r,listing:r.ls[0]}],()=>{})).rejects.toThrow();expect(request).not.toHaveBeenCalled();});
  it("rejects invalid pagination envelope",async()=>{request.mockResolvedValue({data:{items:[],total:100,page:1,page_size:20}});await expect(loadSkuProgress(criteria,2,20,{key:"date",order:"desc"})).rejects.toThrow();});
});

/** Acceptance: the clearance center consumes real API contracts, not demo stock. */
import { expect, test, type Page } from "@playwright/test";

const fixture = {
  listing: {
    id: "88f4f2bc-7f1d-495a-a6e9-c112eaa19c77",
    source_account_ref: "TEST-ACCOUNT",store_id: "TEST-STORE",store_name: "验收店铺",
    item_id: "TEST-ITEM-2201",local_sku: "TEST-SKU-2201",msku: "TEST-MSKU-2201",
    title: "真实接口验收商品",picture_url: null,owner_ref: "验收运营",
    listing_status:"PUBLISHED",sale_price_amount:"19.99",sale_price_currency_code:"USD",
    wfs_available_quantity:"120",snapshot_wfs_available:"120",
    inventory_captured_at:"2026-11-04T02:00:00Z",
    inbound_quantity:null,average_rating:"4.5",review_count:13,
    buybox_status:"WON",listing_start_at_utc:"2026-07-04T00:00:00Z",
  },
  evaluation:{
    risk_level:"medium",candidate_status:"auto",coverage_days:120,
    current_wfs_available:"120",inventory_captured_at:"2026-11-04T02:00:00Z",
    stock_capital_usd:"1050",unit_cost_usd:"8.75",sales_30d:"30",
    margin_30d_percent:"5.0",refund_rate_percent:"3.0",suggested_qty:60,
    positive_stock_days_30d:25,snapshot_coverage_days_30d:26,
    business_signal_groups:["PROFIT"],risk_reasons:["BACKLOG_AND_BUSINESS_SIGNAL"],
    protections:[],warnings:[],sales_complete:true,cost_complete:true,
    rule_version:"clearance-v1-20261104",as_of_date:"2026-11-04",
  },rule_config_version:0,
};

type Recorded = {method:string;path:string;body:unknown};
async function prepare(page:Page, writes:Recorded[], dailyReady: boolean | "stale" = true){
  const ready = dailyReady === true;
  const status = dailyReady === "stale" ? "stale" : ready ? "ready" : "not_ready";
  const runDate = ready ? "2026-11-04" : dailyReady === "stale" ? "2026-11-03" : null;
  const asOfDate = ready ? "2026-11-03" : dailyReady === "stale" ? "2026-11-02" : null;
  await page.addInitScript(()=>localStorage.setItem("szzsbj_auth_token","synthetic-clearance-live"));
  await page.route("**/api/**",async route=>{
    const url = new URL(route.request().url());
    if(!url.pathname.startsWith("/api/"))return route.fallback();
    const path=url.pathname,method=route.request().method();
    const auth=path==="/api/auth/me";
    let data:unknown={items:[],total:0};
    if(auth)data={id:16,username:"clearance-live",display_name:"测试运营",is_super_admin:true,
      role_keys:[],role_names:[],permissions:["*"]};
    else if(path==="/api/products/clearance-center/listings")data={
      items:ready?[fixture]:[],total:ready?1:0,page:1,page_size:50,
      evaluation_status:status,
      run_date_la:runDate,
      as_of_date_la:asOfDate,
    };
    else if(path==="/api/products/clearance-center/facets")data={
      accounts:["TEST-ACCOUNT"],
      stores:[{source_account_ref:"TEST-ACCOUNT",store_id:"TEST-STORE",store_name:"验收店铺"}],
    };
    else if(path==="/api/products/clearance-center/data-readiness")data={
      evaluation_status:status,
      run_date_la:runDate,
      as_of_date_la:asOfDate,
      total_listings:1,evaluated_listings:ready?1:0,
      not_evaluated_listings:ready?0:1,
      missing_sales_window:ready?0:null,
      missing_wfs_stock:ready?0:null,missing_profit_cost:ready?0:null,
      refund_period_data_complete:false,
    };
    else if(path==="/api/products/clearance-center/eligible-listings")data={
      items:[fixture],total:1,page:1,page_size:30,
    };
    else if(path==="/api/products/clearance-center/summary")data={
      total:ready?1:0,high:0,medium:ready?1:0,
      observe:0,review_required:0,eligible_manual:1,
      evaluation_status:status,
      run_date_la:runDate,
      as_of_date_la:asOfDate,
    };
    else if(path.endsWith("/rules"))data={source_account_ref:"TEST-ACCOUNT",version:0,
      rules:{high_coverage_days:180,medium_coverage_days:90,assisted_coverage_days:60}};
    else if(path.startsWith("/api/products/clearance-center/listings/"))data=fixture;
    else if(path==="/api/products/clearance-center/requests"&&method==="GET")data={
      items:[],total:0,page:1,page_size:50,
    };
    else if(path==="/api/products/clearance-center/requests"&&method==="POST"){
      const body=JSON.parse(route.request().postData()??"{}");
      writes.push({method,path,body});
      data={request_id:"REQ-1",approval_id:"APP-1",status:"pending"};
    }
    await route.fulfill({status:200,contentType:"application/json",
      body:JSON.stringify({success:true,data,error:null,meta:{},request_id:"clearance-contract"})});
  });
}

test("clearance page shows real Listing and no synthetic product rows",async({page})=>{
  await prepare(page,[]);
  await page.goto("/#/products/clearance-center");
  await expect(page.getByRole("heading",{name:"WFS 清货中心"})).toBeVisible();
  await expect(page.getByText("真实接口验收商品")).toBeVisible();
  await expect(page.getByText("TEST-SKU-2201")).toBeVisible();
  await expect(page.getByText("DEMO-SKU-101")).toHaveCount(0);
  await expect(page.getByText("中风险Listing")).toBeVisible();
});

test("manual application shows only eligible WFS Listing and posts one Listing",async({page})=>{
  const writes:Recorded[]=[];
  await prepare(page,writes);
  await page.goto("/#/products/clearance-center");
  await expect(page.getByRole("heading",{name:"WFS 清货中心"})).toBeVisible();
  await page.getByRole("button",{name:"申请 SKU"}).click();
  await expect(page.getByRole("dialog",{name:"主动申请 SKU"})).toBeVisible();
  await expect(page.getByText("真实接口验收商品").last()).toBeVisible();
  await page.getByRole("button",{name:"选择商品"}).click();
  await page.getByRole("button",{name:"下一步"}).click();
  const modal=page.getByRole("dialog",{name:"主动申请 SKU"});
  await modal.getByRole("textbox",{name:"申请说明"}).fill("WFS Listing 库存积压，申请通过降价处理");
  await modal.getByRole("button",{name:"提交申请"}).click();
  await expect(modal).toHaveCount(0);
  expect(writes).toHaveLength(1);
  const body=writes[0].body as Record<string,unknown>;
  expect(body.listing_id).toBe(fixture.listing.id);
  expect(body.target_qty).toBe(60);
  expect(body.methods).toEqual(["降价"]);
  expect(body.source).toBe("manual");
});


test("without midnight score, review is visibly pending but WFS application is available",async({page})=>{
  const writes:Recorded[]=[];
  await prepare(page,writes,false);
  await page.goto("/#/products/clearance-center");
  await expect(page.getByText("每日清货评估尚未生成")).toBeVisible();
  await expect(page.getByText("真实接口验收商品")).toHaveCount(0);
  await page.getByRole("button",{name:"申请 SKU"}).click();
  await expect(page.getByRole("dialog",{name:"主动申请 SKU"})).toBeVisible();
  await expect(page.getByText("真实接口验收商品")).toBeVisible();
});

test("daily risk snapshot displays its previous-complete-day provenance",async({page})=>{
  await prepare(page,[]);
  await page.goto("/#/products/clearance-center");
  await expect(page.getByText(/最近评估：2026-11-04/)).toBeVisible();
  await expect(page.getByText(/经营数据截至 2026-11-03/)).toBeVisible();
});


test("stale midnight evaluation is blocked but live WFS picker remains available",async({page})=>{
  await prepare(page,[],"stale");
  await page.goto("/#/products/clearance-center");
  await expect(page.getByText("今日美国太平洋时间的清货评估尚未成功")).toBeVisible();
  await expect(page.getByText("真实接口验收商品")).toHaveCount(0);
  await page.getByRole("button",{name:"申请 SKU"}).click();
  await expect(page.getByText("真实接口验收商品")).toBeVisible();
});


test("analysis Listing scroll fetches 50 at a time without page buttons",async({page})=>{
  const requestedPages:number[]=[];
  await prepare(page,[]);
  await page.route("**/api/products/clearance-center/listings?**",async route=>{
    const url=new URL(route.request().url());
    const current=Number(url.searchParams.get("page")||1);
    requestedPages.push(current);
    const start=(current-1)*50;
    const items=Array.from({length:Math.max(0,Math.min(50,110-start))},(_,i)=>({
      ...fixture,
      listing:{
        ...fixture.listing,
        id:`00000000-0000-4000-8000-${String(start+i).padStart(12,"0")}`,
        item_id:`TEST-WFS-${String(start+i).padStart(4,"0")}`,
        title:`可售 WFS Listing ${start+i+1}`,
      },
    }));
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({
      success:true,data:{items,total:110,page:current,page_size:50,
        evaluation_status:"ready",run_date_la:"2026-11-04",
        as_of_date_la:"2026-11-03"},
      error:null,meta:{},request_id:"clearance-infinite-scroll",
    })});
  });
  await page.goto("/#/products/clearance-center");
  await expect(page.getByText("已加载 50 / 110 条")).toBeVisible();
  await expect(page.getByRole("button",{name:"下一页"})).toHaveCount(0);
  const body=page.locator(".clearance-live-list .ant-table-body");
  await body.evaluate(node=>{node.scrollTop=node.scrollHeight;node.dispatchEvent(new Event("scroll"));});
  await expect(page.getByText("已加载 100 / 110 条")).toBeVisible();
  await body.evaluate(node=>{node.scrollTop=node.scrollHeight;node.dispatchEvent(new Event("scroll"));});
  await expect(page.getByText("已加载全部 110 条 Listing")).toBeVisible();
  expect(requestedPages).toEqual([1,2,3]);
});


test("manual WFS Listing picker appends on scroll without pagination",async({page})=>{
  const pages:number[]=[];
  await prepare(page,[]);
  await page.route("**/api/products/clearance-center/eligible-listings?**",async route=>{
    const current=Number(new URL(route.request().url()).searchParams.get("page")||1);
    pages.push(current);
    const offset=(current-1)*50;
    const items=Array.from({length:Math.max(0,Math.min(50,55-offset))},(_,i)=>({
      ...fixture,
      listing:{
        ...fixture.listing,
        id:`11111111-1111-4111-8111-${String(i+offset).padStart(12,"0")}`,
        item_id:`ELIGIBLE-WFS-${String(offset+i).padStart(4,"0")}`,
        title:`可选 WFS 商品 ${offset+i+1}`,
      },
    }));
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({
      success:true,data:{items,total:55,page:current,page_size:50},
      error:null,meta:{},request_id:"eligible-scroll",
    })});
  });
  await page.goto("/#/products/clearance-center");
  await page.getByRole("button",{name:"申请 SKU"}).click();
  const modal=page.getByRole("dialog",{name:"主动申请 SKU"});
  await expect(modal.getByText("已加载 50 / 55 条")).toBeVisible();
  await expect(modal.getByRole("button",{name:"下一页"})).toHaveCount(0);
  const body=modal.locator(".ant-table-body");
  await body.evaluate(node=>{node.scrollTop=node.scrollHeight;node.dispatchEvent(new Event("scroll"));});
  await expect(modal.getByText("已加载全部 55 条符合条件的商品")).toBeVisible();
  expect(pages).toEqual([1,2]);
});

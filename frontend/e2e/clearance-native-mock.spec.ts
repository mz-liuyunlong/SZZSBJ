import { expect, test, type Page } from "@playwright/test";

async function prepare(page:Page){
 await page.addInitScript(()=>localStorage.setItem("szzsbj_auth_token","synthetic-clearance-layout"));
 await page.route("**/api/**",async route=>{
  const pathname=new URL(route.request().url()).pathname;
  // Vite modules under /src/api/ must never be returned as mock JSON.
  if(!pathname.startsWith("/api/"))return route.fallback();
  const data=pathname==="/api/auth/me"
   ? {id:16,username:"clearance-layout",display_name:"清货测试",is_super_admin:true,role_keys:[],role_names:[],permissions:["*"]}
   : {items:[],total:0};
  await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({success:true,data,error:null,meta:{},request_id:"mock-clearance"})});
 });
}
test("clearance uses one native page, shared table and mock only",async({page})=>{
 await prepare(page);
 const pageErrors:string[]=[];
 const authRequests:string[]=[];
 page.on("pageerror",error=>pageErrors.push(error.message+" "+error.stack));
 page.on("response",response=>{if(new URL(response.url()).pathname==="/api/auth/me")authRequests.push(String(response.status()));});
 await page.goto("/#/products/clearance-center");
 try {
  await expect(page.getByRole("heading",{name:"WFS 清货中心"})).toBeVisible({timeout:15000});
 } catch {
  const body=(await page.locator("body").innerText().catch(()=>"<body unavailable>")).slice(0,1800);
  throw new Error("Clearance route failed: "+JSON.stringify({url:page.url(),body,pageErrors,authRequests,token:await page.evaluate(()=>Boolean(localStorage.getItem("szzsbj_auth_token")))}));
 }
 await expect(page.locator("iframe")).toHaveCount(0);
 await expect(page.locator(".clearance-main-card .ant-pro-table")).toHaveCount(1);
 await expect(page.getByText("数据周期：",{exact:true})).toBeVisible();
 await expect(page.locator(".clearance-period-segmented .ant-segmented-item-selected")).toContainText("30天");
 await expect(page.getByText("7 / 14 / 30 日均销量")).toHaveCount(0);
 const item=page.locator(".clearance-main-card .ant-table-row").filter({hasText:"DEMO-SKU-101"});
 await expect(item).toContainText("$223.86");
 await page.getByText("7天",{exact:true}).click();
 await expect(page.locator(".clearance-period-segmented .ant-segmented-item-selected")).toContainText("7天");
 await expect(item).toContainText("$31.98");
 await page.getByText("30天",{exact:true}).click();
 await expect(item).toContainText("$223.86");
 await expect(page.getByText("仅 Mock 数据")).toBeVisible();
 await page.getByRole("button",{name:"规则配置"}).click();
 await expect(page.getByRole("heading",{name:"清货规则配置"})).toBeVisible();
 await expect(page.getByText("影响预览确认后才保存",{exact:false})).toBeVisible();
 await page.getByRole("tab",{name:/清货管理/}).click();
 await expect(page.getByRole("button",{name:"任务详情"}).first()).toBeVisible();
 await page.getByRole("button",{name:"申请 SKU"}).click();
 await expect(page.getByRole("dialog",{name:"运营主动申请清货"})).toBeVisible();
});

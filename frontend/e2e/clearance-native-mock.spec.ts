import { expect, test, type Page } from "@playwright/test";

async function prepare(page:Page){
 await page.addInitScript(()=>localStorage.setItem("szzsbj_auth_token","synthetic-clearance-layout"));
 await page.route("**/api/**",async route=>{
  const pathname=new URL(route.request().url()).pathname;
  const data=pathname==="/api/auth/me"
   ? {id:16,username:"clearance-layout",display_name:"清货测试",is_super_admin:true,role_keys:[],role_names:[],permissions:["*"]}
   : {items:[],total:0};
  await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({success:true,data,error:null,meta:{},request_id:"mock-clearance"})});
 });
}
test("clearance uses one native page, shared table and mock only",async({page})=>{
 await prepare(page);
 await page.goto("/#/products/clearance-center");
 await expect(page.getByRole("heading",{name:"WFS 清货中心"})).toBeVisible();
 await expect(page.locator("iframe")).toHaveCount(0);
 await expect(page.locator(".clearance-main-card .ant-pro-table")).toHaveCount(1);
 await expect(page.getByText("仅 Mock 数据")).toBeVisible();
 await page.getByRole("button",{name:"规则配置"}).click();
 await expect(page.getByRole("heading",{name:"清货规则配置"})).toBeVisible();
 await expect(page.getByText("影响预览确认后才保存",{exact:false})).toBeVisible();
 await page.getByRole("tab",{name:/清货管理/}).click();
 await expect(page.getByRole("button",{name:"任务详情"}).first()).toBeVisible();
 await page.getByRole("button",{name:"申请 SKU"}).click();
 await expect(page.getByRole("dialog",{name:"运营主动申请清货"})).toBeVisible();
});

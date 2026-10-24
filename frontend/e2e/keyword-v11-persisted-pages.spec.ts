/** Three real routes read synthetic API contracts; no provider or production calls. */
import {expect,test,type Page} from '@playwright/test';

test.use({channel:process.env.PLAYWRIGHT_CHANNEL});
test.setTimeout(60000);

const product='00000000-0000-4000-8000-000000000001';
const account='synthetic-account';
const envelope=(data:unknown)=>({success:true,data,error:null,meta:{},request_id:'synthetic-v11'});

async function prepare(page:Page){
 await page.addInitScript(()=>localStorage.setItem('szzsbj_auth_token','synthetic-keyword-v11'));
 await page.route('**/api/**',async route=>{
  const url=new URL(route.request().url());
  if(!url.pathname.startsWith('/api/'))return route.fallback();
  let data:unknown={items:[],total:0};
  if(url.pathname==='/api/auth/me')data={id:16,username:'v11-fixture',display_name:'V1.1 测试',
   is_super_admin:true,role_keys:[],role_names:[],permissions:['*']};
  else if(url.pathname.endsWith('/source-state'))data={product_id:product,
   latest_confirmed_fact_id:'00000000-0000-4000-8000-000000000002',
   latest_upload_id:'00000000-0000-4000-8000-000000000003',item_id:'123456789',
   asin_reference_count:2,source_status:'fact_confirmed'};
  else if(url.pathname.endsWith('/runs'))data={items:[{run_id:'00000000-0000-4000-8000-000000000004',
   product_id:product,source_account_ref:account,item_id:'123456789',status:'blocked',
   rule_version_id:'00000000-0000-4000-8000-000000000005',created_at:'2026-01-15T00:00:00Z',
   finished_at:'2026-01-15T00:00:01Z',keyword_count:1}],total:1,limit:20,offset:0};
  else if(url.pathname.endsWith('/library'))data={items:[{term_id:'00000000-0000-4000-8000-000000000006',
   keyword:'synthetic pantry bin',translation:null,status:'review',source_kinds:['xlsx'],
   source_count:1,observation_count:0,latest_grade:null,latest_score:null}],
   total:1,limit:50,offset:0,latest_run_id:'00000000-0000-4000-8000-000000000004'};
  else if(url.pathname.endsWith('/rulesets'))data={items:[{rule_set_id:'00000000-0000-4000-8000-000000000007',
   rule_key:'test_scoring',display_name:'合成规则',scope_key:account,is_enabled:false}],total:1};
  else if(url.pathname.endsWith('/versions'))data={items:[{version_id:'00000000-0000-4000-8000-000000000005',
   version_number:1,status:'draft',config:{limits:{}},config_sha256:'a'.repeat(64),created_at:'2026-01-15',
   publish_eligible:false}],total:1};
  else if(url.pathname.endsWith('/decisions'))data={items:[],events:[],total:0};
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(envelope(data))});
 });
}

test('launch reloads persisted analysis history and keeps official upload closed',async({page})=>{
 await prepare(page);await page.goto('/#/ai-center/keyword-launch');
 await expect(page.getByText('Walmart 关键词 V1.1 · 真实数据工作台')).toBeVisible();
 await page.getByPlaceholder('请输入账户范围').fill(account);
 await page.getByPlaceholder('请输入产品 UUID').fill(product);
 await page.getByRole('tab',{name:'分析批次'}).click();
 await expect(page.getByText('123456789')).toBeVisible();
 await page.reload({waitUntil:'domcontentloaded'});
 await expect(page.getByText('Walmart 关键词 V1.1 · 真实数据工作台')).toBeVisible();
 await expect(page.getByRole('button',{name:'Walmart 官方上传'})).toHaveCount(0);
});

test('rules page reads persisted draft and cannot publish pending decisions',async({page})=>{
 await prepare(page);await page.goto('/#/ai-center/keyword-launch/rules');
 await expect(page.getByText('关键词 V1.1 规则版本 · 后端持久化')).toBeVisible();
 await page.getByRole('textbox',{name:'来源账户'}).fill(account);
 await page.getByRole('button',{name:'读取持久化规则集'}).click();
 await expect(page.getByText('合成规则')).toBeVisible();
 await page.getByRole('button',{name:'查看版本'}).click();
 await page.getByRole('button',{name:'查看决策'}).click();
 await expect(page.getByText('未提交')).toHaveCount(8);
 await expect(page.getByRole('button',{name:'请求发布（后端再次核验身份）'})).toBeDisabled();
});

test('library reads persisted words and reload does not invent browser scores',async({page})=>{
 await prepare(page);await page.goto('/#/ads/keyword-library');
 await expect(page.getByText('关键词词库 · 后端持久化')).toBeVisible();
 await page.getByRole('textbox',{name:'来源账户'}).fill(account);
 await page.getByRole('textbox',{name:'产品 UUID'}).fill(product);
 await page.getByRole('button',{name:'读取词库'}).click();
 await expect(page.getByText('synthetic pantry bin')).toBeVisible();
 await expect(page.getByText('待复核')).toBeVisible();
 await page.reload({waitUntil:'domcontentloaded'});
 await expect(page.getByText('关键词词库 · 后端持久化')).toBeVisible();
});

test('launch pages both persisted runs and keyword results through the backend',async({page})=>{
 await prepare(page);
 const offsets:number[]=[];
 await page.route('**/api/v1/keyword-planning/**',async route=>{
  const url=new URL(route.request().url());
  const offset=Number(url.searchParams.get('offset')||0);
  let data:unknown;
  if(url.pathname.endsWith('/keywords')){
   offsets.push(offset);
   data={run_id:'00000000-0000-4000-8000-000000000004',items:[{
    term_id:offset?'00000000-0000-4000-8000-000000000009':'00000000-0000-4000-8000-000000000008',
    keyword:offset?'synthetic page two keyword':'synthetic page one keyword',
    primary_type:'人工确认词',page_coverage:'页面看不出来',core_root:null,score:null,
    base_grade:null,allocation_grade:null,exact_selected:false,broad_selected:false,
    broad_role:null,suggested_optimization_bid:null,decision_status:'review',risk_reasons:[],
    exact_reason:null,broad_reason:null,quality_note:null,rank_index:null,
   }],total:51,limit:50,offset,official_export_authorized:false};
  }else if(url.pathname.endsWith('/runs')){
   offsets.push(offset);
   data={items:[{run_id:'00000000-0000-4000-8000-000000000004',product_id:product,
    source_account_ref:account,item_id:offset?'synthetic-page-two-item':'synthetic-page-one-item',
    status:'blocked',rule_version_id:'00000000-0000-4000-8000-000000000005',
    created_at:'2026-01-15T00:00:00Z',finished_at:'2026-01-15T00:00:01Z',keyword_count:51}],
    total:21,limit:20,offset};
  }else if(url.pathname.endsWith('/runs/00000000-0000-4000-8000-000000000004')){
   data={run_id:'00000000-0000-4000-8000-000000000004',product_id:product,
    source_account_ref:account,item_id:'synthetic-page-two-item',status:'blocked',
    rule_version_id:'00000000-0000-4000-8000-000000000005',
    created_at:'2026-01-15T00:00:00Z',finished_at:'2026-01-15T00:00:01Z',keyword_count:51};
  }else return route.fallback();
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(envelope(data))});
 });
 await page.goto('/#/ai-center/keyword-launch');
 await page.getByPlaceholder('请输入账户范围').fill(account);
 await page.getByPlaceholder('请输入产品 UUID').fill(product);
 await page.getByRole('tab',{name:'分析批次'}).click();
 await expect(page.getByText('synthetic-page-one-item')).toBeVisible();
 await page.locator('.ant-pagination-item-2').first().click();
 await expect(page.getByText('synthetic-page-two-item')).toBeVisible();
 await page.getByRole('button',{name:'查看结果'}).click();
 await expect(page.getByText('synthetic page one keyword')).toBeVisible();
 await page.locator('.ant-pagination-item-2').last().click();
 await expect(page.getByText('synthetic page two keyword')).toBeVisible();
 expect(offsets).toContain(20);
 expect(offsets).toContain(50);
});

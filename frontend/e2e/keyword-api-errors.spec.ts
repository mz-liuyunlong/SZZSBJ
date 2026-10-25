import {expect,test} from '@playwright/test';

const product='00000000-0000-0000-0000-000000000101';
const listing='00000000-0000-0000-0000-000000000102';
const account='synthetic-account';
const productRow={sku_id:product,sku:'SYNTHETIC-A',product_name:'Synthetic product',
  image_count:0,internal_tags:[],source_tags:[],purchase_delivery_days:null,data_quality_score:null};
const listingRow={id:listing,source_account_ref:account,item_id:'12345678',
  local_sku:'SYNTHETIC-A',store_id:'synthetic-store',store_name:'Synthetic store',
  calculated_at:'2026-01-15T00:00:00Z',tags:[]};

test('keyword reads fail independently without changing the original page',async({page})=>{
  const errors:string[]=[];
  const requests=new Map<string,number>();
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(({product,listing})=>{
    localStorage.setItem('szzsbj_auth_token','synthetic-test-token');
    sessionStorage.setItem('keyword-planning:selected-product',JSON.stringify({id:product,sku:'SYNTHETIC-A'}));
    sessionStorage.setItem('keyword-planning:selected-listing',listing);
  },{product,listing});
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(!path.startsWith('/api/'))return route.fallback();
    requests.set(path,(requests.get(path)??0)+1);
    let data:unknown={items:[],total:0};
    let status=200;
    let error:null|{code:string}=null;
    if(path==='/api/auth/me')data={id:1,username:'synthetic',display_name:'Synthetic',
      is_super_admin:true,role_keys:[],role_names:[],permissions:['*']};
    else if(path==='/api/product-management/skus')data={items:[productRow]};
    else if(path==='/api/listings/walmart')data={items:[listingRow]};
    else if(path.endsWith('/source-state'))data={product_id:product,latest_confirmed_fact_id:'00000000-0000-0000-0000-000000000103',
      latest_upload_id:null,latest_upload_filename:null,latest_upload_rows:0,item_id:'12345678',
      confirmed_fields:{},asin_reference_count:0,asin_references:[],source_status:'fact_confirmed'};
    else if(path.endsWith('/rulesets')||path.endsWith('/runs')){
      status=500;error={code:'INTERNAL_ERROR'};data=null;
    }
    await route.fulfill({status,contentType:'application/json',body:JSON.stringify({
      success:status===200,data,error,meta:{total:1},request_id:`synthetic-${status}`,
    })});
  });
  const response=await page.goto('/#/ai-center/keyword-launch');
  try{
    await expect(page.getByRole('heading',{name:'新品关键词投放'})).toBeVisible({timeout:15000});
  }catch{
    throw new Error(`Unexpected page status: ${response?.status()} url: ${page.url()} requests: ${JSON.stringify([...requests])} errors: ${errors.join('; ')} body: ${(await page.locator('body').innerText()).slice(0,500)}`);
  }
  await expect(page.locator('.kw-v2-page')).toBeVisible();
  await expect(page.getByText(/Walmart 已验证/)).toBeVisible();
  await expect(page.getByText(/规则服务端异常（HTTP 500）/)).toBeVisible();
  await expect(page.getByText(/分析历史服务端异常（HTTP 500）/)).toBeVisible();
  await expect(page.getByText(/来源接口返回 404/)).toHaveCount(0);
  expect(requests.get(`/api/v1/keyword-planning/products/${product}/source-state`)).toBe(1);
  expect(requests.get(`/api/v1/keyword-planning/products/${product}/runs`)).toBe(1);
  expect(errors).toEqual([]);
});

test('source 404 and history 403 retain separate diagnostic messages',async({page})=>{
  await page.addInitScript(({product,listing})=>{
    localStorage.setItem('szzsbj_auth_token','synthetic-test-token');
    sessionStorage.setItem('keyword-planning:selected-product',JSON.stringify({id:product,sku:'SYNTHETIC-A'}));
    sessionStorage.setItem('keyword-planning:selected-listing',listing);
  },{product,listing});
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(!path.startsWith('/api/'))return route.fallback();
    let status=200;
    let data:unknown={items:[],total:0};
    if(path==='/api/auth/me')data={id:1,username:'synthetic',display_name:'Synthetic',
      is_super_admin:true,role_keys:[],role_names:[],permissions:['*']};
    else if(path==='/api/product-management/skus')data={items:[productRow]};
    else if(path==='/api/listings/walmart')data={items:[listingRow]};
    else if(path.endsWith('/source-state'))status=404;
    else if(path.endsWith('/runs'))status=403;
    await route.fulfill({status,contentType:'application/json',body:JSON.stringify({
      success:status===200,data:status===200?data:null,error:status===200?null:{code:status===404?'NOT_FOUND':'DATA_SCOPE_DENIED'},
      meta:{total:1},request_id:`synthetic-${status}`,
    })});
  });
  await page.goto('/#/ai-center/keyword-launch');
  await expect(page.getByRole('heading',{name:'新品关键词投放'})).toBeVisible({timeout:15000});
  await expect(page.getByText(/来源接口返回 404/)).toBeVisible();
  await expect(page.getByText(/分析历史读取被拒绝/)).toBeVisible();
  await expect(page.getByText(/请求 ID：synthetic-404/)).toBeVisible();
});

test('a late source response for the previous SKU cannot confirm the new SKU',async({page})=>{
  const nextProduct='00000000-0000-0000-0000-000000000201';
  const nextListing='00000000-0000-0000-0000-000000000202';
  let releaseFirst=()=>{};
  const firstPending=new Promise<void>(resolve=>{releaseFirst=resolve});
  let firstSourceRequested=false;
  let nextSourceRequested=false;
  await page.addInitScript(({product,listing})=>{
    localStorage.setItem('szzsbj_auth_token','synthetic-test-token');
    sessionStorage.setItem('keyword-planning:selected-product',JSON.stringify({id:product,sku:'SYNTHETIC-A'}));
    sessionStorage.setItem('keyword-planning:selected-listing',listing);
  },{product,listing});
  await page.route('**/api/**',async route=>{
    const url=new URL(route.request().url());
    const path=url.pathname;
    if(!path.startsWith('/api/'))return route.fallback();
    let data:unknown={items:[],total:0};
    if(path==='/api/auth/me')data={id:1,username:'synthetic',display_name:'Synthetic',
      is_super_admin:true,role_keys:[],role_names:[],permissions:['*']};
    else if(path==='/api/product-management/skus')data={items:[productRow,{
      ...productRow,sku_id:nextProduct,sku:'SYNTHETIC-B',product_name:'Synthetic B',
    }]};
    else if(path==='/api/listings/walmart')data={items:[url.searchParams.get('keyword')?.includes('B')
      ?{...listingRow,id:nextListing,item_id:'87654321',local_sku:'SYNTHETIC-B'}:listingRow]};
    else if(path.endsWith('/source-state')){
      if(path.includes(product)){firstSourceRequested=true;await firstPending}
      else nextSourceRequested=true;
      data={product_id:path.includes(product)?product:nextProduct,
        latest_confirmed_fact_id:path.includes(product)?'00000000-0000-0000-0000-000000000103':null,
        latest_upload_id:null,latest_upload_filename:null,latest_upload_rows:0,
        item_id:path.includes(product)?'12345678':null,confirmed_fields:{},
        asin_reference_count:0,asin_references:[],source_status:path.includes(product)?'fact_confirmed':'ready_for_import'};
    }
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
      success:true,data,error:null,meta:{total:2},request_id:'synthetic-stale-check',
    })});
  });
  try{
    await page.goto('/#/ai-center/keyword-launch');
    await expect.poll(()=>firstSourceRequested).toBe(true);
    await page.locator('.kw-v2-setup .ant-select').first().click();
    await page.locator('.kw-v2-setup .ant-select-selection-search-input').first().fill('SYNTHETIC-B');
    await page.locator('.ant-select-item-option').filter({hasText:'SYNTHETIC-B'}).click();
    await expect.poll(()=>nextSourceRequested).toBe(true);
    releaseFirst();
    await expect(page.locator('.kw-v2-snapshot .kw-v2-muted')).toContainText('SYNTHETIC-B');
    await expect(page.getByText('已采集确认',{exact:true})).toHaveCount(0);
  }finally{releaseFirst()}
});

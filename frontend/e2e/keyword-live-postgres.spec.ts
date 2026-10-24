import {expect,test} from '@playwright/test';

const api = process.env.KW_LIVE_API_BASE;
test.skip(!api, 'Requires the disposable PostgreSQL + FastAPI sandbox');

test('original pages read frozen results and a manual word from real FastAPI after refresh',async({page})=>{
  const product=process.env.KW_LIVE_PRODUCT_ID!;
  const listing=process.env.KW_LIVE_LISTING_ID!;
  const account='sandbox-account';
  const productRow={sku_id:product,sku:'SYNTHETIC-A',product_name:'Synthetic organizer',
    image_count:0,internal_tags:[],source_tags:[],purchase_delivery_days:null,
    data_quality_score:null};
  const listingRow={id:listing,source_account_ref:account,item_id:'12345678',
    local_sku:'SYNTHETIC-A',store_id:'synthetic-store',store_name:'Synthetic store',
    calculated_at:'2026-01-15T00:00:00Z',tags:[]};
  let realKeywordReads=0;
  const browserErrors:string[]=[];
  page.on('pageerror',error=>browserErrors.push(error.message));
  page.on('console',entry=>{if(entry.type()==='error')browserErrors.push(entry.text());});
  page.on('requestfailed',request=>browserErrors.push(`request ${request.url()} ${request.failure()?.errorText}`));
  page.on('response',response=>{if(response.status()>=400)browserErrors.push(`HTTP ${response.status()} ${response.url()}`);});
  await page.addInitScript(({product,listing})=>{
    localStorage.setItem('szzsbj_auth_token','synthetic-test-token');
    sessionStorage.setItem('keyword-planning:selected-product',JSON.stringify({id:product,sku:'SYNTHETIC-A'}));
    sessionStorage.setItem('keyword-planning:selected-listing',listing);
  },{product,listing});
  await page.route('**/api/**',async route=>{
    const url=new URL(route.request().url());
    if(!url.pathname.startsWith('/api/'))return route.fallback();
    if(url.pathname.startsWith('/api/v1/keyword-planning/')){
      if(url.pathname.endsWith('/keywords'))realKeywordReads++;
      const response=await route.fetch({url:new URL(url.pathname+url.search,api).toString()});
      await route.fulfill({response});
      return;
    }
    let data:unknown={items:[],total:0};
    let meta:Record<string,unknown>={total:0};
    if(url.pathname==='/api/auth/me')data={id:1,username:'synthetic',display_name:'Synthetic',
      is_super_admin:true,role_keys:[],role_names:[],permissions:['*']};
    else if(url.pathname==='/api/product-management/skus'){
      data={items:[productRow]};meta={total:1};
    }else if(url.pathname==='/api/listings/walmart'){
      data={items:[listingRow]};meta={total:1};
    }
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
      success:true,data,error:null,meta,request_id:'synthetic-fixture',
    })});
  });
  await page.goto('/#/ai-center/keyword-launch');
  try{
    await expect(page.getByRole('heading',{name:'新品关键词投放'})).toBeVisible({timeout:10000});
  }catch{
    throw new Error(`Page ${page.url()} errors ${browserErrors.join('; ')} body ${(await page.locator('body').innerText()).slice(0,500)}`);
  }
  await expect(page.getByText('pantry organizer',{exact:true}).first()).toBeVisible();
  await page.reload();
  await expect(page.getByText('pantry organizer',{exact:true}).first()).toBeVisible();
  expect(realKeywordReads).toBeGreaterThanOrEqual(2);

  await page.goto('/#/ads/keyword-library');
  await expect(page.getByRole('region',{name:'SKU 关键词词库明细'}).getByRole('row',{name:/pantry organizer/})).toBeVisible();
  await page.getByRole('button',{name:'跨 SKU 关键词'}).click();
  await expect(page.getByRole('button',{name:'2 个 SKU'}).first()).toBeVisible();
  await page.getByRole('button',{name:'按 SKU 查看'}).click();
  await page.getByRole('button',{name:'＋ 添加关键词'}).first().click();
  await page.getByRole('textbox',{name:'英文关键词',exact:false}).fill('synthetic manual phrase');
  await page.getByRole('button',{name:'添加到词库'}).click();
  await expect(page.getByText('关键词已保存，状态为待分析')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('region',{name:'SKU 关键词词库明细'}).getByRole('row',{name:/synthetic manual phrase/})).toBeVisible();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'导出当前词库'}).click();
  expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
});

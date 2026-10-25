import {expect,test} from '@playwright/test';

test('original keyword page restores a frozen backend run after refresh',async({page})=>{
  const product='00000000-0000-0000-0000-000000000101';
  const listing='00000000-0000-0000-0000-000000000102';
  const runId='00000000-0000-0000-0000-000000000103';
  const rule='00000000-0000-0000-0000-000000000104';
  const fact='00000000-0000-0000-0000-000000000105';
  const upload='00000000-0000-0000-0000-000000000106';
  const account='synthetic-account';
  let resultReads=0;
  const libraryQueries:string[]=[];
  await page.addInitScript(({product,listing})=>{
    localStorage.setItem('szzsbj_auth_token','synthetic-test-token');
    sessionStorage.setItem('keyword-planning:selected-product',JSON.stringify({id:product,sku:'SYNTHETIC-SKU'}));
    sessionStorage.setItem('keyword-planning:selected-listing',listing);
  },{product,listing});
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(!path.startsWith('/api/'))return route.fallback();
    const productRow={sku_id:product,sku:'SYNTHETIC-SKU',product_name:'Synthetic organizer',
      image_count:0,internal_tags:[],source_tags:[],purchase_delivery_days:null,
      data_quality_score:null};
    const listingRow={id:listing,source_account_ref:account,item_id:'123456789',
      local_sku:'SYNTHETIC-SKU',store_id:'synthetic-store',store_name:'Synthetic store',
      calculated_at:'2026-01-15T00:00:00Z',tags:[]};
    const run={run_id:runId,product_id:product,source_account_ref:account,item_id:'123456789',
      status:'succeeded',rule_version_id:rule,created_at:'2026-01-15T00:00:00Z',
      finished_at:'2026-01-15T00:00:02Z',keyword_count:1};
    let data:unknown={items:[],total:0};
    let meta:Record<string,unknown>={total:0};
    if(path==='/api/auth/me')data={id:1,username:'synthetic',display_name:'Synthetic',
      is_super_admin:true,role_keys:[],role_names:[],permissions:['*']};
    else if(path==='/api/product-management/skus'){
      data={items:[productRow]};meta={total:1};
    }else if(path==='/api/listings/walmart'){
      data={items:[listingRow]};meta={total:1};
    }else if(path.endsWith('/source-state'))data={product_id:product,
      latest_confirmed_fact_id:fact,latest_upload_id:upload,
      latest_upload_filename:'synthetic.xlsx',latest_upload_rows:3,item_id:'123456789',
      confirmed_fields:{title:'Synthetic organizer',item_type:'organizer',brand:'Synthetic',
        material:'plastic',color:'blue',pack:'one',size:'small',structure:'box',
        use:'storage',owner:'Synthetic operator'},asin_reference_count:3,
      asin_references:['B000000001','B000000002','B000000003'],source_status:'fact_confirmed'};
    else if(path.endsWith('/runs'))data={items:[run],total:1,limit:20,offset:0};
    else if(path.endsWith('/library')){
      libraryQueries.push(new URL(route.request().url()).searchParams.get('q')||'');
      data={items:[{term_id:'00000000-0000-0000-0000-000000000107',
        keyword:'synthetic organizer',translation:null,status:'active',
        source_kinds:['seller_sprite_xlsx'],source_count:1,observation_count:0,
        latest_grade:'P1',latest_score:73}],total:1,limit:50,offset:0,latest_run_id:runId};
    }
    else if(path.endsWith('/keywords')){
      resultReads++;
      data={run_id:runId,total:1,limit:200,offset:0,official_export_authorized:false,
        items:[{term_id:'00000000-0000-0000-0000-000000000107',keyword:'synthetic organizer',
          primary_type:'核心本体词',page_coverage:'标题已埋词',core_root:'synthetic organizer',
          score:73,match_points:25,intent_points:18,page_points:10,root_points:10,
          data_points:10,risk_points:0,base_grade:'P1',allocation_grade:'P1',
          exact_selected:true,broad_selected:false,broad_role:null,
          suggested_optimization_bid:null,decision_status:'ready',risk_reasons:[],
          exact_reason:null,broad_reason:null,quality_note:null,rank_index:1,evidence:{}}]};
    }
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
      success:true,data,error:null,meta,request_id:'synthetic-fixture',
    })});
  });
  await page.goto('/#/ai-center/keyword-launch');
  await expect(page.getByRole('heading',{name:'新品关键词投放'})).toBeVisible();
  await expect(page.getByText('synthetic organizer',{exact:true}).first()).toBeVisible();
  await expect(page.getByText('后端冻结分析',{exact:false}).first()).toBeVisible();
  await page.reload();
  await expect(page.getByText('synthetic organizer',{exact:true}).first()).toBeVisible();
  expect(resultReads).toBeGreaterThanOrEqual(2);
  await expect(page).toHaveURL(/\/#\/ai-center\/keyword-launch$/);
  await page.goto('/#/ads/keyword-library');
  await expect(page.getByRole('region',{name:'SKU 关键词词库明细'}).getByRole('row',{name:/synthetic organizer/})).toBeVisible();
  await page.getByLabel('选择搜索维度').first().click();
  await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option[title="SKU"]').click();
  await page.getByLabel('输入关键词或SKU').fill('SYNTHETIC-SKU');
  await page.getByRole('button',{name:'搜索',exact:true}).click();
  await expect.poll(()=>libraryQueries.length).toBeGreaterThan(1);
  expect(libraryQueries.every(q=>q!== 'SYNTHETIC-SKU')).toBe(true);
});

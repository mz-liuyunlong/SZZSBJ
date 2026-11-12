import { describe, it, expect } from 'vitest';
import { toPersistedProduct } from './newProductRealAdapter';
import type { NewProductListing } from './newProductBusinessApi';

const original: NewProductListing = {
  listing: {
    id:'test-only',source_account_ref:'acc',store_id:'store',item_id:'item',
    msku:'SKU-M',local_sku:'SKU-L',title:'Test',local_name:'Test',
    store_name:'Store',owner_name:'Operator',picture_url:null,
    wfs_available_quantity:null,product_tags:[{id:'tag',label:'小批量测品',color:null}],
    first_wfs_available_date_la:null,
  },
  facts:{market_score:null,elapsed_days:null,roi:null,gross_margin_pct:null},
  evaluation:{rule_version:0,total:null,grade:null,
    dimensions:{market:null,speed:null,ad:null,profit:null,trust:null},
    missing:['成本缺失'],ad_excluded:false,observation_state:'insufficient_data'},
  tracking_decision:null,tracking_reason:null,market_reason:null,market_version:0,
  purchase_status:null,purchase_id:null,suggested_qty:null,
  system_recommendation:{value:'暂无法判定',reasons:['数据缺失']},
};

describe('new products real adapter',()=>{
 it('never invents a grade or marketplace score',()=>{
   const row=toPersistedProduct(original);
   expect(row.market).toBeNull();
   expect(row.backend.evaluation.total).toBeNull();
   expect(row.backend.evaluation.grade).toBeNull();
   expect(row.backend.available.roi).toBe(false);
   expect(row.status).toBe('待市场评分');
   expect(row.id).toBe('acc::store::item');
 });
 it('carries persisted optimistic concurrency versions',()=>{
   const row=toPersistedProduct({...original,market_version:3});
   expect(row.backend.marketVersion).toBe(3);
 });
 it('renders stage one product identities without inventing evaluation',()=>{
   const row=toPersistedProduct({...original,
     evaluation:{...original.evaluation,observation_state:'not_calculated'},
     facts:{first_wfs_available_date_la:null,elapsed_days:null,data_status:'not_calculated'}});
   expect(row.status).toBe('待计算');
   expect(row.tracking).toBe('未判定');
   expect(row.backend.available.elapsedDays).toBe(false);
   expect(row.backend.evaluation.total).toBeNull();
   expect(row.backend.evaluation.grade).toBeNull();
 });
 it('uses daily order count rather than listing sales units',()=>{
   const row=toPersistedProduct({
     ...original,
     listing:{...original.listing,sales_7d:12},
     facts:{...original.facts,orders_7d:0,valid_orders_14d:0,
       ad_spend_usd:'0',ad_clicks:0},
   });
   expect(row.qty7).toBe(0);
   expect(row.backend.available.qty7).toBe(true);
   expect(row.backend.available.orders14).toBe(true);
   expect(row.backend.available.spend).toBe(true);
   expect(row.backend.available.clicks).toBe(true);
 });
 it('does not show fake zeros when order summaries have not been provided',()=>{
   const row=toPersistedProduct({...original,listing:{...original.listing,sales_7d:10}});
   expect(row.backend.available.qty7).toBe(false);
   expect(row.backend.available.orders14).toBe(false);
 });

});

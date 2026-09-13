# 查询订单利润-MSKU — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-09FE9E838C58` |
| Contract status | `READY_FOR_PRP` |
| Source document | `old-system/source/docs/lingxing/OrderProfitListMSKU.md` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-09FE9E838C58` |
| Path | `/basicOpen/finance/mreport/OrderProfit` |
| Method | `POST` |
| Protocol | `HTTPS` |
| Pagination | `offset/length` |
| Page / batch limit | `5000` |
| Rate limit evidence | `1` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-09FE9E838C58 (8 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `currencyCode` | `currencyCode` | `string` | `否` |
| `endDate` | `endDate` | `string` | `是` |
| `length` | `length` | `int` | `否` |
| `offset` | `offset` | `int` | `否` |
| `searchField` | `searchField` | `string` | `否` |
| `searchValue` | `searchValue` | `array` | `否` |
| `sids` | `sids` | `array` | `否` |
| `startDate` | `startDate` | `string` | `是` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-09FE9E838C58 (142 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `array` | `是` |
| `data[].a_to_z_guarantee_claims` | `a_to_z_guarantee_claims` | `string` | `是` |
| `data[].ad_sales_amount` | `ad_sales_amount` | `string` | `是` |
| `data[].ad_sales_amount_sb` | `ad_sales_amount_sb` | `double` | `是` |
| `data[].ad_sales_amount_sbv` | `ad_sales_amount_sbv` | `double` | `是` |
| `data[].ad_sales_amount_sd` | `ad_sales_amount_sd` | `double` | `是` |
| `data[].ad_sales_amount_sp` | `ad_sales_amount_sp` | `double` | `是` |
| `data[].ad_volume` | `ad_volume` | `number` | `是` |
| `data[].ad_volume_sb` | `ad_volume_sb` | `long` | `是` |
| `data[].ad_volume_sbv` | `ad_volume_sbv` | `long` | `是` |
| `data[].ad_volume_sd` | `ad_volume_sd` | `long` | `是` |
| `data[].ad_volume_sp` | `ad_volume_sp` | `long` | `是` |
| `data[].adjustments_fee` | `adjustments_fee` | `string` | `是` |
| `data[].ads_sb_cost` | `ads_sb_cost` | `string` | `是` |
| `data[].ads_sbv_cost` | `ads_sbv_cost` | `string` | `是` |
| `data[].ads_sd_cost` | `ads_sd_cost` | `string` | `是` |
| `data[].ads_sp_cost` | `ads_sp_cost` | `string` | `是` |
| `data[].afn_amount` | `afn_amount` | `double` | `是` |
| `data[].afn_volume` | `afn_volume` | `long` | `是` |
| `data[].amount` | `amount` | `string` | `是` |
| `data[].asins` | `asins` | `array` | `是` |
| `data[].asins.asin` | `asin` | `string` | `是` |
| `data[].asins.asin_url` | `asin_url` | `string` | `是` |
| `data[].avg_gross_profit` | `avg_gross_profit` | `string` | `是` |
| `data[].avg_logistics_costs` | `avg_logistics_costs` | `string` | `是` |
| `data[].avg_net_amount` | `avg_net_amount` | `string` | `是` |
| `data[].avg_other_costs` | `avg_other_costs` | `string` | `是` |
| `data[].avg_purchase_costs` | `avg_purchase_costs` | `string` | `是` |
| `data[].avg_volume` | `avg_volume` | `number` | `是` |
| `data[].brands` | `brands` | `array` | `是` |
| `data[].categories` | `categories` | `array` | `是` |
| `data[].cost_of_points_granted` | `cost_of_points_granted` | `string` | `是` |
| `data[].currency_code` | `currency_code` | `string` | `是` |
| `data[].currency_icon` | `currency_icon` | `string` | `是` |
| `data[].fba_fulfillment_fee` | `fba_fulfillment_fee` | `string` | `是` |
| `data[].fba_storage_fee` | `fba_storage_fee` | `string` | `是` |
| `data[].fulfillment_fee` | `fulfillment_fee` | `string` | `是` |
| `data[].fulfillment_fee_rate` | `fulfillment_fee_rate` | `string` | `是` |
| `data[].gift_wrap_credits` | `gift_wrap_credits` | `string` | `是` |
| `data[].gross_margin` | `gross_margin` | `string` | `是` |
| `data[].gross_profit` | `gross_profit` | `string` | `是` |
| `data[].inventory_credit` | `inventory_credit` | `string` | `是` |
| `data[].is_parent` | `is_parent` | `boolean` | `是` |
| `data[].item_name` | `item_name` | `string` | `是` |
| `data[].local_infos` | `local_infos` | `array` | `是` |
| `data[].local_infos.local_name` | `local_name` | `string` | `是` |
| `data[].local_infos.local_sku` | `local_sku` | `string` | `是` |
| `data[].logistics_costs` | `logistics_costs` | `string` | `是` |
| `data[].long_term_storage_fee` | `long_term_storage_fee` | `string` | `是` |
| `data[].mfn_amount` | `mfn_amount` | `double` | `是` |
| `data[].mfn_volume` | `mfn_volume` | `long` | `是` |
| `data[].multi_channel_volume` | `multi_channel_volume` | `number` | `是` |
| `data[].net_amount` | `net_amount` | `string` | `是` |
| `data[].net_gross_margin` | `net_gross_margin` | `string` | `是` |
| `data[].off_site_promotion_fee` | `off_site_promotion_fee` | `string` | `是` |
| `data[].other_costs` | `other_costs` | `string` | `是` |
| `data[].other_order_fee` | `other_order_fee` | `string` | `是` |
| `data[].parent_asins` | `parent_asins` | `array` | `是` |
| `data[].pm_discount` | `pm_discount` | `double` | `是` |
| `data[].price_list` | `price_list` | `array` | `是` |
| `data[].price_list.asin` | `asin` | `string` | `是` |
| `data[].price_list.brand_title` | `brand_title` | `string` | `是` |
| `data[].price_list.cate_title` | `cate_title` | `string` | `是` |
| `data[].price_list.is_delete` | `is_delete` | `string` | `是` |
| `data[].price_list.item_name` | `item_name` | `string` | `是` |
| `data[].price_list.local_name` | `local_name` | `string` | `是` |
| `data[].price_list.local_sku` | `local_sku` | `string` | `是` |
| `data[].price_list.parent_asin` | `parent_asin` | `string` | `是` |
| `data[].price_list.principal_uids` | `principal_uids` | `string` | `是` |
| `data[].price_list.seller_sku` | `seller_sku` | `string` | `是` |
| `data[].price_list.sid` | `sid` | `string` | `是` |
| `data[].price_list.site_url` | `site_url` | `string` | `是` |
| `data[].price_list.small_main_image_url` | `small_main_image_url` | `string` | `是` |
| `data[].price_list.status` | `status` | `string` | `是` |
| `data[].price_list.volume` | `volume` | `number` | `是` |
| `data[].principal_names` | `principal_names` | `string` | `是` |
| `data[].promotion_discount` | `promotion_discount` | `string` | `是` |
| `data[].promotion_fee` | `promotion_fee` | `string` | `是` |
| `data[].purchase_costs` | `purchase_costs` | `string` | `是` |
| `data[].refund_amount` | `refund_amount` | `string` | `是` |
| `data[].refund_amount_rate` | `refund_amount_rate` | `string` | `是` |
| `data[].refund_quantity` | `refund_quantity` | `string` | `是` |
| `data[].replacement_quantity` | `replacement_quantity` | `number` | `是` |
| `data[].return_quantity` | `return_quantity` | `number` | `是` |
| `data[].return_rate` | `return_rate` | `string` | `是` |
| `data[].seller_store_countries` | `seller_store_countries` | `array` | `是` |
| `data[].seller_store_countries.country` | `country` | `string` | `是` |
| `data[].seller_store_countries.name` | `name` | `string` | `是` |
| `data[].selling_fee` | `selling_fee` | `string` | `是` |
| `data[].selling_fee_rate` | `selling_fee_rate` | `string` | `是` |
| `data[].selling_other_fee` | `selling_other_fee` | `string` | `是` |
| `data[].shared_amazon_partnered_carrier_shipment_fee` | `shared_amazon_partnered_carrier_shipment_fee` | `string` | `是` |
| `data[].shared_amazon_shipping_reimbursement` | `shared_amazon_shipping_reimbursement` | `string` | `是` |
| `data[].shared_awd_processing_fee` | `shared_awd_processing_fee` | `string` | `是` |
| `data[].shared_awd_storage_fee` | `shared_awd_storage_fee` | `string` | `是` |
| `data[].shared_awd_transportation_fee` | `shared_awd_transportation_fee` | `string` | `是` |
| `data[].shared_bubblewrap_fee` | `shared_bubblewrap_fee` | `string` | `是` |
| `data[].shared_clawbacks` | `shared_clawbacks` | `string` | `是` |
| `data[].shared_commingling_vat_income` | `shared_commingling_vat_income` | `string` | `是` |
| `data[].shared_cost_of_advertising` | `shared_cost_of_advertising` | `string` | `是` |
| `data[].shared_fba_customer_return_fee` | `shared_fba_customer_return_fee` | `string` | `是` |
| `data[].shared_fba_disposal_fee` | `shared_fba_disposal_fee` | `string` | `是` |
| `data[].shared_fba_inbound_convenience_fee` | `shared_fba_inbound_convenience_fee` | `string` | `是` |
| `data[].shared_fba_inbound_defect_fee` | `shared_fba_inbound_defect_fee` | `string` | `是` |
| `data[].shared_fba_inbound_transportation_program_fee` | `shared_fba_inbound_transportation_program_fee` | `string` | `是` |
| `data[].shared_fba_international_inbound_fee` | `shared_fba_international_inbound_fee` | `string` | `是` |
| `data[].shared_fba_liquidation_proceeds` | `shared_fba_liquidation_proceeds` | `string` | `是` |
| `data[].shared_fba_liquidation_proceeds_adjustments` | `shared_fba_liquidation_proceeds_adjustments` | `string` | `是` |
| `data[].shared_fba_overage_fee` | `shared_fba_overage_fee` | `string` | `是` |
| `data[].shared_fba_removal_fee` | `shared_fba_removal_fee` | `string` | `是` |
| `data[].shared_fba_storage_fee` | `shared_fba_storage_fee` | `string` | `是` |
| `data[].shared_fba_transaction_customer_return_fee` | `shared_fba_transaction_customer_return_fee` | `string` | `是` |
| `data[].shared_item_fee_adjustment` | `shared_item_fee_adjustment` | `string` | `是` |
| `data[].shared_labeling_fee` | `shared_labeling_fee` | `string` | `是` |
| `data[].shared_long_term_storage_fee` | `shared_long_term_storage_fee` | `string` | `是` |
| `data[].shared_netco_transaction` | `shared_netco_transaction` | `string` | `是` |
| `data[].shared_other_fba_inventory_fees` | `shared_other_fba_inventory_fees` | `string` | `是` |
| `data[].shared_others` | `shared_others` | `string` | `是` |
| `data[].shared_polybagging_fee` | `shared_polybagging_fee` | `string` | `是` |
| `data[].shared_reimbursements` | `shared_reimbursements` | `string` | `是` |
| `data[].shared_safe_t_reimbursement` | `shared_safe_t_reimbursement` | `string` | `是` |
| `data[].shared_star_storage_fee` | `shared_star_storage_fee` | `string` | `是` |
| `data[].shared_storage_renewal_billing` | `shared_storage_renewal_billing` | `string` | `是` |
| `data[].shared_taping_fee` | `shared_taping_fee` | `string` | `是` |
| `data[].shipping_cost` | `shipping_cost` | `string` | `是` |
| `data[].sids` | `sids` | `array` | `是` |
| `data[].small_image_url` | `small_image_url` | `string` | `是` |
| `data[].sp_discount` | `sp_discount` | `double` | `是` |
| `data[].spend` | `spend` | `string` | `是` |
| `data[].spend_rate` | `spend_rate` | `string` | `是` |
| `data[].tax_amount` | `tax_amount` | `string` | `是` |
| `data[].total_costs` | `total_costs` | `string` | `是` |
| `data[].total_other_granted` | `total_other_granted` | `string` | `是` |
| `data[].total_stock_fee` | `total_stock_fee` | `string` | `是` |
| `data[].total_stock_fee_rate` | `total_stock_fee_rate` | `string` | `是` |
| `data[].volume` | `volume` | `number` | `是` |
| `error_details` | `error_details` | `array` | `是` |
| `message` | `message` | `string` | `是` |
| `request_id` | `request_id` | `string` | `是` |
| `response_time` | `response_time` | `string` | `是` |
| `total` | `total` | `int` | `是` |


## Known missing evidence

- provider authentication applicability
- account/data scope
- provider verification


## Safety decision

Contract shape is repository-derived and unverified; no real call is authorized. `READY_FOR_PRP` permits only a future evidence-backed PRP; it does not approve provider traffic, implementation, data writes, or production use. Deleted, non-Walmart, or side-effecting entries require separate Owner re-evaluation.

## Redacted request shape

```json
{
  "currencyCode": "<redacted>",
  "endDate": "<redacted>",
  "length": "<redacted>",
  "offset": "<redacted>",
  "searchField": "<redacted>",
  "searchValue": "<redacted>",
  "sids": "<redacted>",
  "startDate": "<redacted>"
}
```

## Redacted response shape

```json
{
  "code": "<redacted>",
  "data": "<redacted>",
  "error_details": "<redacted>",
  "message": "<redacted>",
  "request_id": "<redacted>",
  "response_time": "<redacted>",
  "total": "<redacted>"
}
```

Only field names are shown. No real identifier, product value, URL, credential, or response content is included.

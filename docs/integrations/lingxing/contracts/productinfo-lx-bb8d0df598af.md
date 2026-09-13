# 批量查询本地产品详情 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-BB8D0DF598AF` |
| Contract status | `READY_FOR_PRP` |
| Source document | `old-system/source/docs/lingxing/batchGetProductInfo.md` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-BB8D0DF598AF` |
| Path | `/erp/sc/routing/data/local_inventory/batchGetProductInfo` |
| Method | `POST` |
| Protocol | `HTTPS` |
| Pagination | `无` |
| Page / batch limit | `unknown` |
| Rate limit evidence | `1` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-BB8D0DF598AF (3 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `productIds` | `productIds` | `array` | `否` |
| `sku_identifiers` | `sku_identifiers` | `array` | `否` |
| `skus` | `skus` | `array` | `否` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-BB8D0DF598AF (124 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `aux_relation_list` | `aux_relation_list` | `array` | `是` |
| `aux_relation_list[].aux_qty` | `aux_qty` | `string` | `是` |
| `aux_relation_list[].aux_sku` | `aux_sku` | `string` | `是` |
| `aux_relation_list[].sku_qty` | `sku_qty` | `string` | `是` |
| `code` | `code` | `int` | `是` |
| `data` | `data` | `array` | `是` |
| `data[].attachment_id` | `attachment_id` | `array` | `是` |
| `data[].bg_customs_export_name` | `bg_customs_export_name` | `string` | `是` |
| `data[].bg_customs_import_name` | `bg_customs_import_name` | `string` | `是` |
| `data[].bg_customs_import_price` | `bg_customs_import_price` | `number` | `是` |
| `data[].bg_export_hs_code` | `bg_export_hs_code` | `string` | `是` |
| `data[].bg_import_hs_code` | `bg_import_hs_code` | `string` | `是` |
| `data[].bg_tax_rate` | `bg_tax_rate` | `number` | `是` |
| `data[].bid` | `bid` | `int` | `是` |
| `data[].brand_name` | `brand_name` | `string` | `是` |
| `data[].category_name` | `category_name` | `string` | `是` |
| `data[].cg_box_height` | `cg_box_height` | `number` | `是` |
| `data[].cg_box_length` | `cg_box_length` | `number` | `是` |
| `data[].cg_box_pcs` | `cg_box_pcs` | `int` | `是` |
| `data[].cg_box_weight` | `cg_box_weight` | `number` | `是` |
| `data[].cg_box_width` | `cg_box_width` | `number` | `是` |
| `data[].cg_delivery` | `cg_delivery` | `int` | `是` |
| `data[].cg_opt_username` | `cg_opt_username` | `string` | `是` |
| `data[].cg_package_height` | `cg_package_height` | `number` | `是` |
| `data[].cg_package_length` | `cg_package_length` | `number` | `是` |
| `data[].cg_package_width` | `cg_package_width` | `number` | `是` |
| `data[].cg_price` | `cg_price` | `number` | `是` |
| `data[].cg_product_gross_weight` | `cg_product_gross_weight` | `number` | `是` |
| `data[].cg_product_height` | `cg_product_height` | `number` | `是` |
| `data[].cg_product_length` | `cg_product_length` | `number` | `是` |
| `data[].cg_product_material` | `cg_product_material` | `string` | `是` |
| `data[].cg_product_net_weight` | `cg_product_net_weight` | `number` | `是` |
| `data[].cg_product_width` | `cg_product_width` | `number` | `是` |
| `data[].cid` | `cid` | `int` | `是` |
| `data[].clearance` | `clearance` | `object` | `是` |
| `data[].clearance.allocation_remark` | `allocation_remark` | `string` | `是` |
| `data[].clearance.customs_clearance_brand_type` | `customs_clearance_brand_type` | `int` | `是` |
| `data[].clearance.customs_clearance_en_material` | `customs_clearance_en_material` | `string` | `否` |
| `data[].clearance.customs_clearance_hs_code` | `customs_clearance_hs_code` | `string` | `是` |
| `data[].clearance.customs_clearance_internal_code` | `customs_clearance_internal_code` | `string` | `是` |
| `data[].clearance.customs_clearance_material` | `customs_clearance_material` | `string` | `是` |
| `data[].clearance.customs_clearance_pic_url` | `customs_clearance_pic_url` | `string` | `是` |
| `data[].clearance.customs_clearance_preferential` | `customs_clearance_preferential` | `int` | `是` |
| `data[].clearance.customs_clearance_price` | `customs_clearance_price` | `float` | `是` |
| `data[].clearance.customs_clearance_price_currency` | `customs_clearance_price_currency` | `string` | `是` |
| `data[].clearance.customs_clearance_product_pattern` | `customs_clearance_product_pattern` | `string` | `是` |
| `data[].clearance.customs_clearance_remark` | `customs_clearance_remark` | `string` | `是` |
| `data[].clearance.customs_clearance_tax_rate` | `customs_clearance_tax_rate` | `string` | `是` |
| `data[].clearance.customs_clearance_usage` | `customs_clearance_usage` | `string` | `是` |
| `data[].clearance.weaving_mode` | `weaving_mode` | `int` | `是` |
| `data[].combo_product_list` | `combo_product_list` | `array` | `是` |
| `data[].combo_product_list.product_id` | `product_id` | `int` | `是` |
| `data[].combo_product_list.quantity` | `quantity` | `int` | `是` |
| `data[].combo_product_list.sku` | `sku` | `string` | `是` |
| `data[].currency` | `currency` | `string` | `是` |
| `data[].custom_fields` | `custom_fields` | `array` | `是` |
| `data[].custom_fields.id` | `id` | `string` | `是` |
| `data[].custom_fields.name` | `name` | `string` | `是` |
| `data[].custom_fields.val_text` | `val_text` | `string` | `是` |
| `data[].declaration` | `declaration` | `object` | `是` |
| `data[].declaration.customs_declaration_exempt` | `customs_declaration_exempt` | `string` | `是` |
| `data[].declaration.customs_declaration_inlands_source` | `customs_declaration_inlands_source` | `string` | `是` |
| `data[].declaration.customs_declaration_origin_produce` | `customs_declaration_origin_produce` | `string` | `是` |
| `data[].declaration.customs_declaration_spec` | `customs_declaration_spec` | `string` | `是` |
| `data[].declaration.customs_declaration_unit` | `customs_declaration_unit` | `string` | `是` |
| `data[].declaration.other_declare_element` | `other_declare_element` | `string` | `是` |
| `data[].declaration.production_and_sales_enterprise_code` | `production_and_sales_enterprise_code` | `string` | `是` |
| `data[].declaration.production_and_sales_enterprise_name` | `production_and_sales_enterprise_name` | `string` | `是` |
| `data[].description` | `description` | `string` | `是` |
| `data[].global_tags` | `global_tags` | `array` | `是` |
| `data[].global_tags.color` | `color` | `string` | `是` |
| `data[].global_tags.global_tag_id` | `global_tag_id` | `string` | `是` |
| `data[].global_tags.tag_name` | `tag_name` | `string` | `是` |
| `data[].id` | `id` | `int` | `是` |
| `data[].is_combo` | `is_combo` | `int` | `是` |
| `data[].model` | `model` | `string` | `是` |
| `data[].permission_user_info` | `permission_user_info` | `array` | `是` |
| `data[].permission_user_info.permission_uid` | `permission_uid` | `int` | `是` |
| `data[].permission_user_info.permission_user_name` | `permission_user_name` | `string` | `是` |
| `data[].pic_url` | `pic_url` | `string` | `是` |
| `data[].picture_list` | `picture_list` | `array` | `是` |
| `data[].picture_list.is_primary` | `is_primary` | `int` | `是` |
| `data[].picture_list.pic_url` | `pic_url` | `string` | `是` |
| `data[].product_developer` | `product_developer` | `string` | `是` |
| `data[].product_developer_uid` | `product_developer_uid` | `int` | `是` |
| `data[].product_logistics_relation` | `product_logistics_relation` | `array` | `是` |
| `data[].product_logistics_relation.XX_bg_import_hs_code` | `XX_bg_import_hs_code` | `string` | `是` |
| `data[].product_logistics_relation.XX_bg_tax_rate` | `XX_bg_tax_rate` | `number` | `是` |
| `data[].product_logistics_relation.XX_cg_transport_costs` | `XX_cg_transport_costs` | `number` | `是` |
| `data[].product_logistics_relation.XX_clearance_price` | `XX_clearance_price` | `number` | `是` |
| `data[].product_logistics_relation.XX_clearance_price_currency` | `XX_clearance_price_currency` | `string` | `是` |
| `data[].product_logistics_relation.XX_currency` | `XX_currency` | `string` | `是` |
| `data[].product_name` | `product_name` | `string` | `是` |
| `data[].purchase_remark` | `purchase_remark` | `string` | `是` |
| `data[].qc_standard` | `qc_standard` | `object` | `是` |
| `data[].qc_standard.custom_qc_template` | `custom_qc_template` | `object` | `是` |
| `data[].qc_standard.custom_qc_template.qc_image` | `qc_image` | `object` | `是` |
| `data[].qc_standard.custom_qc_template.qc_image.customer_url` | `customer_url` | `string` | `是` |
| `data[].qc_standard.custom_qc_template.qc_image.file_id` | `file_id` | `int` | `是` |
| `data[].sku` | `sku` | `string` | `是` |
| `data[].special_attr` | `special_attr` | `array` | `是` |
| `data[].status` | `status` | `int` | `是` |
| `data[].supplier_quote` | `supplier_quote` | `array` | `是` |
| `data[].supplier_quote.is_primary` | `is_primary` | `int` | `是` |
| `data[].supplier_quote.product_id` | `product_id` | `int` | `是` |
| `data[].supplier_quote.psq_id` | `psq_id` | `string` | `是` |
| `data[].supplier_quote.quote_remark` | `quote_remark` | `string` | `是` |
| `data[].supplier_quote.quotes` | `quotes` | `array` | `是` |
| `data[].supplier_quote.quotes.currency` | `currency` | `string` | `是` |
| `data[].supplier_quote.quotes.currency_icon` | `currency_icon` | `string` | `是` |
| `data[].supplier_quote.quotes.is_tax` | `is_tax` | `int` | `是` |
| `data[].supplier_quote.quotes.step_prices` | `step_prices` | `array` | `是` |
| `data[].supplier_quote.quotes.step_prices.moq` | `moq` | `int` | `是` |
| `data[].supplier_quote.quotes.step_prices.price` | `price` | `number` | `是` |
| `data[].supplier_quote.quotes.step_prices.price_with_tax` | `price_with_tax` | `number` | `是` |
| `data[].supplier_quote.quotes.tax_rate` | `tax_rate` | `number` | `是` |
| `data[].supplier_quote.supplier_id` | `supplier_id` | `int` | `是` |
| `data[].supplier_quote.supplier_name` | `supplier_name` | `string` | `是` |
| `data[].supplier_quote.supplier_product_url` | `supplier_product_url` | `array` | `是` |
| `data[].unit` | `unit` | `string` | `是` |
| `error_details` | `error_details` | `array` | `是` |
| `message` | `message` | `string` | `是` |
| `request_id` | `request_id` | `string` | `是` |
| `response_time` | `response_time` | `string` | `是` |


## Known missing evidence

- provider authentication applicability
- account/data scope
- provider verification


## Safety decision

Contract shape is repository-derived and unverified; no real call is authorized. `READY_FOR_PRP` permits only a future evidence-backed PRP; it does not approve provider traffic, implementation, data writes, or production use. Deleted, non-Walmart, or side-effecting entries require separate Owner re-evaluation.

## Redacted request shape

```json
{
  "productIds": "<redacted>",
  "sku_identifiers": "<redacted>",
  "skus": "<redacted>"
}
```

## Redacted response shape

```json
{
  "aux_relation_list": "<redacted>",
  "code": "<redacted>",
  "data": "<redacted>",
  "error_details": "<redacted>",
  "message": "<redacted>",
  "request_id": "<redacted>",
  "response_time": "<redacted>"
}
```

Only field names are shown. No real identifier, product value, URL, credential, or response content is included.

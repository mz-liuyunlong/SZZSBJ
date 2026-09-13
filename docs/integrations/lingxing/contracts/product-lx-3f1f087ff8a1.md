# 查询本地产品列表 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-3F1F087FF8A1` |
| Contract status | `READY_FOR_PRP` |
| Source document | `old-system/source/docs/lingxing/ProductLists.md` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-3F1F087FF8A1` |
| Path | `/erp/sc/routing/data/local_inventory/productList` |
| Method | `POST` |
| Protocol | `HTTPS` |
| Pagination | `offset/length` |
| Page / batch limit | `1000` |
| Rate limit evidence | `1` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-3F1F087FF8A1 (8 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `create_time_end` | `create_time_end` | `int` | `否` |
| `create_time_start` | `create_time_start` | `int` | `否` |
| `length` | `length` | `int` | `否` |
| `offset` | `offset` | `int` | `否` |
| `sku_identifier_list` | `sku_identifier_list` | `array` | `否` |
| `sku_list` | `sku_list` | `array` | `否` |
| `update_time_end` | `update_time_end` | `int` | `否` |
| `update_time_start` | `update_time_start` | `int` | `否` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-3F1F087FF8A1 (67 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `array` | `是` |
| `data[].attribute` | `attribute` | `array` | `是` |
| `data[].attribute.attr_id` | `attr_id` | `string` | `是` |
| `data[].attribute.attr_name` | `attr_name` | `string` | `是` |
| `data[].attribute.attr_value` | `attr_value` | `string` | `是` |
| `data[].bid` | `bid` | `int` | `是` |
| `data[].brand_name` | `brand_name` | `string` | `是` |
| `data[].category_name` | `category_name` | `string` | `是` |
| `data[].cg_delivery` | `cg_delivery` | `int` | `是` |
| `data[].cg_opt_uid` | `cg_opt_uid` | `string` | `是` |
| `data[].cg_opt_username` | `cg_opt_username` | `string` | `是` |
| `data[].cg_price` | `cg_price` | `number` | `是` |
| `data[].cg_transport_costs` | `cg_transport_costs` | `number` | `是` |
| `data[].cid` | `cid` | `int` | `是` |
| `data[].create_time` | `create_time` | `int` | `是` |
| `data[].custom_fields` | `custom_fields` | `array` | `是` |
| `data[].custom_fields.id` | `id` | `string` | `是` |
| `data[].custom_fields.name` | `name` | `string` | `是` |
| `data[].custom_fields.val_text` | `val_text` | `string` | `是` |
| `data[].global_tags` | `global_tags` | `array` | `是` |
| `data[].global_tags.color` | `color` | `string` | `是` |
| `data[].global_tags.global_tag_id` | `global_tag_id` | `string` | `是` |
| `data[].global_tags.tag_name` | `tag_name` | `string` | `是` |
| `data[].id` | `id` | `int` | `是` |
| `data[].is_combo` | `is_combo` | `int` | `是` |
| `data[].open_status` | `open_status` | `int` | `否` |
| `data[].pic_url` | `pic_url` | `string` | `是` |
| `data[].product_developer` | `product_developer` | `string` | `是` |
| `data[].product_developer_uid` | `product_developer_uid` | `string` | `是` |
| `data[].product_name` | `product_name` | `string` | `是` |
| `data[].ps_id` | `ps_id` | `int` | `是` |
| `data[].purchase_remark` | `purchase_remark` | `string` | `是` |
| `data[].sku` | `sku` | `string` | `是` |
| `data[].sku_identifier` | `sku_identifier` | `string` | `是` |
| `data[].spu` | `spu` | `string` | `是` |
| `data[].status` | `status` | `int` | `是` |
| `data[].status_text` | `status_text` | `string` | `是` |
| `data[].supplier_quote` | `supplier_quote` | `array` | `是` |
| `data[].supplier_quote.cg_currency_icon` | `cg_currency_icon` | `string` | `是` |
| `data[].supplier_quote.cg_price` | `cg_price` | `string` | `是` |
| `data[].supplier_quote.employees_text` | `employees_text` | `string` | `是` |
| `data[].supplier_quote.is_primary` | `is_primary` | `int` | `是` |
| `data[].supplier_quote.level_text` | `level_text` | `string` | `是` |
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
| `data[].supplier_quote.remark` | `remark` | `string` | `是` |
| `data[].supplier_quote.supplier_code` | `supplier_code` | `string` | `是` |
| `data[].supplier_quote.supplier_id` | `supplier_id` | `int` | `是` |
| `data[].supplier_quote.supplier_name` | `supplier_name` | `string` | `是` |
| `data[].supplier_quote.supplier_product_url` | `supplier_product_url` | `array` | `是` |
| `data[].update_time` | `update_time` | `int` | `是` |
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
  "create_time_end": "<redacted>",
  "create_time_start": "<redacted>",
  "length": "<redacted>",
  "offset": "<redacted>",
  "sku_identifier_list": "<redacted>",
  "sku_list": "<redacted>",
  "update_time_end": "<redacted>",
  "update_time_start": "<redacted>"
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

# 查询WFS库存列表 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-531E7CE81EF4` |
| Contract status | `READY_FOR_PRP` |
| Source document | `No matching legacy Markdown; normalized CSV only` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-531E7CE81EF4` |
| Path | `/cepf/warehouse/api/openApi/queryWFSInventionPage` |
| Method | `POST` |
| Protocol | `UNVERIFIED` |
| Pagination | `offset/length` |
| Page / batch limit | `200` |
| Rate limit evidence | `10` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-531E7CE81EF4 (3 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `length` | `length` | `int` | `否` |
| `offset` | `offset` | `int` | `否` |
| `store_id` | `store_id` | `array` | `是` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-531E7CE81EF4 (32 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `object` | `是` |
| `data.records` | `records` | `array` | `是` |
| `data.records[].ats03_months` | `ats03_months` | `string` | `是` |
| `data.records[].ats1_years` | `ats1_years` | `string` | `是` |
| `data.records[].ats36_months` | `ats36_months` | `string` | `是` |
| `data.records[].ats69_months` | `ats69_months` | `string` | `是` |
| `data.records[].ats912_months` | `ats912_months` | `string` | `是` |
| `data.records[].available_quantity` | `available_quantity` | `string` | `是` |
| `data.records[].available_quantity_v2` | `available_quantity_v2` | `string` | `是` |
| `data.records[].gtin` | `gtin` | `string` | `是` |
| `data.records[].inbound_quantity` | `inbound_quantity` | `string` | `是` |
| `data.records[].item_id` | `item_id` | `string` | `是` |
| `data.records[].last30_days_po_units` | `last30_days_po_units` | `string` | `是` |
| `data.records[].last30_days_units_received` | `last30_days_units_received` | `string` | `是` |
| `data.records[].msku` | `msku` | `string` | `是` |
| `data.records[].pic_url` | `pic_url` | `string` | `是` |
| `data.records[].pid` | `pid` | `string` | `是` |
| `data.records[].platform_product_status` | `platform_product_status` | `string` | `是` |
| `data.records[].product_name` | `product_name` | `string` | `是` |
| `data.records[].quantity` | `quantity` | `string` | `是` |
| `data.records[].sku` | `sku` | `string` | `是` |
| `data.records[].store_id` | `store_id` | `string` | `是` |
| `data.records[].store_name` | `store_name` | `string` | `是` |
| `data.records[].unabled_warehousing_quantity` | `unabled_warehousing_quantity` | `string` | `是` |
| `data.records[].warehouse_name` | `warehouse_name` | `string` | `是` |
| `data.records[].warehouse_unique_id` | `warehouse_unique_id` | `string` | `是` |
| `data.total` | `total` | `string` | `是` |
| `error_details` | `error_details` | `array` | `是` |
| `message` | `message` | `string` | `是` |
| `request_id` | `request_id` | `string` | `是` |
| `response_time` | `response_time` | `string` | `是` |


## Known missing evidence

- endpoint-specific protocol evidence
- provider authentication applicability
- account/data scope
- provider verification


## Safety decision

Contract shape is repository-derived and unverified; no real call is authorized. `READY_FOR_PRP` permits only a future evidence-backed PRP; it does not approve provider traffic, implementation, data writes, or production use. Deleted, non-Walmart, or side-effecting entries require separate Owner re-evaluation.

## Redacted request shape

```json
{
  "length": "<redacted>",
  "offset": "<redacted>",
  "store_id": "<redacted>"
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
  "response_time": "<redacted>"
}
```

Only field names are shown. No real identifier, product value, URL, credential, or response content is included.

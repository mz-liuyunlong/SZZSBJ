# 查询报告详情 - Walmart Payment — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-66894A74C546` |
| Contract status | `READY_FOR_PRP` |
| Source document | `No matching legacy Markdown; normalized CSV only` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-66894A74C546` |
| Path | `/cepf/fms/openapi/walmartPayment/queryPage` |
| Method | `POST` |
| Protocol | `UNVERIFIED` |
| Pagination | `offset/length` |
| Page / batch limit | `200` |
| Rate limit evidence | `10` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-66894A74C546 (6 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `length` | `length` | `int` | `否` |
| `offset` | `offset` | `int` | `否` |
| `report_id` | `report_id` | `string` | `否` |
| `store_id` | `store_id` | `array` | `是` |
| `transaction_posted_timestamp_end` | `transaction_posted_timestamp_end` | `string` | `否` |
| `transaction_posted_timestamp_start` | `transaction_posted_timestamp_start` | `string` | `否` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-66894A74C546 (36 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `object` | `是` |
| `data.records` | `records` | `array` | `是` |
| `data.records[].amount` | `amount` | `string` | `是` |
| `data.records[].amount_type` | `amount_type` | `string` | `是` |
| `data.records[].commission_rate` | `commission_rate` | `string` | `是` |
| `data.records[].commission_rate_str` | `commission_rate_str` | `string` | `是` |
| `data.records[].commission_rule` | `commission_rule` | `string` | `是` |
| `data.records[].currency` | `currency` | `string` | `是` |
| `data.records[].customer_order` | `customer_order` | `string` | `是` |
| `data.records[].fulfillment_type` | `fulfillment_type` | `string` | `是` |
| `data.records[].msku` | `msku` | `string` | `是` |
| `data.records[].partner_gtin` | `partner_gtin` | `string` | `是` |
| `data.records[].partner_item_name` | `partner_item_name` | `string` | `是` |
| `data.records[].period_end_date` | `period_end_date` | `string` | `是` |
| `data.records[].period_start_date` | `period_start_date` | `string` | `是` |
| `data.records[].product_taxCode` | `product_taxCode` | `string` | `是` |
| `data.records[].product_type` | `product_type` | `string` | `是` |
| `data.records[].purchase_order` | `purchase_order` | `string` | `是` |
| `data.records[].ship_qty` | `ship_qty` | `int` | `是` |
| `data.records[].ship_to_city` | `ship_to_city` | `string` | `是` |
| `data.records[].ship_to_state` | `ship_to_state` | `string` | `是` |
| `data.records[].ship_to_zipcode` | `ship_to_zipcode` | `string` | `是` |
| `data.records[].shipping_method` | `shipping_method` | `string` | `是` |
| `data.records[].store_id` | `store_id` | `string` | `是` |
| `data.records[].store_name` | `store_name` | `string` | `是` |
| `data.records[].transaction_description` | `transaction_description` | `string` | `是` |
| `data.records[].transaction_key` | `transaction_key` | `string` | `是` |
| `data.records[].transaction_posted_timestamp` | `transaction_posted_timestamp` | `string` | `是` |
| `data.records[].transaction_reason_description` | `transaction_reason_description` | `string` | `是` |
| `data.records[].transaction_type` | `transaction_type` | `string` | `是` |
| `data.total` | `total` | `int` | `是` |
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
  "report_id": "<redacted>",
  "store_id": "<redacted>",
  "transaction_posted_timestamp_end": "<redacted>",
  "transaction_posted_timestamp_start": "<redacted>"
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

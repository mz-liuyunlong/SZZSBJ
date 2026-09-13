# 查询WFS货件列表 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-C95DBD64F2A9` |
| Contract status | `READY_FOR_PRP` |
| Source document | `No matching legacy Markdown; normalized CSV only` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-C95DBD64F2A9` |
| Path | `/cepf/warehouse/api/openApi/queryWFSCargoPage` |
| Method | `POST` |
| Protocol | `UNVERIFIED` |
| Pagination | `offset/length` |
| Page / batch limit | `200` |
| Rate limit evidence | `10` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-C95DBD64F2A9 (11 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `cargo_status_list` | `cargo_status_list` | `array` | `否` |
| `cargo_update_time_ge` | `cargo_update_time_ge` | `string` | `否` |
| `cargo_update_time_le` | `cargo_update_time_le` | `string` | `否` |
| `end_time` | `end_time` | `string` | `否` |
| `inbound_order_id` | `inbound_order_id` | `string` | `否` |
| `length` | `length` | `int` | `否` |
| `offset` | `offset` | `int` | `否` |
| `start_time` | `start_time` | `string` | `否` |
| `store_id` | `store_id` | `array` | `否` |
| `update_time_ge` | `update_time_ge` | `string` | `否` |
| `update_time_le` | `update_time_le` | `string` | `否` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-C95DBD64F2A9 (39 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `object` | `是` |
| `data.records` | `records` | `array` | `是` |
| `data.records[].cargo_code` | `cargo_code` | `string` | `是` |
| `data.records[].cargo_create_date` | `cargo_create_date` | `string` | `是` |
| `data.records[].cargo_good_list` | `cargo_good_list` | `array` | `是` |
| `data.records[].cargo_good_list.dameged_qty` | `dameged_qty` | `string` | `是` |
| `data.records[].cargo_good_list.declare_num` | `declare_num` | `string` | `是` |
| `data.records[].cargo_good_list.gtin` | `gtin` | `string` | `是` |
| `data.records[].cargo_good_list.msku` | `msku` | `string` | `是` |
| `data.records[].cargo_good_list.product_name` | `product_name` | `string` | `是` |
| `data.records[].cargo_good_list.received_num` | `received_num` | `string` | `是` |
| `data.records[].cargo_good_list.shipments_num` | `shipments_num` | `string` | `是` |
| `data.records[].cargo_good_list.sku` | `sku` | `string` | `是` |
| `data.records[].cargo_status` | `cargo_status` | `string` | `是` |
| `data.records[].cargo_sync_status` | `cargo_sync_status` | `string` | `是` |
| `data.records[].country_name` | `country_name` | `string` | `是` |
| `data.records[].creator` | `creator` | `string` | `是` |
| `data.records[].distribution_addresses` | `distribution_addresses` | `string` | `是` |
| `data.records[].id` | `id` | `string` | `是` |
| `data.records[].in_bound_order_id` | `in_bound_order_id` | `string` | `是` |
| `data.records[].logistics_code` | `logistics_code` | `string` | `是` |
| `data.records[].return_addresses` | `return_addresses` | `string` | `是` |
| `data.records[].shipping_list_codes` | `shipping_list_codes` | `array` | `是` |
| `data.records[].status` | `status` | `int` | `是` |
| `data.records[].status_name` | `status_name` | `string` | `是` |
| `data.records[].store_id` | `store_id` | `string` | `是` |
| `data.records[].store_name` | `store_name` | `string` | `是` |
| `data.records[].to_await_time` | `to_await_time` | `string` | `是` |
| `data.records[].to_cancelled_time` | `to_cancelled_time` | `string` | `是` |
| `data.records[].to_closed_time` | `to_closed_time` | `string` | `是` |
| `data.records[].to_pending_time` | `to_pending_time` | `string` | `是` |
| `data.records[].to_receive_time` | `to_receive_time` | `string` | `是` |
| `data.records[].update_date` | `update_date` | `string` | `是` |
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
  "cargo_status_list": "<redacted>",
  "cargo_update_time_ge": "<redacted>",
  "cargo_update_time_le": "<redacted>",
  "end_time": "<redacted>",
  "inbound_order_id": "<redacted>",
  "length": "<redacted>",
  "offset": "<redacted>",
  "start_time": "<redacted>"
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

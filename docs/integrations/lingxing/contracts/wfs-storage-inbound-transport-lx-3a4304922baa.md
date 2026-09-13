# WFS货件暂存 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-3A4304922BAA` |
| Contract status | `DO_NOT_USE` |
| Source document | `No matching legacy Markdown; normalized CSV only` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-3A4304922BAA` |
| Path | `/basicOpen/multiplatform/cargo/storage` |
| Method | `POST` |
| Protocol | `UNVERIFIED` |
| Pagination | `无` |
| Page / batch limit | `unknown` |
| Rate limit evidence | `1` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `no` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-3A4304922BAA (27 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `cargo_goods_list` | `cargo_goods_list` | `array` | `是` |
| `cargo_goods_list[].box_num` | `box_num` | `string` | `是` |
| `cargo_goods_list[].declare_num` | `declare_num` | `string` | `是` |
| `cargo_goods_list[].expected_arrival_time` | `expected_arrival_time` | `string` | `是` |
| `cargo_goods_list[].gtin` | `gtin` | `string` | `是` |
| `cargo_goods_list[].msku` | `msku` | `string` | `是` |
| `cargo_goods_list[].picture_url` | `picture_url` | `string` | `是` |
| `cargo_goods_list[].product_desc` | `product_desc` | `string` | `是` |
| `cargo_goods_list[].product_id` | `product_id` | `string` | `是` |
| `cargo_goods_list[].product_name` | `product_name` | `string` | `是` |
| `cargo_goods_list[].product_type` | `product_type` | `string` | `是` |
| `cargo_goods_list[].single_box_num` | `single_box_num` | `string` | `是` |
| `cargo_goods_list[].sku` | `sku` | `string` | `是` |
| `cargo_goods_list[].value_added_service` | `value_added_service` | `string` | `是` |
| `cargo_remark` | `cargo_remark` | `string` | `否` |
| `inbound_order_id` | `inbound_order_id` | `string` | `否` |
| `return_address` | `return_address` | `object` | `是` |
| `return_address.address_alias` | `address_alias` | `string` | `是` |
| `return_address.address_id` | `address_id` | `string` | `是` |
| `return_address.city` | `city` | `string` | `是` |
| `return_address.mobile` | `mobile` | `string` | `是` |
| `return_address.postal_code` | `postal_code` | `string` | `是` |
| `return_address.province` | `province` | `string` | `是` |
| `return_address.receive_or_delivery_country` | `receive_or_delivery_country` | `string` | `是` |
| `return_address.receive_or_delivery_country_name` | `receive_or_delivery_country_name` | `string` | `是` |
| `return_address.street_detail` | `street_detail` | `string` | `是` |
| `store_id` | `store_id` | `string` | `是` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-3A4304922BAA (8 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `object` | `是` |
| `data.inbound_order_id` | `inbound_order_id` | `string` | `是` |
| `error_details` | `error_details` | `array` | `是` |
| `message` | `message` | `string` | `是` |
| `request_id` | `request_id` | `string` | `是` |
| `response_time` | `response_time` | `string` | `是` |
| `total` | `total` | `int` | `是` |


## Known missing evidence

- endpoint-specific protocol evidence
- provider authentication applicability
- account/data scope
- provider verification


## Safety decision

Current classification is excluded or incomplete. `READY_FOR_PRP` permits only a future evidence-backed PRP; it does not approve provider traffic, implementation, data writes, or production use. Deleted, non-Walmart, or side-effecting entries require separate Owner re-evaluation.

## Redacted request shape

```json
{
  "cargo_goods_list": "<redacted>",
  "cargo_remark": "<redacted>",
  "inbound_order_id": "<redacted>",
  "return_address": "<redacted>",
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
  "response_time": "<redacted>",
  "total": "<redacted>"
}
```

Only field names are shown. No real identifier, product value, URL, credential, or response content is included.

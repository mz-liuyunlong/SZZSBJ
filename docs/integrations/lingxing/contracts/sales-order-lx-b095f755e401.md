# 查询亚马逊订单列表 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-B095F755E401` |
| Contract status | `DELETED` |
| Source document | `old-system/source/docs/lingxing/Orderlists.md` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/deleted_interfaces.csv#LX-B095F755E401` |
| Path | `/erp/sc/data/mws/orders` |
| Method | `POST` |
| Protocol | `HTTPS` |
| Pagination | `offset/length` |
| Page / batch limit | `5000` |
| Rate limit evidence | `1` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `no` |

## Request parameters

Source: `old-system/source/docs/lingxing/Orderlists.md#请求参数 (10 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `sid` | `sid` | `int` | `否` |
| `sid_list` | `sid_list` | `array` | `否` |
| `start_date` | `start_date` | `string` | `是` |
| `end_date` | `end_date` | `string` | `是` |
| `date_type` | `date_type` | `int` | `否` |
| `order_status` | `order_status` | `array` | `否` |
| `sort_desc_by_date_type` | `sort_desc_by_date_type` | `int` | `否` |
| `fulfillment_channel` | `fulfillment_channel` | `int` | `否` |
| `offset` | `offset` | `int` | `否` |
| `length` | `length` | `int` | `否` |


## Response fields

Source: `old-system/source/docs/lingxing/Orderlists.md#返回结果 (45 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `message` | `message` | `string` | `是` |
| `error_details` | `error_details` | `array` | `是` |
| `request_id` | `request_id` | `string` | `是` |
| `response_time` | `response_time` | `string` | `是` |
| `total` | `total` | `int` | `是` |
| `data` | `data` | `array` | `是` |
| `data>>sid` | `data>>sid` | `string` | `是` |
| `data>>seller_name` | `data>>seller_name` | `string` | `是` |
| `data>>amazon_order_id` | `data>>amazon_order_id` | `string` | `是` |
| `data>>order_status` | `data>>order_status` | `string` | `是` |
| `data>>order_total_amount` | `data>>order_total_amount` | `string` | `是` |
| `data>>fulfillment_channel` | `data>>fulfillment_channel` | `string` | `是` |
| `data>>postal_code` | `data>>postal_code` | `string` | `是` |
| `data>>is_return` | `data>>is_return` | `int` | `是` |
| `data>>is_mcf_order` | `data>>is_mcf_order` | `int` | `是` |
| `data>>is_assessed` | `data>>is_assessed` | `int` | `是` |
| `data>>is_replaced_order` | `data>>is_replaced_order` | `int` | `是` |
| `data>>is_replacement_order` | `data>>is_replacement_order` | `int` | `是` |
| `data>>is_return_order` | `data>>is_return_order` | `int` | `是` |
| `data>>order_total_currency_code` | `data>>order_total_currency_code` | `string` | `是` |
| `data>>sales_channel` | `data>>sales_channel` | `string` | `是` |
| `data>>tracking_number` | `data>>tracking_number` | `string` | `是` |
| `data>>refund_amount` | `data>>refund_amount` | `number` | `是` |
| `data>>item_list` | `data>>item_list` | `array` | `是` |
| `data>>item_list>>asin` | `data>>item_list>>asin` | `string` | `是` |
| `data>>item_list>>quantity_ordered` | `data>>item_list>>quantity_ordered` | `string` | `是` |
| `data>>item_list>>seller_sku` | `data>>item_list>>seller_sku` | `string` | `是` |
| `data>>item_list>>local_sku` | `data>>item_list>>local_sku` | `string` | `是` |
| `data>>item_list>>local_name` | `data>>item_list>>local_name` | `string` | `是` |
| `data>>purchase_date_local` | `data>>purchase_date_local` | `string` | `是` |
| `data>>purchase_date_local_utc` | `data>>purchase_date_local_utc` | `string` | `是` |
| `data>>shipment_date` | `data>>shipment_date` | `string` | `是` |
| `data>>shipment_date_utc` | `data>>shipment_date_utc` | `string` | `是` |
| `data>>shipment_date_local` | `data>>shipment_date_local` | `string` | `是` |
| `data>>last_update_date` | `data>>last_update_date` | `string` | `是` |
| `data>>last_update_date_utc` | `data>>last_update_date_utc` | `string` | `是` |
| `data>>posted_date` | `data>>posted_date` | `string` | `是` |
| `data>>posted_date_utc` | `data>>posted_date_utc` | `string` | `是` |
| `data>>purchase_date` | `data>>purchase_date` | `string` | `是` |
| `data>>purchase_date_utc` | `data>>purchase_date_utc` | `string` | `是` |
| `data>>earliest_ship_date` | `data>>earliest_ship_date` | `string` | `是` |
| `data>>earliest_ship_date_utc` | `data>>earliest_ship_date_utc` | `string` | `是` |
| `data>>gmt_modified` | `data>>gmt_modified` | `string` | `是` |
| `data>>gmt_modified_utc` | `data>>gmt_modified_utc` | `string` | `是` |


## Known missing evidence

- provider authentication applicability
- account/data scope
- provider verification


## Safety decision

Current classification is excluded or incomplete. `READY_FOR_PRP` permits only a future evidence-backed PRP; it does not approve provider traffic, implementation, data writes, or production use. Deleted, non-Walmart, or side-effecting entries require separate Owner re-evaluation.

## Redacted request shape

```json
{
  "sid": "<redacted>",
  "sid_list": "<redacted>",
  "start_date": "<redacted>",
  "end_date": "<redacted>",
  "date_type": "<redacted>",
  "order_status": "<redacted>",
  "sort_desc_by_date_type": "<redacted>",
  "fulfillment_channel": "<redacted>"
}
```

## Redacted response shape

```json
{
  "code": "<redacted>",
  "message": "<redacted>",
  "error_details": "<redacted>",
  "request_id": "<redacted>",
  "response_time": "<redacted>",
  "total": "<redacted>",
  "data": "<redacted>",
  "data>>sid": "<redacted>"
}
```

Only field names are shown. No real identifier, product value, URL, credential, or response content is included.

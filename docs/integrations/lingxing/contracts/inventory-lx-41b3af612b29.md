# 查询仓库库存明细 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-41B3AF612B29` |
| Contract status | `READY_FOR_PRP` |
| Source document | `old-system/source/docs/lingxing/InventoryDetails.md` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-41B3AF612B29` |
| Path | `/erp/sc/routing/data/local_inventory/inventoryDetails` |
| Method | `POST` |
| Protocol | `HTTPS` |
| Pagination | `offset/length` |
| Page / batch limit | `800` |
| Rate limit evidence | `1` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-41B3AF612B29 (4 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `length` | `length` | `int` | `否` |
| `offset` | `offset` | `int` | `否` |
| `sku` | `sku` | `string` | `否` |
| `wid` | `wid` | `string` | `否` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-41B3AF612B29 (54 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `array` | `是` |
| `data[].average_age` | `average_age` | `int` | `是` |
| `data[].expect_pending_num` | `expect_pending_num` | `int` | `是` |
| `data[].expect_valid_num` | `expect_valid_num` | `int` | `是` |
| `data[].fnsku` | `fnsku` | `string` | `是` |
| `data[].head_stock_price` | `head_stock_price` | `string` | `是` |
| `data[].price` | `price` | `string` | `是` |
| `data[].product_bad_num` | `product_bad_num` | `int` | `是` |
| `data[].product_id` | `product_id` | `int` | `是` |
| `data[].product_lock_num` | `product_lock_num` | `int` | `是` |
| `data[].product_onway` | `product_onway` | `int` | `是` |
| `data[].product_qc_num` | `product_qc_num` | `int` | `是` |
| `data[].product_total` | `product_total` | `int` | `是` |
| `data[].product_valid_num` | `product_valid_num` | `int` | `是` |
| `data[].purchase_price` | `purchase_price` | `string` | `是` |
| `data[].quantity_receive` | `quantity_receive` | `string` | `是` |
| `data[].seller_id` | `seller_id` | `string` | `是` |
| `data[].sku` | `sku` | `string` | `是` |
| `data[].stock_age_list` | `stock_age_list` | `array` | `是` |
| `data[].stock_age_list.name` | `name` | `string` | `是` |
| `data[].stock_age_list.qty` | `qty` | `int` | `是` |
| `data[].stock_cost` | `stock_cost` | `string` | `是` |
| `data[].stock_cost_total` | `stock_cost_total` | `string` | `是` |
| `data[].stock_price` | `stock_price` | `string` | `是` |
| `data[].storage_distribute_num` | `storage_distribute_num` | `int` | `是` |
| `data[].third_inventory` | `third_inventory` | `object` | `是` |
| `data[].third_inventory.qty_onway` | `qty_onway` | `int` | `是` |
| `data[].third_inventory.qty_pending` | `qty_pending` | `int` | `是` |
| `data[].third_inventory.qty_reserved` | `qty_reserved` | `int` | `是` |
| `data[].third_inventory.qty_sellable` | `qty_sellable` | `int` | `是` |
| `data[].third_inventory.third_inventory_data` | `third_inventory_data` | `array` | `是` |
| `data[].third_inventory.third_inventory_data.box_third` | `box_third` | `int` | `是` |
| `data[].third_inventory.third_inventory_data.children` | `children` | `array` | `是` |
| `data[].third_inventory.third_inventory_data.children.box_third` | `box_third` | `int` | `是` |
| `data[].third_inventory.third_inventory_data.children.match_num` | `match_num` | `int` | `是` |
| `data[].third_inventory.third_inventory_data.children.product_third` | `product_third` | `int` | `是` |
| `data[].third_inventory.third_inventory_data.children.third_name` | `third_name` | `string` | `是` |
| `data[].third_inventory.third_inventory_data.children.third_sku` | `third_sku` | `string` | `是` |
| `data[].third_inventory.third_inventory_data.children.third_total_value` | `third_total_value` | `int` | `是` |
| `data[].third_inventory.third_inventory_data.children.third_value` | `third_value` | `int` | `是` |
| `data[].third_inventory.third_inventory_data.diff` | `diff` | `int` | `是` |
| `data[].third_inventory.third_inventory_data.local` | `local` | `int` | `是` |
| `data[].third_inventory.third_inventory_data.name` | `name` | `string` | `是` |
| `data[].third_inventory.third_inventory_data.product_third` | `product_third` | `int` | `是` |
| `data[].third_inventory.third_inventory_data.support_box` | `support_box` | `boolean` | `是` |
| `data[].third_inventory.third_inventory_data.third` | `third` | `int` | `是` |
| `data[].transit_head_cost` | `transit_head_cost` | `string` | `是` |
| `data[].wid` | `wid` | `int` | `是` |
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
  "length": "<redacted>",
  "offset": "<redacted>",
  "sku": "<redacted>",
  "wid": "<redacted>"
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

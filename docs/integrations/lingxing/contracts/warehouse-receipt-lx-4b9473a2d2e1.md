# 查询收货单列表 — Redacted Contract Snapshot


| Item | Evidence |
|---|---|
| Interface key | `LX-4B9473A2D2E1` |
| Contract status | `DO_NOT_USE（清单现状）→ 申请重评为 READY_FOR_PRP` |
| Source document | normalized CSV only（provider doc path `/docs/Warehouse/PurchaseReceiptOrderList.md` 非仓库文件）|
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-4B9473A2D2E1` |
| Backend registry | `backend/app/integrations/lingxing/data/official_verified_interfaces.csv#LX-4B9473A2D2E1`（OFFICIAL_VERIFIED；is_read=是 / is_write=否 / has_side_effect=否）|
| Path | `/erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/getOrderList` |
| Method | `POST` |
| Protocol | `HTTPS` |
| Pagination | `offset/length` |
| Page / batch limit | `500` |
| Returns total | `是` |
| Incremental fields | `date_type, start_date, end_date` |
| Rate limit evidence | `1` |
| Business use (PMC) | 收货单（PMC 采购看板到仓时间、进度率的唯一来源） |
| Authentication | Common Lingxing authentication evidence exists (see `docs/integrations/lingxing-business-api-contract.md`); endpoint-specific applicability unverified; no credential value recorded here. |
| Can enter PRP planning | `pending owner re-evaluation` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-4B9473A2D2E1 (10 rows)`

| Path | Name | Type | Required | Note |
|---|---|---|---|---|
| `date_type` | `date_type` | `int` | `否` | 查询时间类型：1 预计到货时间，2 收货时间，3 创建时间，4 更新时间 |
| `end_date` | `end_date` | `string` | `否` | 结束时间，格式：Y-m-d 当筛选更新时间时，支持Y-m-d或Y-m-d H:i:s |
| `length` | `length` | `int` | `否` | 分页长度，默认200，上限500 |
| `offset` | `offset` | `int` | `否` | 分页偏移量，默认0 |
| `order_sns` | `order_sns` | `string` | `否` | 收货单号，多个使用英文逗号分隔 |
| `order_type` | `order_type` | `int` | `否` | 收货类型：1 采购订单，2 委外订单 |
| `qc_status` | `qc_status` | `string` | `否` | 质检状态，多个使用英文逗号分隔：0 未质检，1 部分质检，2 完成质检 |
| `start_date` | `start_date` | `string` | `否` | 开始时间，格式：Y-m-d 当筛选更新时间时，支持Y-m-d或Y-m-d H:i:s |
| `status` | `status` | `int` | `否` | 状态：10 待收货，40 已完成 |
| `wid` | `wid` | `string` | `否` | 仓库id，多个使用英文逗号分隔 |

## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-4B9473A2D2E1 (47 rows)`

| Path | Name | Type | Required | Suggested column |
|---|---|---|---|---|
| `code` | `code` | `int` | `是` | `lx_code` |
| `data` | `data` | `object` | `是` | `lx_data` |
| `data.list` | `list` | `array` | `是` | `lx_list` |
| `data.list[].business_order_sn` | `business_order_sn` | `string` | `是` | `lx_business_order_sn` |
| `data.list[].create_realname` | `create_realname` | `string` | `是` | `lx_create_realname` |
| `data.list[].create_time` | `create_time` | `string` | `是` | `lx_create_time` |
| `data.list[].create_uid` | `create_uid` | `int` | `是` | `lx_create_uid` |
| `data.list[].expect_arrival_time` | `expect_arrival_time` | `string` | `是` | `lx_expect_arrival_time` |
| `data.list[].inbound_order_sns` | `inbound_order_sns` | `array` | `是` | `lx_inbound_order_sns` |
| `data.list[].item_list` | `item_list` | `array` | `是` | `lx_item_list` |
| `data.list[].item_list.fnsku` | `fnsku` | `string` | `是` | `lx_fnsku` |
| `data.list[].item_list.item_id` | `item_id` | `string` | `是` | `lx_item_id` |
| `data.list[].item_list.notice_num_total` | `notice_num_total` | `number` | `是` | `lx_notice_num_total` |
| `data.list[].item_list.order_item_id` | `order_item_id` | `string` | `是` | `lx_order_item_id` |
| `data.list[].item_list.product_name` | `product_name` | `string` | `是` | `lx_product_name` |
| `data.list[].item_list.product_receive_num` | `product_receive_num` | `number` | `是` | `lx_product_receive_num` |
| `data.list[].item_list.qc_sn` | `qc_sn` | `array` | `是` | `lx_qc_sn` |
| `data.list[].item_list.quality_examine_status` | `quality_examine_status` | `int` | `是` | `lx_quality_examine_status` |
| `data.list[].item_list.quantity_qc_already` | `quantity_qc_already` | `number` | `是` | `lx_quantity_qc_already` |
| `data.list[].item_list.quantity_qc_prepare` | `quantity_qc_prepare` | `number` | `是` | `lx_quantity_qc_prepare` |
| `data.list[].item_list.remark` | `remark` | `string` | `是` | `lx_remark` |
| `data.list[].item_list.seller_id` | `seller_id` | `string` | `是` | `lx_seller_id` |
| `data.list[].item_list.sku` | `sku` | `string` | `是` | `lx_sku` |
| `data.list[].logistics_company` | `logistics_company` | `string` | `是` | `lx_logistics_company` |
| `data.list[].logistics_order_no` | `logistics_order_no` | `string` | `是` | `lx_logistics_order_no` |
| `data.list[].opt_realname` | `opt_realname` | `string` | `是` | `lx_opt_realname` |
| `data.list[].opt_uid` | `opt_uid` | `int` | `是` | `lx_opt_uid` |
| `data.list[].order_sn` | `order_sn` | `string` | `是` | `lx_order_sn` |
| `data.list[].order_type` | `order_type` | `int` | `是` | `lx_order_type` |
| `data.list[].other_currency` | `other_currency` | `string` | `是` | `lx_other_currency` |
| `data.list[].other_fee` | `other_fee` | `string` | `是` | `lx_other_fee` |
| `data.list[].qc_type` | `qc_type` | `int` | `是` | `lx_qc_type` |
| `data.list[].receive_realname` | `receive_realname` | `string` | `是` | `lx_receive_realname` |
| `data.list[].receive_time` | `receive_time` | `string` | `是` | `lx_receive_time` |
| `data.list[].receive_uid` | `receive_uid` | `int` | `是` | `lx_receive_uid` |
| `data.list[].remark` | `remark` | `string` | `是` | `lx_remark` |
| `data.list[].shipping_cost` | `shipping_cost` | `string` | `是` | `lx_shipping_cost` |
| `data.list[].shipping_currency` | `shipping_currency` | `string` | `是` | `lx_shipping_currency` |
| `data.list[].status` | `status` | `int` | `是` | `lx_status` |
| `data.list[].supplier_id` | `supplier_id` | `int` | `是` | `lx_supplier_id` |
| `data.list[].update_time` | `update_time` | `string` | `是` | `lx_update_time` |
| `data.list[].wid` | `wid` | `int` | `是` | `lx_wid` |
| `data.total` | `total` | `int` | `是` | `lx_total` |
| `error_details` | `error_details` | `string` | `是` | `lx_error_details` |
| `message` | `message` | `string` | `是` | `lx_message` |
| `request_id` | `request_id` | `string` | `是` | `lx_request_id` |
| `response_time` | `response_time` | `string` | `是` | `lx_response_time` |

## Real-data observation (read-only probe, 2026-09-15/17)

见 `features/pmc-purchase/data/probe_20260917/report_v4.md`（部署 AI 经旧系统客户端只读拉取 12 个月数据，产物为脱敏 CSV；不构成 provider verification，仅作字段存在性与取值分布证据）。

## Known missing evidence

- provider authentication applicability
- account/data scope
- provider verification
- **清单标记 `DO_NOT_USE` 与登记表 `is_read=是 / is_write=否 / has_side_effect=否` 矛盾，需负责人按 do-not-use.md 例外流程重评**

## Safety decision

Contract shape is repository-derived and unverified; no real call is authorized by this snapshot. `READY_FOR_PRP` permits only a future evidence-backed PRP; it does not approve provider traffic, implementation, data writes, or production use. 18 位店铺 ID（`sid`/`wid`）等大整数字段必须按字符串处理（探测 v2→v4 证据）。

## Redacted request shape

```json
{
  "date_type": "<redacted>",
  "end_date": "<redacted>",
  "length": "<redacted>",
  "offset": "<redacted>",
  "order_sns": "<redacted>",
  "order_type": "<redacted>",
  "qc_status": "<redacted>",
  "start_date": "<redacted>",
  "status": "<redacted>",
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
  "response_time": "<redacted>"
}
```

Only field names are shown. No real identifier, product value, URL, credential, or response content is included.
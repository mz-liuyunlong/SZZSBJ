# 查询采购单列表 — Redacted Contract Snapshot


| Item | Evidence |
|---|---|
| Interface key | `LX-D332F931885E` |
| Contract status | `READY_FOR_PRP` |
| Source document | normalized CSV only（provider doc path `/docs/Purchase/PurchaseOrderList.md` 非仓库文件）|
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-D332F931885E` |
| Backend registry | `backend/app/integrations/lingxing/data/official_verified_interfaces.csv#LX-D332F931885E`（OFFICIAL_VERIFIED；is_read=是 / is_write=否 / has_side_effect=否）|
| Path | `/erp/sc/routing/data/local_inventory/purchaseOrderList` |
| Method | `POST` |
| Protocol | `HTTPS` |
| Pagination | `offset/length` |
| Page / batch limit | `500` |
| Returns total | `否` |
| Incremental fields | `start_date, end_date, search_field_time` |
| Rate limit evidence | `1` |
| Business use (PMC) | 采购单（PMC 采购看板主单：状态、金额、明细、计划关联） |
| Authentication | Common Lingxing authentication evidence exists (see `docs/integrations/lingxing-business-api-contract.md`); endpoint-specific applicability unverified; no credential value recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-D332F931885E (8 rows)`

| Path | Name | Type | Required | Note |
|---|---|---|---|---|
| `custom_order_sn` | `custom_order_sn` | `array` | `否` | 自定义采购单号，上限500 |
| `end_date` | `end_date` | `string` | `是` | 结束时间，格式：Y-m-d，双闭区间 当筛选更新时间时，支持Y-m-d或Y-m-d H:i:s |
| `length` | `length` | `int` | `否` | 分页长度，默认500，上限500 |
| `offset` | `offset` | `int` | `否` | 分页偏移量，默认0 |
| `order_sn` | `order_sn` | `array` | `否` | 采购单号，上限500 |
| `purchase_type` | `purchase_type` | `int` | `否` | 采购类型，1：普通采购，2:1688采购 |
| `search_field_time` | `search_field_time` | `string` | `否` | 时间搜索维度： create_time 创建时间【默认值】 expect_arrive_time 预计到货时间 update_time 更新时间 |
| `start_date` | `start_date` | `string` | `是` | 开始时间，格式：Y-m-d，双闭区间 当筛选更新时间时，支持Y-m-d或Y-m-d H:i:s |

## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-D332F931885E (102 rows)`

| Path | Name | Type | Required | Suggested column |
|---|---|---|---|---|
| `code` | `code` | `int` | `是` | `lx_code` |
| `data` | `data` | `array` | `是` | `lx_data` |
| `data[].alibaba_order_sn` | `alibaba_order_sn` | `string` | `是` | `lx_alibaba_order_sn` |
| `data[].amount_total` | `amount_total` | `number` | `是` | `lx_amount_total` |
| `data[].auditor_realname` | `auditor_realname` | `string` | `是` | `lx_auditor_realname` |
| `data[].auditor_time` | `auditor_time` | `string` | `是` | `lx_auditor_time` |
| `data[].auditor_uid` | `auditor_uid` | `int` | `是` | `lx_auditor_uid` |
| `data[].contact_number` | `contact_number` | `string` | `是` | `lx_contact_number` |
| `data[].contact_person` | `contact_person` | `string` | `是` | `lx_contact_person` |
| `data[].create_time` | `create_time` | `string` | `是` | `lx_create_time` |
| `data[].custom_fields` | `custom_fields` | `array` | `是` | `lx_custom_fields` |
| `data[].custom_order_sn` | `custom_order_sn` | `string` | `是` | `lx_custom_order_sn` |
| `data[].fee_part_type` | `fee_part_type` | `int` | `是` | `lx_fee_part_type` |
| `data[].icon` | `icon` | `string` | `是` | `lx_icon` |
| `data[].is_tax` | `is_tax` | `int` | `是` | `lx_is_tax` |
| `data[].item_list` | `item_list` | `array` | `是` | `lx_item_list` |
| `data[].item_list.amount` | `amount` | `number` | `是` | `lx_amount` |
| `data[].item_list.attribute` | `attribute` | `string` | `是` | `lx_attribute` |
| `data[].item_list.cases_num` | `cases_num` | `int` | `是` | `lx_cases_num` |
| `data[].item_list.custom_fields` | `custom_fields` | `array` | `是` | `lx_custom_fields` |
| `data[].item_list.expect_arrive_time` | `expect_arrive_time` | `string` | `是` | `lx_expect_arrive_time` |
| `data[].item_list.fnsku` | `fnsku` | `string` | `是` | `lx_fnsku` |
| `data[].item_list.id` | `id` | `int` | `是` | `lx_id` |
| `data[].item_list.is_delete` | `is_delete` | `int` | `是` | `lx_is_delete` |
| `data[].item_list.model` | `model` | `string` | `是` | `lx_model` |
| `data[].item_list.msku` | `msku` | `array` | `是` | `lx_msku` |
| `data[].item_list.plan_sn` | `plan_sn` | `string` | `是` | `lx_plan_sn` |
| `data[].item_list.price` | `price` | `number` | `是` | `lx_price` |
| `data[].item_list.product_id` | `product_id` | `int` | `是` | `lx_product_id` |
| `data[].item_list.product_name` | `product_name` | `string` | `是` | `lx_product_name` |
| `data[].item_list.quantity_entry` | `quantity_entry` | `int` | `是` | `lx_quantity_entry` |
| `data[].item_list.quantity_exchange` | `quantity_exchange` | `int` | `是` | `lx_quantity_exchange` |
| `data[].item_list.quantity_per_case` | `quantity_per_case` | `int` | `是` | `lx_quantity_per_case` |
| `data[].item_list.quantity_plan` | `quantity_plan` | `int` | `是` | `lx_quantity_plan` |
| `data[].item_list.quantity_qc` | `quantity_qc` | `int` | `是` | `lx_quantity_qc` |
| `data[].item_list.quantity_qc_prepare` | `quantity_qc_prepare` | `int` | `是` | `lx_quantity_qc_prepare` |
| `data[].item_list.quantity_real` | `quantity_real` | `int` | `是` | `lx_quantity_real` |
| `data[].item_list.quantity_receive` | `quantity_receive` | `int` | `是` | `lx_quantity_receive` |
| `data[].item_list.quantity_return` | `quantity_return` | `int` | `是` | `lx_quantity_return` |
| `data[].item_list.relation_purchase_plan` | `relation_purchase_plan` | `array` | `是` | `lx_relation_purchase_plan` |
| `data[].item_list.remark` | `remark` | `string` | `是` | `lx_remark` |
| `data[].item_list.sid` | `sid` | `string` | `是` | `lx_sid` |
| `data[].item_list.sku` | `sku` | `string` | `是` | `lx_sku` |
| `data[].item_list.spu` | `spu` | `string` | `是` | `lx_spu` |
| `data[].item_list.spu_name` | `spu_name` | `string` | `是` | `lx_spu_name` |
| `data[].item_list.tax_rate` | `tax_rate` | `string` | `是` | `lx_tax_rate` |
| `data[].item_list.ware_house_name` | `ware_house_name` | `string` | `是` | `lx_ware_house_name` |
| `data[].item_list.wid` | `wid` | `int` | `是` | `lx_wid` |
| `data[].last_realname` | `last_realname` | `string` | `是` | `lx_last_realname` |
| `data[].last_time` | `last_time` | `string` | `是` | `lx_last_time` |
| `data[].last_uid` | `last_uid` | `int` | `是` | `lx_last_uid` |
| `data[].logistics_info` | `logistics_info` | `array` | `是` | `lx_logistics_info` |
| `data[].logistics_info.logistics_company` | `logistics_company` | `string` | `是` | `lx_logistics_company` |
| `data[].logistics_info.logistics_order_no` | `logistics_order_no` | `string` | `是` | `lx_logistics_order_no` |
| `data[].logistics_info.pol_id` | `pol_id` | `string` | `是` | `lx_pol_id` |
| `data[].logistics_info.purchase_order_id` | `purchase_order_id` | `string` | `是` | `lx_purchase_order_id` |
| `data[].logistics_info.purchase_order_sn` | `purchase_order_sn` | `string` | `是` | `lx_purchase_order_sn` |
| `data[].opt_realname` | `opt_realname` | `string` | `是` | `lx_opt_realname` |
| `data[].opt_uid` | `opt_uid` | `int` | `是` | `lx_opt_uid` |
| `data[].order_sn` | `order_sn` | `string` | `是` | `lx_order_sn` |
| `data[].order_time` | `order_time` | `string` | `是` | `lx_order_time` |
| `data[].other_currency` | `other_currency` | `string` | `是` | `lx_other_currency` |
| `data[].other_fee` | `other_fee` | `number` | `是` | `lx_other_fee` |
| `data[].pay_status` | `pay_status` | `int` | `是` | `lx_pay_status` |
| `data[].pay_status_text` | `pay_status_text` | `string` | `是` | `lx_pay_status_text` |
| `data[].payment` | `payment` | `string` | `是` | `lx_payment` |
| `data[].payment_method` | `payment_method` | `int` | `是` | `lx_payment_method` |
| `data[].principal_uids` | `principal_uids` | `array` | `是` | `lx_principal_uids` |
| `data[].principal_uids.id` | `id` | `string` | `是` | `lx_id` |
| `data[].principal_uids.name` | `name` | `string` | `是` | `lx_name` |
| `data[].purchase_currency` | `purchase_currency` | `string` | `是` | `lx_purchase_currency` |
| `data[].purchase_rate` | `purchase_rate` | `number` | `是` | `lx_purchase_rate` |
| `data[].purchase_type` | `purchase_type` | `string` | `是` | `lx_purchase_type` |
| `data[].purchase_type_text` | `purchase_type_text` | `string` | `是` | `lx_purchase_type_text` |
| `data[].purchaser_id` | `purchaser_id` | `int` | `是` | `lx_purchaser_id` |
| `data[].quantity_entry` | `quantity_entry` | `int` | `是` | `lx_quantity_entry` |
| `data[].quantity_real` | `quantity_real` | `int` | `是` | `lx_quantity_real` |
| `data[].quantity_receive` | `quantity_receive` | `int` | `是` | `lx_quantity_receive` |
| `data[].quantity_total` | `quantity_total` | `number` | `是` | `lx_quantity_total` |
| `data[].reason` | `reason` | `string` | `是` | `lx_reason` |
| `data[].remark` | `remark` | `string` | `是` | `lx_remark` |
| `data[].settlement_description` | `settlement_description` | `string` | `是` | `lx_settlement_description` |
| `data[].settlement_method` | `settlement_method` | `int` | `是` | `lx_settlement_method` |
| `data[].shipping_currency` | `shipping_currency` | `string` | `是` | `lx_shipping_currency` |
| `data[].shipping_price` | `shipping_price` | `number` | `是` | `lx_shipping_price` |
| `data[].status` | `status` | `int` | `是` | `lx_status` |
| `data[].status_shipped` | `status_shipped` | `int` | `是` | `lx_status_shipped` |
| `data[].status_shipped_text` | `status_shipped_text` | `string` | `是` | `lx_status_shipped_text` |
| `data[].status_text` | `status_text` | `string` | `是` | `lx_status_text` |
| `data[].sub_status` | `sub_status` | `string` | `是` | `lx_sub_status` |
| `data[].sub_status_text` | `sub_status_text` | `string` | `是` | `lx_sub_status_text` |
| `data[].supplier_id` | `supplier_id` | `int` | `是` | `lx_supplier_id` |
| `data[].supplier_name` | `supplier_name` | `string` | `是` | `lx_supplier_name` |
| `data[].total_price` | `total_price` | `number` | `是` | `lx_total_price` |
| `data[].update_time` | `update_time` | `string` | `是` | `lx_update_time` |
| `data[].ware_house_bak_name` | `ware_house_bak_name` | `string` | `是` | `lx_ware_house_bak_name` |
| `data[].ware_house_name` | `ware_house_name` | `string` | `是` | `lx_ware_house_name` |
| `data[].wid` | `wid` | `int` | `是` | `lx_wid` |
| `error_details` | `error_details` | `array` | `是` | `lx_error_details` |
| `message` | `message` | `string` | `是` | `lx_message` |
| `request_id` | `request_id` | `string` | `是` | `lx_request_id` |
| `response_time` | `response_time` | `string` | `是` | `lx_response_time` |

## Real-data observation (read-only probe, 2026-09-15/17)

见 `features/pmc-purchase/data/probe_20260917/report_v4.md`（部署 AI 经旧系统客户端只读拉取 12 个月数据，产物为脱敏 CSV；不构成 provider verification，仅作字段存在性与取值分布证据）。

## Known missing evidence

- provider authentication applicability
- account/data scope
- provider verification
- `returns_total=否`：分页不能依赖 total，需按“返回行数 < length”终止

## Safety decision

Contract shape is repository-derived and unverified; no real call is authorized by this snapshot. `READY_FOR_PRP` permits only a future evidence-backed PRP; it does not approve provider traffic, implementation, data writes, or production use. 18 位店铺 ID（`sid`/`wid`）等大整数字段必须按字符串处理（探测 v2→v4 证据）。

## Redacted request shape

```json
{
  "custom_order_sn": "<redacted>",
  "end_date": "<redacted>",
  "length": "<redacted>",
  "offset": "<redacted>",
  "order_sn": "<redacted>",
  "purchase_type": "<redacted>",
  "search_field_time": "<redacted>",
  "start_date": "<redacted>"
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
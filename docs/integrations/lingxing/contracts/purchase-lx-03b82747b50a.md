# 查询采购计划列表 — Redacted Contract Snapshot


| Item | Evidence |
|---|---|
| Interface key | `LX-03B82747B50A` |
| Contract status | `READY_FOR_PRP` |
| Source document | normalized CSV only（provider doc path `/docs/Purchase/getPurchasePlans.md` 非仓库文件）|
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-03B82747B50A` |
| Backend registry | `backend/app/integrations/lingxing/data/official_verified_interfaces.csv#LX-03B82747B50A`（OFFICIAL_VERIFIED；is_read=是 / is_write=否 / has_side_effect=否）|
| Path | `/erp/sc/routing/data/local_inventory/getPurchasePlans` |
| Method | `POST` |
| Protocol | `HTTPS` |
| Pagination | `offset/length` |
| Page / batch limit | `500` |
| Returns total | `是` |
| Incremental fields | `search_field_time, start_date, end_date` |
| Rate limit evidence | `1` |
| Business use (PMC) | 采购计划（PMC 采购看板 S1/S2、ItemID 备注来源） |
| Authentication | Common Lingxing authentication evidence exists (see `docs/integrations/lingxing-business-api-contract.md`); endpoint-specific applicability unverified; no credential value recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-03B82747B50A (10 rows)`

| Path | Name | Type | Required | Note |
|---|---|---|---|---|
| `end_date` | `end_date` | `string` | `是` | 结束日期，Y-m-d，闭区间，当筛选update_time时，格式为：Y-m-d H:i:s |
| `is_combo` | `is_combo` | `int` | `否` | 是否为组合商品：0 否，1 是 |
| `is_related_process_plan` | `is_related_process_plan` | `int` | `否` | 是否关联加工计划，0：否，1：是 |
| `length` | `length` | `int` | `否` | 分页长度，默认500，上限500 |
| `offset` | `offset` | `int` | `否` | 分页偏移量，默认0 |
| `plan_sns` | `plan_sns` | `array` | `否` | 采购计划编号 |
| `search_field_time` | `search_field_time` | `string` | `是` | 时间搜索维度： creator_time 创建时间 expect_arrive_time 预计到货时间 update_time 更新时间 |
| `sids` | `sids` | `array` | `否` | 店铺id ，对应[查询亚马逊店铺列表](docs/BasicData/SellerLists)接口对应字段【sid】 |
| `start_date` | `start_date` | `string` | `是` | 开始日期，Y-m-d，闭区间，当筛选update_time时，格式为：Y-m-d H:i:s |
| `status` | `status` | `array` | `否` | 状态： 2 待采购 -2 已完成 121 待审批 122 已驳回 -3、124 已作废 |

## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-03B82747B50A (47 rows)`

| Path | Name | Type | Required | Suggested column |
|---|---|---|---|---|
| `code` | `code` | `int` | `是` | `lx_code` |
| `data` | `data` | `array` | `是` | `lx_data` |
| `data[].attribute` | `attribute` | `array` | `是` | `lx_attribute` |
| `data[].cg_box_pcs` | `cg_box_pcs` | `int` | `是` | `lx_cg_box_pcs` |
| `data[].cg_opt_username` | `cg_opt_username` | `string` | `是` | `lx_cg_opt_username` |
| `data[].cg_uid` | `cg_uid` | `int` | `是` | `lx_cg_uid` |
| `data[].create_time` | `create_time` | `string` | `是` | `lx_create_time` |
| `data[].creator_real_name` | `creator_real_name` | `string` | `是` | `lx_creator_real_name` |
| `data[].creator_uid` | `creator_uid` | `int` | `是` | `lx_creator_uid` |
| `data[].expect_arrive_time` | `expect_arrive_time` | `string` | `是` | `lx_expect_arrive_time` |
| `data[].file` | `file` | `array` | `是` | `lx_file` |
| `data[].file.name` | `name` | `string` | `是` | `lx_name` |
| `data[].file.url` | `url` | `string` | `是` | `lx_url` |
| `data[].fnsku` | `fnsku` | `string` | `是` | `lx_fnsku` |
| `data[].is_aux` | `is_aux` | `int` | `是` | `lx_is_aux` |
| `data[].is_combo` | `is_combo` | `int` | `是` | `lx_is_combo` |
| `data[].is_related_process_plan` | `is_related_process_plan` | `int` | `是` | `lx_is_related_process_plan` |
| `data[].marketplace` | `marketplace` | `string` | `是` | `lx_marketplace` |
| `data[].msku` | `msku` | `array` | `是` | `lx_msku` |
| `data[].perm_uid` | `perm_uid` | `array` | `是` | `lx_perm_uid` |
| `data[].perm_username` | `perm_username` | `object` | `是` | `lx_perm_username` |
| `data[].pic_url` | `pic_url` | `string` | `是` | `lx_pic_url` |
| `data[].plan_remark` | `plan_remark` | `string` | `是` | `lx_plan_remark` |
| `data[].plan_sn` | `plan_sn` | `string` | `是` | `lx_plan_sn` |
| `data[].ppg_sn` | `ppg_sn` | `string` | `是` | `lx_ppg_sn` |
| `data[].product_id` | `product_id` | `int` | `是` | `lx_product_id` |
| `data[].product_name` | `product_name` | `string` | `是` | `lx_product_name` |
| `data[].purchaser_id` | `purchaser_id` | `int` | `是` | `lx_purchaser_id` |
| `data[].purchaser_name` | `purchaser_name` | `string` | `是` | `lx_purchaser_name` |
| `data[].quantity_plan` | `quantity_plan` | `int` | `是` | `lx_quantity_plan` |
| `data[].remark` | `remark` | `string` | `是` | `lx_remark` |
| `data[].seller_name` | `seller_name` | `string` | `是` | `lx_seller_name` |
| `data[].sid` | `sid` | `number` | `是` | `lx_sid` |
| `data[].sku` | `sku` | `string` | `是` | `lx_sku` |
| `data[].spu` | `spu` | `string` | `是` | `lx_spu` |
| `data[].spu_name` | `spu_name` | `string` | `是` | `lx_spu_name` |
| `data[].status` | `status` | `int` | `是` | `lx_status` |
| `data[].status_text` | `status_text` | `string` | `是` | `lx_status_text` |
| `data[].supplier_id` | `supplier_id` | `object` | `是` | `lx_supplier_id` |
| `data[].supplier_name` | `supplier_name` | `string` | `是` | `lx_supplier_name` |
| `data[].warehouse_name` | `warehouse_name` | `string` | `是` | `lx_warehouse_name` |
| `data[].wid` | `wid` | `int` | `是` | `lx_wid` |
| `error_details` | `error_details` | `string` | `是` | `lx_error_details` |
| `message` | `message` | `string` | `是` | `lx_message` |
| `request_id` | `request_id` | `string` | `是` | `lx_request_id` |
| `response_time` | `response_time` | `string` | `是` | `lx_response_time` |
| `total` | `total` | `int` | `是` | `lx_total` |

## Real-data observation (read-only probe, 2026-09-15/17)

见 `features/pmc-purchase/data/probe_20260917/report_v4.md`（部署 AI 经旧系统客户端只读拉取 12 个月数据，产物为脱敏 CSV；不构成 provider verification，仅作字段存在性与取值分布证据）。

## Known missing evidence

- provider authentication applicability
- account/data scope
- provider verification
- 计划审批时间戳不在响应中（审批周期需每日观察推算）

## Safety decision

Contract shape is repository-derived and unverified; no real call is authorized by this snapshot. `READY_FOR_PRP` permits only a future evidence-backed PRP; it does not approve provider traffic, implementation, data writes, or production use. 18 位店铺 ID（`sid`/`wid`）等大整数字段必须按字符串处理（探测 v2→v4 证据）。

## Redacted request shape

```json
{
  "end_date": "<redacted>",
  "is_combo": "<redacted>",
  "is_related_process_plan": "<redacted>",
  "length": "<redacted>",
  "offset": "<redacted>",
  "plan_sns": "<redacted>",
  "search_field_time": "<redacted>",
  "sids": "<redacted>",
  "start_date": "<redacted>",
  "status": "<redacted>"
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
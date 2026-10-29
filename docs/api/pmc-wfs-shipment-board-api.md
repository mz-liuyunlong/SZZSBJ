# WFS 货件看板 API（M1）

日期：2026-10-29。前缀 `/api/pmc/wfs/shipment-board`。只读；M1 不含领星履约字段。

## 权限

页面权限 `page:pmc:wfs:view`；校验来源账号与店铺数据范围。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /shipments | 货件列表；仅含 `ticket.result.labels` 中已有 shipment_id 的行 |
| GET | /shipments/{row_id} | 详情；`row_id`=`{ticket_uuid}:{shipment_id}` |
| GET | /summary | 统计：total、pending_lingxing_sync、test |
| GET | /filter-options | 店铺选项（dim_lingxing_stores + 已出现店铺） |

查询参数（列表/统计）：`store_id`、`keyword`、`keyword_field`（shipment/pk/msku/sku/item/gtin）、`only_test`；列表另有 `page`、`page_size`（默认 20，最大 200）、`sort_by=created_at`、`sort_dir=desc|asc`。

## 行字段

创建侧：`shipment_id`、PK、店铺、商品身份、标签状态、创建/票状态、`its`、`business_test`、`created_at`。  
领星侧 M1：`lingxing_sync_status=PENDING`；`declared_units`/`shipped_units`/`received_units` 为 null。

统一 envelope `{ success, data, error, meta, request_id }`；`meta.lingxing_sync_enabled=false`。

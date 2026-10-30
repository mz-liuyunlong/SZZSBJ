# WFS 货件看板 API（M2）

日期：2026-10-30。前缀 `/api/pmc/wfs/shipment-board`。只读。M2 起以领星 WFS 货件为准，本系统创建记录只做关联。

## 权限

页面权限 `page:pmc:wfs:view`；校验来源账号与店铺数据范围。

## 数据来源

- `mart_wfs_shipment_board` 的当前发布版本（`gov_wfs_board_publications.is_current`）：一行一张领星 WFS 货件，来自 `queryWFSCargoPage` + `queryShippingListPage`（手工一次性运行 `scripts/run_pmc_wfs_board_once.py`，再 `scripts/publish_pmc_wfs_board.py`；不开定时）。
- `ops_wfs_creation_*`：按货件号（`labels` 键 = `cargo_code`）关联；关联不上但本系统已创建的票以 `source=creation_only`、`lingxing_sync_status=PENDING` 出现。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /shipments | 货件行；`row_id` = `lx:{publication_id}:{cargo_id}` 或 `cr:{ticket_uuid}:{shipment_id}` |
| GET | /products | 产品维度：当前筛选下的货件商品行按 店铺 × MSKU 聚合（申报 / 发出 / Received / 破损 / 在途） |
| GET | /shipments/{row_id} | 详情：商品行、领星发货单、地址、节点时间、创建记录 |
| GET | /summary | total、by_status（0–4 → 张数）、pending_lingxing_sync、test、received_short、freshness |
| GET | /filter-options | 店铺选项 |

查询参数（列表 / 产品 / 统计）：`store_id`、`keyword`、`keyword_field`（shipment / inbound / shipping / pk / msku / sku / item / gtin）、`only_test`、`status`（0–4）、`sync`（SYNCED / PENDING）；列表另有 `page`、`page_size`（≤200）、`sort_by`（created_at / updated_at）、`sort_dir`。

## 行字段

领星侧：`shipment_id`（cargo_code）、`inbound_order_id`、`status` + `status_name` + `status_label`（0 待发货 / 1 在途 / 2 收货中 / 3 已关闭 / 4 已取消）、`cargo_sync_status`、`declared_units` / `shipped_units` / `received_units` / `damaged_units`、`sku_count`、`logistics_code`、`shipping_codes`、`shipping_status`、`warehouse_id`、`actual_delivery_date`、`arrival_date`、`expected_arrival_date`、`logistics_numbers`、`created_at`、`to_await_at` / `to_receive_at` / `to_closed_at` / `to_cancelled_at`。  
创建侧（可空）：`pk`、`its`、`business_test`、`operation_id`、`ticket_id`、`ticket_number`、`label_state`、`creation_state`、`ticket_state`。  
`freshness`：`source_observed_at`（领星拉取时间）、`published_at`、`coverage_start/end`、`stale`（>24h）。

统一 envelope；`meta.lingxing_sync_enabled=true`、`meta.lingxing_sync_mode=manual_one_time_run`。看板表未迁移时返回 503 `WFS_BOARD_SCHEMA_NOT_READY`。

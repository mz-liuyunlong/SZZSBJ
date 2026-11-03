# 财务 · 结算利润 V2 表结构（PR-1）

来源：`PRPs/finance-settlement-profit-v2.md` §6.2；模型 `backend/app/modules/finance/settlement_profit_models.py`；迁移 `backend/alembic/versions/20261103_0072_fin_settle_profit_v2.py`（down_revision `20261102_0071_skill_lib`）。

PR-3 迁移 `backend/alembic/versions/20261104_0074_fin_settle_calc.py` 只在本 PR 的表上加列、改 CHECK：调整类型加 `assign_store`；库存异动 `store_mapping_status` 加 `manual_assigned`，并加 `source_row_hash`、`content_hash`；待指定加 `amount_cny`、`reason`、`detail`、`assigned_store_id`，`amount_usd` 可为空（与 `amount_cny` 至少一个非空）；对平加 `inbound_freight_lx_vs_settlement_diff_usd`、`result_hash`。对不上店铺的库存异动，待指定行的 store_id 用占位值 `__unmapped__`（PRP §8.4）。

## 约定

- 分层：RAW（既有 `ods_api_raw_blobs` / `ods_api_raw_request_refs`）→ ODS → FACT → MART；`manual_` 只覆盖计算结果，不写 RAW / ODS / FACT，也不建外键指向它们；`cfg_` 为财务设置。
- 金额 `numeric(18,4)`；列名以 `_usd` / `_cny` 结尾表示币种，`*_amount` 列配 `currency_code`。外部 ID（店铺、订单号、订单行号、GTIN、item_id、流水号、report_id）一律字符串。
- 月份列（`bill_month` / `movement_month` / `month` / `effective_month`）存当月 1 号，CHECK 约束保证。
- 汇率：只读既有 `ref_product_pricing_rule_versions.usd_cny_rate`；`fx_status` 只有 `final` / `missing`，missing 时 CNY 列为空，不做兜底；本 PR 不建汇率表。
- `line_key`：订单行 = 店铺 + reportKey + 订单号 + 订单行号 + GTIN；待指定行 = 店铺 + 账单月 + source_kind + source_ref；对平差额行 = 店铺 + 账单月 + "reconcile_diff"。同一期结算单里同一订单行的各交易类型汇总成一行。
- `remote_job_id` 记录 `walmart_remote_jobs.id`，不建外键（Walmart 只走一店一服务器）。
- 预留列 `promotion_fee_usd`、`packaging_fee_usd` 恒为空，不参与计算。
- 领星 WFS 成本计价明细不在本 PR：表 `ods_lingxing_wfs_cost_valuation_flow`、同步、契约登记归「库存索赔」PRP 的 PR 1；本 PRP 只读 `is_current = true` 的行，`fact_inventory_movement_lines` 以该行 id（`source_flow_id`）为来源、不建外键，不用流水号做键。
- 本 PR 只建表，不写数据、不新增同步、不改任何既有表；PR-2 的新同步一律默认 `is_enabled=false`、`schedule_enabled=false`。

## 表清单

| 层 | 表 | 写入方 | 唯一键 |
|---|---|---|---|
| ODS | `ods_lingxing_mp_profit_order_lines` | 领星多平台结算利润-订单 handler（PR-2，默认关） | (source_account_ref, store_id, platform_order_no, order_item_no, transaction_type, settlement_date, source_row_seq) |
| ODS | `ods_walmart_wfs_fee_detail_lines` | Walmart WFS 费用明细 handler（PR-2，walmart_remote_jobs，默认关） | (source_account_ref, store_id, report_id, line_no) |
| ODS | `ods_walmart_storage_fee_lines` | Walmart 仓储费报表 handler（PR-2，walmart_remote_jobs，默认关） | (source_account_ref, store_id, report_period_start, report_period_end, gtin) |
| ODS | `ods_walmart_review_accelerator_snapshots` | 评价加速器快照 handler（PR-2，walmart_remote_jobs，默认关） | (source_account_ref, store_id, snapshot_report_key, item_id) |
| FACT | `fact_settlement_order_lines` | 计算任务（PR-3） | (store_id, bill_month, calc_version, line_key) |
| FACT | `fact_inventory_movement_lines` | 计算任务（PR-3） | (source_flow_id, calc_version) |
| FACT | `fact_settlement_unassigned_amounts` | 计算任务（PR-3） | (store_id, bill_month, source_kind, source_ref) |
| FACT | `fact_settlement_post_close_diffs` | 计算任务（PR-3） | (store_id, bill_month, line_key, detected_at) |
| MART | `mart_settlement_profit_item_month` | 计算任务（PR-3） | (store_id, item_id, bill_month) |
| MART | `mart_settlement_order_review` | 计算任务（PR-3） | (store_id, bill_month, line_key) |
| MART | `mart_settlement_reconcile_store_month` | 计算任务（PR-3） | (store_id, bill_month) |
| MART | `mart_inventory_movement_month` | 计算任务（PR-3） | (store_id, item_id, month, category) |
| MANUAL | `manual_settlement_order_adjustments` | 财务操作接口（PR-4） | (idempotency_key) |
| MANUAL | `manual_settlement_review_actions` | 财务操作接口（PR-4） | (idempotency_key, line_key) |
| MANUAL | `manual_settlement_month_close` | 财务操作接口（PR-4） | (store_scope, bill_month) |
| CFG | `cfg_net_profit_allocation` | 财务主管（PR-4） | (effective_month) |

## 字段

### `ods_lingxing_mp_profit_order_lines`

| 列 | 类型 | 可空 |
|---|---|---|
| `platform_order_no` | `VARCHAR(255)` | 否 |
| `order_item_no` | `VARCHAR(128)` | 否 |
| `transaction_type` | `VARCHAR(64)` | 否 |
| `settlement_date` | `DATE` | 否 |
| `ordered_at` | `DATETIME` | 是 |
| `shipped_at` | `DATETIME` | 是 |
| `settled_at` | `DATETIME` | 是 |
| `item_id` | `VARCHAR(128)` | 是 |
| `msku` | `TEXT` | 是 |
| `gtin` | `VARCHAR(64)` | 是 |
| `quantity` | `NUMERIC(18, 4)` | 是 |
| `sales_amount` | `NUMERIC(18, 4)` | 是 |
| `promotion_fee_amount` | `NUMERIC(18, 4)` | 是 |
| `review_accelerator_fee_amount` | `NUMERIC(18, 4)` | 是 |
| `currency_code` | `VARCHAR(3)` | 否 |
| `id` | `CHAR(32)` | 否 |
| `source_account_ref` | `VARCHAR(128)` | 否 |
| `store_id` | `VARCHAR(128)` | 否 |
| `source_row_seq` | `INTEGER` | 否 |
| `source_run_id` | `CHAR(32)` | 是 |
| `source_raw_request_ref_id` | `CHAR(32)` | 是 |
| `collected_at` | `DATETIME` | 否 |
| `raw_row` | `JSONB` | 否 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

索引：`ix_ods_lx_mp_profit_order_lookup (store_id, platform_order_no, gtin)`

### `ods_walmart_wfs_fee_detail_lines`

| 列 | 类型 | 可空 |
|---|---|---|
| `report_id` | `VARCHAR(255)` | 否 |
| `line_no` | `INTEGER` | 否 |
| `report_period_start` | `DATE` | 是 |
| `report_period_end` | `DATE` | 是 |
| `transaction_date_la` | `DATE` | 是 |
| `fee_type` | `VARCHAR(128)` | 否 |
| `gtin` | `VARCHAR(64)` | 是 |
| `item_id` | `VARCHAR(128)` | 是 |
| `quantity` | `NUMERIC(18, 4)` | 是 |
| `fee_amount` | `NUMERIC(18, 4)` | 否 |
| `currency_code` | `VARCHAR(3)` | 否 |
| `remote_job_id` | `CHAR(32)` | 是 |
| `id` | `CHAR(32)` | 否 |
| `source_account_ref` | `VARCHAR(128)` | 否 |
| `store_id` | `VARCHAR(128)` | 否 |
| `source_row_seq` | `INTEGER` | 否 |
| `source_run_id` | `CHAR(32)` | 是 |
| `source_raw_request_ref_id` | `CHAR(32)` | 是 |
| `collected_at` | `DATETIME` | 否 |
| `raw_row` | `JSONB` | 否 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

索引：`ix_ods_wm_wfs_fee_detail_gtin_date (store_id, gtin, transaction_date_la)`

### `ods_walmart_storage_fee_lines`

| 列 | 类型 | 可空 |
|---|---|---|
| `report_id` | `VARCHAR(255)` | 是 |
| `report_period_start` | `DATE` | 否 |
| `report_period_end` | `DATE` | 否 |
| `gtin` | `VARCHAR(64)` | 否 |
| `item_id` | `VARCHAR(128)` | 是 |
| `on_hand_quantity` | `NUMERIC(18, 4)` | 是 |
| `volume_cubic_feet` | `NUMERIC(18, 4)` | 是 |
| `storage_fee_amount` | `NUMERIC(18, 4)` | 否 |
| `currency_code` | `VARCHAR(3)` | 否 |
| `remote_job_id` | `CHAR(32)` | 是 |
| `id` | `CHAR(32)` | 否 |
| `source_account_ref` | `VARCHAR(128)` | 否 |
| `store_id` | `VARCHAR(128)` | 否 |
| `source_row_seq` | `INTEGER` | 否 |
| `source_run_id` | `CHAR(32)` | 是 |
| `source_raw_request_ref_id` | `CHAR(32)` | 是 |
| `collected_at` | `DATETIME` | 否 |
| `raw_row` | `JSONB` | 否 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

### `ods_walmart_review_accelerator_snapshots`

| 列 | 类型 | 可空 |
|---|---|---|
| `snapshot_report_key` | `VARCHAR(255)` | 否 |
| `item_id` | `VARCHAR(128)` | 否 |
| `gtin` | `VARCHAR(64)` | 是 |
| `enrollment_status` | `VARCHAR(64)` | 是 |
| `reviews_collected` | `INTEGER` | 否 |
| `sale_price_amount` | `NUMERIC(18, 4)` | 是 |
| `price_amount` | `NUMERIC(18, 4)` | 是 |
| `currency_code` | `VARCHAR(3)` | 否 |
| `snapshot_at` | `DATETIME` | 否 |
| `remote_job_id` | `CHAR(32)` | 是 |
| `id` | `CHAR(32)` | 否 |
| `source_account_ref` | `VARCHAR(128)` | 否 |
| `store_id` | `VARCHAR(128)` | 否 |
| `source_row_seq` | `INTEGER` | 否 |
| `source_run_id` | `CHAR(32)` | 是 |
| `source_raw_request_ref_id` | `CHAR(32)` | 是 |
| `collected_at` | `DATETIME` | 否 |
| `raw_row` | `JSONB` | 否 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

### `fact_settlement_order_lines`

| 列 | 类型 | 可空 |
|---|---|---|
| `id` | `CHAR(32)` | 否 |
| `line_key` | `VARCHAR(512)` | 否 |
| `store_id` | `VARCHAR(128)` | 否 |
| `bill_month` | `DATE` | 否 |
| `report_key` | `VARCHAR(255)` | 否 |
| `platform_order_no` | `VARCHAR(255)` | 否 |
| `order_item_no` | `VARCHAR(128)` | 否 |
| `item_id` | `VARCHAR(128)` | 否 |
| `gtin` | `VARCHAR(64)` | 是 |
| `msku` | `TEXT` | 是 |
| `owner_ref` | `VARCHAR(255)` | 是 |
| `serial_number` | `VARCHAR(128)` | 是 |
| `quantity` | `NUMERIC(18, 4)` | 否 |
| `ordered_at` | `DATETIME` | 是 |
| `shipped_at` | `DATETIME` | 是 |
| `settled_at` | `DATETIME` | 是 |
| `cost_match_status` | `VARCHAR(32)` | 是 |
| `review_status` | `VARCHAR(16)` | 否 |
| `reasons` | `JSONB` | 否 |
| `version` | `INTEGER` | 否 |
| `calc_version` | `INTEGER` | 否 |
| `content_hash` | `VARCHAR(64)` | 否 |
| `source_run_ids` | `JSONB` | 否 |
| `frozen_at` | `DATETIME` | 是 |
| `frozen_by` | `VARCHAR(255)` | 是 |
| `sales_amount_usd` | `NUMERIC(18, 4)` | 否 |
| `platform_subsidy_usd` | `NUMERIC(18, 4)` | 否 |
| `refund_amount_usd` | `NUMERIC(18, 4)` | 否 |
| `commission_usd` | `NUMERIC(18, 4)` | 否 |
| `wfs_fulfillment_fee_usd` | `NUMERIC(18, 4)` | 否 |
| `return_fee_usd` | `NUMERIC(18, 4)` | 否 |
| `tax_withheld_usd` | `NUMERIC(18, 4)` | 否 |
| `wfs_service_fee_usd` | `NUMERIC(18, 4)` | 否 |
| `storage_fee_usd` | `NUMERIC(18, 4)` | 否 |
| `inbound_wpc_usd` | `NUMERIC(18, 4)` | 否 |
| `ad_cost_usd` | `NUMERIC(18, 4)` | 否 |
| `review_accelerator_usd` | `NUMERIC(18, 4)` | 否 |
| `disposal_loss_usd` | `NUMERIC(18, 4)` | 否 |
| `promotion_fee_usd` | `NUMERIC(18, 4)` | 是 |
| `packaging_fee_usd` | `NUMERIC(18, 4)` | 是 |
| `purchase_cost_cny` | `NUMERIC(18, 4)` | 是 |
| `head_cost_cny` | `NUMERIC(18, 4)` | 是 |
| `goods_cost_usd` | `NUMERIC(18, 4)` | 是 |
| `gross_profit_usd` | `NUMERIC(18, 4)` | 是 |
| `gross_profit_cny` | `NUMERIC(18, 4)` | 是 |
| `net_profit_share_cny` | `NUMERIC(18, 4)` | 是 |
| `fx_rate` | `NUMERIC(18, 8)` | 是 |
| `fx_month` | `DATE` | 是 |
| `fx_status` | `VARCHAR(16)` | 否 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

索引：`ix_fact_settlement_order_lines_item_month (store_id, item_id, bill_month)`；`ix_fact_settlement_order_lines_line_key (line_key)`；`ix_fact_settlement_order_lines_order (store_id, bill_month, platform_order_no, order_item_no)`

### `fact_inventory_movement_lines`

| 列 | 类型 | 可空 |
|---|---|---|
| `id` | `CHAR(32)` | 否 |
| `source_flow_id` | `CHAR(32)` | 否 |
| `source_sync_batch_id` | `CHAR(32)` | 是 |
| `source_row_hash` | `VARCHAR(64)` | 否 |
| `content_hash` | `VARCHAR(64)` | 否 |
| `store_code` | `VARCHAR(128)` | 否 |
| `store_id` | `VARCHAR(128)` | 是 |
| `store_mapping_status` | `VARCHAR(16)` | 否 |
| `serial_number` | `VARCHAR(128)` | 是 |
| `business_type` | `VARCHAR(64)` | 否 |
| `gtin` | `VARCHAR(64)` | 是 |
| `item_id` | `VARCHAR(128)` | 是 |
| `owner_ref` | `VARCHAR(255)` | 是 |
| `category` | `VARCHAR(16)` | 否 |
| `movement_month` | `DATE` | 否 |
| `occurred_at` | `DATETIME` | 是 |
| `quantity` | `NUMERIC(18, 4)` | 否 |
| `goods_value_cny` | `NUMERIC(18, 4)` | 是 |
| `goods_value_usd` | `NUMERIC(18, 4)` | 是 |
| `disposal_fee_usd` | `NUMERIC(18, 4)` | 是 |
| `destination` | `VARCHAR(255)` | 是 |
| `calc_version` | `INTEGER` | 否 |
| `fx_rate` | `NUMERIC(18, 8)` | 是 |
| `fx_month` | `DATE` | 是 |
| `fx_status` | `VARCHAR(16)` | 否 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

索引：`ix_fact_inventory_movement_lines_month (store_id, movement_month, category)`；`ix_fact_inventory_movement_lines_serial (serial_number)`

### `fact_settlement_unassigned_amounts`

| 列 | 类型 | 可空 |
|---|---|---|
| `id` | `CHAR(32)` | 否 |
| `line_key` | `VARCHAR(512)` | 否 |
| `store_id` | `VARCHAR(128)` | 否 |
| `bill_month` | `DATE` | 否 |
| `source_kind` | `VARCHAR(64)` | 否 |
| `source_ref` | `VARCHAR(255)` | 否 |
| `amount_usd` | `NUMERIC(18, 4)` | 是 |
| `amount_cny` | `NUMERIC(18, 4)` | 是 |
| `reason` | `VARCHAR(32)` | 否 |
| `detail` | `JSONB` | 否 |
| `status` | `VARCHAR(16)` | 否 |
| `assigned_item_id` | `VARCHAR(128)` | 是 |
| `assigned_store_id` | `VARCHAR(128)` | 是 |
| `adjustment_id` | `CHAR(32)` | 是 |
| `note` | `TEXT` | 是 |
| `calc_version` | `INTEGER` | 否 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

### `fact_settlement_post_close_diffs`

| 列 | 类型 | 可空 |
|---|---|---|
| `id` | `CHAR(32)` | 否 |
| `store_id` | `VARCHAR(128)` | 否 |
| `bill_month` | `DATE` | 否 |
| `line_key` | `VARCHAR(512)` | 否 |
| `detected_at` | `DATETIME` | 否 |
| `old_value` | `JSONB` | 否 |
| `new_value` | `JSONB` | 否 |
| `diff_amount_usd` | `NUMERIC(18, 4)` | 是 |
| `status` | `VARCHAR(24)` | 否 |
| `frozen_calc_version` | `INTEGER` | 否 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

### `mart_settlement_profit_item_month`

| 列 | 类型 | 可空 |
|---|---|---|
| `id` | `CHAR(32)` | 否 |
| `store_id` | `VARCHAR(128)` | 否 |
| `item_id` | `VARCHAR(128)` | 否 |
| `bill_month` | `DATE` | 否 |
| `owner_ref` | `VARCHAR(255)` | 是 |
| `msku` | `TEXT` | 是 |
| `sales_quantity` | `NUMERIC(18, 4)` | 否 |
| `net_profit_cny` | `NUMERIC(18, 4)` | 是 |
| `gross_margin_ratio` | `NUMERIC(12, 8)` | 是 |
| `ad_scope_note` | `VARCHAR(64)` | 是 |
| `calc_version` | `INTEGER` | 否 |
| `frozen_at` | `DATETIME` | 是 |
| `sales_amount_usd` | `NUMERIC(18, 4)` | 否 |
| `platform_subsidy_usd` | `NUMERIC(18, 4)` | 否 |
| `refund_amount_usd` | `NUMERIC(18, 4)` | 否 |
| `commission_usd` | `NUMERIC(18, 4)` | 否 |
| `wfs_fulfillment_fee_usd` | `NUMERIC(18, 4)` | 否 |
| `return_fee_usd` | `NUMERIC(18, 4)` | 否 |
| `tax_withheld_usd` | `NUMERIC(18, 4)` | 否 |
| `wfs_service_fee_usd` | `NUMERIC(18, 4)` | 否 |
| `storage_fee_usd` | `NUMERIC(18, 4)` | 否 |
| `inbound_wpc_usd` | `NUMERIC(18, 4)` | 否 |
| `ad_cost_usd` | `NUMERIC(18, 4)` | 否 |
| `review_accelerator_usd` | `NUMERIC(18, 4)` | 否 |
| `disposal_loss_usd` | `NUMERIC(18, 4)` | 否 |
| `promotion_fee_usd` | `NUMERIC(18, 4)` | 是 |
| `packaging_fee_usd` | `NUMERIC(18, 4)` | 是 |
| `purchase_cost_cny` | `NUMERIC(18, 4)` | 是 |
| `head_cost_cny` | `NUMERIC(18, 4)` | 是 |
| `goods_cost_usd` | `NUMERIC(18, 4)` | 是 |
| `gross_profit_usd` | `NUMERIC(18, 4)` | 是 |
| `gross_profit_cny` | `NUMERIC(18, 4)` | 是 |
| `net_profit_share_cny` | `NUMERIC(18, 4)` | 是 |
| `fx_rate` | `NUMERIC(18, 8)` | 是 |
| `fx_month` | `DATE` | 是 |
| `fx_status` | `VARCHAR(16)` | 否 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

索引：`ix_mart_settlement_profit_item_month_owner (bill_month, owner_ref)`

### `mart_settlement_order_review`

| 列 | 类型 | 可空 |
|---|---|---|
| `id` | `CHAR(32)` | 否 |
| `line_key` | `VARCHAR(512)` | 否 |
| `row_kind` | `VARCHAR(16)` | 否 |
| `store_id` | `VARCHAR(128)` | 否 |
| `bill_month` | `DATE` | 否 |
| `platform_order_no` | `VARCHAR(255)` | 是 |
| `order_item_no` | `VARCHAR(128)` | 是 |
| `item_id` | `VARCHAR(128)` | 是 |
| `owner_ref` | `VARCHAR(255)` | 是 |
| `status` | `VARCHAR(16)` | 否 |
| `reasons` | `JSONB` | 否 |
| `amount_usd` | `NUMERIC(18, 4)` | 是 |
| `profit_usd` | `NUMERIC(18, 4)` | 是 |
| `version` | `INTEGER` | 否 |
| `first_reviewed_by` | `VARCHAR(255)` | 是 |
| `first_reviewed_at` | `DATETIME` | 是 |
| `final_reviewed_by` | `VARCHAR(255)` | 是 |
| `final_reviewed_at` | `DATETIME` | 是 |
| `calc_version` | `INTEGER` | 否 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

索引：`ix_mart_settlement_order_review_order (store_id, bill_month, platform_order_no, order_item_no)`；`ix_mart_settlement_order_review_status (bill_month, status)`

### `mart_settlement_reconcile_store_month`

| 列 | 类型 | 可空 |
|---|---|---|
| `id` | `CHAR(32)` | 否 |
| `store_id` | `VARCHAR(128)` | 否 |
| `bill_month` | `DATE` | 否 |
| `settlement_total_usd` | `NUMERIC(18, 4)` | 否 |
| `order_level_total_usd` | `NUMERIC(18, 4)` | 否 |
| `unassigned_pending_usd` | `NUMERIC(18, 4)` | 否 |
| `diff_usd` | `NUMERIC(18, 4)` | 否 |
| `ad_daily_vs_settlement_diff_usd` | `NUMERIC(18, 4)` | 是 |
| `cross_month_disposal_fee_usd` | `NUMERIC(18, 4)` | 是 |
| `inbound_freight_lx_vs_settlement_diff_usd` | `NUMERIC(18, 4)` | 是 |
| `result_hash` | `VARCHAR(64)` | 是 |
| `status` | `VARCHAR(24)` | 否 |
| `fx_status` | `VARCHAR(16)` | 否 |
| `calc_version` | `INTEGER` | 否 |
| `frozen_at` | `DATETIME` | 是 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

### `mart_inventory_movement_month`

| 列 | 类型 | 可空 |
|---|---|---|
| `id` | `CHAR(32)` | 否 |
| `store_id` | `VARCHAR(128)` | 否 |
| `item_id` | `VARCHAR(128)` | 否 |
| `month` | `DATE` | 否 |
| `category` | `VARCHAR(16)` | 否 |
| `quantity` | `NUMERIC(18, 4)` | 否 |
| `goods_value_cny` | `NUMERIC(18, 4)` | 是 |
| `goods_value_usd` | `NUMERIC(18, 4)` | 是 |
| `disposal_fee_usd` | `NUMERIC(18, 4)` | 是 |
| `calc_version` | `INTEGER` | 否 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

### `manual_settlement_order_adjustments`

| 列 | 类型 | 可空 |
|---|---|---|
| `id` | `CHAR(32)` | 否 |
| `line_key` | `VARCHAR(512)` | 否 |
| `store_id` | `VARCHAR(128)` | 否 |
| `bill_month` | `DATE` | 否 |
| `kind` | `VARCHAR(16)` | 否 |
| `payload` | `JSONB` | 否 |
| `reason` | `TEXT` | 否 |
| `status` | `VARCHAR(16)` | 否 |
| `version` | `INTEGER` | 否 |
| `revoked_by` | `VARCHAR(255)` | 是 |
| `revoked_at` | `DATETIME` | 是 |
| `revoke_reason` | `TEXT` | 是 |
| `actor_id` | `VARCHAR(255)` | 否 |
| `actor_role` | `VARCHAR(64)` | 否 |
| `acted_at` | `DATETIME` | 否 |
| `request_id` | `VARCHAR(128)` | 否 |
| `idempotency_key` | `VARCHAR(128)` | 否 |
| `before` | `JSONB` | 是 |
| `after` | `JSONB` | 是 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

索引：`ix_manual_settlement_adjustments_line (line_key, status)`；`ix_manual_settlement_adjustments_month (store_id, bill_month)`

### `manual_settlement_review_actions`

| 列 | 类型 | 可空 |
|---|---|---|
| `id` | `CHAR(32)` | 否 |
| `line_key` | `VARCHAR(512)` | 否 |
| `store_id` | `VARCHAR(128)` | 否 |
| `bill_month` | `DATE` | 否 |
| `stage` | `VARCHAR(8)` | 否 |
| `decision` | `VARCHAR(8)` | 否 |
| `comment` | `TEXT` | 是 |
| `line_version` | `INTEGER` | 否 |
| `actor_id` | `VARCHAR(255)` | 否 |
| `actor_role` | `VARCHAR(64)` | 否 |
| `acted_at` | `DATETIME` | 否 |
| `request_id` | `VARCHAR(128)` | 否 |
| `idempotency_key` | `VARCHAR(128)` | 否 |
| `before` | `JSONB` | 是 |
| `after` | `JSONB` | 是 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

索引：`ix_manual_settlement_review_line (line_key, acted_at)`

### `manual_settlement_month_close`

| 列 | 类型 | 可空 |
|---|---|---|
| `id` | `CHAR(32)` | 否 |
| `store_scope` | `VARCHAR(128)` | 否 |
| `bill_month` | `DATE` | 否 |
| `status` | `VARCHAR(16)` | 否 |
| `frozen_calc_version` | `INTEGER` | 是 |
| `snapshot_totals` | `JSONB` | 是 |
| `reopen_reason` | `TEXT` | 是 |
| `version` | `INTEGER` | 否 |
| `actor_id` | `VARCHAR(255)` | 否 |
| `actor_role` | `VARCHAR(64)` | 否 |
| `acted_at` | `DATETIME` | 否 |
| `request_id` | `VARCHAR(128)` | 否 |
| `idempotency_key` | `VARCHAR(128)` | 否 |
| `before` | `JSONB` | 是 |
| `after` | `JSONB` | 是 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

### `cfg_net_profit_allocation`

| 列 | 类型 | 可空 |
|---|---|---|
| `id` | `CHAR(32)` | 否 |
| `effective_month` | `DATE` | 否 |
| `fixed_cny` | `NUMERIC(18, 4)` | 否 |
| `excluded_owner_ids` | `JSONB` | 否 |
| `version` | `INTEGER` | 否 |
| `updated_by` | `VARCHAR(255)` | 否 |
| `request_id` | `VARCHAR(128)` | 否 |
| `reason` | `TEXT` | 是 |
| `created_at` | `DATETIME` | 否 |
| `updated_at` | `DATETIME` | 否 |

## 回滚

`alembic downgrade 20261102_0071_skill_lib` 删除以上 16 张表。上线后如 manual_ 表已有数据，回滚前先导出备份（PRP §13）。

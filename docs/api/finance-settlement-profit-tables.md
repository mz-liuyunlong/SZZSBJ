# 结算利润 V3 表结构（PR-1）

对应 PRP：`PRPs/finance-settlement-profit-v3.md` §6.2；迁移 `20261125_0096_settlement_profit_v3_tables`；模型 `backend/app/modules/settlement_profit/models.py`。

PR-1 只建表，不写同步、计算和接口。表都从空开始；同步任务（PR-2）默认 `is_enabled=false`、`schedule_enabled=false`，开启、回填、定时各要业务负责人书面授权一次。

## 通用约定

- 分层：RAW（既有 `ods_api_raw_*`）→ ODS → FACT → MART。`manual_` 只覆盖计算结果，不写 RAW / ODS / FACT；`cfg_` 是财务设置。
- 金额 `numeric(18,4)`，列名带币种后缀（`_usd` / `_cny`）或配 `currency_code`。有折算的行同时存 `fx_rate numeric(18,8)`、`fx_month`、`fx_status`（`final` / `missing`），数据库约束 `final` 时必须有 `fx_rate`、`missing` 时必须为空，不做兜底。汇率只取 `fact_lingxing_fx_rate`。缺汇率时为空的是**折算出来的列**：订单行的 `cost_total_usd`（货本 ¥→$）、店铺级项目的 `amount_cny`、商品月的 `cost_total_usd`、`settlement_profit_cny`、`company_cost_cny`、`net_profit_cny`；人民币原值（`purchase_cny`、`head_cny`、`last_leg_cny`、`cost_total_cny`）和美元原值照常保留。
- 件数列（`quantity`、`delivery_num`、`wfs_inventory_qty`）单独定义件数类型 `numeric(18,4)`，不复用金额类型。
- 外部 ID（订单号、GTIN、item_id、店铺 ID、发货单号、出库单号、`period_key`）一律字符串。
- `period_key` = 回款对账的期（`mart_walmart_bill_periods.report_key`）。`bill_month`、`effective_month` 一律是当月 1 号（CHECK 约束）。
- FACT / MART 行带 `calc_version`、`content_hash`（同一输入重算 hash 不变则不写新版本），以及结账冻结三列 `frozen_at`、`frozen_by`、`frozen_calc_version`。
- `manual_` 表引用稳定业务键 `line_key`（`varchar(320)`），不引用会随重算变化的 UUID：
  - 订单行：店铺 + reportKey + 订单号 + 订单行号 + GTIN；
  - 店铺级项目：店铺 + 账单月 + source_kind + source_ref；
  - 对平差额行：店铺 + 期 + `reconcile_diff`。
- 写操作留痕：`actor_id`、`actor_role`、`request_id`；需要乐观锁的行带 `version`；POST 写入的 manual 表有 `idempotency_key`（唯一）。
- 表之间不建外键；ODS 只存 `source_run_id`、`source_raw_request_ref_id`，不约束到 RAW 表。

## ODS（同步落地，PR-2 写入）

前三张由 PR-2 的三个 Integration Sync 处理器写入（`finShippingList` / `finShippingDetail` / `finWmsOutboundOrders`，默认关闭；上线步骤、口径与错误码见 `docs/runbooks/finance-settlement-profit-sync.md`）。公共列：`source_run_id`、`source_raw_request_ref_id` 指向当次原始页；`synced_at` 每次同步都更新；`row_hash` 是脱敏后原始行的 sha256，发货单表的 `updated_at` 只在 `row_hash` 变化时更新（明细同步靠它判断要不要重拉）；`raw_row` 是脱敏后的原始行（出库单去掉 `product_info`，明细在 JSON 里）。

| 表 | 业务键 | 内容 |
|---|---|---|
| `ods_lingxing_fin_shipping_lists` | source_account_ref, store_id, shipping_list_code | 领星多平台发货单（shippingList v2）当前状态：状态、物流商 id / 名称、渠道、头程费用类型、发货时间。与 PMC 的 `ods_lingxing_wfs_shipping_lists`（每次运行一份快照）不同名、互不依赖 |
| `ods_lingxing_fin_shipping_detail_items` | source_account_ref, shipping_list_code, msku | 发货单明细（shippingDetail），一行 = 发货单 × MSKU：`purchase_price` 采购价、`head_stock_price` 出库头程、`per_firstlet_cost` 头程费用（= `per_firstlet_actual`，已含 `other_cost`）、`per_tax` 税、`wfs_stock_price` 单位成本（¥）、`logistics_way`、`logistics_provider_id`、`value_source` |
| `ods_lingxing_fin_wms_outbound_orders` | source_account_ref, store_id, outbound_order_no | 销售出库单（wmsOrderList）：平台订单号、物流费用、币种、出库时间；非 WFS 自发货订单的尾程来源 |
| `ods_walmart_review_accelerator_snapshots` | source_account_ref, store_id, snapshot_date, item_id | 评价加速器报名清单快照（云函数 POST items，翻 scrollId）：SKU、状态、累计评论数 `reviews_collected`、报名时间、类目；只当分摊权重用 |

ODS 公共列：`synced_at`、`row_hash`、`raw_row`（原始行 JSON）。

## FACT（计算任务写入）

| 表 | 业务键 | 内容 |
|---|---|---|
| `fact_settlement_order_lines` | store_id, period_key, calc_version, line_key | 订单审核的订单行，一期一行一订单行。`line_kind`：sale / refund / mcf；`fulfillment_type`：wfs / seller。收入与订单费用（USD，结算单口径）、广告分摊（只展示）、货本三项（CNY：采购、头程、尾程；WFS 订单的尾程 = 配送费，只展示、不计入 `cost_total_cny`）、`cost_sources`（可多段）、`reasons`（待审原因）、`auto_passed`；`is_current` 标当前版本，同店同期同一 `line_key` 只能有一个当前版本（部分唯一索引） |
| `fact_settlement_store_month_items` | store_id, bill_month, source_kind, source_ref | 店铺级项目：`review_accelerator`、`discount_back`（WFS 费用返还，不分摊）、`transfer_fee`、`mcf`、`storage_fee`、`other_wfs_service`、`company_cost`，以及待指定 `unassigned_bill`（来自结算单行，参与对平）/ `unassigned_wfs`（来自 WFS 费用表，不参与对平但挡结账）。`allocation` 存分到 ItemID 的结果，`assign_status`、`review_status`、`version` |
| `fact_settlement_post_close_diffs` | store_id, bill_month, line_key, detected_at | 结账后源数据变化：旧值 / 新值，不改冻结数；状态 open / acknowledged / resolved_by_unlock |

## MART（计算任务写入，页面读取）

| 表 | 业务键 | 内容 |
|---|---|---|
| `mart_settlement_profit_item_month` | store_id, item_id, bill_month | 结算利润：店铺 × ItemID × 账单月，PRP §0.3 各列（收入、费用、仓储、调拨、MCF、评价加速器、其他 WFS 服务费、弃置损耗、包装费、广告 SP / SB / SV、SEM、货本），结算利润（USD / CNY）、公司级费用分摊、纯利；`flags` 记标注（如仓储报表缺当期、调拨按销售件数分） |
| `mart_settlement_order_review` | store_id, period_key, line_key | 订单审核页的行：`row_kind` = order / store_item / reconcile_diff；`review_status`（pending / auto / first_passed / final_passed / rejected）、初审 / 终审人与时间、`version` |
| `mart_settlement_reconcile_store_period` | store_id, period_key | 每店每期对平（PRP §8.10）：结算单总额与各组成部分、差额、`status`（ok / reconcile_failed / unassigned_pending），以及只列差异不计入总额的几项（WFS 明细 vs 结算单、入库运输费、广告、公司收入） |
| `mart_settlement_no_order_flags` | store_id, item_id, bill_month | 无订单标记（PRP §8.9）：连续无单月数、最后订单日、WFS 库存、累计仓储费、弃置损耗；只给财务分析用 |

## MANUAL（财务操作）

| 表 | 键 | 内容 |
|---|---|---|
| `manual_settlement_cost_entries` | id；同一 店铺 × MSKU × 范围 只能有一条未撤销的录入（部分唯一索引；`scope_ref` 由数据库约束必须等于 `shipping:<发货单号>` 或 `outbound:<出库单号>`，拼错被拒） | 录成本 / 确认：范围 = MSKU × 发货单，或 MSKU × 出库单，二选一（CHECK）；`entry_kind` confirm / override（override 必须写原因）；`prefilled` 存当时领星预填值；初审 / 终审状态、`version`、撤销信息；不回写领星 |
| `manual_settlement_sem_month` | store_id, item_id, bill_month | SEM 月值（旧系统下线前人工导入） |
| `manual_settlement_order_adjustments` | id | 调整：`kind` = amount（改金额，必须带金额）/ assign_item（指定商品，必须带 ItemID）/ note；原因必填、可撤销、`version`、初审 / 终审状态 |
| `manual_settlement_review_actions` | id | 初审 / 终审 / 退回记录，只增不改；`target_kind` = order_line / store_item / cost_entry / adjustment；退回必须写意见；存 before / after |
| `manual_settlement_month_close` | store_id, bill_month, seq | 店铺 × 账单月 结账 / 解锁记录，只增不改，最后一条决定当前状态；解锁必须写原因；记冻结的 calc_version 与合计 |

## CFG（财务主管维护）

| 表 | 键 | 内容 |
|---|---|---|
| `cfg_finance_settlement_settings` | setting_key, effective_month | PRP §0.5 六项（评价加速器单价公式参数、公司级费用分摊参数、固定成本来源优先级、评价加速器快照频率、无订单提示月数、账单月分界日）+ WFS 承运商清单 `wfs_carrier_provider_ids`；`value` 为 JSON；按生效月取值。默认值只在生产库配置，仓库里没有数字和人名 |
| `cfg_finance_owner_tag_rules` | tag_name | Listing 标签 → 负责人；只存数据库，仓库里不出现标签名和人名 |

## 回滚

迁移的 downgrade 先检查这 18 张表，任何一张有数据就报错（`rollback blocked`），不执行 DELETE / TRUNCATE。表都为空时才删表。生产环境要改结构一律写新的前向迁移。

# 国内仓首期 6 张表

日期：2026-10-19。状态：字段已确认，供本地核对。本文不代替 Alembic 迁移，不授权在生产库执行。

可执行脚本：`docs/delivery/domestic-warehouse-phase1-tables.sql`。

沿用现有表，本次不建：`ods_lingxing_receipt_orders`、`ods_lingxing_receipt_order_items`、`gov_integration_sync_runs`、`ods_api_raw_request_refs`。页面读模型、打包、OWS、对账也不建。

4 张 ODS 每次同步追加一行，领星原文放在 `payload_json`。外部编号用 `varchar(64)`，领星原时间用 `varchar(32)`，数量用整数。到仓日只看第 5 张表的 `received_business_date`，由收货单 `receive_time` 按台北日历日算出。

## 1. `ods_lingxing_domestic_warehouses`

仓库列表。一次同步里，同一账号的同一个仓库只出现一次。

治理字段：`id`、`run_id`、`raw_request_ref_id`、`source_account_ref`、`source_item_ordinal`、`payload_json`、`observed_at`、`created_at`。

| 字段 | 类型 | 含义 |
|---|---|---|
| source_warehouse_id | varchar(64) | 仓库 ID |
| warehouse_name | varchar(255) | 仓库名 |
| warehouse_type | varchar(64) | 领星仓库类型 |
| sub_type | varchar(64) | 领星仓库子类型 |

## 2. `ods_lingxing_domestic_inventory`

库存明细，每日全量快照。治理字段与第 1 张表相同。

| 字段 | 类型 | 含义 |
|---|---|---|
| source_warehouse_id | varchar(64) | 仓库 |
| product_id | varchar(64) | 产品 ID |
| sku | varchar(255) | SKU |
| seller_id | varchar(64) | 店铺 |
| fnsku | varchar(64) | FNSKU |
| product_total | integer | 库存总量 |
| product_valid_num | integer | 可用量 |
| product_bad_num | integer | 不良量 |
| product_qc_num | integer | 待质检量 |
| product_lock_num | integer | 锁定量 |
| good_lock_num | integer | 良品锁定量 |
| quantity_receive | integer | 接口上的收货量，不代替收货单 |

## 3. `ods_lingxing_domestic_batches`

批次明细。`purchase_in_time` 只留作核对，不算到仓日。治理字段与第 1 张表相同。

| 字段 | 类型 | 含义 |
|---|---|---|
| source_warehouse_id | varchar(64) | 仓库 |
| warehouse_name | varchar(255) | 仓库名 |
| batch_no | varchar(64) | 批次号 |
| source_batch_no | varchar(64) | 来源批次号 |
| order_sn | varchar(64) | 入库单号 |
| batch_type | integer | 批次类型 |
| batch_type_name | varchar(64) | 类型名称 |
| sku | varchar(255) | SKU |
| product_id | varchar(64) | 产品 ID |
| product_name | text | 产品名 |
| store_id | varchar(64) | 店铺 |
| store_name | varchar(255) | 店铺名 |
| msku | varchar(255) | MSKU |
| fnsku | varchar(64) | FNSKU |
| total_qty | integer | 总量 |
| balance_num | integer | 余额 |
| good_num | integer | 良品 |
| bad_num | integer | 不良 |
| qc_num | integer | 质检 |
| purchase_order_sns | text | 采购单号，可能多个 |
| purchase_in_time | varchar(32) | 领星入库时间原文 |
| batch_time | varchar(32) | 批次时间原文 |

## 4. `ods_lingxing_domestic_inventory_events`

库存流水。`statement_id` 可空，不做业务唯一约束。治理字段与第 1 张表相同。

| 字段 | 类型 | 含义 |
|---|---|---|
| statement_id | varchar(64) | 流水行 ID |
| source_warehouse_id | varchar(64) | 仓库 |
| warehouse_name | varchar(255) | 仓库名 |
| order_sn | varchar(64) | 本单号 |
| ref_order_sn | varchar(64) | 关联单号 |
| sku | varchar(255) | SKU |
| product_id | varchar(64) | 产品 ID |
| seller_id | varchar(64) | 店铺 |
| fnsku | varchar(64) | FNSKU |
| event_type | integer | 流水类型 |
| sub_type | integer | 流水子类型 |
| product_good_num | integer | 良品数量 |
| product_bad_num | integer | 不良数量 |
| product_qc_num | integer | 质检数量 |
| opt_time | varchar(32) | 流水时间原文 |
| remark | text | 备注 |

## 5. `dwd_domestic_receipt_batch`

当前版本的实际收货批次。一行是一张收货单上的一行。`source_ods_id` 只存 UUID，不加外键。

| 字段 | 类型 | 含义 |
|---|---|---|
| id | uuid | 主键 |
| source_account_ref | varchar(128) | 领星账号 |
| source_run_id | uuid | 来源同步 |
| source_ods_id | uuid | 来源收货 ODS 行 |
| source_observed_at | timestamptz | 来源观测时间 |
| provider_update_time | varchar(32) | 领星更新时间原文 |
| builder_version | varchar(64) | 计算版本 |
| created_at / updated_at | timestamptz | 写入、更新时间 |
| receipt_order_sn | varchar(64) | 收货单号 |
| line_ordinal | integer | 收货行号 |
| purchase_order_sn | varchar(64) | 采购单号 |
| source_warehouse_id | varchar(64) | 仓库 |
| sku | varchar(255) | SKU |
| received_qty | integer | 实收数量 |
| receive_time | varchar(32) | 收货时间原文 |
| received_business_date | date | 台北日历日，在仓天数用这个 |

唯一约束：`(source_account_ref, receipt_order_sn, line_ordinal)`。

## 6. `dwd_domestic_receipt_batch_link`

收货行和库存批次的当前对应关系。对不上时 `mapping_status` 为 `unresolved`。

| 字段 | 类型 | 含义 |
|---|---|---|
| id | uuid | 主键 |
| source_account_ref | varchar(128) | 领星账号 |
| receipt_batch_id | uuid | 指向第 5 张表 |
| batch_order_sn | varchar(64) | 入库单号 |
| batch_no | varchar(64) | 批次号 |
| store_id | varchar(64) | 店铺 |
| mapped_qty | integer | 对上的数量 |
| mapping_status | varchar(32) | `unresolved` 或 `matched` |
| mapping_method | varchar(64) | 对应方式 |
| created_at / updated_at | timestamptz | 写入、更新时间 |

## 在 Navicat 执行

1. 打开 Navicat，连接本地或开发 PostgreSQL。不要选生产库。
2. 双击该连接，点开目标数据库，看窗口标题或左上角当前库名，确认是开发库。
3. 菜单选「查询」→「新建查询」。
4. 在查询窗口选「文件」→「打开」，打开 `docs/delivery/domestic-warehouse-phase1-tables.sql`。编码用 UTF-8。
5. 点「运行」。6 条建表和 3 条索引应全部成功。
6. 在左侧表列表点刷新。应能看到这 6 张表：
   - `ods_lingxing_domestic_warehouses`
   - `ods_lingxing_domestic_inventory`
   - `ods_lingxing_domestic_batches`
   - `ods_lingxing_domestic_inventory_events`
   - `dwd_domestic_receipt_batch`
   - `dwd_domestic_receipt_batch_link`
7. 右键其中一张表，选「设计表」，对照本文字段。

若提示表已经存在，说明这段 SQL 已经跑过，不要再执行。若提示 `gov_integration_sync_runs` 或 `ods_api_raw_request_refs` 不存在，说明当前库还不是本项目的开发库。

这次手工建表不会写入 `alembic_version`。以后用 Alembic 正式迁移时，要先处理这 6 张已经存在的表，避免重复创建。

## 四条 ODS 一次性全量同步（CLI）

与采购 Gate 2 相同门禁：`APP_ENV=production`、`LINGXING_ENABLE_REAL_CALLS=true`、治理行 `outbound_enabled` + sync config `is_enabled`（非 schedule）。脚本不会自动 bootstrap 或打开外呼。

1. Bootstrap（仅元数据，默认关闭）：`bootstrap_pmc_domestic_governance.py`（`PMC_DOMESTIC_GOVERNANCE_BOOTSTRAP_AUTHORIZED` + `PMC_DOMESTIC_SOURCE_ACCOUNT_REF`）。
2. 负责人在库内对上述四个 `interface_key` 启用外呼与 config。
3. 全跑四条（顺序：仓库 → 库存明细 → 批次明细 → 批次流水）：

```text
PMC_DOMESTIC_ONE_TIME_RUN_AUTHORIZED=true
PMC_DOMESTIC_SOURCE_ACCOUNT_REF=<账号>
PMC_DOMESTIC_INTERFACE_KEY=all
PMC_DOMESTIC_WINDOW_START / PMC_DOMESTIC_WINDOW_END   # 仅批次流水；省略则默认近 90 天
uv run python scripts/run_pmc_domestic_once.py
```

4. 看板 DWD 仍来自收货 ODS：先跑采购 `purchaseReceiptOrderList`，再 `publish_pmc_domestic_dwd.py`。

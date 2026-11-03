# ODS · `ods_lingxing_wfs_cost_valuation_flow`（领星 WFS 成本计价流水）

- PRP：`PRPs/wfs-inventory-claim.md` §7.1–§7.3（库存索赔 PR 1）
- 数据源决策：`docs/data-sources/decisions/warehouse-wfs-inventory-claim-decision.md`
- 接口契约：`docs/integrations/lingxing/contracts/inventory-lx-8437ad0bcb9e.md`（`LX-8437AD0BCB9E`）
- 迁移：`backend/alembic/versions/20261103_0073_wfs_cost_valuation_flow.py`（down_revision `20261103_0072_fin_settle_profit_v2`）
- 模型：`backend/app/modules/warehouse_wfs/inventory_flow_models.py`
- 同步：`wfsCostValuationFlow` / `lingxing.wfs.cost_valuation_flow.v1`（`backend/app/modules/integration_sync/handlers/lingxing_wfs_cost_valuation_sync.py`）

本表是这个领星接口在全仓库唯一的 ODS。本 PR 不提供 HTTP 读接口（PR 2 再做）。

## 写入方与读方

| 角色 | 说明 |
|---|---|
| 写入方 | 只有上面的同步 handler。默认关闭：接口 `outbound_enabled=false`，配置 `is_enabled=false`、`schedule_enabled=false`。首次开启和补历史数据须 rocky 书面同意 |
| 读方 | 库存索赔（PR 2，读时计算）；结算利润 V2（只读 `is_current = true`，只存本表行 id，不建外键） |

## 行身份与当前行

- 唯一键：`(raw_request_ref_id, source_item_ordinal)`，即「哪一页请求的第几行」。
- `serial_number` 只用于追溯，**不唯一**：同一次拉取里会重复，跨批次还会指向别的商品。
- 每次同步覆盖一个出入库日期窗口（`dateType = 0`）和全部店铺，不过滤 businessType。
- 整段替换：全部页成功、且行数等于 `data.page.total` 之后，在一个事务里把窗口内旧的 `is_current = true` 行改成 false，并写 `superseded_by_run_id`；同时把新批次的行置为 true。
- 失败批次（页失败、total 变化、行数不符、行无法解析）：批次标 failed，已暂存的行保持 `is_current = false`，旧数据不动。
- 每次同步行 id 都会换新。下游按 `is_current = true` 取数；按结算日期取时，先过滤 `is_current` 再看 `settlement_date`。
- 同账号单批次：运行表检查加 PostgreSQL advisory lock；冲突时批次标 failed，错误码 `SYNC_WFS_FLOW_CONCURRENT_RUN`，不发任何请求。

## 主要列

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | uuid | 行 id |
| `run_id` / `raw_request_ref_id` / `source_item_ordinal` | uuid / uuid / int | 批次、页、页内顺序 |
| `source_account_ref` | varchar(128) | 领星账号引用 |
| `window_start` / `window_end` | date | 批次窗口 |
| `is_current` / `superseded_by_run_id` | bool / uuid | 当前有效 / 被哪个批次替换 |
| `serial_number` | varchar(32) | 追溯用，不唯一 |
| `date_local` / `business_date` / `settlement_date` | timestamp / date / date | dateLocal 原值、其日期、date1 的日期（时区待探测） |
| `store_code` / `store_id` / `store_mapping_status` | varchar | sellerName 前 6 位；对照得到的系统店铺；mapped / unmapped |
| `business_type` / `business_name` / `business_desc` | varchar / text | 原始类型字符串 |
| `quantity` | int | 带符号 |
| `msku` / `gtin` / `local_sku` / `business_number` / `order_number` / `cost_source` | text | |
| 六个金额列 | numeric(18,4) | 字符串转 Decimal |
| `currency_code` | varchar(3) | 待探测，确认前为 NULL |
| `row_hash` | varchar(64) | 除 imageUrl 外的业务字段 sha256 |
| `payload_json` | jsonb | 原始一行（sellerName 原值只在这里） |

## 店铺对照

来源 `dim_lingxing_stores`（同一 `source_account_ref`）：先按记录 `sid` 唯一命中；否则按 `store_name` 前 6 位等于 `store_code` 唯一命中；都不唯一命中时 `store_id` 为 NULL、`store_mapping_status = 'unmapped'`，行照样入库。页面只对全店铺权限可见，标「店铺未对照」（PR 2/3）。

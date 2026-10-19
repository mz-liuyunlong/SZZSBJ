# 国内仓领星 ODS 四表（正式纳入）

状态：2026-10-19。Alembic：`20261019_0047_domestic_warehouse_ods`（接在 `20261019_0046_operation_logs` 之后）。

## 背景：生产库如何出现这四张表

| 项目 | 说明 |
|------|------|
| 创建方式 | 2026-10 在 Navicat 对目标应用数据库执行手工 SQL（源自国内仓首期核对脚本，**仅含 ODS 四表部分**），**未**写入 `alembic_version` |
| Git `main`（本 PR 前） | 无这四张表的 Alembic 迁移与 ORM |
| 生产 `alembic_version` | 已为 `20261019_0046_operation_logs`；四表存在但版本链未记录 ODS |
| 当前数据 | 以生产库 `select count(*)` 为准；手工建表后**默认空表**，是否已有同步行取决于是否跑过 Gate 2 domestic 任务（见 `origin/dev` 上的 handler，**尚未合并 `main`**） |

后续结构变更**只走 Alembic + PR**，禁止再在生产手工 DDL。

## 表与领星 Open API

| 表 | interface_key | Open API 路径 | 同步方式 | 行唯一性（ODS） |
|----|---------------|---------------|----------|-----------------|
| `ods_lingxing_domestic_warehouses` | `domesticWarehouseList` | `POST /erp/sc/data/local_inventory/warehouse` | Gate 2 分页追加；`gov_integration_sync_runs` + RAW | `(raw_request_ref_id, source_item_ordinal)`；同 run 内 `(run_id, source_account_ref, source_warehouse_id)` |
| `ods_lingxing_domestic_inventory` | `domesticInventoryDetails` | `POST …/inventoryDetails` | 全量快照追加 | `(raw_request_ref_id, source_item_ordinal)` |
| `ods_lingxing_domestic_batches` | `domesticBatchDetailList` | `POST …/getBatchDetailList` | 批次明细追加 | `(raw_request_ref_id, source_item_ordinal)` |
| `ods_lingxing_domestic_inventory_events` | `domesticBatchStatementList` | `POST …/getBatchStatementList` | 流水追加（日期窗 ≤90 天） | `(raw_request_ref_id, source_item_ordinal)` |

说明：浏览器地址 `https://erp.lingxing.com/api/storage/lists` **不是**本项目登记接口；仓库列表以 Open API `warehouse` 为准。

## 数据血缘（分层）

```text
领星 Open API
  → ods_api_raw_*（RAW）
  → 上表四张 ODS（payload_json 全量 + 提取列）
  → （后续任务）DWD 收货批次、批次 link、看板 API
```

批次看板列表 **不直接读** 这四张 ODS；读 `dwd_domestic_receipt_batch`（来自采购收货 ODS + 发布脚本，在 `origin/dev` 国内仓模块中，**不在本 PR 范围**）。

## Alembic 0047 行为

- **空库**：按 ORM 创建四表、约束与索引。
- **已有表（生产）**：逐列核对 `information_schema` 与 ORM（列名、类型、非空）；不一致则 **失败并中止**，不静默跳过。缺失的非唯一索引会补建。
- **不** truncate、不 drop、不改已有行。
- `downgrade` 故意 `NotImplementedError`，避免误删 append-only ODS。

参考 DDL（与 ORM 一致）：`docs/delivery/domestic-warehouse-ods-tables.sql`。

## 生产迁移（本 PR 不执行）

PR 合并并验收后，由负责人在维护窗口单独执行（示例）：

```bash
PRODUCTION_MIGRATIONS_AUTHORIZED=true uv run alembic -c alembic.ini upgrade 20261019_0047_domestic_warehouse_ods
```

预期：四表已存在时迁移 **验证通过并结束**，`alembic_version` 写入 `20261019_0047_domestic_warehouse_ods`。

## 尚未合并 `main` 的相关代码（`origin/dev`）

- 同步：`pmc_domestic_catalog.py`、`lingxing_pmc_domestic_sync.py`、`run_pmc_domestic_once.py`
- 看板 DWD/API/前端：完整 `pmc_domestic` 模块与国内仓页面

本 PR **仅**四张 ODS 的 ORM + 0047 迁移 + 文档 + 测试，便于生产结构与 Git 对齐。

# 国内仓领星 ODS 四表（正式纳入）

状态：2026-10-19。Alembic：`20261019_0047_domestic_warehouse_ods`（接在 `20261019_0046_operation_logs` 之后）。

## 背景：生产库如何出现这四张表

| 项目 | 说明 |
|------|------|
| 创建方式 | 2026-10 在 Navicat 对 `APPLICATION_DATABASE_NAME` 执行手工 SQL（源自国内仓首期核对脚本，**仅含 ODS 四表部分**），**未**写入 `alembic_version` |
| Git `main`（本 PR 前） | 无这四张表的 Alembic 迁移与 ORM |
| 生产 `alembic_version` | 已为 `20261019_0046_operation_logs`；四表存在但版本链未记录 ODS |
| 当前数据 | 以生产库 `select count(*)` 为准；手工建表后**默认空表**，是否已有同步行取决于是否跑过 Gate 2 domestic 任务 |
| `dev` 分支业务代码 | 同步 handler、DWD 发布、看板 API/前端已在 `dev`；**未**合并 `main`。DWD 与页面权限见 `20261019_0048_domestic_warehouse_dwd_and_permission` |

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

批次看板列表 **不直接读** 这四张 ODS；读 `dwd_domestic_receipt_batch`（采购收货 ODS + `publish_pmc_domestic_dwd`，在 `dev` 的 `pmc_domestic` 模块）。

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

## 表创建时间与方式（结论）

| 问题 | 结论 |
|------|------|
| 何时创建 | 约 2026-10，生产 Navicat 手工执行（脚本源自 `domestic-warehouse-phase1-tables.sql` 中 **ODS 四表** 段落） |
| 如何创建 | 手工 DDL，**未**写入 `alembic_version` |
| 是否已有同步数据 | 以生产 `select count(*) from ods_lingxing_domestic_*` 为准；未跑 domestic Gate 2 前通常为空 |
| 未提交/未合并代码 | 完整国内仓模块在 **`dev`**（sync、publisher、router、前端）；合并 `main` 前生产只会有表结构对齐（0047），不一定有同步与看板 |

## 后续同步（`dev` 已实现，合并后启用）

- 治理 bootstrap：`PMC_DOMESTIC_SYNC_INTERFACE_SPECS` / `bootstrap_pmc_domestic_governance`
- 执行：`lingxing_pmc_domestic_sync` handlers、Owner CLI（如 `run_pmc_domestic_once.py`）
- 发布后：收货 ODS → `dwd_domestic_receipt_batch` / `_link`

**结构变更** 只走 Alembic：`0047`（四 ODS adopt）→ `0048`（DWD + 页面权限，与 ODS 验收可分开执行）。

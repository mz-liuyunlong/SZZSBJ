# Pull Request

**建议标题：** `feat(pmc-domestic): 领星国内仓 ODS 四表 Alembic 0047（生产 adopt 校验）`

**Base：** `main`  
**Head：** `feat/pmc-purchase-board-columns`（相对 `main` 仅 1 commit：`45d20d7`）

**GitHub 创建：** Compare `main` ← `feat/pmc-purchase-board-columns`，将下方正文粘贴到 PR Description。

---

## 本次修改目的

将生产已存在、但 Git/`alembic_version` 未登记的**领星国内仓四张 ODS 表**正式纳入版本管理：

- ORM 定义（约束、索引与 Gate 2 治理字段一致）
- Alembic `20261019_0047_domestic_warehouse_ods`（接在 `20261019_0046_operation_logs` 之后）
- **生产兼容**：表已存在时逐列校验结构，一致则通过并补缺失非唯一索引；不一致则中止迁移
- 参考 DDL、交付说明、数据接口登记与测试

**不在本 PR：** 国内仓同步 handler、DWD/看板 API、前端页面（仍在 `origin/dev`）；**不含**采购看板业务改动。

---

## 四表结构、约束、索引与生产兼容（Reviewer 核心）

### 共同治理列（`DomesticOdsMixin`，四表相同）

| 列 | 类型 | 非空 | 说明 |
|----|------|------|------|
| `id` | `uuid` | 是 | 主键 |
| `run_id` | `uuid` | 是 | FK → `gov_integration_sync_runs.id`，`ON DELETE RESTRICT` |
| `raw_request_ref_id` | `uuid` | 是 | FK → `ods_api_raw_request_refs.id`，`ON DELETE RESTRICT` |
| `source_account_ref` | `varchar(128)` | 是 | 领星账号引用 |
| `source_item_ordinal` | `integer` | 是 | 同 RAW 响应内行序号，≥0 |
| `payload_json` | `jsonb` | 是 |  provider 原始行快照 |
| `observed_at` | `timestamptz` | 是 | 观测时间（UTC 存储） |
| `created_at` | `timestamptz` | 是 | 入库时间 |

**ODS 行语义：** 每次 succeeded 的 Gate 2 同步 run 追加写入；**不更新、不删除**历史行。业务唯一性以 `(raw_request_ref_id, source_item_ordinal)` 为 append 粒度。

---

### 1. `ods_lingxing_domestic_warehouses`

**领星接口：** `domesticWarehouseList` · `POST /erp/sc/data/local_inventory/warehouse`

| 列 | 类型 | 非空 |
|----|------|------|
| `source_warehouse_id` | `varchar(64)` | 是 |
| `warehouse_name` | `varchar(255)` | 否 |
| `warehouse_type` | `varchar(64)` | 否 |
| `sub_type` | `varchar(64)` | 否 |

**约束**

| 类型 | 定义 |
|------|------|
| PRIMARY KEY | `id` |
| UNIQUE | `(raw_request_ref_id, source_item_ordinal)` |
| UNIQUE | `(run_id, source_account_ref, source_warehouse_id)` — 同 run 内同一仓库只一行 |
| CHECK | `source_item_ordinal >= 0` |
| CHECK | `char_length(trim(source_warehouse_id)) > 0` |

**索引：** 无额外命名 B-tree（UNIQUE 约束自带索引）。

---

### 2. `ods_lingxing_domestic_inventory`

**领星接口：** `domesticInventoryDetails` · `POST …/inventoryDetails`

| 列 | 类型 | 非空 |
|----|------|------|
| `source_warehouse_id` | `varchar(64)` | 是 |
| `product_id`, `seller_id`, `fnsku` | `varchar(64)` | 否 |
| `sku` | `varchar(255)` | 否 |
| `product_total`, `product_valid_num`, `product_bad_num`, `product_qc_num`, `product_lock_num`, `good_lock_num`, `quantity_receive` | `integer` | 否 |

**约束**

| 类型 | 定义 |
|------|------|
| PRIMARY KEY | `id` |
| UNIQUE | `(raw_request_ref_id, source_item_ordinal)` |
| CHECK | `source_item_ordinal >= 0` |

**索引**

| 名称 | 列 |
|------|-----|
| `ix_ods_domestic_inventory_wh_sku` | `(source_account_ref, source_warehouse_id, sku)` |

---

### 3. `ods_lingxing_domestic_batches`

**领星接口：** `domesticBatchDetailList` · `POST …/getBatchDetailList`

| 列 | 类型 | 非空 |
|----|------|------|
| `source_warehouse_id` | `varchar(64)` | 是 |
| `warehouse_name`, `batch_type_name`, `store_name`, `msku` | `varchar(255)` 或 `64` | 否 |
| `batch_no`, `source_batch_no`, `order_sn`, `product_id`, `store_id`, `fnsku` | `varchar(64)` | 否 |
| `sku` | `varchar(255)` | 否 |
| `product_name`, `purchase_order_sns` | `text` | 否 |
| `batch_type`, 数量类字段 | `integer` | 否 |
| `purchase_in_time`, `batch_time` | `varchar(32)` | 否（provider 时间字符串） |

**约束**

| 类型 | 定义 |
|------|------|
| PRIMARY KEY | `id` |
| UNIQUE | `(raw_request_ref_id, source_item_ordinal)` |
| CHECK | `source_item_ordinal >= 0` |

**索引**

| 名称 | 列 |
|------|-----|
| `ix_ods_domestic_batches_ib_sku` | `(source_account_ref, order_sn, sku, store_id)` |

---

### 4. `ods_lingxing_domestic_inventory_events`

**领星接口：** `domesticBatchStatementList` · `POST …/getBatchStatementList`（日期窗 ≤90 天）

| 列 | 类型 | 非空 |
|----|------|------|
| `source_warehouse_id` | `varchar(64)` | 是 |
| `statement_id`, `order_sn`, `ref_order_sn`, `product_id`, `seller_id`, `fnsku` | `varchar(64)` | 否 |
| `sku` | `varchar(255)` | 否 |
| `warehouse_name` | `varchar(255)` | 否 |
| `event_type`, `sub_type`, `product_good_num`, `product_bad_num`, `product_qc_num` | `integer` | 否 |
| `opt_time` | `varchar(32)` | 否 |
| `remark` | `text` | 否 |

**约束**

| 类型 | 定义 |
|------|------|
| PRIMARY KEY | `id` |
| UNIQUE | `(raw_request_ref_id, source_item_ordinal)` |
| CHECK | `source_item_ordinal >= 0` |

**索引：** 无额外命名索引（`statement_id` **可空**，ODS 层不对业务流水号做 UNIQUE）。

---

### Alembic 0047 与生产 adopt 方案

| 组件 | 路径 / 行为 |
|------|-------------|
| 迁移 revision | `20261019_0047_domestic_warehouse_ods`，`down_revision` = `20261019_0046_operation_logs` |
| 实现 | `upgrade()` → `adopt_domestic_ods_tables(op.get_bind())` |
| 空库 | 按 ORM `CreateTable` + `CreateIndex` 顺序创建四表（warehouses → inventory → batches → events） |
| 生产已有表（Navicat 手工 DDL，与 `domestic-warehouse-ods-tables.sql` 对齐） | 对每张表：`information_schema.columns` **逐列**核对列名、PG 类型（uuid/jsonb/integer/text/varchar/timestamptz）、`NOT NULL`；一致则继续；**缺失**的 ORM 声明的非唯一索引（上表两个 `ix_*`）会 `CreateIndex` 补建 |
| 不一致 | `DomesticOdsSchemaMismatchError` → Alembic **失败**，不 stamp、不静默 `IF NOT EXISTS` |
| 数据 | **不** truncate / drop / UPDATE 已有行 |
| 未校验项（已知限制） | adopt **不**逐条比对 UNIQUE/CHECK/FK 约束名与存在性；合并前建议在 staging 用生产结构副本跑一遍 `upgrade` |
| downgrade | `NotImplementedError` |

**生产现状（合并前）：** `alembic_version` = `0046`；四表已存在但未登记 `0047`。合并后单独：

`PRODUCTION_MIGRATIONS_AUTHORIZED=true uv run alembic -c alembic.ini upgrade 20261019_0047_domestic_warehouse_ods`

**权威对照：** ORM `backend/app/modules/pmc_domestic/models.py` ≡ 参考 DDL `docs/delivery/domestic-warehouse-ods-tables.sql` ≡ 本 PR 测试中的 hand-SQL adopt 用例。

---

## 单功能开发确认

- [x] 本 PR 只处理一个功能（国内仓 ODS 结构纳入）。
- [x] 本 PR 最多只新增或修改一个页面（无页面变更）。
- [x] 本 PR 没有顺手开发其他模块。
- [x] 本 PR 没有大范围重构。
- [x] 本 PR 没有修改无关公共组件。
- [x] 如修改了共享代码，已说明原因和影响范围（见「修改文件清单」）。

---

## old-system 只读确认

- [x] 本 PR 没有修改 `old-system/`。
- [x] 本 PR 没有从 `old-system/` 直接复制代码。
- [x] 如参考了 `old-system/`，已说明读取了哪些文件（未参考）。
- [x] 如参考了 `old-system/`，已将业务规则重新设计到新系统（不适用）。

---

## 修改范围

- [ ] 前端
- [x] 后端（ORM、`domestic_ods_adopt`、Alembic env / registry）
- [x] 数据库（0047 迁移）
- [ ] Celery 后台任务
- [ ] 外部 API（仅登记 candidate 接口，无运行时调用）
- [ ] LLM 调用层
- [ ] 权限 / 操作日志
- [x] 数据来源 / 字段血缘（文档 + DATA_INTERFACE_REGISTRY）
- [ ] 财务计算
- [ ] 性能优化
- [x] 文档
- [x] 测试

---

## 组件与模块封装

- [x] 页面没有写成大文件（无页面）。
- [x] API 请求已封装（无新 HTTP API）。
- [x] 类型已独立定义（SQLAlchemy ORM）。
- [x] 后端按 Route / Schema / Service / Repository 分层（本 PR 仅 models + db adopt）。
- [x] 如新增 Shared 组件，已更新 `docs/UI_COMPONENT_CATALOG.md`（不适用）。
- [x] 如新增后端通用模块，已更新 `docs/BACKEND_MODULE_CATALOG.md`（本切片为 ODS 表注册，无新 BFF 模块目录）。

---

## 数据、财务、性能确认

- [x] 字段来源已说明（`docs/delivery/domestic-warehouse-ods-tables.md`、登记表四条 ext-lingxing-domestic-*）。
- [x] 财务公式已确认（不涉及）。
- [x] 金额币种明确（不涉及）。
- [x] 时间时区明确（ODS `observed_at` / `created_at` 为 `timestamptz` UTC 存储）。
- [x] 大表查询已分页或说明性能处理（append-only ODS，无列表 API）。
- [x] 外部 API 批量调用已考虑限流 / Celery（同步代码未在本 PR 启用）。

---

## Skill 使用确认

- [x] 本 PR 开发前已进行 Skill 自发现判断。
- [x] 本 PR 已说明本次使用了哪些 Skill 以及选择原因（项目 Rule Pack、`AGENTS.md`、feature slice、Alembic 分层标准）。
- [x] 本 PR 只读取了本次任务相关的 Skill，没有无意义全文读取全部 Skill。
- [x] 本 PR 已读取相关项目规则。
- [ ] 如涉及页面开发，已读取 `skills/feature-slice-planner/SKILL.md`（不适用）。
- [ ] 如涉及组件拆分，已读取 `skills/react-component-architect/SKILL.md`（不适用）。
- [ ] 如涉及 old-system，已读取 `skills/old-system-readonly-analyzer/SKILL.md`（不适用）。
- [x] 如涉及后端模块，已读取 `skills/backend-module-designer/SKILL.md`（ORM / 迁移边界）。
- [ ] 如涉及后台任务，已读取 `skills/background-task-designer/SKILL.md`（不适用）。
- [x] 如涉及数据血缘，已读取 `skills/data-lineage-analyzer/SKILL.md`（文档血缘说明）。
- [ ] 如涉及财务计算，已读取 `skills/financial-calculation-reviewer/SKILL.md`（不适用）。
- [ ] 如涉及性能，已读取 `skills/performance-reviewer/SKILL.md`（不适用）。

---

## API 契约

- [x] 无 API 变更。
- [ ] 有 API 变更，契约如下：

---

## 数据库变更

- [ ] 无数据库变更。
- [x] 有数据库变更，migration 文件为：`backend/alembic/versions/20261019_0047_domestic_warehouse_ods.py`

**兼容性说明：**

| 环境 | 行为 |
|------|------|
| 空库 / 本地新库 | `upgrade` 创建四表及 ORM 定义的约束、索引 |
| 生产（四表已由 Navicat 手工创建，`alembic_version` = `0046`） | `adopt_domestic_ods_tables` 对照 `information_schema` 校验列集、类型、非空；通过则写入 `0047`，可补缺失非唯一索引；**不** truncate/drop/改行 |
| 结构漂移 | 抛出 `DomesticOdsSchemaMismatchError`，迁移失败，需单独修复 DDL 后再 upgrade |
| downgrade | `NotImplementedError`（append-only ODS，禁止自动回滚删表） |

**四表：**

- `ods_lingxing_domestic_warehouses`
- `ods_lingxing_domestic_inventory`（索引 `ix_ods_domestic_inventory_wh_sku`）
- `ods_lingxing_domestic_batches`（索引 `ix_ods_domestic_batches_ib_sku`）
- `ods_lingxing_domestic_inventory_events`

参考 DDL：`docs/delivery/domestic-warehouse-ods-tables.sql`  
Runbook：`docs/delivery/domestic-warehouse-ods-tables.md`

**合并后生产操作（本 PR 不执行）：**

```bash
PRODUCTION_MIGRATIONS_AUTHORIZED=true uv run alembic -c alembic.ini upgrade 20261019_0047_domestic_warehouse_ods
```

---

## 配置 / 依赖变更

- [x] 无配置变更。
- [x] 无新增依赖。
- [ ] 有配置或依赖变更，说明如下：

---

## 测试结果

执行命令：

```bash
cd backend
uv run pytest tests/modules/pmc_domestic tests/db/test_alembic_scaffold.py -q
```

结果：

```text
15 passed, 3 skipped
```

（3 skipped：`TEST_DATABASE_URL` 未配置时的 PostgreSQL adopt 集成用例。）

Reviewer 可选：

```bash
cd backend
uv run alembic -c alembic.ini upgrade head   # 本地空库验证建表
```

如未执行测试，请说明原因：不适用（已在本地执行上述 pytest）。

---

## AI 参与说明

- [ ] 本 PR 未使用 AI。
- [x] 本 PR 使用了 AI 辅助。

AI 工具名称：Cursor Agent

AI 参与范围：

- [x] 需求拆解
- [x] 代码生成
- [x] 代码修改
- [x] 测试建议
- [x] 文档编写
- [ ] Code Review

---

## 修改文件清单（相对 `main`）

| 路径 | 说明 |
|------|------|
| `backend/alembic/versions/20261019_0047_domestic_warehouse_ods.py` | 迁移入口 |
| `backend/app/db/domestic_ods_adopt.py` | 创建 / adopt 逻辑 |
| `backend/app/modules/pmc_domestic/models.py` | 四表 ORM |
| `backend/alembic/env.py`, `backend/app/db/model_registry.py` | 元数据注册 |
| `backend/tests/modules/pmc_domestic/*` | 模型与 adopt 测试 |
| `backend/tests/db/test_alembic_scaffold.py` | head = 0047，链式断言 |
| `docs/delivery/domestic-warehouse-ods-tables.md` / `.sql` | 交付与参考 DDL |
| `docs/data-registry/DATA_INTERFACE_REGISTRY.md` | 四条 candidate 登记 |
| `docs/delivery/pull-request-domestic-warehouse-ods-0047.md` | 本 PR 说明（含四表分析） |

---

## 风险点

1. **生产手工 DDL 与 ORM 不一致**：upgrade 会失败；需对照 `.sql` 修正后再跑，禁止 `stamp` 跳过校验（除非负责人书面 runbook 例外）。
2. **adopt 不校验 UNIQUE/CHECK 名称**：仅列级类型与非空；若生产缺约束，应用层仍可能违反业务唯一性——合并前建议在 staging 对生产结构做一次 `upgrade` 演练。
3. **分支名 `feat/pmc-purchase-board-columns` 与内容不符**：历史命名；本 PR diff 仅 ODS，合并后可 rename 分支或忽略。

---

## 回滚方式

```bash
git revert 45d20d7
```

数据库：已执行 `0047` 的生产**不要**依赖 migration downgrade；回滚代码后 `alembic_version` 是否回退由 DBA/负责人按 runbook 决定（四表数据保留）。

---

## Reviewer 检查清单（摘要）

- [ ] 0047 `down_revision` = `20261019_0046_operation_logs`
- [ ] ORM 与 `domestic-warehouse-ods-tables.sql` 一致
- [ ] CI 通过（含 alembic scaffold）
- [ ] 确认 PR 无采购看板 / 国内仓 sync 代码混入
- [ ] 合并后安排生产 upgrade（非本 PR 自动执行）

# 采购看板改动记录

记录分支 `feat/pmc-purchase-board-columns` 提交 `f0e5592`（说明：采购看板前后端代码提交，2026-10-17）里的文件和数据库改动。列出这份记录时工作区没有未提交改动。

## 改过的文件

### 后端

- `backend/app/modules/pmc_purchase/calculations.py`
- `backend/app/modules/pmc_purchase/gate3_models.py`
- `backend/app/modules/pmc_purchase/publisher.py`
- `backend/app/modules/pmc_purchase/refresh.py`
- `backend/app/modules/pmc_purchase/repository.py`
- `backend/app/modules/pmc_purchase/schemas.py`
- `backend/app/modules/pmc_purchase/service.py`
- `backend/alembic/versions/20261017_0043_purchase_board_listing_item_source.py`
- `backend/tests/modules/pmc_purchase/test_calculations.py`
- `backend/tests/modules/pmc_purchase/test_publisher.py`
- `backend/tests/modules/pmc_purchase/test_read_service.py`
- `backend/tests/modules/pmc_purchase/test_refresh.py`
- `backend/tests/modules/pmc_purchase/test_router.py`

### 前端

- `frontend/src/pages/pmc/purchase-board/PurchaseBoardPage.tsx`
- `frontend/src/pages/pmc/purchase-board/PurchaseBoardPage.css`
- `frontend/src/pages/pmc/purchase-board/PurchaseBoardPage.test.tsx`
- `frontend/src/pages/pmc/purchase-board/purchaseBoardApi.ts`
- `frontend/src/pages/pmc/purchase-board/purchaseBoardApi.test.ts`
- `frontend/src/pages/pmc/purchase-board/purchaseBoardQueries.ts`
- `frontend/src/pages/pmc/purchase-board/purchaseBoardTypes.ts`
- `frontend/src/pages/pmc/purchase-board/purchaseBoardDisplay.tsx`
- `frontend/src/pages/pmc/purchase-board/components/PurchaseBoardCells.tsx`
- `frontend/src/pages/pmc/purchase-board/components/PurchaseBoardSummaryCards.tsx`
- `frontend/src/pages/pmc/purchase-board/components/PurchaseBoardTable.tsx`
- `frontend/src/pages/pmc/purchase-board/components/PurchaseOrderDetailModal.tsx`
- `frontend/src/components/report-table/ManagementStatCards.tsx`
- `frontend/src/components/report-table/ManagementStatCards.css`

### 文档

- `docs/api/pmc-purchase-api.md`
- `docs/business-rules/pmc-purchase-rules.md`
- `docs/page-specs/pmc-purchase-board.md`
- `docs/runbooks/production-pmc-purchase-gate3.md`
- `docs/runbooks/production-pmc-purchase-sync.md`
- `docs/sop/pmc/purchase-board.md`

同一次提交还带了与采购看板无关的迁移：`backend/alembic/versions/20261017_0042_approval_rbac_backfill.py`。它改的是运营计划表 `ops_operation_plan_import_batches` 和权限表 `app_permissions`。

## 数据库表

### 结构

采购看板迁移 `20261017_0043` 只改 `dws_purchase_board` 的检查约束 `ck_dws_purchase_board_item_id_source`，让 ItemID 来源可以是 `from_listing`。没有新建表，也没有加列。

### 数据

对账号 `primary` 做过 DWD 发布和 DWS 刷新，写过这些表：

- `dwd_purchase_plan`
- `dwd_purchase_order`
- `dwd_purchase_order_line_item`
- `dws_purchase_board`
- `dws_purchase_sku_cycle`
- `dws_purchase_pending`
- `gov_parse_jobs`
- `gov_data_lineage`

列表接口 `GET /api/pmc/purchase/board` 只读 `dws_purchase_board`。

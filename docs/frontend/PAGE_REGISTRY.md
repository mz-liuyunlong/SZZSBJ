# Frontend Page Registry

Registry Status: `draft; approved only after owner review and merge`

| Page Key | Page Name | 一级导航 | 二级导航 | Route | Page Status | Components Used | Backend API | Read Model | Permission Key | PRP | PR | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `pmc_purchase_board` | 采购看板 | PMC | 采购看板 | `/pmc/purchase-board` | `testing` / `api_connected`（只读） | PageShell, ManagementStatCards, ReportTableShell, CommittedSearch/ConnectedSearch, ReportFacetSelect, ResetButton, RuntimeColumnConfigDrawer, ResizableColumnTitle, cells (CopyableTextCell/MoneyCell/WalmartItemLink), StatusTag, EmptyState, RequestLoadingOverlay | `GET /api/pmc/purchase/board`, `/board/summary`, `/orders/{order_sn}`, `/plans/pending`；负责人选项 `GET /api/product-management/options`(owners) | `dws_purchase_board`, `dws_purchase_sku_cycle`, `dws_purchase_pending`, `dwd_purchase_plan`（经后端） | `pmc:purchase:read`（后端键；前端仅元数据） | `PRPs/pmc-purchase-board.md` Gate 4a | TBD | 无导出/推送/写操作；店铺下拉待 options 接口（Rocky 2026-09-24 ①）；交期修正 Modal = Gate 4b；ItemID 修正 Modal 已取消（#144）；无 Playwright（仓库尚无 test:e2e），故不标 ready |

## Rules

- 只登记有 navigation、route、PRP 或实现证据的页面；未知写 TBD，不猜测。
- `planned/no_api/mock_only/api_connected/implemented` 必须与仓库事实一致。
- 新增或改变页面、route、数据依赖、permission 或 Shared 组件时同 PR 更新。

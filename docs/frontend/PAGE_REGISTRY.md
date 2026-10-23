# Frontend Page Registry

Registry Status: `draft; approved only after owner review and merge`

| Page Key | Page Name | 一级导航 | 二级导航 | Route | Page Status | Components Used | Backend API | Read Model | Permission Key | PRP | PR | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `pmc_purchase_board` | 采购看板 | PMC | 采购看板 | `/pmc/purchase-board` | `testing` / `api_connected`（只读） | PageShell, ManagementStatCards, ReportTableShell, CommittedSearch/ConnectedSearch, ReportFacetSelect, ResetButton, RuntimeColumnConfigDrawer, ResizableColumnTitle, cells (CopyableTextCell/MoneyCell/WalmartItemLink), StatusTag, EmptyState, RequestLoadingOverlay | `GET /api/pmc/purchase/board`, `/board/summary`, `/orders/{order_sn}`, `/plans/pending`；负责人选项 `GET /api/product-management/options`(owners) | `dws_purchase_board`, `dws_purchase_sku_cycle`, `dws_purchase_pending`, `dwd_purchase_plan`（经后端） | `pmc:purchase:read`（后端键；前端仅元数据） | `PRPs/pmc-purchase-board.md` Gate 4a | #171 | 无导出/推送/写操作；店铺下拉待 options 接口（Rocky 2026-09-24 ①）；交期修正 Modal = Gate 4b；ItemID 修正 Modal 已取消（#144）；无 Playwright（仓库尚无 test:e2e），故不标 ready |
| `pmc_domestic_warehouse_board` | 国内仓看板 | PMC | 国内仓看板 | `/pmc/domestic-warehouse-board` | `testing` / 本地契约接入待联调 | PageShell, ReportFacetSelect, CommittedSearch, ReportTableShell/ProTable, ManagementStatCards | `GET /api/pmc/domestic/filter-options`、`/batches`、`/batches/summary`、`/batches/{batch_id}/trace` | 收货/关联DWD、店铺DIM、SKU身份/当前产品负责人DWD | `pmc:domestic-batch:read` / 现有页面策略 | `PRPs/pmc-domestic-filter-options.md`（增量）；初版页面PRP另见文件 | TBD | 真实店铺ID及当前负责人UID下拉筛选；同源列表统计；业务状态与出库缺源；打包页只做结构；未部署或标ready。 |
| `pmc_wfs` | WFS | PMC | WFS | `/pmc/wfs` | `planned` / `no_api` | ComingSoonPage（PageShell, Result） | 无 | 无 | `page:pmc:wfs:view`（由页面 key 推导，尚未入库） | 无 | 无 | 与采购看板同级。不改仓库模块的 WFS费用异常 |
| `pmc_logistics` | 物流 | PMC | 物流 | `/pmc/logistics` | `planned` / `no_api` | ComingSoonPage（PageShell, Result） | 无 | 无 | `page:pmc:logistics:view`（由页面 key 推导，尚未入库） | 无 | 无 | 与采购看板同级。文案为「功能建设中」和「此页面暂不请求业务数据，也不提供业务操作。」 |
| `settings_user_management` | 用户管理 | 设置 | 用户管理 | `/settings/users` | `api_connected` / `ready_for_review` | PageShell, ProTable, UserFormModal, UserDataScopeModal | `/api/settings/users`, `/api/settings/user-role-options`, `/api/settings/rbac/users/{user_id}/data-scopes` | IAM users/roles/scopes/audit | `page:settings:user-management:view`；profile edit、enable-disable、assign-role、configure-data-scope 分别为 canonical action | N/A — RBAC post-0041 hardening | `#226` | 当前分支未合并；普通用户的 scope 显示 role/user 来源；超管不在该编辑入口；`*` 需确认；只有 source_account 当前由通用业务 API 执行 |
| `settings_role_management` | 角色管理 | 设置 | 角色管理 | `/settings/roles` | `api_connected` / `ready_for_review` | PageShell, RoleDataScopeEditor, permission tree | `/api/settings/rbac/catalog`, `/roles`, `/roles/{role_id}/permissions`, `/roles/{role_id}/data-scopes`, `/audit-events` | IAM roles/permissions/scopes/audit | `page:settings:role-management:view` + create/configure-permissions/configure-data-scope/view-audit | N/A — RBAC post-0041 hardening | `#226` | 普通 admin 不等于超管；不能授予超出自身有效权限或范围；`*` 保存前二次确认 |
| `data_center_approval_workspace` | 审批工作台 | 数据中心 | 审批工作台 | `/data-center/approval-workspace` | `api_connected` / `ready_for_review` | PageShell, ApprovalDetailDrawer | `/api/approvals/**` | Approval requests | `page:data-center:approval-workspace:view`; WFS supplement/request uses archive-request, review uses archive-review | N/A — RBAC post-0041 hardening | `#226` | 当前分支修复旧 key 断链；page view 不能补材料或审核；对象、状态、版本和 source_account 由后端校验 |
| `warehouse_wfs_fee_alert` | WFS费用异常 | 仓库 | WFS费用异常 | `/warehouse/wfs-fee-alert` | `api_connected` / `ready_for_review` | PageShell, WfsFeeAlertTable, WfsFeeAlertDetailModal | `/api/warehouse/wfs-fee-alerts/**`, `/api/warehouse/wfs-fee-cases/**` | WFS cases/alerts | `page:warehouse:wfs-fee-alert:view` + follow/archive-request/archive-review/mark-recovered/sync-legacy | N/A — RBAC post-0041 hardening | `#226` | request/review 分离；前端按钮与后端 action 一致；不因 page view 或旧权限获得写能力 |

| `ai_center_keyword_launch` | 关键词投放 | AI中心 | 关键词投放 | `/ai-center/keyword-launch` | `testing` / `mock_only` | PageShell, ProTable, ReportTableShell, KeywordTextCell, Upload | 无真实API | 内存mock | `ai_center.keyword_launch.view` | Owner-approved keyword demo PRPs 2026-10-22 | TBD | 本地解析卖家精灵Excel，演示广告与翻译；非真实广告执行 |
| `ai_center_keyword_rules` | 规则配置 | AI中心（隐藏） | 关键词投放内部 | `/ai-center/keyword-launch/rules` | `testing` / `mock_only` | PageShell, Form, Tabs | 无真实API | 内存mock | `ai_center.keyword_rules.view` | 同上 | TBD | 左侧导航隐藏，通过页面右上角进入 |
| `ads_keyword_library` | 词库 | 广告 | 词库 | `/ads/keyword-library` | `testing` / `mock_only` | PageShell, ProTable, ReportTableShell, ConnectedSearch | 无真实API | 内存mock | `ads.keyword_library.view` | 同上 | TBD | 原导航原路径，跨SKU演示、计划对账与人工录入 |


## Rules

- 只登记有 navigation、route、PRP 或实现证据的页面；未知写 TBD，不猜测。
- `planned/no_api/mock_only/api_connected/implemented` 必须与仓库事实一致。
- 新增或改变页面、route、数据依赖、permission 或 Shared 组件时同 PR 更新。

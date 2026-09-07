# Frontend Product Management No-API Page Shell PRP

Status: Approved
Owner Approval Required: Yes
Implementation Allowed: Yes, only within the owner-approved No-API scope and implementation allowlist

## 1. Goal

为“产品管理”定义一个统一的 No-API 页面壳。页面使用 50 条前端静态 UI 验收数据验证筛选、搜索、排序、分页和运行时交互，不连接 API，也不提供任何真实业务写入能力。

本 PRP 已由负责人批准，并按负责人后续视觉验收意见补充最终实现范围。静态验收数据不是真实或模拟接口数据，不构成 API、费用口径或数据源契约。

## 2. Navigation and Status

```text
页面路径：/products/management
navigation key：products_product_management
页面状态：planned
```

- 路径、标题和导航状态继续以 `frontend/src/config/navigation.ts` 为事实来源。
- 本任务不得修改 `navigation.ts`、`routeResolver.ts` 或 Tab workspace。
- 负责人后续批准对 `MainLayout` / `PageShell` 做最小全局布局调整，仅用于 breadcrumb right actions / page actions；具体边界见第 6、9 节。
- 页面不得标记为 `ready`。

## 3. Page Grain and Identity

- 主表一行代表一个内部 SKU 产品记录。
- SKU 只是展示字段，不得作为 React key、API 主键或数据库唯一标识。
- 未来 API 必须提供稳定的内部记录 ID；本任务不设计 API schema。
- 多店铺、多平台关系暂不建模，后续必须通过独立数据源决策和 API PRP 确认。

## 4. Scope

### In scope after approval

- 复用现有 PageShell 和路由基础能力，建立产品管理 No-API 页面壳。
- 展示产品等级、标签、SKU 普通搜索、批量 SKU 搜索 Popover、列配置、标签管理、更多和重置入口。
- 使用 50 条前端静态 UI 验收数据验证本地筛选、搜索、排序、分页、选择和详情结构。
- 展示负责人确认的主表字段、Ant Design Pagination、标签相关 Modal、列配置 Drawer 和产品详情 Modal。
- 将帮助入口以及产品管理页“最后同步时间 + 同步图标”放入面包屑右侧的页面级操作区。
- 展示负责人指定的待接入文案。
- 为 No-API 行为和可访问性增加必要测试。

### Out of scope

- 真实产品记录、接口返回数据或伪装成同步结果的数据；仅允许本 PRP 明确批准的 50 条前端静态 UI 验收数据。
- 真实 API、外部平台调用、后端、数据库和 API schema。
- 真实新增、编辑、删除、导入、导出、同步、上传和保存。
- 多店铺、多平台关系建模。
- 费用公式、币种、计算口径、数据来源或权威归属结论。
- 标签或列配置持久化，包括 localStorage 和 sessionStorage。
- 修改导航、路由解析或 Tab workspace。
- 超出 breadcrumb right actions / page actions 的 MainLayout、PageShell 行为改动。

## 5. Data-source Boundary

```text
data source decision：docs/data-sources/decisions/products-basic-information-query-decision.md
decision status：BLOCKED_BY_OWNER_DECISION
API：none
database：none
external platform request：none
old-system reference：no
```

- `BLOCKED_BY_OWNER_DECISION` 不阻止纯 No-API 页面壳展示，但禁止据此设计或接入真实接口。
- WFS费用、采购价、头程运费、仓储费、建议售价、最低售价和清仓售价仅作为 UI 占位。
- 本 PRP 不批准任何费用公式、币种、计算口径或数据源所有权。
- 后续真实接口必须先完成接口数据源决策，再单独编写 API PRP。
- 前端不得直接调用 Walmart、Lingxing 或其他外部平台。

## 6. UI Requirements

完整页面规格见 `docs/page-specs/product-management-page.md`。核心结构包括：

- 单行顶部筛选与操作区。
- 50 条前端静态 UI 验收数据与本地交互。
- 批量 SKU 搜索 Popover。
- 列配置 Drawer。
- 标记标签与标签管理 Modal。
- 由 SKU 或操作列“详情”打开的产品详情 Modal。
- Ant Design 原生 Pagination 和表格 body 内部滚动。

所有写操作和同步入口只能展示待接入提示，不得伪造成功结果或修改静态验收数据。

### Component boundary

- 页面必须复用现有 `PageShell`。
- 主表优先使用现有 ProComponents 的 `ProTable`。
- 弹框、表单、空状态和提示使用现有 Ant Design 组件。
- 不得手写第二套复杂表格、分页或 Modal，不得引入新的 UI 或表格依赖。

### Owner-approved changes after initial approval

负责人在最终视觉验收中明确批准以下范围扩展：

- `PageShell` 的帮助入口通过页面级操作 outlet 渲染到 `MainLayout` 面包屑容器右侧。
- 产品管理页“最后同步时间 + 同步图标”通过同一 page actions 能力显示在帮助入口附近。
- 产品内容卡片内部不重复显示帮助或同步时间。
- 该调整会影响所有使用 `PageShell` 的页面，因此作为最小全局布局变更记录并覆盖相应测试。

该批准只适用于 breadcrumb right actions / page actions，不允许借此修改 `navigation.ts`、`routeResolver.ts`、Tab workspace，不允许接入 API、storage 或权限系统。

## 7. API Contract

```text
method：none
path：none
request schema：none
response schema：none
error codes：none
```

本任务不设计 API schema。未来接口必须返回稳定内部记录 ID，并遵守项目统一 API 契约，但具体字段和数据来源需由后续独立任务确定。

## 8. Storage and State

- 只允许组件运行时的临时 UI 状态。
- 产品管理页面不得创建或写入标签、列配置等新的 localStorage / sessionStorage 数据。
- 现有 `tab_workspace` 属于 MainLayout 的既有 Tab 生命周期行为，必须保持，不得由产品管理页面读取、覆盖或清除。
- 不得持久化筛选条件、SKU 输入、同步状态或产品详情内容。
- 不得修改现有 Tab workspace 的职责或存储结构。

## 9. Approved Implementation Boundary

负责人已将本文件状态改为 `Approved` 并下发实现与视觉验收要求。实现仍必须严格受下列 allowlist 和 No-API 边界约束。

即使获得实现批准，仍不得凭本 PRP 接入 API、修改数据库、批准费用口径或扩展到真实业务操作；这些内容需要独立数据源决策和任务授权。

### Exact implementation allowlist after approval

```text
frontend/src/pages/products/ProductManagementPage.tsx
frontend/src/pages/products/ProductManagementPage.css
frontend/src/pages/products/ProductManagementPage.test.tsx
frontend/src/router/routes.tsx
frontend/src/router/routes.test.tsx
frontend/src/layouts/MainLayout.tsx
frontend/src/layouts/MainLayout.css
frontend/src/layouts/MainLayout.test.tsx
frontend/src/components/page/PageShell.tsx
frontend/src/components/page/PageShell.css
```

### Forbidden files and directories during implementation

```text
frontend/src/config/navigation.ts
frontend/src/router/routeResolver.ts
frontend/src/layouts/useTabWorkspace.ts
frontend/src/App.tsx
frontend/src/components/page/**（上方明确列出的 PageShell.tsx / PageShell.css 除外）
frontend/src/pages/ComingSoonPage.tsx
frontend/package.json
frontend/package-lock.json
frontend/vite.config.ts
backend/**
old-system/**
docs/integrations/**
docs/data-sources/**
.github/**
.env*
其他未列入 allowlist 的文件
```

如果实现必须超出 allowlist，应停止并由负责人重新审查 PRP，不得自行扩大范围。

## 10. Validation Plan after Approval

- 验证页面从既有导航与路由解析结果获取标题和状态。
- 验证 50 条静态验收数据的 SKU 为 `UI-SAMPLE-001` 至 `UI-SAMPLE-050`，产品名称为 `验收示例产品 001` 至 `验收示例产品 050`。
- 验证产品等级、标签、SKU 普通搜索、批量 SKU 搜索、本地排序和分页仅作用于静态验收数据。
- 验证批量 SKU、同步、列配置、标签和操作入口符合规定的 No-API 行为。
- 验证主表字段、选择、列配置、列宽拖拽、详情结构、响应式布局和键盘可访问性。
- 验证默认每页 10 条，pageSize 支持 10 / 20 / 50 / 100；改变 pageSize 后回到第 1 页并清空已选项。
- 验证页面外层、工具栏、表头和 pagination footer 不滚动，只有 table body 内部滚动。
- 验证切换 10 / 20 / 50 / 100 / 10 条后，表头不被压缩、遮挡、顶起或与第一行重叠。
- 验证 PageShell 的帮助与产品管理同步状态通过 MainLayout 页面级操作区显示。
- 验证没有网络请求、产品管理页面新增的 storage 写入或外部平台调用；现有 `tab_workspace` 行为保持不变。
- 桌面端验证 PageShell、筛选操作区、表格、空状态和各 Modal 的布局。
- 在 543px 宽度验证操作区换行、Modal 视口约束、表格内部滚动，以及无 window/body 横向或整页滚动。

```bash
cd frontend
npm run lint
npm run test -- --run
npm run test -- --run
npm run build
cd ..
bash scripts/check-rule-pack.sh
git diff --check
git status --short --untracked-files=all
git diff --stat
```

## 11. Acceptance Criteria

- [x] PRP 已由项目负责人改为 `Approved` 并另行授权实现。
- [ ] 页面路径为 `/products/management`，navigation key 为 `products_product_management`。
- [ ] 页面状态保持 `planned`。
- [ ] 页面符合 `docs/page-specs/product-management-page.md`。
- [ ] 主表一行代表一个内部 SKU 产品记录，且 SKU 不被用作技术唯一标识。
- [ ] 页面只使用获批的 50 条前端静态 UI 验收数据，不接 API，不提供真实写操作。
- [ ] 费用与价格字段只作为 UI 占位。
- [ ] 产品管理页面不创建或写入标签、列配置等新 storage 数据，现有 `tab_workspace` 保持不变。
- [ ] 不修改 navigation、route resolver 或 Tab workspace；MainLayout / PageShell 只包含获批的 page actions 最小全局布局改动。
- [ ] 桌面端和 543px 窄屏视觉验收通过。

## 12. Rollback Boundary

实现阶段回滚范围限定为：删除 `frontend/src/pages/products/` 下本任务新增的三个页面文件，还原 `frontend/src/router/routes.tsx`、`frontend/src/router/routes.test.tsx`，并还原第 9 节 allowlist 中 MainLayout / PageShell 的 page actions 全局布局改动及测试。实现不得产生依赖、storage schema、API、数据库、配置或数据回滚事项。

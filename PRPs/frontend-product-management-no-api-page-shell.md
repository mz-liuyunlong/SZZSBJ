# Frontend Product Management No-API Page Shell PRP

Status: Approved
Owner Approval Required: Yes
Implementation Allowed: No until owner changes Status to Approved

## 1. Goal

为“产品管理”定义一个统一的 No-API 页面壳。页面只展示结构、固定表头、空状态和待接入提示，不展示假数据，不连接 API，也不提供任何写入能力。

本 PRP 仅是 Draft。负责人将状态改为 `Approved` 并另行下发实现任务前，禁止修改前端代码。

## 2. Navigation and Status

```text
页面路径：/products/management
navigation key：products_product_management
页面状态：planned
```

- 路径、标题和导航状态继续以 `frontend/src/config/navigation.ts` 为事实来源。
- 本任务不得修改 `navigation.ts`、`routeResolver.ts`、`MainLayout` 或 Tab workspace。
- 页面不得标记为 `ready`。

## 3. Page Grain and Identity

- 主表一行代表一个内部 SKU 产品记录。
- SKU 只是展示字段，不得作为 React key、API 主键或数据库唯一标识。
- 未来 API 必须提供稳定的内部记录 ID；本任务不设计 API schema。
- 多店铺、多平台关系暂不建模，后续必须通过独立数据源决策和 API PRP 确认。

## 4. Scope

### In scope after approval

- 复用现有 PageShell 和路由基础能力，建立产品管理 No-API 页面壳。
- 展示筛选区、批量搜索 SKU、同步数据、上次同步状态、列配置和标签管理入口。
- 展示固定主表表头、分页占位、空状态和产品详情空结构 Modal。
- 展示负责人指定的待接入文案。
- 为 No-API 行为和可访问性增加必要测试。

### Out of scope

- 真实或 mock 产品记录。
- 真实 API、外部平台调用、后端、数据库和 API schema。
- 新增、编辑、删除、导入、导出、同步、上传和保存。
- 多店铺、多平台关系建模。
- 费用公式、币种、计算口径、数据来源或权威归属结论。
- 标签或列配置持久化，包括 localStorage 和 sessionStorage。
- 修改导航、路由解析、MainLayout 或 Tab workspace。

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

- 顶部筛选与操作区。
- 固定字段主表。
- 批量 SKU 搜索 Modal。
- 列配置 Modal。
- 标签管理 Modal。
- 产品详情结构预览 Modal。
- 分页占位和 No-API 空状态。

所有入口只能展示空结构或待接入提示，不得伪造成功结果或业务数据。

### Component boundary

- 页面必须复用现有 `PageShell`。
- 主表优先使用现有 ProComponents 的 `ProTable`。
- 弹框、表单、空状态和提示使用现有 Ant Design 组件。
- 不得手写第二套复杂表格、分页或 Modal，不得引入新的 UI 或表格依赖。

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

## 9. Implementation Gate

实现必须等待项目负责人将本文件状态改为 `Approved`，并另行下发允许修改文件、测试和验收要求。

即使获得实现批准，仍不得凭本 PRP 接入 API、修改数据库、批准费用口径或扩展到真实业务操作；这些内容需要独立数据源决策和任务授权。

### Exact implementation allowlist after approval

```text
frontend/src/pages/products/ProductManagementPage.tsx
frontend/src/pages/products/ProductManagementPage.css
frontend/src/pages/products/ProductManagementPage.test.tsx
frontend/src/router/routes.tsx
frontend/src/router/routes.test.tsx
```

### Forbidden files and directories during implementation

```text
frontend/src/config/navigation.ts
frontend/src/router/routeResolver.ts
frontend/src/layouts/MainLayout.tsx
frontend/src/layouts/MainLayout.css
frontend/src/layouts/useTabWorkspace.ts
frontend/src/App.tsx
frontend/src/components/page/**
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
- 验证没有产品数据时只展示空状态，不展示假数据。
- 验证批量 SKU、同步、列配置和标签入口只显示待接入状态。
- 验证产品详情预览只打开空结构，不创建产品记录。
- 验证固定表头、排除字段、响应式布局和键盘可访问性。
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

- [ ] PRP 已由项目负责人改为 `Approved` 并另行授权实现。
- [ ] 页面路径为 `/products/management`，navigation key 为 `products_product_management`。
- [ ] 页面状态保持 `planned`。
- [ ] 页面符合 `docs/page-specs/product-management-page.md`。
- [ ] 主表一行代表一个内部 SKU 产品记录，且 SKU 不被用作技术唯一标识。
- [ ] 页面不展示假数据、不接 API、不提供写操作。
- [ ] 费用与价格字段只作为 UI 占位。
- [ ] 产品管理页面不创建或写入标签、列配置等新 storage 数据，现有 `tab_workspace` 保持不变。
- [ ] 不修改 navigation、route resolver、MainLayout 或 Tab workspace。
- [ ] 桌面端和 543px 窄屏视觉验收通过。

## 12. Rollback Boundary

当前 Draft 文档阶段回滚时删除本 PRP 和 Page Spec 即可。

实现阶段的回滚范围限定为：删除 `frontend/src/pages/products/` 下本任务新增的三个页面文件，并还原 `frontend/src/router/routes.tsx` 与 `frontend/src/router/routes.test.tsx` 的本任务改动。实现不得产生依赖、storage schema、API、数据库、配置或数据回滚事项。

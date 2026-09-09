# Frontend Daily Sales No-API Page Shell PRP

Status: Approved
Owner Approval Required: Completed
Implementation Allowed: Yes

## 1. Goal

为销售模块新增“每日销售”高密度运营报表页的 No-API 页面壳。页面用于按平台、负责人、店铺和日期范围查看每日销售表现，本阶段仅使用前端静态验收数据验证布局与交互，不连接真实数据源。

## 2. Navigation and Status

```text
一级导航：销售
页面名称：每日销售
页面路径：/sales/daily-sales
navigation key：sales_daily_sales
页面状态：planned
```

- 以上元数据来自现有 `frontend/src/config/navigation.ts`。
- 每日销售必须作为现有 `PageShell` 的内部内容渲染，并接收 route resolver 解析后传入的 `NavigationPage`。
- 页面标题、状态和帮助入口由 `PageShell` 统一渲染；每日销售不得自行创建第二套标题、状态、帮助入口或页面框架。
- 实现阶段不得修改 `navigation.ts`、`routeResolver.ts` 或 Tab workspace。
- 实现阶段不得修改或绕开 `MainLayout` / `PageShell`。
- 页面不得标记为 `ready`。

## 3. Background

每日销售页面用于集中查看销量、订单、销售额、退货退款、广告、成本、库存和利润等每日运营指标。负责人提供的每日销售参考截图是本任务的主要视觉和布局参考，但不作为字段来源，也不保存到仓库。

本任务需要复用产品管理页面已经验证的报表表格外壳、列配置 Drawer、列宽拖拽和通用单元格能力，避免复制 `ProductManagementPage` 整页或建立第二套表格交互。

## 4. Scope

### In scope after approval

- 新增每日销售 No-API 页面壳，并接入既有 `/sales/daily-sales` 路由。
- 实现顶部筛选工具栏、三张统计卡片、两张趋势图和高密度数据表格。
- 固定使用 50 条清晰标注的前端静态 UI 验收数据进行本地筛选、搜索、排序、分页和滚动验收。
- 严格按第 8 节的 35 个业务字段及其顺序展示表格。
- 在同步时间右侧按刷新、下载、帮助、列配置的视觉顺序显示紧凑操作；其中帮助必须是 `PageShell` 提供的唯一统一帮助入口。
- 使用与产品管理页面一致的列配置 Drawer 和列宽拖拽方式。
- 抽取产品管理与每日销售确实共用的报表表格能力，并最小接入产品管理页面。
- 增加必要的组件、路由与产品管理回归测试。

### Out of scope

- 真实 API、数据库、旧系统数据或外部平台请求。
- 真实同步、下载、保存、后台任务或业务写操作。
- API schema、数据库 schema、字段数据源、币种、公式、聚合口径或权威归属设计。
- localStorage / sessionStorage 中的业务筛选、列配置、分页、排序或页面数据持久化。
- 真实权限、401 / 403、认证、token、cookie 或 session 处理。
- 修改 MainLayout、PageShell、navigation、route resolver 或 Tab workspace。
- 新增依赖、第二套 UI 框架、表格库、图表库或拖拽库。

## 5. Data-source Boundary

```text
API：none
database：none
external platform request：none
old-system reference：no
runtime storage：none for daily-sales business state
```

- 当前静态数据只用于 No-API UI 验收，不代表真实业务数据、接口响应、同步结果或最终数据契约。
- 当前筛选、搜索、排序、分页、统计卡和图表汇总均为前端本地行为。
- 本任务不批准任何金额币种、费用公式、利润公式、聚合逻辑、数据新鲜度或数据源所有权。
- 后续真实接口必须先完成接口数据源决策并单独编写、批准 API PRP。
- 前端不得直接调用 Walmart、Lingxing、TEMU、Amazon 或其他外部平台。

## 6. Visual Reference Rules

负责人提供的每日销售参考截图只用于参考：

- 顶部筛选栏的布局密度。
- 同步时间和右侧小图标的位置。
- 三张统计卡片的排列方式。
- 销量与销售额双图表布局。
- 高密度表格、横向滚动、固定表头和固定 pagination footer 的视觉效果。
- 企业级运营数据页面的整体层级与风格。

截图不是字段来源。截图中出现但未列入第 8 节的字段不得加入表格或列配置。当截图与字段清单冲突时，以第 8 节的 35 个字段为准。

## 7. Page Structure and Toolbar

页面包含四个区域：

```text
顶部筛选工具栏
统计卡片区域
趋势图区域
数据表格区域
```

顶部工具栏从左到右为：

```text
全部平台
负责人
全部店铺
今日 / 本周 / 本月 / 今年
日期范围
币种
搜索类型
搜索内容
重置
同步时间：待接入
刷新
下载
帮助
列配置
隐藏统计
隐藏图表
```

同步时间右侧四个图标的顺序固定为：

```text
刷新 / 下载 / 帮助 / 列配置
```

- 刷新提示 `同步接口待接入`。
- 下载提示 `导出接口待接入`。
- 帮助由 `PageShell` 根据 navigation metadata 提供，是页面唯一帮助入口；每日销售不得创建第二个帮助按钮或 `帮助文档待接入` 占位逻辑。
- 列配置打开右侧 Drawer。
- `隐藏统计` 和 `隐藏图表` 只切换当前组件运行时显示状态。
- 所有图标按钮必须有可访问名称。
- 每日销售页面自身只实现同步时间、刷新、下载、列配置、隐藏统计和隐藏图表；视觉顺序由这些页面动作与 `PageShell` 统一帮助入口共同组成。

## 8. Daily Sales Table Fields

业务字段必须严格按以下 35 项及顺序实现：

1. 图片
2. 分析
3. 日期
4. 店铺
5. 负责人
6. 前7天销量趋势
7. MSKU/商品ID
8. SKU/品名
9. 平台
10. 销量
11. 订单量
12. 销售额
13. 剔除送样额
14. 退货量
15. 退款额
16. 退货率30天
17. 广告费
18. 广告占比
19. WFS配送费
20. WFS配送单价$
21. 佣金
22. 采购成本
23. 采购单价¥
24. 头程成本
25. 头程单价¥
26. 仓储费
27. 仓储单价$
28. WFS可售库存
29. 毛利润(旧)
30. 订单利润
31. 利润率
32. ROI
33. 成本状态
34. 系统运营日志
35. 运营日志

系统选择框列可以位于业务字段之前，但不计入 35 个字段。不得从参考截图新增商品 ID、父体、站点、开发人等未确认字段。

## 9. Statistics and Charts

统计卡片横向显示：

1. 所选日期范围。
2. 所选日期环比。
3. 去年同期。

每张卡片包含销量、销售额、环比和同比；数字突出，涨跌使用克制的红 / 绿箭头并辅以文本，不能只用颜色表达。

趋势图横向显示：

1. 销量趋势。
2. 销售额趋势。

每张图包含所选日期范围、所选日期环比、去年同期三条静态数据线。实现阶段优先复用项目已安装的 ECharts；不得新增图表依赖。

## 10. Table Interactions and Formatting

- 图片：静态缩略图或统一占位，不上传或读取真实图片接口。
- 分析：点击图标打开标题为 `销售详情` 的静态 Modal。
- 前7天销量趋势：单元格显示 sparkline，hover Popover 显示每日静态销量。
- MSKU/商品ID、SKU/品名：省略长文本，hover 显示完整值，并支持复制。
- 金额：销售额、剔除送样额、退款额、广告费、WFS配送费、WFS配送单价$、佣金、采购成本、采购单价¥、头程成本、头程单价¥、仓储费、仓储单价$、毛利润(旧)、订单利润统一格式化；人民币单价字段显示 `¥`，美元字段显示 `$`，不进行汇率换算。
- 百分比：退货率30天、广告占比、利润率、ROI 使用百分比格式。
- 成本状态：使用 Tag，允许 `已完成`、`待补齐`、`异常`、`部分缺失`。四个值仅为 No-API UI 验收占位，不代表最终业务枚举或成本核算口径；真实状态必须在后续 API / 数据口径任务中重新定义。
- 系统运营日志、运营日志：只显示摘要，长文本省略并通过 Tooltip 查看完整内容，不提供真实编辑。

## 11. Filtering, Search and Pagination

- 筛选项包括平台、负责人、店铺、日期快捷项、日期范围、币种和搜索类型。
- 搜索类型包括 MSKU、SKU、商品ID、品名；只对静态数据执行不区分大小写的包含匹配，展示保留原值。
- 筛选和搜索后回到第 1 页并清空已选项。
- 重置清空筛选、搜索、排序和选择，恢复默认日期、全部静态数据和第 1 页；不重置 Drawer 中已应用的运行时列配置。
- 默认每页 20 条，pageSize 支持 10 / 20 / 50 / 100，并支持快速跳页。
- pageSize 改变后回到第 1 页并清空已选项，total 始终基于当前本地过滤结果。
- 分页、筛选、搜索、排序和选择状态不写 storage。
- 本地筛选或搜索无结果时使用 Ant Design `Empty`，不显示自定义大面积空白，不伪造错误或 Loading，也不发起网络请求。
- No-API 阶段不实现真实 Loading / Error 状态；真实 Loading / Error 在 API 接入任务中另行设计。

## 12. Report Table Reuse

实现阶段必须先确认产品管理已有能力的实际边界，只抽取两个页面已经证明确实相同的最小能力：

- 固定表头、table body 内部滚动和固定 pagination footer 的报表表格外壳。
- 10 / 20 / 50 / 100 / 10 pageSize 切换时保持表头稳定的 flex / overflow 结构。
- 列配置 Drawer 的搜索、显示 / 隐藏、顺序调整、恢复默认和运行时应用。
- 表头右边界列宽拖拽，并隔离排序点击。
- 图片、可复制文本、金额、百分比和状态 Tag 等通用单元格。

不得抽取产品管理专属的标签管理、标记标签、产品详情分区、产品等级或专属字段逻辑。不得复制整个产品管理页面。

`useRuntimeColumnConfig.ts`、`useResizableColumns.ts` 和 `useClientTableState.ts` 只是实现 allowlist，不要求全部创建。只有现有代码证明存在真实复用价值时才允许创建对应 Hook；不得为了形式完整创建空 Hook、空组件或其他推测性抽象。

## 13. Column Configuration

- 使用与产品管理页面一致的右侧 Drawer，不使用 Modal 或独立大按钮。
- 配置字段只能来自第 8 节的 35 个字段。
- 支持字段搜索、显示 / 隐藏、非固定列顺序调整、恢复默认和保存并应用。
- 图片、分析、日期、MSKU/商品ID、SKU/品名为核心固定列：checked + disabled，不可取消、移除或改变核心固定顺序。
- 固定列和系统选择框不参与普通拖拽排序。
- 配置只在当前页面运行时生效，刷新后恢复默认；不得写 localStorage、sessionStorage 或调用 API。

## 14. Column Width Resizing

- 复用产品管理已验证的 resize handle 行为。
- handle 位于表头右边界，命中区域为 8px 至 12px。
- pointerdown 和 click 阻止排序冒泡；拖拽不得触发表头排序。
- 拖拽后表头和表体列宽同步。
- 列宽只在当前页面运行时生效，不写 storage，不新增依赖。

## 15. Stable Table Layout

- 页面根容器和表格卡片使用稳定的 flex 高度边界，设置必要的 `min-height: 0` 与 `overflow: hidden`。
- 工具栏、表头和 pagination footer 不参与纵向滚动或 flex 收缩。
- table body 使用内部纵向滚动，表格容器内部承担横向滚动。
- 页面外层不得因数据行数或 pageSize 变化产生异常滚动。
- 必须验证 `10 → 20 → 50 → 100 → 10` 后表头完整、第一行位于表头下方且 footer 位置稳定。
- 不得使用只适配单一屏幕高度的魔法数修复布局。

## 16. Page-local Component Boundary

每日销售页面应拆分必要的 page-local 组件，避免把工具栏、统计卡、图表、35 列定义、表格和详情 Modal 全部塞入 `DailySalesPage.tsx`。建议方向：

```text
frontend/src/pages/sales/components/DailySalesToolbar.tsx
frontend/src/pages/sales/components/DailySalesSummaryCards.tsx
frontend/src/pages/sales/components/DailySalesCharts.tsx
frontend/src/pages/sales/components/DailySalesTable.tsx
frontend/src/pages/sales/components/SalesDetailModal.tsx
```

实际文件名可按现有项目风格最小调整。每日销售专属组件必须留在 `frontend/src/pages/sales/components/**`；只有两个页面已证明共用的报表表格能力才能放入 `frontend/src/components/report-table/**`。

## 17. Implementation Boundary after Approval

本文件已由负责人批准为 `Approved`，允许在本 PRP 约束范围内进入实现阶段。

### Exact implementation allowlist after approval

```text
frontend/src/pages/sales/DailySalesPage.tsx
frontend/src/pages/sales/DailySalesPage.css
frontend/src/pages/sales/DailySalesPage.test.tsx
frontend/src/pages/sales/components/**
frontend/src/pages/sales/dailySalesMockData.ts
frontend/src/pages/sales/dailySalesTypes.ts
frontend/src/router/routes.tsx
frontend/src/router/routes.test.tsx
frontend/src/components/report-table/**
frontend/src/hooks/useRuntimeColumnConfig.ts
frontend/src/hooks/useResizableColumns.ts
frontend/src/hooks/useClientTableState.ts
frontend/src/pages/products/ProductManagementPage.tsx
frontend/src/pages/products/ProductManagementPage.css
frontend/src/pages/products/ProductManagementPage.test.tsx
docs/UI_COMPONENT_CATALOG.md
```

产品管理文件只允许为接入通用表格能力做最小修改，并必须保持视觉、列配置、标签交互和 pageSize 稳定性不回退。

- 页面专属工具栏、统计卡、图表、表格和详情 Modal 放在 `frontend/src/pages/sales/components/**`。
- 固定 50 条静态验收数据放在 `dailySalesMockData.ts`，页面类型放在 `dailySalesTypes.ts`。
- `docs/UI_COMPONENT_CATALOG.md` 仅在实现阶段确实新增或沉淀 `frontend/src/components/report-table/**` 共享组件时做最小登记；没有新增共享组件时不得修改，也不得借机改写其他规则。
- 三个通用 Hook 路径只是允许范围，不是必须创建的交付物。

### Forbidden files and directories during implementation

```text
frontend/src/config/navigation.ts
frontend/src/router/routeResolver.ts
frontend/src/layouts/useTabWorkspace.ts
frontend/src/layouts/MainLayout.tsx
frontend/src/layouts/MainLayout.css
frontend/src/components/page/PageShell.tsx
frontend/src/components/page/PageShell.css
frontend/src/App.tsx
frontend/package.json
frontend/package-lock.json
frontend/vite.config.ts
backend/**
old-system/**
PRPs/**
docs/page-specs/**
.github/**
.env*
其他未列入 allowlist 的文件
```

如果实现必须超出 allowlist，应停止并由负责人重新审查 PRP，不得自行扩大范围。

## 18. Validation Plan after Approval

- 测试 35 个字段完整且顺序严格一致。
- 测试同步时间显示“待接入”，右侧视觉顺序为刷新、下载、`PageShell` 唯一帮助入口、列配置，且页面没有第二套帮助逻辑。
- 测试筛选、搜索、重置、分页、选择、统计和图表显隐只作用于本地状态。
- 测试分析 Modal、趋势 Popover、复制、金额 / 百分比和状态 Tag。
- 测试列配置 Drawer 与产品管理方式一致，固定列不可取消或重排。
- 测试列宽拖拽不触发表头排序。
- 测试默认 20 条及 10 / 20 / 50 / 100 pageSize；改变 pageSize 后回到第 1 页并清空选择。
- 测试表头、table body 和 pagination footer 属于独立稳定区域。
- 测试固定 50 条静态 UI 验收数据，筛选无结果使用 Ant Design `Empty`，不伪造 Loading / Error。
- 测试不发起网络请求，不创建每日销售业务 storage。
- 如果修改产品管理页面，必须运行其完整回归测试。
- 在桌面端和 543px 窄屏进行视觉验收，确认无 window/body 横向或整页滚动。

```bash
cd frontend
npm run lint
npm run test -- --run DailySalesPage.test.tsx routes.test.tsx
npm run test -- --run ProductManagementPage.test.tsx
npm run test -- --run
npm run build
cd ..
bash scripts/check-rule-pack.sh
git diff --check
git status --short --untracked-files=all
git diff --stat
```

## 19. Acceptance Criteria

- [ ] PRP 已由项目负责人改为 `Approved` 并另行授权实现。
- [ ] `/sales/daily-sales` 只对 `sales_daily_sales` 渲染每日销售页面，其他 planned 页面继续使用既有占位页。
- [ ] 页面状态保持 `planned`，不修改 navigation metadata。
- [ ] 页面复用现有 `PageShell`，页面元数据来自 route resolver 传入的 `NavigationPage`，没有第二套标题、状态、帮助入口或页面框架。
- [ ] 视觉结构遵循负责人参考截图，但没有从截图复制字段。
- [ ] 同步时间显示“待接入”，右侧视觉顺序严格为刷新、下载、`PageShell` 唯一帮助入口、列配置。
- [ ] 三张统计卡和两张三序列趋势图可见并可切换显示。
- [ ] 表格严格包含 35 个业务字段及规定顺序。
- [ ] 列配置 Drawer 与产品管理一致且只使用 35 个字段。
- [ ] 固定表头、body 内滚、横向滚动和固定 pagination footer 正常。
- [ ] `10 → 20 → 50 → 100 → 10` 后表头稳定。
- [ ] 分析 Modal、趋势 Popover、复制、状态 Tag 和日志摘要可验收。
- [ ] No-API 阶段固定使用 50 条静态 UI 验收数据；空结果使用 Ant Design `Empty`，不伪造 Loading / Error。
- [ ] 产品管理页面及测试无回退。
- [ ] 没有真实 API、数据库、外部请求、业务 storage 或新增依赖。

## 20. Rollback Boundary

实现阶段回滚限定为删除每日销售页面新增文件与通用报表组件 / Hook，恢复 `frontend/src/router/routes.tsx`、`frontend/src/router/routes.test.tsx`，以及还原产品管理为接入通用能力产生的最小改动。回滚不得影响 navigation、route resolver、Tab workspace、MainLayout、PageShell、后端、数据库、依赖或 storage schema。

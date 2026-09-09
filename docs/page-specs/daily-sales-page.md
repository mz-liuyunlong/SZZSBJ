# Daily Sales No-API Page Specification

## 1. Document Status

```text
Status: Approved
Owner Approval Required: Yes
Implementation Allowed: No until related PRP is Approved
```

关联 PRP：`PRPs/frontend-daily-sales-no-api-page-shell.md`。

本规格只定义每日销售 No-API 页面壳。负责人提供的每日销售参考截图仅作为视觉和布局参考，不保存到仓库；本文件不能代替负责人批准实现。

## 2. Page Positioning

每日销售是销售模块下的高密度运营报表页，用于按平台、负责人、店铺和日期范围查看每日销售表现。当前仅通过前端静态验收数据展示页面结构和交互，不连接真实 API、数据库、旧系统或外部平台。

```text
一级导航：销售
页面名称：每日销售
页面路径：/sales/daily-sales
navigation key：sales_daily_sales
页面状态：planned
```

导航元数据继续以 `frontend/src/config/navigation.ts` 为唯一来源，本任务不得修改该文件。

- 每日销售必须作为现有 `PageShell` 的内部内容渲染，页面元数据由 route resolver 解析后以 `NavigationPage` 传入。
- 页面标题、状态和帮助入口由 `PageShell` 统一渲染。
- 每日销售不得自行渲染第二套标题、状态、帮助入口或页面框架，不得绕开或修改 `MainLayout` / `PageShell`。
- 不得修改 `navigation.ts`、`routeResolver.ts` 或 Tab workspace。

## 3. Visual Reference

负责人提供的每日销售参考截图是页面的主要视觉参考，用于确定：

- 顶部筛选栏的紧凑密度。
- 同步时间与操作图标的相对位置。
- 三张统计卡片和两张趋势图的布局。
- 高密度表格、内部横向滚动、固定表头和固定分页的视觉层级。
- 正式运营后台的数据呈现风格。

参考截图不是字段来源。任何未列入第 8 节的截图字段均不得进入每日销售表格或列配置。

## 4. Page Layout

页面按以下顺序纵向布局：

```text
顶部筛选工具栏
统计卡片区域
趋势图区域
数据表格区域
```

- 工具栏、统计卡和图表按可用宽度排列，窄屏可自然换行。
- 表格区域占用页面剩余高度，只有表格 body 纵向滚动。
- 页面外层不得因表格数据量或 pageSize 改变产生异常滚动。

## 5. Filter Toolbar

工具栏从左到右依次包含：

- 平台 Select，默认显示“全部平台”。
- 负责人 Select。
- 店铺 Select，默认显示“全部店铺”。
- 日期快捷项：今日、本周、本月、今年。
- 日期范围。
- 币种 Select。
- 搜索类型 Select。
- 搜索输入框。
- 重置。
- 同步时间：待接入。
- 刷新、下载、帮助、列配置；其中帮助由 `PageShell` 统一提供。
- 隐藏统计、隐藏图表。

搜索类型包括 MSKU、SKU、商品ID、品名。所有筛选只作用于本地静态验收数据。

## 6. Sync Time and Action Icons

No-API 阶段同步时间固定显示为：

```text
同步时间：待接入
```

紧跟同步时间的四个小图标必须严格按以下顺序排列：

1. 刷新。
2. 下载。
3. 帮助。
4. 列配置。

不得调整顺序，不得改成独立大按钮，也不得移入表格内部。

- 刷新：提示 `同步接口待接入`。
- 下载：提示 `导出接口待接入`。
- 帮助：必须复用 `PageShell` 根据 navigation metadata 提供的唯一统一帮助入口。
- 列配置：打开与产品管理一致的右侧 Drawer。

每日销售页面自身只实现同步时间、刷新、下载、列配置、隐藏统计和隐藏图表。不得创建第二个帮助按钮、页面专属帮助占位或 `帮助文档待接入` 逻辑；这些页面动作与 `PageShell` 的唯一帮助入口共同形成上述视觉顺序。

图标按钮必须提供可访问名称、键盘焦点和轻量 hover / focus 状态。

## 7. Statistics and Trend Charts

### Statistics

横向展示三张卡片：

1. 所选日期范围。
2. 所选日期环比。
3. 去年同期。

每张卡片包含：

- 销量。
- 销售额。
- 环比。
- 同比。

数值突出，涨跌箭头使用克制的红 / 绿样式并同时提供文本语义。`隐藏统计` 切换统计区域显示状态，只保存在组件运行时内存。

### Trend charts

横向展示两张图：

1. 销量趋势。
2. 销售额趋势。

每张图包含三条线：所选日期范围、所选日期环比、去年同期。图表使用本地静态数据；优先复用项目已有 ECharts，不新增依赖。`隐藏图表` 只切换运行时显示状态。

## 8. Table Fields

业务表格必须严格按以下 35 个字段及顺序实现：

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

表格可以在最左侧增加系统选择框列，但该列不属于 35 个业务字段。不得从参考截图加入商品 ID、父体、站点、开发人或其他未确认字段。

## 9. Key Cell Interactions

### Image

- 展示静态商品缩略图或统一占位图。
- 不上传图片，不请求真实图片服务。

### Analysis

- 展示分析图标。
- 点击打开标题为 `销售详情` 的 Modal。
- Modal 使用静态结构展示基础信息、销量 / 订单量 / 销售额、退货 / 退款、广告 / 成本、利润、近 7 天趋势和运营日志摘要。
- 不保存、下载或请求数据。

### Seven-day trend

- 单元格内显示轻量 sparkline。
- hover 打开 Popover，标题为“近 7 天销量趋势”，并列出每日静态销量。

### Copyable identifiers

- MSKU/商品ID 和 SKU/品名支持长文本省略及 Tooltip 完整展示。
- 支持复制；成功和失败均提供明确提示。
- 复制操作不能触发相邻单元格行为。

### Money and percentage

- 金额字段包括销售额、剔除送样额、退款额、广告费、WFS配送费、WFS配送单价$、佣金、采购成本、采购单价¥、头程成本、头程单价¥、仓储费、仓储单价$、毛利润(旧)、订单利润。
- 人民币单价字段显示 `¥`，美元字段显示 `$`；静态 UI 格式不构成最终币种、费用或汇率口径。
- 退货率30天、广告占比、利润率、ROI 使用百分比格式。

### Status and logs

- 成本状态使用 Ant Design Tag，允许：已完成、待补齐、异常、部分缺失。
- 以上四个成本状态仅为 No-API UI 验收占位，不代表最终业务枚举或最终成本核算口径；真实成本状态必须在后续 API / 数据口径任务中重新定义。
- 系统运营日志和运营日志只显示摘要，长文本省略，hover 显示完整内容。
- 当前不提供日志编辑、写入或保存。

## 10. Filtering, Search and Reset

- 平台、负责人、店铺、日期快捷项、日期范围、币种和搜索类型对本地静态数据生效。
- 搜索类型为 MSKU、SKU、商品ID、品名。
- 搜索使用不区分大小写的包含匹配，但展示值保留原始大小写。
- 筛选或搜索后回到第 1 页并清空当前选择。
- 重置清空平台、负责人、店铺、搜索、排序和选择，恢复默认日期范围、全部静态数据和第 1 页。
- 重置不影响已经在当前运行时应用的列配置；列配置只能在 Drawer 中恢复默认。
- 本地筛选或搜索无结果时使用 Ant Design `Empty`，不使用自定义大面积空白，不伪造错误状态，不显示 Loading，也不发起网络请求。
- No-API 阶段不实现真实 Loading / Error 状态；真实 Loading / Error 状态在 API 接入任务中另行设计。

## 11. Table Layout and Scrolling

- 表格使用项目既有 Ant Design / ProComponents 体系。
- 表头固定且不参与 table body 的纵向滚动。
- table body 占据剩余空间并内部纵向滚动。
- 横向滚动限制在表格容器内部。
- pagination footer 固定在表格区域底部，不进入 body 滚动区。
- 页面根容器、表格卡片和表格区域使用正确的 flex 边界、`min-height: 0` 与 `overflow: hidden`。
- 不得以 window/body 或业务页面外层滚动解决数据行高度问题。
- 不得使用只适配单一屏幕的魔法高度。
- 切换 `10 → 20 → 50 → 100 → 10` 后，表头完整、第一行始终位于表头下方、分页始终位于 footer。

## 12. Pagination and Selection

- 使用 Ant Design 原生 Pagination 或已有共享分页外壳。
- 默认每页 20 条。
- pageSize 选项为 10、20、50、100。
- 支持快速跳页。
- total 基于当前本地过滤结果，不伪装为接口 total。
- pageSize 改变后回到第 1 页并清空已选项。
- 筛选、搜索和重置后清空已选项。
- pageSize、页码和选择状态不写 localStorage / sessionStorage。

## 13. Column Configuration Drawer

每日销售列配置必须复用产品管理页面已经验证的方式：

- 点击同步时间右侧第四个小图标打开右侧 Drawer。
- Drawer 的布局、字段搜索、勾选、已选列表、恢复默认、取消和应用方式与产品管理保持一致。
- 配置字段只能来自第 8 节的 35 个字段。
- 图片、分析、日期、MSKU/商品ID、SKU/品名为核心固定列，显示为 checked + disabled，不可取消、移除或改变核心固定顺序。
- 其他列支持运行时显示 / 隐藏及顺序调整。
- 系统选择框不进入业务列配置。
- 应用只在当前页面运行时生效，刷新后恢复默认。
- 不写 localStorage、sessionStorage，不创建用户模板，不调用 API。

## 14. Column Width Resizing

- 复用产品管理页面已验证的列宽拖拽方式。
- resize handle 位于表头右边界，命中区域为 8px 至 12px。
- pointerdown 和 click 阻止事件冒泡，拖拽不得触发表头排序。
- 拖拽后表头和表体列宽保持同步。
- 列宽只在当前运行时生效，不写 storage，不新增拖拽依赖。

## 15. No-API Static Data

- No-API 阶段固定使用 50 条前端静态 UI 验收数据。
- 数据名称必须清楚标注为验收数据，例如 `DAILY-SALES-001`。
- 平台可包含 Walmart、TEMU、Amazon，但页面主业务仍以 Walmart 为主。
- 每行使用独立稳定的内部验收 ID 作为 React key，不使用 SKU、MSKU 或商品ID作为技术唯一标识。
- 统计卡、图表、筛选、搜索、排序和分页均使用本地静态数据。
- 静态数据不写数据库或 storage，不伪装为真实接口结果、同步结果或最终业务口径。
- 真实 API 接入后必须替换这 50 条数据；当前本地筛选、搜索、排序和分页不构成最终接口契约。

## 16. Shared Report Table Boundary

每日销售与产品管理共用的能力应抽取到最小共享层，并仅限两个页面已经证明确实相同的能力：

- 固定表头、body 内滚、横向滚动和固定 pagination footer 的外壳。
- pageSize 切换时稳定的 flex / overflow 结构。
- 列配置 Drawer。
- 列宽拖拽。
- 图片、可复制文本、金额、百分比和状态 Tag 单元格。

不得复制 `ProductManagementPage` 整页。不得把产品管理的标签管理、标记标签、详情分区、产品等级或字段规则抽成全局业务能力。若修改产品管理接入共享层，页面视觉与全部既有交互必须保持不变。

通用 Hook 路径只是实现 allowlist，不要求全部创建；只有确有复用价值时才创建。不得为了形式完整一次性创建空 Hook、空组件或其他推测性抽象。

## 17. Page-local Component Boundary

每日销售页面应拆分必要的 page-local 组件，避免单文件巨型页面。建议方向：

```text
frontend/src/pages/sales/components/DailySalesToolbar.tsx
frontend/src/pages/sales/components/DailySalesSummaryCards.tsx
frontend/src/pages/sales/components/DailySalesCharts.tsx
frontend/src/pages/sales/components/DailySalesTable.tsx
frontend/src/pages/sales/components/SalesDetailModal.tsx
```

实际文件名可按项目风格调整。页面专属工具栏、统计卡、图表、表格和详情 Modal 必须放在 `frontend/src/pages/sales/components/**`；固定 50 条验收数据放在 `dailySalesMockData.ts`，类型放在 `dailySalesTypes.ts`。只有真实共享的报表表格能力才能进入 `frontend/src/components/report-table/**`。

## 18. Accessibility and Responsive Layout

- 所有筛选控件有可识别 label 或可访问名称。
- 图标按钮、分析图标、复制按钮、列宽 handle 和显隐按钮支持键盘与可见焦点。
- 状态、趋势和涨跌不能只依赖颜色表达。
- Modal、Drawer 和 Popover 使用 Ant Design 既有焦点管理能力。
- 桌面端保持参考截图的紧凑布局。
- 543px 窄屏允许工具栏与卡片自然换行，表格在自身容器内横向滚动。
- 窄屏不得产生 window/body 横向滚动或整页异常滚动。

## 19. Tests

实现阶段至少覆盖：

- 每日销售路由只对 `sales_daily_sales` 渲染新页面，其他 planned 页面继续使用既有占位页。
- 工具栏、“同步时间：待接入”、三张统计卡和两张趋势图渲染。
- 刷新、下载、`PageShell` 唯一帮助入口、列配置的视觉顺序，且页面没有第二套帮助逻辑。
- 隐藏统计和隐藏图表切换。
- 35 个字段完整且顺序严格一致，不包含截图额外字段。
- 分析 Modal、趋势 Popover、复制、金额 / 百分比、状态 Tag 和日志摘要。
- 列配置与产品管理一致，固定列不能取消、移除或重排。
- 列宽拖拽不触发表头排序。
- 默认 20 条，pageSize 支持 10 / 20 / 50 / 100，切换后回到第 1 页并清空选择。
- 表头、table body 和 pagination footer 是稳定的独立区域。
- 筛选、搜索、重置和 total 基于本地静态数据。
- 固定 50 条静态 UI 验收数据，空结果使用 Ant Design `Empty`，不伪造 Loading / Error。
- 页面不发起网络请求，不创建每日销售业务 storage。
- 产品管理页面回归测试通过。

不得使用 `.only` / `.skip` 或提高全局 timeout 掩盖问题。

## 20. Future API Integration

- 当前本地 mock、筛选、搜索、排序、分页、统计卡和图表仅用于 No-API UI 验收。
- 真实 API 接入后，筛选、搜索、排序和分页必须替换为后端查询，不得一次性加载全部销售记录。
- 统计汇总和趋势数据必须由经批准的数据源和后端聚合能力提供。
- 当前实现不构成最终 API、数据库、字段、币种、费用、利润或数据源契约。
- 真实 API 开发前必须完成接口数据源决策并获得单独 PRP 批准。
- 前端不得直接调用 Walmart、Lingxing、TEMU、Amazon 或其他外部平台。
- No-API 阶段不实现真实 Loading / Error；真实请求的 Loading / Error 状态在 API 接入任务中另行设计。

## 21. Acceptance Criteria

- [ ] 关联 PRP 已由负责人改为 `Approved` 并另行授权实现。
- [ ] 页面保持 `/sales/daily-sales`、`sales_daily_sales` 和 `planned`。
- [ ] 页面复用现有 `PageShell`，元数据来自 route resolver 传入的 `NavigationPage`，没有第二套标题、状态、帮助入口或页面框架。
- [ ] 视觉布局以负责人参考截图为主，但字段没有从截图复制。
- [ ] 同步时间显示“待接入”，右侧视觉顺序严格为刷新、下载、`PageShell` 唯一帮助入口、列配置。
- [ ] 三张统计卡和两张三序列趋势图符合页面层级。
- [ ] 表格严格显示 35 个业务字段及规定顺序。
- [ ] 列配置 Drawer 与产品管理一致，并且只包含 35 个字段。
- [ ] 固定表头、body 内滚、横向滚动和固定 pagination footer 正常。
- [ ] `10 → 20 → 50 → 100 → 10` 后表头稳定。
- [ ] No-API 提示、分析 Modal、趋势 Popover、复制和状态展示可验收。
- [ ] 固定使用 50 条静态 UI 验收数据，空结果使用 Ant Design `Empty`，且不伪造 Loading / Error。
- [ ] 产品管理共享能力接入无视觉和交互回退。
- [ ] 没有真实 API、数据库、外部请求、业务 storage 或新增依赖。

# Product Management No-API Page Specification

## 1. Document Status

```text
Status: Approved scope via related PRP
Owner Approval Required: Yes
Implementation Allowed: Yes, only within the related PRP's owner-approved No-API scope
```

关联 PRP：`PRPs/frontend-product-management-no-api-page-shell.md`。

关联 PRP 已获负责人批准并下发实现。本文件记录负责人后续视觉验收确认的最终 No-API 范围；页面仍保持 `planned`，不得标记为 `ready`。

## 2. Page Goal

建立“产品管理”的 No-API 页面结构基线，使负责人可以审查信息层级、操作入口、表格字段和详情分区。当前允许 50 条前端静态 UI 验收数据验证本地交互，不接 API，也不提供任何真实业务写入。

## 3. Navigation

```text
一级导航：产品
页面名称：产品管理
页面路径：/products/management
navigation key：products_product_management
页面状态：planned
```

标题、路径、状态和其他导航元数据继续来自 `frontend/src/config/navigation.ts`。不得修改 navigation、route resolver 或 Tab workspace。负责人后续批准 MainLayout / PageShell 仅为 breadcrumb right actions / page actions 做最小全局布局调整，详见下方 Owner-approved changes。

## 4. Page Grain and Identity

- 主表一行代表一个内部 SKU 产品记录。
- SKU 是业务展示和搜索字段，不是 React key、API 主键或数据库唯一标识。
- 未来 API 必须提供稳定内部记录 ID，供前端列表渲染和操作定位使用。
- 本规格不设计 API schema、数据库字段或唯一约束。
- 多店铺、多平台关系暂不建模。

## 5. Data-source Boundary

- 现有决策文件为 `docs/data-sources/decisions/products-basic-information-query-decision.md`，当前状态为 `BLOCKED_BY_OWNER_DECISION`。
- 该状态不阻止本 No-API 页面壳，但禁止据此设计或接入真实接口。
- 当前无产品数据 API，不发起网络请求。
- No-API 阶段允许 50 条前端静态 UI 验收数据：SKU 为 `UI-SAMPLE-001` 至 `UI-SAMPLE-050`，产品名称为 `验收示例产品 001` 至 `验收示例产品 050`。
- 静态数据仅用于 UI 验收，不伪装成真实业务数据、接口响应或同步结果，不写数据库。
- 当前本地筛选、搜索、排序和分页不构成后端接口契约；真实 API 接入后均应迁移为后端查询。
- WFS费用、采购价、头程运费、仓储费、建议售价、最低售价和清仓售价仅保留 UI 占位。
- 本规格不批准费用公式、币种、计算口径、字段来源或数据源权威归属。
- 后续 API 开发前必须完成独立的接口数据源决策和 API PRP。
- 前端不得直接调用 Walmart、Lingxing 或其他外部平台。

## 6. Top Action Area

页面内容区的单行工具栏包含：

- 产品等级。
- 标签。
- 连体搜索组件：搜索类型（默认 SKU）、搜索输入框、搜索图标、批量搜索图标。
- 列配置。
- 标签管理。
- “更多”下拉，其中仅包含“标记”。
- 重置。

页面右上角靠近“帮助”处显示 `最后同步时间：待接入` 和圆形同步图标。产品内容卡片内部不重复显示帮助或同步时间。同步图标 hover 和点击均提示 `同步接口待接入`。

除获批的本地筛选、搜索、排序、分页、选择、列显示/顺序和弹框状态外，所有业务操作只展示待接入提示，不执行新增、编辑、删除、导入、导出、同步、上传或保存。

页面复用现有 `PageShell`；主表优先使用 ProComponents `ProTable`；Modal、表单、按钮、空状态和提示使用 Ant Design。不得手写第二套复杂表格、分页或 Modal。

### Owner-approved changes after initial approval

负责人在最终视觉验收中批准以下最小全局布局改动：

- 帮助入口移动到 `MainLayout` 面包屑容器右侧。
- 产品管理页“最后同步时间 + 同步图标”通过 `PageShell` page actions 显示在帮助入口附近。
- 产品内容卡片内部不再显示帮助或同步时间。
- 该能力影响所有 `PageShell` 页面，因此必须记录为全局布局行为并覆盖 MainLayout / PageShell 测试。

该例外只允许 breadcrumb right actions / page actions，不允许修改 `navigation.ts`、`routeResolver.ts`、Tab workspace，不允许接 API、storage 或权限系统。

## 7. Filter Specification

- 当前支持产品等级筛选、标签筛选和 SKU 普通搜索，结果只作用于 50 条前端静态验收数据。
- WFS费用不作为顶部筛选项，只作为主表展示字段。
- 普通搜索点击搜索图标后执行本地 SKU 包含匹配；搜索类型当前固定为 SKU。
- 筛选、搜索和重置后回到第 1 页并清空当前已选项。
- 重置恢复全部 50 条静态验收数据。
- 当前无 API；筛选、搜索和重置不写 localStorage 或 sessionStorage。
- 未来筛选、搜索、排序和分页必须由后端处理；最终字段、枚举和查询契约由后续 API PRP 确认。

## 8. Main Table

主表表头固定为：

1. 选择框
2. 图片
3. SKU
4. 产品名称
5. 标签
6. 产品等级
7. WFS费用
8. 建议售价
9. 最低售价
10. 清仓售价
11. 操作

明确排除：

- 更新时间。
- 资料完整度 / 异常。

当前表格展示 50 条获批的前端静态 UI 验收数据，每行使用独立内部验收 ID 作为 React key，不使用 SKU。

- 选择框只支持当前页全选、取消选择和半选，不做跨页全选或选择全部查询结果。
- SKU 为蓝色链接，点击打开详情；SKU 与产品名称 hover 时显示复制图标。
- 标签在独立“标签”列展示；无标签显示 `-`，多个标签横向展示，超出可显示 `+N`。
- 不设独立“详情”列。“操作”列固定在右侧，内部显示“详情”和“操作 v”。
- “操作”下拉只包含“编辑”和“删除”；删除使用危险样式。当前分别提示 `产品编辑接口待接入`、`产品删除接口待接入`，不真实修改数据。
- 可排序列：SKU、产品等级、WFS费用、建议售价、最低售价、清仓售价。
- 不排序列：图片、产品名称、标签、操作。
- 当前排序仅作用于 50 条静态验收数据，不代表真实接口排序或费用/价格字段口径；真实数据接入后必须由后端分页查询排序，不得一次性加载全部 SKU。

### Column width resizing

支持拖拽列宽：图片、SKU、产品名称、标签、产品等级、WFS费用、建议售价、最低售价、清仓售价。选择框列和操作列不支持拖拽。

- resize handle 位于表头右边界，命中区域为 8px 至 12px，不占用表头文字区域。
- resize handle 不影响排序图标；pointerdown 必须阻止事件冒泡，拖拽不得触发表头排序。
- 列宽只在当前页面运行时生效，不写 storage。

### Table layout and scrolling

- 产品管理页面外层不滚动，工具栏不滚动，表头不滚动。
- 表格 body 占据剩余空间并内部滚动，pagination footer 固定在表格底部且不得进入 body 滚动区。
- `.ant-table-header` 不得参与 flex 收缩；`.ant-table-body` 只占剩余空间。
- 不得通过开启外层页面滚动解决布局问题。
- 切换 10 / 20 / 50 / 100 / 10 条后，表头不得被压缩、遮挡、顶起或与第一行重叠。

## 9. Batch SKU Search Popover

- 批量搜索不是居中 Modal；点击连体搜索组件右侧的批量图标，在搜索框下方打开 Popover / 下拉浮层。
- 标题 / 可访问名称：`批量搜索 SKU`。
- 说明文案：`精确搜索，一行一项，最多支持1000行`。
- 输入框占位文案：`请输入 SKU，一行一个`。
- 输入规则为一行一个 SKU。
- 忽略空行。
- 保留 SKU 原始大小写。
- 不支持逗号作为主要分隔规则。
- 最多 1000 行，超过时提示 `最多支持1000行`。
- 底部按钮文案：`清空`、`关闭`、`搜索`。
- 点击“搜索”只对静态验收数据做本地精确匹配，不发起网络请求。
- 关闭 Popover 后清空且不持久化输入内容。

## 10. Sync State

- 同步状态预留四种展示值：
  1. 未接入：`最后同步时间：待接入`。
  2. 同步中：`正在同步`。
  3. 成功：`上次同步：2小时前`，其中相对时间只作为未来格式示例。
  4. 失败：`上次同步：失败`。
- 当前只允许显示未接入状态，不模拟同步中、成功或失败。
- 当前在页面右上角靠近“帮助”处显示未接入状态与圆形同步图标；hover 和点击均提示 `同步接口待接入`。
- 同步状态是页面级信息，不是表格每行字段。
- 未来同步按钮只能请求后端创建异步任务，前端不得直接执行同步或调用外部平台。

## 11. Column Configuration Drawer

- “列配置”使用右侧 Drawer，不使用居中 Modal。
- 顶部提供“选择模板”和“保存为新模板”占位；当前不创建模板，点击只提示待接入。
- 左侧提供字段搜索和字段分组勾选，右侧提供已选字段列表；底部提供“恢复默认”“取消”“保存并应用”。
- 系统固定列“选择框”和“操作”不进入列配置，不可隐藏或拖拽。
- 固定业务列“图片”和“SKU”进入列配置但必须 checked + disabled，不可取消、移除或拖拽改变位置。
- 列配置允许字段仅包括：图片、SKU、产品名称、标签、产品等级、WFS费用、建议售价、最低售价、清仓售价、类目、产品采购价、头程运费、WFS配送费、采购交期、仓储费。
- 物流报关清关、图片信息、商品分析资料以及包装规格、单箱重量、单箱数量、外箱规格、单品规格、单品毛重、单品净重不得配置为主表列。
- 允许在 Drawer 内临时勾选字段，并使用原生拖拽或现有上下移动控件调整非固定字段顺序。
- “保存并应用”只在当前页面运行时应用列显示和顺序，刷新后恢复默认；不写 localStorage / sessionStorage，不调用 API，不假装创建模板。

## 12. Tag Modals

默认标签为：测品、清货、停售。

### Mark tags

- 通过顶部“更多 → 标记”打开；未选择产品时提示 `请先选择产品`。
- 已选择产品时打开标题为“标记标签”的 Modal，宽度约 520px 至 600px。
- 默认不选中标签，只允许临时选择或移除已有标签，不提供新建标签入口。
- 下拉选项显示标签颜色圆点。
- 点击保存提示 `标签接口待接入`，不真实保存、不修改表格、不写 storage、不调用 API。

### Tag management

- 标签管理只使用一个 Modal，不弹第二层添加标签 Modal。
- 顶部第一行为标签名输入框 + 新增 / 保存按钮；第二行为“标签颜色” + 7 个颜色圆点。
- 表格只包含“标签名”和“操作”。标签名列显示颜色圆点 + 标签名称；操作列包含“编辑”和“删除”。
- 编辑将标签名和颜色回填到顶部输入区。
- 新增、保存和删除均提示 `标签接口待接入`，不真实修改标签列表，不写 storage，不调用 API。

## 13. Product Detail Modal

- 使用居中 Modal。
- 建议宽度：`min(1100px, calc(100vw - 32px))`。
- 产品详情只能通过点击 SKU 或操作列中的“详情”打开，不提供“预览产品详情结构”等额外入口。
- 左侧显示产品图片占位、产品名称和 SKU，并提供四个分区菜单：基本信息、物流报关清关、图片信息、商品分析资料；默认选中基本信息。
- 以下均为 UI 空标签，不是已批准的 API schema、数据库字段或数据源契约：
  1. 基本信息
     - SKU
     - 类目
     - 产品等级
     - 产品采购价
     - 头程运费
     - WFS配送费
     - 采购交期
     - 仓储费
  2. 物流报关清关
     - 基本信息：
       - 中文报关名
       - 英文报关名
       - 中文材质
       - 英文材质
       - 中文用途
       - 英文用途
     - 报关信息：
       - 报关单价
       - 海关编码
     - 规格信息表格：
       - 包装规格
       - 单箱重量
       - 单箱数量
       - 外箱规格
       - 单品规格
       - 单品毛重
       - 单品净重
  3. 图片信息
     - 产品图片
  4. 商品分析资料
     - 竞品文案信息表
     - 卖家精灵关键词表
     - 图片分析表
     - 沃尔玛竞争ID
- 所有字段当前只显示空值占位，不展示模拟金额、图片、链接或产品资料。
- 未来 API 的稳定内部记录 ID 只用于技术标识，不在本规格中新增为可见字段。
- 主表 `WFS费用` 与详情 `WFS配送费` 当前不得默认视为同一口径；二者的字段来源、币种、单位、公式和映射均待独立数据源决策。

## 14. Pagination and Empty State

- 使用 Ant Design 原生 Pagination，显示总条数、上一页 / 下一页、页码、每页条数选择和“跳至”输入。
- 默认每页 10 条，pageSize 支持 10 / 20 / 50 / 100。
- 改变 pageSize 后回到第 1 页并清空已选产品；保留当前筛选、搜索和排序条件。
- 筛选、搜索和重置后清空已选产品；total 基于当前本地过滤结果。
- pagination footer 固定在表格底部，不进入 table body 滚动区。
- 当前总数和页数只描述 50 条静态验收数据，不伪装为真实接口 total。
- 无匹配结果时显示 No-API 空状态，不暗示同步、筛选或保存已经成功。
- pageSize、页码和选择状态不写 localStorage / sessionStorage。

## 15. Future Loading Strategy

- 首屏只加载当前页核心字段。
- 筛选、分页、排序和批量 SKU 搜索全部走后端。
- 产品详情按需加载。
- 图片懒加载。
- 同步状态使用独立接口。
- 同步按钮只创建后端异步任务。
- 前端不得直接调用 Walmart、Lingxing 或其他外部平台。
- 禁止全量加载全部 SKU、全部详情或全部图片。
- 列表与详情 API 的具体契约、缓存、新鲜度和数据所有权由后续数据源决策与 PRP 确定。

## 16. Accessibility and Responsive Layout

- 所有输入有可见 label，图标按钮有可访问名称。
- Modal 有明确标题，可通过键盘关闭，并保持合理焦点顺序和焦点返回。
- 状态和提示不能只依赖颜色表达。
- 宽屏保持筛选、操作和表格层级清晰；窄屏允许操作区换行和表格容器内部横向滚动。
- 页面不得造成 window/body 横向滚动；Modal 宽度不得超过视口。
- 桌面端和 543px 窄屏切换 10 / 20 / 50 / 100 / 10 条时，表头、首行、table body 和 pagination footer 不得错位。
- 图片未来接入时必须提供替代文本和懒加载属性。

## 17. Tests

实现与复审至少覆盖：

- 页面从既有路由和 navigation metadata 获取标题、路径与状态。
- 最终主表字段、选择框、操作列和两个明确排除字段。
- 50 条静态验收数据的固定 SKU / 产品名称格式，以及稳定内部验收 ID 作为 React key。
- 产品等级、标签、普通 SKU 搜索、批量 SKU 搜索、本地排序、重置和本地分页行为。
- 默认 10 条以及切换 10 / 20 / 50 / 100 后回到第 1 页、清空选择并保持筛选 / 搜索 / 排序。
- 表头位于独立 header 区，table body 内部滚动，pagination 位于 footer 区。
- 批量 SKU 输入按行处理、忽略空行并保留大小写。
- 批量搜索、同步、列配置和标签管理只显示规定的待接入状态。
- SKU 和操作列“详情”打开产品详情，且只包含四个获批分区。
- 标记标签、标签管理、列配置和列宽拖拽的运行时行为与 No-API 边界。
- PageShell 的帮助及产品管理同步状态显示在 MainLayout 面包屑右侧 page actions 区。
- SKU 未被用作 React key 或技术主键。
- 产品管理页面不得创建或写入标签、列配置等新 storage 数据；现有 MainLayout `tab_workspace` 行为必须保持，不得把其正常 sessionStorage 写入误判为产品页面违规。
- 键盘操作、Modal 可访问性和窄屏布局。

不得使用 `.only` / `.skip` 或提高全局 timeout 掩盖问题。

## 18. Explicit Exclusions

- 真实 API、后端、数据库、外部平台调用和数据源结论。
- 真实产品数据、接口返回的 mock 数据、随机数据或模拟同步成功；本规格明确批准的 50 条静态 UI 验收数据除外。
- API schema、数据库 schema、多店铺或多平台关系模型。
- 新增、编辑、删除、导入、导出、同步、上传和保存。
- 费用公式、币种、计算口径和数据源所有权。
- 标签和列配置持久化。
- 产品管理页面新增 localStorage / sessionStorage 数据；现有 `tab_workspace` 行为不在本任务修改范围。
- navigation、route resolver 和 Tab workspace 修改。
- 超出 breadcrumb right actions / page actions 的 MainLayout / PageShell 修改。

## 19. Acceptance Criteria

- [x] 关联 PRP 已由负责人改为 `Approved` 并另行下发实现任务。
- [ ] 页面保持 `/products/management`、`products_product_management` 和 `planned`。
- [ ] 顶部功能区包含全部指定入口和同步状态。
- [ ] 主表显示选择框及十个指定业务表头，并排除“更新时间”“资料完整度 / 异常”和独立“详情”列。
- [ ] 表格只展示 50 条获批的前端静态 UI 验收数据，不伪装真实业务数据或接口响应。
- [ ] 本地筛选、搜索、排序、分页、选择、标签、列配置和详情行为符合本规格。
- [ ] 详情 Modal 宽度响应式，包含四个顶层区域；“物流报关清关”内部包含“基本信息”“报关信息”和“规格信息”表格。
- [ ] 所有费用和价格只作为 UI 占位，不表达公式、币种或数据所有权。
- [ ] 产品详情列出全部 UI 字段，且“物流报关清关”内部包含“基本信息”和“报关信息”。
- [ ] 主表 `WFS费用` 与详情 `WFS配送费` 未被默认视为同一口径。
- [ ] 没有 API、真实业务写入、产品管理页面新增的 storage 数据或外部平台请求；现有 `tab_workspace` 保持不变。
- [ ] 10 / 20 / 50 / 100 / 10 pageSize 切换不压缩、遮挡或顶起表头，且不产生页面外层滚动。
- [ ] 没有修改 navigation、route resolver 或 Tab workspace；MainLayout / PageShell 只包含获批的 page actions 最小全局布局改动。

## 20. Rollback Boundary

实现阶段回滚边界为删除产品管理页面新增文件并还原本任务接入点：

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

其中 MainLayout / PageShell 只回滚本任务的 page actions 全局布局改动，不覆盖其他既有功能。回滚不涉及后端、数据库、依赖、storage schema、API、配置或数据迁移。

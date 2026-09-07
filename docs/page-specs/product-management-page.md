# Product Management No-API Page Specification

## 1. Document Status

```text
Status: Draft
Owner Approval Required: Yes
Implementation Allowed: No until owner changes the related PRP Status to Approved
```

关联 PRP：`PRPs/frontend-product-management-no-api-page-shell.md`。

本文件只定义页面规格，不授权实现。页面保持 `planned`，不得标记为 `ready`。

## 2. Page Goal

建立“产品管理”的 No-API 页面结构基线，使负责人可以审查信息层级、操作入口、表格字段和详情分区。当前页面不得展示假产品数据，不接 API，也不提供任何真实业务写入。

## 3. Navigation

```text
一级导航：产品
页面名称：产品管理
页面路径：/products/management
navigation key：products_product_management
页面状态：planned
```

标题、路径、状态和其他导航元数据继续来自 `frontend/src/config/navigation.ts`。不得修改 navigation、route resolver、MainLayout 或 Tab workspace。

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
- 当前不展示 mock、示例或随机产品记录。
- WFS费用、采购价、头程运费、仓储费、建议售价、最低售价和清仓售价仅保留 UI 占位。
- 本规格不批准费用公式、币种、计算口径、字段来源或数据源权威归属。
- 后续 API 开发前必须完成独立的接口数据源决策和 API PRP。
- 前端不得直接调用 Walmart、Lingxing 或其他外部平台。

## 6. Top Action Area

顶部功能区包含：

- 筛选区。
- 批量搜索 SKU。
- 同步数据。
- 页面级上次同步状态。
- 列配置。
- 标签管理。
- No-API 临时入口“预览产品详情结构”。

除筛选区的本地展开、输入和 Modal 开关外，当前所有操作只展示待接入状态，不执行新增、编辑、删除、导入、导出、同步、上传或保存。

页面复用现有 `PageShell`；主表优先使用 ProComponents `ProTable`；Modal、表单、按钮、空状态和提示使用 Ant Design。不得手写第二套复杂表格、分页或 Modal。

## 7. Filter Specification

- 筛选区预留 SKU / 产品名称关键词、产品等级、标签和 WFS费用控件位置。
- WFS费用筛选当前仅为 UI 占位，不定义金额区间、币种、枚举或后端查询参数。
- 当前无 API，不提交查询，不生成筛选结果，不伪造命中数量。
- 清空仅清除当前运行时输入，不写 localStorage 或 sessionStorage。
- 未来筛选、排序和分页必须由后端处理；最终字段、枚举和查询契约由后续 API PRP 确认。

## 8. Main Table

主表表头固定为：

1. 图片
2. SKU
3. 产品名称
4. 产品等级
5. WFS费用
6. 建议售价
7. 最低售价
8. 清仓售价
9. 详情
10. 操作

明确排除：

- 更新时间。
- 资料完整度 / 异常。

当前表格为空，不渲染假行。未来有数据时必须以 API 提供的稳定内部记录 ID 作为 React key，不得使用 SKU。

- SKU 以蓝色链接样式展示；未来点击后打开该记录的产品详情，当前空表不创建可点击假 SKU。
- “详情”列使用“查看详情”入口；当前只有真实行存在时才出现，No-API 阶段不伪造记录。
- “操作”列预留“编辑”和“删除”语义。No-API 阶段若入口可触发，只显示 `产品数据接口待接入`，不得打开可保存表单、删除数据或显示成功状态。

## 9. Batch SKU Search Modal

- Modal 标题：`批量搜索 SKU`。
- 说明文案：`请输入需要搜索的 SKU，一行一个`。
- 输入框占位文案：`请输入 SKU，一行一个`。
- 格式示例仅说明输入语法，不代表产品数据：

  ```text
  SKU-EXAMPLE-001
  sku-example-002
  ```

- 输入规则为一行一个 SKU。
- 忽略空行。
- 保留 SKU 原始大小写。
- 不支持逗号作为主要分隔规则。
- 底部按钮文案：`取消`、`搜索`。
- 点击“搜索”时不查询、不创建记录，只展示提示：`产品数据接口待接入`。
- 关闭 Modal 后不持久化输入内容。

## 10. Sync State

- 同步状态预留四种展示值：
  1. 未接入：`上次同步：待接入`。
  2. 同步中：`正在同步`。
  3. 成功：`上次同步：2小时前`，其中相对时间只作为未来格式示例。
  4. 失败：`上次同步：失败`。
- 当前只允许显示未接入状态，不模拟同步中、成功或失败。
- 点击同步按钮当前只提示：`同步接口待接入`。
- 同步状态是页面级信息，不是表格每行字段。
- 未来同步按钮只能请求后端创建异步任务，前端不得直接执行同步或调用外部平台。

## 11. Column Configuration Modal

- “列配置”打开居中 Modal，按以下字段组展示配置占位结构：
  - 基础信息：图片、SKU、产品名称、产品等级。
  - 费用与价格：WFS费用、建议售价、最低售价、清仓售价。
  - 详情与操作：详情、操作。
  - 可选详情字段：采购价、头程运费、仓储费、WFS配送费。
- 当前不保存、不应用永久列配置，也不写 localStorage 或 sessionStorage。
- 不新增字段，不改变本规格固定表头和明确排除项。
- 可选详情字段默认不进入固定主表；本阶段只展示字段组，不执行显示/隐藏或保存。
- 真实列配置行为需要后续独立批准。

## 12. Tag Management Modal

默认标签占位：

- 测品
- 清货
- 停售

- Modal 提供“新增标签”入口，并在每个默认标签旁提供可访问名称明确的“删除标签”入口。
- 点击新增或删除入口统一提示：`标签接口待接入`。
- 点击后不得改变默认标签列表，不新增、删除、编辑或保存标签，不写 storage，也不创建真实业务数据。

## 13. Product Detail Modal

- 使用居中 Modal。
- 建议宽度：`min(1100px, calc(100vw - 32px))`。
- 当前空表没有 SKU 可点击，顶部提供 No-API 临时入口：`预览产品详情结构`。
- 临时入口只打开空结构 Modal，不创建假产品记录；API 接入后删除该入口。
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
  3. 规格信息
     - 包装规格
     - 单箱重量
     - 单箱数量
     - 外箱规格
     - 单品规格
     - 单品毛重
     - 单品净重
  4. 图片信息
     - 产品图片
  5. 商品分析资料
     - 竞品文案信息表
     - 卖家精灵关键词表
     - 图片分析表
     - 沃尔玛竞争ID
- 所有字段当前只显示空值占位，不展示模拟金额、图片、链接或产品资料。
- 未来 API 的稳定内部记录 ID 只用于技术标识，不在本规格中新增为可见字段。
- 主表 `WFS费用` 与详情 `WFS配送费` 当前不得默认视为同一口径；二者的字段来源、币种、单位、公式和映射均待独立数据源决策。

## 14. Pagination and Empty State

- 表格下方保留分页结构位置；当前无 API，不生成虚假总数和页数。
- 空状态明确说明产品数据尚未接入，不展示示例 SKU。
- 批量 SKU 搜索使用 `产品数据接口待接入`；同步按钮使用 `同步接口待接入`。
- 空状态不得暗示同步、筛选或保存已经成功。

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
- 图片未来接入时必须提供替代文本和懒加载属性。

## 17. Tests

实现获批后至少覆盖：

- 页面从既有路由和 navigation metadata 获取标题、路径与状态。
- 固定主表字段及两个明确排除字段。
- 无 API 时表格为空且没有假产品记录。
- 批量 SKU 输入按行处理、忽略空行并保留大小写。
- 批量搜索、同步、列配置和标签管理只显示规定的待接入状态。
- 产品详情临时入口只打开空结构 Modal。
- SKU 未被用作 React key 或技术主键。
- 产品管理页面不得创建或写入标签、列配置等新 storage 数据；现有 MainLayout `tab_workspace` 行为必须保持，不得把其正常 sessionStorage 写入误判为产品页面违规。
- 键盘操作、Modal 可访问性和窄屏布局。

本 Draft 不授权新增测试或修改前端代码。

## 18. Explicit Exclusions

- 真实 API、后端、数据库、外部平台调用和数据源结论。
- 假数据、mock 产品行或模拟同步成功。
- API schema、数据库 schema、多店铺或多平台关系模型。
- 新增、编辑、删除、导入、导出、同步、上传和保存。
- 费用公式、币种、计算口径和数据源所有权。
- 标签和列配置持久化。
- 产品管理页面新增 localStorage / sessionStorage 数据；现有 `tab_workspace` 行为不在本任务修改范围。
- navigation、route resolver、MainLayout 和 Tab workspace 修改。

## 19. Acceptance Criteria

- [ ] 关联 PRP 已由负责人改为 `Approved` 并另行下发实现任务。
- [ ] 页面保持 `/products/management`、`products_product_management` 和 `planned`。
- [ ] 顶部功能区包含全部指定入口和同步状态。
- [ ] 主表只显示指定的十个表头，并排除“更新时间”和“资料完整度 / 异常”。
- [ ] 表格不展示假数据。
- [ ] 批量 SKU、同步状态、标签和详情 Modal 符合本规格。
- [ ] 详情 Modal 宽度响应式，包含五个顶层区域；“物流报关清关”内部包含“基本信息”和“报关信息”。
- [ ] 所有费用和价格只作为 UI 占位，不表达公式、币种或数据所有权。
- [ ] 产品详情列出全部 UI 字段，且“物流报关清关”内部包含“基本信息”和“报关信息”。
- [ ] 主表 `WFS费用` 与详情 `WFS配送费` 未被默认视为同一口径。
- [ ] 没有 API、真实业务写入、产品管理页面新增的 storage 数据或外部平台请求；现有 `tab_workspace` 保持不变。
- [ ] 没有修改 navigation、route resolver、MainLayout 或 Tab workspace。

## 20. Rollback Boundary

本阶段只有 Draft PRP 和 Page Spec。回滚边界是删除：

```text
PRPs/frontend-product-management-no-api-page-shell.md
docs/page-specs/product-management-page.md
```

不涉及前端代码、后端、数据库、依赖、配置或数据回滚。

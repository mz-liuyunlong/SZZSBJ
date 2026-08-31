# UI 组件清单

## 文件用途

本文件用于记录本项目计划使用和已经实现的通用 UI 组件。

AI 开发新页面前，必须先查看本文件，优先复用已有组件，避免重复造轮子。

## 组件分级

| 等级 | 说明 |
|---|---|
| Shared | 多个模块通用组件 |
| Feature | 某个业务模块内复用组件 |
| Page Local | 当前页面内部组件 |

## 初始通用组件规划

| 组件名 | 等级 | 建议目录 | 用途 | 使用场景 | 备注 |
|---|---|---|---|---|---|
| PageContainer | Shared | `frontend/src/components/layout/PageContainer.tsx` | 页面统一容器 | 所有后台页面 | 包含标题、面包屑、内容区 |
| PageHeader | Shared | `frontend/src/components/layout/PageHeader.tsx` | 页面标题区 | 需要独立标题/操作区的页面 | 不写具体业务逻辑 |
| StatusTag | Shared | `frontend/src/components/common/StatusTag.tsx` | 状态标签 | 订单/广告/库存等状态 | 颜色必须统一 |
| MoneyText | Shared | `frontend/src/components/common/MoneyText.tsx` | 金额展示 | 涉及金额字段 | 必须显示币种 |
| PercentText | Shared | `frontend/src/components/common/PercentText.tsx` | 百分比展示 | 广告、利润、退款率 | 统一小数位 |
| DateTimeText | Shared | `frontend/src/components/common/DateTimeText.tsx` | 时间展示 | 列表和详情页 | 统一时区展示 |
| EmptyState | Shared | `frontend/src/components/common/EmptyState.tsx` | 空数据状态 | 所有数据页 | 不要每页重复写 |
| ErrorState | Shared | `frontend/src/components/common/ErrorState.tsx` | 错误状态 | 所有数据页 | 可展示重试按钮 |
| DateRangeField | Shared | `frontend/src/components/forms/DateRangeField.tsx` | 日期范围筛选 | 报表、列表筛选 | 统一日期格式 |
| StoreSelect | Shared | `frontend/src/components/forms/StoreSelect.tsx` | 店铺选择 | 多店铺筛选 | 数据来自后端店铺接口 |
| SkuSearchInput | Shared | `frontend/src/components/forms/SkuSearchInput.tsx` | SKU 搜索 | 产品、销售、库存 | 支持 MSKU/SKU |
| DataTableToolbar | Shared | `frontend/src/components/tables/DataTableToolbar.tsx` | 表格工具栏 | 有批量操作的表格 | 不包含业务按钮逻辑 |
| BatchActionBar | Shared | `frontend/src/components/tables/BatchActionBar.tsx` | 批量操作栏 | 多选表格 | 具体按钮由页面传入 |
| TaskStatusBadge | Shared | `frontend/src/components/common/TaskStatusBadge.tsx` | 后台任务状态 | 导入、同步、AI 分析 | 统一状态颜色 |

## AI 使用规则

AI 开发新页面时必须先判断：

1. 当前页面是否已有可复用组件。
2. 是否需要新增页面专属组件。
3. 是否存在重复 UI 逻辑。
4. 是否应该抽成 shared 组件。
5. 是否存在过度封装风险。

AI 不允许在多个页面重复复制同一套筛选、状态标签、金额展示、日期展示和表格工具栏逻辑。

## 组件登记规则

新增 Shared 组件后，AI 必须更新本文件，说明组件用途、目录、使用场景和注意事项。

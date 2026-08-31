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

| 组件名 | 等级 | 建议目录 | 用途 | 使用场景 |
|---|---|---|---|---|
| PageContainer | Shared | `frontend/src/components/layout/PageContainer.tsx` | 页面统一容器 | 所有后台页面 |
| PageHeader | Shared | `frontend/src/components/layout/PageHeader.tsx` | 页面标题区 | 标题、描述、操作区 |
| StatusTag | Shared | `frontend/src/components/common/StatusTag.tsx` | 状态标签 | 订单/广告/库存等状态 |
| MoneyText | Shared | `frontend/src/components/common/MoneyText.tsx` | 金额展示 | 涉及金额字段 |
| PercentText | Shared | `frontend/src/components/common/PercentText.tsx` | 百分比展示 | 广告、利润、退款率 |
| DateTimeText | Shared | `frontend/src/components/common/DateTimeText.tsx` | 时间展示 | 列表和详情页 |
| EmptyState | Shared | `frontend/src/components/common/EmptyState.tsx` | 空数据状态 | 所有数据页 |
| ErrorState | Shared | `frontend/src/components/common/ErrorState.tsx` | 错误状态 | 所有数据页 |
| DateRangeField | Shared | `frontend/src/components/forms/DateRangeField.tsx` | 日期范围筛选 | 报表、列表筛选 |
| StoreSelect | Shared | `frontend/src/components/forms/StoreSelect.tsx` | 店铺选择 | 多店铺筛选 |
| SkuSearchInput | Shared | `frontend/src/components/forms/SkuSearchInput.tsx` | SKU 搜索 | 产品、销售、库存 |
| DataTableToolbar | Shared | `frontend/src/components/tables/DataTableToolbar.tsx` | 表格工具栏 | 有批量操作的表格 |
| BatchActionBar | Shared | `frontend/src/components/tables/BatchActionBar.tsx` | 批量操作栏 | 多选表格 |
| TaskStatusBadge | Shared | `frontend/src/components/common/TaskStatusBadge.tsx` | 后台任务状态 | 导入、同步、AI 分析 |

## 组件登记规则

新增 Shared 组件后，AI 必须更新本文件，说明组件用途、目录、使用场景和注意事项。

# Table Column and Report Rules

## Required Components

- 金额使用 `MoneyText` 或 catalog 中已实现的 canonical money cell。
- 百分比使用 `PercentText` 或 canonical percent cell。
- 时间使用 `DateTimeText` 或 canonical datetime cell。
- 状态使用 `StatusTag` 或 canonical status cell。
- 高密度报表优先使用 `ReportTableShell`。
- 搜索栏优先使用 `ConnectedSearch`、`StoreSelect`、`DateRangeField`、`SkuSearchInput` 中已实现且适用的组件。

使用前必须核对 Catalog status 和实际文件；planned 组件不得假装可复用。

## Table Contract

- 列定义集中且有稳定 key、字段语义、单位/币种/时区和 null 行为。
- 服务端分页、筛选、排序；禁止前端加载全量数据。
- 操作列、批量操作、固定表头、内部横向滚动、分页和密度保持统一。
- 列权限必须由后端控制；前端隐藏不构成安全。
- 空/error/stale/partial 状态不能用假数据填充。
- Display-only 计算必须标记非权威，不与后端指标混名。

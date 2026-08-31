# UI 风格规则

## 文件用途

本文件用于约束 React + Ant Design + ProComponents 页面风格，避免每个 AI 做出不同风格的后台页面。

## 总原则

1. 后台页面风格保持简洁、稳定、可读。
2. 优先使用 Ant Design 与 ProComponents，不随意手写复杂组件。
3. 页面统一使用 PageContainer / 页面标题区。
4. 筛选区、表格、批量操作、详情 Drawer、Modal 风格统一。
5. 不乱写 inline style。
6. 状态颜色、金额格式、日期格式统一。

## 列表页建议布局

```text
页面标题
↓
筛选区
↓
操作区
↓
表格
↓
分页
```

## 表格规则

1. 金额列用 `MoneyText`。
2. 百分比列用 `PercentText`。
3. 时间列用 `DateTimeText`。
4. 状态列用 `StatusTag`。
5. 操作列不放太多按钮，复杂操作放下拉菜单。

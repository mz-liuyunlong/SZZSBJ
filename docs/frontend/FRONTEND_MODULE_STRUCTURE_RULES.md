# Frontend Module Structure Rules

## Required Rules

- Page 负责组合和页面状态，不塞满所有业务、数据和视觉逻辑。
- API 调用不得写在 JSX 中；数据访问走批准的 typed client/service boundary。
- 表格列定义放在清晰的页面/feature 模块，不散落在 JSX 深处。
- 复杂筛选、URL/state 协调可抽专用 hook；简单逻辑不为抽象而抽象。
- 单页面专用组件留在 page/feature；两个以上页面真实复用时评估 Shared。
- Shared 组件不得 import 业务 page；禁止跨模块深层 import 内部实现。
- 优先扩展既有结构，不建立第二套 components、router、state 或 API 目录。

拆分以职责和真实复用为依据，不以任意行数作为唯一理由。

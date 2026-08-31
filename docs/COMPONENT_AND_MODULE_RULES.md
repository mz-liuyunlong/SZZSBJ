# 组件与模块封装规则

## 文件用途

本文件用于约束 AI 如何封装前端组件和后端模块。

本项目采用“一个功能一个模块、一个页面一个任务”的开发方式。AI 必须通过合理封装降低重复代码、降低上下文 token 消耗、提升可维护性。

## 总原则

1. 页面负责组合，不堆复杂逻辑。
2. 业务组件放在对应 feature 目录。
3. 通用组件放在 shared components 目录。
4. API 请求统一封装。
5. 类型统一定义。
6. 复杂业务逻辑封装到 hooks / services。
7. 后端按 Route / Schema / Service / Repository / Model 分层。
8. Celery 任务只做任务编排，不堆业务逻辑。
9. 不允许复制粘贴大段重复代码。
10. 不允许为了封装而过度抽象。

## 前端封装层级

```text
Page
Feature Component
Shared Component
Hook
API Client
Type
Constant
Utility
```

### Page

页面只负责：

- 页面布局
- 组合组件
- 绑定 hooks
- 控制页面级交互

页面不负责：

- 复杂业务计算
- 复杂数据转换
- 直接调用多个外部接口
- 大段重复 JSX
- 复杂权限判断

### Feature Component

业务组件只服务当前业务模块。

推荐目录：

```text
frontend/src/features/{module}/{feature}/components/
```

例如：

```text
frontend/src/features/ads/campaign-list/components/AdCampaignTable.tsx
```

### Shared Component

多个模块复用的组件才能放入：

```text
frontend/src/components/
```

Shared 组件不得包含具体业务模块逻辑。

## 什么时候必须抽组件

AI 遇到以下情况必须抽组件或先提出抽组件方案：

1. 同一 UI 结构在两个地方重复出现。
2. 单个页面文件超过 250 行。
3. 一个弹窗或 Drawer 超过 100 行。
4. 表格 columns 超过 8 列且包含复杂 render。
5. 筛选区包含 4 个以上筛选条件。
6. 同一状态 Tag 在多个页面重复。
7. 同一金额、日期、百分比展示规则重复。
8. API 请求 loading / error / empty 逻辑重复。
9. 一个函数超过 60 行。
10. 一个组件 props 超过 8 个，需要重新评估设计。

## 什么时候不要抽组件

以下情况不要抽组件：

1. 只使用一次且逻辑简单。
2. 抽象后命名含糊。
3. Props 太多导致更难理解。
4. 抽象只是为了减少行数，不提升语义。
5. 页面局部结构没有复用价值。
6. 业务组件被错误放进 common。
7. 为了通用而牺牲可读性。

## 后端模块封装规则

后端按以下层级组织：

```text
API Route
Schema
Service
Repository
Model
Task
Integration
```

### API Route

只负责接收请求、权限检查、参数校验、调用 Service、返回 Response。

### Service

负责业务规则、数据聚合、状态判断、金额计算、跨 Repository 编排、调用 Integration、触发 Celery 任务。

### Repository

负责数据库查询、新增、更新、删除和 SQLAlchemy 查询封装。

### Task

负责后台任务入口、任务状态更新、调用 Service 执行业务、失败重试。

### Integration

负责外部 API 客户端、鉴权封装、请求超时、错误转换、响应标准化。

## AI 开发前必须评估

每次开发页面前，AI 必须回答：

1. 本页面是否需要新组件？
2. 哪些组件是页面专属？
3. 哪些组件可能未来复用？
4. 是否需要自定义 Hook？
5. 是否需要 API client？
6. 是否需要 types.ts？
7. 是否需要 constants.ts？
8. 后端是否需要 Service？
9. 后端是否需要 Repository？
10. 是否涉及 Celery 任务？

## AI 完成后必须说明

1. 封装了哪些组件。
2. 为什么这样拆分。
3. 哪些组件是页面专属。
4. 哪些组件是通用组件。
5. 哪些逻辑放进 Hook。
6. 哪些 API 被封装。
7. 后端有哪些 Service / Repository。
8. 是否存在未来可复用点。

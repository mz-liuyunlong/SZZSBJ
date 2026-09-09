# Module Catalog and Ownership Rules

## Purpose

使模块职责、文件、读写边界和 owner 可发现。

## Required Rules

- 后端通用模块同 PR 更新 `docs/BACKEND_MODULE_CATALOG.md`。
- Shared 前端组件同 PR 更新 `docs/UI_COMPONENT_CATALOG.md`。
- 业务页面、数据接口和任务分别更新 Page、Data Interface 和 Task registries。
- Catalog 条目至少记录 name/key、owner、purpose、owned files、public contract、dependencies、writers/readers、status、tests、PRP/PR、non-scope。
- 一个文件只有一个主要 owning module；跨模块使用通过公开 contract，不深层导入内部实现。
- `planned` 目录或候选路径不得登记为 `implemented`。

## Stop Conditions

模块责任重叠、owner 缺失、循环依赖或新模块复制已有能力时，停止并由架构师确定边界。

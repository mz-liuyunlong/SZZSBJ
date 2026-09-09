# Architecture Decision Record Rules

## Purpose

为会长期约束多个任务的架构决定保留可追溯记录。

## Required Rules

- 影响技术栈、数据权威、模块边界、权限模型、部署、兼容或迁移方向的决定必须新增 ADR。
- ADR 放在 `docs/adr/`，编号稳定，不复用已撤销编号。
- ADR 至少包含：Status、Context、Decision、Alternatives、Consequences、Security/Data impact、Migration/Rollback、Owner approval、Related PRP/PR。
- 状态只用 `draft`、`approved`、`superseded`、`deprecated`。
- 新 ADR 通过链接 supersedes 旧 ADR，不改写历史决定。
- ADR 批准架构方向，不自动授权代码、数据库、外部 API 或部署。

## Stop Conditions

决定涉及业务口径、数据真源、财务、权限或生产风险但缺负责人确认时保持 `draft` 并停止实现。

# Definition of Done Rules

## Purpose

统一“完成”的证据，禁止以代码存在或口头说明替代验收。

## Required Evidence

任务只有同时满足以下适用项才可声明完成：

- 实现与批准的 PRP、prompt 和 allowlist 一致。
- 自动检查、必要人工验收和安全/范围检查已真实执行并报告。
- API contract、SOP、PageShell/help、权限、数据来源、审计和回滚按任务类型完成。
- 相关 Task、Page、Interface、Module、Component registry/catalog 已更新。
- `Explicitly not implemented` 和剩余风险明确。
- 架构师 Review PASS；负责人完成提交、PR 和合并后才可标记 `implemented`。

## Not Done

`Draft`、`planned`、代码未提交、测试未运行、CI 失败、仅本地可见、mock-only、no-api 或缺少负责人批准均不等于完成。

详细测试证据遵守 `docs/VALIDATION_AND_TESTING_RULES.md`。

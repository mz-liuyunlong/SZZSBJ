# Codeowners and Reviewers Rules

## Purpose

定义审查责任，不把 CODEOWNERS 当权限或自动批准系统。

## Required Rules

- `.github/CODEOWNERS` 是 GitHub 审查路由真源；本文不修改其成员。
- 负责人批准业务范围、风险和合并；架构师负责边界与只读复审；工程师负责实现和测试。
- 敏感领域至少需要相应领域 Review：数据库/migration、权限/安全、财务口径、CI/部署、外部集成。
- CODEOWNERS 请求不等于负责人批准，也不授权数据库、API、部署或 Git 写操作。
- Reviewer 必须核对 task/PRP、allowlist、registries、测试、secret scan 和回滚。
- 自审不能替代要求的独立架构 Review。

## Stop Conditions

实际 owner 不明确、CODEOWNERS 使用占位账号、必要领域 reviewer 缺失或 review 与负责人决定冲突时停止合并。

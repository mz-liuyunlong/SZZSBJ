# SZZSBJ Rule Pack v2.0 文件索引

## 1. 最高优先级入口

| 文件 | 用途 |
|---|---|
| `AGENTS.md` | 所有 AI 的总规则 |
| `AI_DAILY_RULES.md` | 日常开发轻量入口 |
| `README_AI_RULES.md` | 规则包使用说明 |
| `docs/00_RULE_PACK_V2_OVERVIEW.md` | v2 总览和优先级 |
| `docs/01_PROJECT_DECISIONS.md` | 项目决策日志 |

## 2. 工程架构

| 文件 | 用途 |
|---|---|
| `docs/architecture/frontend.md` | 前端架构、PageShell、导航、帮助入口 |
| `docs/architecture/backend.md` | 后端分层、模块、任务 |
| `docs/architecture/api.md` | API 返回、分页、错误码、OpenAPI |
| `docs/architecture/database.md` | PostgreSQL、旧库只读、新库分层 |
| `docs/architecture/security-secrets-integrations.md` | Token、飞书、Webhook、密钥管理 |

## 3. 业务规则

| 文件 | 用途 |
|---|---|
| `docs/business-rules/navigation-spec.md` | 最终导航、API文档位置、SOP入口 |
| `docs/business-rules/permission-model.md` | 动态角色、权限点、审计 |
| `docs/business-rules/organization-and-data-scope.md` | 组织架构、小组长、组员、数据范围 |
| `docs/business-rules/fee-rules-versioning.md` | 佣金、汇率、费用规则版本化 |
| `docs/business-rules/time-money-metric-rules.md` | 时间、金额、指标口径 |
| `docs/business-rules/data-lineage-and-quality.md` | 数据血缘、质量、新鲜度 |

## 4. 交付标准

| 文件 | 用途 |
|---|---|
| `docs/delivery/api-documentation-standard.md` | API 文档和 API 文档页面 |
| `docs/delivery/sop-help-standard.md` | 页面右上角帮助和 SOP |
| `docs/delivery/codex-task-standard.md` | Codex 任务粒度与完成报告 |
| `docs/delivery/ci-quality-gate.md` | CI 质量门禁 |
| `docs/delivery/acceptance-checklist.md` | 功能验收清单 |

## 5. 数据库细化

| 文件 | 用途 |
|---|---|
| `docs/database/INITIAL_SCHEMA_PLAN.md` | 初始 schema 表清单 |
| `docs/database/LEGACY_DB_READONLY_PLAN.md` | 旧库只读方案 |
| `docs/database/ACCOUNT_PERMISSION_PLAN.md` | 数据库账号权限 |

## 6. 运维规则

| 文件 | 用途 |
|---|---|
| `docs/operations/deployment-environments.md` | local/staging/production 规则 |
| `docs/operations/release-rollback-backup.md` | 发布、回滚、备份、锁账 |
| `docs/operations/notification-todo-approval.md` | 通知、待办、审批 |

## 7. 任务队列

| 文件 | 用途 |
|---|---|
| `docs/tasks/FIRST_30_CODEX_TASKS.md` | 第一批 30 个 Codex 任务 |

## 8. 模板

| 文件 | 用途 |
|---|---|
| `templates/frontend/src/config/navigation.ts` | 最终导航配置模板 |
| `templates/backend/app/core/response.py` | API Response 模板 |
| `templates/backend/app/core/permissions.py` | 权限校验模板 |
| `templates/backend/alembic/versions/0001_initial_skyc_v2_core_tables.py` | 初始 Alembic migration 草稿 |
| `templates/bootstrap/.node-version` | Node 版本模板 |
| `templates/bootstrap/.python-version` | Python 版本模板 |

## 9. 规则冲突优先级

如果旧文件和 v2 新文件冲突，以 v2 新文件为准。

优先级：

```text
AGENTS.md
AI_DAILY_RULES.md
docs/00_RULE_PACK_V2_OVERVIEW.md
docs/01_PROJECT_DECISIONS.md
docs/architecture/*
docs/business-rules/*
docs/delivery/*
```

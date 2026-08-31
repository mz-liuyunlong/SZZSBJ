# 规则包文件索引

## 最高级规则

| 文件 | 用途 |
|---|---|
| `AGENTS.md` | 所有 AI 必须遵守的总规则 |
| `AI_START_HERE.md` | 任何 AI 工具的通用启动入口 |
| `AI_ONBOARDING.md` | 新开发者第一次让 AI 接手项目时的启动流程 |
| `AI_DAILY_RULES.md` | 日常开发轻量入口，先读它再按任务选择 docs 和 skills |
| `README_AI_RULES.md` | 人看的规则包说明 |
| `RULE_PACK_FILE_INDEX.md` | 本文件，索引所有规则 |
| `INSTALL_TO_PROJECT.md` | 如何把规则包放入项目 |
| `docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md` | AI 首次接手项目时主动检测并协助安装官方 Ponytail 插件的规则 |
| `docs/tools/PONYTAIL_INSTALL_GUIDE.md` | Codex / Claude Code 安装 Ponytail 插件的团队说明 |

## 项目建设和开发方式

| 文件 | 用途 |
|---|---|
| `docs/TECH_STACK.md` | 固定技术栈 |
| `docs/DEVELOPMENT_PHASES.md` | 开发阶段规划 |
| `docs/PROJECT_BOOTSTRAP_RULES.md` | 新项目初始化规则 |
| `docs/PROJECT_STRUCTURE.md` | 目录结构规则 |
| `docs/FEATURE_SLICE_DEVELOPMENT_RULES.md` | 一个功能一个模块、一个页面一个任务 |
| `docs/COMPONENT_AND_MODULE_RULES.md` | 前端组件与后端模块封装 |
| `docs/CODE_COMMENT_RULES.md` | 维护型注释规则 |
| `docs/AI_GIT_DEV_RULES.md` | Git 分支和提交规则 |
| `docs/AI_TECH_DEV_RULES.md` | AI 技术实现规则 |
| `docs/PONYTAIL_COMPATIBILITY_RULES.md` | 所有 AI 默认开启的 Ponytail 规则，防止过度设计、重复代码和无意义依赖 |

## old-system 与重建

| 文件 | 用途 |
|---|---|
| `docs/OLD_SYSTEM_READONLY_RULES.md` | old-system 只读规则 |
| `docs/REBUILD_MAPPING_RULES.md` | 旧功能映射到新系统规则 |
| `docs/old-system-analysis/README.md` | 旧系统分析输出目录说明 |

## 页面、UI、API、后端

| 文件 | 用途 |
|---|---|
| `docs/UI_COMPONENT_CATALOG.md` | 通用 UI 组件清单 |
| `docs/BACKEND_MODULE_CATALOG.md` | 后端模块清单 |
| `docs/UI_STYLE_RULES.md` | UI 风格与 Ant Design 使用规则 |
| `docs/PAGE_DEVELOPMENT_CHECKLIST.md` | 页面开发检查清单 |
| `docs/API_DESIGN_RULES.md` | API 设计规则 |
| `docs/API_CONTRACT_RULES.md` | API 契约规则 |
| `docs/api-contracts/README.md` | 实际 API 契约目录说明 |
| `docs/page-specs/README.md` | 页面需求文档目录说明 |

## 数据、财务、同步、性能

| 文件 | 用途 |
|---|---|
| `docs/DATABASE_RULES.md` | 数据库和 Alembic 规则 |
| `docs/DATA_MODELING_RULES.md` | 业务数据建模规则 |
| `docs/DATA_SOURCE_AND_LINEAGE_RULES.md` | 数据来源和字段血缘规则 |
| `docs/DATA_QUALITY_RULES.md` | 数据质量规则 |
| `docs/DATA_SYNC_RULES.md` | 平台数据同步规则 |
| `docs/FINANCIAL_CALCULATION_RULES.md` | 财务计算规则 |
| `docs/TIMEZONE_AND_CURRENCY_RULES.md` | 时区和币种规则 |
| `docs/PERFORMANCE_RULES.md` | 性能规则 |

## 安全、发布、运维

| 文件 | 用途 |
|---|---|
| `docs/SECURITY_RULES.md` | 密钥和安全规则 |
| `docs/ENVIRONMENT_CONFIG_RULES.md` | 环境变量规则 |
| `docs/DEPENDENCY_MANAGEMENT_RULES.md` | 依赖管理规则 |
| `docs/EXTERNAL_API_INTEGRATION_RULES.md` | 外部 API 接入规则 |
| `docs/LLM_PROVIDER_ADAPTER_RULES.md` | LLM 调用层规则 |
| `docs/PERMISSION_AND_AUDIT_RULES.md` | 权限与操作日志规则 |
| `docs/ROLE_PERMISSION_MATRIX.md` | 角色权限矩阵 |
| `docs/LOGGING_RULES.md` | 日志规则 |
| `docs/OBSERVABILITY_RULES.md` | 监控与可观察性规则 |
| `docs/RELEASE_AND_ROLLBACK_RULES.md` | 发布与回滚规则 |
| `docs/DEPLOYMENT_RULES.md` | 部署规则模板 |
| `docs/BACKUP_AND_RECOVERY_RULES.md` | 备份与恢复规则 |


## Skill 自发现入口

AI 不需要用户手动指定 Skill。

每次任务开始前，AI 应先读取：

1. `AI_DAILY_RULES.md`
2. `skills/README.md`

再根据任务类型选择具体 Skill。

不要一次性读取全部 `skills/**/SKILL.md`，只读取本次任务相关的 Skill。

## Skills

所有项目级 Skills 放在 `skills/`。如果 AI 工具不能自动识别 Skill，也必须把对应 `SKILL.md` 当普通规则文档读取。


| Skill 文件 | 用途 |
|---|---|
| `skills/feature-slice-planner/SKILL.md` | 单功能 / 单页面任务规划 |
| `skills/react-component-architect/SKILL.md` | React 组件拆分与复用设计 |
| `skills/old-system-readonly-analyzer/SKILL.md` | 只读分析旧系统 |
| `skills/rebuild-mapping-planner/SKILL.md` | old-system 功能映射新系统 |
| `skills/backend-module-designer/SKILL.md` | 后端模块分层设计 |
| `skills/background-task-designer/SKILL.md` | Celery 后台任务设计 |
| `skills/api-contract-designer/SKILL.md` | API 契约设计 |
| `skills/page-acceptance-checker/SKILL.md` | 页面验收检查 |
| `skills/external-api-integration-designer/SKILL.md` | 外部 API 接入设计 |
| `skills/llm-provider-adapter-designer/SKILL.md` | LLM 调用层设计 |
| `skills/data-lineage-analyzer/SKILL.md` | 数据来源和字段血缘分析 |
| `skills/data-sync-designer/SKILL.md` | 数据同步任务设计 |
| `skills/financial-calculation-reviewer/SKILL.md` | 财务公式审查 |
| `skills/performance-reviewer/SKILL.md` | 性能审查 |
| `skills/permission-matrix-designer/SKILL.md` | 权限矩阵设计 |
| `skills/code-review-checker/SKILL.md` | PR 自检与风险检查 |
| `skills/rule-pack-maintainer/SKILL.md` | 规则包维护，防止规则冲突 |

## Ponytail 默认开启入口

本项目不依赖用户手动记住、手动引用或安装 Ponytail 才能执行简化原则。Ponytail 在本项目中默认开启。

AI 开发代码时必须读取：

```text
docs/PONYTAIL_COMPATIBILITY_RULES.md
```

该文件用于所有 AI 工具：Codex、Cursor、Claude Code、GitHub Copilot 和其他 AI。

如果当前工具已经安装 Ponytail 官方插件，可以使用插件；如果未安装，则按本项目文件执行默认开启规则。AI 不得把 Ponytail 当成可选 Skill，也不得因为用户没有提到 Ponytail 而跳过。


---

## AI 工具首次配置入口

开发者第一次拉取项目后，AI 必须主动读取：

```text
AI_ONBOARDING.md
docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md
docs/tools/PONYTAIL_INSTALL_GUIDE.md
```

并在用户确认后协助执行：

```bash
bash scripts/check-ai-tools.sh
bash scripts/setup-ai-tools.sh
```

支持官方 Ponytail 插件的工具优先安装官方插件；安装失败时使用 `docs/PONYTAIL_COMPATIBILITY_RULES.md` 兜底。

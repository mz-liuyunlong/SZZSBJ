# 项目级 AI Skills

## 文件用途

本目录存放项目级 AI Skills。它们是可以被任何 AI 工具读取的 Markdown 工作流程，不依赖某个开发者本机环境。

如果 AI 工具不能自动识别 Skill，也必须把对应 `SKILL.md` 当作普通规则文档读取。


## Skill 选择方式

本项目采用 Skill 自发现机制。

用户不需要记住有哪些 Skill，也不需要手动指定 Skill。AI 必须根据任务内容，自行判断需要读取哪些 Skill。

AI 选择 Skill 时必须遵守：

1. 先判断任务类型。
2. 再匹配相关 Skill。
3. 只读取本次任务必要的 Skill。
4. 不一次性读取全部 Skill。
5. 修改代码前先说明选择原因。
6. 用户确认后再执行开发。

## 常见任务与 Skill 对应关系

| 任务类型 | 应读取 Skill |
|---|---|
| 新增页面 / 新增功能 | `skills/feature-slice-planner/SKILL.md` |
| React 页面 / 组件拆分 | `skills/react-component-architect/SKILL.md` |
| 参考旧系统 | `skills/old-system-readonly-analyzer/SKILL.md` |
| old-system 功能映射 | `skills/rebuild-mapping-planner/SKILL.md` |
| 后端接口 / 后端模块 | `skills/backend-module-designer/SKILL.md` |
| API 契约 | `skills/api-contract-designer/SKILL.md` |
| Celery 后台任务 | `skills/background-task-designer/SKILL.md` |
| 数据同步 | `skills/data-sync-designer/SKILL.md` |
| 字段来源 / 数据血缘 | `skills/data-lineage-analyzer/SKILL.md` |
| 财务 / 利润 / 金额计算 | `skills/financial-calculation-reviewer/SKILL.md` |
| 性能 / 大表查询 | `skills/performance-reviewer/SKILL.md` |
| 权限矩阵 | `skills/permission-matrix-designer/SKILL.md` |
| 页面验收 | `skills/page-acceptance-checker/SKILL.md` |
| 外部 API 接入 | `skills/external-api-integration-designer/SKILL.md` |
| LLM 调用层 | `skills/llm-provider-adapter-designer/SKILL.md` |
| PR 自检 | `skills/code-review-checker/SKILL.md` |
| Ponytail 兼容 / 规则守卫 | `skills/ponytail-compatibility/SKILL.md` |
| 规则包维护 | `skills/rule-pack-maintainer/SKILL.md` |

AI 开始开发前必须先输出“本次 Skill 判断”，包括：任务类型、选择的 Skill、选择原因、不读取的 Skill、相关 docs、初步计划。

## Skill 列表

| Skill | 用途 |
|---|---|
| `feature-slice-planner` | 单功能 / 单页面任务规划 |
| `react-component-architect` | 前端组件拆分与复用设计 |
| `old-system-readonly-analyzer` | 只读分析旧系统 |
| `rebuild-mapping-planner` | old-system 功能映射新系统 |
| `backend-module-designer` | 后端模块分层设计 |
| `background-task-designer` | Celery 后台任务设计 |
| `api-contract-designer` | API 契约设计 |
| `page-acceptance-checker` | 页面验收检查 |
| `external-api-integration-designer` | 外部 API 接入设计 |
| `llm-provider-adapter-designer` | LLM 调用层设计 |
| `data-lineage-analyzer` | 数据来源和字段血缘分析 |
| `data-sync-designer` | 数据同步任务设计 |
| `financial-calculation-reviewer` | 财务公式审查 |
| `performance-reviewer` | 性能审查 |
| `permission-matrix-designer` | 权限矩阵设计 |
| `code-review-checker` | PR 自检与风险检查 |
| `rule-pack-maintainer` | 规则包维护，防止规则冲突 |
| `ponytail-compatibility` | Ponytail 兼容与规则守卫 |

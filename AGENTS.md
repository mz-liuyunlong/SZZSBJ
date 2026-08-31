# 项目 AI 开发总规则

## 文件用途

本文件是本项目所有 AI 开发助手必须遵守的最高级项目规则。

本项目不限定开发者使用哪一种 AI 工具。无论使用 Codex、Cursor、Claude Code、GitHub Copilot 或其他 AI，只要 AI 参与本项目的代码生成、修改、解释、测试、提交、PR 或 Code Review，都必须遵守本文件和项目内其他规则文档。

规则只有一套。不同工具的入口文件只是为了让不同 AI 能读取同一套规则，不代表不同 AI 有不同标准。

---

## 1. 项目定位

本项目是**新系统重建项目**。

- 新系统代码从零开始建设。
- 旧系统代码可以放在 `old-system/` 目录中，仅作为只读参考。
- `old-system/` 用于帮助 AI 理解旧功能、页面、API、数据库字段、业务规则和数据流。
- `old-system/` 不是新系统代码目录，不允许继续在其中开发。
- 新系统代码必须放在 `frontend/`、`backend/`、`docs/`、`.github/`、`.cursor/`、`skills/` 等明确目录中。

AI 的目标不是快速堆代码，而是按固定技术栈，从第一行代码开始建设一个可维护、可测试、可审查、可回滚、可交接的生产级系统。

---

## 2. AI 工具无关原则

AI 不允许因为工具不同、上下文没有自动加载、用户没有再次提醒，绕过以下规则：

- Git 分支规则
- 单功能开发规则
- 技术栈规则
- old-system 只读规则
- 组件与模块封装规则
- 注释规则
- API 契约规则
- 数据库迁移规则
- Celery 后台任务规则
- 外部 API 接入规则
- LLM 调用层规则
- 权限与操作日志规则
- 安全与密钥规则
- 测试与验收规则
- 数据来源与血缘规则
- 财务计算规则
- 性能规则
- 发布与回滚规则
- 文档更新规则

如果规则冲突，AI 必须停止修改并向用户确认，不能自行选择更方便的规则。

---

## 3. 最高优先级禁令

未经项目负责人明确授权，AI 不允许执行以下行为：

1. 直接修改 `main` 分支。
2. 直接修改 `dev` 分支。
3. 自行合并到 `main` 或 `dev`。
4. 执行 `git push --force`。
5. 执行 `git reset --hard`。
6. 执行 `git clean -fd`。
7. 修改、格式化、删除 `old-system/` 下任何文件。
8. 在 `old-system/` 中开发新功能或修复旧 Bug。
9. 从 `old-system/` 直接复制代码到新系统。
10. 新系统代码直接 import / require `old-system/` 中的文件。
11. 修改 `.env`、密钥、Token、服务器密码、SSH 私钥。
12. 把密钥写入代码、日志、文档、测试或 Git。
13. 修改生产数据库。
14. 手工修改生产数据库结构。
15. 重启生产服务。
16. 修改 Nginx、systemd、防火墙、部署脚本等生产配置。
17. 自行更换技术栈。
18. 引入第二套 UI 框架、第二套 ORM、第二套任务系统、第二套状态管理方案。
19. 大范围格式化无关文件。
20. 顺手重构无关模块。

如任务可能触发以上行为，AI 必须先说明原因、风险、替代方案，并等待用户确认。

---

## 4. 固定技术栈

### 前端

- React
- TypeScript
- Vite（react-ts）
- Ant Design
- ProComponents
- React Router
- Zustand
- ECharts

### 后端

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- Redis
- Celery
- LLM Provider Adapter，默认实现使用 OpenAI Python SDK

AI 不允许自行改成其他替代技术，除非项目负责人明确批准。

详细说明见：`docs/TECH_STACK.md`。

---

## 5. 开发方式：一个功能一个模块，一个页面一个任务

本项目所有开发必须按功能切片推进：

1. 一个任务只做一个明确功能。
2. 一个任务最多只做一个页面。
3. 一个任务只允许影响一个业务模块。
4. 一个任务只建立必要的最小前后端闭环。
5. 一个任务必须可以独立测试。
6. 一个任务必须可以独立回滚。
7. 一个任务必须单独建分支。
8. 一个任务必须单独提交 PR。

禁止一次性生成整个系统、整个业务模块、多个页面或多个无关接口。

详细说明见：`docs/FEATURE_SLICE_DEVELOPMENT_RULES.md`。

---

## 6. old-system 只读边界

`old-system/` 是旧系统代码归档目录，只允许只读分析。

AI 可以读取 `old-system/` 来理解旧页面、旧 API、旧数据库字段、旧业务计算规则、旧导入导出逻辑、旧定时任务和旧第三方接口调用方式。

AI 不允许：

- 修改 `old-system/`
- 格式化 `old-system/`
- 删除 `old-system/`
- 在 `old-system/` 中安装依赖
- 在 `old-system/` 中运行写入数据库的脚本
- 复制旧代码到新系统
- 让新系统直接依赖旧系统代码

如果参考了旧系统，AI 必须先输出旧系统分析，再设计新系统实现方案，等待用户确认后才能开发。

详细说明见：`docs/OLD_SYSTEM_READONLY_RULES.md` 与 `docs/REBUILD_MAPPING_RULES.md`。

---

## 7. 组件与模块封装

AI 开发页面前必须先评估组件和模块拆分方案。

前端通过以下方式封装：

- Page：页面组合
- Feature Components：业务专属组件
- Shared Components：通用组件
- Hooks：状态和请求逻辑
- API Client：接口调用
- Types：类型定义
- Constants：常量
- Utils：纯工具函数

后端通过以下方式封装：

- Route：接口入口
- Schema：请求与响应结构
- Service：业务逻辑
- Repository：数据库访问
- Model：数据表定义
- Task：Celery 任务编排
- Integration：外部 API 客户端

禁止把页面写成巨型文件，禁止把后端 Route 写成业务大杂烩。

详细说明见：`docs/COMPONENT_AND_MODULE_RULES.md`、`docs/UI_COMPONENT_CATALOG.md`、`docs/BACKEND_MODULE_CATALOG.md`。

---

## 8. 项目级 Skills

本项目包含项目级 AI Skills，目录为：

```text
skills/
```

任何 AI 工具如不支持自动加载 Skill，也必须把对应 `SKILL.md` 当作普通项目规则文档读取。

| 场景 | 必须读取 |
|---|---|
| 新增功能 / 页面 | `skills/feature-slice-planner/SKILL.md` |
| 前端组件拆分 | `skills/react-component-architect/SKILL.md` |
| 只读分析旧系统 | `skills/old-system-readonly-analyzer/SKILL.md` |
| 旧功能映射新系统 | `skills/rebuild-mapping-planner/SKILL.md` |
| 后端模块设计 | `skills/backend-module-designer/SKILL.md` |
| 后台任务设计 | `skills/background-task-designer/SKILL.md` |
| API 契约设计 | `skills/api-contract-designer/SKILL.md` |
| 页面验收 | `skills/page-acceptance-checker/SKILL.md` |
| 外部 API 接入 | `skills/external-api-integration-designer/SKILL.md` |
| LLM 调用层设计 | `skills/llm-provider-adapter-designer/SKILL.md` |
| 数据血缘分析 | `skills/data-lineage-analyzer/SKILL.md` |
| 数据同步设计 | `skills/data-sync-designer/SKILL.md` |
| 财务公式审查 | `skills/financial-calculation-reviewer/SKILL.md` |
| 性能审查 | `skills/performance-reviewer/SKILL.md` |
| 权限矩阵设计 | `skills/permission-matrix-designer/SKILL.md` |
| PR 自检 | `skills/code-review-checker/SKILL.md` |
| 规则包维护 | `skills/rule-pack-maintainer/SKILL.md` |

---

## 9. 开工前必须输出计划

AI 修改代码前，必须先输出：

1. 已读取哪些规则文件。
2. 任务理解。
3. 本次任务范围。
4. 是否参考 `old-system/`。
5. 前端组件拆分方案。
6. 后端模块拆分方案。
7. API 契约草案。
8. 数据来源和字段血缘。
9. 是否涉及数据库。
10. 是否涉及 Celery。
11. 是否涉及外部 API。
12. 是否涉及 LLM 调用。
13. 是否涉及权限和操作日志。
14. 财务/金额/时间口径。
15. 性能风险。
16. 测试和验收方式。

用户确认前，不要修改代码。

---

## 10. 完工后必须输出报告

完成后必须执行或要求用户执行：

```bash
git status
git diff --stat
```

并输出：当前分支、修改文件清单、每个文件修改原因、组件/模块封装、old-system 参考情况、共享代码影响、API 契约、数据库变更、Celery 任务、权限日志、数据血缘、测试结果、验收结果、风险点、回滚方式、文档更新情况。

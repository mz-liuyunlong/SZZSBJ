# Project Rule Pack V1.0

## 0. 文件用途

本文件是新系统重建项目中所有 AI 开发助手必须遵守的最高级项目规则。无论使用 Codex、Cursor、Claude Code、GitHub Copilot、Gemini、OpenCode 或其他 AI，只要 AI 参与本项目的代码生成、修改、解释、测试、提交、PR 或 Code Review，都必须遵守本文件。

**Project Rule Pack 版本：V1.0。**

---

## 1. 最高优先级顺序

AI 在执行任何任务前，必须按以下优先级判断规则冲突：

```text
1. 用户当前最新明确指令
2. AGENTS.md / Project Rule Pack 安全边界
3. AI_DAILY_RULES.md
4. 已确认的 PRP / 任务说明
5. .planning/current/ 本地计划文件
6. 外部 AI 工具：Context7 / planning-with-files / Superpowers / Vercel Agent Skills / 其他已批准工具
```

外部 Skill 是辅助工具，不是项目权威。任何 Skill 与本文件冲突时，必须停止并询问。

---

## 2. 项目定位

本项目是 **新系统重建项目**。

- 新系统从零开始建设。
- 旧系统代码可以放在 `old-system/`，仅作为只读参考。
- `old-system/` 不允许修改、格式化、重构、安装依赖、运行写入任务或复制旧架构到新系统。
- 新系统代码必须放在 `frontend/`、`backend/`、`docs/`、`scripts/`、`.github/`、`.cursor/`、`skills/` 等明确目录中。
- 项目目标不是快速堆页面，而是建设一个可维护、可测试、可审查、可回滚、可交接的企业级运营数据系统。

---

## 3. 固定技术栈

| 项目 | 最终规则 |
|---|---|
| 数据库 | PostgreSQL |
| Python 版本 | Python 3.13 |
| Node 版本 | Node.js 24 LTS |
| 前端包管理器 | npm |
| 后端依赖管理 | uv + pyproject.toml + uv.lock |
| 前端 | React + TypeScript + Vite react-ts |
| UI | Ant Design + ProComponents |
| 路由 | React Router |
| 状态管理 | Zustand |
| 图表 | ECharts |
| 前端 E2E | Playwright |
| 后端 | FastAPI + Pydantic |
| ORM | SQLAlchemy 2 |
| 迁移 | Alembic only |
| 队列 | Redis + Celery |
| AI 调用层 | LLM Provider Adapter，默认 OpenAI Python SDK |
| API 返回格式 | `{ success, data, error, meta, request_id }` |
| 时间口径 | UTC 存储；Asia/Taipei 展示；Walmart 业务日 America/Los_Angeles |
| 金额口径 | numeric(18,4)，必须带 currency_code，换汇记录 fx_rate / fx_date / fx_source |
| 环境 | local / staging / production |

AI 不允许自行更换技术栈，除非项目负责人明确批准。

---

## 4. 最高禁令

未经项目负责人明确授权，AI 不允许：

1. 直接修改 `main` 或 `dev` 分支。
2. 自行合并到 `main` 或 `dev`。
3. 执行 `git push --force`、`git reset --hard`、`git clean -fd`。
4. 修改、格式化、删除 `old-system/` 下任何文件。
5. 在 `old-system/` 中开发新功能或修复旧 Bug。
6. 从 `old-system/` 直接复制代码到新系统。
7. 新系统代码直接 import / require `old-system/` 中的文件。
8. 修改 `.env`、真实密钥、Token、服务器密码、SSH 私钥。
9. 把密钥写入代码、日志、文档、测试或 Git。
10. 修改生产数据库。
11. 手工修改生产数据库结构。
12. 重启生产服务。
13. 修改 Nginx、systemd、防火墙、部署脚本等生产配置。
14. 自行更换技术栈。
15. 引入第二套 UI 框架、第二套 ORM、第二套任务系统、第二套状态管理方案。
16. 新增第二套独立后台管理系统。
17. 新增 `admin-app`、`admin-frontend`、`management-system` 等独立管理前端。
18. 大范围格式化无关文件。
19. 顺手重构无关模块。
20. 一次性生成整个系统。
21. 通过外部 Skill 自动部署、自动连接生产库、自动提交密钥或自动覆盖项目规则。

如任务可能触发以上行为，AI 必须先说明原因、风险、替代方案，并等待用户确认。

---

## 5. 系统边界

### 5.1 不做第二套后台管理系统

本项目 不新增独立后台管理系统。所有管理能力复用：

```text
设置：用户、角色、权限、组织架构、费用规则、业务配置、系统配置、日志、集成配置
数据中心：API文档、数据导入、数据导出、任务中心、失败记录、数据质量、数据血缘、指标字典
页面右上角 ?：当前页面 SOP / 帮助文档，新标签页打开
```

### 5.2 API 文档位置

API 文档固定放在：

```text
数据中心 → API文档
```

普通业务用户默认不可见，必须由 `data_center.api_docs.view` 权限控制。

### 5.3 页面帮助 / SOP 入口

每个正式页面右上角必须有 `? 帮助`，由 `PageShell` 统一渲染。点击后新标签页打开当前页面对应 SOP 文章。

---

## 6. 权限最终规则

角色不写死，由超级管理员在页面上动态配置。系统代码只认 `permissionKey`，不认业务角色名。

禁止写：

```python
if user.role == "finance":
    ...
```

必须写：

```python
require_permission("finance.profit_center.view")
```

权限必须分层：

```text
页面权限：能不能打开页面
动作权限：能不能导入、导出、编辑、审批、删除、重算
数据权限：打开页面后能看哪些数据
字段权限：敏感字段能不能看
高危动作权限：二次确认 + 审批 + 审计 + 可回滚
```

前端隐藏菜单只是体验，真正安全必须由后端校验。

---

## 7. 数据权限与组织架构

每个页面可以单独配置数据权限：

```text
all              全部数据
own              仅自己负责的数据
direct_reports   自己 + 直属下级
team             当前小组
org_tree         当前组织及下级组织
selected         指定店铺 / 负责人 / SKU / 账号
custom           自定义组合
none             无数据
```

组织架构、角色、数据权限必须分离：

```text
角色 = 能做什么
组织架构 = 属于哪个组、管谁
产品负责人归属 = 哪些产品归谁负责
数据权限 = 这个页面实际能看哪些数据
```

---

## 8. 费用规则版本化

所有影响利润、成本、佣金、汇率、费用的规则，禁止写死，禁止覆盖历史。

必须支持：

```text
effective_from
effective_to
rule_version
change_reason
approved_by
approved_at
audit_log
```

利润计算必须按 `business_date` 匹配当时生效规则。已月结数据默认锁定，不允许因新规则自动改变历史报表。

---

## 9. 集成配置与密钥管理

AI Token、飞书 Webhook、外部 API Key、App Secret 等敏感配置放在：

```text
设置 → 系统配置 → 集成配置
```

规则：

- 只能由具备权限的人管理，默认仅超级管理员。
- 代码使用 permissionKey 控制，不硬编码角色名。
- Token 只输入，不回显。
- 保存后加密存储。
- 页面只展示脱敏值，例如 `sk-****abcd`。
- 前端永远不接收完整密钥。
- 所有新增、替换、停用、测试必须写审计日志。
- AI Token 必须支持预算、调用上限、模型白名单、用途模块。

---

## 10. AI Skill 治理规则

外部 AI Skill 只作为辅助，不属于生产运行依赖。默认不得写入 `frontend/package.json`、`backend/pyproject.toml`、Dockerfile、CI 必跑步骤或 `postinstall`。

| Skill | 定位 | 默认状态 |
|---|---|---|
| planning-with-files | 长任务持久计划、防止上下文丢失 | P0 推荐 |
| context-engineering / PRP | 复杂功能施工图 | P0 推荐 |
| Context7 | 查询第三方库最新文档 | P0 推荐 |
| Playwright | 前端 E2E 页面验收 | P0 推荐，前端 devDependency |
| Ponytail | 项目规则持续生效与工作流守卫 | P1，规则行为默认生效，本地安装不强制 |
| Superpowers | AI 工作流增强：讨论、计划、TDD、评审 | P1 可选 |
| Vercel Agent Skills | React/UI/文档审查辅助 | P1 可选 |
| vercel-deploy-claimable | 自动部署 | 默认禁止 |

详细规则见：

- `docs/tools/AI_SKILL_REGISTRY.md`
- `docs/tools/AI_TOOL_PRIORITY_RULES.md`
- `docs/tools/AI_TOOL_INSTALL_GUIDE.md`
- `docs/PONYTAIL_COMPATIBILITY_RULES.md`

---

## 11. 复杂功能开发流程

复杂功能不得直接进入开发，必须先走 PRP 流程：

```text
用户需求
  ↓
templates/INITIAL_FEATURE.md
  ↓
PRPs/templates/prp_base.md
  ↓
项目负责人确认 PRP
  ↓
.planning/current/task_plan.md / findings.md / progress.md
  ↓
开发、测试、验收
  ↓
CODEX_HANDOFF.md
```

以下任务必须先写 PRP：

- 新页面
- 新 API
- 新数据库表
- 新权限模型
- 新费用规则
- 新 AI 任务
- 新导入导出流程
- 涉及 `old-system/` 的迁移/读取
- 涉及生产数据或历史财务口径的功能

PRP 不等于批准开发。PRP 必须先由项目负责人确认后，Codex 才能执行。

---

## 12. Playwright E2E 页面验收

本项目 使用 Playwright 作为前端 E2E 测试和页面验收工具。

- Playwright 只用于浏览器级页面测试，不替代 Vitest、pytest、ESLint、TypeScript 检查。
- 前端初始化完成后，在 `frontend/` 安装 `@playwright/test`。
- 每个 `ready` 页面至少必须有一个 Playwright E2E 测试。
- 高危功能必须覆盖关键流程，例如费用规则、权限配置、导入导出、AI Token、飞书通知、API文档权限。
- E2E 不允许依赖生产数据库、真实外部 API、真实 Token 或真实账号密码。

详细规则见：`docs/delivery/e2e-playwright-standard.md`。

---

## 13. Context7 文档查询

当任务涉及第三方库 API、配置、升级、脚手架、测试工具时，AI 必须优先使用 Context7 或官方文档核对当前版本用法。

规则：

- Context7 不属于生产依赖。
- 不允许提交 Context7 API Key、MCP Token、OAuth 信息。
- Context7 查询结果不能覆盖项目规则、安全边界或测试要求。
- 使用 Context7 后，完成报告必须说明查询的库、版本、问题、结论和不确定点。

详细规则见：`docs/delivery/context7-doc-lookup-standard.md`。

---

## 14. 开发方式：一个任务一个闭环

AI 必须按功能切片推进：

1. 一个任务只做一个明确功能。
2. 一个任务最多一个页面或一个 API 模块。
3. 一个任务只允许影响一个业务模块。
4. 一个任务必须可以独立测试。
5. 一个任务必须可以独立回滚。
6. 一个任务必须单独建分支。
7. 一个任务必须单独提交 PR。

禁止一次性生成整个系统、多个模块或无关接口。

---

## 15. API 完成标准

后端接口完成必须同时具备：

```text
FastAPI route
Pydantic request schema
Pydantic response schema
response_model
统一返回格式
错误码
required permissionKey
required data scope
OpenAPI 可见
Markdown API 文档
API 文档页面可见
测试通过
```

没有文档、没有 response_model、没有测试，不允许声称接口完成。

---

## 16. 功能完成标准

功能完成必须同时具备：

```text
页面 / API 完成
测试通过
API 文档完成
用户 SOP 完成
页面右上角帮助入口可用
开发交接说明完成
权限说明完整
数据来源说明完整
审计 / 回滚说明完整，高危功能必须有
```

没有 SOP 的功能，不允许标记为 `ready`。

---

## 17. Codex 完成报告格式

每个任务完成后必须输出：

```text
## Done
## Files changed
## Commands run
## Tests run
## Context / docs checked
## Risk check
- 是否修改 old-system
- 是否连接数据库
- 是否修改 .env
- 是否调用外部 API
- 是否影响权限
- 是否影响数据库迁移
- 是否使用外部 Skill
## Acceptance checklist
## Next step
```

---

## 18. 详细规则入口

- `docs/00_RULE_PACK_V1_0_OVERVIEW.md`
- `docs/01_PROJECT_DECISIONS.md`
- `docs/architecture/`
- `docs/business-rules/`
- `docs/delivery/`
- `docs/operations/`
- `docs/tools/AI_SKILL_REGISTRY.md`
- `docs/tasks/FIRST_40_CODEX_TASKS.md`

- Frontend admin layout must follow `docs/ui/ADMIN_LAYOUT_RULES.md`.
- Frontend UI component usage must follow `docs/ui/UI_COMPONENT_USAGE_RULES.md`.

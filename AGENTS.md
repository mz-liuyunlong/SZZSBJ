# SKYC V2 AI 开发总规则

## 0. 文件用途

本文件是本项目所有 AI 开发助手必须遵守的最高级项目规则。无论使用 Codex、Cursor、Claude Code、GitHub Copilot 或其他 AI，只要 AI 参与本项目的代码生成、修改、解释、测试、提交、PR 或 Code Review，都必须遵守本文件和项目内其他规则文档。

规则只有一套。不同 AI 工具的入口文件只是适配不同工具，不代表不同 AI 可以执行不同标准。

---

## 1. 项目定位

本项目是 **SKYC V2 新系统重建项目**。

- 新系统从零开始建设。
- 旧系统代码可以放在 `old-system/`，仅作为只读参考。
- `old-system/` 不允许修改、格式化、重构、安装依赖、运行写入任务或复制旧架构到新系统。
- 新系统代码必须放在 `frontend/`、`backend/`、`docs/`、`scripts/`、`.github/`、`.cursor/`、`skills/` 等明确目录中。
- 项目目标不是快速堆页面，而是建设一个可维护、可测试、可审查、可回滚、可交接的企业级运营数据系统。

---

## 2. 最终技术决策

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

## 3. 最高优先级禁令

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

如任务可能触发以上行为，AI 必须先说明原因、风险、替代方案，并等待用户确认。

---

## 4. 系统边界

### 4.1 不做第二套后台管理系统

SKYC V2 不新增独立后台管理系统。所有管理能力复用：

```text
⚙️ 设置：用户、角色、权限、组织架构、费用规则、业务配置、系统配置、日志、集成配置
🗄 数据中心：API文档、数据导入、数据导出、任务中心、失败记录、数据质量、数据血缘、指标字典
页面右上角 ?：当前页面 SOP / 帮助文档，新标签页打开
```

### 4.2 API 文档位置

API 文档固定放在：

```text
🗄 数据中心 → API文档
```

普通业务用户默认不可见，必须由 `data_center.api_docs.view` 权限控制。

### 4.3 页面帮助 / SOP 入口

每个正式页面右上角必须有 `? 帮助`，由 `PageShell` 统一渲染。点击后新标签页打开当前页面对应 SOP 文章。

---

## 5. 权限最终规则

角色不写死，由超级管理员在页面上动态配置。

系统代码只认 `permissionKey`，不认业务角色名。

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

## 6. 数据权限与组织架构

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

## 7. 费用规则版本化

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

## 8. 集成配置与密钥管理

AI Token、飞书 Webhook、外部 API Key、App Secret 等敏感配置放在：

```text
⚙️ 设置 → 系统配置 → 集成配置
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

## 9. 开发方式：一个任务一个闭环

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

## 10. API 完成标准

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

## 11. 功能完成标准

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

## 12. Codex 完成报告格式

每个任务完成后必须输出：

```text
## Done
## Files changed
## Commands run
## Tests run
## Risk check
- 是否修改 old-system
- 是否连接数据库
- 是否修改 .env
- 是否调用外部 API
- 是否影响权限
- 是否影响数据库迁移
## Acceptance checklist
## Next step
```

---

## 13. 详细规则入口

- `docs/00_RULE_PACK_V2_OVERVIEW.md`
- `docs/01_PROJECT_DECISIONS.md`
- `docs/architecture/`
- `docs/business-rules/`
- `docs/delivery/`
- `docs/operations/`
- `docs/tasks/FIRST_30_CODEX_TASKS.md`

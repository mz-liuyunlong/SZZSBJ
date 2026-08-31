# AI 日常开发规则

## 文件用途

本文件是本项目日常 AI 开发的轻量入口规则。

它不是替代完整版规则库，而是用于减少 token 消耗，让 AI 每次开发前先读取最关键规则，再按任务类型选择性读取详细文档和 Skill。

完整版规则仍以以下文件为准：

- `AGENTS.md`
- `RULE_PACK_FILE_INDEX.md`
- `docs/`
- `skills/`

---

## 1. 项目定位

本项目是**新系统重建项目**。

- 新系统代码从零开始建设。
- 旧系统代码可以放在 `old-system/` 目录中。
- `old-system/` 只能作为只读参考。
- AI 可以读取 `old-system/` 来理解旧功能、字段、接口、页面和业务规则。
- AI 不允许修改 `old-system/`。
- AI 不允许复制 `old-system/` 的旧代码到新系统。
- 新系统必须按当前固定技术栈重新设计和实现。

---

## 2. 日常默认读取规则

AI 每次开发前，默认只需要先读取：

```text
AGENTS.md
AI_DAILY_RULES.md
RULE_PACK_FILE_INDEX.md
skills/README.md
docs/TECH_STACK.md
docs/FEATURE_SLICE_DEVELOPMENT_RULES.md
docs/CODE_COMMENT_RULES.md
docs/PONYTAIL_COMPATIBILITY_RULES.md
```

其中 `docs/PONYTAIL_COMPATIBILITY_RULES.md` 是默认开启规则，不需要用户在每次任务里特意引用。

不要每次全文读取整个 `docs/`、`skills/`、`.cursor/rules/`。

规则文件是资料库，不是每次都要全部加载进上下文。



---

## 2.0 AI 工具首次配置规则

当开发者第一次拉取本项目、第一次让 AI 接手项目，或者当前环境尚未确认官方 Ponytail 插件时，AI 必须主动读取：

```text
AI_ONBOARDING.md
docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md
docs/tools/PONYTAIL_INSTALL_GUIDE.md
```

AI 不得假设开发者会自己阅读安装说明。

如果当前 AI 具有终端执行能力，AI 应在用户确认后执行：

```bash
bash scripts/check-ai-tools.sh
bash scripts/setup-ai-tools.sh
```

支持官方 Ponytail 插件的工具，应优先安装官方 Ponytail 插件。尤其是 Codex，应帮助执行：

```bash
codex plugin marketplace add DietrichGebert/ponytail
codex plugin add ponytail@ponytail
```

安装后，AI 必须提醒用户进入 `/hooks` 手动审查并信任 hooks。AI 不得自动替用户信任 hooks。

如果官方 Ponytail 插件未安装或安装失败，AI 必须明确说明当前使用项目内置 Ponytail 默认规则：

```text
docs/PONYTAIL_COMPATIBILITY_RULES.md
```


---

## 2.1 Skill 自发现规则

用户不需要记住项目里有哪些 Skill，也不需要手动指定本次使用哪个 Skill。

每次开始开发任务前，AI 必须先读取：

```text
AI_DAILY_RULES.md
RULE_PACK_FILE_INDEX.md
skills/README.md
```

然后 AI 必须根据本次任务类型，自行判断需要读取哪些具体 Skill 和 docs。

AI 不允许一次性全文读取所有 Skill，也不允许要求用户手动指定 Skill。AI 必须先看 Skill 索引，再按任务选择性读取。

AI 修改代码前必须先输出：

1. 本次任务类型判断。
2. 本次准备读取哪些 Skill。
3. 为什么选择这些 Skill。
4. 哪些 Skill 本次不需要读取。
5. 本次准备读取哪些 docs。
6. 初步开发计划。

用户确认前，AI 不得修改代码。

固定顺序：

```text
读取入口规则
↓
读取 Skill 索引
↓
判断任务类型
↓
选择相关 Skill
↓
读取相关 Skill
↓
输出开发计划
↓
用户确认
↓
修改代码
```

---

## 2.2 Ponytail 项目内置规则

本项目已经把 Ponytail 的核心思想固化为项目规则：

```text
docs/PONYTAIL_COMPATIBILITY_RULES.md
```

所有 AI 工具都必须遵守该文件。用户不需要记住 Ponytail，也不需要手动提醒 AI，AI 不得因为用户没有提到 Ponytail 而跳过该规则。

如果当前 AI 工具已经安装 Ponytail 插件，可以使用 Ponytail mode；如果没有安装，也必须按 `docs/PONYTAIL_COMPATIBILITY_RULES.md` 执行。

AI 修改代码前输出计划时，必须包含 Ponytail 最小正确实现检查，但不得要求用户单独“调用 Ponytail”。

Ponytail 只用于减少过度设计、优先复用、避免重复代码、实现最小正确闭环，不得覆盖项目安全、权限、old-system 只读、API 契约、数据库、Celery、财务、测试、注释等强制规则。

## 3. 按任务类型追加读取

### 前端页面开发

如果本次任务涉及 React 页面、组件、表格、筛选、弹窗、Drawer、路由或菜单，必须追加读取：

```text
docs/COMPONENT_AND_MODULE_RULES.md
docs/UI_COMPONENT_CATALOG.md
docs/UI_STYLE_RULES.md
docs/PAGE_DEVELOPMENT_CHECKLIST.md
skills/feature-slice-planner/SKILL.md
skills/react-component-architect/SKILL.md
```

---

### 后端接口开发

如果本次任务涉及 FastAPI、接口、Schema、Service、Repository、Model 或权限，必须追加读取：

```text
docs/API_DESIGN_RULES.md
docs/API_CONTRACT_RULES.md
docs/BACKEND_MODULE_CATALOG.md
docs/PERMISSION_AND_AUDIT_RULES.md
skills/backend-module-designer/SKILL.md
skills/api-contract-designer/SKILL.md
```

---

### 参考旧系统

如果本次任务需要参考 `old-system/`，必须追加读取：

```text
docs/OLD_SYSTEM_READONLY_RULES.md
docs/REBUILD_MAPPING_RULES.md
skills/old-system-readonly-analyzer/SKILL.md
skills/rebuild-mapping-planner/SKILL.md
```

AI 必须先只读分析旧系统，输出分析报告，等用户确认后再开发新系统代码。

---

### 数据库变更

如果本次任务涉及表、字段、索引、迁移、数据建模，必须追加读取：

```text
docs/DATABASE_RULES.md
docs/DATA_MODELING_RULES.md
docs/DATA_SOURCE_AND_LINEAGE_RULES.md
```

涉及数据库结构变更时，必须使用 Alembic migration，并先说明影响范围。

---

### Celery / 后台任务 / 数据同步

如果本次任务涉及同步、导入、导出、批量处理、AI 批量分析、耗时任务，必须追加读取：

```text
docs/BACKGROUND_TASK_DEVELOPMENT_RULES.md
docs/DATA_SYNC_RULES.md
skills/background-task-designer/SKILL.md
skills/data-sync-designer/SKILL.md
```

本项目固定使用 Redis + Celery，不允许自行引入第二套后台任务系统。

---

### 财务、利润、金额、回款

如果本次任务涉及利润、回款、广告花费、退款、退货运费、供货价、结算、毛利率，必须追加读取：

```text
docs/FINANCIAL_CALCULATION_RULES.md
docs/TIMEZONE_AND_CURRENCY_RULES.md
skills/financial-calculation-reviewer/SKILL.md
```

AI 不允许自行发明财务公式。

---

### 外部 API / 平台接口

如果本次任务涉及 Walmart、Amazon、TEMU、领星、OpenAI、Decodo、紫鸟或其他第三方接口，必须追加读取：

```text
docs/EXTERNAL_API_INTEGRATION_RULES.md
docs/SECURITY_RULES.md
skills/external-api-integration-designer/SKILL.md
```

外部 API 调用必须放入后端 `integrations/`，不得散落在页面或 Route 中。

---

### 系统内 AI 功能 / LLM 调用

如果本次任务涉及 AI 分析、AI 广告、AI Listing、AI 图片、AI 优化建议、Prompt 或模型调用，必须追加读取：

```text
docs/AI_FEATURE_SAFETY_RULES.md
docs/LLM_PROVIDER_ADAPTER_RULES.md
skills/llm-provider-adapter-designer/SKILL.md
```

业务代码不得直接散落调用 OpenAI SDK，必须经过统一 LLM Provider Adapter。

---

### 性能、大表、报表

如果本次任务涉及大数据量列表、复杂查询、报表、聚合统计，必须追加读取：

```text
docs/PERFORMANCE_RULES.md
skills/performance-reviewer/SKILL.md
```

列表必须分页，大表查询必须有筛选条件，不允许一次性全表加载。

---

### 发布、部署、回滚

如果本次任务涉及上线、发布、部署、回滚、生产配置，必须追加读取：

```text
docs/RELEASE_AND_ROLLBACK_RULES.md
docs/DEPLOYMENT_RULES.md
docs/BACKUP_AND_RECOVERY_RULES.md
```

未经用户明确确认，AI 不允许执行生产发布、重启服务、修改生产配置或操作生产数据库。

---

## 4. 每次开发的强制边界

本项目所有 AI 开发必须遵守：

```text
一个功能一个模块
一个页面一个任务
一个任务一个分支
一个分支一个 PR
```

AI 不允许：

1. 一次性生成整个系统。
2. 一次性开发多个业务模块。
3. 一个 PR 同时做多个无关功能。
4. 顺手重构无关代码。
5. 顺手修改全局架构。
6. 顺手新增依赖。
7. 顺手修改 `old-system/`。
8. 顺手复制旧系统代码。

如果任务范围过大，AI 必须先拆分任务，而不是直接开发。

---

## 5. Git 日常规则

开发前必须检查：

```bash
git status
git branch
```

如果当前在 `main` 或 `dev`，不得直接修改。应从 `dev` 创建任务分支：

```bash
git checkout dev
git pull origin dev
git checkout -b ai/YYYYMMDD-task-name
```

分支命名示例：

```text
ai/20260831-ads-campaign-list
ai/20260831-product-list
ai/20260831-order-profit-page
```

禁止：

```bash
git push --force
git reset --hard
git clean -fd
```

未经用户确认，不允许提交、推送、合并 PR。

---

## 6. old-system 日常规则

`old-system/` 是旧系统只读参考目录。

AI 可以：

- 读取旧页面。
- 读取旧 API。
- 读取旧字段。
- 读取旧业务逻辑。
- 输出分析文档。
- 提炼新系统重建建议。

AI 禁止：

- 修改 `old-system/`。
- 格式化 `old-system/`。
- 删除 `old-system/`。
- 在 `old-system/` 中安装依赖。
- 在 `old-system/` 中运行写数据库脚本。
- 复制旧代码到 `frontend/` 或 `backend/`。
- 让新系统 import / require `old-system/` 文件。

如果参考了 `old-system/`，AI 必须输出：

1. 读取了哪些文件。
2. 旧系统当前逻辑是什么。
3. 旧系统数据来源是什么。
4. 旧逻辑哪些保留。
5. 旧设计哪些不建议延续。
6. 新系统如何重新设计。
7. 等用户确认后再开发。

---

## 7. 前端日常规则

前端固定技术栈：

```text
React
TypeScript
Vite
Ant Design
ProComponents
React Router
Zustand
ECharts
```

前端开发必须遵守：

1. 页面只负责组合，不堆复杂逻辑。
2. API 请求必须封装。
3. 类型必须独立定义。
4. 重复 UI 必须考虑组件封装。
5. Shared 组件不得包含具体业务逻辑。
6. 页面必须处理 Loading / Empty / Error / Pagination。
7. 不允许大量使用 `any`。
8. 不允许前端直接调用敏感外部 API。
9. 不允许从 `old-system/` import 代码。

页面开发前必须先输出组件拆分方案。

---

## 8. 后端日常规则

后端固定技术栈：

```text
Python
FastAPI
Pydantic
SQLAlchemy
Alembic
Redis
Celery
LLM Provider Adapter
OpenAI Python SDK 默认实现
```

后端必须按以下层级设计：

```text
API Route
↓
Schema
↓
Service
↓
Repository
↓
Model
```

规则：

1. Route 只做入口、参数校验、权限检查、调用 Service。
2. Service 写业务逻辑。
3. Repository 写数据库访问。
4. Model 定义表结构。
5. Schema 定义请求和响应。
6. Integration 封装外部 API。
7. Celery Task 只做任务编排。
8. 不允许在 Route 中写复杂 SQL。
9. 不允许在 Celery Task 中堆满业务逻辑。
10. 不允许从 `old-system/` import 代码。

---

## 9. API 契约规则

前后端闭环开发前，必须先输出 API 契约草案。

API 契约必须包含：

1. 路径。
2. 方法。
3. Query 参数。
4. Request Body。
5. Response 字段。
6. 分页结构。
7. 错误结构。
8. 权限要求。
9. 是否写操作日志。
10. 是否触发 Celery。

用户确认 API 契约后，再写前后端代码。

---

## 10. 注释规则

AI 新增或修改代码时必须写维护型注释。

注释应该解释：

- 为什么这样做。
- 业务规则是什么。
- 金额公式是什么。
- 时间口径是什么。
- 数据来源是什么。
- 外部 API 失败怎么处理。
- Celery 任务是否幂等。

不要写无意义注释，例如：

```ts
// 设置 loading 为 true
setLoading(true)
```

应该写维护型注释，例如：

```ts
// 保留最近一次筛选条件，用户从详情页返回列表时恢复原查询状态。
setLastQuery(query)
```

---

## 11. 安全规则

AI 不允许提交或输出：

- `.env`
- API Key
- Token
- 数据库密码
- SSH 私钥
- Cookie
- Session
- 服务器密码
- 生产配置
- 真实密钥

如果发现敏感信息，必须停止并提醒用户，不要输出完整密钥。

前端禁止保存或暴露敏感 Key。模型调用、平台 API、数据库连接必须在后端处理。

---

## 12. 开发前必须输出

AI 修改代码前，必须先输出：

```md
## 开发前计划

### 已读取规则

### 当前分支与 Git 状态

### 任务理解

### 本次只做

### 本次不做

### 是否参考 old-system

### 前端组件拆分方案

### 后端模块拆分方案

### API 契约草案

### 是否涉及数据库

### 是否涉及 Celery

### 是否涉及权限和操作日志

### 风险点

### 测试与验收方式
```

用户确认前，不要修改代码。

---

## 13. 完成后必须输出

开发完成后，AI 必须输出：

```md
## 完成报告

### 当前分支

### 修改文件清单

| 文件 | 修改原因 |
|---|---|

### 本次完成内容

### 组件与模块封装说明

### API 契约实现情况

### 是否参考 old-system

### 是否修改共享代码

### 是否涉及数据库

### 是否涉及 Celery

### 是否涉及权限和操作日志

### 测试命令与结果

### 验收标准对照

### 风险点

### 回滚方式

### 后续建议
```

并执行或要求用户执行：

```bash
git status
git diff --stat
```

---

## 14. Token 节省规则

AI 应该：

1. 先读本文件，再按任务类型读取必要文件。
2. 不要一次性读取全部规则库。
3. 不要重复粘贴大段已有代码。
4. 不要每次重新解释整个项目。
5. 修改前先定位相关文件。
6. 输出关键 diff 摘要，不要输出无关全文。
7. 任务变长时写 handoff 文档。

上下文过长时，交接文档写入：

```text
docs/handoffs/YYYYMMDD-task-name.md
```

---

## 15. 一句话总原则

```text
先读轻量规则，再按任务读取细则。
一个功能一个模块，一个页面一个任务。
old-system 只读参考，不修改、不复制。
前端组件化，后端分层化。
API 契约先确认，代码修改后可测试、可回滚、可交接。
```

# Agent Role / Skill Routing Matrix

## 1. 目的

本文定义项目执行角色与 Agent Skill 的使用边界，确保架构师按任务分配合适的工作模式，同时不改变项目权限、PRP、文件范围、Git 和生产安全规则。

## 2. 总原则

- Agent Skill 不等于人员，也不新增人员角色。
- Agent Skill 不等于权限主体，不能授予文件、系统、数据或上传权限。
- 每个任务只能有一个主执行角色；多个 Skill 只能辅助该角色完成同一任务。
- 架构师负责选择任务可用 Skill，并写入已批准 PRP 或工程师 Prompt。
- 未明确分配的 Skill 默认不可由工程师自行启用；高风险 Skill 必须遵守第 8 节。
- 项目规则、当前任务 allowlist 和负责人明确指令始终高于 Skill 指令。

## 3. 项目执行角色

项目执行角色固定为四个：

1. 项目负责人：批准范围、PRP、高风险操作和上传合并动作。
2. 架构师：设计方案、选择 Skill、编写或复审 PRP、执行只读架构复审。
3. 后端工程师：在批准范围内实现后端、数据和测试任务。
4. 前端工程师：在批准范围内实现前端、交互和测试任务。

Agent Skill 不得被登记为第五种执行角色。

## 4. Agent Skill 与项目角色的关系

Agent Skill 是执行角色在特定任务中的工作模式。一个角色可以按架构师分配使用多个 Skill，但 Skill：

- 不改变任务主执行角色。
- 不替代负责人或架构师的批准职责。
- 不扩大允许修改文件和允许命令。
- 不产生数据库、外部 API、部署或 Git 上传权限。
- 不允许绕过数据源决策、PRP、测试或审查门禁。

## 5. Agent Skill Routing Matrix

“是否默认允许”表示架构师已将该 Skill 分配给当前任务后，是否还需要额外的 Skill 专项批准；不代表工程师可以自行启用。Skill 本身不产生实现权限，任何代码实现或修改都必须遵守第 10 节的独立 PRP 和负责人批准规则。

| Agent Skill | 归属角色 | 使用场景 | 是否默认允许 | 是否需要单独 PRP | 禁止事项 |
|---|---|---|---|---|---|
| `engineering-frontend-developer` | 前端工程师 | 已批准的前端组件、页面和交互实现 | 仅在架构师分配后允许 | 代码实现或修改必须遵守第 10 节 | 不得新增第二套前端、越过文件范围或接入未批准 API |
| `engineering-backend-architect` | 架构师；可分配给后端工程师 | 后端边界、接口、服务和数据流设计或复审 | 仅在架构师分配后允许 | 纯设计或复审不需要；代码实现或修改必须遵守第 10 节 | 不得替负责人批准数据源、技术栈或高风险操作 |
| `engineering-multi-agent-systems-architect` | 架构师 | 多 Agent 流程、协作拓扑和治理设计 | 否 | 是 | 不得擅自创建并行执行链、扩大授权或自动审批 |
| `engineering-minimal-change-engineer` | 架构师、后端工程师、前端工程师 | 控制改动范围、避免无关重构 | 是 | 只读建议不需要；代码实现或修改必须遵守第 10 节 | 不得以最小改动为由省略安全、测试或明确验收要求 |
| `engineering-code-reviewer` | 架构师 | 代码和文档的只读正确性复审 | 架构复审默认允许 | 只读复审不需要；代码修复必须遵守第 10 节 | 不得借复审修改代码、上传、合并或替负责人批准 |
| `engineering-git-workflow-master` | 项目负责人；架构师仅可只读复审 | 分支、暂存、提交、PR 和合并流程指导 | 其他角色仅允许只读建议 | 不适用；Git 写操作仅由项目负责人本人执行 | 架构师和工程师不得执行 git add、commit、push、创建 PR、merge、force push 或删除分支 |
| `engineering-technical-writer` | 架构师、后端工程师、前端工程师 | 在任务 allowlist 内编写规范、API 文档和交接说明 | 仅在架构师分配后允许 | 纯文档按任务规则；代码实现或修改必须遵守第 10 节 | 不得编造证据、批准状态、数据口径或扩大文档范围 |
| `engineering-database-optimizer` | 架构师、后端工程师 | 静态分析 schema、字段关系和 SQL 引用；经批准后做数据库优化 | 仅静态分析且被分配时允许 | 只读静态分析不需要；代码或结构修改必须遵守第 10 节 | 默认不得连接数据库、执行 SQL、修改 schema 或生产数据 |
| `engineering-database-reliability-engineer` | 架构师、后端工程师 | 高可用、备份恢复、故障切换和在线迁移设计 | 否 | 设计按任务规则；代码或结构修改必须遵守第 10 节 | 不得连接或操作生产数据库，不得执行迁移、恢复或切换 |
| `engineering-devops-automator` | 架构师；经授权可分配给工程师 | CI/CD、基础设施和部署自动化设计或实现 | 否 | 是 | 不得自动部署、重启服务或修改生产配置、CI 和密钥 |
| `security-ai-generated-code-auditor` | 架构师 | 对已授权代码做只读安全审计和风险复审 | 仅在架构师分配后允许 | 只读审计不需要；代码修复必须遵守第 10 节 | 不得读取真实密钥、攻击真实系统或越过 allowlist 自动修复 |
| `testing-api-tester` | 后端工程师 | 已批准接口的本地契约、错误和集成测试 | 仅本地 mock 或明确授权环境 | 仅执行已有测试不需要；测试代码修改或真实环境测试必须遵守第 10 节 | 不得默认调用真实 API、使用真实 Token 或写入真实数据 |
| `testing-evidence-collector` | 架构师、后端工程师、前端工程师 | 收集只读代码、测试、截图和验收证据 | 仅在架构师分配后允许 | 只读取证不需要；代码实现或修改必须遵守第 10 节 | 不得伪造证据或借调查访问未授权旧系统、数据库和 API |
| `project-management-project-shepherd` | 项目负责人、架构师 | 任务拆分、状态、依赖、风险和交接跟踪 | 是 | 否 | 不得替执行角色实现、替架构师复审或替负责人批准 |

## 6. Phase 2A Agent Assignment 示例

任务：`产品管理 / 产品基础信息查询 Source Discovery`

主执行角色：`后端工程师`

后端工程师允许使用：

```text
engineering-minimal-change-engineer
engineering-technical-writer
testing-evidence-collector
engineering-backend-architect
engineering-database-optimizer
```

其中 `engineering-database-optimizer` 仅允许静态分析仓库中已提交的 schema、字段字典、关系和 SQL 引用，不得连接数据库，不得执行 SQL。

架构师复审允许使用：

```text
engineering-code-reviewer
engineering-backend-architect
project-management-project-shepherd
engineering-minimal-change-engineer
engineering-database-optimizer
security-ai-generated-code-auditor
engineering-git-workflow-master
```

当前禁止：

```text
engineering-frontend-developer
engineering-multi-agent-systems-architect
engineering-database-reliability-engineer
engineering-devops-automator
testing-api-tester
```

即使 `engineering-git-workflow-master` 出现在架构师复审清单中，也只允许只读检查和给出建议。后端工程师不得使用它执行 git add、commit、push、创建 PR、merge、force push 或删除分支。

## 7. Skill 不得扩大权限

任何 Skill 均不得：

- 扩大当前任务 allowlist 或修改禁止目录。
- 绕过数据源决策、PRP、负责人确认或架构师复审。
- 连接真实数据库、调用真实外部 API 或读取真实密钥。
- 自动部署、重启服务或修改生产配置。
- 改变 Git 暂存、提交、push、PR、merge 或删分支权限。
- 替负责人作出批准，或把建议、草稿和调查结论标记为已批准。

Skill 指令与项目规则冲突时，必须停止并按项目最高优先级处理。

## 8. 高风险 Skill 分配规则

工程师不得自行启用未分配的高风险 Skill。下列 Skill 或使用方式视为高风险：

- `engineering-multi-agent-systems-architect`。
- `engineering-database-reliability-engineer`。
- `engineering-devops-automator`。
- `engineering-git-workflow-master` 对架构师和工程师仅限只读；Git 写操作不属于可分配动作。
- `engineering-database-optimizer` 的数据库连接、SQL 执行或结构变更。
- `testing-api-tester` 的真实外部 API、生产环境或数据写入测试。
- `security-ai-generated-code-auditor` 的真实环境验证或主动攻击行为。

架构师必须在 PRP 或工程师 Prompt 中写明 Skill 名称、允许动作、文件与系统范围、禁止事项和验证方式。仅列出 Skill 名称不构成高风险操作授权。

## 9. Git 上传与合并职责

git add、commit、push、创建 PR、merge、force push 和删除分支等 Git 写操作只能由项目负责人本人执行，不得转授权给架构师或工程师。架构师和工程师只能执行 git status、git diff 等只读检查，并提供建议暂存清单、commit message 和 PR 描述。

## 10. 需要单独 PRP 和负责人授权的场景

下列场景不能仅凭 Skill 分配执行，必须按项目规则准备单独 PRP，并取得负责人对具体操作的明确授权：

- 任何由 Agent Skill 导致的代码实现或修改，包括前端代码、后端代码、脚本代码、配置代码、CI 或部署配置、数据库 migration 或 schema、同步任务、worker 和定时任务。
- 新页面、新后端业务接口、新数据库表、新权限模型、新同步、导入导出或 AI 任务。
- 读取或迁移 `old-system/`，连接真实数据库，执行 SQL、迁移、回填、恢复或历史重算。
- 调用或验证真实外部 API，使用真实 Token、Webhook、账号或敏感数据。
- 修改生产基础设施、CI/CD、部署配置，部署或重启服务。
- 建立多 Agent 自动执行流程、自动审批、自动提交或跨系统写入。
- 对真实系统进行主动安全测试、漏洞利用或包含密钥的扫描。

Skill 本身不产生代码实现权限。只要任务结果会写入或修改代码，就必须先完成对应任务类型的独立 PRP 并由项目负责人批准；只读分析或文档建议不能被用作代码写入授权。

数据源调查和后端业务接口还必须先遵守 `docs/delivery/backend-data-source-decision-gate.md`。PRP 或负责人批准只对写明的任务、Skill、动作和范围有效，且不能转授权 Git 写操作。

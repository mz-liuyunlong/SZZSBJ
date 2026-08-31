
# v1.4.4

## 新增：AI 工具首次配置与官方 Ponytail 安装辅助

本版本新增“新开发者拉取项目后，由 AI 主动协助安装官方 Ponytail 插件”的流程。

新增文件：

- `AI_ONBOARDING.md`
- `docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md`
- `scripts/check-ai-tools.sh`
- `scripts/setup-ai-tools.sh`

核心规则：

1. AI 不得假设开发者会自己阅读安装说明。
2. AI 第一次接手项目时，必须主动检查官方 Ponytail 插件安装条件。
3. 支持官方插件的工具优先安装官方 Ponytail。
4. hooks 必须由用户审查并信任，AI 不得自动信任。
5. 不得把官方 Ponytail 安装写入 `npm install`、`postinstall`、CI、Docker、Vercel 或项目运行脚本。
6. 官方插件不可用时，继续使用 `docs/PONYTAIL_COMPATIBILITY_RULES.md` 作为项目内置默认规则。

---

# v1.4.3 - Ponytail 默认开启规则

## 变更

- 将 Ponytail 从“需要提示词显式引用的兼容规则”升级为“项目默认开启规则”。
- 明确 Ponytail 不是任务型 Skill，不参与 Skill 自发现的“用或不用”选择。
- AI 只要进入代码开发、修改、重构、Review 或 PR 自检任务，就必须自动执行 `docs/PONYTAIL_COMPATIBILITY_RULES.md`。
- 更新 `AI_DAILY_RULES.md`、`AGENTS.md`、`AI_START_HERE.md`、`CODEX_START_HERE.md`、`CLAUDE.md`、`README_AI_RULES.md`、`RULE_PACK_FILE_INDEX.md`、`skills/README.md`。
- 更新 Cursor、Copilot、PR 模板和 Ponytail 安装说明，明确不需要用户单独引用 Ponytail。
- 保留最高优先级限制：Ponytail 不能覆盖 old-system 只读、安全、权限、API 契约、数据库、Celery、财务、测试和维护型注释规则。

---

# v1.4.2 - Ponytail 项目内置兼容规则

## 变更

- 新增 `docs/PONYTAIL_COMPATIBILITY_RULES.md`，把 Ponytail 的“最小正确实现、优先复用、避免过度设计”原则固化为项目规则。
- 新增 `docs/tools/PONYTAIL_INSTALL_GUIDE.md`，说明 Codex / Claude Code 如何额外安装官方 Ponytail 插件。
- 更新 `AI_DAILY_RULES.md`、`AGENTS.md`、`AI_START_HERE.md`、`CODEX_START_HERE.md`、`CLAUDE.md`、`README_AI_RULES.md`、`RULE_PACK_FILE_INDEX.md`、`skills/README.md`。
- 更新 Cursor、GitHub Copilot 和 PR 模板，使其他 AI 即使没有安装 Ponytail 插件，也必须遵守项目内置 Ponytail 兼容规则。
- 明确禁止把 Ponytail 插件安装写入 `npm install`、`postinstall`、CI、Vercel 或 Docker 构建流程。
- 明确项目规则优先级高于 Ponytail，不能因为追求简洁而省略安全、权限、日志、校验、API 契约、数据库迁移、Celery 幂等、财务口径、测试和注释。

---

# v1.4.1 - Skill 自发现机制

## 变更

- 新增 `AI_DAILY_RULES.md` 到规则包根目录。
- 增加 Skill 自发现规则：用户不需要记住或手动指定 Skill。
- AI 开发前必须先读取 `skills/README.md`，根据任务类型选择相关 Skill。
- 禁止一次性全文读取全部 Skill，降低 token 消耗。
- 更新 `AGENTS.md`、`AI_START_HERE.md`、`CODEX_START_HERE.md`、`README_AI_RULES.md`、`RULE_PACK_FILE_INDEX.md`、`skills/README.md`、Cursor 规则和 PR 模板。

---

# 规则包更新记录

## v1.4 complete_greenfield_old_system_readonly

本版本将前面讨论的内容统一梳理为完整规则包：

- 保留新系统从零建设定位。
- 加强 `old-system/` 只读参考规则。
- 明确禁止修改 `old-system/`、禁止复制旧代码、禁止新系统直接依赖旧系统。
- 增加单功能切片开发规则。
- 增加前端组件和后端模块封装规则。
- 增加通用 UI 组件清单和后端模块清单。
- 增加项目级 `skills/`，避免依赖某个人电脑本地 Skill。
- 增加测试、环境变量、依赖管理、外部 API、LLM 调用层规则。
- 增加数据来源血缘、数据质量、数据同步、财务计算、时区币种规则。
- 增加性能、日志、可观察性、发布回滚、备份恢复规则。
- 增加页面需求、API 契约、页面验收目录。
- 增加 Cursor、Copilot、Claude、Codex 入口适配。

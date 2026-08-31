# AI 规则包使用说明

## 这是什么

这是本项目的 AI 开发规则包。它用于约束任何 AI 开发助手在本项目中的行为，避免多人、多 AI 协作时出现乱改代码、乱选技术栈、复制旧系统代码、缺少注释、接口不统一、数据来源不清、财务公式不一致、PR 难审查等问题。

## 项目定位

本项目是新系统重建项目：

- 新系统从零开始建设。
- 旧系统代码可放在 `old-system/`，仅只读参考。
- 旧系统分析结果写入 `docs/old-system-analysis/`。
- 新系统代码不能依赖 `old-system/`。

## 推荐先读顺序

日常开发不需要一次性读取全部规则文件。推荐顺序：

1. `AI_DAILY_RULES.md`
2. `AGENTS.md`
3. `RULE_PACK_FILE_INDEX.md`
4. `skills/README.md`
5. `docs/PONYTAIL_COMPATIBILITY_RULES.md`

其中 Ponytail 是默认开启规则，不需要用户在任务提示词里特意引用。

然后由 AI 根据任务类型自行选择需要读取的具体 docs 和 Skill。

用户不需要记住有哪些 Skill，也不需要手动指定 Skill。

## 给团队的统一启动提示词

```md
你现在参与本项目开发。无论你是什么 AI 工具，都必须先读取：

1. AI_DAILY_RULES.md
2. AGENTS.md
3. RULE_PACK_FILE_INDEX.md
4. skills/README.md

然后根据项目规则自动开启 Ponytail 最小正确实现原则，并根据本次任务类型，自己判断需要读取哪些 docs 和 skills，不要一次性读取全部文件，也不要要求我手动指定 Skill。

本次任务是：{填写任务}

要求：
1. 先判断本次任务类型。
2. 先输出本次准备使用哪些 Skill，以及为什么选择。
3. 先输出本次不需要读取哪些 Skill。
4. Ponytail 默认开启，不需要我单独引用。
5. 先输出 Ponytail 最小正确实现检查。
6. 先输出初步开发计划。
7. 等我确认后再修改代码。
8. 一个任务只做一个功能，一个页面一个任务。
9. 不允许修改 old-system，不允许复制 old-system 代码。
```

## 规则文件分工

| 文件 / 目录 | 用途 |
|---|---|
| `AGENTS.md` | 所有 AI 的总规则 |
| `AI_START_HERE.md` | 所有 AI 的通用启动入口 |
| `CODEX_START_HERE.md` | 项目负责人使用 Codex 的操作入口 |
| `CLAUDE.md` | Claude Code 入口适配 |
| `.cursor/rules/` | Cursor 入口适配 |
| `.github/copilot-instructions.md` | GitHub Copilot 入口适配 |
| `skills/` | 项目级 AI Skills，任何 AI 都可按 Markdown 读取 |
| `docs/` | 详细项目规范 |
| `old-system/` | 旧系统只读参考目录 |

工具入口文件只是为了适配不同 AI 的读取方式。核心规则是一套，不允许不同 AI 执行不同标准。

## Ponytail 项目内置说明

本项目已经内置 Ponytail 兼容规则：

```text
docs/PONYTAIL_COMPATIBILITY_RULES.md
```

这表示其他开发者即使没有安装官方 Ponytail 插件、没有主动提醒 AI、没有单独引用 Ponytail，AI 也必须按项目文件执行“避免过度设计、优先复用、最小正确实现”的规则。

Codex / Claude Code 用户可以额外按 `docs/tools/PONYTAIL_INSTALL_GUIDE.md` 安装官方插件，但插件不是项目运行依赖，也不会通过 `npm install` 自动安装。


---

## 新开发者首次拉取项目

开发者第一次拉取项目后，不要求人工阅读所有规则。

直接把下面这段发给当前 AI：

```md
你现在第一次接手本项目。请先读取 AI_ONBOARDING.md、AI_DAILY_RULES.md、AGENTS.md、RULE_PACK_FILE_INDEX.md、skills/README.md、docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md。

先不要开发业务代码。请先检查并帮助安装当前工具支持的官方 Ponytail 插件；如果需要 hooks 信任，请停下来让我确认。安装失败时，使用项目内置 Ponytail 默认规则。
```

本项目提供辅助脚本：

```bash
bash scripts/check-ai-tools.sh
bash scripts/setup-ai-tools.sh
```

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

1. `AGENTS.md`
2. `RULE_PACK_FILE_INDEX.md`
3. `docs/TECH_STACK.md`
4. `docs/PROJECT_BOOTSTRAP_RULES.md`
5. `docs/FEATURE_SLICE_DEVELOPMENT_RULES.md`
6. `docs/OLD_SYSTEM_READONLY_RULES.md`
7. `docs/COMPONENT_AND_MODULE_RULES.md`
8. `docs/CODE_COMMENT_RULES.md`
9. `docs/API_CONTRACT_RULES.md`
10. `docs/TESTING_RULES.md`

## 给团队的统一启动提示词

```md
你现在参与本项目开发。无论你是什么 AI 工具，都必须先读取并遵守：

1. AGENTS.md
2. RULE_PACK_FILE_INDEX.md
3. docs/TECH_STACK.md
4. docs/FEATURE_SLICE_DEVELOPMENT_RULES.md
5. docs/OLD_SYSTEM_READONLY_RULES.md
6. docs/COMPONENT_AND_MODULE_RULES.md
7. docs/CODE_COMMENT_RULES.md
8. docs/API_CONTRACT_RULES.md

本次开发必须一个功能一个模块，一个页面一个任务。修改前先输出技术实施计划，等我确认后再动手。
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

# AI 通用启动入口

## 文件用途

本文件是任何 AI 工具参与本项目时的通用启动入口。具体 AI 工具可以有自己的入口文件，但最终都必须回到 `AGENTS.md` 这一套规则。

## 每次任务开始前必须读取

1. `AGENTS.md`
2. `RULE_PACK_FILE_INDEX.md`
3. `docs/TECH_STACK.md`
4. `docs/FEATURE_SLICE_DEVELOPMENT_RULES.md`
5. `docs/OLD_SYSTEM_READONLY_RULES.md`
6. `docs/COMPONENT_AND_MODULE_RULES.md`
7. `docs/CODE_COMMENT_RULES.md`
8. 与任务相关的 `skills/*/SKILL.md`

## 通用工作流

```text
读取规则
↓
确认当前分支和 git 状态
↓
明确本次只做一个功能 / 一个页面
↓
如需 old-system，先只读分析
↓
输出实施计划
↓
用户确认
↓
小范围修改
↓
测试与验收
↓
输出交接报告
```

## 禁止

用户未确认前，不要修改代码。用户说“先讨论”“只读分析”“暂不改代码”时，只能输出方案和分析。

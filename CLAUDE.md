@AGENTS.md

# Claude Code 入口适配

本项目的核心规则是 `AGENTS.md`。Claude Code 参与本项目开发时，必须遵守 `AGENTS.md` 和 `docs/` 下的项目规范。

## Claude Code 额外要求

1. 修改代码前必须先输出计划。
2. 用户说“先讨论”“只读检查”“暂时不要修改代码”时，必须进入只读模式。
3. 如果任务涉及 `old-system/`，只能只读分析，不能修改旧系统目录。
4. 如果规则冲突，必须停止并询问用户。
5. 如果上下文过长，必须写入 `docs/handoffs/`。
6. 不允许因为 Claude 工具能力不同而绕过项目规则。

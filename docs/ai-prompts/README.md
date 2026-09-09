# AI Prompt Templates

## Purpose

这些模板承载重复执行边界。项目负责人通常只需提供：

1. 工作目录。
2. 当前分支。
3. 当前任务 PRP 或对应 prompt 模板及精确目标。

AI 必须读取 `CODEX_START_HERE.md`、`AI_DAILY_RULES.md`、对应模板和当前 PRP；不得依赖旧聊天记忆。模板不会扩大 PRP、文件、系统、数据库、API、部署或 Git 权限。

## Templates

- `PRP_AUTHOR_PROMPT.md`：只编写 PRP。
- `DOCS_ONLY_TASK_PROMPT.md`：只改批准文档。
- `BACKEND_IMPLEMENTATION_PROMPT.md`：已批准后端实现。
- `FRONTEND_IMPLEMENTATION_PROMPT.md`：已批准前端实现与组件复用计划。
- `POST_MERGE_CLEANUP_PROMPT.md`：合并后只读核对和负责人清理提示。
- `RECOVERY_STOP_PROMPT.md`：状态不一致时停止。
- `TASK_HANDOFF_TEMPLATE.md`：任务交接格式。

使用模板时必须替换所有 `<...>` 占位；未确定值不得猜测。

# Codex 工作流

## 文件用途

本文件用于项目负责人使用 Codex 时的工作流程说明。核心规则仍以 `AGENTS.md` 为准。

## 标准流程

1. 从项目根目录启动 Codex。
2. 让 Codex 读取 `AGENTS.md` 和任务相关文档。
3. 让 Codex 执行 `git status` 和 `git branch`。
4. 如果在 `main` / `dev`，先创建任务分支。
5. 让 Codex 输出技术实施计划。
6. 用户确认。
7. Codex 小范围修改。
8. Codex 输出 `git diff --stat`、测试结果、风险点。
9. 用户审查。
10. 提交 PR。

## 分支示例

```bash
git checkout dev
git pull origin dev
git checkout -b ai/20260831-ads-campaign-list
```

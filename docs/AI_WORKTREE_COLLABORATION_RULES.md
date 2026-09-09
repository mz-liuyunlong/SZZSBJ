# AI Worktree Collaboration Rules

## Purpose

隔离并行任务，避免 AI 在共享目录切分支、覆盖未提交工作或依赖聊天记忆。

## Required Rules

- 一个任务 = 一个独立 worktree = 一个独立分支 = 一个 PR。
- 主目录保持干净 `main`，默认不作为开发目录。
- 新任务由负责人确认后使用：

```bash
git fetch --prune origin
git worktree add -b <branch> ../<worktree> origin/main
```

- AI 不得自行创建、删除或切换 worktree；负责人负责 Git 写操作。
- 本文件是新任务 worktree 创建流程的当前权威入口；旧文档中在主目录执行 `git switch`/`git pull` 的分支示例不得用于新任务。
- 每次开始必须输出 worktree、branch、base commit、`git status --short --untracked-files=all`、目标和 allowlist。
- AI 新会话必须从仓库入口、prompt、PRP 和当前 Git 状态重建上下文，不得依赖旧聊天记忆。
- 发现不属于当前任务的 modified/untracked 文件时立即停止，不得“顺手处理”。
- 暂存必须使用精确文件清单；禁止 `git add .`。
- `.planning/**` 是本地执行记录，默认不得进入 staging、commit 或 PR。

## Forbidden Patterns

未经负责人确认，AI 不得执行 `git switch`、`git pull`、`git stash`、`git stash pop`、`git reset`、`git restore`、`git clean`、`git merge`、`git rebase` 或 `git push --force`。

## Recovery Stop Rule

实际目录、预期 worktree、分支、base、dirty 状态或任务范围任一不一致时，停止并报告事实、风险和负责人可执行的恢复选项；不得自行修复 Git 状态。

## Task Handoff

交接必须包含：Task、Owner/Role、Worktree、Branch、Base commit、PR、Files changed、Implemented、Explicitly not implemented、Validation、Remaining risks、Cleanup status、Next recommended task。

合并后的 worktree/分支清理由负责人按 `docs/ai-prompts/POST_MERGE_CLEANUP_PROMPT.md` 执行。

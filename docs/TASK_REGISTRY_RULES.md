# Task Registry Rules

## Purpose

以仓库文件记录任务状态和边界，避免把聊天记录当项目真源。

## Required Rules

- `docs/tasks/TASK_REGISTRY.md` 是任务登记真源；项目管理工具只能作为镜像。
- 一个登记项对应一个可独立审查和回滚的任务。
- 开始前登记 task ID、目标、主执行角色、worktree、branch、base、PRP、allowlist 和状态。
- 合并后补 PR、merge commit、验证、清理状态和后续任务。
- 只有仓库证据和测试可支持 `implemented`；`planned`、`approved`、`no_api` 均不表示实现。
- 任务状态必须遵守 `docs/STATUS_AND_LIFECYCLE_RULES.md`。

## Stop Conditions

任务 owner、范围、分支或 PRP 不明确；登记状态与 Git 事实冲突；一个任务混入多个模块时停止并由负责人确认。

## Checklist

- [ ] 状态和证据一致。
- [ ] 只有一个主执行角色。
- [ ] Worktree、branch、PRP、PR 可追溯。
- [ ] `Explicitly not implemented` 已记录。
- [ ] 未记录 secret 或生产连接信息。

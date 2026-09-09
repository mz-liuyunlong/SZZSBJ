# Task Registry

Registry Status: `draft; approved only after owner review and merge`

本表只登记有仓库证据的任务。空白不代表任务不存在；聊天中提及也不构成登记或批准。

| Task ID | Task | Main Role | Status | Worktree | Branch | Base Commit | PRP | Allowed Scope | PR | Merge Commit | Validation | Cleanup Status | Explicitly Not Implemented | Next Task | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| data-layer-foundation-prp-approval | Approve Data Layer Foundation implementation PRP | Project Owner | approved | `<project-worktrees-root>/docs/<project-root-name>-approve-data-layer-foundation-prp` | `docs/approve-data-layer-foundation-prp` | `4214e57` | `PRPs/data-layer-foundation-implementation.md` | PRP approval metadata and this task registry record only |  |  | `git diff --check`: PASS; scope check: PASS; rule-pack script: known worktree `.git` pointer false positive, not bypassed; no real secrets; no forbidden implementation changes | active | Backend/frontend code, database access, migrations, business tables, Product API, Source Registry, RAW Storage, external APIs, CI PostgreSQL, and Git publishing | Owner-issued Data Layer Foundation implementation prompt | Owner approval recorded 2026-09-09; rule-pack worktree compatibility requires a separate PR; implementation is not recorded as complete |
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

## Update Checklist

- [ ] 使用 `docs/STATUS_AND_LIFECYCLE_RULES.md` 中的状态。
- [ ] 未合并任务不得标记 `implemented`。
- [ ] PR 和 merge commit 仅在真实存在后填写。
- [ ] 未写入账号、密钥、连接串或生产数据。

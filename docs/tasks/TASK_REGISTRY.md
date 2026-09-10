# Task Registry

Registry Status: `draft; approved only after owner review and merge`

本表只登记有仓库证据的任务。空白不代表任务不存在；聊天中提及也不构成登记或批准。

| Task ID | Task | Main Role | Status | Worktree | Branch | Base Commit | PRP | Allowed Scope | PR | Merge Commit | Validation | Cleanup Status | Explicitly Not Implemented | Next Task | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| data-layer-foundation-prp-approval | Approve Data Layer Foundation implementation PRP | Project Owner | implemented | `<project-worktrees-root>/docs/<project-root-name>-approve-data-layer-foundation-prp` | `docs/approve-data-layer-foundation-prp` | `4214e57` | `PRPs/data-layer-foundation-implementation.md` | PRP approval metadata and this task registry record only | `#36` | `0cd20c2` | `git diff --check`: PASS; scope check: PASS; rule-pack script: known worktree `.git` pointer false positive, not bypassed; no real secrets; no forbidden implementation changes | merged | Backend/frontend code, database access, migrations, business tables, Product API, Source Registry, RAW Storage, external APIs, CI PostgreSQL, and Git publishing | Data Layer Foundation implementation, merged separately in PR #38 | Owner approval recorded 2026-09-09; PR #36 merged at `0cd20c2`; implementation is tracked separately below |
| data-layer-foundation-implementation | Implement Data Layer Foundation | Backend Engineer | implemented | `<project-worktrees-root>/backend/<project-root-name>-data-layer-foundation` | `feat/data-layer-foundation` | `0cd20c2` | `PRPs/data-layer-foundation-implementation.md` | PostgreSQL settings; synchronous SQLAlchemy Base/engine/session/dependency; Alembic scaffold; isolated test fixture; env safeguards; module/data registry alignment | `#38` | `63b281b` | PR #38 merged; implementation validation recorded Ruff format/lint, mypy, pytest (`30 passed, 1 skipped` without `TEST_DATABASE_URL`), safe app import, offline Alembic heads, diff, secret, and scope checks; no database connection | merged | Business tables, Product API, Source Registry, RAW Storage, external APIs, production database access, CI PostgreSQL, migration revisions, and migration execution | Separate Owner-approved PRP before Source Registry or RAW Storage work | Foundation infrastructure only; skipped PostgreSQL integration test remains dependent on an explicitly approved disposable test service |
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

## Update Checklist

- [ ] 使用 `docs/STATUS_AND_LIFECYCLE_RULES.md` 中的状态。
- [ ] 未合并任务不得标记 `implemented`。
- [ ] PR 和 merge commit 仅在真实存在后填写。
- [ ] 未写入账号、密钥、连接串或生产数据。

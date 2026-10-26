# Findings

- PR #239 added read-only WFS calculation, collection seams, standard-fee lookup and dry-run case scaffolding.
- Existing WFS tests pass: 102 passed on the prior detached worktree baseline.
- The existing Integration Sync run/work-item/RAW pipeline and WFS case unique constraint were reusable; no parallel task or case system was needed.
- A store-specific `scope_key` is required on offset work items because one run collects multiple stores with the same page offsets.
- Manual preview must prove successful collection for the exact account/store/window; account-level run success alone is insufficient.
- Source-line upsert must fail closed when store/Item/MSKU identity changes; mutable evidence may update only within the same canonical identity while RAW retains response history.
- The repository-wide mypy command is not currently a clean gate: test discovery finds `domestic_postgresql_support.py` twice, and `mypy app` reports unrelated baseline errors. The 11 changed application modules pass a focused check with imports skipped.
- Current case execution is deliberately disabled; batch runner is read-only and unscheduled.
- Lingxing profit-order endpoint inventory remains unverified for real provider traffic; this task approves local implementation only and keeps all real-call switches closed.
- Existing modules must be extended rather than replaced.

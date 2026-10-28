# Findings

## Owner review hardening (2026-10-26)

- Production detection incorrectly used the collection window end as the
  freshness clock. Historical collection and backtest clocks must be separate.
- Daily Sales rows prove observed sales, not lifetime completeness. The current
  repository has no product-lifecycle start watermark, so automatic detection
  must treat unproven lifetime coverage as `unknown`/`partial`, never `complete`.
- Per-page normalized writes can survive a later-page failure. Detection needs an
  exact account/store/window collection proof and facts linked to that proof.
- `storeId` is present in the repository contract evidence and is the stable
  identity; `storeName` is descriptive only and cannot authorize a match.
- The repository contract does not prove that every non-zero
  `platformLogisticsAmount` is WFS. Until controlled contract evidence exists,
  fee scope must remain unverified and automatic case creation must fail closed.
- `CS*` is a governed business exclusion, not a malformed identity. Parser output
  must distinguish accepted, excluded, invalid, duplicate and missing-identity
  rows.
- Existing Product Management effective-dated/approved pricing rules already
  provide the standard-fee confirmation boundary; a second confirmation system
  is unnecessary.
- Per-row WFS reads/writes were avoidable: standard fee resolution is bounded at
  3 execute + 2 scalar queries, sales coverage at 3 queries, and settlement
  persistence at one identity read plus one batch upsert.
- Seeded PostgreSQL 16 validation preserved pre-0061 synthetic fact/case rows
  through 0060→0061→0060→0061; the downgrade intentionally refuses non-empty
  new collection/evidence tables to prevent silent evidence deletion.

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

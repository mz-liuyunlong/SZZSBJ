# WFS Clearance Center: implementation PRP (owner-approved scope)

## Objective

Replace Clearance Center demo/localStorage with real Postgres-backed, scoped risk analysis, global versioned rule config, manual single-Listing applications, review via the existing Approval Workbench UI, automatic internal task start upon review approval, lifecycle protection, LA-day sales progress and idempotent completion. Never auto-submit applications or execute Walmart price/advertising changes.

## Scope and ownership

Owner: Clearance Center business AI developer. Authorized cross-module edits limited to clearance-specific integration in `app.main`, Celery task routing, approval-workspace clearance tab, Listing lifecycle release guard, and successful integration-sync post-hook. No changes to other approval types or financial formula modules. No old-system edits.

## Real data sources

See `docs/data-sources/decisions/clearance-center-20261106.md`. Unknown values must never be converted to zero; financial values use effective store commission rules, USD evidence, and original product cost calculation. WFS first-stock date is immutable, not a batch inventory age.

## Business invariants

1. One active `(account, store, item)` application/task, guarded by PostgreSQL partial unique index.
2. Only user interactions create applications, and approval is checked with clearance-review permission.
3. Any authorized store-scope page user may apply, even if not the live Listing owner.
4. Applicant can withdraw their own pending application; notes optional. Approval pass note optional, rejection reason mandatory. Authorized reviewer can approve their own application.
5. Approval locks application and Listing, re-reads latest WFS available, sets approved qty `min(requested,available)`, closes on verified 0, rejects unknown inventory.
6. Approval pass atomically updates internal task to `running`, Listing to `清货期`; no external price or ads action.
7. Actual total item sales progress starts LA midnight of approval date. Refunds/returns are not deducted; corrections do not re-open completed tasks.
8. Completion by recorded sales, verified stock 0, or authorized manual action; leaves Listing `清货期` until next ordinary lifecycle calculation without restoring a previous stage.
9. Global admin edits use version optimistic lock and rerun risk analysis; every candidate is re-evaluated nightly using LA dates and on in-scope successful source syncs.
10. High/medium risk candidate list; manual SKU search also covers eligible low/unknown WFS inventory. No hide/ignore control.
11. Removed four unreliable inventory-age-lot rules, repeat backlog and manual ignore. New-product protection 60d on by default, distinct from zero-sales minimum listing age 30d.
12. Unit inventory capital excludes future fulfilment/referral charges, whereas unit full-sale cost and margin include both, using current store-specific rates.

## Tests and acceptance

`backend/tests/modules/clearance/test_evaluator.py` includes 13 pure-evaluation tests. After applying source, run backend pytest, frontend build/lint, new approval and workflow integration tests against a local isolated PostgreSQL with migration applied. Do not mark business flow production-ready until those tests pass. CI may be blocked by private-repository billing; record that separately.

## Rollback / release

Local install does not run DB migrations, push, commit or deploy. For app runtime rollback, switch source release while preserving immutable clearance tables and approval audit. Migration destructive downgrade intentionally refused. Rollback decisions require explicit owner authorization.

## PR #324 CI verification

This draft remains unmerged. Migration 0082 follows finance 0081; clearance
lifecycle and approval history downgrades are refused. The full CI suite must
pass on the reviewed commit before any merge or production authorization.

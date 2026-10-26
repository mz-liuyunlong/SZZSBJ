# WFS Fee Anomaly Auto Detection

Status: local_validation_complete_pending_push_and_ci
Branch: feat/wfs-fee-anomaly-auto-detection
Base: 4c8f67156ae960a2f7397f4c957c1a5b91814d1d

## Plan

- [x] Close Owner-review P0 gaps: detection-time freshness, sales coverage proof,
  verified collection isolation, parser classifications, terminal work items and
  isolated PostgreSQL case tests.
- [x] Complete bounded P1 hardening: append-only detection evidence, shared fee
  arithmetic, batch reads, date-window splitting, stable store identity and 0061
  migration compatibility tests.
- [x] Re-run backend/frontend/isolated-PostgreSQL local gates and update documentation.
- [ ] Commit and push only to PR #257, then require the latest PR HEAD CI to pass.

- [x] Record approved Source Decision and PRP from the Owner task.
- [x] Audit existing WFS, Lingxing, Product Management, sales, Celery and frontend flows.
- [x] Close settlement parsing/calculation and collection completeness gaps.
- [x] Add governed settlement evidence and sales readers only where existing storage is insufficient.
- [x] Complete anomaly amounts, quality states and idempotent case creation.
- [x] Wire default-off multi-store Celery orchestration and protected preview/status API.
- [x] Extend the existing WFS page using existing shared components.
- [x] Add backend/frontend tests and run the approved local validation matrix, including a disposable localhost PostgreSQL 16 database with seeded 0060 data, 0061 upgrade/downgrade/re-upgrade and real concurrent case writes.
- [x] Update registries, API docs, SOP and handoff evidence.

## Hard boundaries

- No production DB, migration execution, provider call, token request, deployment, restart or task enablement.
- No old-system modification or import.
- Automatic detection and automatic case creation remain separate and default-off.
- No real credential or raw business payload in Git, logs, tests or docs.

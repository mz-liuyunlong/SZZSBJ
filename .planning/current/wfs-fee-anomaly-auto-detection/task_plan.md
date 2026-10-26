# WFS Fee Anomaly Auto Detection

Status: ready_for_review
Branch: feat/wfs-fee-anomaly-auto-detection
Base: 4c8f67156ae960a2f7397f4c957c1a5b91814d1d

## Plan

- [x] Record approved Source Decision and PRP from the Owner task.
- [x] Audit existing WFS, Lingxing, Product Management, sales, Celery and frontend flows.
- [x] Close settlement parsing/calculation and collection completeness gaps.
- [x] Add governed settlement evidence and sales readers only where existing storage is insufficient.
- [x] Complete anomaly amounts, quality states and idempotent case creation.
- [x] Wire default-off multi-store Celery orchestration and protected preview/status API.
- [x] Extend the existing WFS page using existing shared components.
- [x] Add backend/frontend tests and run the approved local validation matrix. Isolated PostgreSQL remains an explicit opt-in follow-up because no disposable database was configured.
- [x] Update registries, API docs, SOP and handoff evidence.

## Hard boundaries

- No production DB, migration execution, provider call, token request, deployment, restart or task enablement.
- No old-system modification or import.
- Automatic detection and automatic case creation remain separate and default-off.
- No real credential or raw business payload in Git, logs, tests or docs.

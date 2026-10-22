# Walmart Monitor RAW Ingestion V1 — Handoff

## Scope delivered

- Approved single `POST /api/integrations/walmart-monitor/raw-events` endpoint.
- Exact-route least-privilege machine token authentication.
- Strict `walmart-monitor.raw.v1` schemas for targets, attempts, artifacts, and final snapshot.
- Bounded gzip/base64/size/SHA-256 validation before persistence.
- Independent append-only `raw_walmart_monitor_events` model and additive Alembic 0048.
- PostgreSQL atomic event-ID idempotency and changed-replay conflict behavior.
- Unified response/error envelope, API documentation, module/data/task registry entries.
- Synthetic tests only; no provider, server, or production database access.

## Explicitly not delivered

- Product-source target GET API and monitor producer changes are implemented only in separate
  worktrees; they are not delivered by this RAW receiver branch.
- Live delivery, historical production replay, or end-to-end deployment.
- Historical import.
- RAW read endpoint, parser, replay worker, ODS/current/history/MART/Listing projections.
- Category or monitoring-result fields in Listing Management.
- Celery, object storage, retention jobs, production migration, deployment, or secret setup.

## Security and rollback

- The token is loaded only from `WALMART_MONITOR_INGEST_TOKEN`, masked as `SecretStr`, and
  accepted only for the exact POST route.
- The machine principal receives only `integrations:walmart-monitor:write`.
- Responses and errors do not include RAW data, product identifiers, or credentials.
- Disable/remove the deployment secret to fail closed. Code rollback may remove the router/auth
  seam; keep the RAW table for audit unless a separately approved production data-retention plan
  permits removal.
- Migration downgrade drops only the new table and is not authorized for production by this PR.

## Validation status

- Targeted Walmart Monitor plus Alembic tests: `29 passed`.
- Full backend tests: `1337 passed, 28 skipped` (existing explicit database opt-in suites).
- Full Ruff format/lint, compileall, OpenAPI contract, Alembic head (`0048`), rule-pack and
  `git diff --check` passed.
- Full mypy remains blocked by the unchanged repository baseline (`214 errors in 32
  unrelated/imported files`); no baseline files were changed to hide those errors.

## Next gate

Owner/code review, then a separate production migration/deployment authorization. The product
source API and monitor-side connection remain separate tasks and PRs even though both now have
local implementations.

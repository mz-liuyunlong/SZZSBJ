# Production Lingxing Product Info Sync Runbook

## Current gate

The Product Management BFF, parser/publisher, batch plan, work-item foundation and calculations may
be deployed after review and merge. A real `batchGetProductInfo` request is **not authorized**.
Official request fields, content type, authentication/signing applicability, success/error codes,
batch limit, rate limit and retry behavior remain incomplete. Until those gaps are closed, the
dedicated outbound setting stays false and execution fails with `outbound_not_authorized` or
`provider_contract_missing`.

Do not request a Token, call Lingxing/Walmart, start a sync run, or enable a schedule from this PR.
This branch implements code and synthetic tests only; it does not claim a production migration,
pricing-rule publication, pricing recalculation, or real Product Info synchronization has run.

## Pre-deployment checklist

1. Deploy only a reviewed, clean, merged `main` revision; never run worktree code on a server.
2. Confirm `DATABASE_URL` points to `APPLICATION_DATABASE` without printing the URL or password.
3. Back up/snapshot the database, or confirm that the target is a new empty application database.
4. Review the Alembic head and migration SQL in CI or a disposable test PostgreSQL first.
5. Apply the migration only under the existing one-time production gate:

   ```bash
   PRODUCTION_MIGRATIONS_AUTHORIZED=true uv run alembic -c alembic.ini upgrade head
   ```

6. Do not persist the migration gate in a service environment file.
7. Keep the batch Product Info outbound switch false and all schedules disabled.
8. Before any pricing execution, publish an account-scoped open rule version through the protected
   API. Publication closes the prior open version in the same transaction; an overlap or concurrent
   second open version must stop with `RULE_VERSION_CONFLICT`.
9. Call the protected recalculation endpoint with `preview_only=true` first. Review only the safe
   run ID, mode, status and counts. Execute with `preview_only=false` only after that review and use
   the intended account scope, rule version/effective time, bounded limit and idempotency key.

If migration fails, stop. Do not continue to Token or provider requests. Commands and logs must not
print database URLs, passwords, provider credentials, Token values, signatures, authorization
headers, RAW payloads, SKU/product values, image URLs, or pricing inputs.

Every preview and execute request persists one safe `product_pricing_recalculation_runs` record,
including zero-result runs. Idempotency is isolated by principal, account, capability, mode and key;
the normalized request digest and resolved rule version prevent a changed request from replaying as
the original. Preview must not write `dws_product_management_pricing_current`; only execute may
update that current projection. Do not place SKU text, Product fields, RAW/payload content or amount
inputs in run/audit records or logs.

## Future separately authorized manual validation

Only after the Owner records complete official contract evidence and issues a separate execution
authorization may an operator perform one manual, bounded run. That future authorization must state
the exact merged revision, logical non-secret account reference, maximum IDs/pages/attempts,
timeout, stop conditions and redacted evidence fields.

The future sequence is:

1. Confirm the active ProductList identity set and account scope are persisted.
2. Confirm the Product Info interface/config is explicitly approved but `schedule_enabled=false`.
3. Create one manual governed run and bounded `id_batch_page` work items from active
   `lingxing_sku_id` values only.
4. Request the minimum required Token only through the approved Token Manager.
5. Persist redacted RAW/request evidence before parsing and publishing snapshots/current rows.
6. Rebuild the current base/pricing projection without changing historical snapshots.
7. Verify only safe counts and statuses: work items total/succeeded/failed, records seen/written,
   snapshot/current/image/tag counts, calculation status counts, and duplicate/rejected counts.
8. Keep schedules disabled after the manual run.

Stop immediately on an unknown provider code, contract mismatch, incomplete page/batch, account
scope mismatch, duplicate identity ambiguity, lineage failure, missing active rule, calculation
input failure above the approved threshold, or any possible credential/RAW/business-value leak.

## Rollback and recovery

- Provider failure must not clear the last successful current projection.
- Parser/publisher failure rolls back its transaction and leaves the source RAW evidence governed.
- Pricing rule changes do not automatically recalculate history; snapshots are immutable.
- A failed deployment is rolled back by application revision. Database downgrade requires separate
  Owner authorization and reviewed migration safety; never hand-edit production tables.
- RAW files and provider payload captures must never be added to Git.

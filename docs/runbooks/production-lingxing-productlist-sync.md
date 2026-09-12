# Production Lingxing ProductList Sync Runbook

Status: implementation prepared; execution is prohibited until this change is reviewed, merged to
`main`, deployed, and manually authorized by the Project Owner.

Source Decision:
`docs/decisions/2026-09-13-production-lingxing-productlist-sync-source-decision.md`

## Fixed boundary

- The only authorized Lingxing business endpoint is ProductList:
  `/erp/sc/routing/data/local_inventory/productList`.
- The required Token flow is internal to the existing Token Manager. Never print or copy its
  credentials, request fields, responses, or query authentication material.
- The only authorized database target is `APPLICATION_DATABASE`, supplied through the server
  `DATABASE_URL` secret.
- The first execution is manual only. `schedule_enabled` must remain `false`.
- The only tables this execution may write are:
  `gov_integration_sync_runs`, `gov_integration_sync_run_work_items`, `ods_api_raw_blobs`,
  `ods_api_raw_request_refs`, `ods_lingxing_productlist_sku_refs`, and
  `dwd_lingxing_sku_identity_index`.
- Do not call `batchGetProductInfo` or any other provider endpoint. Do not write Product Core,
  detail, DWS, legacy MySQL, or legacy `raw_lingxing_api`.

## Before migration

Stop unless every item is confirmed without printing a DSN or credential:

1. The deployed revision comes from a clean, merged `main` build. No server-side patch is present.
2. The application environment is the formal server environment; local/test execution remains
   blocked by code.
3. `DATABASE_URL` resolves to the owned PostgreSQL `APPLICATION_DATABASE`, not an old-system,
   MySQL, test, staging, dev, or other database.
4. `APPLICATION_DATABASE` is new or has a verified backup/snapshot and recovery path.
5. The database account has only the minimum required application and migration privileges.
6. The migration head, expected schema, capacity, and lock impact have been reviewed.

Run the migration from the clean, merged `main` backend deployment with authorization scoped to
that one command only:

```bash
PRODUCTION_MIGRATIONS_AUTHORIZED=true uv run alembic -c alembic.ini upgrade head
```

Do not add `PRODUCTION_MIGRATIONS_AUTHORIZED` to `/etc/APPLICATION/app.env` or any other persistent
environment file. The command and its output must not print `DATABASE_URL`, database credentials,
Token material, or Lingxing credentials. If the migration fails, stop before any Token or
ProductList request.

## Before the manual run

Verify through approved metadata tooling that the ProductList interface, active retention policy,
and scoped sync config already exist. Do not insert missing prerequisite rows by hand under this
authorization. Confirm all of the following:

- provider is `lingxing`, interface key is `productList`, method is `POST`, and request kind is
  `offset_page`;
- the endpoint path is the approved ProductList path;
- the config is enabled, `schedule_enabled=false`, `page_size` is at most `1000`, and `max_pages`
  is bounded;
- the source-account scope is the intended non-secret logical account reference;
- server credential variables are present through the controlled secret mechanism, without
  printing their values;
- ProductList outbound and Token requests are enabled only for this Owner-authorized run.

If any prerequisite is missing or ambiguous, stop and request a separate Owner decision.

## Manual trigger

An authorized operator with `integrations:execute` and the matching source-account scope triggers
the existing protected manual-run endpoint for the ProductList config. Do not include credentials,
authentication query fields, full URLs, RAW, or product values in the request reason or operator
notes.

The worker processes pages serially from offset `0`, with `length <= 1000`. Each successful
response is written as credential-redacted RAW and safe request metadata before any SKU identity
parsing or publication. An empty page, the provider total, or the bounded page limit ends the loop.
Duplicate IDs or inconsistent totals fail the run; inactive identities are reconciled only after a
complete successful run and are never physically deleted.

## Post-run reconciliation

Use the protected run/status APIs or parameterized read-only queries. Never select or print
`payload_json`, external ID values, product fields, authentication material, archive URI values, or
full request URLs. For the selected `run_id` and non-secret `source_account_ref`, record only:

- `total_captured`: `gov_integration_sync_runs.records_seen`;
- `raw_blobs_count`: distinct RAW blob references for the run;
- `request_refs_count`: request-reference rows for the run;
- `work_items_count`: work-item rows for the run;
- `sku_identity_active_count`: active Lingxing identities in the same account scope;
- `duplicate_ids_detected`: `0` for a successful run, or the safe aggregate recorded on a
  duplicate failure;
- `inactive_ids_count`: inactive identities whose reconciliation run is the selected run.

A successful run must have `total_captured == sku_identity_active_count`. Request references must
cover every successfully captured page; the number of distinct RAW blobs may be lower only when
response-hash deduplication is explainable. Stop all further real-interface expansion if totals,
work items, RAW references, or active identities cannot be reconciled.

## Failure and rollback

Keep `schedule_enabled=false`, disable ProductList outbound, and stop creating runs. Preserve run,
work-item, RAW, request-reference, and identity evidence. Do not delete rows, downgrade migrations,
retry with relaxed validation, call another endpoint, or inspect/print product payloads to diagnose
the failure. Credential exposure requires immediate stop and Owner-managed rotation without
repeating the exposed value.

RAW JSON and archive files must remain outside Git. Never add them to a commit, report, log, or
task output.

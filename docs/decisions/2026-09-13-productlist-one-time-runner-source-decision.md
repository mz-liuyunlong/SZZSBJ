# Source Decision: ProductList one-time runner

```text
Decision Date: 2026-09-13
Decision Owner: Project Owner
Status: APPROVED_FOR_IMPLEMENTATION
Implementation Branch: feat/productlist-one-time-runner
Current Real Request Permission: No
Future Trigger: Owner-authorized one-time server command only
Allowed Business Endpoint: ProductList only
Schedule Permission: No
```

## Decision

The Project Owner authorizes implementation of a reviewed one-time runner that creates one manual
ProductList sync run and invokes the existing ProductList handler directly. This change does not
authorize executing the runner, requesting a Token, calling ProductList, connecting to a server, or
writing the production application database during development or review.

A future real execution requires a new Owner decision for the exact server operation and the
one-command authorization value `PRODUCTLIST_ONE_TIME_RUN_AUTHORIZED=true`. The operator must supply
a non-secret logical `PRODUCTLIST_SOURCE_ACCOUNT_REF`. Real-call and RAW-write overrides may exist
only for that command; they must not be persisted in an application environment file.

## Fixed scope

- The only permitted business endpoint is
  `/erp/sc/routing/data/local_inventory/productList`.
- The runner uses neither FastAPI nor Celery and does not enable scheduling.
- `batchGetProductInfo` and every non-ProductList provider endpoint remain unauthorized.
- Governance interface, retention-policy, and sync-config rows are read-only prerequisites. Missing
  or mismatched rows cause a safe stop; the runner does not repair or upsert them.
- The future ProductList handler may write only sync runs, sync work items, credential-redacted RAW
  blobs, safe request references, ProductList SKU references, and the Lingxing SKU identity index,
  including their execution state updates.
- Product Core, DWS, old-system data, legacy MySQL, legacy RAW tables, and all other tables remain
  outside this authorization.

## Security and output boundary

The runner may output only generated run identifiers, safe status/error codes, configured page
bounds, and aggregate counts. It must not output the source-account value, database connection
material, credentials, authentication parameters, full URLs, provider responses, RAW payloads,
archive locations, or product fields. RAW JSON and archives remain outside Git.

## Stop conditions

Stop without executing the handler if the one-time authorization is absent, the application is not
in the production environment, any required real-request/write guard is not exact, governance is
missing or inconsistent, another ProductList run is running, or the optional idempotency/reason
input fails non-secret validation. Schedule activation or any broader integration requires a new
Owner decision.

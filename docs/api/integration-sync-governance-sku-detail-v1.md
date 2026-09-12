# Integration Sync Governance + Lingxing SKU Detail V1 API

Status: foundation implemented in PR #61; ProductList-only formal server sync implementation is
prepared on `feat/production-lingxing-productlist-sync` and remains unexecuted until review, merge,
deployment, and a separate Owner manual trigger.

## Contract boundary

- Envelope: `{ success, data, error, meta, request_id }`.
- Runtime source: persisted new-system PostgreSQL governance, DWD, DWS, and Product Core
  listing projections only.
- Authentication: trusted backend `Principal`; no role names are hard-coded.
- Data scope: protected records require a trusted opaque `source_account_ref` allowlist;
  missing/empty scope fails closed. Confirmed Product listing reads also require existing Product scope.
- Pagination: `page >= 1`, `1 <= page_size <= 100`, deterministic ID tie-breakers.
- Freshness: non-empty reads derive `meta.freshness_at` only from persisted run, snapshot,
  RAW-reference, identity, event, or calculation timestamps; it is not a real-time SLA.
- External effects: read routes never call a provider. The protected ProductList manual-run route
  dispatches work; only the merged server deployment may invoke the approved Token and ProductList
  transports. Tests use fakes/`MockTransport` only.
- RAW boundary: only request/blob metadata is serializable; `payload_json`, source values,
  archive URI values, auth material, and full ID batches are excluded.

## Integration endpoints

| Method and URL | Permission | Request | Success data | Source objects | Read-only / audit / risk |
|---|---|---|---|---|---|
| `GET /api/integrations/interfaces` | `integrations:read` | `provider?`, `enabled?`, pagination | Safe interface catalog page | `gov_integration_interfaces` | Read-only; global catalog metadata; no base URL or credentials |
| `GET /api/integrations/sync-configs` | `integrations:read` | Safe filters and pagination | Account-scoped safe configs | `gov_integration_sync_configs` | Read-only; account-scoped |
| `PATCH /api/integrations/sync-configs/{config_id}` | `integrations:update` | Allowlisted schedule/page/batch/retention fields | Updated safe config | `gov_integration_sync_configs` | Audit records actor/request ID and changed field names only; cannot change account, interface, credential, or transport |
| `POST /api/integrations/sync-configs/{config_id}/run` | `integrations:execute` | Required `reason`; optional idempotency key | Queued manual ProductList run; HTTP 202 | `gov_integration_sync_runs` | Exact Lingxing ProductList config only; requires enabled config/interface and `schedule_enabled=false`; no inline provider work |
| `POST /api/integrations/sync-runs/{run_id}/retry` | `integrations:execute` | Required `reason`; optional idempotency key | Queued retry run; HTTP 202 | `gov_integration_sync_runs` | ProductList retries are refused by the current manual-only authorization |
| `POST /api/integrations/sync-configs/{config_id}/backfill` | `integrations:execute` | UTC window, required reason, optional idempotency key | Queued backfill run; HTTP 202 | `gov_integration_sync_runs` | ProductList backfills are refused; other real provider execution remains disabled |
| `GET /api/integrations/sync-runs` | `integrations:read` | Safe status/trigger/time filters and pagination | Sanitized run page | `gov_integration_sync_runs` | Read-only; account-scoped; counters/codes only |
| `GET /api/integrations/sync-runs/{run_id}` | `integrations:read` | UUID path ID | Sanitized run | `gov_integration_sync_runs` | Read-only; account-scoped |
| `GET /api/integrations/sync-runs/{run_id}/work-items` | `integrations:read` | Safe filters and pagination | Work-item metadata | `gov_integration_sync_run_work_items` | Read-only; no complete external ID list |
| `GET /api/integrations/sync-runs/{run_id}/raw-request-refs` | `integrations:raw_metadata:read` | Pagination | RAW ref/blob metadata | `ods_api_raw_request_refs`, `ods_api_raw_blobs` | Sensitive metadata read; no payload or archive URI value |

## SKU endpoints

`{sku_id}` is the internal UUID of `dwd_lingxing_sku_identity_index`; it is not a
provider SKU ID or SKU code.

| Method and URL | Permission | Request | Success data | Source objects | Read-only / audit / risk |
|---|---|---|---|---|---|
| `GET /api/products/skus` | `products:read` | `provider=lingxing`, `active?`, `mapping_status?`, pagination | Identity/current/profile summary page | DWD identity/current, DWS current | Read-only; account-scoped |
| `GET /api/products/skus/{sku_id}/detail` | `products:read`; costs require `products:cost:read` | UUID path ID | Non-staff detail, images, tags, profile; optional cost block | DWD current/children, DWS current | Cost access records safe actor/request/internal-ID metadata only; no RAW fallback or request-time calculation |
| `GET /api/products/skus/{sku_id}/sync-history` | `products:sync_history:read` | Pagination | Run/work-item/snapshot/parser metadata | DWD snapshots, governance runs/work items | Read-only; metadata only |
| `GET /api/products/skus/{sku_id}/raw-lineage` | `products:raw_lineage:read` | Pagination | Lineage paths, hashes, IDs, storage state | `gov_data_lineage`, RAW metadata | Sensitive metadata; no source values or archive credentials |
| `GET /api/products/skus/{sku_id}/platform-listings` | `products:read` plus Product scope | Pagination | Approved listing subset or empty unmapped result | Confirmed identity mapping, `product_platform_listings` | Never infers mapping from SKU strings |
| `GET /api/products/skus/{sku_id}/cost-history` | `products:cost:read` | Pagination | Snapshot costs with currency companions | DWD detail snapshots | Sensitive read with safe access audit metadata; no FX conversion |
| `GET /api/products/skus/{sku_id}/operation-logs` | `products:operation_logs:read` | `event_type?`, pagination | Sanitized state/parse-event metadata | Governance run events | Read-only; excludes payload and arbitrary details |

## Errors

| HTTP | Error code | Meaning |
|---|---|---|
| 401 | `UNAUTHORIZED` | Trusted principal absent |
| 403 | `FORBIDDEN` | Permission absent |
| 403 | `DATA_SCOPE_DENIED` | Trusted account/Product scope absent or denied |
| 404 | `NOT_FOUND` | Resource absent or outside visible scope |
| 409 | `SYNC_RUN_ALREADY_RUNNING` | Provider/interface concurrency conflict |
| 409 | `SYNC_INTERFACE_DISABLED` | Config or outbound interface is disabled |
| 409 | `SYNC_PRODUCTLIST_ONLY` | Manual execution target is not the approved ProductList interface |
| 409 | `SYNC_PRODUCTLIST_MANUAL_ONLY` | ProductList schedule, retry, or backfill is not authorized |
| 409 | `SYNC_RUN_NOT_RETRYABLE` | Source run cannot be retried |
| 422 | `VALIDATION_ERROR` | Path/query/body/range/config validation failed |
| 500 | `INTERNAL_ERROR` | Safe generic server failure |
| 503 | `TASK_DISPATCH_UNAVAILABLE` | Durable run exists but queue dispatch is unavailable |

Errors contain no database details, RAW/source values, external ID lists, credentials, URL query
strings, or exception text.

## Safe examples

```http
GET /api/products/skus?page=1&page_size=20
X-Request-ID: req-synthetic-001
```

```json
{"success":true,"data":{"items":[]},"error":null,"meta":{"source":"new_system_postgresql","source_objects":["dwd_lingxing_sku_identity_index","dwd_lingxing_sku_product_info_current","dws_sku_base_profile_current"],"freshness_at":null,"page":1,"page_size":20,"total":0},"request_id":"req-synthetic-001"}
```

The null freshness value for an empty page makes no real-time claim. Non-empty pages use only
persisted timestamps. Local RAW import is a separate CLI/service boundary and is not exposed as
an upload endpoint.

## Explicit exclusions

This implementation task performs no real Lingxing/Token/ProductList request, database connection,
production migration, or server action. After merge, only the Owner-authorized manual ProductList
path may run. No frontend, real `batchGetProductInfo` or other provider request, automatic schedule,
RAW archive/deletion transport, ADS implementation, Product Core overwrite, SKU-string identity
inference, or captured RAW artifact is included.

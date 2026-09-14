# Integration Sync Task API

## 1. Boundary

The Sync Task page is a read-only governance view over persisted new-system metadata. Its frontend
adapter calls the backend only; it never calls Lingxing, requests a Token, reads RAW payloads, or
starts a sync. ProductInfo execution is a separate controlled write path and remains unavailable
from this page.

The page composes these bounded reads:

- `GET /api/integrations/interfaces?page_size=100`
- `GET /api/integrations/sync-configs?page_size=100`
- `GET /api/integrations/sync-runs?page_size=100`

Every response uses `{ success, data, error, meta, request_id }`. Empty sources return empty
`items` arrays. Nullable values remain `null`; the frontend does not invent schedules, success
counts, trends, errors, or timestamps.

## 2. Authentication, permission, and scope

All reads require authenticated permission `integrations:read`. Config and run reads are restricted
by the trusted non-secret source-account scope. Out-of-scope records are not returned.

For local Vite development only, the shared frontend API client may read
`VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN` from the developer's untracked local environment and send it
as `X-Product-Management-Preview-Token` in DEV mode. Preview authentication is limited to GET on
`/api/integrations/interfaces`, `/api/integrations/sync-configs`, and
`/api/integrations/sync-runs`. It never authorizes mutation or execution routes. Never commit a real
preview token or a token-bearing `.env.local` file.

The backend also exposes separately protected mutation routes, but the Sync Task page does not call
them:

- `PATCH /api/integrations/sync-configs/{config_id}` requires `integrations:update`.
- `POST /api/integrations/sync-configs/{config_id}/run` requires `integrations:execute`.
- `POST /api/integrations/sync-runs/{run_id}/retry` requires `integrations:execute`.
- `POST /api/integrations/sync-configs/{config_id}/backfill` requires `integrations:execute`.

The page keeps execute, retry, enable/disable, schedule, and config-save controls disabled. Real
execution requires a separate Owner authorization and server-side gates; UI availability alone can
never authorize it.

## 3. Read contract

### Interfaces

`GET /api/integrations/interfaces` accepts `page`, `page_size`, optional `provider`, and optional
`enabled`. It returns registered interface identity, method, request kind, contract version, and
outbound-enabled state.

### Sync configurations

`GET /api/integrations/sync-configs` accepts `page`, `page_size`, optional `provider`, optional
`interface_key`, and optional `enabled`. It returns account-scoped enablement, schedule, bounded
page/batch controls, maximum attempts, retention-policy reference, and next/last schedule times.

### Sync runs

`GET /api/integrations/sync-runs` accepts `page`, `page_size`, optional provider/interface/status/
trigger filters, and an optional validated created-time range. It returns safe run references,
states, counts, timestamps, request ID, and stable error code/message. It does not return request
bodies, provider responses, business records, or RAW content.

Additional drill-down reads are available for an authorized run:

- `GET /api/integrations/sync-runs/{run_id}`
- `GET /api/integrations/sync-runs/{run_id}/work-items`
- `GET /api/integrations/sync-runs/{run_id}/raw-request-refs`

The last route returns metadata and hashes only, never the stored payload.

## 4. Frontend field metadata

| field | type | source_table | source_column | nullable | frontend_usage | source_status |
|---|---|---|---|---|---|---|
| `interfaceId` | UUID | `gov_integration_interfaces` | `id` | no | stable interface join | persisted |
| `interfaceName` / `taskName` | string | `gov_integration_interfaces` | `display_name` | no | table/filter | persisted |
| `provider` | string | `gov_integration_interfaces` | `provider` | no | row metadata | persisted |
| `taskType` | enum | `gov_integration_interfaces` | `request_kind` | no | row metadata | persisted |
| `status` | enum | governance interface/config | `outbound_enabled` / `is_enabled` | no | enabled state | persisted |
| `sourceAccountRef` | string | `gov_integration_sync_configs` / latest run | `source_account_ref` | yes | scoped row metadata | persisted non-secret reference |
| `autoSync` | boolean | `gov_integration_sync_configs` | `schedule_enabled` | no | schedule state | persisted; never toggled by this page |
| `frequency` | string | `gov_integration_sync_configs` | `schedule_cron` | yes | table/schedule drawer | persisted or manual-only label |
| `nextRunAt` | datetime | `gov_integration_sync_configs` | `next_run_at` | yes | table/schedule drawer | persisted |
| `lastStatus` | enum | `gov_integration_sync_runs` | `status` | yes | table/filter | latest persisted run, otherwise disabled state |
| `lastRunAt` / `lastRunFinishedAt` | datetime | `gov_integration_sync_runs` | `started_at` / `finished_at` | yes | table/log drawer | persisted |
| work-item counts | integer | `gov_integration_sync_runs` | `work_items_total/succeeded/failed` | no | summary/log | persisted counts |
| record counts | integer | `gov_integration_sync_runs` | `records_seen/written` | no | log drawer | persisted counts |
| `errorCode` | string | `gov_integration_sync_runs` | `error_code` | yes | safe failure summary | stable safe code only |
| `dryRun` | boolean | none | none | yes | config detail | `null`; not available from the current read contract |
| retry interval/notification fields | mixed | none | none | yes | disabled config form | `null`/empty; not available from the current read contract |

## 5. Error and redaction contract

Stable errors include `UNAUTHORIZED`, `FORBIDDEN`, `DATA_SCOPE_DENIED`, `NOT_FOUND`,
`VALIDATION_ERROR`, `IDEMPOTENCY_CONFLICT`, `TASK_DISPATCH_UNAVAILABLE`, and `INTERNAL_ERROR`.
Third-party text is never forwarded.

Responses and UI messages never contain RAW/payload content, request bodies, product values,
credentials, Token values, signatures, or authorization headers. The frontend shows only safe
governance metadata, counts, stable error codes, and timestamps.

## 6. ProductInfo relationship

The ProductInfo executor is a controlled write pipeline: after all production gates pass, it may
persist ODS references, ProductInfo DWD snapshot/current/images/source tags, the DWS base profile,
and the identity SKU code. This task API only reads the resulting governance run/config/interface
metadata. Neither this API nor its page invokes ProductInfo outbound execution.

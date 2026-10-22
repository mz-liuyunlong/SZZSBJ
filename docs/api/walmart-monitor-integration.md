# Walmart Monitor RAW Ingestion API

## 1. Boundary

This endpoint receives one complete `walmart-monitor.raw.v1` logical-check event and appends
it to the isolated L2 RAW table `raw_walmart_monitor_events`. One event may contain Decodo,
Chrome Extension, and fallback attempts. It does not parse or write Listing, Product, GPT,
archive, ODS, MART, or any existing business table.

- Method: `POST`
- URL: `/api/integrations/walmart-monitor/raw-events`
- OpenAPI operation: `ingestWalmartMonitorRawEvent`
- Source: Walmart Product Status monitor producer outbox
- Source table: none on the receiving side
- Target table: `raw_walmart_monitor_events`
- Read/write: append-only RAW write
- Audit: event envelope, canonical payload hash, received time; API errors carry the common request ID
- Risk: high-sensitivity ingestion; there is no RAW read endpoint in this version

Merging the code does not authorize production migration, deployment, token configuration,
historical import, or live monitor delivery.

## 2. Authentication, permission, and data scope

The route requires a dedicated bearer secret injected through the deployment secret reference
`WALMART_MONITOR_INGEST_TOKEN`. The configured value must be at least 32 ASCII characters,
is represented as `SecretStr`, and is never returned or logged.

The token resolves only for the exact POST path above to machine principal
`walmart-monitor-service` with one permission:

```text
integrations:walmart-monitor:write
```

It cannot access Task Center, other integration routes, business pages, or RAW reads. Data scope
is the producer-bound append-only event: every target must provide non-empty opaque
`source_account_ref + store_id + item_id`; the receiver does not infer or broaden these IDs.

Required headers:

```text
Authorization: Bearer <secret_ref>
Idempotency-Key: <exact event_id from the body>
Content-Type: application/json
```

## 3. Request contract

| Field | Rule |
|---|---|
| `schema_version` | exactly `walmart-monitor.raw.v1` |
| `event_id` | canonical non-empty string, max 200; equals `Idempotency-Key` |
| `captured_at` | ISO-8601 datetime with an explicit offset |
| `requested_provider` | producer-requested provider/mode, preserved as source text |
| `producer` | `instance_id`, `check_id`, optional `run_id` |
| `targets` | 1–100; stable opaque keys plus optional source descriptors and category |
| `attempts` | 1–20 with unique `attempt_no`; each attempt keeps provider/outcome/artifacts |
| `final_observation` | final outcome and parsed snapshot; stored as RAW evidence only |

Each `source_payloads[]` item contains `kind`, `content_type`, `compression="gzip"`,
`sha256`, uncompressed `byte_size`, compressed `stored_byte_size`, and `data_base64`.
The receiver validates base64, gzip, declared sizes, bounded decompression, and SHA-256 before
writing any row. One compressed artifact is limited to 10 MiB and one uncompressed artifact
to 25 MiB; one attempt accepts at most 10 artifacts.

Optional target descriptors include `store_name`, `sku`, `msku`, `owner`, `product_name`,
`product_category`, and `wfs_inventory`. They remain inside RAW and are not promoted to
Listing fields by this endpoint. `monitoring_eligible` records the source-system value captured with the observation; both `true` and `false` are accepted so a late result is not discarded when eligibility changes after it was queued.

## 4. Idempotency and transaction behavior

The service canonicalizes the validated JSON and computes SHA-256. PostgreSQL uses an atomic
`ON CONFLICT (event_id) DO NOTHING` boundary:

- first valid event: one row is committed and `duplicate=false`;
- same `event_id` and same canonical hash: no new row, `duplicate=true`;
- same `event_id` and different hash: `409 MONITOR_EVENT_CONFLICT`;
- any artifact or database failure: the request transaction rolls back and no partial event is
  saved.

## 5. Response

Success status is `201` using the common envelope:

```json
{
  "success": true,
  "data": {
    "id": "00000000-0000-4000-8000-000000000001",
    "event_id": "walmart-monitor:synthetic-instance:check:1",
    "accepted": true,
    "duplicate": false,
    "received_at": "2026-01-15T00:00:00Z"
  },
  "error": null,
  "meta": null,
  "request_id": "synthetic-request-id"
}
```

The response never includes target identifiers, parsed results, compressed artifacts, URLs,
payloads, or credentials.

## 6. Errors

| HTTP | Error code | Meaning |
|---:|---|---|
| 401 | `UNAUTHORIZED` | token missing, invalid, unconfigured, or used outside its exact path |
| 403 | `FORBIDDEN` | principal lacks the machine write permission |
| 409 | `MONITOR_EVENT_CONFLICT` | same event ID was already stored with different content |
| 413 | `MONITOR_RAW_PAYLOAD_TOO_LARGE` | compressed or decompressed artifact exceeds its bound |
| 422 | `VALIDATION_ERROR` | request schema is invalid |
| 422 | `MONITOR_IDEMPOTENCY_KEY_INVALID` | header does not equal body event ID |
| 422 | `MONITOR_RAW_PAYLOAD_INVALID` | base64/gzip/size/hash integrity check failed |

All failures use `{ success, data, error, meta, request_id }` and do not echo rejected values.

## 7. Deferred work

The product-source target GET API and monitor producer/outbox have local implementations in
separate worktrees, but they are not part of this RAW receiver PR and have not been merged,
deployed, or connected to this endpoint. Live delivery and historical replay remain separate
production authorizations. RAW parser, ODS/current/history projections, Listing fields, Celery
reprocessing, retention automation, and object storage require separate Source Decisions/PRPs
and approvals.

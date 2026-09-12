# PRP: Integration Sync Governance + Lingxing SKU Detail Foundation V1

```text
Status: Implemented in PR #61 — Production ProductList Follow-on Authorized
Owner Approval Required: Completed for the 2026-09-13 ProductList-only production sync gate
Original Foundation Implementation: Implemented in PR #61, merge commit e8bc130
Production ProductList Follow-on Implementation Authorized: Yes, only on feat/production-lingxing-productlist-sync after a separate implementation prompt
Main Implementation Role After Approval: Backend Engineer
Frontend Implementation: Forbidden in this scope
ProductList and Required Token Requests: Authorized only by docs/decisions/2026-09-13-production-lingxing-productlist-sync-source-decision.md
batchGetProductInfo or Other Lingxing Requests: Forbidden
Source Decision Gate: APPROVED_BY_OWNER_DECISION
Source Decisions: docs/decisions/2026-09-12-integration-sync-governance-backend-v1-source-decision.md; docs/decisions/2026-09-13-production-lingxing-productlist-sync-source-decision.md
```

## 1. Goal

Build one backend-only foundation for governed external-interface synchronization and the first Lingxing SKU-detail pipeline. This is not a standalone ProductList feature. It establishes reusable PostgreSQL, Alembic, RAW/ODS, DWD, DWS, run governance, import, task-orchestration, and protected FastAPI contracts that later Lingxing, Walmart, Amazon, and TEMU integrations can reuse.

PR #61 implemented the original foundation without production migration or real provider requests. The 2026-09-13 Source Decision now authorizes a separate ProductList-only follow-on implementation and controlled server execution against `APPLICATION_DATABASE`; it does not authorize `batchGetProductInfo`, other Lingxing interfaces, automatic scheduling, frontend work, or server-side development outside a merged PR.

### 1.1 Authorized implementation deliverables

1. PostgreSQL/Alembic structures for integration governance.
2. Ten governance tables.
3. Four RAW/ODS tables.
4. Five DWD Lingxing SKU tables.
5. One DWS reusable SKU profile table.
6. A local ProductLists RAW importer.
7. The mapping `productList.data.id -> lingxing_sku_id`.
8. A disabled-by-default `batchGetProductInfo` ID-batch handler foundation.
9. Celery and scheduler backend contracts using the project's existing Celery dependency.
10. Protected FastAPI contracts for the integration sync center and SKU detail reads.
11. Backend-only tests and API/module documentation.

## 2. Why

The current repository has a Lingxing Token Manager, a readonly client, ProductLists query signing, and one controlled local ProductLists RAW capture. It does not yet have a reusable run model, concurrency guard, RAW deduplication, parsing/lineage model, retention policy, SKU identity index, detail snapshots, shared calculations, scheduler contract, or metadata-only operational API.

Without one governed foundation, each future provider or endpoint would otherwise invent its own run states, retry behavior, RAW shape, lineage, and safety rules. This PRP creates one backend pattern while keeping source-specific parsing and identity rules explicit.

## 3. Completed evidence and non-authority boundary

One controlled ProductLists full local RAW capture has completed.

| Item | Sanitized evidence |
|---|---|
| Validation run | `lingxing_product_list_20260911T195715Z_636b2f7d` |
| Local run directory | `/Users/sakura/Desktop/YC-System/local-raw-captures/lingxing/productList/lingxing_product_list_20260911T195715Z_636b2f7d` |
| Pages written | `2` |
| Provider total | `1188` |
| Total captured | `1188` |
| Stop reason | `total_reached` |
| Database written | No |
| Business tables written | No |
| Redis written | No |
| Secrets/full response/product values printed | No |

The local RAW directory is evidence for an explicitly authorized local PostgreSQL import only. It must not enter Git, be copied into repository fixtures, or be printed. This PRP was authored without reading `pages/*.json`.

Evidence paths:

- `PRPs/lingxing-product-list-controlled-validation.md`
- `docs/integrations/lingxing-product-list-endpoint-evidence.md`
- `docs/integrations/lingxing-query-sign-auth-evidence.md`
- `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv`
- `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv`
- `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv`
- `backend/app/integrations/lingxing/client.py`
- `backend/app/integrations/lingxing/query_sign.py`
- `backend/app/integrations/lingxing/token_manager.py`

The controlled capture proves only that the recorded ProductLists run completed for its account scope. It does not prove batchGetProductInfo interoperability, store-level scope, cadence, long-term freshness, field completeness, or business authority for every proposed detail field.

## 4. Scope

### 4.1 Approved implementation scope

- The exact twenty tables in sections 8–11 and their Alembic revisions.
- Synchronous SQLAlchemy 2.x models/repositories using the existing single `Base` and sessionmaker.
- Service-owned transactions; repositories must not commit or roll back.
- One local ProductLists RAW importer with manifest/checksum verification.
- ProductLists identity extraction and full-success active/inactive reconciliation.
- A parser and mock-only handler foundation for `batchGetProductInfo`.
- DWS calculations specified in section 11.
- Celery task signatures and scheduler service contracts without a required live worker.
- The exact protected API paths in section 16.
- Synthetic fixtures, mock transport tests, and optional explicitly authorized local PostgreSQL validation.
- Minimal backend API Markdown documentation and required registry/catalog updates.

### 4.2 Explicitly out of scope

- Any frontend or `admin-frontend` implementation.
- Any `old-system/**` read, import, runtime dependency, or modification.
- Real Lingxing/Token/business API requests other than the ProductList-only follow-on explicitly authorized by the 2026-09-13 Source Decision; `batchGetProductInfo` remains prohibited.
- Server database connection, migration or deployment outside the exact `APPLICATION_DATABASE` preconditions and post-merge manual execution authorized by the 2026-09-13 Source Decision.
- RAW artifacts, real response payloads, or business identifiers in Git/tests/docs/logs.
- Redis persistence validation or starting a live Celery worker/beat process.
- RQ or a second job system.
- Product master overwrite, Product Management CRUD changes, automatic identity matching by SKU, or dual writes.
- Walmart/Amazon/TEMU source-specific handlers; V1 only makes the governance tables reusable.
- Full historical backfill execution, continuous schedule activation, archive transport, or physical RAW deletion.
- ADS/page tables. V1 contains no page-specific computed fields; a measured need requires a separate PRP.
- AI features, notifications, exports, dashboards, or SOP/frontend help content.

## 5. Source Decision and approval gate

The original foundation decision and the ProductList-only follow-on decision are recorded in:

```text
docs/decisions/2026-09-12-integration-sync-governance-backend-v1-source-decision.md
docs/decisions/2026-09-13-production-lingxing-productlist-sync-source-decision.md
```

The first decision authorized the foundation implemented in PR #61 without real provider calls. The second decision authorizes `feat/production-lingxing-productlist-sync` to implement and, only after merge to `main`, execute the ProductList-only formal server path. All other real Lingxing interfaces, including `batchGetProductInfo`, remain prohibited.

| Dataset/field group | Proposed authority/classification | Rule |
|---|---|---|
| Governance configs, runs, locks, events, work items, parse jobs, lineage | `NEW_SYSTEM_OWNED` | Written only by approved backend services; no external system may overwrite governance state. |
| ProductLists local capture files | L1/L2 evidence; `ARCHIVE_ONLY` as local artifacts | Import source only; never an online API source and never committed. |
| ProductLists identities | Lingxing external source; `REBUILD_SYNC` | Imported/synchronized into new-system ODS and L6 identity records before API use. |
| ProductLists formal server sync | Lingxing external source; `REBUILD_SYNC` | May write credential-redacted RAW/request evidence, governed run/work-item state, ProductList SKU refs and identity upserts only to `APPLICATION_DATABASE`, with manual trigger and `schedule_enabled=false`. |
| batchGetProductInfo detail fields | Lingxing external source; `REBUILD_SYNC` implementation foundation | Only skeleton/mock/fixture parsing and `id_batch_page` work-item infrastructure are approved. Real calls and unverified provider parameters remain blocked pending separate official evidence and Owner authorization. |
| DWS values | New-system derived projection | Rebuildable from approved DWD snapshots using versioned formulas; never independent authority. |
| Existing `products` and `product_platform_listings` | Existing `NEW_SYSTEM_OWNED` authority | No overwrite from Lingxing. A link requires explicit identity evidence; SKU string equality is not sufficient. |

Implementation stop conditions:

- The requested implementation differs from this PRP or the linked Source Decision.
- Any real Lingxing or Token request outside the ProductList-only 2026-09-13 authorization is required.
- Any implementation requires credentials in code/Git/output, captured RAW artifacts in Git, database access outside `APPLICATION_DATABASE`, frontend/admin-frontend, or old-system access.
- A migration, identity, currency, data-scope, or provider contract conflicts with the linked Source Decision.

## 6. Mandatory business rules

1. `productList.data.id` is the Lingxing SKU-grain unique ID and is named `lingxing_sku_id` in this scope.
2. `batchGetProductInfo.data.sku` is the SKU code and is named `lingxing_sku_code`; it is not the identity key.
3. batchGetProductInfo reads active `lingxing_sku_id` values from `dwd_lingxing_sku_identity_index`.
4. batchGetProductInfo uses bounded ID batches; it must not send all IDs in one request.
5. ProductLists uses `request_kind=offset_page`.
6. batchGetProductInfo uses `request_kind=id_batch_page`.
7. Every successful source response is persisted to RAW before parsing to DWD. A DWD transaction must reference an existing RAW request reference.
8. Cross-module computed fields are persisted in DWS. APIs must not recalculate them from RAW/DWD per request.
9. Page-only fields belong in ADS. V1 creates no ADS table because no page-only field is approved.
10. APIs perform permission/data-scope checks, filters, deterministic sorting, pagination, and light formatting only.
11. Manual, schedule, retry, backfill, and import triggers use the same `gov_integration_sync_runs` and execution service boundary.
12. At most one run with `status=running` may exist for one `provider + interface_key`, regardless of source account.
13. RAW payloads require retention policy, content hashing, archive metadata, and storage-mode state; main-database storage is not indefinite by default.
14. Original V1 implementation made no real Lingxing or Token request. The separate 2026-09-13 authorization permits only ProductList and its required Token flow after the follow-on code is merged; every other endpoint remains fail closed.
15. IDs are opaque strings; SKU, MSKU, ItemID, Lingxing SKU ID, Lingxing SKU code, internal product ID, and listing ID must never be inferred from one another.
16. All timestamps are timezone-aware UTC. Source timestamps remain separate from ingestion timestamps.
17. All monetary values use `Numeric(18,4)`/`Decimal` and a currency companion field. No conversion or assumed currency is allowed. `purchase_cost_cny` has companion `CNY`; `customs_declared_currency` remains nullable and is `NULL` when the provider supplies no currency; US first-leg currency comes only from `data.product_logistics_relation.US_currency`.

## 7. Layering, naming, and transaction architecture

| Physical group | Project layer/control | Role and authority |
|---|---|---|
| `gov_*` | Cross-layer governance plus L12 audit/lineage | New-system operational control state; not business truth. |
| `ods_api_raw_blobs` | L2 RAW | Immutable/replayable response evidence after credential redaction; not an online API source. |
| Other `ods_*` | L1/L3 staging references | Typed request/identity evidence linked to RAW; not business authority. |
| `dwd_lingxing_sku_identity_index` | L6 Identity | Source identity index and optional audited link to internal product identity. |
| Other `dwd_*` | L3 standardized source snapshots/current projection | Typed Lingxing source representation; not allowed to overwrite new-system-owned Product Core. |
| `dws_sku_base_profile_current` | L9 reusable read projection | Versioned, rebuildable calculations for multiple backend modules. |

The Owner-approved Source Decision establishes `gov_`, `ods_`, `dwd_`, `dws_`, and `ads_` as this project's data-layer prefixes. The names and layer mapping above are approved project design, not ad hoc naming exceptions.

All tables use the existing SQLAlchemy `Base`. UUID primary keys are generated by the application unless a table explicitly uses an ordered bigint event key. All instants use `DateTime(timezone=True)`. JSON uses PostgreSQL JSONB. Enumerations are persisted as bounded strings with check constraints so migrations remain explicit.

Transaction boundary:

- Route/task/CLI creates a service use case with an injected session.
- The service owns begin/commit/rollback and state transitions.
- Repositories may add, flush, lock, and query, but must never commit/rollback or create an engine.
- RAW insert/reference creation and each corresponding parse publication are atomic at the service boundary.
- External HTTP, when separately approved in the future, occurs outside long database transactions.

## 8. Governance tables

Shared enums:

| Enum | Allowed values |
|---|---|
| `trigger_type` | `manual`, `schedule`, `retry`, `backfill`, `import` |
| `run_status` | `queued`, `running`, `succeeded`, `failed`, `canceled` |
| `request_kind` | `offset_page`, `id_batch_page` |
| `dependency_type` | V1: `requires_sku_ids` |
| `work_item_status` / `parse_status` | `queued`, `running`, `succeeded`, `failed`, `canceled` |
| `storage_mode` | `database`, `archive` |

The generic background-task vocabulary uses `pending/cancelled/partial_success`. This module's persisted contract uses the Owner-required values above: adapter `pending -> queued`, `cancelled -> canceled`; V1 has no `partial_success` run status. Any partial item failure makes the run `failed` while counts and events retain partial progress.

### 8.1 `gov_integration_interfaces`

- Purpose: stable registry of an approved provider interface and its handler contract.
- Core fields: `id UUID PK`, `provider varchar(32)`, `interface_key varchar(128)`, `display_name varchar(255)`, `method varchar(10)`, `endpoint_path text`, `request_kind varchar(32)`, `handler_key varchar(128)`, `contract_version varchar(64)`, `outbound_enabled boolean default false`, `created_at`, `updated_at`.
- Constraints: unique `(provider, interface_key)`; unique `(provider, method, endpoint_path)`; method V1 is `POST`; request kind uses the shared enum.
- Relations: source/target of dependencies; parent of sync configs and runs.
- Security: no base URL, credential, Token, signing input, or header. `outbound_enabled` defaults false and cannot itself authorize a real call.

### 8.2 `gov_integration_interface_dependencies`

- Purpose: declare data dependencies between source interfaces without embedding them in handler code.
- Core fields: `id UUID PK`, `source_interface_id FK`, `target_interface_id FK`, `dependency_key varchar(128)`, `dependency_type varchar(64)`, `is_required boolean`, `created_at`.
- Required row: source `productList`, target `batchGetProductInfo`, `dependency_key=lingxing_sku_id`, `dependency_type=requires_sku_ids`.
- Constraints: unique `(source_interface_id, target_interface_id, dependency_type, dependency_key)`; source and target must differ.
- Relations: both FKs reference `gov_integration_interfaces` with restricted deletion.
- Security: metadata only; it never stores source values or credentials.

### 8.3 `gov_integration_sync_configs`

- Purpose: new-system-owned schedule and safe execution configuration per interface/account reference.
- Core fields: `id UUID PK`, `interface_id FK`, `source_account_ref varchar(128)`, `is_enabled boolean`, `schedule_enabled boolean`, `schedule_cron varchar(128) nullable`, `schedule_timezone varchar(64) default 'UTC'`, `page_size integer nullable`, `batch_size integer nullable`, `max_pages integer nullable`, `max_attempts integer`, `retention_policy_id FK nullable`, `next_run_at timestamptz nullable`, `last_scheduled_at timestamptz nullable`, `created_at`, `updated_at`.
- Constraints: unique `(interface_id, source_account_ref)`; positive bounded page/batch/max values; a schedule requires cron and UTC timezone in V1.
- Relations: interface, retention policy, and many runs.
- Security: `source_account_ref` is an opaque non-secret identifier. No secret values, secret files, URLs with query strings, auth headers, or arbitrary JSON config are permitted. Credentials remain behind `secret_ref` outside these tables.

### 8.4 `gov_integration_sync_runs`

- Purpose: canonical execution record shared by every trigger path.
- Core fields: `id UUID PK`, `config_id FK nullable`, `interface_id FK`, duplicated immutable `provider`, `interface_key`, `source_account_ref`, `trigger_type`, `status`, `parent_run_id FK nullable`, `retry_of_run_id FK nullable`, `idempotency_key varchar(255)`, `requested_by varchar(255) nullable`, `request_id varchar(128) nullable`, `reason text nullable`, `window_start`, `window_end`, `queued_at`, `started_at`, `finished_at`, `work_items_total`, `work_items_succeeded`, `work_items_failed`, `records_seen`, `records_written`, `error_code varchar(128) nullable`, `error_message text nullable`, `created_at`.
- Constraints: unique `idempotency_key`; partial unique `(provider, interface_key) WHERE status='running'`; nonnegative counters; valid time ordering; retry rows reference their source run.
- Relations: parent/config/interface, events, lock, work items, parse jobs, lineage.
- Security: errors/reasons are sanitized and length-bounded; no raw payload, item ID list, secret, URL, header, or auth query. `requested_by` is actor identity for audit, not a role name.

### 8.5 `gov_integration_sync_run_events`

- Purpose: append-only state/event history for audit and troubleshooting.
- Core fields: `id bigint identity PK`, `run_id FK`, `sequence_no integer`, `event_type varchar(64)`, `from_status nullable`, `to_status nullable`, `message_code varchar(128)`, `safe_details JSONB nullable`, `occurred_at`, `actor_ref nullable`.
- Constraints: unique `(run_id, sequence_no)`; statuses bounded when present.
- Relations: belongs to one run.
- Security: immutable after insert; `safe_details` has an allowlist and may contain counts/codes only, never request/response bodies, IDs, secrets, URLs, or headers.

### 8.6 `gov_integration_sync_locks`

- Purpose: leased concurrency guard for one running provider/interface.
- Core fields: `id UUID PK`, `provider`, `interface_key`, `run_id FK`, `lock_token_hash char(64)`, `acquired_at`, `heartbeat_at`, `expires_at`, `created_at`.
- Constraints: unique `(provider, interface_key)` and unique `run_id`; SHA-256 length check; `expires_at > acquired_at`.
- Relations: exactly one owning run; deletion is explicit on release/expiry recovery.
- Security: only a hash of an in-memory lease token is persisted. The raw lease token is not logged or returned. Lock acquisition and queued-to-running transition occur in one transaction.

### 8.7 `gov_integration_sync_run_work_items`

- Purpose: durable unit of pagination/batching, retry, progress, and RAW linkage.
- Core fields: `id UUID PK`, `run_id FK`, `ordinal integer`, `request_kind`, `status`, `attempt_count`, `offset_value integer nullable`, `length_value integer nullable`, `batch_no integer nullable`, `id_count integer nullable`, `id_hash char(64) nullable`, `request_safe_params JSONB`, `response_count integer nullable`, `error_code nullable`, `error_message nullable`, `started_at`, `finished_at`, `created_at`.
- Constraints: unique `(run_id, ordinal)`; unique `(run_id, request_kind, offset_value)` for offset items; unique `(run_id, request_kind, batch_no)` for ID batches; kind-specific check constraints require only their allowed columns; positive counts/attempts.
- Relations: belongs to run; parent of RAW request refs and batch item membership.
- Security: `request_safe_params` is schema-validated and contains only `offset/length` or `batch_no/id_count/id_hash`; never the ID list, token, sign, Authorization, full URL, or payload.

### 8.8 `gov_raw_retention_policies`

- Purpose: explicit RAW hot-storage, archive, and deletion policy.
- Core fields: `id UUID PK`, `policy_key varchar(128)`, `provider nullable`, `interface_key nullable`, `hot_retention_days integer`, `archive_after_days integer nullable`, `delete_after_days integer nullable`, `archive_required boolean`, `legal_hold boolean`, `is_active boolean`, `created_at`, `updated_at`.
- Constraints: unique `policy_key`; unique nullable scope through an explicit coalesced unique index; nonnegative days; deletion cannot precede archive; archive-required policies require an archive threshold.
- Relations: referenced by configs and RAW blobs.
- Security: no archive credential or signed URI; only policy metadata. V1 does not implement archive transport or deletion.

### 8.9 `gov_parse_jobs`

- Purpose: idempotent parse/publication record from one RAW request reference to one parser version.
- Core fields: `id UUID PK`, `run_id FK`, `raw_request_ref_id FK`, `parser_key varchar(128)`, `parser_version varchar(64)`, `target_layer varchar(16)`, `status`, `records_seen`, `records_written`, `records_rejected`, `error_code`, `error_message`, `started_at`, `finished_at`, `created_at`.
- Constraints: unique `(raw_request_ref_id, parser_key, parser_version)`; nonnegative counters; target layer V1 is `DWD`.
- Relations: run/raw reference; parent of lineage entries.
- Security: parser errors are safe codes/messages; never persist offending raw values in error fields.

### 8.10 `gov_data_lineage`

- Purpose: field/record lineage from RAW references through DWD/DWS targets.
- Core fields: `id UUID PK`, `run_id FK`, `parse_job_id FK nullable`, `raw_request_ref_id FK`, `raw_blob_id FK`, `source_path varchar(512)`, `target_table varchar(128)`, `target_record_id varchar(128)`, `target_field varchar(128)`, `transform_key varchar(128)`, `transform_version varchar(64)`, `created_at`.
- Constraints: unique `(raw_request_ref_id, target_table, target_record_id, target_field, source_path, transform_version)`.
- Relations: run, parse job, RAW reference/blob, and logical target record.
- Security: metadata only. `source_path` is a JSON path, not a source value; APIs never expose the RAW payload through lineage.

## 9. RAW / ODS tables

### 9.1 `ods_api_raw_blobs`

- Purpose: hold the actual credential-redacted JSON response exactly once for replay/evidence.
- Core fields: `id UUID PK`, `response_hash char(64)`, `payload_json JSONB nullable`, `payload_bytes bigint`, `content_type varchar(128)`, `storage_mode`, `archive_uri text nullable`, `retention_policy_id FK`, `received_at`, `archived_at nullable`, `payload_deleted_at nullable`, `created_at`. Provider/interface/run context belongs to request refs so global hash deduplication cannot mislabel a shared blob.
- Hash: SHA-256 of deterministic UTF-8 canonical JSON after mandatory credential-key redaction, before any DWD transform.
- Constraints: unique `response_hash`; valid hash length; `database` requires `payload_json`; `archive` requires `archive_uri`; nonnegative byte count.
- Relations: referenced by request refs and lineage.
- Security: high sensitivity; default-deny read. Authentication query/header data is never part of the payload. `archive_uri` must be credential-free. The API layer may never serialize `payload_json`. If another reference to the same hash has a stricter retention/legal-hold requirement, the blob adopts the longer/stricter effective policy; deduplication must never shorten retention.

### 9.2 `ods_api_raw_request_refs`

- Purpose: map a request attempt/work item to a deduplicated RAW blob.
- Core fields: `id UUID PK`, `run_id FK`, `work_item_id FK`, `raw_blob_id FK`, `request_kind`, `attempt_no`, `request_safe_params JSONB`, `http_status nullable`, `provider_code nullable`, `is_success`, `response_count nullable`, `requested_at`, `received_at`, `created_at`.
- Constraints: unique `(work_item_id, attempt_no)`; safe-parameter schema must match request kind.
- Relations: run/work item/blob; parent of ProductLists SKU refs, parse jobs, and lineage.
- Security: metadata-only API surface; no payload, auth material, full URL, request body, or full external ID list.

### 9.3 `ods_lingxing_productlist_sku_refs`

- Purpose: typed identity references extracted from ProductLists RAW.
- Core fields: `id UUID PK`, `run_id FK`, `raw_request_ref_id FK`, `source_account_ref`, `lingxing_sku_id varchar(255)`, `source_item_ordinal integer`, `observed_at`, `created_at`.
- Constraints: unique `(raw_request_ref_id, source_item_ordinal)` and unique `(run_id, source_account_ref, lingxing_sku_id)`; nonblank opaque ID.
- Relations: ProductLists RAW reference and run; input to identity upsert.
- Security: business identifier, protected and never logged/listed by importer output. Duplicate IDs cause a DQ/import failure rather than silent collapse.

### 9.4 `ods_lingxing_product_info_batch_items`

- Purpose: freeze and audit every SKU ID assigned to one batchGetProductInfo work item.
- Core fields: `id UUID PK`, `run_id FK`, `work_item_id FK`, `source_account_ref`, `batch_no`, `item_ordinal`, `lingxing_sku_id`, `raw_request_ref_id FK nullable`, `item_status`, `created_at`, `updated_at`.
- Constraints: unique `(run_id, source_account_ref, lingxing_sku_id)` and `(work_item_id, item_ordinal)`; request kind of parent must be `id_batch_page`.
- Relations: run/work item, active identity source, optional completed RAW request reference.
- Security: the complete ID set is stored only in this protected table, never in `request_safe_params`, task arguments, logs, errors, or API responses.

## 10. DWD tables and field contract

### 10.1 `dwd_lingxing_sku_identity_index`

- Purpose: stable L6 index of Lingxing SKU identities and optional evidence-backed link to Product Core.
- Core fields: `id UUID PK` (the API `{sku_id}`), `provider default 'lingxing'`, `source_account_ref`, `lingxing_sku_id`, `lingxing_sku_code nullable`, `product_id UUID FK products.id nullable`, `mapping_status` (`unmapped`, `confirmed`), `mapping_evidence_ref nullable`, `is_active`, `first_seen_run_id FK`, `last_seen_run_id FK`, `first_seen_at`, `last_seen_at`, `inactive_at nullable`, `created_at`, `updated_at`.
- Constraints: unique `(provider, source_account_ref, lingxing_sku_id)`; a confirmed mapping requires both `product_id` and evidence; no uniqueness/inference on SKU code.
- Full-success reconciliation: IDs observed in the completed run are upserted with `is_active=true`; historical IDs in the same provider/account absent from a fully verified run become `is_active=false` and get `inactive_at`. Partial, failed, or unreconciled runs must never deactivate IDs. No physical deletion.
- Security: protected source identity. No automatic `lingxing_sku_code == products.sku` mapping.

### 10.2 Shared snapshot field dictionary

The field entries below are approved for skeleton/mock/fixture parsing and schema implementation. They do not prove the real batchGetProductInfo transport contract or authorize a provider call. Null means absent/unparseable under a recorded parser version; raw values remain only in RAW. Text is trimmed only where approved and case is preserved. Numeric parsing rejects invalid/negative physical or monetary values into DQ records rather than coercing them.

| Source path | Canonical column | PostgreSQL type / rule |
|---|---|---|
| `data.product_name` | `product_name` | `varchar(500) nullable` |
| `data.sku` | `lingxing_sku_code` | `varchar(255) nullable`; not an identity key |
| `data.pic_url` | `main_image_url` | `text nullable`; HTTPS/URL validation, never fetched by parser |
| `data.product_developer` | `product_developer_name` | `varchar(255) nullable` |
| `data.product_developer_uid` | `product_developer_uid` | `varchar(255) nullable`; external ID preserved as string |
| `data.cg_delivery` | `purchase_delivery_days` | `integer nullable`, nonnegative |
| `data.cg_price` | `purchase_cost_cny` | `numeric(18,4) nullable`, nonnegative; companion `purchase_cost_currency_code='CNY'` when present |
| `data.cg_product_material` | `purchase_material` | `text nullable` |
| `data.bg_customs_export_name` | `customs_export_name_cn` | `varchar(500) nullable` |
| `data.bg_customs_import_name` | `customs_import_name_en` | `varchar(500) nullable` |
| `data.bg_customs_import_price` | `customs_declared_unit_price` | `numeric(18,4) nullable`, nonnegative; companion `customs_declared_currency` is nullable and remains `NULL` when provider currency is absent |
| `data.bg_export_hs_code` | `china_hs_code` | `varchar(64) nullable`; preserve leading zeros |
| `data.permission_user_info.permission_uid` | `owner_uid` | `varchar(255) nullable`; sensitive staff identifier |
| `data.permission_user_info.permission_user_name` | `owner_name` | `varchar(255) nullable`; sensitive staff field |
| `data.clearance.customs_clearance_material` | `clearance_material_cn` | `text nullable` |
| `data.clearance.customs_clearance_usage` | `clearance_usage_cn` | `text nullable` |
| `data.clearance.customs_clearance_en_material` | `clearance_material_en` | `text nullable` |
| `data.product_logistics_relation.US_cg_transport_costs` | `us_first_leg_cost` | `numeric(18,4) nullable`, nonnegative |
| `data.product_logistics_relation.US_currency` | `us_first_leg_currency` | `char(3) nullable`, uppercase; required with cost |
| `data.cg_product_length` | `product_length_cm` | `numeric(18,4) nullable`, nonnegative |
| `data.cg_product_width` | `product_width_cm` | `numeric(18,4) nullable`, nonnegative |
| `data.cg_product_height` | `product_height_cm` | `numeric(18,4) nullable`, nonnegative |
| `data.cg_product_net_weight` | `product_net_weight_g` | `numeric(18,4) nullable`, nonnegative |
| `data.cg_package_length` | `package_length_cm` | `numeric(18,4) nullable`, nonnegative |
| `data.cg_package_width` | `package_width_cm` | `numeric(18,4) nullable`, nonnegative |
| `data.cg_package_height` | `package_height_cm` | `numeric(18,4) nullable`, nonnegative |
| `data.cg_box_length` | `box_length_cm` | `numeric(18,4) nullable`, nonnegative |
| `data.cg_box_width` | `box_width_cm` | `numeric(18,4) nullable`, nonnegative |
| `data.cg_box_height` | `box_height_cm` | `numeric(18,4) nullable`, nonnegative |
| `data.cg_box_pcs` | `box_pcs` | `integer nullable`, nonnegative |
| `data.cg_product_gross_weight` | `product_gross_weight_g` | `numeric(18,4) nullable`, nonnegative |
| `data.cg_box_weight` | `box_weight_kg` | `numeric(18,4) nullable`, nonnegative |

`customs_declared_unit_price` is parsed from `data.bg_customs_import_price`. Its companion `customs_declared_currency` is nullable; when the provider does not return a currency, the amount may be stored with currency `NULL` and must not be labeled or converted. No FX conversion is in V1.

The fixture parser must validate its declared cardinality and nesting before mapping. If `permission_user_info` contains multiple owners, or the logistics object/list contains multiple US candidates, V1 must not silently choose one; the parse job fails that record or leaves the affected standardized fields null. Real response cardinality and nesting remain subject to future official evidence before any real call.

### 10.3 `dwd_lingxing_sku_product_info_snapshots`

- Purpose: immutable successful parsed detail snapshot per SKU/run.
- Core fields: `id UUID PK`, `provider`, `source_account_ref`, `identity_id FK`, `lingxing_sku_id`, `source_run_id FK`, `source_raw_request_ref_id FK`, `parser_version`, all shared snapshot columns above plus `purchase_cost_currency_code`, nullable `customs_declared_currency`, `source_observed_at`, `created_at`.
- Constraints: unique `(source_run_id, source_account_ref, lingxing_sku_id)`; monetary fields follow the explicit currency rules above, including nullable `customs_declared_currency`; nonnegative physical values; all source IDs are strings.
- Relations: identity/run/RAW reference; parent of images/tags; source of current and DWS.
- Security: costs and staff fields require field permissions; no endpoint returns all columns by default.

### 10.4 `dwd_lingxing_sku_product_info_current`

- Purpose: replaceable current projection for bounded online reads without scanning snapshot history.
- Core fields: `id UUID PK`, `provider`, `source_account_ref`, `identity_id FK`, `lingxing_sku_id`, `source_snapshot_id FK`, `source_run_id FK`, all shared snapshot columns and currency companions, `source_observed_at`, `updated_at`.
- Constraints: unique `(provider, source_account_ref, lingxing_sku_id)` and unique `source_snapshot_id`; same value constraints as snapshots.
- Publication: in the same service transaction as successful snapshot publication, upsert only if the incoming snapshot is not older than current. Failed/partial parses never replace current.
- Security: protected repository access only; never direct RAW fallback.

### 10.5 `dwd_lingxing_sku_product_images`

- Purpose: normalize `picture_list` into ordered snapshot children.
- Core fields: `id UUID PK`, `source_snapshot_id FK`, `identity_id FK`, `ordinal`, `pic_url text`, `is_primary boolean nullable`, `created_at`.
- Constraints: unique `(source_snapshot_id, ordinal)`; at most one primary image per snapshot via partial unique index; URL validation.
- Relations: snapshot and identity.
- Security: URL is returned only through protected SKU detail; parser never downloads it.

### 10.6 `dwd_lingxing_sku_global_tags`

- Purpose: normalize `global_tags` into ordered snapshot children.
- Core fields: `id UUID PK`, `source_snapshot_id FK`, `identity_id FK`, `ordinal`, `global_tag_id varchar(255) nullable`, `tag_name varchar(255) nullable`, `color varchar(64) nullable`, `created_at`.
- Constraints: unique `(source_snapshot_id, ordinal)`; optional unique `(source_snapshot_id, global_tag_id)` when ID is present.
- Relations: snapshot and identity.
- Security: metadata only; no tag is treated as a role, permission, or identity mapping.

## 11. DWS reusable profile

### 11.1 `dws_sku_base_profile_current`

- Purpose: persist cross-module SKU calculations so APIs never compute them per request.
- Grain: one current row per `(provider, source_account_ref, lingxing_sku_id)`.
- Keys/lineage: `id UUID PK`, `identity_id FK`, `provider`, `source_account_ref`, `lingxing_sku_id`, `source_run_id FK`, `source_snapshot_id FK`, `calc_version varchar(64)`, `calculated_at`, `created_at`, `updated_at`; unique grain and unique source snapshot.
- Types: volumes, weights, and cost values use `Numeric(18,4)`; currency companions use `char(3)`; `has_*` fields use boolean; `data_quality_score` uses `Numeric(5,2)`; `missing_fields_json` is a JSONB string array; IDs are UUID/string as declared and times are UTC timestamptz.

| Column | V1 calculation |
|---|---|
| `product_volume_cm3` | `product_length_cm * product_width_cm * product_height_cm`; null if any input is null |
| `package_volume_cm3` | `package_length_cm * package_width_cm * package_height_cm`; null if any input is null |
| `box_volume_cm3` | `box_length_cm * box_width_cm * box_height_cm`; null if any input is null |
| `box_volume_cbm` | `box_volume_cm3 / 1000000`; null when box volume is null |
| `product_net_weight_kg` | `product_net_weight_g / 1000` |
| `product_gross_weight_kg` | `product_gross_weight_g / 1000` |
| `unit_box_weight_kg` | `box_weight_kg / box_pcs` only when `box_pcs > 0`; otherwise null |
| `purchase_cost_cny` | Copy of approved snapshot value, not a new calculation |
| `us_first_leg_cost` | Copy of approved snapshot value with its currency companion retained |
| `unit_first_leg_cost` | `us_first_leg_cost / box_pcs` only when `box_pcs > 0`; same currency as `us_first_leg_cost` |
| `has_customs_info` | True when at least one customs text/code or a valid declared price is present; missing nullable customs currency remains a separate completeness flag and is never inferred |
| `has_package_info` | True only when all three package dimensions are positive |
| `has_logistics_info` | True only when a valid US first-leg cost/currency pair is present |
| `missing_fields_json` | Sorted JSON array of missing V1 completeness-check field keys; never contains values |
| `data_quality_score` | `round(100 * present_checks / 23, 2)` using the fixed V1 checks below; a completeness indicator, not a business-quality guarantee |

The 23 V1 completeness checks are: product name; SKU code; purchase delivery; purchase cost/CNY pair; material; customs CN name; customs EN name; customs declared price with nullable currency recorded separately; China HS code; product length/width/height; product net/gross weight; package length/width/height; box length/width/height; box pieces; box weight; US first-leg cost/currency pair. `calc_version` is required and any formula/checklist change requires a new version and rebuild plan.

All arithmetic uses Decimal, rejects negative inputs, uses a documented half-up four-decimal quantization only at persistence, and converts numeric overflow into a failed parse/calculation event. The table also stores `purchase_cost_currency_code`, `us_first_leg_currency`, and `unit_first_leg_currency`; monetary values never appear without currency.

## 12. Local ProductLists RAW importer

### 12.1 Input and command boundary

Primary environment input:

```text
LINGXING_PRODUCTLIST_RAW_RUN_DIR
```

Default local directory:

```text
/Users/sakura/Desktop/YC-System/local-raw-captures/lingxing/productList/lingxing_product_list_20260911T195715Z_636b2f7d
```

The implementation provides a backend CLI/module entrypoint, not an API upload endpoint. It also requires an Owner-approved, opaque, non-secret `source_account_ref` argument or existing sync-config selection. It must not derive account identity from App ID, Token, a secret, or payload values.

### 12.2 Validation and import sequence

1. Resolve the directory and reject symlinks/path traversal or a directory inside the Git worktree.
2. Read `manifest.json` without printing it.
3. Parse `checksums.sha256`, validate allowed relative paths, and verify every listed file before reading page JSON.
4. Reject missing/extra pages, duplicate filenames, checksum mismatch, invalid JSON, unexpected run ID, unsafe sizes, or pagination gaps.
5. Confirm manifest/page metadata reconciles to `pages_written=2`, `total_captured=1188`, provider total `1188`, and `stopped_reason=total_reached` for the recorded capture. Counts may be printed; item values may not.
6. Create/finalize one `gov_integration_sync_runs` record with `provider=lingxing`, `interface_key=productList`, `trigger_type=import`; final status is `succeeded`. Record queued/running/succeeded events through the common service.
7. Create one `offset_page` work item per page with safe `offset/length` metadata.
8. Canonicalize credential-redacted response JSON, calculate SHA-256, and insert or reuse `ods_api_raw_blobs` by `response_hash`.
9. Create `ods_api_raw_request_refs` for each page/work item.
10. Parse only `response_json.data[*].id` as nonblank `lingxing_sku_id`; never print it.
11. Write `ods_lingxing_productlist_sku_refs` and upsert the identity index.
12. Only after complete count/pagination reconciliation, mark previously active IDs absent from this full run inactive.
13. Commit through the service. On failure, do not publish partial DWD current state; retain a sanitized failed run/event when transaction boundaries permit.
14. Output only run ID, counts, hashes count, status, timings, and safe error code. No RAW, product field, source ID, secret, Token, sign, Authorization, or full path containing credentials.

The importer must not request Lingxing or Token, connect to Redis, call a business endpoint, or write Product Core. If `DATABASE_URL` is missing, the implementation must still import and test safely as code, skip the live import without failure, and report `LIVE_IMPORT_SKIPPED_DATABASE_URL_MISSING`. It must not construct a fallback database URL.

## 13. batchGetProductInfo foundation

Implementation class contract:

```text
LingxingBatchGetProductInfoSyncHandler
```

Rules:

1. The handler is registered to `provider=lingxing`, `interface_key=batchGetProductInfo`, `request_kind=id_batch_page`.
2. Real outbound execution remains disabled in interface metadata/config and transport settings.
3. At run start, query active identity rows for the authorized `source_account_ref`, sort deterministically by `lingxing_sku_id`, and freeze membership in `ods_lingxing_product_info_batch_items`.
4. Split IDs by a positive bounded implementation default. No real request parameter shape or provider batch limit is asserted in V1; those require later official evidence and Owner authorization.
5. Create one work item per batch. Safe params are exactly `batch_no`, `id_count`, and SHA-256 `id_hash` over the ordered length-delimited ID set.
6. The full ID list exists only in the protected batch-items table and transient outbound body. It never enters Celery arguments, safe params, logs, events, errors, or API responses.
7. When a future call is separately authorized, persist the response in RAW, create the request reference, attach it to batch items, then run the versioned parser.
8. Parser fixtures cover the exact field dictionary, `picture_list`, and `global_tags`; fixtures are synthetic and contain no captured business values.
9. The implementation task must not toggle real-call or Token-request defaults and must not make a real request.

## 14. Sync run service, Celery, and scheduler contracts

### 14.1 Common execution path

```text
API / scheduler / retry / backfill / importer
  -> SyncRunService.create_run(...)
  -> enqueue or invoke execute_sync_run(run_id)
  -> acquire provider+interface lock
  -> handler builds durable work items
  -> RAW-first execution / parsing / publication
  -> counters + events + terminal status
  -> release lock
```

### 14.2 Task signatures

```python
execute_sync_run(run_id: str) -> None
scheduler_tick() -> None
```

Celery arguments contain only `run_id`. The task must reload config and authorization-safe metadata from PostgreSQL. It does not accept secrets, ID lists, payloads, URLs, or user-supplied arbitrary JSON.

- `execute_sync_run`: idempotently claims a queued run, acquires the concurrency lock, selects the registered handler, updates durable events/counters, applies bounded retry policy, and releases/recovers the lease in `finally` semantics.
- `scheduler_tick`: selects due enabled configs using a bounded batch and row locking/skip-locked behavior, creates schedule-triggered runs with deterministic idempotency keys, updates `next_run_at`, and enqueues only their IDs.
- Manual, retry, backfill, and import paths create the same run model. Retry links `retry_of_run_id`; backfill records a bounded UTC window; import invokes the same service locally and need not enqueue.
- The database unique constraint is the final enforcement for one running provider/interface; a lock conflict leaves the later run queued or safely fails with `SYNC_RUN_ALREADY_RUNNING` according to trigger contract.
- Retry is bounded and applies to work items; no infinite loop. Provider success, RAW success, parse success, and run success remain separate states/events.

V1 tests use Celery eager mode, mocks, or service-level calls. They do not start Redis, a real worker, or beat. The project already locks Celery/Redis dependencies; no dependency change or RQ is allowed.

## 15. Permissions, data scope, and sensitive fields

No role names are hard-coded. Every endpoint requires a trusted `Principal` and the listed permission. A module-level source-account scope resolver must fail closed until a trusted provider returns the allowed opaque `source_account_ref` values; frontend hiding is never security.

| Capability | Permission key | Scope/field rule |
|---|---|---|
| Read interfaces/configs/runs/work items | `integrations:read` | Only allowed source-account refs; interface catalog without account data may be global. |
| Update safe sync config | `integrations:update` | Allowed account only; audited diff; cannot change credentials or enable real calls. |
| Manual/retry/backfill run | `integrations:execute` | Allowed account; reason/request ID audit; real outbound remains disabled. |
| Read RAW reference metadata | `integrations:raw_metadata:read` | Metadata only; never blob payload/archive credential. |
| Read SKU list/detail/listings | `products:read` | Allowed source-account refs; listing read also uses existing Product scope after confirmed mapping. |
| Read sync history | `products:sync_history:read` | Allowed source account; metadata only. |
| Read RAW lineage | `products:raw_lineage:read` | Metadata only; never source values/payload. |
| Read cost history | `products:cost:read` | Sensitive costs and currency pairs; access should be audited. |
| Read operation logs | `products:operation_logs:read` | Sanitized sync/parse events only. |

Sensitive fields include purchase/customs/logistics costs, staff UID/name, source-account refs, external SKU identifiers, RAW/archive metadata, and lineage. Responses must not log them. V1 performs no manual write to source-derived fields and no field-level masking substitute for permission denial.

## 16. FastAPI API contract

All routes use the existing envelope:

```json
{
  "success": true,
  "data": {},
  "error": null,
  "meta": {},
  "request_id": "generated-or-accepted-request-id"
}
```

Error responses use the existing unified error envelope. All query/body schemas set `extra='forbid'`. Pagination is `page >= 1`, `1 <= page_size <= 100`, deterministic order with ID tie-breaker. No route makes an external call or performs long work inline; write-trigger routes return `202` with run metadata.

Every route declares an explicit Pydantic `response_model`, standard 401/403/404/409/422/500/503 OpenAPI error models as applicable, and an operation ID. Read `meta` contains only `source='new_system_postgresql'`, the approved logical source objects, pagination when applicable, and a freshness timestamp derived from persisted run/snapshot/calculation times. It never claims real-time freshness or exposes storage connection details.

The exact routes below follow the existing project `/api/...` convention approved by the Owner for this module. V1 does not force a new `/v1` prefix; any future project-wide versioning change requires a separate PRP decision.

### 16.1 Integration sync center APIs

| Method/path | Request contract | Response `data` | Permission / effects |
|---|---|---|---|
| `GET /api/integrations/interfaces` | Query: `provider?`, `enabled?`, `page`, `page_size` | Items: ID, provider, interface key/name, method, request kind, contract version, outbound-enabled flag; page metadata | `integrations:read`; no endpoint secrets/base URL |
| `GET /api/integrations/sync-configs` | Query: `provider?`, `interface_key?`, `enabled?`, `page`, `page_size` | Safe config fields, schedule state, next/last times, retention policy ID | `integrations:read`; account-scoped |
| `PATCH /api/integrations/sync-configs/{id}` | Body allowlist: `is_enabled`, `schedule_enabled`, `schedule_cron`, `page_size`, `batch_size`, `max_pages`, `max_attempts`, `retention_policy_id` | Updated safe config | `integrations:update`; audit event; cannot enable external transport or change credential/account/interface |
| `POST /api/integrations/sync-configs/{id}/run` | Body: `reason` required, `idempotency_key?` | `run_id`, trigger `manual`, status `queued` | `integrations:execute`; `202`; disabled interface returns conflict |
| `POST /api/integrations/sync-runs/{id}/retry` | Body: `reason` required, `idempotency_key?` | New `run_id`, `retry_of_run_id`, trigger `retry`, status `queued` | `integrations:execute`; only failed/canceled source run; `202` |
| `POST /api/integrations/sync-configs/{id}/backfill` | Body: UTC `window_start`, `window_end`, `reason`, `idempotency_key?` | New `run_id`, trigger `backfill`, status `queued` | `integrations:execute`; bounded/validated window; `202` |
| `GET /api/integrations/sync-runs` | Query: `provider?`, `interface_key?`, `status?`, `trigger_type?`, `created_from?`, `created_to?`, `page`, `page_size` | Sanitized run summaries and counters | `integrations:read`; account-scoped |
| `GET /api/integrations/sync-runs/{id}` | Path ID only | Sanitized run metadata, counters, safe error code/message, timestamps | `integrations:read`; account-scoped |
| `GET /api/integrations/sync-runs/{id}/work-items` | Query: `status?`, `request_kind?`, `page`, `page_size` | Work-item metadata and safe params | `integrations:read`; no ID list/payload |
| `GET /api/integrations/sync-runs/{id}/raw-request-refs` | Query: `page`, `page_size` | Ref/blob IDs, request kind, safe params, statuses, hashes, byte count, storage mode, credential-free archive presence, timestamps | `integrations:raw_metadata:read`; explicitly excludes `payload_json` and archive URI value |

### 16.2 SKU backend APIs

`{sku_id}` is the internal UUID primary key of `dwd_lingxing_sku_identity_index`, not a Lingxing ID or SKU code.

| Method/path | Request contract | Response `data` | Permission / source |
|---|---|---|---|
| `GET /api/products/skus` | Query: `provider=lingxing`, `active?`, `mapping_status?`, `page`, `page_size`; fixed sort `lingxing_sku_code NULLS LAST, sku_id` | Items: internal `sku_id`, SKU code nullable, product name nullable, active/mapping status, last-seen/snapshot/calculated timestamps; page metadata | `products:read`; DWD current + DWS; account-scoped |
| `GET /api/products/skus/{sku_id}/detail` | Path only | Identity metadata; approved non-cost DWD fields; images/tags; DWS dimensions/weights/flags/score/missing keys; cost block only with `products:cost:read` | `products:read`; no RAW fallback or request-time calculation |
| `GET /api/products/skus/{sku_id}/sync-history` | Query: `page`, `page_size` | Sanitized runs, work-item status, snapshot IDs/times/parser versions | `products:sync_history:read`; metadata only |
| `GET /api/products/skus/{sku_id}/raw-lineage` | Query: `page`, `page_size` | Lineage IDs, source JSON paths, blob/ref hashes/IDs, target field, transform version, storage mode/times | `products:raw_lineage:read`; no payload/value/archive URI |
| `GET /api/products/skus/{sku_id}/platform-listings` | Query: `page`, `page_size` | Existing approved listing response subset for confirmed `product_id`; empty list plus mapping state when unmapped | `products:read` plus existing Product scope; no SKU-string inference |
| `GET /api/products/skus/{sku_id}/cost-history` | Query: `page`, `page_size` | Snapshot time, purchase CNY amount/currency, customs amount/currency when approved, US first-leg amount/currency, source run/snapshot IDs | `products:cost:read`; sensitive, audited; no FX calculation |
| `GET /api/products/skus/{sku_id}/operation-logs` | Query: `event_type?`, `page`, `page_size` | Sanitized run/parse event code, status transition, actor ref, request ID, timestamp | `products:operation_logs:read`; V1 sync operations only |

List/detail contracts are approved for implementation against persisted new-system projections and synthetic fixtures. This approval does not authorize real provider calls or treat fixture mappings as verified provider evidence. Owner staff fields remain excluded from V1 default responses.

### 16.3 Errors and audit

| HTTP | Error code | Meaning |
|---|---|---|
| 401 | `UNAUTHORIZED` | No trusted principal |
| 403 | `FORBIDDEN` / `DATA_SCOPE_DENIED` | Permission or account/product scope denied |
| 404 | `NOT_FOUND` | Config/run/SKU not visible or absent |
| 409 | `SYNC_RUN_ALREADY_RUNNING` | Provider/interface lock conflict |
| 409 | `SYNC_INTERFACE_DISABLED` | Real/scheduled execution is disabled |
| 409 | `SYNC_RUN_NOT_RETRYABLE` | Source run state is not retryable |
| 422 | `VALIDATION_ERROR` | Invalid filters, schedule, safe config, range, or pagination |
| 500 | `INTERNAL_ERROR` | Safe generic failure |
| 503 | `TASK_DISPATCH_UNAVAILABLE` | Queue dispatch unavailable; run remains durably recoverable |

Config updates and trigger actions write audit/run events with actor, reason, request ID, safe before/after field names, and timestamps. They never record secret values, raw payload, external ID lists, or auth material.

## 17. Proposed implementation structure

The implementation should use the existing module patterns and keep orchestration thin:

```text
backend/app/modules/integration_sync/
  models.py
  schemas.py
  repository.py
  service.py
  router.py
  dependencies.py
  handlers/base.py
  handlers/lingxing_product_list_import.py
  handlers/lingxing_batch_product_info.py
  parsers/lingxing_product_list.py
  parsers/lingxing_product_info.py
  tasks.py
  scheduler.py
  importer.py

backend/app/modules/sku_detail/
  models.py
  schemas.py
  repository.py
  service.py
  router.py
  calculations.py
```

Four ordered Alembic revisions are preferred for independent review and reverse dependency order:

1. Governance tables.
2. RAW/ODS tables.
3. DWD tables.
4. DWS table.

Each revision needs upgrade/downgrade, explicit FKs/indexes/checks, offline-head validation, lock/performance notes, and reverse-order rollback. No migration seeds credentials or business values. Interface bootstrap metadata uses an idempotent application service or a separately reviewed safe metadata migration; implementation must choose one and document it before execution.

The existing `raw_lingxing_api` table is not dropped, rewritten, or dual-written by V1. New governed flows use `ods_api_raw_blobs` and references. Reconciliation/deprecation of the older table requires a separate migration/retention decision.

## 18. Data quality, freshness, retention, and rollback

### 18.1 Data quality gates

- Manifest/page/checksum/count reconciliation before identity deactivation.
- Nonblank string identity; duplicate IDs fail the import/run.
- Work-item response count and provider total reconciliation.
- Strict typed parser with rejected counts and safe error codes.
- Money/currency pair, units, nonnegative values, URL shape, primary-image uniqueness.
- Parser/schema drift fails parsing without replacing DWD current/DWS.
- DWS calculations are deterministic by `calc_version` and covered by Decimal tests.

No dataset may be described as fresh or complete solely because one capture succeeded. APIs expose `last_seen_at`, `source_observed_at`, `calculated_at`, and run status separately; no fabricated freshness SLA is included.

### 18.2 Retention

- RAW blob metadata/hash/lineage remains after payload archival according to policy.
- V1 supports `database` and `archive` state but does not implement archive transport/deletion.
- A future retention executor must verify archive checksum before clearing database payload and must honor legal hold.
- DWD snapshots are append-only history in V1; current/DWS are rebuildable.
- Governance events/lineage are audit evidence and cannot be casually deleted.

### 18.3 Rollback

- Disable configs/scheduler and revoke task dispatch before schema rollback.
- Drain/cancel queued work; no new running run may exist.
- Roll back API/router/task code, then DWS, DWD, ODS, and governance migrations in reverse order only on a non-production authorized environment.
- Preserve/export required RAW hashes and audit evidence before destructive downgrade.
- Rebuild current/DWS from snapshots/RAW when calculation or parser code is reverted.
- Never fall back to legacy MySQL or query local RAW files from the online API.

## 19. Test and validation plan

The future backend implementation must cover at least:

1. All Alembic upgrades/downgrades execute on an explicitly approved disposable PostgreSQL database; offline heads load without a connection.
2. All new models import into the single SQLAlchemy metadata.
3. Local RAW manifest/path/checksum validation, including tamper/missing/extra/path-traversal cases.
4. ProductLists RAW import with a small synthetic fixture.
5. Exact `productList.data.id -> lingxing_sku_id` parsing without logging values.
6. Identity upsert, full-success active/inactive reconciliation, and no deactivation on partial/failure.
7. Deterministic batchGetProductInfo ID freeze/split/work-item generation.
8. `request_safe_params` contains no full ID list, token, sign, Authorization, full URL, or payload.
9. DWD detail parser maps every section-10 field from a synthetic fixture and safely rejects invalid types/currency pairs.
10. `picture_list` writes image children with ordering/primary constraints.
11. `global_tags` writes tag children with ordering/deduplication.
12. DWS product/package/box volumes, g-to-kg conversions, box-unit weight, first-leg allocation, null/zero/rounding/overflow behavior.
13. Concurrent lock conflict and stale-lease recovery without two running provider/interface runs.
14. `manual`, `schedule`, `retry`, `backfill`, and `import` trigger paths create the same run model with the correct trigger type.
15. Every API response model excludes `payload_json`; serialization regression test searches nested output.
16. RAW-lineage returns metadata only and never raw/source values or archive URI credentials.

Also cover: permission/data-scope fail closed, cost field permission, repository no commit/rollback, service transaction failure, idempotency keys, scheduler duplicate tick, task arguments containing only run ID, API validation/404/409/503 envelopes, `/health` DB independence, no external transport call, and no Redis requirement in tests.

Required validation commands, adjusted only after reading the implementation branch config:

```bash
cd backend
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy app tests
uv run pytest -q -rs
uv run alembic -c alembic.ini heads
git diff --check
```

The implementation report must list any PostgreSQL integration/live importer test as `Not run` with reason when no explicitly approved `TEST_DATABASE_URL`/local `DATABASE_URL` exists. It must perform targeted secret and scope scans without printing environment values.

## 20. Implementation phases and atomic PR boundary

This is intentionally a broad but single backend foundation because governance/run IDs, RAW references, parsing, lineage, and the first read contracts must share one schema contract. The implementation remains independently rollbackable from frontend and provider activation.

1. Implement governance models/migration/repositories and lock/run services.
2. Implement ODS migrations and RAW/reference safety.
3. Implement DWD/DWS models, parsers, calculations, and migrations.
4. Implement and test the local importer; run live import only with separate authorization and local PostgreSQL.
5. Implement disabled batch handler foundation and mock parser tests.
6. Implement Celery/scheduler contracts in eager/mock-safe mode.
7. Implement protected API schemas/services/routers and Markdown API docs.
8. Update registries/catalog, run full validation, and provide handoff.

Do not split out an incomplete API that reads RAW directly. If implementation cannot complete the full accepted contract safely, stop and return to the Owner rather than declaring a partial capability ready.

## 21. Acceptance checklist for the original PR #61 implementation

The checklist below records the completed foundation implementation boundary. It is not the acceptance checklist for the separately authorized formal server ProductList work in Section 24.

- [ ] No files under `frontend/**` or `admin-frontend/**` are modified.
- [ ] No files under `old-system/**` are read or modified.
- [ ] No real Lingxing business request is made.
- [ ] No real Token request is made.
- [ ] Approved Alembic migrations execute in an authorized disposable environment and offline heads load.
- [ ] Backend format, lint, type, and test suites pass, with unavailable integration validation reported honestly.
- [ ] With an explicitly authorized local PostgreSQL URL, the importer can verify/import the recorded capture and reconcile `total_captured=1188` without printing product values.
- [ ] When `DATABASE_URL` is absent, live import is safely skipped rather than failing implementation validation or using a fallback URL.
- [ ] No API returns RAW payload JSON, raw product values, credentials, full external ID batches, or credential-bearing archive URLs.
- [ ] Targeted secret scan passes.
- [ ] `git diff --check` passes.

Approval gates:

- [x] The Owner Source Decision is recorded and the implementation gate is approved.
- [x] The data-layer prefixes and existing project `/api/...` path convention are approved.
- [x] The Owner implementation branch and PRP allowlist are identified as `feat/integration-sync-governance-backend-v1` and this PRP.
- [x] Original V1 local RAW import implementation and confirmed-local-PostgreSQL validation were approved without server database access; the later ProductList-only `APPLICATION_DATABASE` authorization is governed separately by the 2026-09-13 Source Decision.

## 22. Forbidden actions

- Treating this approval as authorization for any real external request other than the exact ProductList-only follow-on in the 2026-09-13 Source Decision.
- Reading/printing/committing the captured RAW pages or archives during PRP work.
- Real Lingxing/Token requests in PR #61, tests, or any endpoint outside the post-merge ProductList-only controlled execution.
- Enabling real calls, full sync, schedules, Redis workers, or production migrations by default.
- Putting credentials, auth query/header data, external ID lists, RAW payloads, or product values in logs/events/API/errors/Celery arguments.
- Querying RAW directly from a business API.
- Inferring internal Product identity from SKU code or overwriting Product Core.
- Adding ADS/frontend/provider-specific scope beyond this PRP.
- Git add/commit/push without a later explicit Owner instruction.

## 23. Owner decisions resolved for implementation

1. The linked Source Decision approves the `REBUILD_SYNC`, `NEW_SYSTEM_OWNED`, and `ARCHIVE_ONLY` classifications for this PRP.
2. `gov_`, `ods_`, `dwd_`, `dws_`, and `ads_` are approved project data-layer prefixes.
3. The exact `/api/integrations` and `/api/products/skus` paths are approved under the existing project `/api/...` convention; no `/v1` prefix is forced in this module.
4. `source_account_ref` is an opaque non-secret logical account identifier. Local import may use `default`; protected APIs still fail closed until their trusted account-scope provider supplies allowed refs.
5. batchGetProductInfo is approved only as skeleton/mock/fixture parser and `id_batch_page` work-item foundation. Real parameters, limits, retry/rate behavior, Token use, and provider calls require later official evidence and separate Owner authorization.
6. `data.bg_customs_import_price` maps to `customs_declared_unit_price`; nullable `customs_declared_currency` remains `NULL` when provider currency is absent. `purchase_cost_cny` is CNY and US first-leg currency comes only from `data.product_logistics_relation.US_currency`.
7. The original local RAW importer validation did not authorize server database access. The 2026-09-13 Source Decision separately authorizes `alembic upgrade head` and ProductList-only writes to `APPLICATION_DATABASE` after the follow-on implementation is merged.

The original backend foundation was implemented in PR #61. The next implementation may begin only on `feat/production-lingxing-productlist-sync`, after a separate Owner prompt, and within section 24 plus the 2026-09-13 Source Decision. It must not commit RAW artifacts, modify frontend/admin-frontend or old-system, enable schedules, call `batchGetProductInfo` or other Lingxing endpoints, or continue when requirements diverge from the approved boundary.

## 24. Production ProductList follow-on authorization

The Project Owner authorizes the next phase to implement and, after its code PR is merged to `main`, execute the formal server ProductList sync described in `docs/decisions/2026-09-13-production-lingxing-productlist-sync-source-decision.md`.

Authorized database and write boundary:

- Formal application database name: `APPLICATION_DATABASE`; it is not named or classified as a `test`, `staging`, `dev`, or `prod` database.
- `alembic upgrade head` may run only after target verification, backup/snapshot confirmation and deployment from merged `main`.
- ProductList response RAW may write only to `ods_api_raw_blobs`.
- Safe ProductList request metadata may write only to `ods_api_raw_request_refs`.
- Run/work-item state may write only to `gov_integration_sync_runs` and `gov_integration_sync_run_work_items`.
- `productList.data.id` / response `data.id` may write as `lingxing_sku_id` to `ods_lingxing_productlist_sku_refs` and be idempotently upserted to `dwd_lingxing_sku_identity_index`.
- The first execution is manual only and requires `schedule_enabled=false`.

The follow-on must preserve credential/query redaction, bounded pagination/retry/limiting, run/work-item idempotency and RAW-before-parse ordering. It must not print or commit RAW/product values, write the legacy `raw_lingxing_api`, connect to legacy MySQL, call any non-ProductList endpoint, or activate automatic scheduling. After the first run it must reconcile `total_captured`, `raw_blobs_count`, `request_refs_count` and `sku_identity_active_count`; a ProductList total mismatch blocks all further real-interface expansion.

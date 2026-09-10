# Product Management Backend MVP PRP

```text
Status: Approved
Owner Approval Required: Completed
Implementation Authorized: Yes, after this docs PR is merged and the owner issues the implementation Prompt
Main Execution Role: Backend Engineer
Source Decision: docs/data-sources/decisions/products-basic-information-query-decision.md
Source Decision State: READY_FOR_PRP
```

## 1. Goal

Implement one Product Management backend feature package that owns manually maintained product master data and platform/store/MSKU relationships in the new-system PostgreSQL database.

The separately issued implementation Prompt may deliver the approved migration, SQLAlchemy models, Pydantic schemas, repository, service, FastAPI router, tests and required registry/catalog updates in one independently reviewable PR. This is one business module, not a multi-module or platform-integration PR.

## 2. Why

The current frontend product page is a no-API shell. The system needs a small authoritative backend contract for manual product maintenance before any external synchronization, old-system migration or derived analytics work.

This PRP deliberately establishes only the new-system-owned manual source. It does not copy the legacy schema or create an external ingestion path.

## 3. Prerequisites and Authority

- Backend API Foundation is already merged and remains authoritative for request IDs, envelopes, safe errors, authentication, permission dependencies and protected-by-default behavior.
- Data Layer Foundation is already merged and remains authoritative for PostgreSQL settings, SQLAlchemy Base/session injection, transaction boundaries and Alembic.
- The Source Decision is `READY_FOR_PRP` only for the exact scope in this PRP.
- The Project Owner has approved the field, grain, API and permission decisions recorded below.
- Approval does not authorize production database access, production migration execution, deployment or external API use.

## 4. In Scope

- One `products` core table and one `product_platform_listings` core table.
- One Alembic schema revision creating those tables, constraints and indexes.
- SQLAlchemy 2 models.
- Pydantic request and response schemas.
- A concrete products repository using an injected SQLAlchemy session.
- A products service owning validation orchestration and write transactions.
- One FastAPI router under `/api/v1/products`.
- Eight endpoints listed in section 9.
- Backend permission enforcement using the six approved keys.
- A product-module data-scope seam that fails closed until a trusted provider is supplied.
- Unit tests and bounded integration tests when an explicitly authorized disposable PostgreSQL test database is available.
- OpenAPI metadata and a Markdown API contract.
- Task, module and data-interface registry updates in the implementation PR.

## 5. Explicitly Out of Scope

- Frontend changes or connecting the no-API page to the backend.
- Excel, CSV or other import/export.
- Old-system data migration, backfill, reconciliation execution or runtime reads.
- Production database connection or migration execution.
- Legacy MySQL connectors or repositories.
- Walmart, Amazon, TEMU, Lingxing or Feishu API clients or synchronization.
- External source registry, RAW storage or ingestion work.
- Sales, advertising, inventory, profit, settlement or refund data/calculations.
- Price or fee calculation, WFS validation, FX conversion or financial reconciliation.
- Celery, Redis, workers, schedulers or background jobs.
- DELETE endpoints, restore, archive or purge workflows.
- Bulk create/update, direct SQL editing or file import.
- Full audit-event history or historical version rollback.
- Full RBAC or production data-scope provider integration.
- A normalized store table, cache, mart or read model.
- CI PostgreSQL provisioning.
- Dependency or lock-file changes.

## 6. Source and Ownership Contract

| Dataset | Grain | Classification | Runtime authority | Writer | Reader |
|---|---|---|---|---|---|
| `products` | One company-internal SKU product | `NEW_SYSTEM_OWNED` | New-system PostgreSQL core table | Product Management service only | Product Management repository/service/API |
| `product_platform_listings` | One product + platform + store name + MSKU relation | `NEW_SYSTEM_OWNED` | New-system PostgreSQL core table | Product Management service only | Product Management repository/service/API |

The approved manual-write exception permits these two core tables to be written without an upstream RAW layer. It does not apply to any external sync, import or migration. Future automated writers require a new Source Decision and must follow Source Registry -> RAW -> ingestion/standardization -> Core publication.

## 7. Database Contract

### 7.1 `products`

| Column | Type / nullability | Rule |
|---|---|---|
| `id` | UUID, PK, non-null | Server-generated new-system `product_id`; never derived from SKU or external IDs |
| `sku` | varchar(128), non-null | Trim outer whitespace, preserve case, reject blank, unique |
| `product_name` | varchar(255), non-null | Trim outer whitespace, reject blank |
| `category` | varchar(128), nullable | Manual free text; no external taxonomy claim |
| `product_type` | varchar(128), nullable | Manual free text; no lifecycle inference |
| `status` | varchar(64), nullable | Manual free text; not Walmart publish status |
| `grade` | varchar(64), nullable | Manual free text |
| `purchase_price` | Numeric(18,4), nullable | `Decimal`, non-negative, sensitive, no calculation |
| `currency_code` | varchar(3), nullable | Required when `purchase_price` is present; uppercase three-letter code; no inferred currency |
| `declared_cn_name` | varchar(255), nullable | Manual customs text |
| `declared_en_name` | varchar(255), nullable | Manual customs text |
| `material_cn` | varchar(255), nullable | Manual material text |
| `material_en` | varchar(255), nullable | Manual material text |
| `remark` | text, nullable | Manual note; no secret or external payload |
| `created_at` | timestamptz, non-null | UTC record creation instant |
| `updated_at` | timestamptz, non-null | UTC record update instant; not source freshness |
| `deleted_at` | timestamptz, nullable | Reserved; API never sets it in this MVP |

Required constraints and indexes:

- Primary key on `id`.
- Unique constraint on `sku`.
- Check requiring `purchase_price` and `currency_code` to be both null or both present.
- Check requiring `purchase_price >= 0` when present.
- Query-supporting indexes only where used by the approved list filters; no speculative indexes.

### 7.2 `product_platform_listings`

| Column | Type / nullability | Rule |
|---|---|---|
| `id` | UUID, PK, non-null | Server-generated listing-relation ID |
| `product_id` | UUID, FK, non-null | References `products.id`; deletion is not exposed |
| `platform` | varchar(32), non-null | One of `walmart`, `amazon`, `temu`, `other` |
| `store_name` | varchar(255), non-null | Trim outer whitespace, preserve business spelling, reject blank |
| `msku` | varchar(128), non-null | Trim outer whitespace, preserve case, reject blank |
| `external_listing_id` | varchar(255), nullable | External ID string; never internal ID |
| `listing_url` | varchar(2048), nullable | Display/reference URL only; backend never fetches it |
| `listing_status` | varchar(64), nullable | Manual free text; not a governed external status |
| `fulfillment_type` | varchar(64), nullable | Manual free text |
| `wfs_fee` | Numeric(18,4), nullable | `Decimal`, non-negative, sensitive, no calculation |
| `shipping_cost` | Numeric(18,4), nullable | `Decimal`, non-negative, sensitive, no calculation |
| `currency_code` | varchar(3), nullable | Required when either monetary field is present; no inferred currency |
| `created_at` | timestamptz, non-null | UTC record creation instant |
| `updated_at` | timestamptz, non-null | UTC record update instant; not external freshness |
| `deleted_at` | timestamptz, nullable | Reserved; API never sets it in this MVP |

Required constraints and indexes:

- Primary key on `id`.
- Foreign key from `product_id` to `products.id` with no cascade delete behavior exposed by this MVP.
- Unique constraint on `(platform, store_name, msku)`.
- Check constraint for the approved platform values.
- Checks requiring non-negative money and `currency_code` whenever either money field is present.
- Index on `product_id`; additional indexes only for approved list filters and stable ordering.

### 7.3 Common persistence rules

- UUIDs are new-system identifiers and are never accepted from external sources as authority.
- API and model validation reject unknown request fields.
- Monetary inputs allow at most four decimal places. Excess precision is rejected; no implicit business rounding is performed.
- `precision=18`, `scale=4`, and `rounding_rule=reject_excess_precision` are part of the contract metadata.
- Timestamps are timezone-aware UTC and cannot be supplied as mutable business fields.
- Normal queries exclude rows with non-null `deleted_at`; there is no delete or restore behavior.
- The migration must use the shared SQLAlchemy metadata naming convention and must be manually reviewed.

## 8. Layer Responsibilities

| Layer | Required responsibility | Forbidden responsibility |
|---|---|---|
| Router | Declare contract, validate transport input, require permission and scope dependencies, inject session, call service, return shared envelope | SQL, commit/rollback, external API, business branching |
| Service | Enforce use-case rules, coordinate repository, own successful write commit, map conflicts/not-found to safe API errors | Create engine, bypass permission/scope, return ORM objects as public contracts |
| Repository | Focused SQLAlchemy queries with injected session; document grain, indexes and no-commit boundary | Commit/rollback, auth/permission decisions, HTTP, external API, legacy MySQL |
| Schema | Exact request/response contract, null rules, safe validation and Decimal serialization | ORM leakage, secret fields, undocumented aliases |

No generic repository interface, transaction wrapper, CRUD framework or second API foundation is authorized.

## 9. API Contract

All endpoints use the existing `{ success, data, error, meta, request_id }` envelope and are protected by the existing trusted principal boundary.

### 9.1 Endpoint summary

| Method | Route | Purpose | Permission |
|---|---|---|---|
| GET | `/api/v1/products` | Server-paginated product list | `products:read` |
| GET | `/api/v1/products/{product_id}` | One product | `products:read` |
| POST | `/api/v1/products` | Create one product | `products:create` |
| PATCH | `/api/v1/products/{product_id}` | Update allowed product fields | `products:update` |
| GET | `/api/v1/products/options` | Approved static option values | `products:read` |
| GET | `/api/v1/products/{product_id}/listings` | Server-paginated listing relations | `product_listings:read` |
| POST | `/api/v1/products/{product_id}/listings` | Create one listing relation | `product_listings:create` |
| PATCH | `/api/v1/products/{product_id}/listings/{listing_id}` | Update allowed listing fields | `product_listings:update` |

The static `/api/v1/products/options` route must be declared so it cannot be captured by the `/{product_id}` route.

### 9.2 List contract

`GET /api/v1/products` query:

- `page`: integer, default `1`, minimum `1`.
- `page_size`: integer, default `20`, minimum `1`, maximum `100`.
- `sku`: optional exact/contains filter defined in the Markdown API doc; case is preserved.
- `product_name`: optional contains filter.
- `platform`, `store_name`, `msku`: optional relation filters using joined queries, never frontend full-data filtering.

Stable ordering is `sku ASC, id ASC`. Response data contains `items`, `total`, `page`, and `page_size`; each item uses the product response schema. No unbounded list endpoint is allowed.

`GET /api/v1/products/{product_id}/listings` uses the same bounded `page/page_size` contract and stable ordering `platform ASC, store_name ASC, msku ASC, id ASC`.

### 9.3 Detail and options contract

- Product detail returns one product only. Listing relations are fetched through the listings endpoint.
- Options returns only the approved static `platforms = [walmart, amazon, temu, other]` contract. Free-text manual attributes do not create speculative reference tables or unscoped distinct-value queries.

### 9.4 Write contract

- POST product requires `sku` and `product_name`; all other mutable product fields are optional.
- PATCH product requires at least one mutable field and cannot change `id`, timestamps or `deleted_at`.
- POST listing requires `platform`, `store_name` and `msku`; `product_id` comes from the path.
- PATCH listing requires at least one mutable field and cannot change `id`, `product_id`, timestamps or `deleted_at`.
- Writes operate on one resource per request. Bulk writes are prohibited.
- Duplicate SKU returns HTTP 409 with `PRODUCT_SKU_CONFLICT`.
- Duplicate `(platform, store_name, msku)` returns HTTP 409 with `LISTING_IDENTITY_CONFLICT`.
- Missing product/listing returns 404 using the existing safe error envelope.
- Validation errors remain 422; missing principal is 401; missing permission or denied scope is 403.
- Responses never expose ORM internals, connection data, SQL or exception text.

### 9.5 Schema inventory

| Schema | Contract |
|---|---|
| `ProductCreate` | `sku`, `product_name` required; all other mutable product fields optional; no ID/timestamps/`deleted_at` |
| `ProductUpdate` | At least one mutable product field; no ID/timestamps/`deleted_at`; SKU changes remain uniqueness-checked |
| `ProductRead` | `id`, all approved product business fields plus required currency companion and `created_at`/`updated_at`; omit reserved `deleted_at` |
| `ProductListData` | `items: list[ProductRead]`, `total`, `page`, `page_size` |
| `ProductOptionsData` | `platforms` containing exactly the four approved values |
| `ProductListingCreate` | `platform`, `store_name`, `msku` required; remaining mutable listing fields optional; `product_id` comes from path |
| `ProductListingUpdate` | At least one mutable listing field; no ID/product ID/timestamps/`deleted_at` |
| `ProductListingRead` | `id`, `product_id`, all approved listing business fields plus required currency companion and `created_at`/`updated_at`; omit reserved `deleted_at` |
| `ProductListingListData` | `items: list[ProductListingRead]`, `total`, `page`, `page_size` |

All public response types are wrapped in the existing generic `SuccessEnvelope`. Monetary JSON values are decimal strings, not binary floating-point numbers. Error responses use the existing `ErrorEnvelope`.

## 10. Permission, Data Scope and Sensitive Fields

Approved permission keys:

```text
products:read
products:create
products:update
product_listings:read
product_listings:create
product_listings:update
```

- Role names are never hardcoded.
- Product and listing read permissions cover all fields in their respective MVP response, including the approved monetary fields. This broad field boundary is owner-approved for this MVP; finer field permissions require a later permission PRP.
- Future resource data scope is based on `platform + store_name`.
- The shared `resolve_store_scope` helper is based on `store_id` and must not be relabeled or coerced into this contract.
- The Product module must expose one dependency/provider seam for product/listing scope. With no trusted provider, all Product Management endpoints fail closed with the shared data-scope error.
- Tests may override the trusted principal and scope dependencies with explicit synthetic values only.
- This PRP does not implement a role store, permission store, user store or full RBAC.
- Monetary values are confidential business data: logs and errors must not include their values, and no export endpoint exists.

## 11. Transaction and Concurrency Boundary

- One request uses one injected SQLAlchemy session.
- Repository methods flush when an ID or constraint result is needed but never commit.
- The service commits once after a successful write use case.
- Exceptions propagate to the shared session dependency for rollback and close.
- Database unique constraints are authoritative for race-safe identity enforcement; pre-checks may improve messages but cannot replace constraints.
- Integrity conflicts are converted to stable safe API errors without leaking SQL or values.
- Read-only requests never commit.

## 12. Migration Plan

The implementation PR may create exactly one Alembic revision:

1. Create `products` with the approved fields, checks, unique constraint and indexes.
2. Create `product_platform_listings` with the approved fields, FK, checks, unique constraint and indexes.
3. Downgrade drops `product_platform_listings` before `products`.

The revision contains schema only: no seed data, no legacy copy, no data migration and no raw SQL unless Alembic requires a narrowly justified dialect operation. Autogenerate output must be reviewed line by line.

Creating the migration file is authorized. Applying it to production, staging, development or any existing database is not authorized by this PRP. Execution against a disposable test PostgreSQL database requires explicit authorization and `APP_ENV=test` plus `TEST_DATABASE_URL` supplied outside Git.

## 13. Test Plan

Required unit/contract coverage:

- Both model grains, relationships, metadata, UTC timestamps and reserved `deleted_at` behavior.
- Required, nullable, length, platform enum, Decimal scale and currency-pair validation.
- SKU and listing identity conflicts.
- Repository query filters, stable pagination/order and exclusion of soft-deleted rows.
- Repository never commits; service commits successful writes and allows rollback on failure.
- All eight routes, response models, status codes and shared envelopes.
- 401 without principal, 403 without permission, and 403/fail-closed without trusted product scope.
- Synthetic dependency overrides verify allowed scope paths without real auth infrastructure.
- No external network, legacy MySQL, secret, production data or direct database fallback.
- `/health` remains public and database-independent.
- Application import does not connect to a database.
- OpenAPI schema contains the eight routes and exact response models even if the runtime docs endpoint remains governed separately.

PostgreSQL integration coverage, when explicitly authorized on a disposable test database:

- Upgrade and downgrade of the single revision.
- Database constraints, FK and uniqueness behavior.
- One create/read/update flow for each table with synthetic fixtures only.
- Transaction rollback isolation.

If `TEST_DATABASE_URL` is absent, integration tests must skip with an explicit reason and must never fall back to another URL. The implementation may not claim PostgreSQL integration tests passed when they were skipped.

## 14. Documentation and Registry Updates

The implementation PR must:

- Add `docs/api/product-management-backend-mvp.md` with endpoint, request, response, errors, permissions, scope, source and examples containing synthetic values only.
- Update `docs/tasks/TASK_REGISTRY.md` with real implementation branch/PR/validation state.
- Update `docs/BACKEND_MODULE_CATALOG.md` from `approved` to `implemented` only after merge evidence exists.
- Update the eight API entries and two storage entries in `docs/data-registry/DATA_INTERFACE_REGISTRY.md` from `approved` to `implemented` only after merge evidence exists.
- Keep external interface and sync registries empty for this MVP.

OpenAPI metadata must be present in code. Exposing the API documentation UI to users remains governed by the existing API-doc permission and deployment boundary; this PR must not create a second docs application.

## 15. Candidate Implementation Allowlist

The separate implementation Prompt must convert this list to an exact allowlist:

```text
backend/alembic/env.py
backend/alembic/versions/<one-revision>_add_product_management_tables.py
backend/app/main.py
backend/app/modules/products/__init__.py
backend/app/modules/products/dependencies.py
backend/app/modules/products/models.py
backend/app/modules/products/schemas.py
backend/app/modules/products/repository.py
backend/app/modules/products/service.py
backend/app/modules/products/router.py
backend/tests/modules/products/__init__.py
backend/tests/modules/products/test_models.py
backend/tests/modules/products/test_repository.py
backend/tests/modules/products/test_service.py
backend/tests/modules/products/test_router.py
backend/tests/test_health.py
docs/api/product-management-backend-mvp.md
docs/tasks/TASK_REGISTRY.md
docs/BACKEND_MODULE_CATALOG.md
docs/data-registry/DATA_INTERFACE_REGISTRY.md
```

Do not modify dependency manifests, lock files, environment files, shared API/auth/permission/data-scope foundation, frontend, old-system, CI or deployment configuration. A needed file outside the final allowlist is a stop condition.

## 16. Validation Gates for the Implementation PR

The implementation engineer must inspect existing commands before running them and must report facts, not predictions.

```bash
cd backend
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy app tests
uv run pytest -q
uv run python -c "import app.main"
uv run alembic -c alembic.ini heads
cd ..
bash scripts/check-rule-pack.sh
git diff --check
git status --short --untracked-files=all
git diff --stat
```

Additional required review:

- Exact file-scope review.
- No real secret, connection URL, identifier or business sample.
- No external client, legacy connector, worker, import/export or read model.
- No `.only`, `.skip` added to ordinary tests, or global timeout inflation.
- Any PostgreSQL integration skip is reported explicitly.
- Migration upgrade/downgrade is not run unless a disposable test database is separately authorized.

## 17. Acceptance Criteria

- The two tables and one migration match the exact approved grain and field boundaries.
- Every monetary value uses `Decimal`/`Numeric(18,4)`, has `currency_code`, and has no implicit calculation or FX behavior.
- The eight routes use `/api/v1/products`, shared envelopes, explicit response models and stable safe errors.
- Every route requires the approved permission and the product scope seam; missing trusted scope fails closed.
- List endpoints use server-side pagination, filters, stable order and relevant indexes.
- Repository/service/router responsibilities and transaction ownership match the Data Layer Foundation.
- There is no direct database write path outside the service.
- No DELETE, bulk import, external API, legacy runtime dependency, mart/read model, worker or frontend work exists.
- Tests cover the contract and security boundaries without real data or external calls.
- API documentation and all required registries/catalogs are aligned.
- Validation is factual and the final diff is within the implementation allowlist.

## 18. Rollback Boundary

Before production use, the implementation PR can be reverted as one unit: remove the router/module/tests/docs and downgrade the single schema revision only in an explicitly authorized non-production environment. Production migration execution and rollback require separate approval, backup/restore planning and operator control.

Because this MVP contains no seed, migration or external sync, code rollback does not imply data migration. If records exist in an environment, destructive downgrade requires separate owner authorization and verified backup; it must not be automated by the implementation PR.

## 19. Stop Conditions

Stop and request owner/architect direction if implementation requires:

- a third table, normalized store model, mart or read model;
- any field or endpoint outside this PRP;
- direct database editing, import, delete, archive or bulk operations;
- legacy MySQL, external API, background task or migration/backfill source;
- full RBAC, a non-fail-closed scope shortcut or changes to shared security foundations;
- permission keys other than the six approved keys;
- real database credentials, production/staging migration, CI PostgreSQL or deployment;
- a dependency/lock-file change;
- a destructive or data migration;
- a file outside the implementation Prompt allowlist.

## 20. Agent Role and Skill Boundary

Main execution role: Backend Engineer.

Allowed working modes when assigned by the implementation Prompt:

- `engineering-minimal-change-engineer` for the smallest complete feature package.
- `engineering-backend-architect` for FastAPI/SQLAlchemy boundaries.
- `engineering-technical-writer` for API and registry alignment.
- `testing-api-tester` for in-process synthetic API contract tests only.
- `testing-evidence-collector` for reproducible validation evidence.
- `engineering-database-optimizer` for static query/index review only unless a separate database-access authorization exists.

Agent Skills are work modes, not people or permission grants. They cannot widen the allowlist, connect to a database, run migrations, call external APIs, deploy or perform Git write operations.

## 21. Owner Approval Record

```text
Approved by: Project Owner
Approved date: 2026-09-10
Approval type: implementation authorization
Approval scope: Product Management Backend MVP only
```

Approval authorizes one later implementation PR containing migration, models, schemas, repository, service, router, tests and registry/catalog updates. It does not authorize implementation in this docs branch, Git publishing by an engineer, database connection, migration execution, external APIs, deployment or any future scope.

The Project Owner must merge this docs PR and issue the separate implementation Prompt with the implementation worktree, branch and exact file allowlist before code work begins.

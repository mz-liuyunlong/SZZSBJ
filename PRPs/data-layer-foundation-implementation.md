# Data Layer Foundation Implementation

Status: Draft
Owner Approval Required: Yes
Implementation Allowed: No until the owner changes Status to Approved and issues a separate implementation prompt
Database Access Authorized: No
Migration Execution Authorized: No
Production Access Authorized: No

## 1. Authorization Boundary

This PRP is an implementation plan, not implementation authorization.

This authoring task may create only this PRP. It does not authorize database or server connections, SQL execution, migration creation or execution, ORM models, business tables, production configuration, secrets, backend code, frontend code, external API calls, background jobs, or data movement.

Approval of this PRP permits only a later, separately approved implementation PR for the database foundation described here. That implementation must use a new branch based on the latest clean `main`, remain independently reviewable and reversible, and stay within an owner-approved file allowlist.

The future implementation may establish reusable database infrastructure and conventions. It must not implement any business data model.

## 2. Current Project Baseline

The current `main` baseline includes:

- Backend API Foundation.
- Data Governance Catalog.
- the approved Data Platform Foundation PRP.
- legacy runtime decision alignment.
- remaining legacy runtime example alignment.

The backend currently has FastAPI application and API-foundation modules under `backend/app/`, with synchronous route handlers and no database dependency in `/health`.

The existing dependency manifest already declares:

- SQLAlchemy 2.x (`sqlalchemy>=2.0.52`).
- Alembic (`alembic>=1.19.1`).
- psycopg 3 (`psycopg[binary]>=3.3.5`).
- pydantic-settings (`pydantic-settings>=2.15.0`).

The lock file already resolves those dependencies. The future implementation must not add or upgrade dependencies or modify `backend/pyproject.toml` or `backend/uv.lock` unless a later owner-approved prompt explicitly changes that boundary.

The repository currently has no `backend/app/db/` package, settings module, SQLAlchemy engine/session/base, Alembic configuration, migration directory, ORM model, or test database fixture. Data Layer Foundation is therefore the first database-layer implementation step, despite the dependencies already being present.

The current GitHub Actions backend job runs dependency sync, Ruff formatting and lint checks, pytest, and an application import check. It does not provision PostgreSQL, run mypy, or validate Alembic. Full database integration validation therefore has an unresolved test-environment prerequisite described in Section 12.

## 3. Scope of Future Implementation

One separately approved implementation PR may contain only:

- PostgreSQL application database settings and safe environment validation.
- synchronous SQLAlchemy 2.x engine, session factory, declarative base, and metadata conventions.
- Alembic scaffold and migration governance without a schema revision.
- transaction, repository, and FastAPI dependency boundaries.
- an isolated PostgreSQL test strategy and foundation-level tests.
- UTC-aware datetime conventions.
- Decimal and PostgreSQL Numeric conventions.
- reusable audit-metadata conventions.
- environment and secret safety controls.
- a minimal update to `docs/BACKEND_MODULE_CATALOG.md`.

The implementation must remain infrastructure-only. Any file or behavior not needed to prove these boundaries is deferred.

## 4. Explicit Non-Scope

Neither this PRP nor its implementation PR authorizes:

- product, Listing, sales, inventory, finance, commission, fee, or other business tables.
- business fields or ORM models.
- RAW payload storage or Source Registry tables.
- read models, MART tables, or materialized views.
- Lingxing, Walmart, Feishu, WeCom, or other external connectors.
- an old-system or legacy MySQL runtime connector.
- Celery, Redis, scheduler, worker, or sync-task implementation.
- Field Watch, alerts, or notifications.
- Product API or any other business API.
- profit formulas, commission calculations, or other business rules.
- import/export implementation.
- AI data pipelines.
- retention/archive jobs or a full audit log.
- production deployment or production database access.

The historical system remains evidence only. New-system business APIs must not read it at runtime.

## 5. PostgreSQL Configuration Boundary

### 5.1 Canonical settings

Use the existing project names:

- `APP_ENV` for environment identity.
- `DATABASE_URL` for the application database URL.
- `TEST_DATABASE_URL` only for isolated database integration tests, if the owner approves this test setting before implementation.

Do not introduce `APP_DATABASE_URL` as a second alias. One canonical name avoids split configuration behavior.

The implementation must distinguish `local`, `dev`, `test`, `staging`, and `production`. Existing deployment documentation that currently lists fewer environments may be aligned only through a separately approved documentation change if needed.

### 5.2 Safe loading

- Settings must use the already-installed `pydantic-settings` package.
- Host, username, password, database name, and full URLs must come from environment injection or a secret manager.
- No real database identifier or connection URL may appear in code, docs, logs, tests, fixtures, or Git.
- Production values are injected only by the deployment environment.
- A missing or invalid required setting must fail closed with a sanitized error.
- The engine must be lazy: importing settings, `app.main`, or database modules must not open a connection.
- Local and test execution must reject an explicitly production environment.
- Test execution must never fall back from a missing `TEST_DATABASE_URL` to `DATABASE_URL`.

### 5.3 Example and ignore policy

The future implementation should add `backend/.env.example` containing variable names and non-secret guidance only. It must not contain a usable URL.

The current root `.gitignore` does not explicitly ignore `.env*`. Before anyone creates a real local `.env`, the implementation allowlist must either permit a minimal `.gitignore` update that ignores real environment files while keeping `.env.example`, or the owner must approve another equivalent safeguard. This is a security prerequisite, not authorization to create an `.env` file.

## 6. SQLAlchemy Foundation

Use synchronous SQLAlchemy 2.x with the existing psycopg driver. The current FastAPI endpoints are synchronous, and no measured requirement justifies an async engine/session boundary. Async database access requires a later PRP if a demonstrated need appears.

The minimum foundation consists of:

- one engine factory or lazily created application engine.
- one configured `sessionmaker`.
- one declarative base.
- one canonical request-scoped dependency named `get_db_session`.
- explicit engine disposal in the FastAPI lifespan or shutdown boundary.

Required lifecycle behavior:

1. Open one session for the bounded request or use case.
2. Perform work inside an explicit transaction boundary where writes exist.
3. Commit only at the service/use-case boundary after success.
4. Roll back an active write transaction on an uncaught exception.
5. Always close the session.

Read-only queries do not require commit. Importing the application and calling `/health` must not initialize a database connection.

Repositories must never create engines or own global transactions. Route handlers must not contain complex SQL.

## 7. Declarative Base and Metadata Convention

The foundation must provide a SQLAlchemy `DeclarativeBase` and one metadata naming convention covering at least:

- indexes: `ix`.
- unique constraints: `uq`.
- check constraints: `ck`.
- foreign keys: `fk`.
- primary keys: `pk`.

Stable names are required so Alembic output is reviewable and repeatable.

Candidate reusable conventions are:

- `created_at` and `updated_at`.
- `created_by` and `updated_by` when the owning module has an authenticated actor.
- `request_id` when the record must carry mutation trace context.
- `deleted_at`, `deleted_by`, and `delete_reason` only for models whose approved retention policy requires soft deletion.

Do not create a universal `id` mixin. Each future business-model PRP must define the model grain and stable internal identifier. UUID may be evaluated then; it is not globally approved here.

No business model may be imported into the foundation merely to populate metadata. The first model and first actual schema revision belong to the first separately approved business-model PRP.

## 8. Alembic Foundation

The future implementation may create an Alembic scaffold under `backend/`:

```text
backend/alembic.ini
backend/alembic/env.py
backend/alembic/script.py.mako
backend/alembic/versions/.gitkeep
```

`alembic/env.py` must import the single declarative `Base.metadata` and obtain its URL through the approved settings boundary. It must contain no hardcoded URL, production default, or second configuration path.

Migration governance:

- revision names must describe one schema change and remain module-scoped.
- generated migrations require human review; autogenerate output is never approval.
- destructive or data migrations require their own PRP, rollback plan, backup/restore checks, and owner authorization.
- no migration may be applied to production from a developer command or test.
- commands must make the target environment explicit and fail closed when unsafe.

Do not create a no-op initial revision. With no approved schema, an empty revision would create a false baseline. The first revision must accompany the first approved database model in a separate PR.

Safe scaffold validation may include `uv run alembic -c alembic.ini heads`, which must not require a database connection. `alembic check`, upgrade, downgrade, or autogenerate may run only against an explicitly approved disposable test PostgreSQL instance.

## 9. Transaction Boundary

| Layer | Responsibility | Prohibited responsibility |
|---|---|---|
| FastAPI route | Parse validated input, enforce existing auth/permission/data-scope dependencies, inject session, call service, return the existing envelope | Complex SQL, commit/rollback, transaction orchestration |
| Service/use case | Define the business transaction boundary, coordinate repositories, commit on success, allow rollback on failure | Creating engines, returning ORM objects as API contracts |
| Repository | Execute focused persistence/query operations using the injected session | Commit, global transaction ownership, HTTP/external API logic, permission decisions |

One request or use case should use one transaction boundary. Read-only queries may use the request-scoped session without commit. A future batch or sync task must create its own session and one bounded transaction per approved work unit; it must not reuse a web-request session.

Avoid a custom transaction-manager abstraction in this foundation. SQLAlchemy session context and `session.begin()` are sufficient until repeated, measured needs prove otherwise.

## 10. Repository Boundary

The foundation defines rules, not a generic repository implementation.

- A repository receives a session from its caller.
- It contains database access only.
- It must not import FastAPI request/response types.
- It must not call external APIs.
- It must not make permission or data-scope decisions.
- It must not accept unvalidated frontend data directly.
- It must not access historical MySQL at runtime.
- It must not commit.
- It must not return ORM objects as public API response contracts; a service/schema/DTO boundary performs that mapping.

When an approved business module needs persistence, its concrete repository should live with that module, for example `backend/app/modules/<module>/repository.py`. Do not add a one-implementation interface, generic base repository, or protocol in this foundation. Introduce an interface only when multiple implementations or an established testing seam makes it necessary.

## 11. FastAPI Dependency Boundary

The canonical dependency is `get_db_session`.

- Protected business routes may inject it after the route's existing authentication, permission, and data-scope checks.
- `/health` remains public, database-independent, and safe during database outages.
- A database readiness check, if needed later, requires a separate endpoint decision and PRP; it must not silently change `/health`.
- The dependency manages open, exception rollback, and close. It does not auto-commit successful requests.
- Services own write transaction completion.

The existing API envelope, error mapping, and request ID remain authoritative. The existing request ID helper should be reused to pass request context into future audit metadata or transaction context. A request ID is trace metadata only; it is not authentication, authorization, or idempotency.

Engine creation and disposal should be attached to FastAPI lifespan only if that can be done without import-time or `/health` database access. No second app factory or API foundation may be created.

## 12. Test DB Strategy

### 12.1 Unit tests

Foundation unit tests should verify settings validation, metadata naming, session cleanup/rollback behavior, safe application import, and engine construction without contacting a database where possible. Fakes or SQLAlchemy event inspection may be used only when they test the real boundary without recreating SQLAlchemy.

### 12.2 Integration tests

Database integration tests require a disposable, isolated PostgreSQL database because SQLite cannot validate PostgreSQL types, transaction behavior, or Alembic semantics reliably.

Requirements:

- `APP_ENV=test` must be explicit.
- `TEST_DATABASE_URL` must be explicit if that name is approved.
- missing test configuration must skip or fail with a clear safe message; it must never fall back to a development or production URL.
- fixtures should isolate tests with a transaction and roll it back.
- destructive commands and business data are prohibited.
- no real business samples may be loaded.
- Alembic tests may inspect configuration and scaffold offline; upgrade/downgrade testing requires the disposable database and explicit authorization.

The current CI has no PostgreSQL service and the repository has no test-database environment. Before implementation, the owner must choose one of these bounded options:

1. approve an isolated PostgreSQL service for CI in a separate CI-scoped change; or
2. approve an existing disposable test service with non-production credentials supplied outside Git.

Until then, complete PostgreSQL integration validation is an implementation blocker. The engineer must not substitute a local development database or production database.

## 13. UTC Datetime Convention

- Server and persistence timestamps must be timezone-aware UTC.
- PostgreSQL timestamp columns representing instants must use `timestamptz` through SQLAlchemy `DateTime(timezone=True)` or the approved equivalent.
- Naive `datetime` values are prohibited at the database boundary.
- Local timezone conversion belongs at the presentation boundary.
- System timestamps such as `created_at` and `updated_at` must remain distinct from source/business dates such as `business_date`, `order_date`, and `settlement_date`.
- A sync observation time, source event time, and source business date must not be silently substituted for one another.

This foundation defines the convention only; it creates no business date fields.

## 14. Decimal / Numeric Money Convention

- Python money, fee, profit, and FX values use `Decimal`, never `float`.
- PostgreSQL amount fields use `Numeric`; the project default is `Numeric(18, 4)` unless a later approved field contract documents another precision and scale.
- Canonical monetary contracts retain `amount`, `currency_code`, `precision`, `scale`, and `rounding_rule`.
- Currency conversion contracts also retain `fx_rate`, `fx_date`, and `fx_source`.
- Source aliases must be mapped through documented lineage rather than becoming competing canonical names.

This foundation may provide a reusable type convention only when actual code needs it. It must not create finance tables, currency tables, FX tables, profit formulas, or calculation services.

## 15. Audit Metadata Convention

Candidate mutation metadata is:

- `created_at`.
- `updated_at`.
- `created_by`.
- `updated_by`.
- `request_id`.

Time fields follow the UTC rule. Actor fields must use a stable authenticated principal identifier defined by the owning module. `request_id` reuses the Backend API Foundation context.

These fields support traceability but are not a full audit trail. High-risk actions still require immutable audit events, before/after details, approval evidence, and retention rules through a separate Audit / Operation Log PRP.

## 16. Soft Delete / Retention Boundary

Do not apply soft delete to every table.

A `deleted_at`, `deleted_by`, and `delete_reason` mixin may be provided only if the implementation can keep it optional and a near-term approved model requires it. Otherwise defer the mixin to the first such model PRP.

RAW data, audit records, finance records, calculation results, and alerts have different retention and immutability requirements. Each requires a separate data-model PRP. This foundation implements no retention, archive, purge, restore, or legal-hold behavior.

## 17. Environment and Secret Boundary

- Environments are `local`, `dev`, `test`, `staging`, and `production`.
- Secrets never enter Git, documentation, source code, test output, logs, screenshots, chat, or fixtures.
- Production database configuration exists only in the deployment secret environment.
- Local safe mode rejects production configuration and performs no import-time connection.
- Tests use only an explicitly identified disposable test database.
- CI database provisioning, if selected, requires a separate owner-approved CI scope.
- No implementation command may print a complete connection URL.

This PRP contains no real connection string and does not authorize creation or modification of a real `.env` file.

## 18. Future Implementation Candidate Files

The future implementation prompt should approve only files that remain necessary after final design review. Candidate files are:

```text
backend/.env.example
backend/app/core/config.py
backend/app/db/__init__.py
backend/app/db/base.py
backend/app/db/session.py
backend/alembic.ini
backend/alembic/env.py
backend/alembic/script.py.mako
backend/alembic/versions/.gitkeep
backend/app/main.py
backend/tests/db/test_config.py
backend/tests/db/test_base.py
backend/tests/db/test_session.py
backend/tests/db/test_alembic_scaffold.py
backend/tests/test_health.py
docs/BACKEND_MODULE_CATALOG.md
.gitignore
```

Conditional candidates:

- `backend/app/db/mixins.py` only if an approved reusable audit mixin is implemented now.
- `backend/app/db/types.py` only if a reusable Numeric type is exercised by foundation code; otherwise defer it to the first model.

Do not create `transaction.py`: SQLAlchemy's native session transaction API is sufficient. Do not create a generic repository or business module. Do not modify dependency manifests or lock files.

The implementation prompt must turn this candidate list into an exact allowlist. Files not expressly allowed remain prohibited.

## 19. Validation Plan for Future Implementation PR

Before running anything, the implementation engineer must inspect existing commands and use the project's Python 3.13 and uv environment. No command may target a real development or production database.

Required repository and backend checks:

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

`uv run alembic ... heads` must remain offline. Commands that require a database may run only after isolated test PostgreSQL is approved and configured. The implementation report must say which tests were offline and which used the isolated test database.

Additional review checks must confirm:

- no secret or usable connection URL is present, using the existing CI secret scan and a review of new configuration files.
- no legacy MySQL driver, connector, URL, or runtime dependency was added.
- no frontend file changed.
- no ORM business model, table, migration revision, SQL file, external API client, worker, or sync task was added.
- `/health` remains public and database-independent.
- imports do not open a database connection.

If the current CI configuration still lacks PostgreSQL, the implementation may not claim integration-test completion. CI changes require their own approved scope and must not be slipped into the Data Layer implementation.

## 20. Acceptance Criteria

The future implementation PR is complete only when:

- settings, SQLAlchemy base, engine/session factory, and `get_db_session` can be imported safely.
- imports and `/health` do not connect to a database.
- unsafe production fallback is rejected.
- session cleanup and rollback behavior are tested.
- repositories are documented as injected-session data access with no commit authority.
- SQLAlchemy metadata has stable constraint naming.
- Alembic scaffold exists and can be inspected offline.
- no migration revision or business table exists.
- UTC-aware datetime and Decimal/Numeric conventions are documented and covered where code exists.
- isolated test-database prerequisites are either satisfied and tested or reported as an unresolved blocker; production is never used as a substitute.
- `docs/BACKEND_MODULE_CATALOG.md` records the Data Layer Foundation module and boundaries.
- Ruff, mypy, pytest, application import, rule-pack, and diff checks pass within the approved environment.
- no historical MySQL runtime dependency, external API call, frontend change, or committed secret exists.
- the final diff contains only the approved allowlist.

## 21. Risk Controls

| Risk | Required control |
|---|---|
| Local or test execution reaches production | Explicit environment validation; test URL never falls back; lazy connection; no production defaults |
| Migration runs against production | Explicit target environment, separate execution authorization, no upgrade in routine validation |
| Route handler accumulates SQL/transactions | Inject session, keep route thin, put transaction in service and access in repository |
| Repository commits unexpectedly | Repository contract forbids commit; tests verify service/session boundary |
| Money uses binary floating point | `Decimal` in Python and `Numeric` in PostgreSQL |
| Naive timestamps enter persistence | timezone-aware UTC validation and timezone-aware database types |
| Historical MySQL returns as runtime source | dependency and source scans; no connector or URL; reviewer verifies all database code targets the application PostgreSQL boundary |
| Foundation becomes a business-model PR | exact file allowlist, no models/revisions/tables, stop on business fields |
| Empty migration creates a false baseline | scaffold only; first revision waits for an approved model PRP |
| Generic abstractions grow without use | no generic repository, transaction wrapper, universal ID mixin, or unused type module |
| Connection URL leaks | environment-only configuration, sanitized errors, blank example, secret scan, no URL logging |
| CI cannot prove PostgreSQL behavior | treat isolated test database as a prerequisite; do not weaken tests or substitute another database |

Stop and request owner direction if implementation needs a business model, migration revision, SQL file, external connector, historical database access, extra dependency, CI modification, real database credential, or any file outside the approved allowlist.

## 22. Relationship to Future PRPs

The intended sequence is:

1. Data Layer Foundation Implementation.
2. Source Registry + RAW Storage PRP.
3. First Lingxing Endpoint Ingestion PRP.
4. Product Core Data Model PRP.
5. Product Read Model PRP.
6. Product API reading the new-system database or approved read model PRP.
7. Sync Control API / Scheduler PRP.
8. Field Watch / Alert / Notification PRPs.
9. Business Rules / Metrics PRPs.
10. Commission / Fee Rules PRPs.

Each item is a separate gate, branch, PRP where required, implementation prompt, test scope, review, and PR. Approval or completion of this foundation does not authorize any later item.

## 23. Agent Role and Skill Boundary

The future implementation has one main execution role: Backend Engineer.

Agent Skills are working modes, not people, roles, approval authorities, or permission grants. Suggested skills are:

- `engineering-minimal-change-engineer` for the smallest sufficient foundation.
- `engineering-backend-architect` for SQLAlchemy/FastAPI boundary checks.
- `engineering-technical-writer` for module-catalog alignment.
- `testing-evidence-collector` for reproducible validation evidence.
- `engineering-database-reliability-engineer` only for static safety review unless a separate database-access PRP is approved.

No skill may expand the file allowlist, connect to a database, run a migration, modify CI, deploy, or perform Git write operations without explicit owner authorization. The owner remains responsible for `git add`, commit, push, PR creation, and merge.

## 24. Owner Approval Checklist

Before changing this PRP to `Approved`, the owner must confirm:

- synchronous SQLAlchemy 2.x with psycopg is the approved first boundary.
- canonical settings are `APP_ENV`, `DATABASE_URL`, and, if accepted, test-only `TEST_DATABASE_URL`.
- the implementation may add a blank `backend/.env.example`.
- the implementation may minimally update `.gitignore` to protect real `.env` files, or an equivalent safeguard is approved first.
- Alembic scaffold contains no no-op revision.
- `/health` remains public and independent of the database.
- the isolated PostgreSQL test environment and whether CI provisioning is a separate PR.
- the exact future implementation file allowlist.
- no business model, migration revision, legacy connector, external API, worker, or sync task is authorized.

Approval of this PRP alone does not start implementation. The owner must issue a separate implementation prompt.

## 25. Rollback Boundary

The future implementation PR must be removable as one unit before any business migration depends on it. Rollback means reverting only its configuration, database foundation, Alembic scaffold, tests, lifespan hook, and module-catalog entry. It must not require reversing business data because this foundation creates none.

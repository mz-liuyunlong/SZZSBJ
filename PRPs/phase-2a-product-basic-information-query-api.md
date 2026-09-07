# Phase 2A Product Basic Information Query API PRP

```text
Status: Approved
Owner Approval Required: Yes
Implementation Allowed Before Merge: No
Database Access Used In This PRP Task: No
Server Access Used In This PRP Task: No
External API Used In This PRP Task: No
```

## 1. Authorization Boundary

This PRP defines the bounded scope for a later backend implementation of the Phase 2A product basic information read-only query API. It is not implementation authorization on this branch.

- This PRP does not authorize API development before Architect review, owner approval and merge.
- This PRP does not authorize connecting to a database or server during PRP authoring.
- This PRP does not authorize executing SQL during PRP authoring.
- This PRP does not authorize writing to the legacy database or the new PostgreSQL database.
- This PRP does not authorize creating a table, migration, ORM model, temporary table, mart or read model.
- This PRP does not authorize Walmart, Lingxing, Feishu or other external API calls.
- This PRP does not authorize frontend work, deployment or production configuration changes.
- Only after the owner changes `Status` to `Approved` and merges this PRP may a Backend Engineer implement the read-only endpoint within the exact approved boundary.
- Approval does not waive the implementation prerequisites or stop conditions in this PRP.

## 2. Governing Decisions and Evidence

This PRP is governed by:

- `docs/data-sources/decisions/products-basic-information-query-decision.md`
- `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md`
- `PRPs/phase-2a-product-basic-information-source-discovery.md`
- `PRPs/phase-2a-product-basic-information-od9-readonly-db-inventory.md`
- `docs/delivery/backend-data-source-decision-gate.md`
- `docs/data-sources/database-layering-standard.md`
- `docs/data-sources/field-standardization-standard.md`
- `docs/DATA_SOURCE_AND_LINEAGE_RULES.md`
- `docs/architecture/api.md`
- `docs/architecture/backend.md`
- `docs/delivery/api-documentation-standard.md`

The Source Decision is `READY_FOR_PRP` only for the narrowed Phase 2A product basic information query. The approved first-stage classification is `READ_LEGACY_TEMPORARILY`.

OD-9 established that `dim_product`, `dim_store` and `dim_store_config` exist, but the approved runtime source for this endpoint is only `dim_product`. The store tables were evidence sources for OD-3 and are not runtime query dependencies for this API.

## 3. Goal

Implement one authenticated, permission-protected, read-only FastAPI endpoint that returns a paginated subset of legacy `dim_product` through a dedicated Legacy Readonly Repository.

The endpoint must:

- expose only the five approved fields;
- use the project response envelope and include `request_id`;
- enforce bounded pagination, exact-match `item_id`/`store_id` filters and a fixed stable internal order;
- enforce page permission and `store_id` data scope on the backend;
- report legacy-source and data-quality warnings without inventing missing values;
- keep route, service, schema and repository responsibilities separate;
- remain independently testable without connecting to a real legacy database.

This PRP does not make the complete Product Management page or all product data ready for backend implementation.

## 4. Business Grain and Data Layer

```text
Business grain: one returned item represents one approved legacy dim_product record at its source listing/operational identity grain.
Queried layer: legacy MySQL as an approved temporary L0 source dependency.
Runtime table: dim_product only.
Classification: READ_LEGACY_TEMPORARILY.
New PostgreSQL tables: none.
Mart/read model: none.
Write path: none.
```

The returned item is not a new-system `product_id`, is not a globally unique SKU entity and must not be presented as canonical product master data. The long-term direction remains Walmart Listing verification first, Lingxing local product evaluation only if needed, followed by a separately approved standardized/master-data path.

## 5. Proposed API Contract

### 5.1 Endpoint

```text
Method: GET
Path: /api/v1/products/basic-information
Summary: Query Phase 2A product basic information
Page: 产品 > 产品管理
PermissionKey: products.product_management.view
Data scope resource: store_id
Source: legacy_mysql
Source tables: dim_product
Readonly: true
Audit required: false for the ordinary read itself
High risk: false within the approved five-field scope
```

The route must declare `response_model`, OpenAPI summary/description/tags and this metadata through the project's `openapi_extra` convention.

### 5.2 Request Parameters

| Parameter | Type | Required | Default / limit | Phase 2A behavior |
|---|---|---:|---|---|
| `page` | integer | No | default `1`, minimum `1` | Page number. Requests producing an offset above `10_000` are rejected as `INVALID_PAGE`. |
| `page_size` | integer | No | default `20`, minimum `1`, maximum `100` | The default follows the existing project API pagination rule; this endpoint uses a stricter maximum than the project-wide ceiling. |
| `item_id` | string | No | exact match only | Case is preserved; no wildcard or fuzzy search. |
| `store_id` | string | No | exact match only | The requested value is intersected with backend-authorized store scope. |

Rules:

- All filters are combined with `AND`.
- Empty query values must be rejected as `INVALID_FILTER`; they must not silently become unfiltered scans.
- Arbitrary `filters` JSON is not supported.
- `sku` and `msku` remain response fields but are not accepted Phase 2A production filters.
- Filters on `store_name`, `product_name`, brand, category, status or any excluded field are forbidden.
- The repository must bind parameters; string interpolation into SQL is forbidden.
- The API must not accept a client-controlled flag that disables permission or data-scope filtering.

#### 5.2.1 Deferred SKU/MSKU Filters

`sku` and `msku` filters are `Blocked pending owner-approved readonly query-plan/performance verification` because OD-9 found no independent indexes for those columns.

- Supplying `sku` or `msku` as a filter in Phase 2A must return `INVALID_FILTER`.
- Enabling either filter requires a separate owner-authorized read-only query-plan/performance verification and a reviewed contract update.
- Production runtime timeout is failure handling, not performance admission evidence.
- Deferring these filters does not remove `sku` or `msku` from the response contract.

### 5.3 Keyword Search

`keyword` is not supported in Phase 2A and is omitted from the accepted request contract. A supplied `keyword` or other unknown filter must be rejected as `INVALID_FILTER`, not silently ignored.

Keyword search is deferred because it could create an unindexed fuzzy scan and ambiguous cross-field semantics. It requires a later approved contract and performance evidence.

### 5.4 Sorting

Phase 2A exposes no caller-selectable sorting. The external sort whitelist is therefore empty.

- Any supplied `sort_by` or `sort_order` is rejected as `SORT_NOT_ALLOWED`.
- `platform` is a fixed server-side source constraint and internal ordering/lineage key only. It is not a response field, request filter or frontend field.
- The exact fixed platform value must be owner-approved in the implementation prompt; implementation stops if that source constraint is unresolved.
- Within that fixed source constraint, the repository uses the OD-9 unique-key direction for deterministic ordering: `platform`, `store_id`, `item_id`, then `msku`, all ascending.
- The fixed order is an internal output-order rule, not a claim that the five returned fields form a globally unique business identity.
- Sorting by `sku` or `item_name` is deferred and is not part of Phase 2A.
- SKU, ItemID or MSKU must not be described as globally unique.
- Arbitrary column names and dynamic SQL ordering are forbidden.
- If this fixed order cannot remain within the approved timeout/scan boundary, implementation must stop for PRP review; it must not create an index, temporary table or read model under this PRP.

### 5.5 Versioned Response Item Contract

This approved PRP, once merged as `Approved`, is the versioned v1 contract for these response fields. No other business field may be added during implementation.

| Field | Type | Nullable | Meaning and constraints | Source |
|---|---|---:|---|---|
| `item_id` | string | No | Platform item/listing identifier. It is not an internal `product_id`. Preserve as text. | `dim_product.item_id` |
| `sku` | string | Yes | Source/local SKU label. Null or blank source values normalize to JSON null; it is not globally unique. Do not infer, normalize case or discard the row. | `dim_product.sku` |
| `msku` | string | No | Marketplace/operational SKU identifier. It does not automatically equal `product_id`. Preserve as text. | `dim_product.msku` |
| `item_name` | string | Yes | First-stage product name. Preserve the source value; do not fallback to `product_name` or invent a name. | `dim_product.item_name` |
| `store_id` | string | No | Source store/account identifier used for data-scope enforcement. It is not `store_name`. | `dim_product.store_id` |

No response item field performs currency, unit, enum or time conversion. The API performs only the bounded string trim and null normalization defined below; case is preserved and the legacy source is never mutated.

The API does not return a synthetic `row_key`. Consumers must not use SKU or any undocumented combination of returned fields as a proven unique key. If a frontend needs a stable row key, a later frontend contract or API implementation PRP must define it without exposing an excluded business field. A new canonical identifier requires a separate identity decision and PRP.

#### 5.5.1 Field Standardization Declaration

The following entries are `Draft` while this PRP is Draft. Owner approval changes them to `Approved` only for this v1 API contract; it does not create canonical master-data ownership.

| canonical_field | business_meaning / grain | data_type | nullable | source_system / source_fields | cleaning / enum / time / currency | identity rule | owner / status / first module | evidence and notes |
|---|---|---|---:|---|---|---|---|---|
| `item_id` | Platform item/listing identifier on one returned legacy source row | string | No | `legacy_mysql` / `dim_product.item_id` | Trim outer whitespace; preserve case; enum, unit, time and currency not applicable | Preserve as external ID; never derive `product_id`, SKU or MSKU | Project Owner / Draft until approval / Phase 2A product basic information query | Source Decision section 6 and OD-9 report sections 4, 6 and 7; preserve leading zeros and source text |
| `sku` | Source/local SKU label on one returned legacy source row | string | Yes | `legacy_mysql` / `dim_product.sku` | Trim outer whitespace; blank or null becomes JSON null; preserve case; enum, unit, time and currency not applicable | Not globally unique; do not infer, merge or drop a row | Project Owner / Draft until approval / Phase 2A product basic information query | Source Decision OD-4; OD-9 reports 27.06% null-or-blank and duplicate/mapping risk |
| `msku` | Marketplace/operational SKU on one returned legacy source row | string | No | `legacy_mysql` / `dim_product.msku` | Trim outer whitespace; preserve case; enum, unit, time and currency not applicable | Preserve as external operational ID; not `product_id` | Project Owner / Draft until approval / Phase 2A product basic information query | Source Decision section 6 and OD-9 report sections 4, 6 and 7 |
| `item_name` | First-stage source product name on one returned legacy source row | string | Yes | `legacy_mysql` / `dim_product.item_name` | Trim outer whitespace; blank or null becomes JSON null; no translation, rewrite or fallback; enum, unit, time and currency not applicable | Not an identity field | Project Owner / Draft until approval / Phase 2A product basic information query | Source Decision OD-2; missing values remain missing and never fallback to `product_name` |
| `store_id` | Source store/account identifier on one returned legacy source row | string | No | `legacy_mysql` / `dim_product.store_id` | Trim outer whitespace; preserve case; enum, unit, time and currency not applicable | Preserve source ID; use for backend data scope; never infer `store_name` | Project Owner / Draft until approval / Phase 2A product basic information query | Source Decision OD-3 and OD-9 report sections 4, 6 and 8 |

#### 5.5.2 Field Standardization Applicability Matrix

| Step | Applies? | Rule for this API | Failure / warning handling |
|---|---|---|---|
| 1. Source Field Capture | Yes | Read only `item_id`, `sku`, `msku`, `item_name` and `store_id` from legacy readonly `dim_product`. `platform` is internal source/order/lineage context only and never enters the response. | Any need for another source field or table stops implementation for PRP review. |
| 2. Field Name Normalize | Yes | Canonical response names are exactly `item_id`, `sku`, `msku`, `item_name` and `store_id`. | Undefined or aliased business fields are rejected from the contract. |
| 3. Data Type Normalize | Yes | Return external IDs, SKU, MSKU and store ID as strings; never cast them to numbers or lose leading zeros. | An unrepresentable required ID produces `DATA_SOURCE_NOT_READY`; no coercion is invented. |
| 4. Null Normalize | Yes | Normalize source NULL, empty strings and whitespace-only strings to JSON null. Only `sku` and `item_name` are nullable; null never causes a row to be silently discarded. | Missing SKU or name adds its warning. A missing required `item_id`, `msku` or `store_id` produces `DATA_SOURCE_NOT_READY`. |
| 5. Trim / Text Clean | Yes | Trim leading and trailing whitespace while preserving case. Do not translate, rewrite, concatenate, infer or fallback to `product_name`; never mutate the legacy source. | Any proposed semantic rewrite stops for contract review. Missing results use the approved null/warning behavior. |
| 6. Enum Normalize | No (`not_applicable`) | Phase 2A returns no status or enum field. | Adding an enum requires a Source Decision and PRP update. |
| 7. Unit Normalize | No (`not_applicable`) | The response contains no dimensions, weight, volume or other unit-bearing field. | Adding one requires a Source Decision and PRP update. |
| 8. Currency Normalize | No (`not_applicable`) | The response contains no amount, cost, profit, settlement or currency field. | Adding one requires a Source Decision and PRP update. |
| 9. Timezone Normalize | No for response (`not_applicable`) | No timestamp is returned. Freshness remains `unknown` in meta with `DATA_FRESHNESS_UNKNOWN`; no real time range is returned. | Do not substitute legacy row timestamps. A time field requires a separate approved contract. |
| 10. Identity Mapping | Yes, bounded | `item_id` is not `product_id`; SKU is not globally unique; MSKU is not automatically `product_id`. Create no `product_id`/`listing_id`, store-name or SKU mapping. | Identity ambiguity is preserved; no merge, inference, write or dropped row is allowed. |
| 11. Data Quality Check | Yes | There is no global DQ eviction threshold. Nullable fields plus `SKU_MISSING`, `SKU_NOT_GLOBAL_UNIQUE`, `ITEM_NAME_MISSING` and `DATA_FRESHNESS_UNKNOWN` express approved risks. | Do not discard rows because of DQ risk. Required identity failure uses `DATA_SOURCE_NOT_READY`. |
| 12. Lineage Record | Yes | Cite the Source Decision, OD-9 inventory report, approved OD-9 PRP and `READ_LEGACY_TEMPORARILY`; return `LEGACY_READONLY_SOURCE` in meta. | Never claim the legacy database is the long-term authority; missing lineage stops implementation. |

Lineage boundary:

- Current source writer evidence points to the legacy daily Lingxing/Walmart Listing chain, but OD-9 did not prove that the job is currently running.
- The new reader is only the product basic information service through its Legacy Readonly Repository.
- No field is written, standardized into PostgreSQL or promoted to a new-system master table by this API.
- Freshness remains unknown; legacy row timestamps are not source-update or sync-success evidence.
- `source_system`, exact source field and Source Decision evidence remain documented in this contract even though they are not added as response item fields.

### 5.6 Success Response

The response must use the canonical project envelope. Pagination, warnings and data freshness belong in `meta`, not in a second top-level response format.

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "item_id": "<string>",
        "sku": null,
        "msku": "<string>",
        "item_name": null,
        "store_id": "<string>"
      }
    ]
  },
  "error": null,
  "meta": {
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 0,
      "total_pages": 0
    },
    "source": "legacy_mysql",
    "source_tables": ["dim_product"],
    "freshness": {
      "status": "unknown",
      "as_of": null
    },
    "warnings": [
      "LEGACY_READONLY_SOURCE",
      "DATA_FRESHNESS_UNKNOWN",
      "SKU_NOT_GLOBAL_UNIQUE"
    ]
  },
  "request_id": "<request-id>"
}
```

`meta.freshness` is the project's canonical location for the requested data-freshness information. It must not contain an invented sync time or reuse legacy row `updated_at` as source freshness.

Rows contain only the five approved fields. Warning codes are response metadata and must not add business fields to an item.

### 5.7 Warning Codes

| Code | When included | Meaning |
|---|---|---|
| `LEGACY_READONLY_SOURCE` | Always | The response is temporarily sourced from approved read-only legacy data. |
| `DATA_FRESHNESS_UNKNOWN` | Always | No approved evidence proves current Walmart/Lingxing source freshness. |
| `SKU_NOT_GLOBAL_UNIQUE` | Always | Clients must not treat SKU as a global identifier. |
| `SKU_MISSING` | Returned page contains a SKU normalized to JSON null | The row remains in the response; no inference is performed. |
| `ITEM_NAME_MISSING` | Returned page contains an `item_name` normalized to JSON null | The value remains missing; no `product_name` fallback is performed. |

Warnings must not contain real SKU, MSKU, ItemID or store values.

### 5.8 Error Response and Codes

Errors use the canonical envelope:

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "INVALID_FILTER",
    "message": "请求参数无效",
    "details": {}
  },
  "meta": null,
  "request_id": "<request-id>"
}
```

| Error code | HTTP status | Required scenario |
|---|---:|---|
| `INVALID_PAGE` | 422 | Page is below 1 or exceeds the approved offset boundary. |
| `PAGE_SIZE_TOO_LARGE` | 422 | `page_size` exceeds 100. |
| `INVALID_FILTER` | 422 | Empty, unknown, fuzzy, excluded-field or deferred `sku`/`msku` filter. |
| `SORT_NOT_ALLOWED` | 422 | Caller supplies any unsupported sort parameter. |
| `UNAUTHORIZED` | 401 | No valid backend authentication. |
| `FORBIDDEN` | 403 | Missing `products.product_management.view`. |
| `DATA_SCOPE_DENIED` | 403 | Explicit `store_id` is outside the user's authorized data scope. |
| `LEGACY_DB_UNAVAILABLE` | 503 | Legacy readonly connection is unavailable. |
| `DATA_SOURCE_NOT_READY` | 503 | Required approved identity data cannot be safely represented. |
| `LEGACY_QUERY_TIMEOUT` | 504 | Query exceeds the approved database timeout. |
| `INTERNAL_ERROR` | 500 | Unexpected internal failure; no database or secret detail is exposed. |

Every success and failure response must include `request_id`. Frontend code must not need to parse error message strings.

## 6. Legacy Readonly Repository Boundary

The later implementation must use one dedicated Legacy Readonly Repository.

```text
route
  -> permission and strict request validation
  -> product basic information service
  -> legacy product readonly repository
  -> separately configured legacy readonly session
  -> legacy dim_product
```

Responsibilities:

- Route: authentication dependency, permission declaration, request validation, service call and response-model return only.
- Service: authorized data-scope input, warning composition and error translation; no SQL.
- Legacy repository: parameterized read-only queries against `dim_product`; no business permission decisions.
- Legacy session: physically separate engine/session factory from the new PostgreSQL write session.

Mandatory controls:

- Select exactly `item_id`, `sku`, `msku`, `item_name` and `store_id`; `SELECT *` is forbidden.
- Query only `dim_product`; do not join `dim_store`, `dim_store_config`, facts, costs or manual tables.
- Apply the owner-approved fixed `platform` source constraint before data scope, counting and pagination. `platform` may be referenced only by that internal predicate/order and is never selected into the response or exposed as a request parameter.
- Apply backend-authorized `store_id` scope before pagination and counting.
- Every data query must use `LIMIT` and `OFFSET` or an equivalent bounded pagination mechanism.
- Count and page queries must share the same approved filters and data scope.
- Database statement timeout: `2_000 ms` by default and never above `5_000 ms` without a PRP update and owner approval.
- Maximum calculated offset: `10_000`.
- Do not execute DML, DDL, stored procedures, multi-statements, temporary tables or migrations.
- Do not let Alembic discover or manage the legacy engine.
- Do not share a transaction/session with new PostgreSQL.
- Do not retry a timed-out query in the request path.
- Map unavailable and timeout failures to the approved error codes without exposing host, schema, SQL or credentials.

The implementation must not test production credentials, inspect a real `.env` file or connect to the real legacy database unless the owner separately authorizes an exact read-only verification task.

## 7. Authentication, Permission and Data Scope

Required permission:

```text
products.product_management.view
```

Rules:

- The endpoint must require backend-authenticated identity.
- Role names must not be hard-coded.
- The backend must enforce the permission key even if the frontend hides the page.
- The effective `store_id` set must be supplied by the backend data-scope layer, never trusted from a client flag.
- An explicit permitted `store_id` narrows the authorized set.
- An explicit unauthorized `store_id` returns `DATA_SCOPE_DENIED` without revealing whether matching data exists.
- A request without `store_id` is still restricted to the caller's authorized store set.
- Empty authorized scope returns an empty page without querying outside that scope.
- Full export is not supported. Export requires a separate PRP.
- No cost, procurement, profit, settlement, advertising or other sensitive field is exposed.

### 7.1 Blocking Implementation Prerequisite

The current baseline contains only the backend health endpoint and does not contain an approved backend authentication, permission or data-scope implementation. It also does not contain a shared canonical response/request-ID foundation.

This product API PRP does not authorize inventing a header-based identity, trusting frontend state, hard-coding an admin role or building a new authentication system inside the products module. Before product API implementation begins, the latest `main` must contain an owner-approved backend authentication/permission/data-scope foundation that can enforce the requirements above. If it does not, implementation must stop and that foundation requires its own PRP.

The latest `main` must also provide the project-wide response envelope and request-ID mechanism, or those cross-cutting pieces must be approved in a separate foundation PRP. This product module must not create a second envelope or a route-local request-ID convention.

## 8. Legacy Connection and Dependency Prerequisite

The current backend dependency set contains SQLAlchemy but no MySQL dialect driver, and no `legacy_mysql` session module exists.

Before implementation, the owner must approve one of these bounded options:

1. a separate Legacy Readonly Connection Foundation PRP; or
2. inclusion of one SQLAlchemy-compatible MySQL driver and the minimum isolated `legacy_mysql` engine/session module in the approved implementation prompt for this PRP.

Only one driver may be added. Its package and version must be verified against Python 3.13 and SQLAlchemy 2 using Context7 or official documentation before modification. Dependency changes must use `uv`, update `pyproject.toml` and `uv.lock` together, and must not install or execute old-system dependencies.

Runtime credentials must come from owner-controlled environment/secret configuration. Real values must never appear in `.env.example`, code, logs, tests, PRP content or chat. The engineer must not open or read the owner's real `.env`.

If neither option is approved, this API implementation remains blocked; a mock-only production endpoint is not acceptable.

## 9. Performance and Scan Boundary

- Page responses are always bounded; unpaginated list responses are forbidden.
- Default `page_size` is 20 and endpoint maximum is 100.
- Maximum calculated offset is 10,000.
- Only exact-match `item_id` and `store_id` filters are accepted in Phase 2A.
- Wildcards, `LIKE`, case-folded search, regex, keyword search and arbitrary filter objects are forbidden.
- Caller-selectable sorting is forbidden in Phase 2A.
- The fixed order and all filters must remain inside the repository timeout.
- Do not join inventory, sales, profit, advertising, settlement, refund, costs or other fact domains.
- Do not join store tables to produce `store_name`.
- Do not create legacy indexes, helper views, temporary tables or stored routines.
- Do not create a new-system table, cache, snapshot, mart or read model for this endpoint.
- SKU/MSKU filtering remains blocked until a separate owner-authorized read-only query-plan/performance verification and reviewed contract update approve it. Runtime timeout must not be used as its admission test.

Implementation-time tests must not be presented as proof of real production query performance. Any real database performance verification requires a separate owner-authorized read-only task.

## 10. Data Quality Behavior

### 10.1 SKU Missing

- `sku` is nullable; source null, empty or whitespace-only values normalize to JSON null.
- Rows are not discarded when SKU normalizes to null.
- Add `SKU_MISSING` to response warnings when the returned page contains a null SKU.
- Do not infer SKU from MSKU or ItemID.

### 10.2 SKU Duplicate and Identity Risk

- SKU is not globally unique and must not become a database, service or UI identity by itself.
- API documentation must state this limitation.
- No deduplication or automatic merging is allowed.
- The API preserves source rows at the approved grain.

### 10.3 Item Name Missing

- Normalize source null, empty or whitespace-only `item_name` to JSON null.
- Add `ITEM_NAME_MISSING` to response warnings when applicable.
- Do not query or fallback to `product_name`.
- Do not synthesize, translate or rewrite a product name.

### 10.4 Freshness Unknown

- Legacy `updated_at` is not source freshness and is not returned by this API.
- The API must not claim that data is real-time, current or the latest Walmart/Lingxing state.
- `meta.freshness.status` remains `unknown` and `as_of` remains `null` until a separately approved source/sync decision provides evidence.
- `DATA_FRESHNESS_UNKNOWN` is always returned.

### 10.5 Store ID

- `store_id` is a source store identity and a data-scope key.
- Do not translate it to `store_name`.
- Do not query or display `store_name`.
- Store alias and correction behavior remain out of scope.

## 11. Explicit Exclusions

The API contract, implementation and tests must exclude:

- `store_name` and the legacy multi-table name fallback;
- `product_name` fallback;
- brand and category;
- Walmart, ERP or manual status;
- `product_type`, lifecycle and CS-prefix derivation;
- owner or employee fields;
- manual correction, store alias and SKU-mapping write capabilities;
- inventory, sales, profit, advertising, settlement and refund data;
- costs, prices, WFS fee and currency data;
- full export or unbounded retrieval;
- mart/read model, cache or snapshot creation;
- new table creation, migration and ORM model creation;
- external API sync or request-path external calls;
- writes to the legacy or new database;
- frontend implementation;
- AI summary or AI recommendation;
- any business response field beyond the approved five.

## 12. OpenAPI and Markdown Documentation

The implementation is not complete without:

- a FastAPI route with `response_model`;
- OpenAPI-visible request and response schemas;
- `openapi_extra` containing:
  - `x-page: 产品 > 产品管理`;
  - `x-permission: products.product_management.view`;
  - `x-data-scope: [store_id]`;
  - `x-source: legacy_mysql`;
  - `x-source-tables: [dim_product]`;
  - `x-readonly: true`;
  - `x-audit-required: false`;
  - `x-high-risk: false`;
- a Markdown API document under `docs/api/`;
- documentation of parameters, the five fields, pagination, fixed order, warnings, errors, permission, data scope, legacy source and freshness limits;
- synthetic request/response examples only, with no real identifiers or credentials.

API documentation must not provide online execution against production or expose connection details.

## 13. Test Plan

Implementation tests must use mocks or fixtures and must not connect to a real legacy database, server or external API.

Required coverage:

1. Success uses the canonical response model and includes `request_id`.
2. Each item contains exactly the five approved fields.
3. `store_name`, `product_name`, brand, category, status and all other excluded fields are absent.
4. Null, empty or whitespace-only SKU normalizes to JSON null without discarding the row and adds `SKU_MISSING` when applicable.
5. Tests do not identify or deduplicate rows by SKU alone.
6. Null, empty or whitespace-only `item_name` normalizes to JSON null, does not fallback to `product_name` and adds `ITEM_NAME_MISSING`.
7. `page_size > 100` produces `PAGE_SIZE_TOO_LARGE`.
8. Invalid page/offset produces `INVALID_PAGE`.
9. Unknown, empty, fuzzy, excluded-field and deferred `sku`/`msku` filters produce `INVALID_FILTER`.
10. Caller-supplied sorting produces `SORT_NOT_ALLOWED`.
11. Missing authentication, missing permission and denied store scope produce the approved security errors.
12. Data scope is applied before repository pagination/count behavior.
13. Legacy unavailable and timeout failures map to `LEGACY_DB_UNAVAILABLE` and `LEGACY_QUERY_TIMEOUT` without leaking SQL or connection details.
14. `LEGACY_READONLY_SOURCE`, `DATA_FRESHNESS_UNKNOWN` and `SKU_NOT_GLOBAL_UNIQUE` are present.
15. Repository selects only the five approved columns, queries only `dim_product`, applies bounded pagination and contains no write/DDL path.
16. Tests perform no real network, external API or database call.

Do not use `.only`, `.skip`, global timeout increases or production data fixtures.

## 14. Implementation Plan and Provisional File Boundary

The final engineer execution prompt must narrow the exact file allowlist after checking the latest `main`. The expected minimum structure is:

```text
backend/app/main.py
backend/app/modules/products/__init__.py
backend/app/modules/products/router.py
backend/app/modules/products/schemas.py
backend/app/modules/products/service.py
backend/app/modules/products/legacy_repository.py
backend/tests/modules/products/test_product_basic_information_api.py
backend/tests/modules/products/test_product_basic_information_service.py
backend/tests/modules/products/test_legacy_product_repository.py
docs/api/products-basic-information-query.md
docs/api/README.md                         # only if an index entry is needed
```

If owner option 2 in section 8 is approved, the allowlist may additionally include only:

```text
backend/app/core/config.py
backend/app/db/legacy_mysql.py
backend/.env.example
backend/pyproject.toml
backend/uv.lock
```

Real `.env*` values remain forbidden. Authentication, permission and data-scope foundation files are not added to this allowlist; they must already exist through their own approved task.

Implementation sequence:

1. Confirm authentication/permission/data-scope and legacy connection prerequisites on latest `main`.
2. Define the Pydantic query, item, envelope metadata and error schemas without adding fields.
3. Implement the read-only repository with fixed select list, filters, data scope, pagination, order and timeout.
4. Implement service warning/error composition.
5. Register the permission-protected route and OpenAPI metadata.
6. Add mock/fixture tests and Markdown API documentation.
7. Run all backend and rule-pack validation gates.

No frontend file, old-system file, database schema or production configuration belongs to the implementation diff.

## 15. Implementation Stop Conditions

Stop and return to the Architect/Owner if:

- the Source Decision is no longer `READY_FOR_PRP` for the exact five fields;
- the PRP remains `Draft`, is unmerged or lacks owner approval;
- backend authentication, permission or data-scope enforcement is absent;
- no owner-approved isolated legacy readonly connection is available;
- implementation requires a second business table or any join;
- implementation requires `store_name`, `product_name` fallback or another excluded field;
- implementation requires a write, DDL, temporary table, migration, ORM model, mart/read model or external API;
- query performance cannot be bounded by pagination, offset cap and timeout;
- a real database connection or query-plan check is needed without separate explicit authorization;
- a secret, token, password, connection string or real `.env` value would need to be read or recorded;
- implementation would hard-code a role, trust a client-supplied data scope or expose an unauthenticated endpoint;
- the work would modify frontend, old-system, CI, deployment or production configuration;
- a dependency beyond one owner-approved MySQL driver appears necessary.

A stop condition does not authorize expanding the PRP.

## 16. Validation Gates for Later Implementation

The implementation task must run at least:

```bash
cd backend
uv run ruff check .
uv run mypy app tests
uv run pytest
cd ..
bash scripts/check-rule-pack.sh
git diff --check
git status --short --untracked-files=all
git diff --stat
```

Additional checks:

- OpenAPI includes the endpoint, response model and required metadata.
- No test opens a real network or database connection.
- No selected or serialized response item contains an excluded field.
- No repository path contains DML, DDL, `SELECT *`, dynamic sort SQL or an unbounded result set.
- No real credential, host, connection string or production record appears in the diff or test output.

The implementation task must not run Alembic because no schema change is allowed. It must not deploy or perform a real legacy smoke test without a separate owner-authorized task.

## 17. Rollback and Legacy Exit

### 17.1 Code rollback

The owner can revert the single API implementation PR. Because the task creates no database state, rollback requires no migration or data repair. Removing the route registration and product module restores the prior backend behavior.

### 17.2 Legacy readonly exit criteria

The temporary read path must be retired when these approved milestones are met:

1. Walmart Listing source verification is complete.
2. Lingxing local product is evaluated if actually needed.
3. The new-system standardized/master-data design has an approved Source Decision and PRP.
4. The synchronization task has an approved PRP and passes review.
5. The backend query switches to the approved new-system authoritative source.
6. The legacy product basic information query is disabled and removed.

No default dual read or dual write is allowed during transition. A cutover requires a separate PRP with reconciliation and rollback.

## 18. Owner Approval Checklist

- [ ] Confirm `Status` remains `Draft` until review is complete.
- [ ] Confirm the endpoint is `GET /api/v1/products/basic-information`.
- [ ] Confirm the only response item fields are `item_id`, `sku`, `msku`, `item_name` and `store_id`.
- [ ] Confirm `store_name`, `product_name` fallback and every listed business exclusion remain out of scope.
- [ ] Confirm `page_size` defaults to 20, is capped at 100 and calculated offset is capped at 10,000.
- [ ] Confirm first-stage exact filters are only `item_id` and `store_id`; `sku`/`msku` filters remain blocked pending owner-approved read-only query-plan/performance verification.
- [ ] Confirm no caller-selectable sorting; `platform` is an owner-approved fixed internal source constraint/order key, and the default order follows `platform`, `store_id`, `item_id`, `msku` without returning `platform`.
- [ ] Confirm `products.product_management.view` and backend-enforced `store_id` data scope.
- [ ] Confirm rows contain no synthetic identifier and SKU is not used as a unique key.
- [ ] Confirm warnings and freshness are returned under canonical `meta`.
- [ ] Confirm the legacy statement timeout defaults to 2 seconds and cannot exceed 5 seconds without a PRP update.
- [ ] Confirm runtime reads only `dim_product` through a dedicated Legacy Readonly Repository.
- [ ] Confirm no real database is used by implementation tests.
- [ ] Confirm no table, migration, ORM model, mart/read model, write path or external API is authorized.
- [ ] Confirm the authentication/permission/data-scope prerequisite must be delivered separately before implementation.
- [ ] Confirm the canonical response/request-ID prerequisite must be delivered separately before implementation.
- [ ] Choose and approve section 8 option 1 or option 2 for the legacy connection prerequisite.
- [ ] Confirm API documentation and tests are required for completion.
- [ ] After Architect Review PASS, change `Status` to `Approved`, then merge this PRP before implementation.

## 19. PRP Authoring Validation

This PRP-authoring branch creates only this file. It does not run backend tests because no backend code changed.

```bash
git status --short --untracked-files=all
git diff --check
bash scripts/check-rule-pack.sh
sed -n '1,260p' PRPs/phase-2a-product-basic-information-query-api.md
sed -n '261,520p' PRPs/phase-2a-product-basic-information-query-api.md
```

If `scripts/check-rule-pack.sh` reports the worktree `.git` pointer path as forbidden content, record it as the known worktree false positive and do not modify the script in this PRP.

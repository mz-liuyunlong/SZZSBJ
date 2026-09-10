# Product Management Backend MVP Source Decision

## 1. Decision Status

```text
Decision file: docs/data-sources/decisions/products-basic-information-query-decision.md
Decision updated: 2026-09-10
Decision owner: Project Owner
Source discovery status: Completed
OD-9 readonly DB inventory: Completed
Overall Decision State: READY_FOR_PRP
Contains NEED_OWNER_DECISION in approved MVP scope: No
Implementation authorized by this decision: No
Database access used for this update: No
Server access used for this update: No
External API used for this update: No
Approval PR: #40 (`ce423754`)
Implementation PR: #41 (`fab3aef`), merged
```

`READY_FOR_PRP` applies only to the Product Management Backend MVP scope defined below. It permits an interface PRP to be written and approved; it does not itself authorize code, a migration, a database connection, an external API call, or deployment.

## 2. Owner Decision Summary

The Project Owner approved the following authority model on 2026-09-10:

- `products`: `NEW_SYSTEM_OWNED`.
- `product_platform_listings`: `NEW_SYSTEM_OWNED`.
- The new system is the runtime authority for manually maintained product master data and manually maintained platform/store/MSKU relationships in this MVP.
- `old-system/**` remains read-only historical evidence and is not a runtime data source.
- Walmart, Amazon, TEMU, Lingxing and Feishu do not participate in the MVP write path.
- Manual creation and correction must go through the approved Product Management API. Direct database writes are prohibited.

This decision supersedes the earlier legacy-read and external-ingestion-first runtime proposals for this narrow manual-data MVP. It does not erase the prior discovery evidence or authorize any migration from the old system.

## 3. Scope and Grain

### 3.1 `products`

One row represents one company-internal SKU product.

- `products.id` is the new-system internal `product_id`.
- `products.sku` is the company-internal SKU and is required and unique in this MVP.
- `products.product_name` is required.
- One product may have many platform/store/MSKU listing relationships.
- Category, product type, status, grade, purchase price, customs names and material names are manually maintained attributes in this MVP.

Approved business fields:

```text
id
sku
product_name
category
product_type
status
grade
purchase_price
declared_cn_name
declared_en_name
material_cn
material_en
remark
created_at
updated_at
deleted_at
```

`purchase_price` is sensitive monetary data. The implementation PRP must pair it with a required `currency_code` whenever an amount is present, use `Decimal` / `Numeric(18,4)`, reject binary float, and document the field permission boundary. The currency companion is a mandatory project contract, not approval for FX conversion or price calculation.

### 3.2 `product_platform_listings`

One row represents one product SKU's selling relationship for one platform, one store name and one MSKU.

- `id` is the new-system internal listing-relation identifier.
- `product_id` references `products.id`.
- `platform` uses the MVP controlled values `walmart`, `amazon`, `temu`, or `other`.
- `store_name` is a required manual string in this MVP. A normalized store table is deferred.
- `msku` is the platform/store selling SKU.
- `external_listing_id` is nullable and remains distinct from internal identifiers.
- `listing_url`, `listing_status`, `fulfillment_type`, `wfs_fee`, and `shipping_cost` are manual attributes or reserved future-sync fields.
- The approved uniqueness boundary is `(platform, store_name, msku)`.

Approved business fields:

```text
id
product_id
platform
store_name
msku
external_listing_id
listing_url
listing_status
fulfillment_type
wfs_fee
shipping_cost
created_at
updated_at
deleted_at
```

`wfs_fee` and `shipping_cost` are sensitive monetary data. The implementation PRP must pair them with `currency_code` whenever either amount is present, use `Decimal` / `Numeric(18,4)`, reject binary float, and document their field permission boundary. This does not approve fee calculation, validation, reconciliation, or FX conversion.

## 4. Dataset Classification

| Dataset | Authority | Classification | Approved writer | Approved reader | Short-term strategy | Long-term boundary |
|---|---|---|---|---|---|---|
| `products` | New-system Product Management module | `NEW_SYSTEM_OWNED` | Product Management API service only | Product Management API repository/service | Create and edit manual product master records in PostgreSQL | Remains core authority unless a later Source Decision changes ownership |
| `product_platform_listings` | New-system Product Management module | `NEW_SYSTEM_OWNED` | Product Management API service only | Product Management API repository/service | Create and edit manual platform/store/MSKU relations in PostgreSQL | External synchronization may propose or publish changes only through a separately approved ingestion and ownership boundary |

No approved MVP dataset uses `READ_LEGACY_TEMPORARILY`, `REBUILD_SYNC`, `MIGRATE_ONCE`, `ARCHIVE_ONLY`, or `NEED_OWNER_DECISION`.

## 5. Manual Write Boundary

Allowed after a separate Approved implementation PRP and implementation Prompt:

- Create and edit `products` through Product Management API endpoints.
- Create and edit `product_platform_listings` through Product Management API endpoints.
- Correct MVP data through validated `PATCH` requests.

Not allowed:

- Direct SQL or direct database editing by users, frontend code, AI, scripts, or operators.
- Excel or other batch import.
- Delete endpoints, purge, restore, archive workflows, or reuse of soft-deleted identities.
- Old-system migration or automatic external synchronization.
- Silent overwrite by a future external feed.

`deleted_at` is reserved and remains null in this MVP. Full immutable audit history, version restore and deletion policy require separate PRPs. Until then, correction through authenticated and authorized `PATCH` is the only rollback mechanism.

## 6. Data-Layer Exception and Future Ingestion

The Project Owner approved a narrow exception to the normal Source Registry -> RAW -> ingestion -> Core -> read-model sequence:

- Human-maintained product master data may be written directly through the Product Management service to the `products` core table.
- Human-maintained platform/store/MSKU relationships may be written directly through the Product Management service to the `product_platform_listings` core table.

The exception does not apply to:

- external API synchronization;
- Walmart, Amazon, TEMU, Lingxing or Feishu collection;
- ERP or spreadsheet import;
- old-system migration or backfill;
- reconciliation publication;
- derived marts or read models.

Those flows still require Source Registry, RAW evidence, ingestion/standardization, lineage, data-quality gates and an approved publish-to-Core boundary. A future external feed must not silently become a second authority or overwrite manual values.

## 7. Legacy and External Source Boundary

- `old-system/**` is `legacy_reference` only. No new-system runtime import, connector, query, fallback or dependency is approved.
- The OD-9 report at `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md` remains historical evidence about legacy structure and data quality; it is not a runtime contract.
- No production data is migrated by this decision.
- No Walmart, Amazon, TEMU, Lingxing or Feishu endpoint is approved for invocation.
- The previously approved validation order remains Walmart Listing first, then Lingxing local product if needed, but only in later separately approved Source Discovery/ingestion work.

## 8. API and Permission Boundary for the PRP

The subsequent PRP may define only these endpoints:

```text
GET    /api/v1/products
GET    /api/v1/products/{product_id}
POST   /api/v1/products
PATCH  /api/v1/products/{product_id}
GET    /api/v1/products/options
GET    /api/v1/products/{product_id}/listings
POST   /api/v1/products/{product_id}/listings
PATCH  /api/v1/products/{product_id}/listings/{listing_id}
```

Owner-approved permission keys:

```text
products:read
products:create
products:update
product_listings:read
product_listings:create
product_listings:update
```

Rules:

- Every endpoint is protected and enforced by the backend; role names must not be hardcoded.
- The supplied read/update permission is the approved field boundary for all MVP fields in its resource, including sensitive monetary fields. A later split into finer field permissions requires a separate permission decision.
- Future resource-level data scope is `platform + store_name` for listing relationships.
- The current shared scope helper is `store_id` based and must not be misrepresented or reused as `store_name` scope.
- The implementation PRP must define a product-module scope seam that fails closed when no trusted provider is present. Full RBAC and provider integration remain out of scope.
- Repository code never performs permission decisions and never commits.

## 9. Evidence and Historical Decisions

Evidence retained from the completed Source Discovery and OD-9 inventory:

- The legacy product page and endpoint combined product identity with cost, status, sales, inventory and advertising data. That legacy shape is not copied.
- Legacy SKU was nullable and non-unique in the observed inventory, so it remains unsuitable as a global cross-system identity. The MVP's required unique internal SKU is a new-system business rule for new manual records, not a claim about legacy data.
- Legacy `store_name` authority was unresolved. The MVP's manual `store_name` is new-system-owned relationship data and does not adopt the legacy multi-table fallback.
- OD-9 did not prove legacy freshness or external API availability.

The former OD outcomes are superseded only where the new manual-authority decision changes the runtime strategy. Historical evidence remains available in Git history and the OD-9 report; it must not be presented as current production truth.

### 9.1 Prior OD resolution under the new MVP decision

| OD | Current resolution |
|---|---|
| OD-1 | Superseded. No legacy runtime read is approved; the two MVP datasets are `NEW_SYSTEM_OWNED`. |
| OD-2 | Superseded for this MVP. `product_name` is required manual new-system data; no `item_name` or legacy `product_name` fallback is used. |
| OD-3 | Superseded for this MVP. Listing `store_name` is manually entered new-system-owned relationship data; no legacy store-name authority or fallback is adopted. |
| OD-4 | Preserved as historical DQ evidence only. New manual `products.sku` is required and unique within this new-system table; this does not reclassify legacy SKU as a global identity. MSKU remains listing-scoped. |
| OD-5 | Partially superseded. Manual `category` is approved; `brand` remains out of scope. No external taxonomy is implied. |
| OD-6 | Partially superseded. Manual product `status` is approved; Walmart publish status remains out of scope and requires a separate decision. |
| OD-7 | Partially superseded. Manual `product_type` is approved; CS-prefix inference and lifecycle semantics remain prohibited. |
| OD-8 | Partially superseded. API-only manual product/listing create and edit are approved; store aliases, SKU-mapping automation, imports and direct database corrections remain deferred. |
| OD-9 | Completed. The report remains legacy evidence only and creates no runtime dependency. |
| OD-10 | Preserved as a future validation order only: Walmart Listing first, then Lingxing local product if needed; no API call or sync is approved. |

## 10. Explicitly Out of Scope

- Frontend work or connecting the existing no-API page to this API.
- Excel, CSV or other import/export.
- Legacy MySQL runtime reads.
- Old-system data migration, reconciliation execution or backfill.
- Production database connection or migration execution.
- External API calls or platform synchronization.
- Walmart, Amazon, TEMU, Lingxing or Feishu clients.
- Sales, advertising, inventory, profit, settlement or refund calculations.
- Price or fee calculation, validation, FX conversion or financial reconciliation.
- Celery, Redis, workers, schedulers or background jobs.
- DELETE endpoints, restore, archive or purge workflows.
- Full audit/version rollback.
- Full RBAC or production data-scope provider integration.
- A normalized store table, mart or read model.
- CI PostgreSQL provisioning.

## 11. Risks and Stop Conditions

Stop and request a new owner decision if:

- the implementation needs a field, endpoint, table or writer outside this decision;
- an external source, legacy database, file import or migration is proposed;
- the implementation cannot enforce the approved uniqueness and foreign-key boundaries;
- sensitive monetary fields cannot be protected and paired with currency;
- a scope implementation would default to allow or would pretend that `store_id` equals `store_name`;
- delete, restore, audit history, bulk operations or direct database writes are required;
- a second authority or default dual-write path is proposed;
- a real database, server, secret, CI service or deployment change is required without separate explicit authorization.

## 12. Approval Record and Next Step

```text
Approved by: Project Owner
Approved date: 2026-09-10
Approval type: source authority and PRP-entry authorization
Approval scope: Product Management Backend MVP only
```

All datasets in the approved scope have executable classifications and no unresolved `NEED_OWNER_DECISION`; therefore the overall state is `READY_FOR_PRP`.

`PRPs/product-management-backend-mvp.md` was approved in PR #40 (`ce423754`), and its bounded implementation was merged in PR #41 (`fab3aef`). This records implementation evidence only: it does not authorize frontend integration, production migration execution, legacy migration/runtime reads, external API synchronization, mart/read-model creation, DELETE, full RBAC or any other deferred scope.

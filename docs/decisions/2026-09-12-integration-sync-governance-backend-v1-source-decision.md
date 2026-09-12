# Source Decision: Integration Sync Governance + Lingxing SKU Detail Foundation V1

```text
Decision Date: 2026-09-12
Decision Owner: Project Owner
Status: APPROVED_FOR_IMPLEMENTATION
Source Decision Status: READY_FOR_PRP
Implementation Authorized: Yes
Implementation Branch: feat/integration-sync-governance-backend-v1
Authorized PRP: PRPs/integration-sync-governance-backend-v1.md
Real Lingxing API Authorization: No
```

## Decision

The Project Owner authorizes backend implementation of `PRPs/integration-sync-governance-backend-v1.md` on `feat/integration-sync-governance-backend-v1`. This authorization is limited to the exact PRP scope and does not mark any capability implemented.

If implementation requirements differ from the PRP or this decision, implementation must stop and return to the Owner.

## Source authority and data flow

| Object | Decision |
|---|---|
| Governance/control-plane data | `NEW_SYSTEM_OWNED` |
| Local ProductList capture | Local L1/L2 evidence and `ARCHIVE_ONLY` artifact outside Git |
| ProductList identity observations | Lingxing-derived `REBUILD_SYNC`; `productList.data.id` maps to `lingxing_sku_id` |
| SKU detail foundation | Lingxing-derived `REBUILD_SYNC` schema/parser foundation using synthetic fixtures only |
| DWS values | Rebuildable new-system calculations from approved DWD structures |
| Existing Product Core | Remains `NEW_SYSTEM_OWNED`; no Lingxing overwrite or SKU-string inference |

## Authorization boundaries

### Real provider calls

Real Lingxing API authorization is **No**. This stage must not request a Token or call ProductList or batchGetProductInfo. Real batchGetProductInfo work requires later official interface evidence and a separate Owner authorization.

### Local RAW import

Local RAW importer implementation is authorized. It may read the recorded ProductList RAW directory as input to a confirmed local PostgreSQL import. It must verify the manifest/checksums, avoid printing payload content, and must not commit RAW JSON or archives. Production database access and production migration are not authorized.

### Data-layer table naming

The following prefixes are approved as project data-layer design, not ad hoc naming exceptions:

| Prefix | Layer |
|---|---|
| `gov_` | Governance and control plane |
| `ods_` | RAW/ODS layer |
| `dwd_` | Detail standardized layer |
| `dws_` | Service/reusable calculated layer |
| `ads_` | App-serving API DTO/view layer |

### API paths

This module follows the existing project `/api/...` routing convention. It does not force a `/v1` prefix. Any future unified API-versioning change requires a separate PRP decision.

### Account scope

`source_account_ref` is a non-secret logical data-source/account-scope identifier. It must never contain credential or authentication material. Local import may use the non-secret placeholder `default`; future multi-account operation uses non-secret logical account refs. Protected APIs must continue to fail closed until a trusted scope provider supplies allowed refs.

### batchGetProductInfo contract

Only the skeleton, mock transport boundary, synthetic fixture parser, and `id_batch_page` work-item foundation are authorized. No real call or unverified real request parameter is authorized.

The approved identity rules are:

- `productList.data.id = lingxing_sku_id`.
- `batchGetProductInfo.data.sku = lingxing_sku_code`.
- batchGetProductInfo work is modeled as bounded `id_batch_page` batches.

Actual request parameters, response cardinality, provider batch limits, rate limits, retry behavior, and interoperability require official evidence and separate Owner authorization before any real call.

### Customs and logistics currency

- `data.bg_customs_import_price` maps to `customs_declared_unit_price`.
- `customs_declared_currency` is nullable; if provider currency is absent, it is stored as `NULL` and no currency is inferred.
- `purchase_cost_cny` is explicitly a CNY purchase cost.
- `us_first_leg_currency` comes only from `data.product_logistics_relation.US_currency`.
- No FX conversion or assumed currency is authorized.

## Registry state

The implementation task, related API/storage/flow entries, and backend module are `approved_for_implementation`. They must not be marked `implemented` until implementation is merged with validation evidence. Real Lingxing calls remain blocked until separate authorization.

## Explicitly not authorized

- Frontend or admin-frontend changes.
- old-system reads, runtime dependencies, or changes.
- Real Lingxing, Token, ProductList, or batchGetProductInfo requests.
- RAW JSON/archive commits or payload output.
- Production database access, production migrations, deployment, or Git publishing.

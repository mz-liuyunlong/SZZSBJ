# Lingxing / Walmart API Contract Inventory

Status: repository evidence inventory; not provider verification, implementation approval, or call authorization
Generated from repository sources: 2026-09-14

## Purpose and boundary

This inventory reconciles repository-held Lingxing and Walmart-related contract evidence. It is documentation-only. It does not authorize an external request, credential use, database access, migration, synchronization, or implementation. Legacy material is read-only evidence; normalized CSV files are derived indexes rather than official provider authority.

No request or response example values are copied. The inventory contains only interface metadata, field names/types, evidence paths, classifications, and redacted shapes.

## Evidence order

1. Explicit repository governance: `do-not-use.md`, deleted-interface index, Data Interface Registry.
2. Repository legacy Markdown snapshots under `old-system/source/docs/lingxing/`.
3. Normalized interface/request/response CSV indexes.
4. Draft module/data maps, used only for target-module hints.

`old-system/source/docs/lingxing-api.json` is HTML content despite its filename and is not treated as machine-readable JSON contract evidence.

## Classification rules

- `READY_FOR_PRP`: path, method, request parameters, and response fields are structurally present; the interface is not deleted, side-effecting, or explicitly non-Walmart. This means planning may begin, not that a real call is approved.
- `PARTIAL_CONTRACT`: path and method exist, but request or response evidence is incomplete.
- `PROVIDER_CONTRACT_MISSING`: no usable repository contract evidence exists.
- `CONTRACT_SOURCE_CONFLICT`: legacy Markdown and normalized evidence disagree on path or method.
- `DO_NOT_USE`: retained index entry is write/side-effecting and falls under the repository prohibition policy.
- `DELETED`: entry is in `normalized/deleted_interfaces.csv`.
- `NOT_WALMART`: retained entry is explicitly dedicated to a non-Walmart platform.
- `NEED_OWNER_DECISION`: evidence does not support an automatic classification and business selection is required.

具有写入或副作用语义的接口，即使契约字段完整，也不得标记为 `READY_FOR_PRP`。以下接口默认应为 `DO_NOT_USE` 或 `NEED_OWNER_DECISION`，除非已有单独 Owner Decision：

- `create` / `update` / `delete` / `merge` / `split`
- `refund` / `cancel` / `submit` / `approve`
- `recalculate` / `generate` / `weighing`
- task creation
- order mutation
- shipment mutation
- inventory mutation
- ad mutation
- finance mutation

Risk is a single primary code chosen by precedence: source conflict, exclusion status, missing request, missing response, authentication verification, rate limit, pagination, then none. Secondary uncertainty remains in notes and snapshots.

## Totals

| Metric | Count | Interpretation |
|---|---:|---|
| Total indexed interfaces | 664 | Retained plus deleted normalized indexes |
| Retained normalized interfaces | 329 | Present in `interfaces.csv`; not equivalent to approved |
| Explicit Walmart retained interfaces | 32 | Platform text explicitly names Walmart/WFS |
| Deleted interfaces | 335 | Must not enter implementation without re-evaluation |
| Deleted / do-not-use / non-Walmart | 471 | Excluded by current classification |
| Matching legacy Markdown evidence | 17 | Interface-level repository snapshot found by document basename |
| Normalized-CSV-only evidence | 647 | No matching interface-level legacy Markdown in this checkout |
| Structurally complete (`READY_FOR_PRP`) | 186 | PRP planning only; no real-call authorization |
| Structurally incomplete/conflicting | 7 | Partial, missing, conflicting, or owner-decision status |
| High priority (`P0` + `P1`) | 426 | Priority copied from normalized indexes |
| Risk-coded interfaces | 664 | Primary risk is not `NONE` |

## Status distribution

| Contract status | Count |
|---|---:|
| `READY_FOR_PRP` | 186 |
| `PARTIAL_CONTRACT` | 7 |
| `PROVIDER_CONTRACT_MISSING` | 0 |
| `CONTRACT_SOURCE_CONFLICT` | 0 |
| `DO_NOT_USE` | 136 |
| `DELETED` | 335 |
| `NOT_WALMART` | 0 |
| `NEED_OWNER_DECISION` | 0 |

## Primary risk distribution

| Risk code | Count |
|---|---:|
| `NONE` | 0 |
| `MISSING_REQUEST_PARAMS` | 7 |
| `MISSING_RESPONSE_FIELDS` | 0 |
| `AUTH_UNKNOWN` | 186 |
| `RATE_LIMIT_UNKNOWN` | 0 |
| `PAGINATION_UNKNOWN` | 0 |
| `FIELD_CONFLICT` | 0 |
| `SOURCE_CONFLICT` | 0 |
| `RAW_ONLY` | 0 |
| `DO_NOT_USE` | 136 |
| `DELETED` | 335 |
| `NOT_WALMART` | 0 |


## High-priority review queue

The initial redacted snapshots are under `docs/integrations/lingxing/contracts/`. They cover ProductLists/ProductInfo, legacy non-Walmart/deleted comparators, store/account evidence, order/inventory, Walmart payment and settlement, Walmart advertising, and WFS/inbound transport. The source map identifies remaining gaps, including the absence of a repository contract for a standalone WFS fee endpoint.

## Usage guardrails

- Use `API_CONTRACT_INVENTORY.csv` for filtering and reconciliation.
- Use `API_CONTRACT_SOURCE_MAP.md` for domain-level review and missing-evidence triage.
- A `READY_FOR_PRP` row may be cited by a future PRP, but real provider traffic still requires official evidence, data-source decision, Owner authorization, default-off transport, and tests.
- `DELETED`, `DO_NOT_USE`, and `NOT_WALMART` rows cannot be revived by this inventory. A row may only leave `DO_NOT_USE` through the exception flow in `docs/integrations/lingxing-walmart-openapi/do-not-use.md` with a written Owner Decision.

## Owner-approved exceptions

| Key | Interface | Before | After | Owner decision | Boundary |
|---|---|---|---|---|---|
| `LX-4B9473A2D2E1` | 查询收货单列表 `/erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/getOrderList` | `DO_NOT_USE` | `READY_FOR_PRP` (risk `AUTH_UNKNOWN`) | mz-liuyunlong, 2026-09-18, 方案 A, `docs/data-sources/decisions/pmc-purchase-board-decision.md` | Read-only per `official_verified_interfaces.csv`; PRP planning only; not provider verification; not real-call authorization; production use requires separate authorization |
- Never infer authentication, account scope, rate limits, pagination, side effects, or field meaning from a similar endpoint.

## Source set

- `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv`
- `docs/integrations/lingxing-walmart-openapi/normalized/deleted_interfaces.csv`
- `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv`
- `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv`
- `docs/integrations/lingxing-walmart-openapi/api-verification-status.csv`
- `docs/integrations/lingxing-walmart-openapi/normalized/module_mapping.csv`
- `docs/data-sources/lingxing-walmart-api-to-system-data-map-draft.csv`
- `docs/integrations/lingxing-walmart-openapi/README.md`
- `docs/integrations/lingxing-walmart-openapi/do-not-use.md`
- `old-system/source/docs/lingxing/**/*.md` (read-only)
- `old-system/source/docs/lingxing-api.json` (identified as HTML; not parsed as JSON evidence)

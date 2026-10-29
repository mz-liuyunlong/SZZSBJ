# Walmart SCF backend entrypoint: fail-closed rollout

This PR does **not** activate any production API, API writes, schedule, RAW capture,
database persistence or migrations. Existing nine-store SCF `stable` GET
verification is not an approval for all marketplace operations.

## Configuration (all absent by default)

- `SZZSBJ_WALMART_SCF_READ_ENABLED=1`: explicit API feature gate.
- `SZZSBJ_WALMART_SCF_STORE_ID_MAP`: reviewed JSON map from a verified **Lingxing store_id** to one Walmart store code, e.g. `{"110711149541688320":"HK2613"}`. Do not infer this mapping from display names or user input. Values must be unique.
- `SZZSBJ_WALMART_SCF_APPROVED_READ_KEYS`: explicit comma-separated **reviewed** GET operation IDs. Default none. Both the main server and each cloud SCF must independently approve a key. The existing cloud SCF approval documented so far is `wfs_inventory`; do not enable other keys yet.
- `SZZSBJ_WALMART_SCF_CVM_ROLE`: approved CVM runtime identity role.
- `SZZSBJ_WALMART_SCF_TARGET_ROLE_ARN`: approved cross-account Invoke role ARN.
- `SZZSBJ_WALMART_SCF_TASKS_ENABLED=1`: separate on-demand worker feature gate.
- `SZZSBJ_WALMART_SCF_TASK_ACCOUNT_SCOPE`: operator-reviewed account references for the worker, not an HTTP parameter.
- `SZZSBJ_WALMART_SCF_TASK_OPERATION=wfs_inventory`: explicit operation gate.
- `SZZSBJ_WALMART_SCF_WFS_ITEMS_PATH=inventory`: approved payload list path; must first be verified against actual SCF response schema.

## HTTP endpoints

- `POST /api/integrations/walmart-scf/read` accepts `source_account_ref`, `store_id`, `operation`, `params`. This is **only a request envelope**; outbound contracts are GET-only.
- `GET /api/integrations/walmart-scf/wfs-inventory?source_account_ref=...&store_id=...&limit=1`

Both require `integrations:execute`, verified `require_source_account_scope`, explicit RBAC `store` grant, and an active matching Walmart store in `dim_lingxing_stores`. Unknown or absent mappings, disabled switches, unapproved operations or cross-account access fail without dispatch.

## Pagination

`collect_offset_pages` is a bounded, all-or-nothing offset implementation (maximum 20 pages, 2,000 records); caller provides a verified items path. It does not guess response schema, retry ambiguous requests or silently return incomplete pages. Other contracts may require cursor-mode or a different response envelope, which must be separately reviewed and tested. Never use the generic pagination helper on an unapproved API or guessed list path.

## Celery

`walmart_scf.read_inventory_count` is registered but **never scheduled** by Beat. It requires its own gate, its own trusted account allowlist, and an approved list path; it performs only a bounded GET scan. It does **not** persist payloads or produce broker results. To implement durable synchronization, add a separate reviewed work-item state machine, raw retention/DQ/idempotency checks and database write authorization.

## Review gates before merging/enabling

1. Validate actual `source_account_ref` ↔ store mapping against IAM governance registry (no guessed equivalence).
2. Verify each cloud SCF has reviewed GET contracts and per-store approval.
3. Review returned data for PII handling and least-privilege endpoint access.
4. Run CI (Ruff, tests), ensure no secret logging and cross-store negative cases.
5. Do not deploy `main` solely to enable this feature: any deployment requires a separate production change approval.

The Lingxing source account `primary` is shared across nine Walmart stores: it must not be substituted for a unique store identity. SCF routing is keyed by store_id and verifies the approved code matches the persisted store-name prefix. Existing production store grants are absent, so the new interface intentionally denies every store until an audited operator grants the appropriate RBAC scopes. The Celery task also requires `SZZSBJ_WALMART_SCF_TASK_STORE_SCOPE`; the schedule remains disabled.

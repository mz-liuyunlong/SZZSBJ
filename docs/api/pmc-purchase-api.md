# PMC Purchase Board API

## 1. Status and boundary

Gate 3 read contract for the PMC purchase board (PRP `PRPs/pmc-purchase-board.md` §7.1–7.4,
business rules `docs/business-rules/pmc-purchase-rules.md` v4). Routes read only the DWS
tables written by the Gate 3 refresh (`dws_purchase_board`, `dws_purchase_sku_cycle`,
`dws_purchase_pending`), the DWD plan table (`dwd_purchase_plan`, S2 drill-down only), the
rule table and `dim_lingxing_stores`. They never request Lingxing and never read ODS / RAW.
The single write route (PRP §7.5, SKU cycle override) appends to
`manual_purchase_cycle_override` and rebuilds the account's DWS; it never writes DWD / ODS /
RAW. Merging this contract does not authorize any production migration, DWD publish or DWS
refresh; those remain Owner-authorized runbook steps.

Path prefix is `/api/pmc/purchase` (repository convention, no `v1`; Owner 2026-09-21).

All responses use:

```json
{ "success": true, "data": {}, "error": null, "meta": {}, "request_id": "..." }
```

`meta` = `{ source: "new_system_postgresql", source_objects: [...], freshness_at, rule_version, page, page_size, total }`
where `freshness_at` is the newest `calculated_at` among the returned DWS rows and
`rule_version` the `rule_purchase_thresholds` version those rows were calculated with.

## 2. Authentication, permissions, and scope

| Route | Permission |
|---|---|
| all GET routes below | `pmc:purchase:read` |
| `POST /sku-cycles/{sku}/overrides` | `pmc:purchase:override` |

Plus the trusted `source_account_ref` scope (`require_source_account_scope`, fail closed).
The read-only preview principal may call these GET routes under `/api/pmc/` (auth.py preview
prefix); the POST route is **not** reachable through preview (the preview principal never
carries `pmc:purchase:override`), so until a real login principal exists (Gate 4 dependency)
it can only be exercised with a full principal. Money is serialized as a decimal
string with a sibling `currency_code`; dates are Beijing calendar dates.

## 3. Endpoints

### `GET /api/pmc/purchase/board` — board list (PRP §7.1)

One row per purchase-order line × plan (merged lines already split by plan quantity, rules
§5.2). Purchase plans that have not become an order are **not** rows here (Rocky
2026-09-23); see `/plans/pending`.

Query: `page` (≥1), `page_size` (1–200), `sort` (`order_date_desc` default | `order_date_asc` |
`overdue_days_desc` | `arrival_date_desc` | `amount_desc`), `owner_uid[]`, `store_id[]`,
`status[]` (`s2` 待下单 | `s3` 已下单未到货 | `s4` 部分到货 | `overdue` 任一逾期 | `s9` 已到货 |
`s0` 作废 | `unattributed` 未归属店铺), `search_type` (`sku|item_id|gtin|msku|order_sn`) +
`search_values[]` (batch; comma / whitespace separated values are split),
`item_id_source[]`, `order_date_from/to`, `qty_min/max` (on `quantity_allocated`),
`price_min/max` (on `unit_price`), `wfs_not_ready`, `today_followup` (overdue or due today).
Unknown parameters and inconsistent ranges are `422 VALIDATION_ERROR`.

Row fields: `purchase_order_sn, order_item_id, plan_sn, plan_sns[], order_status,
stage{stage_code, stage_start, stage_start_estimated, threshold_days, due_date, overdue_days,
overdue_kind(purchase|arrival|null), alert_due_since}, store{id,name,attributed}, sku,
product_name, item_id{item_id, source, source_ref, matched_at, match_status, msku, gtin,
fulfillment_type, wfs_not_ready}, owner{uid,name}, quantity_total, quantity_allocated,
quantity_received, progress_ratio, remaining_quantity, order_date, order_create_date,
plan_create_date, arrival_date, arrival_receipt_order_sn, purchase_cycle_days,
approval_cycle_days, sku_cycle{value_days, source, sample_count, unstable}, unit_price,
amount_allocated, amount_total, currency_code, calculated_at`.

`overdue_kind` keeps the two overdue notions apart: `purchase` = 待采购超时 (stage `S2`),
`arrival` = 到货逾期 (stage `S3`/`S4`). Rows with `store.attributed = false` (sid = 0) never
carry an overdue value (rules §1.3).

### `GET /api/pmc/purchase/board/summary` — cards (PRP §7.2)

Same filters as the list (no paging). Returns `awaiting_arrival_orders` (S3+S4, distinct
orders), `arrival_overdue_orders`, `purchase_overdue_orders` (S2 orders), `purchase_overdue_plans`
(plans status = 2 not yet ordered, past `s2_pending_days`; store filter applies),
`average_purchase_cycle_days_90d` (orders arrived in the last 90 days, one value per order),
`month_purchase_amount[]` (`amount_allocated` of lines ordered this month, per currency, no
FX), `unstable_sku_count`, `itemid_pending_lines`, `wfs_not_ready_lines`,
`unattributed_store_lines`, `as_of`.

### `GET /api/pmc/purchase/orders/{order_sn}` — detail (PRP §7.3)

Header (status, dates, quantities, arrival, money, stage) + `lines[]` (board rows of the
order) + `receipts[]` (`receipt_order_sn`, `is_arrival_receipt` — receipt numbers only; line
quantities stay in ODS and are not exposed) + `plans[]` (plan chain from `dwd_purchase_plan`)
+ `sku_cycles[]` (the order's SKUs, see §7.4). `404 NOT_FOUND` when the order has no board row
inside the caller's account scope.

### `GET /api/pmc/purchase/sku-cycles?sku=…` — SKU actual purchase cycle (PRP §7.4)

`sku[]` required (1–100, batch). Per SKU: `value_days, source (samples | baseline_mix |
lingxing_default | no_baseline), sample_count, baseline_days, baseline_set_on,
lingxing_default_days, unstable, range_days, samples[] (purchase_order_sn, order_date,
arrival_date, cycle_days, used, exclusion auto_short|manual|before_baseline|outside_window),
rule_version, calculated_at`. Requested SKUs without a DWS row are listed in `data.missing`.

### `GET /api/pmc/purchase/plans/pending` — 待采购计划 (S2 card drill-down)

Purchase plans with Lingxing `status = 2` (approved, awaiting purchase) that do not yet
appear on any purchase-order line. Query: `page`, `page_size`, `store_id[]`, `overdue_only`,
`search_values[]` (plan_sn or SKU). Fields: `plan_sn, plan_status, plan_create_date,
pending_since, pending_since_estimated (true until the incremental sync has observed the
pending state), pending_days, overdue_days (vs `s2_pending_days`; 0 for unattributed
stores), store, sku, product_name, quantity_plan, remark_item_id`; `data.threshold_days`
echoes the rule value. Plans in 待审批 (status 121) are never listed.

### `GET /api/pmc/purchase/sku-cycles/{sku}/overrides` — 修正记录

All manual corrections of the SKU, newest first, including closed ones (`is_active=false`,
`effective_to` set). Fields: `id, source_account_ref, sku, kind, purchase_order_sn,
value_days, value_date, before{…}, after{…}, reason, operator_ref, request_id,
effective_from, effective_to, is_active, created_at`.

### `POST /api/pmc/purchase/sku-cycles/{sku}/overrides` — 交期人工修正 (PRP §7.5)

Body: `{ source_account_ref, kind: exclude | restore | arrival_date | baseline,
purchase_order_sn?, value_days?, value_date?, reason, request_id? }`.

| kind | required | rule |
|---|---|---|
| `exclude` | `purchase_order_sn` | the order must be one of the SKU's arrived samples (`dws_purchase_sku_cycle.samples_json`) → `422 PURCHASE_ORDER_NOT_A_SAMPLE` |
| `restore` | `purchase_order_sn` | the order must currently be manually excluded → `422 PURCHASE_ORDER_NOT_EXCLUDED` |
| `arrival_date` | `purchase_order_sn`, `value_date` | `value_date ≥` the order's order date → `422 ARRIVAL_DATE_BEFORE_ORDER_DATE` |
| `baseline` | `value_days` | closes the previous active baseline (`effective_to = now`, `is_active = false`) and returns its id in `replaced_override_id` |

`reason` must be non-blank. `source_account_ref` must be inside the caller's account scope
(`403 DATA_SCOPE_DENIED`). `request_id` defaults to the request's `X-Request-ID`; the same
`(account, sku, request_id)` submitted again returns the first record with
`idempotent_replay = true` and writes nothing.

Effect: one new append-only row (`before` = the SKU cycle and sample state at the time,
`after` = the correction, `operator_ref` = principal) and a rebuild of the account's three
DWS tables in the same transaction (rolled back together on failure). Response: `override`,
`replaced_override_id`, `idempotent_replay`, `sku_cycle` (after the rebuild), and
`refresh_board_rows`. `404 NOT_FOUND` when the SKU has no DWS cycle row in scope. Undo is
always a newer record (`restore`, or a new `baseline`); records are never deleted
(`docs/MANUAL_OVERRIDE_BOUNDARY_RULES.md`). There is no manual ItemID route (Owner
decision 2026-09-21, #144).

## 4. Errors

`401 UNAUTHORIZED`, `403 FORBIDDEN` (permission), `403 DATA_SCOPE_DENIED` (no trusted account
scope), `404 NOT_FOUND` (order detail), `422 VALIDATION_ERROR`, `500 INTERNAL_ERROR` — all
in the error envelope.

## 5. Source map

| Response data | Source object | Produced by |
|---|---|---|
| board rows, stage, ItemID attribution, owner, listing fields, money | `dws_purchase_board` | G3-D refresh from `dwd_purchase_*` + `dim_lingxing_stores` + `dim_walmart_listings` + `dwd_lingxing_sku_product_info_current` + succeeded-run ODS receipt lines |
| SKU cycles | `dws_purchase_sku_cycle` | G3-D refresh (`calculations.compute_sku_cycle`, manual overrides applied) |
| pending plans | `dwd_purchase_plan` (status 2, not on any board row) | G3-B publisher |
| thresholds | `rule_purchase_thresholds` (active version) | G3-A seed / later rule PRs |
| manual corrections | `manual_purchase_cycle_override` (append-only) | G3-F override route; consumed by the G3-D refresh |

## 6. Tests

`backend/tests/modules/pmc_purchase/test_router.py` (OpenAPI, fail-closed auth/scope,
envelope/meta, validation) and `test_read_service.py` (filters, sorting, batch search,
summary, detail, SKU cycles, pending plans on DWS rows produced by the refresh), and
`test_overrides.py` (exclude / restore / arrival_date / baseline end-to-end with the DWS
rebuild, idempotent replay, validation, permission and OpenAPI).

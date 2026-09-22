# Production PMC Purchase Sync Runbook

Status: **go-live window executed 2026-09-22** (see execution log). Further windows still require the Owner's written authorization per run; nothing here is scheduled. Code for Gate 2 is merged (PR #128 contracts,
#129 ODS migration `20260919_0016`, #130 governance bootstrap, #131 handlers, this PR
runner). Merging any of them authorizes nothing. Every step below is a production action
that the Project Owner performs personally, one at a time, after writing an execution
record into the log at the end of this file. No step may run without its record.

Source decision: `docs/data-sources/decisions/pmc-purchase-board-decision.md`
(`READY_FOR_PRP`, Owner approval 2026-09-18, 方案 A). PRP: `PRPs/pmc-purchase-board.md`.

## Fixed boundary

- Interfaces: `purchasePlanList` (`getPurchasePlans`), `purchaseOrderList`,
  `purchaseReceiptOrderList` (`PurchaseReceiptOrder/getOrderList`). All read-only.
- Tables this runbook may write: `gov_integration_sync_runs`, `gov_integration_sync_run_work_items`,
  `gov_parse_jobs`, `gov_data_lineage`, `ods_api_raw_blobs`, `ods_api_raw_request_refs`,
  `ods_lingxing_purchase_plans`, `ods_lingxing_purchase_orders`, `ods_lingxing_purchase_order_items`,
  `ods_lingxing_receipt_orders`, `ods_lingxing_receipt_order_items`, plus the three
  governance rows the bootstrap/enable steps touch. Nothing else.
- Data range: windows start at **2026-08-01** (business decision, Rocky 2026-09-19). Earlier
  history is pulled only on a separate written instruction, never by default.
- One run at a time across the three interfaces (provider token bucket = 1).
- No schedule. `schedule_enabled` stays `false`; `scheduler_tick` is unchanged. Enabling a
  schedule is a separate PR + authorization.
- No Lingxing write endpoint is involved anywhere in this runbook.
- Never print `DATABASE_URL`, credentials, Token material, `sign`, RAW responses or SKU-level
  detail into a terminal, ticket or this file. Runner output is counts and codes only.

## Step 0 — Preconditions (verify, do not fix by hand)

1. Deployed revision is a clean merged `main` build containing #131. No server-side patch.
2. `APP_ENV=production`; `DATABASE_URL` resolves to the owned PostgreSQL `APPLICATION_DATABASE`.
3. A verified backup/snapshot of `APPLICATION_DATABASE` exists and the restore path is known.
4. `alembic_version` is `20260918_0015`, `20260919_0016`, or a later revision whose chain includes
   `20260919_0016` (e.g. `20260921_0010_add_listing_custom_tags`, which was applied together with
   #136 and already contains this migration — Step 1 then becomes a read-only check).
5. Nobody else is running a governed sync (`gov_integration_sync_runs` has no `running` row).

## Step 1 — Migration (`20260919_0016`, create-only)

Authorization scoped to this single command; do not persist the variable.

```bash
PRODUCTION_MIGRATIONS_AUTHORIZED=true uv run alembic -c alembic.ini upgrade head
```

If `alembic_version` already includes `20260919_0016` (see Step 0.4), skip the command and only
verify. Verify: `alembic_version` is `20260919_0016` or later; the five `ods_lingxing_purchase_*` /
`ods_lingxing_receipt_*` tables exist and are empty. Record in the log. If this fails, stop.

## Step 2 — Governance bootstrap (creates disabled rows)

```bash
PMC_PURCHASE_GOVERNANCE_BOOTSTRAP_AUTHORIZED=true \
PMC_PURCHASE_SOURCE_ACCOUNT_REF=<approved account ref> \
uv run python scripts/bootstrap_pmc_purchase_governance.py
```

Expected output: three `created` lines and `outbound_enabled=false`, `is_enabled=false`,
`schedule_enabled=false`. Re-running is idempotent (`unchanged`) and reverts any manual
enabling. Record in the log.

## Step 3 — Enable exactly one interface for exactly one run

The runner refuses unless, for the chosen interface, **both** flags are true:
`gov_integration_interfaces.outbound_enabled` and `gov_integration_sync_configs.is_enabled`
(and `schedule_enabled = false`, `schedule_cron IS NULL`, `page_size <= 500`,
`max_attempts = 1`, `retention_policy_id` = the interface's policy). Enable one interface,
run Step 4 for it, disable it (Step 5), then move to the next. Never enable two at once.

Run `psql` without `-q`/`-t` so each statement's `UPDATE n` tag is captured for the log. Both flags are changed by direct SQL. (`PATCH /api/integrations/sync-configs/{id}` exists,
but `app/core/auth.py` currently issues only a GET-scoped read preview principal — no
principal carries `integrations:update` — so the endpoint fails closed with 401 in
production. Until a write principal exists, SQL is the only executable path; the
execution-log entry is the audit record.) First, the read-only lookup:

```sql
-- read-only lookup (psql, as the application role; run inside BEGIN READ ONLY)
SELECT c.id AS config_id, i.interface_key, i.outbound_enabled, c.is_enabled,
       c.schedule_enabled, c.schedule_cron, c.page_size, c.max_attempts, c.source_account_ref
FROM gov_integration_sync_configs c
JOIN gov_integration_interfaces i ON i.id = c.interface_id
WHERE i.provider = 'lingxing'
  AND i.interface_key IN ('purchasePlanList','purchaseOrderList','purchaseReceiptOrderList')
ORDER BY i.interface_key;
```

**3a/3b. Enable — one interface, one transaction, each statement must report `UPDATE 1`:**

```sql
BEGIN;
UPDATE gov_integration_interfaces
   SET outbound_enabled = true, updated_at = now()
 WHERE provider = 'lingxing'
   AND interface_key = '<ONE of purchasePlanList | purchaseOrderList | purchaseReceiptOrderList>'
   AND outbound_enabled = false;
-- expect: UPDATE 1
UPDATE gov_integration_sync_configs c
   SET is_enabled = true, updated_at = now()
  FROM gov_integration_interfaces i
 WHERE c.interface_id = i.id
   AND i.provider = 'lingxing'
   AND i.interface_key = '<the same interface>'
   AND c.source_account_ref = '<approved account ref>'
   AND c.is_enabled = false
   AND c.schedule_enabled = false;
-- expect: UPDATE 1. Any other count on either statement → ROLLBACK and stop.
COMMIT;
```

**3c. Verify only one interface is enabled** (must return exactly one row, the one you chose):

```sql
SELECT i.interface_key, i.outbound_enabled, c.is_enabled, c.schedule_enabled
FROM gov_integration_interfaces i
JOIN gov_integration_sync_configs c ON c.interface_id = i.id
WHERE i.provider = 'lingxing'
  AND i.interface_key IN ('purchasePlanList','purchaseOrderList','purchaseReceiptOrderList')
  AND (i.outbound_enabled OR c.is_enabled);
```

Also confirm the productList / DATA-PAGES rows were not touched: the same query without the
`interface_key IN (...)` filter must show no change versus Step 0 for other interfaces.
Record in the log: interface, config_id, both statements' row counts, timestamp.

**Rollback of Step 3** (no run started yet): Step 5 for that interface, or re-run the
Step 2 bootstrap script, which restores `outbound_enabled=false` / `is_enabled=false` on all
three rows and reports `updated`.

## Step 4 — First window run (go-live window)

Run the three interfaces **sequentially**, receipt orders last (they reference purchase
order lines). Window = `2026-08-01` → go-live date (≤ 90 days; split into two windows if
longer). Authorization is one command, one interface, one window. **Always set the
idempotency key** as `<interface>:<start>:<end>`: the runner refuses a second run with the
same key, so an accidental re-execution of the go-live window is rejected instead of
duplicating raw pages and ODS rows.

The runner's `_validate_runtime_settings` requires, in addition to `APP_ENV=production`,
`LINGXING_ENABLE_TOKEN_REQUESTS=true`, `LINGXING_ENABLE_REAL_CALLS=true`, `LINGXING_DRY_RUN=false`
and `LINGXING_ALLOW_RAW_WRITE=true`, with structured write and full sync still `false`. The
production env file deliberately keeps real calls disabled, so — exactly as the ProductList runbook
does — these four overrides are scoped to the single command and never persisted. Without them the
runner exits `2` with `PMC_PURCHASE_ONE_TIME_RUN_ENV_NOT_AUTHORIZED` before any request (observed
on the first go-live attempt, 2026-09-21).

```bash
LINGXING_ENABLE_TOKEN_REQUESTS=true \
LINGXING_ENABLE_REAL_CALLS=true \
LINGXING_DRY_RUN=false \
LINGXING_ALLOW_RAW_WRITE=true \
PMC_PURCHASE_ONE_TIME_RUN_AUTHORIZED=true \
PMC_PURCHASE_INTERFACE_KEY=purchasePlanList \
PMC_PURCHASE_SOURCE_ACCOUNT_REF=<approved account ref> \
PMC_PURCHASE_WINDOW_START=2026-08-01 \
PMC_PURCHASE_WINDOW_END=<go-live date> \
PMC_PURCHASE_ONE_TIME_RUN_IDEMPOTENCY_KEY=purchasePlanList:2026-08-01:<go-live date> \
PMC_PURCHASE_ONE_TIME_RUN_REASON="go-live window purchasePlanList" \
uv run python scripts/run_pmc_purchase_once.py
```

Repeat (with the same four `LINGXING_*` overrides) with `PMC_PURCHASE_INTERFACE_KEY=purchaseOrderList` /
`…IDEMPOTENCY_KEY=purchaseOrderList:2026-08-01:<go-live date>`, then
`purchaseReceiptOrderList` / `…IDEMPOTENCY_KEY=purchaseReceiptOrderList:2026-08-01:<go-live date>`,
each after its own Step 3 → Step 5 cycle. If the window is split, each half gets its own key.

Exit codes: `0` succeeded, `1` run failed (inspect
`error_code` in the output and in `gov_integration_sync_runs`), `2` refused before any
request. The runner prints counts only (`headers_written`, `lines_written`,
`duplicates_skipped`, `quality=…`).

After each run, copy the printed summary into the log. **Read the `quality=` line**: PR #131
records header/line quantity mismatches, lines without id, integer store ids and receipts
without a purchase order as counts instead of failing the run. The first real run decides
whether any of these becomes a hard gate (follow-up PR), so keep the numbers.

## Step 5 — Disable again (after each run, before enabling the next interface)

**5a/5b. Disable — same shape as Step 3, reversed, each statement `UPDATE 1`:**

```sql
BEGIN;
UPDATE gov_integration_sync_configs c
   SET is_enabled = false, updated_at = now()
  FROM gov_integration_interfaces i
 WHERE c.interface_id = i.id
   AND i.provider = 'lingxing'
   AND i.interface_key = '<the interface just run>'
   AND c.source_account_ref = '<approved account ref>'
   AND c.is_enabled = true;
-- expect: UPDATE 1
UPDATE gov_integration_interfaces
   SET outbound_enabled = false, updated_at = now()
 WHERE provider = 'lingxing'
   AND interface_key = '<the interface just run>'
   AND outbound_enabled = true;
-- expect: UPDATE 1, otherwise ROLLBACK and investigate.
COMMIT;
```

**5c.** Verify: the Step 3c query must return **zero rows**. Record in the log.

**Fallback / full reset:** re-run the Step 2 bootstrap script. It is idempotent and writes
the approved disabled defaults to all three interfaces, policies and configs (`updated` for
any row that drifted). Use this if 5a/5b left anything inconsistent.

## Step 6 — Incremental windows (manual, no schedule)

Until a schedule is separately approved, each incremental pull is Step 3 → Step 4 → Step 5
with a window `[last window_end, today]` (≤ 90 days) and the same idempotency key
convention `<interface>:<start>:<end>`. Overlapping windows are safe for the ODS layer (rows are per-run; DWD dedupes),
but wasteful — avoid them.

## Rollback

- A failed run leaves `gov_integration_sync_runs.status = failed` with `error_code`; ODS rows
  written by that run stay (append-only, keyed by `run_id`) and are excluded downstream by
  run status. Nothing to undo by hand.
- To roll back the schema before any run wrote data: `alembic downgrade 20260918_0015`
  (drops the five empty tables). After data exists, do not downgrade; disable instead.
- Disabling: set `is_enabled = false` / `outbound_enabled = false`; the bootstrap script also
  restores the disabled defaults.

## Execution log (append one entry per action; never edit earlier entries)

| Date (CST) | Step | Interface | Window | Operator | Result (counts / codes only) | Notes |
|---|---|---|---|---|---|---|
| 2026-09-21 11:57 | 0 | — | — | deploy AI (Rocky-approved exception; Owner authorization in #132) | HEAD 118264f clean; APP_ENV=production; backup `<app-db-backup-before-pmc-purchase-20260921-115450>.dump` 980,898,422 B + .sha256; running=0; account ref `primary` | alembic already `20260921_0010` (0016 applied together with #136) |
| 2026-09-21 | 1 (verify only) | — | — | deploy AI | 5 ODS tables present, all 0 rows | no `upgrade` run |
| 2026-09-21 | 2 | all three | — | deploy AI | interface/policy/config `created` ×3, all disabled, page_size=500, max_attempts=1 | config ids b82eb148… / 9c74da63… / aa60c874… |
| 2026-09-21 | 3 | purchasePlanList | — | deploy AI | enabled, verify 1 row | |
| 2026-09-21 | 4 | purchasePlanList | 2026-08-01→2026-09-20 | deploy AI | exit 2 `PMC_PURCHASE_ONE_TIME_RUN_ENV_NOT_AUTHORIZED`, no request, no run | runbook omitted per-command LINGXING_* overrides → #139 |
| 2026-09-21 | 5 | purchasePlanList | — | deploy AI | disabled, verify 0 rows | |
| 2026-09-21 12:33 | 3 | purchasePlanList | — | deploy AI | UPDATE 1 / UPDATE 1, verify 1 row | per #139 |
| 2026-09-21 12:33 | 4 | purchasePlanList | 2026-08-01→2026-09-20 | deploy AI | exit 1, run `99cc1354-aa24-4e8e-a180-189fec851cd4` failed `PROVIDER_ERROR` (HTTP 200 / code 500: search_field_time enum), 1 raw_blob + 1 request_ref, ODS 0 | root cause: plans need `creator_time`, not `create_time` → #140; run kept as audit record |
| 2026-09-21 12:33 | 5 | purchasePlanList | — | deploy AI | UPDATE 1 / UPDATE 1, verify 0 rows | |
| 2026-09-22 | 0 (re-check) | — | — | deploy AI | HEAD 1fbd9e1 (main, ≥ d744ae0) clean; /health ok; alembic current=heads=`20260921_0013`; running=0; three interfaces disabled; ODS 0 rows; failed run 99cc1354 retained | Owner deployed #140/#143/#145/#146 |
| 2026-09-22 11:28 | 3 | purchasePlanList | — | deploy AI | UPDATE 1 / UPDATE 1, verify 1 row | |
| 2026-09-22 11:28 | 4 | purchasePlanList | 2026-08-01→2026-09-20 (update_time) | deploy AI | exit 0, run `58c69f5a-3dbf-4bb2-8bff-5157b50757c7` succeeded; headers_written=742 lines_written=0 duplicates_skipped=0; `quality=header_line_mismatches=0 missing_line_keys=0 non_string_store_ids=742 receipts_without_purchase_order=0`; 4 s | idempotency key `…:retry1`; non_string_store_ids = provider sends `sid` as JSON int (stored as string, no precision loss in Python json) |
| 2026-09-22 11:28 | 5 | purchasePlanList | — | deploy AI | UPDATE 1 / UPDATE 1, verify 0 rows | |
| 2026-09-22 11:28 | 3 | purchaseOrderList | — | deploy AI | UPDATE 1 / UPDATE 1, verify 1 row | |
| 2026-09-22 11:28 | 4 | purchaseOrderList | 2026-08-01→2026-09-20 (update_time) | deploy AI | exit 0, run `86ff667e-f659-4d58-ac31-95517901bd5d` succeeded; headers_written=615 lines_written=657 duplicates_skipped=0; `quality=header_line_mismatches=138 missing_line_keys=0 non_string_store_ids=0 receipts_without_purchase_order=0`; 3 s | mismatches compare header `quantity_total` with Σ line `quantity_plan`; to be verified against Σ `quantity_real` before any hard gate |
| 2026-09-22 11:28 | 5 | purchaseOrderList | — | deploy AI | UPDATE 1 / UPDATE 1, verify 0 rows | |
| 2026-09-22 11:28 | 3 | purchaseReceiptOrderList | — | deploy AI | UPDATE 1 / UPDATE 1, verify 1 row | |
| 2026-09-22 11:28 | 4 | purchaseReceiptOrderList | 2026-08-01→2026-09-20 (date_type=4) | deploy AI | exit 0, run `92c20513-fa3e-4c33-a028-b4a8a28e9488` succeeded; headers_written=543 lines_written=576 duplicates_skipped=0; `quality=header_line_mismatches=0 missing_line_keys=0 non_string_store_ids=0 receipts_without_purchase_order=0`; 7 s | |
| 2026-09-22 11:29 | 5 | purchaseReceiptOrderList | — | deploy AI | UPDATE 1 / UPDATE 1, verify 0 rows | |
| 2026-09-22 11:29 | final | all three | — | deploy AI | ODS rows: plans 742 / orders 615 / order_items 657 / receipts 543 / receipt_items 576; today raw_blobs +6, request_refs +6, parse_jobs +6 (all succeeded); enabled=0; running=0 | go-live window complete |

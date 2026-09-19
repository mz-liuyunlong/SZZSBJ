# Production PMC Purchase Sync Runbook

Status: **prepared — execution prohibited**. Code for Gate 2 is merged (PR #128 contracts,
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
4. Current `alembic_version` is `20260918_0015` (or already `20260919_0016` if Step 1 ran).
5. Nobody else is running a governed sync (`gov_integration_sync_runs` has no `running` row).

## Step 1 — Migration (`20260919_0016`, create-only)

Authorization scoped to this single command; do not persist the variable.

```bash
PRODUCTION_MIGRATIONS_AUTHORIZED=true uv run alembic -c alembic.ini upgrade head
```

Verify: `alembic_version = 20260919_0016`; the five `ods_lingxing_purchase_*` /
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

The runner refuses unless, for the chosen interface: `gov_integration_interfaces.outbound_enabled = true`
and `gov_integration_sync_configs.is_enabled = true` (with `schedule_enabled = false`,
`schedule_cron IS NULL`, `page_size <= 500`, `max_attempts = 1`). Flip these two flags through
the approved metadata tooling, for one interface, immediately before Step 4, and record which
interface and when. Do not enable all three at once.

## Step 4 — First window run (go-live window)

Run the three interfaces **sequentially**, receipt orders last (they reference purchase
order lines). Window = `2026-08-01` → go-live date (≤ 90 days; split into two windows if
longer). Authorization is one command, one interface, one window.

```bash
PMC_PURCHASE_ONE_TIME_RUN_AUTHORIZED=true \
PMC_PURCHASE_INTERFACE_KEY=purchasePlanList \
PMC_PURCHASE_SOURCE_ACCOUNT_REF=<approved account ref> \
PMC_PURCHASE_WINDOW_START=2026-08-01 \
PMC_PURCHASE_WINDOW_END=<go-live date> \
PMC_PURCHASE_ONE_TIME_RUN_REASON="go-live window purchasePlanList" \
uv run python scripts/run_pmc_purchase_once.py
```

Repeat with `PMC_PURCHASE_INTERFACE_KEY=purchaseOrderList`, then
`purchaseReceiptOrderList`. Exit codes: `0` succeeded, `1` run failed (inspect
`error_code` in the output and in `gov_integration_sync_runs`), `2` refused before any
request. The runner prints counts only (`headers_written`, `lines_written`,
`duplicates_skipped`, `quality=…`).

After each run, copy the printed summary into the log. **Read the `quality=` line**: PR #131
records header/line quantity mismatches, lines without id, integer store ids and receipts
without a purchase order as counts instead of failing the run. The first real run decides
whether any of these becomes a hard gate (follow-up PR), so keep the numbers.

## Step 5 — Disable again

After the three runs, set `is_enabled = false` on the three configs (leave
`outbound_enabled` as the Owner prefers; the runner needs both true to start). Record.

## Step 6 — Incremental windows (manual, no schedule)

Until a schedule is separately approved, each incremental pull is Step 3 → Step 4 → Step 5
with a window `[last window_end, today]` (≤ 90 days). Idempotency: use
`PMC_PURCHASE_ONE_TIME_RUN_IDEMPOTENCY_KEY=<interface>:<start>:<end>` so an accidental repeat
is refused. Overlapping windows are safe for the ODS layer (rows are per-run; DWD dedupes),
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
| | | | | | | |

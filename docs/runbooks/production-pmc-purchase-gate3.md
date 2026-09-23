# Production PMC Purchase Gate 3 Runbook — migration, DWD publish, DWS refresh

Status: **prepared — execution prohibited until the Owner writes the authorization into
this file's execution log.** Gate 3 code is merged (PR #152 tables + #156 seed cast, #148/#153
builder + publisher, #141 rules, #157 DWS refresh, #159 read API, #161 override API).
Merging authorizes nothing. Every step below is a production action performed one at a time
by the Project Owner or by the deploy AI on a Rocky-approved ticket, after an execution
record is appended to the log at the end of this file. No step may run without its record.

Upstream runbook: `docs/runbooks/production-pmc-purchase-sync.md` (Gate 2 ODS sync; go-live
window executed 2026-09-22). This runbook starts from the ODS rows that one produced.
PRP: `PRPs/pmc-purchase-board.md`. API contract: `docs/api/pmc-purchase-api.md`.

## Fixed boundary

- Tables this runbook may write: the eight Gate 3 tables created by migration
  `20260922_0017_add_pmc_purchase_gate3_tables` (`dwd_purchase_plan`, `dwd_purchase_order`,
  `dwd_purchase_order_line_item`, `dws_purchase_board`, `dws_purchase_sku_cycle`,
  `dws_purchase_pending`, `manual_purchase_cycle_override`, `rule_purchase_thresholds`) plus
  `gov_parse_jobs` and `gov_data_lineage` rows the publisher records. Nothing else.
- Read-only inputs: the five `ods_lingxing_purchase_* / ods_lingxing_receipt_*` tables
  (succeeded runs only), `gov_integration_sync_runs`, `dim_lingxing_stores`,
  `dim_walmart_listings`, `dwd_lingxing_sku_product_info_current`. Never modified here.
- No Lingxing / Walmart / carrier call anywhere in this runbook. No governance row is touched
  (`is_enabled` / `outbound_enabled` / `schedule_enabled` stay as they are).
- No schedule. Both scripts are manual, one account per invocation. Enabling a schedule is a
  separate PR + authorization.
- `manual_purchase_cycle_override` is never written by this runbook (only by the G3-F API
  with a real principal); `rule_purchase_thresholds` receives only the migration seed (v1).
- Never print `DATABASE_URL`, credentials, Token material, RAW responses, SKU / order / store
  detail rows into a terminal, ticket or this file. Script output is counts and codes only;
  verification queries return counts only.

## Step 0 — Preconditions (verify, do not fix by hand)

1. Deployed revision is a clean merged `main` build at or after `9ddeccd` (PR #161). No
   server-side patch (`git status` clean).
2. `APP_ENV=production`; `DATABASE_URL` resolves to the owned PostgreSQL `APPLICATION_DATABASE`
   (confirm by name only, never print the URL). `/health` responds.
3. A verified backup/snapshot of `APPLICATION_DATABASE` taken **today** exists (size +
   checksum recorded, path redacted as `<app-db-backup-before-pmc-gate3-YYYYMMDD-HHMMSS>.dump`).
4. Report `alembic current` **as found** (do not assume `20260921_0013`; the Owner may have
   advanced the after-sales chain). Report `alembic heads` from the deployed code: expected
   `20260923_0019_after_sales_reason_classification`.
5. The eight Gate 3 tables do **not** exist yet (or, if the Owner already migrated, exist
   and are empty except `rule_purchase_thresholds` = 1 row). Report which.
6. ODS row counts (succeeded runs only) as a baseline: `ods_lingxing_purchase_plans`,
   `ods_lingxing_purchase_orders`, `ods_lingxing_purchase_order_items`,
   `ods_lingxing_receipt_orders`, `ods_lingxing_receipt_order_items`. Reference from the
   go-live window (2026-09-22): 742 / 615 / 657 / 543 / 576.
7. Dimension coverage baseline (counts only): rows in `dim_lingxing_stores`,
   `dim_walmart_listings`, `dwd_lingxing_sku_product_info_current` for the approved
   `source_account_ref`.
8. Nobody else is running a governed sync (`gov_integration_sync_runs` has no `running` row).
9. **Stop here and report** before Step 1 (the ticket requires a confirmation after Step 0).

## Step 1 — Migration (create-only; the Owner chooses the target)

The Gate 3 migration `20260922_0017_add_pmc_purchase_gate3_tables` sits on a branch that the
Owner merged with the after-sales chain (`20260923_0018_merge_after_sales_pmc_heads`, head
`20260923_0019`). **The Owner decides one of the two targets and writes it in the log
before this step runs:**

- **Target A — full head** (also applies the after-sales revisions 0016 / 0017 / 0019, which
  belong to the Owner's own module):

  ```bash
  PRODUCTION_MIGRATIONS_AUTHORIZED=true uv run alembic -c alembic.ini upgrade head
  ```

- **Target B — Gate 3 branch only** (leaves the after-sales branch where it is; Alembic then
  reports two current revisions until the Owner later upgrades to head):

  ```bash
  PRODUCTION_MIGRATIONS_AUTHORIZED=true uv run alembic -c alembic.ini upgrade 20260922_0017_add_pmc_purchase_gate3_tables
  ```

Authorization is scoped to the single command; do not persist the variable. If Step 0.5
found the tables already present, skip the command and only verify.

Verify (counts only): the eight tables exist; `rule_purchase_thresholds` has exactly 1 row
with `rule_key='pmc_purchase_thresholds'`, `version=1`, `arrival_ratio=0.5000`,
`effective_from=2026-08-01`, `is_active=true`; the other seven tables have 0 rows;
`alembic current` shows the chosen target. Record in the log. If this fails, stop.

## Step 2 — DWD publish (ODS → `dwd_purchase_*`)

Reads only ODS rows of `succeeded` runs; upserts by business key; removes stale order lines
absent from the current build (#153 review); records `gov_parse_jobs`
(`parser_key=pmc_purchase.dwd.v1`) and `gov_data_lineage`. Re-running is idempotent
(`unchanged` counts) and safe.

```bash
PMC_PURCHASE_DWD_PUBLISH_AUTHORIZED=true \
PMC_PURCHASE_SOURCE_ACCOUNT_REF=<approved account ref> \
uv run python scripts/publish_pmc_purchase_dwd.py
```

Exit codes: `0` published, `1` failed (`PMC_PURCHASE_DWD_…` code printed; transaction rolled
back, nothing partial), `2` refused before touching the database. Output = `builder_version=…`,
one `plans=i/u/n orders=i/u/n lines=i/u/n lines_removed=… parse_jobs=… lineage=…
stores_known=… receipt_lines=…` line and a `build_report:` line with the builder's counters
(superseded versions, aux/combo excluded, deleted lines, merged lines split, unlinked receipt
lines).

Expected on the first publish (reference, not a gate): `plans` inserted ≈ 742 minus aux/combo
exclusions; `orders` inserted ≈ 615; `lines` inserted ≥ 657 (merged lines split per plan);
`lines_removed = 0`; `parse_jobs = 3` (one per go-live raw page set), `updated = unchanged = 0`.
Copy the printed lines into the log. If `plans` or `orders` inserted is 0 while ODS has rows,
stop and report (likely wrong `source_account_ref` or no `succeeded` run).

Verify (counts only): `dwd_purchase_plan`, `dwd_purchase_order`,
`dwd_purchase_order_line_item` row counts; `dwd_purchase_order_line_item` rows with
`plan_found=false`; rows with `store_attributed=false`; `dwd_purchase_plan` rows with
`store_matched=false`.

## Step 3 — DWS refresh (`dwd_purchase_*` → `dws_purchase_*`)

Delete + insert per account. Reads the active `rule_purchase_thresholds` version, active
manual overrides (none yet), dimensions and succeeded-run ODS receipt lines. **Always pass the
business date explicitly** (Owner requirement, #157 review) as the Beijing calendar date of
the run so the overdue arithmetic does not depend on the server clock / UTC:

```bash
PMC_PURCHASE_DWS_REFRESH_AUTHORIZED=true \
PMC_PURCHASE_SOURCE_ACCOUNT_REF=<approved account ref> \
PMC_PURCHASE_DWS_AS_OF=<YYYY-MM-DD Beijing date> \
uv run python scripts/refresh_pmc_purchase_dws.py
```

Exit codes: `0` refreshed, `1` failed (`PMC_PURCHASE_DWS_…` code; rolled back, previous DWS
rows untouched), `2` refused. Output = one line:
`account=… calc_version=pmc_purchase.dws.v1 rule_version=1 today=… board=… sku_cycles=…
pending=… orders=… lines=… plans=… receipt_lines=… overrides=0 stages[S0=…,S2=…,S3=…,S4=…,S9=…]
item_id_sources[from_plan_remark=…,pending_packing_slip=…] pending_types[itemid_pending=…,
overdue=…,wfs_not_ready=…]`. Copy it into the log.

Expected (reference): `board` = number of DWD lines; `sku_cycles` = distinct SKUs on lines;
`overrides=0`; `item_id_sources` contains only `from_plan_remark` and `pending_packing_slip`
(no packing-slip source is wired yet — every line without a plan-remark ItemID is
`pending_packing_slip`, which is the expected state, not an error); `stages` has no
`UNKNOWN` (report if it does). Re-running with the same `AS_OF` is idempotent.

## Step 4 — Read-only verification (counts only; copy into the log)

Each query returns a single number or a small grouped count. No row-level output.

```sql
-- 4.1 layer sizes
SELECT 'dwd_plan', count(*) FROM dwd_purchase_plan UNION ALL
SELECT 'dwd_order', count(*) FROM dwd_purchase_order UNION ALL
SELECT 'dwd_line', count(*) FROM dwd_purchase_order_line_item UNION ALL
SELECT 'dws_board', count(*) FROM dws_purchase_board UNION ALL
SELECT 'dws_sku_cycle', count(*) FROM dws_purchase_sku_cycle UNION ALL
SELECT 'dws_pending', count(*) FROM dws_purchase_pending;
-- 4.2 stage distribution and the two overdue kinds
SELECT stage_code, count(*), count(*) FILTER (WHERE overdue_days > 0) AS overdue
FROM dws_purchase_board GROUP BY stage_code ORDER BY stage_code;
-- 4.3 unattributed store share (sid = 0)
SELECT store_attributed, count(*) FROM dws_purchase_board GROUP BY 1;
-- 4.4 ItemID source distribution and listing join coverage
SELECT item_id_source, count(*), count(gtin) AS with_gtin FROM dws_purchase_board GROUP BY 1;
-- 4.5 owner coverage (product-info DWD join)
SELECT count(*) FILTER (WHERE owner_uid IS NOT NULL) AS with_owner, count(*) FROM dws_purchase_board;
-- 4.6 store name coverage
SELECT count(*) FILTER (WHERE store_name IS NOT NULL) AS with_store_name, count(*) FILTER (WHERE store_id IS NOT NULL) AS with_store_id FROM dws_purchase_board;
-- 4.7 SKU cycle sources and unstable SKUs
SELECT source, count(*), count(*) FILTER (WHERE unstable) AS unstable FROM dws_purchase_sku_cycle GROUP BY 1;
-- 4.8 pending lists
SELECT pending_type, count(*) FROM dws_purchase_pending GROUP BY 1;
-- 4.9 arrival: orders with an arrival date vs ordered
SELECT count(DISTINCT order_sn) FILTER (WHERE arrival_date IS NOT NULL) AS arrived, count(DISTINCT order_sn) FROM dws_purchase_board;
-- 4.10 governance side effects of Step 2
SELECT count(*) FROM gov_parse_jobs WHERE parser_key = 'pmc_purchase.dwd.v1';
SELECT count(*) FROM gov_data_lineage WHERE transform_key = 'pmc_purchase.dwd.current';
-- 4.11 nothing else moved
SELECT count(*) FROM gov_integration_sync_configs WHERE is_enabled OR outbound_enabled OR schedule_enabled;
```

Sanity expectations (report, do not "fix"): 4.3 unattributed share in the same order of
magnitude as the probe (~56 % of order lines had `sid=0` in the 12-month probe; the
2026-08-01+ window may differ); 4.4 `pending_packing_slip` ≈ the 88/657 lines the go-live
quality check found without a plan ItemID, plus lines whose plan remark has no `ITEMID:`;
4.5 / 4.6 coverage gaps are data reality (product-info DWD and store dimension coverage), not
a Gate 3 defect — record the percentages; 4.11 must be 0.

## Rollback

- DWS: re-run Step 3 at any time (delete + insert per account). Nothing else depends on it yet.
- DWD: a failed publish rolls back completely. To rebuild from scratch, `TRUNCATE
  dwd_purchase_order_line_item, dwd_purchase_order, dwd_purchase_plan` (ODS is untouched) and
  re-run Step 2; `gov_parse_jobs` / `gov_data_lineage` rows from the earlier publish stay as
  audit records.
- Schema: `alembic downgrade <previous revision>` only while all eight tables are empty; after
  data exists, do not downgrade — leave the tables and disable the API instead.
- Manual overrides: append-only by design; nothing to roll back here.

## Execution log (append one entry per action; never edit earlier entries)

| Date (CST) | Step | Target / Account | Operator | Result (counts / codes only) | Notes |
|---|---|---|---|---|---|
| — | authorization | — | Owner | _pending_ | Owner writes the migration target (A or B) and the approved account ref here before Step 0 |

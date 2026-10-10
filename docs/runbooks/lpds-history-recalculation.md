# Controlled LPDS historical recalculation

## Status and authorization boundary

This runbook documents the database-only runner introduced for the historical Walmart
low-price delivery surcharge (LPDS) recalculation. Merging the runner does **not** authorize
production execution. Production dry-run, commit, and restore each require a separate Owner
authorization naming the account and bounded business date.

The runner supports two explicit recalculation modes:

- `canonical` (the default) rebuilds Daily Sales and then Order Profit through the existing
  canonical DATA-PAGES MART methods. It can therefore pick up currently effective Product
  Management cost inputs.
- `lpds-only` is the historical repair mode. It computes LPDS from the persisted historical
  Daily Sales rows and freezes every non-LPDS input. It does not reread Product Management
  costs.

Both modes:

- never creates a Lingxing, Walmart, advertising, order, refund, or Token API client;
- never dispatches a task-center or Celery sync;
- defaults to a real transactional dry-run followed by `ROLLBACK`;
- processes one account business day per transaction and stops after the first failure;
- writes no product identifiers or URLs to its console summary.

It must not be reused for manual fixes to commissions, WFS base fees, storage fees, refunds,
advertising costs, or any other amount.

The `lpds-only` mode exists because an audited single-day dry-run case correctly failed the #207
profit-gap gate: the LPDS delta was valid, but current Product Management costs also changed
historical non-LPDS amounts. Freezing those historical inputs is an explicit business decision;
the #207 gate remains mandatory and must not be weakened.

## Historical scope

Production target counts, dates, and financial amounts are intentionally excluded from this
public runbook. The runner derives the current bounded scope at execution time and rechecks each
target day. It stops if a target is empty, mixed-version, unknown-version, or has changed in a way
that violates its gates.

## CLI

Run from `backend/` using the deployed project's Python environment:

```bash
uv run python scripts/recalculate_lpds_history.py \
  --source-account-ref '<approved-account-ref>' \
  --date 2026-01-15 \
  --mode canonical \
  --dry-run \
  --limit-days 1
```

The date scope must be either `--date` or both `--start-date` and `--end-date`. A range cannot
exceed `--limit-days`; the safe default is one day. Dates already entirely on
`real-data-2.0+business-rules-1+refund-v3-lpds` are skipped. Mixed or unknown versions fail
closed.

Historical LPDS-only dry-run:

```bash
uv run python scripts/recalculate_lpds_history.py \
  --source-account-ref '<approved-account-ref>' \
  --date 2026-01-15 \
  --mode lpds-only \
  --dry-run \
  --limit-days 1
```

`lpds-only` changes only `wfs_low_price_surcharge_amount`, `wfs_fee_total_amount`,
`gross_profit_amount`, `gross_margin`, `roi`, and `calc_version`. It preserves system and business
timestamps, business keys, sales, samples, refunds, advertising, SEM, commission, purchase,
first-leg, base WFS, storage, cost status, and all identity/linkage fields. A NULL historical
profit remains NULL. Order Profit receives the LPDS rollup from the updated Daily Sales rows while
preserving the same NULL-profit aggregation semantics.

In production, even dry-run requires the separately authorized `--allow-production` flag. A
commit additionally requires a protected backup directory and the exact confirmation phrase:

```bash
uv run python scripts/recalculate_lpds_history.py \
  --source-account-ref '<approved-account-ref>' \
  --date 2026-01-15 \
  --mode canonical \
  --commit \
  --allow-production \
  --backup-dir '<protected-directory-outside-the-repository>' \
  --confirm-token CONFIRM_LPDS_HISTORY_RECALC \
  --limit-days 1
```

Do not run this commit command from an unmerged branch. Do not place backups in Git, a shared
directory, or a web-served directory.

## Production hard gates

Before rebuilding each day, the runner starts a serializable transaction, applies bounded lock
and statement timeouts, locks the two target MART tables and the integration-run table, then
requires all of the following:

1. production Alembic revision is exactly
   `20261010_0033_add_wfs_low_price_surcharge`;
2. both MART LPDS columns exist;
3. running code exposes calc version
   `real-data-2.0+business-rules-1+refund-v3-lpds`;
4. Daily Sales and Order Profit are both uniformly on the known legacy version;
5. there is no queued or running DATA-PAGES sync for the same account and overlapping day;
6. row counts and business-key hashes remain stable;
7. both MARTs have unique business keys and the expected new calc version;
8. every Daily Sales LPDS value matches the canonical LPDS helper;
9. Daily Sales and Order Profit LPDS aggregates match by local SKU;
10. comparable profit groups have exact Daily Sales / Order Profit delta and gap invariance,
    while mixed-null groups have no unexplained profit-gap change;
11. non-target dates remain byte-content stable.

In `lpds-only` mode, an additional byte/hash gate requires every column outside the six-field
allowlist above to remain unchanged. The runner also compares the persisted transaction result
with its deterministic preserved-input projection before commit.

Daily Sales and Order Profit profit totals are not required to be equal. For a comparable group,
all Daily Sales profits and the corresponding Order Profit are non-NULL; its two profit deltas
must match exactly and its pre-existing gap must remain unchanged.

A mixed-null group contains at least one Daily Sales row with a NULL profit, and its Order Profit
is NULL under the canonical `bool_and(gross_profit_amount is not null)` aggregation rule. That
group is not forced into the two-sided profit-delta comparison because a non-NULL Daily Sales row
can receive LPDS while the NULL Order Profit remains excluded from `SUM`. The runner instead
requires stable business keys and NULL semantics, exact surcharge rollup, and a per-row `Decimal`
profit change equal to the negative LPDS change for every non-NULL Daily Sales row. The explained
LPDS amount must account for the entire global gap change; any remainder fails with
`LPDS_PROFIT_GAP_INVARIANT_FAILED` before commit.

An audited single-day dry-run case confirmed a fully explained mixed-null profit gap: one
partial-cost Daily Sales row had NULL profit, another non-NULL row received the expected LPDS
delta, and Order Profit remained NULL. That LPDS delta fully explained the aggregate gap change.
No product identifier is part of this runbook evidence. The fix does not permit unmatched or
duplicate keys, changed NULL semantics, surcharge rollup drift, non-LPDS profit drift, or any
unexplained gap.

The canonical execution order is Daily Sales first, Order Profit second. No amount is updated by
ad hoc SQL.

## Dry-run behavior

Dry-run executes the selected recalculation mode and the same validations as commit inside the
transaction. It then rolls back and uses a new session to verify that the target content hash and
all non-target content remain unchanged. It does not create a formal before-image file.

## Commit backups

Before a commit changes a target day, the runner writes the full Daily Sales and Order Profit
before-image to one JSON document. The document contains typed values, scope metadata, and a
SHA-256 payload hash. The file is created exclusively with mode `0600`; only its generated file
name and aggregate summary may appear in logs.

After commit, a new database session rechecks the persisted target snapshot and non-target
digest. A validation failure rolls back that day and prevents all later dates from running.

## Restore

Restore reads only the account and day embedded in a validated before-image. It validates the
payload hash, schema version, table allowlist, account, date, and every row's scope before opening
the restore transaction.

Dry-run restore:

```bash
uv run python scripts/recalculate_lpds_history.py \
  --source-account-ref '<approved-account-ref>' \
  --restore-from '<before-image.json>' \
  --dry-run \
  --allow-production
```

Commit restore requires a new pre-restore backup and a different confirmation phrase:

```bash
uv run python scripts/recalculate_lpds_history.py \
  --source-account-ref '<approved-account-ref>' \
  --restore-from '<before-image.json>' \
  --commit \
  --allow-production \
  --backup-dir '<protected-directory-outside-the-repository>' \
  --confirm-token CONFIRM_LPDS_HISTORY_RESTORE
```

Restore replaces only the two MART slices recorded for the validated account and business date.
It does not call an external API, trigger sync, or apply a partial fee update.

## Next production sequence after this validation fix

1. Confirm clean, merged production `main`, the exact Alembic revision, and no active overlapping
   DATA-PAGES work.
2. After this PR is merged and deployed, run only the approved single-day dry-run target with
   `--mode lpds-only --dry-run`.
3. Review row counts, frozen-field hashes, comparable and mixed-null profit summaries,
   LPDS/profit deltas, unexplained gap, and rollback verification.
4. Stop. Do not commit the target and do not process later historical dates.
5. Obtain separate Owner authorization before any commit or resumed batch plan.

Do not use current Product Management costs to rewrite historical profit unless the Owner approves
that separate business change.

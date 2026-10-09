# Controlled LPDS historical recalculation

## Status and authorization boundary

This runbook documents the database-only runner introduced for the historical Walmart
low-price delivery surcharge (LPDS) recalculation. Merging the runner does **not** authorize
production execution. Production dry-run, commit, and restore each require a separate Owner
authorization naming the account and bounded business date.

The runner:

- rebuilds Daily Sales and then Order Profit by calling the existing canonical DATA-PAGES MART
  methods;
- never creates a Lingxing, Walmart, advertising, order, refund, or Token API client;
- never dispatches a task-center or Celery sync;
- defaults to a real transactional dry-run followed by `ROLLBACK`;
- processes one account business day per transaction and stops after the first failure;
- writes no product identifiers or URLs to its console summary.

It must not be reused for manual fixes to commissions, WFS base fees, storage fees, refunds,
advertising costs, or any other amount.

## Audited historical scope

The pre-implementation read-only audit found:

- 102 old-version account business days;
- an estimated aggregate LPDS increase of USD 4,439;
- recommended first rehearsal date: `2026-09-26`;
- that first date contained 249 Daily Sales rows, 221 Order Profit rows, four LPDS-eligible
  rows, and an estimated USD 13 increase at audit time.

Those figures are audit evidence, not immutable runtime expectations. The runner rechecks the
current target day and stops if it is empty, mixed-version, unknown-version, or has changed in a
way that violates its gates.

## CLI

Run from `backend/` using the deployed project's Python environment:

```bash
uv run python scripts/recalculate_lpds_history.py \
  --source-account-ref '<approved-account-ref>' \
  --date 2026-09-26 \
  --dry-run \
  --limit-days 1
```

The date scope must be either `--date` or both `--start-date` and `--end-date`. A range cannot
exceed `--limit-days`; the safe default is one day. Dates already entirely on
`real-data-2.0+business-rules-1+refund-v3-lpds` are skipped. Mixed or unknown versions fail
closed.

In production, even dry-run requires the separately authorized `--allow-production` flag. A
commit additionally requires a protected backup directory and the exact confirmation phrase:

```bash
uv run python scripts/recalculate_lpds_history.py \
  --source-account-ref '<approved-account-ref>' \
  --date 2026-09-26 \
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
10. non-target dates remain byte-content stable.

The canonical execution order is Daily Sales first, Order Profit second. No amount is updated by
ad hoc SQL.

## Dry-run behavior

Dry-run executes the same canonical rebuild and validations as commit inside the transaction. It
then rolls back and uses a new session to verify that the target content hash and all non-target
content remain unchanged. It does not create a formal before-image file.

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

## First production sequence after a future authorization

1. Confirm clean, merged production `main`, the exact Alembic revision, and no active overlapping
   DATA-PAGES work.
2. Run only `2026-09-26` in dry-run mode.
3. Review row counts, hashes, LPDS/profit deltas, and rollback verification.
4. Stop. Do not proceed to full history.
5. Obtain a separate explicit authorization before the `2026-09-26` commit rehearsal.
6. Only after that commit and its new-session verification may a later bounded batch be proposed.

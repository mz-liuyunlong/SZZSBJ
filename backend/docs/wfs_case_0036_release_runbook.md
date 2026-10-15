# WFS Case 0036 controlled release checklist

Applies to PR #218. This is an approval-gated operational runbook, **not** permission to deploy.

## Proven and unproven

- Production database was last independently observed at `20261014_0035_add_auth_rbac`.
- Production read-only reconciliation found 132/132 identities, zero ambiguity,
  duplicate or invalid values. Snapshot: 2026-10-15.
- Monetary baseline from that snapshot: estimated USD 45,866.37;
  recovered USD 22,991.05. Five legacy status counts: 11 / 31 / 8 / 40 / 42.
- CI runs `0035 → 0036` on ephemeral PostgreSQL with synthetic source
  tables and five synthetic Cases. It tests first import, strict comparison,
  idempotence, manual edit protection and ambiguous account rejection.
- CI does **not** certify production's current data, permissions, deployment
  hooks, full schema, infrastructure or availability.

## Non-negotiable release gates

1. **Production frontend automatically deploys on main** (confirmed by owner).
   WFS Case is a new page, and the owner accepts that it may be visible before
   the formal backend and table are ready. No frontend feature flag or
   legacy-API fallback is required; the page calls the formal Case endpoints.
   If the backend or table is not ready, the WFS Case page may temporarily
   fail to load or show an API error. This is an explicitly accepted UI
   availability risk, **not** approval to migrate or write production data.
   Validate that existing unrelated pages remain unaffected.
2. Recheck production Alembic revision via a read-only `alembic_version` query;
   it must still be the PR's parent `20261014_0035_add_auth_rbac`.
3. Recheck that the old `ops_wfs_fee_anomaly_cases` is **empty** and the
   backup table does not already exist. The migration deliberately refuses
   destructive/ambiguous states.
4. Rerun the read-only legacy account resolution and compare the total count,
   account ambiguities, duplicates and invalid values against the fresh
   source snapshot. Stop on any nonzero exception count.
5. Independently approve the migration, deployment and historic sync;
   each production action requires its own explicit authorization.
   Never disable `Production migrations require separate authorization`
   to perform a read-only check.
6. Ensure a verified database backup and rollback/recovery procedure, and
   a maintenance window. The downgrade intentionally refuses nonempty
   formal tables; restoring data is not an automatic Alembic downgrade.

## Post-authorization staged acceptance (not instructions to execute now)

1. Deploy an approved backend version without exposing an unready UI.
2. Apply only the approved `0036` migration, check its Alembic revision,
   physical table, archive backup and RBAC grants.
3. Run a formal Case sync preview; **write remains disabled by default**
   on production and needs separate `WFS_CASE_SYNC_AUTHORIZED` authorization.
4. Only after explicit import approval, run the historic sync.
   It must insert the expected count and produce zero discrepancies
   under the strict comparison endpoint/script.
5. Compare total, five states, fee rates, quantities, claims,
   recovered amounts, estimated recovery, and Case numbers against
   the same immutable source snapshot. Track any source changes separately.
6. Re-import once to verify no duplicates and no changed manual notes;
   exercise least-privilege denial and two-person archival review.
7. The frontend may auto-publish when main merges, without an additional
   feature toggle. The WFS Case page is considered provisionally unavailable
   until the separately authorized backend, migration and historic import
   are ready. After readiness, verify HTTP 200, old and new Case statuses,
   historical dates, pagination, write permissions and error handling.
8. Keep `legacy_mirror.event_wfs_fee_case` available for comparison.
   Do not stop its refresh or delete it as part of this PR.

## Abort conditions

Stop immediately for any revision mismatch, nonempty old table, missing
backup, identity collision, count/value discrepancy, permission leak, or
unexpected frontend production deployment. Log aggregate data only; never
print API credentials, RAW payloads, account identifiers or real SKUs.

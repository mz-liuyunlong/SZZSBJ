# Listing grade: finance + advertising publication evidence (v1)

This contract is deliberately **fail closed**. A provisional A/B/C/D grade from `/api/listings/evaluation-preview` is **not** an official grade. Neither `cost_status=complete` nor a numeric zero ad-spend amount demonstrates that the advertising source-day ingest has closed.

## Current data limitation

The current `data_pages_real_sync.py` may populate daily sales rows with `cost_status='missing'` and `ad_spend_amount=0` even when the upstream advertising source has not finished. The business database currently lacks a trusted explicit per-account/store/Item/MSKU/day sign-off for financial closure, advertising closure and completeness of zero-order dates. **Do not fabricate sign-off markers in production.**

## Trusted attestations (required, not yet populated by the existing ETL)

After an independent audited reconciliation process has verified complete finance and advertising source-day coverage, it may add this key to `mart_daily_sales_item_day.source_lineage_json` for each closed date:

```json
{
  "listing_grade_finance_ads_closure_v1": {
    "origin": "trusted_finance_ads_reconciliation",
    "financial_complete": true,
    "advertising_complete": true,
    "zero_sales_coverage_confirmed": true,
    "evidence_sha256": "<lowercase SHA-256 of reconciliation input evidence>"
  }
}
```

Those markers must originate in the reviewed ingestion/reconciliation process, not in user-facing browser requests. In particular, never treat missing ad records as zero ad spending. A financial day also requires complete costs, explicit USD currencies, non-null ad fields, non-null profit and no missing cost codes. The profitability evaluator uses **only attested valid days** and the persisted version of the Listing grade rules (short/medium min-valid-days, weights, thresholds).

## Publishing

`ListingGradePublicationService.publish_run(run_id)` accepts an existing **succeeded** diagnostic run and locks each scoped Listing and its snapshot. It recalculates the official grade from attested daily facts, requires agreement with the diagnostic candidate, protects archive/lifecycle exclusions and blocks stale cutoff dates. For successes it updates `mart_listing_management_current.product_grade` and `biz_listing_evaluation_snapshots.published`; C/D follow-up items derive only from published snapshots.

An explicitly invoked Celery task `listing_evaluation.publish_grade_run` is provided, but **no recurring schedule is registered**. `LISTING_EVALUATION_PUBLISH_ENABLED` remains false by default. This feature must not be enabled for production until the real reconciliation producer and its tests are in place, and a fresh production deployment authorization is granted.

## Lifecycle and diagnostics

The diagnostic backend now delegates lifecycle evaluation to the same WFS inventory/Item-day algorithm as the official publisher. The frontend requests read-only batches of up to 50 Listing IDs and always renders a diagnostic icon, even while the opt-in preview API is disabled. Production preview still requires `LISTING_EVALUATION_PREVIEW_ENABLED=true`, separately authorized during deployment. The 517 `HISTORICAL_FIRST_WFS_NOT_LAUNCH_VERIFIED` cases retain their genuine historical-provenance explanations. Never replace them with unproven `启动期` defaults.

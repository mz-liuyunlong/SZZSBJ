# DATA-PAGES production runbook handoff

## Status

- Task: `SYNC-1G`
- Scope: non-production fixture validation and production runbook handoff
- Production Lingxing calls: not authorized
- Production database writes: not authorized
- Production schedules: not authorized
- Production Celery dispatch: not authorized

This runbook closes the foundation phase for DATA-PAGES ingestion. It does not approve
or perform production execution. A future production run requires separate written
authorization and an implementation PR that intentionally enables outbound execution.

## Covered source interfaces

| Parser key | Interface key | API path | Production status |
| --- | --- | --- | --- |
| `seller_list_multi_platform` | `getSellerList` | `/pb/mp/shop/v2/getSellerList` | disabled |
| `walmart_listing_list` | `walmartListingList` | `/basicOpen/multiplatform/walmart/list` | disabled |
| `sale_stat_page_list` | `saleStatPageList` | `/basicOpen/platformStatisticsV2/saleStat/pageList` | disabled |
| `order_v2_list` | `orderV2List` | `/pb/mp/order/v2/list` | disabled |
| `walmart_return_order_list` | `walmartReturnOrderList` | `/basicOpen/openapi/multiplatform/walmart/returnOrder/list` | disabled |
| `walmart_advertiser_list` | `walmartAdvertiserList` | `/basicOpen/adReport/advertiser/list` | disabled |
| `walmart_ad_item_sp_list` | `walmartAdItemSpList` | `/basicOpen/multiplatform/ads/reportAdItemSpList` | disabled |

## Foundation already completed

- `SYNC-1A`: static ingestion catalog for the seven source interfaces.
- `SYNC-1B`: request-planning contracts.
- `SYNC-1C`: governance bootstrap metadata with disabled sync configs.
- `SYNC-1D`: controlled RAW-capture contract for already-received envelopes.
- `SYNC-1E`: DIM / FACT writer contracts.
- `SYNC-1F`: MART refresh contracts.
- `SYNC-1G`: fixture validation and this production handoff runbook.

## Non-production fixture validation

The fixture validation contract must stay synthetic and display-safe:

1. Every approved source interface has one synthetic fixture case.
2. Fixture cases contain normalized field metadata, not real Lingxing payloads.
3. Required parser fields must be represented by the fixture case.
4. Writer unique-key fields must be represented by the fixture case.
5. Request metadata must reject token, secret, authorization, password, sign,
   payload, and raw-looking keys.
6. Return-order fixtures must contain only `REFUND` records.
7. `sale_stat_page_list` must keep explicit `result_type` fan-out.
8. `walmart_ad_item_sp_list` must declare its advertiser-list dependency.
9. MART refresh plans must build without executing SQL.
10. The validation report must state `production_calls=false` and
    `production_writes=false`.

Recommended non-production validation command:

```bash
cd backend
uv run ruff format --check .
uv run ruff check .
uv run pytest \
  tests/modules/integration_sync/test_data_pages_sync_catalog.py \
  tests/modules/integration_sync/test_data_pages_request_plans.py \
  tests/modules/integration_sync/test_data_pages_governance_bootstrap.py \
  tests/modules/integration_sync/test_data_pages_raw_capture.py \
  tests/modules/integration_sync/test_data_pages_writer_specs.py \
  tests/modules/integration_sync/test_data_pages_mart_refresh.py \
  tests/modules/integration_sync/test_data_pages_fixture_validation.py \
  tests/modules/integration_sync/test_parsers_calculations.py \
  tests/modules/data_pages/test_validation_registry.py \
  tests/modules/data_pages/test_models.py
uv run python -c "import app.main"
```

## Production authorization gate

Production execution must not begin until all of these are true:

1. Owner gives explicit production authorization for the specific interface.
2. Target source account and date window are named explicitly.
3. `outbound_enabled` is intentionally enabled for the interface.
4. `is_enabled` is intentionally enabled for the sync config.
5. `schedule_enabled` remains disabled for first manual production trials.
6. A dry-run or fixture replay has passed for the same interface contract.
7. Stop conditions and rollback owner are named before execution.
8. The operator has confirmed no secrets or RAW payloads will be pasted into chat.
9. The production database backup and observability window are confirmed.

## First production trial sequence

When production execution is separately authorized, use this conservative order:

1. `getSellerList` store metadata.
2. `walmartAdvertiserList` advertiser metadata.
3. `walmartListingList` listing metadata.
4. `saleStatPageList` for one store and one business date.
5. `orderV2List` for the same constrained window.
6. `walmartReturnOrderList` for the same constrained window, retaining only `REFUND`.
7. `walmartAdItemSpList` for one advertiser and one business date.
8. Refresh `mart_daily_sales_item_day` for the same date window.
9. Refresh `mart_order_profit_sku_day` for the same date window.
10. Refresh `mart_listing_management_current` only after DIM and FACT checks pass.

Do not enable schedules during the first production trial.

## Required preflight checks

Before any future production trial, run read-only checks:

```bash
cd backend
uv run python -c "import app.main"
uv run pytest tests/modules/integration_sync/test_data_pages_fixture_validation.py
```

Then inspect governance state through read-only queries or admin views:

- Interface exists.
- Retention policy exists.
- Sync config exists.
- Outbound is still disabled until explicitly authorized.
- Schedule is still disabled for the first trial.
- No unexpected pending production runs exist for the same interface.

## Stop conditions

Stop immediately if any of these occur:

- Authentication or authorization error from the provider.
- Provider rate-limit error not covered by the approved retry policy.
- Required field missing in more than one fixture-equivalent production record.
- Unexpected non-`REFUND` return record enters the refund pipeline.
- `result_type` cannot be tied to request metadata.
- Advertiser dependency is missing for SP ad item reports.
- More records are written than the planned page/window limit.
- RAW redaction or request metadata validation fails.
- Any production secret, payload, or SKU detail is about to be pasted into chat.

## Rollback and containment

The first authorized production implementation must provide concrete rollback SQL or
service commands. Until then, this foundation phase allows only these safe actions:

- Keep DATA-PAGES interfaces disabled.
- Keep sync configs disabled.
- Keep schedules disabled.
- Delete non-production fixture artifacts if they were created locally.
- Revert the production-enabling PR if a future authorization PR is opened.

## Handoff summary

After `SYNC-1G`, the DATA-PAGES foundation is complete, but production execution is
still blocked by design. The next work should be a separate, explicitly authorized
production-enablement slice, not a hidden side effect of this foundation work.

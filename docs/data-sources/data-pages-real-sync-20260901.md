# REAL-DATA-1 DATA-PAGES 2026-09-01 real sync

## Scope

This runbook covers the one-time controlled DATA-PAGES real sync for business
date `2026-09-01`.

The run calls all approved DATA-PAGES source interfaces:

1. `/pb/mp/shop/v2/getSellerList`
2. `/basicOpen/adReport/advertiser/list`
3. `/basicOpen/multiplatform/walmart/list`
4. `/basicOpen/platformStatisticsV2/saleStat/pageList`
5. `/pb/mp/order/v2/list`
6. `/basicOpen/openapi/multiplatform/walmart/returnOrder/list`
7. `/basicOpen/multiplatform/ads/reportAdItemSpList`

The run writes redacted RAW blobs, DIM rows, FACT rows, and the three frontend
MART tables. It does not enable schedules or run historical full sync.

## Preconditions

- Server code is on a commit that includes this runner.
- Database revision is `20260917_0011`.
- `LINGXING_ENABLE_REAL_CALLS=true` is present in the runtime environment.
- `LINGXING_ENABLE_TOKEN_REQUESTS=true` and token request credentials are present.
- The command is run with `DATA_PAGES_REAL_SYNC_AUTHORIZED=true`.
- Do not paste secrets, RAW content, real SKU values, or request bodies into chat.

## Command

```bash
cd <APP_BACKEND_DIR>
set -a
source <APP_ENV_FILE>
set +a

DATA_PAGES_REAL_SYNC_AUTHORIZED=true \
uv run python -m scripts.run_data_pages_real_sync \
  --business-date 2026-09-01 \
  --source-account-ref "<ONE_SOURCE_ACCOUNT_REF>" \
  --page-size 3 \
  --campaign-type SP
```

If the configured source account value contains more than one account, run the
command once for each explicit source account reference. Do not pass a
comma-separated list as a single source account value.

## Expected safe output

The runner prints counts only:

```text
source_account_ref=...
business_date=2026-09-01
requested_interfaces=...
raw_blobs=...
store_rows=...
listing_rows=...
advertiser_rows=...
sales_rows=...
order_rows=...
refund_rows=...
ad_rows=...
mart_daily_sales_rows=...
mart_order_profit_rows=...
mart_listing_rows=...
```

No token, order ID, SKU, item detail, or provider response body should be printed.

## Frontend validation

After a successful run, validate these pages against the production backend:

- Listing management: `mart_listing_management_current`
- Daily sales: `mart_daily_sales_item_day` for `2026-09-01`
- Order profit: `mart_order_profit_sku_day` for `2026-09-01`

Minimum checks:

- API does not return 500.
- `total` is greater than zero for any page with matched source data.
- `latest_calculated_at` is populated for MART-backed pages.
- Date and search filters still work.
- Missing cost fields are surfaced as cost status, not silent zero profit.

## Stop conditions

Stop the run and do not retry blindly if any of these occur:

- Lingxing authorization failure.
- Provider error for more than one interface.
- Unexpected response-size failure.
- Database write failure.
- MART refresh failure.
- Any secret, RAW content, order ID, or SKU value is about to be pasted into chat.

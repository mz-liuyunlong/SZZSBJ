# DATA-PAGES validation registry

Status: implementation registry for DATA-PAGES-1G validation and handoff.

This document closes the first DATA-PAGES implementation pass for the three read pages built in DATA-PAGES-1D through DATA-PAGES-1F. It records the current read-only API boundary, MART objects, frontend adapters, metadata behavior, and data-quality checkpoints.

## Scope

In scope:

- Daily Sales read API and frontend adapter.
- Order Profit read API and frontend adapter.
- Listing Management read API and frontend adapter.
- MART source object registry used by response metadata.
- Empty-data behavior and temporary frontend fallback behavior.
- Data-quality checkpoints required before real sync/backfill is considered accepted.

Out of scope:

- Lingxing API calls.
- Parser writers and persistence writers.
- MART refresh jobs.
- Backfill or production data migration.
- Celery worker or scheduler productionization.
- Production database operation.
- Formal auth/role split beyond the current preview-safe permission boundary.

## API registry

| Page | Task | API | Permission | MART source object | Frontend page | API adapter |
| --- | --- | --- | --- | --- | --- | --- |
| Daily Sales | DATA-PAGES-1D | `GET /api/sales/daily-sales` | `sales:daily-sales:read` | `mart_daily_sales_item_day` | `frontend/src/pages/sales/DailySalesPage.tsx` | `frontend/src/pages/sales/dailySalesApi.ts` |
| Order Profit | DATA-PAGES-1E | `GET /api/sales/order-profit` | `sales:daily-sales:read` | `mart_order_profit_sku_day` | `frontend/src/pages/sales/OrderProfitPage.tsx` | `frontend/src/pages/sales/orderProfitApi.ts` |
| Listing Management | DATA-PAGES-1F | `GET /api/listings/walmart` | `products:read` | `mart_listing_management_current` | `frontend/src/pages/products/ListingManagementPage.tsx` | `frontend/src/pages/products/listingManagementApi.ts` |

The backend registry lives in `backend/app/modules/data_pages/registry.py`. Router metadata must use that registry so `meta.source_objects` cannot drift from the documented MART source object list.

## Empty data and fallback behavior

For all three APIs, an empty MART result is a successful read response:

```json
{
  "success": true,
  "data": { "items": [] },
  "error": null,
  "meta": {
    "source": "new_system_postgresql",
    "source_objects": ["<page_mart_object>"],
    "page": 1,
    "page_size": 100,
    "total": 0
  },
  "request_id": "<generated>"
}
```

Temporary frontend fallback remains only for local acceptance while MART sync/backfill is not implemented. A backend failure keeps the existing local acceptance rows visible instead of blanking the page. Once real sync and MART refresh are implemented, this fallback should be reviewed and either removed or changed to an explicit empty/error state.

## Data-quality checkpoints

These checks are required before DATA-PAGES can be considered real-data accepted:

### Common checks

- `source_account_ref` is always constrained by the caller's integration source-account scope.
- All three endpoints read from MART objects only. They must not read RAW, ODS, STG, FACT, DIM, or external API data directly.
- Response envelope remains `{ success, data, error, meta, request_id }`.
- `meta.source_objects` is exactly one MART object for the page.
- `latest_calculated_at` reflects MART calculation freshness when rows exist.
- No response exposes RAW payload, Authorization, token, app secret, sign, or source JSON.

### Daily Sales

- `business_date_la` is the Walmart business date in `America/Los_Angeles`.
- `sales_7d_trend` is a display-safe list of date/value points.
- `cost_status` and `missing_cost_codes` are present for incomplete cost inputs.
- Money and ratio values serialize from Decimal-compatible backend values.
- Empty result returns `data.items=[]` and `meta.total=0`.

### Order Profit

- Aggregation grain remains SKU/day from `mart_order_profit_sku_day`.
- `store_ids_json` and `item_ids_json` are display-safe string lists.
- `cost_status` and `missing_cost_codes` are present for incomplete profit inputs.
- Money and ratio values serialize from Decimal-compatible backend values.
- Empty result returns `data.items=[]` and `meta.total=0`.

### Listing Management

- Current-state grain remains listing/current row from `mart_listing_management_current`.
- `tags` serializes as a string list.
- Listing fields expose display-safe status, price, inventory, rating, review, GTIN/UPC, and WFS fee values only.
- Empty result returns `data.items=[]` and `meta.total=0`.

## Validation commands

Recommended local checks for this registry PR:

```bash
cd backend
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/modules/data_pages/test_validation_registry.py tests/modules/data_pages/test_listing_management_router.py tests/modules/data_pages/test_order_profit_router.py tests/modules/data_pages/test_daily_sales_router.py tests/modules/data_pages/test_models.py
uv run python -c "import app.main"

cd ../frontend
npm test -- --run src/pages/products/ListingManagementPage.test.tsx src/pages/sales/OrderProfitPage.test.tsx src/pages/sales/DailySalesPage.test.tsx
npm run build
```

## Next boundary

DATA-PAGES-1G does not create real data. The next implementation boundary is a separate sync task that writes parsed Lingxing/API data through controlled writers and refreshes the MART tables. That work should remain separate from this registry closure so production data, migration, worker, and backfill decisions stay explicit.

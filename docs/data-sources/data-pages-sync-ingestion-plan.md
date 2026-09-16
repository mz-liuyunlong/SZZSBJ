# DATA-PAGES sync ingestion plan

## Status

- Task: `SYNC-1`
- Current slice: `SYNC-1B` request planning foundation
- Status: implementation foundation only
- Production calls: not authorized
- Production database writes: not authorized

## Purpose

This document records the approved first steps for turning DATA-PAGES read APIs into a real ingestion pipeline.
DATA-PAGES-1 already created the DIM / FACT / MART tables and read-model APIs. SYNC-1 connects the seven approved Lingxing/Walmart source interfaces into those tables.

## Approved source interfaces

| Parser key | Interface key | API path | Target table | Initial outbound |
| --- | --- | --- | --- | --- |
| `seller_list_multi_platform` | `getSellerList` | `/pb/mp/shop/v2/getSellerList` | `dim_lingxing_stores` | disabled |
| `walmart_listing_list` | `walmartListingList` | `/basicOpen/multiplatform/walmart/list` | `dim_walmart_listings` | disabled |
| `sale_stat_page_list` | `saleStatPageList` | `/basicOpen/platformStatisticsV2/saleStat/pageList` | `fact_walmart_sales_item_daily` | disabled |
| `order_v2_list` | `orderV2List` | `/pb/mp/order/v2/list` | `fact_walmart_order_items` | disabled |
| `walmart_return_order_list` | `walmartReturnOrderList` | `/basicOpen/openapi/multiplatform/walmart/returnOrder/list` | `fact_walmart_refund_items` | disabled |
| `walmart_advertiser_list` | `walmartAdvertiserList` | `/basicOpen/adReport/advertiser/list` | `dim_walmart_advertisers` | disabled |
| `walmart_ad_item_sp_list` | `walmartAdItemSpList` | `/basicOpen/multiplatform/ads/reportAdItemSpList` | `fact_walmart_ad_item_sp_daily` | disabled |

## Request planning foundation

`SYNC-1B` adds a static, test-covered request-planning contract for the same seven DATA-PAGES interfaces.
The contract records pagination fields, date-window fields, store-scope fields, fixed request values, fan-out fields, and upstream dependencies without executing any outbound call.

Important planning rules:

- `sale_stat_page_list` must fan out `result_type` explicitly for sales, order count, and sales amount.
- `order_v2_list` uses `date_type=global_purchase_time` for profit lineage.
- `walmart_return_order_list` plans only refund return records for DATA-PAGES marts.
- `walmart_ad_item_sp_list` depends on advertiser IDs collected from `walmart_advertiser_list`.
- `walmart_listing_list` keeps the initial no-store-filter boundary from the approved field mapping.

## Boundary

These foundation slices only add stable catalog and request-planning metadata that ties parser specs to integration interface metadata.
They do not call Lingxing APIs, do not create real sync runs, do not write production data, and do not run migrations.

## Next implementation slices

1. `SYNC-1C`: add governance bootstrap for DATA-PAGES interfaces, retention policies, and disabled sync configs.
2. `SYNC-1D`: add controlled RAW capture handlers that persist redacted RAW envelopes through existing governance tables.
3. `SYNC-1E`: add DIM/FACT parser writers for the seven target tables with idempotent upsert behavior.
4. `SYNC-1F`: add MART refresh service for `mart_daily_sales_item_day`, `mart_order_profit_sku_day`, and `mart_listing_management_current`.
5. `SYNC-1G`: add non-production fixture validation and production runbook handoff. Production execution remains a separate authorized operation.

## Notes

- `walmart_ad_item_sp_list` depends on advertiser IDs from `walmart_advertiser_list`.
- `sale_stat_page_list` requires `result_type` request fan-out and must not infer result_type from the response.
- Order business date is calculated from source purchase time into `America/Los_Angeles` business date.
- Store metadata from `getSellerList` is a prerequisite for store-scoped joins.
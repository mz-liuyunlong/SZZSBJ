# DATA-PAGES sync ingestion plan

## Status

- Task: `SYNC-1`
- Current slice: `SYNC-1E` + `SYNC-1F` writer and MART refresh foundations
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

## Governance bootstrap foundation

`SYNC-1C` adds idempotent governance bootstrap metadata for the seven DATA-PAGES interfaces.
The bootstrap creates or updates:

- `gov_integration_interfaces` rows with `outbound_enabled=false`.
- `gov_raw_retention_policies` rows with active DATA-PAGES retention policies.
- `gov_integration_sync_configs` rows with `is_enabled=false` and `schedule_enabled=false`.

The bootstrap is safe by default. It does not make the interfaces executable, does not enable schedules, and does not authorize production runs.

## RAW capture foundation

`SYNC-1D` adds controlled RAW capture foundations for already-received DATA-PAGES envelopes.
The capture contract persists redacted response blobs and request references through the existing governance tables.
It validates the run/work-item/policy context before persistence and rejects unsafe request parameters that look like credentials, payloads, or RAW data.

This foundation does not call Lingxing APIs. Future execution code must supply an already-received envelope from a separately authorized runner.

## DIM / FACT writer foundation

`SYNC-1E` adds writer contracts for the seven approved DATA-PAGES parser targets.
The writer contracts record:

- Target DIM / FACT table.
- Idempotent upsert mode.
- Approved unique-key identity from the parser spec.
- Required source fields.
- Required lineage metadata, including RAW request references and sync timestamps.
- Downstream MART objects affected by each target table.

This slice still does not execute real writes. It defines the safe writer contract that future parser execution must follow.

## MART refresh foundation

`SYNC-1F` adds refresh contracts for the three DATA-PAGES MART objects:

- `mart_daily_sales_item_day`.
- `mart_order_profit_sku_day`.
- `mart_listing_management_current`.

The refresh contracts define delete-insert refresh mode, source table dependencies, grain, and business-date window requirements.
Business-date MARTs require explicit `business_date_from` and `business_date_to` windows. The current listing MART can be planned as a current snapshot refresh.

## Boundary

These foundation slices add stable catalog, request-planning, governance, RAW-capture, writer, and MART-refresh metadata.
They do not call Lingxing APIs, do not create real production sync runs, do not write production data, and do not run migrations.

## Next implementation slices

1. `SYNC-1G`: add non-production fixture validation and production runbook handoff. Production execution remains a separate authorized operation.

## Notes

- `walmart_ad_item_sp_list` depends on advertiser IDs from `walmart_advertiser_list`.
- `sale_stat_page_list` requires `result_type` request fan-out and must not infer result_type from the response.
- Order business date is calculated from source purchase time into `America/Los_Angeles` business date.
- Store metadata from `getSellerList` is a prerequisite for store-scoped joins.

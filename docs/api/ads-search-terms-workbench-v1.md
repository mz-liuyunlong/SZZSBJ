# API Contract Draft — Ads Search Terms Workbench V1

Status: Draft; owner confirmation required before backend/frontend implementation.
PRP: PRPs/ads-search-terms-workbench-v1.md
Data source decision: docs/data-sources/decisions/ads-search-terms-workbench-decision.md

## External Lingxing contracts

### Walmart SP Search Impression / Search Terms

- Method: POST
- Path: /basicOpen/multiplatform/ads/reportSearchImpressionSpList
- Official docs: https://apidoc.lingxing.com/#/docs/MultiPlatform/Advertisement/walmart-reportSearchImpressionSpList
- Required: advertiserIds (Long[]), startDate, endDate.
- Optional: searchText, campaignIds, searchedKeywords, reportFieldFilter, pageSize (max 200), pageNum, day (3/14/30), orderField, orderType.
- Gateway requests include operationSourceType=gateway.
- Response data.list contains mpSellerName, mpAdvertiserName, advertiserId, campaignName, campaignId, campaignType, targetingType, campaignStatus, searchedKeyword, numAdsShown, numAdsClicks, adSpend, advertisedSkuSales, advertisedSkuUnits, attributedOrders, otherSkuSales, otherSkuUnits, cpc, ctr, cvr, cpa and percentage share fields.
- No itemId/adGroupId/keywordId/triggering keyword field is documented in the search-term row.

### Manual keyword coverage

- Method: POST
- Path: /basicOpen/multiplatform/ads/reportKeywordSpList
- Purpose: read the existing manual keyword inventory/performance for exact searchedKeyword coverage checks.
- Do not expose its matchType or keywordName as the “original triggering keyword”; keywordName is only the manually configured keyword inventory used for exact coverage.

## Internal API draft

All read APIs use the existing SuccessEnvelope and request_id. All filters are applied server-side before pagination. No route performs external provider calls.

### GET /api/ads/search-terms/summary

Query:
- start_date, end_date (required, bounded)
- store_ids[], advertiser_ids[], campaign_ids[]
- targeting_type: all | auto | manual
- q
- conversion_state: all | orders | no_orders
- optional order/spend min/max

Response:
- total_terms
- converting_terms
- auto_converting_not_manually_covered
- no_order_terms_with_spend
- ad_spend_total
- attributed_orders_total
- direct_sales_total
- other_sales_total
- freshness / partial-data state

### GET /api/ads/search-terms

Query:
- view: summary | detail
- same filters
- page, page_size
- sort_by, sort_order

Summary rows group exact normalized search terms across the requested comparison dimensions. Detail rows preserve advertiser/campaign/date/source identity. A summary row is not an external source record.

### GET /api/ads/search-terms/trends

Query:
- search_term_key or selected summary identity
- date range and same account/store/campaign/type filters

Response:
- daily or explicitly labelled rolling-window points
- current/prior values and deltas
- no unapproved anomaly thresholds

### GET /api/ads/search-terms/options

Returns authorized store, advertiser, campaign and uniquely mapped Listing options only. Unresolved mappings remain explicit.

### Internal action task APIs — pending owner decision

- GET /api/ads/search-terms/actions
- POST /api/ads/search-terms/actions
- POST /api/ads/search-terms/actions/batch
- PATCH /api/ads/search-terms/actions/{action_id}

These APIs only create and update internal tasks. They do not call Lingxing, do not claim external write success, and are not implemented until the owner approves the fallback.

### Refresh

Reuse existing Integration Sync:
- POST /api/integrations/sync-configs/{config_id}/run
- GET /api/integrations/sync-runs/{run_id}

## Permissions

- ads.search_terms.view
- ads.search_terms.actions.manage (pending)
- integrations:execute (existing)

All routes require authenticated principal and trusted source_account scope. The UI's global view does not override IAM scope.

## Errors

- ADS_SEARCH_TERMS_SCOPE_DENIED
- ADS_SEARCH_TERMS_DATA_NOT_READY
- ADS_SEARCH_TERMS_SYNC_IN_PROGRESS
- ADS_SEARCH_TERMS_MAPPING_UNRESOLVED
- ADS_SEARCH_TERMS_ACTION_WRITE_UNAVAILABLE
- Existing integration sync errors

## Data lineage

meta.source_tables should identify:
- fact_walmart_ad_search_term_daily
- fact_walmart_keyword_sp_daily
- fact_walmart_ad_item_sp_daily
- dim_walmart_advertisers
- dim_lingxing_stores
- mart_listing_management_current
- ops_ads_search_term_actions (if approved)

Never return RAW payload_json, signed URLs, tokens or credential values.

# Lingxing Walmart SP Search Impression / Search Terms Contract

Status: Owner-provided official documentation snapshot; repository normalization pending.
Provider: Lingxing OpenAPI
Official page: https://apidoc.lingxing.com/#/docs/MultiPlatform/Advertisement/walmart-reportSearchImpressionSpList

## Endpoint

- Method: POST
- Path: /basicOpen/multiplatform/ads/reportSearchImpressionSpList
- Protocol: HTTPS
- Token bucket capacity: 1

## Request

Required:
- advertiserIds: Long[]
- startDate: yyyy-MM-dd
- endDate: yyyy-MM-dd

Optional:
- searchText: string, fuzzy match against searchedKeyword
- campaignIds: Long[]
- searchedKeywords: string[]
- reportFieldFilter: object of camelCase metric key to [min,max]
- pageSize: integer, default 20, maximum 200
- pageNum: integer, starts at 1
- day: 3, 14 or 30 attribution days
- orderField: camelCase field
- orderType: ASC or DESC
- operationSourceType: gateway (documented cURL example)

Signing/auth uses the existing Lingxing Token Manager and query-sign client. Never store or print credential values.

## Response envelope

- code: 0 indicates success
- message
- error_details
- request_id
- response_time
- data.total
- data.list[]

## Documented row fields

- mpSellerName
- mpAdvertiserName
- advertiserId
- campaignName
- biddingStrategy
- targetingType
- campaignStatus
- campaignId
- searchedKeyword
- numAdsShown
- numAdsClicks
- adSpend
- advertisedSkuSales
- advertisedSkuUnits
- attributedOrders
- otherSkuSales
- otherSkuUnits
- cpc
- ctr
- cvr
- cpa
- adSpendPercent
- numAdsShownPercent
- numAdsClicksPercent
- attributedOrdersPercent
- advertisedSkuSalesPercent
- advertisedSkuUnitsPercent
- otherSkuSalesPercent
- otherSkuUnitsPercent

## Important limitations

- The documented row does not contain itemId, adGroupId, adItemId, keywordId or a triggered keyword/matchType field.
- Listing mapping must be derived from existing campaign/item facts only when the mapping is unique; ambiguous cases stay unresolved.
- This is a read/query interface. It does not add keywords, add negative keywords, change bids or modify campaigns.
- Page size max 200; all pages must be fetched and validated.
- Provider request success does not prove data completeness.

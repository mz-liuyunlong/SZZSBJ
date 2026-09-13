# 查询沃尔玛-广告 - SP广告 - 广告活动 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-058A66EC8E8E` |
| Contract status | `READY_FOR_PRP` |
| Source document | `No matching legacy Markdown; normalized CSV only` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-058A66EC8E8E` |
| Path | `/basicOpen/multiplatform/ads/queryCampaignSpList` |
| Method | `POST` |
| Protocol | `UNVERIFIED` |
| Pagination | `pageNum/pageSize` |
| Page / batch limit | `unknown` |
| Rate limit evidence | `1` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-058A66EC8E8E (14 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `advertiserIds` | `advertiserIds` | `array` | `是` |
| `campaignIds` | `campaignIds` | `array` | `否` |
| `campaignType` | `campaignType` | `array` | `是` |
| `day` | `day` | `int` | `是` |
| `endDate` | `endDate` | `string` | `是` |
| `operationSourceType` | `operationSourceType` | `string` | `是` |
| `orderField` | `orderField` | `string` | `否` |
| `orderType` | `orderType` | `string` | `否` |
| `pageNum` | `pageNum` | `int` | `是` |
| `pageSize` | `pageSize` | `int` | `是` |
| `paging` | `paging` | `boolean` | `是` |
| `searchText` | `searchText` | `string` | `否` |
| `startDate` | `startDate` | `string` | `是` |
| `status` | `status` | `array` | `否` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-058A66EC8E8E (72 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `object` | `是` |
| `data.list` | `list` | `array` | `是` |
| `data.list[].acos` | `acos` | `double` | `否` |
| `data.list[].adSpend` | `adSpend` | `double` | `否` |
| `data.list[].advertisedSkuSales` | `advertisedSkuSales` | `double` | `否` |
| `data.list[].advertisedSkuUnits` | `advertisedSkuUnits` | `int` | `否` |
| `data.list[].advertiserId` | `advertiserId` | `long` | `否` |
| `data.list[].aov` | `aov` | `double` | `否` |
| `data.list[].appliedTemplate` | `appliedTemplate` | `array` | `否` |
| `data.list[].attributedOrders` | `attributedOrders` | `int` | `否` |
| `data.list[].attributedSales` | `attributedSales` | `double` | `否` |
| `data.list[].attributedUnits` | `attributedUnits` | `int` | `否` |
| `data.list[].benchmarkVal` | `benchmarkVal` | `double` | `否` |
| `data.list[].biddingStrategy` | `biddingStrategy` | `object` | `是` |
| `data.list[].biddingStrategy.biddingStrategyStatus` | `biddingStrategyStatus` | `string` | `是` |
| `data.list[].biddingStrategy.strategy` | `strategy` | `string` | `是` |
| `data.list[].biddingStrategy.troas` | `troas` | `string` | `是` |
| `data.list[].budgetType` | `budgetType` | `string` | `否` |
| `data.list[].campaignId` | `campaignId` | `long` | `否` |
| `data.list[].campaignName` | `campaignName` | `string` | `否` |
| `data.list[].campaignStatus` | `campaignStatus` | `string` | `否` |
| `data.list[].campaignType` | `campaignType` | `string` | `否` |
| `data.list[].completeViewRevenue` | `completeViewRevenue` | `double` | `否` |
| `data.list[].cpa` | `cpa` | `double` | `否` |
| `data.list[].cpc` | `cpc` | `double` | `否` |
| `data.list[].ctr` | `ctr` | `double` | `否` |
| `data.list[].cvr` | `cvr` | `double` | `否` |
| `data.list[].dailyBudget` | `dailyBudget` | `double` | `否` |
| `data.list[].endDate` | `endDate` | `string` | `否` |
| `data.list[].entityCreateAt` | `entityCreateAt` | `string` | `否` |
| `data.list[].haloCompleteViewRevenue` | `haloCompleteViewRevenue` | `double` | `否` |
| `data.list[].isApplyTime` | `isApplyTime` | `boolean` | `否` |
| `data.list[].key` | `key` | `long` | `否` |
| `data.list[].mpAdvertiserName` | `mpAdvertiserName` | `string` | `否` |
| `data.list[].mpSellerName` | `mpSellerName` | `string` | `否` |
| `data.list[].ntbOrderRate` | `ntbOrderRate` | `double` | `否` |
| `data.list[].ntbOrders` | `ntbOrders` | `int` | `否` |
| `data.list[].ntbOrdersPercent` | `ntbOrdersPercent` | `double` | `否` |
| `data.list[].ntbRevenue` | `ntbRevenue` | `double` | `否` |
| `data.list[].ntbRevenuePercent` | `ntbRevenuePercent` | `double` | `否` |
| `data.list[].ntbUnits` | `ntbUnits` | `int` | `否` |
| `data.list[].ntbUnitsPercent` | `ntbUnitsPercent` | `double` | `否` |
| `data.list[].numAdsClicks` | `numAdsClicks` | `int` | `否` |
| `data.list[].numAdsShown` | `numAdsShown` | `int` | `否` |
| `data.list[].otherSkuSales` | `otherSkuSales` | `double` | `否` |
| `data.list[].otherSkuUnits` | `otherSkuUnits` | `int` | `否` |
| `data.list[].reportTag` | `reportTag` | `string` | `否` |
| `data.list[].roas` | `roas` | `double` | `否` |
| `data.list[].rollover` | `rollover` | `boolean` | `否` |
| `data.list[].startDate` | `startDate` | `string` | `否` |
| `data.list[].targetingType` | `targetingType` | `string` | `否` |
| `data.list[].totalBudget` | `totalBudget` | `double` | `否` |
| `data.list[].totalCompleteViewOrders` | `totalCompleteViewOrders` | `long` | `否` |
| `data.list[].totalCompleteViewUnits` | `totalCompleteViewUnits` | `long` | `否` |
| `data.list[].video5SecondViews` | `video5SecondViews` | `long` | `否` |
| `data.list[].videoCompleteViews` | `videoCompleteViews` | `long` | `否` |
| `data.list[].videoFirstQuartileViews` | `videoFirstQuartileViews` | `long` | `否` |
| `data.list[].videoImpressions` | `videoImpressions` | `long` | `否` |
| `data.list[].videoMidpointViews` | `videoMidpointViews` | `long` | `否` |
| `data.list[].videoThirdQuartileViews` | `videoThirdQuartileViews` | `long` | `否` |
| `data.list[].videoUnmutes` | `videoUnmutes` | `long` | `否` |
| `data.list[].viewThroughOrders` | `viewThroughOrders` | `long` | `否` |
| `data.list[].viewThroughSales` | `viewThroughSales` | `double` | `否` |
| `data.list[].viewThroughUnitsSold` | `viewThroughUnitsSold` | `long` | `否` |
| `data.list[].viewableImpressions` | `viewableImpressions` | `long` | `否` |
| `data.total` | `total` | `int` | `是` |
| `error_details` | `error_details` | `array` | `是` |
| `message` | `message` | `string` | `是` |
| `request_id` | `request_id` | `string` | `是` |
| `response_time` | `response_time` | `string` | `是` |
| `total` | `total` | `int` | `是` |


## Known missing evidence

- endpoint-specific protocol evidence
- provider authentication applicability
- account/data scope
- provider verification


## Safety decision

Contract shape is repository-derived and unverified; no real call is authorized. `READY_FOR_PRP` permits only a future evidence-backed PRP; it does not approve provider traffic, implementation, data writes, or production use. Deleted, non-Walmart, or side-effecting entries require separate Owner re-evaluation.

## Redacted request shape

```json
{
  "advertiserIds": "<redacted>",
  "campaignIds": "<redacted>",
  "campaignType": "<redacted>",
  "day": "<redacted>",
  "endDate": "<redacted>",
  "operationSourceType": "<redacted>",
  "orderField": "<redacted>",
  "orderType": "<redacted>"
}
```

## Redacted response shape

```json
{
  "code": "<redacted>",
  "data": "<redacted>",
  "error_details": "<redacted>",
  "message": "<redacted>",
  "request_id": "<redacted>",
  "response_time": "<redacted>",
  "total": "<redacted>"
}
```

Only field names are shown. No real identifier, product value, URL, credential, or response content is included.

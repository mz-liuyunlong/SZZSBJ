# 查询沃尔玛-广告 - SP广告 - 广告 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-0CB86D55776C` |
| Contract status | `READY_FOR_PRP` |
| Source document | `old-system/source/docs/lingxing/MultiPlatform/Advertisement/walmart-reportAdItemSpList_17.md` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-0CB86D55776C` |
| Path | `/basicOpen/multiplatform/ads/reportAdItemSpList` |
| Method | `POST` |
| Protocol | `HTTPS` |
| Pagination | `pageNum/pageSize` |
| Page / batch limit | `200` |
| Rate limit evidence | `1` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-0CB86D55776C (15 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `adGroupIds` | `adGroupIds` | `array` | `否` |
| `advertiserIds` | `advertiserIds` | `array` | `是` |
| `campaignIds` | `campaignIds` | `array` | `否` |
| `campaignType` | `campaignType` | `array` | `是` |
| `day` | `day` | `int` | `否` |
| `endDate` | `endDate` | `string` | `是` |
| `orderField` | `orderField` | `string` | `否` |
| `orderType` | `orderType` | `string` | `否` |
| `pageNum` | `pageNum` | `int` | `否` |
| `pageSize` | `pageSize` | `int` | `否` |
| `paging` | `paging` | `boolean` | `否` |
| `searchText` | `searchText` | `string` | `否` |
| `searchType` | `searchType` | `string` | `否` |
| `startDate` | `startDate` | `string` | `是` |
| `status` | `status` | `array` | `否` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-0CB86D55776C (71 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `object` | `是` |
| `data.list` | `list` | `array` | `是` |
| `data.list[].acos` | `acos` | `string` | `是` |
| `data.list[].adGroupId` | `adGroupId` | `string` | `是` |
| `data.list[].adGroupName` | `adGroupName` | `string` | `是` |
| `data.list[].adGroupStatus` | `adGroupStatus` | `string` | `是` |
| `data.list[].adItemId` | `adItemId` | `string` | `是` |
| `data.list[].adName` | `adName` | `string` | `是` |
| `data.list[].adSpend` | `adSpend` | `string` | `是` |
| `data.list[].adStatus` | `adStatus` | `string` | `是` |
| `data.list[].addDate` | `addDate` | `string` | `是` |
| `data.list[].advertisedSkuSales` | `advertisedSkuSales` | `string` | `是` |
| `data.list[].advertisedSkuUnits` | `advertisedSkuUnits` | `string` | `是` |
| `data.list[].advertiserId` | `advertiserId` | `string` | `是` |
| `data.list[].aov` | `aov` | `string` | `是` |
| `data.list[].appliedTemplate` | `appliedTemplate` | `array` | `是` |
| `data.list[].appliedTemplate.benchmarkFixedVal` | `benchmarkFixedVal` | `string` | `是` |
| `data.list[].appliedTemplate.benchmarkType` | `benchmarkType` | `string` | `是` |
| `data.list[].appliedTemplate.curBenchmarkVal` | `curBenchmarkVal` | `string` | `是` |
| `data.list[].appliedTemplate.effectiveTime` | `effectiveTime` | `object` | `是` |
| `data.list[].appliedTemplate.effectiveTime.begin` | `begin` | `string` | `是` |
| `data.list[].appliedTemplate.effectiveTime.end` | `end` | `string` | `是` |
| `data.list[].appliedTemplate.id` | `id` | `string` | `是` |
| `data.list[].appliedTemplate.taskName` | `taskName` | `string` | `是` |
| `data.list[].appliedTemplate.taskStatus` | `taskStatus` | `string` | `是` |
| `data.list[].appliedTemplate.taskType` | `taskType` | `string` | `是` |
| `data.list[].appliedTemplate.timezone` | `timezone` | `string` | `是` |
| `data.list[].attributedOrders` | `attributedOrders` | `string` | `是` |
| `data.list[].attributedSales` | `attributedSales` | `string` | `是` |
| `data.list[].attributedUnits` | `attributedUnits` | `string` | `是` |
| `data.list[].benchmarkVal` | `benchmarkVal` | `string` | `是` |
| `data.list[].bid` | `bid` | `string` | `是` |
| `data.list[].campaignAndTargetingType` | `campaignAndTargetingType` | `string` | `是` |
| `data.list[].campaignId` | `campaignId` | `string` | `是` |
| `data.list[].campaignName` | `campaignName` | `string` | `是` |
| `data.list[].campaignStatus` | `campaignStatus` | `string` | `是` |
| `data.list[].campaignType` | `campaignType` | `string` | `是` |
| `data.list[].cpa` | `cpa` | `string` | `是` |
| `data.list[].cpc` | `cpc` | `string` | `是` |
| `data.list[].ctr` | `ctr` | `string` | `是` |
| `data.list[].cvr` | `cvr` | `string` | `是` |
| `data.list[].entityCreateAt` | `entityCreateAt` | `string` | `是` |
| `data.list[].isApplyTime` | `isApplyTime` | `string` | `是` |
| `data.list[].itemId` | `itemId` | `string` | `是` |
| `data.list[].itemImageUrl` | `itemImageUrl` | `string` | `是` |
| `data.list[].itemPageUrl` | `itemPageUrl` | `string` | `是` |
| `data.list[].key` | `key` | `string` | `是` |
| `data.list[].mpAdvertiserName` | `mpAdvertiserName` | `string` | `是` |
| `data.list[].mpSellerName` | `mpSellerName` | `string` | `是` |
| `data.list[].ntbOrderRate` | `ntbOrderRate` | `string` | `是` |
| `data.list[].ntbOrders` | `ntbOrders` | `string` | `是` |
| `data.list[].ntbOrdersPercent` | `ntbOrdersPercent` | `string` | `是` |
| `data.list[].ntbRevenue` | `ntbRevenue` | `string` | `是` |
| `data.list[].ntbRevenuePercent` | `ntbRevenuePercent` | `string` | `是` |
| `data.list[].ntbUnits` | `ntbUnits` | `string` | `是` |
| `data.list[].ntbUnitsPercent` | `ntbUnitsPercent` | `string` | `是` |
| `data.list[].numAdsClicks` | `numAdsClicks` | `string` | `是` |
| `data.list[].numAdsShown` | `numAdsShown` | `string` | `是` |
| `data.list[].otherSkuSales` | `otherSkuSales` | `string` | `是` |
| `data.list[].otherSkuUnits` | `otherSkuUnits` | `string` | `是` |
| `data.list[].reviewReason` | `reviewReason` | `string` | `是` |
| `data.list[].reviewStatus` | `reviewStatus` | `string` | `是` |
| `data.list[].roas` | `roas` | `string` | `是` |
| `data.list[].suggestedBid` | `suggestedBid` | `string` | `是` |
| `data.total` | `total` | `string` | `是` |
| `error_details` | `error_details` | `array` | `是` |
| `message` | `message` | `string` | `是` |
| `request_id` | `request_id` | `string` | `是` |
| `response_time` | `response_time` | `string` | `是` |
| `total` | `total` | `int` | `是` |


## Known missing evidence

- provider authentication applicability
- account/data scope
- provider verification


## Safety decision

Contract shape is repository-derived and unverified; no real call is authorized. `READY_FOR_PRP` permits only a future evidence-backed PRP; it does not approve provider traffic, implementation, data writes, or production use. Deleted, non-Walmart, or side-effecting entries require separate Owner re-evaluation.

## Redacted request shape

```json
{
  "adGroupIds": "<redacted>",
  "advertiserIds": "<redacted>",
  "campaignIds": "<redacted>",
  "campaignType": "<redacted>",
  "day": "<redacted>",
  "endDate": "<redacted>",
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

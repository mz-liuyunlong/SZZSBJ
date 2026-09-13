# Walmart-查询回款明细列表 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-63E99B54ED72` |
| Contract status | `READY_FOR_PRP` |
| Source document | `No matching legacy Markdown; normalized CSV only` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-63E99B54ED72` |
| Path | `/basicOpen/multiplatformFinance/walmart/bill/payout/list` |
| Method | `POST` |
| Protocol | `UNVERIFIED` |
| Pagination | `offset/length` |
| Page / batch limit | `200` |
| Rate limit evidence | `1` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-63E99B54ED72 (19 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `compareLogic` | `compareLogic` | `string` | `否` |
| `currencyCode` | `currencyCode` | `string` | `否` |
| `endDate` | `endDate` | `string` | `否` |
| `fieldCompares` | `fieldCompares` | `array` | `否` |
| `fieldCompares[].field` | `field` | `string` | `是` |
| `fieldCompares[].operator` | `operator` | `string` | `是` |
| `fieldCompares[].value` | `value` | `double` | `是` |
| `hasDifference` | `hasDifference` | `Boolean` | `否` |
| `length` | `length` | `int` | `是` |
| `offset` | `offset` | `int` | `是` |
| `searchExactly` | `searchExactly` | `Boolean` | `否` |
| `searchMultiValue` | `searchMultiValue` | `array` | `否` |
| `searchSingleValue` | `searchSingleValue` | `string` | `否` |
| `searchType` | `searchType` | `int` | `否` |
| `sids` | `sids` | `array` | `否` |
| `siteCodes` | `siteCodes` | `array` | `否` |
| `sortField` | `sortField` | `string` | `否` |
| `sortType` | `sortType` | `string` | `否` |
| `startDate` | `startDate` | `string` | `否` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-63E99B54ED72 (35 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `object` | `是` |
| `data.list` | `list` | `array` | `是` |
| `data.list[].companyId` | `companyId` | `long` | `是` |
| `data.list[].currency` | `currency` | `string` | `是` |
| `data.list[].currencyIcon` | `currencyIcon` | `string` | `是` |
| `data.list[].id` | `id` | `long` | `是` |
| `data.list[].periodEndDate` | `periodEndDate` | `string` | `是` |
| `data.list[].periodRange` | `periodRange` | `string` | `是` |
| `data.list[].periodStartDate` | `periodStartDate` | `string` | `是` |
| `data.list[].platformCode` | `platformCode` | `string` | `是` |
| `data.list[].reportKey` | `reportKey` | `string` | `是` |
| `data.list[].settlementCount` | `settlementCount` | `long` | `是` |
| `data.list[].settlementDifference` | `settlementDifference` | `double` | `是` |
| `data.list[].site` | `site` | `string` | `是` |
| `data.list[].siteCode` | `siteCode` | `string` | `是` |
| `data.list[].siteDisplay` | `siteDisplay` | `string` | `是` |
| `data.list[].storeId` | `storeId` | `long` | `是` |
| `data.list[].storeName` | `storeName` | `string` | `是` |
| `data.list[].totalPayable` | `totalPayable` | `double` | `是` |
| `data.list[].transactionDescription` | `transactionDescription` | `string` | `是` |
| `data.list[].transactionPostedTimestamp` | `transactionPostedTimestamp` | `string` | `是` |
| `data.list[].transactionType` | `transactionType` | `string` | `是` |
| `data.totalCount` | `totalCount` | `long` | `是` |
| `data.totalSum` | `totalSum` | `object` | `是` |
| `data.totalSum.currency` | `currency` | `string` | `是` |
| `data.totalSum.currencyIcon` | `currencyIcon` | `string` | `是` |
| `data.totalSum.settlementCount` | `settlementCount` | `long` | `是` |
| `data.totalSum.settlementDifference` | `settlementDifference` | `double` | `是` |
| `data.totalSum.totalCount` | `totalCount` | `long` | `是` |
| `data.totalSum.totalPayable` | `totalPayable` | `double` | `是` |
| `error_details` | `error_details` | `array` | `是` |
| `message` | `message` | `string` | `是` |
| `request_id` | `request_id` | `string` | `是` |
| `response_time` | `response_time` | `string` | `是` |


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
  "compareLogic": "<redacted>",
  "currencyCode": "<redacted>",
  "endDate": "<redacted>",
  "fieldCompares": "<redacted>",
  "hasDifference": "<redacted>",
  "length": "<redacted>",
  "offset": "<redacted>",
  "searchExactly": "<redacted>"
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
  "response_time": "<redacted>"
}
```

Only field names are shown. No real identifier, product value, URL, credential, or response content is included.

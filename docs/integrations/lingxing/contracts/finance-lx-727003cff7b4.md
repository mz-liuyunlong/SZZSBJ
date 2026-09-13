# Walmart-查询结算账单列表 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-727003CFF7B4` |
| Contract status | `READY_FOR_PRP` |
| Source document | `No matching legacy Markdown; normalized CSV only` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-727003CFF7B4` |
| Path | `/basicOpen/multiplatformFinance/walmart/bill/statement/list` |
| Method | `POST` |
| Protocol | `UNVERIFIED` |
| Pagination | `offset/length` |
| Page / batch limit | `200` |
| Rate limit evidence | `1` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-727003CFF7B4 (16 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `amountTypes` | `amountTypes` | `array` | `否` |
| `currencyCode` | `currencyCode` | `string` | `否` |
| `endDate` | `endDate` | `string` | `否` |
| `fulfillmentTypes` | `fulfillmentTypes` | `array` | `否` |
| `length` | `length` | `int` | `是` |
| `offset` | `offset` | `int` | `是` |
| `searchExactly` | `searchExactly` | `Boolean` | `否` |
| `searchMultiValue` | `searchMultiValue` | `array` | `否` |
| `searchSingleValue` | `searchSingleValue` | `string` | `否` |
| `searchType` | `searchType` | `int` | `否` |
| `sids` | `sids` | `array` | `否` |
| `sortField` | `sortField` | `string` | `否` |
| `sortType` | `sortType` | `string` | `否` |
| `startDate` | `startDate` | `string` | `否` |
| `transactionDescriptions` | `transactionDescriptions` | `array` | `否` |
| `transactionTypes` | `transactionTypes` | `array` | `否` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-727003CFF7B4 (77 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `object` | `是` |
| `data.list` | `list` | `array` | `是` |
| `data.list[].amount` | `amount` | `double` | `是` |
| `data.list[].amountType` | `amountType` | `string` | `是` |
| `data.list[].baseCommissionRate` | `baseCommissionRate` | `double` | `是` |
| `data.list[].campaignId` | `campaignId` | `string` | `是` |
| `data.list[].chargeSavings` | `chargeSavings` | `double` | `是` |
| `data.list[].commissionIncentiveProgram` | `commissionIncentiveProgram` | `string` | `是` |
| `data.list[].commissionRate` | `commissionRate` | `double` | `是` |
| `data.list[].commissionRule` | `commissionRule` | `string` | `是` |
| `data.list[].commissionSaving` | `commissionSaving` | `double` | `是` |
| `data.list[].companyId` | `companyId` | `long` | `是` |
| `data.list[].contractCategory` | `contractCategory` | `string` | `是` |
| `data.list[].currency` | `currency` | `string` | `是` |
| `data.list[].currencyIcon` | `currencyIcon` | `string` | `是` |
| `data.list[].customerOrderLineNo` | `customerOrderLineNo` | `string` | `是` |
| `data.list[].customerOrderNo` | `customerOrderNo` | `string` | `是` |
| `data.list[].customerPromoType` | `customerPromoType` | `string` | `是` |
| `data.list[].deleteFlag` | `deleteFlag` | `int` | `是` |
| `data.list[].fulfillmentDetails` | `fulfillmentDetails` | `string` | `是` |
| `data.list[].fulfillmentType` | `fulfillmentType` | `string` | `是` |
| `data.list[].id` | `id` | `long` | `是` |
| `data.list[].incentiveProgramName` | `incentiveProgramName` | `string` | `是` |
| `data.list[].itemCondition` | `itemCondition` | `string` | `是` |
| `data.list[].originalCharge` | `originalCharge` | `double` | `是` |
| `data.list[].originalCommission` | `originalCommission` | `double` | `是` |
| `data.list[].partnerGtin` | `partnerGtin` | `string` | `是` |
| `data.list[].partnerItemId` | `partnerItemId` | `string` | `是` |
| `data.list[].partnerItemName` | `partnerItemName` | `string` | `是` |
| `data.list[].periodEndDate` | `periodEndDate` | `string` | `是` |
| `data.list[].periodStartDate` | `periodStartDate` | `string` | `是` |
| `data.list[].platformCode` | `platformCode` | `string` | `是` |
| `data.list[].productTaxCode` | `productTaxCode` | `string` | `是` |
| `data.list[].productType` | `productType` | `string` | `是` |
| `data.list[].purchaseOrderLineNo` | `purchaseOrderLineNo` | `string` | `是` |
| `data.list[].purchaseOrderNo` | `purchaseOrderNo` | `string` | `是` |
| `data.list[].remark` | `remark` | `string` | `是` |
| `data.list[].reportDate` | `reportDate` | `string` | `是` |
| `data.list[].reportId` | `reportId` | `long` | `是` |
| `data.list[].reportKey` | `reportKey` | `string` | `是` |
| `data.list[].shipQty` | `shipQty` | `int` | `是` |
| `data.list[].shipToCity` | `shipToCity` | `string` | `是` |
| `data.list[].shipToCountry` | `shipToCountry` | `string` | `是` |
| `data.list[].shipToState` | `shipToState` | `string` | `是` |
| `data.list[].shipToZipcode` | `shipToZipcode` | `string` | `是` |
| `data.list[].shippingMethod` | `shippingMethod` | `string` | `是` |
| `data.list[].site` | `site` | `string` | `是` |
| `data.list[].siteCode` | `siteCode` | `string` | `是` |
| `data.list[].siteDisplay` | `siteDisplay` | `string` | `是` |
| `data.list[].storeId` | `storeId` | `long` | `是` |
| `data.list[].storeName` | `storeName` | `string` | `是` |
| `data.list[].totalPayable` | `totalPayable` | `double` | `是` |
| `data.list[].totalWalmartFundedSavingsProgram` | `totalWalmartFundedSavingsProgram` | `double` | `是` |
| `data.list[].transactionDescription` | `transactionDescription` | `string` | `是` |
| `data.list[].transactionKey` | `transactionKey` | `string` | `是` |
| `data.list[].transactionPostedTimestamp` | `transactionPostedTimestamp` | `string` | `是` |
| `data.list[].transactionReasonDescription` | `transactionReasonDescription` | `string` | `是` |
| `data.list[].transactionType` | `transactionType` | `string` | `是` |
| `data.list[].uniqueNo` | `uniqueNo` | `string` | `是` |
| `data.totalCount` | `totalCount` | `long` | `是` |
| `data.totalSum` | `totalSum` | `object` | `是` |
| `data.totalSum.amount` | `amount` | `double` | `是` |
| `data.totalSum.chargeSavings` | `chargeSavings` | `double` | `是` |
| `data.totalSum.commissionSaving` | `commissionSaving` | `double` | `是` |
| `data.totalSum.currency` | `currency` | `string` | `是` |
| `data.totalSum.currencyIcon` | `currencyIcon` | `string` | `是` |
| `data.totalSum.originalCharge` | `originalCharge` | `double` | `是` |
| `data.totalSum.originalCommission` | `originalCommission` | `double` | `是` |
| `data.totalSum.shipQty` | `shipQty` | `int` | `是` |
| `data.totalSum.totalCount` | `totalCount` | `long` | `是` |
| `data.totalSum.totalPayable` | `totalPayable` | `double` | `是` |
| `data.totalSum.totalWalmartFundedSavingsProgram` | `totalWalmartFundedSavingsProgram` | `double` | `是` |
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
  "amountTypes": "<redacted>",
  "currencyCode": "<redacted>",
  "endDate": "<redacted>",
  "fulfillmentTypes": "<redacted>",
  "length": "<redacted>",
  "offset": "<redacted>",
  "searchExactly": "<redacted>",
  "searchMultiValue": "<redacted>"
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

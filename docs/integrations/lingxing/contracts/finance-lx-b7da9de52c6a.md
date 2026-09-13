# 查询可用报告列表 - Walmart Payment — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-B7DA9DE52C6A` |
| Contract status | `READY_FOR_PRP` |
| Source document | `No matching legacy Markdown; normalized CSV only` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-B7DA9DE52C6A` |
| Path | `/cepf/fms/openapi/walmartPayment/queryReport` |
| Method | `POST` |
| Protocol | `UNVERIFIED` |
| Pagination | `无` |
| Page / batch limit | `unknown` |
| Rate limit evidence | `10` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-B7DA9DE52C6A (2 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `new_report` | `new_report` | `int` | `是` |
| `store_id` | `store_id` | `array` | `是` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-B7DA9DE52C6A (10 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `array` | `是` |
| `data[].list` | `list` | `array` | `是` |
| `data[].list.report_date` | `report_date` | `string` | `是` |
| `data[].list.report_id` | `report_id` | `string` | `是` |
| `data[].store_id` | `store_id` | `string` | `是` |
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
  "new_report": "<redacted>",
  "store_id": "<redacted>"
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

# 查询沃尔玛广告主列表 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-1DC15769BD57` |
| Contract status | `READY_FOR_PRP` |
| Source document | `old-system/source/docs/lingxing/WalmartQueryAdvertiserList.md` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-1DC15769BD57` |
| Path | `/basicOpen/adReport/advertiser/list` |
| Method | `POST` |
| Protocol | `HTTPS` |
| Pagination | `page/limit` |
| Page / batch limit | `unknown` |
| Rate limit evidence | `1` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-1DC15769BD57 (4 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `limit` | `limit` | `int` | `否` |
| `page` | `page` | `int` | `否` |
| `paging` | `paging` | `string` | `是` |
| `searchText` | `searchText` | `string` | `否` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-1DC15769BD57 (11 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `object` | `是` |
| `data.list` | `list` | `array` | `是` |
| `data.list[].advertiserId` | `advertiserId` | `string` | `是` |
| `data.list[].advertiserName` | `advertiserName` | `string` | `是` |
| `data.list[].status` | `status` | `int` | `是` |
| `data.total` | `total` | `int` | `是` |
| `error_details` | `error_details` | `array` | `是` |
| `message` | `message` | `string` | `是` |
| `request_id` | `request_id` | `string` | `是` |
| `response_time` | `response_time` | `string` | `是` |


## Known missing evidence

- provider authentication applicability
- account/data scope
- provider verification


## Safety decision

Contract shape is repository-derived and unverified; no real call is authorized. `READY_FOR_PRP` permits only a future evidence-backed PRP; it does not approve provider traffic, implementation, data writes, or production use. Deleted, non-Walmart, or side-effecting entries require separate Owner re-evaluation.

## Redacted request shape

```json
{
  "limit": "<redacted>",
  "page": "<redacted>",
  "paging": "<redacted>",
  "searchText": "<redacted>"
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

# 查询多平台店铺信息 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-F8354824E040` |
| Contract status | `READY_FOR_PRP` |
| Source document | `old-system/source/docs/lingxing/StoreInfoV2.md` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-F8354824E040` |
| Path | `/pb/mp/shop/v2/getSellerList` |
| Method | `POST` |
| Protocol | `HTTPS` |
| Pagination | `offset/length` |
| Page / batch limit | `200` |
| Rate limit evidence | `10` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `yes` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-F8354824E040 (5 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `is_sync` | `is_sync` | `int` | `否` |
| `length` | `length` | `int` | `否` |
| `offset` | `offset` | `int` | `否` |
| `platform_code` | `platform_code` | `array` | `否` |
| `status` | `status` | `int` | `否` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-F8354824E040 (15 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `array` | `是` |
| `data[].list` | `list` | `array` | `是` |
| `data[].list.currency` | `currency` | `string` | `是` |
| `data[].list.is_sync` | `is_sync` | `int` | `是` |
| `data[].list.platform_code` | `platform_code` | `int` | `是` |
| `data[].list.platform_name` | `platform_name` | `string` | `是` |
| `data[].list.sid` | `sid` | `string` | `是` |
| `data[].list.status` | `status` | `int` | `是` |
| `data[].list.store_id` | `store_id` | `string` | `是` |
| `data[].list.store_name` | `store_name` | `string` | `是` |
| `data[].total` | `total` | `int` | `是` |
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
  "is_sync": "<redacted>",
  "length": "<redacted>",
  "offset": "<redacted>",
  "platform_code": "<redacted>",
  "status": "<redacted>"
}
```

## Redacted response shape

```json
{
  "code": "<redacted>",
  "data": "<redacted>",
  "message": "<redacted>",
  "request_id": "<redacted>",
  "response_time": "<redacted>"
}
```

Only field names are shown. No real identifier, product value, URL, credential, or response content is included.

# 查询WFS货件可添加商品列表 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-1074DDF41A1A` |
| Contract status | `DO_NOT_USE` |
| Source document | `No matching legacy Markdown; normalized CSV only` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv#LX-1074DDF41A1A` |
| Path | `/basicOpen/multiplatform/cargo/addCargoGoods/list` |
| Method | `POST` |
| Protocol | `UNVERIFIED` |
| Pagination | `offset/length` |
| Page / batch limit | `200` |
| Rate limit evidence | `1` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `no` |

## Request parameters

Source: `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv#LX-1074DDF41A1A (3 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `length` | `length` | `int` | `否` |
| `offset` | `offset` | `int` | `否` |
| `store_id` | `store_id` | `string` | `是` |


## Response fields

Source: `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv#LX-1074DDF41A1A (13 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `data` | `data` | `array` | `是` |
| `data[].gtin` | `gtin` | `string` | `是` |
| `data[].item_id` | `item_id` | `string` | `是` |
| `data[].local_name` | `local_name` | `string` | `是` |
| `data[].local_sku` | `local_sku` | `string` | `是` |
| `data[].msku` | `msku` | `string` | `是` |
| `data[].picture_url` | `picture_url` | `string` | `是` |
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

Current classification is excluded or incomplete. `READY_FOR_PRP` permits only a future evidence-backed PRP; it does not approve provider traffic, implementation, data writes, or production use. Deleted, non-Walmart, or side-effecting entries require separate Owner re-evaluation.

## Redacted request shape

```json
{
  "length": "<redacted>",
  "offset": "<redacted>",
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
  "response_time": "<redacted>",
  "total": "<redacted>"
}
```

Only field names are shown. No real identifier, product value, URL, credential, or response content is included.

# 查询已有商品信息 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-71639106AB00` |
| Contract status | `DELETED` |
| Source document | `old-system/source/docs/lingxing/QueryProductList.md` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/deleted_interfaces.csv#LX-71639106AB00` |
| Path | `/listing/publish/openapi/amazon/product/search` |
| Method | `POST` |
| Protocol | `HTTPS` |
| Pagination | `无` |
| Page / batch limit | `unknown` |
| Rate limit evidence | `1` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `no` |

## Request parameters

Source: `old-system/source/docs/lingxing/QueryProductList.md#请求参数 (2 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `store_id` | `store_id` | `int` | `是` |
| `skus` | `skus` | `array` | `是` |


## Response fields

Source: `old-system/source/docs/lingxing/QueryProductList.md#返回结果 (6 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `number` | `是` |
| `msg` | `msg` | `string` | `是` |
| `data` | `data` | `array` | `是` |
| `data>>msku` | `data>>msku` | `string` | `是` |
| `data>>info` | `data>>info` | `object` | `是` |
| `request_id` | `request_id` | `string` | `是` |


## Known missing evidence

- provider authentication applicability
- account/data scope
- provider verification


## Safety decision

Current classification is excluded or incomplete. `READY_FOR_PRP` permits only a future evidence-backed PRP; it does not approve provider traffic, implementation, data writes, or production use. Deleted, non-Walmart, or side-effecting entries require separate Owner re-evaluation.

## Redacted request shape

```json
{
  "store_id": "<redacted>",
  "skus": "<redacted>"
}
```

## Redacted response shape

```json
{
  "code": "<redacted>",
  "msg": "<redacted>",
  "data": "<redacted>",
  "data>>msku": "<redacted>",
  "data>>info": "<redacted>",
  "request_id": "<redacted>"
}
```

Only field names are shown. No real identifier, product value, URL, credential, or response content is included.

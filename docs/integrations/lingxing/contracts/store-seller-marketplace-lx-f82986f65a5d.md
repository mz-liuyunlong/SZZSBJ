# 查询亚马逊店铺列表 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-F82986F65A5D` |
| Contract status | `DELETED` |
| Source document | `old-system/source/docs/lingxing/SellerLists.md` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/deleted_interfaces.csv#LX-F82986F65A5D` |
| Path | `/erp/sc/data/seller/lists` |
| Method | `GET` |
| Protocol | `HTTPS` |
| Pagination | `无` |
| Page / batch limit | `unknown` |
| Rate limit evidence | `1` |
| Authentication | Common Lingxing authentication evidence exists, but endpoint-specific applicability remains unverified; no credential value is recorded here. |
| Can enter PRP planning | `no` |

## Request parameters

Source: `NONE`

No field rows are available in the normalized evidence.


## Response fields

Source: `old-system/source/docs/lingxing/SellerLists.md#返回结果 (16 rows)`

| Path | Name | Type | Required |
|---|---|---|---|
| `code` | `code` | `int` | `是` |
| `message` | `message` | `string` | `是` |
| `error_details` | `error_details` | `array` | `是` |
| `response_time` | `response_time` | `string` | `是` |
| `data` | `data` | `array` | `是` |
| `data>>sid` | `data>>sid` | `number` | `是` |
| `data>>mid` | `data>>mid` | `number` | `是` |
| `data>>name` | `data>>name` | `string` | `是` |
| `data>>seller_id` | `data>>seller_id` | `string` | `是` |
| `data>>account_name` | `data>>account_name` | `string` | `是` |
| `data>>seller_account_id` | `data>>seller_account_id` | `number` | `是` |
| `data>>region` | `data>>region` | `string` | `是` |
| `data>>country` | `data>>country` | `string` | `是` |
| `data>>has_ads_setting` | `data>>has_ads_setting` | `int` | `是` |
| `data>>marketplace_id` | `data>>marketplace_id` | `string` | `是` |
| `data>>status` | `data>>status` | `int` | `是` |


## Known missing evidence

- request parameter rows
- provider authentication applicability
- account/data scope
- provider verification


## Safety decision

Current classification is excluded or incomplete. `READY_FOR_PRP` permits only a future evidence-backed PRP; it does not approve provider traffic, implementation, data writes, or production use. Deleted, non-Walmart, or side-effecting entries require separate Owner re-evaluation.

## Redacted request shape

```json
{}
```

## Redacted response shape

```json
{
  "code": "<redacted>",
  "message": "<redacted>",
  "error_details": "<redacted>",
  "response_time": "<redacted>",
  "data": "<redacted>",
  "data>>sid": "<redacted>",
  "data>>mid": "<redacted>",
  "data>>name": "<redacted>"
}
```

Only field names are shown. No real identifier, product value, URL, credential, or response content is included.

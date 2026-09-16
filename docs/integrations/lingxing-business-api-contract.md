# Lingxing business API contract

Status: `IMPLEMENTED_IN_PR_108`

Evidence: owner-provided `lingxing-walmart.zip` complete documentation snapshot, reviewed 2026-09-17.

## Purpose

This document records the common transport contract that must be applied before any current or future Lingxing business interface is enabled. Endpoint-specific request fields still come from the approved interface contract / PRP; this document does not authorize any interface by itself.

## Common authentication

All Lingxing **business** API calls use four common URL query parameters:

```text
access_token
app_key
timestamp
sign
```

Do not put the access token in an `Authorization` header for these business interfaces.

The signature includes the business parameters plus `access_token`, `app_key`, and `timestamp`. Values are sorted by key; an empty string does not participate, while `null` does. Nested collections use their canonical JSON/string representation for signing. The resulting signing string is MD5-hashed to uppercase and encrypted with AES/ECB/PKCS padding using App ID as the key. The `sign` query value is URL encoded by the HTTP client.

`timestamp` uses Unix seconds and a signature must be generated per request rather than cached.

## GET business requests

- Business parameters are transmitted in the URL query.
- The same business values participate in signing.
- The four common authentication parameters are also in the URL query.

## POST business requests

- Business parameters are transmitted as JSON in the request body unless the endpoint document explicitly says otherwise.
- The same body business values participate in signing.
- Only the four common authentication parameters are added to the URL query.
- `Content-Type: application/json` is used for the standard JSON contract.

## Runtime implementation

Shared transport:

```text
backend/app/integrations/lingxing/business_api.py
```

Safety remains controlled by the existing default-deny `LingxingOpenApiClient`:

```text
registry contract
  -> enabled_interface_ids allowlist
  -> owner authorization for write / side-effect interfaces
  -> LingxingBusinessApiExecutor
  -> signed HTTP request
```

Creating the reusable executor does **not** enable any of the 329 registry interfaces automatically.

## DATA-PAGES contract corrections

REAL-DATA-1 uses seven approved read interfaces. The full documentation snapshot confirmed the following corrections to the earlier derived-index implementation:

| Interface | Correct runtime contract |
| --- | --- |
| `getSellerList` | `platform_code` is an array, e.g. `[10008]` |
| Walmart listing list | `offset/length`; current approved flow may omit `store_ids` |
| sales statistics V2 | SKU grain uses `data_type="4"`; day uses `date_unit="4"`; `result_type` is the documented string enum |
| order V2 list | `start_time/end_time` are Unix seconds; `platform_code` and `store_id` are arrays |
| Walmart return order list | `dateType` is numeric; current flow uses `1` and `REFUND` only |
| Walmart advertiser list | keep the JSON `paging` value supplied by the approved caller; do not move auth into a header |
| Walmart SP ad item report | `campaignType` is an array; SP requires `sponsoredProducts-manual` and `sponsoredProducts-auto`; advertiser IDs are numeric values |

The compatibility normalization lives in:

```text
backend/app/integrations/lingxing/data_pages_contracts.py
```

## Derived-index method corrections

The complete endpoint documents show five method values that differ from the generated runtime index. Execution uses these explicit owner-verified overrides:

| Interface ID | Path | Verified method |
| --- | --- | --- |
| `LX-ECC5B6E072BC` | `/basicOpen/outboundOrder/outbound/delete` | POST |
| `LX-50E3A9271BE9` | `/basicOpen/storageAllocationList/delete` | POST |
| `LX-9AE1466FB085` | `/basicOpen/overSeaWarehouse/stockOrder/delete` | POST |
| `LX-1E89A7A2DA3C` | `/bd/fee/management/open/feeManagement/otherFee/delete` | POST |
| `LX-2AD144D844C7` | `/bd/sp/api/open/settlement/export/url/get` | POST |

The source normalized index remains immutable; corrections are isolated in `official_contract_overrides.py` so they are reviewable and testable.

## Future interface onboarding rule

For every later Lingxing interface:

1. Check the project do-not-use/deleted lists and data-source decision gate.
2. Read `Guidance/newInstructions.md` and `Guidance/QA.md` before the endpoint page.
3. Verify endpoint method/path, body/query location, value types, page limits, date limits, bucket capacity, errors, and account permission.
4. Register only the endpoint-specific business fields. Never add auth fields to the business body contract.
5. Keep the registry/stub default-deny. Read-only execution requires an explicit enabled-interface allowlist; write/side-effect execution additionally requires owner authorization.
6. Use `LingxingBusinessApiExecutor` rather than creating another signing implementation.
7. Test with `httpx.MockTransport` first. A mock pass is not proof of provider compatibility; the first real call remains a separately authorized bounded validation.
8. Never print token, App Secret, signed query, RAW provider body, SKU/order/item details, or other sensitive business values during validation.

## Production boundary

This implementation changes source code and tests only. It does not:

- enable a schedule or Celery worker;
- authorize a production API call;
- call Lingxing during CI/tests;
- modify PostgreSQL or MySQL;
- run a migration;
- change production environment variables;
- restart any service.

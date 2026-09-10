# Product Management Backend MVP API

Status: implementation prepared; remains `approved` until the implementation PR is merged.

## Contract boundary

- Base path: `/api/v1/products`
- Envelope: `{ success, data, error, meta, request_id }`
- Runtime authority: new-system PostgreSQL only
- Source tables: `products`, `product_platform_listings`
- Authentication: trusted backend principal
- Data scope: trusted Product module provider; missing or denied provider fails closed
- Future scope grain: `platform + store_name`; the shared `store_id` scope helper is not reused
- Content type for bodies: `application/json`

Both tables are `NEW_SYSTEM_OWNED`. This API does not read the legacy system or call an external platform. Monetary JSON values are decimal strings with at most four decimal places; binary floating-point inputs and implicit rounding are rejected.

## Endpoints

| Name | Method and URL | Permission | Request | Success `data` | Source | Read-only | Audit / risk |
|---|---|---|---|---|---|---|---|
| Product list | `GET /api/v1/products` | `products:read` | Query fields below | `ProductListData` | Both tables when relation filters are used; otherwise `products` | Yes | No audit write; response can contain confidential purchase price |
| Product detail | `GET /api/v1/products/{product_id}` | `products:read` | UUID path ID | `ProductRead` | `products` | Yes | No audit write; response can contain confidential purchase price |
| Product create | `POST /api/v1/products` | `products:create` | `ProductCreate` | `ProductRead` | Writes `products` | No | Authoritative-data write; no approval workflow or audit-history table in this MVP |
| Product update | `PATCH /api/v1/products/{product_id}` | `products:update` | UUID path ID and `ProductUpdate` | `ProductRead` | Writes `products` | No | Authoritative-data write; no approval workflow, rollback API, or audit-history table |
| Product options | `GET /api/v1/products/options` | `products:read` | None | `ProductOptionsData` | Approved in-code enum | Yes | No audit write; not a database distinct-value query |
| Listing list | `GET /api/v1/products/{product_id}/listings` | `product_listings:read` | UUID path ID and pagination | `ProductListingListData` | `products`, `product_platform_listings` | Yes | No audit write; response can contain confidential fee fields |
| Listing create | `POST /api/v1/products/{product_id}/listings` | `product_listings:create` | UUID path ID and `ProductListingCreate` | `ProductListingRead` | Writes `product_platform_listings` | No | Authoritative-data write; no external sync, approval workflow, or audit-history table |
| Listing update | `PATCH /api/v1/products/{product_id}/listings/{listing_id}` | `product_listings:update` | Two UUID path IDs and `ProductListingUpdate` | `ProductListingRead` | Writes `product_platform_listings` | No | Authoritative-data write; no external sync, rollback API, or audit-history table |

Every endpoint requires both its listed permission and an allowed Product data scope. Route order keeps `/options` separate from `/{product_id}`.

## Query parameters

`GET /api/v1/products` accepts only:

| Field | Type | Default / rule |
|---|---|---|
| `page` | integer | Default `1`; minimum `1` |
| `page_size` | integer | Default `20`; range `1..100` |
| `sku` | string | Case-preserving contains filter; trimmed, nonblank, max 128 |
| `product_name` | string | Contains filter; trimmed, nonblank, max 255 |
| `platform` | enum | Exact relation filter: `walmart`, `amazon`, `temu`, or `other` |
| `store_name` | string | Exact relation filter; trimmed, nonblank, max 255 |
| `msku` | string | Exact relation filter; trimmed, nonblank, max 128 |

Product ordering is `sku ASC, id ASC`. Relation filters must match one same, non-deleted listing row.

`GET /api/v1/products/{product_id}/listings` accepts only `page` and `page_size` with the same bounds. Ordering is `platform ASC, store_name ASC, msku ASC, id ASC`. Unknown query fields are rejected.

## Schemas

### Product write fields

`ProductCreate` requires `sku` and `product_name`. `ProductUpdate` requires at least one field. Both allow these mutable fields:

| Field | Rule |
|---|---|
| `sku` | Nonblank string, max 128, outer whitespace trimmed, case preserved, globally unique |
| `product_name` | Nonblank string, max 255, outer whitespace trimmed |
| `category`, `product_type` | Nullable string, max 128 |
| `status`, `grade` | Nullable string, max 64 |
| `purchase_price` | Nullable non-negative decimal string, precision 18, scale at most 4 |
| `currency_code` | Nullable uppercase three-letter code; must be present exactly when `purchase_price` is present |
| `declared_cn_name`, `declared_en_name`, `material_cn`, `material_en` | Nullable string, max 255 |
| `remark` | Nullable string |

`ProductRead` adds server-owned `id`, `created_at`, and `updated_at`. It never returns `deleted_at` or listing relations.

### Listing write fields

`ProductListingCreate` requires `platform`, `store_name`, and `msku`; `product_id` comes from the path. `ProductListingUpdate` requires at least one field. Both allow these mutable fields:

| Field | Rule |
|---|---|
| `platform` | `walmart`, `amazon`, `temu`, or `other` |
| `store_name` | Nonblank string, max 255, outer whitespace trimmed |
| `msku` | Nonblank string, max 128, outer whitespace trimmed, case preserved |
| `external_listing_id` | Nullable string, max 255 |
| `listing_url` | Nullable reference-only string, max 2048; the backend does not fetch it |
| `listing_status`, `fulfillment_type` | Nullable string, max 64 |
| `wfs_fee`, `shipping_cost` | Nullable non-negative decimal string, precision 18, scale at most 4 |
| `currency_code` | Nullable uppercase three-letter code; required if either monetary field is present |

The identity `(platform, store_name, msku)` is unique across listing rows. `ProductListingRead` adds server-owned `id`, `product_id`, `created_at`, and `updated_at`; it omits `deleted_at`.

List responses have `items`, `total`, `page`, and `page_size`. Options returns exactly:

```json
{"platforms":["walmart","amazon","temu","other"]}
```

## Errors

| HTTP | Error code | Meaning |
|---|---|---|
| 401 | `UNAUTHORIZED` | No trusted principal |
| 403 | `FORBIDDEN` | Required permission is absent |
| 403 | `DATA_SCOPE_DENIED` | Trusted Product scope provider is absent or denies access |
| 404 | `NOT_FOUND` | Product or listing relation does not exist in the active view |
| 409 | `PRODUCT_SKU_CONFLICT` | Product SKU already exists |
| 409 | `LISTING_IDENTITY_CONFLICT` | Listing identity already exists |
| 422 | `VALIDATION_ERROR` | Path, query, body, precision, currency-pair, or unknown-field validation failed |

Errors never include SQL, connection information, submitted monetary values, or exception text.

## Synthetic examples

Create one product:

```http
POST /api/v1/products
Content-Type: application/json
X-Request-ID: req-synthetic-001

{"sku":"SKU-SYNTHETIC","product_name":"Synthetic Product","purchase_price":"12.3400","currency_code":"USD"}
```

```json
{"success":true,"data":{"id":"00000000-0000-0000-0000-000000000001","sku":"SKU-SYNTHETIC","product_name":"Synthetic Product","category":null,"product_type":null,"status":null,"grade":null,"purchase_price":"12.3400","currency_code":"USD","declared_cn_name":null,"declared_en_name":null,"material_cn":null,"material_en":null,"remark":null,"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"},"error":null,"meta":null,"request_id":"req-synthetic-001"}
```

Create one listing relation:

```http
POST /api/v1/products/00000000-0000-0000-0000-000000000001/listings
Content-Type: application/json

{"platform":"walmart","store_name":"Synthetic Store","msku":"MSKU-SYNTHETIC","wfs_fee":"2.5000","currency_code":"USD"}
```

The corresponding success status is `201`. Product/listing `GET` and `PATCH` responses use the same envelope and their read schema. A safe conflict response is:

```json
{"success":false,"data":null,"error":{"code":"PRODUCT_SKU_CONFLICT","message":"请求失败","details":{}},"meta":null,"request_id":"req-synthetic-002"}
```

## Explicit exclusions

No DELETE, restore, bulk operation, Excel import, old-system migration/runtime read, platform sync, external API, calculation, FX conversion, normalized store table, mart/read model, worker, notification, frontend integration, production migration, or production database access is part of this MVP.

# Product Management API

## 1. Status and boundary

This contract implements the approved Product Management BFF over persisted new-system data.
Routes never request Lingxing, Walmart, Token endpoints, legacy MySQL, or RAW payloads. The
ProductInfo executor is a separate controlled write path: after every production gate is satisfied,
it may call only contract `LX-BB8D0DF598AF` with a `productIds` body and publish the successful
response through the existing ODS/DWD/DWS storage chain. The BFF never invokes that executor.
No real provider call or production write has been performed by this implementation task.

All responses use:

```json
{
  "success": true,
  "data": {},
  "error": null,
  "meta": {},
  "request_id": "generated-or-accepted-request-id"
}
```

`{sku_id}` is the internal UUID from `dwd_lingxing_sku_identity_index.id`. It is not a SKU
string, MSKU, Lingxing external ID, or an inferred Product ID. Active identities remain readable
before Product bootstrap; Product Core is an optional left join through `identity.product_id`.

## 2. Authentication, permissions, and scope

All routes are protected by the existing auth foundation and Product scope. SKU data routes also
require a non-empty trusted `source_account_ref` scope.

| Route | Permission |
|---|---|
| Product list, summary, detail, options, pricing breakdown | `products:read` |
| Cost, price, margin, ROI, and breakdown components | additional `products:cost:read` |
| Export | `products:export` |
| Read pricing rules | `products:pricing_rules:read` |
| Publish pricing rules | `products:pricing_rules:update` |
| Recalculate pricing | `products:pricing:recalculate` |
| Save table view | `products:table_views:update` |

Missing auth, permission, Product scope, or account scope fails closed. A resource outside scope is
not returned. Product bootstrap is not required for list/detail reads.

For local Vite development only, `VITE_PRODUCT_MANAGEMENT_PREVIEW_TOKEN` may be supplied through the
developer's untracked local environment. The shared frontend API client sends it as
`X-Product-Management-Preview-Token` only in Vite DEV mode. Preview authentication permits only GET
requests under `/api/product-management/` and the exact GET table-view path; all write methods remain
unauthorized. Never commit a real preview token or a token-bearing `.env.local` file.

## 3. Endpoints

### `GET /api/product-management/skus`

Server-side bounded list. Query parameters:

- `page` (default 1) and `page_size` (default 20, maximum 100)
- optional fuzzy `sku`, exact `sku_batch`, `product_name`, `category`, exact `internal_tag`,
  `product_grade`, and `calculation_status`
- `sort_by`: `sku`, `product_name`, `product_grade`, or `calculated_at`
- `sort_order`: `asc` or `desc`

`sku_batch` may be repeated and each value may contain newline-separated entries. The server trims
entries, removes blanks, de-duplicates exact values in first-seen order, and preserves case. It
accepts at most 1,000 unique values of at most 128 characters each, is mutually exclusive with
`sku`, and is applied as an exact repository/database filter. Empty or oversized input returns 422;
clients must not download the full list and filter it locally.

The stable secondary order is the internal identity UUID. `sku_id` is always the identity UUID.
`sku` and `product_name` prefer Product Core when it exists, otherwise they use the persisted
ProductInfo current projection. Other fields include primary image, image count, separately typed
ProductInfo source tags and internal tags, category, SKU-level weight/dimensions,
first-leg/WFS/storage/fixed costs, three price tiers, root missing codes, calculation status,
formula versions, calculation timestamp, and rule version. `grade_reason`
distinguishes a Product Core manual grade from a calculated grade. Fee and price values carry
`USD`/`CNY` currency codes. Sensitive
monetary results are `null` unless the principal has `products:cost:read`.
`meta.list_freshness_at` is the oldest source observation among the returned page, while
`meta.latest_observed_at` is the newest. This prevents a recently observed row from hiding an older
row on the same page. Both are `null` for an empty page.
`meta.stale` is `null` until an Owner-approved freshness threshold exists; it is never guessed from
system update time.

The frontend renders the server-provided page directly and uses `meta.total` for pagination and the
product total. It does not re-filter the current page. Statistics are hidden by default. The default
columns are image, SKU, product name, category, purchase cost, first-leg freight, purchase lead time,
data completeness, updated time, and actions. Fee and price fields remain optional columns until
their controlled sources are available; the column drawer can restore these defaults.

### `GET /api/product-management/skus/summary`

Returns count-only statistics for the same account scope and filters as the SKU list: total active
identities, identities with ProductInfo current detail, average persisted `data_quality_score`,
identities with at least one current-snapshot image, identities with at least one current-snapshot
source tag, and identities whose score is missing or below 100. It also returns
`missing_purchase_cost_count`, `missing_gross_weight_count`,
`missing_package_dimensions_count`, `missing_dimension_image_count`,
`invalid_pricing_rule_count`, and `pricing_ok_count`. These are root-cause counts; there are no
derived `missing_wfs_fee`, `missing_storage_fee`, or `missing_billing_data` counters. It never
returns product field values. `meta.total` repeats the filtered total so clients do not derive
totals from one page.

### `GET /api/product-management/skus/{sku_id}`

Returns the active identity, optional Product Core, approved persisted ProductInfo detail fields,
images, ProductInfo source tags, internal tags, and the SKU-level fee/price breakdown. The
calculation reads ProductInfo/DWS data and does not require `products.product_id`. It does not
return developer/owner fields by default and does not preload history or RAW.

### `GET /api/product-management/options`

Returns the bounded grade/status allowlists and active internal tag definitions. It does not run an
unscoped distinct scan over business rows.

### `POST /api/product-management/skus/export`

Accepts the same bounded query object plus `max_rows <= 5000`. V1 returns
`status=not_implemented_safe` and `file_created=false`; it does not pretend that an export exists.
The route still enforces export permission and both data scopes.

### `GET /api/product-management/pricing-rules`

Requires the non-secret `source_account_ref` query parameter. Returns at most 100 immutable rule
versions for that authorized account and the current effective rule ID. Rules contain only
validated configuration and safe evidence references.

### `PUT /api/product-management/pricing-rules`

Publishes a new immutable version for the authorized `source_account_ref`. New versions must be
open-ended (`effective_to=null`). In one service-owned transaction the previous open version is
locked and closed at the new `effective_from`, then the new version is inserted. A PostgreSQL
partial unique index permits only one active open version per `rule_key` and account, including the
first-version concurrency case. Backdating returns `PRICING_RULE_BACKDATING_NOT_ALLOWED` with HTTP
422; duplicate versions, overlaps, and concurrent conflicts return `RULE_VERSION_CONFLICT`.
Required content includes the effective start, change reason,
approval reference, WFS source confirmation,
storage/first-leg/pricing/ROI/grade configuration, and any explicitly controlled rate rows. Binary
floating-point inputs and unknown fields are rejected.

The version row records `actor_ref`, `request_id`, action/status, rule/version ID, account scope and
timestamps. It does not store SKU selections, calculation inputs, RAW content, or request payloads.

No Walmart rate value is bundled with the application. Until controlled fulfillment/storage rows
are published, calculations return missing-rate states.

### `POST /api/product-management/skus/recalculate-pricing`

Accepts `source_account_ref`, `scope=all|selected|missing_price|pricing_failed`, an optional explicit
rule version, effective time, reason, idempotency key, `preview_only` (default `true`), and
`max_items <= 100`. `selected` requires at most 100 unique internal identity UUIDs.

The client must preview first. Preview persists a safe run/audit record but never writes the current
pricing projection. Execute (`preview_only=false`) is the only mode that writes current pricing.
Both modes return `run_id`, `mode`, `status`, `matched_count`, `eligible_count`, `skipped_count`,
`estimated_affected_count`, `affected_count`, `failed_count`, and `idempotent_replay`; zero matches
still produce a durable `no_items` run.

Idempotency is isolated by trusted principal, source account, page/capability, mode, and key, with a
database unique constraint. The stored normalized request digest covers scope, sorted internal UUID
selection, requested rule/effective time, reason, mode, and limit; the run also records the resolved
pricing rule version. Reusing a key with a different request in the same isolation boundary returns
`IDEMPOTENCY_CONFLICT`. Preview and execute are separate boundaries. Run records contain only safe
references, counts, status/error code and timestamps, never SKU text, product fields, calculation
amount inputs, RAW content, or payloads. V1 remains bounded and never changes historical snapshots.

### `GET /api/product-management/skus/{sku_id}/pricing-breakdown`

Returns SKU-level statuses, inputs, formula versions, grade and timestamp. Detailed monetary values
are returned only with `products:cost:read`. Authorized responses include typed
WFS fulfillment USD/CNY values, package volume, daily and estimated storage USD/CNY values, three
USD prices, suggested margin/ROI, `price_currency_code=USD`, and the calculation effective time.
The `components` array contains exactly `purchase_cost`, `first_leg`, `wfs_fulfillment`,
`estimated_storage`, `other_fixed_cost`, and `commission`. Every item has `name`, nullable decimal
`amount`, nullable `currency`, an allowlisted `source`, `included`, `status`, and optional `reason`.
`included=true` means the component enters `included_costs_cny`. Commission therefore always has
`included=false`: it is deducted separately from `revenue_cny` and is never part of
`included_costs_cny`.
Cost-authorized detail and breakdown reads emit safe audit metadata (actor, request ID and internal
UUID only), not amounts or business identifiers.

### `GET /api/user-table-views/product-management`

Returns the current principal's default view or a safe server default. The owner is taken only from
the trusted principal.

### `PUT /api/user-table-views/product-management`

Stores only allowlisted `applied_column_keys` and `column_widths`. It cannot store a user ID, SKU
selection, filter result, permission, business value, or secret.

## 4. Field sources

| Field group | Source |
|---|---|
| Internal `sku_id` and account scope | `dwd_lingxing_sku_identity_index` |
| `sku`, product name | Product Core when present, otherwise ProductInfo current |
| Product Core category/status/manual grade | optional mapping to `products` |
| Product detail and source observation time | `dwd_lingxing_sku_product_info_current` |
| Images | `dwd_lingxing_sku_product_images` |
| Lingxing source tags | `dwd_lingxing_sku_global_tags` |
| Internal tags | `manual_product_tags` and effective assignments |
| Dimensions and gross weight | ProductInfo current |
| Purchase cost | DWS base profile, with ProductInfo current fallback |
| Rules | `ref_product_pricing_rule_versions` |
| Recalculation run/audit | `product_pricing_recalculation_runs` |
| SKU display price/fee result | read-time Decimal calculation from ProductInfo/DWS plus effective rule/defaults |
| Persisted recalculation result / grade | `dws_product_management_pricing_current` when present |
| Column preferences | `user_table_views` |

### 4.1 Product Management frontend field metadata

| field | type | source_table | source_column | nullable | frontend_usage | source_status |
|---|---|---|---|---|---|---|
| `sku_id` | UUID | `dwd_lingxing_sku_identity_index` | `id` | no | row key and detail route | persisted |
| `sku` | string | `products` / `dwd_lingxing_sku_product_info_current` / identity index | `sku` / `lingxing_sku_code` | yes | table and detail | Product preferred; synchronized fallback |
| `product_name` | string | `products` / ProductInfo current | `product_name` | yes | table and detail | Product preferred; synchronized fallback |
| `primary_image` | string | `dwd_lingxing_sku_product_images` | `pic_url` | yes | image cell | synchronized |
| `images` | array | `dwd_lingxing_sku_product_images` | `pic_url`, `ordinal`, `is_primary` | yes | detail gallery; each item identifies `source=picture_list` | synchronized |
| `source_tags` | array | `dwd_lingxing_sku_global_tags` | `source_tag_id`, `tag_name`, `tag_color` | yes | optional table column and detail tags | synchronized |
| `internal_tags` | array | manual tag tables | active assignment and tag fields | yes | filter/table/detail | Product-linked only |
| `category` | string | `products` | `category` | yes | filter/table/detail | Product-linked only |
| `purchase_delivery_days` | integer | ProductInfo current | `purchase_delivery_days` | yes | table/detail | synchronized |
| material/customs/dimension/weight fields | decimal/string | ProductInfo current | matching standardized columns | yes | detail | synchronized when supplied |
| `purchase_cost_cny` | decimal string | `dws_sku_base_profile_current` | `purchase_cost_cny` | yes | cost column | synchronized profile; permission gated |
| `unit_first_leg_cost` | decimal string | `dws_sku_base_profile_current` | `unit_first_leg_cost` | yes | cost column | synchronized profile; permission gated |
| `data_quality_score` | decimal string | `dws_sku_base_profile_current` | `data_quality_score` | yes | completeness | synchronized profile |
| `linked_platform_sku_count` | integer | `product_platform_listings` | count by optional `product_id` | no | table/summary | `0` without Product/listings |
| SKU fee/price fields | decimal/status | ProductInfo current + DWS base profile + effective rule/defaults | calculated projection | yes | table/detail | Product mapping not required; prices remain `null` when purchase cost, weight, or package dimensions are unavailable |
| `source_observed_at` | datetime | ProductInfo current | `source_observed_at` | yes | freshness display | synchronized |

Lingxing global tags remain source tags and are not interchangeable with internal tags.
Internal tag assignments are read-only in this API. No tag mutation route is present; any future
writer must separately prevent overlapping effective periods for the same Product/tag pair before
it can be approved.
ProductInfo `data.picture_list` is parsed into the existing immutable snapshot image table. The
detail route returns the complete, ordinal-sorted image collection for the current snapshot only;
an empty or absent source list returns `images=[]`. Duplicate URLs inside one source list are
collapsed before publication. Historical snapshot images remain lineage records and are not mixed
into the current detail response. List responses continue to expose only `primary_image` and
`image_count`.
The separate persisted Product-linked recalculation path preserves Product Core manual-cost
precedence. The SKU display calculation introduced here reads the DWS purchase-cost profile with a
ProductInfo-current fallback, so an unmapped active identity can still be evaluated.

## 5. WFS fulfillment fee

The SKU display projection reproduces the approved business spreadsheet formula and never calls a
Walmart API:

```text
actual_lb = gross_weight_g / 453.6
dimensional_lb = 0 when gross_weight_g < 453.6,
  otherwise length_cm * width_cm * height_cm / 2277.8
chargeable_lb = ceil(max(actual_lb, dimensional_lb) + 0.25)
fee_usd = 0.4 * chargeable_lb + lookup_base_fee(chargeable_lb)
```

The lookup thresholds are `1, 2, 3, 4, 21, 31, 51` with corresponding base fees
`3.05, 4.15, 4.25, 4.15, 7.15, 2.15, -2.85`. The response includes actual, dimensional and
chargeable weight, padding, base fee, final USD fee, status/reason, and
`wfs_formula_version=walmart_wfs_formula_v1`. Missing/non-positive weight or any package dimension
returns `wfs_calc_status=unavailable` and `wfs_calc_reason=missing_weight_or_dimensions`; no amount
is fabricated. This read-time calculation does not overwrite listing or persisted pricing rows.

## 6. Daily WFS storage fee

The SKU display estimate is per unit, not an inventory bill. This version intentionally uses the
single approved 10–12 month, up-to-30-day rule: `0.75 USD/cuft/month`, a 30-day month basis, and 30
pricing days. It does not use inventory age or implement later-age tiers.

```text
package_volume_cuft = package_length_cm * package_width_cm * package_height_cm / 28316.846592
daily_storage_fee_per_unit_usd = package_volume_cuft * 0.75 / 30
estimated_storage_fee_usd = package_volume_cuft * 0.75
```

Valid canonical package dimensions are sufficient to calculate this estimate; missing/non-positive
dimensions return `unavailable`, and zero is not substituted. The response uses the existing
non-failure `storage_calc_status=ok` for a calculated estimate.

## 7. Pricing, margin, ROI, and grade

All operations use `Decimal`. Product Management API decimal amounts, dimensions, weights, volumes,
rates, and ratios are serialized as two-place decimal strings with `ROUND_HALF_UP`; database and
internal calculation precision remain unchanged. Count fields remain integers.

```text
gross_weight_kg = gross_weight_g / 1000
first_leg_volume_weight_kg = length_cm * width_cm * height_cm / 6000
first_leg_chargeable_weight_kg = max(gross_weight_kg, first_leg_volume_weight_kg)
first_leg_fee_cny = first_leg_chargeable_weight_kg * 12
fixed_cost_usd = (purchase_cost_cny + first_leg_fee_cny) / 6.7
  + wfs_fulfillment_fee_usd + storage_fee_usd
suggested_price_usd = fixed_cost_usd / (1 - 0.15 - 0.05 - 0.15 - 0.20)
minimum_price_usd = fixed_cost_usd / (1 - 0.15 - 0.05 - 0.15 - 0.10)
clearance_price_usd = fixed_cost_usd / (1 - 0.15)
```

Defaults are USD/CNY `6.7`, first leg `12 CNY/kg`, commission `0.15`, after-sales `0.05`, ads
`0.15`, and suggested/minimum target margins `0.20`/`0.10`. Clearance includes only fixed cost and
commission. A non-positive denominator produces `invalid_denominator` and no price. All values use
`Decimal`; money is returned with two-place `ROUND_HALF_UP` rounding.

The SKU display calculation uses the effective versioned pricing rule where available and the
documented defaults otherwise. Its storage component uses the fixed `0.75` estimate above for this
version, so a valid package size does not become unavailable solely because inventory age or a
month-specific storage configuration is absent.

ROI defaults to `gross_profit_cny / purchase_cost_cny`. A new rule version may choose
`roi_base=total_cost`, using included costs. Missing/non-positive denominators fail safely.

Grade uses the suggested-price margin and ROI: A is margin >= 0.20 and ROI >= 1.00; B is margin >=
0.10 and ROI >= 0.50; other calculable products are C. Missing inputs or invalid calculations are
`exception`, with `productGrade` and `gradeReason` kept separate from Product Core manual grade and
provider source status. All thresholds are versioned configuration.

## 8. Error and empty-data contract

Stable API errors include `UNAUTHORIZED`, `FORBIDDEN`, `DATA_SCOPE_DENIED`, `NOT_FOUND`,
`IDENTITY_MAPPING_REQUIRED`, `RULE_VERSION_CONFLICT`, `IDEMPOTENCY_CONFLICT`,
`PRICING_RULE_BACKDATING_NOT_ALLOWED`, `RECALCULATION_NOT_AUTHORIZED`,
`VALIDATION_ERROR`, `CALCULATION_INPUT_INCOMPLETE`, `RULE_NOT_AVAILABLE`, `SOURCE_DATA_STALE`, and
`INTERNAL_ERROR`.

SKU display root causes are limited to `missing_purchase_cost`, `missing_gross_weight`,
`missing_package_dimensions`, `missing_dimension_image`, and `invalid_pricing_rule`.
`missing_dimension_image` does not block pricing. Display calculation status is `ok`,
`pricing_unavailable`, `storage_unavailable`, or `invalid_denominator`; component statuses explain
first-leg, WFS, and storage availability. These are data states, not 500 errors. Lists return an
empty `items` array when nothing is in scope, and unavailable monetary values are `null`.

## 9. Redaction

No response or error contains ODS/RAW content, `payload_json`, request bodies, provider responses,
Token values, credentials, signatures, authorization headers, or secret references. Audit logs are
limited to actor, request/run/internal UUID, safe count, version and stable status/error code.

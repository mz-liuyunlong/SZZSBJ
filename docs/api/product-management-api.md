# Product Management API

## 1. Status and boundary

This contract implements the approved Product Management BFF over persisted new-system data.
Routes never request Lingxing, Walmart, Token endpoints, legacy MySQL, or RAW payloads. The
`batchGetProductInfo` provider contract is still incomplete, so its outbound path remains disabled
and fails closed until separate Owner authorization and repository-verifiable official evidence
exist.

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
string, MSKU, Lingxing external ID, or an inferred Product ID. Product Core is joined only when the
identity mapping is `confirmed`.

## 2. Authentication, permissions, and scope

All routes are protected by the existing auth foundation and Product scope. SKU data routes also
require a non-empty trusted `source_account_ref` scope.

| Route | Permission |
|---|---|
| Product list, detail, options, pricing breakdown | `products:read` |
| Cost, price, margin, ROI, and breakdown components | additional `products:cost:read` |
| Export | `products:export` |
| Read pricing rules | `products:pricing_rules:read` |
| Publish pricing rules | `products:pricing_rules:update` |
| Recalculate pricing | `products:pricing:recalculate` |
| Save table view | `products:table_views:update` |

Missing auth, permission, Product scope, account scope, or confirmed mapping fails closed. A
resource outside scope is not returned.

## 3. Endpoints

### `GET /api/product-management/skus`

Server-side bounded list. Query parameters:

- `page` (default 1) and `page_size` (default 20, maximum 100)
- optional fuzzy `sku`, exact `sku_batch`, `product_name`, `product_grade`, and
  `calculation_status`
- `sort_by`: `sku`, `product_name`, `product_grade`, or `calculated_at`
- `sort_order`: `asc` or `desc`

`sku_batch` may be repeated and each value may contain newline-separated entries. The server trims
entries, removes blanks, de-duplicates exact values in first-seen order, and preserves case. It
accepts at most 1,000 unique values of at most 128 characters each, is mutually exclusive with
`sku`, and is applied as an exact repository/database filter. Empty or oversized input returns 422;
clients must not download the full list and filter it locally.

The stable secondary order is the internal identity UUID. Core response fields are `sku_id`,
Product Core `sku`/`product_name`, primary image, internal tags, effective grade, calculation
status, calculation timestamp, and rule version. `grade_reason` distinguishes a Product Core manual
grade from a calculated grade. Fee and price values carry `USD`/`CNY` currency codes. Sensitive
monetary results are `null` unless the principal has `products:cost:read`.
`meta.list_freshness_at` is the oldest source observation among the returned page, while
`meta.latest_observed_at` is the newest. This prevents a recently observed row from hiding an older
row on the same page. Both are `null` for an empty page.
`meta.stale` is `null` until an Owner-approved freshness threshold exists; it is never guessed from
system update time.

### `GET /api/product-management/skus/{sku_id}`

Returns confirmed Product Core identity, approved persisted detail fields, images, internal tags,
and a persisted pricing summary. It does not return developer/owner fields by default and does not
preload history or RAW.

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

Returns persisted statuses, source selection, rule/calc versions, grade and timestamp. Detailed
cost components are returned only with `products:cost:read`. Authorized responses include typed
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
| `sku`, product name, manual grade | confirmed mapping to `products` |
| Product detail and source observation time | `dwd_lingxing_sku_product_info_current` |
| Images | `dwd_lingxing_sku_product_images` |
| Internal tags | `manual_product_tags` and effective assignments |
| Dimensions, weight, purchase/first-leg source profile | `dws_sku_base_profile_current` |
| Rules | `ref_product_pricing_rule_versions` |
| Recalculation run/audit | `product_pricing_recalculation_runs` |
| Current price/fee/ROI/grade result | `dws_product_management_pricing_current` |
| Column preferences | `user_table_views` |

Lingxing global tags remain source tags and are not interchangeable with internal tags.
Internal tag assignments are read-only in this API. No tag mutation route is present; any future
writer must separately prevent overlapping effective periods for the same Product/tag pair before
it can be approved.
Product Core manual purchase price takes precedence over the synchronized purchase-cost profile;
USD manual cost is converted only with the selected rule's recorded FX value. Unsupported manual
cost currency fails safely instead of falling through to synchronized cost.

## 5. WFS fulfillment fee states and overrides

The approved selection order is:

1. active identity-level manual override;
2. active primary Walmart listing override;
3. the only active Walmart listing override;
4. an identical amount/currency shared by all active Walmart listing overrides;
5. conflicting values produce `needs_confirm` / `multiple_listing_wfs_overrides`;
6. otherwise use a matching active configured rule;
7. no applicable rule produces `missing_rate`.

V1 cannot safely apply listing-level overrides because the existing listing table has no
`source_account_ref`. The Product Management service therefore fails closed by ignoring all listing
overrides and evaluates only an account-scoped identity override or configured system rule. The
listing steps above remain a deferred contract until listing ownership is explicitly account-scoped;
no listing from another account can influence the current result.

More than one configured rule matching the same inputs produces `needs_confirm` /
`multiple_matching_wfs_rates`; order never decides the fee.

Other safe component states include `missing_dimension` and `missing_weight`. The response source is
one of `manual_sku_override`, `manual_primary_listing_override`,
`manual_single_listing_override`, `manual_consistent_listing_override`, `calculated_rule`, or
`needs_confirm`. Calculated values never overwrite `product_platform_listings.wfs_fee`.

## 6. Daily WFS storage fee

Persisted output is per unit, not an inventory bill:

```text
package_volume_cuft = package_length_in * package_width_in * package_height_in / 1728
daily_storage_fee_per_unit_usd =
  package_volume_cuft * monthly_storage_rate_usd_per_cuft / storage_month_basis_days
estimated_storage_fee_usd = daily_storage_fee_per_unit_usd * pricing_storage_days
```

Canonical package dimensions are converted from centimetres to inches before this formula. Both day
settings default to 30 in each new version. Missing controlled rates or dimensions produce
`missing_rate` or `missing_dimension`; zero is not substituted.

## 7. Pricing, margin, ROI, and grade

All operations use `Decimal`; money is serialized as a decimal string.

```text
revenue_cny = price_usd * usd_cny_rate
commission_cny = revenue_cny * platform_commission_rate
included_costs_cny = purchase_cost_cny
  + included_first_leg_cost_cny
  + included_wfs_fulfillment_fee_cny
  + included_estimated_storage_fee_cny
  + other_fixed_cost_cny
gross_profit_cny = revenue_cny - commission_cny - included_costs_cny
gross_margin_rate = gross_profit_cny / revenue_cny
price_usd = included_costs_cny
  / (usd_cny_rate * (1 - platform_commission_rate - target_margin_rate))
```

Default target margins are 0.20, 0.10, and 0.00 for suggested, minimum, and clearance price. All
three include platform commission. A non-positive denominator produces
`invalid_pricing_denominator`. Target margins and final prices must remain descending. The `none`
rounding mode uses `ROUND_HALF_UP` to two decimal places, then raises to the next cent if ordinary
rounding would fall below the raw price.

Missing commission config means zero with `commission_source=default_zero`; missing FX is
`missing_fx_rate`. First-leg V1 uses configured CNY/kg multiplied by product gross weight kg; missing
gross weight is `missing_weight`.

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

Calculation states such as `missing_fx_rate`, `missing_purchase_cost`, `missing_weight`,
`missing_wfs_rate`, `missing_storage_rate`, `invalid_revenue`, `invalid_pricing_denominator`,
`invalid_pricing_rule_config`, `invalid_roi_base`, and `needs_confirm` are data states, not 500
errors. Lists return an empty `items` array; missing pricing may be `null` in detail, while the
dedicated breakdown route returns `RULE_NOT_AVAILABLE`.

## 9. Redaction

No response or error contains ODS/RAW content, `payload_json`, request bodies, provider responses,
Token values, credentials, signatures, authorization headers, or secret references. Audit logs are
limited to actor, request/run/internal UUID, safe count, version and stable status/error code.

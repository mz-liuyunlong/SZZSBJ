# Walmart Monitor Listing Projection Source Decision

```text
Status: APPROVED_BY_OWNER
Decision Date: 2026-10-27
Scope: Listing Management monitor-derived display fields and lifecycle evidence
```

## Decision

The Walmart monitor remains the authoritative source for non-empty observed values of:

- title;
- strike price;
- sale price;
- Walmart page category;
- buy-box status;
- Walmart seller;
- explicit reseller/hijack decision;
- rating;
- review count;
- brand.

The stable identity is `source_account_ref + store_id + item_id`. Monitor values never infer or
replace that identity. Missing monitor values fall back to the existing Listing read model; they do
not erase existing values.

One monitor check is scoped to a Walmart Item page and may carry several stable target identities
when that Item belongs to more than one account/store Listing. The single observed page result is
therefore standardized once per supplied target identity, inside the same transaction as the RAW
event; target identity fields themselves still come only from `targets[]`.

## Governed flow

```text
raw_walmart_monitor_events (L2, immutable)
  -> std_walmart_monitor_listing_observations (L3, immutable typed observations)
  -> mart_walmart_monitor_listing_current (L9, latest typed monitor observation)
  -> Listing Management API overlay
```

Frontend and business APIs must not read RAW directly. The existing Listing MART is not updated by
monitor ingestion. This avoids losing monitor authority when the Lingxing Listing refresh rebuilds
`mart_listing_management_current`.

## Field rules

- `final_observation.parsed_result.walmartCategory` is the monitored Walmart page category.
- `targets[].product_category` is retained as source-category lineage only and is not displayed.
- `is_hijacked` is populated only from an explicit monitor decision. Seller presence alone is not
  sufficient because another seller may still be an owned seller.
- Boolean `false` and numeric zero are explicit values; blank strings and missing keys fall back to
  the existing Listing read model for that field.
- Failed observations remain immutable L3 evidence but do not replace the last successful L9
  monitor projection. If there has never been a successful observation, Listing values remain the
  fallback.
- Monitor outcome/source, image URLs, error code and RAW event identity remain audit/lineage fields
  and are not added to the Listing page response.
- A category change/recovery alert remains a monitor-producer responsibility. The new system keeps
  every standardized observation so those events can be audited and replayed.

## Owner approval

The owner explicitly approved implementing the monitor consumption path together with PR #260 on
2026-10-27. This approval does not authorize production migration, deployment, replay or sync.

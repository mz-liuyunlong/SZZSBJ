# WFS Clearance Center: source decisions (2026-11-06)

Approval: business workflow and risk policies confirmed by project owner in chat, implementation explicitly authorized 2026-11-06. Git reference used for the initial implementation: `4b702c712eab16618418003f2faec574f78416dc`.

| Business value | Existing canonical source | Reliability rule |
|---|---|---|
| Listing identity | `mart_listing_management_current` | `(source_account_ref,store_id,item_id)`; SKU/MSKU display only |
| Current WFS available units | latest captured `fact_walmart_listing_inventory_daily`, or newer `mart_listing_management_current` | NULL is unknown; reservations not counted |
| First positive WFS date | immutable `listing_wfs_first_stock_la_locked` | do not infer pre-monitor stock age |
| LA daily sales | `mart_daily_sales_item_day` | unique MSKU/day contributions; incomplete days are unknown |
| Profit/cost | existing daily sales MART numeric costs/profit | only complete cost evidence, recognized USD; never invent FX |
| Store commission | effective `ref_store_commission_rule_versions` | item/range/store priority; no blanket 15% fallback |
| Rating, Buy Box, owner, price | `mart_listing_management_current` | optional missing values remain unknown |
| Ads clicks/attributed orders | not authoritatively mapped in this implementation | ad-conversion rule stays disabled until verified source |
| Open purchase quantity | not authoritatively mapped | warning rule stays disabled until verified source |
| Risk duration / forward holding cost | no authorized daily series or forecasting contract | keep switches off, never fill simulated results |
| Rule versions and application history | new `biz_clearance_*` append-only tables | Alembic-only, immutable version and event history |

Safety: only manual clearance application submission; never automatic approval, price change, ad campaign action, removal or disposal. The only automatic post-approval actions are internal task creation/transition and Listing lifecycle lock. Approved targets never increase when inventory changes. Every request is tenant-scoped and server-side permission checked.

Limitations for final DEV acceptance: confirm daily-sale completeness semantics against actual synced source data. If daily rows are sparse (no row for zero-sale day), zero-sales will correctly remain `unknown` instead of being treated as zero; a separate verified day-level ingestion ledger must be mapped before enabling that inference. Confirm current WFS and cost source timestamps and in-scope store identity on a DEV snapshot. Existing approval workbench real WFS/purchase paths are untouched.

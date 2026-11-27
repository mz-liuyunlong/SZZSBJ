# Approval workbench unified read V1 — data source decision

- Baseline: main `a770765d728212aa9dfc3bb0714935acf99ad9c9` (2026-11-26).
- Candidate local implementation authorized by owner request to unify workbench reads and preload current-page purchase details. PR/production approval is separate.
- Existing authorities, formulas and permission predicates retained. No legacy runtime read, new table, migration, data write, or external API.
- Old-system page/API/table writers: not applicable, this is a new-system-only read composition of existing governed endpoints, not a legacy migration or replacement of their data sources.

| Dataset | Classification | Existing authority and read path | Freshness/transform |
|---|---|---|---|
| Formal approvals, WFS mirrored case decisions | NEW_SYSTEM_OWNED / WFS mirror read of previously synchronized facts (separate authorities) | `ApprovalService.list_requests`, `app_approval_requests`, `ops_wfs_fee_anomaly_cases` | Existing role/scope/status predicates; keep WFS dedupe and sorting. |
| Clearance applications | NEW_SYSTEM_OWNED | `hybrid_v28.list_applications`, `storage_session`, `biz_clearance_applications`, existing `batch_read` | Existing storage/read boundary, authorized accounts. Risk/keyword filter uses same fields before merge. |
| Purchase applications and review evidence | NEW_SYSTEM_OWNED | `NewProductPurchaseBridge`, `biz_new_product_purchase_applications`, `biz_new_product_action_events`, performance rule versions | Exact application ID/version, as-submitted snapshot, historical events <= application creation, latest 120 per application, original evidence rules. |
| Listing, evaluation and advertising view | REBUILD_SYNC (existing synchronized source, no new sync) / NEW_SYSTEM_OWNED saved evaluation projection | `NewProductService.list` existing dispatcher, `NewProductRepository.page`, `load_persisted`, `decorate_page`, Listing MART and saved performance | Account/store/Item ID. Existing new-product source read session and scope. No grade publication or re-score. |
| Operating daily and profit | REBUILD_SYNC existing FACT/MART plus NEW_SYSTEM_OWNED saved operating archive | `evaluation_operating_archive_v1`, `mart_daily_sales_item_day`, `fact_walmart_ad_item_sp_daily`, `build_operating_daily_same_source` | Archive first under existing frozen-grade condition; otherwise the same engine/cutoff as detail, LA business days, USD, same sample/refund policy. Batch fallback parameterizes each identity's cutoff. |
| Purchase cost | REBUILD_SYNC existing product management projections | `ProductManagementService.list_skus`, existing product scope and purchase-cost field permission | Current purchase cost in CNY × original requested quantity; exact account/SKU after verifying Listing identity. No cost inference from price. |
| FX | REBUILD_SYNC existing synchronized monthly rates | `load_usd_cny_rates`, `usd_cny_rate_for`, `fact_lingxing_fx_rate` | Existing application month Shanghai timezone and `my_rate`; no rate fallback. |
| Applicant name | NEW_SYSTEM_OWNED | existing `attach_approval_names`, `attach_clearance_names` / IAM | Authorized rows only. |

Write authorities are unchanged: existing application/decision routes, scoring publishers, sync tasks and IAM. No new write entry, dual-write, source migration or exit plan needed. Existing demo listing/price rows remain frontend-only. Raw, temporary, legacy or backup data are not queried. Sensitive values remain subject to existing data scope and cost field permissions. Local integration and performance parity must be verified before production.

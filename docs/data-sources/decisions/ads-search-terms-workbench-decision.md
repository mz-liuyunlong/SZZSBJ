# 数据源决策 — Walmart SP 搜索词工作台

Status: BLOCKED_BY_OWNER_DECISION
Owner decision date: 2026-11-09
PRP: PRPs/ads-search-terms-workbench-v1.md
Planning branch: feat/ads-search-terms-workbench
Base main SHA: cfb28285e9b57a32f9d3d66950466151a4f644c3

## 1. Owner-confirmed source direction

- 只使用领星 OpenAPI；明确不接 Walmart 官方 API。
- 搜索词来源为领星 Walmart SP 搜索词列表：
  POST /basicOpen/multiplatform/ads/reportSearchImpressionSpList
- 手动投放关键词覆盖来源为领星 SP 关键词列表：
  POST /basicOpen/multiplatform/ads/reportKeywordSpList
- 已有的广告主、店铺、SP 广告商品数据沿用当前 SZZSBJ 已治理的数据源与事实表。
- 搜索词页不展示原始触发关键词、matchType 等无法由搜索词接口直接证明的字段。

## 2. Legacy read-only survey

Old-system references were inspected read-only; no legacy database or runtime was accessed.

- Current new-system page: navigation entry ads_search_terms and path /ads/search-terms exist; routes.tsx currently falls through to ComingSoonPage because no dedicated renderer is registered.
- Old-system search-term UI: no dedicated page component was found in the inspected old-system tree. checkAutoAdSearchTermImport.ts references a historical import tool URL, but the page implementation was not found.
- Legacy manual keyword source: old-system/source/src/syncManualAdKeywordDaily.ts calls Lingxing reportKeywordSpList and reportAdItemSpList, maps campaignId+adGroupId to itemId, and writes MySQL fact_ads_keyword_daily with source_type=manual_kw.
- Legacy automatic search-term source: old-system/source/src/checkAutoAdSearchTermImport.ts and old-system/source/scripts/rebuild_auto_ads_fact.py reference CSV-based automatic search-term ingestion into legacy MySQL raw_walmart_ads_csv / fact_ads_keyword_daily with source_type=walmart_auto_csv. The CSV writer/page implementation was not located in the inspected tree.
- Legacy schedule: a historical script comment references a scheduled run around 17:25; the actual cron/scheduler configuration was not verified.
- Legacy data is not selected as a runtime source. No legacy MySQL reads, migration or code reuse are planned.

## 3. Dataset classification

| Dataset | Classification | Authoritative source | New-system target / usage | Decision |
|---|---|---|---|---|
| Buyer search-term metrics | REBUILD_SYNC | Lingxing reportSearchImpressionSpList | fact_walmart_ad_search_term_daily | Selected |
| Manual keyword inventory/performance | REBUILD_SYNC | Lingxing reportKeywordSpList | fact_walmart_keyword_sp_daily | Selected |
| Advertiser/store identity | REBUILD_SYNC / existing L6 | dim_walmart_advertisers, dim_lingxing_stores, existing seller list sync | account/store filters and source display | Reuse; no guessed mapping |
| Listing identity for ad rows | Existing L6 evidence | fact_walmart_ad_item_sp_daily + mart_listing_management_current | unique campaign or campaign+adGroup mapping only | Reuse; ambiguous stays unresolved |
| RAW request evidence | Existing L2 | ods_api_raw_request_refs / ods_api_raw_blobs | replay/audit lineage | Reuse |
| Sync governance | Existing NEW_SYSTEM_OWNED governance | gov_integration_sync_configs / runs / work items | manual refresh, schedule and run status | Reuse |
| Add/negative action tasks | NEW_SYSTEM_OWNED (proposed) | operator-created task records | ops_ads_search_term_actions | Pending owner confirmation |
| Search-term comparison/trends | L8/L9 derived read model | persisted search-term facts + existing ad item/keyword facts | summary/detail/trend queries | Selected subject to date-grain contract |

## 4. Provider contract evidence

Owner-provided official Lingxing document:
https://apidoc.lingxing.com/#/docs/MultiPlatform/Advertisement/walmart-reportSearchImpressionSpList

It documents:
- required advertiserIds, startDate, endDate;
- optional campaignIds, searchedKeywords, searchText, reportFieldFilter;
- pageSize max 200, pageNum, day values 3/14/30, orderField/orderType;
- response fields searchedKeyword, advertiserId, campaignId, campaignType, targetingType, spend/click/order/direct-sales/other-sales metrics;
- no adGroupId, adItemId, itemId or triggering keyword ID in the listed search-term row schema.

Owner-run read-only server probes (2026-11-09) confirmed:
- Auto campaign query and search-term endpoint returned HTTP 200 / code 0; auto sample produced 154 strictly counted first-page rows for the selected query.
- Manual campaign query and search-term endpoint returned HTTP 200 / code 0; manual sample produced 200 strictly verified first-page rows, with one row rejected for advertiser mismatch and reported total 219.
- These were one advertiser and selected campaign samples, not a full-account/full-pagination reconciliation.
- reportKeywordSpList was previously read successfully for the same advertiser; the sample reported total 5,590.
- No production data was written by those probes.

## 5. Listing and store mapping decision

Search-term rows do not contain store_id or item_id directly.

- First use existing dim_walmart_advertisers.store_id when populated and supported by current identity evidence.
- Otherwise derive a candidate from fact_walmart_ad_item_sp_daily using source_account_ref + advertiser_id + campaign_id + business_date_la.
- Auto search-term rows may map to a Listing only when exactly one distinct (store_id, item_id) is evidenced for that campaign/date.
- Manual keyword rows may map using advertiser_id + campaign_id + ad_group_id to exactly one distinct (store_id, item_id).
- If zero or multiple candidates exist, retain campaign/account source and mark listing mapping unresolved/ambiguous.
- Never infer from campaign name, SKU text, item title or first-row wins.
- This is required to support cross-Listing comparisons without inventing associations.

## 6. Manual coverage decision

- Compare searchedKeyword with manual keywordName from reportKeywordSpList using exact normalized equality only.
- Preserve original text; comparison normalization is a derived key and must be documented/tested.
- Same Listing coverage is confirmed only if both source term and manual keyword map to the same unique Listing identity.
- Same-account keyword existence without a unique Listing mapping is account-level evidence only.
- No fuzzy match, semantic match, matchType-based claim, or actual-trigger-keyword claim.
- Missing manual keyword data must be “not synced/unknown”, not “not added”.

## 7. Write API gap — owner decision required

The current Walmart advertising catalog contains read/query interfaces. The project normalized/deleted interface evidence marks generic SP add-keyword / add-negative-keyword endpoints as DELETED / NOT_WALMART; they must not be reactivated or called for Walmart.

No Walmart-specific Lingxing add-keyword or add-negative-keyword endpoint has been verified in the supplied official Walmart advertising docs.

Proposed safe fallback:
- create internal NEW_SYSTEM_OWNED ADD_KEYWORD / ADD_NEGATIVE_KEYWORD action tasks;
- require operator to execute manually in Lingxing UI;
- operator records manual completion, target campaign/scope and reason;
- subsequent persisted search-term data is compared to show post-action observations;
- UI must say “待人工执行 / 已手动完成”, never “领星添加成功 / 领星否词成功”.

Owner decision required: approve this internal task workflow as the V1 substitute for direct provider writes, or provide a verified Walmart-specific Lingxing write contract. Until resolved, source decision remains BLOCKED_BY_OWNER_DECISION and implementation must not proceed.

## 8. Trend and refresh strategy

- Owner confirmed automatic sync + manual refresh.
- Use existing Integration Sync / Celery / RAW lineage; no route-time provider requests.
- Schedule config and outbound default disabled; production schedule enablement/first run requires separate authorization.
- Search-term response has no per-row reportDate. Daily trend requires a validated date grain. Proposed approach: request one-day date windows with day=14 and persist business_date_la; this exact one-day behavior has not yet been verified. If provider rejects one-day windows, use explicitly labelled rolling-window snapshots; never infer row date from response_time.
- Default attribution window 14 days matches the owner-run probes. Other day values require explicit business decision before adding UI choices.
- Paginate every advertiser and every page; validate row advertiser membership, source identity and data.total. Partial failures remain partial, never full success.

## 9. Database layering

- No legacy MySQL runtime reads or bulk migration.
- Reuse existing L2 RAW request/blob tables and governed Integration Sync tables.
- Additive PostgreSQL FACT tables for search-term daily facts and manual keyword daily facts.
- Internal action records, if approved, are NEW_SYSTEM_OWNED.
- Fact rows retain source_account_ref, advertiser_id, campaign_id, date/window, source_row_hash, source_raw_request_ref_id and synced_at.
- No raw payload, credential or signed URL returned to frontend.
- No modification of existing ad-spend, sales, profit or Listing calculation facts.

## 10. Permission and scope

- Page read: ads.search_terms.view.
- Action queue: ads.search_terms.actions.manage (only if fallback approved).
- Refresh: existing integrations:execute.
- All-user/global view means no product-owner filter; still obeys existing source_account IAM scope. The implementation must not bypass source_account scope or auto-grant roles.
- User's “all users see all” requirement can only be met for users whose IAM role has the appropriate all-account source scope.

## 11. Owner decision checklist

- [x] Lingxing only; no Walmart official API.
- [x] Search-term source contract identified.
- [x] Auto/manual SP search-term read probes completed on one advertiser.
- [x] Legacy system surveyed read-only; no legacy runtime source selected.
- [ ] Approve internal action queue fallback because Walmart-specific Lingxing write API is not verified.
- [ ] Approve daily trend date-grain strategy after one-day contract probe or rolling-window alternative.
- [ ] Confirm all operators who need global view have source_account=* IAM data scope.

Until the blocking action decision is resolved, this document remains BLOCKED_BY_OWNER_DECISION.

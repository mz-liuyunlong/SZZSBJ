# PRP — 广告 / 搜索词工作台 V1

Status: Approved for implementation — Owner confirmed 2026-11-09: external add/negative write APIs may be incomplete; all other V1 capabilities must be completed.
Base main SHA: cfb28285e9b57a32f9d3d66950466151a4f644c3
Planning branch: feat/ads-search-terms-workbench
Owner request: 2026-11-09；GitHub Issue #329；implementation may proceed on this scope.

## 1. Goal

实现导航「广告 → 搜索词」独立业务页面，使用领星 Walmart SP 搜索词数据，支持自动/手动广告分析、出单词发现、自动词的手动覆盖检查、跨店铺/Listing 对比、汇总/明细两种视图、历史变化、刷新、批量处理与效果跟踪。

页面已有导航与路径 /ads/search-terms；本任务不新增第二个导航项或改变路径，只接入独立页面组件和后端数据链路。

## 2. Confirmed business requirements

1. 自动广告和手动广告在同一工作台，可一起比较，也可单独筛选。
2. 快速查看出单词、未出单词及自动广告出单但手动尚未覆盖的词；不把“有订单”直接等同于“盈利好”。
3. 搜索词支持汇总视图和广告活动明细视图。
4. 同词跨店铺、跨 Listing 比较自动/手动表现。
5. 自动广告出单词优先检查当前 Listing 的手动覆盖，同时展示其他店铺/Listing 的已确认覆盖情况。
6. 好词处理支持单条和批量处理；差词支持指定范围的处理任务、人工确认及效果跟踪。
7. 所有运营默认查看全局搜索词数据，不按产品负责人过滤；仍必须遵守现有 IAM page permission 和 source_account data scope，不绕过 RBAC。
8. 自动同步与手动刷新均需支持；刷新使用现有 Integration Sync 治理与 Celery，不在请求线程直接调用领星。
9. 支持历史趋势和变化对比；在未确认阈值前只显示客观趋势/变化，不自行定义“异常”阈值。
10. 不需要个人常用查询，不需要导出。
11. 来源只展示可由真实数据确认的店铺、广告账户、广告活动和自动/手动类型；不展示或推断原始触发关键词、匹配方式。
12. 不增加相似搜索词语义归组；该需求未确认。
13. 不调用 Walmart 官方 API，只使用领星 API。

## 3. Scope

### In scope

- 独立页面组件：/ads/search-terms。
- SP 搜索词读取：/basicOpen/multiplatform/ads/reportSearchImpressionSpList。
- 手动关键词覆盖数据：/basicOpen/multiplatform/ads/reportKeywordSpList。
- 复用现有广告主维度、SP 广告商品事实、店铺/Listing 读模型，做有证据的来源关联。
- 搜索词事实数据、手动关键词事实数据、内部处理任务数据。
- 自动/手动分类、出单状态、手动覆盖状态、汇总与明细、跨店铺/Listing 比较、趋势、同步状态。
- 内部加词/否词处理任务与效果跟踪（仅在负责人确认下述受限方案后）。
- 页面专属 API、权限、审计、SOP、接口登记、测试。

### Out of scope

- Walmart 官方 API。
- 未经领星 Walmart 文档验证的外部广告写入。
- 导出、个人保存视图、相似词自动分组。
- 猜测原始触发关键词、matchType、SKU 或 Listing。
- 修改广告活动、词库、否定关键词等其他页面的既有业务。
- 自动执行加词/否词、自动调价或自动否词。
- 生产数据库迁移、生产 API 调用、开启生产定时任务、部署、服务重启。

## 4. Navigation / Page

- 一级导航：广告
- 二级导航：搜索词
- 页面路径：/ads/search-terms
- 现有 page key：ads_search_terms
- 现有 permissionKey：ads.search_terms.view（navigation.ts page() 默认生成）
- 不改变 navigation path；routes.tsx 只增加页面 renderer/import。
- 页面状态：实现阶段 building/testing；完成验收前不得标记 ready。
- PageShell helpUrl：/help/ads/search_terms。

## 5. Data source decision

Decision file: docs/data-sources/decisions/ads-search-terms-workbench-decision.md
Current decision status: BLOCKED_BY_OWNER_DECISION（读取来源已确定；加词/否词外部写入替代方案待负责人确认）。

- 搜索词：REBUILD_SYNC，领星 reportSearchImpressionSpList。
- 手动关键词覆盖：REBUILD_SYNC，领星 reportKeywordSpList。
- 广告商品/店铺/Listing 映射：复用现有 fact_walmart_ad_item_sp_daily、dim_walmart_advertisers、dim_lingxing_stores、mart_listing_management_current。
- 同步 run、RAW request refs/blobs：复用现有 Integration Sync / RAW 治理。
- 加词/否词处理记录：建议 NEW_SYSTEM_OWNED 内部待办，不调用领星写接口；待负责人确认。
- 不读旧 MySQL 作为运行时来源，不复制 old-system 代码。
- 不使用 Walmart 官方 API。

## 6. Identity and data correctness boundaries

- 搜索词接口返回 advertiserId、campaignId、campaignName、mpSellerName、mpAdvertiserName、campaignType、targetingType、searchedKeyword 和指标；未返回 adGroupId、adItemId、itemId、keywordId。
- 自动搜索词只能在同 advertiser + campaign + 日期范围的现有 ad item facts 能证明唯一 store_id + item_id 时映射到 Listing；多个商品、无证据或冲突时标记 listing_mapping_status=ambiguous/unresolved，不猜。
- 手动关键词接口返回 campaignId、adGroupId、keywordName 等；只有同 advertiser + campaign + adGroup 的 ad item facts 能证明唯一商品时，才建立该手动关键词与 Listing 的映射。
- 自动词对手动词覆盖检查：比较 searchedKeyword 与手动 keywordName 的精确规范化文本；保留原始文本，比较 key 仅用于 trim/case-insensitive equality；不做模糊或语义匹配。
- 覆盖状态必须区分：same_listing_confirmed、other_listing_confirmed、account_match_listing_unresolved、not_found、mapping_unresolved、data_not_synced。不能把数据缺失判成“未投放”。
- 当前 Listing 检查只有在来源 Listing 被唯一映射时才可判定；否则展示广告账户/活动来源和“Listing 未能准确关联”。
- 所有查询均过滤 advertiserId 必须属于本次请求的授权集合。领星响应出现跨 advertiser 行时丢弃并计入数据质量事件。
- ID 全部按字符串保存和比较；金额使用 Decimal；比率单位沿用领星字段，不在未核实前二次乘 100。
- 搜索词接口没有 attributedSales 总字段；direct/other sales 分开保存与展示。若展示归因总销售额，明确标记为 direct + other 的派生值。
- 不将请求成功、HTTP 200 或 code=0 直接等同于数据完整；必须验证分页、total、行身份、过滤结果和 RAW lineage。

## 7. API contract draft

本节为待确认契约，不代表接口已经实现。

### Read APIs

- GET /api/ads/search-terms/summary
  - Query: start_date, end_date, store_ids[], advertiser_ids[], campaign_ids[], targeting_type=all|auto|manual, query, conversion_state=all|orders|no_orders, page-specific filters.
  - Response: filtered counts and sums; totals must be computed from persisted fact rows, not current page.
- GET /api/ads/search-terms
  - Query: view=summary|detail, same filters, page, page_size, sort_by, sort_order.
  - Summary grain: normalized search term + selected comparison dimensions.
  - Detail grain: source_account_ref + advertiser_id + campaign_id + business date/window + source row identity.
- GET /api/ads/search-terms/trends
  - Query: search_term_key, advertiser/store/campaign/listing filters, start_date, end_date, attribution_days.
  - Response: date series and period-over-period deltas; no unapproved anomaly threshold.
- GET /api/ads/search-terms/options
  - Returns only authorized stores, advertisers, campaigns and resolvable Listing options from persisted data.
- GET /api/ads/search-terms/actions
  - Reads internal action tasks only if the action-queue fallback is approved.

### Internal action APIs — pending owner confirmation

- POST /api/ads/search-terms/actions
- POST /api/ads/search-terms/actions/batch
- PATCH /api/ads/search-terms/actions/{action_id}

These APIs create/update internal ADD_KEYWORD / ADD_NEGATIVE_KEYWORD tasks, record target campaign/scope, manual execution confirmation, operator, timestamps and post-action observations. They MUST NOT call Lingxing or claim that the ad was changed. Owner approved this V1 fallback in GitHub Issue #329.

### Refresh

Reuse existing Integration Sync APIs:
- POST /api/integrations/sync-configs/{config_id}/run
- GET /api/integrations/sync-runs/{run_id}
The page must not call Lingxing directly. Manual refresh requires integrations:execute and the user's existing source_account scope.

### Permissions

- Page read: ads.search_terms.view.
- Internal action task management: ads.search_terms.actions.manage.
- Refresh: existing integrations:execute.
- Data scope: existing source_account scope; global view means no product-owner restriction, not an IAM bypass.
- No permission grants are seeded or assigned automatically.

### Envelope / errors

Use existing SuccessEnvelope, request_id and standard ApiError conventions.
Expected safe error codes include ADS_SEARCH_TERMS_SCOPE_DENIED, ADS_SEARCH_TERMS_DATA_NOT_READY, ADS_SEARCH_TERMS_SYNC_IN_PROGRESS, ADS_SEARCH_TERMS_MAPPING_UNRESOLVED, ADS_SEARCH_TERMS_ACTION_WRITE_UNAVAILABLE, and existing integration sync errors.
meta.source_tables must name persisted fact/read-model tables; no RAW payload is returned.

## 8. UI requirements draft

- Follow current SZZSBJ light theme and existing PageShell/report patterns.
- Top summary cards: total terms, converting terms, auto converting terms without confirmed manual coverage, no-order terms with spend, ad spend, attributed orders.
- Filters: store, advertiser, campaign, date range, auto/manual, search text, orders state, order/spend range.
- Summary/detail toggle.
- Summary view groups same exact normalized search term and supports cross-store/listing/auto/manual comparisons.
- Detail view preserves campaign-level source records.
- Source display: store, advertiser, campaign, auto/manual. Listing shown only when unique mapping is proven.
- Compare drawer/panel displays per-store/listing/campaign rows and differences; unresolved mappings remain explicit.
- Search-term detail shows source metrics and mapping/coverage evidence, not trigger keyword or matchType.
- Trends compare dates and previous periods; no invented thresholds.
- Single/batch action task creation and status tracking only after owner approves fallback.
- Refresh uses existing Integration Sync governance and shows last success, partial/failed/stale state.
- Honest loading, empty, permission, stale, partial and error states; no mock rows or fake success.
- No export, no personal views, no similar-term grouping.

## 9. Sync and storage

Proposed additive storage:
- fact_walmart_ad_search_term_daily
- fact_walmart_keyword_sp_daily (manual keyword coverage evidence)
- ops_ads_search_term_actions (only if owner approves internal action queue)

Reuse:
- ods_api_raw_request_refs / ods_api_raw_blobs
- gov_integration_sync_configs / gov_integration_sync_runs / work_items
- dim_walmart_advertisers
- dim_lingxing_stores
- fact_walmart_ad_item_sp_daily
- mart_listing_management_current

Sync:
- advertiser IDs are discovered from persisted authorized advertiser dimensions, never hard-coded.
- All pages are fetched sequentially under the existing Lingxing client/rate controls.
- Default attribution window is 14 days, matching the owner-run probes; changing 3/14/30 requires explicit product decision.
- Date granularity/trend strategy must be contract-tested. The endpoint has date range inputs but no reportDate in each row; never infer a daily date from response time. Use one-day request slices only after validating startDate=endDate behavior; otherwise use explicitly labelled rolling-window snapshots.
- Automatic schedule config defaults disabled; schedule enablement and first production run require separate owner authorization.
- Manual refresh is bounded, idempotent and queued through Celery/Integration Sync.
- Partial advertiser/page failures are not reported as full success.

## 10. Implementation / PR split

Project PR Scope requires separate database, backend and frontend PRs.

1. Database PR: additive models/migrations/indexes/check constraints for approved fact/action tables only; no page/API code.
2. Backend PR: Lingxing contract allowlist, parser, Integration Sync handler, RAW lineage, persisted facts, manual keyword coverage, read APIs, internal action queue if approved, permissions and tests; no frontend files.
3. Frontend PR: SearchTerms page/components/hooks/API client, routes renderer only, Page Registry/SOP/UI tests; no backend files.
4. An integration branch may be supplied for local acceptance, but each PR must preserve the repository's scope gates.

## 11. Component reuse plan

Reuse actual existing components after verifying their current contracts:
- PageShell
- ManagementStatCards
- ReportTableShell
- ReportTableSelectionBar / existing batch selection pattern
- ConnectedSearch
- ResetButton
- RuntimeColumnConfigDrawer
- ReportTableCells / MoneyCell / PercentCell
- existing API client, auth and query hooks

No new Shared UI component is planned. Any new component should be Page Local or Ads Feature unless a second real consumer is approved. Update UI_COMPONENT_CATALOG only if a genuinely Shared component is introduced.

## 12. Validation gates

- Database: migration fresh/upgrade/downgrade tests, constraints/index tests, PostgreSQL isolated integration tests.
- Backend: parser contract tests, all-page pagination, row count vs total, duplicate/hash idempotency, cross-advertiser contamination, account scope, unique Listing mapping vs ambiguous mapping, manual coverage states, action audit/state tests, Celery retry/lock/partial failure tests.
- Frontend: Vitest for summary/detail, filters, auto/manual, coverage statuses, cross comparison, action task states, trend, stale/error/empty states; Playwright route workflow.
- Run repository preflight and applicable lint/type/build/test/CI gates. Do not mark NOT RUN as PASS.
- No production DB/API/worker/scheduler tests in this PRP.

## 13. Forbidden actions

- No Walmart official API.
- No deleted or non-Walmart Lingxing write endpoint.
- No external ad write, real add/negative, bidding, pause/resume or budget modification.
- No old-system modification or code copy.
- No production DB, credentials, .env, migration, API call, schedule activation, deployment or restart.
- No mock data, hardcoded store/campaign IDs, guessed Listing/keyword relationships, hidden errors or fake success.

## 14. Rollback

- Revert frontend PR, then backend PR, then database PR in reverse dependency order.
- Keep production scheduler disabled until separate authorization.
- New tables are additive; downgrade only after confirming no retained production data depends on them. If populated, back up/retain data before any downgrade.
- Internal action tasks are audit records; do not delete completed tasks as a rollback shortcut.

## 15. Acceptance checklist

- [ ] Owner approves this PRP and source decision.
- [ ] Owner approves internal action-queue fallback or supplies a verified Walmart Lingxing write API.
- [ ] Search term and manual keyword data fully paginated and lineage-preserved.
- [ ] Listing mapping is evidence-based; ambiguous rows never guessed.
- [ ] Global view obeys IAM scope and does not filter by product owner.
- [ ] Summary/detail, compare, trends, refresh, single/batch task tracking implemented.
- [ ] No export/personal view/similar-term feature.
- [ ] API docs, Data Interface Registry, Page Registry, Task Registry and SOP updated.
- [ ] Tests and latest-head CI pass.
- [ ] User local acceptance complete.
- [ ] No production schedule or deployment without separate authorization.

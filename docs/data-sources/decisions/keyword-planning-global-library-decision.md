# Keyword Planning Global Library: Data Source Decision

Status: READY_FOR_PRP. Owner implementation instruction: current Walmart Keyword V1.1 integration task.

| Investigation | Decision |
|---|---|
| Old page, API, files, tables, writer, cron, external API | Not applicable. This is a new-system owned keyword asset; no legacy runtime read or external fetch. |
| Manual entry | Existing `POST /products/{product_id}/library/manual` writes `biz_sku_keyword` and `biz_kw_source_event`. |
| Excel entry | Existing upload parser writes the same account-scoped asset and source event with immutable upload evidence. |
| Short-term and long-term source | `NEW_SYSTEM_OWNED`: `biz_sku_keyword` linked to `dim_kw_term` and `products`. Source events remain provenance, not an alternate asset authority. |
| Keyword score/grade | Latest account-and-product `ai_kw_analysis_run` joined to frozen `ai_kw_run_keyword`. Missing analysis remains unscored; no browser score calculation. |
| Freshness | Current committed asset on every request; analysis grade is frozen at the latest run. |
| Scope | Explicit `source_account_ref` grant plus `products:read`; every asset and run subquery is filtered by the same account. Cross-account associations are excluded. |
| Query grain | One normalized term per account in the global page; its associated products are the account's asset rows. Per-SKU endpoint retains product × term grain. |
| Rollback | Read-only endpoint. Roll back code without data changes. |

No schema change, second authority, background job, old-system dependency, or external API is introduced.

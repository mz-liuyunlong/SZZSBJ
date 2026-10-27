# Keyword Planning Global Library V1.1

Owner-approved scope: current Walmart Keyword V1.1 integration instruction. Data source decision: `docs/data-sources/decisions/keyword-planning-global-library-decision.md`.

Implement an account-scoped, backend-paginated distinct-term read from `biz_sku_keyword` and `dim_kw_term`, with product association and latest frozen analysis. Reuse the existing Keyword Library page and `products:read` plus source-account scope. Search and source/grade/status filters run before pagination; totals are computed by PostgreSQL. No RAW direct read, external API, schema migration, new UI, or writes. Verify account isolation, duplicate-free terms, pagination, filters, and unchanged per-SKU behavior with local isolated PostgreSQL and frontend tests. The separate rule-publishing policy remains blocked pending an approved exception.

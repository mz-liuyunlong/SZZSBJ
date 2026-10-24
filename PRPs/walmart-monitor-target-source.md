# Walmart Monitor Target Source PRP

## 1. Approval

```text
PRP Status: Approved
Implementation Authorized: Yes — local branch implementation only
Source Decision Gate: READY_FOR_PRP
Main Role: Backend Engineer
Branch: codex/walmart-monitor-target-source
Base: a35c690faa7475d38165f179d785b05ec7be1df6
Source Decision: docs/data-sources/decisions/walmart-monitor-target-source-decision.md
```

## 2. Goal

新增受保护的 `GET /api/integrations/walmart-monitor/targets`，以稳定分页从现有 Listing MART 返回监控目标；不新增数据库对象，不触发同步或外部 API。

## 3. Scope

### In scope

- route/schema/service/repository 分层；归档 Listing 从结果与 `total` 排除。
- 独立只读 machine bearer token 和 `integrations:walmart-monitor:read`。
- `source_account_ref + store_id + item_id`、类目、可空库存和 `monitoring_eligible=true`。
- 统一 envelope、response_model、错误响应、OpenAPI metadata、Markdown 文档和 tests。

### Out of scope

- RAW 接收端、RAW/ODS/MART 新表、Alembic。
- 资格配置页面或资格持久化。
- 历史回传、真实联调、部署、secret 配置、同步、Walmart/Decodo/Lingxing 调用。
- frontend、`old-system/**`、GPT/归档/价格/利润/成本。

## 4. Permissions and data scope

```text
page permissionKey: none
action permissionKey: integrations:walmart-monitor:read
data scope resource: non-archived current Listing MART rows, dedicated machine principal only
field permissions: approved target fields only
high-risk actions: none; read-only
```

## 5. Data source

```text
data source decision file: docs/data-sources/decisions/walmart-monitor-target-source-decision.md
decision status: READY_FOR_PRP
dataset classifications: REBUILD_SYNC + NEW_SYSTEM_OWNED
contains NEED_OWNER_DECISION: no
owner approval status: approved for local implementation
short-term strategy: read mart_listing_management_current
long-term strategy: separate approved eligibility rule when required
legacy exit criteria: switch monitor PRODUCT_SOURCE_URL after deployment and validation
old-system reference: no
new PostgreSQL tables: none
cache / mart tables: mart_listing_management_current
sensitive domain: inventory and store/account identifiers; machine-only contract
```

## 6. API contract

```text
method: GET
path: /api/integrations/walmart-monitor/targets
query: page >= 1; page_size 1..500 (default 200)
response data: {items, total, page, page_size}
meta.source: listing_management
meta.source_tables: [mart_listing_management_current, listing_archive_states]
errors: UNAUTHORIZED, FORBIDDEN, VALIDATION_ERROR, INTERNAL_ERROR
request_id: required
```

## 7. Implementation

1. Add exact-path machine auth with an independent secret setting; fail closed.
2. Add repository count/page query ordered by the stable business key, excluding current archived Listings in both queries.
3. Add service mapping without fallback inference; V1 eligibility constant true.
4. Register router, docs, catalog/registry/task/handoff.
5. Add synthetic tests proving auth, pagination, null/category mapping and no write/external calls.

## 8. Validation gates

- targeted pytest and complete relevant backend suite.
- ruff format/check with isolated cache.
- import/OpenAPI route check.
- `git diff --check` and rule-pack.
- confirm no migration/dependency/frontend/old-system changes.

## 9. Rollback

Remove router registration and machine-auth exact path. Withhold the service token to fail closed. No database rollback is required because the feature is read-only and has no migration.

## 10. Acceptance checklist

- [x] Source Decision complete and owner-approved.
- [x] route/schema/service/repository and response_model complete.
- [x] exact machine auth and permission tests pass.
- [x] stable pagination/category/null inventory/eligibility tests pass.
- [x] docs/catalog/registry/handoff complete.
- [x] no production/external actions performed.

## 11. Owner approval

The project owner explicitly approved continuing all monitoring integration tasks on 2026-10-22. Authorization is limited to local code, documentation and synthetic validation; production deployment, secrets, migrations, real monitoring and external API calls remain separate approvals.

The owner subsequently clarified that archived Listings must not be returned to the monitor. This supersedes the earlier all-current-Listings eligibility scope; non-archived Listings remain eligible in V1.

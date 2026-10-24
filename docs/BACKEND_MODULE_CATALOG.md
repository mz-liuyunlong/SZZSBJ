# 后端模块清单

## 文件用途

本文件用于记录本项目计划使用和已经实现的后端通用模块。

后端不使用“组件”这个概念，应使用 Route / Schema / Service / Repository / Model / Task / Integration 分层。

## 初始通用模块规划

| 模块 | 建议目录 | 用途 |
|---|---|---|
| Backend API Foundation | `backend/app/core/` | 请求关联、响应契约、异常、认证、权限与资源级数据范围 |
| Data Layer Foundation | `backend/app/core/config.py`, `backend/app/db/`, `backend/alembic/` | PostgreSQL 配置、同步 SQLAlchemy 会话和 Alembic 基础设施 |
| Product Management Backend MVP | `backend/app/modules/products/` | 新系统自有的产品主数据与平台销售关系 CRUD 边界 |
| Lingxing RAW Foundation | `backend/app/integrations/lingxing/`, `backend/app/models/raw_lingxing_api.py`, `backend/app/repositories/lingxing_raw.py`, `backend/app/services/lingxing_raw.py` | 受控 endpoint allowlist 的 readonly client 与脱敏 L2 RAW 写入边界 |
| Walmart Monitor RAW Ingestion V1 | `backend/app/modules/walmart_monitor/` | 接收一个统一 logical-check 事件，校验压缩 RAW 完整性并幂等写入独立 L2 RAW 表；不写 Listing/ODS/MART |
| Lingxing Token Manager | `backend/app/integrations/lingxing/token_manager.py` | 已合并的后端内部 Token client、单进程内存缓存与安全刷新边界；implementation PR #48，merge commit `a78af4d` |
| Integration Sync Governance + Lingxing SKU Detail Foundation V1 | `backend/app/modules/integration_sync/` and `backend/app/modules/sku_detail/` | 当前实现分支已准备可复用同步治理、RAW/ODS、Lingxing SKU DWD/DWS、local RAW importer、任务骨架与受保护 API contract；合并前仍为 `approved_for_implementation` |
| Media Image Assets M1 | `backend/app/modules/media_assets/` | 第三方商品图登记、异步安全缓存、128/512 WebP 派生图、签名同源读取和 Product Management 图片加速；受控 backfill 同时承担 pending/retryable-failed/stale-processing reconciliation；生产 migration/backfill 需独立授权 |
| Logging | `backend/app/core/logging.py` | 日志配置 |
| Pagination | `backend/app/schemas/pagination.py` | 分页请求和响应 |
| Task Model | `backend/app/models/task.py` | 统一后台任务表 |
| Audit Log | `backend/app/models/audit_log.py` | 操作日志 |
| LLM Adapter | `backend/app/integrations/llm/` | 模型调用封装 |
| External Client Base | `backend/app/integrations/base.py` | 第三方 API 基类 |

新增通用后端模块后，AI 必须更新本文件。

## Backend API Foundation

| 项目 | 内容 |
|---|---|
| Module name | Backend API Foundation |
| Module key | `backend-api-foundation` |
| Purpose | 提供 request ID、统一响应和错误、默认关闭认证、权限入口及资源级 store scope |
| Owned backend files | `backend/app/core/api.py`, `backend/app/core/auth.py`, `backend/app/core/permissions.py`, `backend/app/core/data_scope.py` |
| Application entrypoint | `backend/app/main.py` |
| Tests | `backend/tests/core/test_backend_api_foundation.py`, `backend/tests/test_health.py` |
| Public endpoint | 仅 `/health`；无需认证、权限或 data scope，只返回安全存活状态 |
| Protected default | 其他业务路由默认需要可信 Principal；无可信认证时 fail closed |
| Dependencies | 仅使用现有 FastAPI、Pydantic 与 Python 标准库；无数据库、无外部 API |
| Not in scope | 产品 API、legacy MySQL、PyMySQL、ORM、migration、mart/read model、frontend |

## Data Layer Foundation

| 项目 | 内容 |
|---|---|
| Module name | Data Layer Foundation |
| Module key | `data-layer-foundation` |
| Status | `implemented`；PR #38 已合并 |
| Purpose | 提供环境注入的 PostgreSQL 配置、单一 SQLAlchemy `Base`、延迟同步 engine、单一 sessionmaker、FastAPI DB dependency 和 Alembic scaffold |
| Owned backend files | `backend/.env.example`, `backend/app/core/config.py`, `backend/app/db/`, `backend/alembic.ini`, `backend/alembic/`, `backend/tests/db/` |
| Shared integration point | `backend/app/main.py` 的 lifespan 仅在应用关闭时释放已创建 engine；导入应用和 `/health` 不初始化数据库连接 |
| Public contract | `Base`, `get_engine`, `get_session_factory`, `get_db_session` |
| Transaction boundary | Route 只注入 session；Service/use case 在写成功后 commit；异常由 dependency rollback 并始终 close；Repository 只接收已注入 session，禁止 commit/rollback 和创建 engine |
| Persistence conventions | 瞬时时间使用 UTC-aware `DateTime(timezone=True)`；金额使用 Python `Decimal` 与 PostgreSQL `Numeric(18, 4)`；首个获批模型负责实际字段和校验 |
| Audit convention | 未来模型可按其 PRP 定义 `created_at`, `created_by`, `updated_at`, `updated_by`, `request_id`；本模块不提供 mixin、不创建审计表 |
| Dependencies | 仅复用锁文件已有 SQLAlchemy 2.x、Alembic、psycopg 3 和 pydantic-settings；未新增或升级依赖 |
| Tests | `backend/tests/db/test_config.py`, `backend/tests/db/test_base.py`, `backend/tests/db/test_session.py`, `backend/tests/db/test_alembic_scaffold.py` |
| PRP | `PRPs/data-layer-foundation-implementation.md` |
| PR | `#38` |
| Merge commit | `63b281b` |
| Not in scope | 业务 model/table、Product API 或其他业务 API、migration revision、SQL、Source Registry、RAW Storage、legacy MySQL、外部 API、worker、frontend、生产数据库连接、CI PostgreSQL |

## Product Management Backend MVP

| 项目 | 内容 |
|---|---|
| Module name | Product Management Backend MVP |
| Module key | `product-management-backend-mvp` |
| Status | `implemented`；PR #41 已合并（`fab3aef`） |
| Purpose | 通过受保护的 `/api/v1/products` 接口维护新系统权威的内部 SKU 产品和 platform/store/MSKU 销售关系 |
| Source authority | `products` 与 `product_platform_listings` 均为 `NEW_SYSTEM_OWNED`；`old-system/**` 不得作为 runtime datasource |
| Backend files | `backend/app/modules/products/`, one Alembic revision, scoped tests, and minimal router/metadata registration |
| API scope | 8 个已批准的产品与 listing GET/POST/PATCH 端点；无 DELETE、bulk、import/export |
| Permission keys | `products:read`, `products:create`, `products:update`, `product_listings:read`, `product_listings:create`, `product_listings:update` |
| Data scope | Future `platform + store_name`; module seam must fail closed until a trusted provider is supplied; full RBAC deferred |
| Sensitive fields | `purchase_price`, `wfs_fee`, `shipping_cost`; Decimal/Numeric(18,4), required currency companion, no values in logs/errors |
| API documentation | `docs/api/product-management-backend-mvp.md` |
| Validation evidence | PR #41 merged after frozen dependency sync, Ruff format/lint, mypy, and DB-disabled pytest (`63 passed, 1 skipped`) passed; PostgreSQL integration was skipped without an authorized `TEST_DATABASE_URL` |
| PRP | `PRPs/product-management-backend-mvp.md` |
| PR | `#41`；merge commit `fab3aef` |
| Not in scope | Frontend, legacy migration/runtime reads, external APIs/sync, import/export, workers, calculations, mart/read model, production DB, deployment, CI PostgreSQL |

## Walmart Monitor RAW Ingestion V1

| 项目 | 内容 |
|---|---|
| Module name | Walmart Monitor RAW Ingestion V1 |
| Module key | `walmart-monitor-raw-ingestion-v1` |
| Status | `approved_for_implementation`；当前分支实现已通过定向和完整后端验证，合并前不标记 `implemented` |
| Main role | Backend Engineer；branch `codex/walmart-monitor-raw-ingestion-v2` |
| Purpose | 将监控端一个 logical check（含 Decodo、Chrome 和 fallback attempts）作为单一 `walmart-monitor.raw.v1` 事件完整、幂等、append-only 保存 |
| Backend files | `backend/app/modules/walmart_monitor/`、一个 additive Alembic revision、settings/auth seam、scoped synthetic tests |
| API | `POST /api/integrations/walmart-monitor/raw-events`；统一 envelope；无 RAW read API |
| Authentication | 精确 POST 路径专用 bearer secret；machine principal `walmart-monitor-service`；仅 `integrations:walmart-monitor:write` |
| Data scope | Producer-bound opaque `source_account_ref + store_id + item_id`；不推断、不扩权、不返回 RAW |
| Storage | 独立 `raw_walmart_monitor_events` L2 RAW 表；完整 payload JSONB + searchable safe envelope；无 business-table foreign key |
| Integrity | base64/gzip/declared bytes/SHA-256、bounded decompression、schema limits、canonical hash、PostgreSQL atomic `event_id` conflict handling |
| Transaction | 首次事件 commit；相同重放返回 duplicate；同 ID 不同内容 409；任何失败 rollback，不留部分事件 |
| Source Decision | `docs/data-sources/decisions/walmart-monitor-raw-ingestion-decision.md` |
| PRP | `PRPs/walmart-monitor-raw-ingestion.md` (Approved 2026-10-22) |
| API documentation | `docs/api/walmart-monitor-integration.md` |
| Validation | targeted `28 passed`; full backend `1336 passed, 28 skipped`; full Ruff/compileall/Alembic head/rule-pack PASS；isolated PostgreSQL suites remain opt-in and were not connected |
| Not in scope | 商品来源 GET、监控端代码/SQLite、历史导入、RAW parser、ODS/MART/Listing、Celery、对象存储、外部 API、生产 migration/deploy、frontend、old-system |

## Lingxing RAW Foundation

| 项目 | 内容 |
|---|---|
| Module name | Lingxing RAW Foundation |
| Module key | `lingxing-raw-foundation` |
| Status | `approved`；实现已在当前分支完成并验证，合并前不标记 `implemented` |
| Main role | Backend Engineer |
| Purpose | 为 5 个获批 P0 endpoint 提供 readonly client shell，并将成功/失败分页响应经递归脱敏后写入 `raw_lingxing_api` L2 RAW 证据层 |
| Owned backend files | `backend/app/integrations/lingxing/`, `backend/app/models/raw_lingxing_api.py`, `backend/app/repositories/lingxing_raw.py`, `backend/app/services/lingxing_raw.py`, one Alembic revision, scoped tests, settings placeholders and metadata registration |
| Public contract | 内部写入边界；不新增业务 API、RAW read API 或前端入口 |
| Endpoint allowlist | `POST /basicOpen/multiplatform/walmart/list`；`POST /basicOpen/platformStatisticsV2/saleStat/pageList`；`POST /erp/sc/routing/data/local_inventory/batchGetProductInfo`；`POST /pb/mp/shop/v2/getSellerList`；`POST /basicOpen/multiplatform/profit/report/order` |
| Store/page boundary | store scope 不硬编码；未来真实运行必须显式传入非空 store allowlist；默认 `page_size <= 3`、`max_pages = 1`；full sync 禁止 |
| Writers/readers | `lingxing_raw:write` 预留给批准的 RAW writer；`lingxing_raw:read` 仅预留，读取默认拒绝并需后续独立批准 |
| Dependencies | 已实现的 Data Layer Foundation；使用现有锁定依赖；真实 credential 仅通过 `secret_ref` 边界注入 |
| Tests | 只使用 synthetic/mock HTTP，覆盖 redaction、hash、pagination、success/failure response 和禁止结构化写入 |
| PRP | `PRPs/lingxing-raw-foundation.md` |
| Approval evidence | Project Owner 于 2026-09-10 批准 implementation gate；规划 PR #43 已合并（`6c955d9`）；审批 PR #44 已合并（`0c7508a`）；implementation PR TBD |
| Not in scope | 真实 Lingxing API 调用/采样、DIM/FACT/Core/read model、frontend、full sync、定时任务、历史回补、RAW read API、自动删除、production migration、部署、secret 读取或输出 |

## Lingxing Token Manager

| 项目 | 内容 |
|---|---|
| Module name | Lingxing Token Manager |
| Module key | `lingxing-token-manager` |
| Status | `implemented` / `merged`；implementation PR #48，merge commit `a78af4d` |
| Main role | Backend Engineer |
| Purpose | 在后端内部安全获取、缓存和刷新 Lingxing access_token，并隔离 AppSecret/Token 与日志、RAW、前端和业务响应 |
| Owned backend files | `backend/app/integrations/lingxing/token_manager.py`、settings placeholders、scoped synthetic/mock tests and metadata registration |
| Official contracts | `POST /api/auth-server/oauth/access-token`；`POST /api/auth-server/oauth/refresh`；均为 `multipart/form-data` |
| Evidence | `docs/integrations/lingxing-auth-token-spec.md` |
| PRP | `PRPs/lingxing-token-manager.md`（Approved） |
| Storage | MVP 仅单进程内存缓存；不落库、不写 Redis、不写 `raw_lingxing_api` |
| Refresh | 以集中封装的 `expires_in` 为准；正常剩余 10 分钟刷新，短 TTL 按剩余总有效期的 20% 提前；refresh_token 单次使用并原子轮换 |
| Retry/concurrency | 每条 Token 请求链最多 2 次总尝试，切换 endpoint 不重置预算；短退避、无无限循环；单进程 lock/single-flight |
| Dependencies | 现有 Lingxing integration boundary；真实凭据只能通过后端 `secret_ref` 注入，不新增明文配置 |
| Security boundary | Token/AppSecret 使用 `SecretStr` 或等价封装，不得进入 repr、日志、异常、RAW、前端、测试夹具、文档或 Git；默认 `LINGXING_ENABLE_TOKEN_REQUESTS=false` |
| Tests | 仅使用 `httpx.MockTransport` 与 synthetic values；覆盖精确 multipart 字段、string/number TTL、提前刷新、原子轮换、已消费 refresh token 不重用、`2001003`/`2001008`/`2001009`/`3001008`、默认拒绝和并发刷新 single-flight |
| Approval | Project Owner 于 2026-09-11 批准 implementation gate 并下发后端 Prompt；implementation PR #48 已合并（merge commit `a78af4d`） |
| Controlled validation | 脱敏记录已在 PR #49 合并（merge commit `0032e4e`）；不表示业务 API 已接入或 P0 endpoint sampling 已完成 |
| Business client integration | PR #51 已合并（merge commit `e946503`）：readonly client 已完成 Token Manager provider 注入、逐请求认证 header 构造与 `2001003` 单次恢复重放；全部为 fake provider/MockTransport 验证，不表示真实业务 API 或 P0 sampling 已验证 |
| productList Python mock-only implementation | `implemented` / `merged`；PR #57，merge commit `63ad40b`；精确 `/erp/sc/routing/data/local_inventory/productList` contract、query-sign adapter、现有 Token Manager reuse、认证 query 隔离与 MockTransport/synthetic tests 已合并；官方 evidence 仍为 partial，不因 mock tests 改写为完整官方证据 |
| productList controlled full local RAW capture | Owner 后续一次性授权的运行 `lingxing_product_list_20260911T195715Z_636b2f7d` 已完成：ProductLists-only 串行分页 2 页，captured/total 均为 `1188`，stop `total_reached`；4 个本地文件位于 `LINGXING_LOCAL_RAW_DIR/<validation_run_id>/` 且不进入 Git；无 DB、`raw_lingxing_api`、业务表或 Redis 写入，无 P0 sampling、完整 response/商品字段/credential 输出 |
| productList next phase | 独立设计并实现 `local RAW -> server RAW import`；必须另行批准导入目标、完整性、幂等、敏感性、权限、失败恢复与审计边界，本次未实现 |
| Token Manager module not in scope | 真实 Token 获取/验证、业务 API、RAW 写入、Redis/共享存储、多实例协调、数据库表/migration、DIM/FACT/Core/read model、frontend、sync、deployment；上面的 controlled capture 是独立一次性验证，不扩大 Token Manager 模块范围 |

## Integration Sync Governance + Lingxing SKU Detail Foundation V1

| 项目 | 内容 |
|---|---|
| Module name | Integration Sync Governance + Lingxing SKU Detail Foundation V1 |
| Module key | `integration-sync-governance-backend-v1` |
| Status | `approved_for_implementation`；当前分支实现已准备并待只读复审，合并前不得标记 `implemented` |
| Main role | Backend Engineer；implementation branch `feat/integration-sync-governance-backend-v1` |
| Purpose | 为 Lingxing 及未来 Walmart/Amazon/TEMU source handlers 提供统一 run/config/dependency/event/lock/work-item/retention/parse/lineage 治理，并建设首个 Lingxing SKU identity/detail/DWS 后端链路 |
| Backend directories | `backend/app/modules/integration_sync/`, `backend/app/modules/sku_detail/`, four ordered Alembic revisions, scoped tests and `docs/api/integration-sync-governance-sku-detail-v1.md` |
| Governance storage | `gov_integration_interfaces`, `gov_integration_interface_dependencies`, `gov_integration_sync_configs`, `gov_integration_sync_runs`, `gov_integration_sync_run_events`, `gov_integration_sync_locks`, `gov_integration_sync_run_work_items`, `gov_raw_retention_policies`, `gov_parse_jobs`, `gov_data_lineage` |
| RAW / ODS storage | `ods_api_raw_blobs`, `ods_api_raw_request_refs`, `ods_lingxing_productlist_sku_refs`, `ods_lingxing_product_info_batch_items`; response hash dedup and safe request metadata; no payload API |
| DWD / DWS storage | `dwd_lingxing_sku_identity_index`, detail snapshots/current, images, global tags, and `dws_sku_base_profile_current`; source-derived/rebuildable, not Product Core authority |
| Identity contract | `productList.data.id -> lingxing_sku_id`; `batchGetProductInfo.data.sku -> lingxing_sku_code`; no SKU/MSKU/ItemID/internal Product inference except the Owner-approved `OD-ProductInfo-Bootstrap-01` exact SKU create/link path |
| Local import | Manifest/checksum/path/pagination-verified importer implemented for an outside-Git ProductList run; no provider/Token request; live import remains skipped when `DATABASE_URL` is missing |
| batchGetProductInfo | Redacted contract snapshots support the offline batch response parser, fixture publisher and `id_batch_page` one-time runner foundation; provider transport remains disabled and no real parameter choice, Token, or provider call is approved |
| Tasks | `execute_sync_run(run_id)` and `scheduler_tick()` Celery skeleton contracts are present; args contain only run ID, real outbound remains disabled, and tests require no live Redis/worker/beat |
| API scope | Approved protected `/api/integrations/**` metadata/trigger routes and `/api/products/skus/**` read routes under the existing project `/api/...` convention; unified envelope/request ID; no RAW payload; no frontend |
| Permission keys | `integrations:read`, `integrations:update`, `integrations:execute`, `integrations:raw_metadata:read`, `products:read`, `products:sync_history:read`, `products:raw_lineage:read`, `products:cost:read`, `products:operation_logs:read` |
| Data scope | Trusted opaque `source_account_ref` scope must fail closed; confirmed Product mapping additionally uses existing Product scope; roles are not hard-coded |
| Source/field status | Governance is `NEW_SYSTEM_OWNED`; ProductList identity and the synthetic/mock SKU-detail foundation are `REBUILD_SYNC`; real batchGetProductInfo interoperability remains blocked pending official evidence and separate Owner authorization |
| Security | No credential, Token, sign, Authorization, full URL, RAW payload, full ID batch, captured product value, or secret-bearing archive URI in logs/events/API/docs/tasks |
| Existing-table boundary | Does not drop, rewrite, or dual-write existing `raw_lingxing_api`; `OD-ProductInfo-Bootstrap-01` permits only minimal `products.sku/product_name` creation or exact active-SKU linking and never overwrites Product fields or creates/updates `product_platform_listings` |
| PRP | `PRPs/integration-sync-governance-backend-v1.md` |
| Source Decision | `docs/decisions/2026-09-12-integration-sync-governance-backend-v1-source-decision.md` |
| PR | TBD |
| Current branch evidence | Four revisions through `20260912_0006`, 20 approved tables in one metadata, 17 protected routes, synthetic parser/calculation/importer/batch tests; final merge status and PR remain TBD |
| Not in scope | Frontend/admin-frontend, old-system, real Lingxing/Token/ProductList/batchGetProductInfo calls, production DB/migration, live Redis/Celery, archive transport/deletion, ADS implementation, external provider handlers beyond the reusable contract, deployment, or Git publishing |

## Walmart Order / Sample Integrity Guard

| 项目 | 内容 |
|---|---|
| Module name | Walmart Order / Sample Integrity Guard |
| Module key | `walmart-order-sample-integrity-v1` |
| Status | `approved`；当前分支实现准备复审，合并前不得标记 `implemented` |
| Main role | Backend Engineer；branch `codex/fix-walmart-sample-order-dedup` |
| Purpose | 阻止可变订单字段生成新业务身份，保留历史冲突证据，兼容已确认 v3/v5 送样事实，并让 Daily Sales 区分确认零、未知和待核验 |
| Canonical identity | `source_account_ref + store_id + source_order_id + source_order_line_id`；跨账号/店铺隔离，金额、数量、商品、状态、折扣不参与身份 |
| Storage | Existing `fact_walmart_order_items` gains nullable canonical hash/current marker plus separate provider/effective Item ID lineage；Listing fill does not mutate provider evidence or create replay versions；`platform_order_no` / `reference_no` are versioned source-snapshot fields because availability and immutability are not provider-verified；legacy/current business snapshots remain immutable；audit uniqueness uses physical prior/current fact IDs so repeated A→B transitions remain distinct；legacy rows are never deleted automatically |
| Sample rules | Valid historical `zero-total-provider-status-strict-triple-v3` and valid current `provider-verified-sample-v5` are preserved only after a locked, complete evidence replay；missing/changed identity, product, amount, currency, quantity or cancellation evidence fails closed；candidate v5 remains unverified；unknown valid rule fails closed |
| Downstream boundary | Identity resolution uses current rows；refund matching prefers current and permits a unique pre-adoption legacy row only, while duplicate legacy versions fail closed；MART counts distinct verified orders and unique verified line quantities；missing/pending evidence is explicit |
| Migration | `20261020_0047_walmart_order_identity_guard` is additive and contains no data rewrite；current rows require complete identity/hash/Item lineage；downgrade succeeds only before current/audit evidence exists and otherwise fails before DROP；production execution or data-level rollback requires separate DBA/Owner authorization, conflict preview and recoverable backup |
| Tests | Synthetic unit/migration/UI tests plus opt-in isolated PostgreSQL 16 tests for 0046↔0047, data-bearing downgrade refusal, 5 identities/12 immutable legacy versions, Provider-NULL Item resolution replay, A→B→A→B audit events, concurrency/refunds, v3/v5 evidence replay and MART rollback |
| Evidence | `docs/data-sources/walmart-order-sample-integrity-fix.md` |
| PR | `#237`；merge commit TBD |
| Not in scope | Production database/migration/sync/backfill/MART rebuild, provider or Token request, sample auto-approval, historical deletion/update, scheduler/service change, old-system, deployment or merge |

## Product Detail Sync + Product Management BFF / Pricing V1

| 项目 | 内容 |
|---|---|
| Module name | Product Detail Sync foundation and Product Management BFF / Pricing V1 |
| Module key | `product-detail-sync-product-management-api-v1` |
| Status | `approved_for_implementation`; current worktree implementation is not `implemented` before review and merge |
| Main role | Backend Engineer; branch `feat/product-detail-sync-product-management-api` |
| Backend directory | `backend/app/modules/product_management/` plus minimal registration, Product listing primary flag, one Alembic revision, synthetic/mock tests, API doc and runbook |
| APIs | Eleven protected operations under `/api/product-management/**` and `/api/user-table-views/product-management`, including the count-only filtered summary, using the shared envelope/request ID foundation |
| Storage | Internal tags/assignments, account-scoped immutable pricing rule versions, safe persistent recalculation runs, rebuildable current pricing projection and principal-owned table views; existing Product/listing/DWD/DWS objects are reused |
| Calculations | Decimal-only WFS override selection, configured WFS/storage state flow, gross-weight first leg, three prices, gross margin, purchase/total-cost ROI and versioned A/B/C/exception grade |
| WFS evidence | Source URL/confirmation metadata can be versioned, but no concrete fulfillment/storage value is bundled; missing config returns `missing_rate` |
| Product Info integration | Contract-aligned batch fixture parser/publisher and `id_batch_page` one-time runner are reused; dedicated setting defaults false, field mismatch fails `CONTRACT_FIELD_MISMATCH`, and real outbound remains `outbound_not_authorized` |
| Permissions | `products:read`, `products:cost:read`, `products:export`, `products:pricing_rules:read`, `products:pricing_rules:update`, `products:pricing:recalculate`, `products:table_views:update` |
| Scope | Confirmed Product mapping plus trusted Product and source-account scopes; no SKU/MSKU/name inference except `OD-ProductInfo-Bootstrap-01` exact SKU create/link with traceable evidence |
| Product Core bootstrap | Recovery extension branch `feat/productinfo-controlled-sync`; default dry-run; minimal Product create/exact-link only; duplicate, missing, deleted or uncertain cases skip/fail closed; implementation pending review and merge |
| Review hardening | Exact batch SKU search is bounded to 1,000 values; recalculation defaults to persistent preview and isolates idempotency by principal/account/capability/mode; rule rollover is transactional with a partial unique open-version index; listing-level WFS overrides fail closed until listings gain account scope |
| Security | BFF never reads/returns RAW, provider payload, auth material or secret values; logs contain only actor/request/internal UUID/count/version/status |
| PRP | `PRPs/product-detail-sync-product-management-api-v1.md` |
| Source Decision | `docs/data-sources/decisions/product-management-product-detail-sync-decision.md` |
| API docs / runbook | `docs/api/product-management-api.md`; `docs/runbooks/production-lingxing-product-info-sync.md` |
| PR | TBD |
| Not in scope | Frontend, old-system, real Token/Lingxing/Walmart, production DB/server/migration/sync/deployment, guessed provider contract/rates, automatic schedule, RAW artifact, or Git publishing |

## RBAC v2 Post-0041 Hardening

| 项目 | 内容 |
|---|---|
| Module name | RBAC v2 Post-0041 Hardening |
| Module key | `rbac-v2-post-0041-hardening` |
| Status | `ready_for_review`；未合并、未部署、未执行生产 migration |
| Branch / base | `fix/rbac-post-0041-end-to-end-hardening` / `7a8eab793c4edf9e419b3ae846e2b47dddf51587` |
| Purpose | 对齐 navigation、page/action/field/data-scope、FastAPI route、对象状态校验和角色/用户授权；修复 Approval/WFS 断链、通配符判断、数据源账号范围及飞书异常泄漏 |
| Backend scope | `app/core/permission_policy_v2.py`, `app/core/data_scope.py`, IAM/RBAC、Approval、WFS、Product/SKU、Integration scope dependencies，以及 scoped tests |
| Migration | `20261017_0042_rbac_backfill`；接在 0041 后；回填已有旧审批 read grant并增加运营计划导入批次账号范围证据列；旧 key 暂留；不自动增加 WFS review、利润字段 grant 或 data scope；forward-only |
| New protected APIs | `GET/PUT /api/settings/rbac/users/{user_id}/data-scopes`；需要用户管理 page + `action:settings:user-management:configure-data-scope` |
| Data scope | 只有 `source_account` 已由通用业务 dependency 执行；合法值来自 governance config；用户级同类型覆盖角色级；空集 fail closed；store/owner/sku/product 仍是 registry-only |
| Product Core boundary | 缺少可信 ownership 模型，`/api/v1/products/**` 在独立 PRP 前仅真实 `is_super_admin` 可用；角色名 `admin` 不构成超管 |
| Security | 飞书 provider body/message/cause 和未净化 exception text 不进入日志、异常或公共响应；不记录 Token、重置链接或 RAW |
| Frontend alignment | Approval、WFS、User/Role Management 按 canonical action 控制按钮；用户资料、启停、角色与 scope 独立授权 |
| Evidence | `docs/iam/RBAC_V2_POST_0041_AUDIT.md` 及 `docs/operations/RBAC_V2_*`；最终 test/CI/PR 信息在发布验收文档更新 |
| PR | `#226`；open，未合并 |
| Not in scope | 生产数据库/服务器、生产 migration/deploy/restart、真实角色自动扩权、`source_account='*'` 自动授予、外部 API/Token、旧系统修改、store/owner/sku/product 通用过滤实现 |

## Walmart Monitor Target Source V1

| 项目 | 内容 |
|---|---|
| Module name | Walmart Monitor Target Source V1 |
| Module key | `walmart-monitor-target-source-v1` |
| Status | `approved_for_implementation`；本地实现待评审，未合并或部署 |
| Directory | `backend/app/modules/walmart_monitor_targets/` |
| Purpose | 通过专用只读 machine contract 向 Walmart 监控程序稳定分页提供未归档 Listing 目标 |
| API | `GET /api/integrations/walmart-monitor/targets`；统一 envelope、response model 与 OpenAPI metadata |
| Data source | `mart_listing_management_current`；用 `listing_archive_states` 排除归档商品；`REBUILD_SYNC`；不读取 RAW、旧系统或外部 provider |
| Stable key | `source_account_ref + store_id + item_id`，同时作为稳定分页顺序 |
| Fields | 店铺、SKU/MSKU、负责人、来源商品名、来源类目、可空 WFS 库存、V1 固定 `monitoring_eligible=true` |
| Permission | 专用 principal + `integrations:walmart-monitor:read`；独立 Bearer Token；普通用户会话不可用 |
| Database | 无新表、无 migration、无写入 |
| External effects | 不触发同步、Celery、Walmart、Lingxing、Decodo 或其他外部 API |
| PRP / Decision | `PRPs/walmart-monitor-target-source.md`；`docs/data-sources/decisions/walmart-monitor-target-source-decision.md` |
| API docs | `docs/api/walmart-monitor-target-source.md` |
| PR | TBD |
| Not in scope | RAW 接收、资格持久化、历史回传、真实联调、生产 secret/deploy、frontend、old-system、GPT/归档状态写入/利润/成本 |

## PMC Domestic Inbound Board M1

Module：既有pmc_domestic的独立入库模型（非收货行），inbound_router/schemas/service/repository/builder/publisher/models；文件采集器inbound_collector，复用Lingxing只读client与Token Manager。新增三个表由0049迁移管理；原收货接口不改。CSV无数据库依赖；发布CLI只读成功ODS并事务切换版本；Celery复用integration_sync已登记handler，不启用定时。状态：本地实现待真实数据验收；API/SOP/runbook与registry见同模块文档。


## 2026-10-20 国内仓打包单审批本地M1

来源决策READY_FOR_PRP及负责人本轮授权；四表OPS发号/订单/分配+EVT事件，0050接本地0049，保留已有迁移及业务资料。候选来自当前入库MART×符合条件Listing；builder v2把既有ODS良品/锁定证明规范化到MART payload，本地重新发布保留旧版，当前1454行。GET不查ODS、不调用外部。8个API见pmc-domestic-packing-approval-api.md；POST独立动作权限，可信账号隔离、幂等/并发库存/统一北京日发号/不可变事件。前端真实列表、审批弹窗、筛选/重试/分页及历史审计已接通。所有写入仅本地验证is_test=true，生产写保护；原采购与IAM保留，未自动授权角色。AD/manual/OWS/装箱/六态为后续切片。验证与逐表记录：docs/delivery/pmc-domestic-packing-approval-verification.md。继续dev，未新建分支/提交/推送/部署。

## 国内仓打包审批M2：最终手工流程（2026-10-21）

2026-10-21，当前dev，本地127.0.0.1:55432/LOCAL_DATABASE_NAME。最终范围是手工添加打包单与审批前同SKU商品身份修改；系统打包单管理已按负责人要求删除。没有生产访问、提交、推送或部署。

流程：先选择当前批次看板的入库单×SKU，再选择同账号同SKU的有效Listing目标店铺/ItemID；GTIN/MSKU跟随Listing，不能自由修改SKU。填写数量、报关、收货仓备注和原因后，仅保存待审批申请，不发PK、不分配库存。通过审批时重新核对当前来源和Listing指纹、库存上限，并在单事务中发PK、分配原来源库存和写不可变审计；驳回需要原因。多个手工申请共用原入库库存池，可分批审批但不可超量。

跨店铺以当前批次看板入库单为依据，保存原始和目标快照，不要求不存在的领星审批/转移单，不修改领星库存归属。缺少报关信息默认不报关并标记default；人工选择标记manual。未知到货数量保持未知。全部审批仍受local-only/is_test保护，不创建领星OWS或调用WFS。

手工新增需独立packing-manual-create动作权限；页面只读权限不能提交。既有approve/reject动作和来源账号隔离继续生效，不自动授予角色或用户权限。

本轮本地历史：0051已执行，保留其迁移历史；0052接0051，已在全库备份并检查pg_restore目录后仅应用本地。0052确认OWS关联表为空后删除，停用3条系统管理动作定义；新增ops_domestic_packing_manual_requests，保存来源复合外键、来源/目标快照、数量、报关、备注、原因、操作者、请求JSON/哈希、账号幂等键和UTC提交时间。原发号/审批/分配/事件四表沿用；orders的原快照与最终身份字段用于审批，0051剩余兼容字段不代表存在系统管理功能。

负责人最新要求：后续本地开发不再自动新增或执行迁移编号。本次不增加0053，不回退现有0051/0052。未来结构调整记录SQL及影响；上线前必须单独整理最终生产迁移方案，从生产实际版本验证，不把本地迁移历史直接当作发布批准。当前代码依赖新表/字段，不能只部署代码。现有local-only审批保护也不代表生产写入已开放。

前缀 /api/pmc/domestic/packing-approval，复用标准success/data/error/meta/request_id响应。

|方法/路径|用途/参数|权限与校验|
|---|---|---|
|GET /manual/sources|入库单×SKU来源，keyword/page/page_size及既有PackingQuery筛选|页面读+来源账号；当前发布惠州仓；余额含本地分配扣减|
|GET /manual/{board_id}/options|source_account_ref，返回来源指纹与同SKUListing身份及listing_version|页面读+来源账号；不跨账号|
|POST /manual|source_account_ref、warehouse_id=16168、board_id、source_version、target_store_id、target_item_id、listing_version、qty、customs、rwh、reason、idempotency_key|manual-create+local guard；同SKU/当前有效Listing/可用量/原因；响应id和pending|
|GET /pending/{candidate_id}/edit-options|source_account_ref，读取候选与目标身份|适用于自动候选或手工申请|
|GET /pending、/pending/summary|沿用现有列表及统计，追加origin=manual待审行|手工来源变化时阻断，成功审批后退出待审|
|POST /pending/{candidate_id}/approve、/reject|沿用既有命令，approve扩展目标店铺/ItemID、listing_version、edit_reason|独立approve/reject；单事务幂等、并发库存、审计|

其余历史及事件接口保持。/packs及/orders/{id}/link、/void、/test-flag已删除。来源、Listing、库存或状态变化返回冲突而非假成功。完整原接口契约见pmc-domestic-packing-approval-api.md；具体模型以packing_schemas.py为准。

验收证据：docs/delivery/pmc-domestic-packing-approval-m2-verification.md。


> 占位名称说明：`LOCAL_DATABASE_NAME` 与 `ISOLATED_TEST_DATABASE_NAME` 分别表示负责人已批准的本地开发库和隔离测试库；执行前必须与获批本地配置中的实际数据库名逐字核对，并同时核对环境、host、port及连接后数据库身份。占位名称不是可直接执行的数据库名，也不授权其他本地库或生产库。历史数量、指纹及备份哈希保持原记录。

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
| Lingxing Token Manager | `backend/app/integrations/lingxing/token_manager.py` | 已合并的后端内部 Token client、单进程内存缓存与安全刷新边界；implementation PR #48，merge commit `a78af4d` |
| Integration Sync Governance + Lingxing SKU Detail Foundation V1 | Proposed `backend/app/modules/integration_sync/` and `backend/app/modules/sku_detail/` | `approved_for_implementation` 的可复用同步治理、RAW/ODS、Lingxing SKU DWD/DWS、local RAW import、任务骨架与受保护 API contract；尚未实现 |
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
| Status | `approved_for_implementation`；Owner 已批准后端实现，尚未实现 |
| Main role | Backend Engineer；implementation branch `feat/integration-sync-governance-backend-v1` |
| Purpose | 为 Lingxing 及未来 Walmart/Amazon/TEMU source handlers 提供统一 run/config/dependency/event/lock/work-item/retention/parse/lineage 治理，并建设首个 Lingxing SKU identity/detail/DWS 后端链路 |
| Proposed backend directories | `backend/app/modules/integration_sync/`, `backend/app/modules/sku_detail/`, ordered Alembic revisions, scoped tests and backend API docs |
| Governance storage | `gov_integration_interfaces`, `gov_integration_interface_dependencies`, `gov_integration_sync_configs`, `gov_integration_sync_runs`, `gov_integration_sync_run_events`, `gov_integration_sync_locks`, `gov_integration_sync_run_work_items`, `gov_raw_retention_policies`, `gov_parse_jobs`, `gov_data_lineage` |
| RAW / ODS storage | `ods_api_raw_blobs`, `ods_api_raw_request_refs`, `ods_lingxing_productlist_sku_refs`, `ods_lingxing_product_info_batch_items`; response hash dedup and safe request metadata; no payload API |
| DWD / DWS storage | `dwd_lingxing_sku_identity_index`, detail snapshots/current, images, global tags, and `dws_sku_base_profile_current`; source-derived/rebuildable, not Product Core authority |
| Identity contract | `productList.data.id -> lingxing_sku_id`; `batchGetProductInfo.data.sku -> lingxing_sku_code`; no SKU/MSKU/ItemID/internal Product inference |
| Local import | Approved manifest/checksum-verified importer from the recorded ProductList run outside Git; no provider/Token request; may validate against confirmed local PostgreSQL and skips safely when `DATABASE_URL` is missing |
| batchGetProductInfo | Approved only for disabled-by-default skeleton/mock/fixture parser and `id_batch_page` work-item foundation; no real parameters, Token, or provider call are approved |
| Tasks | Approved `execute_sync_run(run_id)` and `scheduler_tick()` Celery skeleton contracts; manual/schedule/retry/backfill/import share the run model; eager/mock/service tests, no live Redis/worker/beat and no RQ |
| API scope | Approved protected `/api/integrations/**` metadata/trigger routes and `/api/products/skus/**` read routes under the existing project `/api/...` convention; unified envelope/request ID; no RAW payload; no frontend |
| Permission keys | `integrations:read`, `integrations:update`, `integrations:execute`, `integrations:raw_metadata:read`, `products:read`, `products:sync_history:read`, `products:raw_lineage:read`, `products:cost:read`, `products:operation_logs:read` |
| Data scope | Trusted opaque `source_account_ref` scope must fail closed; confirmed Product mapping additionally uses existing Product scope; roles are not hard-coded |
| Source/field status | Governance is `NEW_SYSTEM_OWNED`; ProductList identity and the synthetic/mock SKU-detail foundation are `REBUILD_SYNC`; real batchGetProductInfo interoperability remains blocked pending official evidence and separate Owner authorization |
| Security | No credential, Token, sign, Authorization, full URL, RAW payload, full ID batch, captured product value, or secret-bearing archive URI in logs/events/API/docs/tasks |
| Existing-table boundary | Does not drop, rewrite, or dual-write existing `raw_lingxing_api`; does not overwrite `products` or `product_platform_listings` |
| PRP | `PRPs/integration-sync-governance-backend-v1.md` |
| Source Decision | `docs/decisions/2026-09-12-integration-sync-governance-backend-v1-source-decision.md` |
| PR | TBD |
| Not in scope | Frontend/admin-frontend, old-system, real Lingxing/Token/ProductList/batchGetProductInfo calls, production DB/migration, live Redis/Celery, archive transport/deletion, ADS implementation, external provider handlers beyond the reusable contract, deployment, or Git publishing |

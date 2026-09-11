# Data Interface Registry

Registry Status: `draft; approved only after owner review and merge`

## Registry Rules Summary

- GitHub 中本文件是真源；外部表格仅是只读镜像。
- 空表不表示能力不存在；条目只有在 PR 合并且验证通过后才可为 `implemented`。
- 未知值写 `TBD` 并保持 `candidate/blocked`；Secret 只写 `secret_ref`。

## External Interface Registry

| Interface ID | Provider | Interface Name | Direction | Method | Endpoint / Source Path | Auth Type | Secret Ref | Business Purpose | Platform / Store Scope | Sync Type | Sync Cadence | RAW Required | RAW Storage Location | Standardized Layer | Core Table | Read Model | Backend API | Frontend Page | Permission Key | Owner | Status | PRP | PR | Last Updated | Risk / Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `ext-lingxing-p0-raw-candidates` | Lingxing | P0 RAW endpoint allowlist | Inbound | POST | `/basicOpen/multiplatform/walmart/list`<br>`/basicOpen/platformStatisticsV2/saleStat/pageList`<br>`/erp/sc/routing/data/local_inventory/batchGetProductInfo`<br>`/pb/mp/shop/v2/getSellerList`<br>`/basicOpen/multiplatform/profit/report/order` | Lingxing Token Manager；client integration implemented in PR #51 | `secret_ref` only | 为获批 P0 业务响应保存脱敏、可回放 RAW 证据 | 代码不硬编码；真实调用必须显式传入非空 store allowlist | Bounded capture implementation scope | None；真实运行另行批准 | Yes | `storage-raw-lingxing-api-candidate` | None approved | None | None | None | None | Default deny；reserved `lingxing_raw:write` / `lingxing_raw:read` | Project Owner | `approved` | `PRPs/lingxing-raw-foundation.md` | `#43` planning；`#44` approval；`#51` client Token integration (`e946503`) | 2026-09-11 | Client Token Manager integration 已通过 mock-only PR #51 合并；真实业务调用和 P0 sampling 仍未批准或验证；`page_size <= 3`、`max_pages = 1`、禁止 full sync 和认证明文存储 |
| `ext-lingxing-auth-access-token-candidate` | Lingxing | 获取 access_token 与 refresh_token | Outbound auth request | POST | `/api/auth-server/oauth/access-token` | AppID/AppSecret credential exchange | `secret_ref` only | 为后端 Token Manager 获取短期访问令牌 | Enterprise credential scope；不涉及 store scope | On demand；internal client implemented, default disabled | None | No | None；Token 明文禁止写 RAW | None | None | None | None | None | Backend internal only；不暴露业务 API | Project Owner | `implemented` | `PRPs/lingxing-token-manager.md` | `#46` evidence；`#47` approval；`#48` implementation；`#49` controlled validation（`0032e4e`） | 2026-09-11 | Backend MVP 已在 PR #48 合并；2026-09-11 controlled validation 仅确认 GetToken 成功、Token 字段存在及 `expires_in` 观察值 `7199`/`7092` 与当前按秒处理兼容；不构成固定两小时 SLA；未验证业务 API，未写 RAW/DB/Redis，未记录凭据 |
| `ext-lingxing-auth-refresh-token-candidate` | Lingxing | 续约接口令牌 | Outbound auth request | POST | `/api/auth-server/oauth/refresh` | AppID + single-use refreshToken | `secret_ref` only | 为后端 Token Manager 刷新访问令牌 | Enterprise credential scope；不涉及 store scope | On demand；internal client implemented, default disabled | None | No | None；Token 明文禁止写 RAW | None | None | None | None | None | Backend internal only；不暴露业务 API | Project Owner | `implemented` | `PRPs/lingxing-token-manager.md` | `#46` evidence；`#47` approval；`#48` implementation；`#49` controlled validation（`0032e4e`） | 2026-09-11 | 2026-09-11 controlled validation 确认 RefreshToken 成功、refresh token 与 snapshot 轮换且旧 refresh token 未复用；立即刷新时 access token 字符串未变化，因此不得以字符串变化作为成功条件；未验证业务 API，未写 RAW/DB/Redis，未记录凭据 |
| `ext-lingxing-product-list-candidate` | Lingxing | 查询本地产品列表 | Outbound business read candidate | POST | `/erp/sc/routing/data/local_inventory/productList` | Official query auth: access_token + app_key + timestamp + sign; current client contract absent | `secret_ref` only | 评估本地产品列表是否适合作为首个 controlled business API validation 目标 | 官方 endpoint 未列 store/seller/company/warehouse 参数；账号级实际范围未确认 | None approved | None | No in this gate | None | None approved | None | None | None | None | No frontend/API router | Project Owner | `candidate` | `PRPs/lingxing-product-list-controlled-validation.md` | TBD | 2026-09-11 | 官方 ProductLists 页面与通用指南证据已捕获：POST JSON body、offset/length、SKU/时间筛选、code 0、data/total、bucket capacity 1 及 query signing；当前 header-only client auth 与官方 query/sign contract 的差异待 Owner review；禁止实现、真实调用、RAW/DB/Redis 写入和 broad P0 sampling，PR/merge TBD |
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

## Internal Backend API Registry

| API ID | Method | Route | Purpose | Source Layer | Read Model / Table | Permission Key | Data Scope | Frontend Page | Status | PRP | PR | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `api-product-list` | GET | `/api/v1/products` | 分页查询内部 SKU 产品 | L4 Core, manual-write exception | `products`; optional listing filters join `product_platform_listings` | `products:read` | Future `platform + store_name`; trusted module provider required, absent provider fails closed | `products_product_management` | `implemented` | `PRPs/product-management-backend-mvp.md` | `#41` | PR #41 merged at `fab3aef`; no legacy runtime source, external API or read model |
| `api-product-detail` | GET | `/api/v1/products/{product_id}` | 查询单个内部 SKU 产品 | L4 Core, manual-write exception | `products` | `products:read` | Trusted Product module scope; absent provider fails closed | `products_product_management` | `implemented` | `PRPs/product-management-backend-mvp.md` | `#41` | PR #41 merged at `fab3aef`; product response excludes listing collection |
| `api-product-create` | POST | `/api/v1/products` | 人工创建一个产品 | L4 Core, manual-write exception | `products` | `products:create` | Trusted Product module scope; absent provider fails closed | `products_product_management` | `implemented` | `PRPs/product-management-backend-mvp.md` | `#41` | PR #41 merged at `fab3aef`; API-only write, no bulk/import/direct DB path |
| `api-product-update` | PATCH | `/api/v1/products/{product_id}` | 人工更新一个产品 | L4 Core, manual-write exception | `products` | `products:update` | Trusted Product module scope; absent provider fails closed | `products_product_management` | `implemented` | `PRPs/product-management-backend-mvp.md` | `#41` | PR #41 merged at `fab3aef`; no delete, restore or version rollback |
| `api-product-options` | GET | `/api/v1/products/options` | 返回 MVP 静态平台选项 | L5 Reference, in-code approved enum | N/A | `products:read` | Trusted Product module scope; absent provider fails closed | `products_product_management` | `implemented` | `PRPs/product-management-backend-mvp.md` | `#41` | PR #41 merged at `fab3aef`; only `walmart`, `amazon`, `temu`, `other`; no speculative reference table |
| `api-product-listings-list` | GET | `/api/v1/products/{product_id}/listings` | 分页查询产品的平台销售关系 | L4 Core, manual-write exception | `product_platform_listings` | `product_listings:read` | Future `platform + store_name`; trusted module provider required, absent provider fails closed | `products_product_management` | `implemented` | `PRPs/product-management-backend-mvp.md` | `#41` | PR #41 merged at `fab3aef`; no external API or sync |
| `api-product-listing-create` | POST | `/api/v1/products/{product_id}/listings` | 人工创建一个平台销售关系 | L4 Core, manual-write exception | `product_platform_listings` | `product_listings:create` | Future `platform + store_name`; trusted module provider required, absent provider fails closed | `products_product_management` | `implemented` | `PRPs/product-management-backend-mvp.md` | `#41` | PR #41 merged at `fab3aef`; one relation per request, no import/direct DB path |
| `api-product-listing-update` | PATCH | `/api/v1/products/{product_id}/listings/{listing_id}` | 人工更新一个平台销售关系 | L4 Core, manual-write exception | `product_platform_listings` | `product_listings:update` | Future `platform + store_name`; trusted module provider required, absent provider fails closed | `products_product_management` | `implemented` | `PRPs/product-management-backend-mvp.md` | `#41` | PR #41 merged at `fab3aef`; no delete, external sync or bulk update |

## Storage / Table / Read Model Registry

| Storage ID | Layer | Object Name | Purpose | Authority Level | Source Interface | Write Owner | Read Owner | Retention | Permission / Sensitivity | Status | PRP | PR | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `storage-application-postgresql-foundation` | Infrastructure | Application PostgreSQL data layer | 提供环境注入的 PostgreSQL 连接、SQLAlchemy metadata/session 与 Alembic scaffold 边界 | Foundation only；不承载业务权威数据 | N/A | 未来获批 Service/use case | 未来获批 Repository | N/A | URL 仅通过环境 secret 注入；本层不存储业务数据 | `implemented` | `PRPs/data-layer-foundation-implementation.md` | `#38` | PR #38 已合并（`63b281b`）；无业务表、Product API、Source Registry、RAW Storage、外部 API、生产数据库连接、CI PostgreSQL、table/read model 或 migration revision |
| `storage-products-core` | L4 Core | `products` | 公司内部 SKU 粒度产品主数据 | `NEW_SYSTEM_OWNED` | Human input through approved Product Management API; no external interface | Product Management service | Product Management repository/service | Retention/delete policy deferred; `deleted_at` reserved only | Purchase price is sensitive; protected API only | `implemented` | `PRPs/product-management-backend-mvp.md` | `#41` | PR #41 merged at `fab3aef`; direct DB writes, legacy migration, import and external sync remain prohibited |
| `storage-product-platform-listings-core` | L4 Core | `product_platform_listings` | 产品与 platform/store/MSKU 的销售关系 | `NEW_SYSTEM_OWNED` | Human input through approved Product Management API; no external interface | Product Management service | Product Management repository/service | Retention/delete policy deferred; `deleted_at` reserved only | Store relationship and fee fields are sensitive; protected API only | `implemented` | `PRPs/product-management-backend-mvp.md` | `#41` | PR #41 merged at `fab3aef`; unique `platform + store_name + msku`; no normalized store table or external sync |
| `storage-raw-lingxing-api-candidate` | L2 RAW | `raw_lingxing_api` | 保存获批领星业务响应的脱敏、append-only 来源证据 | Evidence only；不是业务权威 | `ext-lingxing-p0-raw-candidates` | Approved Lingxing RAW writer | No reader implemented；future reader requires separate approval | MVP no auto-delete；archive/delete requires separate Owner task | High sensitivity；default deny；reserved `lingxing_raw:write` / `lingxing_raw:read`；no credential plaintext | `approved` | `PRPs/lingxing-raw-foundation.md` | `#43` planning；`#44` approval；implementation PR TBD | 表、migration、model、repository/service/writer 已在当前分支实现并通过验证，合并前仍为 `approved`；`raw_hash` 仅普通索引；不允许前端/业务 API 直查，不允许写 DIM/FACT/Core，不授权真实 API 调用 |

## Frontend Usage Registry

| Page Key | Page Name | Data Dependency | Backend API | Read Model | Display-only Calculation | Mock Status | Permission Key | Status | PRP | PR | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `products_product_management` | 产品管理 | Approved future Product Management MVP dependency | `api-product-list`, `api-product-detail`, `api-product-create`, `api-product-update`, `api-product-options`, `api-product-listings-list`, `api-product-listing-create`, `api-product-listing-update` | None | None | Existing page remains no-API until a separate frontend integration task | Backend API keys are recorded above; existing page permission remains separately governed | `approved` | `PRPs/product-management-backend-mvp.md` | TBD | Dependency contract only; this PR does not connect or modify the frontend |

## Sync / Import / Export Registry

| Flow ID | Type | Source Interface / File | RAW Location | Target Layer / Object | Run / Batch ID | Idempotency Key | Cadence / Trigger | Permission Key | Owner | Status | PRP | PR | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |

## Notification / Webhook Registry

| Notification ID | Provider | Purpose | Source Event | Secret Ref | Recipient Scope | Dedup / Cooldown | Permission Key | Owner | Status | PRP | PR | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |  |  |  |

## Status Definitions

| Status | Meaning |
|---|---|
| `planned` | 已规划，未批准实现 |
| `candidate` | 候选，证据不足 |
| `approved` | 精确范围获批，未必实现 |
| `implemented` | 已合并并有验证证据 |
| `blocked` | 存在明确阻塞 |
| `deprecated` | 不再新增使用 |
| `superseded` | 已被另一条目取代 |

## Update Checklist

- [ ] 状态有 PRP/PR 或负责人决定证据。
- [ ] 来源、RAW、目标层、读写方和前端依赖可追溯。
- [ ] 权限、data scope、敏感性和 freshness 已说明。
- [ ] 只记录 `secret_ref`，没有秘密值。
- [ ] 同一 PR 同步更新受影响的 Page/Task/Module catalog。

# Backend API Foundation PRP

```text
Status: Approved
Owner Approval Required: Yes
Implementation Allowed Before Merge: No
Database Access Used In This PRP Task: No
Server Access Used In This PRP Task: No
External API Used In This PRP Task: No
```

## 1. Authorization Boundary

本 PRP 只定义后续 Backend API Foundation 的批准范围、架构约束和验收要求。

```text
Canonical module name: Backend API Foundation
Canonical module key: backend-api-foundation
```

后续实现文件、测试、模块清单和 Review 报告必须统一使用该 canonical name/key；代码标识符需要 snake_case 时使用 `backend_api_foundation`。本文后续单独使用 “Foundation” 时，仅是 `Backend API Foundation` 的解释性简称，不代表另一个模块。

- 本 PRP 不授权在当前分支编写或修改后端代码。
- 本 PRP 不授权在当前分支连接数据库、服务器或 SSH tunnel。
- 本 PRP 不授权在当前分支执行 SQL、migration、同步或外部 API 调用。
- 本 PRP 不授权在当前分支修改 `backend/pyproject.toml` 或 `backend/uv.lock`。
- 本 PRP 不批准任何业务 API、业务字段、数据源或数据库对象。
- 只有架构师 Review PASS、负责人将状态改为 `Approved` 并合并本 PRP 后，后端工程师才可在独立实现分支和明确执行 Prompt 下实施本 PRP。
- 产品基础信息 API 必须等待本 Foundation 的实现 PR 合并到 `main` 后，才可按其已批准 PRP 继续。

PRP 合并不是代码实现，也不授权 Git 上传、生产启用、数据库访问或产品 API 实现。

## 2. Background and Current Baseline

当前后端基线只有一个 FastAPI health endpoint；仓库内尚无共享的 request ID、统一响应、统一异常、认证 Principal、permission dependency 或 data-scope foundation。

已合并的 `PRPs/phase-2a-product-basic-information-query-api.md` 明确要求以下能力先通过独立批准任务进入 `main`：

- authentication / permission / data-scope foundation；
- unified response envelope / request-ID foundation。

之前的 combined backend attempt 被 Review 阻塞，主要原因是：

1. 通用 foundation 未经独立 PRP/PR 批准并进入 `main`；
2. 除 404 外的 `StarletteHTTPException` 不能全部转成 500，405 等客户端错误必须保留安全的 HTTP 语义；
3. dependency lockfile 不得在没有负责人授权时修改；
4. rule-pack 的 worktree 误报或命名冲突不得在业务 PR 中顺手修改检查脚本。

本 PRP 先将共享 Backend API Foundation 独立定义和审批。后续顺序固定为：

```text
Foundation PRP Review / Approval / Merge
  -> Foundation implementation PR Review / Merge to main
  -> Product Basic Information API implementation resumes under its own Approved PRP
```

## 3. Goal

后续实现提供一套最小、共享、可测试且默认安全关闭的 FastAPI foundation，使业务模块能够复用：

- request ID middleware 和一致传递；
- success/error response envelope；
- 基础 error code 与统一 exception handling；
- authentication dependency entrypoint；
- permission-key check entrypoint；
- `store_id` data-scope abstraction；
- 不进入生产路径的测试注入方式。

本 Foundation 不是完整登录系统、RBAC 管理系统或数据权限配置后台，不新增业务 endpoint，也不读取或写入业务数据。

## 4. Data and Governance Applicability

```text
Business dataset: none
L0-L19 queried layer: not_applicable
Database read/write path: none
Business response fields: none
Source Decision required for this foundation itself: no
Relevant governance planes: G3 Data Contract, G4 Permission / Data Scope
```

本 Foundation 只定义 HTTP、安全上下文和授权边界，不决定任何业务数据来源或字段含义。所有消费该 Foundation 的业务 API 仍必须独立满足 Source Decision、字段标准化、权限、数据质量和 API PRP 门禁；不得以 Foundation 已合并为由绕过业务门禁。

## 5. Foundation Flow

```text
Inbound request
  -> request ID middleware
  -> trusted authentication dependency entrypoint
  -> permission-key dependency
  -> data-scope resolver
  -> approved business route/service/repository, when separately authorized
  -> shared success envelope

Validation / HTTP / application / unknown exception
  -> shared exception mapping
  -> safe error envelope
  -> response X-Request-ID
```

Foundation 不承担业务 Service、Repository、Model、Integration 或 Celery Task 职责。

## 6. Request ID Foundation

### 6.1 Required behavior

- 每个 HTTP request 必须获得一个非空 `request_id`。
- 优先读取入站 `X-Request-ID`。
- 入站值缺失、为空或不符合安全格式时，后端生成 UUID。
- response header 必须返回 `X-Request-ID`。
- success 和 error response body 必须返回同一个 `request_id`。
- request ID 只用于请求关联，不作为用户、权限、业务记录或幂等键。
- request ID 不得由账号、Token、邮箱、SKU、ItemID、store ID、query string、request body 或其他敏感/业务值拼接生成。

### 6.2 Safe inbound format

后续实现固定使用以下边界：

- 去除入站 header 两端空白后再校验；
- 长度为 1–128；
- 只允许 ASCII 字母、数字、点、下划线、冒号和连字符；
- 不截断、不猜测修复、不改变大小写；
- 不符合格式时丢弃原值并生成 UUID，不在响应或日志中回显无效原值。

调用方应提供不含业务含义的 opaque correlation ID。格式校验不能证明语义无敏感信息，因此服务端不得主动从业务内容生成 request ID。

## 7. Unified Response Envelope

### 7.1 Success response

```json
{
  "success": true,
  "data": {},
  "error": null,
  "meta": null,
  "request_id": "<opaque-request-id>"
}
```

- `data` 和 `meta` 的具体 schema 由各业务 API 的 Approved PRP 定义。
- Foundation 只提供共享 envelope schema/helper；业务 route 仍必须声明具体 `response_model`。
- `meta` 可为 `null`，或使用业务 PRP 明确批准的结构。

### 7.2 Error response

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数无效",
    "details": {}
  },
  "meta": null,
  "request_id": "<opaque-request-id>"
}
```

- `error.code` 是稳定的机器可读字符串；客户端不得解析 message 判断错误类型。
- `error.message` 必须安全、简洁且面向调用方，不直接使用底层异常文本。
- `error.details` 默认 `{}`；如返回校验详情，只允许安全字段名和稳定原因码，不回显敏感输入。
- `error.details`、message 和 meta 均不得包含 stack trace、SQL、DSN、secret、Token、凭据、内部主机或原始异常详情。
- 普通 error response 的 `meta` 固定为 `null`；业务模块如需错误 meta，必须在自己的 PRP 中单独批准。

Route handler 不得散写 envelope。后续实现应通过共享 Pydantic schema、helper 和 exception handler 统一生成，同时避免在共享 helper 中加入业务字段或业务判断。

## 8. Error Code and Exception Model

Foundation 基础错误码固定为：

| Code | HTTP status | Foundation meaning |
|---|---:|---|
| `INVALID_REQUEST` | 400 | 请求无法按基础 HTTP 契约处理。 |
| `VALIDATION_ERROR` | 422 | FastAPI/Pydantic 请求校验失败。 |
| `UNAUTHORIZED` | 401 | 没有可信、有效的 Principal。 |
| `FORBIDDEN` | 403 | Principal 缺少所需 permission key。 |
| `DATA_SCOPE_DENIED` | 403 | 请求的显式数据范围超出授权范围。 |
| `NOT_FOUND` | 404 | 路径或资源不存在，且无更具体业务错误。 |
| `METHOD_NOT_ALLOWED` | 405 | 路径存在但 HTTP method 不允许。 |
| `INTERNAL_ERROR` | 500 | 未知内部异常；不得泄露底层详情。 |

Foundation 的异常模型必须接受业务模块在其 Approved PRP 中声明的稳定错误码，而不是用封闭枚举阻止扩展，也不得接受客户端提供错误码。

产品基础信息 API 后续仍由其自己的 PRP 定义并实现：

- `INVALID_PAGE`
- `PAGE_SIZE_TOO_LARGE`
- `INVALID_FILTER`
- `SORT_NOT_ALLOWED`
- `LEGACY_DB_UNAVAILABLE`
- `LEGACY_QUERY_TIMEOUT`
- `DATA_SOURCE_NOT_READY`

这些不是本 Foundation PRP 的实现内容。Foundation 只提供承载模块错误码、HTTP status、安全 message/details 和 request ID 的通用机制。

## 9. HTTP Exception Handling

### 9.1 Mapping rules

- `RequestValidationError` 映射为 `VALIDATION_ERROR` / 422。
- 404 映射为 `NOT_FOUND` / 404。
- 405 映射为 `METHOD_NOT_ALLOWED`，必须保留 HTTP 405。
- 405 应保留框架提供的 `Allow` header；不得用调用方输入构造该 header。
- 401、403 和其他已知 4xx HTTPException 应保留原 HTTP status，并映射到相应 foundation code 或 `INVALID_REQUEST`。
- 其他 4xx 不得伪装成 `INTERNAL_ERROR`。
- 显式 server-side HTTPException 不得无条件改成 500；应保留安全 status，并隐藏底层 detail。
- 只有未预期、未分类的异常统一映射为 `INTERNAL_ERROR` / 500。
- 所有上述响应仍必须包含 body `request_id` 和 header `X-Request-ID`。

不得直接回显 `HTTPException.detail`、Pydantic 原始输入、异常 `str()` 或底层 traceback。实现如需保留标准响应 header，只允许经过审查的安全 header，至少覆盖 405 的 `Allow`。

### 9.2 Safe logging boundary

Foundation 可记录 request ID、HTTP method、路由模板、status、error code 和异常类型名。默认不得记录 Authorization/Cookie、完整 headers、query string、request body、DSN、SQL、原始异常 message 或业务标识。若未来需要更丰富的安全日志，应由独立 logging/security PRP 定义，不得在本实现中扩张。

## 10. Authentication Dependency Entrypoint

### 10.1 Principal contract

最小可信 Principal 应表达：

```text
user_id: non-empty string
permissions: immutable set of permission-key strings
```

- Principal 必须由后端可信认证层构造，不能由任意前端 header、query parameter、request body 或客户端状态直接构造。
- 不得硬编码业务角色名；Foundation 和业务代码只读取 permission key 与 data scope。
- Principal 负责表达身份和权限，但不得将单一全局 `allowed_store_ids` 或全局 store 标记作为所有页面、资源和模块的唯一长期授权模型。
- 具体 store scope 是针对 protected resource/page/module 的可信授权结果，必须由 data-scope resolver 按 `resource_key`、`permission_key` 和 Principal 计算；同一 Principal 在不同 resource 下可以得到不同 scope。
- Foundation 只定义可信 data-scope provider/resolver 入口，不在 Principal 上伪造临时全局店铺范围。没有可信 provider 或没有匹配授权时必须 fail closed。

### 10.2 Current fail-closed behavior

当前仓库没有真实认证系统，因此后续 Foundation 实现只提供稳定 dependency entrypoint，并在没有可信 Principal provider 时默认返回 `UNAUTHORIZED` / 401。

- 不得新增生产 `X-User-ID`、`X-Permissions`、`X-Store-IDs` 等 header 信任方案。
- 不得通过 environment flag、debug mode 或默认管理员绕过认证。
- 测试可以使用 FastAPI `dependency_overrides` 注入 synthetic Principal。
- 测试 override 只存在于测试进程和测试代码，不得成为生产 route、middleware、配置开关或后门。

本 PRP 不实现登录、Token 验证、Session、用户表、角色管理或权限配置页面。没有另行批准的可信认证 provider 时，生产受保护 endpoint 必须继续安全失败关闭。

### 10.3 Public/protected endpoint boundary

Foundation 的 public endpoint allowlist 固定包含现有 `/health`：

- `/health` 不要求认证、permission 或 data scope；
- `/health` 只返回安全的服务存活状态，不返回敏感配置、secret、数据库连接串或内部依赖详情；
- 除明确 public allowlist 外，业务 API 默认均为 protected；
- protected endpoint 没有可信 Principal 时必须返回 `UNAUTHORIZED` / 401，不得因认证系统尚未完成而默认开放；
- 业务 route 不得自行扩展 public allowlist。任何新增 public endpoint 必须由后续独立 PRP 和 Review 明确批准。

## 11. Permission Check Entrypoint

- 提供共享 `require_permission(permission_key)` dependency/factory 或项目现有等价机制。
- permission key 为后端可信常量，不接受客户端传入。
- dependency 先取得可信 Principal，再检查 `principal.permissions`。
- 无 Principal 使用 `UNAUTHORIZED`；有 Principal 但缺少 key 使用 `FORBIDDEN`。
- 权限检查应在 route dependency 或 service 调用之前完成。
- 不允许每个 route 自行散写权限判断，也不允许按角色名判断。
- 前端隐藏菜单不替代后端 permission check。

后续产品管理查看权限使用：

```text
products.product_management.view
```

列出该 key 仅用于验证 Foundation 能承载任意 permission key，不授权本 PRP 创建产品 route。

## 12. Store Data-Scope Abstraction

### 12.1 Resolver input/output

Foundation 提供纯后端 data-scope resolver。resolver 输入至少包含：

```text
principal
resource_key or page_key
permission_key
requested_store_id, optional
```

`resource_key` 是 protected resource/page/module 的 canonical key；`page_key` 如被现有项目标准采用，只能作为同一概念的命名适配，不能形成第二套 scope 体系。resolver 必须从可信后端授权 provider 取得该 Principal 在指定 resource 下的授权结果，不能从客户端声明中取得。输出至少表达：

```text
ALL       explicit global store scope
SELECTED  one or more authorized store_id values
NONE      no authorized store scope
```

业务 Repository 只能接收 resolver 的结果，不得直接信任客户端数据范围。请求 `store_id` 只可缩小范围，不能扩大范围。

后续产品基础信息 API 固定使用：

```text
resource_key = products.product_management
permission_key = products.product_management.view
```

之后只可基于 resolver 输出和 `dim_product.store_id` 收敛查询范围；不得直接读取一个跨资源通用的 `Principal.allowed_store_ids` 作为最终授权结果。

### 12.2 Fixed policy

| Trusted resource scope/request state | Required result |
|---|---|
| resource authorization explicitly grants all stores, no requested store | `ALL` |
| resource authorization explicitly grants all stores, requested store | `SELECTED` containing only that store |
| resource authorization grants selected stores, no requested store | `SELECTED` containing that authorized set |
| requested store is in the resource's selected scope | `SELECTED` containing only that store |
| requested store is outside the resource's scope | raise `DATA_SCOPE_DENIED` / 403 without revealing whether data exists |
| resource key is unknown, no matching scope exists, or trusted scope is `NONE` | raise `DATA_SCOPE_DENIED` / 403 before calling a business repository |

- 不得默认全店铺可见。
- `ALL` 必须由可信后端 provider 针对当前 `resource_key` 显式授权；客户端不能请求或切换 `ALL`，scope 缺失也不能推导为 `ALL`。
- 未知 `resource_key`、无匹配 scope 或 `NONE` 一律 fail closed；对受保护业务接口返回 `DATA_SCOPE_DENIED` / 403。
- `SELECTED` 查询只能限制在 resolver 返回的 store IDs 内。
- `store_id` 保持 source identity 语义，不自动转换为店铺名称。
- 不得使用 `store_name` 做 data scope。
- Foundation 不查询 `dim_store`、`dim_store_config` 或任何数据库表解析 scope。
- Foundation 不定义 `own`、`team`、`org_tree` 等组织解析；这些需要后续独立权限/组织 PRP。

产品基础信息 API 后续必须将该结果应用于 `dim_product.store_id`，并继续遵守其 Approved PRP；该行为不在本 PRP 中实现。

## 13. Test Utilities Boundary

后续实现允许：

- 在测试模块创建 synthetic Principal factory；
- 使用 FastAPI `dependency_overrides` 注入 Principal；
- 使用 test-only FastAPI app/route 验证通用 dependency；
- 使用 mock/fake request context；
- 每个测试结束后清除 overrides，避免测试间污染。

后续实现禁止：

- 测试读取真实 `.env` 或 secret；
- 测试连接数据库、服务器或外部 API；
- 使用真实账号、Token、业务 store ID 或生产记录；
- 在生产 app 暴露 test login、test Principal route、debug bypass 或 header-based identity；
- 让 test utility 被生产模块 import。

## 14. Backend Module Design

### API Route

不新增业务 route。只在应用入口安装共享 middleware/handlers，并用现有 public `/health` 验证 success envelope 和 request ID。`/health` 保持无需认证、permission 或 data scope，只返回安全存活状态。404/405 使用现有应用路由行为验证；auth 的 fail-closed 验证可使用 test-only protected route，不创建生产测试 endpoint。

### Pydantic Schema

定义共享 success/error envelope、error body 和可信 Principal/data-scope 值对象。业务 API 仍需声明自己的具体 request/response schema。

### Service

无业务 Service。Foundation 只提供纯权限/data-scope helper 和 FastAPI dependency。

### Repository / Model / Migration

全部不适用；不得创建。

### Integration / Celery Task

全部不适用；不得创建。

### Permission and Logging

只定义 permission-key 检查入口和最小安全日志字段；不实现 RBAC 管理、审计表或 logging platform。

### Tests

使用本地 TestClient、dependency override 和 synthetic fixtures，覆盖请求关联、envelope、HTTP exception、auth、permission 与 data scope；不接触外部系统。

## 15. Provisional Implementation File Boundary

实际实现前必须重新盘点最新 `main`。如已有同类模块，应扩展现有模块，不得创建第二套 Foundation，也不得强行重构全项目。

如果最新结构仍与当前基线一致，建议最小文件边界为：

```text
backend/app/main.py
backend/app/core/__init__.py
backend/app/core/api.py
backend/app/core/auth.py
backend/app/core/permissions.py
backend/app/core/data_scope.py
backend/tests/core/test_backend_api_foundation.py
docs/BACKEND_MODULE_CATALOG.md
```

`api.py` 可承载 request-ID middleware、共享 envelope schema/helper 和 exception handler；只有文件明显过大或现有 catalog 结构要求时，才拆分为 `responses.py`、`errors.py` 或 `request_id.py`。

Backend API Foundation 实现 PR 必须将 `docs/BACKEND_MODULE_CATALOG.md` 纳入 allowlist 并同步模块清单，这不是可选项，也不得留给后续产品 API PR。如果该文件存在，必须更新；如果实施时不存在，必须按项目规则创建，或在改动前按 Review 明确的替代路径处理。模块清单、实现文件、测试和 Review 报告统一使用 canonical module name `Backend API Foundation` 和 module key `backend-api-foundation`。

当前 PRP-authoring 分支仍只允许创建或修改 `PRPs/backend-api-foundation.md`，不得现在创建或修改模块清单。

以上只是后续实施建议，不授权当前分支创建任何这些文件。后续实现 PR 的允许范围为 `backend/**` 和 `docs/BACKEND_MODULE_CATALOG.md`，但必须从 `backend/**` 中继续排除 `backend/pyproject.toml`、`backend/uv.lock` 及所有产品业务实现。最终实施 Prompt 必须给出精确 allowlist，并保持数据库、前端、旧系统、PRPs 和 `docs/data-sources/**` 在范围外。

## 16. Implementation Plan

后续独立实现按以下顺序：

1. 重新确认 PRP 已为 `Approved` 且已合并，并盘点最新 backend 是否已有同类 foundation。
2. 定义 request-ID 安全规则、共享 envelope、基础 error code 和异常类型。
3. 安装全局 middleware/exception handlers，保持 404/405 及其他 HTTP status 的安全语义。
4. 定义 fail-closed auth dependency、Principal、permission dependency，以及按 `resource_key`/`permission_key` 解析可信授权的 store data-scope resolver。
5. 将现有 health response 对齐共享 envelope/request ID，不新增业务 endpoint。
6. 添加纯本地 foundation tests。
7. 使用 canonical name/key 同步 `docs/BACKEND_MODULE_CATALOG.md`。
8. 运行 lint、type check、pytest、rule-pack 和 Git 只读检查。

禁止从 paused combined worktree 直接复制文件。实施者可将其作为 Review 经验参考，但必须从合并后的 `main` 按本 PRP 重新实现最小、可审查的 Foundation。

## 17. Acceptance and Test Requirements

### 17.1 Request ID tests

- [ ] 无 `X-Request-ID` 时生成可验证 UUID。
- [ ] 合法 `X-Request-ID` 原值透传。
- [ ] response header 包含同一 `X-Request-ID`。
- [ ] success body 包含同一 `request_id`。
- [ ] error body 包含同一 `request_id`。
- [ ] 非安全、过长或空白 `X-Request-ID` 被替换，原值不回显。

### 17.2 Response/error tests

- [ ] success response 精确遵守 canonical envelope。
- [ ] error response 精确遵守 canonical envelope。
- [ ] FastAPI/Pydantic validation error 使用 `VALIDATION_ERROR` envelope。
- [ ] 404 使用 `NOT_FOUND` envelope 并保持 404。
- [ ] 405 使用 `METHOD_NOT_ALLOWED` envelope 并保持 405。
- [ ] 405 在框架提供时保留 `Allow` header。
- [ ] 其他 4xx 不被统一转成 500。
- [ ] 未知异常使用 `INTERNAL_ERROR` / 500。
- [ ] 未知异常和 validation details 不泄露异常文本、输入、SQL、DSN 或 secret。

### 17.3 Auth/permission tests

- [ ] 无 Principal 返回 `UNAUTHORIZED` / 401。
- [ ] Principal 缺少 permission key 返回 `FORBIDDEN` / 403。
- [ ] Principal 拥有所需 permission key 时通过 dependency。
- [ ] 不存在生产 header identity 或 debug bypass。
- [ ] test override 清理后，生产默认仍 fail closed。
- [ ] public `/health` 无认证可访问，且不返回敏感配置、secret、连接串或内部依赖详情。
- [ ] test-only protected endpoint 无认证时返回 `UNAUTHORIZED` / 401。
- [ ] 业务 route 不能在没有后续 PRP/Review 批准时自行扩展 public allowlist。

### 17.4 Data-scope tests

- [ ] 不同 `resource_key` 可以获得不同 store scope，同一 Principal 在不同 resource 下不被强制共享范围。
- [ ] 未知 `resource_key` fail closed，返回 `DATA_SCOPE_DENIED` / 403。
- [ ] 无匹配 scope 或 scope=`NONE` 时 fail closed，返回 `DATA_SCOPE_DENIED` / 403，且不调用业务 repository。
- [ ] `SELECTED` 只包含当前 resource 下可信授权的 store IDs。
- [ ] 显式授权 store 收敛为单一 `SELECTED`。
- [ ] 请求未授权 store 返回 `DATA_SCOPE_DENIED` / 403。
- [ ] 只有可信 provider 针对当前 resource 显式授权时才能获得 `ALL`。
- [ ] client 不能请求 global scope。
- [ ] data scope 不使用 `store_name`、数据库或外部服务。

### 17.5 Safety and quality gates

- [ ] 测试只使用 synthetic fixtures，不读取真实 `.env`。
- [ ] 测试不连接数据库、服务器、tunnel 或外部 API。
- [ ] 实现不新增依赖，不修改 `pyproject.toml` 或 `uv.lock`。
- [ ] 实现不执行 SQL、migration 或 Alembic。
- [ ] Ruff、mypy 和 pytest 全部通过；不得使用 skip/only 或全局 timeout 放宽规避失败。
- [ ] Rule-pack 除已知 worktree `.git` 指针误报外不得命中实现文件。

## 18. Explicit Out of Scope

本 PRP 明确不包含：

- 产品基础信息 API 实现；
- `GET /api/v1/products/basic-information` 的 route/service/repository/schema；
- legacy MySQL connection、PyMySQL 或任何数据库 driver；
- `backend/pyproject.toml`、`backend/uv.lock` 修改或依赖安装；
- 旧库查询、SQL、数据库连接或 server/tunnel；
- PostgreSQL schema、ORM model、Alembic migration、建表或数据写入；
- mart/read model、cache、snapshot 或同步任务；
- `old-system/**`、`frontend/**` 或 `docs/data-sources/**` 修改；
- Walmart、Lingxing 或任何外部业务 API；
- `store_name`、brand、category、status；
- inventory、sales、profit、ads、settlement、refund、WFS 或其他业务领域；
- 导出、导入、批量操作、AI summary 或 AI recommendation；
- 登录页面、Token 颁发/验证、用户/角色/权限数据库、组织树解析或权限管理 UI；
- rule-pack 脚本修复、CI、部署或生产配置。

## 19. Implementation-Stage Forbidden Actions

即使本 PRP 后续获批，Foundation 实现阶段仍禁止：

实现 PR 只允许修改经 Prompt 精确限定的 `backend/**` 文件和必须同步的 `docs/BACKEND_MODULE_CATALOG.md`；其中 `backend/pyproject.toml`、`backend/uv.lock` 和产品业务模块仍不在允许范围内。

- 实现任何产品业务 API 或 legacy MySQL connection；
- 修改 `backend/pyproject.toml`、`backend/uv.lock`、PRPs 或 `docs/data-sources/**`；
- 连接数据库/服务器、打开 tunnel、执行 SQL 或 migration；
- 创建 ORM model、表、repository、mart/read model 或 Celery task；
- 修改 frontend、old-system、CI、部署或生产配置；
- 调用外部业务 API；
- 写入或读取真实 secret、`.env`、Token、密码或连接串；
- 信任客户端 header 作为生产 Principal；
- 修改 rule-pack 脚本以消除业务分支失败；
- 执行 git add、commit、push、PR、merge 或其他 Git 写操作。

任何一项成为实现必需条件时，必须停止并返回架构师/负责人，不得扩大本 PRP。

## 20. Relationship to Product Basic Information API

- Backend API Foundation 是产品基础信息 API 的阻塞前置条件。
- Foundation PRP 合并只允许创建独立 Foundation 实现任务，不等于产品 API 可以直接实现。
- Foundation 实现 PR 经 Review 并合并到 `main` 后，产品基础信息 API 才可继续。
- 产品 API 仍必须完整遵守 `PRPs/phase-2a-product-basic-information-query-api.md`，不得复用 paused combined branch 作为批准依据。
- Legacy readonly connection、fixed platform、PyMySQL、`uv.lock`、`dim_product` 查询、产品 warnings 和业务错误码仍属于后续产品/legacy 实现范围。
- 如果届时仍无可信生产认证 provider，受保护 endpoint 必须保持 fail closed；本 Foundation 不授权临时 header 认证。

## 21. Validation Gates for Later Implementation

后续实现至少执行：

```bash
cd backend
uv run ruff check .
uv run mypy app tests
uv run pytest -q
cd ..
bash scripts/check-rule-pack.sh
git diff --check
git status --short --untracked-files=all
git diff --stat
```

验证命令不得触发数据库、外部 API、migration、依赖升级或部署。若本地工具缺失，实施者不得自行联网安装，应如实报告阻塞并由负责人决定环境准备方式。

## 22. Rollback Boundary

当前 PRP-authoring 分支的回滚仅为负责人放弃这一个未跟踪 PRP 文件。合并后的文档回滚使用普通 docs-only revert。

后续 Foundation 实现不创建数据库或外部状态。产品 API 尚未依赖它时，可通过移除 middleware/handler 注册及新增 core 文件回滚；一旦已有消费方，必须先回滚或兼容处理消费方，再移除 Foundation，避免破坏共享响应和安全依赖。

## 23. Execution Role and Skill Boundary

```text
Main implementation role: Backend Engineer
```

后续实施 Prompt 可在本 PRP 文件和系统边界内分配：

- `engineering-minimal-change-engineer`：控制最小改动；
- `engineering-backend-architect`：解释共享边界，不替代负责人批准；
- `testing-api-tester`：仅使用本地 TestClient/mock，不访问真实系统；
- `testing-evidence-collector`：仅收集本地非敏感验证结果。

Skill 不产生额外文件、数据库、外部 API、Git、部署或 secret 权限。任何 Skill 与本 PRP 冲突时，以项目规则和负责人指令为准。

## 24. Owner Approval Checklist

- [ ] 确认本文件在 Review 前保持 `Draft`。
- [ ] 确认 Foundation 只覆盖 request ID、envelope、exception、auth dependency、permission 和 data scope。
- [ ] 确认基础错误码与业务模块扩展方式。
- [ ] 确认 405 保持 405 并保留安全 `Allow` header。
- [ ] 确认无真实认证 provider 时生产默认 fail closed。
- [ ] 确认 `/health` 是无需 auth/permission/data scope 的安全 public endpoint，其他 protected endpoint 默认 fail closed。
- [ ] 确认 store scope 按 resource 解析；`ALL` 必须针对当前 resource 显式授予，未知/空/`NONE` scope 和显式越权均返回 `DATA_SCOPE_DENIED`。
- [ ] 确认实现 PR 必须使用 canonical name/key 同步 `docs/BACKEND_MODULE_CATALOG.md`。
- [ ] 确认不新增依赖且不修改 `pyproject.toml` 或 `uv.lock`。
- [ ] 确认不包含产品 API、legacy connection、数据库、前端或业务数据。
- [ ] 确认实施前必须重新盘点最新 `main` 并使用独立实现分支。
- [ ] Architect Review PASS 后，将 `Status` 改为 `Approved` 再合并；不得从 Draft 执行。

## 25. PRP-Authoring Validation

本分支只创建 `PRPs/backend-api-foundation.md`，不运行 backend tests，因为没有后端代码变化。

```bash
git status --short --untracked-files=all
git diff --check
bash scripts/check-rule-pack.sh
sed -n '1,260p' PRPs/backend-api-foundation.md
sed -n '261,520p' PRPs/backend-api-foundation.md
```

如果 rule-pack 只因 worktree `.git` 指针路径命中，记录为已知误报，不修改脚本。本 PRP 出现任何其他命中时必须修正后再交付。

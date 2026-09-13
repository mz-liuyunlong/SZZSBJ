# Product Management Preview Auth V1 PRP

## 1. Approval

```text
PRP Status: Approved — Owner Authorized for Implementation
Implementation Authorized: Yes
Source Decision Gate: APPROVED_BY_OWNER_DECISION
Main Role: Backend Engineer
Branch: feat/product-management-preview-auth
Source Decision: docs/data-sources/decisions/product-management-preview-auth-decision.md
```

本 PRP 记录负责人于 2026-09-14 批准的临时 Product Management Preview Auth
例外。该例外不修改 `PRPs/backend-api-foundation.md` 的全局安全基线，也不把
header identity 扩展为通用认证方案。

## 2. Goal and Why

Product Management BFF 已保持 protected-by-default，但真实认证、权限和数据范围
provider 尚未接入。前端需要在 new backend service 上受控联调已存在的 Product Management
页面，因此增加一个默认关闭、显式配置、路径受限且可删除的临时认证入口。

接口不能直接公开，也不能关闭 `enforce_protected_by_default` 或扩展
`PUBLIC_ENDPOINT_PATHS`，否则会把临时联调需求变成全局认证绕过。

## 3. Scope

### In scope

- `backend/app/core/config.py` 中三个默认关闭/空值的 Preview 配置项。
- `backend/app/core/auth.py` 中仅限 Product Management 路径的 header 认证适配。
- 复用现有 `Principal`、permission dependency、Product scope provider 和
  source-account scope provider seam。
- synthetic/mock-only 后端测试。
- 本 PRP、Source Decision 和 Task Registry 登记。

### Out of scope

- 公开 Product Management 路由或修改 public allowlist。
- 完整登录、会话、RBAC、组织权限或长期认证方案。
- 前端、旧系统、生产服务器配置、部署或生产验证。
- 数据库 schema、migration、SQL、RAW 或业务数据写入。
- Lingxing/Walmart、Token 请求、真实同步或外部 API。
- export 权限、全局管理员权限或其他业务模块访问。

## 4. Configuration Contract

| Setting | Environment variable | Default | Rule |
|---|---|---|---|
| `product_management_preview_auth_enabled` | `PRODUCT_MANAGEMENT_PREVIEW_AUTH_ENABLED` | `false` | 必须显式开启 |
| `product_management_preview_auth_token` | `PRODUCT_MANAGEMENT_PREVIEW_AUTH_TOKEN` | unset | `SecretStr`；启用时非空值至少 32 字符，且不得记录或回显 |
| `product_management_preview_source_account_refs` | `PRODUCT_MANAGEMENT_PREVIEW_SOURCE_ACCOUNT_REFS` | unset | 英文逗号分隔；strip、去空、去重 |

不开启、token 缺失或 token 不匹配时均返回现有 `UNAUTHORIZED` / 401。启用时若提供的非空
token 少于 32 字符或不是 ASCII，必须以不含输入值的安全配置错误拒绝，并保持路由 fail closed。
非 ASCII 错误 Header 必须安全返回 `UNAUTHORIZED` / 401，不得导致 500。refs 缺失或解析后为空时，所有
Preview 路径（包括 `/api/product-management/options`）均返回 `DATA_SCOPE_DENIED` / 403，
不得推导为全量范围。

## 5. Authentication and Permission Contract

请求使用 `X-Product-Management-Preview-Token`。仅当 feature flag 开启、配置存在、header 与配置
通过 `secrets.compare_digest` 完全匹配且 path 位于下列范围时创建 Preview Principal：

- `/api/product-management/` 前缀；
- `/api/user-table-views/product-management` 精确路径。

Principal 固定为非业务账号 `frontend-preview`，仅授予：

- `products:read`
- `products:pricing_rules:read`
- `products:table_views:update`
- `products:cost:read`

不授予 `products:export`、全局管理员权限或其他模块权限。现有
`require_permission`、Product scope 和 source-account scope 校验不得绕过。

## 6. Data Scope Contract

- Product scope provider 仅在 Preview Auth 配置有效且解析出非空 source-account refs 时，
  允许 `frontend-preview` 访问 canonical resource `product_management`。
- Source-account provider 只向同一 Preview Principal 返回配置解析出的非空
  `frozenset`。
- 其他 principal、其他 resource、缺 token 配置或空 refs 均 fail closed。
- 代码、文档、响应和日志不得包含真实 source-account ref。

## 7. Safety and Lifecycle

- Token 不进入代码、文档、日志、响应、测试快照或 Git。
- Source-account refs 不进入代码、文档、日志、响应或 Git。
- 本实现不新增 route，不修改 `/health`，不修改 `PUBLIC_ENDPOINT_PATHS`，不移除
  `enforce_protected_by_default`。
- 部署边界仅适用于 port 8010 preview deployment；不得影响旧 8000 服务。本 PRP 不授权部署或
  修改任何服务器配置。
- 真实认证、权限和数据范围 provider 接入后，必须先关闭 feature flag，再删除 Preview
  Auth 配置、header 分支、scope provider 例外及其专用测试。

## 8. Validation

- 默认关闭、无 header、错误 header 均为 401；`/health` 仍为 200。
- 正确 header 仅在批准路径创建 Preview Principal，其他业务路径仍为 401。
- options/list/pricing-rules 依照既有 permission/scope 校验；export 仍为 403。
- 空 refs 使所有 Preview 路径（含 options）返回 `DATA_SCOPE_DENIED` / 403；逗号输入正确
  strip、去空和去重。
- Token 使用 `SecretStr`，启用时非空值至少 32 字符；repr、model dump、JSON、验证错误和
  HTTP 响应均不得包含原始 token。
- Token 配置必须为 ASCII；比较使用 ASCII bytes 的 `secrets.compare_digest`，非 ASCII 错误
  Header 安全返回 `UNAUTHORIZED` / 401。
- 响应、日志和 diff 不包含 token、真实账号、RAW 或业务数据。
- 运行 compileall、Ruff、mypy、pytest、Alembic heads、diff/rule-pack/scope/secret/RAW
  检查。

## 9. Rollback

不设置或移除 `PRODUCT_MANAGEMENT_PREVIEW_AUTH_ENABLED` 即恢复原有 fail-closed 行为。代码回滚只删除
本 PRP 批准的三个配置项、认证适配和两个 scope provider 例外；不改变业务 API、数据库
或全局安全基线。

## 10. Stop Conditions

- 需要扩大到批准路径之外、加入 public allowlist 或绕过 permission/scope。
- 需要真实账号值、真实密钥、数据库/服务器连接、外部 API、Token 或同步。
- 需要修改 frontend、old-system、migration、依赖或生产配置。
- 当前 worktree、branch 或 allowlist 与本 PRP 不一致。

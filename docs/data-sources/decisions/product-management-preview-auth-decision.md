# Source Decision: Product Management Preview Auth V1

## Decision status

```text
Decision: APPROVED_BY_OWNER_DECISION
Implementation Authorized: Yes
Decision date: 2026-09-14
Implementation branch: feat/product-management-preview-auth
Approved PRP: PRPs/product-management-preview-auth-v1.md
```

## Context

Product Management BFF 已保持默认受保护，但真实认证、权限和数据范围 provider 尚未接入。
前端需要对现有 Product Management 页面进行临时联调。直接公开接口、关闭
`enforce_protected_by_default` 或扩展 `PUBLIC_ENDPOINT_PATHS` 均会破坏全局安全基线，
因此不获批准。

## Owner decision

负责人批准一个临时、默认关闭、显式配置、仅限 Product Management 的 Preview Auth
例外：

1. 仅识别 `X-Product-Management-Preview-Token`，并使用安全的精确比较。
2. 仅允许 `/api/product-management/` 前缀和
   `/api/user-table-views/product-management` 精确路径。
3. 只创建非业务 Preview Principal `frontend-preview`，只授予 PRP 列明的最小权限。
4. Product scope 只允许 canonical resource `product_management`。
5. Source-account scope 只来自部署环境显式提供的逗号分隔 refs；缺失或为空时，所有
   Preview 路径（包括 `/api/product-management/options`）均返回 `DATA_SCOPE_DENIED` / 403，
   不得返回全量。
6. Preview token 使用 `SecretStr`；启用时提供的非空 token 必须为 ASCII 且不少于 32 字符，
   否则以安全配置错误拒绝。比较使用 ASCII bytes；非 ASCII 错误 Header 返回
   `UNAUTHORIZED` / 401，不得导致 500。配置/验证错误、日志、repr、model dump、JSON 和
   HTTP 响应均不得包含原始值。
7. 默认关闭；feature flag、token 或 scope 条件任一不满足时继续 fail closed。

## Global baseline remains unchanged

- 不修改 `PRPs/backend-api-foundation.md`。
- 不修改 `PUBLIC_ENDPOINT_PATHS`；`/health` 仍是唯一公开路径。
- 不移除或绕过 `enforce_protected_by_default`、`require_permission` 或既有 data-scope
  dependency。
- 该例外不是可复用的 header identity、debug login、长期认证或全局管理员入口。

## Secret and data boundary

- Preview token 仅由部署环境注入；不得写入代码、文档、日志、响应、测试快照或 Git。
- Source-account refs 仅由部署环境注入；不得写死、记录、回显或提交。
- 不读取或返回 RAW、provider payload、真实商品字段或其他账号数据。
- 不授权 Lingxing/Walmart、Token 请求、真实同步、数据库变更或数据写入。

## Deployment boundary

该设计只可用于 port 8010 preview deployment 的 Product Management 前端联调，不能影响旧 8000
服务。本决策只授权代码实现和本地 synthetic/mock 验证，不授权修改服务器配置、部署或
生产调用。

## Closure and deletion condition

真实认证、permission provider 与 Product/source-account data-scope provider 接入后：

1. 先关闭 Preview Auth feature flag；
2. 验证 Product Management 通过真实身份链路工作；
3. 删除 Preview header 认证分支、三个 Preview 配置项、两个 scope provider 例外和专用
   测试；
4. 不保留兼容 fallback 或长期 debug bypass。

## Explicitly not authorized

- 公开业务接口或修改 public allowlist；
- frontend、admin-frontend、old-system 修改；
- 生产配置修改、部署、服务器/数据库连接或 migration；
- Lingxing/Walmart、Token、真实同步、RAW 或业务数据写入；
- export、全局管理员权限或批准路径之外的访问。

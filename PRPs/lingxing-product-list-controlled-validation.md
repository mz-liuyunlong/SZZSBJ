# PRP: Lingxing productList Controlled Validation Gate

Status: `Blocked — Pending Official Endpoint Evidence`

Owner Approval Required: `Pending official endpoint contract evidence and renewed Owner review`

Implementation Allowed: `No`

Real Business API Validation Allowed: `No`

Main Execution Role After Approval: `Backend Engineer` (`Validation Engineer` is a work mode, not a separate project role)

## 1. 目标

判断 `/erp/sc/routing/data/local_inventory/productList` 是否可以成为第一个 Lingxing controlled business API validation 目标，并在证据充分后为以下两步建立严格 gate：

1. 独立后端 PR 先实现单 endpoint、mock-only contract。
2. mock implementation 合并并复审通过后，由负责人另行批准单 endpoint controlled validation。

本 PRP 当前仅记录阻塞状态，不授权任何一步实现或真实调用。

## 2. 背景与依赖

- PR #48 已合并 Lingxing Token Manager Backend MVP。
- PR #49 已完成并合并 GetToken/RefreshToken 脱敏 controlled validation。
- PR #51 已合并 readonly business client 与 Token Manager 的 mock-only 集成。
- 当前 `LingxingReadonlyClient` 不包含本 endpoint；不得绕过 endpoint contract 直接调用。
- 证据基线：`docs/integrations/lingxing-product-list-endpoint-evidence.md`。

## 3. Gate 决定

当前离线派生索引只能确认候选 path、`POST`、候选字段、offset/length 分页以及候选响应结构。它没有提供足以安全实现的官方 Content-Type、参数位置、完整 required-field 规则、scope 语义和可执行限流契约。

因此本 PRP 保持 `Blocked`：

- 不批准 backend implementation。
- 不批准向 `_ENDPOINT_CONTRACTS` 增加本 endpoint。
- 不批准真实 productList 调用。
- 不批准 P0 sampling。

## 4. 解除阻塞所需证据

必须由独立 docs-only 官方 endpoint 取证任务补齐并由架构师复审：

- endpoint path、method、Content-Type 和参数位置；
- allowed/required fields、类型、默认值、组合规则；
- pagination 起点、页大小边界及单页最小请求；
- store/seller/tenant scope 语义；
- success code、response data location、错误码；
- rate limit、权限及额外签名要求。

如果任何关键项仍未确认，状态继续保持 `Blocked`。

## 5. 未来可批准的 mock-only implementation 上限

本节只描述未来状态更新为 `Approved` 后可考虑的上限，不构成当前授权：

- 只在现有 Lingxing readonly client 增加本 endpoint 的精确 contract。
- 只使用 fake Token Manager、synthetic values 和 `httpx.MockTransport`。
- 严禁 absolute URL、额外字段、query/body 混用和未获批 scope。
- 强制单页；页大小使用官方 contract 允许的最小正值且不得超过 `3`。
- `LINGXING_ENABLE_REAL_CALLS=false` 时必须在 token/transport 前 fail closed。
- 不写 RAW、DB 或 Redis，不接 frontend/API router，不新增其他 endpoint。

未来后端实现必须由负责人另行下发 implementation Prompt；不能把本 PRP 的状态变化视作自动开工授权。

## 6. 未来 controlled validation 上限

只有 mock-only implementation 合并、复审通过且负责人再次明确授权后，才能考虑：

- 只调用 `/erp/sc/routing/data/local_inventory/productList`。
- 只执行一页、官方允许的最小页大小。
- 不扩大到其他 P0 endpoint。
- 不写 RAW、DB 或 Redis。
- 不输出业务明细、完整请求/响应、Token、Authorization 或其他 secret。
- 不接 frontend/API router，不启动同步或历史回补。

## 7. 当前允许修改

本 docs-only gate 仅允许：

- `PRPs/lingxing-product-list-controlled-validation.md`
- `docs/integrations/lingxing-product-list-endpoint-evidence.md`
- `docs/tasks/TASK_REGISTRY.md`
- `docs/data-registry/DATA_INTERFACE_REGISTRY.md`
- `docs/BACKEND_MODULE_CATALOG.md`

## 8. 当前明确禁止

- 修改任何 backend/frontend/admin-frontend/old-system 文件。
- 请求真实 Token 或调用任何 Lingxing 业务 API。
- P0 endpoint sampling。
- 读取 `.env`、凭据或 secret 文件。
- RAW、DB、Redis 写入或数据库/服务器连接。
- 新 endpoint、endpoint contract 扩展、frontend/API router、sync、migration 或依赖变更。

## 9. Acceptance Criteria

- [x] 当前 client 不包含本 endpoint 的事实已记录。
- [x] 离线候选证据与官方证据缺口已分开记录。
- [x] 状态保持 `Blocked`，未批准实现或真实验证。
- [x] productList gate 的 Registry/catalog 记录未标记 implemented，PR/merge 保持 TBD。
- [x] 未修改代码，未调用 API，未读取或记录 secret。
- [ ] 官方 endpoint contract 已补齐并通过架构师复审。
- [ ] 负责人将 gate 明确更新为 `Approved`。
- [ ] 负责人另行下发 mock-only backend implementation Prompt。

## 10. 下一步

创建独立 docs-only 官方 endpoint 取证任务，获取并脱敏记录 `/docs/Product/ProductLists.md` 的完整 contract。证据复审前，不得开始后端实现或 controlled validation。

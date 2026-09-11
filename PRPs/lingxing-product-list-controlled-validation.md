# PRP: Lingxing ProductLists Controlled Validation Gate

Status: `Evidence Captured — Pending Owner Review`

Owner Approval Required: `Yes`

Implementation Allowed: `No until separate Owner Approval Gate`

Real Business API Validation Allowed: `No`

Main Execution Role After Approval: `Backend Engineer` (`Validation Engineer` is a work mode, not a separate project role)

## 1. 目标

基于领星官方 ProductLists 页面和通用接入指南，判断 `/erp/sc/routing/data/local_inventory/productList` 是否适合作为第一个 controlled business API validation 目标，并为未来两步建立边界：

1. 独立后端 PR 先实现单 endpoint、mock-only contract 与官方业务认证/签名契约。
2. mock-only implementation 合并并复审通过后，由负责人另行批准单 endpoint controlled validation。

本 PRP 当前只记录证据和待决策项，不授权实现或真实调用。

## 2. 背景与依赖

- PR #48 已合并 Lingxing Token Manager Backend MVP。
- PR #49 已完成并合并 GetToken/RefreshToken 脱敏 controlled validation。
- PR #51 已合并 readonly business client 与 Token Manager 的 mock-only 集成。
- PR #52 记录本 endpoint 因缺少官方证据而阻塞。
- 官方证据现已记录在 `docs/integrations/lingxing-product-list-endpoint-evidence.md`。
- 当前 `LingxingReadonlyClient` 仍不包含本 endpoint；不得绕过 endpoint contract 直接调用。

## 3. 已确认的官方 contract

| 项目 | 结论 |
|---|---|
| Path | `/erp/sc/routing/data/local_inventory/productList` |
| Protocol / method | HTTPS / `POST` |
| Business parameters | `application/json` body |
| Public authentication | Query Params：`access_token`、`app_key`、`timestamp`、`sign` |
| Business fields | `offset`, `length`, four create/update time bounds, `sku_list`, `sku_identifier_list` |
| Required business fields | 官方页面全部标为非必填；不等于空 body 已验证 |
| Pagination | `offset` 默认 `0` 且不得为负；`length` 默认/最大 `1000`，最小正值未说明 |
| Explicit scope fields | 未列 store/seller/company/warehouse 字段 |
| Success envelope | `code = 0`; top-level `data` array and `total` int |
| Rate limit | endpoint token bucket capacity `1`; dimension `appId + 接口 URL`; rate-limit code `3001008` |
| Extra signing | `timestamp` 与 `sign` 必需；未见 nonce |

## 4. 当前阻塞的 Owner/架构决策

官方 endpoint evidence 已捕获，但以下事项必须在任何实现前由 Owner 明确决定：

1. 是否批准新增本 endpoint 的 mock-only contract。
2. 如何处理官方 Query Params + signature 契约与当前 client header-only 认证路径的差异；不得假定现有 header 等价。
3. 是否由独立通用 business request signer/auth task 先实现 `app_key/timestamp/sign`，还是与本 endpoint 的 mock-only contract 同一受限 PRP 实现。
4. 无显式 store scope 字段时，是否接受账号级数据范围；需要何种安全证明和输出限制。
5. future controlled validation 的正整数 `length` 取值；项目上限必须 `<= 3`，但官方未声明最小值。
6. 响应中超出产品基础身份范围的字段必须丢弃、仅验证字段存在性还是允许脱敏聚合；默认不得输出或落库。

Owner 未解决以上边界前，状态不得改为 `Approved`。

## 5. 未来 mock-only implementation 上限

本节只描述 separate Owner Approval Gate 可能批准的最大范围，不构成当前授权：

- 只在现有 Lingxing readonly client 增加本 endpoint 的精确 contract。
- 只使用 fake Token Manager、synthetic values 和 `httpx.MockTransport`。
- 精确允许官方列出的 JSON body 字段，禁止额外字段和 query/body 混用。
- 业务 body 强制 `offset = 0`、正整数 `length <= 3`，并只允许一次请求。
- 认证与签名必须按另行批准的官方 contract 实现；不得继续假定 header-only 认证有效。
- `LINGXING_ENABLE_REAL_CALLS=false` 时必须在 token/signing/transport 前 fail closed。
- 不写 RAW、DB 或 Redis，不接 frontend/API router，不新增其他 endpoint。
- 不读取 `.env`，不把认证材料写入日志、异常、test output、RAW envelope 或 docs。

未来后端实现必须由负责人另行下发 implementation Prompt。

## 6. 未来 controlled validation 上限

只有 mock-only implementation 合并、复审通过且负责人再次明确授权后，才能考虑：

- 只调用 `/erp/sc/routing/data/local_inventory/productList`。
- 只发送一次请求，使用 `offset = 0` 和 Owner 批准的正整数 `length <= 3`。
- 不扩大到其他 P0 endpoint。
- 不写 RAW、DB 或 Redis。
- 不输出业务明细、完整请求/响应、认证 query、Token、signature 或其他 secret。
- 不接 frontend/API router，不启动同步或历史回补。
- 一旦出现 scope 不明、响应过大、未批准字段、权限错误或限流，立即停止并只记录脱敏结果。

## 7. 安全边界

- 官方业务认证参数位于 URL query，后续实现必须防止 URL、query、exception、HTTP trace 和 access log 泄露认证材料。
- Token/AppSecret/signature 不得进入 RAW、DB、Redis、logs、docs、test snapshots 或 exception text。
- ProductLists 响应可能包含成本、供应商、负责人等超出当前批准范围的字段；默认不得保存、输出或转换。
- 本 PRP 不授权真实 Token 请求、真实业务 API、数据库/服务器连接、P0 sampling 或 secret 读取。

## 8. 当前允许修改

本 docs-only evidence task 仅允许：

- `PRPs/lingxing-product-list-controlled-validation.md`
- `docs/integrations/lingxing-product-list-endpoint-evidence.md`
- `docs/tasks/TASK_REGISTRY.md`
- `docs/data-registry/DATA_INTERFACE_REGISTRY.md`
- `docs/BACKEND_MODULE_CATALOG.md`

## 9. 当前明确禁止

- 修改任何 backend/frontend/admin-frontend/old-system 文件。
- 请求真实 Token 或调用任何 Lingxing 业务 API。
- ProductLists controlled validation 或其他 P0 endpoint sampling。
- 读取 `.env`、凭据或 secret 文件。
- RAW、DB、Redis 写入或数据库/服务器连接。
- endpoint contract 实现、business signer 实现、frontend/API router、sync、migration 或依赖变更。

## 10. Acceptance Criteria

- [x] 官方 ProductLists 原始页面已找到并记录来源。
- [x] endpoint path、method、JSON body、字段、分页、成功 envelope 和 rate-limit 证据已摘要记录。
- [x] 官方业务公共 Query Params 与签名要求已记录。
- [x] 未确认的最小页长、scope、字段组合和错误 catalog 没有被猜测为事实。
- [x] 当前 client 与官方认证契约的差异已标为 Owner/架构决策点。
- [x] 状态为 `Evidence Captured — Pending Owner Review`，未批准实现或真实验证。
- [x] Registry/catalog 未标记 implemented，PR/merge 保持 TBD。
- [x] 未修改代码，未调用 API，未读取或记录 secret。
- [ ] Owner 完成 evidence review 并通过独立 approval gate。
- [ ] 负责人另行下发 mock-only backend implementation Prompt。
- [ ] mock-only implementation 合并后，负责人另行批准 controlled validation。

## 11. 下一步

Owner/架构师只读复审本官方证据，先决定业务请求认证/签名架构、账号级 scope 边界和最小验证参数。只有独立 approval gate 明确批准后，才能创建 mock-only backend implementation task；真实 ProductLists 调用仍需后续单独 controlled validation authorization。

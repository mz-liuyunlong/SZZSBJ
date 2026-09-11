# PRP: Lingxing ProductLists Controlled Validation Gate

Status: `Blocked — Pending Query-Sign Auth Evidence`

Owner Approval Required: `Pending complete official query-sign evidence and renewed Owner review`

Implementation Allowed: `No`

Real Business API Validation Allowed: `No`

Main Execution Role After Approval: `Backend Engineer` (`Validation Engineer` is a work mode, not a separate project role)

## 1. 目标

复审 `/erp/sc/routing/data/local_inventory/productList` 的官方 endpoint evidence，判断是否可以批准下一轮 backend mock-only implementation：

1. ProductLists JSON body endpoint contract。
2. 官方 Query Params auth/sign adapter。
3. Lingxing Token Manager 提供的 access token 参与 query auth。
4. MockTransport 与 synthetic signing tests。

Owner Review 结论：ProductLists endpoint contract 本身已有足够证据进入 mock contract 设计，但 query-sign auth 证据仍不完整，因此上述组合 implementation gate 当前不得批准。

## 2. 背景与依赖

- PR #48 已合并 Lingxing Token Manager Backend MVP。
- PR #49 已完成并合并 GetToken/RefreshToken 脱敏 controlled validation。
- PR #51 已合并 readonly business client 与 Token Manager 的 mock-only 集成。
- PR #52 记录本 endpoint 因缺少官方证据而阻塞。
- PR #53 已合并 ProductLists 官方 endpoint evidence，状态推进至 Owner Review。
- Evidence：`docs/integrations/lingxing-product-list-endpoint-evidence.md`。
- 当前 `LingxingReadonlyClient` 仍不包含本 endpoint，并使用 header-only 认证路径；不得绕过 endpoint contract 直接调用。

## 3. ProductLists contract Review

以下证据足以支持未来精确的 mock-only endpoint contract：

| 项目 | Review 结论 |
|---|---|
| Path | `/erp/sc/routing/data/local_inventory/productList` |
| Protocol / method | HTTPS / `POST` |
| Business parameters | `application/json` body |
| Allowed body fields | `offset`, `length`, four create/update time bounds, `sku_list`, `sku_identifier_list` |
| Required body fields | 官方页面全部标为非必填；mock contract 不得据此假定空 body 已验证 |
| Pagination | `offset` 默认 `0` 且不得为负；`length` 默认/最大 `1000`，官方未说明最小正值 |
| Explicit scope fields | 未列 store/seller/company/warehouse 字段；不得伪造 store scope 字段 |
| Success envelope | `code = 0`; top-level `data` array and `total` int |
| Rate limit | endpoint token bucket capacity `1`; dimension `appId + 接口 URL`; rate-limit code `3001008` |

结论：上述证据只足以说明 endpoint body/envelope contract 可以进入后续 mock-only 设计，不足以批准真实业务 API validation。

## 4. Query-sign auth Review

当前仓库证据只确认：

- 业务 API 的公共参数包括 `access_token`、`app_key`、`timestamp`、`sign`，通过 Query Params 传递。
- `access_token` 应由已合并的 `LingxingTokenManager` 提供。
- `timestamp` 必须按请求生成，旧签名不得复用。
- `sign` 传输时需要 URL encoding。
- ProductLists 页面未见 `nonce`。

当前仓库证据没有完整记录以下实现必需事实：

1. `app_key` 的官方来源映射，以及它与现有安全配置字段的精确关系。
2. 参与签名的全部字段集合与 canonical ordering 规则。
3. 空字符串、null、布尔、数字、数组和嵌套 JSON 的 canonical serialization 规则。
4. 拼接格式、字符编码、摘要算法及大小写规则。
5. 二次加密/编码步骤、算法、模式、padding、密钥来源和最终输出编码。
6. Query Params 的最终 URL encoding 顺序及签名前后编码边界。
7. 官方可复核的脱敏签名测试向量或等价示例。

缺少这些证据时实现 signing helper 会依赖猜测，因此 query-sign adapter 和 combined implementation gate 必须 fail closed。

## 5. Owner Review 决定

- ProductLists JSON body endpoint contract：证据足够进入未来 mock-only implementation proposal。
- Query Params auth/sign adapter：证据不足，不批准实现。
- Combined backend implementation gate：`Blocked — Pending Query-Sign Auth Evidence`。
- Real Business API Validation：不批准，必须保留为后续独立任务。
- P0 endpoint sampling：不批准。
- Registry/catalog：只能标记 `blocked`，PR 与 merge commit 保持 `TBD`。

本次 Review 不允许把 ProductLists endpoint contract 单独塞入现有 client，也不允许先写不完整 signer 再补证据。

## 6. 解除阻塞条件

必须先完成新的 docs-only 官方 query-sign 取证，并由 Owner/架构师重新 Review：

- 官方页面与复核日期。
- `app_key` 的来源和安全配置映射。
- 完整签名输入、排序、序列化、摘要、加密、padding、encoding 与 URL encoding 规则。
- 数组/嵌套 body 的签名规则。
- 不包含真实 credential 的官方或等价 synthetic test vector。
- 签名材料的 secret boundary、日志/异常/query/RAW 脱敏要求。

证据合并后仍需独立 Owner Approval Gate；即使未来 gate 改为 Approved，也必须等待负责人另行下发 backend implementation Prompt。

## 7. 当前允许修改

本 docs-only Owner Review task 仅允许：

- `PRPs/lingxing-product-list-controlled-validation.md`
- `docs/integrations/lingxing-product-list-endpoint-evidence.md` 的 Owner Review note
- `docs/tasks/TASK_REGISTRY.md`
- `docs/data-registry/DATA_INTERFACE_REGISTRY.md`
- `docs/BACKEND_MODULE_CATALOG.md`

## 8. 当前明确禁止

- 修改任何 backend/frontend/admin-frontend/old-system 文件。
- 实现 ProductLists endpoint contract 或 query-sign adapter。
- 请求真实 Token 或调用任何 Lingxing 业务 API。
- ProductLists controlled validation 或其他 P0 endpoint sampling。
- 读取 `.env`、凭据或 secret 文件。
- RAW、DB、Redis 写入或数据库/服务器连接。
- frontend/API router、service 接入、sync、migration 或依赖变更。
- 将认证 query、Token、signature 或 secret 写入 envelope、日志、异常、文档或测试输出。

## 9. Acceptance Criteria

- [x] PR #53 的官方 ProductLists endpoint evidence 已复审。
- [x] ProductLists body/envelope contract 与 query-sign auth 证据充分性已分别判断。
- [x] 缺失的 signing algorithm 与 `app_key` 来源证据已明确列出。
- [x] 状态为 `Blocked — Pending Query-Sign Auth Evidence`。
- [x] Backend implementation 和 Real Business API Validation 均为 `No`。
- [x] Registry/catalog 未标记 approved 或 implemented，PR/merge 保持 TBD。
- [x] 未修改代码，未调用 API，未读取或记录 secret。
- [ ] 完整官方 query-sign evidence 已通过独立 docs-only PR 合并。
- [ ] Owner 完成 renewed approval gate。
- [ ] 负责人另行下发 mock-only backend implementation Prompt。
- [ ] mock-only implementation 合并后，负责人另行批准 controlled validation。

## 10. 下一步

创建独立 docs-only query-sign auth evidence 任务，只补齐签名算法、`app_key` 来源、复杂 body canonicalization 和脱敏 synthetic test vector。证据完成并经 renewed Owner Review 前，不得开始后端实现或真实 ProductLists validation。

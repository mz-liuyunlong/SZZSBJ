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
- Query-sign evidence：`docs/integrations/lingxing-query-sign-auth-evidence.md`（官方高层算法证据已捕获，但 contract 仍不完整）。
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

官方接入指南现已确认：

- 业务 API 的公共参数包括 `access_token`、`app_key`、`timestamp`、`sign`，通过 Query Params 传递。
- `app_key` 的官方来源为应用 APP ID；Token 表单字段 `appId` 与业务 query 字段 `app_key` 使用不同协议名称。
- `access_token` 应由已合并的 `LingxingTokenManager` 提供。
- 签名输入包括全部业务请求参数以及 `access_token`、`app_key`、`timestamp`；`sign` 是输出，不参与自身签名。
- 官方页面要求按其所写的 `ASII` 顺序排序，以 `key=value` 和 `&` 拼接；空值不参与，`null` 参与。
- body 集合需转为字符串后参与签名，但未定义确定性序列化格式。
- 拼接结果执行 32 位 MD5 并转大写，再以 appId 为 key 执行 AES/ECB/PKCS5PADDING。
- `sign` 生成后需要 URL encoding。
- `timestamp` 必须按请求生成；固定 timestamp 的签名有效期为 2 分钟，不得缓存。
- ProductLists 页面未见 `nonce`。

官方证据仍没有完整记录以下实现必需事实：

1. 官方 `ASII` 表述对应的精确 comparator、大小写和非 ASCII key 规则。
2. 空字符串、空数组、空对象、`null`、布尔、数字、数组和嵌套 JSON 的逐字节 canonical serialization。
3. 拼接字符串的字符编码。
4. AES 结果的最终输出编码，以及是否存在额外包装步骤。
5. timestamp 的正式单位、时区和服务端容差。
6. 官方可复核且不含可复用 credential 的 expected-sign 测试向量。

缺少这些证据时实现 signing helper 会依赖猜测，因此 query-sign adapter 和 combined implementation gate 必须 fail closed。

## 5. Owner Review 决定

- ProductLists JSON body endpoint contract：证据足够进入未来 mock-only implementation proposal。
- Query Params auth/sign adapter：高层算法证据已捕获，但确定性 contract 仍不足，不批准实现。
- Combined backend implementation gate：`Blocked — Pending Query-Sign Auth Evidence`。
- Real Business API Validation：不批准，必须保留为后续独立任务。
- P0 endpoint sampling：不批准。
- Registry/catalog：只能标记 `blocked`，PR 与 merge commit 保持 `TBD`。

本次 Review 不允许把 ProductLists endpoint contract 单独塞入现有 client，也不允许先写不完整 signer 再补证据。

## 6. 解除阻塞条件

必须先完成新的 docs-only 官方 query-sign 取证，并由 Owner/架构师重新 Review：

- 官方 SDK、官方签名实现或官方支持证据的来源与复核日期。
- 精确排序 comparator、字符编码和 timestamp 单位/时区。
- 空值、`null`、数组与嵌套 body 的逐字节 canonical serialization。
- AES 结果的最终输出编码及任何附加编码步骤。
- 不包含可复用 credential 的官方 expected-sign test vector。
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
- [x] 官方高层签名算法和 `app_key` 来源已完成 docs-only 取证，剩余确定性 contract 缺口已明确列出。
- [x] 状态为 `Blocked — Pending Query-Sign Auth Evidence`。
- [x] Backend implementation 和 Real Business API Validation 均为 `No`。
- [x] Registry/catalog 未标记 approved 或 implemented，PR/merge 保持 TBD。
- [x] 未修改代码，未调用 API，未读取或记录 secret。
- [ ] 完整官方 query-sign evidence 已通过独立 docs-only PR 合并。
- [ ] Owner 完成 renewed approval gate。
- [ ] 负责人另行下发 mock-only backend implementation Prompt。
- [ ] mock-only implementation 合并后，负责人另行批准 controlled validation。

## 10. 下一步

继续以独立 docs-only evidence 任务从官方 SDK、官方签名实现或官方支持回复补齐复杂 body canonicalization、AES 输出编码、timestamp 单位/时区、精确排序 comparator 和非密钥 expected-sign vector。证据完成并经 renewed Owner Review 前，不得开始后端实现或真实 ProductLists validation。

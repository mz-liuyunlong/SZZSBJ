# Lingxing productList Endpoint Evidence

Status: `Blocked — Pending Official Endpoint Evidence`

Evidence review date: `2026-09-11`

## 1. 文档定位

本文只记录 `/erp/sc/routing/data/local_inventory/productList` 在当前仓库中的离线证据及缺口，用于判断是否可以进入受控业务 API 验证。本文不是官方 endpoint contract，不授权后端实现、真实 Token 请求或真实业务 API 调用。

当前仓库的 `docs/integrations/lingxing-walmart-openapi/normalized/` 是负责人提供资料包的派生索引，不是官方事实权威；其引用的原始页面 `/docs/Product/ProductLists.md` 未导入仓库。因此，派生字段只能作为候选线索，不能单独批准出站请求契约。

## 2. 当前仓库事实

- `LingxingReadonlyClient` 的 endpoint 类型和 `_ENDPOINT_CONTRACTS` 均不包含本 endpoint。
- 当前 client 会在 transport 调用前拒绝未登记 endpoint，禁止使用任意路径、absolute URL 或其他方式绕过 contract。
- PR #51 只完成现有 approved readonly client 与 Token Manager 的 mock-only 集成；未新增本 endpoint，也未执行真实业务 API 验证。

## 3. 当前离线证据

| 项目 | 当前仓库证据 | 证据状态 |
|---|---|---|
| Interface ID | `LX-3F1F087FF8A1` | 派生索引确认 |
| Interface name | 查询本地产品列表 | 派生索引确认 |
| Endpoint path | `/erp/sc/routing/data/local_inventory/productList` | 派生索引确认 |
| HTTP method | `POST` | 派生索引确认 |
| Source document reference | `/docs/Product/ProductLists.md` | 仅有引用；原始页面不在仓库 |
| Content-Type | 当前仓库资料未记录 | `NEEDS_OFFICIAL_EVIDENCE` |
| Parameter location | 当前仓库资料未确认 query、form 或 JSON body | `NEEDS_OFFICIAL_EVIDENCE` |
| Request fields | `offset`, `length`, `sku_list`, `sku_identifier_list`, `create_time_start`, `create_time_end`, `update_time_start`, `update_time_end` | 派生索引候选，需官方页面复核 |
| Required fields | 派生索引把上述字段均标为非必填 | 需官方页面复核；不得据此假定空 body 有效 |
| Pagination | `offset` 默认 `0`；`length` 默认/上限 `1000` | 派生索引候选，需官方页面复核 |
| Store/seller scope | 派生请求参数中没有 store/seller scope 字段 | 不证明 endpoint 无需租户/店铺边界 |
| Response success code | `code = 0` 表示成功 | 派生索引候选，需官方示例复核 |
| Response data location | `data` array；`total` 为总数 | 派生索引候选，需官方示例复核 |
| Rate limit | 接口索引记录 token bucket capacity `1` | 缺少单位、维度与运行含义，不足以制定调用频率 |
| Verification status | 文档已收录、未验证；账号权限、分页、频控、字段、数据范围和错误码待确认 | 明确阻塞 |
| Forbidden-list check | 未在 exact-path / interface-ID 禁止清单中定位到匹配项 | 不等于 approved |

离线索引显示 `length` 是整数且上限为 `1000`，因此未来可以提出单页、小页验证方案；但当前资料没有确认官方允许的最小正整数、参数承载位置或空筛选条件语义。不能仅凭索引把 `length = 1` 写成已确认 contract。

## 4. 证据缺口

进入 mock-only endpoint contract 实现前，必须从官方 `ProductLists` 页面或等价可验证官方来源补齐：

1. 精确 endpoint path 与 HTTP method。
2. Content-Type。
3. 每个参数的承载位置，以及是否允许 query/body 混用。
4. 完整请求字段、类型、必填条件、默认值和互斥/组合规则。
5. 分页起点、最小/最大 `length`、单页请求的正确表达。
6. endpoint 的企业、店铺或卖家 scope 语义；若没有显式 store 字段，必须说明权限范围如何由服务端确定。
7. 成功码、响应 envelope、`data`/`total` 位置及典型错误码。
8. 令牌桶容量的准确含义、调用频率或退避要求。
9. 账号权限前置条件和是否存在额外签名/timestamp 要求。

官方证据必须以脱敏摘要记录，不复制整篇文档，不记录访问凭据、AppSecret、Token、Authorization 或可复用请求值。

## 5. Gate 结论

- official/local evidence not found in current repo docs in a form sufficient to define the complete outbound contract.
- implementation not allowed until official endpoint contract is obtained.
- 当前状态为 `Blocked — Pending Official Endpoint Evidence`。
- 不批准修改 `_ENDPOINT_CONTRACTS`，不批准 mock-only endpoint 实现，也不批准真实 API validation。
- 当前只允许后续创建/执行独立 docs-only 官方 endpoint 取证任务。

补齐官方证据后，负责人和架构师必须重新复审本证据文档与 `PRPs/lingxing-product-list-controlled-validation.md`。只有 gate 明确更新为 `Approved`，并由负责人另行下发后端 implementation Prompt，才能实现单 endpoint mock contract；真实 controlled validation 仍需再由负责人单独授权。

## 6. 明确未执行

- 未修改 backend、frontend、admin-frontend 或 old-system。
- 未请求真实 access token 或 refresh token。
- 未调用本 endpoint 或任何 Lingxing 业务 API。
- 未进行 P0 endpoint sampling。
- 未写 RAW、数据库或 Redis。
- 未读取 `.env` 或任何 secret 文件。


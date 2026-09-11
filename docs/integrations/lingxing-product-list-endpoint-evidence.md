# Lingxing ProductLists 官方 Endpoint Evidence

Status: `Evidence Captured — Pending Owner Review`

Evidence capture date: `2026-09-11`

## 1. 文档定位

本文记录领星官方文档中“查询本地产品列表（ProductLists）”的 endpoint contract 摘要，作为后续 Owner/架构 Review 的证据输入。本文不是 implementation approval，不授权修改 `LingxingReadonlyClient`、调用真实业务 API、执行 P0 sampling 或写入 RAW/DB/Redis。

官方来源：

- ProductLists：<https://apidoc.lingxing.com/#/docs/Product/ProductLists>
- 领星 API 接入指南：<https://apidoc.lingxing.com/#/docs/Guidance/newInstructions>

本次只读取官方文档页面。文档访问凭据、AppSecret、Token、Authorization 和官方示例中的业务值均未写入本文或仓库。

## 2. 当前仓库事实

- 当前 `LingxingReadonlyClient` 的 endpoint contract 不包含本 endpoint，任何实现前仍必须先新增精确、fail-closed 的 mock-only contract。
- 当前 client 使用内部构造的认证 header；官方通用接入指南则要求业务接口的 `access_token`、`app_key`、`timestamp`、`sign` 作为 Query Params。两者存在契约差异，不能在本 docs-only 任务中假定兼容或自行修正。
- PR #51 只完成现有 approved readonly client 与 Token Manager 的 mock-only 集成；未新增本 endpoint，也未验证真实业务 API。

## 3. 官方 endpoint contract 摘要

| 项目 | 官方证据 | 结论 |
|---|---|---|
| 页面 | 查询本地产品列表（ProductLists） | 已定位官方原始页面 |
| Endpoint path | `/erp/sc/routing/data/local_inventory/productList` | 已确认 |
| Protocol | HTTPS | 已确认 |
| HTTP method | `POST` | 已确认 |
| Business parameter location | 页面请求示例为 JSON object；通用指南说明无特殊说明时 body 参数使用 JSON | JSON body |
| Content-Type | 通用指南要求 JSON body 设置 `Content-Type: application/json` | 已确认，来源为通用指南 |
| Public auth parameter location | 通用指南要求 `access_token`、`app_key`、`timestamp`、`sign` 使用 Query Params | 已确认；不是 endpoint JSON body 字段 |
| Additional signing | 业务参数与三个固定参数参与签名；`sign` 需 URL encode；固定时间戳生成的签名有效期很短，不应缓存 | `sign` 与 `timestamp` 必需；未见 `nonce` |
| Success code | 成功示例为顶层 `code = 0` | 已确认 |
| Response collection | 顶层 `data`，类型为 array | 已确认 |
| Response total | 顶层 `total`，类型为 int | 已确认 |
| Rate limit | 页面标注 token bucket capacity `1`；通用指南说明维度为 `appId + 接口 URL`，令牌桶无可用令牌时返回 `3001008` | 已确认容量和维度；不是“每分钟 1 次” |

## 4. 请求字段

官方页面列出的业务请求字段如下；均标为非必填。该事实不等于官方保证空 body 可用。

| 字段 | 类型 | 官方语义 | 必填 | 默认/边界 |
|---|---|---|---|---|
| `offset` | int | 分页偏移 | No | 默认 `0`；失败示例表明不得为负数 |
| `length` | int | 单次返回数量 | No | 默认 `1000`；最大 `1000`；未说明最小正值 |
| `update_time_start` | int | 更新时间起点，秒级时间戳 | No | 左闭右开区间起点 |
| `update_time_end` | int | 更新时间终点，秒级时间戳 | No | 左闭右开区间终点 |
| `create_time_start` | int | 创建时间起点，秒级时间戳 | No | 左闭右开区间起点 |
| `create_time_end` | int | 创建时间终点，秒级时间戳 | No | 左闭右开区间终点 |
| `sku_list` | array | 本地产品 SKU 列表 | No | 数组元素约束未单独说明 |
| `sku_identifier_list` | array | SKU 标识列表 | No | 数组元素约束未单独说明 |

官方页面没有列出：

- `store_id`、seller、company、warehouse 等显式 scope 字段；这不证明 endpoint 无租户/账号数据范围。
- 名为 `msku` 的筛选字段。
- 时间字段必须成对出现、时间过滤与 SKU 过滤互斥等组合规则。
- `length` 的最小正值。

未写明的规则必须保持“官方文档未确认”，不得由 normalized 索引、旧代码或经验补写成官方事实。

## 5. 响应与错误证据

| 字段/情况 | 官方证据 | 风险说明 |
|---|---|---|
| `code` | 顶层 required int；成功示例为 `0` | mock contract 必须按本业务 endpoint 的成功码处理，不能复用 Token endpoint 的成功码规则 |
| `message` | 顶层 required string | 不得将完整 provider payload 拼入异常或日志 |
| `error_details` | 字段表列为 array；失败示例展示了不同形态 | 解析必须容忍 provider schema 漂移，并保持安全失败 |
| `request_id` | 顶层 required string | 可作为脱敏追踪线索，不替代本系统 trace id |
| `response_time` | 顶层 required string | 仅为 provider response metadata |
| `total` | 顶层 required int | 总数位置已确认 |
| `data` | 顶层 required array | 列表位置已确认；本任务不复制响应业务明细 |
| `list` / `items` | 官方 envelope 未列这两个集合路径 | 列表直接位于顶层 `data` |
| 非法 `offset` 示例 | 官方失败示例返回 `code = 500` | 这是示例，不是完整 endpoint error-code catalog |
| 请求过频 | 通用指南给出 `3001008` | 后续真实验证必须 fail closed，不得重试风暴 |

官方页面列出的产品响应字段范围较广，包含基础产品、成本、供应商、负责人等信息。本取证只确认 envelope 与列表位置，不授权采集、输出或落库超出未来批准范围的字段。

## 6. 最小受控验证可行性

从官方 contract 可确认：

- `offset = 0` 是官方默认起点，且不得为负数。
- `length` 上限为 `1000`，因此项目可在未来 gate 中施加更严格的本地上限 `length <= 3`。
- 单页应由“一次请求后停止”控制；endpoint 没有独立 `page` 或 `max_pages` 字段。

但官方页面未说明 `length` 的最小正值，因此本任务不能把 `length = 1` 写成已由官方验证。Owner 后续若批准 controlled validation，应明确采用正整数小页请求，并把实际可接受性作为单 endpoint 验证结果，而不是当前事实。

## 7. 关键风险与待 Owner 决策

1. **认证契约差异**：官方指南要求 Query Params 中的 access token、app key、timestamp 和 signature；当前 client 的 header-only 认证路径不能直接视为符合官方 contract。需要单独的架构/Owner 决策和 mock-only 实现边界。
2. **敏感 Query Params**：认证材料位于 URL query 时更容易进入 access log、异常、trace 或 RAW。后续实现必须在发送、日志、异常、测试 capture 和 RAW envelope 处完整脱敏。
3. **Scope 未显式声明**：endpoint 没有 store/seller/company/warehouse 字段。必须确认账号授权范围及是否接受企业级结果；不能伪造 store allowlist 字段。
4. **返回字段超范围**：响应包含本任务未批准的敏感业务字段。未来 validation 只能记录 envelope/字段存在性和脱敏聚合，不得输出业务明细。
5. **请求组合未说明**：空 body、时间字段配对、SKU 数组长度和组合语义仍未由官方页面确认。
6. **错误 schema 漂移**：`error_details` 的字段表与示例形态不一致，客户端必须安全解析。

## 8. Gate 结论

- 官方 ProductLists 原始页面已找到，endpoint contract 核心证据已捕获。
- 状态更新为 `Evidence Captured — Pending Owner Review`。
- 本状态不等于 `Approved`、`implemented` 或真实 API 已验证。
- 当前仍禁止修改 `_ENDPOINT_CONTRACTS`、调用真实 ProductLists、执行 P0 sampling 或写入 RAW/DB/Redis。
- 下一步必须由 Owner/架构师审查认证/签名差异、scope 风险和最小验证参数，再决定是否创建独立 mock-only implementation approval gate。
- mock-only contract 合并并复审通过后，真实 controlled validation 仍需另一项明确 Owner 授权。

## 9. 明确未执行

- 未修改 backend、frontend、admin-frontend 或 old-system。
- 未请求真实 access token 或 refresh token。
- 未调用 ProductLists 或任何 Lingxing 业务 API。
- 未执行 P0 endpoint sampling。
- 未写 RAW、数据库或 Redis。
- 未读取 `.env` 或任何 secret 文件。

## 10. Owner Review note

Owner/架构 Review date: `2026-09-11`

- ProductLists 的 path、method、JSON body 字段、分页边界、成功 envelope 与限流证据足以支持未来 mock-only endpoint contract proposal。
- 本文只记录了公共 Query Params、`sign` 参与要求和 URL encoding，没有记录可直接实现的完整签名算法、复杂 body canonicalization 或 `app_key` 来源映射。
- 因签名实现仍会依赖猜测，`PRPs/lingxing-product-list-controlled-validation.md` 更新为 `Blocked — Pending Query-Sign Auth Evidence`。
- 本 Review note 不改变既有官方证据，不批准 backend implementation、真实业务 API validation 或 P0 endpoint sampling。
